/* 검색 전 빈 화면 · 난수 제거 · 못 구하는 값 표시.
 *
 * ★ 왜
 *   전에는 들어오자마자 '발레코어' 로 자동 검색돼 화면이 숫자로 가득 찼다.
 *   묻지도 않았는데 답이 떠 있으면 그게 진짜 측정값인 줄 안다.
 *   그리고 그 숫자들은 전부 gSeed 로 만든 난수였다.
 *
 * 돌리는 법:  node tests/trend_empty.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';

const read = (rel) => fs.readFileSync(new URL(rel, import.meta.url), 'utf8');
const dispatch = read('../trend/static/js/dispatch.js');
const helpers  = read('../trend/static/js/render_helpers.js');
const live     = read('../trend/static/js/live_data.js');

let pass = 0, fail = 0;
const t = (n, f) => { try { f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; } };

// ── 기본값이 사라졌나 ────────────────────────────────────
t("★ KW 기본 검색어가 비어 있다", () => {
  assert.match(helpers, /export var KW=\{q:'',/);
  assert.doesNotMatch(helpers, /KW=\{q:'발레코어'/);
});

t("★ fsItem 이 발레코어로 안 떨어진다", () => {
  /* 마지막 기댈 곳이 빈 문자열이어야 한다. 무엇을 거치든 이름이 박혀 있으면 안 된다.
     객체 리터럴의 첫 `}`를 함수 끝으로 오인하지 않게 다음 함수 선언 전까지 본다. */
  const start = helpers.indexOf('export function fsItem()');
  const end = helpers.indexOf('export function fsItemFull()', start);
  const body = helpers.slice(start, end);
  assert.match(body, /return\s+''\s*;/, '빈 문자열로 끝나야 한다: ' + body);
  assert.doesNotMatch(body, /return\s+['"]발레코어['"]/, '발레코어 기본값이 박혀 있다: ' + body);
});

t("★ 탭들이 발레코어를 기본값으로 안 쓴다", () => {
  assert.doesNotMatch(dispatch, /KW\.q\|\|'발레코어'/);
});

// ── 빈 화면 ──────────────────────────────────────────────
t("검색 전에는 빈 화면을 그리고 끝낸다", () => {
  assert.match(dispatch, /if \(KW_TABS\.indexOf\(id\) >= 0 && !KW\.q\)/);
  assert.match(dispatch, /if \(SEARCH_TABS\.indexOf\(id\) >= 0 && id !== 'stock' && !fsItem\(\)\)/);
  assert.match(dispatch, /if \(!FS\.stockItem\)/,
    '할인률은 상품 ID가 없을 때 별도의 선택 안내를 보여야 한다');
  // 빈 화면을 그린 뒤 반드시 멈춰야 한다 — 안 그러면 아래 난수 코드가 또 돈다
  const a = dispatch.indexOf('KW_TABS.indexOf');
  const seg = dispatch.slice(a, a + 1200);
  assert.equal((seg.match(/return;/g) || []).length, 2,
    '두 갈래 다 return 해야 한다 — 안 그러면 아래 난수 코드가 이어서 돈다');
});

t("빈 화면이 무엇을 하면 되는지 알려 준다", () => {
  assert.match(helpers, /export function trEmpty/);
  assert.match(dispatch, /검색창에 스타일·소재·아이템·브랜드를 넣어 주세요/);
});

t("빈 화면이 실존 CSS 변수만 쓴다", () => {
  const seg = helpers.slice(helpers.indexOf('export function trEmpty'));
  const vars = [...seg.matchAll(/var\(--([a-z0-9]+)\)/g)].map((m) => m[1]);
  const known = ['line', 'ink', 'coral', 'bg', 'ease', 'mono', 'num', 'logo', 'slot'];
  const bad = vars.filter((v) => !known.includes(v));
  assert.deepEqual(bad, [], `없는 변수: ${bad}`);
});

// ── 난수 제거 ────────────────────────────────────────────
t("★ 온도 탭이 실값을 먼저 본다", () => {
  assert.match(dispatch, /const st=stateOf\(kw\), S=summaryOf\(kw\);/);
  assert.match(dispatch, /const temp=S\?Math\.round\(S\.temp\)/);
});

t("★ 못 구한 값은 지어내지 않고 대시로 둔다", () => {
  assert.match(dispatch, /const nOr=v=>v===null\|\|v===undefined\?'–':v;/);
  assert.match(dispatch, /yoy===null\?'1년치가 모여야 나옵니다'/);
  assert.match(dispatch, /wk===null\?' \(자료 부족\)'/);
});

t("★ 온도가 아직 계산 안 됐으면 화면을 안 채운다", () => {
  assert.match(dispatch, /트렌드 온도가 아직 계산되지 않았습니다/);
});

t("실값일 때 언제 기준인지 밝힌다", () => {
  /* 2026-09-21 — 기준일은 데이터 적재일(dataAsOf)을 먼저 쓴다. 기간은 일/주/월 전환 라벨(data-win-label) */
  assert.match(dispatch, /\(S\.dataAsOf\|\|S\.asOf\)\+' 기준 · <span data-win-label>/);
  assert.match(dispatch, /S\.thin\?' — 자료가 짧아 변화값은 참고만 하세요'/);
});

t("연관어·긍부정도 못 붙으면 사유를 적는다", () => {
  const n = (dispatch.match(/unavailableHTML\(st\.reason/g) || []).length;
  assert.ok(n >= 3, `세 탭 다 있어야 한다 (지금 ${n})`);
});

// ── summaryOf 계산 ───────────────────────────────────────
t("★ summaryOf 는 지표를 새로 만들지 않는다", () => {
  const seg = live.slice(live.indexOf('export function summaryOf'));
  // 온도를 직접 계산하는 흔적이 없어야 한다 (수준*0.6 + 가속*0.4 같은 것)
  assert.doesNotMatch(seg, /0\.6\s*\*|\*\s*0\.4/, '온도를 여기서 계산하면 안 된다');
  assert.match(seg, /temp: need\(num\(last\.temp\)/, '읽기만 해야 한다');
});

t("못 구하는 값은 null 이고 무엇이 없는지 남긴다", () => {
  const seg = live.slice(live.indexOf('export function summaryOf'));
  assert.match(seg, /missing\.push\(name\)/);
  assert.match(seg, /thin: rows\.length < 10/);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
