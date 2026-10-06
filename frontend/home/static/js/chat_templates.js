/* ══════════════════════════════════════════════════════
   리포트 템플릿 그림 (2026-10-02)

   질문 유형마다 한눈에 읽히는 그림을 그린다. 어떤 템플릿을 세울지는 서버
   (ChatBot/app/report_skill.choose_template)가 정하고, 값은 서버 블록에 있는
   것만 쓴다. 여기서는 축·위치·경로만 계산한다.

     ticker       진단   온도를 시세처럼 · 7/28/90일 전환 · 스토리 이미지
     timeline     원인   60일 언급량 막대 · 급상승한 날 주석 · 근거 카드
     versus       비교   두 추이선(역전 지점) · 지표별 덤벨
     leaderboard  순위   1~3위 카드 + 나머지 줄
     verdict      판정   살/말/보류 도장 · 가중치 × 점수 막대
     lifecycle    수명주기 곡선 위 '지금 여기'
     orbit        연관   연관 강도만큼 가까이 놓은 말
     lowsignal    관측 부족 — 온도 대신 지금 아는 것만

   ★ 없는 값은 그리지 않는다. null 을 0 으로 바꾸면 '변화 없음' 처럼 읽힌다.
   ★ 날짜 축은 '며칠째' 가 아니라 실제 날짜로 놓는다. 관측이 빈 날을 당겨 붙이면
     그래프가 실제보다 매끈해 보인다.
   ★ 클래스는 전부 chat_report.css 의 '리포트 템플릿' 블록에 있다.
   ══════════════════════════════════════════════════════ */

import { chatVideoHTML, groupVideoEvidence, videoKindLabel } from './chat_video.js';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = v => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v))) ? null : Number(v);
const r1 = v => String(Math.round(v * 10) / 10);
const f1 = v => v.toFixed(1);
const comma = v => Math.round(v).toLocaleString('ko-KR');
/* '발레코어와' · '카고팬츠와' · '레더 재킷과' — 지표 이름 앞에 누구의 값인지 붙일 때 (2026-10-02) */
const hasFinal = w => { const ch = String(w || '').trim().slice(-1); const c = ch.charCodeAt(0);
  return c >= 0xAC00 && c <= 0xD7A3 ? (c - 0xAC00) % 28 !== 0 : /[0-9lmnLMN]$/.test(ch); };
const wa = w => esc(w) + (hasFinal(w) ? '과' : '와');
const DAY = 864e5;
const dayNo = iso => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? Math.round(Date.UTC(+m[1], +m[2] - 1, +m[3]) / DAY) : null;
};
const mmdd = iso => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? (+m[2]) + '/' + (+m[3]) : '';
};
const fromDayNo = n => new Date(n * DAY).toISOString().slice(0, 10);
const path = pts => pts.map((p, i) => (i ? 'L' : 'M') + f1(p[0]) + ' ' + f1(p[1])).join(' ');
/* SVG 모양의 색·굵기는 속성으로 직접 단다 — 리포트를 사진으로 저장할 때(html-to-image)
   클래스로 건 SVG 스타일이 빠져 면이 검게, 격자가 사라졌다(2026-10-02 실측). */
const NS = ' vector-effect="non-scaling-stroke"';
const SV = {
  tplGrid: 'stroke="#ebe8e2" stroke-width="1"' + NS,
  tplBase: 'stroke="#cfcbc4" stroke-width="1"' + NS,
  tkArea: 'fill="#ff6b4a" fill-opacity="0.1" stroke="none"',
  tkAvg: 'stroke="#a8a49d" stroke-width="1" stroke-dasharray="3 4"' + NS,
  tkLine: 'fill="none" stroke="#0a0a0a" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"' + NS,
  tlOld: 'fill="#d9d5ce"', tlRecent: 'fill="#0a0a0a"', tlSpike: 'fill="#ff6b4a"',
  tlLead: 'stroke="#0a0a0a" stroke-width="1"' + NS,
  vsLineA: 'fill="none" stroke="#0a0a0a" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"' + NS,
  vsLineB: 'fill="none" stroke="#ff6b4a" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"' + NS,
  vsCross: 'stroke="#a8a49d" stroke-width="1" stroke-dasharray="2 4"' + NS,
  lcBand: 'fill="#ff6b4a" fill-opacity="0.08"',
  lcPast: 'fill="none" stroke="#0a0a0a" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"' + NS,
  lcFuture: 'fill="none" stroke="#b9b5ae" stroke-width="2" stroke-dasharray="4 5" stroke-linecap="round"' + NS,
  lcNowLine: 'stroke="#ff6b4a" stroke-width="1.4" stroke-dasharray="2 3"' + NS,
  lsGrid: 'stroke="#f1efea" stroke-width="1"' + NS, lsStem: 'stroke="#cfcbc4" stroke-width="1.2"' + NS,
};
const sv = cls => 'class="' + cls + '" ' + (SV[cls] || '');
/* ── 그래프 그릇 ──
   선·막대·면은 SVG 가 그리고(폭에 맞춰 늘어난다 · 선 굵기는 그대로), 글자와 점은 HTML 로
   얹는다. SVG 글자를 함께 늘이면 휴대폰 폭에서 6px 로 줄어 읽을 수 없고, 점은 타원이 된다.
   좌표는 viewBox 단위로 계산하고 % 로 바꿔 단다. */
const at = (x, y, W, H) => 'left:' + f1(x / W * 100) + '%;top:' + f1(y / H * 100) + '%';
const plot = (W, H, px, label, cls, shapes, over) =>
  '<div class="tplPlot ' + cls + '" style="height:' + px + 'px" role="img" aria-label="' + esc(label) + '">' +
  '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true">' + shapes + '</svg>' +
  (over || '') + '</div>';
/* align: l = 점의 오른쪽으로 · r = 점의 왼쪽으로 · c = 가운데 */
const lbl = (x, y, W, H, text, cls, align) =>
  '<span class="tplLbl ' + (align || 'l') + (cls ? ' ' + cls : '') + '" style="' + at(x, y, W, H) + '">' + esc(text) + '</span>';
const pt = (x, y, W, H, cls) => '<i class="tplPt ' + (cls || '') + '" style="' + at(x, y, W, H) + '"></i>';
const hline = (x1, x2, y, cls) => '<line ' + sv(cls) + ' x1="' + f1(x1) + '" x2="' + f1(x2) + '" y1="' + f1(y) + '" y2="' + f1(y) + '"/>';
const vline = (x, y1, y2, cls) => '<line ' + sv(cls) + ' x1="' + f1(x) + '" x2="' + f1(x) + '" y1="' + f1(y1) + '" y2="' + f1(y2) + '"/>';
const tri = up => '<svg class="tplTri" viewBox="0 0 10 10" aria-hidden="true"><path d="' +
  (up ? 'M5 1 9.5 9H.5z' : 'M5 9 .5 1h9z') + '" fill="currentColor"/></svg>';
const delta = (v, unit) => {
  const d = num(v);
  if(d === null) return '';
  const cls = d > 0 ? 'up' : d < 0 ? 'dn' : 'flat';
  return '<span class="tplDelta ' + cls + '">' + (d === 0 ? '±' : tri(d > 0)) +
    '<b>' + r1(Math.abs(d)) + (unit || '') + '</b></span>';
};
const bandClass = band => ({'과열': 'hot', '따뜻함': 'warm', '미지근': 'mild', '차가움': 'cold'}[band] || 'mild');

/* 날짜로 놓은 선 그래프 하나 — 티커 · 스토리 · VS 가 같이 쓴다 */
function lineChart(points, o){
  const pts = points.filter(p => num(p.v) !== null && dayNo(p.d) !== null);
  if(pts.length < 2) return '';
  const W = o.w, H = o.h, L = o.left ?? 34, R = W - (o.right ?? 8), T = o.top ?? 16, B = H - (o.bottom ?? 24);
  const d0 = dayNo(pts[0].d), d1 = dayNo(pts[pts.length - 1].d);
  const vs = pts.map(p => num(p.v));
  const lo = o.lo ?? Math.floor(Math.min(...vs) - 2), hi = o.hi ?? Math.ceil(Math.max(...vs) + 3);
  const X = d => L + (d1 === d0 ? 0.5 : (d - d0) / (d1 - d0)) * (R - L);
  const Y = v => T + (hi - v) / ((hi - lo) || 1) * (B - T);
  const xy = pts.map(p => [X(dayNo(p.d)), Y(num(p.v))]);
  return {X, Y, lo, hi, L, R, T, B, d0, d1, xy, pts,
    line: path(xy),
    area: path(xy) + ' L' + f1(xy[xy.length - 1][0]) + ' ' + f1(B) + ' L' + f1(xy[0][0]) + ' ' + f1(B) + ' Z'};
}

/* ── 진단: 티커 ─────────────────────────────────────── */
const RANGES = [7, 28, 90];

function tickerChart(series, n){
  const last = dayNo(series[series.length - 1].d);
  const sub = series.filter(p => last - dayNo(p.d) < n).map(p => ({d: p.d, v: p.t}));
  const W = 560, H = 186;
  const c = lineChart(sub, {w: W, h: H, left: 30, right: 10, top: 18, bottom: 26});
  if(!c) return null;
  const avg = c.pts.reduce((a, p) => a + num(p.v), 0) / c.pts.length;
  const mid = Math.round((c.lo + c.hi) / 2);
  const [lx, ly] = c.xy[c.xy.length - 1];
  const first = num(c.pts[0].v), end = num(c.pts[c.pts.length - 1].v);
  const shapes = [c.hi, mid, c.lo].map(v => hline(c.L, c.R, c.Y(v), 'tplGrid')).join('') +
    '<path ' + sv('tkArea') + ' d="' + c.area + '"/>' + hline(c.L, c.R, c.Y(avg), 'tkAvg') +
    '<path ' + sv('tkLine') + ' d="' + c.line + '"/>';
  const over = [c.hi, mid, c.lo].map(v => lbl(0, c.Y(v), W, H, String(v) + '°', 'tplAxis')).join('') +
    lbl(c.L + 4, c.Y(avg) - 9, W, H, '기간 평균 ' + r1(avg) + '°', 'tplNote') +
    pt(lx, ly, W, H, 'tkDot') + lbl(lx - 10, ly - 14, W, H, Math.round(end) + '°', 'tkEnd', 'r') +
    lbl(c.L, 178, W, H, mmdd(c.pts[0].d), 'tplAxis') +
    lbl(c.R, 178, W, H, mmdd(c.pts[c.pts.length - 1].d), 'tplAxis', 'r');
  const svg = plot(W, H, 186, '최근 ' + n + '일 트렌드 온도, ' + first + '도에서 ' + end + '도', 'tkChart', shapes, over);
  return {svg, change: end - first};
}

function ticker(b){
  const temp = num(b.temp);
  if(temp === null) return '';
  const series = (b.series || []).filter(p => num(p.t) !== null && dayNo(p.d) !== null);
  const charts = [];
  if(series.length >= 2){
    for(const n of RANGES){
      const last = dayNo(series[series.length - 1].d);
      const count = series.filter(p => last - dayNo(p.d) < n).length;
      /* 짧은 기간은 점이 모자라면 버튼을 만들지 않는다 — 두 점짜리 '그래프' 는 선 하나다 */
      if(count < (n === 7 ? 4 : 6) && n !== 90) continue;
      if(n === 90 && charts.length && count === series.filter(p => last - dayNo(p.d) < 28).length) continue;
      const c = tickerChart(series, n);
      if(c) charts.push({n, ...c});
    }
  }
  const pick = (charts.find(c => c.n === 28) || charts[charts.length - 1] || {}).n;
  const ranges = charts.length > 1
    ? '<div class="tkRanges" role="group" aria-label="기간">' + charts.map(c =>
        '<button type="button" class="tkRange' + (c.n === pick ? ' on' : '') + '" data-tk-range="' + c.n +
        '" aria-pressed="' + (c.n === pick) + '">' + c.n + '일</button>').join('') + '</div>' : '';
  const notes = charts.map(c => '<span class="tkRangeNote' + (c.n === pick ? ' on' : '') + '" data-range="' + c.n +
    '">트렌드 온도 · 최근 ' + c.n + '일 동안 <b>' + (c.change >= 0 ? '+' : '−') + r1(Math.abs(c.change)) + '°</b></span>').join('');
  const svgs = charts.map(c => c.svg.replace('class="tplPlot tkChart"',
    'class="tplPlot tkChart' + (c.n === pick ? ' on' : '') + '" data-range="' + c.n + '"')).join('');

  const d = num(b.delta_1w), prev = num(b.temp_1w_ago);
  const chips = [
    b.verdict ? '<span class="tplChip tplChip--' + bandClass(b.band) + '">' + esc(b.verdict) + '</span>' : '',
    num(b.top_pct) !== null ? '<span class="tplChip">상위 <b>' + num(b.top_pct) + '%</b></span>' : '',
    num(b.ratio) !== null ? '<span class="tplChip">4주 평균 대비 <b>×' + num(b.ratio) + '</b>' +
      (b.direction ? ' · ' + esc(b.direction) : '') + '</span>' : '',
  ].join('');
  const plats = (b.platforms || []).filter(p => num(p.temp) !== null);
  const assoc = (b.assoc || []).filter(a => a && a.name);
  const m7 = num(b.mention_7d), m28 = num(b.mention_28d);
  const side = (plats.length || assoc.length || m7 !== null)
    ? '<aside class="tkSide">' +
      /* ★ 누구의 값인지 머리에 적는다 (2026-10-02) — 티커 두 개가 나란히 서면 '플랫폼별 온도'
         '같이 뜨는 말' 이 어느 키워드 것인지 구분되지 않았다. */
      (plats.length ? '<div class="tkSideBlock"><h4>' + esc(b.term) + ' · 플랫폼별 트렌드 온도</h4>' + plats.map(p =>
        '<div class="tkPlat"><span>' + esc(p.name) + '</span><u><i data-w="' + Math.max(0, Math.min(100, Math.round(num(p.temp)))) +
        '"></i></u><b>' + Math.round(num(p.temp)) + '°</b></div>').join('') + '</div>' : '') +
      (m7 !== null || m28 !== null ? '<div class="tkSideBlock"><h4>' + esc(b.term) + ' · 언급량 (건)</h4><div class="tkMentions">' +
        (m7 !== null ? '<div><span>최근 7일</span><b>' + comma(m7) + '</b></div>' : '') +
        (m28 !== null ? '<div><span>최근 28일</span><b>' + comma(m28) + '</b></div>' : '') + '</div></div>' : '') +
      (assoc.length ? '<div class="tkSideBlock"><h4>' + wa(b.term) + ' 같이 뜨는 말 (연관어)</h4><div class="tkAssoc">' + assoc.map(a =>
        '<button type="button" class="tplChip tplChip--btn' + (a.is_new ? ' tplChip--new' : '') + '" data-kw="' + esc(a.name) + '">' +
        esc(a.name) + (a.is_new ? '<em>NEW</em>' : '') + '</button>').join('') + '</div></div>' : '') +
      '</aside>' : '';
  const story = {term: b.term, temp, delta_1w: d, verdict: b.verdict, top_pct: num(b.top_pct),
    as_of: b.as_of, assoc: assoc[0] ? assoc[0].name : null,
    series: series.slice(-28).map(p => ({d: p.d, t: num(p.t)}))};
  return '<div class="tk' + (side ? '' : ' tk--solo') + '">' +
    '<div class="tkMain">' +
      '<div class="tkHead"><b>' + esc(b.term) + '</b>' + (b.facet ? '<span class="tplTag">' + esc(b.facet) + '</span>' : '') +
        '<em>트렌드 온도' + (b.as_of ? ' · ' + esc(String(b.as_of).slice(0, 10)) + ' 기준' : '') + '</em></div>' +
      '<div class="tkNumber"><span class="tkTemp">' + Math.round(temp) + '<small>°</small></span>' +
        '<span class="tkChange">' + (d !== null ? delta(d, '°') + (prev !== null ? '<em>지난주 ' + Math.round(prev) + '°보다</em>' : '')
          : '<em>지난주 대비는 관측이 모자라 적지 않았어요</em>') + '</span></div>' +
      (chips ? '<div class="tkChips">' + chips + '</div>' : '') +
      (charts.length ? '<div class="tkChartHead">' + notes + ranges + '</div>' + svgs : '') +
    '</div>' + side +
    '<footer class="tkFoot"><span class="tplDot"></span><span>' + esc(b.verdict_text || (b.direction ? '방향: ' + b.direction : '')) + '</span>' +
      '<button type="button" class="tplStoryBtn" data-rp-story="' + esc(JSON.stringify(story)) + '">' +
      '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="3" width="11" height="18" rx="2.2"/><path d="M10 17.5h4"/></svg>스토리 이미지</button>' +
    '</footer>' +
    ((b.notes || []).length ? '<div class="tplNotes">' + b.notes.map(n => '<p>' + esc(n) + '</p>').join('') + '</div>' : '') +
  '</div>';
}

/* ── 공유용 스토리 카드 (9:16) — chat_popup 이 화면 밖에 그려 사진으로 저장한다 ── */
export function storyHTML(s){
  const temp = num(s && s.temp);
  if(temp === null) return '';
  const pts = (s.series || []).map(p => ({d: p.d, v: p.t}));
  const c = lineChart(pts, {w: 308, h: 110, left: 4, right: 4, top: 8, bottom: 6});
  const d = num(s.delta_1w);
  return '<div class="tkStoryCard">' +
    '<div class="tkStoryTop"><b>FEEDiT</b><span>TREND REPORT' + (s.as_of ? ' · ' + esc(mmdd(s.as_of)) : '') + '</span></div>' +
    '<p class="tkStoryKicker">지금 이 트렌드의 온도</p>' +
    '<p class="tkStoryTerm">' + esc(s.term) + '</p>' +
    '<p class="tkStoryTemp">' + Math.round(temp) + '<small>°</small></p>' +
    (d !== null ? '<p class="tkStoryDelta">' + (d > 0 ? '▲ ' : d < 0 ? '▼ ' : '± ') + r1(Math.abs(d)) +
      '° <span>지난주보다</span></p>' : '') +
    (c ? '<svg class="tkStoryChart" viewBox="0 0 308 110" aria-hidden="true"><path fill="#ff6b4a" fill-opacity="0.16" d="' + c.area +
      '"/><path fill="none" stroke="#ff6b4a" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round" d="' + c.line +
      '"/><circle fill="#ff6b4a" stroke="#1c1a17" stroke-width="3" cx="' + f1(c.xy[c.xy.length - 1][0]) + '" cy="' +
      f1(c.xy[c.xy.length - 1][1]) + '" r="5.5"/></svg><p class="tkStoryCap">LAST ' + (c.d1 - c.d0 + 1) + ' DAYS</p>' : '') +
    '<div class="tkStoryFacts">' +
      (s.verdict ? '<p><span>지금 구간</span><b>' + esc(s.verdict) + '</b></p>' : '') +
      (num(s.top_pct) !== null ? '<p><span>전체 순위</span><b>상위 ' + num(s.top_pct) + '%</b></p>' : '') +
      (s.assoc ? '<p><span>같이 뜨는 말</span><b>' + esc(s.assoc) + '</b></p>' : '') +
    '</div>' +
    '<div class="tkStoryFoot"><span>살까 말까? 피딧에서 물어보기</span><b>살!말?</b></div>' +
  '</div>';
}

/* ── 원인: 주석 그래프 ───────────────────────────────── */
function timeline(b){
  const pts = (b.points || []).filter(p => dayNo(p.d) !== null);
  if(pts.length < 2) return '';
  const W = 824, H = 214, L = 34, R = 820, T = 40, B = 186;
  const last = dayNo(pts[pts.length - 1].d), n = Math.max(2, num(b.window) || 60);
  const first = last - n + 1;
  const max = Math.max(...pts.map(p => num(p.m) || 0), 1);
  const hi = Math.ceil(max / 10) * 10 || 10;
  const step = (R - L) / n, bw = Math.max(2, Math.min(10, step - 3));
  const bx = d => L + (d - first) * step + (step - bw) / 2;
  const by = v => B - v / hi * (B - T);
  const spikes = (b.spikes || []).filter(s => dayNo(s.d) !== null);
  const spikeDays = new Set(spikes.map(s => s.d));
  const groups = {old: [], recent: [], spike: []};
  pts.forEach(p => {
    const m = num(p.m) || 0;
    if(!m) return;
    const dn = dayNo(p.d);
    if(dn < first) return;
    const rect = 'M' + f1(bx(dn)) + ' ' + f1(by(m)) + 'h' + f1(bw) + 'V' + B + 'h-' + f1(bw) + 'Z';
    (spikeDays.has(p.d) ? groups.spike : last - dn < 14 ? groups.recent : groups.old).push(rect);
  });
  /* 번호만 막대 위에 달고, 설명은 그래프 아래 목록으로 — 급상승이 가까이 붙으면
     그래프 안의 글자끼리 겹친다(휴대폰 폭에서는 거의 항상). */
  const over = [];
  const leads = spikes.map((s, i) => {
    const x = bx(dayNo(s.d)) + bw / 2, top = by(num(s.m) || 0);
    const y = Math.max(14, top - 22);
    over.push('<span class="tlBadge" style="' + at(x, y, W, H) + '">' + (i + 1) + '</span>');
    return vline(x, y + 10, top - 3, 'tlLead');
  }).join('');
  const marks = spikes.map((s, i) =>
    '<li><span class="tlBadge tlBadge--inline">' + (i + 1) + '</span><b>' + esc(mmdd(s.d)) + '</b>' +
    '<span>언급이 평소의 <b>' + num(s.x) + '배</b>' + (s.src ? ' · 그 무렵 ' + esc(s.src) : '') + '</span>' +
    (s.body ? '<q>' + esc(s.body) + '</q>' : '') + '</li>').join('');
  [hi, hi / 2].forEach(v => over.push(lbl(0, by(v), W, H, comma(v), 'tplAxis')));
  over.push(lbl(L, 204, W, H, mmdd(fromDayNo(first)), 'tplAxis'));
  over.push(lbl((L + R) / 2, 204, W, H, mmdd(fromDayNo(first + Math.floor(n / 2))), 'tplAxis', 'c'));
  over.push(lbl(R, 204, W, H, mmdd(fromDayNo(last)), 'tplAxis', 'r'));
  const chart = plot(W, H, 214, '최근 ' + n + '일 하루 언급량' + (spikes.length ? ', 급상승 ' + spikes.length + '번' : ''), 'tlChart',
    [hi, hi / 2].map(v => hline(L, R, by(v), 'tplGrid')).join('') + hline(L, R, B, 'tplBase') +
    '<path ' + sv('tlOld') + ' d="' + groups.old.join(' ') + '"/><path ' + sv('tlRecent') + ' d="' + groups.recent.join(' ') + '"/>' +
    '<path ' + sv('tlSpike') + ' d="' + groups.spike.join(' ') + '"/>' + leads, over.join('')) +
    (marks ? '<ol class="tlMarks">' + marks + '</ol>' : '');

  /* 같은 영상에서 나온 설명·댓글은 카드 하나로 묶는다 — 썸네일이 겹쳐 반복되지 않게. */
  const evMeta = e => [e.at ? mmdd(e.at) : '', e.tone || ''].filter(Boolean).join(' · ');
  const cards = groupVideoEvidence(b.evidence).slice(0, 3).map((g, i) => {
    const e = g.items[0];
    if(g.video) return '<div class="tlCard tlCard--video">' +
      chatVideoHTML({url:e.url, no:String(i + 1).padStart(2, '0'), source:e.src || 'YOUTUBE',
        notes:g.items.map(x => ({ label:videoKindLabel(x.kind), text:x.body, meta:evMeta(x) }))}) + '</div>';
    const tag = e.url ? 'a' : 'div';
    const href = e.url ? ' href="' + esc(e.url) + '" target="_blank" rel="noopener"' : '';
    return '<' + tag + ' class="tlCard"' + href + '>' +
      '<span class="tlCardNo">' + String(i + 1).padStart(2, '0') + '</span>' +
      '<span class="tlCardSrc">' + esc([e.src, e.kind].filter(Boolean).join(' · ')) + '</span>' +
      '<q>' + esc(e.body) + '</q>' +
      '<span class="tlCardMeta">' + esc([e.at ? mmdd(e.at) : '', e.tone || ''].filter(Boolean).join(' · ')) +
        (e.url ? ' <i aria-hidden="true">↗</i>' : '') + '</span>' +
    '</' + tag + '>';
  }).join('');
  const s = b.sentiment;
  const sent = s ? '<div class="tlSent"><h4>반응</h4><div><div class="tlSentBar" role="img" aria-label="긍정 ' + s.pos + '%, 중립 ' +
      s.neu + '%, 부정 ' + s.neg + '%"><i class="p" style="width:' + s.pos + '%"></i><i class="u" style="width:' + s.neu +
      '%"></i><i class="n" style="width:' + s.neg + '%"></i></div><p><span>긍정 <b class="up">' + s.pos + '%</b></span>' +
      '<span>중립 <b>' + s.neu + '%</b></span><span>부정 <b class="dn">' + s.neg + '%</b></span><em>최근 ' + s.days +
      '일 · 반응 ' + comma(s.n) + '건</em></p></div></div>' : '';
  return '<div class="tl">' +
    '<p class="tlKicker">WHY NOW — ' + esc(b.term) + '</p>' +
    '<p class="tlDek">최근 ' + n + '일 하루 언급량' + (spikes.length ? ' · 평소보다 크게 튄 날에 번호를 붙였어요' :
      ' · 이 기간엔 평소보다 크게 튄 날이 없었어요') + '</p>' + chart +
    (cards ? '<div class="tlCards">' + cards + '</div>' : '') + sent + '</div>';
}

/* ── 비교: VS ───────────────────────────────────────── */
function versus(b){
  const a = b.a || {}, c = b.b || {};
  if(num(a.temp) === null || num(c.temp) === null) return '';
  const side = (s, cls) => '<div class="vsSide ' + cls + '">' +
    '<span class="vsName"><i></i>' + esc(s.term) + '</span>' +
    '<span class="vsTemp" title="트렌드 온도">' + Math.round(num(s.temp)) + '<small>°</small></span>' +
    '<span class="vsMetric">트렌드 온도</span>' +
    '<span class="vsMeta">' + delta(s.delta_1w, '°') +
      (s.verdict ? '<span class="tplChip">' + esc(s.verdict) + '</span>' : '') + '</span></div>';
  /* 두 선을 같은 축에 — 날짜가 겹치는 구간에서 앞뒤가 바뀐 마지막 날을 '역전' 으로 적는다 */
  const sa = (a.series || []).map(p => ({d: p.d, v: p.t})), sb = (c.series || []).map(p => ({d: p.d, v: p.t}));
  const all = sa.concat(sb).filter(p => num(p.v) !== null && dayNo(p.d) !== null);
  let chart = '';
  if(sa.length >= 2 && sb.length >= 2){
    const vs = all.map(p => num(p.v));
    const lo = Math.floor(Math.min(...vs) - 2), hi = Math.ceil(Math.max(...vs) + 2);
    const d0 = Math.min(...all.map(p => dayNo(p.d))), d1 = Math.max(...all.map(p => dayNo(p.d)));
    const o = {w: 824, h: 176, left: 30, right: 84, top: 22, bottom: 24, lo, hi};
    const mk = pts => {
      const xy = pts.filter(p => num(p.v) !== null).map(p => [o.left + (d1 === d0 ? .5 : (dayNo(p.d) - d0) / (d1 - d0)) * (o.w - o.right - o.left),
        o.top + (hi - num(p.v)) / ((hi - lo) || 1) * (o.h - o.bottom - o.top)]);
      return xy;
    };
    const xa = mk(sa), xb = mk(sb);
    const byDay = arr => Object.fromEntries(arr.map(p => [p.d, num(p.v)]));
    const ma = byDay(sa), mb = byDay(sb);
    const common = Object.keys(ma).filter(d => mb[d] !== undefined && ma[d] !== null && mb[d] !== null).sort();
    /* 같은 값으로 맞닿은 날을 지나 뒤집혀도 역전이다 — 맞닿기 시작한 날을 적는다 */
    let cross = null, last = 0, touch = null;
    for(const d of common){
      const s = Math.sign(ma[d] - mb[d]);
      if(!s){ touch = touch || d; continue; }
      if(last && s !== last) cross = touch || d;
      last = s; touch = null;
    }
    const Y = v => o.top + (hi - v) / ((hi - lo) || 1) * (o.h - o.bottom - o.top);
    const X = d => o.left + (d1 === d0 ? .5 : (dayNo(d) - d0) / (d1 - d0)) * (o.w - o.right - o.left);
    const endA = xa[xa.length - 1], endB = xb[xb.length - 1];
    const gap = Math.abs(endA[1] - endB[1]) < 14 ? (endA[1] < endB[1] ? [-7, 7] : [7, -7]) : [0, 0];
    const W = 824, H = 176;
    const over = [hi, Math.round((hi + lo) / 2), lo].map(v => lbl(0, Y(v), W, H, String(v) + '°', 'tplAxis')).join('') +
      (cross ? lbl(X(cross) + 6, 12, W, H, '역전 · ' + mmdd(cross), 'tlHead') : '') +
      pt(endA[0], endA[1], W, H, 'vsDotA') + pt(endB[0], endB[1], W, H, 'vsDotB') +
      lbl(endA[0] + 10, endA[1] + gap[0], W, H, a.term, 'vsEndA') +
      lbl(endB[0] + 10, endB[1] + gap[1], W, H, c.term, 'vsEndB') +
      lbl(o.left, 168, W, H, mmdd(fromDayNo(d0)), 'tplAxis') +
      lbl(W - o.right, 168, W, H, mmdd(fromDayNo(d1)), 'tplAxis', 'r');
    chart = plot(W, H, 176, a.term + '과 ' + c.term + '의 트렌드 온도 추이' + (cross ? ', ' + mmdd(cross) + ' 역전' : ''), 'vsChart',
      [hi, Math.round((hi + lo) / 2), lo].map(v => hline(o.left, W - o.right, Y(v), 'tplGrid')).join('') +
      (cross ? vline(X(cross), o.top, H - o.bottom, 'vsCross') : '') +
      '<path ' + sv('vsLineA') + ' d="' + path(xa) + '"/><path ' + sv('vsLineB') + ' d="' + path(xb) + '"/>', over);
    /* 그래프가 무슨 값인지 · 어느 선이 누구인지 — 끝 이름표는 좁은 화면에서 숨으므로 범례를 따로 둔다 */
    chart = '<div class="vsChartHead"><b>트렌드 온도 추이 (°)</b>' +
      '<span class="vsKey a"><i></i>' + esc(a.term) + '</span><span class="vsKey b"><i></i>' + esc(c.term) + '</span></div>' + chart;
  }
  const rows = (b.rows || []).filter(r => num(r.a) !== null && num(r.b) !== null).map(r => {
    const lo = num(r.lo) ?? Math.min(r.a, r.b), hi = num(r.hi) ?? Math.max(r.a, r.b);
    const pct = v => Math.max(0, Math.min(100, (v - lo) / ((hi - lo) || 1) * 100));
    const pa = pct(num(r.a)), pb = pct(num(r.b));
    const left = Math.min(pa, pb), width = Math.abs(pa - pb);
    const win = r.better === 'a' ? a.term : r.better === 'b' ? c.term : '같음';
    return '<div class="vsRow"><span class="vsK">' + esc(r.k) + '</span>' +
      '<div class="vsTrack"><i class="vsSpan" style="left:' + f1(left) + '%;width:' + f1(width) + '%"></i>' +
        '<i class="vsDot a" style="left:' + f1(pa) + '%"></i><i class="vsDot b" style="left:' + f1(pb) + '%"></i>' +
        '<em class="vsLab a' + (pa <= pb ? ' l' : '') + '" style="left:' + f1(pa) + '%" title="' + esc(a.term) + '">' + esc(r.av) + '</em>' +
        '<em class="vsLab b' + (pb < pa ? ' l' : '') + '" style="left:' + f1(pb) + '%" title="' + esc(c.term) + '">' + esc(r.bv) + '</em></div>' +
      '<span class="vsWin ' + (r.better || 'tie') + '">' + esc(win) + '</span></div>';
  }).join('');
  return '<div class="vs"><div class="vsHero">' + side(a, 'a') + '<span class="vsBadge">VS</span>' + side(c, 'b') + '</div>' +
    chart + (rows ? '<div class="vsRows"><div class="vsRow vsRow--head"><span>지표</span><span>두 대상의 거리 ' +
      '<i class="vsKey a"><i></i>' + esc(a.term) + '</i><i class="vsKey b"><i></i>' + esc(c.term) + '</i></span><span>앞선 쪽</span></div>' +
    rows + '</div>' : '') + '</div>';
}

/* ── 순위: 리더보드 ─────────────────────────────────── */
function leaderboard(b){
  const items = (b.items || []).filter(it => it && it.term);
  if(!items.length) return '';
  const asOf = String(b.as_of || '').slice(0, 10);
  const day = it => (it.date && String(it.date).slice(0, 10) !== asOf) ? mmdd(it.date) : '';
  const temp = it => num(it.temp) === null ? '—' : Math.round(num(it.temp)) + '°';
  const podium = items.slice(0, 3).map((it, i) =>
    '<button type="button" class="lbCard' + (i === 0 ? ' lbCard--top' : '') + '" data-kw="' + esc(it.term) + '">' +
      '<span class="lbRank">' + (it.rank || i + 1) + '</span>' +
      '<span class="lbName">' + esc(it.term) + '</span>' +
      '<span class="lbTemp" title="트렌드 온도">' + temp(it) + '<small>트렌드 온도</small></span>' +
      '<span class="lbMeta">' + (it.verdict ? '<span class="tplChip tplChip--' + bandClass(it.band) + '">' + esc(it.verdict) + '</span>' : '') +
        esc([it.facet, day(it)].filter(Boolean).join(' · ')) + '</span>' +
    '</button>').join('');
  const rest = items.slice(3).map((it, i) =>
    '<button type="button" class="lbRow" data-kw="' + esc(it.term) + '">' +
      '<span class="lbRank">' + (it.rank || i + 4) + '</span>' +
      '<span class="lbName">' + esc(it.term) + '<small>' + esc([it.facet, day(it)].filter(Boolean).join(' · ')) + '</small></span>' +
      (it.verdict ? '<span class="tplChip tplChip--' + bandClass(it.band) + '">' + esc(it.verdict) + '</span>' : '<span></span>') +
      '<u><i data-w="' + Math.max(0, Math.min(100, Math.round(num(it.temp) || 0))) + '"></i></u>' +
      '<b title="트렌드 온도">' + temp(it) + '</b></button>').join('');
  const foot = (num(b.window_days) ? '최근 ' + num(b.window_days) + '일 안에서 용어마다 마지막 날의 온도순' : '트렌드 온도순') +
    (b.short ? ' · 찾은 것 ' + items.length + '개가 전부예요' : '') + ' · 누르면 그 용어를 물어봐요';
  return '<div class="lb"><div class="lbPodium">' + podium + '</div>' +
    (rest ? '<div class="lbRows"><div class="lbRowsHead"><span>순위 · 용어</span><span>트렌드 온도 (°)</span></div>' + rest + '</div>' : '') +
    '<p class="tplFoot">' + esc(foot) + '</p></div>';
}

/* ── 판정: 살말 도장 ─────────────────────────────────── */
function verdict(b){
  const score = num(b.score);
  if(score === null) return '';
  const rec = String(b.rec || '보류');
  const kind = rec === '살' ? 'buy' : rec === '말' ? 'pass' : 'hold';
  const stamp = kind === 'buy' ? ['살!', 'BUY'] : kind === 'pass' ? ['말!', 'PASS'] : ['보류', 'HOLD'];
  const conf = {'높음': 3, '보통': 2, '낮음': 1}[b.confidence] || 1;
  const maxW = Math.max(35, ...(b.signals || []).map(s => num(s.weight) || 0), ...(b.missing || []).map(s => num(s.weight) || 0));
  const bar = (w, fill, empty) => '<u class="vdTrack' + (empty ? ' empty' : '') + '" style="width:' + f1((num(w) || 0) / maxW * 100) +
    '%">' + (empty ? '' : '<i data-w="' + Math.max(0, Math.min(100, Math.round(fill))) + '"></i>') + '</u>';
  const rows = (b.signals || []).map(s =>
    '<div class="vdRow"><div class="vdRowHead"><span>' + esc(s.label) + (s.why ? '<small>' + esc(s.why) + '</small>' : '') +
      '</span><b>' + Math.round(num(s.score) || 0) + '<em>점 · 가중치 ' + (num(s.weight) || 0) + '</em></b></div>' +
      bar(s.weight, num(s.score) || 0, false) + '</div>').join('') +
    (b.missing || []).map(s =>
    '<div class="vdRow vdRow--missing"><div class="vdRowHead"><span>' + esc(s.label) + '</span><b><em>자료 없음 · 가중치 ' +
      (num(s.weight) || 0) + '</em></b></div>' + bar(s.weight, 0, true) + '</div>').join('');
  return '<div class="vd vd--' + kind + '">' +
    '<div class="vdHero">' +
      '<div class="vdStamp" aria-label="판정 ' + esc(rec) + '"><b>' + stamp[0] + '</b><span>' + stamp[1] + '</span></div>' +
      '<div class="vdScore"><span>살말 지수' + (b.term ? ' · ' + esc(b.term) : '') + '</span>' +
        '<p><b>' + Math.round(score) + '</b><em>/ 100</em></p>' +
        '<span>' + (b.allowed ? '확인된 신호만으로 계산했어요' : '근거가 모자라 살/말을 정하지 않았어요') + '</span></div>' +
      '<div class="vdConf"><span>신뢰도</span><div><i class="' + (conf >= 1 ? 'on' : '') + '"></i><i class="' + (conf >= 2 ? 'on' : '') +
        '"></i><i class="' + (conf >= 3 ? 'on' : '') + '"></i><b>' + esc(b.confidence || '낮음') + '</b></div>' +
        '<span>근거 충족 ' + (num(b.coverage) || 0) + '%</span></div>' +
    '</div>' +
    (rows ? '<div class="vdParts"><div class="vdPartsHead"><b>살말 지수 ' + Math.round(score) + '점은 이렇게 나왔어요</b>' +
      '<span>막대 길이 = 가중치 · 채운 만큼 = 점수</span></div>' + rows +
      (b.missing_note ? '<p class="tplFoot">' + esc(b.missing_note) + '</p>' : '') + '</div>' : '') +
  '</div>';
}

/* ── 수명주기 ───────────────────────────────────────── */
const STAGES = [['태동', 0, .25], ['확산', .25, .45], ['정점', .45, .6], ['쇠퇴', .6, 1]];

function lifecycle(b){
  const stage = STAGES.find(s => s[0] === b.stage);
  if(!stage) return '';
  const W = 470, H = 186, L = 16, R = 454, T = 30, B = 150;
  const f = t => Math.pow(t, 1.6) * Math.exp(-3.2 * t);
  const fmax = f(.5);
  const X = t => L + t * (R - L), Y = t => B - f(t) / fmax * (B - T);
  const curve = (a, z) => { const p = []; for(let i = 0; i <= 48; i++){ const t = a + (z - a) * i / 48; p.push([X(t), Y(t)]); } return path(p); };
  /* 진행도(0~100)를 그 단계 구간 안에 놓는다. 판정(stage)과 진행도가 조금 어긋나도
     점이 다른 단계 칸에 서지 않게 — 화면이 말하는 단계는 판정이 정한다. */
  const prog = num(b.progress);
  const raw = prog === null ? (stage[1] + stage[2]) / 2 : prog / 100;
  const now = Math.max(stage[1] + .02, Math.min(stage[2] - .02, raw));
  const nx = X(now), ny = Y(now);
  const meta = [num(b.age_weeks) !== null ? '처음 오른 뒤 ' + num(b.age_weeks) + '주째' : '',
    b.peak_date && (b.stage === '정점' || b.stage === '쇠퇴') ? '최고점 ' + mmdd(b.peak_date) : ''].filter(Boolean).join(' · ');
  return '<div class="lc"><div class="lcHead"><b>트렌드 수명주기' + (b.term ? ' · ' + esc(b.term) : '') + '</b>' +
    '<span>지금 <b class="lcStage">' + esc(b.stage) + '</b>' + (meta ? ' · ' + esc(meta) : '') + '</span></div>' +
    plot(W, H, 186, '수명주기 곡선. 지금은 ' + b.stage + ' 단계', 'lcChart',
      '<rect ' + sv('lcBand') + ' x="' + f1(X(stage[1])) + '" y="' + T + '" width="' + f1(X(stage[2]) - X(stage[1])) + '" height="' + (B - T + 12) + '"/>' +
      STAGES.slice(1).map(s => vline(X(s[1]), T, B, 'tplGrid')).join('') + hline(L, R, B, 'tplBase') +
      '<path ' + sv('lcFuture') + ' d="' + curve(now, 1) + '"/><path ' + sv('lcPast') + ' d="' + curve(0, now) + '"/>' + vline(nx, ny, B, 'lcNowLine'),
      '<span class="lcPill" style="' + at(nx, ny - 25, W, H) + '">지금 여기</span>' + pt(nx, ny, W, H, 'lcNow') +
      STAGES.map(s => lbl(X((s[1] + s[2]) / 2), 170, W, H, s[0], s[0] === b.stage ? 'lcLabel on' : 'lcLabel', 'c')).join('')) +
    '<p class="tplFoot">28일 언급 흐름이 최고점 대비 어디에 있는지로 판정했어요 · 트렌드 분석 화면과 같은 규칙</p></div>';
}

/* ── 연관: 오빗 ─────────────────────────────────────── */
function orbit(b){
  const items = (b.items || []).filter(it => it && it.name && num(it.lift) !== null).slice(0, 8);
  if(items.length < 3) return '';
  const lifts = items.map(it => num(it.lift));
  const hi = Math.max(...lifts), lo = Math.min(...lifts);
  const coMax = Math.max(...items.map(it => num(it.co) || 1), 1);
  const dist = l => 27 + (hi - l) / ((hi - lo) || 1) * 17;          /* 상자 폭의 % — 가운데 원과 겹치지 않게 27%부터 */
  const bubbles = items.map((it, i) => {
    const a = (-90 + i * (360 / items.length) + (i % 2 ? 14 : 0)) * Math.PI / 180;
    const d = dist(num(it.lift));
    const x = 50 + d * Math.cos(a), y = 50 + d * Math.sin(a);
    const size = 30 + Math.round(Math.sqrt((num(it.co) || 1) / coMax) * 22);
    return '<button type="button" class="obBubble' + (it.is_new ? ' new' : '') + '" data-kw="' + esc(it.name) + '" style="left:' + f1(x) +
      '%;top:' + f1(y) + '%;--ob:' + size + 'px" aria-label="' + esc(it.name + ', 연관 ×' + it.lift) + '"><b>×' + r1(num(it.lift)) +
      '</b><span>' + esc(it.name) + '</span></button>';
  }).join('');
  const rings = [27, 35.5, 44].map((r, i) => '<circle cx="50" cy="50" r="' + r + '" fill="none" stroke="#e4e1db" stroke-width="0.3"' +
    (i ? ' stroke-dasharray="' + (i === 1 ? '1 1.2' : '.4 1.2') + '"' : '') + '/>').join('');
  const list = items.map(it =>
    '<button type="button" class="obRow" data-kw="' + esc(it.name) + '"><span class="obSw' + (it.is_new ? ' new' : '') + '"></span>' +
    '<span class="obName">' + esc(it.name) + (it.is_new ? '<em>NEW</em>' : '') + '</span>' +
    '<b>×' + r1(num(it.lift)) + '</b><small>함께 ' + comma(num(it.co) || 0) + '회</small></button>').join('');
  return '<div class="ob"><div class="obMap" role="img" aria-label="' + esc(b.term) + '를 가운데 두고 같이 언급되는 말을 연관 강도 순으로 배치">' +
    '<svg viewBox="0 0 100 100" aria-hidden="true">' + rings + '</svg>' +
    '<span class="obCenter">' + esc(b.term) + '</span>' + bubbles + '</div>' +
    '<div class="obList"><div class="obListHead"><b>' + esc(b.term) + ' 연관어 · 연관 강도 순</b>' +
      '<span>×는 ' + wa(b.term) + ' 우연보다 몇 배 자주 같이 나오나</span></div>' + list +
    '<p class="tplFoot">NEW 는 이번 주 처음 같이 언급된 말 · 누르면 그 말을 물어봐요</p></div></div>';
}

/* ── 관측 부족 ───────────────────────────────────────── */
function lowsignal(b){
  const n = num(b.n) || 0, need = Math.max(1, num(b.need) || 20), win = num(b.window) || 28;
  const ticks = Array.from({length: Math.min(need, 40)}, (_, i) =>
    '<i class="' + (i < Math.round(Math.min(n, need) / need * Math.min(need, 40)) ? 'on' : '') + '"></i>').join('');
  const pts = (b.points || []).filter(p => dayNo(p.d) !== null && num(p.m));
  let dots = '';
  if(pts.length){
    const last = dayNo(pts[pts.length - 1].d), first = last - win + 1;
    const max = Math.max(...pts.map(p => num(p.m)), 1);
    const X = d => 8 + (d - first) / (win - 1) * 808, Y = v => 86 - v / max * 64;
    const W = 824, H = 108;
    dots = plot(W, H, 108, '최근 ' + win + '일 중 관측된 ' + pts.length + '일의 언급 수', 'lsChart',
      Array.from({length: win}, (_, i) => vline(X(first + i), 14, 86, 'lsGrid')).join('') + hline(0, W, 86, 'tplBase') +
      pts.map(p => vline(X(dayNo(p.d)), 86, Y(num(p.m)), 'lsStem')).join(''),
      pts.map(p => pt(X(dayNo(p.d)), Y(num(p.m)), W, H, 'lsDot')).join('') +
      lbl(0, 100, W, H, mmdd(fromDayNo(first)), 'tplAxis') + lbl(W, 100, W, H, mmdd(fromDayNo(last)), 'tplAxis', 'r'));
  }
  const srcs = (b.sources || []).map(s => esc(s.name) + ' ' + comma(num(s.n) || 0)).join(' · ');
  const near = (b.near || []).filter(Boolean);
  return '<div class="ls">' +
    '<div class="lsTop"><div><span class="lsLabel"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/></svg>' +
      esc(b.term) + ' · 관측 부족</span><h4>아직 온도를 매기기엔<br>관측이 적어요</h4>' +
      '<p>최근 ' + win + '일 동안 ' + comma(n) + '건 보였어요. 트렌드 판단은 <b>' + comma(need) + '건</b>부터 해요 — 그 전 숫자는 우연에 크게 흔들려서 보여 드리지 않아요.</p></div>' +
      '<div class="lsMeter"><div><b>판단까지</b><span><b>' + comma(n) + '</b> / ' + comma(need) + '건</span></div>' +
      '<div class="lsTicks" aria-hidden="true">' + ticks + '</div></div></div>' +
    (dots ? '<div class="lsDots"><div class="lsDotsHead"><b>관측된 날만 점으로</b><span>선으로 잇지 않았어요 — 빈 날은 \'0\'이 아니라 \'모름\'이에요</span></div>' + dots + '</div>' : '') +
    '<div class="lsFacts">' +
      (b.first_seen ? '<div><span>처음 보인 날</span><b>' + esc(mmdd(b.first_seen)) + '</b></div>' : '') +
      (srcs ? '<div><span>주로 나온 곳</span><b>' + srcs + '</b></div>' : '') +
      (near.length ? '<div><span>' + wa(b.term) + ' 같이 보인 말</span><p>' + near.map(x => '<button type="button" class="tplChip tplChip--btn" data-kw="' +
        esc(x) + '">' + esc(x) + '</button>').join('') + '</p></div>' : '') +
    '</div>' +
    '<div class="lsActs"><button type="button" class="tplBtn" data-kw="' + esc(b.term + '랑 비슷한 스타일 알려줘') + '">비슷한 스타일 보기</button></div>' +
  '</div>';
}

export const TEMPLATE_BLOCKS = {ticker, timeline, versus, leaderboard, verdict, lifecycle, orbit, lowsignal};
export const TEMPLATE_LABEL = {ticker: 'TICKER', verdict: 'VERDICT', why: 'WHY NOW', versus: 'VERSUS',
  leaderboard: 'LEADERBOARD', orbit: 'ORBIT', lowsignal: 'LOW SIGNAL'};

/* 티커의 기간 버튼 — 서버를 다시 부르지 않고 미리 그려 둔 그래프만 바꿔 단다 */
export function tickerRange(btn){
  const box = btn && btn.closest('.tk');
  if(!box) return;
  const n = btn.dataset.tkRange;
  box.querySelectorAll('[data-tk-range]').forEach(b => {
    const on = b.dataset.tkRange === n;
    b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on));
  });
  box.querySelectorAll('[data-range]').forEach(el => el.classList.toggle('on', el.dataset.range === n));
}
