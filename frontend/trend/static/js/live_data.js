/* 실데이터 공급기 — 화면이 난수 대신 AWS RDS 값을 쓰게 한다.
 *
 * ══════════════════════════════════════════════════════════
 *  왜 이게 필요한가
 * ══════════════════════════════════════════════════════════
 * `chart_engine.js` 는 지금까지 `gSeries()` 로 **씨드 난수**를 그렸다.
 * 이름을 씨앗으로 고정해서 "언제 봐도 같은 그림"이 나오게 만든 것이라,
 * 데이터가 하나도 없어도 화면은 멀쩡해 보였다. 이게 제일 위험하다 —
 * 보는 사람은 그게 진짜 측정값인 줄 안다.
 *
 * 그래서 규칙을 바꾼다:
 *
 *     값이 있으면 → 그 값을 그린다
 *     값이 없으면 → **'측정 불가'라고 적는다.** 난수로 채우지 않는다
 *
 * ══════════════════════════════════════════════════════════
 *  왜 미리 받아 두나 (동기 조회가 필요하다)
 * ══════════════════════════════════════════════════════════
 * `gChart()` 는 동기 함수다. 그 안에서 await 를 하려면 차트를 그리는
 * 모든 자리를 async 로 바꿔야 하는데, 그건 화면 전체를 흔드는 일이다.
 * 대신 **탭을 열 때 미리 받아 두고**, 그릴 때는 캐시에서 꺼내 쓴다.
 */

const CACHE = new Map();   // term → {status, reason, byDate:Map, unavailable}
/* 담아 두는 시간.
   값이 있거나 아직 없는 것(ok·empty)은 5분 — 적재가 도는 주기보다 짧게.

   ★ 실패는 15초만 담는다. 두 가지를 **동시에** 지켜야 하기 때문이다:
     · 안 담으면 stateOf() 가 'unknown' 이라 화면이 **난수로 되돌아간다.**
       DB 가 죽었는데 그럴듯한 숫자가 뜨는, 제일 나쁜 상태다.
     · 오래 담으면 서버를 고치고 다시 눌러도 옛 오류가 계속 뜬다.
   그래서 짧게 담고, 사람이 직접 누르면 force 로 무시한다. */
const TTL_MS = 5 * 60 * 1000;
const TTL_ERR_MS = 15 * 1000;
const INFLIGHT = new Map();

/** 지표가 실제로 있는 용어 목록 (검색 후보). 없으면 빈 배열. */
export let AVAILABLE_TERMS = [];

/**
 * 이 용어의 지표를 받아 둔다. 그리기 전에 한 번 부른다.
 * 같은 용어를 여러 번 불러도 요청은 한 번만 나간다.
 */
export async function prime(term, days = 400, opts = {}) {
  const key = String(term || '').trim();
  if (!key) return null;
  const hit = CACHE.get(key);
  const ttl = hit && hit.status === 'error' ? TTL_ERR_MS : TTL_MS;
  /* force = 사람이 직접 조회를 눌렀다. 방금 실패했어도 시키는 대로 다시 묻는다. */
  if (!opts.force && hit && Date.now() - (hit.at || 0) < ttl) return hit;
  if (hit) CACHE.delete(key);          // 오래됐거나 다시 하라고 했다
  if (INFLIGHT.has(key)) return INFLIGHT.get(key);

  const p = (async () => {
    const url = `/api/trend?term=${encodeURIComponent(key)}&days=${days}`;
    let out;
    /* ★ 실패를 뭉뚱그리지 않는다.
       예전엔 무엇이 잘못됐든 "닿지 못했습니다" 한 마디였다. 그러면
       ① 서버가 안 떴다 ② 주소가 틀렸다(404) ③ 서버가 터졌다(500)
       ④ 프록시가 엉뚱한 데로 보냈다 를 구별할 수가 없다.
       고칠 방법이 각각 다른데 화면은 똑같이 말하니 헤매게 된다. */
    try {
      const r = await fetch(url);
      if (!r.ok) {
        return finish({
          status: 'error',
          reason: `지표 API 가 ${r.status} 를 돌려줬습니다.`,
          detail:
            r.status === 404
              ? `${url} 주소가 없습니다. 개발 중이면 vite 를 다시 켜 보세요 ` +
                `(프록시 설정이 바뀌었습니다). 배포본이면 BACKEND_API_URL 을 확인하세요.`
              : `백엔드 로그에 무슨 일이 있었는지 남아 있습니다.`,
          byDate: null,
          unavailable: null,
        });
      }
      const text = await r.text();
      try {
        out = toEntry(JSON.parse(text));
      } catch (_) {
        /* JSON 이 아니면 대개 프록시가 엉뚱한 곳(HTML 을 주는 서버)으로 보낸 것이다. */
        return finish({
          status: 'error',
          reason: '지표 API 가 JSON 이 아닌 것을 돌려줬습니다.',
          detail: `앞 40자: ${text.slice(0, 40).replace(/\s+/g, ' ')}`,
          byDate: null,
          unavailable: null,
        });
      }
    } catch (e) {
      out = {
        status: 'error',
        reason: '지표 서버에 연결하지 못했습니다.',
        detail:
          '백엔드가 떠 있는지 확인하세요 — backend에서 Django 서버를 실행하세요. ' +
          '떠 있는데도 이러면 vite 를 다시 켜 보세요(프록시 설정이 바뀌었습니다).',
        byDate: null,
        unavailable: null,
      };
    }
    /* ★ 실패는 담아 두지 않는다.
       예전엔 오류도 캐시해서, 서버를 고치고 같은 말을 다시 검색해도
       **계속 옛 오류가 떴다.** 고쳤는데 화면이 안 바뀌면 뭘 더 해야 할지 모른다.
       값이 있거나(ok) 아직 없는 것(empty)만 담고, 그것도 5분이면 잊는다 —
       적재는 하루에도 몇 번 도니까. */
    return finish(out);

    function finish(v) {
      v.at = Date.now();
      CACHE.set(key, v);
      INFLIGHT.delete(key);
      return v;
    }
  })();

  INFLIGHT.set(key, p);
  return p;
}

function toEntry(j) {
  if (!j || j.status === 'error') {
    return { status: 'error', reason: (j && j.reason) || '알 수 없는 오류', byDate: null, unavailable: null };
  }
  if (j.status === 'empty') {
    return { status: 'empty', reason: j.reason || '측정된 자료가 없습니다.', byDate: null, unavailable: null };
  }
  const byDate = new Map();
  for (const p of j.data.series) byDate.set(p.date, p);
  return {
    status: 'ok',
    reason: '',
    byDate,
    facet: j.data.facet,
    term: j.data.term,
    asOf: j.data.as_of || null,
    data: j.data,                          // platforms · new_terms 등 시계열 밖의 값
    unavailable: j.unavailable || null,   // temp·momentum 처럼 RDS 에 없는 값
  };
}

/** 용어 캐시 항목 그대로 (platforms · new_terms 를 꺼낼 때) */
export function entryOf(term) {
  return CACHE.get(String(term || '').trim()) || null;
}

/* ── URL 단위 캐시 ──────────────────────────────────────────
 * 연관어(/api/assoc) · 할인률(/api/discount) · 리세일(/api/resale) · 수명주기(/api/lifecycle)
 * 는 용어 하나의 시계열이 아니라 조건(스타일·종류·브랜드·아이템명)마다 다른 답이다.
 * 같은 규칙(ok·empty 5분 / error 15초 / 동시 요청 한 번)으로 URL 을 키로 담는다. */
const URL_CACHE = new Map();
const URL_INFLIGHT = new Map();

export function stateOfUrl(url) {
  return URL_CACHE.get(url) || { status: 'unknown', reason: '아직 확인하지 않았습니다.' };
}

/* 온보딩 가이드가 저장된 예시 응답을 기존 렌더러로 보여 줄 때만 쓴다.
 * 네트워크를 호출하지 않고 기존 캐시 자리에 잠시 얹으며, 반환된 함수를
 * 실행하면 사용자가 가이드를 열기 전 캐시 상태로 정확히 되돌아간다. */
export function installGuideDemo({ trends = [], urls = [] } = {}) {
  const beforeTrend = trends.map(({ term }) => [term, CACHE.has(term), CACHE.get(term)]);
  const beforeUrl = urls.map(({ url }) => [url, URL_CACHE.has(url), URL_CACHE.get(url)]);
  trends.forEach(({ term, payload }) => {
    const entry = toEntry(payload);
    entry.at = Date.now();
    CACHE.set(String(term || '').trim(), entry);
  });
  urls.forEach(({ url, payload }) => URL_CACHE.set(url, {
    status: 'ok', reason: '', data: payload.data, extra: payload, at: Date.now(), guideDemo: true,
  }));
  return () => {
    beforeTrend.forEach(([key, had, value]) => had ? CACHE.set(key, value) : CACHE.delete(key));
    beforeUrl.forEach(([key, had, value]) => had ? URL_CACHE.set(key, value) : URL_CACHE.delete(key));
  };
}

export function sentimentUrl(term, facet = '') {
  const p = new URLSearchParams({ term: String(term || ''), days: '400' });
  if (facet === '브랜드' || facet === 'BRAND') p.set('subject', 'brand');
  return '/api/sentiment?' + p.toString();
}

export async function primeUrl(url, opts = {}) {
  const hit = URL_CACHE.get(url);
  const ttl = hit && hit.status === 'error' ? TTL_ERR_MS : TTL_MS;
  if (!opts.force && hit && Date.now() - (hit.at || 0) < ttl) return hit;
  if (URL_INFLIGHT.has(url)) return URL_INFLIGHT.get(url);
  const p = (async () => {
    let out;
    try {
      const r = await fetch(url);
      const text = await r.text();
      if (!r.ok) {
        out = { status: 'error', reason: `지표 API 가 ${r.status} 를 돌려줬습니다.`,
                detail: r.status === 404 ? `${url.split('?')[0]} 주소가 없습니다. 백엔드를 최신으로 올렸는지 확인하세요.`
                                         : '백엔드 로그를 확인하세요.' };
      } else {
        let j = null;
        try { j = JSON.parse(text); } catch (_) {
          out = { status: 'error', reason: '지표 API 가 JSON 이 아닌 것을 돌려줬습니다.',
                  detail: `앞 40자: ${text.slice(0, 40).replace(/\s+/g, ' ')}` };
        }
        if (j) {
          out = j.status === 'ok'
            ? { status: 'ok', reason: '', data: j.data, extra: j }
            : { status: j.status === 'empty' ? 'empty' : 'error',
                reason: j.reason || '측정된 자료가 없습니다.' };
        }
      }
    } catch (e) {
      out = { status: 'error', reason: '지표 서버에 연결하지 못했습니다.',
              detail: '백엔드(Django :8000)가 떠 있는지 확인하세요.' };
    }
    out.at = Date.now();
    URL_CACHE.set(url, out);
    URL_INFLIGHT.delete(url);
    return out;
  })();
  URL_INFLIGHT.set(url, p);
  return p;
}

/** 지금 이 용어가 어떤 상태인가 — 그리기 전에 확인한다. */
export function stateOf(term) {
  const e = CACHE.get(String(term || '').trim());
  if (!e) return { status: 'unknown', reason: '아직 확인하지 않았습니다.' };
  return e;
}

/**
 * 차트가 쓸 0~1 배열을 만든다. 값이 없으면 **null 을 돌려준다.**
 *
 * ★ 0 으로 채우지 않는다. 0 은 "측정했는데 0이었다"는 뜻이고,
 *   여기 상황은 "측정하지 못했다"라서 완전히 다른 말이다.
 *
 * @param field 'mention' | 'score' | 'temp' …  (RDS 에 없으면 null)
 */
export function seriesOf(term, { points = 30, step = 'd', field = 'mention', raw = false, agg = 'avg', fill = true } = {}) {
  const e = CACHE.get(String(term || '').trim());
  if (!e || e.status !== 'ok' || !e.byDate) return null;
  return resample(e.byDate, { points, step, field, raw, agg, fill });
}

/**
 * 날짜별 행 배열 → 차트 계열. 할인률·리세일·수명주기처럼 용어 캐시 밖의 자료가 쓴다.
 * @param rows [{date:'YYYY-MM-DD', …}]
 */
export function seriesFromRows(rows, { points = 30, step = 'd', field = 'value', raw = true, agg = 'avg', fill = true } = {}) {
  if (!Array.isArray(rows) || !rows.length) return null;
  const byDate = new Map();
  for (const r of rows) if (r && r.date) byDate.set(String(r.date).slice(0, 10), r);
  return resample(byDate, { points, step, field, raw, agg, fill });
}

/** 가장 마지막 날짜 — 적재가 오늘보다 늦을 수 있으므로 눈금은 여기를 끝으로 잡는다. */
export function lastDateOf(byDateOrRows) {
  const keys = byDateOrRows instanceof Map ? [...byDateOrRows.keys()]
    : (byDateOrRows || []).map((r) => String(r.date).slice(0, 10));
  return keys.length ? keys.sort().pop() : null;
}

/* agg  — 주·월 구간을 한 값으로 줄이는 법. 'avg'(비율·온도) | 'sum'(건수)
   fill — 빈 자리를 앞뒤 값으로 이을지. 건수 막대는 false:
          없는 구간에 옆 막대를 복사해 세우면 없던 반응을 지어낸 그림이 된다. 빈 칸(null)으로 둔다. */
function resample(byDate, { points, step, field, raw, agg = 'avg', fill = true }) {
  const out = [];
  const endIso = lastDateOf(byDate);
  const end = endIso ? new Date(endIso + 'T00:00:00Z') : new Date();
  for (let i = points - 1; i >= 0; i--) {
    const d = new Date(end);
    if (step === 'd') d.setUTCDate(d.getUTCDate() - i);
    else if (step === 'w') d.setUTCDate(d.getUTCDate() - i * 7);
    else d.setUTCMonth(d.getUTCMonth() - i);
    out.push(pickNear(byDate, d, step, field, agg));
  }
  // 한 점도 못 찾았으면 그릴 게 없다.
  if (!out.some((v) => v !== null)) return null;
  if (!fill) return out;

  // 빈 자리는 앞뒤 값으로 잇는다 — 없는 날을 0 으로 떨어뜨리면
  // 그래프가 바닥을 치는 것처럼 보여서 거짓말이 된다.
  let last = null;
  const filled = out.map((v) => (v === null ? last : (last = v)));
  const nums = out.filter((v) => v !== null);
  const lo = Math.min(...nums);
  for (let i = filled.length - 1; i >= 0; i--) if (filled[i] === null) filled[i] = filled[i + 1] ?? lo;
  if (raw) return filled;

  // 0~1 로 눕힌다 (예전 호출부 호환).
  const hi = Math.max(...nums);
  const span = hi - lo || 1;
  return filled.map((v) => (v - lo) / span);
}

/** 그 날짜(또는 그 구간)의 값. 주·월이면 구간 안 평균. */
function pickNear(byDate, d, step, field, agg = 'avg') {
  const iso = (x) => x.toISOString().slice(0, 10);
  if (step === 'd') {
    const p = byDate.get(iso(d));
    return p ? numOr(p[field]) : null;
  }
  const back = step === 'w' ? 7 : 30;
  const vals = [];
  for (let k = 0; k < back; k++) {
    const t = new Date(d);
    t.setUTCDate(t.getUTCDate() - k);
    const p = byDate.get(iso(t));
    const v = p ? numOr(p[field]) : null;
    if (v !== null) vals.push(v);
  }
  if (!vals.length) return null;
  const total = vals.reduce((a, b) => a + b, 0);
  return agg === 'sum' ? total : total / vals.length;
}

function numOr(v) {
  return v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v);
}

/** 지표가 있는 용어 목록을 한 번 받아 둔다. */
export async function loadAvailableTerms() {
  try {
    const j = await fetch('/api/trend').then((r) => r.json());
    AVAILABLE_TERMS = j.status === 'ok' ? j.data : [];
    return { status: j.status, reason: j.reason || '', terms: AVAILABLE_TERMS };
  } catch (e) {
    AVAILABLE_TERMS = [];
    return { status: 'error', reason: '지표 서버에 닿지 못했습니다.', terms: [] };
  }
}

/**
 * '측정 불가' 안내 HTML.
 * 실존 클래스만 쓴다 — `.note` (trend/static/css/weekly_report.css).
 */
export function unavailableHTML(reason, extra) {
  /* ★ 제목은 태그이고 사유는 사람이 쓴 글이다.
     예전엔 둘 다 esc() 를 먹여서 `<b>측정 불가</b>` 가 글자 그대로 떴다.
     태그는 우리가 쓴 것이니 그대로 두고, **바깥에서 온 글만** 이스케이프한다. */
  const 몸 = [esc(reason || '이 값은 아직 측정된 자료가 없습니다.')];
  if (extra) 몸.push(esc(extra));
  return '<div class="note"><i>◆</i><span><b>측정 불가</b><br>' +
         몸.join('<br>') + '</span></div>';
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (m) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}


/* ── 화면이 쓰는 요약값 ────────────────────────────────────
 * 다이얼·배지·문구가 쓰는 숫자를 시계열에서 뽑아 준다.
 *
 * ★ 여기서 지표를 **새로 만들지 않는다.**
 *   temp·momentum·level 은 크롤러가 계산해 둔 값을 그대로 읽는다.
 *   설계서(FEEDiT_지표계산_설계서.md)가 정의의 원본이고, 두 곳에서 계산하면
 *   화면과 챗봇이 다른 숫자를 말하게 된다.
 *
 *   여기서 하는 건 '읽은 값끼리의 뺄셈'뿐이다 — 지난주 대비, 작년 대비.
 *   그건 같은 표의 두 행을 비교하는 것이라 정의가 갈릴 여지가 없다.
 *
 * ★ 못 구하는 값은 **null** 이다. 0 도 아니고 지어낸 수도 아니다.
 *   부르는 쪽이 그 자리를 '측정 불가'로 그린다.
 */
export function summaryOf(term) {
  const e = CACHE.get(String(term || '').trim());
  if (!e || e.status !== 'ok' || !e.byDate) return null;

  const rows = [...e.byDate.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map((x) => x[1]);
  if (!rows.length) return null;
  const last = rows[rows.length - 1];

  // 며칠 전 행 — 정확히 그날이 없으면 가장 가까운 앞 날짜를 쓴다.
  const back = (days) => {
    const want = new Date(last.date);
    want.setDate(want.getDate() - days);
    const iso = want.toISOString().slice(0, 10);
    let best = null;
    for (const r of rows) if (r.date <= iso) best = r;
    return best;
  };

  const diff = (days, field) => {
    const then = back(days);
    if (!then) return null;
    const a = num(then[field]);
    const b = num(last[field]);
    return a === null || b === null ? null : b - a;
  };

  const missing = [];
  const need = (v, name) => { if (v === null || v === undefined) missing.push(name); return v ?? null; };

  return {
    asOf: last.date,
    /* 화면에 띄우는 기준일은 DB 최신화 일자로 통일한다 (2026-09-21) */
    dataAsOf: (e.data && e.data.data_as_of) || last.date,
    points: rows.length,
    temp: need(num(last.temp), '온도'),
    momentum: need(num(last.momentum), '가속'),
    level: need(num(last.level), '수준'),
    mention: num(last.mention),
    // 점유율은 크롤러가 metrics.share_pct 로 넣어 준다.
    share: num(last.share_pct ?? last.share),
    wk: diff(7, 'mention'),          // 지난주 대비 언급량
    mo: diff(28, 'mention'),         // 4주 전 대비
    yoy: diff(365, 'mention'),       // 작년 대비 — 자료가 1년치 있어야 나온다
    yoyPct: pctDiff(back(365), last, 'mention'),   // 같은 값의 % 표현
    tempWk: diff(7, 'temp'),
    missing,
    /* 시계열이 짧으면 비교값을 믿으면 안 된다.
       설계서가 정한 최소 관측(28일 10건)을 그대로 쓴다. */
    thin: rows.length < 10,
  };
}

function num(v) {
  return v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v);
}

/** 두 행의 같은 칸 사이 변화율(%). 기준이 없거나 0 이면 null. */
function pctDiff(then, now, field) {
  if (!then || !now) return null;
  const a = num(then[field]);
  const b = num(now[field]);
  return a === null || b === null || a === 0 ? null : ((b - a) / a) * 100;
}
