/* 실제 서버가 뱉은 SSE 바이트를 그대로 재생한다.
   형식을 흉내낸 게 아니라 서버 출력 그 자체다. 잘리는 경계도 실제와 같게 랜덤으로 쪼갠다. */
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const POPUP = fs.readFileSync('popup.html','utf8');
const dom = new JSDOM('<!doctype html><body>'+POPUP+'</body>',
  {url:'http://localhost:5173/', pretendToBeVisual:true});
for (const k of ['location','requestAnimationFrame','cancelAnimationFrame','HTMLElement',
                 'Node','Event','CustomEvent','MouseEvent','getComputedStyle',
                 'TextDecoder','AbortController'])
  { try{ global[k]=dom.window[k]??global[k] }catch(e){} }
global.window = dom.window; global.document = dom.window.document;

let FILE = 'sse/pro_level.sse';
global.fetch = async (url) => {
  const u=String(url);
  if(u.endsWith('/v1/health')) return {ok:true,json:async()=>({ok:true})};
  const buf = fs.readFileSync(FILE);
  /* 네트워크는 이벤트 경계에서 예쁘게 안 끊긴다. 일부러 아무 데서나 자른다. */
  const parts=[]; let i=0;
  while(i<buf.length){ const n=7+Math.floor(Math.random()*40); parts.push(buf.subarray(i,i+n)); i+=n; }
  let k=0;
  return {ok:true, body:{getReader:()=>({read:async()=>k<parts.length?{done:false,value:parts[k++]}:{done:true}})}};
};

const cp = await import('./app/home/static/js/chat_popup.js');
await import('./app/home/static/js/chat.js');
const wait = ms => new Promise(r=>setTimeout(r,ms));
const th = () => document.getElementById('cpThread');
let fail=0; const ok=(c,m)=>{ console.log((c?'  OK  ':'  X!! ')+m); if(!c) fail++; };

console.log('=== 실제 서버 바이트 재생 (경계를 랜덤으로 쪼갬) ===');
for(const [f,label,check] of [
  ['sse/pro_level.sse','PRO 발레코어', t=>{
     ok(!!t.querySelector('.ansCard'),'  카드');
     ok(t.querySelectorAll('.bars .b').length===6,`  플랫폼 막대 6개 (실제 ${t.querySelectorAll('.bars .b').length})`);
     ok(t.querySelector('.say').textContent.includes('86점'),`  온도 86점이 글자로 (실제 "${t.querySelector('.say').textContent.trim()}")`);
     ok(t.querySelectorAll('.act .pill').length===2,'  행동 버튼 2개');
  }],
  ['sse/free_level.sse','FREE 발레코어', t=>{
     ok(!t.querySelector('.bars'),'  막대 없음');
     ok(!!t.querySelector('.kwReq .ask'),'  업셀');
  }],
  ['sse/refusal.sse','사전 밖', t=>{
     ok(!!t.querySelector('.kwReq .near button'),'  후보 칩');
     ok(!!t.querySelector('[data-lexreq]'),'  등록 요청 버튼');
  }],
]){
  FILE=f; cp.cpNewConvo(); cp.openChatWith('질문');
  await wait(2600);
  console.log(' ·', label);
  check(th());
}
console.log(fail? `\n실패 ${fail}건` : '\n전부 통과 — 서버 출력 그대로 그려진다');
process.exit(fail?1:0);
