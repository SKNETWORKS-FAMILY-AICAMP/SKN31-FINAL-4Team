/* 새로고침할 때 헤더가 잠깐 [로그인] 으로 보이던 깜빡임 (2026-10-02).
 *   돌리는 법:  node tests/auth_header_pending.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'), {url:'http://localhost:5173/'});
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement',
                 'KeyboardEvent','MouseEvent','CustomEvent','Event','MutationObserver','history'])
  globalThis[k] = k==='window'?dom.window:dom.window[k];
globalThis.requestAnimationFrame=(f)=>setTimeout(f,0);
globalThis.cancelAnimationFrame=(h)=>clearTimeout(h);
globalThis.addEventListener=dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener=dom.window.removeEventListener.bind(dom.window);
globalThis.location=dom.window.location;
globalThis.localStorage=dom.window.localStorage;
globalThis.sessionStorage=dom.window.sessionStorage;
globalThis.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
globalThis.scrollTo=()=>{};
globalThis.innerWidth=1280; globalThis.innerHeight=800;
globalThis.IntersectionObserver=class{observe(){}unobserve(){}disconnect(){}};
globalThis.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};

/* 로그아웃 상태에서 새로고침 — 남아 있던 이름 기억(지난번 로그인)은 복구 답을 받고 지운다 */
localStorage.setItem('feedit.introSeen.v1','1');
localStorage.setItem('feedit:auth-hint','진');
let answerMe;
const meHeld=new Promise(r=>{ answerMe=r });
globalThis.fetch = async (u) => {
  const url=decodeURIComponent(String(u));
  const ok=(body)=>({ok:true,status:200,text:async()=>JSON.stringify(body),json:async()=>body});
  if(/\/api\/auth\/me$/.test(url)){ await meHeld; return ok({status:'ok',data:{authenticated:false}}); }
  await new Promise(r=>setTimeout(r,10));
  throw new Error('ECONNREFUSED');
};
await import(`${F}/main.js`);
const wait=(ms)=>new Promise(r=>setTimeout(r,ms));
const btn=()=>document.getElementById('mAuthBtn');

await wait(40);
assert.ok(!btn().textContent.includes('로그인'),'복구 전에 [로그인] 이 보인다');
answerMe(); await wait(80);
assert.equal(btn().textContent,'로그인','복구 결과 로그아웃이면 [로그인] 이어야 한다');
assert.equal(btn().dataset.v,'login');
assert.equal(localStorage.getItem('feedit:auth-hint'),null,'로그아웃인데 이름 기억이 남았다');





console.log('✅ 새로고침 중 헤더는 [로그인] 을 먼저 그리지 않고, 로그아웃이 확인되면 그때 그린다');
process.exit(0);
