import { $, $$ } from '../../../core/static/js/dom.js';
import { cancelJobRequest, jobRequestSubmit, jobRequestsList, jobReviewDecide } from './account_api.js';
import { imageFileToDataURL } from '../../../home/static/js/chat_api.js';

/* ══════════════════════════════════════════════════════════════
   직업 인증 · 배지
   --------------------------------------------------------------
   가입 · 회원정보 수정에서 직업을 고르고, 증빙 서류를 올린다.
   서류는 관리자가 확인해 승인해야만 배지와 사이드바 직위에 반영된다.

   ★ 직업 선택은 선택 입력이다.
     관련 직종이어도 인증이 번거로워 Basic 으로 가입하는 사람이 있다.
     그래서 직업을 비워 두거나, 승인 전이면 모두 Basic 으로 보인다.

   ★ 2026-09-19 — 목업(브라우저 안 JOB_QUEUE)을 끊고 서버로 옮겼다 (backend/apps/api/job_views.py).
     신청은 서버에 남고, 서류는 S3 에 저장되며, 승인·반려는 운영(ADMIN) 계정만 한다.
     인증이 필요한 직업은 **승인 전까지 직업이 비어 있다**(Basic 으로 보인다).
   ══════════════════════════════════════════════════════════════ */

/* 드롭다운 목록 — fashion:true 는 주황 배지, Basic 은 검정 배지 */
export const JOBS=[
  {id:'MD',       label:'MD',       fashion:true,  doc:'재직증명서'},
  {id:'Buyer',    label:'Buyer',    fashion:true,  doc:'재직증명서'},
  {id:'Designer', label:'Designer', fashion:true,  doc:'재직증명서'},
  {id:'Stylist',  label:'Stylist',  fashion:true,  doc:'재직증명서'},
  {id:'Creator',  label:'Creator',  fashion:true,  doc:'운영 중인 SNS 계정 캡처'},
  {id:'Editor',   label:'Editor',   fashion:true,  doc:'운영 중인 SNS 계정 캡처'},
  {id:'Marketer', label:'Marketer', fashion:true,  doc:'재직증명서'},
  {id:'Platform', label:'Platform', fashion:true,  doc:'재직증명서'},
  {id:'Student',  label:'Student',  fashion:true,  doc:'입학증명서 또는 재학증명서'},
  {id:'Basic',    label:'Basic',    fashion:false, doc:''}
];
export const jobOf=id=>JOBS.find(j=>j.id===id)||null;
/* 서류가 필요한 직업인가 — Basic 은 확인할 것이 없으니 바로 반영한다 */
export const jobNeedsDoc=id=>{ const j=jobOf(id); return !!(j&&j.fashion) };

/* 목업 시연용 — 가입 직후엔 관리자 계정이 아니라 심사 화면을 열 사람이 없다.
   시연 중에도 승인 흐름을 보여 줄 수 있게 메뉴를 열어 둔다.
   실제 서비스에서는 false 로 두고 관리자 계정에서만 보이게 한다. */
export const JOB_REVIEW_DEMO=false;   /* 2026-09-19 — 운영 계정(ADMIN)이 생겨 시연용 개방을 닫는다 */


const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

/* ── 배지 ──
   승인된 직업만 주황으로 선다. 직업이 없거나 승인 전이면 검정 Basic. */
export function jobBadgeHTML(jobId){
  const j=jobOf(jobId)||jobOf('Basic');
  return '<span class="jobBadge'+(j.fashion?'':' basic')+'" title="'+esc(j.label)+'">'+esc(j.label)+'</span>';
}
/* 사용자 객체에서 지금 보여 줄 직업 — 관리자 계정은 직업 배지를 달지 않는다 */
export function jobShown(u){
  if(!u||u.role==='admin')return null;
  return u.job||'Basic';
}
/* 사이드바 하단 닉네임 아래 한 줄 */
export function jobPlanText(u){
  if(!u)return '';
  if(u.role==='admin')return u.plan||'ADMIN';
  const j=jobOf(u.job)||jobOf('Basic');
  const req=jobPendingOf(u);
  return j.label+(u.job==='Student'&&u.major?' · '+u.major:'')+(req?' · 인증 대기':'');
}
/* 심사 중인 내 신청 — 서버가 로그인 응답(job_request)으로 준다 */
export function jobPendingOf(u){
  const r=u&&u.jobRequest;
  return r&&r.status==='PENDING'?r:null;
}

/* ── 가입 · 수정 폼 한 줄 ──
   [파일 첨부 버튼] [직업 드롭다운] 순서. 직업에 맞춰 안내 문구가 바뀐다.
   prefix 는 'su'(가입) 또는 'edit'(회원정보 수정). */
export function jobFieldBind(prefix){
  const sel=$('#'+prefix+'Job'), file=$('#'+prefix+'JobFile'),
        btn=$('#'+prefix+'JobFileBtn'), msg=$('#'+prefix+'JobMsg'),
        majorWrap=$('#'+prefix+'MajorWrap');
  if(!sel||sel.dataset.bound)return;
  sel.dataset.bound='1';
  if(sel.options.length<=1){
    sel.insertAdjacentHTML('beforeend',JOBS.map(j=>
      '<option value="'+j.id+'">'+(j.id==='Student'?'Student (전공)':j.id==='Basic'?'Basic (일반 사용자)':j.label)+'</option>').join(''));
  }
  btn.addEventListener('click',()=>{ if(!btn.disabled)file.click() });
  file.addEventListener('change',()=>jobFieldPaint(prefix));
  sel.addEventListener('change',()=>{
    if(!jobNeedsDoc(sel.value)){ file.value='' }
    jobFieldPaint(prefix);
  });
  jobFieldPaint(prefix);
}
export function jobFieldPaint(prefix,note){
  const sel=$('#'+prefix+'Job'), file=$('#'+prefix+'JobFile'),
        btn=$('#'+prefix+'JobFileBtn'), msg=$('#'+prefix+'JobMsg'),
        majorWrap=$('#'+prefix+'MajorWrap');
  if(!sel)return;
  const j=jobOf(sel.value), f=file.files&&file.files[0];
  const need=jobNeedsDoc(sel.value);
  btn.disabled=!need;
  btn.classList.toggle('has',!!f);
  btn.querySelector('span').textContent=f?f.name:'서류 첨부';
  if(majorWrap)majorWrap.hidden=(sel.value!=='Student');
  if(!msg)return;
  let t='', cls='fieldMsg';
  if(note){ t=note }
  else if(!j){ t='선택 입력입니다. 비워 두면 Basic 으로 가입됩니다.' }
  else if(!need){ t='Basic 은 인증 없이 바로 적용됩니다.' }
  else if(f){ t='관리자 승인 후 '+j.label+' 배지가 달립니다.'; cls+=' ok' }
  else { t='첨부할 서류: '+j.doc+'\n관리자 승인 후 배지가 달립니다.' }
  msg.innerHTML=esc(t).replace(/\n/g,'<br>');
  msg.className=cls;
}
export function jobFieldReset(prefix,u){
  const sel=$('#'+prefix+'Job'), file=$('#'+prefix+'JobFile'), major=$('#'+prefix+'Major');
  if(!sel)return;
  sel.value=(u&&u.role!=='admin'&&u.job)||'';
  if(file)file.value='';
  if(major)major.value=(u&&u.major)||'';
  const req=u&&jobPendingOf(u);
  jobFieldPaint(prefix, req?(jobOf(req.job).label+' 인증을 심사 중입니다.\n새 서류를 올리면 이전 신청을 대신합니다.'):'');
}
/* 폼 값 검사 — 문제가 있으면 문구, 없으면 '' */
export function jobFieldCheck(prefix,u){
  const sel=$('#'+prefix+'Job'), file=$('#'+prefix+'JobFile');
  if(!sel)return '';
  const f=file.files&&file.files[0];
  if(!jobNeedsDoc(sel.value))return '';
  /* 이미 승인된 직업을 그대로 두는 것은 다시 인증할 필요가 없다 */
  if(u&&u.job===sel.value&&!f)return '';
  if(u&&jobPendingOf(u)&&jobPendingOf(u).job===sel.value&&!f)return '';
  if(!f)return '선택한 직업을 확인할 서류를 첨부하거나, 직업을 비워 두세요.';
  const pdf=f.type==='application/pdf';
  if(!pdf&&!/^image\/(jpeg|png|webp)$/.test(f.type))return '서류는 JPG · PNG · WebP 이미지나 PDF 로 올려 주세요.';
  if(pdf&&f.size>3*1024*1024)return 'PDF 서류는 3MB 이하로 올려 주세요. 사진으로 찍어 올려도 됩니다.';
  if(!pdf&&f.size>20*1024*1024)return '서류 이미지는 20MB 이하로 올려 주세요.';
  return '';
}
/* 폼 값을 서버에 반영한다 (가입 직후 · 회원정보 저장 직후에 부른다).
   · Basic · 비움 → 바로 반영(진행 중 신청 취소)
   · 인증 직업 + 서류 → 심사 신청. 승인 전까지 직업은 비어 있다.
   바뀐 게 없으면 서버를 부르지 않는다. 돌려주는 값: {changed, pending, job} */
export async function jobFieldApply(prefix,u){
  const sel=$('#'+prefix+'Job'), file=$('#'+prefix+'JobFile'), major=$('#'+prefix+'Major');
  if(!sel||!u||u.role==='admin')return {changed:false};
  const v=sel.value, f=file&&file.files&&file.files[0];
  const mj=major?major.value.trim().slice(0,20):'';
  const cur=u.job||'';
  if(!jobNeedsDoc(v)){
    const want=v==='Basic'?'':v;
    if(want===cur&&!jobPendingOf(u))return {changed:false};
    const d=await jobRequestSubmit({job:v||'Basic'});
    jobSync(u,d); return {changed:true, pending:false, job:u.job};
  }
  if(!f)return {changed:false};
  const pdf=f.type==='application/pdf';
  const docDataUrl=pdf?await readDataURL(f):await imageFileToDataURL(f);
  const d=await jobRequestSubmit({job:v, major:mj, docDataUrl, docName:f.name});
  jobSync(u,d); return {changed:true, pending:true, job:u.job};
}
const readDataURL=f=>new Promise((ok,no)=>{ const r=new FileReader();
  r.onload=()=>ok(String(r.result||'')); r.onerror=()=>no(new Error('서류 파일을 읽지 못했습니다.')); r.readAsDataURL(f); });
function jobSync(u,d){
  if(!d)return;
  u.job=d.job||''; if('major' in d)u.major=d.major||'';
  u.jobRequest=d.job_request||null;
  jobNotify();
}
export async function jobCancel(u){
  const d=await cancelJobRequest(); jobSync(u,d);
}
function jobNotify(){ try{ document.dispatchEvent(new CustomEvent('feedit:job')) }catch(e){} }

/* ── 관리자 심사 모달 (운영 계정만) ── */
let JR_ROWS=[], JR_FILTER='PENDING';
const JR_ST={PENDING:'대기',APPROVED:'승인',REJECTED:'반려'};
const jrDate=v=>{ const d=new Date(v); return isNaN(d)?'':(d.getMonth()+1)+'.'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0') };
export async function jobReviewRender(){
  const host=$('#jobReviewList'); if(!host)return;
  host.innerHTML='<p class="jrEmpty">신청 목록을 불러오는 중입니다.</p>';
  try{
    const d=await jobRequestsList(JR_FILTER);
    JR_ROWS=d.items||[];
  }catch(e){ host.innerHTML='<p class="jrEmpty">'+esc(e.message||'목록을 불러오지 못했습니다.')+'</p>'; return; }
  jrPaint();
}
function jrPaint(){
  const host=$('#jobReviewList'); if(!host)return;
  const tabs='<div class="jrTabs">'+[['PENDING','대기 중'],['ALL','전체']].map(([k,l])=>
    '<button type="button" data-jr-tab="'+k+'" class="'+(JR_FILTER===k?'on':'')+'">'+l+'</button>').join('')+'</div>';
  if(!JR_ROWS.length){
    host.innerHTML=tabs+'<p class="jrEmpty">'+(JR_FILTER==='PENDING'?'심사를 기다리는 신청이 없습니다.':'아직 들어온 인증 신청이 없습니다.')+'</p>';
    return;
  }
  host.innerHTML=tabs+JR_ROWS.map(r=>{
    const j=jobOf(r.job), img=r.doc_url&&/^image\//.test(r.doc_type);
    const st=String(r.status||'').toLowerCase();
    return '<div class="jrItem '+st+'">'+
      '<div class="jrThumb">'+(img?'<a href="'+esc(r.doc_url)+'" target="_blank" rel="noopener"><img src="'+esc(r.doc_url)+'" alt=""></a>':'<span>'+(r.doc_type==='application/pdf'?'PDF':'FILE')+'</span>')+'</div>'+
      '<div class="jrBody">'+
        '<div class="jrHead">'+jobBadgeHTML(r.job)+'<b>'+esc(r.nickname)+'</b><small>@'+esc(r.username)+'</small>'+
          '<em class="jrSt">'+(JR_ST[r.status]||r.status)+'</em></div>'+
        '<div class="jrMeta">'+esc(j?j.doc:'')+(r.major?' · 전공 '+esc(r.major):'')+' · '+jrDate(r.requested_at)+'<br>'+
          (r.doc_url?'<a href="'+esc(r.doc_url)+'" target="_blank" rel="noopener">'+esc(r.doc_name||'서류 보기')+'</a>':esc(r.doc_name||'서류 없음'))+
          (r.current_job?' · 현재 '+esc(r.current_job):'')+'</div>'+
      '</div>'+
      (r.status==='PENDING'
        ? '<div class="jrActs"><button type="button" class="pill ghost sm" data-jr-no="'+r.user_id+'">반려</button>'+
          '<button type="button" class="pill sm" data-jr-ok="'+r.user_id+'">승인</button></div>'
        : '')+
    '</div>';
  }).join('');
}
export function jobReviewBind(onDone){
  const host=$('#jobReviewList');
  if(!host||host.dataset.bound)return;
  host.dataset.bound='1';
  host.addEventListener('click',async e=>{
    const tab=e.target.closest('[data-jr-tab]');
    if(tab){ JR_FILTER=tab.dataset.jrTab; jobReviewRender(); return; }
    const ok=e.target.closest('[data-jr-ok]'), no=e.target.closest('[data-jr-no]');
    if(!ok&&!no)return;
    const btn=ok||no; btn.disabled=true;
    try{
      await jobReviewDecide({userId:+(ok?ok.dataset.jrOk:no.dataset.jrNo), approve:!!ok});
      await jobReviewRender();
      if(onDone)onDone(!!ok);
    }catch(err){ btn.disabled=false; if(onDone)onDone(null, err.message); }
  });
}
