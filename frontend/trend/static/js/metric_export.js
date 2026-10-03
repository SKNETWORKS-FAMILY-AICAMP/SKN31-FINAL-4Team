/* ══════════════════════════════════════════════════════
   EDIT 지표 내려받기 — 엑셀(.xlsx) 시트 구성 (2026-10-02)

   언급량·온도 / 연관어 / 긍부정 / 수명주기 / 할인률 변화 / 리세일 지수 화면에서
   검색 결과가 뜬 뒤 오른쪽 위 다운로드 → 엑셀을 누르면 여기서 파일을 만든다.
   양식은 기획 리포트 엑셀과 같다:
     01_요약       제목 · 지표 카드 4칸 · 상품 기획 해석 · 핵심 표
     02_분석/추이  주간·일별 표 + 차트
     03_데이터설명 필드 정의 · 원천 조회 주소 · 원천 데이터
   값은 화면이 이미 받아 둔 응답(live_data 캐시)만 쓴다. 없는 값은 빈칸('–')으로 두고 지어내지 않는다.
   ══════════════════════════════════════════════════════ */
import { Book, C, ST, withFmt } from './xlsx_book.js';

const LAST = 11;   /* 요약 시트의 제목 · 해석 칸은 A~L 을 병합한다 */
const SUM_W = [18, 18, 11, 18, 18, 11, 18, 18, 3, 18, 18, 4, 13, 13, 13, 13];
const F = { int:'#,##0', d1:'0.0', d2:'0.00', pct:'0.0%', won:'#,##0"원"' };

/* ── 값 다루기 ── */
const num = v => (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) ? null : Number(v);
const r1 = v => v == null ? null : Math.round(v * 10) / 10;
const fx = (v, d = 1) => v == null ? '–' : Number(v).toLocaleString('ko-KR', { maximumFractionDigits:d });
const won = v => v == null ? '–' : Math.round(v).toLocaleString('ko-KR') + '원';
const signed = (v, u = '') => v == null ? '–' : (v > 0 ? '+' : '') + fx(v) + u;
const day = v => String(v || '').slice(0, 10);
const isoAdd = (iso, n) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10) };
const weekStart = iso => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return d.toISOString().slice(0, 10) };
const sortRows = rows => (rows || []).filter(r => r && r.date).map(r => Object.assign({}, r, { date:day(r.date) }))
  .sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
/* 마지막 관측일로부터 n일 안의 행 */
const within = (rows, n) => { if (!rows.length) return []; const from = isoAdd(rows[rows.length - 1].date, -(n - 1)); return rows.filter(r => r.date >= from) };
const sumF = (rows, f) => rows.reduce((a, r) => a + (num(r[f]) || 0), 0);
const avgF = (rows, f) => { const v = rows.map(r => num(r[f])).filter(x => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null };
/* 주(월요일 시작) 단위로 묶는다. spec: {열이름:[필드, 'sum'|'avg']} */
function weekly(rows, spec){
  const by = new Map();
  rows.forEach(r => { const k = weekStart(r.date); (by.get(k) || by.set(k, []).get(k)).push(r) });
  return [...by.keys()].sort().map(k => {
    const g = by.get(k), o = { week:k };
    Object.keys(spec).forEach(n => {
      const [f, agg] = spec[n];
      const has = g.some(r => num(r[f]) != null);
      o[n] = !has ? null : agg === 'sum' ? sumF(g, f) : avgF(g, f);
    });
    return o;
  });
}
const tone = v => v == null ? C.ink : v > 0 ? C.green : v < 0 ? C.red : C.ink;

/* ── 시트 조각 ── */
function header(s, title, sub){
  s.put(1, 0, title, ST.title, 29).merge(1, 0, 1, LAST, ST.title);
  s.put(2, 0, sub, ST.sub, 34).merge(2, 0, 2, LAST, ST.sub);
}
/* 지표 카드 4칸 — [이름, 값(글자), 설명, 색] */
function kpis(s, r, cards){
  cards.slice(0, 4).forEach((k, i) => {
    const c = i * 3;
    s.put(r, c, k[0], ST.kLabel).merge(r, c, r, c + 1, ST.kLabel);
    s.put(r + 1, c, k[1], ST.kValue(k[3])).merge(r + 1, c, r + 2, c + 1, ST.kValue(k[3]));
    s.put(r + 3, c, k[2] || '', ST.kNote).merge(r + 3, c, r + 3, c + 1, ST.kNote);
  });
  s.height(r, 20).height(r + 1, 18).height(r + 2, 18).height(r + 3, 20);
  return r + 6;
}
function section(s, r, text, coral, last = LAST){
  const st = coral ? ST.secCoral : ST.secDark;
  s.put(r, 0, text, st, 24).merge(r, 0, r, last, st);
  return r + 1;
}
function notes(s, r, lines){
  lines.filter(Boolean).forEach(t => {
    s.put(r, 0, t, ST.note, t.length > 80 ? 40 : 25).merge(r, 0, r, LAST, ST.note);
    r++;
  });
  return r + 2;
}
/* 표 — fmts[i] 는 i번째 열의 숫자 서식. 반환값은 표 다음 행 */
function table(s, r, c0, heads, rows, fmts = [], wrapCols = []){
  heads.forEach((h, i) => s.put(r, c0 + i, h, ST.th));
  s.height(r, 23);
  rows.forEach((row, j) => {
    row.forEach((v, i) => {
      const base = wrapCols.includes(i) ? ST.tdWrap : ST.td;
      s.put(r + 1 + j, c0 + i, v == null ? '' : v, fmts[i] ? withFmt(base, fmts[i]) : base);
    });
    s.height(r + 1 + j, wrapCols.length ? 30 : 20);
  });
  return r + 1 + rows.length;
}
/* 이름 · 값 · 설명 세 칸 표 — 값은 B, 설명은 D~L 병합 */
function kvTable(s, r, rows){
  s.put(r, 0, '지표', ST.th).put(r, 1, '값', ST.th).merge(r, 1, r, 2, ST.th);
  s.put(r, 3, '설명', ST.th).merge(r, 3, r, LAST, ST.th).height(r, 23);
  rows.forEach((row, j) => {
    const y = r + 1 + j;
    s.put(y, 0, row[0], ST.td).put(y, 1, row[1] == null ? '–' : row[1], ST.td).merge(y, 1, y, 2, ST.td);
    s.put(y, 3, row[2] || '', ST.td).merge(y, 3, y, LAST, ST.td);
    s.height(y, 20);
  });
  return r + 1 + rows.length;
}
/* 원천 행 → 표. 숫자·글자인 칸만, date 를 맨 앞에 */
function rawTable(rows){
  const keys = [];
  rows.forEach(r => Object.keys(r).forEach(k => {
    const v = r[k];
    if (!keys.includes(k) && (v == null || ['string', 'number', 'boolean'].includes(typeof v))) keys.push(k);
  }));
  const ordered = keys.includes('date') ? ['date'].concat(keys.filter(k => k !== 'date')) : keys;
  return { heads:ordered, rows:rows.map(r => ordered.map(k => {
    const v = r[k];
    if (typeof v === 'boolean') return v ? 'TRUE' : 'FALSE';
    return typeof v === 'number' ? v : v == null ? '' : String(v);
  })) };
}
/* 03_데이터설명 — 필드 정의 · 원천 주소 · 원천 데이터 */
function dataSheet(b, name, title, defs, rows, source){
  const raw = rawTable(rows);
  const head = 8 + defs.length + 1 + 3;   /* 원천 표 머리 행 */
  const s = b.sheet(name, { widths:[24, 38, 48].concat(Array(Math.max(0, raw.heads.length - 3)).fill(16)), freeze:head + 1 });
  header(s, title + ' 데이터 설명', '필드 정의와 원천 조회값');
  s.put(5, 0, 'Source: ' + source, ST.link).merge(5, 0, 5, LAST, ST.link);
  let r = table(s, 7, 0, ['필드', '뜻', '해석 시 주의'], defs, [], [1, 2]);
  r = section(s, r + 1, '원천 데이터');
  s.put(r, 0, '내려받은 시각 ' + new Date().toLocaleString('ko-KR') + ' · ' + rows.length + '행', ST.small);
  if (raw.heads.length) table(s, head, 0, raw.heads, raw.rows);
  else s.put(head, 0, '(원천 행 없음)', ST.small);
  return s;
}
const fileSafe = v => String(v || '').replace(/[\\/:*?"<>|\s]+/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '').slice(0, 40);

/* ══════════════ 언급량 · 온도 ══════════════ */
function buildTemp(ctx){
  const { kw, entry, summary:S, search } = ctx;
  const ED = (entry && entry.data) || {};
  const rows = sortRows([...entry.byDate.values()]);
  const last = rows[rows.length - 1] || {};
  const r90 = within(rows, 90), r28 = within(rows, 28), r7 = within(rows, 7);
  const prev7 = rows.filter(r => r.date >= isoAdd(last.date, -13) && r.date < isoAdd(last.date, -6));
  const m28 = sumF(r28, 'mention'), m7 = sumF(r7, 'mention'), p7 = sumF(prev7, 'mention');
  const chg7 = p7 > 0 ? (m7 - p7) / p7 * 100 : null;
  const temp = S && S.temp != null ? S.temp : num(last.temp);
  const mom = S && S.momentum != null ? S.momentum : num(last.momentum);
  const band = temp >= 85 ? ['과열', '이미 정점을 지나는 신호가 섞여 있습니다. 지금부터는 식는 속도를 지켜볼 구간입니다.']
    : temp >= 65 ? ['뜨거움', '언급량이 꾸준히 오르는 중입니다. 지금 붙잡을 만한 온도입니다.']
    : temp >= 40 ? ['달아오르는 중', '막 올라오기 시작한 단계입니다. 조금 더 지켜보면 방향이 뚜렷해집니다.']
    : ['아직 잠잠', '절대 언급량이 적어 판단하기엔 이릅니다. 추적만 걸어두는 편이 안전합니다.'];
  const flow = mom == null ? '' : mom >= 55 ? '상승' : mom <= 45 ? '하락' : '보합';
  const b = new Book();

  /* 01_요약 */
  const s = b.sheet('01_요약', { widths:SUM_W });
  header(s, '언급량·온도 리포트', kw + ' · ' + ctx.period + ' · 최근 90일 · ' + (S && (S.dataAsOf || S.asOf) || last.date) + ' 기준');
  let r = kpis(s, 5, [
    ['트렌드 온도', temp == null ? '–' : fx(temp) + '°', '0~100 상대 지표', C.coral],
    ['최근 28일 언급량', fx(m28, 0) + '건', '일별 mention 합계'],
    ['최근 7일 증감', chg7 == null ? '–' : signed(chg7, '%'), '직전 7일 대비', tone(chg7)],
    ['모멘텀', mom == null ? '–' : fx(mom), '50=보합 기준'],
  ]);
  r = section(s, r, '상품 기획 해석', true);
  r = notes(s, r, [
    '현재 온도는 ' + fx(temp) + '도' + (mom == null ? '' : ', 모멘텀은 ' + fx(mom) + '로 ' + flow + ' 흐름') + '입니다. (' + band[0] + ' 구간)',
    band[1],
    '최근 28일 언급은 ' + fx(m28, 0) + '건입니다.' + (S && S.share != null ? ' 같은 날 전체 언급 중 비중은 ' + fx(S.share) + '%입니다.' : '') +
      (S && S.yoyPct != null ? ' 전년 동기 대비 ' + signed(S.yoyPct, '%') + '입니다.' : ''),
    '온도는 판매량이 아니라 텍스트 신호의 상대 강도입니다.',
  ]);
  const plats = (ED.platforms || []).filter(p => p.temp != null && !(p.legacy && !p.mention));
  r = section(s, r, '플랫폼별 최신 관측');
  r = table(s, r, 0, ['플랫폼', '기준일', '온도', '레벨', '언급량', '오래된 값'],
    plats.length ? plats.map(p => [p.name, day(p.date), num(p.temp), num(p.level), num(p.mention), p.stale ? '예' : '아니오'])
      : [['(플랫폼별 행 없음)', '', '', '', '', '']], ['', '', F.d1, F.d1, F.int]);
  const newT = (ED.new_terms || []).filter(x => x.term !== kw);
  if (newT.length){
    r = section(s, r + 2, '신규 진입 키워드 (최근 7일)');
    table(s, r, 0, ['키워드', '온도'], newT.map(x => [x.term, num(x.temp)]), ['', F.d1]);
  }

  /* 02_추이 */
  const wk = weekly(r90, { m:['mention', 'sum'], d:['document', 'sum'], t:['temp', 'avg'], mo:['momentum', 'avg'] });
  const t = b.sheet('02_추이', { widths:[18, 14, 12, 14, 14, 3].concat(Array(10).fill(13)), freeze:6 });
  header(t, '주간 추이', '언급량·온도·모멘텀을 같은 기간으로 비교합니다. (' + kw + ')');
  let e = table(t, 5, 0, ['주 시작일', '언급량', '문서 수', '평균 온도', '평균 모멘텀'],
    wk.map(w => [w.week, w.m, w.d, w.t, w.mo]), ['', F.int, F.int, F.d1, F.d1]);
  if (wk.length > 1){
    t.chart({ type:'line', title:'주간 언급량', cat:[0, 6, 5 + wk.length], series:[{ name:'언급량', col:1, color:C.coral }], at:[6, 5, 14, 21] });
    t.chart({ type:'line', title:'주간 온도 · 모멘텀', cat:[0, 6, 5 + wk.length], min:0, max:100,
      series:[{ name:'평균 온도', col:3, color:C.coral }, { name:'평균 모멘텀', col:4, color:C.ink }], at:[6, 22, 14, 39] });
  }
  /* 검색량 — 언급과 계산 근거가 달라 따로 둔다 */
  const SD = search && search.status === 'ok' ? (search.data || {}) : null;
  if (SD){
    e = Math.max(e, 40) + 1;
    const V = SD.volume || {}, by = V.by_source || {}, sh = V.share || {};
    e = section(t, e, '검색량 (네이버 · 구글)', false, 4);
    e = table(t, e, 0, ['플랫폼', '검색량', '비중(%)'],
      [['네이버', num(by.naver && by.naver.total), num(sh.naver)], ['구글', num(by.google && by.google.total), num(sh.google)]],
      ['', F.int, F.d1]);
    const SS = SD.seasonality || [];
    if (SS.length){
      const top = e + 2;
      e = section(t, top, '월별 검색량', false, 4);
      e = table(t, e, 0, ['월', '검색량'], SS.map(x => [x.month, num(x.volume)]), ['', F.int]);
      t.chart({ type:'bar', title:'월별 검색량', cat:[0, top + 2, top + 1 + SS.length], series:[{ name:'검색량', col:1, color:C.coral }],
        at:[6, top, 14, top + 17] });
      e = Math.max(e, top + 18);
    }
    const RG = SD.regions || [];
    if (RG.length){
      e = section(t, e + 2, '지역별 검색 비중', false, 4);
      table(t, e, 0, ['시·도', '상대 비중'], RG.map(x => [x.region, num(x.value)]), ['', F.d1]);
    }
  }

  dataSheet(b, '03_데이터설명', '언급량·온도', [
    ['mention', '해당 날짜에 용어가 검증되어 언급된 건수', '수집 문서량 변화의 영향을 받을 수 있습니다.'],
    ['document', '해당 용어가 포함된 고유 문서 수', '댓글·리뷰 등 문서 유형이 함께 포함됩니다.'],
    ['temp', '언급 수준과 흐름을 0~100으로 환산한 트렌드 온도', '판매량이나 확률이 아닙니다.'],
    ['momentum', '최근 흐름의 방향 지표', '50 전후는 보합, 높을수록 상승 신호입니다.'],
    ['level', '화제성 레벨', '같은 용어의 과거 대비 상대 수준입니다.'],
    ['ma7 / ma28', '7일·28일 이동평균', '단기와 중기 흐름을 비교합니다.'],
    ['share_pct', '같은 날 전체 용어 언급량 중 해당 용어의 비중', '전체 집계량이 바뀌면 함께 움직입니다.'],
  ], r90, ctx.source);
  return { book:b, name:'언급량온도_' + fileSafe(kw) };
}

/* ══════════════ 연관어 ══════════════ */
const AX_ORDER = ['아이템', '소재', '색', '디테일', 'TPO', '스타일', '브랜드', '인물'];
function buildAssoc(ctx){
  const { kw, data:A } = ctx;
  const groups = {};
  (A.items || []).forEach(it => { const c = it.facet_ko || it.facet; (groups[c] = groups[c] || []).push(it) });
  Object.keys(groups).forEach(c => groups[c].sort((a, b) =>
    (a.rank != null ? a.rank : 1e6) - (b.rank != null ? b.rank : 1e6) || (b.pmi || 0) - (a.pmi || 0)));
  const cats = AX_ORDER.filter(c => groups[c]).concat(Object.keys(groups).filter(c => !AX_ORDER.includes(c)));
  const ALL = cats.reduce((a, c) => a.concat(groups[c]), []);
  const strength = a => a.score != null ? a.score : a.percentile != null ? a.percentile : a.lift != null ? a.lift * 10 : a.cooccurrence;
  const filled = AX_ORDER.reduce((n, c) => n + Math.min(10, (groups[c] || []).length), 0);
  const density = Math.min(100, Math.round(filled / (AX_ORDER.length * 10) * 100));
  const top = ALL.slice().sort((a, b) => (strength(b) || 0) - (strength(a) || 0))[0];
  const catTotals = cats.map(c => [c, groups[c].length, groups[c].reduce((n, a) => n + (a.cooccurrence || 0), 0)]);
  const topCat = catTotals.slice().sort((a, b) => b[2] - a[2])[0];
  const newCnt = ALL.filter(a => a.change === 'new').length;
  const band = density >= 75 ? ['폭발적 확산', '여러 축에 걸쳐 연관어가 최대치에 가깝게 쌓였습니다. 소비자 언어가 이미 풍부하게 형성된 상태입니다.']
    : density >= 50 ? ['활발한 확산', '연관어가 절반 이상 채워졌습니다. 축마다 고르게 늘고 있는지 확인해볼 때입니다.']
    : density >= 25 ? ['완만한 확산', '연관어가 서서히 쌓이고 있지만 아직 절반에 못 미칩니다. 확산 초반 구간입니다.']
    : ['정체', '연관어 수가 아직 적어 판단하기엔 이릅니다. 소재가 한정적으로 소비되고 있을 가능성이 있습니다.'];
  const win = A.window_days ? '최근 ' + A.window_days + '일' : '';
  const scoreOf = a => num(a.score != null ? a.score : a.percentile);
  const b = new Book();

  /* 01_요약 */
  const s = b.sheet('01_요약', { widths:[14, 18, 10, 18, 10, 18, 10, 14, 3, 18, 18, 4] });
  header(s, 'FEEDiT 연관어 MD 기획 리포트', kw + ' · ' + ctx.period + ' · ' + (win || '연관어 분석') + ' · ' + day(A.data_as_of || A.as_of) + ' 기준');
  let r = kpis(s, 5, [
    ['연관어 포화도', density + '%', band[0], C.coral],
    ['연관어 총량', ALL.length + '건', cats.length + '개 축'],
    ['신규 연관어', newCnt + '건', '전주 대비 새로 등장'],
    ['최다 연관어', top ? top.term : '–', top && num(top.lift) != null ? 'lift ' + num(top.lift).toFixed(2) : (top ? '동시 언급 ' + (top.cooccurrence || 0) + '건' : '')],
  ]);
  r = section(s, r, '상품 기획 방향');
  r = table(s, r, 0, ['기획 축', '1순위', '점수', '2순위', '점수', '3순위', '점수'],
    cats.map(c => { const g = groups[c]; const row = [c];
      for (let i = 0; i < 3; i++){ row.push(g[i] ? g[i].term : ''); row.push(g[i] ? scoreOf(g[i]) : null) }
      return row }), ['', '', F.d2, '', F.d2, '', F.d2]);
  const pick = c => groups[c] && groups[c][0] ? groups[c][0].term : null;
  const memo = [pick('아이템') && pick('아이템') + '를 중심으로', pick('소재') && pick('소재') + ' 소재', pick('색') && pick('색') + ' 컬러',
    pick('디테일') && pick('디테일') + ' 디테일', pick('TPO') && pick('TPO') + ' 상황', pick('스타일') && pick('스타일') + ' 무드'].filter(Boolean);
  r = section(s, r + 2, '이번 시즌 기획 메모', true);
  r = notes(s, r, [
    memo.length ? memo.join(', ') + '을(를) 우선 검토합니다.' : '',
    '‘' + kw + '’는 ' + (win ? win + ' 기준 ' : '') + band[0] + ' 단계입니다. ' + band[1],
    topCat ? '가장 뜨거운 축은 ‘' + topCat[0] + '’(동시 언급 ' + topCat[2] + '건)입니다. 축 하나에 몰릴수록 유행이 아니라 단일 아이템 소비일 확률이 높습니다.' : '',
  ]);
  r = section(s, r, '축별 비중');
  table(s, r, 0, ['축', '키워드 수', '동시 언급 합계', '비중'],
    catTotals.map(c => [c[0], c[1], c[2], ALL.length ? c[1] / ALL.length : null]), ['', F.int, F.int, F.pct]);

  /* 02_연관어 — 축별로 이어 붙인 전체 순위 + 축마다 상위 8개 막대 차트 */
  const t = b.sheet('02_연관어', { widths:[10, 7, 18, 12, 12, 10, 11, 10, 9, 9, 16, 3].concat(Array(10).fill(10)), freeze:6 });
  header(t, kw + ' 연관어 분석', '상품 기획 축별 전체 순위 · ' + (win || '전체 기간') + ' 기준');
  const flat = [];
  cats.forEach(c => groups[c].forEach((a, i) => flat.push([c, i + 1, a.term, num(a.cooccurrence),
    Array.isArray(a.weekly_counts) && a.weekly_counts.length ? num(a.weekly_counts[a.weekly_counts.length - 1]) : null,
    a.change == null ? '' : a.change === 'new' ? 'new' : num(a.change), scoreOf(a),
    a.percentile != null ? num(a.percentile) / 100 : null, num(a.lift), num(a.pmi), (a.basis || []).join(' · ')])));
  table(t, 5, 0, ['구분', '순위', '키워드', '동시 언급량', '최근 주 언급', '전주 대비', '연관점수', '백분위', 'lift', 'PMI', '근거'],
    flat, ['', F.int, '', F.int, F.int, '', F.d2, F.pct, F.d2, F.d2]);
  let at = 0, cy = 5;
  cats.slice(0, 6).forEach(c => {
    const n = Math.min(8, groups[c].length), from = 6 + at;
    if (n >= 2){
      t.chart({ type:'bar', title:c + ' 상위 연관어', cat:[2, from, from + n - 1],
        series:[{ name:'연관점수', col:6, color:c === (topCat && topCat[0]) ? C.coral : C.ink }], at:[12, cy, 20, cy + 15] });
      cy += 16;
    }
    at += groups[c].length;
  });

  /* 03_트렌드추이 */
  const hist = sortRows(A.history || []);
  const u = b.sheet('03_트렌드추이', { widths:[18, 14, 14, 14, 14, 3].concat(Array(10).fill(13)), freeze:6 });
  header(u, kw + ' 트렌드 추이', '연관어 수와 관심 강도의 최근 변화');
  let e = table(u, 5, 0, ['날짜', '연관어 수'], hist.length ? hist.map(h => [h.date, num(h.count)]) : [['(적재 이력 없음)', '']], ['', F.int]);
  if (hist.length > 1) u.chart({ type:'line', title:'연관어 수 추이', cat:[0, 6, 5 + hist.length], series:[{ name:'연관어 수', col:1, color:C.coral }], at:[6, 5, 14, 21] });
  const T = ctx.trend && ctx.trend.status === 'ok' && ctx.trend.byDate ? sortRows([...ctx.trend.byDate.values()]) : [];
  if (T.length){
    const wk = weekly(within(T, 90), { m:['mention', 'sum'], t:['temp', 'avg'], mo:['momentum', 'avg'] });
    const top2 = Math.max(e, 22) + 2;
    e = section(u, top2, '주간 요약 (언급량 · 온도 · 모멘텀)', false, 3);
    table(u, e, 0, ['주 시작일', '언급량', '평균 온도', '평균 모멘텀'], wk.map(w => [w.week, w.m, w.t, w.mo]), ['', F.int, F.d1, F.d1]);
    if (wk.length > 1) u.chart({ type:'line', title:'주간 온도 · 모멘텀', cat:[0, e + 1, e + wk.length], min:0, max:100,
      series:[{ name:'평균 온도', col:2, color:C.coral }, { name:'평균 모멘텀', col:3, color:C.ink }], at:[6, top2, 14, top2 + 17] });
  }

  dataSheet(b, '04_데이터설명', '연관어', [
    ['cooccurrence', '키워드와 같은 문서에서 함께 언급된 문서 수', '검색 기반 연관어는 0일 수 있습니다.'],
    ['score', '동시 언급·검색 신호를 섞은 통합 연관 점수', '축 안 순위를 정하는 기준입니다.'],
    ['percentile', '같은 날 연관 강도의 백분위', '하루 값이라 표본이 적으면 튈 수 있습니다.'],
    ['lift / pmi', '우연히 함께 나올 확률 대비 실제 동시 출현 비율', '1(또는 0)보다 클수록 연관이 강합니다.'],
    ['change', '전주 대비 순위 변화 (new = 새로 등장)', '양수면 순위가 오른 것입니다.'],
    ['basis', 'text = 같은 문서 언급 · search = 연관검색어', '출처에 따라 언급 수가 없을 수 있습니다.'],
  ], ALL.map(a => Object.assign({ facet:a.facet_ko || a.facet }, a)), ctx.source);
  return { book:b, name:'연관어_' + fileSafe(kw) };
}

/* ══════════════ 긍부정 ══════════════ */
function buildSentiment(ctx){
  const { kw, data:D } = ctx;
  const rows = sortRows(D.series || []);
  const last = rows[rows.length - 1] || {};
  const rec = within(rows, 28);
  const pos = sumF(rec, 'pos_n'), neu = sumF(rec, 'neu_n'), neg = sumF(rec, 'neg_n'), total = pos + neu + neg;
  const p = v => total ? v / total : null;
  const score = num(last.intent) != null ? Math.round(last.intent) : null;
  const lead = pos + neg > 0 ? Math.round(pos / (pos + neg) * 100) : null;
  const thin = score == null && (total < 20 || lead == null);
  const dial = score != null ? score : lead;
  const band = thin ? ['판단 보류', '최근 28일 반응이 ' + total + '건뿐이라 판정하기엔 자료가 적습니다. 20건 이상 모이면 판정합니다.']
    : dial >= 75 ? ['강한 구매 신호', '긍정 신호가 압도적입니다. 지금 재고·물량을 걱정할 시점입니다.']
    : dial >= 55 ? ['구매 신호 우세', '긍정 쪽이 앞서 있습니다. 부정 신호가 늘지 않는지만 함께 지켜보세요.']
    : dial >= 35 ? ['팽팽한 신호', '긍정과 부정이 비슷하게 맞섭니다. 부정 신호의 종류를 먼저 확인해야 합니다.']
    : ['구매 저해 신호 우세', '부정 신호가 앞섭니다. 가격·실물 관련 이슈부터 해소돼야 반등합니다.'];
  const SIG = [['질문', 'question_n', '중립'], ['구매', 'purchase_n', '긍정'], ['경험', 'experience_n', '긍정'],
    ['호평', 'praise_n', '긍정'], ['비판', 'critique_n', '부정'], ['잡담', 'chitchat_n', '중립']]
    .map(x => [x[0], sumF(rec, x[1]), x[2]]).sort((a, b) => b[1] - a[1]);
  const b = new Book();

  const s = b.sheet('01_요약', { widths:SUM_W });
  header(s, '긍부정 리포트', kw + ' · 최근 28일 · ' + (D.scope_label || '용어 직접 언급') + ' · ' + day(D.data_as_of || last.date) + ' 기준');
  let r = kpis(s, 5, [
    ['긍정', p(pos) == null ? '–' : fx(p(pos) * 100) + '%', pos + '건', C.green],
    ['중립', p(neu) == null ? '–' : fx(p(neu) * 100) + '%', neu + '건', C.blue],
    ['부정', p(neg) == null ? '–' : fx(p(neg) * 100) + '%', neg + '건', C.red],
    ['분류 표본', total + '건', '긍정+중립+부정'],
  ]);
  r = section(s, r, '판정');
  r = kvTable(s, r, [
    ['판정', band[0], thin ? '자료가 적어 판정을 미룹니다.' : '구매의향 지수(없으면 긍정 우위)로 판정합니다.'],
    ['구매의향 지수', score, '구매·질문·경험 등 의도 신호를 종합한 지수입니다. 판매 전환율이 아닙니다.'],
    ['긍정 우위', lead == null ? null : lead + '%', '긍정 ÷ (긍정+부정) — 중립을 뺀 비교입니다.'],
    ['기준일', day(D.data_as_of || last.date), '최근 28일 합계로 계산합니다.'],
  ]);
  const sigTop = r + 2;
  r = section(s, sigTop, '반응 유형', false, 5);
  const sigEnd = table(s, r, 0, ['순위', '유형', '건수', '계열'], SIG.map((x, i) => [i + 1, x[0], x[1], x[2]]), [F.int, '', F.int]);
  if (SIG.some(x => x[1] > 0))
    s.chart({ type:'bar', title:'반응 유형별 건수 (최근 28일)', cat:[1, r + 1, r + SIG.length], series:[{ name:'건수', col:2, color:C.coral }],
      at:[6, sigTop, 12, sigTop + 13] });
  r = section(s, Math.max(sigEnd, sigTop + 14) + 1, '상품 기획 해석', true);
  const topPos = SIG.find(x => x[2] === '긍정' && x[1] > 0), topNeg = SIG.find(x => x[2] === '부정' && x[1] > 0);
  notes(s, r, [
    '‘' + kw + '’는 지금 ' + band[0] + '입니다. ' + band[1],
    '최근 28일 분류 표본은 ' + total + '건(긍정 ' + pos + ' · 중립 ' + neu + ' · 부정 ' + neg + ')입니다.',
    topPos ? '가장 많은 긍정 신호는 ‘' + topPos[0] + '’(' + topPos[1] + '건)' + (topNeg ? ', 부정 신호는 ‘' + topNeg[0] + '’(' + topNeg[1] + '건)입니다.' : '입니다.') : '',
    '일별 소표본 변동이 크므로 단일 날짜 비율보다 주간·28일 합계로 보세요.',
  ]);

  const r90 = within(rows, 90);
  const wk = weekly(r90, { pos:['pos_n', 'sum'], neu:['neu_n', 'sum'], neg:['neg_n', 'sum'], it:['intent', 'avg'] });
  const t = b.sheet('02_반응분석', { widths:[14, 11, 11, 11, 11, 11, 11, 16, 3].concat(Array(10).fill(13)), freeze:6 });
  header(t, '주간 긍부정 변화', '일별 소표본 변동을 줄이기 위해 주간 합계로 봅니다. (' + kw + ')');
  let e = table(t, 5, 0, ['주 시작일', '긍정 건수', '중립 건수', '부정 건수', '긍정 비율', '중립 비율', '부정 비율', '구매의향 지수 평균'],
    wk.map(w => { const n = (w.pos || 0) + (w.neu || 0) + (w.neg || 0);
      return [w.week, w.pos, w.neu, w.neg, n ? (w.pos || 0) / n : null, n ? (w.neu || 0) / n : null, n ? (w.neg || 0) / n : null, w.it] }),
    ['', F.int, F.int, F.int, F.pct, F.pct, F.pct, F.d1]);
  if (wk.length > 1){
    const cat = [0, 6, 5 + wk.length];
    t.chart({ type:'line', title:'주간 긍정 · 중립 · 부정 비율', cat, fmt:'0%', min:0, max:1,
      series:[{ name:'긍정', col:4, color:C.green }, { name:'중립', col:5, color:C.blue }, { name:'부정', col:6, color:C.red }], at:[9, 5, 17, 21] });
    t.chart({ type:'bar', title:'주간 반응 건수', cat,
      series:[{ name:'긍정', col:1, color:C.green }, { name:'중립', col:2, color:C.blue }, { name:'부정', col:3, color:C.red }], at:[9, 22, 17, 39] });
  }
  const EV = D.evidence || {}, KO = { QUESTION:'질문', PURCHASE:'구매', EXPERIENCE:'경험', PRAISE:'호평', CRITIQUE:'비판', CHITCHAT:'잡담' };
  const ev = [];
  Object.keys(EV).forEach(k => (EV[k] || []).forEach(x => ev.push([KO[k] || k, x.tag || '', x.text || ''])));
  if (ev.length){
    e = section(t, Math.max(e, 40) + 1, '반응 유형별 근거 문장', false, 7);
    table(t, e, 0, ['유형', '출처', '근거 문장'], ev, [], [2]);
    for (let y = e; y <= e + ev.length; y++) t.merge(y, 2, y, 7, y === e ? ST.th : ST.tdWrap);
  }

  dataSheet(b, '03_데이터설명', '긍부정', [
    ['pos_n / neu_n / neg_n', '긍정·중립·부정으로 분류된 일별 건수', '비율 계산의 분자입니다.'],
    ['pos_rate / neu_rate / neg_rate', '해당 날짜 분류 표본 중 각 감정의 비율', '일별 표본이 적으면 변동이 큽니다.'],
    ['sentiment', '일별 감성 종합 점수', '긍정 비율과 동일한 값이 아닙니다.'],
    ['intent', '구매·질문·경험 등 의도 신호를 종합한 구매의향 지수', '판매 전환율이 아닙니다.'],
    ['praise_n / critique_n', '호평·비판 의도로 분류된 건수', '긍부정 분류와 별도의 반응 유형입니다.'],
    ['집계 기준', '최근 28일의 일별 건수를 합산해 비율 계산', '단일 날짜 비율보다 표본 안정성이 높습니다.'],
  ], r90, ctx.source);
  return { book:b, name:'긍부정_' + fileSafe(kw) };
}

/* ══════════════ 수명주기 ══════════════ */
function buildLife(ctx){
  const { data:D } = ctx;
  const label = ctx.label || D.label || D.term;
  const stages = ['태동', '확산', '정점', '쇠퇴'], si = stages.indexOf(D.stage);
  const MSG = [['아직 아무도 모릅니다', '지금 사면 남들보다 먼저 입는 구간입니다. 다만 물량이 적어 선택지가 좁고, 그대로 사라질 위험도 함께 있습니다.'],
    ['가장 안전한 구간입니다', '화제성이 올라가는 중입니다. 물량도 충분해 고르기 좋습니다.'],
    ['지금이 마지막입니다', '정점 부근입니다. 사도 되지만 오래 못 갑니다. 오래 입을 옷이라면 다음 것을 보세요.'],
    ['이미 지났습니다', '최고점에서 내려오는 중입니다. 싸게 나와도 올해 안에 안 입게 될 확률이 높습니다.']][si] || ['판정 보류', D.rule || ''];
  const timing = ['적기', '적기', '주의', '비추천'][si] || '–';
  const mom = D.momentum == null ? null : Math.round(D.momentum - 50);
  const OT = D.order_timing || null;
  const series = sortRows(D.series || []), sales = sortRows(D.sales_series || []);
  const b = new Book();

  const s = b.sheet('01_요약', { widths:SUM_W });
  header(s, '수명주기 리포트', label + ' · 대표 용어 ‘' + (D.term || '') + '’ · 관측 ' + (D.points || 0) + '일 · ' + day(D.data_as_of || D.as_of) + ' 기준');
  let r = kpis(s, 5, [
    ['현재 단계', si < 0 ? '–' : stages[si], '태동 → 확산 → 정점 → 쇠퇴', [C.blue, C.green, C.amber, C.red][si] || C.ink],
    ['유행 진행도', D.progress == null ? '–' : fx(D.progress, 0) + '%', '0~100% · 높을수록 끝에 가까움', C.coral],
    ['현재 온도', D.temp == null ? '–' : fx(D.temp) + '°', '0~100 상대 지표'],
    ['성장 모멘텀', signed(mom), '모멘텀 지수 50 = 보합', tone(mom)],
  ]);
  r = section(s, r, '핵심 지표');
  r = kvTable(s, r, [
    ['구매 타이밍', timing, MSG[0]],
    ['발주 관점', OT ? OT.label : null, OT ? OT.reason : '서버 판정 없음'],
    ['신규 유입률', D.inflow_pct == null ? null : signed(Math.round(D.inflow_pct), '%'), '최근 4주 언급 · 직전 4주 대비'],
    ['시장 포화도', D.level == null ? null : fx(D.level, 0) + '%', '화제성 레벨 기준'],
    ['화제성 시작 후', D.age_weeks == null ? null : D.age_weeks + '주', '처음 화제성이 잡힌 뒤 지난 기간'],
    ['최고점', D.peak_date || null, '28일 평균 기준 최고점 날짜'],
    ['현재 방향', mom == null ? null : mom >= 0 ? '상승' : '하강', '모멘텀 50 기준'],
  ]);
  r = section(s, r + 2, '상품 기획 해석', true);
  notes(s, r, [
    '‘' + label + '’는 ' + (si < 0 ? '관측이 모자라 단계를 판정하지 않았습니다.' : stages[si] + ' 단계 — ' + MSG[0] + '.'),
    MSG[1],
    OT ? '발주 관점: ' + OT.label + ' — ' + OT.reason : '',
    D.rule ? '판정 규칙: ' + D.rule : '',
  ]);

  /* 02_추이 */
  const salesBy = new Map(sales.map(x => [x.date, x]));
  const merged = series.map(x => Object.assign({}, x, salesBy.has(x.date) ? { sales:salesBy.get(x.date).sales } : {}));
  const wk = weekly(merged, { l:['level', 'avg'], m:['mention', 'sum'], s:['sales', 'sum'] });
  const t = b.sheet('02_추이', { widths:[18, 14, 14, 14, 3].concat(Array(12).fill(13)), freeze:6 });
  header(t, '유행 곡선 · 주간 추이', '화제성 레벨과 언급량·판매량의 흐름 (' + label + ')');
  let e = table(t, 5, 0, ['주 시작일', '평균 화제성 레벨', '언급량', '판매량'], wk.map(w => [w.week, w.l, w.m, w.s]), ['', F.d1, F.int, F.int]);
  if (wk.length > 1){
    t.chart({ type:'line', title:'유행 곡선 (화제성 레벨)', cat:[0, 6, 5 + wk.length], min:0, max:100,
      series:[{ name:'화제성 레벨', col:1, color:C.coral }], at:[5, 5, 13, 21] });
    t.chart({ type:'bar', title:sales.length ? '주간 언급량 · 판매량' : '주간 언급량', cat:[0, 6, 5 + wk.length],
      series:[{ name:'언급량', col:2, color:C.ink }].concat(sales.length ? [{ name:'판매량', col:3, color:C.coral }] : []), at:[5, 22, 13, 39] });
  }
  const W = D.weekly_temp || [];
  if (W.length){
    e = section(t, Math.max(e, 40) + 1, '주별 온도', false, 3);
    table(t, e, 0, ['시기', '온도'], W.map(x => [x.weeks_ago === 0 ? '이번 주' : x.weeks_ago + '주 전', num(x.temp)]), ['', F.d1]);
  }

  dataSheet(b, '03_데이터설명', '수명주기', [
    ['level', '화제성 레벨 — 같은 용어의 과거 대비 상대 수준', '0~100, 유행 곡선의 높이입니다.'],
    ['mention', '해당 날짜의 언급 건수', '수집 문서량의 영향을 받습니다.'],
    ['sales', '같은 상품 판매수 스냅샷의 일별 증가', '여러 날 쌓여야 생깁니다.'],
    ['stage / progress', '태동·확산·정점·쇠퇴 단계와 진행도(%)', 'level·ma28·momentum 규칙으로 판정합니다.'],
    ['momentum', '최근 흐름의 방향 지표', '50 전후는 보합입니다.'],
    ['inflow_pct', '최근 4주 언급의 직전 4주 대비 증감률', '새로 유입되는 관심의 크기입니다.'],
  ], merged, ctx.source);
  return { book:b, name:'수명주기_' + fileSafe(label) };
}

/* ══════════════ 할인률 변화 ══════════════ */
function buildStock(ctx){
  const { data:D } = ctx;
  const P = D.product || {};
  const byDay = new Map();
  sortRows(D.price_series || []).forEach(x => byDay.set(x.date, x));
  const ps = [...byDay.values()].map(x => {
    const l = num(x.list_price), sp = num(x.sale_price);
    const rate = num(x.discount_rate) != null ? num(x.discount_rate) : (l && sp != null ? r1((l - sp) / l * 100) : null);
    return { date:x.date, list:l, sale:sp, rate };
  });
  const first = ps[0], lastP = ps[ps.length - 1];
  const b = new Book();

  const s = b.sheet('01_요약', { widths:SUM_W });
  header(s, '할인율 변화 리포트', [P.brand, P.name].filter(Boolean).join(' · '));
  let r = kpis(s, 5, [
    ['정상가', won(num(P.list_price)), '최신 관측 정상가'],
    ['현재 판매가', won(num(P.sale_price)), (P.source || '판매처') + ' 최신가'],
    ['현재 할인율', P.discount_rate == null ? '–' : fx(P.discount_rate) + '%', '정상가 대비', C.coral],
    ['관측 기간', (P.observed_days || 0) + '일', P.observed_at ? day(P.observed_at) + ' 기준' : '관측일 미확인'],
  ]);
  r = section(s, r, '상품 정보');
  const info = [['상품명', P.name], ['브랜드', P.brand], ['판매처', P.source], ['상품 ID', P.id != null ? String(P.id) : ''],
    ['최저 관측가', num(P.history_min_price)], ['최고 관측가', num(P.history_max_price)], ['상품 이미지 URL', P.image]];
  info.forEach((x, j) => {
    s.put(r + j, 0, x[0], ST.td).put(r + j, 1, x[1] == null ? '–' : x[1], typeof x[1] === 'number' ? withFmt(ST.td, F.won) : ST.td)
      .merge(r + j, 1, r + j, LAST, typeof x[1] === 'number' ? withFmt(ST.td, F.won) : ST.td).height(r + j, 20);
  });
  r = section(s, r + info.length + 2, '할인 지표');
  r = kvTable(s, r, [
    ['할인율 변화', D.change_2w == null ? null : signed(D.change_2w, '%p'), D.change_2w == null ? '2주 전 비교 기록 없음' : '2주 전 대비'],
    ['첫 할인 관측', D.first_discount_at || null, '현재 보유한 기록 기준'],
    ['관측 최고 할인율', D.max_discount_period == null ? null : fx(D.max_discount_period) + '%', '최근 ' + (D.days || '') + '일 기록'],
    ['가격 관측일', (P.observed_days || 0) + '일', '이력이 부족하면 추이를 그리지 않습니다'],
  ]);
  r = section(s, r + 2, '상품 기획 해석', true);
  const dir = first && lastP && first.rate != null && lastP.rate != null ? (lastP.rate > first.rate ? '커졌' : lastP.rate < first.rate ? '줄었' : '그대로였') : null;
  notes(s, r, [
    first && lastP && ps.length > 1 ? '판매가는 ' + won(first.sale) + '에서 ' + won(lastP.sale) + '으로 변했고, 할인율은 ' +
      fx(first.rate) + '%에서 ' + fx(lastP.rate) + '%로 ' + (dir || '변했') + '습니다.' : '가격이 기록된 날짜가 하루뿐이라 추이를 판단하지 않았습니다.',
    D.change_2w != null ? '2주 전 대비 할인율은 ' + signed(D.change_2w, '%p') + ' 변했습니다.' : '',
    '할인율 상승이 수요 하락을 직접 의미하지는 않습니다. 쿠폰·회원가는 별도일 수 있습니다.',
  ]);

  const t = b.sheet('02_가격추이', { widths:[14, 14, 14, 11, 3].concat(Array(12).fill(13)), freeze:6 });
  header(t, '실제 상품 가격·할인 추이', P.name || '');
  let e = table(t, 5, 0, ['날짜', '정상가', '판매가', '할인율'], ps.map(x => [x.date, x.list, x.sale, x.rate]), ['', F.int, F.int, F.d1]);
  if (ps.length > 1){
    t.chart({ type:'line', title:'정상가 · 판매가', cat:[0, 6, 5 + ps.length], fmt:'#,##0',
      series:[{ name:'정상가', col:1, color:C.ink }, { name:'판매가', col:2, color:C.coral }], at:[5, 5, 13, 21] });
    t.chart({ type:'line', title:'할인율 추이 (%)', cat:[0, 6, 5 + ps.length], series:[{ name:'할인율', col:3, color:C.coral }], at:[5, 22, 13, 39] });
  }
  const M = D.matched_platforms || [];
  if (M.length){
    e = section(t, Math.max(e, 40) + 1, '판매처별 가격 비교', false, 4);
    table(t, e, 0, ['판매처', '할인율', '최근 관측가', '기준일', '선택 상품'],
      M.map(x => [x.name, num(x.discount_rate), num(x.sale_price), day(x.observed_at), x.source_id === P.id ? '예' : '']), ['', F.d1, F.int]);
  }

  dataSheet(b, '03_데이터설명', '할인율', [
    ['list_price', '판매처가 표시한 정상가', 'MSRP와 다를 수 있습니다.'],
    ['sale_price', '해당 관측 시점의 실제 판매가', '쿠폰·회원가가 별도일 수 있습니다.'],
    ['discount_rate', '(정상가-판매가) ÷ 정상가 × 100', '할인율 상승이 수요 하락을 직접 의미하지 않습니다.'],
    ['history_min/max_price', '조회 기간 중 최저·최고 판매가', '관측된 날짜만 기준으로 합니다.'],
    ['observed_days', '가격 스냅샷이 존재한 고유 날짜 수', '캘린더 전체 기간과 다릅니다.'],
    ['change_2w', '최근 할인율과 약 2주 전 할인율 차이', '두 시점이 있어야 계산됩니다.'],
  ], sortRows(D.price_series || []).map(x => Object.assign({ source_id:P.id, product_name:P.name, brand:P.brand, source:P.source }, x)), ctx.source);
  return { book:b, name:'할인율변화_' + fileSafe(P.brand) + '_' + fileSafe(P.id) };
}

/* ══════════════ 리세일 지수 ══════════════ */
function buildResale(ctx){
  const { data:D } = ctx;
  const P = D.product || {};
  const full = P.name || ctx.label || D.label || '';
  const exact = D.analysis_scope === 'product' || D.analysis_scope === 'platform_only';
  const keep = D.keep_pct == null ? null : Math.round(D.keep_pct);
  const listing = exact && D.current_listing_count != null ? Number(D.current_listing_count) : null;
  const hasTrade = D.volume_basis !== 'observed_listings';
  const scope = { brand:'브랜드', category:'카테고리', style:'스타일', selection:'조건' }[D.analysis_scope] || '상품';
  const flow = D.keep_change_pp == null ? null : D.keep_change_pp < -1 ? 'down' : D.keep_change_pp > 1 ? 'up' : 'flat';
  let head = '', expl = '';
  if (keep != null && !exact){
    head = full + ' ' + scope + '의 중고 가치는 정가 대비 ' + keep + '% 수준입니다.';
    expl = flow === 'down' ? '최근 가치 유지율이 내려가는 구간입니다. 매입·재고 판단은 보수적으로 확인하세요.'
      : flow === 'up' ? '최근 가치 유지율이 오르는 구간입니다. 수요와 매물 증가가 함께 나타나는지 확인하세요.'
      : flow === 'flat' ? '최근 가치 유지율은 큰 변화 없이 유지되고 있습니다.' : '현재 시장 수준은 확인되지만 이전 기간 비교 자료가 부족합니다.';
  } else if (keep != null){
    head = ctx.mode === 'sell' ? full + ', 지금 팔면 정가의 ' + keep + '%를 회수할 수 있습니다.'
      : (100 - keep >= 0 ? full + ', 지금 사면 정가보다 ' + (100 - keep) + '% 저렴합니다.' : full + ', 현재 정가보다 ' + (keep - 100) + '% 비쌉니다.');
    expl = flow === 'down' ? '최근 중고 가치가 내려가고 있습니다.' : flow === 'up' ? '최근 중고 가치가 오르고 있습니다.'
      : flow === 'flat' ? '최근 가격 흐름은 큰 변화 없이 유지되고 있습니다.' : '가격 흐름을 판단할 이전 관측이 부족해 현재 시세만 보여 드립니다.';
  } else head = '현재 시세는 확인했지만 정가 대비 비율은 계산하지 않았습니다.';
  const b = new Book();

  const s = b.sheet('01_요약', { widths:SUM_W });
  header(s, '리세일 지수 리포트', [P.brand, full, P.model_code].filter(Boolean).join(' · ') + ' · ' + day(D.as_of) + ' 기준 · 최근 ' + (D.days || '') + '일');
  let r = kpis(s, 5, [
    ['정가', won(num(D.regular_price)), '신상품 최신 판매가 중앙값'],
    ['중고가', won(num(D.used_price)), '최근 관측 중고가 중앙값', C.coral],
    ['현재 매물 수', listing == null ? '–' : listing.toLocaleString('ko-KR') + '건' + (D.current_listing_count_partial ? '+' : ''), listing == null ? '현재 수량 미적재' : '판매 가능한 최신 매물'],
    ['4주간 중고거래량', hasTrade && D.volume_4w != null ? Number(D.volume_4w).toLocaleString('ko-KR') + '건' : '측정 전', hasTrade ? '최근 4주 실제 거래 기준' : '실거래량 미적재·관측 기준'],
  ]);
  r = section(s, r, '리세일 시장');
  r = kvTable(s, r, [['가치 유지율', keep == null ? null : keep + '%', '중고가 ÷ 신상품 기준가 × 100 (100% 초과 시 프리미엄)']]
    .concat((D.md_signals || []).map(x => [x.label, x.value, x.description]))
    .concat([['판단 신뢰도', (D.confidence && D.confidence.label) || '낮음', '플랫폼 수·표본·관측일 기반']]));
  if (D.product){
    r = section(s, r + 2, '표준상품 매핑');
    r = kvTable(s, r, [
      ['상품명', P.name, P.mapped === false ? '플랫폼 단독 상품' : 'FEEDiT 표준상품'],
      ['브랜드', P.brand, ''], ['카테고리', P.category, ''], ['모델번호', P.model_code, ''], ['FEEDiT 코드', P.code, ''],
      ['연결 플랫폼', ((D.mapping && D.mapping.platform_count) || 0) + '개', ((D.mapping && D.mapping.platforms) || []).join(' · ')],
    ]);
  }
  r = section(s, r + 2, '상품 기획 해석', true);
  notes(s, r, [head, expl, D.basis_note || '']);

  /* 02_시장분석 */
  const t = b.sheet('02_시장분석', { widths:[14, 10, 10, 13, 13, 9, 10, 14, 13, 13, 3].concat(Array(8).fill(13)) });
  header(t, '플랫폼별 가격과 가치 유지율', full + (D.analysis_scope ? ' · ' + scope + ' 기준' : ''));
  const cards = D.platform_cards || [];
  let e = table(t, 5, 0, ['플랫폼', '시장', '연결 상품', '정상가', '판매가', '할인율', '현재 매물', '중고가 중앙값', '최저가', '기준일'],
    cards.length ? cards.map(c => [c.name, c.market === 'resale' ? '중고·리셀' : '신상품', num(c.product_sources), num(c.list_price), num(c.sale_price),
      num(c.discount_rate), num(c.listing_count), num(c.median_price), num(c.min_price), day(c.as_of)]) : [['(플랫폼 가격 없음)']],
    ['', '', F.int, F.int, F.int, F.d1, F.int, F.int, F.int]);
  const ser = sortRows(D.series || []);
  const tempBy = new Map(sortRows((D.temperature && D.temperature.series) || []).map(x => [x.date, num(x.temp)]));
  const top = e + 2;
  e = section(t, top, '가치 유지율 추이', false, 2);
  e = table(t, e, 0, ['날짜', '가치 유지율(%)', '트렌드 온도'], ser.map(x => [x.date, num(x.keep_pct), tempBy.has(x.date) ? tempBy.get(x.date) : null]), ['', F.d1, F.d1]);
  if (ser.length > 1)
    t.chart({ type:'line', title:'가치 유지율 vs 트렌드 온도', cat:[0, top + 2, top + 1 + ser.length],
      series:[{ name:'가치 유지율(%)', col:1, color:C.coral }].concat(tempBy.size ? [{ name:'트렌드 온도', col:2, color:C.ink }] : []),
      at:[4, top, 12, top + 17] });
  e = Math.max(e, top + 18) + 1;
  if ((D.grades || []).length){ e = section(t, e, '상태별 가격대', false, 2); e = table(t, e, 0, ['상태', '비중(%)', '시세'], D.grades.map(x => [x.label, num(x.share_pct), num(x.price)]), ['', F.d1, F.int]) + 2 }
  if ((D.sizes || []).length){ e = section(t, e, '사이즈별 시세', false, 2); e = table(t, e, 0, ['사이즈', '정가 대비', '시세'], D.sizes.map(x => [x.label, num(x.ratio), num(x.price)]), ['', F.d2, F.int]) + 2 }
  if (exact && D.spread){ e = section(t, e, '현재 매물과 최근 거래', false, 2); e = table(t, e, 0, ['구분', '중앙값'], [['현재 최저 매물', num(D.spread.ask)], ['최근 거래 사례', num(D.spread.trade)]], ['', F.int]) + 2 }
  const recs = D.recommendations || [];
  if (recs.length){
    e = section(t, e, '중고 추천 상품', false, 6);
    table(t, e, 0, ['브랜드', '상품명', '플랫폼', '가격', '관측 매물', '모델번호', '상품 ID'],
      recs.map(x => [x.brand || '', x.name, x.platform || '', num(x.price), num(x.listing_count), x.model_code || '', String(x.product_id || x.source_id || '')]),
      ['', '', '', F.int, F.int]);
  }

  dataSheet(b, '03_데이터설명', '리세일', [
    ['regular_price', '같은 표준상품의 일반 판매처 최신 판매가 중앙값', 'MSRP가 아니라 현재 신상품 기준가입니다.'],
    ['used_price', '최근 관측 중고 가격의 중앙값', '호가·거래가·스냅샷 구성에 따라 달라집니다.'],
    ['keep_pct', '중고가 ÷ 신상품 기준가 × 100', '100% 초과 시 프리미엄 구간입니다.'],
    ['current_listing_count', '플랫폼 최신 판매 가능 매물 수 합계', '+ 표시는 일부 표본 기반 최소치입니다.'],
    ['volume_4w', '최근 4주 거래량 또는 대체 관측량', 'volume_basis를 반드시 함께 확인합니다.'],
    ['confidence', '플랫폼 수·표본·관측일 기반 판단 신뢰도', '낮음은 데이터 부족이지 상품 평가가 아닙니다.'],
  ], ser.map(x => Object.assign({}, x, { product_id:P.id, model_code:P.model_code, regular_price:D.regular_price,
    used_price:D.used_price, volume_basis:D.volume_basis })), ctx.source);
  return { book:b, name:'리세일지수_' + fileSafe(P.model_code || P.id || full) };
}

const BUILD = { temp:buildTemp, assoc:buildAssoc, sentiment:buildSentiment, life:buildLife, stock:buildStock, resale:buildResale };

/* ctx: { id, kw, label, period('2026-10-W1'), source(조회 주소), data | entry·summary … }
   돌려주는 값: { blob, filename } */
export function metricXlsx(ctx){
  const { book, name } = BUILD[ctx.id](ctx);
  return { blob:book.blob(), filename:'FEEDiT_' + name + '_' + ctx.period + '.xlsx' };
}
