/* 알파 테스트 모드 — 해커톤 시연 15일 한정.
 *
 * 하는 일 세 가지.
 *   1) 로그인 안 한 채로 들어온 사람에게 알파 계정을 하나 발급받아 바로 로그인시킨다.
 *      (접속자마다 다른 계정. 같은 브라우저로 다시 오면 세션 쿠키가 살아 있는 한 같은 계정)
 *   2) 상단에 안내 배너를 띄우고 챗봇 잔여 횟수를 보여 준다.
 *   3) 처음 한 번만 핵심 4곳을 순서대로 하이라이트하는 가이드를 돌린다.
 *
 * 기간이 끝나면 이 파일과 backend/apps/api/alpha_views.py,
 * account_api.js 의 alpha* 세 줄, main.js·main.css 의 import 한 줄씩을 지우면
 * 원래 상태로 돌아간다. 다른 파일의 동작은 바꾸지 않았다.
 */
import { session, alphaAccount, alphaQuota } from '../../../account/static/js/account_api.js';

const TOUR_KEY = 'feedit.alpha.tour.v1';
const BANNER_KEY = 'feedit.alpha.banner.v1';
const ASKED_KEY = 'feedit.alpha.asked.v1';
const STYLE_MAX = 3;                 /* 정식 가입과 같은 규칙 */

/* 챗봇 쪽(chat_api.js)이 횟수를 쓰고 나서 여기에 알려 준다 */
export const ALPHA_EVENT = 'feedit:alpha-quota';

let state = { alpha:false, limit:null, used:0, remaining:null };

export function alphaState(){ return state; }

export function setAlphaState(next){
  if(!next) return;
  state = { ...state, ...next };
  paintBanner();
  document.dispatchEvent(new CustomEvent(ALPHA_EVENT, { detail:state }));
}

/* ── 1. 부팅 — 미로그인이면 알파 계정 발급 ───────────────── */
async function boot(){
  let me = null;
  try { me = await session(); }
  catch (_) { return; }                    /* 백엔드가 안 떠 있으면 조용히 포기 */

  if(!me || !me.authenticated){
    /* 한 번 거절한 사람에게 매번 다시 묻지 않는다 */
    if(askedAlready()) return;
    /* 로딩·소개 화면에서는 띄우지 않는다 — 메인에 실제로 들어온 뒤에만 묻는다 */
    whenMainView(() => setTimeout(openInvite, 600));
    return;
  }

  try { setAlphaState(await alphaQuota()); } catch(_){ return; }
  if(!state.alpha) return;                 /* 정식 회원은 배너도 가이드도 없다 */
  whenMainView(() => {
    mountBanner();
    if(!seen(TOUR_KEY)) setTimeout(startTour, 700);
  });
}

/* 메인 화면에 들어왔을 때 한 번만 실행한다.
   router.js 의 enterMain() 이 body 에 'mainmode' 를 붙이는 것이 유일한 신호다
   (#startBtn · #jumpBtn · 뒤로가기 복원이 모두 그 함수를 지난다).
   router 를 import 하지 않고 클래스만 지켜본다 — 모듈 순환을 만들지 않기 위해서다. */
function whenMainView(run){
  const inMain = () => document.body.classList.contains('mainmode');
  if(inMain()) return run();
  const watch = new MutationObserver(() => {
    if(!inMain()) return;
    watch.disconnect();
    run();
  });
  watch.observe(document.body, { attributes:true, attributeFilter:['class'] });
}

/* ── 1-1. 빠른 계정 만들기 창 ────────────────────────── */
let inviteEl = null;

function closeInvite(){
  if(inviteEl){ inviteEl.remove(); inviteEl = null; }
}

export function openInvite(){
  if(inviteEl) return;
  inviteEl = document.createElement('div');
  inviteEl.className = 'alphaInvite';
  inviteEl.id = 'alphaInvite';
  inviteEl.innerHTML = '<div class="alphaInviteScrim"></div><div class="alphaCard" role="dialog" aria-modal="true"></div>';
  document.body.appendChild(inviteEl);
  inviteEl.querySelector('.alphaInviteScrim').addEventListener('click', () => {
    markAsked(false);          /* 바깥을 눌러 닫은 것은 '이번 방문만' 으로 본다 */
    closeInvite();
  });
  paintChoice();
}

function paintChoice(){
  const card = inviteEl.querySelector('.alphaCard');
  card.innerHTML =
    '<span class="alphaBadge">ALPHA TEST</span>' +
    '<h3>지금은 알파테스트 기간입니다</h3>' +
    '<p>회원가입 없이 <b>빠른 계정</b>을 만들어 바로 둘러보실 수 있습니다.<br>' +
    '챗봇 20회 제한 외에는 모든 기능을 그대로 쓰실 수 있어요.</p>' +
    '<div class="alphaPick">' +
      '<button type="button" class="alphaPrimary" data-a="quick">빠른 계정 생성하기</button>' +
      /* data-v="signup" 은 router.js 의 전역 클릭 위임이 받아 회원가입 화면으로 보낸다 —
         router 를 import 하지 않는 이유는 모듈 순환을 피하기 위해서다. */
      '<button type="button" class="alphaGhost" data-a="signup" data-v="signup">그냥 회원가입</button>' +
    '</div>' +
    '<button type="button" class="alphaLater" data-a="later">나중에 할게요</button>';
  card.onclick = e => {
    const b = e.target.closest('[data-a]');
    if(!b) return;
    if(b.dataset.a === 'quick') return paintForm();
    /* 회원가입을 고른 사람에게는 다시 묻지 않는다. '나중에' 는 이번 방문만 조용히 둔다. */
    markAsked(b.dataset.a === 'signup');
    closeInvite();          /* 'signup' 이동은 위 data-v 를 router 가 받아 처리한다 */
  };
}

/* 스타일 목록·썸네일은 정식 가입 뒤 뜨는 선택 팝업과 **같은 원본**을 쓴다.
   목록은 chat.js 의 STYLES, 사진은 style_page.js 의 SIMG(s.ph || IMG(s.img)),
   마크업·CSS 는 profile.css 의 .styleSelectGrid / .styleSelCard 를 그대로 쓴다.
   정적 import 를 쓰면 모듈 순환이 생겨(chat_api → alpha → chat → chat_api)
   필요한 순간에만 동적으로 불러온다. */
async function styleCards(){
  try {
    const [chat, page] = await Promise.all([
      import('../../../home/static/js/chat.js'),
      import('../../../style/static/js/style_page.js'),
    ]);
    const simg = page.SIMG || (s => s.ph || '');
    return (chat.STYLES || []).map(s => ({ id:s.id, name:s.n, img:simg(s) }));
  } catch (_) { return []; }
}

async function paintForm(){
  const card = inviteEl && inviteEl.querySelector('.alphaCard');
  if(!card) return;
  const styles = await styleCards();
  const byId = new Map(styles.map(s => [s.id, s.name]));
  const picked = [];                 /* 고른 순서를 기억한다 — 가입 팝업과 같은 규칙 */
  card.classList.add('wide');        /* 사진 그리드는 4칸이라 창을 넓힌다 */
  card.innerHTML =
    '<span class="alphaBadge">ALPHA TEST</span>' +
    '<h3>두 가지만 알려 주세요</h3>' +
    '<label class="alphaLabel" for="alphaNick">닉네임</label>' +
    '<input id="alphaNick" class="alphaInput" type="text" maxlength="12" autocomplete="off" ' +
      'placeholder="2~12자로 입력해 주세요">' +
    '<label class="alphaLabel">즐겨입는 스타일 <span>최대 ' + STYLE_MAX + '개 · 건너뛰어도 됩니다</span></label>' +
    '<div class="styleSelectGrid">' +
      styles.map(s =>
        '<button type="button" class="styleSelCard" data-style-pick="' + esc(s.id) + '">' +
        '<img src="' + esc(s.img) + '" alt="" draggable="false" loading="lazy">' +
        '<span>' + esc(s.name) + '</span></button>').join('') +
    '</div>' +
    '<p class="alphaErr" id="alphaErr" hidden></p>' +
    '<div class="alphaPick">' +
      '<button type="button" class="alphaPrimary" data-a="make">계정 만들고 시작하기</button>' +
      '<button type="button" class="alphaGhost" data-a="back">뒤로</button>' +
    '</div>';

  const err = card.querySelector('#alphaErr');
  const nick = card.querySelector('#alphaNick');
  setTimeout(() => nick && nick.focus(), 60);
  nick.addEventListener('keydown', e => { if(e.key === 'Enter') card.querySelector('[data-a="make"]').click(); });

  card.onclick = async e => {
    const pick = e.target.closest('[data-style-pick]');
    if(pick){
      const id = pick.dataset.stylePick;
      const at = picked.indexOf(id);
      if(at >= 0){
        picked.splice(at, 1);
        pick.classList.remove('on');
      }else{
        /* 3개를 넘기면 가장 최근에 고른 것을 밀어낸다 — 가입 팝업(styleSelectBind)과 같은 동작 */
        if(picked.length >= STYLE_MAX){
          const out = picked.pop();
          const prev = card.querySelector('[data-style-pick="' + out + '"]');
          if(prev) prev.classList.remove('on');
        }
        picked.push(id);
        pick.classList.add('on');
      }
      hide(err);
      return;
    }
    const b = e.target.closest('[data-a]');
    if(!b) return;
    if(b.dataset.a === 'back'){ card.classList.remove('wide'); return paintChoice(); }
    if(b.dataset.a !== 'make') return;

    const nickname = (nick.value || '').trim();
    if(nickname.length < 2 || nickname.length > 12) return show(err, '닉네임은 2~12자로 입력해 주세요.');

    b.disabled = true; b.textContent = '만드는 중…';
    try {
      const issued = await alphaAccount({
        nickname,
        styles: picked.map(id => byId.get(id)).filter(Boolean),
      });
      setAlphaState(issued.alpha || { alpha:true });
      /* 헤더·프로필을 로그인 상태로 다시 그리게 한다 (account/profile.js 가 듣는다).
         직접 import 하지 않는 이유는 모듈 순환을 피하기 위해서다. */
      document.dispatchEvent(new CustomEvent('feedit:alpha-issued'));
      markAsked(true);
      try { localStorage.removeItem(TOUR_KEY); localStorage.removeItem(BANNER_KEY); } catch(_){}
      closeInvite();
      mountBanner();
      setTimeout(startTour, 450);          /* 창이 닫히자마자 가이드로 이어 준다 */
    } catch (e2) {
      b.disabled = false; b.textContent = '계정 만들고 시작하기';
      show(err, (e2 && e2.message) || '계정을 만들지 못했습니다. 잠시 뒤 다시 시도해 주세요.');
    }
  };
}

function esc(v){
  return String(v == null ? '' : v).replace(/[&<>"']/g, c =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
}
function show(el, msg){ if(el){ el.textContent = msg; el.hidden = false; } }
function hide(el){ if(el) el.hidden = true; }

function seen(key){
  try { return localStorage.getItem(key) === '1'; } catch(_){ return false; }
}
function markSeen(key){
  try { localStorage.setItem(key, '1'); } catch(_){}
}

/* 빠른 계정 안내를 이미 물어봤나.
   persist=true 면 이 브라우저에 계속 남기고(계정을 만들었거나 회원가입을 골랐을 때),
   false 면 이번 방문(탭)에만 남긴다 — '나중에' 를 고른 사람은 다음에 다시 만난다. */
function askedAlready(){
  if(seen(ASKED_KEY)) return true;
  try { return sessionStorage.getItem(ASKED_KEY) === '1'; } catch(_){ return false; }
}
function markAsked(persist){
  if(persist) return markSeen(ASKED_KEY);
  try { sessionStorage.setItem(ASKED_KEY, '1'); } catch(_){}
}

/* ── 2. 상단 배너 ────────────────────────────────────── */
function mountBanner(){
  if(document.getElementById('alphaBar')) return;
  if(seen(BANNER_KEY)) return;
  const bar = document.createElement('div');
  bar.className = 'alphaBar';
  bar.id = 'alphaBar';
  bar.innerHTML =
    '<span class="alphaDot" aria-hidden="true"></span>' +
    '<p class="alphaMsg">현재 <b>알파테스트 계정</b>으로 <b class="alphaLeft">챗봇 20회</b> 이용제한 외 ' +
    '모든 기능이 이용 가능합니다.</p>' +
    '<button type="button" class="alphaGuide" id="alphaGuide">가이드 다시 보기</button>' +
    '<button type="button" class="alphaX" id="alphaX" aria-label="안내 닫기">✕</button>';
  document.body.appendChild(bar);
  document.body.classList.add('hasAlphaBar');
  paintBanner();
  bar.querySelector('#alphaX').addEventListener('click', () => {
    bar.remove();
    document.body.classList.remove('hasAlphaBar');
    markSeen(BANNER_KEY);
  });
  bar.querySelector('#alphaGuide').addEventListener('click', startTour);
}

function paintBanner(){
  const left = document.querySelector('#alphaBar .alphaLeft');
  if(!left) return;
  const limit = state.limit == null ? 20 : state.limit;
  const remaining = state.remaining == null ? limit : state.remaining;
  left.textContent = remaining > 0
    ? `챗봇 ${limit}회(남은 ${remaining}회)`
    : `챗봇 ${limit}회(모두 사용)`;
}

/* ── 3. 가이드 투어 ──────────────────────────────────── */
const STEPS = [
  { sel:'.mNav button[data-v="trend"]',
    title:'트렌드 분석',
    body:'언급량·연관어·긍부정·수명주기까지, 지금 무엇이 오르고 내리는지 봅니다.' },
  { sel:'.mNav button[data-v="salmal"]',
    title:'살!말?',
    body:'살까 말까 고민되는 아이템을 올리면 다른 사람들이 대신 판단해 줍니다.' },
  { sel:'.mNav button[data-v="style"]',
    title:'스타일',
    body:'스타일별로 지금 뜨는 아이템과 브랜드를 모아 봅니다.' },
  { sel:'#chatFab',
    title:'AI 챗봇',
    body:'알파테스트 계정은 챗봇만 20회로 제한됩니다. 나머지 기능은 횟수 제한이 없습니다.' },
];

let tourAt = 0;
let tourNodes = null;
let tourTarget = null;      /* 지금 가리키는 요소 */
let tourRaf = 0;            /* 위치 동기화 루프 */

export function startTour(){
  closeTour();
  tourAt = 0;
  tourNodes = buildTour();
  showStep();
  /* 웹폰트가 늦게 적용되면 글자 폭이 바뀌면서 버튼 위치가 밀린다.
     한 번 더 맞춰 준다 (아래 동기화 루프가 이미 잡지만, 첫 프레임을 아끼려고). */
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(syncRing).catch(()=>{});
}

/* 링과 말풍선을 대상의 '지금' 위치에 붙인다.
   한 번만 재서 고정하면 웹폰트 적용·진입 애니메이션·스크롤 때문에 어긋난다.
   투어가 열려 있는 동안 매 프레임 다시 맞춘다 — 읽기 몇 번이라 부담이 없다. */
function syncRing(){
  if(!tourNodes || !tourTarget || !tourTarget.isConnected) return;
  const r = tourTarget.getBoundingClientRect();
  if(!r.width && !r.height) return;
  const pad = 8;
  const { ring, tip } = tourNodes;
  ring.style.left = (r.left - pad) + 'px';
  ring.style.top = (r.top - pad) + 'px';
  ring.style.width = (r.width + pad * 2) + 'px';
  ring.style.height = (r.height + pad * 2) + 'px';

  const t = tip.getBoundingClientRect();
  if(!t.width) return;
  let left = r.left + r.width / 2 - t.width / 2;
  left = Math.max(16, Math.min(left, window.innerWidth - t.width - 16));
  let top = r.bottom + 14;
  if(top + t.height > window.innerHeight - 16) top = Math.max(16, r.top - t.height - 14);
  tip.style.left = left + 'px';
  tip.style.top = top + 'px';
}

function startSync(){
  stopSync();
  const tick = () => { syncRing(); tourRaf = requestAnimationFrame(tick); };
  tourRaf = requestAnimationFrame(tick);
}
function stopSync(){
  if(tourRaf) cancelAnimationFrame(tourRaf);
  tourRaf = 0;
}

function buildTour(){
  const wrap = document.createElement('div');
  wrap.className = 'alphaTour';
  wrap.id = 'alphaTour';
  wrap.innerHTML =
    '<div class="alphaScrim"></div>' +
    '<div class="alphaRing" aria-hidden="true"></div>' +
    '<div class="alphaTip" role="dialog" aria-live="polite">' +
      '<span class="alphaStep"></span>' +
      '<h4></h4><p></p>' +
      '<div class="alphaActs">' +
        '<button type="button" class="alphaSkip">건너뛰기</button>' +
        '<button type="button" class="alphaNext">다음</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(wrap);
  wrap.querySelector('.alphaSkip').addEventListener('click', finishTour);
  wrap.querySelector('.alphaScrim').addEventListener('click', finishTour);
  wrap.querySelector('.alphaNext').addEventListener('click', () => {
    tourAt += 1;
    if(tourAt >= STEPS.length) finishTour(); else showStep();
  });
  return {
    wrap,
    ring: wrap.querySelector('.alphaRing'),
    tip: wrap.querySelector('.alphaTip'),
  };
}

function showStep(){
  if(!tourNodes) return;
  const step = STEPS[tourAt];
  const target = document.querySelector(step.sel);
  /* 그 화면에 없는 요소는 건너뛴다 — 홈이 아닌 곳에서 눌러도 깨지지 않게 */
  if(!target){
    tourAt += 1;
    if(tourAt >= STEPS.length) return finishTour();
    return showStep();
  }
  tourTarget = target;

  const { tip } = tourNodes;
  tip.querySelector('.alphaStep').textContent = `${tourAt + 1} / ${STEPS.length}`;
  tip.querySelector('h4').textContent = step.title;
  tip.querySelector('p').textContent = step.body;
  tip.querySelector('.alphaNext').textContent =
    tourAt === STEPS.length - 1 ? '시작하기' : '다음';

  /* 글이 바뀌면 말풍선 크기도 바뀐다 — 새 크기로 잰 뒤에 보여 준다 */
  tip.style.visibility = 'hidden';
  syncRing();
  requestAnimationFrame(() => {
    syncRing();
    tip.style.visibility = 'visible';
    startSync();
  });
}

function finishTour(){
  markSeen(TOUR_KEY);
  closeTour();
}

function closeTour(){
  stopSync();
  const old = document.getElementById('alphaTour');
  if(old) old.remove();
  tourNodes = null;
  tourTarget = null;
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
