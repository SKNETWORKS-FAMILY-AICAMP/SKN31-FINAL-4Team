/* 챗바 — 엔터 검색 · 조회 버튼 · 예시 질문 회전 · 조회 중 표시.
 *
 * ★ 왜 생겼나
 *   빈 화면을 넣으면서 `return` 을 kwWire(id) 보다 **앞**에 뒀다.
 *   그래서 검색창은 그려지는데 배선이 안 붙어
 *   엔터도 안 먹고 예시 질문도 안 굴렀다. 눈으로는 멀쩡해 보인다.
 *
 * 돌리는 법:  node tests/search_bar.test.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';

const read = (r) => fs.readFileSync(new URL(r, import.meta.url), 'utf8');
const dispatch = read('../trend/static/js/dispatch.js');
const saved    = read('../trend/static/js/saved_keywords.js');
const css      = read('../trend/static/css/my_feed.css');

let pass = 0, fail = 0;
const t = (n, f) => { try { f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; } };

// ── 배선이 살아 있나 ─────────────────────────────────────
t('★ 검색창 배선이 어떤 분기보다 앞에, 딱 한 번 붙는다', () => {
  // 각 탭 블록 끝에 두면, 값이 없어 중간에 return 할 때 안 붙어서
  // 두 번째 검색이 죽는다. 그래서 trTabsRender 바로 뒤 한 곳에만 둔다.
  const calls = dispatch.match(/kwWire\(/g) || [];
  assert.equal(calls.length, 1, `kwWire 를 ${calls.length}번 부른다 — 한 번이어야 한다`);
  const w = dispatch.indexOf('kwWire(');
  const e = dispatch.indexOf('KW_TABS.indexOf(id) >= 0 && !KW.q');
  assert.ok(w > 0 && w < e, '빈 화면 분기보다 앞이어야 한다');
  assert.match(dispatch, /trTabsRender\(id\);\r?\n[\s\S]{0,600}?kwWire\(id\)/);
});

t('예시 질문 회전이 빈 입력일 때만 돈다', () => {
  assert.match(saved, /if\(i&&!i\.value&&\$\('#trTabs'\)\.classList\.contains\('kwmode'\)\)kwQStep\(\)/);
  // 탭을 새로 그릴 때마다 한 번은 바로 찍고, 타이머는 한 번만 건다.
  assert.match(saved, /if\(!inp\.value\) kwQStep\(\);/);
  assert.match(saved, /if\(!kwQBooked\)\{ kwQBooked=true; setTimeout\(kwQTick,3200\) \}/);
});

t('엔터가 조회로 이어진다', () => {
  assert.match(saved, /else if\(e\.key==='Enter'\)\{ e\.preventDefault\(\);/);
  assert.match(saved, /kwGo\(KW\.sug\[KW\.cur\]\); else kwGo\(\);/);
});

// ── 돋보기 버튼은 없다 — 오른쪽에 사전 버튼이 선다 ─────────
t('★ 검색바 안에 조회 버튼이 없고 사전 버튼이 있다', () => {
  assert.doesNotMatch(dispatch, /id="kwGoBtn"/);
  assert.match(dispatch, /data-dict-open/);
});

// ── 조회 중 표시 ─────────────────────────────────────────
t('★ 조회하는 동안 busy 를 켜고, 실패해도 반드시 끈다', () => {
  const i = saved.indexOf('function kwGo(');
  const seg = saved.slice(i, saved.indexOf('function kwBusy(', i));   /* 함수 끝까지 — 주석이 늘어도 창 밖으로 밀리지 않게 */
  assert.match(seg, /kwBusy\(true\)/);
  assert.match(seg, /\.catch\(\(\)=>\{\}\)\)\)\.then\(\(\)=>\{/, '실패해도 끝나야 한다');
  assert.match(seg, /kwBusy\(false\)/);
});

t('조회 전에 지표를 받아 온다', () => {
  assert.match(saved, /import \{ prime, primeUrl, sentimentUrl \} from '\.\/live_data\.js'/);
  // 사람이 직접 누른 것이므로 캐시를 무시하고 새로 받는다. (1년치 — 전년 대비를 위해 기본 기간)
  assert.match(saved, /prime\(q,undefined,\{force:true\}\)/);
  assert.match(saved, /primeUrl\(assocUrl,\{force:true\}\)/);
  assert.match(saved, /primeUrl\(sentUrl,\{force:true\}\)/);
});

// ── 모션 ─────────────────────────────────────────────────
t('돋보기가 도는 CSS 가 있다', () => {
  assert.match(css, /\.fsBar\.busy \.kwGoIc\{animation:kwSpin/);
  assert.match(css, /@keyframes kwSpin\{to\{transform:rotate\(360deg\)\}\}/);
});

t('★ 너무 빠르게 돌지 않는다 (조급해 보인다)', () => {
  const m = css.match(/animation:kwSpin ([\d.]+)s/);
  assert.ok(m, '회전 속도를 못 찾음');
  assert.ok(parseFloat(m[1]) >= 0.9, `${m[1]}s 는 너무 빠르다`);
});

t('움직임을 줄여 달라는 설정을 존중한다', () => {
  assert.match(css, /@media \(prefers-reduced-motion:reduce\)/);
  const i = css.indexOf('prefers-reduced-motion');
  assert.match(css.slice(i, i + 200), /animation:none/);
});

t('없는 CSS 변수를 쓰지 않는다', () => {
  const seg = css.slice(css.indexOf('.kwGoBtn{'));
  const used = [...seg.matchAll(/var\(--([a-z0-9-]+)\)/g)].map((m) => m[1]);
  const known = ['pink-0','pink-1','pink-2','pink-3','paper','coral','ease','line','ink','bg','num'];
  const bad = [...new Set(used)].filter((v) => !known.includes(v));
  assert.deepEqual(bad, [], `없는 변수: ${bad}`);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
