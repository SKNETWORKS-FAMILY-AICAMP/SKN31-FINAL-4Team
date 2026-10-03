/* 팝업의 새 조작 세 가지 — 제목 수정 · 새 세션 · 모드 뒤집기.
 * jsdom 으로 진짜 실행한다. node --check 는 정의되지 않은 이름을 통과시킨다 (AGENTS.md §5). */
import { JSDOM } from 'jsdom';
import { browserEnv } from './browser_env.mjs';
import fs from 'node:fs';

const POPUP = `
<div class="modalOverlay cpOverlay" id="cpOverlay"><div class="modalShell cpShell">
 <div class="cpBox" id="cpBox">
  <aside class="cpSide">
   <div class="cpProfile"><div class="cpAv" id="cpAv"></div>
    <div class="cpProfileText"><b id="cpName"></b><p id="cpDesc"></p></div></div>
   <button type="button" class="cpNewBtn" id="cpNewBtn"><i>+</i>새로운 대화</button>
   <div class="cpListLabel">대화 목록</div><div class="cpList" id="cpList"></div>
  </aside>
  <div class="cpMain"><div class="cpThreadWrap" id="cpThreadWrap">
    <div class="cpEmpty"><p id="cpEmptyText"></p></div>
    <div class="thread cpThread" id="cpThread"></div></div>
   <div class="cpInputRow"><textarea id="cpInput" rows="1"></textarea>
    <button class="cpSend" id="cpSend">→</button></div>
  </div></div><button class="modalClose" id="cpClose">×</button></div></div>
<section class="view on" id="v-home"><div id="hotList"></div><div id="mChips"></div>
 <h1 id="mState"><span class="ln">a</span></h1><div class="heroL"><p>x</p></div>
 <div class="heroR"></div><div class="chatbar"><button id="smToggle"><span class="lbl">
 <i class="ic">◑</i><span class="tx">살!말?</span></span></button>
 <div class="ghostQ" id="ghostQ"><span class="spark">✧</span><span class="qline" id="qline"></span></div>
 <input id="mInput"><button class="cpOpenBtn" id="cpOpen"><i>☰</i><span>지난 대화</span></button>
 </div><div class="thread" id="thread"></div></section>`;

/* ★ 2026-09-27 — 팝업 모듈이 앱 셸(라우터 · 인트로 · 연관어 팝오버)까지 끌고 들어와
   불러오는 순간 그 칸들을 찾는다. 조각 마크업 대신 실제 index.html 을 세운다(run.sh 가 app_index.html 로 복사). */
const dom = new JSDOM(fs.existsSync('app_index.html') ? fs.readFileSync('app_index.html','utf8')
                                                    : '<!doctype html><body>'+POPUP+'</body>',
  {url:'http://localhost:5173/', pretendToBeVisual:true});
for (const k of ['location','requestAnimationFrame','cancelAnimationFrame','HTMLElement','Node',
                 'Event','CustomEvent','MouseEvent','KeyboardEvent','getComputedStyle',
                 'TextDecoder','AbortController']) {
  try { global[k] = dom.window[k] ?? global[k] } catch(e) {}
}
global.window = dom.window; global.document = dom.window.document;
browserEnv(dom);   /* 앱 셸이 따라 들어오며 찾는 나머지 창 전역 */
global.fetch = async () => { throw new Error('서버 없음 (의도됨)') };

/* 앱과 같은 순서로 불러온다 — chat_popup.js 를 먼저 부르면 모듈 순환에서 ME 가 아직 없다 */
if (fs.existsSync('app/main.js')) await import('./app/main.js');
/* 2026-09 부터 챗봇은 로그인 관문을 지나야 질문을 보낸다 — 지난 상태로 둔다 (frontend/tests/chat_popup_ui 와 같다) */
if (fs.existsSync('app/account/static/js/profile.js'))
  (await import('./app/account/static/js/profile.js')).AUTH.in = true;
const cp = await import('./app/home/static/js/chat_popup.js');
const wait = ms => new Promise(r=>setTimeout(r,ms));
let fail=0;
const ok=(c,m)=>{ console.log((c?'  OK  ':'  X!! ')+m); if(!c) fail++ };
const $=s=>document.querySelector(s);

/* 팝업을 한 번 열어 로그인한 사람의 대화함으로 맞춘다(cpSyncOwner).
   열기 전에 만든 대화는 주인이 바뀌면서 빠진다 — 실제 앱에서도 팝업을 연 뒤에 대화가 생긴다. */
cp.openChatPopup(); cp.closeChatPopup();

console.log('=== 1. 대화 목록에 메뉴(⋮)가 붙는가 ===');
const a=cp.cpNewConvo(); a.title='발레코어는 지금 유행이야?';
const b=cp.cpNewConvo(); b.title='고프코어 반응';
cp.cpRenderList();
ok(document.querySelectorAll('.cpItemRow').length===2, '.cpItemRow 두 줄');
ok(document.querySelectorAll('.cpItem[data-cid]').length===2, '.cpItem[data-cid] 는 그대로 (라우터가 이걸 잡는다)');
/* 2026-09 부터 연필 대신 ⋮ 메뉴(이름 바꾸기 · 고정 · 삭제) */
ok(document.querySelectorAll('.cpKebab[data-menu]').length===2, '.cpKebab[data-menu] 두 개');
ok($('.cpItem').querySelector('button')===null, '.cpItem 안에 버튼이 없다 (버튼 중첩은 잘못된 HTML)');

console.log('\n=== 2. 제목을 그 자리에서 고치는가 ===');
cp.cpEditTitle(a.id);
const inp=$('.cpTitleIn');
ok(!!inp, '.cpTitleIn 이 생겼다');
ok(inp && inp.value==='발레코어는 지금 유행이야?', '현재 제목이 들어 있다');
if(inp){
  inp.value='  발레코어  정리  ';
  inp.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
}
ok(a.title==='발레코어 정리', '엔터로 저장되고 공백이 정리된다 ('+a.title+')');
ok(!$('.cpTitleIn'), '저장하면 입력칸이 사라진다');
/* cpNewConvo 는 unshift 라 나중에 만든 b 가 위에 온다 — a 의 줄을 콕 집어 본다 */
const rowA=()=>document.querySelector('.cpItem[data-cid="'+a.id+'"] span').textContent;
ok(rowA()==='발레코어 정리', '목록에 반영된다 ('+rowA()+')');

console.log('\n=== 3. Esc 는 되돌린다 ===');
cp.cpEditTitle(a.id);
const inp2=$('.cpTitleIn'); inp2.value='딴 제목';
inp2.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
ok(a.title==='발레코어 정리', 'Esc 면 원래 제목 그대로 ('+a.title+')');

console.log('\n=== 4. 제목을 비우면 "새 대화" 로 보인다 ===');
cp.cpEditTitle(b.id);
const inp3=$('.cpTitleIn'); inp3.value='   ';
inp3.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
ok(b.title==='', '빈 제목이 저장된다');
ok([...document.querySelectorAll('.cpItem span')].some(s=>s.textContent==='새 대화'),
   '목록에는 "새 대화" 로 보인다');

console.log('\n=== 5. 홈에서 들어오면 언제나 새 대화 ===');
const before=cp.cpStore().convos.length;
cp.openChatWith('나일론 요즘 어때?', 'rise', {fresh:true});
await wait(40);
const after=cp.cpStore().convos.length;
ok(after===before+1, '새 대화가 하나 늘었다 ('+before+' → '+after+')');
ok(cp.cpStore().convos[0].messages.length>=1, '질문이 새 대화 안에 들어갔다');
ok(cp.cpStore().convos[1].messages.length===0, '이전 대화는 건드리지 않았다');

console.log('\n=== 6. fresh 없이 부르면 이어 붙는다 (팝업 안에서 이어 묻는 경우) ===');
const n0=cp.cpStore().convos.length, m0=cp.cpStore().convos[0].messages.length;
cp.openChatWith('그러면 새틴은?', 'rise');
await wait(40);
ok(cp.cpStore().convos.length===n0, '대화 수는 그대로');
ok(cp.cpStore().convos[0].messages.length>m0, '같은 대화에 쌓였다');

console.log('\n=== 7. 아바타 뒤집기가 터지지 않는가 (anime 없는 환경) ===');
let threw=null;
try{ cp.cpToggleMode() }catch(e){ threw=e }   /* 예전 cpFlipMode */
await wait(60);
ok(!threw, 'cpToggleMode 가 예외를 던지지 않는다'+(threw?' — '+threw.message:''));
ok($('#cpAv').getAttribute('role')==='button', '아바타에 role=button 이 붙는다');
ok($('#cpAv').hasAttribute('title'), '무엇을 하는 버튼인지 title 로 알려준다');

console.log('\n=== 8. 쓰는 클래스가 CSS 에 있는가 ===');
/* 7번에서 살말 모드로 넘어가 목록이 비었다. 일반 모드 목록을 다시 세워 놓고 본다.
   smSwitch 는 연타를 막으려 900ms 동안 smBusy 를 걸어 둔다 — 그만큼 기다려야 되돌아간다. */
await wait(950);          /* 먼저 기다린다 — 7번 직후엔 아직 잠겨 있어 전환이 무시된다 */
cp.cpToggleMode();
await wait(60);
cp.cpRenderList();
const css=fs.readdirSync('css').map(f=>fs.readFileSync('css/'+f,'utf8')).join('\n');
const declared=new Set([...css.matchAll(/\.([A-Za-z][A-Za-z0-9_-]*)/g)].map(m=>m[1]));
const used=new Set();
document.querySelectorAll('#cpList *, #cpOpen').forEach(el=>el.classList.forEach(c=>used.add(c)));
const missing=[...used].filter(c=>!declared.has(c));
ok(missing.length===0, '없는 클래스: '+(missing.join(', ')||'없음')+' / 쓴 것: '+[...used].join(' '));

console.log(fail ? `\n실패 ${fail}건` : '\n전부 통과');
process.exit(fail?1:0);
