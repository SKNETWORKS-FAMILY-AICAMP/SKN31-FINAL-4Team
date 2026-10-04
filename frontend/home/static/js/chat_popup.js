import { $, $$, HAS_A, aAnimate } from '../../../core/static/js/dom.js';
import { SM_ON, STYLES, LIKED, M_QUESTIONS, SM_QUESTIONS, ansCardHTML, smSwitch } from './chat.js';
import { API_BASE, classifyFitImages, sendAnswerFeedback, isUp, askStream, reportHTML, notesHTML, followupHTML, actionsHTML, refusalHTML, requestLexicon, fillBars, MAX_IMAGES, imageFileToDataURL, bindImageDrop, wantsVirtualFit, responseCardHTML, storyHTML, tickerRange } from './chat_api.js';
import { AUTH, ME, openStyleSelect, requireAuth } from '../../../account/static/js/profile.js';
import { logChat, chatList, chatLoad, chatSaveTurn, chatImport, chatUpdate, chatTruncate, chatDelete } from '../../../account/static/js/account_api.js';
import { planGuard } from '../../../account/static/js/plan.js';

/* ══════════════════════════════════════════════════════
   챗봇 팝업 — 일반 모드 · 살말 모드
   ------------------------------------------------------
   두 모드는 대화창 자체가 다르다. 각자 자기 대화 목록(CP_STORE)을
   따로 들고 있어서, 모드를 오가도 서로의 대화에 섞이지 않는다.
   홈의 입력창·칩 버튼은 이제 인라인으로 답을 펼치지 않고
   전부 이 팝업 하나로 모인다.
   ══════════════════════════════════════════════════════ */
const CP_STORE={ general:{convos:[],activeId:null}, salmal:{convos:[],activeId:null} };
let CP_UID=1;

/* ── 대화 보관 (2026-09-13) ────────────────────────────
   예전에는 대화가 이 파일의 변수에만 있었다. 새로고침 한 번에 어제 물어본 답이
   통째로 사라졌고, 사용자는 같은 질문을 다시 쳐야 했다.
   서버에 계정별로 쌓는 것이 옳지만 그 전까지는 브라우저에 남긴다 —
   같은 기기에서는 새로고침·재방문을 견딘다.
   ★ 용량이 문제다. 첨부 사진이 data URL 이라 대화 몇 개로도 한도를 넘긴다.
     넘치면 (1) 오래된 대화의 사진부터 버리고 (2) 그래도 넘치면 오래된 대화를
     버린다. 사진을 버린 대화는 글은 그대로 남는다 — 다시 열었을 때 무엇을
     물었는지는 읽을 수 있어야 한다. */
const CP_KEY='feedit.chat.v1';
let CP_OWNER='';                     /* 로그인한 계정 — 계정마다 따로 보관한다 (아래 DB 연동) */
const CP_KEEP=20;                    /* 모드별로 보관할 대화 수 */
let cpSaveT=0;
function cpPackMsg(m,keepImages){
  const out={role:m.role,text:m.text||'',html:m.html||'',key:m.key||null,
             cardHtml:m.cardHtml||'',followHtml:m.followHtml||'',cueHtml:m.cueHtml||'',
             actionsHtml:m.actionsHtml||'',turn:m.turn||null,
             feedback:m.feedback||null,feedbackPrompt:m.feedbackPrompt===true,
             imagesDropped:!!m.imagesDropped, sid:m.sid||null};
  if(m.images&&m.images.length){
    if(keepImages)out.images=m.images; else out.imagesDropped=true;
  }
  return out;   /* run·fit 은 일부러 뺀다 — 진행 중 상태와 약속(Promise)은 저장할 것이 아니다 */
}
function cpPack(keepImagesFor){
  const out={};
  for(const mode of ['general','salmal']){
    const s=CP_STORE[mode];
    /* 단독 VTON은 fit 상태를 저장하지 않는 한시 화면이다.
       fit만 빼고 대화를 남기면 새로고침 후 안내 문장만 남는 꺼진 진입점이 된다. */
    const kept=s.convos.filter(c=>!c.transient).slice(0,CP_KEEP);
    out[mode]={activeId:kept.some(c=>c.id===s.activeId)?s.activeId:null,
      convos:kept.map((c,i)=>({
        id:c.id,key:c.key,mode,sid:c.sid||null,at:c.at||0,loaded:c.loaded!==false,
        title:c.title||'',time:c.time||'',pinned:!!c.pinned,
        messages:(c.messages||[]).filter(m=>!m.pending).map(m=>cpPackMsg(m,i<keepImagesFor))}))};
  }
  return out;
}
export function cpSave(){
  if(typeof localStorage==='undefined')return;
  clearTimeout(cpSaveT);
  /* 연달아 바뀌는 동안 매번 쓰지 않는다 — 타이핑 중 저장이 겹치면 버벅인다 */
  cpSaveT=setTimeout(()=>{
    for(const keep of [CP_KEEP,3,1,0]){
      try{ localStorage.setItem(cpStorageKey(),JSON.stringify({v:1,uid:CP_UID,store:cpPack(keep)})); return }
      catch(e){ /* 한도 초과 — 사진을 더 버리고 다시 */ }
    }
    try{ localStorage.removeItem(cpStorageKey()) }catch(e){ /* 지우지도 못하면 포기한다 */ }
  },400);
}
function cpRestore(){
  if(typeof localStorage==='undefined')return;
  let saved=null;
  try{ saved=JSON.parse(localStorage.getItem(cpStorageKey())||'null') }catch(e){ saved=null }
  /* 계정별 보관 전의 기록(feedit.chat.v1)은 처음 로그인한 계정이 가져간다 — 그 뒤 DB 로 옮겨진다 */
  if(!saved&&CP_OWNER){
    try{
      saved=JSON.parse(localStorage.getItem(CP_KEY)||'null');
      if(saved)localStorage.removeItem(CP_KEY);
    }catch(e){ saved=null }
  }
  if(!saved||saved.v!==1||!saved.store)return;
  let max=0;
  for(const mode of ['general','salmal']){
    const from=saved.store[mode];
    if(!from||!Array.isArray(from.convos))continue;
    CP_STORE[mode].convos=from.convos.filter(c=>c&&Array.isArray(c.messages)).map(c=>{
      max=Math.max(max,Number(c.id)||0);
      return {id:Number(c.id)||0,key:cpValidKey(c.key)||cpNewKey(),mode,
              sid:Number(c.sid)||null,at:Number(c.at)||0,loaded:c.loaded!==false,
              title:String(c.title||''),time:String(c.time||''),
              pinned:!!c.pinned,
              messages:c.messages.map(m=>Object.assign({},m,{pending:false}))};
    });
    CP_STORE[mode].activeId=from.activeId||null;
    cpSortConvos(CP_STORE[mode]);
  }
  CP_UID=Math.max(CP_UID,max+1,Number(saved.uid)||1);
}
cpRestore();
/* ── 대화 기록 DB 연동 (2026-09-18) ─────────────────────
   원본은 RDS(app.chat_session · app.chat_message, /api/auth/chats)다.
   위의 localStorage 는 팝업을 열자마자 그리기 위한 사본이다.
   · 대화 하나 = 서버 세션 하나. 둘을 잇는 값은 c.key (기기마다 세는 c.id 는 겹친다)
   · 팝업을 열면 목록을 받아 합치고, 대화를 누르면 그때 본문을 받는다
   · 답이 끝날 때마다 질문+답을 한 턴으로 저장한다 — turn(무엇을 물었나·용어·사진 관찰값)도
     같이 남으므로, 다른 기기에서 이어 물어도 챗봇이 앞 맥락을 그대로 받는다
   · 쓰기 실패는 조용히 넘긴다 — 저장이 안 된다고 대화가 막히면 안 된다 */
function cpStorageKey(){ return CP_OWNER?CP_KEY+':'+CP_OWNER:CP_KEY }
function cpNewKey(){ return Date.now().toString(36)+Math.random().toString(36).slice(2,8) }
function cpValidKey(k){ k=String(k||''); return /^[A-Za-z0-9_-]{1,40}$/.test(k)?k:'' }
const cpModeOf=c=>c&&c.mode==='salmal'?'salmal':(c&&c.mode==='general'?'general':cpMode());
export const cpConvId=c=>'cp-'+cpModeOf(c)+'-'+c.key;
/* 로그인한 계정이 바뀌면(로그아웃 → 다른 계정) 앞 사람 대화를 보이지 않게 갈아 끼운다 */
function cpSyncOwner(){
  const owner=AUTH.in?String(ME.mail||'me').toLowerCase():'';
  if(owner===CP_OWNER)return false;
  CP_OWNER=owner;
  for(const mode of ['general','salmal']){ CP_STORE[mode].convos=[]; CP_STORE[mode].activeId=null }
  cpRestore();
  cpHydratedAt=0;
  return true;
}
function cpTimeLabel(iso){
  const d=new Date(iso||Date.now());
  return isNaN(d)?cpNowLabel():(d.getMonth()+1)+'월 '+d.getDate()+'일';
}
function cpFromServer(rows){
  return (rows||[]).map(r=>{
    const meta=r.metadata||{};
    if(r.role==='USER')return {role:'me',text:r.content||'',images:[],
      imagesDropped:Number(meta.images)>0,sid:r.id};
    if(r.role!=='ASSISTANT')return null;
    return {role:'ai',html:meta.html||'',cardHtml:meta.card_html||'',followHtml:meta.follow_html||'',
      cueHtml:meta.cue_html||'',actionsHtml:meta.actions_html||'',key:meta.key||null,
      turn:meta.turn||null,feedbackPrompt:false,pending:false,sid:r.id};
  }).filter(Boolean);
}
function cpSortByTime(bucket){
  bucket.convos.sort((a,b)=>(b.at||0)-(a.at||0));
  cpSortConvos(bucket);
}
/* 대화 본문을 서버에서 받는다. 이미 있는 것(sid 가 같은 것)은 겹쳐 넣지 않는다. */
function cpEnsureLoaded(c){
  if(!c||!c.sid||c.loaded!==false||!AUTH.in)return Promise.resolve();
  if(c.loadP)return c.loadP;
  c.loadP=chatLoad(c.sid).then(d=>{
    const have=new Set(c.messages.map(m=>m.sid).filter(Boolean));
    const older=cpFromServer(d&&d.messages).filter(m=>!have.has(m.sid));
    c.messages=older.concat(c.messages);
    c.loaded=true; cpSave();
  }).catch(()=>{ /* 다음에 열 때 다시 받는다 */ }).finally(()=>{
    c.loadP=null;
    if(cpActiveConvo()===c)cpRenderThread();
  });
  return c.loadP;
}
/* 브라우저에만 있던 대화(연동 전 기록)를 한 번 서버로 옮긴다 */
function cpTurnsOf(c){
  const out=[];
  for(let i=0;i<c.messages.length;i++){
    const me=c.messages[i], ai=c.messages[i+1];
    if(me.role!=='me'||!ai||ai.role!=='ai'||ai.pending||ai.fit)continue;
    out.push({question:me.text||'',images:(me.images||[]).length,answer:cpAnswerPayload(ai)});
    i++;
  }
  return out;
}
async function cpImportLocal(c){
  if(c.importing||c.saving)return;
  const turns=cpTurnsOf(c); if(!turns.length)return;
  c.importing=true;
  try{
    const d=await chatImport({mode:cpModeOf(c),key:c.key,title:c.title||'',pinned:!!c.pinned,turns});
    if(d&&d.session){
      c.sid=d.session.id; c.loaded=true;
      const pairs=d.ids||[]; let k=0;
      for(let i=0;i<c.messages.length&&k<pairs.length;i++){
        const me=c.messages[i], ai=c.messages[i+1];
        if(me.role!=='me'||!ai||ai.role!=='ai'||ai.pending||ai.fit)continue;
        me.sid=pairs[k][0]; ai.sid=pairs[k][1]; k++; i++;
      }
      cpSave();
    }
  }finally{ c.importing=false }
}
let cpHydratedAt=0, cpHydrating=null;
function cpHydrate(force){
  if(!AUTH.in)return Promise.resolve();
  if(cpHydrating)return cpHydrating;
  if(!force&&Date.now()-cpHydratedAt<60000)return Promise.resolve();
  cpHydrating=(async()=>{
    const d=await chatList();
    const rows=(d&&d.sessions)||[];
    const seen={general:new Set(),salmal:new Set()};
    for(const r of rows){
      const mode=r.mode==='salmal'?'salmal':'general';
      const key=cpValidKey(r.key); if(!key)continue;
      seen[mode].add(key);
      const bucket=CP_STORE[mode];
      const at=Date.parse(r.updated_at)||0;
      let c=bucket.convos.find(x=>x.key===key);
      if(c){
        c.sid=r.id; c.title=r.title||c.title; c.pinned=!!r.pinned;
        c.at=Math.max(c.at||0,at); c.time=cpTimeLabel(r.updated_at);
      }else{
        bucket.convos.push({id:CP_UID++,key,mode,sid:r.id,at,time:cpTimeLabel(r.updated_at),
          title:r.title||'',pinned:!!r.pinned,messages:[],loaded:false});
      }
    }
    const full=rows.length>=60;   /* 서버 목록 상한 — 넘치면 '없음'을 '지워짐'으로 읽지 않는다 */
    for(const mode of ['general','salmal']){
      const bucket=CP_STORE[mode];
      bucket.convos=bucket.convos.filter(c=>{
        if(!c.sid||seen[mode].has(c.key)||full)return true;
        if(cpActiveRun&&cpActiveRun.c===c)return true;
        return false;                                /* 다른 기기에서 지운 대화 */
      });
      if(bucket.activeId&&!bucket.convos.some(c=>c.id===bucket.activeId))bucket.activeId=null;
      cpSortByTime(bucket);
      for(const c of bucket.convos) if(!c.sid&&!seen[mode].has(c.key)) void cpImportLocal(c);
    }
    cpHydratedAt=Date.now(); cpSave();
    if($('#cpOverlay')&&$('#cpOverlay').classList.contains('on')){ cpRenderList(); cpRenderThread(); }
  })().catch(()=>{ /* 서버가 꺼져 있으면 브라우저 사본으로 계속 쓴다 */ }).finally(()=>{ cpHydrating=null });
  return cpHydrating;
}
function cpAnswerPayload(ai){
  const holder=typeof document!=='undefined'?document.createElement('div'):null;
  let text='';
  if(holder){
    holder.innerHTML=[ai.html,ai.cardHtml].filter(Boolean).join(' ');
    text=(holder.textContent||'').replace(/\s+/g,' ').trim();
  }
  return {text,html:ai.html||'',card_html:ai.cardHtml||'',follow_html:ai.followHtml||'',
    cue_html:ai.cueHtml||'',actions_html:ai.actionsHtml||'',key:ai.key||null,turn:ai.turn||null};
}
/* 답 한 턴을 저장한다. 돌아온 메시지 id 를 붙여 둔다 — 질문을 고쳐 다시 물을 때 쓴다. */
async function cpPersistTurn(c,me,ai){
  if(!AUTH.in||!c||!me||!ai)return;
  c.saving=(c.saving||0)+1;
  let d=null;
  try{
    d=await chatSaveTurn({mode:cpModeOf(c),key:c.key,title:c.title||'',
      question:me.text||'',images:(me.images||[]).length,answer:cpAnswerPayload(ai),
      answer_ms:ai.t0?Math.max(0,Date.now()-ai.t0):null});
  }finally{ c.saving-=1 }
  if(!d||!d.session)return;
  c.sid=d.session.id; if(c.loaded===undefined)c.loaded=true;
  me.sid=d.user_message_id; ai.sid=d.ai_message_id;
  cpSave();
}
/* 사이드바 프로필(이름·소개)은 모드별로 다르게 남겨 둔다 — 팝업 자체가 둘이라는 것을
   보여주는 자리라서다. 대화 안의 답변 라벨은 별개로 항상 FEEDiT 하나로 묶는다(아래). */
const CP_PROFILE={
  general:{name:'일반 모드', desc:'요즘 뜨는 트렌드를 알려드려요.',
    empty:'요즘 뜨는 트렌드가 궁금하다면 물어보세요.', ph:'궁금한 트렌드를 질문해 주세요.'},
  salmal :{name:'살말 모드', desc:'사도 되는지, 대신 판단해 드려요.',
    empty:'살까 말까 고민되는 아이템을 물어보세요.', ph:'고민되는 아이템을 질문해 주세요.'}
};
/* 답변 중엔 이 하나로 통일 — 별이 돌고 글자가 옅어졌다 밝아지며 "생각 중"을 표현한다 */
let cpTypeTimer=null;
let cpActiveRun=null;
/* escapeHtml 은 salmalBoot() 지역 함수라 팝업(전역 스코프)에서는 안 보인다 — 따로 하나 둔다 */
function cpEsc(s){
  return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
function cpShopUrl(raw){
  try{
    const url=new URL(String(raw||''));
    return url.protocol==='https:'||url.protocol==='http:'?url.href:'';
  }catch(_){ return '' }
}
const cpMode =()=>SM_ON?'salmal':'general';

/* ── 팝업 챗바 이미지 첨부 ─────────────────────────────
   홈 챗바(chat.js의 mImages)와 별개로 팝업 자체에서도 사진을 올릴 수 있다 —
   팝업이 떠 있는 동안 이어 묻는 질문에도 새 사진을 붙일 수 있어야 하므로. */
let cpImages=[];
function cpImgPaint(){
  const box=$('#cpImgAttach'); if(!box)return;
  box.hidden = cpImages.length===0;
  box.innerHTML = cpImages.map((im,i)=>
    '<span class="imgChip"><img src="'+im.url+'" alt=""><button type="button" data-rm="'+i+'" aria-label="사진 삭제">×</button></span>').join('');
  if(cpActiveRun)cpRunButton(true);      /* 답하는 중에 사진을 넣으면 버튼이 '다음 질문' 으로 */
}
async function cpImgPick(files){
  for(const f of files){
    if(cpImages.length>=MAX_IMAGES)break;
    try{ const url=await imageFileToDataURL(f); cpImages.push({url}); }catch(e){ /* 이미지가 아니면 조용히 건너뛴다 */ }
  }
  cpImgPaint();
}
/* 보낼 때만 비운다 — 그 전까지는 대화창을 닫았다 열어도 그대로 남아 있는다 */
function cpImgTake(){ const out=cpImages.map(im=>im.url); cpImages=[]; cpImgPaint(); return out; }
export function cpImgInit(){
  const add=$('#cpImgAdd'), input=$('#cpImgFile'), box=$('#cpImgAttach');
  if(add&&input){
    add.addEventListener('click', ()=>input.click());
    input.addEventListener('change', ()=>{
      if(input.files&&input.files.length)cpImgPick([...input.files]);
      input.value='';
    });
  }
  if(box)box.addEventListener('click', e=>{
    const rm=e.target.closest('[data-rm]'); if(!rm)return;
    cpImages.splice(+rm.dataset.rm,1); cpImgPaint();
  });
  /* 팝업 입력줄에 사진을 끌어다 놓아도 + 버튼과 같은 경로로 들어간다 */
  bindImageDrop($('.cpInputWrap'), files=>cpImgPick(files));
}
/* 고정한 대화는 언제나 목록 맨 위에 둔다 (2026-09-14).
   같은 무리(고정끼리·보통끼리) 안의 순서는 건드리지 않는다 — 최근 것이
   위라는 규칙이 고정 때문에 뒤집히면 찾던 대화가 사라진 것처럼 보인다. */
function cpSortConvos(s){
  if(!s||!Array.isArray(s.convos))return;
  const pinned=s.convos.filter(c=>c.pinned), rest=s.convos.filter(c=>!c.pinned);
  s.convos=pinned.concat(rest);
}
export const cpStore=()=>CP_STORE[cpMode()];
function cpActiveConvo(){
  const s=cpStore();
  return s.convos.find(c=>c.id===s.activeId)||null;
}
function cpTitleFrom(text){
  const t=text.replace(/\s+/g,' ').trim();
  return t.length>24 ? t.slice(0,24)+'…' : t;
}
function cpNowLabel(){
  const d=new Date();
  return (d.getMonth()+1)+'월 '+d.getDate()+'일';
}
export function cpNewConvo(){
  const s=cpStore();
  const c={id:CP_UID++, key:cpNewKey(), mode:cpMode(), at:Date.now(), title:'', time:cpNowLabel(), messages:[]};
  s.convos.unshift(c);
  s.activeId=c.id;
  cpSave();
  return c;
}
/* 질문 문장에서 어떤 카드를 보여줄지 고른다 — sendChat() 이 쓰던 것과 같은 규칙 */
export function cpKeyFor(v){
  if(SM_ON){
    if(/최저가|가격|싸|비싸|할인/.test(v))return 'smPrice';
    if(/내년|오래|수명|계속/.test(v))return 'smLife';
    if(/대신|비슷|대안|다른/.test(v))return 'smAlt';
    if(/투표|다들|사람들|반응/.test(v))return 'smVote';
    return 'smBuy';
  }
  if(/고프/.test(v))return 'gorp';
  if(/발레/.test(v))return 'ballet';
  if(/29CM|무신사|비교|온도/.test(v))return 'plat';
  if(/체형|코트|추천/.test(v))return 'body';
  return 'rise';
}
function cpPaintProfile(){
  const p=CP_PROFILE[cpMode()];
  $('#cpAv').textContent=SM_ON?'◑':'✧';
  $('#cpName').textContent=p.name;
  $('#cpDesc').textContent=p.desc;
  cpEmptyPaint();
  cpTastePaint();
  const ta=$('#cpInput'); if(ta)ta.placeholder=p.ph;
}
/* ── 대화 줄 메뉴 (2026-09-14) ────────────────────────
   연필(이름 수정)과 휴지통(삭제)이 줄마다 나와 있었다. 버튼 두 개가 제목을
   밀어 붙이고, 마우스를 올려야 드러나니 무엇이 있는지 알기도 어려웠다.
   세로 점 셋(⋮) 하나로 모으고, 눌렀을 때 할 수 있는 일을 글로 보여 준다.
   ★ 메뉴는 목록(.cpList) 안에 두지 않는다 — 목록은 세로 스크롤이 걸려 있어
     (overflow-y:auto) 그 안에 띄우면 아래쪽 줄에서 잘린다. 화면 좌표로
     띄우고(position:fixed) 버튼 옆에 붙인다. */
const CP_KEBAB='<svg viewBox="0 0 14 14" fill="currentColor" aria-hidden="true">'+
  '<circle cx="7" cy="2.6" r="1.25"/><circle cx="7" cy="7" r="1.25"/><circle cx="7" cy="11.4" r="1.25"/></svg>';
const CP_MI=(d)=>'<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" '+
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+d+'</svg>';
const CP_MI_PIN=CP_MI('<path d="M7.6 2.8h4.8l-.6 4 2.6 2.6H5.6l2.6-2.6z"/><path d="M10 9.4v7.2"/>');
const CP_MI_UNPIN=CP_MI('<path d="M7.6 2.8h4.8l-.6 4 2.6 2.6H5.6l2.6-2.6z"/><path d="M10 9.4v7.2"/><path d="M3 3l14 14"/>');
const CP_MI_RENAME=CP_MI('<path d="M3.5 16.5h3.2L16 7.2a1.7 1.7 0 0 0-2.4-2.4L4.3 14.1z"/><path d="M12.6 5.9l2.3 2.3"/>');
const CP_MI_DEL=CP_MI('<path d="M3.6 5.4h12.8M8 5.4V3.7h4v1.7M5.2 5.4l.7 11h8.2l.7-11"/><path d="M8.4 8.4v5M11.6 8.4v5"/>');

export function cpRenderList(){
  const list=$('#cpList'); if(!list)return;
  cpCloseMenu();
  const s=cpStore();
  cpSortConvos(s);
  if(!s.convos.length){
    list.innerHTML='<p class="cpListEmpty">최근 대화가 없습니다.</p>';
    return;
  }
  /* ⋮ 는 .cpItem 밖에 둔다 — 버튼 안에 버튼을 넣을 수 없고,
     라우터가 잡는 .cpItem[data-cid] 도 그대로 살아야 한다. */
  list.innerHTML=s.convos.map(c=>
      '<div class="cpItemRow'+(c.pinned?' pinned':'')+'">'+
        '<button type="button" class="cpItem'+(c.id===s.activeId?' on':'')+'" data-cid="'+c.id+'">'+
          '<em>'+c.time+(c.pinned?'<b class="cpPinMark" title="고정된 대화">고정</b>':'')+'</em>'+
          '<span>'+cpEsc(c.title||'새 대화')+'</span>'+
        '</button>'+
        '<button type="button" class="cpKebab" data-menu="'+c.id+'" '+
          'title="대화 메뉴" aria-label="대화 메뉴" aria-haspopup="true" aria-expanded="false">'+
          CP_KEBAB+'</button>'+
      '</div>').join('');
}

/* ── 메뉴 열고 닫기 ────────────────────────────────────
   한 번에 하나만 떠 있는다. 바깥을 누르거나 Esc·스크롤·창 크기 변화에 닫힌다 —
   목록이 움직이는데 메뉴만 제자리에 남아 있으면 엉뚱한 대화를 지우게 된다. */
let cpMenuFor=0;
function cpMenuEl(){
  let el=document.getElementById('cpMenu');
  if(!el){
    el=document.createElement('div');
    el.id='cpMenu'; el.className='cpMenu'; el.setAttribute('role','menu');
    el.hidden=true;
    document.body.appendChild(el);
  }
  return el;
}
function cpMenuHTML(c,confirming){
  if(confirming){
    return '<p class="cpMenuAsk">이 대화를 지울까요? 되돌릴 수 없습니다.</p>'+
      '<div class="cpMenuAskRow">'+
      '<button type="button" class="cpMenuItem" data-mi="cancel">취소</button>'+
      '<button type="button" class="cpMenuItem danger" data-mi="del-yes">삭제</button>'+
      '</div>';
  }
  return '<button type="button" class="cpMenuItem" data-mi="pin" role="menuitem">'+
      (c.pinned?CP_MI_UNPIN:CP_MI_PIN)+'<span>'+(c.pinned?'고정 해제':'고정')+'</span><em>P</em></button>'+
    '<button type="button" class="cpMenuItem" data-mi="rename" role="menuitem">'+
      CP_MI_RENAME+'<span>이름 변경</span><em>R</em></button>'+
    '<div class="cpMenuLine"></div>'+
    '<button type="button" class="cpMenuItem danger" data-mi="del" role="menuitem">'+
      CP_MI_DEL+'<span>삭제</span><em>D</em></button>';
}
function cpPlaceMenu(el,btn){
  const r=btn.getBoundingClientRect();
  el.hidden=false;
  el.style.visibility='hidden'; el.style.left='0px'; el.style.top='0px';
  const w=el.offsetWidth, h=el.offsetHeight;
  let left=r.right-w, top=r.bottom+6;
  if(left<10)left=10;
  if(left+w>window.innerWidth-10)left=window.innerWidth-10-w;
  if(top+h>window.innerHeight-10)top=Math.max(10,r.top-6-h);
  el.style.left=Math.round(left)+'px';
  el.style.top=Math.round(top)+'px';
  el.style.visibility='';
}
export function cpOpenMenu(btn){
  const id=Number(btn.dataset.menu);
  if(cpMenuFor===id){ cpCloseMenu(); return }
  const c=cpStore().convos.find(x=>x.id===id); if(!c)return;
  cpCloseMenu();
  cpMenuFor=id;
  const el=cpMenuEl();
  el.dataset.cid=String(id);
  el.innerHTML=cpMenuHTML(c,false);
  el.classList.remove('on');
  cpPlaceMenu(el,btn);
  requestAnimationFrame(()=>el.classList.add('on'));
  btn.setAttribute('aria-expanded','true');
  btn.classList.add('on');
}
export function cpCloseMenu(){
  const el=document.getElementById('cpMenu');
  if(el){ el.hidden=true; el.classList.remove('on'); el.dataset.cid=''; }
  document.querySelectorAll('.cpKebab.on').forEach(b=>{
    b.classList.remove('on'); b.setAttribute('aria-expanded','false');
  });
  cpMenuFor=0;
}
/* 메뉴 안의 선택. 삭제만 한 번 더 묻는다 — 지운 대화는 되돌릴 수 없다. */
function cpMenuPick(what){
  const el=document.getElementById('cpMenu'); if(!el)return;
  const id=Number(el.dataset.cid);
  const s=cpStore(), c=s.convos.find(x=>x.id===id);
  if(!c){ cpCloseMenu(); return }
  if(what==='pin'){ c.pinned=!c.pinned; cpCloseMenu(); cpRenderList(); cpSave();
    if(AUTH.in&&c.sid)chatUpdate({mode:cpModeOf(c),key:c.key,pinned:c.pinned});
    return }
  if(what==='rename'){ cpCloseMenu(); cpEditTitle(id); return }
  if(what==='del'){
    const btn=document.querySelector('.cpKebab[data-menu="'+id+'"]');
    el.innerHTML=cpMenuHTML(c,true);
    if(btn)cpPlaceMenu(el,btn);
    return;
  }
  if(what==='del-yes'){ cpCloseMenu(); cpDeleteConvo(id); return }
  if(what==='cancel'){ cpCloseMenu(); return }
}
/* 바깥을 누르면 닫는다. ⋮ 자체를 누른 것은 cpOpenMenu 가 맡는다(열림 토글). */
document.addEventListener('click',e=>{
  const item=e.target.closest('#cpMenu [data-mi]');
  if(item){ e.stopPropagation(); cpMenuPick(item.dataset.mi); return }
  if(e.target.closest('#cpMenu')||e.target.closest('.cpKebab'))return;
  if(cpMenuFor)cpCloseMenu();
});
/* 메뉴에 적어 둔 글쇠(P·R·D)는 실제로 눌린다 — 적어 두고 안 먹으면
   적어 두지 않느니만 못하다. 메뉴가 떠 있는 동안에만 가로챈다. */
document.addEventListener('keydown',e=>{
  if(!cpMenuFor)return;
  if(e.key==='Escape'){ cpCloseMenu(); return }
  if(e.metaKey||e.ctrlKey||e.altKey)return;
  const key=String(e.key||'').toLowerCase();
  const hit={p:'pin',r:'rename',d:'del'}[key];
  if(!hit)return;
  e.preventDefault();
  cpMenuPick(hit);
});
window.addEventListener('resize',()=>cpCloseMenu());
/* 목록이 스크롤되면 메뉴만 제자리에 남는다 — 같이 닫는다 */
document.addEventListener('scroll',()=>{ if(cpMenuFor)cpCloseMenu() },true);

/* 대화 하나를 지운다. 지운 것이 보고 있던 대화면 다음 대화로 옮겨 간다.
   목록이 비면 빈 화면(예시 질문)으로 돌아간다. (2026-09-13) */
export function cpDeleteConvo(id){
  const s=cpStore();
  const at=s.convos.findIndex(c=>c.id===id);
  if(at<0)return;
  /* 답변을 만드는 중인 대화를 지우면 그 응답부터 멈춘다 */
  if(cpActiveRun&&cpActiveRun.c&&cpActiveRun.c.id===id)cpStop();
  const gone=s.convos[at];
  for(let i=cpQueue.length-1;i>=0;i--) if(cpQueue[i].c===gone)cpQueue.splice(i,1);
  cpQueuePaint();
  if(AUTH.in&&gone&&gone.key)chatDelete({mode:cpModeOf(gone),key:gone.key});
  s.convos.splice(at,1);
  if(s.activeId===id)s.activeId=s.convos.length?s.convos[Math.min(at,s.convos.length-1)].id:null;
  cpCloseMenu();
  cpRenderList(); cpRenderThread(); cpSave();
}
/* 대화 목록 제목을 그 자리에서 고친다.
   span 을 input 으로 바꿔치고, Enter 로 저장 · Esc 로 되돌린다.
   저장할 때 앞뒤 공백과 중복 공백을 정리한다 — 빈 제목이면 "새 대화" 로 보인다. */
export function cpEditTitle(id){
  const row=document.querySelector('.cpItem[data-cid="'+id+'"]'); if(!row)return;
  if(row.querySelector('.cpTitleIn'))return;
  const s=cpStore();
  const c=s.convos.find(x=>x.id===id); if(!c)return;
  const span=row.querySelector('span'); if(!span)return;
  const input=document.createElement('input');
  input.type='text'; input.className='cpTitleIn'; input.maxLength=60;
  input.value=c.title||'';
  span.replaceWith(input);
  input.focus(); input.select();
  let done=false;
  const commit=(save)=>{
    if(done)return; done=true;
    if(save){
      const next=input.value.replace(/\s+/g,' ').trim();
      if(next!==(c.title||'')&&AUTH.in&&c.sid)chatUpdate({mode:cpModeOf(c),key:c.key,title:next});
      c.title=next;
    }
    cpRenderList(); cpSave();
  };
  input.addEventListener('keydown',e=>{
    if(e.key==='Enter'){ e.preventDefault(); commit(true) }
    else if(e.key==='Escape'){ e.preventDefault(); commit(false) }
  });
  input.addEventListener('blur',()=>commit(true));
}
/* AI 말풍선 한 줄 — 별 아이콘 + FEEDiT. 답을 기다리는 동안(pending)엔
   말풍선 대신 이 헤더만 돌고 옅어졌다 밝아지며 "생각 중"을 표현한다 */
/* ── 답변 피드백 (2026-09-13) ──────────────────────────
   틀린 답을 봐도 알릴 곳이 없었다. 한 줄로 묻고, '아쉬움' 이면 사유를 고르게 한다.
   사유는 실제로 자주 나는 실패 네 가지다 — 무엇을 고쳐야 하는지가 바로 읽힌다. */
const CP_FB_REASONS=['사실이 틀렸어요','엉뚱한 걸 답했어요','자료가 부족해요','원하는 내용이 아니에요'];
/* 첫 두 답은 흐름을 끊지 않는다. 세 번째에 한 번 묻고 그 뒤로는 다섯 답마다
   한 번만 묻는다(3, 8, 13…). 랜덤이면 다시 그릴 때 질문이 생겼다 사라지므로
   답변 순번으로 결정한다. */
export function cpFeedbackSample(ordinal){
  const n=Number(ordinal)||0;
  return n>=3 && (n-3)%5===0;
}
function cpFeedbackEligible(m){
  return !!(m&&m.role==='ai'&&!m.pending&&m.turn&&(m.html||m.cardHtml));
}
function cpScheduleFeedback(current){
  if(!cpFeedbackEligible(current)||current.feedbackPrompt!==undefined)return false;
  let prior=0;
  for(const mode of ['general','salmal']) for(const c of CP_STORE[mode].convos||[]){
    for(const m of c.messages||[]) if(m!==current&&cpFeedbackEligible(m))prior++;
  }
  current.feedbackPrompt=cpFeedbackSample(prior+1);
  return current.feedbackPrompt;
}
function cpFeedbackHTML(m,idx){
  if(!m||m.pending)return '';
  if(!m.html&&!m.cardHtml&&!m.key)return '';
  if(m.feedback==='up')return '<div class="cpFb done">의견 고맙습니다.</div>';
  if(m.feedback==='down')return '<div class="cpFb done">알려 주셔서 고맙습니다. 답변 품질을 고치는 데 씁니다.</div>';
  if(!m.feedbackPrompt)return '';
  if(m.fbOpen){
    return '<div class="cpFb open"><span>무엇이 아쉬웠나요?</span>'+
      CP_FB_REASONS.map(r=>'<button type="button" data-fb-reason="'+idx+'" data-reason="'+cpEsc(r)+'">'+
        cpEsc(r)+'</button>').join('')+
      '<button type="button" class="cpFbSkip" data-fb-close="'+idx+'">닫기</button></div>';
  }
  return '<div class="cpFb"><span>이 답변이 도움이 되었나요?</span>'+
    '<button type="button" data-fb="up" data-fb-idx="'+idx+'">도움됨</button>'+
    '<button type="button" data-fb="down" data-fb-idx="'+idx+'">아쉬움</button></div>';
}
/* 살말 모드에서 즐겨입는 스타일이 비어 있으면 판단의 가장 무거운 축(취향 35%)이
   통째로 빠진다. 마이페이지까지 가야 고를 수 있던 것을, 여기서 바로 고르게 한다. */
function cpTastePaint(){
  const box=$('#cpTaste'); if(!box)return;
  const need=SM_ON&&AUTH.in&&ME.styles&&ME.styles.size===0;
  box.hidden=!need;
  if(need&&!box.dataset.built){
    box.dataset.built='1';
    box.innerHTML='<span>즐겨입는 스타일을 고르면 살말 판단이 정확해집니다 '+
      '(취향이 판단의 35%입니다).</span>'+
      '<button type="button" id="cpTasteBtn">스타일 고르기</button>';
    box.addEventListener('click',e=>{
      if(e.target.closest('#cpTasteBtn'))openStyleSelect();
    });
  }
}
/* 빈 화면 — 무엇을 물어야 할지 알려 준다. 모드 차이와 전환 단축키도 여기서 한 번
   보여 준다. 예시는 홈 챗바가 돌리는 것과 같은 목록을 쓴다. */
function cpEmptyPaint(){
  const box=$('#cpEmpty'); if(!box)return;
  const p=CP_PROFILE[cpMode()];
  const set=(SM_ON?SM_QUESTIONS:M_QUESTIONS).slice(0,4);
  box.innerHTML='<p id="cpEmptyText">'+cpEsc(p.empty)+'</p>'+
    '<div class="cpEmptyChips">'+set.map(q=>{
      const text=q[0]+' '+q[1];
      return '<button type="button" data-ask="'+cpEsc(text)+'">'+
        '<b>'+cpEsc(q[0])+'</b> '+cpEsc(q[1])+'</button>';
    }).join('')+'</div>'+
    '<p class="cpEmptyHint">'+(SM_ON
      ? '살!말? 모드는 <b>살지 말지</b>를 판단합니다. 트렌드 흐름이 궁금하면'
      : '일반 모드는 <b>트렌드 흐름</b>을 알려드립니다. 살지 말지 고민이라면')+
    ' <b>Tab</b> 키로 모드를 바꾸세요.</p>';
}

document.addEventListener('feedit:styles',()=>cpTastePaint());

function cpWhoHTML(stage){
  /* ★ stage — 서버가 도구를 부를 때마다 보내는 한 줄("온도 보는 중").
     기다리는 동안 무엇을 보고 있는지 알면 같은 시간도 기다림이 된다. */
  return '<div class="who"><i class="cpStar">✧</i>FEEDiT' +
         '<span class="cpStage">' + (stage ? cpEsc(stage) : '') + '</span></div>';
}
/* 착장 칸 (2026-09-14: 모자·벨트·안경 추가).
   ★ 서버 vton.SLOT_ORDER 와 같은 순서·같은 이름이어야 한다 — 한쪽만 늘리면
     화면의 드롭다운과 서버가 아는 칸이 어긋난다. */
const VF_CATEGORIES=['상의','하의','아우터','원피스(셋업)','신발','양말','모자','벨트','안경'];
const VF_AUTO='자동 분류';
/* 칸을 몇 개까지 열 수 있나 — 서버 vton.MAX_ITEMS 와 같아야 한다. */
const VF_MAX=VF_CATEGORIES.length;
/* 생성 엔진 (2026-10-01) — 서버 vton.ENGINES 와 같은 이름.
   기본은 화질 쪽(Sunburst). 빨리 보고 싶으면 Flare 를 고른다. */
const VF_ENGINES=[
  {v:'sunburst',label:'고화질',name:'SUNBURST',title:'GPT Image 2.5 Sunburst — 화질 우선'},
  {v:'flare',   label:'빠르게',name:'FLARE',   title:'GPT Image 2.5 Flare — 속도 우선'},
];
const VF_DEFAULT_ENGINE='sunburst';
const cpFitEngineOf=(f)=>VF_ENGINES.some(e=>e.v===(f&&f.engine))?f.engine:VF_DEFAULT_ENGINE;
/* 착장 옵션 — 서버로는 예전처럼 **켠 이름만 true** 로 보낸다(vton.OPTION_LINES).
   화면에서 묶는 방법만 바뀌었다 (2026-10-01):
     · 아우터 · 상의 — 버튼 하나. 기본 Open(열어 입기), 누르면 Close(여며 입기).
       여밈이 없는 옷(티셔츠·니트)은 서버 문장이 '그대로 두라' 고 말하고,
       그 칸의 옷이 없으면 문장 자체가 빠진다(vton.SLOT_OF).
     · 핏 — 세 칸. 기본 정핏. 정핏은 문장을 붙이지 않는다(상품 핏 그대로).
     · 레이어드 — 켜고 끈다(아우터 둘을 겹쳐 입기). */
const VF_OPTIONS=['outer_layered','outer_open','outer_closed','top_open','top_closed','fit_over','fit_slim'];
const VF_OPTION_GROUPS=[
  {kind:'switch',key:'outer_layered',title:'레이어드'},
  {kind:'slide',key:'outer',title:'아우터',def:'open',
   cells:[{v:'open',label:'Open',opt:'outer_open'},{v:'closed',label:'Close',opt:'outer_closed'}]},
  {kind:'slide',key:'top',title:'상의',def:'open',
   cells:[{v:'open',label:'Open',opt:'top_open'},{v:'closed',label:'Close',opt:'top_closed'}]},
  {kind:'slide',key:'fit',title:'핏',def:'regular',
   cells:[{v:'over',label:'오버핏',opt:'fit_over'},{v:'regular',label:'정핏',opt:''},{v:'slim',label:'슬림핏',opt:'fit_slim'}]},
];
/* 슬라이드 묶음의 지금 값 — 켜진 이름이 있는 칸, 없으면 기본 칸 */
function cpSlideValue(on,g){
  const hit=g.cells.find(c=>c.opt&&on&&on[c.opt]);
  return hit?hit.v:g.def;
}
/* 슬라이드 값을 켠 이름들로 되돌려 적는다 — 고른 칸의 이름만 true */
function cpSlideSet(on,g,value){
  g.cells.forEach(c=>{ if(c.opt)on[c.opt]=(c.v===value) });
}
/* ── 그림 (2026-10-01, 시안 C) ─────────────────────────────
   선 하나짜리 24px 그림. 색은 글자색(currentColor)을 따른다. */
const VF_SVG=(d,size)=>'<svg width="'+(size||20)+'" height="'+(size||20)+'" viewBox="0 0 24 24" fill="none" '+
  'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+d+'</svg>';
/* 칸 종류마다 그림 하나 — 칸 오른쪽 아래 배지와 종류 고르기 판에 같이 쓴다.
   ★ 이름은 VF_CATEGORIES · VF_AUTO 와 같아야 한다. 없는 이름은 Auto 그림으로 떨어진다. */
const VF_KIND_ICON={
  [VF_AUTO]:'<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8"/><path d="M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8"/><path d="M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16"/><path d="M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><path d="M12 8.5l1 2.5 2.5 1-2.5 1-1 2.5-1-2.5-2.5-1 2.5-1z"/>',
  '아우터':'<path d="M8.5 4 4.5 6.2 3 13l2.4.5L6 20h12l.6-6.5L21 13l-1.5-6.8L15.5 4 12 8.5 8.5 4z"/><path d="M12 8.5V20"/>',
  '상의':'<path d="M8 4 4 6l1.5 4L7 9.5V20h10V9.5l1.5.5L20 6l-4-2c-.5 1.5-2 2.5-4 2.5S8.5 5.5 8 4z"/>',
  '하의':'<path d="M7 3h10l1 18h-4.5L12 9l-1.5 12H6L7 3z"/><path d="M7 6.5h10"/>',
  '원피스(셋업)':'<path d="M9.5 3h5l-1 4.5L18 20H6l4.5-12.5z"/><path d="M10.5 7.5h3"/>',
  '신발':'<path d="M3 17v-5l5-.5 3-4 3.5 3.5L21 13v4z"/><path d="M3 17h18v1.5H3z"/>',
  '양말':'<path d="M9 3h6v9.5l3.2 3.2a2.6 2.6 0 0 1-3.7 3.7L9 13.9z"/><path d="M9 6.5h6"/>',
  '모자':'<path d="M4.5 15a7.5 7.5 0 0 1 15 0"/><path d="M3 15h13.5l4.5 2"/><path d="M12 7.5V6"/>',
  '벨트':'<rect x="2.5" y="9.5" width="19" height="5" rx="1"/><rect x="9" y="8" width="6" height="8" rx="1.2"/><path d="M12 12h2"/>',
  '안경':'<circle cx="7" cy="14" r="3.5"/><circle cx="17" cy="14" r="3.5"/><path d="M10.5 14h3"/><path d="M3.6 13 5 8.5"/><path d="M20.4 13 19 8.5"/>',
};
/* 종류 고르기 판의 순서 — Auto 를 맨 앞에. 화면 이름은 Auto, 서버로는 '자동 분류'. */
const VF_KINDS=[VF_AUTO,'아우터','상의','하의','원피스(셋업)','신발','양말','모자','벨트','안경'];
const vfKindName=(k)=>k===VF_AUTO?'Auto':k;
const vfKindIcon=(k,size)=>VF_SVG(VF_KIND_ICON[k]||VF_KIND_ICON[VF_AUTO],size);
const VF_IC={
  plus:'<path d="M12 5v14"/><path d="M5 12h14"/>',
  chevron:'<path d="M6 9l6 6 6-6"/>',
  close:'<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',
  warn:'<path d="M12 3.5 2.5 20h19L12 3.5z"/><path d="M12 10v4.5"/><path d="M12 17.2v.1"/>',
  sideOpen:'<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M9.5 4.5v15"/><path d="M16 10l-2 2 2 2"/>',
  sideClosed:'<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M9.5 4.5v15"/><path d="M14 10l2 2-2 2"/>',
  outerOpen:'<path d="M8.5 4 4.5 6.2 3 13l2.4.5L6 20h4.5V9.2L8.5 4z"/><path d="M15.5 4l4 2.2L21 13l-2.4.5L18 20h-4.5V9.2L15.5 4z"/><path d="M10.5 9.2 12 11l1.5-1.8"/>',
  outerClosed:'<path d="M8.5 4 4.5 6.2 3 13l2.4.5L6 20h12l.6-6.5L21 13l-1.5-6.8L15.5 4 12 8.5 8.5 4z"/><path d="M12 8.5V20"/>',
  topOpen:'<path d="M9 3.5 5 5.5 3.5 10.5l2.6.9L7 20h4.2V8.8L9 3.5z"/><path d="M15 3.5l4 2 1.5 5-2.6.9L17 20h-4.2V8.8L15 3.5z"/>',
  topClosed:'<path d="M9 3.5 5 5.5 3.5 10.5l2.6.9L7 20h10l.9-8.6 2.6-.9L19 5.5l-4-2-3 3.2-3-3.2z"/><path d="M12 6.7V20"/>',
  over:'<path d="M7 4 2.5 7l1.6 4.2L6 10.4V20.5h12V10.4l1.9.8L21.5 7 17 4c-.6 1.6-2.4 2.6-5 2.6S7.6 5.6 7 4z"/>',
  regular:'<path d="M8 4 4 6l1.5 4L7 9.5V20h10V9.5l1.5.5L20 6l-4-2c-.5 1.5-2 2.5-4 2.5S8.5 5.5 8 4z"/>',
  slim:'<path d="M9 4 5.5 5.8l1.3 3.6 1.5-.5V20h7.4V8.9l1.5.5 1.3-3.6L15 4c-.4 1.4-1.6 2.3-3 2.3S9.4 5.4 9 4z"/>',
  layers:'<path d="M12 3 3 8l9 5 9-5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  sunburst:'<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z"/>',
  flare:'<path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2z"/>',
  arrow:'<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
};
/* 내 말풍선 아래 아이콘 줄에 쓰는 그림 (2026-09-14).
   글자 버튼('다시 묻기') 하나로는 되돌리기밖에 못 했다 — 같은 질문을 그대로
   다시 보내거나 문장만 복사할 방법이 없었다. */
const CP_SVG=(d)=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '+
  'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+d+'</svg>';
const CP_IC_RESEND=CP_SVG('<path d="M3.5 9.5h10a5.5 5.5 0 1 1 0 11H8"/><polyline points="7.5 5.5 3.5 9.5 7.5 13.5"/>');
const CP_IC_EDIT=CP_SVG('<path d="M4.5 19.5h4L19.6 8.4a2.05 2.05 0 0 0-2.9-2.9L5.5 16.6z"/><path d="M15.2 7l2.8 2.8"/>');
const CP_IC_COPY=CP_SVG('<rect x="9.5" y="9.5" width="10.5" height="10.5" rx="2.2"/><path d="M5.5 14.5V6a2 2 0 0 1 2-2h7"/>');
const CP_IC_DOWN=CP_SVG('<path d="M12 4v11"/><polyline points="7.5 10.5 12 15 16.5 10.5"/><path d="M5 19.5h14"/>');
/* 회원정보의 성별 — 챗봇에는 이것만 보낸다. 질문 글자로 성별을 정하지 않는다:
   "여자친구랑 데이트할 때 뭐 입지?" 는 남자가 입을 옷이다. 다른 사람이 입을 옷이라고
   분명히 말했는지는 챗봇(propose_fit 의 wearer)이 문장 전체를 보고 정한다. */
function cpMyGender(){
  return AUTH.in&&(ME.gender==='FEMALE'||ME.gender==='MALE')?ME.gender:'';
}
/* 사진을 직접 올린 입혀보기의 첫 모델. "남자 모델로" 처럼 입을 사람을 말했으면 그쪽,
   아니면 회원정보. 여자친구·남자친구(여친·남친)는 데이트 상대라 입을 사람이 아니다 —
   먼저 지운다. 틀리면 위젯에서 바로 바꿀 수 있다. */
function cpFitGender(text){
  const asked=String(text||'').replace(/(여자|남자)\s*친구|여친|남친/g,' ');
  if(/(여자|여성|우먼|\bfemale\b)/i.test(asked)) return 'FEMALE';
  if(/(남자|남성|맨즈|\bmale\b)/i.test(asked)) return 'MALE';
  return cpMyGender();
}
function cpFitModel(text){
  return cpFitGender(text)==='MALE'?'man':'woman';
}
function cpNewFit(images,text){
  const attached=(images||[]).slice(0,VF_MAX);
  /* 칸은 넣은 사진 수만큼만 연다 (2026-09-14). 예전엔 아홉 칸이 늘 펼쳐져 있어,
     한 장만 올려도 빈 상자 여덟 개를 지나 스크롤해야 했다. 모자란 칸은
     ＋ 로 한 칸씩 늘린다. */
  const rows=(attached.length?attached:['']).map(image=>
    ({category:VF_CATEGORIES[0],image:image||'',auto:true}));
  return {key:String(Date.now()),v:2,items:rows,
    model:cpFitModel(text),status:'',result:'',loading:false,
    /* 옵션은 전부 꺼진 채로 시작한다 — 끈 상태가 예전 동작이다. 켜지 않은
       연출이 프롬프트에 실리면 사용자가 고르지 않은 사진이 나온다. */
    options:cpFitOptions(null),
    /* 왼쪽 설정 칸 펼침(open)·접힘(closed), 종류 고르기 판을 연 칸(-1 = 닫힘).
       화면 상태라 서버로는 보내지 않는다 (2026-10-01, 시안 C). */
    side:'open',kindOpen:-1,
    /* 붙인 사진이 있으면 곧바로 종류를 확인한다(cpFitAutoSort). 그 전까지는
       예전처럼 순서대로 놓아 둔다 — 기다리는 동안 빈 화면을 보여주지 않는다. */
    sorting:attached.length>0};
}
/* ★ 서버가 고른 코디로 착장 칸을 채운다 (2026-09-22).
   sorting 을 켜지 않는다 — 칸은 이미 DB 태그로 정해졌고(propose_fit), 사진은
   서버가 build_fit 에서 한 번 봤다. 여기서 또 분류하면 vision 을 두 번 쓰고,
   '아우터' 로 넣은 트랙 재킷이 '상의' 로 바뀌어 레이어드 조건이 깨진다.
   모델이 정한 연출은 결과 아래 독에 늘 보인다(2026-10-01) — 예전 서랍처럼 펴 둘
   필요가 없다. 사용자가 그 자리에서 보고 끌 수 있다. */
export function cpFitFromServer(fit,text){
  const f=cpNewFit([],text||'');
  if(fit&&fit.gender==='MALE') f.model='man';
  else if(fit&&fit.gender==='FEMALE') f.model='woman';
  const rows=(fit&&Array.isArray(fit.items)?fit.items:[]).slice(0,VF_MAX)
    .filter(it=>it&&(it.image||it.image_url))
    .map(it=>({category:VF_CATEGORIES.includes(it.slot)?it.slot:VF_CATEGORIES[0],
               /* 사진은 주소로 보낸다 — 서버가 받아 온다(vton.fetch_as_data_url).
                  브라우저가 CDN 을 직접 fetch 하면 CORS 로 막힌다. */
               image:'', imageUrl:String(it.image||it.image_url||''),
               name:String(it.name||''), brand:String(it.brand||''),
               source:String(it.source||''), sourceLabel:String(it.source_label||''),
               url:cpShopUrl(it.url), auto:false}));
  if(rows.length)f.items=rows;
  f.options=cpFitOptions((fit&&fit.options||[]).reduce((o,k)=>(o[k]=true,o),{}));
  f.sorting=false;
  f.fromServer=true;
  /* 입을 상황과 근거 코디 기사 — '다른 룩' 이 같은 상황을 잇고 같은 기사를 피한다 */
  f.occasion=String(fit&&fit.occasion||'').slice(0,40);
  f.styles=(fit&&Array.isArray(fit.styles)?fit.styles:[]).map(x=>String(x||'').slice(0,20)).filter(Boolean).slice(0,4);
  const ref=fit&&fit.ref; f.ref=(ref&&cpShopUrl(ref.url))
    ?{title:String(ref.title||'').slice(0,80),who:String(ref.who||'').slice(0,40),
      url:cpShopUrl(ref.url),domain:String(ref.domain||'').slice(0,60)}:null;
  return f;
}
/* 승인 카드가 넘긴 코디를 한 줄로 적는다 — 새 대화에는 앞 대화의 근거가 없다.
   왜 이 조합인지(why)와 무엇으로 골랐는지(styles)가 없으면, 사용자는 살!말? 로
   넘어온 뒤 방금 받은 추천과 이 코디가 같은 것인지 알 수 없다. */
function cpFitWhyHTML(fit){
  const styles=(fit&&fit.styles||[]).filter(Boolean).join(' · ');
  const why=String((fit&&fit.why)||'').trim();
  const names=(fit&&fit.items||[]).map(it=>String(it&&it.name||'').trim()).filter(Boolean);
  const out=[];
  out.push('<p>'+cpEsc(styles?styles+' 코디로 골랐습니다.':'고른 코디입니다.')+
           (why?' '+cpEsc(why):'')+'</p>');
  if(names.length)out.push('<p>'+cpEsc(names.join(' + '))+'</p>');
  if(fit&&fit.ref)out.push(cpFitRefHTML(fit.ref));
  const dropped=(fit&&fit.dropped||[]).filter(Boolean);
  if(dropped.length)out.push('<p>'+cpEsc(dropped.join(' '))+'</p>');
  return out.join('');
}
/* ★ 첨부 사진을 알맞은 칸으로 옮긴다 (2026-09-13).
   스커트를 올렸는데 '상의' 칸이 차 버려서, 상의를 넣으려면 사용자가 지우고 다시
   넣어야 했다. 어떤 옷인지는 사진을 볼 수 있는 서버만 안다 — 물어보고 옮긴다.
   같은 칸이 겹치면 뒤엣것은 빈 칸으로 흘려보내고, 판별을 못 한 사진은 예전처럼
   남은 칸에 순서대로 놓는다. 실패해도 화면은 그대로다(칸만 안 바뀐다). */
function cpFitAutoSort(m){
  const f=m&&m.fit; if(!f||!f.sorting)return Promise.resolve();
  /* 생성 버튼이 분류를 기다릴 수 있게 약속을 남겨 둔다 — 분류 도중에 만들면
     칸이 바뀌기 전 순서로 프롬프트가 나간다. */
  f._sort=cpFitSortNow(m,f);
  return f._sort;
}
async function cpFitSortNow(m,f){
  /* ★ 칸이 가변이 된 뒤로는 사진을 옮기지 않는다 (2026-09-14) — 사진은 사용자가
     넣은 칸에 그대로 두고, 그 칸의 종류만 판별한 이름으로 바꿔 단다. 옮기던
     시절엔 같은 종류 둘(아우터 두 벌)이 들어오면 뒤엣것이 엉뚱한 칸으로
     흘러갔다. 이제는 같은 종류가 몇 칸이든 그대로 남는다. */
  const rows=cpFitItems(f).filter(item=>item.image);
  if(!rows.length){ f.sorting=false; return }
  let cats=[];
  try{ cats=await classifyFitImages(rows.map(item=>item.image)); }catch(e){ cats=[] }
  f.sorting=false;
  rows.forEach((item,i)=>{
    const name=String(cats[i]||'');
    /* 판별 못 한 사진은 '자동 분류'로 남긴다 — 서버가 다시 본다 */
    if(VF_CATEGORIES.includes(name)){ item.category=name; item.auto=false }
  });
  if(cpActiveConvo()&&cpActiveConvo().messages.includes(m))cpFitRender(m);
}
/* 칸 목록을 항상 같은 길이·같은 모양으로 되돌린다.
   ★ 같은 축이 둘 있어도 막지 않는다 (2026-09-14). 아우터 두 벌을 겹쳐 입히려면
     '아우터' 칸이 둘 필요하다 — 축마다 하나씩으로 강제하면 레이어드를 만들 수
     없다. 칸 수(=VF_CATEGORIES.length)만 서버 MAX_ITEMS 와 맞춰 둔다. */
function cpFitItems(f){
  let rows=(Array.isArray(f.items)?f.items:[]).slice(0,VF_MAX).map(r=>{
    const row=(r&&typeof r==='object')?r:{};
    return {category:VF_CATEGORIES.includes(row.category)?row.category:VF_CATEGORIES[0],
            image:String(row.image||''),
            /* 서버가 고른 상품 사진의 주소. 사용자가 올린 사진에는 없다. */
            imageUrl:String(row.imageUrl||''),
            name:String(row.name||''),
            brand:String(row.brand||''), source:String(row.source||''),
            sourceLabel:String(row.sourceLabel||''), url:cpShopUrl(row.url),
            /* 예전 자료에는 auto 가 없다 — 없으면 '자동 분류'로 본다 */
            auto:row.auto===undefined?!row.category:Boolean(row.auto)};
  });
  /* 아홉 칸이 늘 펼쳐져 있던 시절에 저장된 대화 — 빈 칸을 한 번만 걷어낸다.
     매번 걷어내면 사용자가 방금 ＋ 로 연 빈 칸까지 사라진다. */
  if(f.v!==2){
    if(!rows.length&&f.image)rows=[{category:VF_CATEGORIES[0],image:f.image,auto:true}];
    rows=rows.filter(r=>r.image);
    f.v=2;
  }
  if(!rows.length)rows=[{category:VF_CATEGORIES[0],image:'',auto:true}];
  f.items=rows;
  return f.items;
}
/* 옵션 상태 — 모르는 이름은 버리고 없는 것은 false 로 채운다.
   ★ 슬라이드 묶음은 늘 한 칸이 골라져 있다 (2026-10-01). 아무것도 없던 옛 대화·서버
     제안은 기본 칸(열어 입기 · 정핏)으로 채운다. 서버가 top_closed 를 골라 왔으면
     상의는 '여며 입기' 로 선다. */
function cpFitOptions(saved){
  const out={};
  VF_OPTIONS.forEach(k=>{ out[k]=Boolean(saved&&saved[k]) });
  VF_OPTION_GROUPS.forEach(g=>{ if(g.kind==='slide')cpSlideSet(out,g,cpSlideValue(out,g)) });
  return out;
}
function cpFitOptionsOf(f){
  if(!f.options)f.options=cpFitOptions(null);
  return f.options;
}
/* ── 칸 목록 높이 (2026-09-14) ────────────────────────
   칸을 늘릴 때마다 왼쪽 설정 칸이 길어졌고, .cpFitGrid 가 align-items:stretch 라
   오른쪽 결과 칸까지 덩달아 늘어났다 — 아직 아무것도 없는 검은 칸만 길어지는
   셈이었다. 두 줄까지만 자리를 잡고 나머지는 목록 안에서 스크롤하게 한다.
   ★ 왜 CSS 가 아니라 여기서 재나 —
     타일이 정사각형(aspect-ratio:1)이라 한 줄 높이가 폭에 따라 정해진다.
     CSS 의 max-height 에서 % 는 '부모의 높이' 기준이라 폭에서 높이를 끌어올
     방법이 없다. 한 줄을 실제로 재서 두 줄치를 얹는 편이 정확하다.
   ★ 셋째 줄을 조금 비쳐 둔다 — 딱 두 줄에서 자르면 아래 더 있다는 것이
     보이지 않아, 칸을 늘려 놓고도 못 찾는다. */
const CP_FIT_ROWS=2, CP_FIT_PEEK=18;
export function cpFitSizeItems(root){
  const scope=root||document;
  scope.querySelectorAll('.cpFitItems').forEach(box=>{
    const slot=box.querySelector('.cpFitSlot:not(.addSlot)');
    const h=slot?slot.offsetHeight:0;
    /* 레이아웃이 없는 환경(jsdom)이나 아직 안 그려진 동안엔 손대지 않는다 —
       0 을 그대로 쓰면 칸이 통째로 접힌다. */
    if(!h){ box.style.maxHeight=''; return }
    const gap=parseFloat(getComputedStyle(box).rowGap)||10;
    box.style.maxHeight=(h*CP_FIT_ROWS+gap*(CP_FIT_ROWS-1)+CP_FIT_PEEK)+'px';
  });
}
/* 창 폭이 바뀌면 타일도 같이 커지고 작아진다 — 다시 잰다 */
window.addEventListener('resize',()=>cpFitSizeItems());
/* 저장 파일 확장자 — 서버가 무엇으로 만들어 보냈는지를 따른다 (2026-09-14).
   4K 로 올리면서 결과를 webp 로 받게 됐는데(vton.OUTPUT_FORMAT), 여기만 .png 로
   박혀 있어 내려받은 파일이 이름과 속이 다른 채로 저장됐다. 서버가 format 을
   안 보내던 옛 대화도 있으니 data URL 에서 직접 읽고, 그것도 없으면 png 로 둔다. */
/* 결과 사진의 가로:세로 — 태그 점을 사진 위 비율 그대로 찍으려면 감싸는 틀이 사진과
   같은 비율이어야 한다. 서버가 준 size(예: 2480x3312), 없으면 3/4. */
function cpFitRatio(f){
  const hit=/^(\d+)x(\d+)$/.exec(String(f&&f.size||''));
  return hit?hit[1]+' / '+hit[2]:'3 / 4';
}
function cpFitExt(f){
  const named=String(f&&f.format||'').toLowerCase();
  if(named==='webp'||named==='jpeg'||named==='png')return named==='jpeg'?'jpg':named;
  const hit=/^data:image\/([a-z]+);/i.exec(String(f&&f.result||''));
  const mime=hit?hit[1].toLowerCase():'';
  if(mime==='webp')return 'webp';
  if(mime==='jpeg'||mime==='jpg')return 'jpg';
  return 'png';
}
/* ── 착장 위젯 (2026-10-01, 시안 C · 결과 아래 독) ──────────────
   한눈에 들어오게 작게 — 왼쪽은 접히는 설정 칸(모델 · 옷), 오른쪽은 결과와
   그 아래 독(아우터 · 상의 Open/Close, 핏, 레이어드, 엔진, 입혀보기).
   ★ 독은 결과 사진 위에 얹지 않는다. 사진 아래 따로 선다 — 고르는 동안 정작
     봐야 할 결과가 가려지지 않게.
   ★ 왼쪽을 접으면 모델 · 옷이 작은 네모로 줄고(.cpFitMini), 결과 칸이 그만큼 넓어진다.
   ★ 옷 칸 종류는 칸 아래 이름을 눌러 고른다. 판은 칸 목록 위에 덮어 펼친다 —
     스크롤하는 목록 안에 드롭다운을 두면 아래가 잘린다. */
const VF_FIT_NAME={over:'오버핏',regular:'정핏',slim:'슬림핏'};
const VF_MODELS=[{v:'woman',label:'Female',img:'/assets/vton-models/woman.png'},
                 {v:'man',  label:'Male',  img:'/assets/vton-models/man.png'}];
function cpFitDockHTML(f){
  const on=cpFitOptionsOf(f), engine=cpFitEngineOf(f);
  const sep='<span class="cpDockSep" aria-hidden="true"></span>';
  /* 아우터 · 상의 — 버튼 하나로 Open ↔ Close. 그림도 같이 바뀐다. */
  const flip=(key,title)=>{
    const g=VF_OPTION_GROUPS.find(x=>x.key===key);
    const open=cpSlideValue(on,g)==='open';
    return '<button type="button" class="cpDockBtn cpDockFlip" data-vf-flip="'+key+'" '+
      'aria-label="'+title+' '+(open?'열어 입기':'여며 입기')+' — 눌러서 바꾸기">'+
      VF_SVG(VF_IC[key+(open?'Open':'Closed')],20)+
      '<span>'+title+' <b>'+(open?'Open':'Close')+'</b></span></button>';
  };
  const fitG=VF_OPTION_GROUPS.find(x=>x.key==='fit'), fit=cpSlideValue(on,fitG);
  const fits='<div class="cpDockFit"><div class="cpDockFitRow" role="radiogroup" aria-label="핏">'+
    fitG.cells.map(c=>'<button type="button" role="radio" class="cpDockMini'+(c.v===fit?' on':'')+'" '+
      'data-vf-slide="fit" data-vf-val="'+c.v+'" aria-checked="'+(c.v===fit)+'" aria-label="'+cpEsc(c.label)+'">'+
      VF_SVG(VF_IC[c.v],19)+'</button>').join('')+
    '</div><span>핏 · '+cpEsc(VF_FIT_NAME[fit]||'정핏')+'</span></div>';
  const layered=Boolean(on.outer_layered);
  const layer='<button type="button" role="switch" class="cpDockBtn cpDockLayer'+(layered?' on':'')+'" '+
    'data-vf-opt="outer_layered" aria-checked="'+layered+'" aria-label="레이어드 — 아우터 둘을 겹쳐 입기">'+
    VF_SVG(VF_IC.layers,20)+'<span>레이어드 <b>'+(layered?'On':'Off')+'</b></span></button>';
  const engines='<div class="cpDockEngine" role="radiogroup" aria-label="생성 방식">'+
    VF_ENGINES.map(e=>'<button type="button" role="radio" class="cpDockEng'+(e.v===engine?' on':'')+'" '+
      'data-vf-slide="engine" data-vf-val="'+e.v+'" aria-checked="'+(e.v===engine)+'" title="'+cpEsc(e.title)+'"'+
      (f.loading?' disabled':'')+'>'+VF_SVG(VF_IC[e.v],17)+'<span>'+cpEsc(e.label)+'</span></button>').join('')+
    '</div>';
  const go='<button type="button" class="cpDockGo" data-vf-generate'+(f.loading?' disabled':'')+'>'+
    '<span>'+(f.loading?'만드는 중':'입혀보기')+'</span>'+VF_SVG(VF_IC.arrow,15)+'</button>';
  return '<div class="cpFitDockWrap"><div class="cpFitDock">'+
    '<div class="cpDockGroup">'+flip('outer','아우터')+flip('top','상의')+'</div>'+sep+
    '<div class="cpDockGroup">'+fits+'</div>'+sep+
    '<div class="cpDockGroup">'+layer+'</div>'+sep+
    '<div class="cpDockGroup">'+engines+'</div>'+go+'</div></div>';
}
/* ── 상품 출처 (2026-10-02) ──────────────────────────────────
   ① 칸 사진 위 판매처 배지 · ② 위젯 아래 '코디 상품' 줄 · ③ 결과 사진 위 쇼핑 태그.
   출처가 있는 상품(서버가 고른 추천 상품)만 다룬다. 사용자가 직접 올린 사진에는 판매처가
   없다 — 지어내지 않고 줄 · 태그에서 뺀다. */
function cpFitSourceName(item){ return String(item&&(item.sourceLabel||item.source)||'').trim(); }
function cpFitIsShop(item){ return Boolean(item&&(item.image||item.imageUrl)&&(item.url||cpFitSourceName(item))); }
function cpFitShopLabel(item){
  return cpEsc(item.name||'상품')+' · '+cpEsc(cpFitSourceName(item)||'판매처')+'에서 상품 보기';
}
/* ② 코디 상품 줄 — 인스타 'Shop the look' 처럼 한 줄에 상품 카드. 카드를 누르면 판매처로.
   ★ 상품 사진은 referrer 없이 부른다 (2026-10-02). 크림 사진(네이버 pstatic)은 다른 사이트에서
     온 요청을 막아 카드 사진이 빈 칸으로 떴다. 칸 사진 · 태그 카드도 같다. */
function cpFitLookHTML(f,items){
  const rows=items.map((item,i)=>({item,i})).filter(r=>cpFitIsShop(r.item));
  if(!rows.length)return '';
  const cards=rows.map(({item,i})=>{
    const src=item.image||item.imageUrl, source=cpFitSourceName(item);
    const body='<span class="cpFitLookImg"><img src="'+cpEsc(src)+'" alt="" loading="lazy" referrerpolicy="no-referrer"></span>'+
      '<span class="cpFitLookText">'+
        '<small>'+cpEsc(item.brand||vfKindName(item.auto?VF_AUTO:item.category))+'</small>'+
        '<b>'+cpEsc(item.name||vfKindName(item.auto?VF_AUTO:item.category))+'</b>'+
        (source?'<em>'+cpEsc(source)+(item.url?' ↗':'')+'</em>':'')+
      '</span>';
    return item.url
      ?'<a class="cpFitLookCard" data-vf-look="'+i+'" href="'+cpEsc(item.url)+'" target="_blank" rel="noopener noreferrer" '+
        'aria-label="'+cpFitShopLabel(item)+'">'+body+'</a>'
      :'<div class="cpFitLookCard" data-vf-look="'+i+'">'+body+'</div>';
  }).join('');
  return '<div class="cpFitLook" data-vf-id="look">'+cpFitRefHTML(f.ref)+'<div class="cpFitLookHead"><b>코디 상품</b>'+
    '<span>'+rows.length+'</span>'+(f.tags&&f.tags.length&&f.result?'<em>사진에 올리면 어디에 입혔는지 보여요</em>':'')+'</div>'+
    '<div class="cpFitLookRow">'+cards+'</div></div>';
}
/* 근거로 쓴 코디 기사 (2026-10-02) — 서버 find_looks 가 출처를 확인한 것만 온다(tools._look_for).
   웹에서 찾은 코디라 FEEDiT 측정값이 아니다 — '참고한 코디' 로만 적는다. */
function cpFitRefHTML(ref){
  const url=cpShopUrl(ref&&ref.url); if(!url)return '';
  const who=String(ref.who||ref.domain||'').trim();
  return '<a class="cpFitRef" href="'+cpEsc(url)+'" target="_blank" rel="noopener noreferrer">'+
    '<span>참고한 코디</span><b>'+cpEsc(ref.title||'코디 기사')+'</b>'+(who?'<em>'+cpEsc(who)+' ↗</em>':'<em>↗</em>')+'</a>';
}
/* 결과가 나온 뒤 '다른 룩도 볼까요?' (2026-10-02). 같은 말이 대화 기록(turn.next)에도 남아서
   사용자가 "응" 이라고만 쳐도 챗봇이 무엇에 대한 대답인지 안다(orchestrator._ctx_block). */
function cpFitNextQuestion(f){
  const occ=String(f&&f.occasion||'').trim();
  return (occ?occ+' ':'')+'다른 룩도 추천해 드릴까요?';
}
function cpFitNextHTML(f){
  if(!f||!f.result||f.loading||!f.fromServer)return '';
  const occ=String(f.occasion||'').trim();
  return '<div class="cpFitNext" data-vf-id="next"><p><b>이 룩 어떠세요?</b> '+cpEsc(cpFitNextQuestion(f))+'</p>'+
    '<div class="cpFitNextBtns">'+
      '<button type="button" class="cpFitNextBtn main" data-vf-more="look">다른 룩 추천 '+VF_SVG(VF_IC.arrow,13)+'</button>'+
      '<button type="button" class="cpFitNextBtn" data-vf-more="mood">다른 분위기로</button>'+
    '</div></div>';
}
/* 이 대화에서 보여 준 코디 기억 — 서버가 같은 상품을 다시 내밀지 않게(fit.clean_memory).
   승인 전 제안(proposal) · 승인한 코디(fitProposal) · 입혀보기 칸(fit) 모두 본다. */
export function cpFitMemory(c){
  const seen=[], refs=[]; let occasion='';
  for(const m of (c&&c.messages)||[]){
    for(const box of [m.proposal,m.fitProposal,m.fit]){
      if(!box||typeof box!=='object')continue;
      for(const it of (Array.isArray(box.items)?box.items:[])){
        const k=String((it&&(it.url||it.product_source_id||it.image||it.imageUrl))||'').trim();
        if(k&&!seen.includes(k))seen.push(k);
      }
      const ref=cpShopUrl(box.ref&&box.ref.url);
      if(ref&&!refs.includes(ref))refs.push(ref);
      if(box.occasion)occasion=String(box.occasion).slice(0,40);
    }
  }
  if(!seen.length&&!refs.length&&!occasion)return undefined;
  return {seen:seen.slice(-60),refs:refs.slice(-8),occasion};
}
/* ③ 결과 사진 위 쇼핑 태그 — 서버(vton.locate)가 준 점. 점을 누르면 그 상품 카드가 뜬다. */
function cpFitTagsHTML(f,items){
  const tags=(Array.isArray(f.tags)?f.tags:[]).filter(t=>t&&cpFitIsShop(items[t.item]));
  if(!tags.length)return '';
  /* 점이 겹치면 아래로 비켜 놓는다 — 두 점이 한 점처럼 보이면 하나를 못 누른다 */
  const placed=[];
  const spots=tags.map(t=>{
    let x=Math.min(.96,Math.max(.04,+t.x||0)), y=Math.min(.96,Math.max(.04,+t.y||0));
    while(placed.some(p=>Math.abs(p.x-x)<.05&&Math.abs(p.y-y)<.04)) y=Math.min(.96,y+.05);
    placed.push({x,y});
    return {...t,x,y};
  });
  /* ★ 2026-10-02 (오후) — 점이 늘 떠 있으니 사진이 가려진다는 말을 들었다.
     점은 사진에 마우스를 올렸을 때만 나타나고(CSS .cpFitShot:hover), 카드는 점에 올리거나
     눌러 고정했을 때(.on)만 뜬다. 터치 기기는 마우스오버가 없으니 점을 작게 늘 두고 눌러서 연다. */
  const marks=spots.map(t=>{
    const item=items[t.item], on=t.item===f.tagOpen;
    const source=cpFitSourceName(item), src=item.image||item.imageUrl;
    /* 점 오른쪽에 펴되, 사진 오른쪽 가장자리면 왼쪽으로. 위아래 끝이면 안쪽으로 붙인다. */
    const side=t.x>.55?' l':'', edge=t.y<.18?' top':t.y>.82?' bottom':'';
    const card='<div class="cpFitTagCard'+side+edge+'" role="tooltip">'+
      '<span class="cpFitTagImg"><img src="'+cpEsc(src)+'" alt="" loading="lazy" referrerpolicy="no-referrer"></span>'+
      '<span class="cpFitTagText"><small>'+cpEsc([item.brand,source].filter(Boolean).join(' · '))+'</small>'+
        '<b>'+cpEsc(item.name||vfKindName(item.category))+'</b>'+
        (item.url?'<a href="'+cpEsc(item.url)+'" target="_blank" rel="noopener noreferrer" aria-label="'+cpFitShopLabel(item)+'">'+
          cpEsc(source||'판매처')+'에서 보기 ↗</a>':'')+
      '</span></div>';
    return '<span class="cpFitTagMark'+(on?' on':'')+'" style="left:'+(t.x*100).toFixed(1)+'%;top:'+(t.y*100).toFixed(1)+'%">'+
      '<button type="button" class="cpFitTag" data-vf-tag="'+t.item+'" aria-expanded="'+on+'" '+
      'aria-label="'+cpEsc(vfKindName(item.auto?VF_AUTO:item.category))+' · '+cpEsc(item.name||'상품')+' 보기"><i></i></button>'+
      card+'</span>';
  }).join('');
  return '<div class="cpFitTags">'+marks+'</div>';
}
/* 왼쪽 설정 칸 — 펼친 모습 */
function cpFitSetupHTML(f,items){
  const models='<div class="cpFitModels m-'+(f.model==='man'?'man':'woman')+'" role="radiogroup" aria-label="모델">'+
    VF_MODELS.map(x=>'<button type="button" role="radio" class="cpFitModel'+(f.model===x.v?' on':'')+'" '+
      'data-vf-model="'+x.v+'" aria-checked="'+(f.model===x.v)+'" aria-label="'+x.label+' 모델">'+
      '<img src="'+x.img+'" alt="" loading="lazy"><span>'+x.label+'</span></button>').join('')+
    '<span class="cpFitModelFrame" aria-hidden="true"></span></div>';
  const slots=items.map((item,index)=>{
    const kind=item.auto?VF_AUTO:item.category;
    const src=item.image||item.imageUrl;
    const source=cpFitSourceName(item);
    const identity=item.name?'<span class="cpFitProductName" title="'+cpEsc(item.name)+'">'+cpEsc(item.name)+'</span>':'';
    /* ① 판매처는 사진 위 배지로 — 글자를 읽지 않아도 '어디 상품' 인지 보인다 (2026-10-02).
       사러 가는 길은 아래 '코디 상품' 줄과 결과 사진의 태그가 맡는다. */
    const srcTag=(src&&source)?'<span class="cpFitSrcTag" aria-hidden="true">'+cpEsc(source)+'</span>':'';
    return '<div class="cpFitSlot">'+
      '<button type="button" class="cpFitItem'+(src?' has':'')+'" data-vf-pick="'+index+'" '+
        'aria-label="'+(index+1)+'번 칸에 사진 '+(src?'바꾸기':'넣기')+'">'+
        (src?'<img class="cpFitItemImg" src="'+cpEsc(src)+'" alt="'+cpEsc(item.name||vfKindName(kind))+'" referrerpolicy="no-referrer">'
            :'<span class="cpFitPlus">'+VF_SVG(VF_IC.plus,18)+'</span>')+
        srcTag+'<span class="cpFitBadge" aria-hidden="true">'+vfKindIcon(kind,15)+'</span></button>'+
      '<button type="button" class="cpFitRemove" data-vf-remove="'+index+'" aria-label="'+(index+1)+'번 칸 빼기">'+
        VF_SVG(VF_IC.close,12)+'</button>'+
      '<button type="button" class="cpFitKind'+(kind===VF_AUTO?' auto':'')+(f.kindOpen===index?' on':'')+'" '+
        'data-vf-kind="'+index+'" aria-haspopup="dialog" aria-expanded="'+(f.kindOpen===index)+'" '+
        'aria-label="'+(index+1)+'번 칸 종류: '+cpEsc(kind)+'">'+
        '<span>'+cpEsc(vfKindName(kind))+'</span>'+VF_SVG(VF_IC.chevron,11)+'</button>'+identity+
      '<input type="file" data-vf-file="'+index+'" accept="image/png,image/jpeg,image/webp" hidden></div>';
  }).join('');
  /* 칸 늘리기 — 아홉 칸(서버 MAX_ITEMS)이 차면 사라진다 */
  const add=items.length<VF_MAX
    ?'<div class="cpFitSlot addSlot"><button type="button" class="cpFitItem cpFitAdd" data-vf-add="1" aria-label="칸 추가">'+
      '<span class="cpFitPlus">'+VF_SVG(VF_IC.plus,18)+'</span></button><p class="cpFitAddCap">칸 추가</p></div>':'';
  const ko=f.kindOpen, row=(ko>=0&&ko<items.length)?items[ko]:null;
  const picked=row?(row.auto?VF_AUTO:row.category):'';
  const sheet=row
    ?'<div class="cpFitSheet" role="dialog" aria-label="'+(ko+1)+'번 칸 종류 고르기">'+
      '<div class="cpFitSheetHead"><b>'+(ko+1)+'번 칸 · 종류 고르기</b>'+
      '<button type="button" data-vf-kind="'+ko+'" aria-label="닫기">'+VF_SVG(VF_IC.close,14)+'</button></div>'+
      '<div class="cpFitSheetList" role="listbox" aria-label="옷 종류">'+
      VF_KINDS.map(k=>'<button type="button" role="option" class="'+(k===picked?'on':'')+'" '+
        'data-vf-kindpick="'+ko+'|'+cpEsc(k)+'" aria-selected="'+(k===picked)+'">'+
        vfKindIcon(k,16)+'<span>'+cpEsc(vfKindName(k))+'</span></button>').join('')+
      '</div></div>':'';
  const note=f.sorting
    ?'<p class="cpFitWarn busy">사진이 어떤 옷인지 확인하는 중입니다…</p>'
    :'<p class="cpFitWarn">'+VF_SVG(VF_IC.warn,14)+
      '<span>Auto 분류는 정확하지 않을 수 있습니다.<br>칸 아래 이름을 눌러 직접 고를 수 있어요.</span></p>';
  /* 모델 위 성별 표시 (2026-10-02) — 사진만으로는 지금 누구로 입히는지 한눈에 안 들어온다 */
  const who=f.model==='man'?'남성':'여성';
  const modelHead='<div class="cpFitModelHead"><b>모델</b><span class="cpFitGender g-'+(f.model==='man'?'man':'woman')+'">'+who+'</span></div>';
  return '<div class="cpFitFull" data-vf-id="full">'+modelHead+models+
    '<div class="cpFitClothesHead"><b>옷</b><span>'+items.length+' / '+VF_MAX+'</span></div>'+
    '<div class="cpFitClothes"><div class="cpFitItems">'+slots+add+'</div>'+sheet+'</div>'+note+'</div>';
}
/* 왼쪽 설정 칸 — 접힌 모습. 위에서부터 모델, 옷 칸들, 칸 추가. 누르면 펼친다. */
function cpFitMiniHTML(f,items){
  const model=VF_MODELS.find(x=>x.v===f.model)||VF_MODELS[0];
  return '<div class="cpFitMini" data-vf-id="mini">'+
    '<button type="button" class="cpMiniSq model" data-vf-side="1" aria-label="'+model.label+' 모델 — 눌러서 설정 펼치기">'+
      '<img src="'+model.img+'" alt=""></button><span class="cpMiniRule" aria-hidden="true"></span>'+
    items.map((item,i)=>{
      const kind=item.auto?VF_AUTO:item.category, src=item.image||item.imageUrl;
      return '<button type="button" class="cpMiniSq" data-vf-side="1" aria-label="'+(i+1)+'번 칸 · '+cpEsc(vfKindName(kind))+' — 눌러서 설정 펼치기">'+
        (src?'<img src="'+cpEsc(src)+'" alt="" referrerpolicy="no-referrer">':vfKindIcon(kind,18))+'</button>';
    }).join('')+
    (items.length<VF_MAX?'<button type="button" class="cpMiniSq add" data-vf-side="1" aria-label="칸 추가 — 눌러서 설정 펼치기">'+VF_SVG(VF_IC.plus,16)+'</button>':'')+
    '</div>';
}
/* ── 착장 위젯만 고쳐 그리기 (2026-10-02) ─────────────────────
   옵션 하나를 바꿀 때마다 대화 전체를 innerHTML 로 다시 그렸더니, 왼쪽 모델 사진과
   옷 사진이 새 <img> 로 바뀌며 깜빡였고(4K 결과 · data URL 사진은 다시 그리는 데
   한 박자 걸린다), 펼침 애니메이션도 매번 다시 돌았다. 모델 테가 미끄러지는
   움직임도 요소가 새로 생겨 보이지 않았다.
   → 이 위젯의 새 마크업을 만들어 지금 화면과 **달라진 곳만** 고친다(cpMorph).
     바뀌지 않은 <img> 는 그 자리에 남고, 클래스만 바뀐 요소는 CSS 전환이 그대로 걸린다.
   ★ data-vf-id 가 다른 요소(펼친 칸 ↔ 접힌 네모)는 고치지 않고 통째로 바꾼다.
     새로 들어온 쪽에만 cpFitIn 을 붙여 한 번 서서히 나타나게 한다.
   ★ 화면에 이 위젯이 없으면(다른 대화를 보는 중 등) 예전처럼 대화를 다시 그린다. */
function cpMorph(a,b){
  const idOf=(n)=>n.nodeType===1?(n.getAttribute('data-vf-id')||''):'';
  if(a.nodeType!==b.nodeType||a.nodeName!==b.nodeName||idOf(a)!==idOf(b)){
    if(idOf(b))b.classList.add('cpFitIn');
    a.replaceWith(b); return;
  }
  if(a.nodeType!==1){ if(a.nodeValue!==b.nodeValue)a.nodeValue=b.nodeValue; return; }
  if(a.isEqualNode(b))return;
  for(const at of [...b.attributes]) if(a.getAttribute(at.name)!==at.value)a.setAttribute(at.name,at.value);
  for(const at of [...a.attributes]) if(!b.hasAttribute(at.name))a.removeAttribute(at.name);
  const ac=[...a.childNodes], bc=[...b.childNodes];
  bc.forEach((n,i)=>{ if(i<ac.length)cpMorph(ac[i],n); else a.appendChild(n); });
  for(let i=bc.length;i<ac.length;i++)ac[i].remove();
}
/* 착장 칸을 화면 안으로 — 버튼을 눌렀는데 칸이 화면 밖이면 반응이 없는 것처럼 보인다 */
function cpFitReveal(m){
  const key=String(m&&m.fit&&m.fit.key||'');
  const th=$('#cpThread'); if(!th||!key)return;
  const sec=[...th.querySelectorAll('.cpFit')].find(x=>x.dataset.fitKey===key);
  if(sec&&sec.scrollIntoView)sec.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function cpFitRender(m){
  const th=$('#cpThread');
  const key=String(m&&m.fit&&m.fit.key||'');
  const sec=th&&key?[...th.querySelectorAll('.cpFit')].find(x=>x.dataset.fitKey===key):null;
  if(!sec){ cpRenderThread({keepScroll:true}); return; }
  const tpl=document.createElement('template');
  tpl.innerHTML=cpFitHTML(m);
  const fresh=tpl.content.firstElementChild;
  if(!fresh){ cpRenderThread({keepScroll:true}); return; }
  cpMorph(sec,fresh);
  cpFitSizeItems(sec);
}
function cpFitHTML(m){
  const f=m.fit; if(!f)return '';
  const items=cpFitItems(f);
  const open=f.side!=='closed';
  const engine=cpFitEngineOf(f);
  const engineSpec=VF_ENGINES.find(e=>e.v===engine);
  /* 결과 저장 — data URL 을 그대로 내려받는다. 서버를 한 번 더 부르지 않는다.
     ★ 2026-10-02 — 사진 오른쪽 위에 얹는다. 예전엔 결과 칸 오른쪽 위에 떠 있어 사진과
       떨어져 보였고, 세로 독을 세운 뒤엔 독 옆 빈자리에 혼자 남았다. */
  const save=(f.result&&!f.loading)
    ?'<a class="cpFitDl" href="'+cpEsc(f.result)+'" download="feedit-fitting-'+cpEsc(f.key)+'.'+cpFitExt(f)+'"'+
     ' title="이미지 저장" aria-label="착용 이미지 저장">'+CP_IC_DOWN+'</a>':'';
  const stage=f.loading?'<div class="cpFitLoader" aria-label="착용 이미지 생성 중"><i class="cpStar">✧</i></div>':
    f.result?'<div class="cpFitShot" style="aspect-ratio:'+cpFitRatio(f)+'">'+
      '<img class="cpFitResult" src="'+cpEsc(f.result)+'" alt="AI 모델 착용 결과" data-vf-tagclose="1">'+
      cpFitTagsHTML(f,items)+save+'</div>':
    '<div class="cpFitResultEmpty">완성된 착용 이미지가<br>여기에 나타납니다.</div>';
  /* 무엇으로 몇 초 걸렸나 (2026-10-01) — 엔진을 고르는 이유가 시간이라, 결과마다 남긴다. */
  const made=(f.result&&!f.loading&&f.made&&f.made.label)
    ?'<p class="cpFitState success cpFitMade">'+cpEsc(f.made.label)+
     (f.made.sec?' · '+cpEsc(String(f.made.sec))+'초':'')+'</p>':'';
  const state=(!f.loading&&f.stateKind==='error')
    ?'<p class="cpFitState error">'+cpEsc(f.status||'')+
     '<button type="button" class="cpFitRetry" data-vf-retry="1">다시 시도</button></p>':made;
  return '<section class="cpFit'+(open?'':' side-closed')+'" data-fit-key="'+cpEsc(f.key)+'">'+
    '<div class="cpFitHead">'+
      '<button type="button" class="cpFitSideBtn" data-vf-side="1" aria-expanded="'+open+'" '+
        'aria-label="'+(open?'설정 접기':'설정 펼치기')+'">'+VF_SVG(open?VF_IC.sideOpen:VF_IC.sideClosed,18)+'</button>'+
      '<span>VIRTUAL TRY ON</span><b>코디 입혀보기</b></div>'+
    '<div class="cpFitGrid">'+
      '<aside class="cpFitSetup">'+(open?cpFitSetupHTML(f,items):cpFitMiniHTML(f,items))+'</aside>'+
      '<div class="cpFitOutput">'+
        '<span class="cpFitEngineTag">'+VF_SVG(VF_IC[engine],12)+'<span>'+cpEsc(engineSpec.name)+'</span></span>'+
        '<div class="cpFitStage">'+stage+state+'</div>'+
        cpFitDockHTML(f)+
      '</div></div>'+cpFitLookHTML(f,items)+cpFitNextHTML(f)+'</section>';
}
/* 사용자가 친 문장을 상품명 자리에 쓸 수 있는지. 주소가 섞여 있으면 쓰지 않는다 —
   "https://… 이거 사도 될까?" 에서 주소를 떼어 내도 남는 말은 상품명이 아니다. */
function cpTitleFromText(text){
  const t=String(text||'').trim();
  if(!t)return '';
  return /https?:\/\/|www\.[^\s]+/i.test(t) ? '' : t;
}
function cpAIMessageFor(el){
  const node=el&&el.closest('.msg.ai'), c=cpActiveConvo();
  if(!node||!c)return null;
  return c.messages[Number(node.dataset.msgIndex)]||null;
}
/* ★ 그리고 나면 늘 맨 아래로 내려갔다 (2026-09-14). 새 답이 올라올 땐 맞는
   동작이지만, 옵션 하나를 켜거나 칸을 하나 늘릴 때도 화면이 통째로 아래로
   튀었다 — 보고 있던 자리가 사라진다. keepScroll 을 받으면 보던 자리를
   그대로 되돌려 놓는다. */
/* ── 마지막 질문 그 자리에서 고치기 (2026-09-14) ───────────
   연필을 누르면 입력창으로 글이 되돌아가던 것을, 말풍선이 그대로 입력칸이
   되게 바꿨다. 고칠 수 있는 것은 **마지막 질문 하나**뿐이다 —
   중간 질문을 고치면 그 뒤의 대화가 통째로 날아간다. */
function cpLastMeIndex(c){
  if(!c||!c.messages)return -1;
  for(let i=c.messages.length-1;i>=0;i--) if(c.messages[i].role==='me')return i;
  return -1;
}
function cpEditFocus(th){
  const box=th&&th.querySelector('.cpEditIn'); if(!box)return;
  if(box.dataset.ready)return;
  box.dataset.ready='1';
  box.focus();
  box.setSelectionRange(box.value.length,box.value.length);
}
export function cpEditStart(idx){
  const c=cpActiveConvo(); if(!c)return;
  if(cpActiveRun)return;                 /* 답이 도는 중에는 고치지 않는다 */
  if(idx!==cpLastMeIndex(c))return;      /* 마지막 질문만 */
  const m=c.messages[idx]; if(!m||m.role!=='me')return;
  c.messages.forEach(x=>{ delete x.editing });
  m.editing=true;
  cpRenderThread({keepScroll:true});
}
export function cpEditCancel(idx){
  const c=cpActiveConvo(); if(!c)return;
  const m=c.messages[idx]; if(!m)return;
  delete m.editing;
  cpRenderThread({keepScroll:true});
}
/* 저장 — 고친 질문으로 다시 묻는다.
   ★ 이 질문 뒤의 것은 전부 버린다. 고친 질문에 옛 답이 붙어 있으면
     읽는 사람은 그 답이 고친 질문의 답이라고 읽는다. */
export function cpEditSave(idx){
  const c=cpActiveConvo(); if(!c)return;
  if(cpActiveRun)return;
  const m=c.messages[idx]; if(!m||m.role!=='me')return;
  const box=$('#cpThread [data-edit-in="'+idx+'"]');
  const next=box?box.value.replace(/\s+$/,''):'';
  const images=(m.images||[]).slice();
  if(!next&&!images.length)return;       /* 빈 질문은 보내지 않는다 */
  delete m.editing;
  if(next===(m.text||'')){ cpRenderThread({keepScroll:true}); return; }
  /* 서버에도 이 질문부터 뒤를 지운다 — 남겨 두면 다시 열었을 때 옛 답이 되살아난다 */
  const cut=c.messages.slice(idx).find(x=>x.sid);
  if(AUTH.in&&cut)chatTruncate({mode:cpModeOf(c),key:c.key,from_message_id:cut.sid});
  c.messages.length=idx;                 /* 이 질문과 그 뒤를 걷어낸다 */
  cpSave();
  cpAsk(next, cpKeyFor(next), {images});
}
export function cpRenderThread(opts){
  const wrap=$('#cpThreadWrap'), th=$('#cpThread'); if(!wrap||!th)return;
  const keepAt=(opts&&opts.keepScroll)?wrap.scrollTop:-1;
  const toBottom=()=>{ wrap.scrollTop=keepAt>=0?keepAt:wrap.scrollHeight };
  const c=cpActiveConvo();
  if(cpTypeTimer){ clearTimeout(cpTypeTimer); cpTypeTimer=null; }
  if(c&&c.loaded===false){
    void cpEnsureLoaded(c);
    if(!c.messages.length){
      wrap.classList.add('hasMsg');
      th.innerHTML='<p class="cpListEmpty">'+(c.loadP?'대화를 불러오는 중…':'대화를 불러오지 못했습니다. 다시 열어 주세요.')+'</p>';
      return;
    }
  }
  if(!c||!c.messages.length){ wrap.classList.remove('hasMsg'); th.innerHTML=''; return; }
  wrap.classList.add('hasMsg');
  const typeIdx=(opts&&opts.typeLast)?c.messages.length-1:-1;
  const lastMe=cpLastMeIndex(c);
  th.innerHTML=c.messages.map((m,idx)=>{
    if(m.role==='me'){
      const imgs=(m.images&&m.images.length)
        ?'<div class="bubImgs">'+m.images.map(u=>'<img src="'+u+'" alt="">').join('')+'</div>':'';
      /* ── 그 자리에서 고치기 (2026-09-14) ──────────────────
         예전에는 연필을 누르면 입력창으로 글이 되돌아갔다. 화면 아래로 눈이
         내려가고, 무엇을 고치는 중인지 말풍선 쪽에는 아무 표시가 없었다.
         이제 말풍선이 그대로 입력칸이 된다. */
      if(m.editing){
        return '<div class="msg me editing">'+imgs+
          '<div class="cpEditBox">'+
            '<span class="cpEditSizer" aria-hidden="true">'+cpEsc(m.text||'')+'</span>'+
            '<textarea class="cpEditIn" data-edit-in="'+idx+'" rows="1">'+cpEsc(m.text||'')+'</textarea>'+
          '</div>'+
          '<div class="cpEditActs">'+
            '<span class="cpEditWhy" title="저장하면 이 아래 답변은 지워지고 고친 질문으로 다시 물어봅니다.">ⓘ</span>'+
            '<button type="button" class="cpEditBtn" data-edit-cancel="'+idx+'">취소</button>'+
            '<button type="button" class="cpEditBtn on" data-edit-save="'+idx+'">저장</button>'+
          '</div></div>';
      }
      const bub=m.text?('<div class="bub">'+cpEsc(m.text)+'</div>'):'';
      /* 말풍선 아래 아이콘 줄 (2026-09-14) — 재전송 · 수정 · 복사.
         재전송: 같은 질문과 사진을 그대로 한 번 더 보낸다.
         수정  : 마지막 질문만. 그 자리에서 고쳐 다시 묻는다.
         복사  : 질문 문장만 클립보드로.
         ★ 수정은 마지막 질문에만 붙인다 — 중간 질문을 고치면 그 뒤의 대화가
           통째로 날아간다. 되돌릴 수 없는 일을 아이콘 하나로 두지 않는다.
         사진이 저장 한도 때문에 빠진 대화는 글만 되돌린다(2026-09-13). */
      const again=(m.text||(m.images&&m.images.length))
        ?'<div class="cpMeActs">'+
          '<button type="button" class="cpMeAct" data-resend="'+idx+'" title="재전송" aria-label="같은 질문 다시 보내기">'+CP_IC_RESEND+'</button>'+
          (idx===lastMe&&m.text?'<button type="button" class="cpMeAct" data-again="'+idx+'" title="수정" aria-label="질문 고쳐서 다시 묻기">'+CP_IC_EDIT+'</button>':'')+
          (m.text?'<button type="button" class="cpMeAct" data-copy="'+idx+'" title="복사" aria-label="질문 복사">'+CP_IC_COPY+'</button>':'')+
        '</div>':'';
      const dropped=m.imagesDropped&&!(m.images&&m.images.length)
        ?'<div class="cpDropped">첨부 사진은 저장 한도로 남기지 못했습니다.</div>':'';
      return '<div class="msg me">'+imgs+dropped+bub+again+'</div>';
    }
    if(m.pending) return '<div class="msg ai thinking" data-msg-index="'+idx+'">'+cpWhoHTML(m.stage)+'</div>';
    if(idx===typeIdx) return '<div class="msg ai" data-msg-index="'+idx+'" data-type-target="1">'+cpWhoHTML()+'<div class="say"></div></div>';
    { const card=responseCardHTML(m,ansCardHTML);
      return '<div class="msg ai" data-msg-index="'+idx+'">'+cpWhoHTML()+'<div class="say">'+(m.html||'')+'</div>'+
        card+(m.followHtml||'')+(m.cueHtml||'')+(m.actionsHtml||'')+cpFitHTML(m)+
        cpFeedbackHTML(m,idx)+'</div>'; }
  }).join('');
  $$('i[data-w]',th).forEach(f=>f.style.width=f.dataset.w+'%');
  cpFitSizeItems(th);
  cpEditFocus(th);
  toBottom();
  if(typeIdx>=0){
    const m=c.messages[typeIdx];
    const target=th.querySelector('[data-type-target="1"] .say');
    if(target&&m)cpTypeHTML(target,m.html,()=>{
      if(m.key){
        const holder=document.createElement('div');
        holder.innerHTML=ansCardHTML(m.key);
        const cardEl=holder.firstElementChild;
        cardEl.classList.add('reveal');
        target.parentElement.appendChild(cardEl);
        $$('i[data-w]',cardEl).forEach(f=>f.style.width=f.dataset.w+'%');
        requestAnimationFrame(()=>{ requestAnimationFrame(()=>cardEl.classList.add('in')); });
      }
      toBottom();
    });
  }
}
/* 답 텍스트를 한 글자씩 밀어 넣는다. html 안의 태그(<b>…</b>)는 한 번에
   통째로 소비해서, 어느 순간에 잘라도 항상 닫힌 HTML만 그려지게 한다. */
function cpTypeHTML(el,html,done){
  el.innerHTML='';
  let i=0;
  const wrap=$('#cpThreadWrap');
  function step(){
    if(i>=html.length){ done&&done(); return; }
    if(html[i]==='<'){
      const end=html.indexOf('>',i);
      i=end===-1?html.length:end+1;
      el.innerHTML=html.slice(0,i);
      step();
      return;
    }
    i++;
    el.innerHTML=html.slice(0,i);
    if(wrap)wrap.scrollTop=wrap.scrollHeight;
    const prev=html[i-1];
    const delay=/[.,!?]/.test(prev)?110:14+Math.random()*16;
    cpTypeTimer=setTimeout(step,delay);
  }
  step();
}
/* 질문 하나를 대화에 밀어 넣는다 — 답은 곧장 나오지 않고, 잠깐 "생각 중" 상태로
   있다가 텍스트가 타이핑되듯 채워진 뒤 카드가 뒤따라 떠오른다 */
/* 서버는 스타일을 **이름**으로 보낸다(chat_api.js actionsHTML 주석).
   라우터(goStyle)는 id 를 기대하므로 여기서 이름 → id 로 바꿔 단다.
   못 찾으면 조용히 첫 번째 스타일로 떨어지면 안 되니 — 버튼 자체를 지운다. */
function cpFixStyleLinks(host){
  if(!host)return;
  host.querySelectorAll('[data-style-name]').forEach(btn=>{
    const name=btn.dataset.styleName;
    const hit=STYLES.find(x=>x.n===name);
    if(hit){ btn.dataset.style=hit.id; btn.removeAttribute('data-style-name'); }
    else{ btn.remove(); }
  });
}
/* 서버가 보낸 이어 갈 질문(HTML 한 줄) → 글자만. 기억(turn)에 넣을 값이라 태그·엔티티를 걷는다.
   (DOM 에 붙이지 않는다 — 받은 HTML 을 innerHTML 로 해석할 이유가 없다.) */
function cpNextText(html){
  return String(html||'').replace(/<[^>]+>/g,' ')
    .replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;|&#x27;/g,"'")
    .replace(/&amp;/g,'&').replace(/\s+/g,' ').trim().slice(0,200);
}
/* 최근 턴 몇 개 — server.py history 형식({q,intent,terms,next})으로.
   답이 아직 안 온 턴(진행 중)은 넣지 않는다 — intent 가 아직 없다. */
export function cpHistoryFor(c){
  const out=[];
  for(const m of c.messages) if(m.role==='ai'&&m.turn) out.push(m.turn);
  return out.slice(-8);
}
/* 살말 지수의 '취향' 축이 보는 것 — 가입할 때 고른 즐겨입는 스타일이다.
   이름만 보내면 서버에서 "블록코어" 와 "벌룬 카고 미디 스커트" 를 맞대게 되어
   겹치는 일이 거의 없다. 그래서 스타일의 대표 어휘(STYLES.kw)도 같이 보낸다 —
   표는 STYLES 에 드러나 있고, 고치면 판단이 바뀐다. */
function cpTasteContext(c){
  const byId=new Map(STYLES.map(s=>[s.id,s]));
  const picked=[...ME.styles].map(id=>byId.get(id)).filter(Boolean);
  const favorite=picked.map(s=>s.n);
  const profiles=picked.map(s=>({name:s.n, keywords:[s.en, ...(s.kw||[])].filter(Boolean).slice(0,8)}));
  const saved=[];
  LIKED.forEach(v=>{
    if(v&&v.nm)saved.push(v.nm);
    if(v&&v.br)saved.push(v.br);
  });
  const searched=[];
  for(const turn of cpHistoryFor(c)) for(const term of (turn.terms||[])){
    if(term&&term.canonical)searched.push(term.canonical);
  }
  return {favorite_styles:favorite.slice(0,10),
          favorite_style_profiles:profiles.slice(0,10),
          searched_terms:[...new Set(searched)].slice(-20),
          saved_terms:[...new Set(saved)].slice(0,30)};
}
function cpAskUnavailable(c,aiMsg){
  // 불완전한 결과와 예시 카드를 지운다. 질문·사진은 재전송 버튼으로 다시 보낼 수 있다.
  aiMsg.html='<p role="alert">답변을 받지 못했습니다.<br>잠시 후 질문 아래의 재전송 버튼으로 다시 시도해 주세요.</p>';
  aiMsg.cardHtml=''; aiMsg.followHtml=''; aiMsg.cueHtml=''; aiMsg.actionsHtml='';
  aiMsg.turn=null; aiMsg.key=null;
  aiMsg.pending=false;
  if(cpActiveConvo()===c)cpRenderThread();
}
/* feedit-chat(:8770)에 실제로 묻는다. 연결 실패와 불완전한 스트림은 오류로 안내한다.
   대화 id 에 모드를 붙여 보낸다 —
   두 모드가 따로 1,2,3… 으로 세므로 안 붙이면 섞인다. */
async function cpAskLive(c,aiMsg,text,images){
  const run=aiMsg.run;
  const conv=cpConvId(c);
  const history=cpHistoryFor(c);
  /* pending 은 아직 true 로 남겨둔다 — 첫 실제 응답(text/report/error)이
     오기 전까지는 별 아이콘이 돌아가는 "생각 중" 헤더를 그대로 보여준다.
     cardHtml 만 미리 비워서 m.key 목업 카드가 새지 않게 잠근다. */
  aiMsg.html='';
  aiMsg.cardHtml='';           /* 아직 스트리밍 전 — m.key 목업 카드로 떨어지지 않게 잠근다 */
  const sayEl=()=>{
    if(cpActiveConvo()!==c)return null;
    const wrap=$('#cpThreadWrap'); if(!wrap)return null;
    const nodes=wrap.querySelectorAll('.msg.ai');
    return nodes.length?nodes[nodes.length-1].querySelector('.say'):null;
  };
  /* pending 상태를 풀고 "생각 중" 헤더 대신 실제 말풍선(.say)을 그린다 —
     text/report/error 중 뭐가 먼저 오든 한 번만 호출된다. */
  const settle=()=>{
    if(!aiMsg.pending)return;
    aiMsg.pending=false;
    if(cpActiveConvo()===c)cpRenderThread();
  };
  let acc='';
  await askStream({question:text, mode:cpMode(), plan:'FREE', request_id:run.requestId,
                    conversation_id:conv, history,
                    /* ★ 로그인 사실을 챗봇에 알린다 (2026-09-18). 예전에는 안 보내서 챗봇이
                       모든 사용자를 비로그인으로 보고 취향 도구를 막았다. 취향 값 자체는
                       taste_context 로 가고, 챗봇은 이 id 로 다른 데이터를 조회하지 않는다. */
                    user_id:(AUTH.in&&ME.id!=null)?String(ME.id):undefined,
                    gender:cpMyGender()||undefined,
                    taste_context:cpTasteContext(c),
                    /* 승인된 코디. 이것이 있는 턴에만 서버가 build_fit 을 부를 수 있다. */
                    fit_proposal:aiMsg.fitProposal||undefined,
                    /* 이 대화에서 보여 준 코디 — '다른 룩' 에 같은 상품이 다시 나오지 않게 */
                    fit_memory:cpFitMemory(c),
                    images:(images&&images.length)?images:undefined},{
    /* ★ 진행 상황 (server.py 의 push("status", {stage:"tool", message})).
       예전에는 이 핸들러가 아예 없어서 서버가 보낸 이벤트가 **조용히
       버려졌다** — askStream 은 on[ev] 가 없으면 그냥 넘어간다.
       그래서 답이 올 때까지 헤더만 돌았다. 예산이 14초라 그 침묵이 길다. */
    status:(d)=>{
      if(!d || d.stage!=='tool' || !d.message) return;
      aiMsg.stage=d.message;
      if(!aiMsg.pending) return;                 /* 이미 말풍선이 떴으면 끝 */
      const th=$('#cpThread');
      const node=th&&th.querySelector('.msg.ai.thinking .cpStage');
      /* 한 글자만 바꾼다 — 전체를 다시 그리면 회전 애니메이션이 끊긴다 */
      if(node) node.textContent=d.message;
      else if(cpActiveConvo()===c) cpRenderThread();
    },
    text:(d)=>{
      settle();
      acc+=d.delta||''; aiMsg.html=acc;
      const el=sayEl(); const wrap=$('#cpThreadWrap');
      if(el){ el.innerHTML=acc; if(wrap)wrap.scrollTop=wrap.scrollHeight; }
    },
    report:(rep)=>{
      settle();
      aiMsg.reportPayload=rep;
      aiMsg.turn={q:text, intent:rep.intent,
        terms:(rep.terms||[]).map(t=>({canonical:t.canonical,facet:t.facet,term_key:t.term_key}))};
      /* 사진 답변의 item·소재·색·실루엣은 다음 턴의 주어다. 예전에는 terms만
         저장해서 "소재는 뭐야?"가 무엇을 가리키는지 통째로 사라졌다. */
      if(rep.visual_context)aiMsg.turn.visual=rep.visual_context;
      /* 챗봇이 끝에 되물은 것도 기억한다 (2026-10-01). "응 두개 다 알려줘" 는 이 질문에 대한
         대답인데, 예전엔 다음 턴에 사용자 질문만 넘어가서 서버가 '두 개' 를 짐작했다. */
      const nextQ=cpNextText(rep.followup);
      if(nextQ)aiMsg.turn.next=nextQ;
      /* 확정된 코디 — 답변과 함께 착장 칸을 펼친다 (2026-09-22). 버튼을 한 번 더
         누르게 하지 않는다. 원본은 이 하나다(server.actions_for 주석). */
      if(rep.fit&&(rep.fit.items||[]).length&&!aiMsg.fit){
        aiMsg.fit=cpFitFromServer(rep.fit,text);
      }
      /* 승인 전 제안도 기억한다 — 바로 이어 "다른 룩" 을 물으면 이 상품들을 뺀다 */
      if(rep.fit_proposal&&(rep.fit_proposal.items||[]).length){
        const p=rep.fit_proposal;
        aiMsg.proposal={items:(p.items||[]).slice(0,9).map(it=>({url:String(it.url||''),
          product_source_id:String(it.product_source_id||''),image:String(it.image||'')})),
          occasion:String(p.occasion||'').slice(0,40),ref:p.ref&&cpShopUrl(p.ref.url)?{url:cpShopUrl(p.ref.url)}:null};
      }
      aiMsg.cardHtml=reportHTML(rep);
      const el=sayEl(); const host=el&&el.parentElement;
      if(host){
        const holder=document.createElement('div'); holder.innerHTML=aiMsg.cardHtml;
        while(holder.firstChild)host.appendChild(holder.firstChild);
        fillBars(host);
      }
      /* 카드 다음 순서는 셋이다 — 이어 갈 질문 · 못 한 것 · 버튼.
         라이브로 붙이는 순서와 다시 그릴 때의 순서가 같아야 한다
         (cpRenderThread 가 card 다음에 followHtml → cueHtml 을 끼운다). */
      aiMsg.followHtml=followupHTML(rep.followup);
      if(host&&aiMsg.followHtml)host.insertAdjacentHTML('beforeend',aiMsg.followHtml);
      aiMsg.cueHtml=notesHTML(rep.notes);
      if(host&&aiMsg.cueHtml)host.insertAdjacentHTML('beforeend',aiMsg.cueHtml);
    },
    actions:(acts)=>{
      aiMsg.actionsHtml=actionsHTML(acts);
      const el=sayEl(); const host=el&&el.parentElement;
      if(host&&aiMsg.actionsHtml){
        host.insertAdjacentHTML('beforeend',aiMsg.actionsHtml);
        cpFixStyleLinks(host);
        aiMsg.actionsHtml=host.querySelector('.act')?host.querySelector('.act').outerHTML:'';
      }
    },
    error:(err)=>{
      settle();
      aiMsg.html=''; aiMsg.cardHtml=refusalHTML(err); aiMsg.turn=null;
      const el=sayEl(); const host=el&&el.parentElement;
      if(el)el.innerHTML='';
      if(host)host.insertAdjacentHTML('beforeend',aiMsg.cardHtml);
    },
    done:()=>{
      settle();
      const showFeedback=cpScheduleFeedback(aiMsg);
      if(showFeedback&&cpActiveConvo()===c)cpRenderThread();
      const wrap=$('#cpThreadWrap');
      if(wrap&&cpActiveConvo()===c)wrap.scrollTop=wrap.scrollHeight;
    }
  },{signal:run.controller.signal});
}
function cpRunButton(running){
  const btn=$('#cpSend'); if(!btn)return;
  /* 답하는 중에 입력칸에 무언가 쳐 두었으면 '중단' 이 아니라 '다음 질문으로 넣기' 다 */
  const ta=$('#cpInput');
  const typed=Boolean((ta&&ta.value.trim())||cpImages.length);
  const queue=running&&typed;
  btn.classList.toggle('stop',running&&!queue);
  btn.classList.toggle('queue',queue);
  btn.textContent=queue?'↑':running?'■':'→';
  btn.setAttribute('aria-label',queue?'다음 질문으로 보내기':running?'답변 중단':'보내기');
  btn.title=queue?'지금 답이 끝나면 이어서 묻습니다':running?'답변 생성을 중단합니다':'';
}
/* ── 답하는 중에 들어온 질문 — 대기열 (2026-10-02) ───────────────
   예전에는 답이 도는 중에 칩 · 버튼을 누르거나 새로 물으면 새 요청이 바로 나갔다.
   앞 요청은 서버에서 계속 돌면서 화면의 '마지막 말풍선' 에 글자를 흘려, 앞 답이 끊기고
   뒤 답과 섞였다. 이제는 막지도 버리지도 않는다 — 대기열에 넣고 지금 답이 끝나는 대로
   이어서 묻는다. 다음 질문은 앞 답을 history 로 보고 답하므로 중간에 덧붙인 말이
   그대로 반영된다(ChatGPT · Claude 의 '답하는 중 입력' 과 같은 흐름). 줄 끝 × 로 뺀다. */
const cpQueue=[];
let cpQSeq=0;
function cpQueuePaint(){
  const box=$('#cpQueue'); if(!box)return;
  if(!cpQueue.length){ box.hidden=true; box.innerHTML=''; cpRunButton(Boolean(cpActiveRun)); return; }
  box.hidden=false;
  box.innerHTML='<span class="cpQHead">답이 끝나면 이어서 물어요</span>'+cpQueue.map(q=>{
    const n=(q.opts&&q.opts.images||[]).length;
    const label=q.text||(n?'사진 '+n+'장':'');
    return '<div class="cpQItem"><i class="cpQDot" aria-hidden="true"></i>'+
      '<span class="cpQText">'+cpEsc(label)+(q.text&&n?' <em>· 사진 '+n+'장</em>':'')+'</span>'+
      '<button type="button" class="cpQDrop" data-q-drop="'+q.id+'" aria-label="대기 중인 질문 빼기">×</button></div>';
  }).join('');
  cpRunButton(Boolean(cpActiveRun));
}
function cpEnqueue(text,key,opts){
  const o={...(opts||{})};
  /* 어느 대화에 물었는지 기억한다 — 기다리는 동안 다른 대화로 옮겨 가도 제자리에 묻는다 */
  const c=o.forceNew?null:cpActiveConvo();
  cpQueue.push({id:++cpQSeq,c,text,key,opts:o});
  cpQueuePaint();
}
function cpQueueDrain(){
  if(cpActiveRun||!cpQueue.length)return;
  const q=cpQueue.shift();
  cpQueuePaint();
  const alive=q.c&&cpStore().convos.includes(q.c);
  if(q.c&&!alive){ cpQueueDrain(); return; }     /* 그사이 지운 대화 — 건너뛴다 */
  cpAsk(q.text,q.key,{...q.opts,fromQueue:true,convo:q.c||null});
}
export function cpQueueSize(){ return cpQueue.length }
document.addEventListener('click',e=>{
  const drop=e.target.closest&&e.target.closest('#cpQueue [data-q-drop]'); if(!drop)return;
  const at=cpQueue.findIndex(q=>q.id===Number(drop.dataset.qDrop));
  if(at>=0)cpQueue.splice(at,1);
  cpQueuePaint();
});
/* 입력칸에 치는 동안 버튼 모양(중단 ↔ 다음 질문)을 맞춘다 */
document.addEventListener('input',e=>{
  if(e.target&&e.target.id==='cpInput'&&cpActiveRun)cpRunButton(true);
});
export function cpStop(){
  const run=cpActiveRun; if(!run)return;
  run.controller.abort();
  fetch(API_BASE+'/v1/chat/cancel',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({request_id:run.requestId})}).catch(()=>{});
}
/* 질문 하나를 대화에 밀어 넣고 실제 응답 또는 연결 오류를 표시한다. */
function cpAsk(text,key,opts){
  const images=(opts&&opts.images)||[];
  /* 승인된 코디 — 이 턴에만 서버의 build_fit 이 목록에 있다(tools.specs_for) */
  const fit=(opts&&opts.fit)||null;
  if(!text && !images.length)return;
  if(cpActiveRun&&!(opts&&opts.fromQueue)){ cpEnqueue(text,key,opts); return; }
  let c=(opts&&opts.convo)?opts.convo
       :(opts&&opts.forceNew)?cpNewConvo():cpActiveConvo(); if(!c)c=cpNewConvo();
  /* 서버에서 아직 본문을 안 받은 대화면 받고 나서 잇는다 — 앞 턴이 있어야 챗봇이 맥락을 잇는다 */
  if(c.loaded===false&&c.sid){
    cpEnsureLoaded(c).finally(()=>cpAskInto(c,text,key,images,fit));
    return;
  }
  cpAskInto(c,text,key,images,fit);
}
function cpAskInto(c,text,key,images,fit){
  const meMsg={role:'me', text, images};
  c.messages.push(meMsg);
  c.at=Date.now(); c.time=cpNowLabel();
  if(!c.title)c.title=cpTitleFrom(text||'사진 문의');
  /* 금주의 리포트 '챗봇 사용 시간' — 로그인한 사용자만 chat_session 에 남긴다 */
  if(AUTH.in)logChat(cpConvId(c), c.title);
  const directFit=wantsVirtualFit(text,images);
  const aiMsg={role:'ai', html:'', key, pending:!directFit};
  if(fit)aiMsg.fitProposal=fit;      /* 서버로 같이 보낸다(cpAskLive) */
  aiMsg.t0=Date.now();   /* 응답 시간 — 금주의 리포트 '챗봇 사용 시간'에 쓴다 (저장은 안 함) */
  if(directFit)aiMsg.fit=cpNewFit(images,text);
  c.messages.push(aiMsg);
  cpRenderList();
  cpRenderThread();
  cpSave();
  if(directFit){ cpFitAutoSort(aiMsg); cpGenerateFitMessage(aiMsg); return; }
  const requestId='cp-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10);
  const run={controller:new AbortController(),requestId,c,aiMsg};
  aiMsg.run=run;
  cpActiveRun=run; cpRunButton(true);
  (async()=>{
    try{
      let live=false;
      try{ live=await isUp() }catch(e){ live=false }
      if(run.controller.signal.aborted)throw new DOMException('Aborted','AbortError');
      if(!live){
        /* 서버가 없어도 승인된 코디는 열어 준다 — 목업 답으로 떨어지면 방금 승인한
           코디가 사라진다. 사진 검수(build_fit)만 없는 상태로 그대로 펼친다. */
        if(fit){ aiMsg.pending=false; aiMsg.html=cpFitWhyHTML(fit);
                 aiMsg.fit=cpFitFromServer(fit,text); cpRenderThread(); return }
        cpAskUnavailable(c,aiMsg);return
      }
      await cpAskLive(c,aiMsg,text,images);
    }
    catch(e){
      if(run.controller.signal.aborted){
        aiMsg.pending=false; aiMsg.html='<p>답변 생성을 중단했습니다.</p>';
        aiMsg.cardHtml=''; aiMsg.followHtml=''; aiMsg.cueHtml=''; aiMsg.actionsHtml='';
        if(cpActiveConvo()===c)cpRenderThread();
      }else if(e&&(e.alphaQuota||e.planQuota||e.tooLarge)){   /* 알파 · 요금제 하루 횟수 소진 · 사진 용량 초과 — 목업으로 떨어지지 않고 사유를 말한다 */
        /* 알파 테스트 계정의 챗봇 횟수 소진 — 목업 답으로 떨어지면 안 된다.
           (시연 15일 한정. chat_api.js 의 같은 표식과 한 쌍) */
        aiMsg.pending=false; aiMsg.cardHtml=''; aiMsg.followHtml='';
        aiMsg.cueHtml=''; aiMsg.actionsHtml=''; aiMsg.turn=null;
        aiMsg.html='<p>'+String(e.message||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
                          .replace(/\n/g,'<br>')+'</p>';
        if(cpActiveConvo()===c)cpRenderThread();
      }else{
        cpAskUnavailable(c,aiMsg);
      }
    }finally{
      delete aiMsg.run;
      if(cpActiveRun===run){cpActiveRun=null;cpRunButton(false)}
      cpSave();          /* 답이 끝난 상태 그대로 남긴다 */
      /* 기다리던 다음 질문 — 화면이 이 답을 다 그린 뒤에 보낸다 */
      if(cpQueue.length)setTimeout(cpQueueDrain,120);
      /* 중단한 답은 서버에 남기지 않는다 — 다른 기기에서 반쪽 답을 보게 된다 */
      if(!run.controller.signal.aborted&&!aiMsg.pending&&(aiMsg.html||aiMsg.cardHtml||aiMsg.key))
        void cpPersistTurn(c,meMsg,aiMsg);
    }
  })();
}
export function cpSend(){
  const ta=$('#cpInput'); const v=(ta&&ta.value.trim())||'';
  /* 답하는 중: 쳐 둔 것이 없으면 중단, 있으면 다음 질문으로 넣는다(cpAsk 가 대기열로 보낸다) */
  if(cpActiveRun&&!v&&!cpImages.length){cpStop();return}
  if(!v && !cpImages.length)return;
  /* ★ 로그인 관문 (2026-09-13). 예전에는 여기서 그냥 돌아섰다 —
     "발레코어 요즘 어때?" 를 치다 로그인 화면으로 넘어가면 로그인을 마쳐도
     그 질문이 사라져 사용자가 다시 쳐야 했다. 이제는 지금 친 문장과 사진을
     그대로 들고 갔다가, 로그인이 끝나면 팝업을 다시 열어 그대로 보낸다.
     입력창은 여기서 비우지 않는다 — 로그인을 그만두고 돌아왔을 때
     쳐 둔 문장이 남아 있어야 한다. */
  if(!AUTH.in){
    const images=cpImages.map(im=>im.url);
    requireAuth(()=>{
      openChatPopup();
      const box=$('#cpInput');
      if(box && box.value.trim()===v){ box.value=''; box.style.height=''; }
      if(images.length)cpImgTake();
      cpAsk(v,cpKeyFor(v),{images});
    });
    return;
  }
  cpAsk(v,cpKeyFor(v),{images:cpImgTake()});
  if(ta){ ta.value=''; ta.style.height=''; }
}
export function openChatPopup(){
  const ov=$('#cpOverlay'); if(!ov)return;
  ov.classList.toggle('sm',SM_ON);
  ov.classList.add('on');
  document.body.style.overflow='hidden';
  cpSyncOwner();
  cpPaintProfile(); cpRenderList(); cpRenderThread();
  void cpHydrate();
  setTimeout(()=>{ const ta=$('#cpInput'); if(ta)ta.focus(); },260);
}
export function closeChatPopup(){
  const ov=$('#cpOverlay'); if(!ov)return;
  ov.classList.remove('on');
  document.body.style.overflow='';
  /* 열려 있는 동안 모아 둔 알림 토스트를 이제 띄운다 (notify.js) */
  window.dispatchEvent(new Event('feedit:chatclose'));
}
/* 홈 하단 예시 버튼("이거 사도 될까?" 등)에서 바로 넘어올 때 쓰는 진입점.
   {fresh:true} 면 무조건 새 대화 — 홈에서 한 줄 치는 건 새로 묻는 동작이지
   마지막 대화를 잇는 동작이 아니다. 없으면 열려 있던(또는 마지막) 대화에 잇는다. */
export function openChatWith(text,key,opts){
  /* 로그인 전이면 이 질문을 들고 로그인 화면으로 간다. 끝나면 그대로 이어 묻는다. */
  if(!AUTH.in){
    requireAuth(()=>openChatWith(text,key,opts));
    return;
  }
  openChatPopup();
  if(opts&&opts.fresh) cpNewConvo();
  cpAsk(text, key||cpKeyFor(text), opts);
}

/* Virtual Try On 단독 진입 — 질문이나 챗봇 응답을 거치지 않고
   빈 착장 위젯을 새 대화에 바로 연다. 응답 아래의 입혀보기와 같은
   cpNewFit/cpFitHTML을 재사용해 사진 분류·생성·재시도 동작이 다르지 않게 한다. */
export function openVirtualTryOn(){
  if(!AUTH.in){
    requireAuth(()=>openVirtualTryOn());
    return;
  }
  /* ★ 살!말? 대화 안에서 누르면 어디서 열지 묻는다 (2026-10-02). 예전에는 누를 때마다
     새 대화가 생겨 목록이 'Virtual Try On' 으로 쌓였다. 일반 모드에서 넘어오면 묻지 않고
     새 대화로 연다 — 일반 대화에 착장 칸을 끼우면 두 모드의 경계가 흐려진다. */
  const here=SM_ON?cpActiveConvo():null;
  if(here&&here.messages.length){
    cpChooseWhere('어디서 입혀볼까요?',()=>cpVtonInto(here),()=>cpVtonNew());
    return;
  }
  cpVtonNew();
}
const CP_VTON_HELLO='<p>입혀보고 싶은 아이템 사진을 종류별로 올려 주세요.</p>';
function cpVtonNew(){
  if(!SM_ON)smSwitch(true,null,true);
  openChatPopup();
  const c=cpNewConvo();
  c.title='Virtual Try On';
  c.transient=true;
  cpVtonInto(c);
}
function cpVtonInto(c){
  const m={role:'ai',pending:false,key:null,html:CP_VTON_HELLO,fit:cpNewFit([],'')};
  c.messages.push(m);
  c.at=Date.now();
  cpRenderList();
  cpRenderThread();
  cpSave();
  cpFitReveal(m);
  setTimeout(()=>{
    const key=String(m.fit&&m.fit.key||'');
    const sec=[...document.querySelectorAll('#cpThread .cpFit')].find(x=>x.dataset.fitKey===key);
    const first=sec&&sec.querySelector('[data-vf-pick="0"]');
    if(first)first.focus();
  },300);
}

/* 승인된 코디를 살!말? 로 넘긴다 (2026-09-22).
   openVirtualTryOn 과 같은 이동 경로(smSwitch → 새 대화)를 쓰되, 빈 위젯이 아니라
   질문 한 턴을 보낸다 — 서버가 상품 사진을 실제로 보고(build_fit) 연출을 확정한 뒤
   착장 칸이 채워진다. 떠나온 일반 대화에는 이어진 자리를 남긴다(from).
   ★ 이미 살!말? 대화 안이면 이 대화에서 입혀볼지 새 대화로 열지 묻는다 (2026-10-02).
     일반 모드에서 넘어온 코디는 묻지 않고 새 대화다. */
export function cpConfirmFit(fit){
  if(!AUTH.in){ requireAuth(()=>cpConfirmFit(fit)); return; }
  const here=SM_ON?cpActiveConvo():null;
  if(here&&here.messages.length){
    cpChooseWhere('이 코디를 어디서 입혀볼까요?',
      ()=>cpAsk('이 코디로 입혀보기',null,{fit,convo:here}),
      ()=>cpConfirmFitNew(fit));
    return;
  }
  cpConfirmFitNew(fit);
}
function cpConfirmFitNew(fit){
  const from=cpActiveConvo();
  if(!SM_ON)smSwitch(true,null,true);
  openChatPopup();
  const c=cpNewConvo();                       /* mode:'salmal' 로 스탬프된다 */
  const styles=(fit&&fit.styles||[]).filter(Boolean).join('·');
  c.title='코디 입혀보기'+(styles?' · '+styles:'');
  if(from)c.from=cpConvId(from);
  cpAsk('이 코디로 입혀보기',null,{fit,convo:c});
}

/* ── 어디서 입혀볼까 — 이 대화 / 새 대화 (2026-10-02) ──────────────
   팝업 안에 뜨는 작은 선택 카드. 고르기 전에는 아무것도 만들지 않는다.
   바깥(대화 영역)을 누르거나 Esc · × 로 닫으면 그냥 취소다. */
let cpWherePending=null;
export function cpChooseWhere(title,onHere,onNew){
  const box=$('#cpWhere');
  if(!box){ onNew(); return; }
  cpWherePending={onHere,onNew};
  box.innerHTML='<div class="cpWhereCard" role="dialog" aria-labelledby="cpWhereT">'+
    '<button type="button" class="cpWhereX" data-where="close" aria-label="닫기">×</button>'+
    '<span class="cpWhereKick">VIRTUAL TRY ON</span>'+
    '<b id="cpWhereT">'+cpEsc(title)+'</b>'+
    '<p>지금 대화에 이어서 열면 앞의 질문과 답을 그대로 보면서 입혀볼 수 있어요.</p>'+
    '<div class="cpWhereBtns">'+
      '<button type="button" class="cpWhereBtn" data-where="here"><b>이 대화에서</b><span>아래에 착장 칸을 열어요</span></button>'+
      '<button type="button" class="cpWhereBtn new" data-where="new"><b>새 대화로</b><span>목록에 따로 남겨요</span></button>'+
    '</div></div>';
  box.hidden=false;
  setTimeout(()=>{ const b=box.querySelector('[data-where="here"]'); if(b)b.focus(); },30);
}
function cpWhereClose(pick){
  const box=$('#cpWhere'); if(box){ box.hidden=true; box.innerHTML=''; }
  const p=cpWherePending; cpWherePending=null;
  if(!p)return;
  if(pick==='here')p.onHere(); else if(pick==='new')p.onNew();
}
document.addEventListener('click',e=>{
  const box=$('#cpWhere'); if(!box||box.hidden)return;
  const b=e.target.closest&&e.target.closest('#cpWhere [data-where]');
  if(b){ cpWhereClose(b.dataset.where); return; }
  if(e.target===box)cpWhereClose('close');
});
document.addEventListener('keydown',e=>{
  const box=$('#cpWhere');
  if(e.key!=='Escape'||!box||box.hidden)return;
  /* 팝업 전체를 닫는 Esc 처리기보다 먼저 — 선택 카드만 닫는다 */
  e.preventDefault(); e.stopImmediatePropagation(); cpWhereClose('close');
});

/* 팝업 상단 좌측 마크 — 눌리면 동전이 뒤집히듯 한 바퀴 돌며 일반/살말 모드를 바꾼다.
   실제 모드 값은 SM_ON 하나뿐이라 홈 챗바의 토글과 같은 smSwitch() 를 그대로 쓰고,
   팝업 쪽 화면(프로필·목록·대화)만 이 자리에서 다시 그려 준다. */
function cpAvFlip(){
  const av=$('#cpAv'); if(!av||!HAS_A)return;
  aAnimate(av,{rotateY:[0,360],duration:640,ease:'inOut(2)'});
}
export function cpToggleMode(){
  cpAvFlip();
  /* ★ force=true — 홈 쪽 연출 잠금(smBusy, 0.9초)에 막히면 한 번 눌러선 안 바뀐다.
     사용자가 직접 누른 전환은 언제나 즉시 먹힌다.
     try/finally 로 감싼 이유: 홈 화면 연출이 실패해도 팝업 화면은 반드시 새로
     그린다 — 예전에는 그 예외 탓에 팝업만 옛 모드로 남아 두 번 눌러야 했다.
     (2026-09-13) */
  try{ smSwitch(!SM_ON,null,true); }
  finally{
    const ov=$('#cpOverlay'); if(ov)ov.classList.toggle('sm',SM_ON);
    cpPaintProfile(); cpRenderList(); cpRenderThread();
  }
}
/* 리포트 안 버튼 — 근접 키워드 재질문 · 모드 전환 힌트 · 외부 링크.
   actionsHTML/refusalHTML 이 만드는 data-kw·data-mode·data-href 를 여기서 받는다. */
document.addEventListener('click', e=>{
  const kw=e.target.closest('#cpThread [data-kw]');
  if(kw){ cpAsk(kw.dataset.kw, cpKeyFor(kw.dataset.kw)); return; }
  const md=e.target.closest('#cpThread [data-mode]');
  if(md){ smSwitch(md.dataset.mode==='salmal'); return; }
  const play=e.target.closest('#cpThread [data-chat-video-play]');
  if(play){
    const card=play.closest('.chatVideo'), screen=card?.querySelector('.chatVideoScreen');
    const id=card?.dataset.videoId;
    if(screen && /^[A-Za-z0-9_-]{11}$/.test(id || '')){
      const frame=document.createElement('iframe');
      frame.src='https://www.youtube-nocookie.com/embed/'+id+'?autoplay=1&rel=0';
      frame.title=(card.querySelector('.chatVideoCopy strong')?.textContent || 'YouTube 영상')+' 재생';
      frame.setAttribute('allow','accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen');
      frame.setAttribute('allowfullscreen','');
      frame.setAttribute('referrerpolicy','strict-origin-when-cross-origin');
      screen.replaceChildren(frame);
    }
    return;
  }
  const fullscreen=e.target.closest('#cpThread [data-chat-video-fullscreen]');
  if(fullscreen){
    const card=fullscreen.closest('.chatVideo');
    const request=card?.requestFullscreen || card?.webkitRequestFullscreen;
    if(request) Promise.resolve(request.call(card)).catch(()=>{});
    return;
  }
  const hr=e.target.closest('#cpThread [data-href]');
  if(hr){ window.open(hr.dataset.href, '_blank', 'noopener'); return; }
  const rq=e.target.closest('#cpThread [data-lexreq]');
  if(rq){ cpSendLexiconRequest(rq); return; }
  const community=e.target.closest('#cpThread [data-community]');
  if(community){
    const c=cpActiveConvo();
    const ai=cpAIMessageFor(community), aiIndex=c&&c.messages.indexOf(ai);
    const user=(c&&aiIndex>=0)?c.messages.slice(0,aiIndex).reverse().find(m=>m.role==='me'):null;
    /* 서버가 확인한 상품명·브랜드·가격이 있으면 그것을 쓴다.
       없을 때만 사용자가 친 문장으로 떨어지되, **링크는 상품명이 아니다** —
       주소가 섞여 있으면 상품명 칸을 비워 두고 사용자가 직접 적게 한다
       (2026-09-11: 카드 상품명에 무신사 주소가 그대로 들어갔다). */
    let served=null;
    try{ served=community.dataset.draft?JSON.parse(community.dataset.draft):null; }
    catch(_e){ served=null; }
    window.__salmalDraft={
      title:(served&&served.title)||cpTitleFromText(user&&user.text),
      brand:(served&&served.brand)||'',
      price:(served&&served.price!=null)?served.price:'',
      /* 사진을 올려 물었으면 그 사진, 링크로 물었으면 서버가 상품 페이지에서
         확인한 대표 이미지를 그대로 들고 간다 (2026-09-21). */
      image:(user&&user.images&&user.images[0])||(served&&served.image)||''};
    closeChatPopup();
    const nav=document.querySelector('#mNav [data-v="salmal"]');
    if(nav)nav.click();
    setTimeout(()=>{ if(window.smOpenCreate)window.smOpenCreate(window.__salmalDraft) },320);
    return;
  }
  /* '바로 입혀보기' — 누르면 펼치고, 한 번 더 누르면 접는다 (2026-09-13).
     접을 때 만들어 둔 것을 버리지 않는다(m.fitSaved). 사진을 넣고 결과까지 뽑은
     뒤 실수로 닫았다가 다시 열었을 때 처음부터 다시 하게 되면 안 된다.
     ★ 만드는 중에는 닫지 않는다 — 화면에서 사라진 채로 요청만 도는 꼴이 된다. */
  /* 예시 질문 칩 — 빈 화면에서 바로 묻는다 */
  const ask=e.target.closest('#cpEmpty [data-ask]');
  if(ask){ cpAsk(ask.dataset.ask, cpKeyFor(ask.dataset.ask)); return; }
  /* 재전송 — 같은 질문과 사진을 그대로 한 번 더 보낸다 (2026-09-14).
     답이 중간에 끊기거나 마음에 안 들 때, 같은 문장을 다시 치게 하지 않는다. */
  const resend=e.target.closest('#cpThread [data-resend]');
  if(resend){
    if(cpActiveRun)return;                 /* 답이 도는 중에는 겹쳐 보내지 않는다 */
    const c=cpActiveConvo(); if(!c)return;
    const m=c.messages[Number(resend.dataset.resend)]; if(!m)return;
    cpAsk(m.text||'', cpKeyFor(m.text||''), {images:(m.images||[]).slice()});
    return;
  }
  /* 복사 — 질문 문장만. 성공·실패를 버튼이 스스로 말한다(조용히 실패하지 않는다). */
  const copy=e.target.closest('#cpThread [data-copy]');
  if(copy){
    const c=cpActiveConvo(); if(!c)return;
    const m=c.messages[Number(copy.dataset.copy)]; if(!m||!m.text)return;
    cpCopyText(m.text).then(ok=>{
      if(ok)cpFlashBtn(copy);
      cpToast(ok?'질문을 복사했습니다.':'복사하지 못했습니다.');
    });
    return;
  }
  /* 수정 — 질문과 사진을 입력창으로 되돌린다 */
  /* 수정 — 말풍선이 그 자리에서 입력칸이 된다 (2026-09-14) */
  const again=e.target.closest('#cpThread [data-again]');
  if(again){ cpEditStart(Number(again.dataset.again)); return; }
  const editCancel=e.target.closest('#cpThread [data-edit-cancel]');
  if(editCancel){ cpEditCancel(Number(editCancel.dataset.editCancel)); return; }
  const editSave=e.target.closest('#cpThread [data-edit-save]');
  if(editSave){ cpEditSave(Number(editSave.dataset.editSave)); return; }
  /* 답변 피드백 */
  const fb=e.target.closest('#cpThread [data-fb]');
  if(fb){ cpFeedback(Number(fb.dataset.fbIdx), fb.dataset.fb); return; }
  const fbr=e.target.closest('#cpThread [data-fb-reason]');
  if(fbr){ cpFeedback(Number(fbr.dataset.fbReason),'down',fbr.dataset.reason); return; }
  const fbc=e.target.closest('#cpThread [data-fb-close]');
  if(fbc){
    const c=cpActiveConvo(); const m=c&&c.messages[Number(fbc.dataset.fbClose)];
    if(m){ delete m.fbOpen; cpRenderThread(); }
    return;
  }
  /* 착장 생성 재시도 — 실패하면 문구만 남아 다시 만들 방법이 없었다 */
  const retry=e.target.closest('#cpThread [data-vf-retry]');
  if(retry){ const m=cpAIMessageFor(retry); if(m)cpGenerateFitMessage(m); return; }
  /* 승인 카드 (2026-09-22) — VTON 은 살!말? 의 고유 기능이라 여기서 모드를 넘긴다.
     대화는 cpNewConvo 가 mode 를 스탬프하므로, 코디 대화는 살!말? 목록에만 남는다. */
  const confirm=e.target.closest('#cpThread [data-fit-confirm]');
  if(confirm){
    let payload=null;
    try{ payload=JSON.parse(confirm.dataset.fitConfirm||'null') }catch(_e){ payload=null }
    if(payload)cpConfirmFit(payload);
    return;
  }
  const fit=e.target.closest('#cpThread [data-virtual-fit]');
  if(fit){
    const c=cpActiveConvo();
    const m=cpAIMessageFor(fit);
    if(m){
      /* ★ 열려 있으면 접지 않는다 (2026-10-02 제보: "입혀보기를 두 번 눌러야 반응한다").
         확정된 코디는 답과 함께 착장 칸이 이미 펼쳐져 있는데, 이 버튼이 예전엔 접기·펴기라
         첫 번째 누름이 칸을 **닫았다** — 사용자에겐 반응이 없는 것처럼 보였고, 두 번째에야
         다시 열렸다. 이제는 이름 그대로 '입혀보기' 다: 칸으로 데려가고, 아직 만든 사진이
         없고 넣은 옷이 있으면 바로 만든다. */
      if(m.fit){
        cpFitReveal(m);
        const ready=cpFitItems(m.fit).some(r=>r.image||r.imageUrl);
        if(!m.fit.loading&&!m.fit.result&&ready)cpGenerateFitMessage(m);
        return;
      }
      if(m.fitSaved){ m.fit=m.fitSaved; delete m.fitSaved; cpRenderThread(); cpFitReveal(m); return; }
      const aiIndex=c.messages.indexOf(m);
      const user=c.messages.slice(0,aiIndex).reverse().find(x=>x.role==='me');
      const images=(user&&user.images)||[];
      m.fit=cpNewFit(images,'');
      cpRenderThread();
      cpFitAutoSort(m);
      cpFitReveal(m);
    }
    return;
  }
  /* ③ 결과 사진 위 태그 — 누르면 그 상품 카드, 한 번 더 누르거나 사진을 누르면 닫는다. */
  const tag=e.target.closest('#cpThread [data-vf-tag]');
  if(tag){
    const m=cpAIMessageFor(tag); if(!m||!m.fit)return;
    const i=Number(tag.dataset.vfTag);
    m.fit.tagOpen=m.fit.tagOpen===i?-1:i;
    cpFitRender(m);
    return;
  }
  /* 결과 뒤 '다른 룩 추천' — 같은 상황으로 새 코디를 묻는다. 서버는 이 대화에서 보여 준
     상품과 근거 기사를 빼고 고른다(fit_memory). */
  const more=e.target.closest('#cpThread [data-vf-more]');
  if(more){
    const m=cpAIMessageFor(more); if(!m||!m.fit)return;
    const occ=String(m.fit.occasion||'').trim();
    const styles=(m.fit.styles||[]).join('·');
    const text=more.dataset.vfMore==='mood'
      ?(occ?occ+' ':'')+'코디를 다른 분위기로 추천해줘'+(styles?' ('+styles+' 말고)':'')
      :(occ?occ+' ':'')+'다른 룩도 추천해줘';
    cpAsk(text,cpKeyFor(text));
    return;
  }
  const tagClose=e.target.closest('#cpThread [data-vf-tagclose]');
  if(tagClose){
    const m=cpAIMessageFor(tagClose);
    if(m&&m.fit&&m.fit.tagOpen>=0){ m.fit.tagOpen=-1; cpFitRender(m); }
    return;
  }
  /* 왼쪽 설정 칸 접기·펼치기 (2026-10-01). 접힌 칸의 작은 네모를 눌러도 펼친다.
     종류 고르기 판은 같이 닫는다 — 접힌 칸에는 판을 띄울 자리가 없다. */
  const side=e.target.closest('#cpThread [data-vf-side]');
  if(side){
    const m=cpAIMessageFor(side); if(!m||!m.fit)return;
    m.fit.side=m.fit.side==='closed'?'open':'closed'; m.fit.kindOpen=-1;
    cpFitRender(m);
    return;
  }
  /* 모델 고르기 — Female / Male 두 장 중 하나 */
  const model=e.target.closest('#cpThread [data-vf-model]');
  if(model){
    const m=cpAIMessageFor(model); if(!m||!m.fit)return;
    const v=model.dataset.vfModel;
    if(VF_MODELS.some(x=>x.v===v)&&m.fit.model!==v){ m.fit.model=v; cpFitRender(m); }
    return;
  }
  /* 칸 아래 이름 — 그 칸의 종류 고르기 판을 열고 닫는다 */
  const kind=e.target.closest('#cpThread [data-vf-kind]');
  if(kind){
    const m=cpAIMessageFor(kind); if(!m||!m.fit)return;
    const i=Number(kind.dataset.vfKind);
    m.fit.kindOpen=(m.fit.kindOpen===i)?-1:i;
    cpFitRender(m);
    return;
  }
  /* 판에서 종류 하나 고르기 — Auto 면 서버가 사진을 보고 정한다.
     사용자가 직접 고른 종류는 auto 를 내려 두어야 프롬프트에 그 이름이 실린다. */
  const kindPick=e.target.closest('#cpThread [data-vf-kindpick]');
  if(kindPick){
    const m=cpAIMessageFor(kindPick); if(!m||!m.fit)return;
    const raw=String(kindPick.dataset.vfKindpick||''), cut=raw.indexOf('|');
    const item=cpFitItems(m.fit)[Number(raw.slice(0,cut))], k=raw.slice(cut+1);
    if(item){
      if(k===VF_AUTO){ item.auto=true }
      else if(VF_CATEGORIES.includes(k)){ item.category=k; item.auto=false }
    }
    m.fit.kindOpen=-1;
    cpFitRender(m);
    return;
  }
  /* 아우터 · 상의 Open ↔ Close — 버튼 하나를 누를 때마다 뒤집는다 */
  const flipBtn=e.target.closest('#cpThread [data-vf-flip]');
  if(flipBtn){
    const m=cpAIMessageFor(flipBtn); if(!m||!m.fit)return;
    const g=VF_OPTION_GROUPS.find(x=>x.kind==='slide'&&x.key===flipBtn.dataset.vfFlip&&x.cells.length===2);
    if(!g)return;
    const on=cpFitOptionsOf(m.fit);
    const now=cpSlideValue(on,g);
    cpSlideSet(on,g,g.cells.find(c=>c.v!==now).v);
    cpFitRender(m);
    return;
  }
  /* 켜고 끄는 스위치 — 지금은 아우터 레이어드 하나다. */
  const opt=e.target.closest('#cpThread [data-vf-opt]');
  if(opt){
    const m=cpAIMessageFor(opt); if(!m||!m.fit)return;
    const key=opt.dataset.vfOpt;
    const g=VF_OPTION_GROUPS.find(x=>x.kind==='switch'&&x.key===key); if(!g)return;
    const on=cpFitOptionsOf(m.fit);
    on[key]=!on[key];
    cpFitRender(m);
    return;
  }
  /* 고르기 묶음 (2026-10-01) — 핏 세 칸, 생성 엔진 두 칸. 누른 칸이 골라진다.
     ★ 같은 묶음 안의 이름은 고른 것 하나만 true 다(cpSlideSet) — 오버핏·슬림핏이
       같이 켜져 모순된 지시가 나가는 일이 생길 수 없다. */
  const cell=e.target.closest('#cpThread [data-vf-slide]');
  if(cell){
    const m=cpAIMessageFor(cell); if(!m||!m.fit)return;
    const key=cell.dataset.vfSlide, val=cell.dataset.vfVal;
    if(key==='engine'){
      if(m.fit.loading)return;                 /* 만드는 중에는 바꾸지 않는다 */
      if(!VF_ENGINES.some(x=>x.v===val))return;
      m.fit.engine=val;
    }else{
      const g=VF_OPTION_GROUPS.find(x=>x.kind==='slide'&&x.key===key); if(!g)return;
      if(!g.cells.some(c=>c.v===val))return;
      cpSlideSet(cpFitOptionsOf(m.fit),g,val);
    }
    cpFitRender(m);
    return;
  }
  /* 칸 한 개 늘리기 — 새 칸은 '자동 분류'로 시작한다 */
  const addSlot=e.target.closest('#cpThread [data-vf-add]');
  if(addSlot){
    const m=cpAIMessageFor(addSlot); if(!m||!m.fit)return;
    const rows=cpFitItems(m.fit);
    if(rows.length<VF_MAX)rows.push({category:VF_CATEGORIES[0],image:'',auto:true});
    cpFitRender(m);
    return;
  }
  /* 칸 빼기 — 사진만 지우는 것이 아니라 칸째로 뺀다 (2026-09-14).
     빈 칸이 남으면 ＋ 로 늘린 칸과 구별이 안 된다. 마지막 하나는 남겨 둔다 —
     칸이 아예 없으면 사진을 넣을 자리가 사라진다. */
  const remove=e.target.closest('#cpThread [data-vf-remove]');
  if(remove){
    const m=cpAIMessageFor(remove), index=Number(remove.dataset.vfRemove);
    if(m&&m.fit){
      const rows=cpFitItems(m.fit);
      if(rows[index]){
        if(rows.length>1)rows.splice(index,1);
        else{ rows[0].image=''; rows[0].imageUrl=''; rows[0].name=''; rows[0].brand='';
              rows[0].source=''; rows[0].sourceLabel=''; rows[0].url='';
              rows[0].category=VF_CATEGORIES[0]; rows[0].auto=true }
        m.fit.result=''; m.fit.status=''; m.fit.stateKind=''; cpFitRender(m);
      }
    }
    return;
  }
  const pick=e.target.closest('#cpThread [data-vf-pick]');
  if(pick){ const input=pick.closest('.cpFit').querySelector('[data-vf-file="'+pick.dataset.vfPick+'"]'); if(input)input.click(); return; }
  const generate=e.target.closest('#cpThread [data-vf-generate]');
  if(generate){ cpGenerateFit(generate); return; }
  /* 리포트 저장(PNG) · 공유 (2026-09-14) */
  /* 리포트 템플릿 (2026-10-02) — 티커 기간 전환 · 스토리 이미지 저장 */
  const tkRange=e.target.closest('#cpThread [data-tk-range]');
  if(tkRange){ tickerRange(tkRange); return; }
  /* 요금제 (2026-10-03) — 리포트 내보내기(이미지 저장 · 공유 · 스토리)는 프로부터.
     베타 동안 planGuard 는 언제나 통과한다. */
  const rpStory=e.target.closest('#cpThread [data-rp-story]');
  if(rpStory){ if(planGuard('report_export',cpToast))cpStorySave(rpStory); return; }
  const rpSave=e.target.closest('#cpThread [data-rp-save]');
  if(rpSave){ if(planGuard('report_export',cpToast))cpReportSave(rpSave); return; }
  const rpShare=e.target.closest('#cpThread [data-rp-share]');
  if(rpShare){ if(planGuard('report_export',cpToast))cpReportShare(rpShare); return; }
  /* 탭 리포트(구조안 02) — 서버 왕복 없이 그 카드 안에서만 전환한다. */
  const tb=e.target.closest('#cpThread [data-tab]');
  if(tb){
    const box=tb.closest('.tabreport'); if(!box)return;
    const key=tb.dataset.tab;
    box.querySelectorAll('.rpTabBtn').forEach(x=>x.classList.toggle('on', x===tb));
    box.querySelectorAll('.rpTabPanel').forEach(x=>x.classList.toggle('on', x.dataset.panel===key));
    return;
  }
});
/* 고치는 칸의 글쇠 — 챗바와 같은 규칙으로 둔다.
   Enter 저장 · Shift+Enter 줄바꿈 · Esc 취소. 한글 조합 중의 Enter 는
   흘려보낸다(챗바와 같은 이유 — 마지막 자모가 따로 떨어져 나간다). */
document.addEventListener('keydown',e=>{
  const box=e.target.closest&&e.target.closest('#cpThread [data-edit-in]'); if(!box)return;
  const idx=Number(box.dataset.editIn);
  /* ★ stopPropagation 으로는 모자란다 — 팝업을 닫는 Esc 처리기도 document 에
     붙어 있어서, 같은 노드의 다른 처리기까지 막는 stopImmediatePropagation 이
     필요하다. 이게 없으면 고치다 Esc 를 누를 때 대화창이 통째로 닫힌다.
     (이 파일이 router.js 보다 먼저 실행되므로 이 처리기가 먼저 걸린다 —
      router.js 4번 줄에서 이 파일을 import 한다.) */
  if(e.key==='Escape'){ e.preventDefault(); e.stopImmediatePropagation(); cpEditCancel(idx); return; }
  if(e.isComposing||e.keyCode===229)return;
  if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); cpEditSave(idx); }
});
document.addEventListener('change',async e=>{
  const file=e.target.closest('#cpThread [data-vf-file]');
  if(file){
    const m=cpAIMessageFor(file), picked=file.files&&file.files[0]; if(!m||!m.fit||!picked)return;
    const index=Number(file.dataset.vfFile);
    /* 새로 넣은 사진은 Auto 로 시작한다 (2026-10-01) — 예전엔 auto 를 내려 버려서,
       칸이 처음 받은 이름('상의')이 사진과 상관없이 그대로 프롬프트에 실렸다.
       Auto 면 서버가 사진을 보고 정하고, 틀리면 칸 아래 이름을 눌러 고친다. */
    try{ const item=cpFitItems(m.fit)[index]; item.image=await imageFileToDataURL(picked); item.imageUrl=''; item.name=''; item.brand=''; item.source=''; item.sourceLabel=''; item.url=''; item.auto=true; m.fit.kindOpen=-1; m.fit.result=''; m.fit.status=''; m.fit.stateKind=''; }
    catch(_err){ m.fit.status='이미지를 읽지 못했습니다.'; m.fit.stateKind='error'; }
    cpFitRender(m);
  }
});
async function cpGenerateFit(button){
  const m=cpAIMessageFor(button); if(!m||!m.fit||m.fit.loading)return;
  return cpGenerateFitMessage(m);
}
async function cpGenerateFitMessage(m){
  if(!m||!m.fit||m.fit.loading)return;
  /* 자동 분류가 돌고 있으면 끝난 뒤에 만든다 — 칸이 정해진 다음이라야
     프롬프트에 "2번째 이미지는 하의" 처럼 제대로 실린다. (2026-09-13) */
  if(m.fit._sort){ try{ await m.fit._sort }catch(e){ /* 분류 실패는 넘어간다 */ } }
  if(!m.fit||m.fit.loading)return;
  const rows=cpFitItems(m.fit);
  /* 보낸 순서 → 칸 번호. 결과의 태그(index)는 보낸 순서로 온다. */
  const sent=rows.map((item,i)=>i).filter(i=>rows[i].image||rows[i].imageUrl);
  const items=sent.map(i=>rows[i]).map(item=>({
      ...(item.image?{image:item.image}
        /* 서버가 고른 상품 사진 — 주소만 보낸다. 받는 쪽은 vton._items 다. */
        :{image_url:item.imageUrl}),
      category:item.auto?VF_AUTO:item.category,
      /* 이름 — 결과 사진에서 이 옷 자리를 찾을 때(vton.locate) 쓴다 */
      name:item.name||''}));
  /* 결과 사진 위 태그는 판매처가 있는 상품이 있을 때만 — vision 이 한 번 더 든다. */
  const wantTags=sent.some(i=>cpFitIsShop(rows[i]));
  if(!items.length){ m.fit.status='아이템 사진이 하나 이상 필요합니다.'; m.fit.stateKind='error'; cpFitRender(m); return; }
  m.fit.loading=true; m.fit.status=''; m.fit.stateKind='loading'; m.fit.made=null;
  m.fit.tags=[]; m.fit.tagOpen=-1; cpFitRender(m);
  try{
    const engine=cpFitEngineOf(m.fit);
    const t0=Date.now();
    const res=await fetch(API_BASE+'/v1/virtual-fitting',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({items,model_id:m.fit.model,options:cpFitOptionsOf(m.fit),engine,
                           tags:wantTags})});
    const raw=await res.text();
    let data;
    try{ data=JSON.parse(raw); }
    catch(_parseError){ throw new Error('입혀보기 서버 응답을 확인하지 못했습니다. 배포 설정을 확인해 주세요.'); }
    if(!res.ok||!data.ok)throw new Error(data.message||'착용 이미지를 만들지 못했습니다.');
    m.fit.result=data.image; m.fit.format=data.format||''; m.fit.status=''; m.fit.stateKind='success';
    m.fit.size=String(data.size||'');
    m.fit.tags=(Array.isArray(data.tags)?data.tags:[])
      .filter(t=>t&&Number.isInteger(t.index)&&sent[t.index]!==undefined&&isFinite(t.x)&&isFinite(t.y))
      .map(t=>({item:sent[t.index],x:+t.x,y:+t.y}));
    /* 서버가 실제로 쓴 엔진을 따른다 — 옛 서버는 engine 을 모르니 Sunburst 로 만든다.
       시간은 화면이 기다린 시간(중계·전송 포함)이다. 사용자가 느끼는 시간이 그것이다. */
    const used=VF_ENGINES.find(e=>e.v===data.engine)||VF_ENGINES.find(e=>e.v===VF_DEFAULT_ENGINE);
    m.fit.made={engine:used.v,label:used.label+' ('+used.name+')',
                sec:Math.max(1,Math.round((Date.now()-t0)/1000))};
    /* 결과 아래 '다른 룩도 볼까요?' 를 대화 기록에도 남긴다 — "응" 만 쳐도 이어진다 */
    if(m.fit.fromServer){
      m.turn=m.turn||{q:'이 코디로 입혀보기',intent:'agent',terms:[]};
      m.turn.next=cpFitNextQuestion(m.fit);
    }
  }catch(err){ m.fit.status=(err&&err.message)||'착용 이미지를 만들지 못했습니다.'; m.fit.stateKind='error'; }
  m.fit.loading=false; cpFitRender(m);
}
/* 피드백 한 번. '아쉬움' 은 사유를 고르는 줄로 한 번 더 열린다.
   보내기에 실패해도 화면은 고맙다고 답한다 — 사용자가 할 수 있는 일이 없다. */
function cpFeedback(idx,verdict,reason){
  const c=cpActiveConvo(); if(!c)return;
  const m=c.messages[idx]; if(!m)return;
  if(verdict==='down'&&!reason){ m.fbOpen=true; cpRenderThread(); return; }
  delete m.fbOpen;
  m.feedback=verdict;
  cpRenderThread(); cpSave();
  const user=c.messages.slice(0,idx).reverse().find(x=>x.role==='me');
  sendAnswerFeedback({verdict, reason:reason||'', mode:cpMode(),
    question:(user&&user.text)||'', intent:(m.turn&&m.turn.intent)||''});
}

/* 등록 요청 버튼 — 누른 즉시 잠그고(중복 전송 방지), 서버가 답하면 결과를 말한다.
   "누르면 되는 척" 을 하지 않는다(server.py 주석) — 실패해도 실패라고 말한다. */
async function cpSendLexiconRequest(btn){
  if(btn.disabled)return;
  const surface=btn.dataset.surface||'', question=btn.dataset.question||'';
  btn.disabled=true; btn.textContent='요청하는 중…';
  try{
    const r=await requestLexicon(surface, question);
    btn.textContent=(r&&r.surface?'"'+r.surface+'" ':'')+'등록 요청 완료';
  }catch(e){
    btn.textContent='요청 실패 — 잠시 후 다시 시도해 주세요';
    btn.disabled=false;
  }
}

/* ══════════════════════════════════════════════════════
   2026-09-14 추가 — 복사 · 알림 한 줄 · 리포트 저장/공유
   ══════════════════════════════════════════════════════ */

/* 클립보드. 보안 컨텍스트가 아니면(예: http 로 연 로컬 화면) Clipboard API 가
   없으므로 옛 방식으로 한 번 더 시도한다. 성공 여부를 그대로 돌려준다 —
   부르는 쪽이 "복사했습니다" 를 거짓으로 말하지 않게. */
async function cpCopyText(text){
  const value=String(text||'');
  if(!value)return false;
  try{
    if(navigator.clipboard&&window.isSecureContext){ await navigator.clipboard.writeText(value); return true }
  }catch(_e){ /* 아래 옛 방식으로 */ }
  try{
    const ta=document.createElement('textarea');
    ta.value=value; ta.setAttribute('readonly','');
    ta.style.cssText='position:fixed;top:-1000px;opacity:0';
    document.body.appendChild(ta); ta.select();
    const ok=document.execCommand('copy'); ta.remove(); return ok;
  }catch(_e){ return false }
}
/* 눌린 버튼이 스스로 "됐다" 고 말한다 — 화면을 다시 그리지 않는다(누른 자리가
   사라지면 무엇이 일어났는지 알 수 없다). */
function cpFlashBtn(btn){
  if(!btn)return;
  btn.classList.add('done');
  setTimeout(()=>btn.classList.remove('done'),1300);
}
let cpToastT=0;
function cpToast(text){
  const ov=$('#cpOverlay'); if(!ov)return;
  let box=$('#cpToast');
  if(!box){ box=document.createElement('div'); box.id='cpToast'; box.className='cpToast'; ov.appendChild(box); }
  box.textContent=String(text||'');
  box.classList.add('on');
  clearTimeout(cpToastT);
  cpToastT=setTimeout(()=>box.classList.remove('on'),2200);
}
/* 답변 본문(서버가 보낸 HTML)에서 글만 꺼낸다 — 공유는 태그가 아니라 말이다. */
function cpPlainText(html){
  const box=document.createElement('div');
  box.innerHTML=String(html||'');
  return (box.textContent||'').replace(/\n{3,}/g,'\n\n').trim();
}
/* 리포트 카드를 그림으로. html2canvas 는 누를 때 처음 불러온다 —
   쓰지 않는 사용자에게까지 번들을 지우지 않기 위해서다. */
/* 리포트 카드를 이미지로 뜬다.
   ★ 2026-09-18 — html2canvas → html-to-image.
     html2canvas 는 CSS 를 스스로 다시 해석하는데, 리포트 카드가 쓰는 color-mix() 를
     모른다. 만나면 예외를 던져서 저장·공유가 한 번도 된 적이 없었다
     ("리포트 이미지를 만들지 못했습니다"). html-to-image 는 브라우저가 그린 그대로를
     SVG 로 감싸 뜨므로 color-mix · 웹폰트 · 그림자까지 화면과 같게 나온다. */
async function cpReportCanvas(card){
  const { toCanvas } = await import('html-to-image');
  return toCanvas(card,{
    backgroundColor:'#ffffff',
    pixelRatio:Math.min(2,window.devicePixelRatio||1),
    cacheBust:true,
    /* 다른 사이트 상품 사진이 CORS 로 막혀도 통째로 실패하지 않게 빈 칸으로 둔다 */
    imagePlaceholder:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=',
    /* 저장·공유 · 스토리 버튼 자체는 그림에 넣지 않는다 */
    filter:el=>!(el&&el.classList&&(el.classList.contains('rpTools')||el.classList.contains('tplStoryBtn'))),
  });
}
const cpCanvasBlob=canvas=>new Promise(done=>canvas.toBlob(done,'image/png'));
/* 스토리 이미지 (2026-10-02) — 티커 값으로 9:16 카드를 화면 밖에 그려 1080×1920 PNG 로 저장한다.
   ★ 카드 그림을 따로 들고 다니지 않는다 — 버튼이 들고 있는 값(서버 블록 그대로)으로 그때 그린다.
   ★ 화면 밖 자리는 저장이 끝나면 바로 걷는다. 남겨 두면 다음 캡처에 끼어든다. */
async function cpStorySave(btn){
  if(btn.disabled)return;
  let data=null;
  try{ data=JSON.parse(btn.dataset.rpStory||'null') }catch(_e){ data=null }
  const html=data?storyHTML(data):'';
  if(!html){ cpToast('스토리 이미지를 만들 값이 없습니다.'); return; }
  btn.disabled=true;
  const stage=document.createElement('div');
  stage.className='tkStoryStage'; stage.setAttribute('aria-hidden','true');
  stage.innerHTML=html;
  document.body.appendChild(stage);
  try{
    const { toCanvas } = await import('html-to-image');
    const canvas=await toCanvas(stage.firstElementChild,{backgroundColor:'#1c1a17',pixelRatio:3,cacheBust:true});
    const blob=await cpCanvasBlob(canvas);
    if(!blob)throw new Error('empty');
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url; a.download='feedit-story-'+Date.now().toString(36)+'.png';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),4000);
    cpToast('스토리 이미지를 저장했습니다.');
  }catch(_e){ cpToast('스토리 이미지를 만들지 못했습니다.'); }
  stage.remove();
  btn.disabled=false;
}
async function cpReportSave(btn){
  const card=btn.closest('.skillReport'); if(!card||btn.disabled)return;
  btn.disabled=true;
  try{
    const blob=await cpCanvasBlob(await cpReportCanvas(card));
    if(!blob)throw new Error('empty');
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;
    a.download='feedit-report-'+Date.now().toString(36)+'.png';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),4000);
    cpFlashBtn(btn); cpToast('리포트를 이미지로 저장했습니다.');
  }catch(_e){ cpToast('리포트 이미지를 만들지 못했습니다.'); }
  btn.disabled=false;
}
/* 공유 — 리포트를 **이미지째** 넘긴다 (2026-09-18).
   예전에는 이미지를 못 만들어(cpReportCanvas 주석) 결국 답변 글 + 현재 주소를 복사했는데,
   그 주소는 홈페이지일 뿐 리포트로 가는 링크가 아니었다. 리포트는 로그인한 사람의 대화
   안에만 있어서 남이 열 수 있는 주소가 없다 — 그래서 주소 대신 이미지를 보낸다.
     ① 모바일 등 파일 공유가 되면 공유 시트로 이미지 + 글
     ② 아니면 클립보드에 이미지(+글) — 카톡·슬랙에 붙여 넣으면 그림이 들어간다
     ③ 그것도 안 되면 글만 복사 */
async function cpReportShare(btn){
  const card=btn.closest('.skillReport'); if(!card||btn.disabled)return;
  const m=cpAIMessageFor(btn);
  const text=cpPlainText(m&&m.html);
  btn.disabled=true;
  let blob=null;
  try{ blob=await cpCanvasBlob(await cpReportCanvas(card)) }catch(_e){ blob=null }
  try{
    if(blob&&navigator.share&&navigator.canShare){
      const file=new File([blob],'feedit-report.png',{type:'image/png'});
      if(navigator.canShare({files:[file]})){
        await navigator.share({files:[file],title:'FEEDiT 리포트',text});
        btn.disabled=false; return;
      }
    }
  }catch(err){
    if(err&&err.name==='AbortError'){ btn.disabled=false; return; }   /* 공유 시트를 닫았다 */
  }
  if(blob&&navigator.clipboard&&window.ClipboardItem){
    for(const parts of [{'image/png':blob,'text/plain':new Blob([text],{type:'text/plain'})},
                        {'image/png':blob}]){
      try{
        await navigator.clipboard.write([new ClipboardItem(parts)]);
        cpFlashBtn(btn); cpToast('리포트 이미지를 복사했습니다. 붙여 넣어 공유하세요.');
        btn.disabled=false; return;
      }catch(_e){ /* 이 조합을 못 받는 브라우저 — 다음으로 */ }
    }
  }
  const ok=text?await cpCopyText(text):false;
  if(ok)cpFlashBtn(btn);
  cpToast(ok?'리포트 이미지를 만들지 못해 답변 글만 복사했습니다.':'공유하지 못했습니다.');
  btn.disabled=false;
}

/* ★ 2026-09-19 — 계정이 바뀌면 열려 있는 대화창도 그 자리에서 새 계정 기록으로 갈아 끼운다.
   (닫혀 있을 때는 openChatPopup 이 열 때 맞춘다) */
document.addEventListener('feedit:auth',()=>{
  if(!cpSyncOwner())return;
  const ov=$('#cpOverlay');
  if(ov&&ov.classList.contains('on')){ cpPaintProfile(); cpRenderList(); cpRenderThread(); void cpHydrate(); }
});
