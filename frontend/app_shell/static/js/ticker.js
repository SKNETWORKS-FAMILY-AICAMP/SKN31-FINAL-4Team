/* 실시간 공지 — 상단 가운데에 흘러가는 한 줄 (2026-10-02).
 *
 * 운영자가 관리자 화면(서비스 › 알림 · 실시간 공지)에서 올리면, 열려 있는 모든 화면이
 * 30초 안에 받아 헤더 바로 아래 가운데에 띄운다. 로그인하지 않은 방문자도 본다.
 *
 * 왜 30초 폴링인가 — API 는 동기 gunicorn 워커 3개라 연결을 오래 붙잡는 SSE/웹소켓을
 * 두면 그 자체가 렉이 된다. 버셀 중계도 10초면 끊는다. 서버는 목록을 15초 캐시하므로
 * 방문자가 늘어도 DB 는 15초에 한 번만 본다(notification_service.live_announcements).
 *
 * 닫기(×)는 그 공지만 이 브라우저에서 다시 안 띄운다. 새 공지가 오면 다시 뜬다.
 */
import { $ } from '../../../core/static/js/dom.js';
import { goView } from './router.js';
import { liveAnnouncements } from '../../../account/static/js/account_api.js';

const POLL_MS = 30000;
const SPEED = 70;                       /* 흐르는 속도 px/s — 한국어 한 줄을 편하게 읽는 정도 */
const SEEN_KEY = 'feedit:ticker-closed';
const TK = { items: [], timer: 0, sig: '' };

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));

function closedIds(){
  try{ return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]').map(Number)) }
  catch(e){ return new Set() }
}
function rememberClosed(ids){
  try{
    const keep = [...new Set([...closedIds(), ...ids])].slice(-40);
    localStorage.setItem(SEEN_KEY, JSON.stringify(keep));
  }catch(e){ /* 저장이 막힌 브라우저 — 이번 화면에서만 닫힌다 */ }
}

function host(){
  let el = $('#mTicker');
  if(el) return el;
  const head = document.querySelector('.mHead');
  if(!head) return null;
  el = document.createElement('div');
  el.id = 'mTicker';
  el.className = 'mTicker';
  el.hidden = true;
  el.setAttribute('role', 'status');
  el.setAttribute('aria-live', 'polite');
  head.appendChild(el);
  return el;
}

export function tickerPaint(items){
  const el = host(); if(!el) return;
  const closed = closedIds();
  const show = (items || []).filter(a => a && a.message && !closed.has(Number(a.id)));
  const sig = show.map(a => a.id + ':' + a.message + ':' + (a.link || '')).join('|');
  if(sig === TK.sig) return;               /* 같은 내용이면 흐름을 끊지 않는다 */
  TK.sig = sig; TK.items = show;
  if(!show.length){ el.hidden = true; el.innerHTML = ''; return; }
  const one = show.map(a =>
    '<button type="button" class="mTickItem"' + (a.link ? ' data-tick-go="' + esc(a.link) + '"' : ' tabindex="-1"') + '>' +
      esc(a.message) + (a.link ? '<i aria-hidden="true">→</i>' : '') + '</button>').join('<i class="mTickSep" aria-hidden="true">✦</i>');
  el.innerHTML =
    '<span class="mTickTag"><i class="mTickDot" aria-hidden="true"></i>NOTICE</span>' +
    '<span class="mTickWin"><span class="mTickTrack">' +
      '<span class="mTickRun">' + one + '</span>' +
      '<span class="mTickRun" aria-hidden="true">' + one + '</span>' +
    '</span></span>' +
    '<button type="button" class="mTickX" data-tick-close aria-label="공지 닫기">×</button>';
  el.hidden = false;
  /* 글 길이에 맞춰 속도를 일정하게 — 짧은 공지가 휙 지나가지 않게 */
  requestAnimationFrame(() => {
    const run = el.querySelector('.mTickRun');
    const w = run ? run.scrollWidth : 0;
    const win = el.querySelector('.mTickWin');
    const fits = win && w && w <= win.clientWidth;
    el.classList.toggle('still', Boolean(fits));
    if(w) el.style.setProperty('--tick-dur', Math.max(8, Math.round(w / SPEED)) + 's');
  });
}

async function refresh(){
  if(document.hidden) return;
  tickerPaint(await liveAnnouncements());
}
function start(){
  if(TK.timer) return;
  refresh();
  TK.timer = setInterval(refresh, POLL_MS);
}

document.addEventListener('click', e => {
  const t = e.target; if(!t || !t.closest) return;
  if(t.closest('#mTicker [data-tick-close]')){
    rememberClosed(TK.items.map(a => Number(a.id)));
    const el = $('#mTicker'); if(el){ el.hidden = true; el.innerHTML = ''; }
    TK.sig = '';
    return;
  }
  const go = t.closest('#mTicker [data-tick-go]');
  if(go) goView(go.dataset.tickGo);
});
document.addEventListener('visibilitychange', () => { if(!document.hidden) refresh(); });

start();
