import { $ } from '../../../core/static/js/dom.js';
import { planRequestsList, planReviewDecide, planRevoke, planStatus } from './account_api.js';

/* ══════════════════════════════════════════════════════════════
   요금제 — 프리 · 프로 · 비즈니스 (2026-10-03)
   --------------------------------------------------------------
   서버(backend/apps/api/plan_policy.py)가 로그인 응답의 user.billing 으로 준다.
     enforced  베타가 끝났나
     plan      FREE · PRO · BUSINESS · ADMIN
     features  지금 쓸 수 있는 것 {chat_daily, trend_edit:[탭 id], report_export, data_api …}
     request   진행 중인 내 신청 {plan, status:'PENDING'|…}

   ★ 베타 동안에는 아무것도 막지 않는다.
     서버가 enforced:true 를 보낼 때만 막는다. 값이 없거나(옛 서버) 모르면 막지 않는다 —
     화면이 먼저 배포되고 서버가 늦게 올라가도 지금의 베타 동작이 그대로다.

   ★ 화면의 잠금은 안내다. 돈이 드는 챗봇은 서버가 따로 막는다
     (Django 하루 횟수 + 챗봇 서버의 확인증 · 지표 게이트).
   ══════════════════════════════════════════════════════════════ */

export const PLAN_LABEL={FREE:'프리',PRO:'프로',BUSINESS:'비즈니스',ADMIN:'운영'};
export const PLAN_EVENT='feedit:plan';

const EDIT_ALL=['temp','assoc','sentiment','life','stock','resale'];
const OPEN={salmal:true,chat_daily:null,trend_feed:true,trend_edit:EDIT_ALL,report_export:true,data_api:true};
/* 서버가 enforced 라고 하면서 요금제 표를 안 보냈을 때만 쓰는 프리 기준 — 서버 표와 같은 값 */
const FREE_FALLBACK={salmal:true,chat_daily:20,trend_feed:true,trend_edit:['temp'],report_export:false,data_api:false};

let BILLING={enforced:false,signed_in:false,plan:'FREE',features:OPEN,plans:null,request:null,chat:null};

const notify=()=>{ try{ document.dispatchEvent(new CustomEvent(PLAN_EVENT,{detail:BILLING})) }catch(e){} };

export function planState(){ return BILLING }
export function planEnforced(){ return BILLING.enforced===true }

/* 서버가 준 billing 을 그대로 받는다. 모양이 이상하면 받지 않는다(지금 상태 유지). */
export function planApply(b){
  if(!b||typeof b!=='object')return;
  const enforced=b.enforced===true;
  BILLING={
    enforced,
    signed_in:Boolean(b.signed_in),
    plan:PLAN_LABEL[b.plan]?b.plan:'FREE',
    features:enforced?{...FREE_FALLBACK,...(b.features||{})}:OPEN,
    plans:b.plans&&typeof b.plans==='object'?b.plans:null,
    request:b.request&&typeof b.request==='object'?b.request:null,
    chat:b.chat&&typeof b.chat==='object'?b.chat:null,
  };
  notify();
}
/* 서버에서 지금 요금제를 다시 받는다 — 승인 · 반려 알림이 왔을 때. 실패는 조용히 넘긴다. */
export function planRefresh(){
  return planStatus().then(planApply).catch(()=>{});
}
/* 챗봇 한 번 쓰고 받은 오늘 사용량만 바꾼다 */
export function planApplyChat(d){
  if(!d||typeof d!=='object'||!d.chat)return;
  BILLING={...BILLING,chat:d.chat};
  notify();
}
/* 로그아웃 — 베타 여부는 그대로 두고 로그인 전(프리 기준)으로 돌린다 */
export function planSignedOut(){
  const free=(BILLING.plans&&BILLING.plans.FREE)||FREE_FALLBACK;
  BILLING={...BILLING,signed_in:false,plan:'FREE',request:null,chat:null,
           features:BILLING.enforced?{...FREE_FALLBACK,...free}:OPEN};
  notify();
}

export function planAllows(key){
  if(!planEnforced())return true;
  return Boolean((BILLING.features||{})[key]);
}
/* 트렌드 분석 EDIT 탭 하나를 볼 수 있나 */
export function planEditAllowed(tab){
  if(!planEnforced())return true;
  const t=(BILLING.features||{}).trend_edit;
  return Array.isArray(t)&&t.indexOf(tab)>=0;
}
/* 진행 중인 신청 */
export function planPending(){
  const r=BILLING.request;
  return r&&r.status==='PENDING'?r:null;
}

/* ── 잠겼을 때 하는 말 ──
   재촉하지 않는다. 무엇이 어느 요금제부터인지 사실만 적는다. */
const LOCK_TEXT={
  report_export:'리포트 내보내기(저장 · 공유)는 프로 요금제부터 쓸 수 있어요.',
  data_api:'데이터 API 연동은 비즈니스 요금제에서 쓸 수 있어요.',
};
function planToast(msg){
  const t=$('#toast'); if(!t)return;
  t.textContent=msg; t.classList.add('on');
  clearTimeout(planToast.t);
  planToast.t=setTimeout(()=>t.classList.remove('on'),2600);
}
/* 쓸 수 있으면 true. 못 쓰면 이유를 알리고 false. toast 를 주면 그 화면의 알림으로 말한다. */
export function planGuard(key,toast){
  if(planAllows(key))return true;
  (typeof toast==='function'?toast:planToast)(LOCK_TEXT[key]||'지금 요금제에서는 쓸 수 없는 기능이에요.');
  return false;
}

const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

/* 받침에 맞는 조사 — "긍부정은" / "연관어는" */
const eunNeun=w=>{ const c=String(w||'').trim().slice(-1);
  const h=c.charCodeAt(0)-0xAC00; return (h>=0&&h<11172&&h%28)?'은':'는' };

/* 트렌드 분석 — 잠긴 탭 자리에 세우는 안내. '요금제 보기' 는 router 의 data-v 위임이 받는다. */
export function planLockHTML(title){
  const pending=planPending();
  const name=title||'이 지표';
  return '<div class="planLock">'+
    '<span class="planLockTag">PRO</span>'+
    '<h4>'+esc(name)+eunNeun(name)+' 프로 요금제부터 볼 수 있어요.</h4>'+
    '<p>프리 요금제의 EDIT 은 언급량 · 온도까지 열려 있습니다.<br>'+
      (pending?esc(PLAN_LABEL[pending.plan]||pending.plan)+' 신청을 심사 중이에요. 승인되면 알림으로 알려 드려요.'
              :'프로로 바꾸면 연관어 · 긍부정 · 수명주기 · 할인률 · 리세일까지 모두 볼 수 있어요.')+'</p>'+
    '<button type="button" class="pill sm" data-v="price">요금제 보기</button>'+
  '</div>';
}

/* ── 관리자 — 요금제 신청 심사 (운영 계정만 · 서버도 403 으로 막는다) ── */
let PR_ROWS=[], PR_FILTER='PENDING', PR_ENFORCED=true;
const PR_ST={PENDING:'대기',APPROVED:'승인',REJECTED:'반려'};
const prDate=v=>{ const d=new Date(v); return isNaN(d)?'':(d.getMonth()+1)+'.'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0') };
const badge=p=>'<span class="planBadge '+esc(String(p||'').toLowerCase())+'">'+esc(PLAN_LABEL[p]||p||'-')+'</span>';

export async function planReviewRender(){
  const host=$('#planReviewList'); if(!host)return;
  host.innerHTML='<p class="jrEmpty">신청 목록을 불러오는 중입니다.</p>';
  try{
    const d=await planRequestsList(PR_FILTER);
    PR_ROWS=d.items||[];
    PR_ENFORCED=d.enforced!==false;
  }catch(e){ host.innerHTML='<p class="jrEmpty">'+esc(e.message||'목록을 불러오지 못했습니다.')+'</p>'; return; }
  prPaint();
}
function prPaint(){
  const host=$('#planReviewList'); if(!host)return;
  const tabs='<div class="jrTabs">'+[['PENDING','대기 중'],['ALL','전체']].map(([k,l])=>
    '<button type="button" data-pr-tab="'+k+'" class="'+(PR_FILTER===k?'on':'')+'">'+l+'</button>').join('')+'</div>';
  const beta=PR_ENFORCED?'':'<p class="prqBeta">지금은 베타 기간이라 새 신청을 받지 않습니다.<br>FEEDIT_PUBLIC_BETA=0 으로 베타를 끝내면 신청이 열립니다.</p>';
  if(!PR_ROWS.length){
    host.innerHTML=tabs+beta+'<p class="jrEmpty">'+(PR_FILTER==='PENDING'?'심사를 기다리는 신청이 없습니다.':'아직 들어온 요금제 신청이 없습니다.')+'</p>';
    return;
  }
  host.innerHTML=tabs+beta+PR_ROWS.map(r=>{
    const st=String(r.status||'').toLowerCase();
    const live=r.status==='APPROVED'&&r.current_plan===r.plan&&r.plan!=='FREE';
    const lines=[
      '현재 '+esc(PLAN_LABEL[r.current_plan]||r.current_plan)+' → '+esc(PLAN_LABEL[r.plan]||r.plan)+' · '+prDate(r.requested_at),
      r.company?'팀 · 회사 '+esc(r.company):'',
      '연락처 '+esc(r.contact||r.email||'계정 이메일 없음'),
      r.note?'메모 '+esc(r.note):'',
      r.reason?'사유 '+esc(r.reason):'',
    ].filter(Boolean).join('<br>');
    let acts='';
    if(r.status==='PENDING'){
      acts='<div class="jrActs prqActs">'+
        '<input type="text" class="prqReason" maxlength="200" placeholder="사유 (선택)" data-pr-reason="'+r.user_id+'">'+
        '<button type="button" class="pill ghost sm" data-pr-no="'+r.user_id+'">반려</button>'+
        '<button type="button" class="pill sm" data-pr-ok="'+r.user_id+'">승인</button></div>';
    }else if(live){
      acts='<div class="jrActs"><button type="button" class="pill ghost sm" data-pr-revoke="'+r.user_id+'" '+
        'title="이 사용자의 요금제를 바로 프리로 바꿉니다">프리로 되돌리기</button></div>';
    }
    return '<div class="jrItem prq '+st+(live?' live':'')+'">'+
      '<div class="jrBody">'+
        '<div class="jrHead">'+badge(r.plan)+'<b>'+esc(r.nickname)+'</b><small>@'+esc(r.username)+'</small>'+
          '<em class="jrSt">'+(live?'이용 중':(PR_ST[r.status]||esc(r.status)))+'</em></div>'+
        '<div class="jrMeta">'+lines+'</div>'+
      '</div>'+acts+
    '</div>';
  }).join('');
}
export function planReviewBind(onDone){
  const host=$('#planReviewList');
  if(!host||host.dataset.bound)return;
  host.dataset.bound='1';
  host.addEventListener('click',async e=>{
    const tab=e.target.closest('[data-pr-tab]');
    if(tab){ PR_FILTER=tab.dataset.prTab; planReviewRender(); return; }
    const ok=e.target.closest('[data-pr-ok]'), no=e.target.closest('[data-pr-no]'),
          rv=e.target.closest('[data-pr-revoke]');
    if(!ok&&!no&&!rv)return;
    const btn=ok||no||rv;
    const userId=+(ok?ok.dataset.prOk:no?no.dataset.prNo:rv.dataset.prRevoke);
    if(rv&&typeof confirm==='function'&&!confirm('이 사용자의 요금제를 지금 프리로 바꿀까요?'))return;
    const input=host.querySelector('[data-pr-reason="'+userId+'"]');
    const reason=input?input.value.trim().slice(0,200):'';
    btn.disabled=true;
    try{
      if(rv)await planRevoke({userId});
      else await planReviewDecide({userId, approve:!!ok, reason});
      await planReviewRender();
      if(onDone)onDone(rv?'revoke':ok?'approve':'reject');
    }catch(err){ btn.disabled=false; if(onDone)onDone(null, err.message); }
  });
}
