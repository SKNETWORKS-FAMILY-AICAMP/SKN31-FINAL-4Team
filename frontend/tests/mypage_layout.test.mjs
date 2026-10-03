/* 마이페이지 배치 — 세 칸(프로필·오늘의 추천·살!말? 피드백)과
   '오늘의 추천' 칸마다 6개(한 줄 3개)까지만 나오는지 실제로 그려 본다. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost:5173/' });
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent','Event'])
  globalThis[key] = key === 'window' ? dom.window : dom.window[key];
/* notify.js 가 본문을 기다릴 때 쓴다 — jsdom 전역에 없어서 이 시험들이 통째로 죽어 있었다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame = fn => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = id => clearTimeout(id);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.location = dom.window.location;
globalThis.history = dom.window.history;
globalThis.localStorage = dom.window.localStorage;
globalThis.innerWidth = 1680; globalThis.innerHeight = 900;
globalThis.matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
globalThis.scrollTo = () => {};
globalThis.IntersectionObserver = class{ observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class{ observe(){} unobserve(){} disconnect(){} };

const reply = payload => ({ ok:true, status:200, text:async () => JSON.stringify(payload),
  json:async () => payload });

/* 상품은 넉넉히 준다 — 화면이 6개에서 끊는지 보는 게 목적이다 */
const products = Array.from({ length: 16 }, (_, i) => ({
  product_source_id: 100 + i, name:`상품 ${i}`, brand:'브랜드', image:'',
  price:{ list:39000, sale:29000 },
}));
const user = { id:7, username:'feedit01', email:'feedit01', nickname:'전서연', initial:'전',
  birth_date:'2000-01-02', height:170, weight:60, avatar:0, role:'user', job:'', major:'',
  bio:'', styles:['고프코어','애슬레저','아메카지'], saved_count:17, vote_count:0, badges:{} };

globalThis.fetch = async (url) => {
  const u = String(url);
  if(u.includes('/api/auth/me'))
    return reply({ status:'ok', data:{ authenticated:true, csrf_token:'csrf', user } });
  if(u.includes('/api/products')) return reply({ status:'ok', data:{ items:products } });
  if(u.includes('/api/auth/notifications'))
    return reply({ status:'ok', data:{ items:[], unread:0 } });
  if(u.includes('/api/salmal/feedback'))
    return reply({ status:'ok', data:{ pending:[], done:[], counts:{ pending:0, done:0 } } });
  if(u.includes('/api/auth/saved')) return reply({ status:'ok', data:{ items:[], count:0 } });
  return reply({ status:'empty', reason:'테스트 데이터 없음', data:null });
};

await import(`${root}/main.js`);
const router = await import(`${root}/app_shell/static/js/router.js`);
document.getElementById('jumpBtn').click();
await new Promise(r => setTimeout(r, 150));
router.goView('mypage');
await new Promise(r => setTimeout(r, 300));

/* ① 칸이 셋이고, 순서가 프로필 → 오늘의 추천 → 피드백이다 */
const cols = document.querySelectorAll('#v-mypage .myGrid > .myCol');
assert.equal(cols.length, 3, '마이페이지는 세 칸이다');
assert.ok(cols[0].querySelector('.profilePanel'), '왼쪽 칸에 프로필');
assert.ok(cols[0].querySelector('#styleWrap'), '왼쪽 칸에 즐겨입는 스타일');
assert.ok(cols[1].querySelector('#todayRecPanel'), '가운데 칸에 오늘의 추천');
assert.equal(cols[2].id, 'myColFb', '오른쪽 칸은 살!말? 피드백 자리');

/* ② 살!말? 피드백 패널이 그 오른쪽 칸 안에 들어간다 */
const fb = document.getElementById('fbPanel');
assert.ok(fb, '피드백 패널이 그려진다');
assert.equal(fb.parentElement.id, 'myColFb', '피드백은 오른쪽 칸 안에 있다');
assert.equal(fb.style.marginTop, '', '칸의 첫 패널이라 위쪽 여백을 따로 주지 않는다');

/* ③ 칸마다 6개까지 */
const mine = document.querySelectorAll('#recMine .itemCard');
const hot = document.querySelectorAll('#recHot .itemCard');
assert.equal(mine.length, 6, `내 취향은 6개 (지금 ${mine.length}개)`);
assert.equal(hot.length, 6, `지금 뜨는 코어도 6개 (지금 ${hot.length}개)`);

/* ④ 스크롤은 패널이 아니라 안쪽 칸이 한다 — 막대가 패널의 둥근 모서리에 얹히면
      오른쪽 모서리가 각져 보인다 */
const panel = document.getElementById('todayRecPanel');
const scroll = document.getElementById('recScroll');
assert.ok(scroll, '패널 안에 스크롤 칸이 있다');
assert.equal(scroll.parentElement, panel, '스크롤 칸은 패널 바로 안이다');
assert.equal(scroll.querySelectorAll('.recBlock').length, 2,
  '두 칸(내 취향 · 지금 뜨는 코어)이 그 안에서 같이 스크롤한다');

const css = fs.readFileSync(new URL('../account/static/css/profile.css', import.meta.url), 'utf8');
assert.equal(/#todayRecPanel\{overflow-y:auto\}/.test(css), false,
  '패널 자신은 스크롤하지 않는다');
assert.match(css, /#todayRecPanel \.recScroll\{[^}]*overflow-y:auto/,
  '스크롤은 안쪽 칸이 한다');
assert.match(css, /\.acct \.recGrid\{display:grid;grid-template-columns:repeat\(3,var\(--recCardW\)\)/,
  '한 줄에 3개 · 카드 폭은 고정(늘려서 채우지 않는다)');
assert.match(css, /--recCardW:188px/, '카드 폭은 예전 4열 화면과 같은 188px 다');

/* ⑤ 피드백 패널도 같은 높이로 서고, 길어지면 안쪽에서 스크롤한다 */
assert.match(css, /\.fbPanel #fbPanelBody\{[^}]*overflow-y:auto/,
  '피드백도 패널이 아니라 안쪽 칸이 스크롤한다');
const js = fs.readFileSync(new URL('../account/static/js/profile.js', import.meta.url), 'utf8');
assert.match(js, /const fb = \$\('#fbPanel'\);[\s\S]{0,120}fb\.style\.height/,
  '피드백 패널 높이도 왼쪽 칸에 맞춘다');
assert.match(js, /innerWidth >= MY_THREE_COL/,
  '세 칸이 아닐 때는 높이를 박지 않는다');

console.log('✅ 마이페이지 세 칸 배치 · 칸마다 6개 · 안쪽 칸 스크롤을 확인했습니다.');
process.exit(0);
