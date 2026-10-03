import { $ } from '../../../core/static/js/dom.js';
import { feedbackList, saveFeedback } from '../../../account/static/js/account_api.js';
import { goView } from '../../../app_shell/static/js/router.js';

/* ══════════════════════════════════════════════════════════════
   살!말? 사후 피드백 (2026-09-19)
   --------------------------------------------------------------
   내가 올린 카드의 투표가 마감되면 글쓴이에게 결과를 묻는다.
     구매 여부 · 투표가 도움이 됐나 · 한 줄 후기   (★ 2026-09-19 만족도 1~5 는 뺐다)
   · 살말 페이지에 들어오면 아직 안 쓴 피드백이 있을 때 팝업을 띄운다(fbPromptOnce).
     '나중에'를 누르면 이번 접속(sessionStorage) 동안은 같은 카드로 다시 묻지 않는다.
   · 마이페이지 '살말 피드백' 패널이 작성 현황을 보여 준다(fbPanelRender).
   · 알림(팀원 작업)은 서버의 pending_feedback_cards() / GET /api/salmal/feedback 을 쓰면 된다.
   저장한 결과는 투표자들의 '적중'(연속 적중 · 여론 조력자 배지)에 쓰인다.
   ══════════════════════════════════════════════════════════════ */

const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SNOOZE_KEY='feedit.fb.snooze';
const PURCHASE=[['BOUGHT','구매했어요'],['SKIPPED','구매하지 않았어요'],['UNDECIDED','아직 고민 중이에요']];
/* 고른 답에 따라 후기 질문과 예시가 달라진다 */
const REVIEW_Q={BOUGHT:'구매하셨다면 후기를 들려주세요',SKIPPED:'구매하지 않은 이유를 들려주세요',UNDECIDED:'어떤 점이 고민인지 남겨 주세요'};
const REVIEW_PH={BOUGHT:'실물 색이 더 예뻐요, 한 치수 크게 추천해요',SKIPPED:'가격이 부담돼서 비슷한 걸로 샀어요',UNDECIDED:'핏은 좋은데 가격이 고민이에요'};

/* sessionStorage 를 못 쓰는 환경(사생활 보호 창 등)에서도 이번 화면 동안은 기억하도록 메모리에도 둔다 */
const SNOOZE_MEM=new Set();
function snoozed(){ let a=[]; try{ a=JSON.parse(sessionStorage.getItem(SNOOZE_KEY)||'[]') }catch(e){} return [...new Set([...a, ...SNOOZE_MEM])] }
function snooze(id){ SNOOZE_MEM.add(id); try{ sessionStorage.setItem(SNOOZE_KEY, JSON.stringify(snoozed())) }catch(e){} }

let fbState={loaded:false, pending:[], done:[], error:''};
export const fbPendingCount=()=>fbState.pending.length;

export async function fbLoad(){
  try{
    const d=await feedbackList();
    fbState={loaded:true, pending:d.pending||[], done:d.done||[], error:''};
  }catch(e){
    fbState={loaded:true, pending:[], done:[], error:e.message||'피드백 현황을 불러오지 못했습니다.'};
  }
  document.dispatchEvent(new CustomEvent('feedit:feedback'));
  return fbState;
}

function modalRoot(){
  let m=$('#fbModal');
  if(m)return m;
  document.body.insertAdjacentHTML('beforeend','<div class="fbModal" id="fbModal" role="dialog" aria-modal="true" aria-labelledby="fbTitle"><div class="fbCard"></div></div>');
  m=$('#fbModal');
  m.addEventListener('click',e=>{ if(e.target===m)fbClose(); });
  return m;
}
export function fbClose(){ const m=$('#fbModal'); if(m)m.classList.remove('on','in'); }

/* 카드 한 장의 피드백 창. row = {card_id, title, image_url, vote_summary, feedback}
   ★ 2026-09-19 디자인 개편 — 한 번에 한 질문씩 드러나는 단계형(구매 여부 → 도움 여부 → 후기).
     제목·질문을 h3/b 같은 맨 태그로 두지 않는다 — 전역 스타일·등장 모션에 먹혀 글자가 사라졌다. */
export function fbOpen(row, { onSaved, askLater=true } = {}){
  /* ★ 2026-09-20 — 이미 남긴 결과는 다시 열지 않는다(수정 기능 없음).
     결과는 투표자들의 적중·배지 판정에 쓰이므로 한 번 남기면 고정한다. */
  if(row&&row.feedback)return;
  const m=modalRoot(), card=m.querySelector('.fbCard');
  const fb=row.feedback||{};
  const st={purchase:fb.purchase||'', helpful:fb.helpful??null, comment:fb.comment||''};
  const vs=row.vote_summary||{};
  const buy=Number.isFinite(+vs.buy_pct)?Math.round(+vs.buy_pct):null;
  const paint=()=>{
    const helpOn=!!st.purchase;
    card.innerHTML=
      '<button type="button" class="fbX" data-fb="close" aria-label="닫기">'+
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>'+
      /* 위쪽 카드 정보를 누르면 그 살말 카드로 간다 */
      '<button type="button" class="fbTop" data-fb="card" title="이 카드 보러 가기">'+
        '<span class="fbThumb">'+(row.image_url?'<img src="'+esc(row.image_url)+'" alt="">':'')+'</span>'+
        '<span class="fbTopTx">'+
          '<span class="fbEyebrow">투표가 마감됐어요<em class="fbGo">카드 보기 ›</em></span>'+
          '<span class="fbTitle" id="fbTitle">'+esc(row.title||'내 카드')+'</span>'+
          (buy!=null
            ? '<span class="fbBar"><i style="width:'+buy+'%"></i></span>'+
              '<span class="fbBarTx"><em>살 '+buy+'%</em><em>말 '+(100-buy)+'%</em><em class="n">'+(vs.total||0)+'표</em></span>'
            : '')+
        '</span>'+
      '</button>'+
      '<div class="fbStep">'+
        '<span class="fbLabel">이 아이템, 구매하셨나요?</span>'+
        '<div class="fbSeg c3">'+PURCHASE.map(([k,l])=>'<button type="button" data-p="'+k+'" class="'+(st.purchase===k?'on':'')+'">'+l+'</button>').join('')+'</div>'+
      '</div>'+
      (helpOn
        ? '<div class="fbStep">'+
            '<span class="fbLabel">투표 결과가 결정에 도움이 되었나요?</span>'+
            '<div class="fbSeg c2">'+
              '<button type="button" data-h="1" class="'+(st.helpful===true?'on':'')+'">도움이 됐어요</button>'+
              '<button type="button" data-h="0" class="'+(st.helpful===false?'on':'')+'">크게 도움되진 않았어요</button></div>'+
          '</div>'+
          '<div class="fbStep">'+
            '<span class="fbLabel">'+REVIEW_Q[st.purchase]+' <small>선택</small></span>'+
            '<div class="fbInput"><input type="text" maxlength="100" placeholder="'+esc(REVIEW_PH[st.purchase])+'" value="'+esc(st.comment)+'">'+
              '<span class="fbCount">'+st.comment.length+'/100</span></div>'+
          '</div>'
        : '')+
      '<div class="fbErr" hidden></div>'+
      '<p class="fbNote">남긴 결과는 투표자들의 적중·배지에 반영돼 이후에 수정할 수 없어요.</p>'+
      '<div class="fbActs">'+
        (askLater?'<button type="button" class="fbLater" data-fb="later">다음에 할게요</button>':'<span></span>')+
        '<button type="button" class="fbSave" data-fb="save"'+(st.purchase?'':' disabled')+'>'+'후기 남기기</button>'+
      '</div>';
  };
  paint();
  card.oninput=e=>{
    if(!e.target.matches('input'))return;
    st.comment=e.target.value;
    const c=card.querySelector('.fbCount'); if(c)c.textContent=st.comment.length+'/100';
  };
  card.onclick=async e=>{
    const b=e.target.closest('button'); if(!b)return;
    if(b.dataset.p){ st.purchase=b.dataset.p; paint(); return; }
    if(b.dataset.h){ st.helpful=b.dataset.h==='1'; paint(); return; }
    if(b.dataset.fb==='close'){ fbClose(); return; }
    if(b.dataset.fb==='card'){ fbGoCard(row.card_id); return; }
    if(b.dataset.fb==='later'){ snooze(row.card_id); fbClose(); return; }
    if(b.dataset.fb==='save'){
      const err=card.querySelector('.fbErr');
      const fail=msg=>{ err.textContent=msg; err.hidden=false; };
      if(!st.purchase)return fail('구매하셨는지 먼저 골라 주세요.');
      b.disabled=true; b.textContent='저장 중…';
      try{
        const saved=await saveFeedback({cardId:row.card_id, purchase:st.purchase, satisfaction:null,
                            helpful:st.helpful, comment:st.comment});
        fbApplyLocal(row, saved&&saved.feedback);   /* 목록을 서버 응답 전에 바로 바꾼다 */
        fbClose();
        if(onSaved)onSaved();
        fbLoad();                                   /* 뒤에서 서버 값으로 한 번 더 맞춘다 */
      }catch(ex){ fail(ex.message||'저장하지 못했습니다.'); b.disabled=false; b.textContent='후기 남기기'; }
    }
  };
  m.classList.add('on');
  requestAnimationFrame(()=>m.classList.add('in'));
}
/* 피드백 창 위 카드 정보 → 그 살말 카드 상세 */
function fbGoCard(cardId){
  /* 살말로 들어가면 '안 쓴 피드백' 창이 저절로 다시 뜬다 — 이번 접속 동안 이 카드는 묻지 않게 둔다 */
  snooze(Number(cardId));
  fbClose();
  goView('salmal');
  const t0=Date.now();
  (function tick(){
    if(window.smOpenCard){ window.smOpenCard(Number(cardId)); return }
    if(Date.now()-t0<4000)setTimeout(tick,80);
  })();
}
/* ★ 2026-09-19 — 마감 알림을 누르면 살말 화면으로 가지 않고 피드백 창만 띄운다.
   내 카드 목록(작성 전·완료)에 없으면(남의 카드·아직 진행 중) 그 카드로 보낸다. */
window.feeditOpenFeedback=async cardId=>{
  const id=Number(cardId);
  const s=await fbLoad();
  const row=[...s.pending,...s.done].find(r=>Number(r.card_id)===id);
  /* 목록에 없거나 이미 남긴 카드면 창 대신 그 카드(글쓴이의 결과가 보인다)로 보낸다 */
  if(!row||row.feedback){ fbGoCard(id); return }
  fbOpen(row,{askLater:false, onSaved:()=>window.smReloadVotes&&window.smReloadVotes()});
};
/* 저장 직후 — 작성 전 → 작성 완료로 바로 옮기고 화면에 알린다 */
function fbApplyLocal(row, feedback){
  if(!feedback)return;
  const id=row.card_id;
  const base=[...fbState.pending,...fbState.done].find(r=>r.card_id===id)||row;
  const done={...base, feedback};
  fbState={...fbState, loaded:true,
    pending:fbState.pending.filter(r=>r.card_id!==id),
    done:[done,...fbState.done.filter(r=>r.card_id!==id)]};
  document.dispatchEvent(new CustomEvent('feedit:feedback'));
}

/* 살말 페이지 진입 시 — 아직 안 쓴 피드백이 있으면 하나만 묻는다 */
export async function fbPromptOnce(){
  const s=await fbLoad();
  const skip=new Set(snoozed());
  const next=s.pending.find(r=>!skip.has(r.card_id));
  if(next)fbOpen(next,{askLater:true, onSaved:()=>window.smReloadVotes&&window.smReloadVotes()});
}

/* 마이페이지 패널 */
export function fbPanelRender(host){
  if(!host)return;
  const s=fbState;
  if(!s.loaded){ host.innerHTML='<div class="fbEmpty">불러오는 중입니다.</div>'; return; }
  if(s.error){ host.innerHTML='<div class="fbEmpty">'+esc(s.error)+'</div>'; return; }
  if(!s.pending.length&&!s.done.length){
    host.innerHTML='<div class="fbEmpty">아직 마감된 내 카드가 없습니다.<br>살!말?에 고민을 올리면 마감 뒤 여기서 결과를 남길 수 있어요.</div>';
    return;
  }
  const row=(r,pending)=>{
    const f=r.feedback;
    const sub=pending?'작성 전':(f.purchase_label+
      (f.helpful===true?' · 투표 도움됨':f.helpful===false?' · 투표 도움 안 됨':''));
    return '<div class="fbRow'+(pending?' pending':'')+'">'+
      (r.image_url?'<img src="'+esc(r.image_url)+'" alt="">':'<i></i>')+
      '<div class="fbRowT"><b>'+esc(r.title)+'</b><span>'+esc(sub)+'</span>'+
        (f&&f.comment?'<q>'+esc(f.comment)+'</q>':'')+'</div>'+
      (pending?'<button type="button" class="pill" data-fb-open="'+r.card_id+'">작성하기</button>':'')+'</div>';
  };
  host.innerHTML=
    '<div class="fbSum"><span>작성 전 <b>'+s.pending.length+'</b></span><span>작성 완료 <b>'+s.done.length+'</b></span></div>'+
    s.pending.map(r=>row(r,true)).join('')+s.done.map(r=>row(r,false)).join('');
  host.onclick=e=>{
    const b=e.target.closest('[data-fb-open]'); if(!b)return;
    const id=+b.dataset.fbOpen;
    const r=s.pending.find(x=>x.card_id===id);
    if(r)fbOpen(r,{askLater:false});
  };
}
/* 저장·재조회가 끝나면 마이페이지 패널이 떠 있을 때 바로 다시 그린다 (새로고침 없이) */
document.addEventListener('feedit:feedback',()=>{ const h=document.getElementById('fbPanelBody'); if(h)fbPanelRender(h); });

export function fbReset(){ SNOOZE_MEM.clear(); fbState={loaded:false,pending:[],done:[],error:''}; }
