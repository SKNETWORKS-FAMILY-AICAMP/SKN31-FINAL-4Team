/* ══════════════════════════════════════════════════════════════
   경험치 기록 — 접속 · 트렌드 분석 체류 시간 (2026-09-25)
   --------------------------------------------------------------
   · 접속
     새로고침 · 로그인할 때 서버(/api/auth/me)가 오늘 접속을 이미 적는다.
     여기서는 탭을 켜 둔 채 자정(한국 시간)을 넘긴 경우만 다시 알린다.

   · 트렌드 분석 체류
     아래가 모두 맞을 때만 초를 센다.
       - 로그인했다
       - 트렌드 분석 화면(v-trend)에 있다
       - 탭이 보이고 창에 초점이 있다
       - 5분 안에 마우스 · 키보드 · 스크롤 · 터치가 있었다
     60초가 모이면 서버로 보낸다 (/api/auth/xp {type:'DWELL'}).

     서버도 믿지 않는다 — 한 번에 90초까지,
     그리고 오늘 마지막으로 받은 때부터 실제로 흐른 시간만큼만 더한다
     (backend/apps/api/xp_service.add_dwell).
   ══════════════════════════════════════════════════════════════ */
import { AUTH, applyXp } from './profile.js';
import { xpDwell, xpVisit } from './account_api.js';

const TICK_MS = 5000;
const SEND_AT = 60;               /* 이만큼(초) 모이면 보낸다 */
const IDLE_MS = 5 * 60 * 1000;    /* 이보다 오래 손을 안 대면 자리를 비운 것으로 본다 */

let pending = 0;                  /* 아직 보내지 않은 체류 초 */
let lastInput = Date.now();
let sending = false;
let visitDay = kstDay();

/* 한국 시간 날짜 — 서버의 하루 기준과 같다 */
function kstDay(){
  return new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
}

function watching(){
  return AUTH.in
    && document.body.dataset.view === 'trend'
    && document.visibilityState === 'visible'
    && (typeof document.hasFocus !== 'function' || document.hasFocus())
    && Date.now() - lastInput < IDLE_MS;
}

function flush(){
  if(sending || !AUTH.in || pending < 1) return;
  const seconds = Math.min(90, Math.round(pending));
  pending = 0;
  sending = true;
  xpDwell(seconds)
    .then(d => applyXp(d && d.xp))
    .catch(() => { /* 기록 실패는 화면을 막지 않는다 — 다음 60초에 다시 모인다 */ })
    .finally(() => { sending = false; });
}

function dayCheck(){
  const d = kstDay();
  if(d === visitDay || !AUTH.in || document.visibilityState !== 'visible') return;
  visitDay = d;
  xpVisit().then(r => applyXp(r && r.xp)).catch(() => {});
}

['pointermove', 'pointerdown', 'keydown', 'wheel', 'scroll', 'touchstart'].forEach(ev =>
  addEventListener(ev, () => { lastInput = Date.now(); }, { passive:true, capture:true }));

setInterval(() => {
  if(watching()) pending += TICK_MS / 1000;
  if(pending >= SEND_AT) flush();
  dayCheck();
}, TICK_MS);

document.addEventListener('visibilitychange', () => {
  if(document.visibilityState === 'hidden'){ if(pending >= 10) flush(); }
  else { lastInput = Date.now(); dayCheck(); }
});

/* 계정이 바뀌면 앞 계정의 초를 넘기지 않는다. 오늘 접속은 로그인 응답이 이미 적었다. */
document.addEventListener('feedit:auth', () => { pending = 0; visitDay = kstDay(); });
