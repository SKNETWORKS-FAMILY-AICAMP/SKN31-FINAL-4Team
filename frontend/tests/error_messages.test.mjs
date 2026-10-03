/* 실패를 뭉뚱그리지 않는지 — 네 가지를 각각 다르게 말해야 한다.
 *
 * ★ 왜
 *   예전엔 무엇이 잘못됐든 "지표 서버에 닿지 못했습니다" 한 마디였다.
 *   그런데 고치는 방법이 전부 다르다:
 *     서버가 안 떴다   → Django 서버 up
 *     주소가 없다(404) → vite 재시작 / BACKEND_API_URL 확인
 *     서버가 터졌다    → 백엔드 로그
 *     HTML 이 왔다     → 프록시가 엉뚱한 데로 보냈다
 *   같은 말을 하면 사람이 뭘 해야 할지 모른 채 헤맨다.
 *
 * 돌리는 법:  node tests/error_messages.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom'; import fs from 'node:fs';
const F=new URL('..', import.meta.url).href.replace(/\/$/,'');
const dom=new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'),{url:'http://localhost:5173/'});
for(const k of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent'])
  globalThis[k]=k==='window'?dom.window:dom.window[k];
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame=f=>setTimeout(f,0); globalThis.cancelAnimationFrame=h=>clearTimeout(h);
globalThis.addEventListener=dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener=dom.window.removeEventListener.bind(dom.window);
globalThis.location=dom.window.location; globalThis.localStorage=dom.window.localStorage;
globalThis.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}}); globalThis.scrollTo=()=>{};
globalThis.IntersectionObserver=class{observe(){}unobserve(){}disconnect(){}};
globalThis.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};

let plan='down';
globalThis.fetch=async()=>{
  if(plan==='down')  throw new Error('ECONNREFUSED');
  if(plan==='404')   return {ok:false,status:404,text:async()=>'<!doctype html>Not Found'};
  if(plan==='500')   return {ok:false,status:500,text:async()=>'server error'};
  if(plan==='html')  return {ok:true,status:200,text:async()=>'<!doctype html><html>vite index</html>'};
  return {ok:true,status:200,text:async()=>JSON.stringify({status:'empty',reason:'적재 전입니다.'})};
};
await import(`${F}/main.js`);
const live=await import(`${F}/trend/static/js/live_data.js`);

let pass=0,fail=0;
const t=async(n,f)=>{try{await f();console.log('✅',n);pass++}catch(e){console.log('❌',n,'\n   ',e.message);fail++}};
const ask=async(kw)=>{ const r=await live.prime(kw,120,{force:true}); return r; };

await t('★ 서버가 안 떠 있으면 — 켜라고 말한다', async () => {
  plan='down'; const r=await ask('발레코어');
  assert.equal(r.status,'error');
  assert.match(r.reason,/연결하지 못했습니다/);
  assert.match(r.detail,/Django 서버/);
});

await t('★ 주소가 없으면(404) — 프록시/주소를 짚는다', async () => {
  plan='404'; const r=await ask('새틴');
  assert.match(r.reason,/404/);
  assert.match(r.detail,/vite 를 다시 켜|BACKEND_API_URL/);
});

await t('★ 서버가 터지면(500) — 로그를 보라고 한다', async () => {
  plan='500'; const r=await ask('나일론');
  assert.match(r.reason,/500/);
  assert.match(r.detail,/로그/);
});

await t('★ HTML 이 오면 — 엉뚱한 데로 갔다고 말한다', async () => {
  plan='html'; const r=await ask('데님');
  assert.match(r.reason,/JSON 이 아닌/);
  assert.match(r.detail,/앞 40자/);
});

await t('정상이면 그대로 통과', async () => {
  plan='ok'; const r=await ask('고프코어');
  assert.equal(r.status,'empty');
  assert.match(r.reason,/적재 전입니다/);
});

await t('★ 네 가지가 서로 다른 말이다', async () => {
  const msgs=[];
  for (const p of ['down','404','500','html']) { plan=p; msgs.push((await ask('발레코어')).reason); }
  assert.equal(new Set(msgs).size, 4, `겹치는 문구가 있다: ${msgs}`);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail?1:0);
