import { $, $$ } from '../../../core/static/js/dom.js';
import { AUTH, ME, requireAuth } from '../../../account/static/js/profile.js';
import { cancelPlanRequest, planRequestSubmit } from '../../../account/static/js/account_api.js';
import { PLAN_EVENT, PLAN_LABEL, planApply, planEnforced, planPending, planState } from '../../../account/static/js/plan.js';
import { goView } from '../../../app_shell/static/js/router.js';

/* ── 요금제 ─────────────────────────────────────────── */
/* k 는 서버 요금제 이름(backend/apps/api/plan_policy.py)과 같다 */
const PRICES=[
  {k:'FREE',n:'프리',p:'0',u:'원 / 월',d:'개인 사용자를 위한 기본 플랜'},
  {k:'PRO',n:'프로',p:'19,900',u:'원 / 월',d:'실무에 매일 쓰는 분들께',best:1},
  {k:'BUSINESS',n:'비즈니스',p:'문의',u:'',d:'팀 단위 협업과 데이터 연동'}
];
/* 기능 비교표 — 값은 [프리, 프로, 비즈니스] 순. 줄바꿈은 '|'
   ★ 실제로 막는 규칙은 서버(plan_policy.py FEATURES)에 있다. 이 표를 바꾸면 거기도 같이 바꾼다. */
const COMPARE=[
  ['살!말? 참여',['무제한','무제한','무제한']],
  ['AI 챗',['하루 20회','무제한','무제한']],
  ['트렌드 분석',['FEED 전체|+|EDIT 언급량·온도','FEED 전체|+|EDIT 전체','FEED 전체|+|EDIT 전체']],
  ['리포트 내보내기',['미지원','지원','지원']],
  ['데이터 API 연동',['미지원','미지원','지원']]
];
const FAQS=[
  ['데이터는 어디서 수집하나요?','무신사·지그재그·KREAM 등 커머스와 유튜브(롱폼/숏폼), 패션 카페·블로그, 네이버 데이터랩을 24시간 주기로 수집합니다.'],
  ['상승·하락은 어떤 기준인가요?','직전 4주 평균 대비 최근 7일 언급량 변화율을 기본으로, 긍부정 반응률과 저장·클릭을 가중합니다. “언급은 늘었는데 반응은 나쁜” 케이스를 걸러내기 위해서입니다.'],
  ['살!말?은 누구에게 노출되나요?','기본값은 취향 태그가 2개 이상 겹치는 유저입니다.'],
  ['무료 플랜에도 제한이 있나요?','AI 챗은 하루 20회, 랭킹은 TOP 10까지 보입니다. 살!말? 참여와 스타일 탐색은 제한 없이 사용할 수 있습니다.']
];
/* 베타가 끝난 뒤(서버 enforced)에만 바꿔 다는 문구 — 베타 동안에는 위 원래 문구 그대로다.
   ★ '베타 기간엔 대부분 무료' 는 베타가 끝나면 사실이 아니게 된다. */
const LIVE_TITLE='필요한 만큼만<br>골라 쓰세요.';
const LIVE_FREE_FAQ='AI 챗은 하루 20회, 트렌드 분석 EDIT 은 언급량·온도까지 볼 수 있고 리포트 내보내기는 지원하지 않습니다. 살!말? 참여와 FEED(내 피드 · 금주의 리포트 · 찜한 키워드)는 제한 없이 사용할 수 있습니다.';
let BETA_TITLE=null;

var prToastT;
function prToast(msg){
  const t=$('#toast'); if(!t)return;
  t.textContent=msg; t.classList.add('on');
  clearTimeout(prToastT);
  prToastT=setTimeout(()=>t.classList.remove('on'),2600);
}
export function prBuild(){
  const cards=PRICES.map(p=>
    '<div class="prCard'+(p.best?' best':'')+'" role="button" tabindex="0" data-plan="'+p.k+'"><div class="pl"><div class="bd1"><b>'+p.n+'</b>'+
    (p.best?'<u>추천</u>':'')+'</div><div class="ds">'+p.d+'</div></div>'+
    '<div class="pz"><b>'+p.p+'</b><span>'+p.u+'</span></div></div>').join('');
  const table='<table class="prTbl"><thead><tr><th class="corner"><i>요금제</i><em>기능</em></th>'+
    PRICES.map(p=>'<th>'+p.n+'</th>').join('')+'</tr></thead><tbody>'+
    COMPARE.map(r=>'<tr><th>'+r[0]+'</th>'+
      r[1].map(v=>'<td>'+v.split('|').join('<br>')+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
  $('#prGrid').innerHTML='<div class="prCards">'+cards+'</div><div class="prTblWrap">'+table+'</div>';
  document.querySelectorAll('#prGrid .prCard').forEach((c,i)=>{
    /* 베타 동안은 예전 그대로 안내만 한다. 베타가 끝나면(서버 enforced) 신청 · 해지 창을 연다. */
    const go=()=>planEnforced()?prPick(PRICES[i].k):prToast('현재 베타 기간으로 무료로 사용 가능합니다.');
    c.addEventListener('click',go);
    c.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); go(); } });
  });
  $('#faq').innerHTML=FAQS.map(f=>'<details><summary>'+f[0]+'</summary><p>'+f[1]+'</p></details>').join('');
  prPaint();
  prFormBind();
}

/* ── 베타 이후 — 카드에 '이용 중' · '심사 중' 표시, 머리글 · 자주 묻는 질문 문구 ── */
function prPaint(){
  const live=planEnforced();
  const title=$('#v-price .priceTitle');
  if(title){
    if(BETA_TITLE===null)BETA_TITLE=title.innerHTML;
    const want=live?LIVE_TITLE:BETA_TITLE;
    if(title.innerHTML!==want)title.innerHTML=want;
  }
  const freeFaq=$$('#faq details p')[3];
  if(freeFaq)freeFaq.textContent=live?LIVE_FREE_FAQ:FAQS[3][1];
  const st=planState(), pending=planPending();
  $$('#prGrid .prCard').forEach(c=>{
    const old=c.querySelector('.prState'); if(old)old.remove();
    c.classList.remove('current','pending');
    if(!live||!st.signed_in)return;
    const k=c.dataset.plan;
    let tag='';
    if(st.plan===k||(st.plan==='ADMIN'&&k==='BUSINESS')){
      c.classList.add('current');
      tag=st.plan==='ADMIN'?'운영 계정':'이용 중';
      /* 프리 — 오늘 AI 챗을 몇 번 썼는지 같이 적는다 */
      if(k==='FREE'&&st.chat&&st.chat.limit!=null)tag+=' · 오늘 AI 챗 '+st.chat.used+'/'+st.chat.limit+'회';
    }else if(pending&&pending.plan===k){
      c.classList.add('pending'); tag='신청 심사 중';
    }
    if(tag){
      const em=document.createElement('em'); em.className='prState'; em.textContent=tag;
      const bd=c.querySelector('.bd1'); if(bd)bd.appendChild(em);
    }
  });
}
document.addEventListener(PLAN_EVENT,prPaint);

/* ── 신청 · 해지 창 (#planModal) ── */
let PR_MODE=null;   /* {k, kind:'request'|'downgrade'|'cancel'} */
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modal=on=>{ const m=$('#planModal'); if(m)m.classList.toggle('on',on); };

function prPick(k){
  if(!AUTH.ready){ prToast('로그인 상태를 확인하는 중이에요. 잠시 뒤 다시 눌러 주세요.'); return; }
  if(!AUTH.in){
    prToast('로그인한 뒤 요금제를 신청할 수 있어요.');
    requireAuth(()=>goView('price'));
    return;
  }
  const st=planState(), cur=st.plan, pending=planPending();
  if(cur==='ADMIN'||ME.role==='admin'){ prToast('운영 계정은 요금제와 상관없이 모든 기능을 씁니다.'); return; }
  if(k==='FREE'){
    if(cur!=='FREE')return prOpen({k,kind:'downgrade'});
    if(pending)return prOpen({k:pending.plan,kind:'cancel'});
    prToast('지금 프리 요금제를 쓰고 계세요.'); return;
  }
  if(cur===k){ prToast('이미 '+PLAN_LABEL[k]+' 요금제를 쓰고 계세요.'); return; }
  prOpen({k,kind:'request'});
}

function prField(id,label,sub,attrs){
  return '<div class="planField"><label for="'+id+'">'+label+(sub?' <span>'+sub+'</span>':'')+'</label>'+
    (attrs.area?'<textarea id="'+id+'" maxlength="'+attrs.max+'" rows="3" placeholder="'+esc(attrs.ph||'')+'"></textarea>'
               :'<input id="'+id+'" type="text" maxlength="'+attrs.max+'" autocomplete="off" placeholder="'+esc(attrs.ph||'')+'">')+
  '</div>';
}
function prOpen(mode){
  PR_MODE=mode;
  const st=planState(), pending=planPending();
  const label=PLAN_LABEL[mode.k]||mode.k;
  const title=$('#planModalTitle'), body=$('#planFormBody'), btns=$('#planFormBtns'), err=$('#planFormErr');
  if(!title||!body||!btns)return;
  if(err){ err.hidden=true; err.textContent=''; }
  if(mode.kind==='downgrade'){
    title.textContent='프리로 바꾸기';
    body.innerHTML='<p class="planLead">지금 쓰는 <b>'+esc(PLAN_LABEL[st.plan]||st.plan)+'</b> 요금제를 해지하고 프리로 돌아갑니다.<br>'+
      '바로 적용되고, 승인을 기다리지 않습니다.</p>'+
      '<p class="planNote">프리에서는 AI 챗이 하루 20회로 줄고,<br>트렌드 분석 EDIT 은 언급량 · 온도만 열리며, 리포트 내보내기가 잠깁니다.</p>'+
      (pending?'<p class="planNote">심사 중인 '+esc(PLAN_LABEL[pending.plan]||pending.plan)+' 신청도 함께 취소됩니다.</p>':'');
    btns.innerHTML='<button type="button" class="pill ghost" data-plan-close>닫기</button>'+
      '<button type="submit" class="pill">해지하기</button>';
  }else if(mode.kind==='cancel'){
    title.textContent='신청 취소';
    body.innerHTML='<p class="planLead">심사 중인 <b>'+esc(label)+'</b> 요금제 신청을 취소할까요?</p>';
    btns.innerHTML='<button type="button" class="pill ghost" data-plan-close>닫기</button>'+
      '<button type="submit" class="pill">신청 취소</button>';
  }else{
    const biz=mode.k==='BUSINESS';
    title.textContent=label+' 요금제 신청';
    body.innerHTML='<p class="planLead">결제는 아직 붙어 있지 않아요.<br>'+
      '신청하면 운영팀이 확인한 뒤 승인해 드리고, 결과는 알림으로 알려 드려요.</p>'+
      (pending?'<p class="planNote">지금 '+esc(PLAN_LABEL[pending.plan]||pending.plan)+' 신청을 심사 중이에요.<br>새로 신청하면 이전 신청을 대신합니다.</p>':'')+
      (biz?prField('planCompany','팀 · 회사 이름','필수',{max:60,ph:'예: FEEDiT 마케팅팀'}):'')+
      prField('planContact','연락처','선택 · 비우면 계정 이메일로 연락드려요',{max:80,ph:'이메일 또는 전화번호'})+
      prField('planNote',biz?'문의 내용':'남길 말','선택',{max:300,area:true,
        ph:biz?'인원 · 쓰려는 기능 · 데이터 연동 범위를 적어 주세요':'운영팀에 전할 말이 있으면 적어 주세요'});
    btns.innerHTML=(pending&&pending.plan===mode.k?'<button type="button" class="pill ghost" data-plan-cancel>신청 취소</button>':
        '<button type="button" class="pill ghost" data-plan-close>닫기</button>')+
      '<button type="submit" class="pill">신청하기</button>';
  }
  modal(true);
  setTimeout(()=>{ const f=body.querySelector('input,textarea'); if(f)f.focus(); },60);
}

function prFormBind(){
  const form=$('#planForm');
  if(!form||form.dataset.bound)return;
  form.dataset.bound='1';
  const err=$('#planFormErr');
  const fail=msg=>{ if(err){ err.textContent=msg; err.hidden=false; } };
  const run=async(btn,work,done)=>{
    if(btn.disabled)return;
    const label=btn.textContent;
    btn.disabled=true; btn.textContent='보내는 중…';
    if(err)err.hidden=true;
    try{ planApply(await work()); modal(false); prToast(done); }
    catch(e){ fail((e&&e.message)||'처리하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'); }
    finally{ btn.disabled=false; btn.textContent=label; }
  };
  form.addEventListener('click',e=>{
    if(e.target.closest('[data-plan-close]')){ modal(false); return; }
    const cancel=e.target.closest('[data-plan-cancel]');
    if(cancel)run(cancel,cancelPlanRequest,'신청을 취소했어요.');
  });
  form.addEventListener('submit',e=>{
    e.preventDefault();
    if(!PR_MODE)return;
    const btn=form.querySelector('[type="submit"]'); if(!btn)return;
    const mode=PR_MODE, label=PLAN_LABEL[mode.k]||mode.k;
    if(mode.kind==='downgrade')return run(btn,()=>planRequestSubmit({plan:'FREE'}),'프리 요금제로 바꿨어요.');
    if(mode.kind==='cancel')return run(btn,cancelPlanRequest,'신청을 취소했어요.');
    const val=id=>{ const el=$('#'+id); return el?el.value.trim():''; };
    const company=val('planCompany');
    if(mode.k==='BUSINESS'&&!company){ fail('팀(회사) 이름을 적어 주세요.'); return; }
    run(btn,()=>planRequestSubmit({plan:mode.k,company,contact:val('planContact'),note:val('planNote')}),
      label+' 요금제를 신청했어요. 승인되면 알림으로 알려 드려요.');
  });
}
