import { JSDOM } from 'jsdom';
import { browserEnv } from './browser_env.mjs';
import fs from 'node:fs';

/* 팝업 마크업을 index.html 에서 쓰는 그대로 세운다 */
const POPUP = `
<div class="modalOverlay cpOverlay" id="cpOverlay"><div class="modalShell cpShell">
 <div class="cpBox" id="cpBox">
  <aside class="cpSide">
   <div class="cpProfile"><div class="cpAv" id="cpAv"></div>
    <div class="cpProfileText"><b id="cpName"></b><p id="cpDesc"></p></div></div>
   <button type="button" class="cpNewBtn" id="cpNewBtn"><i>+</i>새로운 대화</button>
   <div class="cpListLabel">대화 목록</div><div class="cpList" id="cpList"></div>
  </aside>
  <div class="cpMain">
   <div class="cpThreadWrap" id="cpThreadWrap">
    <div class="cpEmpty"><p id="cpEmptyText"></p></div>
    <div class="thread cpThread" id="cpThread"></div></div>
   <div class="cpInputRow"><textarea id="cpInput" rows="1"></textarea>
    <button class="cpSend" id="cpSend">→</button></div>
  </div></div>
 <button class="modalClose" id="cpClose">×</button></div></div>
<section class="view on" id="v-home"><div id="hotList"></div><div id="mChips"></div>
 <h1 id="mState"><span class="ln">a</span></h1><div class="heroL"><p>x</p></div>
 <div class="heroR"></div><div class="chatbar"><button id="smToggle"><span class="lbl">
 <i class="ic">◑</i><span class="tx">살!말?</span></span></button>
 <div class="ghostQ" id="ghostQ"><span class="spark">✧</span><span class="qline" id="qline"></span></div>
 <input id="mInput"></div><div class="thread" id="thread"></div></section>`;

/* ★ 2026-09-27 — 팝업 모듈이 앱 셸(라우터 · 인트로 · 연관어 팝오버)까지 끌고 들어와
   불러오는 순간 그 칸들을 찾는다. 조각 마크업 대신 실제 index.html 을 세운다(run.sh 가 app_index.html 로 복사). */
const dom = new JSDOM(fs.existsSync('app_index.html') ? fs.readFileSync('app_index.html','utf8')
                                                    : '<!doctype html><body>'+POPUP+'</body>',
  {url:'http://localhost:5173/', pretendToBeVisual:true});
for (const k of ['location','requestAnimationFrame','cancelAnimationFrame','HTMLElement',
                 'Node','Event','CustomEvent','MouseEvent','getComputedStyle',
                 'TextDecoder','AbortController']) {
  try { global[k] = dom.window[k] ?? global[k]; } catch(e) { /* getter-only 는 건너뛴다 */ }
}
global.window = dom.window; global.document = dom.window.document;
browserEnv(dom);   /* 앱 셸이 따라 들어오며 찾는 나머지 창 전역 */
/* setTimeout 은 노드 것을 그대로 쓴다 — jsdom 것으로 덮으면 재귀에 빠진다 */

const FX = JSON.parse(fs.readFileSync('_chat_fixtures.json','utf8'));

/* 서버 흉내 — 진짜 SSE 바이트를 흘린다 */
function sseBody(rep){
  const enc = new TextEncoder();
  const parts = [];
  const push=(ev,d)=>parts.push(enc.encode(`event: ${ev}\ndata: ${JSON.stringify(d)}\n\n`));
  push('status',{stage:'lexicon'});
  if(rep.ok===false){ push('error',rep); push('done',{ok:false}); }
  else{
    for(const seg of (rep.headline||'').match(/(<[^>]+>|.{1,3})/g)||[]) push('text',{delta:seg});
    push('report',rep);
    push('actions',[{label:'Style 탭에서 자세히',type:'view',view:'style',style:(rep.terms[0]||{}).canonical},
                    {label:'지표로 보기',type:'view',view:'trend'}]);
    push('done',{ok:true});
  }
  let i=0;
  return {getReader:()=>({read:async()=>i<parts.length?{done:false,value:parts[i++]}:{done:true}})};
}
let SERVE = FX.level, HEALTH = true, LEXREQ = null, FAILURE = null, LAST_CHAT = null;
global.fetch = async (url, opt) => {
  const u = String(url);
  if(!HEALTH) throw new Error('서버 없음');   /* 죽으면 전부 실패한다 */
  if(u.endsWith('/v1/health'))
    return HEALTH ? {ok:true, json:async()=>({ok:true})} : Promise.reject(new Error('down'));
  if(u.endsWith('/v1/lexicon/requests')){
    LEXREQ = JSON.parse(opt.body);
    return {ok:true, json:async()=>({ok:true, surface:LEXREQ.surface, count:1})};
  }
  if(u.endsWith('/v1/chat')) {
    try { LAST_CHAT = JSON.parse(opt.body); } catch(e) { LAST_CHAT = null; }
    if(FAILURE==='http') return {ok:false,status:503};
    if(FAILURE==='stream' || FAILURE==='eof') {
      let sent=false;
      return {ok:true,body:{getReader:()=>({read:async()=>{
        if(!sent){ sent=true; return {done:false,value:new TextEncoder().encode('event: text\ndata: {"delta":"중간 응답"}\n\n')}; }
        if(FAILURE==='stream') throw new Error('connection lost');
        return {done:true};
      }})}};
    }
    return {ok:true, body:sseBody(SERVE)};
  }
  throw new Error('unexpected '+u);
};

/* 앱과 같은 순서로 불러온다 — chat_popup.js 를 먼저 부르면 모듈 순환에서 ME 가 아직 없다 */
if (fs.existsSync('app/main.js')) await import('./app/main.js');
/* 2026-09 부터 챗봇은 로그인 관문을 지나야 질문을 보낸다 — 지난 상태로 둔다 (frontend/tests/chat_popup_ui 와 같다) */
if (fs.existsSync('app/account/static/js/profile.js'))
  (await import('./app/account/static/js/profile.js')).AUTH.in = true;
const cp = await import('./app/home/static/js/chat_popup.js');
const chat = await import('./app/home/static/js/chat.js');
const wait = ms => new Promise(r=>setTimeout(r,ms));

let fail=0;
const ok=(c,m)=>{ console.log((c?'  OK  ':'  X!! ')+m); if(!c) fail++; };
const thread = () => document.getElementById('cpThread');

console.log('=== 0. 피드백은 간헐적으로만 묻나 ===');
const feedbackTurns=Array.from({length:13},(_,i)=>i+1).filter(cp.cpFeedbackSample);
ok(JSON.stringify(feedbackTurns)===JSON.stringify([3,8,13]),
   `3·8·13번째 답만 묻는다 (${feedbackTurns.join(',')})`);

console.log('=== 1. 서버가 살아 있을 때 — 실데이터 리포트가 뜨나 ===');
cp.openChatWith('발레코어 어때?');
await wait(2600);
let th = thread();
ok(th.querySelectorAll('.msg.me').length===1, '내 말풍선 1개');
ok(th.querySelectorAll('.msg.ai').length===1, 'AI 말풍선 1개');
/* 2026-09 부터 리포트는 .skillReport 안에 그린다(예전 .ansCard) */
ok(!!th.querySelector('.skillReport, .ansCard'), '리포트 카드 렌더');
ok(th.querySelector('.say').textContent.includes('발레코어'), '한 줄 결론에 키워드');
ok(th.querySelectorAll('.rank .row').length>=2, `.rank 행 ${th.querySelectorAll('.rank .row').length}개`);
ok(th.querySelectorAll('.bars .b').length>0, `.bars 막대 ${th.querySelectorAll('.bars .b').length}개 (PRO)`);
/* 발레코어는 스타일 탭 10종 밖이라 'Style 탭에서 자세히' 는 지워지고 '지표로 보기' 만 남는다 */
ok(th.querySelectorAll('.act .pill').length===1, `행동 버튼 ${th.querySelectorAll('.act .pill').length}개 (10종 밖 스타일 버튼은 지운다)`);
ok(!th.querySelector('[data-style]'), '10종 밖 스타일은 첫 번째 스타일로 떨어지지 않는다');
ok(!th.querySelector('[data-style-name]:not([data-style])'), '해석 못 한 스타일 버튼은 남지 않는다');

/* 10종 안의 스타일이면 이름 → id 로 바꿔 단다 */
SERVE = {...FX.level, terms:[{...FX.level.terms[0], canonical:'고프코어'}, ...FX.level.terms.slice(1)]};
cp.cpNewConvo(); cp.openChatWith('고프코어 어때?');
await wait(2600);
th = thread();
const sBtn = th.querySelector('[data-style]');
ok(th.querySelectorAll('.act .pill').length===2, `행동 버튼 ${th.querySelectorAll('.act .pill').length}개`);
ok(sBtn && sBtn.dataset.style==='gorp',
   `스타일 버튼이 id 로 바뀜 (data-style="${sBtn&&sBtn.dataset.style}") — 이름 그대로면 라우터가 엉뚱한 데로 간다`);
SERVE = FX.level;

console.log('\n=== 2. 사전에 없는 말 ===');
SERVE = FX.refusal;
cp.cpNewConvo(); cp.openChatWith('우리 랩실에서 회의했어요');
await wait(2200);
th = thread();
ok(!!th.querySelector('.kwReq'), '.kwReq 렌더');
ok(th.querySelectorAll('.kwReq .near button').length>0, `후보 ${th.querySelectorAll('.kwReq .near button').length}개`);
const rq = th.querySelector('[data-lexreq]');
ok(!!rq, '등록 요청 버튼');
rq.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true}));
await wait(120);
ok(rq.disabled===true, '누른 즉시 잠긴다');
await wait(400);
ok(LEXREQ && LEXREQ.surface==='회의했어요',
   `서버로 실제 전송됨 surface="${LEXREQ&&LEXREQ.surface}"`);
ok(rq.textContent.includes('완료'), `끝나면 결과를 말한다 ("${rq.textContent}")`);

console.log('\n=== 3. 후보 칩을 누르면 그 말로 다시 묻는다 ===');
SERVE = FX.direction;
const before = thread().querySelectorAll('.msg.me').length;
thread().querySelector('.kwReq .near button').dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true}));
await wait(2200);
ok(thread().querySelectorAll('.msg.me').length===before+1, '질문이 하나 더 쌓임');

console.log('\n=== 4. 서버 장애 — 예시 수치 없이 오류와 재전송 ===');
const api = await import('./chat_api.js');
function checkUnavailable(label){
  const host=thread();
  ok(host.textContent.includes('답변을 받지 못했습니다'), label+' 오류 안내');
  ok(!host.querySelector('.skillReport,.ansCard,.bars'), label+' 예시/부분 리포트 없음');
  ok(!host.textContent.includes('LIVE REPORT'), label+' 실데이터 머리표 없음');
  ok(!!host.querySelector('[data-resend]'), label+' 재전송 유지');
  ok(host.querySelector('.msg.me').textContent.includes('고프코어'), label+' 질문 보존');
  ok(!host.querySelector('.thinking'), label+' 진행 상태 종료');
}
HEALTH=false;
cp.cpNewConvo(); cp.openChatWith('고프코어 꺾였어?','gorp');
await wait(100);
checkUnavailable('전송 실패');
await api.isUp({force:true});
cp.cpNewConvo(); cp.openChatWith('고프코어 꺾였어?','gorp');
await wait(100);
checkUnavailable('health 실패');
HEALTH=true;
for(const mode of ['http','stream','eof']){
  FAILURE=mode;
  cp.cpNewConvo(); cp.openChatWith('고프코어 꺾였어?','gorp');
  await wait(100);
  checkUnavailable(mode);
}
FAILURE=null; SERVE=FX.level;
thread().querySelector('[data-resend]').dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true}));
await wait(200);
ok(thread().querySelectorAll('.msg.me').length===2,'복구 후 같은 질문 재전송');
ok(!!thread().querySelector('.skillReport'),'복구 후 서버 리포트 표시');

console.log('\n=== 5. FREE 플랜 — 서버가 자른 대로 그린다 ===');
HEALTH = true; SERVE = FX.level_free;
cp.cpNewConvo(); cp.openChatWith('발레코어 어때?');
await wait(2600);
th = thread();
ok(!th.querySelector('.bars'), '플랫폼 막대 없음');
ok(!!th.querySelector('.kwReq .ask button[data-v="price"]'), '업셀 버튼이 요금제로 간다');

console.log('\n=== 6. 챗봇이 되물은 것이 다음 턴의 맥락으로 넘어가나 (2026-10-01) ===');
/* "더비슈즈의 출처별 반응이나 … 볼까요?" → "응 두개 다" 가 무엇에 대한 대답인지
   서버가 알아야 한다. 예전엔 history 에 사용자 질문만 실렸다. */
HEALTH = true;
SERVE = {...FX.level, followup:'<p>더비슈즈의 출처별 반응이나, 실제 언급 근거를 더 볼까요?</p>'};
cp.cpNewConvo(); cp.openChatWith('더비슈즈는 왜 93점이야?');
await wait(2600);
SERVE = FX.level;
const input = document.getElementById('cpInput');
input.value = '응 두개 다 알려줘';
cp.cpSend();
await wait(2600);
const sent = (LAST_CHAT && (LAST_CHAT.history || (LAST_CHAT.context||{}).history)) || [];
const lastTurn = sent[sent.length-1] || {};
ok(lastTurn.q === '더비슈즈는 왜 93점이야?', `직전 턴이 실렸다 (${lastTurn.q})`);
ok(lastTurn.next === '더비슈즈의 출처별 반응이나, 실제 언급 근거를 더 볼까요?',
   `되물은 질문이 글자로 실렸다 (${lastTurn.next})`);

console.log(fail? `\n실패 ${fail}건` : '\n전부 통과');
process.exit(fail?1:0);
