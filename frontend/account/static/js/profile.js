import { $, $$, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';
import { BADGES, badgesApply, bgDetail, bgRender, bgSelect } from './badges.js';
import { fbLoad, fbPanelRender, fbReset } from '../../../salmal/static/js/feedback.js';
import { IMG, itemCard, LIKED, STYLES, toggleLike, likedSync, likedClear } from '../../../home/static/js/chat.js';
import { SIMG } from '../../../style/static/js/style_page.js';
import { styleProductCard, styleProductsURL } from '../../../style/static/js/products.js';
import { goView } from '../../../app_shell/static/js/router.js';
import { rkLevelOf, rkName, rkPaintAll, rkPaintAv, xpPaint } from './rank.js';
import { trRender } from '../../../trend/static/js/dispatch.js';
import { jobFieldApply, jobFieldBind, jobFieldCheck, jobFieldReset, jobReviewBind, jobReviewRender } from './job.js';
import { PLAN_EVENT, planApply, planEnforced, planReviewBind, planReviewRender, planSignedOut } from './plan.js';
import { emailCode, emailVerify, googleLogin, googleSignupAccount, kakaoLogin, kakaoSignupAccount, kakaoStart, loginAccount, logoutAccount, prepareGoogle, saveAccount, saveLiked, session, signupAccount, withdrawAccount, xpState } from './account_api.js';
/* 내 계정 — 운영자라 최고 등급 고정 */
/* ★ 2026-09-19 — 예전 기본값(혁진 · xp 9400 · 적중 94 · 찜 128 · ADMIN)은 시연용 목업이었다.
   로그인 전 기본값은 비워 두고, 값은 전부 applyAccount() 가 서버 응답으로 채운다. */
export const ME={name:'FEEDiT 사용자',mail:'',initial:'F',
          xp:0,              /* 누적 경험치 — 서버가 기록으로 계산한다 (backend/apps/api/xp.py) */
          xpFixed:false,     /* 운영 계정 — 경험치를 세지 않고 최고 레벨로 고정 */
          xpInfo:null,       /* 오늘 · 이번 주 내역 (경험치 창 · 마이페이지 요약) */
          height:'',weight:'',gender:'',   /* 체형·성별 — 가입·정보수정에서 받는다 */
          plan:'FREE',saved:0,
          role:'user',       /* 서버가 admin(슈퍼유저·스태프) 또는 user 로 준다 */
          job:'',            /* 승인된 직업(job.js JOBS id). 비어 있거나 승인 전이면 Basic 으로 보인다 */
          major:'',          /* Student 전공 */votes:0,
          bio:'',            /* 비어 있으면 예시 문구가 흐리게 대신 선다 */
          birth:'',          /* 가입·정보수정에서 채운다 */
          ava:0,             /* 프로필 아이콘 색 (AVA 인덱스) */
          styles:new Set()};  /* 즐겨입는 스타일 (가입 시 선택) */
/* rank 는 저장하지 않는다 — 경험치에서 항상 다시 센다.
   이렇게 두면 XP 만 올려도 링·문구·바가 한꺼번에 따라온다. */
Object.defineProperty(ME,'rank',{get(){ return rkLevelOf(ME.xp, ME.xpFixed) }, enumerable:true});

/* 경험치 — 서버가 계산한 값만 쓴다. 운영 계정은 {fixed:true} 로 와서 최고 레벨로 고정된다. */
function xpApply(state){
  ME.xpFixed=Boolean(state&&state.fixed);
  ME.xp=ME.xpFixed?0:Math.max(0,Number(state&&state.total)||0);
  ME.xpInfo=ME.xpFixed?null:(state||null);
}
/* 기록 API(접속 · 체류 · 피드백) 응답으로 경험치를 바꾼다.
   레벨이 오르면 한 번 알려 주고, 화면의 링 · 바 · 사이드바 칩을 한꺼번에 다시 칠한다. */
export function applyXp(state){
  if(!state||!AUTH.in)return;
  const before=ME.rank;
  xpApply(state);
  if(!ME.xpFixed&&ME.rank>before)acctToast('레벨이 올랐어요 · '+rkName(ME.rank));
  xpPaint(); avaPaint();
  try{ document.dispatchEvent(new CustomEvent('feedit:account')) }catch(e){}
}

/* DB 사용자 응답을 기존 화면 모델(ME)에 옮긴다.
   마크업과 렌더 함수는 그대로 두고, 값의 출처만 목업에서 API로 바꾼다. */
function applyAccount(user){
  if(!user)return;
  ME.id=user.id==null?null:user.id;   /* 챗봇에 로그인 사실을 알릴 때 쓴다 (2026-09-18) */
  ME.name=user.nickname||user.username||ME.name;
  ME.initial=ME.name[0]||'F';
  ME.mail=user.email||user.username||'';
  ME.birth=user.birth_date||'';
  ME.height=user.height==null?'':String(user.height);
  ME.weight=user.weight==null?'':String(user.weight);
  ME.gender=user.gender==='FEMALE'||user.gender==='MALE'?user.gender:'';
  ME.bio=user.bio||'';
  ME.ava=Number.isFinite(+user.avatar)?+user.avatar:0;
  ME.role=user.role||'user';
  /* 요금제 — 서버가 준다 (ADMIN · FREE · 이후 알파 테스트용 TEST) */
  ME.plan=user.plan||(ME.role==='admin'?'ADMIN':'FREE');
  /* 요금제 상태 (plan.js · 2026-10-03). 베타 동안 서버는 enforced:false 를 보내 아무것도 막지 않는다.
     user.billing 이 없는 응답(옛 서버)이면 지금 상태를 그대로 둔다. */
  planApply(user.billing);
  badgesApply(user.badges||{});
  xpApply(user.xp);
  ME.job=user.job||'';
  ME.jobRequest=user.job_request||null;   /* 심사 중인 직업 인증 — 승인 전에는 job 이 비어 있다 */
  ME.major=user.major||'';
  ME.saved=Number(user.saved_count||0);
  ME.votes=Number(user.vote_count||0);
  const names=new Set(Array.isArray(user.styles)?user.styles:[]);
  ME.styles.clear();
  STYLES.forEach(s=>{ if(names.has(s.n))ME.styles.add(s.id) });
  /* 이름·직업·소개가 바뀌었음을 알린다 — 트렌드 머리·사이드바가 받아 다시 칠한다 */
  try{ document.dispatchEvent(new CustomEvent('feedit:account')) }catch(e){}
}
/* 다른 모듈이 서버에서 받은 사용자 응답을 그대로 반영할 때 (알림의 성별 고르기 등) */
export function applyAccountUser(user){ applyAccount(user) }
/* ★ 2026-09-20 — 로그아웃하면 ME 를 로그인 전 기본값으로 되돌린다.
   예전엔 값을 그대로 두어서, 로그아웃 뒤 트렌드 분석(로그인 안내 뒤편)에
   앞 계정의 이름·취향 피드가 그대로 비쳤다. */
function resetAccount(){
  Object.assign(ME,{id:null,name:'FEEDiT 사용자',mail:'',initial:'F',xp:0,xpFixed:false,xpInfo:null,height:'',weight:'',gender:'',
    plan:'FREE',saved:0,role:'user',job:'',jobRequest:null,major:'',votes:0,bio:'',birth:'',ava:0});
  ME.styles.clear();
  planSignedOut();
  try{ document.dispatchEvent(new CustomEvent('feedit:account')) }catch(e){}
}
const styleNames=()=>STYLES.filter(s=>ME.styles.has(s.id)).map(s=>s.n);

/* 프로필 아이콘 색 — 팔레트 밖으로 나가지 않게 코랄·먹·모래 계열만 썼다 */
const AVA=[
  ['#ff6b4a','#ffb199'], ['#1c1a17','#4a453d'], ['#c8a27a','#e6d3bd'],
  ['#3d5a6c','#7d9db0'], ['#6b5b95','#a89bc4'], ['#4a6b52','#8fae95']
];
/* 아바타가 쓰이는 곳(마이페이지 원형 + 헤더 작은 원)을 한 번에 칠한다 */
function avaPaint(){
  const g=AVA[ME.ava]||AVA[0];
  const bg='linear-gradient(135deg,'+g[0]+','+g[1]+')';
  /* 헤더의 작은 원(.meAv)은 2026-09-19 에 없앴다 — 남은 건 마이페이지 원 하나다. */
  const c=$('#avatarInitial'); if(c){ c.style.background=bg; rkPaintAv(c, ME.rank) }
}

/* ── 소개글 인라인 편집 ──────────────────────────────────
   따로 창을 띄우지 않는다. 연필을 누르면 그 문장이 그대로 입력칸이 되고,
   Enter 나 바깥 클릭으로 저장, Esc 로 되돌린다. */
const BIO_MAX=60;
export function bioPaint(){
  const p=$('#trProfBio'); if(!p)return;
  p.textContent=ME.bio||'';
  p.classList.toggle('isEmpty',!ME.bio);
}
function bioEdit(on){
  const p=$('#trProfBio'), b=$('#trBioEdit');
  if(!p||!b)return;
  if(on){
    p.dataset.prev=ME.bio||'';
    p.setAttribute('contenteditable','plaintext-only');
    b.classList.add('on');
    p.focus();
    /* 커서를 문장 끝으로 */
    const r=document.createRange(); r.selectNodeContents(p); r.collapse(false);
    const s=getSelection(); s.removeAllRanges(); s.addRange(r);
  }else{
    ME.bio=(p.textContent||'').replace(/\s+/g,' ').trim().slice(0,BIO_MAX);
    p.removeAttribute('contenteditable');
    b.classList.remove('on');
    bioPaint();
    if(AUTH.in) saveAccount({bio:ME.bio}).then(d=>applyAccount(d.user))
      .catch(e=>acctToast(e.message||'소개글을 저장하지 못했습니다.'));
  }
}
function bioBind(){
  const p=$('#trProfBio'), b=$('#trBioEdit');
  if(!p||!b||b.dataset.bound)return;
  b.dataset.bound='1';
  b.addEventListener('click',e=>{ e.stopPropagation();
    bioEdit(p.getAttribute('contenteditable')===null); });
  p.addEventListener('click',()=>{ if(p.getAttribute('contenteditable')===null)bioEdit(true) });
  p.addEventListener('input',()=>{ p.classList.toggle('isEmpty',!p.textContent.trim()) });
  p.addEventListener('keydown',e=>{
    if(e.key==='Enter'){ e.preventDefault(); bioEdit(false) }
    else if(e.key==='Escape'){ e.preventDefault();
      p.textContent=p.dataset.prev||''; bioEdit(false) }
    else if(p.textContent.length>=BIO_MAX&&e.key.length===1&&!e.metaKey&&!e.ctrlKey)e.preventDefault();
  });
  p.addEventListener('blur',()=>{ if(p.getAttribute('contenteditable')!==null)bioEdit(false) });
}
bioBind();

/* ══════════════════════════════════════════════════════════════
   계정 — 로그인 · 회원가입 · 마이페이지
   --------------------------------------------------------------
   목업이라 서버가 없다. 인증 흉내는 여기서만 내고,
   실제 값은 전부 ME(사용자)와 기존 데이터(SV 찜 · VOTES 투표 · STYLES 스타일)에
   연결해 둔다. API 가 붙으면 authLogin / authSignup / acctSave 안쪽만 갈아 끼우면 된다.
   ══════════════════════════════════════════════════════════════ */
/* in    : 지금 로그인돼 있는가
   ready : **판정해도 되는가**.
   ★ 2026-09-22 — 새로고침하면 router 의 resumeNav 가 보던 화면을 그 자리에서
     바로 세우는데, 로그인 복구(session())는 그보다 늦게 끝난다. 그 사이의
     in=false 를 '로그아웃'으로 읽어서, 로그인한 사람에게도 트렌드 분석의
     '로그인이 필요합니다' 팝업이 떴고 마이페이지는 로그인 화면으로 튕겼다.
     복구가 끝나기 전에는 아무 판정도 하지 않는다 — 그게 ready 다. */
export var AUTH = { in: false, ready: false };
/* 로그인 상태가 확정됐음을 알린다. 화면들(router)이 이걸 받고 관문을 다시 판정한다.
   ★ 둘로 나눈 이유 — feedit:auth 는 '계정이 바뀌었다' 는 뜻이라서, 받는 쪽이
     앞 계정의 화면을 버린다(trend 의 trAccountChanged). 복구해 보니 로그아웃
     이더라 는 '바뀐' 것이 아니므로 그걸로 남의 화면을 지우면 안 된다.
     상태가 실제로 바뀌었을 때만 feedit:auth, 아니면 feedit:auth-ready. */
function authNotify(changed){
  AUTH.ready = true;
  document.dispatchEvent(new CustomEvent(changed?'feedit:auth':'feedit:auth-ready'));
}
function authSettled(){ if(!AUTH.ready){ authNotify(false); authPaint(); } }
/* ── 새로고침 깜빡임 (2026-10-02) ───────────────────────────────
   새로고침하면 헤더가 먼저 [로그인] 으로 그려지고, 로그인 복구(/api/auth/me 왕복)가 끝난
   뒤에야 이름으로 바뀌었다 — 잠깐 로그아웃된 것처럼 보였다.
   → 복구가 끝나기 전(AUTH.ready=false)에는 [로그인] 을 그리지 않는다. 지난번에 로그인해
     있던 브라우저면 그때 이름(닉네임 하나만 — 다른 정보는 남기지 않는다)을 먼저 보여 주고,
     아니면 빈 자리표시만 둔다. 복구 결과가 오면 진짜 상태로 다시 그린다.
   ★ 이 값은 화면 표시에만 쓴다. 로그인 판정(AUTH.in)과 관문은 여전히 서버 답만 믿는다. */
const AUTH_HINT='feedit:auth-hint';
function hintName(){ try{ return String(localStorage.getItem(AUTH_HINT)||'').slice(0,40) }catch(e){ return '' } }
function hintSave(name){ try{ if(name)localStorage.setItem(AUTH_HINT,String(name).slice(0,40)) }catch(e){} }
function hintClear(){ try{ localStorage.removeItem(AUTH_HINT) }catch(e){} }
/* 로그인 없이 쓸 수 없는 기능(챗봇 사용 · 트렌드 분석 · 살!말? 투표/등록)의
   공통 관문. 로그인 전이면 로그인 화면으로 보내고 false 를 돌려준다. */
/* 로그인 관문에 걸려 중단된 동작 하나. 로그인/가입이 끝나면 그대로 이어 한다.
   ★ 2026-09-13. 챗봇에 "발레코어 요즘 어때?" 를 치던 중 로그인 화면으로 넘어가면
     로그인을 마쳐도 질문이 사라져 있었다. 사용자는 같은 문장을 다시 쳐야 했다.
     하나만 들고 있는다 — 여러 개를 쌓아 두면 로그인 뒤에 예상치 못한 화면이
     연달아 뜬다. 새로 걸리면 앞의 것을 버린다. */
let pendingAfterAuth = null;
export function requireAuth(resume){
  if(AUTH.in)return true;
  pendingAfterAuth = (typeof resume === 'function') ? resume : null;
  goView('login');
  return false;
}
/* 로그인을 포기하고 다른 화면으로 갔다면 이어 할 일도 버린다 —
   한참 뒤에 로그인했을 때 잊고 있던 질문이 튀어나오면 안 된다. */
export function dropPendingAuth(){ pendingAfterAuth = null; }
function runPendingAuth(){
  const fn = pendingAfterAuth;
  pendingAfterAuth = null;
  if(!fn) return;
  /* 화면 전환(goView) 애니메이션이 끝난 뒤에 이어 한다 */
  setTimeout(() => { try{ fn() }catch(e){ /* 이어 하기 실패는 조용히 넘긴다 */ } }, 320);
}
/* 회원가입 진행 중 소셜 모드 — '' | 'google' | 'kakao'. 가입 폼을 벗어나면 반드시 초기화된다 */
let signupSocial = '';
const SOCIAL_LABEL = { google:'Google', kakao:'카카오' };
/* 아이디 가입의 이메일 인증 상태 — 인증을 마친 주소와 재발송 대기 타이머 */
let emailVerified = '';
let emailGapTimer = 0;
/* 찜(위시리스트) — 원본은 서버(/api/auth/saved?view=all), 화면은 chat.js 의 LIKED 사본을 읽는다.
   로그인·세션 복구 때 likedAfterAuth() 가 서버 목록으로 맞춘다 (2026-09-19). */

/* 헤더 오른쪽 — 로그인 전에는 [로그인], 후에는 [혁진] 버튼이 마이페이지로 */
const ME_CARET = '<svg class="meCaret" viewBox="0 0 12 12" fill="none" stroke="currentColor" ' +
  'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M2.5 4.5L6 8l3.5-3.5"/></svg>';
function authPaint(){
  const b = $('#mAuthBtn');
  if(!b) return;
  b.removeAttribute('aria-busy');
  if(!AUTH.in && !AUTH.ready){
    /* 아직 모른다 — [로그인] 을 그리지 않는다(위 '새로고침 깜빡임' 주석) */
    const hint = hintName();
    b.removeAttribute('data-v');
    b.setAttribute('aria-busy','true');
    if(hint){ b.className = 'pill me pending'; b.innerHTML = cpEscHTML(hint) + ME_CARET; }
    else{ b.className = 'pill authPending'; b.textContent = ''; b.setAttribute('aria-label','로그인 상태 확인 중'); }
    return;
  }
  b.removeAttribute('aria-label');
  if(AUTH.in){
    hintSave(ME.name);
    b.className = 'pill me';
    b.removeAttribute('data-v');       /* 전역 [data-v] 위임 대신 메뉴를 연다 */
    /* ★ 2026-09-19 — 닉네임 왼쪽의 프로필 원(.meAv)은 뺐다.
       그 자리에 알림 아이콘이 오른쪽으로 붙으면서 헤더에 동그라미가 둘이 됐다. */
    b.innerHTML = ME.name +
      '<svg class="meCaret" viewBox="0 0 12 12" fill="none" stroke="currentColor" ' +
      'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M2.5 4.5L6 8l3.5-3.5"/></svg>';
    avaPaint();
    const mj = $('#menuJobReview');
    /* 직업 인증 심사는 운영(ADMIN) 계정에만 보인다 */
    if(mj) mj.hidden = ME.role !== 'admin';
    planMenuPaint();
  }else{
    hintClear();
    b.className = 'pill';
    b.dataset.v = 'login';
    b.textContent = '로그인';
    acctMenu(false);
  }
}
/* 요금제 신청 심사 메뉴 — 운영 계정만, 그리고 베타가 끝난 뒤에만 (2026-10-03).
   베타 동안에는 신청이 들어올 수 없으니 메뉴도 세우지 않는다 — 베타 화면은 운영 계정에게도 지금과 같다. */
function planMenuPaint(){
  const mp = $('#menuPlanReview');
  if(mp) mp.hidden = !(AUTH.in && ME.role === 'admin' && planEnforced());
}
document.addEventListener(PLAN_EVENT, planMenuPaint);
function cpEscHTML(t){ return String(t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) }
/* 로그인 뒤 이름 버튼을 누르면 뜨는 작은 메뉴 */
export function closeAcctMenu(){ acctMenu(false) }
function acctMenu(on){
  const m = $('#acctMenu');
  if(m){
    m.classList.toggle('on', on === undefined ? !m.classList.contains('on') : on);
    /* 계정 메뉴와 알림창은 한 번에 하나만 — 메뉴를 열면 알림창을 닫는다 */
    if(m.classList.contains('on')) document.dispatchEvent(new CustomEvent('feedit:popover', { detail:'acct' }));
    const w = m.closest('.mAuthWrap');
    if(w) w.classList.toggle('open', m.classList.contains('on'));
  }
}
/* 찜을 서버 원본으로 맞춘 뒤 숫자·마이페이지를 다시 그린다 */
function likedAfterAuth(){
  likedSync(ME.id).then(ok=>{
    if(!ok)return;
    const n=$('#statSavedN'); if(n)n.textContent=LIKED.size;
    if(document.body.dataset.view==='mypage')myRender();
  });
}
function authLogin(user){
  applyAccount(user);
  AUTH.in = true; AUTH.ready = true;
  likedAfterAuth();
  document.dispatchEvent(new CustomEvent('feedit:auth'));
  authPaint();
  goView('home');
  runPendingAuth();
}
async function authLogout(){
  try{
    await logoutAccount();
    AUTH.in = false; AUTH.ready = true;
    likedClear();
    badgesApply(null);
    resetAccount();
    fbReset();
    document.dispatchEvent(new CustomEvent('feedit:auth'));
    pendingAfterAuth = null;
    authPaint();
    goView('home');
  }catch(e){ acctToast(e.message||'로그아웃하지 못했습니다.') }
}
/* 회원가입 완료(구글 · 아이디 공통) — 홈 화면으로 보낸 뒤 그 위에
   '즐겨입는 스타일' 선택 팝업을 띄운다. 팝업을 닫아도 화면은 홈에 그대로 남는다. */
function signupComplete(){
  AUTH.in = true; AUTH.ready = true;
  likedAfterAuth();
  document.dispatchEvent(new CustomEvent('feedit:auth'));
  authPaint();
  ME.styles.clear();   /* 팝업은 항상 빈 상태에서 시작한다 */
  goView('home');
  openStyleSelect();
  runPendingAuth();
}
/* 작은 확인 토스트 — 살!말? 쪽과 같은 #toast 를 그대로 쓴다 */
var acctToastT;
export function acctToast(msg){
  const t = $('#toast'); if(!t) return;
  t.textContent = msg; t.classList.add('on');
  clearTimeout(acctToastT);
  acctToastT = setTimeout(() => t.classList.remove('on'), 2200);
}

/* 회원정보 수정 — 비밀번호 칸 바로 아래 안내 (빈 문자열이면 감춘다) */
function editPwMsg(msg){
  const el = $('#editPwMsg'); if(!el) return;
  el.textContent = msg || '';
  el.style.display = msg ? 'block' : 'none';
}

/* 스타일 칩 — 가입·마이페이지가 스타일 페이지와 같은 10종(STYLES)을 쓴다 */
const STYLE_MAX = 3;
function acctChips(host, sel){
  if(!host) return;
  host.innerHTML = STYLES.map(s =>
    '<button type="button" class="chip' + (sel.has(s.id) ? ' on' : '') +
    '" data-style-pick="' + s.id + '">' + s.n + '</button>').join('');
  host.onclick = e => {
    const b = e.target.closest('[data-style-pick]');
    if(!b) return;
    const id = b.dataset.stylePick;
    /* 가입 팝업과 같은 규칙 — 즐겨입는 스타일은 최대 3개 */
    if(!sel.has(id) && sel.size >= STYLE_MAX){
      acctToast('즐겨입는 스타일은 ' + STYLE_MAX + '개까지 고를 수 있어요. 하나를 먼저 빼 주세요.');
      return;
    }
    sel.has(id) ? sel.delete(id) : sel.add(id);
    b.classList.toggle('on', sel.has(id));
    if(host.id === 'styleWrap'){
      myRender();   /* 마이페이지는 고르는 즉시 추천이 바뀐다 */
      try{ document.dispatchEvent(new CustomEvent('feedit:styles')) }catch(e){}
    }
  };
}

/* 가입 완료 팝업 — 코어/원형 구분 없이 STYLES 순서 그대로, 최대 3개까지 중복 선택.
   처음엔 아무것도 선택돼 있지 않고(= signupComplete 에서 비워 둔다),
   3개가 찬 상태에서 새로 고르면 '가장 최근에 골랐던 것'의 테두리가 새 선택으로 옮겨간다. */
let styleSelOrder = [];
function styleSelectBuild(){
  styleSelOrder = [...ME.styles];
  const host = $('#styleSelectGrid'); if(!host) return;
  host.innerHTML = STYLES.map(s =>
    '<button type="button" class="styleSelCard' + (ME.styles.has(s.id) ? ' on' : '') +
    '" data-style-pick="' + s.id + '"><img src="' + SIMG(s) + '" alt="" draggable="false">' +
    '<span>' + s.n + '</span></button>').join('');
}
function styleSelectBind(){
  const host = $('#styleSelectGrid');
  if(host && !host.dataset.bound){
    host.dataset.bound = '1';
    host.addEventListener('click', e => {
      const b = e.target.closest('[data-style-pick]'); if(!b) return;
      const id = b.dataset.stylePick;
      if(ME.styles.has(id)){
        ME.styles.delete(id); b.classList.remove('on');
        styleSelOrder = styleSelOrder.filter(x => x !== id);
      }else{
        if(ME.styles.size >= STYLE_MAX){
          const last = styleSelOrder.pop();   /* 가장 최근 선택을 밀어낸다 */
          if(last){
            ME.styles.delete(last);
            const prev = host.querySelector('[data-style-pick="' + last + '"]');
            if(prev) prev.classList.remove('on');
          }
        }
        ME.styles.add(id); b.classList.add('on');
        styleSelOrder.push(id);
      }
    });
  }
  const save = $('#styleSelectSave');
  if(save && !save.dataset.bound){
    save.dataset.bound = '1';
    save.addEventListener('click', async () => {
      save.disabled=true;
      try{
        const data=await saveAccount({styles:styleNames()});
        applyAccount(data.user);
        acctModal('styleSelectModal', false);
        acctChips($('#styleWrap'), ME.styles);   /* 마이페이지 칩과 동기화 */
        myRender();
        acctToast('즐겨입는 스타일이 저장되었어요.');
      }catch(e){ acctToast(e.message||'스타일을 저장하지 못했습니다.') }
      finally{ save.disabled=false }
      /* 취향이 바뀐 것을 화면들에 알린다 — 챗봇 팝업의 '스타일 고르기' 안내는
         이 신호를 받아 사라진다(2026-09-13). */
      try{ document.dispatchEvent(new CustomEvent('feedit:styles')) }catch(e){}
    });
  }
  const close = $('#styleSelectClose');
  if(close && !close.dataset.bound){
    close.dataset.bound = '1';
    close.addEventListener('click', () => acctModal('styleSelectModal', false));
  }
}
export function openStyleSelect(){
  styleSelectBuild();
  styleSelectBind();
  acctModal('styleSelectModal', true);
}

/* 아이템 카드 — '스타일' 상세와 마이페이지가 같은 chat.js 의 itemCard() 를 그대로 쓴다 */

/* ── 오늘의 추천 (실데이터) ─────────────────────────── */
const REC_PER_BLOCK = 6;       /* 칸마다 보여 줄 카드 수 — 한 줄에 3개씩 두 줄 */
const REC_POOL = 16;           /* 스타일마다 받아 오는 후보 수 — 여기서 날짜별로 골라 쓴다 */
const REC_RISE = ['확산','재상승','재점화','정점 통과'];
const recCache = new Map();    /* 스타일명 → 상품 목록 Promise. 칩을 누를 때마다 다시 받지 않는다 */
let recSeq = 0;

function recFetch(styleName){
  if(!recCache.has(styleName)){
    const job = fetch(styleProductsURL(styleName, 0, REC_POOL))
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(j => (j && j.status === 'ok' && j.data && Array.isArray(j.data.items)) ? j.data.items : [])
      .catch(e => { recCache.delete(styleName); throw e });   /* 실패는 캐시하지 않는다 */
    recCache.set(styleName, job);
  }
  return recCache.get(styleName);
}

/* 날짜를 씨앗으로 섞는다 — 같은 날에는 같은 순서, 다음 날에는 다른 상품이 앞에 선다 */
function recDayShuffle(list, salt){
  const d = new Date();
  let h = (d.getFullYear() * 400 + d.getMonth() * 31 + d.getDate()) ^ salt;
  const rnd = () => { h = (h * 1103515245 + 12345) & 0x7fffffff; return h / 0x7fffffff };
  const out = list.slice();
  for(let i = out.length - 1; i > 0; i--){ const j = Math.floor(rnd() * (i + 1)); [out[i], out[j]] = [out[j], out[i]] }
  return out;
}

/* 여러 스타일의 상품을 번갈아 뽑아 한 칸을 만든다. used 에 든 상품은 건너뛴다(두 칸 중복 방지) */
async function recPick(styles, used){
  const lists = await Promise.all(styles.map(s => recFetch(s.n).then(
    items => recDayShuffle(items, s.id.length * 7919).map(it => ({ it, s })),
    () => [])));
  const out = [];
  for(let round = 0; out.length < REC_PER_BLOCK; round++){
    let any = false;
    for(const l of lists){
      if(round >= l.length) continue;
      any = true;
      const { it, s } = l[round];
      const card = styleProductCard(it, s.n);
      if(used.has(card.id)) continue;
      used.add(card.id);
      out.push({ ...card, style: s.id });
      if(out.length >= REC_PER_BLOCK) break;
    }
    if(!any) break;
  }
  return out;
}

function recBlockHTML(host, cards, emptyText){
  host.innerHTML = cards.length
    ? cards.map(itemCard).join('')
    : '<div class="itState">' + emptyText + '</div>';
}

async function recRender(){
  const mineHost = $('#recMine'), hotHost = $('#recHot');
  if(!mineHost || !hotHost) return;
  const seq = ++recSeq;
  const picked = STYLES.filter(s => ME.styles.has(s.id)).slice(0, 3);
  const rising = STYLES.filter(s => REC_RISE.includes(s.pk) && !ME.styles.has(s.id));

  const mineTitle = $('#recMineTitle');
  if(mineTitle) mineTitle.textContent = '내 취향 ' + picked.length + '개 기준';

  if(!picked.length) mineHost.innerHTML = '<div class="itState recEmpty">즐겨입는 스타일을 추가해 보세요.</div>';
  else mineHost.innerHTML = '<div class="itState">상품을 불러오는 중…</div>';
  hotHost.innerHTML = '<div class="itState">상품을 불러오는 중…</div>';

  const used = new Set();
  try{
    const mine = picked.length ? await recPick(picked, used) : [];
    const hot = await recPick(rising, used);
    if(seq !== recSeq) return;   /* 그 사이 취향이 또 바뀌었으면 늦게 온 결과는 버린다 */
    if(picked.length) recBlockHTML(mineHost, mine, '고른 스타일에 연결된 상품이 아직 없습니다.');
    recBlockHTML(hotHost, hot, '지금 뜨는 스타일에 연결된 상품이 아직 없습니다.');
  }catch(e){
    if(seq !== recSeq) return;
    const msg = '<div class="itState">상품을 불러오지 못했습니다.</div>';
    if(picked.length) mineHost.innerHTML = msg;
    hotHost.innerHTML = msg;
  }
  syncTodayRecHeight();
}

export function myRender(){
  /* 프로필 */
  const av = $('#avatarInitial'), nm = $('#profileName'), em = $('#profileEmail');
  if(av) av.textContent = ME.initial;
  if(nm) nm.textContent = ME.name;
  if(em) em.textContent = ME.mail;
  xpPaint();
  avaPaint();
  /* 경험치는 들어올 때마다 서버에서 다시 받는다 — 다른 화면에서 쌓인 몫까지 맞춘다 */
  if(AUTH.in) xpState().then(d=>applyXp(d&&d.xp)).catch(()=>{});

  /* 저장 · 투표 수는 실제 데이터에서 센다 */
  const savedN = $('#statSavedN'), votedN = $('#statVotedN');
  if(savedN) savedN.textContent = LIKED.size;
  const voted = (typeof VOTES !== 'undefined')
    ? VOTES.filter(v => v.voted !== null && v.voted !== undefined) : [];
  if(votedN) votedN.textContent = voted.length || ME.votes;
  /* 뱃지 — 컬렉션 뱃지 개수. 등급은 뱃지가 아니라 아바타 링으로 표현한다.
     팀원 데이터가 붙으면 BADGES 만 채우면 숫자도 같이 맞는다. */
  const badgeN = $('#statBadgeN');
  if(badgeN) badgeN.textContent = BADGES.filter(b => b.earned).length;

  /* 오늘의 추천 — 실데이터(/api/products) 상품으로 두 칸을 나눠 채운다(2026-09-17).
     · 내 취향 N개 기준 : 즐겨입는 스타일(최대 3개)에 태그된 상품
     · 지금 뜨는 코어 기준 : 추세 단계가 확산·재상승·재점화·정점 통과인 스타일의 상품
     매칭도(%) 표기는 계산 근거가 없어 뺐다. */
  recRender();
  syncTodayRecHeight();

  /* 살!말? 피드백 작성 현황 (2026-09-19) — 마감된 내 카드에 결과를 남겼는지 */
  fbPanelMount();

  if(HAS_A){
    aAnimate($$('#v-mypage .panel'), {opacity:[0,1],translateY:[14,0],
      duration:640,delay:aStagger(60),ease:'out(3)',
      onComplete:()=>$$('#v-mypage .panel').forEach(e=>{e.style.transform='';e.style.opacity=''})});
  }
}

/* 살!말? 피드백 패널 — 오른쪽 칸(#myColFb)에 넣는다.
   ★ 2026-09-20 — 예전에는 '오늘의 추천' 바로 뒤에 끼워 넣어 가운데 칸 아래에 달렸다. */
function fbPanelMount(){
  const host = $('#myColFb') || $('#todayRecPanel');
  if(!host) return;
  if(!$('#fbPanel')){
    const html = '<div class="panel fbPanel" id="fbPanel">'+
      '<div class="panelHead"><h3>살!말? 피드백</h3><span class="sub">마감된 내 카드의 결과</span></div>'+
      '<div id="fbPanelBody"></div></div>';
    if(host.id === 'myColFb') host.insertAdjacentHTML('beforeend', html);
    else host.insertAdjacentHTML('afterend', html);   /* 칸이 없는 예전 화면 대비 */
  }
  const body = $('#fbPanelBody');
  if(!AUTH.in){ body.innerHTML = '<div class="fbEmpty">로그인하면 확인할 수 있습니다.</div>'; return; }
  fbPanelRender(body);
  syncTodayRecHeight();
  fbLoad().then(() => fbPanelRender($('#fbPanelBody')));
}
/* 가운데 '오늘의 추천'과 오른쪽 '살!말? 피드백' 높이를
   왼쪽 칸(프로필 + 즐겨입는 스타일) 높이에 맞춘다.
   피드백만 그 3분의 2 높이다(FB_HEIGHT_RATIO).
   넘치는 내용은 패널 안쪽(.recScroll · #fbPanelBody)에서 스크롤한다.
   패널 자신이 스크롤하면 막대가 둥근 모서리 위에 얹혀 모서리가 각져 보인다(2026-09-20).

   ★ 1280px 미만에서는 피드백이 아래로 내려와 가로로 눕는다(profile.css 의 같은 기준).
     그때는 높이를 박지 않는다 — 가로로 누운 패널에 세로 길이를 강제하면 빈 칸만 길어진다. */
const MY_THREE_COL = 1280;
const FB_HEIGHT_RATIO = 2 / 3;   /* 피드백 패널 높이 = 오늘의 추천 × 2/3 */
function syncTodayRecHeight(){
  const left = $('.myGrid .myCol:first-child');
  const panel = $('#todayRecPanel');
  if(!left || !panel || !panel.offsetParent) return;
  const h = Math.round(left.getBoundingClientRect().height);
  panel.style.height = h + 'px';
  /* 피드백은 '오늘의 추천'의 3분의 2 높이. 같은 높이로 세우면 빈 칸이 너무 길다. */
  const fb = $('#fbPanel');
  if(fb) fb.style.height = (innerWidth >= MY_THREE_COL)
    ? Math.round(h * FB_HEIGHT_RATIO) + 'px' : '';
}
if(!window.__recHeightBound){
  window.__recHeightBound = true;
  addEventListener('resize', () => syncTodayRecHeight());
}

/* 모달 */
function acctModal(id, on){
  const m = $('#' + id);
  if(m) m.classList.toggle('on', on);
}

/* 카드 오른쪽 위 하트 — 눌러서 찜 토글. 어느 카드에서 누르든(스타일 상세 · 오늘의 추천 ·
   찜 목록 모달) 같은 저장소(chat.js 의 LIKED)로 모여 마이페이지 '찜'과 곧장 이어진다. */
export function likeClick(btn){
  if(!requireAuth())return;
  const id=btn.dataset.likeId; if(!id)return;
  const before=LIKED.get(id);
  const on=toggleLike(id);
  btn.classList.toggle('on',on);
  /* 서버에도 찜/해제를 남긴다 — 금주의 리포트 '새로 찜한 것 · 총 추적 수' */
  const d=on?LIKED.get(id):before;
  if(d){
    const st=STYLES.find(s=>s.id===d.style);
    saveLiked({ itemId:id, liked:on, name:d.nm||'', brand:d.br||'', style:d.styleName||(st?st.n:'') })
      .then(r=>{
        if(r&&Number.isFinite(+r.saved_count))ME.saved=+r.saved_count;
        if(r)document.dispatchEvent(new CustomEvent('feedit:saved'));
        /* 방금 누른 찜의 '같은 걸 찜한 사람 수'까지 서버 값으로 다시 맞춘다 */
        if(r)likedAfterAuth();
      });
  }
  const n=$('#statSavedN'); if(n)n.textContent=LIKED.size;
}

/* Google 버튼 공통 처리 — 로그인 화면·가입 화면이 같은 흐름을 쓴다.
   ★ googleLogin() 은 await 앞에서 바로 불러야 팝업이 막히지 않는다. */
function googleContinue(btn, errEl){
  if(errEl) errEl.style.display = 'none';
  btn.disabled = true;
  googleLogin().then(data => {
    if(data.authenticated){ authLogin(data.user); return; }
    if(data.needs_signup) enterSocialSignup('google', data.google || {});
  }).catch(e => {
    if(e && e.cancelled) return;   /* 사용자가 창을 닫은 것은 오류로 보이지 않는다 */
    const msg = (e && e.message) || 'Google 로그인에 실패했습니다.';
    if(errEl && errEl.closest('.view.on')){ errEl.textContent = msg; errEl.style.display = 'block'; }
    else acctToast(msg);
  }).finally(() => { btn.disabled = false; });
}

/* 카카오로 계속하기 — 카카오 로그인 페이지로 나갔다가 이 사이트 첫 화면으로 돌아온다.
   돌아온 뒤의 처리는 kakaoReturn() 이 맡는다. */
const KAKAO_MARK = 'feeditKakao';
function kakaoContinue(btn, errEl){
  if(errEl) errEl.style.display = 'none';
  btn.disabled = true;
  kakaoStart(location.origin + '/').then(url => {
    try{ sessionStorage.setItem(KAKAO_MARK, '1') }catch(e){}
    location.href = url;
  }).catch(e => {
    btn.disabled = false;
    const msg = (e && e.message) || '카카오 로그인을 시작하지 못했습니다.';
    if(errEl && errEl.closest('.view.on')){ errEl.textContent = msg; errEl.style.display = 'block'; }
    else acctToast(msg);
  });
}
/* 카카오에서 ?code=&state= (취소면 ?error=) 를 달고 돌아왔을 때.
   우리가 보낸 이동일 때만(표시가 남아 있을 때만) 처리하고, 주소창의 값은 바로 지운다. */
function kakaoReturn(){
  let mark = null;
  try{ mark = sessionStorage.getItem(KAKAO_MARK); sessionStorage.removeItem(KAKAO_MARK) }catch(e){}
  if(!mark) return;                      /* 우리가 보낸 이동이 아니면 주소창을 읽지도 않는다 */
  const qs = new URLSearchParams(location.search);
  if(!qs.has('state') || !(qs.has('code') || qs.has('error'))) return;
  const code = qs.get('code'), state = qs.get('state'), error = qs.get('error');
  history.replaceState(history.state, '', location.pathname + location.hash);
  if(error){
    if(error !== 'access_denied') acctToast('카카오 로그인을 완료하지 못했습니다.');   /* 취소는 오류로 보이지 않는다 */
    return;
  }
  kakaoLogin(code, state).then(data => {
    if(data.authenticated){ authLogin(data.user); return; }
    if(data.needs_signup) enterSocialSignup('kakao', data.kakao || {});
  }).catch(e => acctToast((e && e.message) || '카카오 로그인에 실패했습니다.'));
}

/* 처음 온 소셜 계정 — 가입 화면을 소셜 모드로 연다.
   아이디 칸에는 그 계정의 이메일을 읽기 전용으로 두고, 비밀번호·이메일 인증 칸은 숨긴다.
   (카카오는 이메일을 안 줄 수 있다 — 그땐 '카카오 계정' 으로 적어 둔다) */
function enterSocialSignup(provider, info){
  goView('signup');
  resetSignupForm();
  signupSocial = provider;
  const label = SOCIAL_LABEL[provider];
  const suIdField = $('#suIdField'), suPwBlock = $('#suPwBlock'), emailField = $('#suEmailField'),
        div = $('#signupGoogleDivider'), note = $('#signupGoogleNote'), suId = $('#suId'),
        nick = $('#suNickname');
  ['#googleSignupBtn', '#kakaoSignupBtn'].forEach(sel => { const b = $(sel); if(b) b.hidden = true; });
  if(div) div.hidden = true;
  if(suPwBlock) suPwBlock.hidden = true;
  if(emailField) emailField.hidden = true;
  if(note){ note.textContent = label + ' 계정으로 가입을 진행합니다. 아래 정보를 마저 입력해 주세요.'; note.hidden = false; }
  if(suIdField) suIdField.hidden = false;
  if(suId){ suId.value = info.email || label + ' 계정'; suId.readOnly = true; }
  if(nick && !nick.value) nick.value = String(info.name || '').trim().slice(0, 12);
}

/* 이메일 인증 칸을 처음 상태로 — 주소를 바꾸거나 가입 폼을 새로 열 때 */
function emailVerifyReset(){
  emailVerified = '';
  clearInterval(emailGapTimer); emailGapTimer = 0;
  const send = $('#suEmailSend'), row = $('#suCodeRow'), msg = $('#suEmailMsg'), code = $('#suCode');
  if(send){ send.disabled = false; send.textContent = '인증번호 받기'; }
  if(row) row.hidden = true;
  if(code) code.value = '';
  if(msg){ msg.textContent = ''; msg.className = 'fieldMsg'; }
}
function emailMsg(text, kind){
  const msg = $('#suEmailMsg'); if(!msg) return;
  msg.textContent = text; msg.className = 'fieldMsg' + (kind ? ' ' + kind : '');
}

/* 회원가입 폼 초기화 — 완료하지 않고 다른 화면으로 나가면 구글 모드를 포함해
   다음에 다시 들어왔을 때 처음 상태 그대로 보이게 한다. */
export function resetSignupForm(){
  signupSocial = '';
  const ks = $('#kakaoSignupBtn'), emailField = $('#suEmailField');
  if(ks) ks.hidden = false;
  if(emailField) emailField.hidden = false;
  emailVerifyReset();
  const gs = $('#googleSignupBtn'), suIdField = $('#suIdField'), suPwBlock = $('#suPwBlock'),
        div = $('#signupGoogleDivider'), note = $('#signupGoogleNote'), suId = $('#suId'),
        err = $('#signupErr'), form = $('#signupForm'),
        idMsg = $('#suIdMsg'), pwMsg = $('#suPwMsg'), bodyMsg = $('#suBodyMsg');
  if(gs) gs.hidden = false;
  if(suIdField) suIdField.hidden = false;
  if(suPwBlock) suPwBlock.hidden = false;
  if(div) div.hidden = false;
  if(note) note.hidden = true;
  if(suId) suId.readOnly = false;
  if(err) err.style.display = 'none';
  if(form) form.reset();
  if(idMsg){ idMsg.textContent = ''; idMsg.className = 'fieldMsg'; }
  if(pwMsg){ pwMsg.textContent = ''; pwMsg.className = 'fieldMsg'; }
  if(bodyMsg){ bodyMsg.textContent = ''; bodyMsg.className = 'fieldMsg'; }
  jobFieldReset('su', null);   /* form.reset() 은 파일 버튼 글자까지는 못 되돌린다 */
}

export function acctBoot(){
  /* ── 로그인 ── */
  const lf = $('#loginForm');
  if(lf) lf.addEventListener('submit', async e => {
    e.preventDefault();
    const id = $('#loginId').value.trim(), pw = $('#loginPw').value.trim();
    const err = $('#loginErr');
    if(!id || !pw){ err.style.display = 'block'; return; }
    err.style.display = 'none';
    const submit=lf.querySelector('[type="submit"]'); if(submit)submit.disabled=true;
    try{
      const data=await loginAccount(id,pw);
      authLogin(data.user);
      lf.reset();
    }catch(ex){ err.textContent=ex.message||'로그인하지 못했습니다.'; err.style.display='block' }
    finally{ if(submit)submit.disabled=false }
  });
  /* Google 로그인 — 화면이 뜰 때 GIS 스크립트와 클라이언트를 미리 준비해 둔다
     (클릭 뒤에 준비하면 브라우저가 팝업을 막는다). */
  prepareGoogle().catch(()=>{ /* 서버 연결 실패는 아래 session() 경고가 이미 알린다 */ });
  const gl = $('#googleLoginBtn');
  if(gl) gl.addEventListener('click', ()=>googleContinue(gl, $('#loginErr')));
  const kl = $('#kakaoLoginBtn');
  if(kl) kl.addEventListener('click', ()=>kakaoContinue(kl, $('#loginErr')));
  kakaoReturn();

  /* ── 직업 선택 · 서류 첨부 (가입 · 회원정보 수정 공통) ── */
  jobFieldBind('su');
  jobFieldBind('edit');
  jobReviewBind((ok, err) => acctToast(err ? err : ok ? '승인했어요. 해당 사용자의 직업·배지가 반영됩니다.' : '반려했어요.'));
  planReviewBind((done, err) => acctToast(err ? err
    : done === 'approve' ? '승인했어요. 해당 사용자의 요금제가 바로 바뀝니다.'
    : done === 'revoke' ? '프리로 되돌렸어요.' : '반려했어요.'));

  /* ── 회원가입 ── */
  const sf = $('#signupForm');
  if(sf) sf.addEventListener('submit', async e => {
    e.preventDefault();
    const err = $('#signupErr');
    const nick = $('#suNickname').value.trim();
    const pw = $('#suPw').value, pw2 = $('#suPw2').value;
    const id = $('#suId').value.trim();
    const email = ($('#suEmail').value || '').trim().toLowerCase();
    let msg = '';
    if(signupSocial){
      /* 소셜 가입 — 아이디 칸엔 그 계정의 이메일이 이미 채워져 있고 수정할 수 없다.
         비밀번호도 소셜 계정이 대신하니 닉네임·체형만 본다 */
      if(nick.length < 2 || nick.length > 12) msg = '닉네임은 2~12자로 입력해 주세요.';
      else {
        const b = bodyCheck($('#suHeight').value, $('#suWeight').value);
        if(b) msg = b;
      }
    }else{
      if(!/^[A-Za-z0-9]{4,16}$/.test(id)) msg = '아이디는 영문·숫자 4~16자로 입력해 주세요.';
      else if(!emailVerified || emailVerified !== email) msg = '이메일 인증을 완료해 주세요.';
      else if(nick.length < 2 || nick.length > 12) msg = '닉네임은 2~12자로 입력해 주세요.';
      else if(pw.length < 8) msg = '비밀번호는 8자 이상이어야 합니다.';
      else if(pw !== pw2) msg = '비밀번호가 서로 다릅니다.';
      else {
        const b = bodyCheck($('#suHeight').value, $('#suWeight').value);
        if(b) msg = b;
      }
    }
    if(!msg && !sf.querySelector('input[name="suGender"]:checked')) msg = '성별을 선택해 주세요.';
    if(!msg) msg = jobFieldCheck('su', null);
    if(!msg && !$('#suAgeAgree').checked) msg = '만 14세 이상만 가입할 수 있습니다.';
    if(!msg && !$('#suTermsAgree').checked) msg = '이용약관에 동의해 주세요.';
    if(!msg && !$('#suPrivacyAgree').checked) msg = '개인정보처리방침을 확인해 주세요.';
    if(msg){ err.textContent = msg; err.style.display = 'block'; return; }
    err.style.display = 'none';
    const submit=sf.querySelector('[type="submit"]'); if(submit)submit.disabled=true;
    try{
      const profileFields={
        nickname:nick,
        birth_date:$('#suBirth').value||'',
        height:$('#suHeight').value||null,
        weight:$('#suWeight').value||null,
        gender:sf.querySelector('input[name="suGender"]:checked').value,
      };
      /* 소셜 가입은 서버 세션에 보관된 Google·카카오 신원으로 계정을 만든다 —
         아이디·비밀번호는 보내지 않는다. 아이디 가입은 인증을 마친 이메일을 함께 보낸다. */
      const data=signupSocial==='google' ? await googleSignupAccount(profileFields)
        : signupSocial==='kakao' ? await kakaoSignupAccount(profileFields)
        : await signupAccount({ username:id, password:pw, email, ...profileFields });
      applyAccount(data.user);
      ME.role='user'; ME.job=''; ME.major='';
      /* 인증이 필요한 직업을 골랐으면 심사를 신청한다 — 승인 전까지 직업은 비어 있다 */
      let jobMsg='';
      try{
        const r=await jobFieldApply('su', ME);
        if(r&&r.pending) jobMsg='직업 인증을 신청했어요. 관리자 승인 후 배지가 달립니다.';
      }catch(jx){ jobMsg='가입은 됐지만 직업 인증 신청은 실패했어요 — '+(jx.message||'')+' 회원정보 수정에서 다시 올려 주세요.'; }
      signupComplete();
      /* ★ 2026-09-23 — 가입이 끝났다는 말을 한 번은 해 준다.
         예전에는 곧바로 '즐겨입는 스타일 고르기' 팝업만 떠서, 가입이 된 것인지
         아직 한 단계가 남은 것인지 알 수 없었다.
         (직업 인증을 신청했으면 그 안내가 600ms 뒤 이어서 뜬다) */
      acctToast('회원 가입이 완료되었어요.');
      if(jobMsg) setTimeout(()=>acctToast(jobMsg), 600);
      sf.reset();
    }catch(ex){ err.textContent=ex.message||'회원가입하지 못했습니다.'; err.style.display='block' }
    finally{ if(submit)submit.disabled=false }
  });
  /* 구글로 계속하기 — 이미 연결된 Google 계정이면 바로 로그인하고,
     처음이면 같은 회원가입 폼 위에서 아이디/비밀번호 입력만 막고 닉네임·생년월일·체형을 마저 받는다. */
  const gs = $('#googleSignupBtn');
  if(gs) gs.addEventListener('click', () => googleContinue(gs, $('#signupErr')));
  const ks = $('#kakaoSignupBtn');
  if(ks) ks.addEventListener('click', () => kakaoContinue(ks, $('#signupErr')));

  /* 이메일 인증 — [인증번호 받기] → 메일로 온 6자리 → [확인].
     인증한 뒤 주소를 고치면 처음부터 다시 받는다. */
  const suEmail = $('#suEmail'), suEmailSend = $('#suEmailSend'), suCode = $('#suCode'), suCodeCheck = $('#suCodeCheck');
  if(suEmail) suEmail.addEventListener('input', () => {
    if(emailVerified && suEmail.value.trim().toLowerCase() !== emailVerified) emailVerifyReset();
  });
  if(suEmailSend) suEmailSend.addEventListener('click', async () => {
    const email = suEmail.value.trim().toLowerCase();
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){ emailMsg('이메일 주소를 올바르게 입력해 주세요.', 'err'); return; }
    suEmailSend.disabled = true;
    try{
      await emailCode(email);
      emailVerified = '';
      $('#suCodeRow').hidden = false;
      suCode.value = ''; suCode.focus();
      emailMsg('인증번호를 보냈어요. 10분 안에 입력해 주세요. 메일이 없으면 스팸함도 확인해 주세요.', 'ok');
      /* 서버가 같은 주소로 1분 안에 다시 보내지 않는다 — 버튼에도 남은 시간을 보여 준다 */
      let left = 60;
      suEmailSend.textContent = '다시 받기 (' + left + ')';
      clearInterval(emailGapTimer);
      emailGapTimer = setInterval(() => {
        left -= 1;
        if(left > 0){ suEmailSend.textContent = '다시 받기 (' + left + ')'; return; }
        clearInterval(emailGapTimer); emailGapTimer = 0;
        if(!emailVerified){ suEmailSend.disabled = false; suEmailSend.textContent = '다시 받기'; }
      }, 1000);
    }catch(ex){
      suEmailSend.disabled = false;
      emailMsg(ex.message || '인증번호를 보내지 못했습니다.', 'err');
    }
  });
  const codeCheck = async () => {
    const email = suEmail.value.trim().toLowerCase(), code = suCode.value.trim();
    if(!/^\d{6}$/.test(code)){ emailMsg('인증번호 6자리를 입력해 주세요.', 'err'); return; }
    suCodeCheck.disabled = true;
    try{
      await emailVerify(email, code);
      emailVerified = email;
      clearInterval(emailGapTimer); emailGapTimer = 0;
      $('#suCodeRow').hidden = true;
      suEmailSend.disabled = true; suEmailSend.textContent = '인증 완료';
      emailMsg('이메일 인증이 완료됐어요.', 'ok');
    }catch(ex){ emailMsg(ex.message || '인증번호를 확인하지 못했습니다.', 'err'); }
    finally{ suCodeCheck.disabled = false; }
  };
  if(suCodeCheck) suCodeCheck.addEventListener('click', codeCheck);
  if(suCode) suCode.addEventListener('keydown', e => {
    if(e.key === 'Enter' && !e.isComposing){ e.preventDefault(); codeCheck(); }
  });
  /* 아이디·비밀번호 안내는 치는 동안 바로 알려 준다 */
  const suId = $('#suId'), suIdMsg = $('#suIdMsg');
  if(suId) suId.addEventListener('input', () => {
    const v = suId.value.trim();
    if(!v){ suIdMsg.textContent = ''; suIdMsg.className = 'fieldMsg'; return; }
    const ok = /^[A-Za-z0-9]{4,16}$/.test(v);
    suIdMsg.textContent = ok ? '사용할 수 있는 아이디입니다.' : '영문·숫자 4~16자';
    suIdMsg.className = 'fieldMsg ' + (ok ? 'ok' : 'err');
  });
  const suPw = $('#suPw'), suPw2 = $('#suPw2'), suPwMsg = $('#suPwMsg');
  const pwCheck = () => {
    if(!suPw.value && !suPw2.value){ suPwMsg.textContent = ''; suPwMsg.className = 'fieldMsg'; return; }
    const ok = suPw.value.length >= 8 && suPw.value === suPw2.value;
    suPwMsg.textContent = suPw.value.length < 8 ? '8자 이상 입력해 주세요.'
      : (ok ? '비밀번호가 일치합니다.' : '비밀번호가 서로 다릅니다.');
    suPwMsg.className = 'fieldMsg ' + (ok ? 'ok' : 'err');
  };
  if(suPw) suPw.addEventListener('input', pwCheck);
  if(suPw2) suPw2.addEventListener('input', pwCheck);

  /* 체형 — 비워 둬도 통과시킨다. 넣었다면 사람 범위인지만 본다. */
function bodyCheck(h,w){
  if(h && (h<120 || h>220)) return '키는 120~220cm 사이로 입력해 주세요.';
  if(w && (w<30  || w>200)) return '몸무게는 30~200kg 사이로 입력해 주세요.';
  return '';
}
/* 가입 화면에서 치는 동안 세그먼트를 미리 알려 준다 */
const suH=$('#suHeight'), suW=$('#suWeight'), suBodyMsg=$('#suBodyMsg');
function bodyHint(){
  if(!suBodyMsg)return;
  const h=+suH.value, w=+suW.value;
  const bad=bodyCheck(suH.value,suW.value);
  if(bad){ suBodyMsg.textContent=bad; suBodyMsg.className='fieldMsg err'; return }
  if(!h||!w){ suBodyMsg.textContent=''; suBodyMsg.className='fieldMsg'; return }
  const bmi=w/((h/100)**2);
  const seg=bmi<18.5?'슬림':bmi<23?'표준':bmi<25?'스탠다드 플러스':'볼륨';
  suBodyMsg.textContent=''+seg+' 세그먼트로 분류돼요. 비슷한 체형의 살!말? 를 먼저 보여 드립니다.';
  suBodyMsg.className='fieldMsg ok';
}
if(suH) suH.addEventListener('input', bodyHint);
if(suW) suW.addEventListener('input', bodyHint);

/* ── 마이페이지 ── */
  acctChips($('#styleWrap'), ME.styles);
  const ssb = $('#styleSaveBtn');
  if(ssb) ssb.addEventListener('click', async () => {
    ssb.disabled=true;
    try{
      const data=await saveAccount({styles:styleNames()});
      applyAccount(data.user); myRender();
      acctToast('즐겨입는 스타일이 저장되었어요.');
    }catch(e){ acctToast(e.message||'스타일을 저장하지 못했습니다.') }
    finally{ ssb.disabled=false }
  });
  /* 로그아웃은 헤더 계정 메뉴 한 곳으로 모았다 (#menuLogout) */
  /* 아이콘 색 바꾸기 */
  const avb = $('#avatarEditBtn');
  if(avb) avb.addEventListener('click', () => {
    const w = $('#avaPick');
    if(w) w.innerHTML = AVA.map((g, i) =>
      '<button type="button" class="avaSw' + (i === ME.ava ? ' on' : '') +
      '" data-ava="' + i + '" style="background:linear-gradient(135deg,' + g[0] + ',' + g[1] + ')"' +
      ' aria-label="아이콘 ' + (i + 1) + '"></button>').join('');
    acctModal('avatarModal', true);
  });
  const aw = $('#avaPick');
  if(aw) aw.addEventListener('click', async e => {
    const b = e.target.closest('[data-ava]');
    if(!b) return;
    try{
      const data=await saveAccount({avatar:+b.dataset.ava});
      applyAccount(data.user);
      $$('.avaSw', aw).forEach(x => x.classList.toggle('on', x === b));
      avaPaint(); authPaint();
      setTimeout(() => acctModal('avatarModal', false), 240);
    }catch(ex){ acctToast(ex.message||'아이콘을 저장하지 못했습니다.') }
  });
  const ep = $('#editProfileBtn');
  if(ep) ep.addEventListener('click', () => {
    $('#editNickname').value = ME.name;
    $('#editBirth').value = ME.birth || '';
    $('#editHeight').value = ME.height || '';
    $('#editWeight').value = ME.weight || '';
    $$('#editProfileForm input[name="editGender"]').forEach(r => { r.checked = r.value===ME.gender; });
    /* ★ 2026-09-23 — 비밀번호 칸은 열 때마다 반드시 비운다.
       예전에는 그대로 남아 있었다. 저장이 한 번 실패해 닫았다가 다시 열면
       아까 친 비밀번호가 칸에 그대로 있고, 다음 저장 때 같이 올라가
       **바꿀 생각이 없던 비밀번호가 바뀐다.** */
    $('#editPw').value = '';
    $('#editPw2').value = '';
    editPwMsg('');
    $('#editModalErr').style.display = 'none';
    jobFieldReset('edit', ME);
    /* 운영자 계정은 직업을 바꾸지 않는다 — 칸은 보이되 잠가 둔다 */
    const ej = $('#editJob'), ejb = $('#editJobFileBtn'), ejm = $('#editJobMsg');
    if(ej) ej.disabled = (ME.role === 'admin');
    if(ME.role === 'admin'){
      if(ejb) ejb.disabled = true;
      if(ejm){ ejm.textContent = '운영자 계정은 직업 대신 ADMIN 으로 표시됩니다.'; ejm.className = 'fieldMsg'; }
    }
    acctModal('editModal', true);
  });
  const ef = $('#editProfileForm');
  /* 비밀번호 칸을 다시 건드리면 안내를 지운다 — 고친 뒤에도 빨간 줄이 남아 있지 않게 */
  [$('#editPw'), $('#editPw2')].forEach(i => i && i.addEventListener('input', () => editPwMsg('')));
  if(ef) ef.addEventListener('submit', async e => {
    e.preventDefault();
    const nick = $('#editNickname').value.trim();
    const pw = $('#editPw').value, pw2 = $('#editPw2').value;
    const err = $('#editModalErr');
    /* ★ 2026-09-23 — 비밀번호 안내는 맨 아래 공용 자리가 아니라 그 칸 바로 아래에 띄운다.
       예전에는 직업 안내 밑에 붙어서, 어느 칸을 고치라는 말인지 이어지지 않았다. */
    let pwErr = '';
    if(pw && pw.length < 8) pwErr = '새 비밀번호는 8자 이상이어야 합니다.';
    else if(pw !== pw2) pwErr = '새 비밀번호가 서로 다릅니다.';
    editPwMsg(pwErr);
    let msg = '';
    if(nick.length < 2 || nick.length > 12) msg = '닉네임은 2~12자로 입력해 주세요.';
    else if(!pwErr) msg = bodyCheck($('#editHeight').value, $('#editWeight').value) || '';
    if(!msg && !pwErr && ME.role !== 'admin') msg = jobFieldCheck('edit', ME);
    if(msg){ err.textContent = msg; err.style.display = 'block'; return; }
    err.style.display = 'none';
    if(pwErr){ $('#editPw').focus(); return; }
    const submit=ef.querySelector('[type="submit"]'); if(submit)submit.disabled=true;
    try{
      const data=await saveAccount({
        nickname:nick, birth_date:$('#editBirth').value||'',
        height:$('#editHeight').value||null, weight:$('#editWeight').value||null,
        gender:ef.querySelector('input[name="editGender"]:checked')?.value||null,
        password:pw||'',
      });
      applyAccount(data.user);
      /* ★ 2026-09-23 — 'DB에 저장됐어요'는 우리가 쓰는 말이지 사용자의 말이 아니다.
         사용자가 알고 싶은 것은 저장소가 아니라 '수정이 끝났는가' 하나다.
         비밀번호를 함께 바꿨을 때만 그 사실을 따로 알려 준다
         (지금 창은 update_session_auth_hash 덕분에 로그인 상태가 그대로 유지된다 —
          그래서 '다음 로그인부터'라고 적는다). */
      let saved=pw
        ? '비밀번호가 변경되었어요. 다음 로그인부터 새 비밀번호를 사용하세요.'
        : '회원 정보가 수정되었어요.';
      if(ME.role !== 'admin'){
        try{
          const r=await jobFieldApply('edit', ME);
          if(r&&r.pending) saved='저장했어요. 직업 인증은 관리자 승인 후 반영됩니다.';
        }catch(jx){ saved='회원정보는 저장했지만 직업 인증 신청은 실패했어요 — '+(jx.message||''); }
      }
      acctModal('editModal', false);
      editPwMsg('');
      ef.reset(); myRender(); authPaint();
      acctToast(saved);
      /* ★ 2026-09-19 — 닉네임을 바꾸면 이미 올린 살!말? 카드의 작성자 이름도 함께 바뀌어야 한다.
         카드 목록은 한 번 받아 두고 쓰므로, 여기서 다시 받아 오라고 알려 준다. */
      if(typeof window.smReloadVotes === 'function') window.smReloadVotes();
      if(typeof trRender === 'function' && document.body.dataset.view === 'trend') trRender('myfeed');
    }catch(ex){ err.textContent=ex.message||'회원정보를 저장하지 못했습니다.'; err.style.display='block' }
    finally{ if(submit)submit.disabled=false }
  });
  [$('#editModalClose'), $('#editModalCancel')].forEach(b =>
    b && b.addEventListener('click', () => acctModal('editModal', false)));

  /* 저장 · 투표 목록 모달 — 실제 찜 목록과 투표 이력을 그대로 보여 준다 */
  const sb = $('#statSavedBtn');
  if(sb) sb.addEventListener('click', () => {
    const g = $('#savedGrid');
    const items = [...LIKED.entries()];
    if(g) g.innerHTML = items.map(([id, d]) => itemCard({ ...d, id })).join('') ||
      '<p class="fieldMsg">찜한 아이템이 없습니다.</p>';
    acctModal('savedModal', true);
  });
  const vb = $('#statVotedBtn');
  if(vb) vb.addEventListener('click', () => {
    const g = $('#votedGrid');
    const voted = (typeof VOTES !== 'undefined')
      ? VOTES.filter(v => v.voted !== null && v.voted !== undefined) : [];
    if(g) g.innerHTML = voted.map(v => itemCard({
      img: v.imgURL, tag: v.voted === 0 ? '살! 선택' : '말? 선택',
      br: v.b, nm: v.t, pr: fmtWon(v.p)
    })).join('') || '<p class="fieldMsg oneLine">아직 투표한 카드가 없습니다. 살!말? 에서 골라 보세요.</p>';
    acctModal('votedModal', true);
  });
  /* 뱃지 — 컬렉션 뱃지 전용 자리다.
     등급은 뱃지가 아니라 아바타 링으로 표현하기로 했으니 여기 섞지 않는다.
     팀원 컬렉션 뱃지가 도착하면 BADGES 배열만 채우면 그대로 그려진다. */
  const bb = $('#statBadgeBtn');
  if(bb) bb.addEventListener('click', () => { bgRender(); acctModal('badgeModal', true) });
  /* 알림에서 뱃지 설명 창 바로 열기 — 달성 여부·진행도는 서버 값을 다시 받아 맞춘다 */
  window.feeditOpenBadge = id => {
    bgRender(); bgSelect(id); acctModal('badgeModal', true);
    session(true).then(d => { if(d && d.user){ applyAccount(d.user); bgRender(); bgSelect(id) } }).catch(() => {});
  };
  /* 타일을 고르면 위 상세 패널이 바뀐다 */
  const bg = $('#badgeGrid');
  if(bg) bg.addEventListener('click', e => {
    const t = e.target.closest('.bgTile'); if(!t) return;
    $$('.bgTile.active', bg).forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const b = BADGES.find(x => x.id === t.dataset.badge);
    if(b) bgDetail(b);
  });

  /* ★ 2026-09-23 — 회원 탈퇴를 실제로 지운다.
     예전에는 확인만 받고 로그아웃해서, 같은 아이디로 다시 로그인하면 계정이 그대로 있었다.
     지금은 서버(/api/auth/withdraw)가 계정과 딸린 기록(찜 · 투표 · 알림 · 인증)을 지운다.
     서버가 실패하면 로그아웃하지 않는다 — 지워지지 않았는데 지워진 것처럼 보이면 안 된다. */
  const lv = $('#leaveBtn');
  if(lv) lv.addEventListener('click', () => acctModal('leaveModal', true));
  const lvGo = $('#leaveConfirm');
  if(lvGo) lvGo.addEventListener('click', async () => {
    if(lvGo.disabled) return;
    lvGo.disabled = true;
    const label = lvGo.textContent;
    lvGo.textContent = '탈퇴 처리 중…';
    try{
      await withdrawAccount();
      acctModal('leaveModal', false);
      /* 세션은 서버에서 이미 끊겼다 — 화면 쪽 흔적만 정리한다 */
      AUTH.in = false;
      likedClear();
      badgesApply(null);
      resetAccount();
      fbReset();
      document.dispatchEvent(new CustomEvent('feedit:auth'));
      pendingAfterAuth = null;
      authPaint();
      goView('home');
      acctToast('탈퇴가 완료됐습니다. 그동안 이용해 주셔서 감사합니다.');
    }catch(e){
      acctToast(e.message || '탈퇴를 처리하지 못했습니다.');
    }finally{
      lvGo.disabled = false;
      lvGo.textContent = label;
    }
  });
  $$('[data-close-modal]').forEach(b =>
    b.addEventListener('click', () => $$('.acctModal').forEach(m => m.classList.remove('on'))));

  /* 트렌드 분석 로그인 안내 팝업 — 로그인은 로그인 화면으로, 취소는 홈으로 */
  const trGateLogin = $('#trendGateLogin');
  if(trGateLogin) trGateLogin.addEventListener('click', () => {
    acctModal('trendGateModal', false);
    goView('login');
  });
  const trGateCancel = $('#trendGateCancel');
  if(trGateCancel) trGateCancel.addEventListener('click', () => {
    acctModal('trendGateModal', false);
    goView('home');
  });
  /* ★ 2026-09-20 — data-lock 이 달린 창(트렌드 분석 로그인 안내)은 바깥 클릭 · Esc 로 닫히지 않는다.
     닫히면 로그인 없이 뒤편 화면을 그대로 눌러 볼 수 있었다. '취소' · '로그인' 으로만 빠져나간다. */
  $$('.acctModal').forEach(m => m.addEventListener('click', e => {
    if(e.target === m && !m.dataset.lock) m.classList.remove('on');
  }));
  addEventListener('keydown', e => {
    if(e.key === 'Escape') $$('.acctModal').forEach(m => { if(!m.dataset.lock) m.classList.remove('on') });
  });

  /* 헤더 계정 메뉴 */
  const ab = $('#mAuthBtn');
  if(ab) ab.addEventListener('click', e => {
    if(!AUTH.in) return;              /* 로그인 전에는 data-v 위임이 로그인 화면으로 보낸다 */
    e.stopPropagation();
    acctMenu();
  });
  const mm = $('#menuMypage');
  if(mm) mm.addEventListener('click', () => { acctMenu(false); goView('mypage') });
  const mj = $('#menuJobReview');
  if(mj) mj.addEventListener('click', () => {
    acctMenu(false);
    if(ME.role !== 'admin') return;   /* 운영 계정만 — 서버도 403 으로 막는다 */
    jobReviewRender(); acctModal('jobReviewModal', true);
  });
  /* 알림(직업 인증 심사 대기 N건)에서 바로 여는 손잡이 */
  window.feeditOpenJobReview = () => {
    if(ME.role !== 'admin') return;
    acctMenu(false); jobReviewRender(); acctModal('jobReviewModal', true);
  };
  /* 요금제 신청 심사 (2026-10-03) — 계정 메뉴 · 알림(신청 대기 N건)에서 연다 */
  const openPlanReview = () => {
    acctMenu(false);
    if(ME.role !== 'admin') return;   /* 운영 계정만 — 서버도 403 으로 막는다 */
    planReviewRender(); acctModal('planReviewModal', true);
  };
  const mpr = $('#menuPlanReview');
  if(mpr) mpr.addEventListener('click', openPlanReview);
  window.feeditOpenPlanReview = openPlanReview;
  const ml = $('#menuLogout');
  if(ml) ml.addEventListener('click', () => { acctMenu(false); authLogout() });
  document.addEventListener('click', e => {
    if(!e.target.closest('.mAuthWrap')) acctMenu(false);
  });
  document.addEventListener('feedit:popover', e => { if(e.detail !== 'acct') acctMenu(false) });

  authPaint();
  rkPaintAll();      /* 화면에 이미 떠 있는 아바타들도 한 번 맞춰 둔다 */
  /* 새로고침해도 Django 세션 쿠키로 로그인 상태와 프로필을 복원한다. */
  session().then(data=>{
    /* 로그인 전에도 요금제 화면은 베타인지 알아야 한다 (plan.js) */
    if(!data.authenticated) planApply(data.billing);
    if(!data.authenticated||!data.user)return;
    applyAccount(data.user); AUTH.in=true; authPaint();
    likedAfterAuth();
    acctChips($('#styleWrap'),ME.styles);
    if(document.body.dataset.view==='mypage')myRender();
    /* 복구로 로그인 상태가 됐다 — 보고 있던 화면이 새 계정 기준으로 다시 그려진다 */
    authNotify(true);
  }).catch(e=>console.warn('[account]',e.message||e))
    /* 복구됐든 아니든 '이제 판정해도 된다' 는 반드시 알린다 —
       실패했을 때 알리지 않으면 로그아웃 상태에서 관문이 영영 안 선다. */
    .finally(authSettled);
}

/* 알파 테스트 모드 — 시연 15일 한정 (app_shell/static/js/alpha.js 와 한 쌍).
   방문자에게 알파 계정이 자동 발급되면 헤더·프로필을 로그인 상태로 다시 그린다.
   alpha.js 를 여기서 import 하지 않고 이벤트로만 받는다 — 모듈 순환을 만들지 않기 위해서다.
   기간이 끝나면 이 블록만 지우면 된다. */
document.addEventListener('feedit:alpha-issued', () => {
  session(true).then(data=>{
    if(!data.authenticated||!data.user)return;
    applyAccount(data.user); AUTH.in=true; authPaint();
    likedAfterAuth();
    acctChips($('#styleWrap'),ME.styles);
    if(document.body.dataset.view==='mypage')myRender();
    /* 알파 계정이 발급되면 그것도 로그인이다 — 관문·화면이 다시 판정하게 알린다 */
    authNotify(true);
  }).catch(()=>{}).finally(authSettled);
});
