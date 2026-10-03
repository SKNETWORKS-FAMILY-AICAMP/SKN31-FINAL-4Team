import { HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';
import { AUTH, ME, requireAuth } from '../../../account/static/js/profile.js';
import { RANK_ON, rkClamp, rkLevelOf, rkRingHTML } from '../../../account/static/js/rank.js';
import { jobBadgeHTML, jobShown } from '../../../account/static/js/job.js';
import { smBarFill, smBarLabels } from '../../../trend/static/js/discount_resale.js';
import { STYLES } from '../../../home/static/js/chat.js';
import { fbOpen, fbPromptOnce } from './feedback.js';
import { imageFileToDataURL } from '../../../home/static/js/chat_api.js';
import { createVoteCard, deleteVoteCard, deleteVoteComment, reportVoteTarget, saveVote, saveVoteComment } from '../../../account/static/js/account_api.js';

/* ══════════════ 살!말? (feedit-salmal_2 이식) ══════════════
   이름 충돌을 막기 위해 통째로 자기 범위 안에서 돌린다. */
export function salmalBoot(){

/* 카드·투표·댓글의 단일 원본은 Django API와 PostgreSQL이다. */
let VOTES=[];
let BRAND_LIST=[];
function cardFromApi(card,i){
  const summary=card.vote_summary||{};
  const similar=card.similar_user_summary||summary;
  const source=card.source||{};
  return {
    id:card.id, cardKey:String(card.id), t:card.title,
    b:card.brand||'브랜드 미확인', p:card.price,
    base:summary.buy_pct??50, baseSal:summary.buy||0, baseMal:summary.pass||0,
    a:summary.buy_pct??50, votes:summary.total||0,
    hours:card.closed?0:card.hours_remaining,
    createdAt:Date.parse(card.created_at)||0,
    closesAt:Date.parse(card.closes_at)||Number.POSITIVE_INFINITY,
    /* 나와 비슷한 사용자들 — 표본이 0명이면 has_sample:false 이고 비율은 null 이다.
       예전에는 이때 전체 투표 비율이 그대로 내려와 "비슷한 사용자"라는 말이
       거짓이 됐다. 이제 없으면 없다고 쓴다. */
    simHas:Boolean(similar.has_sample),
    simPct:similar.has_sample?similar.buy_pct:null,
    simUsers:similar.sample_users||0,
    simReason:similar.reason||'',
    taste:similar.has_sample?similar.buy_pct:(summary.buy_pct??50),
    tasteMatch:card.taste_match_count||0,
    tasteTags:Array.isArray(card.taste_match_tags)?card.taste_match_tags:[],
    tone:['#302d2b','#6e6660'], imgURL:card.image_url,
    /* 판매처 구매 평점 — 없으면 null. 예전 '구매자 만족도'(투표율 계산값)를 대신한다 (2026-09-19) */
    buyer:card.buyer_rating||null,
    /* 사후 피드백 — 마감 뒤 글쓴이가 남긴 결과. 내 카드인데 아직 안 썼으면 feedbackPending */
    feedback:card.feedback||null, feedbackPending:Boolean(card.feedback_pending),
    youtubeId:source.video_id||'', upload_date:source.upload_date||'',
    productSourceId:card.product_source_id,
    closed:Boolean(card.closed), st:Array.isArray(card.style_tags)?card.style_tags:[],
    mine:Boolean(card.mine),
    deletable:Boolean(card.deletable),
    authorNote:{name:card.author?.name||'FEEDiT 사용자',text:card.author?.story||card.description||''},
    voted:card.my_choice==='BUY'?0:card.my_choice==='PASS'?1:null,
    comments:(card.comments||[]).map(comment=>({
      id:comment.id, name:comment.name,
      tag:comment.choice==='BUY'?0:comment.choice==='PASS'?1:null,
      /* 작성자 레벨 — 서버가 경험치 사본(xp)을 주고 레벨은 rank.js 구간표로 센다.
         운영 계정(xp_fixed)은 최고 레벨. 예전 comment.rank 는 아이콘 색 번호였다 (2026-09-25) */
      rk:rkLevelOf(comment.xp, comment.xp_fixed), job:comment.job, text:comment.text, time:comment.time,
      me:Boolean(comment.mine),
      /* 운영 계정은 남의 댓글도 지울 수 있다 — 서버가 판단해 준다 */
      deletable:Boolean(comment.deletable??comment.mine)
    })),
    seq:i
  };
}
let ACTIVITY=null;   /* {hours, participants} — 최근 N시간 실제 참여자 수 */
/* ★ 2026-09-19 — 로그아웃·로그인을 빠르게 하면 두 번의 조회가 겹치는데, 늦게 도착한 '로그아웃 상태'
   응답이 로그인 뒤 목록을 덮어써 내 카드인데 '신고하기'만 보였다. 가장 마지막 요청만 반영한다.
   no-store — 브라우저가 다른 계정으로 받은 응답을 재사용하지 않게 한다. */
let LOAD_SEQ=0;
async function loadVotes(){
  const seq=++LOAD_SEQ;
  const groups=await Promise.all(['latest','result'].map(tab=>
    fetch('/api/salmal/cards?tab='+tab,{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}})
      .then(async response=>{
        /* ★ 2026-09-21 — 백엔드가 500 을 내면 장고가 HTML 오류 쪽을 돌려준다.
           그대로 response.json() 하면 "Unexpected token '<'" 같은 자바스크립트 말이
           화면에 그대로 찍힌다. 먼저 글로 받아서 JSON 일 때만 푼다. */
        const raw=await response.text();
        let payload=null;
        try{ payload=JSON.parse(raw); }catch(_){
          throw new Error('살말 서버가 응답을 주지 못했습니다 ('+response.status+'). 잠시 뒤 다시 시도해 주세요.');
        }
        if(!response.ok||payload.status!=='ok') throw new Error(payload.reason||'살말 데이터를 불러오지 못했습니다.');
        if(tab==='latest'&&payload.data.activity) ACTIVITY=payload.data.activity;
        return payload.data.items||[];
      })));
  if(seq!==LOAD_SEQ) return false;   /* 더 새 요청이 있다 — 이 응답은 버린다 */
  paintActivity();
  const unique=new Map([...groups[0],...groups[1]].map(card=>[card.id,card]));
  VOTES=[...unique.values()].map(cardFromApi);
  BRAND_LIST=[...new Set(VOTES.map(v=>v.b))].sort();
  return true;
}

/* 페이지를 계속 열어 둔 상태에서도 마감 시간이 지나면 즉시 종료 영역으로 옮긴다. */
function syncExpiredCards(){
  const now=Date.now();
  let changed=false;
  VOTES.forEach(v=>{
    if(v.closed||!Number.isFinite(v.closesAt))return;
    const remaining=v.closesAt-now;
    if(remaining<=0){
      v.closed=true;
      v.hours=0;
      changed=true;
      return;
    }
    const hours=Math.max(1,Math.ceil(remaining/3600000));
    if(v.hours!==hours){ v.hours=hours; changed=true; }
  });
  if(changed){
    if(modalState.i!==null) updateModalVote();
    renderGrid();
    renderClosedGrid();
  }
}

const $=(s,el=document)=>el.querySelector(s);
const $$=(s,el=document)=>[...el.querySelectorAll(s)];
const fmtWon=n=>Number.isFinite(n)?n.toLocaleString('ko-KR')+'원':'가격 정보 없음';
const fmtHours=h=>Number.isFinite(h)?(h>=24?Math.round(h/24)+'일':h+'시간'):'기간 정보 없음';
const fmtNum=n=>n.toLocaleString('ko-KR');
/* 등록할 때 고른 스타일 이름 — 고르지 않았으면 빈 문자열 */
const styleNameOf=v=>(v&&Array.isArray(v.st)?v.st:[])
  .map(id=>STYLES.find(x=>x.id===id)?.n||id).find(Boolean)||'';
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
/* 비슷한 사용자들의 살 비율. 표본이 없으면 null — 숫자를 만들어 내지 않는다. */
const simA=v=>v.simHas?v.simPct:null;
/* 새로 단 댓글의 임시 id — 서버 id 가 오면 그걸 쓴다 */
let COMMENT_UID=1;
const nextCommentId=()=>COMMENT_UID++;


function orderFor(tab){
  let idx=VOTES.map((_,i)=>i).filter(i=>!VOTES[i].deleted);
  /* ★ 2026-09-19 — 로그인 전에는 내가 올린 카드를 다른 탭에서 빼 둔다.
     인기순 · 최신순 · 마감임박은 남의 고민을 보는 자리이므로 로그인과는 상관이 없다. */
  if(!AUTH.in&&tab!=='mine') idx=idx.filter(i=>!VOTES[i].mine);
  /* ★ 2026-09-19 — '내 카드': 내가 올린 글만. 마감된 것도 내 글이므로 같이 보여 준다. */
  if(tab==='mine'){
    return idx.filter(i=>VOTES[i].mine)
      .sort((a,b)=>VOTES[b].createdAt-VOTES[a].createdAt||VOTES[b].seq-VOTES[a].seq);
  }
  if(tab==='result'){
    /* 결과보기: 마감된(투표 종료) 게시글만 */
    return idx.filter(i=>VOTES[i].closed).sort((a,b)=>VOTES[b].votes-VOTES[a].votes);
  }
  /* 그 외 탭은 진행 중인 게시글만 노출 */
  idx=idx.filter(i=>!VOTES[i].closed);
  if(tab==='closing'){
    /* 마감임박: 진행 중인 게시글을 실제 마감 시각이 가까운 순서로 */
    return idx.sort((a,b)=>VOTES[a].closesAt-VOTES[b].closesAt||VOTES[b].createdAt-VOTES[a].createdAt);
  }
  if(tab==='popular'){
    /* 인기순: 참여수(투표수) 많은 순 */
    return idx.sort((a,b)=>VOTES[b].votes-VOTES[a].votes);
  }
  if(tab==='taste'){
    /* 내 취향: 취향 매칭도 높은 순 */
    const matched=idx.filter(i=>VOTES[i].tasteMatch>0);
    return (matched.length?matched:idx).sort((a,b)=>
      VOTES[b].tasteMatch-VOTES[a].tasteMatch||VOTES[b].taste-VOTES[a].taste);
  }
  /* 최신순: 가장 최근에 등록된 게시글 먼저 */
  return idx.sort((a,b)=>VOTES[b].createdAt-VOTES[a].createdAt||VOTES[b].seq-VOTES[a].seq);
}

function plateStyle(v){
  return v.imgURL
    ? `background-image:url('${v.imgURL}');background-size:cover;background-position:center`
    : `background:linear-gradient(150deg,${v.tone[0]},${v.tone[1]})`;
}

function cardHTML(i){
  const v=VOTES[i];
  const buyOn=v.voted===0, noOn=v.voted===1;
  const votesShown=v.votes;
  const capText=v.closed
    ? `${fmtNum(votesShown)}표 · 투표 종료`
    : `${fmtNum(votesShown)}표 · 마감까지 ${fmtHours(v.hours)}${v.voted!==null?' · <em>투표함</em>':''}`;
  const btnsHTML=v.closed
    ? `<div class="closedNote">투표가 종료됐어요</div>`
    : `<div class="smBtns">
        <button class="buy${buyOn?' picked':''}" data-vote="0">살!</button>
        <button class="${noOn?'picked':''}" data-vote="1">말?</button>
      </div>`;
  return `
  <div class="voteCard" data-i="${i}" data-card-id="${v.id}">
    <div class="fig">
      <div class="plate" style="${plateStyle(v)}"></div>
      <div class="vig"></div>
      <span class="pricep">${fmtWon(v.p)}</span>
      <span class="tagp"><b>${escapeHtml(v.b)}</b></span>
    </div>
    <div class="body">
      <h4>${escapeHtml(v.t)}</h4>
      <div class="cap">${capText}</div>
      <div class="smBar"><i class="buy" data-w="${v.a}" style="width:${v.a}%"><span>살 ${v.a}%</span></i><i class="no" data-w="${100-v.a}" style="width:${100-v.a}%"><span>${100-v.a}% 말</span></i></div>
      ${btnsHTML}
    </div>
  </div>`;
}

const PAGE_SIZE=8;
const state={tab:'popular', page:1};

function renderGrid(){
  /* ★ '내 취향'은 로그인해야 고를 수 있다.
       예전에는 비로그인일 때 tasteMatch 가 전부 0 이라 orderFor 의
       `matched.length?matched:idx` 가 **전체 카드로 떨어져**, 로그아웃 상태에서도
       내 취향 추천이 있는 것처럼 보였다. 맞지 않는 것을 맞는다고 쓰지 않는다. */
  const gate=$('#smGate'), grid0=$('#voteGrid'), pager0=$('#pager');
  /* ★ 2026-09-19 — '내 카드'도 내가 누구인지 알아야 고를 수 있다.
     로그인 전에는 카드 대신 안내와 로그인 · 회원가입 버튼을 둔다. */
  const locked=(state.tab==='taste'||state.tab==='mine')&&!AUTH.in;
  if(gate){
    gate.hidden=!locked;
    if(locked){
      const t=$('#smGateTitle'), d=$('#smGateDesc');
      if(t)t.textContent=state.tab==='mine'
        ? '내가 올린 카드는 로그인해야 볼 수 있어요.'
        : '내 취향 추천은 로그인해야 볼 수 있어요.';
      if(d)d.textContent=state.tab==='mine'
        ? '로그인하면 내가 올린 살!말? 글과 그 결과를 한자리에서 볼 수 있습니다.'
        : '즐겨입는 스타일과 체형을 알아야 나와 맞는 고민을 골라 드릴 수 있습니다.';
    }
  }
  if(locked){
    if(grid0)grid0.innerHTML='';
    if(pager0)pager0.innerHTML='';
    return;
  }
  const order=orderFor(state.tab);
  const totalPages=Math.max(1,Math.ceil(order.length/PAGE_SIZE));
  if(state.page>totalPages) state.page=totalPages;
  const start=(state.page-1)*PAGE_SIZE;
  const pageItems=order.slice(start,start+PAGE_SIZE);

  const grid=$('#voteGrid');
  if(state.tab==='mine'&&!order.length){
    grid.innerHTML='<div class="smDataState">아직 올린 카드가 없습니다. ‘＋ 살까말까 물어보기’로 첫 글을 올려 보세요.</div>';
    renderPager(1);
    return;
  }
  grid.innerHTML=pageItems.map(cardHTML).join('');
  attachCardHandlers(grid);
  smCardsIn(grid);
  renderPager(totalPages);
}

/* ══════════════════════════════════════════════════════════
   살!말? 모션
   ----------------------------------------------------------
   카드가 한 장씩 올라오고, 그 뒤를 살/말 막대가 따라 찬다.
   투표하면 막대가 스프링으로 밀려가고 누른 버튼이 한 번 눌린다.
   마감이 임박한 카드만 시간 표시가 조용히 뛴다 — 나머진 가만히 둔다.
   ══════════════════════════════════════════════════════════ */
function smCardsIn(root){
  const cards=$$('.voteCard',root||document);
  if(!cards.length)return;
  const bars=$$('.smBar i',root||document);
  if(!HAS_A){
    cards.forEach(c=>c.classList.add('in'));
    smBarFill(bars);
    smUrgent(root); return;
  }
  aUtils.remove(cards);
  cards.forEach(c=>{ c.classList.add('in'); c.style.transform=''; c.style.opacity='' });
  aUtils.set(cards,{opacity:0,translateY:16,scale:.985});
  aAnimate(cards,{opacity:[0,1],translateY:[16,0],scale:[.985,1],
    duration:760,delay:aStagger(52),ease:aSpring({stiffness:88,damping:16}),
    /* 끝나면 인라인 transform 을 지운다 — 남겨두면 :hover 의 들어올림이 먹히지 않는다 */
    onComplete:()=>cards.forEach(c=>{c.style.transform='';c.style.opacity=''})});
  smBarFill(bars,{start:180,step:26});
  smUrgent(root);
}
/* 마감 6시간 안쪽인 카드에만 표시를 남긴다 */
function smUrgent(root){
  $$('.voteCard',root||document).forEach(c=>{
    const v=VOTES[+c.dataset.i];
    c.classList.toggle('urgent', !!v && !v.closed && v.hours>0 && v.hours<=6);
  });
}
/* 투표 순간 — 막대가 밀려가고 누른 버튼이 한 번 들어갔다 나온다 */
function smVoteBeat(card,side){
  if(!HAS_A||!card)return;
  const btn=$$('.smBtns button',card)[side];
  if(btn)aAnimate(btn,{keyframes:[{scale:.94,duration:120,ease:'out(2)'},
    {scale:1,duration:480,ease:aSpring({stiffness:170,damping:11})}]});
  const fig=$('.fig',card);
  if(fig)aAnimate(fig,{keyframes:[{scale:1.015,duration:180,ease:'out(2)'},
    {scale:1,duration:560,ease:aSpring({stiffness:90,damping:14})}]});
}

function renderPager(totalPages){
  const pager=$('#pager');
  if(totalPages<=1){ pager.innerHTML=''; return; }
  let nums='';
  for(let p=1;p<=totalPages;p++){
    nums+=`<button data-page="${p}" class="${p===state.page?'on':''}">${p}</button>`;
  }
  pager.innerHTML=`
    <button class="pagerBtn" id="pagerPrev" ${state.page===1?'disabled':''} aria-label="이전 페이지">←</button>
    <div class="pagerNums">${nums}</div>
    <button class="pagerBtn" id="pagerNext" ${state.page===totalPages?'disabled':''} aria-label="다음 페이지">→</button>`;
  $('#pagerPrev').onclick=()=>{ state.page--; renderGrid(); scrollToGrid(); };
  $('#pagerNext').onclick=()=>{ state.page++; renderGrid(); scrollToGrid(); };
  $$('.pagerNums button',pager).forEach(btn=>{
    btn.onclick=()=>{ state.page=+btn.dataset.page; renderGrid(); scrollToGrid(); };
  });
}

function scrollToGrid(){
  $('.voteSection').scrollIntoView({behavior:'smooth',block:'start'});
}

/* ── 마감된 투표 — 4개씩, 점 3개를 눌러 직접 이동하는 정적 섹션 ── */
const CLOSED_PAGE_SIZE=4;
const closedState={page:0};

function closedItems(){
  return VOTES.map((_,i)=>i).filter(i=>VOTES[i].closed&&!VOTES[i].deleted);
}

function renderClosedGrid(){
  const items=closedItems();
  const totalPages=Math.max(1,Math.ceil(items.length/CLOSED_PAGE_SIZE));
  if(closedState.page>=totalPages) closedState.page=0;
  const start=closedState.page*CLOSED_PAGE_SIZE;
  const pageItems=items.slice(start,start+CLOSED_PAGE_SIZE);

  const grid=$('#closedGrid');
  grid.innerHTML=pageItems.map(cardHTML).join('');
  attachCardHandlers(grid);
  requestAnimationFrame(()=>{
    $$('.voteCard',grid).forEach((c,k)=>setTimeout(()=>c.classList.add('in'),k*55));
  });
  renderClosedDots(totalPages);
}

function renderClosedDots(totalPages){
  const dots=$('#closedDots');
  if(totalPages<=1){ dots.innerHTML=''; return; }
  dots.innerHTML=Array.from({length:totalPages},(_,p)=>
    `<span class="dot${p===closedState.page?' on':''}" data-page="${p}"></span>`).join('');
  $$('.dot',dots).forEach(d=>{
    d.addEventListener('click',()=>{
      closedState.page=+d.dataset.page;
      renderClosedGrid();
    });
  });
}

function updateCard(i){
  const card=$(`.voteCard[data-i="${i}"]`);
  if(!card)return;
  const v=VOTES[i];
  const bar=$('.smBar',card), buyBar=$('.buy',bar), noBar=$('.no',bar);
  buyBar.innerHTML='<span>살 '+v.a+'%</span>'; noBar.innerHTML='<span>'+(100-v.a)+'% 말</span>';
  buyBar.dataset.w=v.a; noBar.dataset.w=100-v.a;   /* 다시 그릴 때의 목표값도 같이 옮긴다 */
  buyBar.classList.remove('tight'); noBar.classList.remove('tight');
  if(HAS_A){
    aUtils.remove(buyBar);
    aAnimate(buyBar,{width:v.a+'%',duration:820,ease:aSpring({stiffness:104,damping:15}),
      onComplete:()=>smBarLabels([buyBar,noBar])});
  }else{ buyBar.style.width=v.a+'%'; smBarLabels([buyBar,noBar]) }
  noBar.style.removeProperty('width');
  $$('.smBtns button',card).forEach(btn=>{
    const side=+btn.dataset.vote;
    btn.classList.toggle('picked', v.voted===side);
  });
  const votesShown=v.votes;
  $('.cap',card).innerHTML=`${fmtNum(votesShown)}표 · 마감까지 ${fmtHours(v.hours)}${v.voted!==null?' · <em>투표함</em>':''}`;
}

function castVote(i,side){
  if(!requireAuth())return;
  const v=VOTES[i];
  const before=v.voted;
  const after=before===side?null:side;
  if(before===0)v.baseSal=Math.max(0,v.baseSal-1);
  if(before===1)v.baseMal=Math.max(0,v.baseMal-1);
  if(after===0)v.baseSal++;
  if(after===1)v.baseMal++;
  v.voted=after;
  v.votes=v.baseSal+v.baseMal;
  v.a=v.votes?Math.round(v.baseSal*100/v.votes):50;
  updateCard(i);
  smVoteBeat($(`.voteCard[data-i="${i}"]`), side);
  saveVote({ cardKey:v.cardKey, title:v.t, brand:v.b,
    style:styleNameOf(v), choice:v.voted===null?null:(v.voted===0?'BUY':'PASS') })
    .then(r=>{ if(r&&Number.isFinite(+r.vote_count))ME.votes=+r.vote_count; });
}

function attachCardHandlers(root=document){
  $$('.voteCard',root).forEach(card=>{
    const i=+card.dataset.i;
    $$('.smBtns button',card).forEach(btn=>{
      btn.onclick=(e)=>{ e.stopPropagation(); castVote(i,+btn.dataset.vote); };
    });
    card.addEventListener('click',(e)=>{
      if(e.target.closest('.smBtns'))return;
      openModal(i);
    });
  });
}

/* ============================================================
   신고 / 삭제 컨텍스트 메뉴 — 카드와 댓글에서 공용으로 사용
   ============================================================ */
let ctxTarget=null; /* {type:'card', i} | {type:'comment', i, commentId} */

function openCtxMenu(triggerEl, target){
  ctxTarget=target;
  const menu=$('#ctxMenu');
  const deleteButton=$('[data-action="delete"]',menu);
  const reportButton=$('[data-action="report"]',menu);
  if(target.type==='card'){
    const mine=Boolean(VOTES[target.i]?.mine);
    /* 운영 계정은 어떤 카드든 지울 수 있다 — 서버가 다시 확인한다 */
    deleteButton.hidden=!(VOTES[target.i]?.deletable||ME.role==='admin');
    reportButton.hidden=mine;
  }else{
    const comment=VOTES[target.i]?.comments.find(item=>item.id===target.commentId);
    const mine=Boolean(comment?.me);
    deleteButton.hidden=!(comment?.deletable||ME.role==='admin');
    reportButton.hidden=mine;
  }
  const r=triggerEl.getBoundingClientRect();
  const mw=menu.offsetWidth||150, mh=menu.offsetHeight||90;
  const vw=window.innerWidth, vh=window.innerHeight, pad=10;
  let left=r.right-mw, top=r.bottom+6;
  if(left<pad) left=pad;
  if(left+mw>vw-pad) left=vw-pad-mw;
  if(top+mh>vh-pad) top=r.top-mh-6;
  menu.style.left=left+'px';
  menu.style.top=top+'px';
  menu.classList.add('on');
}
function closeCtxMenu(){
  $('#ctxMenu').classList.remove('on');
  ctxTarget=null;
}
async function deleteCard(i){
  if(!(VOTES[i]?.deletable||ME.role==='admin')){ showToast('직접 등록한 내 카드만 삭제할 수 있어요.'); return; }
  try{
    const gone=VOTES[i].id;
    await deleteVoteCard(gone);
    VOTES[i].deleted=true;
    if(modalState.i===i) closeModal();
    /* ★ 카드가 어느 자리에 그려져 있었는지 따지지 않는다 — 두 격자를 모두 다시 그리고,
       혹시 남아 있는 DOM 은 바로 걷어낸다(다시 그리기 전 잔상 방지). */
    $$('.voteCard[data-card-id="'+gone+'"]').forEach(el=>el.remove());
    renderGrid();
    renderClosedGrid();
    showToast('게시글이 삭제됐어요.');
  }catch(error){ showToast(error.message||'카드를 삭제하지 못했습니다.'); }
}
async function deleteComment(i,commentId){
  if(i===null)return;
  const comment=VOTES[i]?.comments.find(c=>c.id===commentId);
  if(!(comment?.deletable||ME.role==='admin')){ showToast('내가 작성한 댓글만 삭제할 수 있어요.'); return; }
  try{
    await deleteVoteComment(commentId);
    VOTES[i].comments=VOTES[i].comments.filter(c=>c.id!==commentId);
    if(modalState.i===i)renderComments();
    showToast('댓글이 삭제됐어요.');
  }catch(error){ showToast(error.message||'댓글을 삭제하지 못했습니다.'); }
}
$$('#ctxMenu button').forEach(btn=>{
  btn.addEventListener('click',async()=>{
    const action=btn.dataset.action;
    const target=ctxTarget;
    closeCtxMenu();
    if(!target)return;
    if(action==='report'){
      const targetType=target.type==='card'?'CARD':'COMMENT';
      const targetId=target.type==='card'?VOTES[target.i]?.id:target.commentId;
      try{
        const saved=await reportVoteTarget({targetType,targetId});
        showToast(saved?.created
          ? (targetType==='CARD'?'카드 신고가 접수됐어요.':'댓글 신고가 접수됐어요.')
          : '이미 접수한 신고예요.');
      }catch(error){ showToast(error.message||'신고를 접수하지 못했습니다.'); }
      return;
    }
    if(action==='delete'){
      if(target.type==='card') deleteCard(target.i);
      else deleteComment(target.i,target.commentId);
    }
  });
});
document.addEventListener('click',e=>{
  const menu=$('#ctxMenu');
  if(!menu.classList.contains('on'))return;
  if(e.target.closest('#ctxMenu')||e.target.closest('.cardMenuBtn')||e.target.closest('.cMenuBtn'))return;
  closeCtxMenu();
});
window.addEventListener('resize',()=>{ if($('#ctxMenu').classList.contains('on')) closeCtxMenu(); });
$('#commentsList').addEventListener('click',e=>{
  const btn=e.target.closest('.cMenuBtn');
  if(!btn)return;
  e.stopPropagation();
  const commentId=+btn.dataset.commentId;
  const already=$('#ctxMenu').classList.contains('on') && ctxTarget && ctxTarget.type==='comment' && ctxTarget.commentId===commentId;
  already ? closeCtxMenu() : openCtxMenu(btn,{type:'comment', i:modalState.i, commentId});
});
$('#modalMenuBtn').addEventListener('click',e=>{
  e.stopPropagation();
  if(modalState.i===null)return;
  const i=modalState.i;
  const btn=e.currentTarget;
  const already=$('#ctxMenu').classList.contains('on') && ctxTarget && ctxTarget.type==='card' && ctxTarget.i===i;
  already ? closeCtxMenu() : openCtxMenu(btn,{type:'card', i});
});

/* ============================================================
   상세 모달 — 이미지 · 투표현황(전체/유사세그먼트) · 댓글 · AI 리포트
   ============================================================ */
const modalState={i:null,version:0};
const pendingCommentCards=new Set();

function escapeHtml(s){
  return s.replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function resetCommentComposer(card=null){
  const input=$('#commentInput');
  const sendButton=$('#commentSend');
  const isClosed=Boolean(card?.closed);
  const isPending=Boolean(card&&pendingCommentCards.has(card.id));
  input.value='';
  input.disabled=isClosed||isPending;
  sendButton.disabled=isClosed||isPending;
  input.placeholder=isClosed?'마감된 투표에는 댓글을 달 수 없어요':'댓글을 남겨보세요';
}

function openModal(i){
  if(!requireAuth())return;
  modalState.version+=1;
  modalState.i=i;
  const v=VOTES[i];
  resetCommentComposer(v);
  const plate=$('#modalPlate');
  if(v.imgURL){
    plate.style.background='';
    plate.style.backgroundImage=`url('${v.imgURL}')`;
    plate.style.backgroundSize='cover';
    plate.style.backgroundPosition='center';
  }else{
    plate.style.backgroundImage='';
    plate.style.background=`linear-gradient(150deg,${v.tone[0]},${v.tone[1]})`;
  }
  $('#modalTitle').textContent=v.t;
  $('#modalBrand').textContent=v.b;
  $('#modalPrice').textContent=fmtWon(v.p);
  { const sn=styleNameOf(v); $('#modalStyleName').textContent=sn; $('#modalStyle').hidden=!sn; }
  const segmentTitle=$('#modalSegLabel').parentElement;
  segmentTitle.firstChild.textContent='나와 비슷한 사용자들';
  $('#modalSegLabel').textContent=' (체형 · 스타일 · 나이)';
  const note=v.authorNote||{name:'FEEDiT 사용자',text:''};
  $('#modalNoteName').textContent=note.name;
  $('#modalNote').textContent=note.text;
  paintModalFeedback(v);
  closeAiModal();
  updateModalVote();
  renderComments();
  $('#modalOverlay').classList.add('on');
  document.body.style.overflow='hidden';
}
/* 모달 — 글쓴이의 사후 결과(있으면), 내 카드인데 아직 안 썼으면 '결과 남기기' */
function paintModalFeedback(v){
  let el=$('#modalFeedback');
  if(!el){
    const note=$('#modalNote'); if(!note)return;
    note.insertAdjacentHTML('afterend','<div class="modalFeedback" id="modalFeedback" hidden></div>');
    el=$('#modalFeedback');
  }
  const f=v.feedback;
  if(f){
    el.hidden=false;
    el.innerHTML='<b>글쓴이의 결과</b><span>'+escapeHtml(f.purchase_label||'')+
      (f.helpful===true?' · 투표가 도움이 됐어요':'')+'</span>'+
      (f.comment?'<q>'+escapeHtml(f.comment)+'</q>':'')+
      '';   /* ★ 2026-09-20 — 남긴 결과는 뱃지·적중률에 쓰여 수정하지 않는다 */
  }else if(v.feedbackPending){
    el.hidden=false;
    el.innerHTML='<b>투표가 마감됐어요</b><span>결국 어떻게 하셨는지 알려 주세요. 투표한 사람들의 적중이 계산됩니다.</span>'+
      '<button type="button" class="pill" data-fb-card>결과 남기기</button>';
  }else{ el.hidden=true; el.innerHTML=''; return; }
  const btn=el.querySelector('[data-fb-card]');
  if(btn)btn.onclick=()=>fbOpen({card_id:v.id, title:v.t, image_url:v.imgURL, feedback:v.feedback,
      vote_summary:{buy_pct:v.a, pass_pct:100-v.a, total:v.votes}},
    {askLater:false, onSaved:()=>window.smReloadVotes&&window.smReloadVotes()});
}
function closeModal(){
  $('#modalOverlay').classList.remove('on');
  document.body.style.overflow='';
  modalState.version+=1;
  modalState.i=null;
  resetCommentComposer();
  closeAiModal();
}

function updateModalVote(){
  const i=modalState.i; if(i===null)return;
  const v=VOTES[i];
  const votesShown=v.votes;
  $('#modalCntAll').textContent=v.closed
    ? `${fmtNum(votesShown)}표 · 투표 종료`
    : `${fmtNum(votesShown)}표 · 마감까지 ${fmtHours(v.hours)}`;
  /* 한쪽이 크게 이겨도 진 쪽 %가 잘려 사라지지 않게 tight 를 같이 걸어 둔다 */
  const setPair=(bar,a)=>{
    const b=$('.buy',bar), n=$('.no',bar);
    b.style.background='';
    b.style.width=a+'%';       b.innerHTML='<span>살 '+a+'%</span>';
    n.style.removeProperty('width'); n.innerHTML='<span>'+(100-a)+'% 말</span>';
    b.classList.toggle('tight',a<28); n.classList.toggle('tight',(100-a)<28);
  };
  setPair($('#modalBarAll'), v.a);
  /* 표본이 있을 때만 막대를 그린다. 없으면 막대를 감추고 이유를 쓴다. */
  const sim=simA(v), simBar=$('#modalBarSim'), simNote=$('#modalSimNote');
  if(sim==null){
    simBar.hidden=true;
    if(simNote){
      simNote.hidden=false;
      simNote.textContent=v.simReason||'아직 나와 비슷한 사용자가 이 카드에 투표하지 않았습니다.';
    }
  }else{
    simBar.hidden=false;
    if(simNote)simNote.hidden=true;
    setPair(simBar, sim);
  }

  if($('#aiChatBubble').classList.contains('on')) buildAIReport(i);
}

function buildAIReport(i){
  const v=VOTES[i], sim=simA(v), br=v.buyer;
  const simTx=sim==null
    ? '나와 비슷한 사용자의 투표가 아직 없어 이 부분은 비교하지 못했습니다.'
    : `성별·체형·나이·취향이 겹치는 사용자 ${v.simUsers}명 중 ${sim}%가 구매에 동의했습니다.`;
  const verdictBuy=v.a>=55;
  const el=$('#aiVerdict');
  el.textContent=verdictBuy?'지금 사도 좋아요':'조금 더 지켜보세요';
  el.classList.toggle('buy',verdictBuy);
  $('#aiWhy').textContent=
    `전체 투표에서는 ${v.a>=50?'살':'말'} 의견이 우세합니다. `+
    `${simTx} `+
    (br
      ? `판매처 구매 평점은 ${br.rating}/${br.scale}${br.review_count?`(후기 ${fmtNum(Number(br.review_count))}개)`:''}입니다. `
      : '판매처 구매 평점 정보가 없어 이 부분은 보지 못했습니다. ')+
    (v.closed?'투표가 종료되어 최종 결과를 보여드립니다.':`마감까지 ${fmtHours(v.hours)} 남았습니다.`);
  $('#aiStats').innerHTML=`
    <div><div class="k">전체 살 비율</div><div class="v">${v.a}%</div></div>
    <div><div class="k">유사 세그먼트</div><div class="v">${sim==null?'–':sim+'%'}</div></div>
    <div><div class="k">구매 평점</div><div class="v">${br?br.rating+'<small>/'+br.scale+'</small>':'–'}</div></div>`;
}

function renderComments(){
  const i=modalState.i; if(i===null)return;
  const list=VOTES[i].comments;
  $('#commentCount').textContent=list.length;
  $('#commentsList').innerHTML=list.map(c=>{
    const rk=rkClamp(c.rk!=null?c.rk:0);
    return `
    <div class="cItem">
      <div class="cAvatar${RANK_ON?` rkAv rk${rk+1}`:''}">${rkRingHTML(rk)}${RANK_ON&&rk>=3?'<b class="rkGloss"></b>':''}<span>${c.name[0]}</span></div>
      <div class="cBody">
        <div class="cHead">
          <b>${escapeHtml(c.name)}</b>${c.me ? (jobShown(ME) ? jobBadgeHTML(jobShown(ME)) : '') : jobBadgeHTML(c.job)}
          <span class="cTime">${c.time}</span>
          <button class="cMenuBtn" data-comment-id="${c.id}" aria-label="더보기">⋯</button>
        </div>
        <div class="cText">${escapeHtml(c.text)}</div>
      </div>
    </div>`;
  }).join('');
}

async function sendComment(){
  const i=modalState.i; if(i===null)return;
  const modalVersion=modalState.version;
  if(!requireAuth())return;
  const card=VOTES[i];
  if(card.closed){ showToast('마감된 투표에는 댓글을 달 수 없어요.'); return; }
  const ta=$('#commentInput');
  const sendButton=$('#commentSend');
  const text=ta.value.trim();
  if(!text)return;
  const cardId=card.id;
  if(pendingCommentCards.has(cardId))return;
  pendingCommentCards.add(cardId);
  ta.disabled=true;
  sendButton.disabled=true;
  try{
    const saved=await saveVoteComment({cardId,content:text});
    card.comments.unshift({
      name:ME.name||'나',rk:ME.rank,job:jobShown(ME)||'Basic',me:true,deletable:true,text,time:'방금 전',
      tag:saved?.choice==='BUY'?0:saved?.choice==='PASS'?1:null,id:saved?.id||nextCommentId()
    });
    if(modalState.i!==null && VOTES[modalState.i].id===cardId){
      if(modalState.version===modalVersion)ta.value='';
      renderComments();
      $('#commentsList').scrollTop=0;
    }
  }catch(error){ showToast(error.message||'댓글을 저장하지 못했습니다.'); }
  finally{
    pendingCommentCards.delete(cardId);
    if(modalState.i!==null && VOTES[modalState.i].id===cardId){
      ta.disabled=false;
      sendButton.disabled=false;
      ta.focus();
    }
  }
}

/* 모달 내 정적 요소 바인딩 (한 번만) */
$('#modalClose').addEventListener('click',closeModal);
$('#modalOverlay').addEventListener('click',e=>{ if(e.target.id==='modalOverlay') closeModal(); });
document.addEventListener('keydown',e=>{
  if(e.key!=='Escape')return;
  if($('#aiChatBubble').classList.contains('on')){ closeAiModal(); return; }
  if($('#createOverlay').classList.contains('on')){ closeCreateModal(); return; }
  if($('#modalOverlay').classList.contains('on')){ closeModal(); return; }
});

/* AI 살!말? 리포트 — 버튼 옆에 나란히 뜨는 말풍선 팝오버
   position:fixed 로 두고 버튼 위치를 기준으로 좌표를 계산해서
   모달 크기가 줄어도 항상 화면 안에서 버튼 옆(공간이 없으면 아래)에 붙는다 */
function positionAiBubble(){
  const btn=$('#aiBtn'), bubble=$('#aiChatBubble');
  const r=btn.getBoundingClientRect();
  const bw=bubble.offsetWidth||272, bh=bubble.offsetHeight||220;
  const vw=window.innerWidth, vh=window.innerHeight, pad=12;
  let left=r.right+10, top=r.top;
  if(left+bw>vw-pad){ left=Math.max(pad, r.left); top=r.bottom+10; }
  if(top+bh>vh-pad) top=Math.max(pad, vh-pad-bh);
  if(left+bw>vw-pad) left=Math.max(pad, vw-pad-bw);
  bubble.style.left=left+'px';
  bubble.style.top=top+'px';
}
function openAiModal(){
  if(modalState.i===null)return;
  buildAIReport(modalState.i);
  positionAiBubble();
  $('#aiChatBubble').classList.add('on');
}
function closeAiModal(){ $('#aiChatBubble').classList.remove('on'); }
$('#aiBtn').addEventListener('click',(e)=>{
  e.stopPropagation();
  $('#aiChatBubble').classList.contains('on') ? closeAiModal() : openAiModal();
});
$('#aiChatClose').addEventListener('click',(e)=>{ e.stopPropagation(); closeAiModal(); });
document.addEventListener('click',(e)=>{
  const bubble=$('#aiChatBubble');
  if(!bubble.classList.contains('on'))return;
  if(e.target.closest('#aiChatBubble')||e.target.closest('#aiBtn'))return;
  closeAiModal();
});
/* 왼쪽 컬럼을 스크롤하면 버튼 위치가 바뀌므로 팝오버는 닫는다 */
$('.modalLeft').addEventListener('scroll',()=>closeAiModal());
window.addEventListener('resize',()=>{ if($('#aiChatBubble').classList.contains('on')) closeAiModal(); });

$('#commentSend').addEventListener('click',sendComment);
$('#commentInput').addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){ e.preventDefault(); sendComment(); }
});

/* ── 탭 전환 ─────────────────────────────────────────── */
$$('#smTabs button').forEach(btn=>{
  btn.addEventListener('click',()=>{
    $$('#smTabs button').forEach(b=>b.classList.remove('on'));
    btn.classList.add('on');
    state.tab=btn.dataset.tab;
    state.page=1;
    renderGrid();
  });
});

/* ── 아이템 등록 토스트 ──────────────────────────────── */
let toastT;
function showToast(msg){
  const t=$('#toast');
  t.textContent=msg;
  t.classList.add('on');
  clearTimeout(toastT);
  toastT=setTimeout(()=>t.classList.remove('on'),2200);
}

/* ============================================================
   글쓰기 모달 — "살까말까 물어보기"
   ============================================================ */
/* ── 브랜드 검색 ──────────────────────────────────────
   치는 동안 맞는 브랜드를 아래 목록으로 보여 준다.
   목록에 없는 브랜드는 그대로 적어서 낼 수 있다 — 우리가 아는 브랜드만
   물어볼 수 있는 것이 아니기 때문이다.
   ↑↓ 로 옮기고 Enter 로 고르며 Esc 로 닫는다. */
const brandCombo=(function(){
  const input=$('#cBrand'), list=$('#cBrandList');
  let open=false, cursor=-1, shown=[];

  const norm=s=>String(s||'').toLowerCase().replace(/[\s'’·\-_.]+/g,'');
  function match(q){
    const n=norm(q);
    if(!n) return BRAND_LIST.slice(0,8);
    const starts=[], has=[];
    BRAND_LIST.forEach(b=>{
      const nb=norm(b);
      if(nb.startsWith(n)) starts.push(b);
      else if(nb.includes(n)) has.push(b);
    });
    return [...starts,...has].slice(0,8);
  }
  function paint(){
    list.innerHTML=shown.map((b,i)=>
      '<li role="option" class="cComboItem'+(i===cursor?' on':'')+'" data-brand="'+escapeHtml(b)+'"'+
      ' aria-selected="'+(i===cursor)+'">'+escapeHtml(b)+'</li>').join('');
  }
  function show(q){
    shown=match(q);
    if(!shown.length){ hide(); return; }
    cursor=-1; paint();
    list.hidden=false; open=true;
    input.setAttribute('aria-expanded','true');
  }
  function hide(){
    list.hidden=true; open=false; cursor=-1;
    input.setAttribute('aria-expanded','false');
  }
  function pick(b){ input.value=b; hide(); }
  function move(step){
    if(!open){ show(input.value); return; }
    if(!shown.length)return;
    cursor=(cursor+step+shown.length)%shown.length;
    paint();
    const on=list.querySelector('.cComboItem.on');
    if(on&&on.scrollIntoView)on.scrollIntoView({block:'nearest'});
  }

  input.addEventListener('input',()=>show(input.value));
  input.addEventListener('focus',()=>show(input.value));
  input.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'){ e.preventDefault(); move(1); return; }
    if(e.key==='ArrowUp'){ e.preventDefault(); move(-1); return; }
    if(e.key==='Enter'&&open&&cursor>=0){ e.preventDefault(); pick(shown[cursor]); return; }
    if(e.key==='Escape'&&open){ e.preventDefault(); e.stopPropagation(); hide(); }
  });
  /* mousedown 으로 잡는다 — click 은 input 의 blur 뒤라 목록이 이미 닫혀 있다 */
  list.addEventListener('mousedown',e=>{
    const li=e.target.closest('.cComboItem'); if(!li)return;
    e.preventDefault(); pick(li.dataset.brand);
  });
  document.addEventListener('click',e=>{
    if(!open)return;
    if(e.target.closest('#cBrandCombo'))return;
    hide();
  });
  return {hide};
})();

let createImgURL=null;
let createImgFile=null;
/* 스타일 드롭다운 — 스타일 페이지와 같은 핵심 스타일 10종을 그대로 쓴다 */
(function fillStyleSelect(){
  const sel=$('#cStyle'); if(!sel)return;
  sel.insertAdjacentHTML('beforeend',STYLES.map(s=>`<option value="${s.id}">${s.n}</option>`).join(''));
})();
function resetCreateForm(){
  $('#cTitle').value='';
  $('#cBrand').value='';
  brandCombo.hide();
  $('#cPrice').value='';
  if($('#cStyle')) $('#cStyle').value='';
  $('#cNote').value='';
  $('#imgInput').value='';
  if(createImgURL){ URL.revokeObjectURL(createImgURL); createImgURL=null; }
  createImgFile=null;
  $('#imgPreview').hidden=true;
  $('#imgPreview').src='';
  $('#imgDropInner').style.display='';
  $('#imgDrop').classList.remove('has-img');
}
function openCreateModal(draft){
  if(!requireAuth())return;
  resetCreateForm();
  if(draft&&typeof draft==='object'){
    $('#cTitle').value=String(draft.title||'').replace(/\s+/g,' ').trim().slice(0,120);
    /* 챗봇이 확인한 것만 채운다 — 확인하지 못한 칸은 비워 두고 사용자가 적는다 */
    if(draft.brand) $('#cBrand').value=String(draft.brand).replace(/\s+/g,' ').trim().slice(0,60);
    if(draft.price!=null&&String(draft.price).trim()!==''){
      const digits=String(draft.price).replace(/[^0-9]/g,'');
      if(digits) $('#cPrice').value=digits;
    }
    if(draft.image){
      createImgURL=String(draft.image);
      createImgFile=null;
      $('#imgPreview').src=createImgURL;
      $('#imgPreview').hidden=false;
      $('#imgDropInner').style.display='none';
      $('#imgDrop').classList.add('has-img');
    }
  }
  $('#createOverlay').classList.add('on');
  document.body.style.overflow='hidden';
}
function closeCreateModal(){
  $('#createOverlay').classList.remove('on');
  document.body.style.overflow='';
}
$('#addItemBtn').addEventListener('click',()=>openCreateModal());
$('#createClose').addEventListener('click',closeCreateModal);
$('#createOverlay').addEventListener('click',e=>{ if(e.target.id==='createOverlay') closeCreateModal(); });

$('#imgDrop').addEventListener('click',()=>$('#imgInput').click());
$('#imgInput').addEventListener('change',e=>{
  const file=e.target.files[0];
  if(!file)return;
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){
    e.target.value='';
    showToast('JPEG, PNG, WebP 이미지만 등록할 수 있어요.');
    return;
  }
  /* ★ 2026-09-19 — 원본을 그대로 base64 로 보내다 서버 앞단(nginx 기본 1MB)에서 413 으로 막혔다.
     이제 올릴 때 긴 변 1280px · JPEG 로 줄여 보낸다(보통 100~300KB). 원본은 20MB 까지만 받는다. */
  if(file.size>20*1024*1024){
    e.target.value='';
    showToast('이미지는 20MB 이하만 등록할 수 있어요.');
    return;
  }
  if(createImgURL) URL.revokeObjectURL(createImgURL);
  createImgFile=file;
  createImgURL=URL.createObjectURL(file);
  const img=$('#imgPreview');
  img.src=createImgURL;
  img.hidden=false;
  $('#imgDropInner').style.display='none';
  $('#imgDrop').classList.add('has-img');
});

$('#cPrice').addEventListener('input',()=>{
  $('#cPrice').value=$('#cPrice').value.replace(/[^0-9]/g,'');
});

/* 업로드용으로 줄인 JPEG data URL — 챗봇 사진 첨부와 같은 함수(긴 변 1280px · 품질 0.82) */
const fileDataUrl=async file=>{
  try{ return await imageFileToDataURL(file); }
  catch(e){ throw new Error('이미지 파일을 읽지 못했습니다.'); }
};

$('#createSubmit').addEventListener('click',async()=>{
  const title=$('#cTitle').value.trim();
  const brand=$('#cBrand').value.replace(/\s+/g,' ').trim();
  const priceRaw=$('#cPrice').value.trim();
  const note=$('#cNote').value.trim();
  const style=$('#cStyle')?$('#cStyle').value:'';

  if(!title){ showToast('상품명을 입력해주세요'); return; }
  if(!brand){ showToast('브랜드를 입력해주세요'); return; }
  if(!priceRaw){ showToast('가격을 입력해주세요'); return; }
  /* ★ 2026-09-19 — 사진 없는 카드는 받지 않는다. 살까 말까는 눈으로 보고 고르는 일이라
     사진이 빠지면 판이 회색으로만 뜨고 투표도 제대로 되지 않는다. */
  if(!createImgFile&&!createImgURL){ showToast('상품 이미지를 등록해주세요'); return; }

  const submit=$('#createSubmit');
  submit.disabled=true;
  const originalText=submit.textContent;
  submit.textContent='등록 중...';
  try{
    const styleName=STYLES.find(item=>item.id===style)?.n||'';
    const imageData=createImgFile?await fileDataUrl(createImgFile):'';
    const externalImage=!createImgFile&&createImgURL&&!createImgURL.startsWith('blob:')?createImgURL:'';
    const saved=await createVoteCard({
      title,brand,price:parseInt(priceRaw,10),description:note,
      tags:styleName?[styleName]:[],image_data_url:imageData,image_url:externalImage
    });
    VOTES.push(cardFromApi(saved,VOTES.length));
    if(!BRAND_LIST.includes(brand)) BRAND_LIST.push(brand);
    BRAND_LIST.sort();
    closeCreateModal();
    resetCreateForm();
    showToast('살까말까 물어보기 등록 완료!');
    state.tab='latest'; state.page=1;
    $$('#smTabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab==='latest'));
    renderGrid();
  }catch(error){
    showToast(error.message||'카드를 저장하지 못했습니다.');
  }finally{
    submit.disabled=false;
    submit.textContent=originalText;
  }
});

/* ── 최근 24시간 참여자 수 (2026-09-19) ─────────────────
   예전에는 102 에서 시작해 2.6초마다 ±1 씩 무작위로 흔들리는 가짜 인원이었다.
   이제 서버가 센 실제 참여자(투표·댓글·카드 작성, 중복 제거)를 그대로 쓴다. */
function paintActivity(){
  const el=$('#liveCount'); if(!el)return;
  el.textContent=ACTIVITY&&Number.isFinite(ACTIVITY.participants)?fmtNum(ACTIVITY.participants):'–';
}

/* ── 초기 렌더 ───────────────────────────────────────── */
$('#voteGrid').innerHTML='<div class="smDataState loading">살!말? 고민들을 불러오고 있어요</div>';
const SM_READY=loadVotes().then(()=>{
  syncExpiredCards();
  renderGrid();
  renderClosedGrid();
  setInterval(syncExpiredCards,30000);
}).catch(error=>{
  $('#voteGrid').innerHTML=`<div class="smDataState">${escapeHtml(error.message||'살!말? 데이터를 불러오지 못했습니다.')}</div>`;
  $('#closedGrid').innerHTML='';
});

/* ★ 2026-09-19 — 알림에서 바로 그 카드로 (댓글 알림이면 그 댓글을 잠깐 강조한다).
   notify.js 의 openTarget() 이 부른다. 목록에 없으면 한 번 다시 받아 보고, 그래도 없으면 알린다. */
window.smOpenCard=async(cardId,commentId)=>{
  try{ await SM_READY; }catch(e){}
  const find=()=>VOTES.findIndex(v=>Number(v.id)===Number(cardId)&&!v.deleted);
  let i=find();
  if(i<0&&window.smReloadVotes){ await window.smReloadVotes(); i=find(); }
  if(i<0){ showToast('게시글이 삭제됐거나 더 이상 볼 수 없어요.'); return; }
  openModal(i);
  if(commentId){
    setTimeout(()=>{
      const btn=document.querySelector('#commentsList [data-comment-id="'+commentId+'"]');
      const row=btn&&btn.closest('.cItem');
      if(!row)return;
      row.classList.remove('flash'); void row.offsetWidth;
      row.scrollIntoView({block:'center',behavior:'smooth'});
      row.classList.add('flash');
      row.addEventListener('animationend',()=>row.classList.remove('flash'),{once:true});
    },380);
  }
};
/* 이 화면을 다시 열 때 등장 모션만 되돌려 준다.
   salmalBoot 은 한 번만 도니까, 바깥에서 부를 손잡이를 남긴다.
   다시 그리지 않고 모션만 태워서 이미 누른 투표는 그대로 남는다. */
window.smReplay=()=>{ smCardsIn($('#voteGrid')); smCardsIn($('#closedGrid')) };
/* 살말 화면에 들어올 때마다 — 마감된 내 카드에 결과를 안 남겼으면 팝업으로 묻는다 */
window.smFeedbackPrompt=()=>{ if(AUTH.in) fbPromptOnce().catch(()=>{}); };
window.smFeedbackPrompt();
/* ★ 2026-09-19 — 회원정보에서 닉네임을 바꿔도 카드에는 예전 이름이 남아 있었다.
   카드 목록을 한 번 받아 두고 화면 전환만 해 왔기 때문이다 — 서버에서 다시 받아 그린다. */
window.smReloadVotes=async()=>{
  try{
    if(!await loadVotes()) return;
    syncExpiredCards();
    renderGrid();
    renderClosedGrid();
    if(modalState.i!==null) openModal(modalState.i);
  }catch(e){ /* 못 받아 오면 지금 화면을 그대로 둔다 */ }
};
/* ★ 2026-09-19 — 계정을 바꿔도(로그아웃 → 다른 계정 로그인) 앞 계정의 투표가 눌린 채 보였다.
   카드 목록(내 선택 my_choice 포함)을 첫 진입 때 한 번만 받아 두고 계속 썼기 때문이다.
   로그인·로그아웃이 일어나면 '나'에 딸린 값부터 바로 비우고, 서버에서 새 계정 기준으로 다시 받는다. */
document.addEventListener('feedit:auth',()=>{
  VOTES.forEach(v=>{ v.voted=null; v.mine=false; v.deletable=false; v.feedbackPending=false;
    v.comments=(v.comments||[]).map(c=>({...c, me:false, deletable:false})); });
  if(modalState.i!==null) closeModal();
  renderGrid(); renderClosedGrid();
  window.smReloadVotes();
  if(AUTH.in) window.smFeedbackPrompt();
});
/* 바깥(내 피드 등)에서 특정 탭으로 열어 달라고 할 때 쓴다 */
window.smGoTab=(tab)=>{
  const b=$$('#smTabs button').filter(x=>x.dataset.tab===tab)[0];
  if(!b)return;
  $$('#smTabs button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');
  state.tab=tab; state.page=1; renderGrid();
};
/* 챗봇의 '물어보기' 버튼에서 상품명·첨부 사진을 그대로 이어받는다. */
window.smOpenCreate=(draft)=>{
  window.__salmalDraft=null;
  openCreateModal(draft||{});
};

}
