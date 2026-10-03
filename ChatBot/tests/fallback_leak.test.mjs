/* 목업 누출 회귀 시험.
   증상 — 사전 밖 질문에 서버가 거절을 보냈는데,
          목업 문장("…1,284명 중 73%가 산다에 투표…")이 그 위에 그대로 남았다.
   원인 — `if(head) aiMsg.html=head` 라서 head 가 빈 거절 응답에서는 목업이 안 지워졌다. */
import { JSDOM } from 'jsdom';
import { browserEnv } from './browser_env.mjs';
import fs from 'node:fs';

const POPUP = fs.readFileSync('popup.html','utf8');
/* ★ 2026-09-27 — 팝업 모듈이 앱 셸(라우터 · 인트로 · 연관어 팝오버)까지 끌고 들어와
   불러오는 순간 그 칸들을 찾는다. 조각 마크업 대신 실제 index.html 을 세운다(run.sh 가 app_index.html 로 복사). */
const dom = new JSDOM(fs.existsSync('app_index.html') ? fs.readFileSync('app_index.html','utf8')
                                                    : '<!doctype html><body>'+POPUP+'</body>',
  {url:'http://localhost:5173/', pretendToBeVisual:true});
for (const k of ['location','requestAnimationFrame','cancelAnimationFrame','HTMLElement',
                 'Node','Event','CustomEvent','MouseEvent','getComputedStyle',
                 'TextDecoder','AbortController'])
  { try{ global[k]=dom.window[k]??global[k] }catch(e){} }
global.window = dom.window; global.document = dom.window.document;
browserEnv(dom);   /* 앱 셸이 따라 들어오며 찾는 나머지 창 전역 */

const FX = JSON.parse(fs.readFileSync('_chat_fixtures.json','utf8'));
let SERVE = FX.refusal;
global.fetch = async (url) => {
  const u=String(url);
  if(u.endsWith('/v1/health')) return {ok:true,json:async()=>({ok:true})};
  const enc=new TextEncoder(); const parts=[];
  const push=(ev,d)=>parts.push(enc.encode(`event: ${ev}\ndata: ${JSON.stringify(d)}\n\n`));
  push('status',{stage:'lexicon'});
  if(SERVE.ok===false){ push('error',SERVE); push('done',{ok:false}); }
  else { for(const seg of (SERVE.headline||'').match(/(<[^>]+>|.{1,3})/g)||[]) push('text',{delta:seg});
         push('report',SERVE); push('done',{ok:true}); }
  let i=0;
  return {ok:true, body:{getReader:()=>({read:async()=>i<parts.length?{done:false,value:parts[i++]}:{done:true}})}};
};

/* 앱과 같은 순서로 불러온다 — chat_popup.js 를 먼저 부르면 모듈 순환에서 ME 가 아직 없다 */
if (fs.existsSync('app/main.js')) await import('./app/main.js');
/* 2026-09 부터 챗봇은 로그인 관문을 지나야 질문을 보낸다 — 지난 상태로 둔다 (frontend/tests/chat_popup_ui 와 같다) */
if (fs.existsSync('app/account/static/js/profile.js'))
  (await import('./app/account/static/js/profile.js')).AUTH.in = true;
const cp = await import('./app/home/static/js/chat_popup.js');
const chat = await import('./app/home/static/js/chat.js');
const wait = ms => new Promise(r=>setTimeout(r,ms));
const th = () => document.getElementById('cpThread');
let fail=0; const ok=(c,m)=>{ console.log((c?'  OK  ':'  X!! ')+m); if(!c) fail++; };

console.log('=== 살말 모드 + 사전 밖 — 목업이 새어 나오나 ===');
chat.smSwitch(true);            /* 살!말? 모드로 */
await wait(50);
cp.cpNewConvo(); cp.openChatWith('그러면 사랑은어때?');
await wait(2400);
const t = th();
const say = (t.querySelector('.say')||{textContent:''}).textContent;
console.log('     .say =', JSON.stringify(say.trim()));
ok(!say.includes('1,284'),  '목업 숫자 "1,284명" 이 없다');
ok(!say.includes('73%'),    '목업 숫자 "73%" 가 없다');
ok(!say.includes('사도 됩니다'), '목업 판정 문구가 없다');
ok(!!t.querySelector('.kwReq'), '거절 카드는 그대로 뜬다');
ok(!t.querySelector('.ansCard'), '지표 카드는 안 뜬다');

console.log('\n=== 살말 모드 + 정상 — 판정 못 한다고 먼저 말하나 ===');
SERVE = FX.salmal;      /* 서버가 실제로 만든 살말 응답 그대로 */
cp.cpNewConvo(); cp.openChatWith('발레코어 지금 살만 해?');
/* 한 줄 결론이 길어져 타이핑이 오래 걸린다. 넉넉히 기다린다. */
await wait(6000);
const t2=th(); const say2=(t2.querySelector('.say')||{textContent:''}).textContent;
ok(say2.includes('판단하지 못합니다'), `못 한다고 먼저 말한다`);
ok(t2.textContent.includes('살!말?지수는 아직'), '카드 각주에도 남는다');
ok(!!t2.querySelector('.skillReport, .ansCard'), '아는 것은 그대로 보여준다');   /* 2026-09 부터 .skillReport */

console.log(fail? `\n실패 ${fail}건` : '\n전부 통과');
process.exit(fail?1:0);
