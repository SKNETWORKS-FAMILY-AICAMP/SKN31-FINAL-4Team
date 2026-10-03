/* 알림 — 헤더 종 아이콘 · 알림 패널 · 알림 설정 · 용어 등재 요청.
   원본은 서버다 (backend/apps/api/notification_views.py).
   화면은 받아서 그리기만 한다 — 여기서 알림을 만들지 않는다.

   종류 (2026-09-19)
     PRICE_DROP     찜한 상품 변동(급락 · 6개월 최저가 · 급등 · 품절) — 하루 한 번 묶어서
     VOTE_RESULT    살!말? 투표가 10표를 넘었을 때
     WEEKLY_REPORT  주간 트렌드 리포트 — 주 1회
     BADGE          뱃지 달성
     TERM_ADDED     요청한 용어가 사전에 올라갔을 때
     ADMIN_NOTICE   운영자가 관리자 화면에서 보낸 공지 (2026-10-02)
     PROFILE_GENDER 성별이 비어 있는 회원에게 한 번 — 누르면 바로 고른다 (2026-10-02)
     PLAN_REVIEW    요금제 신청 승인 · 반려 · 운영자의 해지, (운영) 신청 대기 N건 (2026-10-03)

   내 취향 스타일의 단계 변화 · FEEDiT Pick 갱신은 아직 없다.
   판정 규칙과 Pick 의 정의가 확정되면 그때 더한다 — 지금 칸만 만들어 두면
   켜 놓고 기다려도 아무것도 오지 않는다. */
import { $, $$ } from '../../../core/static/js/dom.js';
import { AUTH, acctToast, applyAccountUser } from './profile.js';
import { goView } from '../../../app_shell/static/js/router.js';
import { planRefresh } from './plan.js';
import {
  deleteAllNotifications, deleteNotification, notifications, notificationSettings,
  readAllNotifications, readNotification, requestTerm, saveGender, saveNotificationSettings, session,
} from './account_api.js';

/* 설정 모달에 그릴 종류. 서버(notifications.SETTING_FIELD)와 같은 값이어야 한다. */
const KINDS = [
  /* ★ 2026-09-27 — 가격 하락만 알리던 칸이 급락 · 6개월 최저가 · 급등 · 품절까지 맡는다 (FAVORITE-002). 종류 값은 그대로 */
  { id:'PRICE_DROP',    n:'찜한 상품 변동',      d:'하루 한 번, 크게 내리거나(6개월 최저가 포함) 오르거나 품절된 찜 상품을 묶어서 알려 드려요.' },
  { id:'VOTE_RESULT',   n:'살!말? 투표 결과',    d:'내가 올린 상품에 표가 10개 모이거나 투표가 마감되면 알려 드려요.' },
  { id:'WEEKLY_REPORT', n:'주간 트렌드 리포트',  d:'매주 월요일, 지난 한 주 리포트가 도착해요.' },
  { id:'BADGE',         n:'뱃지 달성',           d:'새 뱃지를 딴 날 알려 드려요.' },
  { id:'TERM_ADDED',    n:'용어 사전 등재',      d:'요청한 용어가 사전에 올라가면 알려 드려요.' },
  { id:'JOB_REVIEW',    n:'직업 인증 결과',      d:'신청한 직업 인증이 승인되거나 반려되면 알려 드려요.' },
  { id:'VOTE_COMMENT',  n:'살!말? 새 댓글',      d:'내가 올린 상품에 누군가 댓글을 달면 알려 드려요.' },
];
const KIND_NAME = Object.fromEntries(KINDS.map(k => [k.id, k.n]));
/* 운영 계정만 받는 알림 — 수집 실패 · 장기 미갱신 (2026-09-27). 끌 수 없어 설정 모달(KINDS)에는 없다 */
KIND_NAME.OPS_ALERT = '운영 알림';
/* 운영 공지 · 성별 요청 (2026-10-02) — 끌 수 있는 칸이 따로 없다('전체 알림' 만 따른다) */
KIND_NAME.ADMIN_NOTICE = '공지';
KIND_NAME.PROFILE_GENDER = '프로필';
/* 요금제 신청 결과 · (운영) 신청 대기 (2026-10-03) — 끌 수 없다. 쓰는 요금제가 바뀌었다는 소식이다 */
KIND_NAME.PLAN_REVIEW = '요금제';

/* 종류별 아이콘 (2026-09-19 디자인 개편) — 라벨 글자 대신 작은 원 안의 선 아이콘으로 구분한다 */
const SVG = d => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
const KIND_ICON = {
  /* ★ 2026-09-19 — 투표는 투표함, 가격은 내려가는 꺾은선, 주간 리포트는 막대그래프 */
  PRICE_DROP:    SVG('<path d="M3.5 7l6 6 3.5-3.5 7.5 7.5"/><path d="M20.5 12v5h-5"/>'),
  VOTE_RESULT:   SVG('<path d="M3.5 13.5h17v6.5h-17z"/><path d="M7.5 13.5V4.5h9v9"/><path d="M9.8 9l1.7 1.7L14.4 7.6"/>'),
  WEEKLY_REPORT: SVG('<path d="M5 20V11M10 20V5M15 20v-6M20 20V9"/>'),
  BADGE:         SVG('<circle cx="12" cy="9" r="5"/><path d="M9 13.5L8 21l4-2 4 2-1-7.5"/>'),
  TERM_ADDED:    SVG('<path d="M5 4h11a3 3 0 013 3v13H8a3 3 0 01-3-3z"/><path d="M5 17a3 3 0 013-3h11"/>'),
  JOB_REVIEW:    SVG('<path d="M12 3l7 3v5c0 4.4-3 8-7 10-4-2-7-5.6-7-10V6z"/><path d="M9 12l2 2 4-4"/>'),
  VOTE_COMMENT:  SVG('<path d="M4 5.5h16v10H9.5L5 19.5v-4H4z"/><path d="M8 9.5h8M8 12.3h5"/>'),
  /* 운영 알림 — 경고 삼각형 */
  OPS_ALERT:     SVG('<path d="M12 4l9 16H3z"/><path d="M12 10v4.5M12 17.2v.3"/>'),
  /* 운영 공지 — 확성기 */
  ADMIN_NOTICE:  SVG('<path d="M4 10v4h3l6 4V6L7 10z"/><path d="M16.5 9a4 4 0 010 6M19 6.5a7.5 7.5 0 010 11"/>'),
  /* 성별 요청 — 사람 윤곽 */
  PROFILE_GENDER: SVG('<circle cx="12" cy="8" r="3.6"/><path d="M5 20c.8-3.6 3.6-5.6 7-5.6s6.2 2 7 5.6"/>'),
  /* 요금제 — 카드 */
  PLAN_REVIEW:   SVG('<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h4"/>'),
};
/* 운영 계정이 받는 '직업 인증 심사 대기' — 서류 판 */
const CLIPBOARD = SVG('<rect x="5" y="4.5" width="14" height="16.5" rx="2"/><path d="M9 4.5V3h6v1.5"/><path d="M8.5 10h7M8.5 13.5h7M8.5 17h4"/>');
const adminPending = it => (it.kind === 'JOB_REVIEW' || it.kind === 'PLAN_REVIEW') && it.payload && it.payload.admin_pending;
const kindName = it => adminPending(it) ? (it.kind === 'PLAN_REVIEW' ? '요금제 신청 심사' : '직업 인증 심사') : (KIND_NAME[it.kind] || '알림');
const iconOf = it => adminPending(it) ? CLIPBOARD : (KIND_ICON[it.kind] || BELL);
const BELL = SVG('<path d="M6 16V11a6 6 0 0112 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 004 0"/>');

const POLL_MS = 30000;          /* 30초마다 다시 센다 — 새 알림은 오른쪽 위 토스트로도 띄운다 */
const LIST_MAX = 6;             /* 한 화면에 보이는 알림 수. 넘으면 스크롤 */
const NT = { items:[], unread:0, setting:null, timer:0, loading:false, open:false };

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));

/* ★ 2026-09-20 — 알림 본문을 줄 단위로 정돈한다.
   서버는 이제 \n 으로 줄을 나눠 보내지만, 예전에 쌓인 알림은 한 줄로 이어 붙어 있다.
   그래서 문장 끝(. ! ?)과 ' — ' 에서도 줄을 나눈다. 줄마다 span 으로 감싸 한 줄씩 선다. */
function bodyHTML(body){
  const lines = String(body || '').replace(/\r/g, '')
    .replace(/\s+—\s+/g, '\n')
    .replace(/([.!?])\s+(?=\S)/g, '$1\n')
    .split('\n').map(x => x.trim()).filter(Boolean);
  return lines.map(l => '<span class="nbLine">' + esc(l) + '</span>').join('');
}

/* "방금 · 12분 전 · 3시간 전 · 2일 전 · 2026.09.01" */
function ago(iso){
  const t = Date.parse(iso);
  if(!Number.isFinite(t)) return '';
  const m = Math.floor((Date.now() - t) / 60000);
  if(m < 1) return '방금';
  if(m < 60) return m + '분 전';
  if(m < 60 * 24) return Math.floor(m / 60) + '시간 전';
  if(m < 60 * 24 * 7) return Math.floor(m / 1440) + '일 전';
  const d = new Date(t);
  return d.getFullYear() + '.' + String(d.getMonth() + 1).padStart(2, '0') + '.' +
    String(d.getDate()).padStart(2, '0');
}

/* ── 그리기 ───────────────────────────────────────────── */
function paintDot(){
  const dot = $('#notiDot'), btn = $('#notiBtn');
  if(dot) dot.hidden = !NT.unread;
  if(btn) btn.setAttribute('aria-label', NT.unread ? `알림 ${NT.unread}건 안 읽음` : '알림');
  paintCount();
}

/* 휴지통 — 이모지가 아니라 아이콘 */
const TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M4 7h16M10 7V5h4v2M6 7l1 12h10l1-12"/><path d="M10.5 10.5v5M13.5 10.5v5"/></svg>';

function paintList(note){
  const box = $('#notiList');
  if(!box) return;
  paintCount();
  if(note){ box.innerHTML = '<div class="notiEmpty"><i>' + BELL + '</i><p>' + esc(note) + '</p></div>'; fitList(); return }
  if(!NT.items.length){
    box.innerHTML = '<div class="notiEmpty"><i>' + BELL + '</i><b>새 알림이 없어요</b></div>';
    fitList();
    return;
  }
  box.innerHTML = NT.items.map(it =>
    '<div class="notiItem' + (it.read ? '' : ' unread') + '" data-id="' + it.id + '" data-kind="' + esc(it.kind) + '">' +
      '<button type="button" class="notiOpen" data-link="' + esc(it.link || '') + '">' +
        '<span class="notiIc">' + iconOf(it) + '</span>' +
        '<span class="notiTx">' +
          '<span class="notiMeta"><span class="notiKind">' + esc(kindName(it)) + '</span>' +
            '<span class="notiAgo">' + esc(ago(it.created_at)) + '</span></span>' +
          '<span class="notiTitle">' + esc(it.title) + '</span>' +
          (it.body ? '<span class="notiBody">' + bodyHTML(it.body) + '</span>' : '') +
        '</span>' +
      '</button>' +
      '<button type="button" class="notiDel" aria-label="이 알림 삭제">' + TRASH + '</button>' +
    '</div>').join('');
  fitList();
}

/* 머리의 '안 읽음 N' — 0 이면 숨긴다 */
function paintCount(){
  const c = $('#notiCount');
  if(!c) return;
  c.textContent = NT.unread > 99 ? '99+' : String(NT.unread || '');
  c.hidden = !NT.unread;
}

/* 한 화면에 LIST_MAX 개까지만 보이게 높이를 맞춘다.
   알림마다 본문이 있고 없고라 높이가 달라서, 글자 수로 어림하지 않고
   실제로 그려진 여섯 번째 알림의 위치를 잰다. */
function fitList(){
  const box = $('#notiList');
  if(!box) return;
  const rows = box.querySelectorAll('.notiItem');
  box.classList.toggle('scrolls', rows.length > LIST_MAX);
  box.style.maxHeight = '';
  if(rows.length > LIST_MAX){
    const h = rows[LIST_MAX].offsetTop - rows[0].offsetTop;
    /* 아직 화면에 없어 재지 못하면(0) CSS 의 기본 최대 높이가 대신 막는다 */
    if(h > 0) box.style.maxHeight = h + 'px';
  }
}

/* ── 서버에서 받아 오기 ───────────────────────────────── */
export function notiRefresh(){
  if(!AUTH.in || NT.loading) return Promise.resolve();
  NT.loading = true;
  return notifications().then(data => {
    NT.items = Array.isArray(data.items) ? data.items : [];
    NT.unread = Number(data.unread || 0);
    if(data.setting) NT.setting = data.setting;
    paintDot();
    if(NT.open) paintList();
    toastNew();
  }).catch(e => {
    if(NT.open) paintList('알림을 받아오지 못했습니다 — ' + (e.message || e));
  }).finally(() => { NT.loading = false });
}

function start(){
  const wrap = $('#notiWrap');
  if(wrap) wrap.hidden = false;
  notiRefresh();
  clearInterval(NT.timer);
  NT.timer = setInterval(() => {
    if(document.hidden || !AUTH.in) return;   /* 보이지 않는 탭에서는 세지 않는다 */
    notiRefresh();
  }, POLL_MS);
}

function stop(){
  clearInterval(NT.timer); NT.timer = 0;
  toastReset();
  NT.items = []; NT.unread = 0; NT.setting = null;
  panel(false);
  const wrap = $('#notiWrap');
  if(wrap) wrap.hidden = true;
  paintDot();
}

/* ── 토스트 — 맥 알림처럼 오른쪽 위에 한 장만 떴다 사라진다 (2026-09-19) ─────────
   · 새 알림이 1개면 그 알림을, 여러 개면 **가장 최근 것 + '외 N개 새 알림'** 을 한 장으로.
     (여러 장을 쌓지 않는다 — 화면이 알림으로 덮였다)
   · 로그인 직후: 안 읽은 알림 기준. 로그인해 있는 동안: 30초마다 받아 올 때 처음 보는 안 읽은 알림.
   · 같은 알림은 두 번 띄우지 않는다. 가려진 탭에서는 모았다가 돌아오면 띄운다.
     ★ 2026-09-23 — 예전에는 이 기록을 sessionStorage 에 뒀다. 그래서 탭을 닫거나
       로그아웃했다가 다시 들어오면 **이미 떴던 알림이 또 떴다** — 읽지 않았다는 이유로.
       한 번 띄운 알림을 다시 들이밀 이유는 없다(안 읽은 것은 종 아이콘과 목록에 그대로 남는다).
       이제 localStorage 에 두고, 로그아웃해도 지우지 않는다.
       알림 id 는 행마다 하나뿐이라 계정이 바뀌어도 서로 겹치지 않는다.
   · 누르면 그 알림이 가리키는 곳으로 간다(openTarget). '외 N개'를 누르면 알림 목록을 연다. */
const TOAST_MS = 4000, TOAST_KEY = 'feedit.noti.toasted.v2';
/* ★ 토스트는 본문(홈)에 들어온 뒤부터 — 로딩 · 설명 페이지 위에는 띄우지 않는다 */
const inMain = () => document.body.classList.contains('mainmode');
/* 인트로를 지나 본문으로 들어오면 모아 둔 토스트를 그때 띄운다 */
(function waitForMain(){
  if(inMain())return;
  const ob = new MutationObserver(() => {
    if(!inMain())return;
    ob.disconnect();
    if(TOAST_WAIT && !document.hidden && !chatOpen() && AUTH.in){
      const w = TOAST_WAIT; TOAST_WAIT = null;
      setTimeout(() => toastShow(w.latest, w.count), 600);
    }
  });
  ob.observe(document.body, { attributes:true, attributeFilter:['class'] });
})();
let TOAST_PRIMED = false, TOAST_WAIT = null;
/* 챗봇 팝업이 떠 있으면 토스트가 그 위에 겹친다 — 닫힐 때까지 모아 둔다 */
function chatOpen(){ const ov = $('#cpOverlay'); return !!(ov && ov.classList.contains('on')) }
window.addEventListener('feedit:chatclose', () => {
  if(!TOAST_WAIT || document.hidden || !inMain() || !AUTH.in) return;
  const w = TOAST_WAIT; TOAST_WAIT = null;
  setTimeout(() => toastShow(w.latest, w.count), 300);
});
const toastSeen = new Set();
function toastLoad(){ try{ JSON.parse(localStorage.getItem(TOAST_KEY) || '[]').forEach(id => toastSeen.add(id)) }catch(e){} }
function toastSave(){ try{ localStorage.setItem(TOAST_KEY, JSON.stringify([...toastSeen].slice(-200))) }catch(e){} }
function toastReset(){
  /* 화면에 떠 있는 것만 걷고, '이미 띄웠다'는 기록은 남긴다 —
     지우면 다시 로그인할 때 같은 알림이 처음부터 다시 뜬다. */
  TOAST_PRIMED = false; TOAST_WAIT = null; toastSeen.clear();
  const box = $('#notiToasts'); if(box) box.innerHTML = '';
}
function toastBox(){
  let box = $('#notiToasts');
  if(!box){
    document.body.insertAdjacentHTML('beforeend', '<div class="notiToasts" id="notiToasts" aria-live="polite"></div>');
    box = $('#notiToasts');
  }
  return box;
}
function toastNew(){
  if(!TOAST_PRIMED){ toastLoad(); TOAST_PRIMED = true; }
  const fresh = NT.items.filter(it => !it.read && !toastSeen.has(it.id));
  NT.items.forEach(it => toastSeen.add(it.id));
  toastSave();
  /* 요금제 결과가 새로 왔으면 지금 요금제를 다시 받아 둔다 — 승인되자마자 잠금이 풀리게 (2026-10-03) */
  if(fresh.some(it => it.kind === 'PLAN_REVIEW' && !(it.payload && it.payload.admin_pending))) planRefresh();
  if(!fresh.length || NT.open) return;
  /* 가려진 탭이거나 아직 인트로(로딩 · 설명 페이지)면 모아 둔다 —
     본문(홈)에 들어온 뒤 한 장으로 합쳐 띄운다 */
  const pack = { latest: fresh[0], count: fresh.length + (TOAST_WAIT ? TOAST_WAIT.count : 0) };
  if(document.hidden || !inMain() || chatOpen()){ TOAST_WAIT = pack; return }
  TOAST_WAIT = null;
  toastShow(pack.latest, pack.count);
}
/* 탭으로 돌아오면: 모아 둔 토스트를 띄우고, 그동안 못 받은 알림도 바로 받아 온다 */
document.addEventListener('visibilitychange', () => {
  if(document.hidden || !AUTH.in) return;
  if(TOAST_WAIT && !chatOpen()){ const w = TOAST_WAIT; TOAST_WAIT = null; toastShow(w.latest, w.count) }
  notiRefresh();
});
const XMARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17"/></svg>';
function toastShow(it, count){
  if(!it) return;
  const box = toastBox();
  box.querySelectorAll('.notiToast').forEach(old => { old.classList.remove('in'); old.classList.add('out'); setTimeout(() => old.remove(), 300) });
  const more = Math.max(0, (count || 1) - 1);
  const el = document.createElement('div');
  el.className = 'notiToast';
  el.setAttribute('role', 'status');
  el.innerHTML =
    '<span class="ntIc">' + iconOf(it) + '</span>' +
    '<span class="ntTx"><span class="ntMeta"><b>FEEDiT</b><span>' + esc(kindName(it)) + '</span>' +
      '<span class="ntAgo">' + esc(ago(it.created_at)) + '</span></span>' +
      '<span class="ntTitle">' + esc(it.title) + '</span>' +
      (it.body ? '<span class="ntBody">' + bodyHTML(it.body) + '</span>' : '') +
      (more ? '<span class="ntMore" data-more>외 ' + more + '개의 새 알림 · 모두 보기</span>' : '') +
    '</span>' +
    '<button type="button" class="ntX" aria-label="닫기">' + XMARK + '</button>';
  box.prepend(el);
  void el.offsetWidth;          /* rAF 대신 — 가려진 탭에서도 시작 상태가 확정된다 */
  el.classList.add('in');
  let timer = setTimeout(close, TOAST_MS + (more ? 2000 : 0));
  function close(){
    clearTimeout(timer);
    el.classList.remove('in'); el.classList.add('out');
    setTimeout(() => el.remove(), 320);
  }
  el.addEventListener('mouseenter', () => clearTimeout(timer));
  el.addEventListener('mouseleave', () => { timer = setTimeout(close, 2500) });
  el.addEventListener('click', e => {
    if(e.target.closest('.ntX')){ close(); return }
    close();
    if(e.target.closest('[data-more]')){ panel(true); return }
    markRead(it.id);
    openTarget(it);
  });
}

/* ── 알림을 누르면 어디로 가나 (2026-09-19) ─────────────────
   VOTE_COMMENT · VOTE_RESULT → 그 살말 카드 상세(댓글이면 그 댓글을 잠깐 강조)
   VOTE_RESULT(마감)          → 살말로 가지 않고 피드백 창만
   JOB_REVIEW(운영 · 대기 N건) → 직업 인증 심사 창
   BADGE                      → 그 뱃지 설명 창 (어떻게 따는지 · 진행도)
   JOB_REVIEW                 → 마이페이지
   PRICE_DROP                 → 트렌드 분석 › 찜한 키워드
   WEEKLY_REPORT              → 트렌드 분석 › 금주의 리포트
   TERM_ADDED                 → 트렌드 분석 › 언급량·온도에서 그 용어를 바로 검색
   갈 곳이 없으면 아무것도 하지 않는다. */
function markRead(id){
  const row = NT.items.find(x => x.id === id);
  if(row && !row.read){
    row.read = true; NT.unread = Math.max(0, NT.unread - 1);
    paintDot(); if(NT.open) paintList();
    readNotification(id);
  }
}
const waitFor = (fn, ms = 4000) => new Promise(ok => {
  const t0 = Date.now();
  (function tick(){ const v = fn(); if(v || Date.now() - t0 > ms) ok(v); else setTimeout(tick, 80) })();
});
function goTrendTab(tab){
  if(document.body.dataset.view === 'trend'){
    const b = document.querySelector('[data-tr="' + tab + '"]');
    if(b){ b.click(); return }
  }
  window.__trWant = tab;
  goView('trend');
}
async function openTarget(it){
  if(!it) return;
  const p = it.payload || {};
  panel(false);
  switch(it.kind){
    case 'VOTE_RESULT':
      /* 마감 알림 → 살말로 가지 않고 피드백 창만 띄운다 (카드 정보를 누르면 그때 카드로 간다) */
      if(p.closed && p.card_id && window.feeditOpenFeedback){ window.feeditOpenFeedback(Number(p.card_id)); return }
      /* fallthrough — 10표 돌파 같은 알림은 그 카드로 */
    case 'VOTE_COMMENT':
      goView('salmal');
      if(p.card_id){
        const open = await waitFor(() => window.smOpenCard);
        if(open) open(Number(p.card_id), p.comment_id ? Number(p.comment_id) : null);
      }
      return;
    case 'JOB_REVIEW':
      /* 운영 계정 — 심사 창을 바로 연다. 신청자 — 결과를 볼 수 있는 마이페이지 */
      if(p.admin_pending && window.feeditOpenJobReview){ window.feeditOpenJobReview(); return }
      goView('mypage'); return;
    case 'PLAN_REVIEW':
      /* 운영 계정 — 요금제 신청 심사 창. 신청자 — 지금 요금제가 표시되는 요금제 화면 */
      if(p.admin_pending && window.feeditOpenPlanReview){ window.feeditOpenPlanReview(); return }
      planRefresh(); goView('price'); return;
    case 'BADGE':
      if(p.badge_id && window.feeditOpenBadge){ window.feeditOpenBadge(p.badge_id); return }
      goView('mypage'); return;
    case 'PROFILE_GENDER': openGenderAsk(); return;
    case 'PRICE_DROP':     goTrendTab('saved'); return;
    case 'WEEKLY_REPORT':  goTrendTab('report'); return;
    case 'TERM_ADDED':
      goTrendTab('temp');
      if(p.canonical_name){
        const go = await waitFor(() => window.feeditKwGo && document.getElementById('kwInput') && window.feeditKwGo);
        if(go) setTimeout(() => go(p.canonical_name), 120);
      }
      return;
    default:
      if(it.link) goView(it.link);
  }
}

/* ── 성별 고르기 (2026-10-02) ──────────────────────────────
   '성별을 알려 주세요' 알림을 누르면 뜬다. 고르는 순간 저장한다 — 버튼을 한 번 더
   누르게 하지 않는다. 저장되면 서버가 그 알림을 내리고(clear_gender_prompt),
   화면은 ME.gender 를 바꿔 입혀보기 기본 모델 · 코디 추천이 바로 따른다. */
let genderBusy = false;
export function openGenderAsk(){
  const m = $('#genderAskModal'); if(!m) return;
  const msg = $('#genderAskMsg'); if(msg) msg.textContent = '';
  m.querySelectorAll('[data-gender]').forEach(b => b.classList.remove('on'));
  m.classList.add('show');
  setTimeout(() => { const b = m.querySelector('[data-gender]'); if(b) b.focus() }, 60);
}
function closeGenderAsk(){ const m = $('#genderAskModal'); if(m) m.classList.remove('show') }
async function pickGender(btn){
  if(genderBusy) return;
  const value = btn.dataset.gender;
  const msg = $('#genderAskMsg');
  genderBusy = true;
  btn.classList.add('on');
  try{
    const data = await saveGender(value);
    if(data && data.user) applyAccountUser(data.user);
    closeGenderAsk();
    acctToast('성별을 저장했어요 · 입혀보기 모델과 코디 추천이 맞춰져요');
    notiRefresh();
  }catch(e){
    btn.classList.remove('on');
    if(msg) msg.textContent = (e && e.message) || '저장하지 못했어요. 잠시 후 다시 시도해 주세요.';
  }finally{ genderBusy = false }
}
document.addEventListener('click', e => {
  const t = e.target;
  if(!t || !t.closest) return;
  const pick = t.closest('#genderAskModal [data-gender]');
  if(pick){ pickGender(pick); return }
  if(t.closest('#genderAskModal [data-gender-close]') || t.id === 'genderAskModal') closeGenderAsk();
});
document.addEventListener('keydown', e => {
  const m = $('#genderAskModal');
  if(e.key === 'Escape' && m && m.classList.contains('show')) closeGenderAsk();
});

/* ── 패널 여닫기 ──────────────────────────────────────── */
function panel(on){
  const p = $('#notiPanel'), b = $('#notiBtn');
  if(!p) return;
  NT.open = on === undefined ? !p.classList.contains('on') : !!on;
  p.classList.toggle('on', NT.open);
  if(b) b.setAttribute('aria-expanded', NT.open ? 'true' : 'false');
  if(NT.open){
    document.dispatchEvent(new CustomEvent('feedit:popover', { detail:'noti' }));   /* 계정 메뉴를 닫는다 */
    paintList(); notiRefresh();
  }
}

function openItem(row){
  const id = Number(row.dataset.id);
  const open = row.querySelector('.notiOpen');
  const link = (open && open.dataset.link) || '';
  const it = NT.items.find(i => i.id === id);
  if(it && !it.read){
    it.read = true;
    NT.unread = Math.max(0, NT.unread - 1);
    row.classList.remove('unread');
    paintDot();
    readNotification(id);
  }
  openTarget(it || { link });
}

function delItem(row){
  const id = Number(row.dataset.id);
  const at = NT.items.findIndex(i => i.id === id);
  if(at < 0) return;
  const was = NT.items[at];
  NT.items.splice(at, 1);
  if(!was.read) NT.unread = Math.max(0, NT.unread - 1);
  paintDot(); paintList();
  deleteNotification(id).catch(e => {
    /* 못 지웠으면 되돌린다 — 지운 줄 알았는데 다음 새로고침에 살아 있으면 안 된다 */
    NT.items.splice(at, 0, was);
    if(!was.read) NT.unread += 1;
    paintDot(); paintList('지우지 못했습니다 — ' + (e.message || e));
    setTimeout(() => { if(NT.open) paintList() }, 1600);
  });
}

function delAll(){
  if(!NT.items.length) return;
  const before = NT.items.slice(), unread = NT.unread;
  NT.items = []; NT.unread = 0;
  paintDot(); paintList();
  deleteAllNotifications().catch(e => {
    NT.items = before; NT.unread = unread;
    paintDot(); paintList('지우지 못했습니다 — ' + (e.message || e));
    setTimeout(() => { if(NT.open) paintList() }, 1600);
  });
}

/* ── 알림 설정 ────────────────────────────────────────── */
function setMsg(text, bad){
  const p = $('#notiSetMsg');
  if(!p) return;
  p.textContent = text || '';
  p.classList.toggle('err', !!bad);
  p.style.display = text ? 'block' : 'none';
}

function setPaint(setting){
  const all = $('#notiSetAll'), box = $('#notiSetKinds');
  if(!all || !box) return;
  const on = setting ? setting.enabled !== false : true;
  const kinds = (setting && setting.kinds) || {};
  all.checked = on;
  box.innerHTML = KINDS.map(k =>
    '<label class="notiSetRow"><span class="notiSetName"><b>' + esc(k.n) + '</b>' +
    '<em>' + esc(k.d) + '</em></span>' +
    '<input type="checkbox" class="notiSw" data-kind="' + k.id + '"' +
    (kinds[k.id] === false ? '' : ' checked') + '>' +
    '<i class="notiSwUi" aria-hidden="true"></i></label>').join('');
  box.classList.toggle('off', !on);     /* 전체가 꺼지면 아래가 흐려진다 */
}

export function openNotiSetting(){
  const m = $('#notiSetModal');
  if(!m) return;
  setMsg('');
  setPaint(NT.setting);
  m.classList.add('on');
  /* 화면에 뜬 값은 서버 값이어야 한다 — 캐시로 먼저 그리고, 받으면 다시 그린다 */
  notificationSettings().then(s => { NT.setting = s; setPaint(s) })
    .catch(e => setMsg('설정을 받아오지 못했습니다 — ' + (e.message || e), true));
}

function saveSetting(){
  const all = $('#notiSetAll'), btn = $('#notiSetSave');
  if(!all || !btn) return;
  const kinds = {};
  $$('#notiSetKinds .notiSw').forEach(el => { kinds[el.dataset.kind] = el.checked });
  btn.disabled = true;
  const before = btn.textContent;
  btn.textContent = '저장 중…';
  setMsg('');
  saveNotificationSettings({ enabled: all.checked, kinds })
    .then(s => {
      NT.setting = s;
      setMsg('✓ 저장했습니다.');
      setTimeout(() => { const m = $('#notiSetModal'); if(m) m.classList.remove('on') }, 700);
    })
    .catch(e => setMsg('✕ ' + (e.message || e), true))
    .finally(() => { btn.disabled = false; btn.textContent = before });
}

/* ── 용어 사전 등재 요청 ──────────────────────────────────
   검색창이 "사전에 없다"고 말하는 자리(style/static/js/search.js)의 버튼이
   여기로 온다. 요청이 받아들여지면 등재된 날 TERM_ADDED 알림이 간다. */
function termReq(btn){
  const term = btn.dataset.termReq || '';
  if(!term) return;
  if(!AUTH.in){ goView('login'); return }
  btn.disabled = true;
  const before = btn.textContent;
  btn.textContent = '요청 중…';
  requestTerm(term)
    .then(d => {
      if(d.already){
        btn.textContent = '이미 사전에 있어요 — ' + d.canonical_name;
        return;
      }
      btn.textContent = d.created ? '✓ 요청했어요 — 등재되면 알림으로 알려 드려요'
                                  : '이미 요청한 용어예요';
    })
    .catch(e => {
      btn.disabled = false;
      btn.textContent = '✕ ' + (e.message || e || before);
    });
}

/* ── 묶기 ─────────────────────────────────────────────── */
function bind(){
  const btn = $('#notiBtn');
  if(btn) btn.addEventListener('click', e => { e.stopPropagation(); panel() });

  const list = $('#notiList');
  if(list) list.addEventListener('click', e => {
    const row = e.target.closest('.notiItem');
    if(!row) return;
    if(e.target.closest('.notiDel')){ delItem(row); return }
    if(e.target.closest('.notiOpen')) openItem(row);
  });

  const all = $('#notiReadAll');
  if(all) all.addEventListener('click', () => {
    if(!NT.unread) return;
    NT.items.forEach(i => { i.read = true });
    NT.unread = 0;
    paintDot(); paintList();
    readAllNotifications();
  });

  const delAllBtn = $('#notiDelAll');
  if(delAllBtn) delAllBtn.addEventListener('click', delAll);

  const link = $('#notiSetLink');
  if(link) link.addEventListener('click', () => { panel(false); openNotiSetting() });

  const save = $('#notiSetSave');
  if(save) save.addEventListener('click', saveSetting);
  [['#notiSetClose'], ['#notiSetCancel']].forEach(([sel]) => {
    const el = $(sel);
    if(el) el.addEventListener('click', () => { const m = $('#notiSetModal'); if(m) m.classList.remove('on') });
  });
  const allSw = $('#notiSetAll');
  if(allSw) allSw.addEventListener('change', () => {
    const box = $('#notiSetKinds');
    if(box) box.classList.toggle('off', !allSw.checked);
  });

  /* 패널 밖을 누르면 닫는다 (모달 오버레이는 profile.js 가 이미 처리한다) */
  document.addEventListener('click', e => {
    if(!e.target.closest('#notiWrap')) panel(false);
  });
  addEventListener('keydown', e => { if(e.key === 'Escape') panel(false) });

  /* 검색창의 '사전 등재 요청' 버튼 — 그리는 쪽은 search.js 다 */
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-term-req]');
    if(b) { e.stopPropagation(); termReq(b) }
  });

  document.addEventListener('feedit:auth', () => { AUTH.in ? start() : stop() });
  document.addEventListener('feedit:popover', e => { if(e.detail !== 'noti' && NT.open) panel(false) });
}

bind();
/* 새로고침해도 세션이 살아 있으면 알림을 켠다.
   profile.js 의 세션 복구는 feedit:auth 를 쏘지 않으므로 여기서 직접 확인한다. */
session().then(d => { if(d && d.authenticated) start() }).catch(() => {});
