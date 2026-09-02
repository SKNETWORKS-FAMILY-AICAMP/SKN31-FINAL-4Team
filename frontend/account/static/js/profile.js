import { $, $$, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';
import { BADGES, bgDetail, bgRender } from './badges.js';
import { IMG, STYLES } from '../../../home/static/js/chat.js';
import { SIMG } from '../../../style/static/js/style_page.js';
import { SV, svWon } from '../../../trend/static/js/discount_resale.js';
import { goView } from '../../../app_shell/static/js/router.js';
import { rkLevelOf, rkPaintAll, rkPaintAv, xpPaint } from './rank.js';
import { trRender } from '../../../trend/static/js/dispatch.js';

/* 내 계정 — 운영자라 최고 등급 고정 */
export const ME={name:'혁진',mail:'hyeokjin@feedit.co.kr',initial:'혁',xp:9400,   /* 누적 경험치. rank 는 여기서 계산된다 */
          height:'',weight:'',   /* 체형 — 가입·정보수정에서 받는다 */
          plan:'ADMIN · 서울',saved:128,votes:42,hit:94,
          bio:'',            /* 비어 있으면 예시 문구가 흐리게 대신 선다 */
          birth:'',          /* 가입·정보수정에서 채운다 */
          ava:0,             /* 프로필 아이콘 색 (AVA 인덱스) */
          styles:new Set(['ballet','block','ameka'])};  /* 즐겨입는 스타일 (가입 시 선택) */
/* rank 는 저장하지 않는다 — 경험치에서 항상 다시 센다.
   이렇게 두면 XP 만 올려도 링·문구·바가 한꺼번에 따라온다. */
Object.defineProperty(ME,'rank',{get(){ return rkLevelOf(ME.xp) }, enumerable:true});

/* 프로필 아이콘 색 — 팔레트 밖으로 나가지 않게 코랄·먹·모래 계열만 썼다 */
const AVA=[
  ['#ff6b4a','#ffb199'], ['#1c1a17','#4a453d'], ['#c8a27a','#e6d3bd'],
  ['#3d5a6c','#7d9db0'], ['#6b5b95','#a89bc4'], ['#4a6b52','#8fae95']
];
/* 아바타가 쓰이는 곳(마이페이지 원형 + 헤더 작은 원)을 한 번에 칠한다 */
function avaPaint(){
  const g=AVA[ME.ava]||AVA[0];
  const bg='linear-gradient(135deg,'+g[0]+','+g[1]+')';
  const c=$('#avatarInitial'); if(c){ c.style.background=bg; rkPaintAv(c, ME.rank) }
  $$('.mAuth .meAv').forEach(e=>{
    e.style.background=bg; e.style.color='#fff'; rkPaintAv(e, ME.rank);
  });
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
export var AUTH = { in: false };

/* 헤더 오른쪽 — 로그인 전에는 [로그인], 후에는 [혁진] 버튼이 마이페이지로 */
function authPaint(){
  const b = $('#mAuthBtn');
  if(!b) return;
  if(AUTH.in){
    b.className = 'pill me';
    b.removeAttribute('data-v');       /* 전역 [data-v] 위임 대신 메뉴를 연다 */
    b.innerHTML = '<span class="meAv">' + ME.initial + '</span>' + ME.name +
      '<svg class="meCaret" viewBox="0 0 12 12" fill="none" stroke="currentColor" ' +
      'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M2.5 4.5L6 8l3.5-3.5"/></svg>';
    avaPaint();
  }else{
    b.className = 'pill';
    b.dataset.v = 'login';
    b.textContent = '로그인';
    acctMenu(false);
  }
}
/* 로그인 뒤 이름 버튼을 누르면 뜨는 작은 메뉴 */
function acctMenu(on){
  const m = $('#acctMenu');
  if(m){
    m.classList.toggle('on', on === undefined ? !m.classList.contains('on') : on);
    const w = m.closest('.mAuthWrap');
    if(w) w.classList.toggle('open', m.classList.contains('on'));
  }
}
function authLogin(){
  AUTH.in = true;
  authPaint();
  goView('mypage');
}
function authLogout(){
  AUTH.in = false;
  authPaint();
  goView('home');
}

/* 스타일 칩 — 가입·마이페이지가 같은 14종을 쓴다 */
function acctChips(host, sel){
  if(!host) return;
  host.innerHTML = STYLES.map(s =>
    '<button type="button" class="chip' + (sel.has(s.id) ? ' on' : '') +
    '" data-style-pick="' + s.id + '">' + s.n + '</button>').join('');
  host.onclick = e => {
    const b = e.target.closest('[data-style-pick]');
    if(!b) return;
    const id = b.dataset.stylePick;
    sel.has(id) ? sel.delete(id) : sel.add(id);
    b.classList.toggle('on', sel.has(id));
    if(host.id === 'styleWrap') myRender();   /* 마이페이지는 고르는 즉시 추천이 바뀐다 */
  };
}

/* 마이페이지 카드 한 장 — 스타일 사진과 대표 아이템을 쓴다 */
/* 원본 마이페이지 카드 구조 그대로 — 사진 / 브랜드 / 이름 / 가격 */
function acctCard(o){
  return '<div class="recCard"' + (o.style ? ' data-style="' + o.style + '"' : '') + '>' +
    '<div class="recFig"><img src="' + o.img + '" alt="" loading="lazy">' +
      (o.tag ? '<span class="fitTag">' + o.tag + '</span>' : '') + '</div>' +
    '<div class="recBody"><div class="br">' + o.br + '</div>' +
      '<div class="nm">' + o.nm + '</div>' +
      '<div class="pr">' + o.pr + '</div></div></div>';
}

export function myRender(){
  /* 프로필 */
  const av = $('#avatarInitial'), nm = $('#profileName'), em = $('#profileEmail');
  if(av) av.textContent = ME.initial;
  if(nm) nm.textContent = ME.name;
  if(em) em.textContent = ME.mail;
  xpPaint();
  avaPaint();

  /* 저장 · 투표 수는 실제 데이터에서 센다 */
  const savedN = $('#statSavedN'), votedN = $('#statVotedN');
  if(savedN) savedN.textContent = (typeof SV !== 'undefined' ? SV.length : ME.saved);
  const voted = (typeof VOTES !== 'undefined')
    ? VOTES.filter(v => v.voted !== null && v.voted !== undefined) : [];
  if(votedN) votedN.textContent = voted.length || ME.votes;
  /* 뱃지 — 컬렉션 뱃지 개수. 등급은 뱃지가 아니라 아바타 링으로 표현한다.
     팀원 데이터가 붙으면 BADGES 만 채우면 숫자도 같이 맞는다. */
  const badgeN = $('#statBadgeN');
  if(badgeN) badgeN.textContent = BADGES.filter(b => b.earned).length;

  /* 추천 — 고른 취향에 맞춰 바뀐다. 아무것도 안 골랐으면 지금 뜨는 코어 순 */
  const picked = STYLES.filter(s => ME.styles.has(s.id));
  const rise = ['확산','재상승','재점화','정점 통과'];
  const rec = (picked.length ? picked : STYLES.filter(s => rise.includes(s.pk))).slice(0, 6);
  const g1 = $('#recGrid');
  if(g1) g1.innerHTML = rec.slice(0, 4).map((s, i) => acctCard({
    style: s.id, img: SIMG(s), tag: '매칭 ' + (96 - i * 3) + '%',
    br: s.en, nm: s.n + ' 룩', pr: s.kw.slice(0, 2).join(' · ')
  })).join('');
  const sub = $('#recSub');
  if(sub) sub.textContent = picked.length ? '내 취향 ' + picked.length + '개 기준' : '지금 뜨는 코어 기준';

  /* 무난템 — 흔들림이 적은 원형에서 */
  const basic = STYLES.filter(s => s.g === '원형').slice(0, 4);
  const g2 = $('#basicGrid');
  if(g2) g2.innerHTML = basic.map(s => acctCard({
    style: s.id, img: SIMG(s), tag: '국밥템',
    br: s.en, nm: s.n + ' 기본', pr: s.kw[0]
  })).join('');

  if(HAS_A){
    aAnimate($$('#v-mypage .panel'), {opacity:[0,1],translateY:[14,0],
      duration:640,delay:aStagger(60),ease:'out(3)',
      onComplete:()=>$$('#v-mypage .panel').forEach(e=>{e.style.transform='';e.style.opacity=''})});
  }
}

/* 모달 */
function acctModal(id, on){
  const m = $('#' + id);
  if(m) m.classList.toggle('on', on);
}

export function acctBoot(){
  /* ── 로그인 ── */
  const lf = $('#loginForm');
  if(lf) lf.addEventListener('submit', e => {
    e.preventDefault();
    const id = $('#loginId').value.trim(), pw = $('#loginPw').value.trim();
    const err = $('#loginErr');
    if(!id || !pw){ err.style.display = 'block'; return; }
    err.style.display = 'none';
    ME.name = id.slice(0, 12) || ME.name;
    ME.initial = ME.name[0];
    authLogin();
  });
  const gl = $('#googleLoginBtn');
  if(gl) gl.addEventListener('click', authLogin);

  /* ── 회원가입 ── */
  acctChips($('#styleChips'), ME.styles);
  const sf = $('#signupForm');
  if(sf) sf.addEventListener('submit', e => {
    e.preventDefault();
    const err = $('#signupErr');
    const id = $('#suId').value.trim(), nick = $('#suNickname').value.trim();
    const pw = $('#suPw').value, pw2 = $('#suPw2').value;
    let msg = '';
    if(!/^[A-Za-z0-9]{4,16}$/.test(id)) msg = '아이디는 영문·숫자 4~16자로 입력해 주세요.';
    else if(nick.length < 2 || nick.length > 12) msg = '닉네임은 2~12자로 입력해 주세요.';
    else if(pw.length < 8) msg = '비밀번호는 8자 이상이어야 합니다.';
    else if(pw !== pw2) msg = '비밀번호가 서로 다릅니다.';
    else if(!ME.styles.size) msg = '즐겨입는 스타일을 하나 이상 골라 주세요.';
    else {
      const b = bodyCheck($('#suHeight').value, $('#suWeight').value);
      if(b) msg = b;
    }
    if(msg){ err.textContent = msg; err.style.display = 'block'; return; }
    err.style.display = 'none';
    ME.name = nick; ME.initial = nick[0];
    ME.mail = id + '@feedit.co.kr';
    ME.birth = $('#suBirth').value || ME.birth;
    ME.height = $('#suHeight').value || '';
    ME.weight = $('#suWeight').value || '';
    authLogin();
  });
  const gs = $('#googleSignupBtn');
  if(gs) gs.addEventListener('click', authLogin);
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
  if(aw) aw.addEventListener('click', e => {
    const b = e.target.closest('[data-ava]');
    if(!b) return;
    ME.ava = +b.dataset.ava;
    $$('.avaSw', aw).forEach(x => x.classList.toggle('on', x === b));
    avaPaint(); authPaint();
    setTimeout(() => acctModal('avatarModal', false), 240);
  });
  const ep = $('#editProfileBtn');
  if(ep) ep.addEventListener('click', () => {
    $('#editNickname').value = ME.name;
    $('#editBirth').value = ME.birth || '';
    $('#editHeight').value = ME.height || '';
    $('#editWeight').value = ME.weight || '';
    $('#editModalErr').style.display = 'none';
    acctModal('editModal', true);
  });
  const ef = $('#editProfileForm');
  if(ef) ef.addEventListener('submit', e => {
    e.preventDefault();
    const nick = $('#editNickname').value.trim();
    const pw = $('#editPw').value, pw2 = $('#editPw2').value;
    const err = $('#editModalErr');
    let msg = '';
    if(nick.length < 2 || nick.length > 12) msg = '닉네임은 2~12자로 입력해 주세요.';
    else if(pw && pw.length < 8) msg = '새 비밀번호는 8자 이상이어야 합니다.';
    else if(pw !== pw2) msg = '새 비밀번호가 서로 다릅니다.';
    else msg = bodyCheck($('#editHeight').value, $('#editWeight').value) || '';
    if(msg){ err.textContent = msg; err.style.display = 'block'; return; }
    ME.name = nick; ME.initial = nick[0];
    ME.birth = $('#editBirth').value || ME.birth;
    ME.height = $('#editHeight').value || '';
    ME.weight = $('#editWeight').value || '';
    acctModal('editModal', false);
    myRender(); authPaint();
    if(typeof trRender === 'function' && document.body.dataset.view === 'trend') trRender('myfeed');
  });
  [$('#editModalClose'), $('#editModalCancel')].forEach(b =>
    b && b.addEventListener('click', () => acctModal('editModal', false)));

  /* 저장 · 투표 목록 모달 — 실제 찜 목록과 투표 이력을 그대로 보여 준다 */
  const sb = $('#statSavedBtn');
  if(sb) sb.addEventListener('click', () => {
    const g = $('#savedGrid');
    if(g) g.innerHTML = (typeof SV !== 'undefined' ? SV : []).map(s => acctCard({
      img: IMG(s.img), tag: s.d + '일 전', br: s.b, nm: s.n, pr: svWon(s.p)
    })).join('') || '<p class="fieldMsg">저장한 아이템이 없습니다.</p>';
    acctModal('savedModal', true);
  });
  const vb = $('#statVotedBtn');
  if(vb) vb.addEventListener('click', () => {
    const g = $('#votedGrid');
    const voted = (typeof VOTES !== 'undefined')
      ? VOTES.filter(v => v.voted !== null && v.voted !== undefined) : [];
    if(g) g.innerHTML = voted.map(v => acctCard({
      img: v.imgURL, tag: v.voted === 0 ? '살! 선택' : '말? 선택',
      br: v.b, nm: v.t, pr: fmtWon(v.p)
    })).join('') || '<p class="fieldMsg">아직 투표한 카드가 없습니다. 살!말? 에서 골라 보세요.</p>';
    acctModal('votedModal', true);
  });
  /* 뱃지 — 컬렉션 뱃지 전용 자리다.
     등급은 뱃지가 아니라 아바타 링으로 표현하기로 했으니 여기 섞지 않는다.
     팀원 컬렉션 뱃지가 도착하면 BADGES 배열만 채우면 그대로 그려진다. */
  const bb = $('#statBadgeBtn');
  if(bb) bb.addEventListener('click', () => { bgRender(); acctModal('badgeModal', true) });
  /* 타일을 고르면 위 상세 패널이 바뀐다 */
  const bg = $('#badgeGrid');
  if(bg) bg.addEventListener('click', e => {
    const t = e.target.closest('.bgTile'); if(!t) return;
    $$('.bgTile.active', bg).forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const b = BADGES.find(x => x.id === t.dataset.badge);
    if(b) bgDetail(b);
  });

  /* 회원 탈퇴 — 목업이라 진짜로 지우지는 않는다. 확인만 받고 로그아웃한다 */
  const lv = $('#leaveBtn');
  if(lv) lv.addEventListener('click', () => acctModal('leaveModal', true));
  const lvGo = $('#leaveConfirm');
  if(lvGo) lvGo.addEventListener('click', () => {
    acctModal('leaveModal', false);
    authLogout();
  });
  $$('[data-close-modal]').forEach(b =>
    b.addEventListener('click', () => $$('.acctModal').forEach(m => m.classList.remove('on'))));
  $$('.acctModal').forEach(m => m.addEventListener('click', e => {
    if(e.target === m) m.classList.remove('on');
  }));
  addEventListener('keydown', e => {
    if(e.key === 'Escape') $$('.acctModal').forEach(m => m.classList.remove('on'));
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
  const ml = $('#menuLogout');
  if(ml) ml.addEventListener('click', () => { acctMenu(false); authLogout() });
  document.addEventListener('click', e => {
    if(!e.target.closest('.mAuthWrap')) acctMenu(false);
  });

  authPaint();
  rkPaintAll();      /* 화면에 이미 떠 있는 아바타들도 한 번 맞춰 둔다 */
}
