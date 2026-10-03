/* 트렌드 화면이 실제로 실데이터를 보는지 — 호출부까지 이어졌는지 본다.
 *
 * ★ 왜 필요한가
 *   chart_engine 에 실데이터 경로를 냈지만, dispatch.js 가 `term` 을 안 넘기면
 *   그 경로가 한 번도 안 탄다. 배선을 해 놓고 연결을 빼먹은 것을 잡는 시험이다.
 *   실제로 처음엔 그 상태였다 — 화면이 계속 씨드 난수였다.
 *
 * 돌리는 법:  node tests/trend_wiring.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const W = new URL('..', import.meta.url).href.replace(/\/$/, '');  // 이 파일 기준 프론트 뿌리
const dom = new JSDOM('<!doctype html><div id="c"></div>', { url: 'http://localhost:5173/' });
/* 차트가 new CustomEvent('gwin') 을 쏜다 — Node 전역 CustomEvent 는 jsdom 요소가 받지 않는다 */
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node','CustomEvent'])
  globalThis[k] = k === 'window' ? dom.window : dom.window[k];
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};

let reply = null, calls = [];
globalThis.fetch = async (u) => { calls.push(u);
  return { ok: true, status: 200,
    text: async () => JSON.stringify(reply), json: async () => reply }; };

const live = await import(`${W}/trend/static/js/live_data.js`);
const { gChart } = await import(`${W}/trend/static/js/chart_engine.js`);

let pass = 0, fail = 0;
const t = async (n, f) => { try { await f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; } };
const host = () => { document.body.innerHTML = '<div id="c"></div>'; return document.getElementById('c'); };
const days = (n) => { const o=[]; for(let i=n-1;i>=0;i--){ const d=new Date(); d.setDate(d.getDate()-i);
  o.push({date:d.toISOString().slice(0,10),mention:10+(i%7),temp:50+(i%20),document:3,sentiment:0.2}); } return o; };

// ── dispatch.js 가 term·field 를 넘기는지 (소스 대조) ──
const src = fs.readFileSync(new URL('../trend/static/js/dispatch.js', import.meta.url), 'utf8');
const apiSrc = fs.readFileSync(new URL('../../backend/apps/api/views.py', import.meta.url), 'utf8');
const popSrc = fs.readFileSync(new URL('../trend/static/js/assoc_popover.js', import.meta.url), 'utf8');
await t('★ 온도 차트가 term 을 넘긴다', () => {
  assert.match(src, /G_CFG\.tempMain=\{key:kw\+'temp',term:kw/);
  assert.match(src, /field:'mention'/);
  assert.match(src, /field:'temp'/);
});
await t('★ 연관어는 term, 긍부정은 직접 집계 rows 를 넘긴다', () => {
  assert.match(src, /G_CFG\.assocMain=\{key:kw\+'assoc',term:kw/);
  assert.match(src, /sentPie\(\$\('\[data-chart="sentMain"\]'\),\{key:kw\+'sent',rows:rows/);
  assert.match(src, /sentimentUrl\(kw,KW\.f\)/);
});
await t('연관어 이름 옆에 내부 검색 출처 배지를 붙이지 않는다', () => {
  assert.doesNotMatch(src, /basisChip/);
  assert.doesNotMatch(src, /class="axSrc"/);
  assert.match(src, /assocDisplayTerm\(a\.term\)/);
  assert.match(src, /\\s\*\\\(\(\?:검색\|둘\\s\*다\)\\\)\\s\*\$/);
});
await t('연관어는 누적 기준선과 최근 28일을 합치고 적은 문서의 순위를 보정한다', () => {
  assert.match(apiSrc, /metric_version__startswith="feedit-l2-"/);
  assert.match(apiSrc, /exclude\(metric_version__startswith="feedit-l2-"\)/);
  assert.match(apiSrc, /ASSOC_WINDOW_DAYS = 28/);
  assert.match(apiSrc, /math\.log1p\(support\)/);
  assert.match(apiSrc, /limit", 200/);
});
await t('연관도순과 언급량순은 같은 축의 직전 28일 순위를 각각 비교한다', () => {
  assert.match(apiSrc, /"feature_change": feature_change/);
  assert.match(apiSrc, /"cooc_change": cooc_change/);
  assert.match(apiSrc, /"recent_cooccurrence": recent_cooccurrence/);
  assert.match(apiSrc, /"is_historical": not bool\(item\.get\("recent_bases"\)\)/);
  assert.match(apiSrc, /"weekly_counts": weekly_counts\.get\(tid, \[\]\)/);
  assert.match(apiSrc, /"ranking_scope": "cumulative"/);
  assert.match(src, />연관도순<\/button>/);
  assert.match(src, /sort === 'cooc' \? a\.cooc_change/);
  assert.match(src, /\(b\.cooccurrence \|\| 0\) - \(a\.cooccurrence \|\| 0\)/);
});
await t('최다 연관어 카드도 목록과 같은 통합 점수를 쓴다', () => {
  assert.match(src, /const strength = a => a\.score != null \? a\.score/);
});
await t('포화도 문구는 최근 28일로 보이고 최근 활동은 팝오버 주별 값으로 분리한다', () => {
  assert.match(src, /const MAX_TAGS = AX_ORDER\.length \* 10/);
  assert.match(src, /Math\.min\(10, \(groups\[c\] \|\| \[\]\)\.length\)/);
  assert.doesNotMatch(src, /const byPmi = all\.slice\(0, 10\)/);
  assert.match(src, /최근 ' \+ A\.window_days \+ '일 기준으로 '/);
  assert.doesNotMatch(src, /누적 전체 기준으로/);
  assert.match(src, /'언급량 ' \+ \(a\.cooccurrence \|\| 0\) \+ '건'/);
  assert.match(src, /spark: a\.weekly_counts \|\| null/);
});
await t('연관어 카드는 5개에서 10개까지만 펼치고 이후 순위를 페이지로 넘긴다', () => {
  assert.match(src, /const AX_SHOW = 5/);
  assert.match(src, /const AX_PAGE = 10/);
  assert.match(src, /data-page-dir="next"/);
  assert.match(src, /data-page-dir="prev"/);
  assert.match(src, /class="axCollapseBtn"/);
  assert.match(src, /if \(pages <= 1\)[\s\S]*\? rows \+ '<button type="button" class="axCollapseBtn">− 접기<\/button>'[\s\S]*: rows;/);
  assert.doesNotMatch(src, /axRow\.axHide/);
});
await t('연관어별 주차 추이가 없으면 빈 그래프 축도 숨긴다', () => {
  assert.match(popSrc, /sparkBox\.hidden=pts\.length<=1/);
});
await t('그리기 전에 prime 을 부른다', () => {
  assert.match(src, /prime\(kw\)\.then/);
  assert.match(src, /stateOf\(kw\)\.status==='unknown'/);
  assert.match(src, /primeOnce\(id,sentimentUrl\(KW\.q,KW\.f\)\)/);
});
await t('★ 늦게 온 응답이 딴 탭을 덮지 않는다', () => {
  assert.match(src, /if\(TR_CUR===id\) trRender\(id\)/);
});
await t('★ 금주 추천 영상은 검색 목업이 아니라 개인화 API의 영상 ID를 쓴다', () => {
  assert.match(src, /weeklyVideos\(term\)/);   // 이번 주 가장 많이 검색한 키워드로 찾는다
  assert.match(src, /video\.embed_url/);
  assert.doesNotMatch(src, /embed\?listType=search/);
  assert.match(src, /조회 .*metrics\.views/);
});

// ── 실제로 그려 본다 ──
await t('값이 있으면 두 계열 다 실값으로 그린다', async () => {
  reply = { status:'ok', data:{ term:'발레코어', facet:'STYLE', series: days(90) } };
  await live.prime('발레코어');
  const el = host();
  gChart(el, { key:'k', term:'발레코어', min:0, max:100,
    sets:[{id:'m',field:'mention'},{id:'t',field:'temp'}] });
  assert.equal(el.dataset.live, 'ok');
  assert.ok(el.querySelector('svg'));
});

await t('★ 한 계열만 없어도 반쪽짜리로 안 그린다', async () => {
  const s = days(90).map(p => ({ ...p, temp: null }));   // 온도가 아직 안 들어옴
  reply = { status:'ok', data:{ term:'새틴', facet:'MATERIAL', series: s },
            unavailable:{ fields:['temp'], reason:'temp 가 아직 비어 있습니다.' } };
  await live.prime('새틴');
  const el = host();
  gChart(el, { key:'k', term:'새틴', sets:[{id:'m',field:'mention'},{id:'t',field:'temp'}] });
  assert.equal(el.dataset.live, 'partial');
  assert.ok(/측정 불가/.test(el.textContent));
  assert.ok(/temp 가 아직 비어/.test(el.textContent));
});

await t('지표가 0행이면 그 사실을 화면에 적는다', async () => {
  reply = { status:'empty', reason:'적재가 아직 안 돌았습니다.' };
  await live.prime('키르시');
  const el = host();
  gChart(el, { key:'k', term:'키르시', sets:[{id:'m',field:'mention'}] });
  assert.equal(el.dataset.live, 'unavailable');
  assert.ok(/적재가 아직/.test(el.textContent));
});

await t('같은 용어를 여러 번 열어도 요청은 한 번', async () => {
  calls = [];
  await live.prime('발레코어'); await live.prime('발레코어');
  assert.equal(calls.length, 0, '캐시에 있으면 다시 안 부른다');
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
