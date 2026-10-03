import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aTimeline, aUtils } from '../../../core/static/js/dom.js';
import { AUTH, acctBoot, dropPendingAuth, likeClick, myRender, requireAuth, resetSignupForm } from '../../../account/static/js/profile.js';
import { SM_ON, hotBuild, mImgInit, newChat, qRoll, sendChat, smSwitch } from '../../../home/static/js/chat.js';
import { closeChatPopup, cpCloseMenu, cpImgInit, cpNewConvo, cpOpenMenu, cpRenderList, cpRenderThread, cpSave, cpSend, cpStore, cpToggleMode, openChatWith, openVirtualTryOn } from '../../../home/static/js/chat_popup.js';
import { mPaintVote, mVote, smBuild } from '../../../salmal/static/js/nav_widget.js';
import { prBuild } from '../../../pricing/static/js/pricing.js';
import { renderDeck } from '../../../intro/static/js/deck.js';
import { salmalBoot } from '../../../salmal/static/js/vote_app.js';
import { stBuild, stOpen, stOpenFit } from '../../../style/static/js/style_page.js';
import { trBuild, trRender } from '../../../trend/static/js/dispatch.js';

/* ============================================================
   메인 랜딩 페이지
   레퍼런스: https://pamidordesign.com — 오프화이트 지면, 큰 선언문,
   스크롤을 따라 한 단어씩 물드는 문단, 검정 알약 버튼.
   ============================================================ */
export var mainMode=false, mainReady=false, curView='home';

/* ── 브라우저 뒤로가기 ─────────────────────────────────
   화면이 바뀔 때마다 히스토리 항목을 쌓아 두고(pushNav), popstate 로 그
   항목을 다시 읽어 같은 화면 · 같은 탭 · 같은 스타일로 복원한다.
   navSkip 은 popstate 로 인한 복원 자체가 새 히스토리 항목을 또 쌓는 걸
   막는 플래그다. */
let curTr='myfeed', curStyleId=null, navSkip=false, viewSeq=0;
function navState(){
  return { view:curView, tr:curView==='trend'?curTr:null, style:curView==='style'?curStyleId:null };
}
/* ★ 새로고침해도 보던 화면 그대로 — 지금 화면을 세션에 적어 둔다.
   (탭을 닫으면 지워지므로 다음에 새로 들어오면 인트로부터 본다) */
const NAV_KEY='feedit.nav.v1';
/* ★ 2026-09-21 — 인트로(로딩 + 설명 페이지)는 **평생 한 번**이다.
   세션 열쇠(NAV_KEY)는 탭을 닫으면 지워져 다음에 또 인트로부터 봤다.
   한 번 본문까지 들어온 사람은 브라우저에 표시를 남겨, 다음에 들어와도
   곧장 홈 화면으로 떨어진다. (intro/loader.js 의 boot 이 같은 열쇠를 본다) */
export const SEEN_KEY='feedit.introSeen.v1';
export function introSeen(){
  try{ return localStorage.getItem(SEEN_KEY)==='1' }catch(e){ return false }
}
function markIntroSeen(){
  try{ localStorage.setItem(SEEN_KEY,'1') }catch(e){}
}
function saveNav(){
  if(!mainMode)return;
  try{ sessionStorage.setItem(NAV_KEY,JSON.stringify(navState())) }catch(e){}
}
function pushNav(){
  saveNav();
  if(navSkip){ navSkip=false; return }
  if(!mainMode)return;   /* 랜딩(인트로) 단계에서는 기록하지 않는다 */
  history.pushState(navState(), '', location.href);
}

/* ── 히어로 등장 ────────────────────────────────────── */
function mHeroIn(){
  const wds=$$('#mState .wd'); if(!HAS_A||!wds.length)return;
  aUtils.set(wds,{opacity:0,translateY:'104%'});
  aUtils.set(['.mKicker','.heroL p','.hot','.chatWrap','.chips'],{opacity:0});
  const t=aTimeline();
  t.add('.mKicker', {opacity:[0,1],translateY:[12,0],duration:700,ease:'out(3)'},0)
   .add(wds,{opacity:[0,1],translateY:['104%','0%'],duration:1080,delay:aStagger(70),
      ease:aSpring({stiffness:72,damping:16})},110)
   .add('.hot',      {opacity:[0,1],translateY:[-14,0],duration:860,
      ease:aSpring({stiffness:80,damping:16})},520)
   .add('.heroL p',  {opacity:[0,1],translateY:[16,0],duration:820,ease:'out(3)'},640)
   .add('.chatWrap', {opacity:[0,1],translateY:[18,0],duration:900,
      ease:aSpring({stiffness:78,damping:16})},680)
   .add('.chips',    {opacity:[0,1],translateY:[14,0],duration:800,ease:'out(3)'},860);
  setTimeout(()=>{ const em=$('#mState em'); if(em)em.classList.add('ul') },1050);
}
function mHeroSettle(){
  const els=[...$$('#mState .wd'),...$$('#v-home .mKicker, #v-home .heroL p, #v-home .hot, #v-home .chatWrap, #v-home .chips')];
  if(HAS_A)aUtils.remove(els);
  els.forEach(el=>{ el.style.opacity=''; el.style.transform=''; el.style.translate='' });
}

/* ── 트렌드 분석 사이드바 ────────────────────────────
   토글 버튼과 뷰 진입이 같은 함수를 쓴다. 상태가 갈리지 않게. */
export function trSideOpen(on){
  const sd=$('#side'), wr=$('.trWrap');
  if(!sd)return;
  sd.classList.toggle('open',on);
  if(wr)wr.classList.toggle('open',on);
  const toggle=$('#sToggle');
  if(toggle){
    toggle.setAttribute('aria-expanded',String(!!on));
    toggle.setAttribute('aria-label',on?'사이드바 접기':'사이드바 펼치기');
  }
}
const trWide=()=>typeof matchMedia!=='function'||!matchMedia('(max-width:920px)').matches;
window.addEventListener('resize',()=>{ if(!trWide())trSideInstant(false) });
/* 접힌 상태로 되돌리되 폭이 줄어드는 장면은 보이지 않게 — 전환을 한 프레임 끈다 */
function trSideInstant(on){
  const sd=$('#side'), wr=$('.trWrap');
  if(!sd)return;
  sd.classList.add('noTr'); if(wr)wr.classList.add('noTr');
  trSideOpen(on);
  void sd.offsetWidth;
  sd.classList.remove('noTr'); if(wr)wr.classList.remove('noTr');
}
function trSideReset(){ trSideInstant(false) }

/* ── 뷰 라우터 ──────────────────────────────────────── */
export function goView(v,fromTopNav=false){
  if(!v)return;
  /* ★ 없는 화면으로는 가지 않는다.
     아래 `$$('.view').forEach(s=>s.classList.toggle('on', s.id==='v-'+v))` 는
     맞는 게 없으면 **모든 화면을 끔다** — 그게 공백 페이지였다.
     예전에 세부 검색 팝업의 필터 버튼이 data-v="스트릿" 을 달고 있어
     아래 전역 클릭 위임이 goView('스트릿') 을 불렀고, 그 순간
     화면이 통째로 비었다. 버튼 손 data-v 는 data-fv 로 바꿨지만,
     같은 사고가 다시 나지 않게 여기서도 막는다. */
  if(!document.getElementById('v-'+v)){
    if(window.console&&console.warn)console.warn('[router] 없는 화면입니다:',v);
    return;
  }
  if(v===curView){
    if(fromTopNav){
      const current=$('#v-'+v);
      if(HAS_A)aUtils.remove(current);
      current.style.opacity=''; current.style.transform='';
    }
    /* 스타일 탭에서 상세 화면에 들어가 있을 때 스타일 탭을 다시 누르면
       그 자리에 머무르지 않고 스타일 목록 처음 화면으로 되돌아간다 —
       이때도 처음 진입할 때와 똑같이 네비 아이콘이 튀고 화면이 살짝
       떠오르며 나타나는 모션을 그대로 태운다 (정적으로 뚝 끊기지 않게) */
    if(v==='style'){
      $('#styleDetail').style.display='none'; $('#styleHome').style.display='';
      const nb=$$('#mNav button').filter(b=>b.dataset.v===v)[0];
      if(HAS_A&&nb)aAnimate($('span',nb),{translateY:[-3,0],duration:560,
        ease:aSpring({stiffness:150,damping:12})});
      const el=$('#v-style');
      if(HAS_A&&el&&!fromTopNav){
        el.style.transform='';
        aAnimate(el,{opacity:[0,1],translateY:[14,0],duration:640,ease:'out(3)',
          onComplete:()=>{ el.style.transform='' }});
      }
    }
    scrollTo(0,0);
    return;
  }
  const analysisSwitch=(curView==='trend'&&v==='salmal')||(curView==='salmal'&&v==='trend');
  const seamless=fromTopNav||analysisSwitch;
  const seq=++viewSeq;
  /* 상단 탭과 분석 화면 왕복은 진행 중인 화면 전체 모션을 끊는다.
     숨겼던 화면의 opacity:0 이 다음 진입까지 남으면 렉처럼 깜빡인다. */
  if(seamless&&HAS_A){
    const views=[document.getElementById('v-'+curView),document.getElementById('v-'+v)];
    aUtils.remove(views);
    views.forEach(view=>{ if(view){ view.style.opacity=''; view.style.transform='' } });
  }
  if(curView==='signup'&&v!=='signup')resetSignupForm();   /* 완료 안 하고 나가면 다음엔 처음 상태로 */
  /* 로그인/가입 화면을 그냥 벗어났다 — 관문에 걸려 들고 있던 질문도 여기서 버린다.
     한참 뒤에 로그인했을 때 잊고 있던 질문이 저절로 보내지면 안 된다. (2026-09-13) */
  if((curView==='login'||curView==='signup')&&v!=='login'&&v!=='signup'&&!AUTH.in)
    dropPendingAuth();
  curView=v;
  $$('#mNav button').forEach(b=>b.classList.toggle('on',b.dataset.v===v));
  document.body.classList.toggle('acctmode',v==='login'||v==='signup'||v==='mypage');
  $$('.view').forEach(s=>s.classList.toggle('on',s.id==='v-'+v));
  scrollTo(0,0);
  const nb=$$('#mNav button').filter(b=>b.dataset.v===v)[0];
  if(HAS_A&&nb)aAnimate($('span',nb),{translateY:[-3,0],duration:560,
    ease:aSpring({stiffness:150,damping:12})});
  const el=$('#v-'+v);
  /* 끝나면 transform 을 지운다 — 남겨두면 안쪽 position:fixed 가 뷰 기준이 된다.
     트렌드 분석은 고정 사이드바가 있어 transform 을 아예 쓰지 않는다. */
  if(HAS_A&&el&&!seamless){
    if(v==='trend')aAnimate(el,{opacity:[0,1],duration:520,ease:'out(3)'});
    else aAnimate(el,{opacity:[0,1],translateY:[14,0],duration:640,ease:'out(3)',
      onComplete:()=>{ el.style.transform='' }});
  }
  document.body.classList.toggle('athome',v==='home');
  document.body.dataset.view=v;
  if(v==='home'){
    if(fromTopNav)mHeroSettle();
    else if(!$('#v-home').classList.contains('asking'))mHeroIn();
  }
  if(v==='style'){ $('#styleDetail').style.display='none'; $('#styleHome').style.display='' }
  if(v==='salmal'){
    const first=!window.__smOn;
    if(first){ window.__smOn=1; try{ salmalBoot() }catch(e){} }
    else if(window.smFeedbackPrompt){ try{ window.smFeedbackPrompt() }catch(e){} }
    /* 어느 탭에서 시작할지 지정돼 있으면 그쪽에서 다시 그리며 모션까지 태운다.
       첫 진입이든 아니든 반드시 반영한다 — 예전엔 첫 진입일 때 흘려버려서
       내 피드에서 넘어와도 '내 취향' 표시가 안 붙었다.
       탭 이동과 재생을 둘 다 돌리면 같은 막대에 애니메이션이 두 번 걸리므로 하나만 돌린다. */
    if(window.__smWant&&window.smGoTab){
      const want=window.__smWant; window.__smWant=null;
      if(seamless){ try{ window.smGoTab(want) }catch(e){} }
      else setTimeout(()=>{ if(seq===viewSeq&&curView==='salmal')try{ window.smGoTab(want) }catch(e){} },first?280:90);
    }
    else if(!first&&window.smReplay&&!seamless)
      setTimeout(()=>{ if(seq===viewSeq&&curView==='salmal')try{ window.smReplay() }catch(e){} },90);
  }
  if(v==='mypage'){
    /* ★ 2026-09-22 — 로그인 복구가 끝나기 전에는 튕기지 않는다.
       새로고침하면 이 화면이 복구보다 먼저 서기 때문에, 그 찰나의
       AUTH.in=false 로 로그인 화면으로 넘기면 로그인한 사람이 튕겼다.
       복구가 끝나면 아래 feedit:auth 에서 다시 판정한다. */
    if(AUTH.ready&&!AUTH.in){ setTimeout(()=>goView('login'),0); return }
    myRender();
  }
  /* 트렌드 분석 — 들어올 때마다 내 피드에서 다시 시작하고,
     사이드바는 접힌 상태에서 스르륵 열리며 화면이 전개된다.
     로그인 전에는 곧장 로그인 화면으로 튕기지 않는다 — 내 피드 화면은 뒤에
     그대로 두고 흐릿하게 가린 뒤 그 위에 로그인 안내 팝업만 띄운다. */
  if(v==='trend'){
    trendGateSync();
    window.__trOn=1;
    window.__trEnterAt=Date.now();     /* 사이드바 전환과 겹치지 않게 재는 기준점 */
    const startTr=window.__trWant||'myfeed'; window.__trWant=null;
    const reuseTr=seamless&&curTr===startTr&&!!$('#trBody').childElementCount;
    curTr=startTr;
    $$('.sItem').forEach(x=>x.classList.toggle('on',x.dataset.tr===startTr));
    if(seamless){
      /* 상단 탭에서 돌아올 때는 기존 내 피드 DOM을 유지한다.
         매번 다시 그리면 카드가 0% 투명도로 돌아갔다 나타난다. */
      trSideInstant(trWide());
      if(!reuseTr)trRender(startTr);
    }else{
      trSideReset();                     /* 첫 진입에서는 기존 사이드바 모션 유지 */
      setTimeout(()=>{ if(seq===viewSeq&&curView==='trend')trRender(startTr) },130);
      setTimeout(()=>{ if(seq===viewSeq&&curView==='trend')trSideOpen(trWide()) },240);
    }
  }
  trendGateSync();   /* 트렌드를 벗어나면 관문도 같이 내린다 */
  pushNav();
}
/* ── 트렌드 분석 관문 ──────────────────────────────────
   ★ 2026-09-22 — 로그인한 채 새로고침하면 '로그인이 필요합니다' 팝업이 떴다.
     resumeNav 가 보던 화면을 그 자리에서 바로 세우는데, 로그인 복구
     (/api/me)는 그보다 늦게 끝난다. 그 사이의 AUTH.in=false 를 '로그아웃'
     으로 읽은 것이다. 게다가 복구가 끝나도 다시 판정하는 곳이 없어서,
     한번 뜬 팝업은 화면을 옮겼다 오기 전까지 그대로 남았다.
     ① 복구가 끝나기 전(AUTH.ready=false)에는 세우지 않는다.
     ② 복구가 끝나면(feedit:auth) 여기서 한 번 더 판정한다. */
function trendGateSync(){
  const g=$('#trendGateModal'); if(!g)return;
  g.classList.toggle('on', curView==='trend'&&AUTH.ready&&!AUTH.in);
}
/* feedit:auth = 계정이 바뀌었다 · feedit:auth-ready = 복구가 끝났다(상태는 그대로).
   관문은 둘 다에서 다시 판정한다. */
['feedit:auth','feedit:auth-ready'].forEach(ev=>document.addEventListener(ev,()=>{
  trendGateSync();
  /* 복구해 보니 정말 로그아웃이었다면 그때 로그인 화면으로 보낸다 */
  if(curView==='mypage'&&AUTH.ready&&!AUTH.in)goView('login');
}));

function goStyle(id){
  curView='style'; curStyleId=id;
  document.body.classList.remove('athome');
  $$('#mNav button').forEach(b=>b.classList.toggle('on',b.dataset.v==='style'));
  $$('.view').forEach(s=>s.classList.toggle('on',s.id==='v-style'));
  stOpen(id);
  pushNav();
}

/* ── 조립 ───────────────────────────────────────────── */
(function buildMain(){
  $$('#mState .ln').forEach(ln=>{
    const parts=[...ln.childNodes]; ln.innerHTML='';
    parts.forEach(node=>{
      if(node.nodeType===3){
        node.textContent.split(/(\s+)/).forEach(tk=>{
          if(!tk)return;
          if(/^\s+$/.test(tk)){ ln.appendChild(document.createTextNode(' ')); return }
          const s=document.createElement('span'); s.className='wd'; s.textContent=tk; ln.appendChild(s);
        });
      }else{ const s=document.createElement('span'); s.className='wd'; s.appendChild(node); ln.appendChild(s) }
    });
  });
  hotBuild(); trBuild(); smBuild(); stBuild(); prBuild(); mPaintVote(); acctBoot(); mImgInit(); cpImgInit();
})();

/* ── 상호작용 ───────────────────────────────────────── */
document.addEventListener('click',e=>{
  const like=e.target.closest('[data-like-id]');
  if(like)return likeClick(like);
  const product=e.target.closest('[data-product-url]');
  if(product){
    window.open(product.dataset.productUrl,'_blank','noopener,noreferrer');
    return;
  }
  const fit=e.target.closest('[data-fit-style]');
  if(fit)return stOpenFit(fit.dataset.fitStyle);
  const nav=e.target.closest('#mNav button'); if(nav)return goView(nav.dataset.v,true);
  const st=e.target.closest('[data-style]');
  if(st&&st.dataset.style)return goStyle(st.dataset.style);
  const v=e.target.closest('[data-v]');
  /* data-sm 이 붙어 있으면 살!말? 로 갈 때 지정한 탭에서 시작한다. */
  if(v){
    /* 로그인·회원가입 링크는 href="#" 를 갖는다. 기본 앵커 이동을 그대로 두면
       goView 가 pushState 한 직후 빈 hash 기록이 하나 더 생기고, popstate 가 그
       기록을 인트로로 해석해 설명 화면으로 되돌린다. SPA 전환만 실행한다. */
    e.preventDefault();
    if(v.dataset.sm)window.__smWant=v.dataset.sm;
    return goView(v.dataset.v);
  }
  const tr=e.target.closest('[data-tr]');
  if(tr){ $$('.sItem').forEach(x=>x.classList.remove('on')); tr.classList.add('on');
          curTr=tr.dataset.tr; pushNav();
          /* 좁은 화면(920px 이하, responsive.css)에서는 메뉴를 고르면 사이드바를 접어 본문을 가리지 않는다 */
          if(!trWide()&&tr.classList.contains('sItem'))trSideOpen(false);
          return trRender(tr.dataset.tr) }
  const vt=e.target.closest('[data-vote]'); if(vt)return mVote(vt.dataset.vote);
});

document.addEventListener('keydown',e=>{
  if(e.key!=='Enter'&&e.key!==' ')return;
  const salmalCard=e.target.closest&&e.target.closest('[data-v="salmal"][data-sm]');
  if(salmalCard){ e.preventDefault(); salmalCard.click(); return; }
  const product=e.target.closest&&e.target.closest('[data-product-url]');
  if(!product)return;
  e.preventDefault();
  window.open(product.dataset.productUrl,'_blank','noopener,noreferrer');
});
$('#mHome')&&$('#mHome').addEventListener('click',()=>goView('home'));
/* #chatFab 은 전역 도움말 허브의 펼침 버튼으로 바뀌었다.
   챗봇 열기는 assistant_hub.js 의 '챗봇' 메뉴가 맡는다. */
$('#mSend')&&$('#mSend').addEventListener('click',sendChat);
/* 살!말? 버튼은 이제 뷰 이동이 아니라 모드 전환이다 */
$('#smToggle')&&$('#smToggle').addEventListener('click',e=>{ e.stopPropagation(); smSwitch(!SM_ON,e) });
$('#newChat')&&$('#newChat').addEventListener('click',newChat);
$('#mInput')&&$('#mInput').addEventListener('input',e=>{
  $('#ghostQ').classList.toggle('hide',!!e.target.value) });
$('#mInput')&&$('#mInput').addEventListener('keydown',e=>{
  if(e.isComposing||e.keyCode===229)return;
  if(e.key==='Enter')sendChat();
});

/* ── 챗봇 팝업 바인딩 ──────────────────────────────────
   salmalBoot() 은 살!말? 탭에 처음 들어갈 때까지 미뤄지는 지연 함수라,
   홈에서 곧장 여는 이 팝업의 바인딩은 반드시 여기(항상 실행되는 조립부)에
   있어야 한다. salmalBoot 안에 두면 살!말? 탭을 한 번도 안 들어간 채로
   홈에서 팝업을 열었을 때 닫기·전송·새 대화가 전부 먹통이 된다. */
$('#cpAv')&&$('#cpAv').addEventListener('click',cpToggleMode);
$('#cpVtonQuick')&&$('#cpVtonQuick').addEventListener('click',openVirtualTryOn);
/* 마크가 버튼 역할을 하므로 키보드로도 눌린다 — Enter · Space */
$('#cpAv')&&$('#cpAv').addEventListener('keydown',e=>{
  if(e.key==='Enter'||e.key===' '){ e.preventDefault(); cpToggleMode(); }
});
$('#cpNewBtn')&&$('#cpNewBtn').addEventListener('click',()=>{
  cpNewConvo(); cpRenderList(); cpRenderThread();
  const ta=$('#cpInput'); if(ta)ta.focus();
});
$('#cpList')&&$('#cpList').addEventListener('click',e=>{
  /* ⋮ — 고정·이름 변경·삭제를 한자리에 모은 메뉴 (2026-09-14).
     메뉴가 뜨고 닫히는 것과 그 안의 선택은 chat_popup 쪽이 맡는다. */
  const menu=e.target.closest('.cpKebab[data-menu]');
  if(menu){ e.stopPropagation(); cpOpenMenu(menu); return; }
  const item=e.target.closest('.cpItem[data-cid]'); if(!item)return;
  cpCloseMenu();
  cpStore().activeId=+item.dataset.cid;
  cpRenderList(); cpRenderThread(); cpSave();
});
$('#cpSend')&&$('#cpSend').addEventListener('click',cpSend);
$('#cpInput')&&$('#cpInput').addEventListener('keydown',e=>{
  /* 한글 등 조합 입력 중에 눌리는 Enter(조합 확정용)까지 전송으로 잡으면
     마지막 자모가 따로 떨어져 나가 메시지가 두 번 나뉘어 찍힌다 —
     조합 중일 땐(e.isComposing / 구형 브라우저의 keyCode 229) 무시한다. */
  if(e.isComposing||e.keyCode===229)return;
  if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); cpSend(); }
});
$('#cpInput')&&$('#cpInput').addEventListener('input',e=>{
  const el=e.target; el.style.height=''; el.style.height=Math.min(el.scrollHeight,120)+'px';
});
$('#cpClose')&&$('#cpClose').addEventListener('click',closeChatPopup);
$('#cpOverlay')&&$('#cpOverlay').addEventListener('click',e=>{ if(e.target.id==='cpOverlay')closeChatPopup(); });
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&$('#cpOverlay').classList.contains('on'))closeChatPopup();
});
/* Tab — 일반 ↔ 살말 모드 전환 (2026-09-13).
   좌상단 마크를 마우스로 누르는 것 말고 키보드로도 오가게 한다. 팝업이 열려 있을
   때만 가로챈다.
   ★ Shift+Tab 은 그대로 둔다 — 브라우저 기본 이동을 통째로 막으면 마우스 없이는
     대화 목록·버튼에 닿을 수 없다. 되돌아가는 이동 하나는 남겨 둔다.
   ★ 제목을 고치는 중(.cpTitleIn)이거나 한글 조합 중일 땐 건드리지 않는다. */
document.addEventListener('keydown',e=>{
  if(e.key!=='Tab'||e.shiftKey||e.ctrlKey||e.metaKey||e.altKey)return;
  if(e.isComposing||e.keyCode===229)return;
  const ov=$('#cpOverlay'); if(!ov||!ov.classList.contains('on'))return;
  const t=e.target;
  if(t&&t.classList&&t.classList.contains('cpTitleIn'))return;
  e.preventDefault();
  cpToggleMode();
  const ta=$('#cpInput'); if(ta)ta.focus();
});

/* ── 모드 전환 — 버튼으로만 ─────────────────────────── */
function enterMain(){
  markIntroSeen();                      /* 여기까지 왔으면 인트로는 본 것이다 */
  if(mainMode)return; mainMode=true;
  document.body.classList.add('mainmode');
  scrollTo(0,0);
  if(!mainReady){ mainReady=true; qRoll() }
  curView=''; goView('home');
}
export function exitMain(){
  if(!mainMode)return; mainMode=false;
  scrollTo(0,0);
  document.body.classList.remove('mainmode');
  renderDeck();
}
$('#startBtn')&&$('#startBtn').addEventListener('click',enterMain);
/* 설명이 지루한 사람은 여기서 바로 넘어간다 */
$('#jumpBtn')&&$('#jumpBtn').addEventListener('click',enterMain);

/* 뒤로가기(및 앞으로가기) — pushNav 로 쌓아 둔 항목을 그대로 복원한다.
   랜딩(인트로) 단계로 완전히 나가 있었다면 다시 들어올 땐 홈에서 시작하고,
   기록이 없는(=우리가 처음 pushState 하기 전) 항목으로 돌아가면 인트로로 나간다. */
addEventListener('popstate', e=>{
  const st=e.state;
  navSkip=true;
  if(!mainMode){
    if(st&&st.view)enterMain(); else navSkip=false;
    return;
  }
  if(!st||!st.view){ exitMain(); return }
  if(st.view==='style'&&st.style){ goStyle(st.style); return }
  if(st.view==='trend')window.__trWant=st.tr||'myfeed';
  goView(st.view);
});

/* 아이템 목록은 '더 보기' 버튼으로 넘긴다 — 무한 스크롤은 걷어냈다(2026-09-18) */

/* ── 새로고침 복원 ──────────────────────────────────────
   인트로(로딩 + 설명 페이지)는 처음 들어온 사람에게만 보여 준다.
   이미 본문에 들어와 있던 세션이면 같은 화면을 그 자리에 다시 그린다.
   (로딩 시퀀스 자체는 intro/loader.js 의 boot 이 같은 열쇠를 보고 건너뛴다) */
(function resumeNav(){
  let st=null;
  try{ st=JSON.parse(sessionStorage.getItem(NAV_KEY)||'null') }catch(e){}
  /* ★ 2026-09-23 — 공유 링크(?view=trend&tr=report)로 들어오면 그 화면을 바로 연다.
     금주의 리포트 '공유' 버튼이 이 주소를 만든다(trend/static/js/report_export.js).
     주소에 적힌 화면이 세션 기록보다 우선이다 — 링크를 받은 사람이 기대하는 것은
     자기가 마지막에 보던 화면이 아니라 링크가 가리키는 화면이다. */
  try{
    const qs=new URLSearchParams(location.search);
    const want=qs.get('view');
    if(want&&document.getElementById('v-'+want)){
      st={view:want};
      if(want==='trend')st.tr=qs.get('tr')||'report';
    }
  }catch(e){}
  /* 세션 기록이 없어도, 예전에 인트로를 본 적이 있으면 홈으로 바로 들어간다 */
  if((!st||!st.view)&&introSeen())st={view:'home'};
  if(!st||!st.view)return;
  document.body.classList.add('loaded');
  const site=$('#site'); if(site)site.classList.add('on');
  enterMain();
  if(st.view==='style'&&st.style){ goStyle(st.style); return }
  if(st.view==='trend')window.__trWant=st.tr||'myfeed';
  if(st.view!=='home')goView(st.view);
})();
