/* 사전에 없는 말을 쳤을 때 뜨는 '사전 등재 요청' 버튼을 실제로 눌러 본다.
   등재되면 TERM_ADDED 알림이 가는 자리다 (backend/apps/api/notification_views.py).

   ★ 이 화면은 검색바를 다시 그린다(trRender → fsBuild). 그래서 알림 패널 테스트
     (notify_ui.test.mjs)와 달리 여기서는 로딩 화면을 건너뛰지 않는다 —
     jumpBtn 을 누르면 검색바가 한 번 묶인 뒤 trRender 가 마크업을 갈아 끼워
     입력 이벤트가 끊긴다. 파일을 나눈 이유다. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost:5173/' });
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent','Event'])
  globalThis[key] = key === 'window' ? dom.window : dom.window[key];
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame = fn => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = id => clearTimeout(id);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.location = dom.window.location;
globalThis.history = dom.window.history;
globalThis.localStorage = dom.window.localStorage;
globalThis.innerWidth = 1440; globalThis.innerHeight = 900;
globalThis.matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
globalThis.scrollTo = () => {};
globalThis.IntersectionObserver = class{ observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class{ observe(){} unobserve(){} disconnect(){} };

const asked = [];
const reply = payload => ({ ok:true, status:200, text:async () => JSON.stringify(payload),
  json:async () => payload });
let termReply = { already:false, created:true, id:3, term:'블로코어', status:'PENDING' };

globalThis.fetch = async (url, opts = {}) => {
  const u = String(url), method = (opts.method || 'GET').toUpperCase();
  asked.push({ url:u, method, body:opts.body });
  if(u.includes('/api/auth/me'))
    return reply({ status:'ok', data:{ authenticated:false, csrf_token:'csrf', user:null } });
  if(u.includes('/api/auth/term-request')) return reply({ status:'ok', data:termReply });
  if(u.includes('/api/dictionary')) return reply({ status:'ok', data:[] });
  return reply({ status:'empty', reason:'테스트 데이터 없음', data:null });
};

await import(`${root}/main.js`);
const S = await import(`${root}/style/static/js/search.js`);
const D = await import(`${root}/trend/static/js/dispatch.js`);
const profile = await import(`${root}/account/static/js/profile.js`);

D.trRender('life');       /* 리세일은 표준상품 검색, 사전 등재 요청은 사전 검색 탭에서 확인 */
S.fsBuild();

function type(word){
  const inp = document.getElementById('fsInput');
  inp.value = word;
  inp.dispatchEvent(new dom.window.Event('input', { bubbles:true }));
  return document.querySelector('#fsSug [data-term-req]');
}

/* ① 사전에 없는 말이면 요청 버튼이 뜬다 */
const btn = type('블로코어');
assert.ok(btn, '사전에 없는 말이면 등재 요청 버튼이 뜬다');
assert.equal(btn.dataset.termReq, '블로코어');
assert.ok(btn.textContent.includes('사전 등재 요청'));

/* ② 로그인하지 않았으면 로그인 화면으로 보낸다 — 조용히 실패하지 않는다 */
profile.AUTH.in = false;
btn.dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 40));
assert.equal(asked.some(a => a.url.includes('/api/auth/term-request')), false,
  '로그인 전에는 요청을 보내지 않는다');
assert.equal(document.body.dataset.view, 'login', '로그인 화면으로 보낸다');

/* ③ 로그인 상태에서 누르면 서버로 간다 */
profile.AUTH.in = true;
const btn2 = type('블로코어');
btn2.dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 60));
const call = asked.find(a => a.url.includes('/api/auth/term-request'));
assert.ok(call, '등재 요청을 서버에 보낸다');
assert.equal(call.method, 'POST');
assert.equal(JSON.parse(call.body).term, '블로코어');
assert.ok(btn2.textContent.includes('요청했어요'), '누른 결과를 화면에 말한다');
assert.equal(btn2.disabled, true, '같은 요청을 두 번 보내지 않는다');

/* ④ 이미 사전에 있는 말이면 그 사실을 그대로 말한다 */
termReply = { already:true, canonical_name:'블록코어', term_type:'STYLE' };
const btn3 = type('블로코어2');
assert.ok(btn3, '요청 버튼이 뜬다');
btn3.dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 60));
assert.ok(btn3.textContent.includes('이미 사전에 있어요'), btn3.textContent);
assert.ok(btn3.textContent.includes('블록코어'));

console.log('✅ 사전 등재 요청 버튼이 실제로 서버로 이어집니다.');
process.exit(0);
