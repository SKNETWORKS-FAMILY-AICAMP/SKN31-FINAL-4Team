/* ══════════════════════════════════════════════════════════════
   경험치 창 · 홈페이지 피드백 창 (2026-09-25)
   --------------------------------------------------------------
   · 경험치 창(#xpModal)
     마이페이지 경험치 바 아래 요약(#xpMore)을 누르면 뜬다.
     오늘 · 이번 주에 무엇으로 얼마를 받았는지, 레벨 구간이 어떻게 되는지 보여 준다.
     숫자와 항목 이름 · 설명은 전부 서버가 준다 (backend/apps/api/xp.py).

   · 홈페이지 피드백 창(#siteFbModal)
     헤더 계정 메뉴의 '피드백 보내기', 또는 경험치 창의 '남기기'로 연다.
     불편사항·추가요청 / 수정사항·버그리포트 중 하나를 골라 남긴다.
     이번 주 첫 피드백이면 +25 XP.
   ══════════════════════════════════════════════════════════════ */
import { $ } from '../../../core/static/js/dom.js';
import { AUTH, ME, applyXp, closeAcctMenu, requireAuth } from './profile.js';
import { RK_MAX, RK_XP, rkChip, rkName } from './rank.js';
import { sendSiteFeedback, siteFeedbackList, xpState } from './account_api.js';

const esc = s => String(s ?? '').replace(/[&<>"']/g,
  c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
const modal = (id, on) => { const m = $('#' + id); if(m) m.classList.toggle('on', on); };
const n = v => (Number(v) || 0).toLocaleString();

/* ── 경험치 창 ───────────────────────────────────────── */

function dayLabel(iso){
  const [y, m, d] = String(iso || '').split('-').map(Number);
  if(!y) return '';
  const w = '일월화수목금토'[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return m + '.' + d + ' (' + w + ')';
}
const shortDay = iso => { const [, m, d] = String(iso || '').split('-').map(Number); return m ? m + '.' + d : ''; };

/* 항목마다 '지금 어디까지 했는지' — 서버가 준 횟수 · 분을 사람 말로 */
function progressText(item){
  switch(item.key){
    case 'visit':         return item.count ? '접속함' : '아직';
    case 'chat':
    case 'vote':
    case 'save':
    case 'hit':           return n(item.count) + '회';
    case 'attend':        return item.count + ' / ' + item.goal + '일';
    case 'dwell':         return n(item.minutes) + ' / ' + item.goal + '분';
    case 'vote_feedback':
    case 'site_feedback': return item.count ? n(item.count) + '건' : '아직';
    default:              return '';
  }
}

function rowHTML(item){
  const cls = item.xp >= item.max ? ' full' : item.xp > 0 ? ' got' : '';
  const stat = item.key === 'site_feedback' && !item.count
    ? '<button type="button" class="xpRowGo" data-xp-go="feedback">남기기</button>'
    : esc(progressText(item));
  return '<li class="xpRow' + cls + '">' +
    '<div class="xpRowName"><b>' + esc(item.label) + '</b><span>' + esc(item.hint) + '</span></div>' +
    '<div class="xpRowStat">' + stat + '</div>' +
    '<div class="xpRowXp"><b>' + item.xp + '</b><span>/ ' + item.max + '</span></div>' +
  '</li>';
}

function ladderHTML(lv){
  const cells = [];
  for(let i = 0; i <= RK_MAX; i++){
    cells.push('<li class="' + (i === lv ? 'on' : i < lv ? 'past' : '') + '">' +
      '<b>' + rkName(i) + '</b>' + n(RK_XP[i]) + '</li>');
  }
  return '<ol class="xpLadder" aria-label="레벨 구간">' + cells.join('') + '</ol>';
}

export function xpRender(){
  const host = $('#xpDetail'); if(!host) return;
  if(ME.xpFixed){
    host.innerHTML =
      '<div class="xpHero">' + rkChip(RK_MAX, true) + '<b>운영 계정</b>' +
        '<em>경험치를 세지 않고 최고 레벨로 고정합니다.</em></div>' +
      ladderHTML(RK_MAX);
    return;
  }
  const info = ME.xpInfo;
  if(!info || !info.today || !info.week){
    host.innerHTML = '<p class="fieldMsg">경험치를 불러오는 중…</p>';
    return;
  }
  const lv = ME.rank, total = Number(ME.xp) || 0, next = RK_XP[lv + 1];
  const t = info.today, w = info.week;
  host.innerHTML =
    '<div class="xpHero">' + rkChip(lv, true) + '<b>' + n(total) + ' XP</b>' +
      '<em>' + (next === Infinity ? '최고 레벨입니다' : rkName(lv + 1) + ' 까지 ' + n(next - total) + ' XP') + '</em></div>' +

    '<section class="xpSec">' +
      '<header class="xpSecHead"><h4>오늘</h4><span>' + esc(dayLabel(t.date)) + '</span>' +
        '<strong>' + t.earned + '<em> / ' + t.cap + '</em></strong></header>' +
      '<ul class="xpRows">' + t.items.map(rowHTML).join('') + '</ul>' +
    '</section>' +

    '<section class="xpSec">' +
      '<header class="xpSecHead"><h4>이번 주</h4><span>' + esc(shortDay(w.start)) + ' – ' + esc(shortDay(w.end)) + '</span>' +
        '<strong>' + w.earned + '<em> / ' + w.cap + '</em></strong></header>' +
      '<div class="xpSplit"><span>일일 합계 <b>' + w.daily.earned + '</b> / ' + w.daily.cap + '</span>' +
        '<span>주간 항목 <b>' + w.weekly.earned + '</b> / ' + w.weekly.cap + '</span></div>' +
      '<ul class="xpRows">' + w.weekly.items.map(rowHTML).join('') + '</ul>' +
    '</section>' +

    ladderHTML(lv) +
    '<p class="xpFoot">하루는 0시, 한 주는 월요일 0시(한국 시간)에 새로 시작합니다.<br>' +
      '경험치는 서버에 남은 활동 기록으로만 계산합니다.</p>';
}

export function openXp(){
  if(!requireAuth(openXp)) return;
  xpRender();
  modal('xpModal', true);
  /* 창을 연 순간의 값으로 먼저 그리고, 서버 값이 오면 다시 그린다 */
  xpState().then(d => { applyXp(d && d.xp); xpRender(); }).catch(() => {});
}

/* ── 홈페이지 피드백 창 ───────────────────────────────── */

const VIEW_NAME = { home:'홈', trend:'트렌드 분석', salmal:'살!말?', style:'스타일', price:'요금제', mypage:'마이페이지' };
const PLACEHOLDER = {
  REQUEST:'어떤 점이 불편했나요?\n있었으면 하는 기능도 좋아요.',
  BUG:'어느 화면에서 무엇을 눌렀을 때 어떻게 됐는지 적어 주세요.\n\n예) 트렌드 분석 → 긍부정 탭을 누르면 차트가 비어요',
};
const MIN_LEN = 10;
let sfKind = 'REQUEST';
let sfPage = '';

function sfMsg(text, kind){
  const m = $('#sfMsg'); if(!m) return;
  m.textContent = text || '';
  m.className = 'fieldMsg' + (kind ? ' ' + kind : '');
}
function sfCount(){
  const t = $('#sfText'), c = $('#sfCount');
  if(t && c) c.textContent = t.value.length;
}
function sfKindSet(kind){
  sfKind = kind === 'BUG' ? 'BUG' : 'REQUEST';
  document.querySelectorAll('#sfKinds .sfKind').forEach(b => {
    const on = b.dataset.kind === sfKind;
    b.classList.toggle('on', on);
    b.setAttribute('aria-checked', on ? 'true' : 'false');
  });
  const t = $('#sfText'); if(t) t.placeholder = PLACEHOLDER[sfKind];
}

async function sfLoadList(){
  const host = $('#sfList'); if(!host) return;
  host.innerHTML = '<p class="sfEmpty">불러오는 중…</p>';
  try{
    const d = await siteFeedbackList();
    const items = (d && d.items) || [];
    host.innerHTML = items.length
      ? '<ul class="sfItems">' + items.map(it =>
          '<li class="sfItem"><div class="sfItemHead">' +
            '<span class="sfTag">' + esc(it.kind_label) + '</span>' +
            '<span class="sfState s-' + esc(String(it.status || '').toLowerCase()) + '">' + esc(it.status_label) + '</span>' +
            '<time>' + esc(it.created_at) + '</time></div>' +
          '<p>' + esc(it.content) + '</p></li>').join('') + '</ul>'
      : '<p class="sfEmpty">아직 남긴 피드백이 없어요.</p>';
  }catch(e){
    host.innerHTML = '<p class="sfEmpty">목록을 불러오지 못했어요.</p>';
  }
}

export function openSiteFeedback(){
  if(!requireAuth(openSiteFeedback)) return;
  const view = document.body.dataset.view || '';
  sfPage = VIEW_NAME[view] || view;
  modal('xpModal', false);
  sfKindSet(sfKind);
  sfMsg('');
  sfCount();
  const p = $('#sfPage'); if(p) p.textContent = sfPage ? '보내는 화면 · ' + sfPage : '';
  modal('siteFbModal', true);
  sfLoadList();
  setTimeout(() => { const t = $('#sfText'); if(t) t.focus(); }, 60);
}

async function sfSend(){
  const btn = $('#sfSend'), t = $('#sfText');
  if(!btn || !t || btn.disabled) return;
  const text = t.value.trim();
  if(text.length < MIN_LEN){ sfMsg(MIN_LEN + '자 이상 적어 주세요.', 'err'); t.focus(); return; }
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = '보내는 중…';
  sfMsg('');
  try{
    const d = await sendSiteFeedback({ kind:sfKind, content:text, page:sfPage });
    applyXp(d && d.xp);
    t.value = '';
    sfCount();
    sfMsg(d && d.rewarded ? '보냈어요. 이번 주 피드백 경험치 +25 XP 를 받았어요.'
      : ME.xpFixed ? '보냈어요. 운영 계정은 경험치가 고정이라 따로 쌓이지 않아요.'
      : '보냈어요. 이번 주 피드백 경험치는 이미 받으셨어요.', 'ok');
    sfLoadList();
  }catch(e){
    sfMsg(e.message || '보내지 못했어요. 잠시 뒤 다시 시도해 주세요.', 'err');
  }finally{
    btn.disabled = false;
    btn.textContent = label;
  }
}

/* ── 바인딩 ──────────────────────────────────────────── */
const more = $('#xpMore');
if(more) more.addEventListener('click', openXp);
const detail = $('#xpDetail');
if(detail) detail.addEventListener('click', e => {
  if(e.target.closest('[data-xp-go="feedback"]')) openSiteFeedback();
});
const menu = $('#menuFeedback');
if(menu) menu.addEventListener('click', () => { closeAcctMenu(); openSiteFeedback(); });
const kinds = $('#sfKinds');
if(kinds) kinds.addEventListener('click', e => {
  const b = e.target.closest('.sfKind'); if(b) sfKindSet(b.dataset.kind);
});
const txt = $('#sfText');
if(txt) txt.addEventListener('input', () => { sfCount(); sfMsg(''); });
const send = $('#sfSend');
if(send) send.addEventListener('click', sfSend);
/* 로그아웃하면 열려 있던 두 창을 닫는다 — 앞 계정의 경험치 · 피드백이 남지 않게 */
document.addEventListener('feedit:auth', () => {
  if(!AUTH.in){ modal('xpModal', false); modal('siteFbModal', false); }
});
