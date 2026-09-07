import { HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';
import { ME } from '../../../account/static/js/profile.js';
import { rkClamp, rkRingHTML } from '../../../account/static/js/rank.js';
import { smBarFill, smBarLabels } from '../../../trend/static/js/discount_resale.js';

/* ══════════════ 살!말? (feedit-salmal_2 이식) ══════════════
   이름 충돌을 막기 위해 통째로 자기 범위 안에서 돌린다. */
export function salmalBoot(){

/* ============================================================
   데이터 — feedit-mockup_1.html VOTES 구조 참조, 필드 확장
   ============================================================ */
const VOTES=[
 {t:'스웨이드 블루종 (버건디)', b:'ANDERSSON BELL', p:329000, base:81, votes:842, hours:6,  taste:92, tone:['#3a332f','#6b5c52'], imgURL:'assets/hi/f20.jpg'},
 {t:'셀비지 와이드 데님',       b:'MUSINSA STANDARD', p:89000, base:64, votes:1930, hours:48, taste:75, tone:['#2f3336','#5a6166'], imgURL:'assets/hi/f21.jpg'},
 {t:'퀼팅 다운 베스트',         b:'NAUTICA',         p:149000, base:47, votes:512, hours:11, taste:60, tone:['#33302c','#7a7267'], imgURL:'assets/hi/f22.jpg'},
 {t:'스퀘어 토 로퍼',           b:'RANDOM IDENTITIES', p:268000, base:73, votes:1104, hours:24, taste:88, tone:['#2b2b2b','#585858'], imgURL:'assets/hi/f23.jpg'},
 {t:'울 발마칸 코트',           b:'SOLEW',           p:398000, base:38, votes:226, hours:40, taste:40, tone:['#37312c','#8c7f6e'], imgURL:'assets/hi/f24.jpg'},
 {t:'니트 집업 카디건',         b:'INSILENCE',       p:119000, base:69, votes:764, hours:8,  taste:81, tone:['#302d2b','#6e6660'], imgURL:'assets/hi/f25.jpg'},
 {t:'와이드 코듀로이 팬츠',     b:'SOLEW',           p:139000, base:58, votes:391, hours:15, taste:70, tone:['#332e2a','#75695c'], imgURL:'assets/hi/f26.jpg'},
 {t:'레더 크로스 백',           b:'MATIN KIM',       p:168000, base:44, votes:305, hours:30, taste:66, tone:['#2c2c2e','#5f5f63'], imgURL:'assets/hi/f27.jpg'},
 {t:'오버핏 울 블레이저',       b:'AMOMENTO',        p:298000, base:55, votes:410, hours:20, taste:77, tone:['#332f2b','#6f6255'], imgURL:'assets/hi/f28.jpg'},
 {t:'캐시미어 머플러',          b:'LE 17 SEPTEMBRE', p:98000,  base:71, votes:602, hours:5,  taste:85, tone:['#2e2a2c','#5c5459'], imgURL:'assets/hi/f29.jpg'},
 {t:'워시드 후드 집업',         b:'THISISNEVERTHAT', p:129000, base:49, votes:288, hours:40, taste:58, tone:['#2b2d2e','#565b5d'], imgURL:'assets/hi/f30.jpg'},
 {t:'베이직 옥스포드 셔츠',     b:'MUSINSA STANDARD',p:39900,  base:62, votes:733, hours:14, taste:69, tone:['#302f2c','#6a655c'], imgURL:'assets/hi/f31.jpg'},
 {t:'헤비 코튼 크루넥',         b:'COS',             p:59000,  base:35, votes:190, hours:36, taste:44, tone:['#2c2b29','#6b665e'], imgURL:'assets/hi/f32.jpg'},
 {t:'원턱 와이드 슬랙스',       b:'UNIFORM BRIDGE',  p:79000,  base:66, votes:521, hours:9,  taste:79, tone:['#2b2c2d','#585d60'], imgURL:'assets/hi/f33.jpg'},
 {t:'삼바 OG',                 b:'ADIDAS',          p:139000, base:88, votes:2210,hours:3,  taste:95, tone:['#2f2b2b','#726358'], imgURL:'assets/hi/f34.jpg'},
 {t:'레이어드 체인 목걸이',     b:'CENTIME',         p:68000,  base:41, votes:167, hours:45, taste:52, tone:['#2d2d2f','#5e6165'], imgURL:'assets/hi/f35.jpg'},
 {t:'와이드 리넨 셔츠',         b:'COS',             p:79000,  base:72, votes:1560,hours:0,  taste:70, tone:['#33322d','#736c5e'], closed:true, imgURL:'assets/hi/f02.jpg'},
 {t:'스트랩 샌들',              b:'RANDOM IDENTITIES',p:98000, base:33, votes:640, hours:0,  taste:55, tone:['#2c2b2a','#615c56'], closed:true, imgURL:'assets/hi/f05.jpg'},
 {t:'헤링본 트위드 재킷',       b:'SOLEW',           p:259000, base:61, votes:920, hours:0,  taste:66, tone:['#302c2a','#6f6459'], closed:true, imgURL:'assets/hi/f11.jpg'},
 {t:'미니멀 크로스백',          b:'MSTA',            p:87000,  base:69, votes:1240,hours:0,  taste:73, tone:['#2b2a29','#645d54'], closed:true, imgURL:'assets/hi/f13.jpg'},
 {t:'스트라이프 니트',          b:'COS',             p:69000,  base:44, votes:512, hours:0,  taste:58, tone:['#302e2c','#6c655c'], closed:true, imgURL:'assets/hi/f04.jpg'},
 {t:'카고 워크 팬츠',           b:'CARHARTT WIP',    p:149000, base:58, votes:880, hours:0,  taste:66, tone:['#2d2c2a','#665f56'], closed:true, imgURL:'assets/hi/f06.jpg'},
 {t:'레트로 러너 스니커즈',     b:'NEW BALANCE',     p:159000, base:91, votes:3020,hours:0,  taste:92, tone:['#2b2b2d','#5c5c60'], closed:true, imgURL:'assets/hi/f08.jpg'},
 {t:'오버사이즈 후드티',        b:'THISISNEVERTHAT', p:89000,  base:37, votes:410, hours:0,  taste:48, tone:['#2e2b28','#6d655a'], closed:true, imgURL:'assets/hi/f09.jpg'},
 {t:'데님 셔츠 자켓',           b:"LEVI'S",          p:119000, base:63, votes:670, hours:0,  taste:70, tone:['#2c2d30','#585c63'], closed:true, imgURL:'assets/hi/f12.jpg'},
 {t:'버킷햇',                   b:'KIJUN',           p:45000,  base:52, votes:390, hours:0,  taste:60, tone:['#302f2b','#726a5d'], closed:true, imgURL:'assets/hi/f15.jpg'},
 {t:'스퀘어 선글라스',          b:'GENTLE MONSTER',  p:229000, base:76, votes:1560,hours:0,  taste:81, tone:['#2a2a2c','#59595e'], closed:true, imgURL:'assets/hi/f17.jpg'},
 {t:'램스울 가디건',            b:'LEMAIRE',         p:389000, base:41, votes:240, hours:0,  taste:52, tone:['#312d2a','#756c60'], closed:true, imgURL:'assets/hi/f03.jpg'}
];
VOTES.forEach((v,i)=>{v.a=v.base; v.voted=null; v.comments=[]; v.seq=i;});
const BRAND_LIST=[...new Set(VOTES.map(v=>v.b))].sort();
const TONE_PALETTE=[['#332e2a','#75695c'],['#2c2c2e','#5f5f63'],['#302f2c','#6a655c'],
  ['#2b2c2d','#585d60'],['#33322d','#736c5e'],['#2e2a2c','#5c5459']];
const randomTone=()=>TONE_PALETTE[Math.floor(Math.random()*TONE_PALETTE.length)];

const $=(s,el=document)=>el.querySelector(s);
const $$=(s,el=document)=>[...el.querySelectorAll(s)];
const fmtWon=n=>n.toLocaleString('ko-KR')+'원';
const fmtHours=h=>h>=24?Math.round(h/24)+'일':h+'시간';
const fmtNum=n=>n.toLocaleString('ko-KR');
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const simA=v=>clamp(v.a+Math.round((v.taste-70)/4),3,97);
const satisfaction=v=>clamp(v.taste+Math.round((v.base-70)/5),30,99);

/* ── 댓글 시드 데이터 ─────────────────────────────────── */
/* rk: 작성자 등급(0~4) — 아바타 링(rkPaintAv)이 여기서 색을 가져온다 */
const COMMENT_SEED=[
 {name:'민지', tag:0, rk:1, text:'실물이 훨씬 예뻐요, 색감도 안 뜨고 좋았어요.', time:'2시간 전'},
 {name:'현우', tag:1, rk:3, text:'핏이 생각보다 커요. 한 사이즈 다운 추천드려요.', time:'4시간 전'},
 {name:'소은', tag:0, rk:0, text:'가격 대비 소재가 꽤 괜찮은 편이에요.', time:'6시간 전'},
 {name:'재훈', tag:null, rk:2, text:'구매 전에 후기 더 보고 싶어요, 다들 어떠세요?', time:'9시간 전'},
 {name:'다인', tag:0, rk:4, text:'재구매 의사 있어요! 세탁 후에도 변형 없었어요.', time:'11시간 전'},
 {name:'유진', tag:1, rk:1, text:'다음 시즌엔 색상이 더 다양하게 나왔으면 좋겠어요.', time:'1일 전'},
 {name:'태윤', tag:0, rk:2, text:'매장에서 직접 보고 왔는데 사진보다 훨씬 낫습니다.', time:'1일 전'},
 {name:'하은', tag:1, rk:0, text:'배송이 좀 느렸어요, 아이템 자체는 무난해요.', time:'2일 전'}
];
function seedComments(i){
  const out=[];
  for(let k=0;k<3;k++) out.push(COMMENT_SEED[(i*3+k)%COMMENT_SEED.length]);
  return out;
}
let COMMENT_UID=1;
const nextCommentId=()=>COMMENT_UID++;
/* 시드 댓글을 각 아이템의 실제 comments 배열로 한 번만 옮겨 담아서
   (신고/삭제 등) 개별 조작이 가능하게 만든다. 이후 새로 만든 게시글은
   비어있는 comments 배열을 그대로 유지한다. */
VOTES.forEach((v,i)=>{
  if(v.comments.length===0){
    v.comments=seedComments(i).map(c=>({...c, id:nextCommentId()}));
  }
});

/* ── 작성자 사연 시드 ─────────────────────────────────── */
const NOTE_POOL=[
 {name:'benni_92', text:'평소에는 심플한 스타일을 입는데 이런 스타일에 도전해보고 싶어서 올려봅니다.'},
 {name:'ju_da', text:'제 눈에는 예쁜데 다른 분들 의견은 어떨지 궁금해서 올려봅니다.'},
 {name:'minsu.k', text:'이 가격에 구매하는 거 어떻게 생각하시는지 궁금해서 올려봅니다.'},
 {name:'hyeree', text:'친구가 추천해준 아이템인데 저한테 어울릴지 감이 안 잡혀서 올려봅니다.'},
 {name:'wonjin_c', text:'세일 마지막 날이라 고민 중인데, 사도 후회 안 할지 봐주세요.'}
];
function noteFor(i){ return NOTE_POOL[i%NOTE_POOL.length]; }

function orderFor(tab){
  let idx=VOTES.map((_,i)=>i).filter(i=>!VOTES[i].deleted);
  if(tab==='result'){
    /* 결과보기: 마감된(투표 종료) 게시글만 */
    return idx.filter(i=>VOTES[i].closed).sort((a,b)=>VOTES[b].votes-VOTES[a].votes);
  }
  /* 그 외 탭은 진행 중인 게시글만 노출 */
  idx=idx.filter(i=>!VOTES[i].closed);
  if(tab==='closing'){
    /* 마감임박: 마감까지 12시간 이하 남은 게시글만 */
    return idx.filter(i=>VOTES[i].hours<=12).sort((a,b)=>VOTES[a].hours-VOTES[b].hours);
  }
  if(tab==='popular'){
    /* 인기순: 참여수(투표수) 많은 순 */
    return idx.sort((a,b)=>VOTES[b].votes-VOTES[a].votes);
  }
  if(tab==='taste'){
    /* 내 취향: 취향 매칭도 높은 순 */
    return idx.sort((a,b)=>VOTES[b].taste-VOTES[a].taste);
  }
  /* 최신순: 가장 최근에 등록된 게시글 먼저 */
  return idx.sort((a,b)=>VOTES[b].seq-VOTES[a].seq);
}

function plateStyle(v){
  return v.imgURL
    ? `background-image:url('${v.imgURL}');background-size:cover;background-position:center`
    : `background:linear-gradient(150deg,${v.tone[0]},${v.tone[1]})`;
}

function cardHTML(i){
  const v=VOTES[i];
  const buyOn=v.voted===0, noOn=v.voted===1;
  const votesShown=v.votes+(v.voted!==null?1:0);
  const capText=v.closed
    ? `${fmtNum(votesShown)}표 · 투표 종료`
    : `${fmtNum(votesShown)}표 · 마감까지 ${fmtHours(v.hours)}${v.voted!==null?' · <em>투표함</em>':''}`;
  const btnsHTML=v.closed
    ? `<div class="closedNote">투표가 종료됐어요</div>`
    : `<div class="smBtns">
        <button class="buy${buyOn?' picked':''}" data-vote="0">살!</button>
        <button class="${noOn?'picked':''}" data-vote="1">말래요</button>
      </div>`;
  return `
  <div class="voteCard" data-i="${i}">
    <div class="fig">
      <div class="plate" style="${plateStyle(v)}"></div>
      <div class="vig"></div>
      <span class="pricep">${fmtWon(v.p)}</span>
      <span class="tagp"><b>${v.b}</b></span>
    </div>
    <div class="body">
      <h4>${v.t}</h4>
      <div class="cap">${capText}</div>
      <div class="smBar">
        <i class="buy" data-w="${v.a}" style="width:${v.a}%"><span>살 ${v.a}%</span></i>
        <i class="no" data-w="${100-v.a}" style="width:${100-v.a}%"><span>${100-v.a}% 말</span></i>
      </div>
      ${btnsHTML}
    </div>
  </div>`;
}

const PAGE_SIZE=8;
const state={tab:'taste', page:1};

function renderGrid(){
  const order=orderFor(state.tab);
  const totalPages=Math.max(1,Math.ceil(order.length/PAGE_SIZE));
  if(state.page>totalPages) state.page=totalPages;
  const start=(state.page-1)*PAGE_SIZE;
  const pageItems=order.slice(start,start+PAGE_SIZE);

  const grid=$('#voteGrid');
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
    aAnimate(buyBar,{width:v.a+'%',duration:820,ease:aSpring({stiffness:104,damping:15}),
      onComplete:()=>smBarLabels([buyBar,noBar])});
    aAnimate(noBar ,{width:(100-v.a)+'%',duration:820,ease:aSpring({stiffness:104,damping:15})});
  }else{ buyBar.style.width=v.a+'%'; noBar.style.width=(100-v.a)+'%'; smBarLabels([buyBar,noBar]) }
  $$('.smBtns button',card).forEach(btn=>{
    const side=+btn.dataset.vote;
    btn.classList.toggle('picked', v.voted===side);
  });
  const votesShown=v.votes+(v.voted!==null?1:0);
  $('.cap',card).innerHTML=`${fmtNum(votesShown)}표 · 마감까지 ${fmtHours(v.hours)}${v.voted!==null?' · <em>투표함</em>':''}`;
}

function castVote(i,side){
  const v=VOTES[i];
  v.voted = (v.voted===side) ? null : side;
  if(v.voted===0) v.a=Math.min(97, v.base+4);
  else if(v.voted===1) v.a=Math.max(3, v.base-4);
  else v.a=v.base;
  updateCard(i);
  smVoteBeat($(`.voteCard[data-i="${i}"]`), side);
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
function deleteCard(i){
  VOTES[i].deleted=true;
  if(modalState.i===i) closeModal();
  if(VOTES[i].closed){ renderClosedGrid(); }
  else renderGrid();
  showToast('게시글이 삭제됐어요.');
}
function deleteComment(i,commentId){
  if(i===null)return;
  VOTES[i].comments=VOTES[i].comments.filter(c=>c.id!==commentId);
  renderComments();
  showToast('댓글이 삭제됐어요.');
}
$$('#ctxMenu button').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const action=btn.dataset.action;
    const target=ctxTarget;
    closeCtxMenu();
    if(!target)return;
    if(action==='report'){
      showToast(target.type==='card' ? '신고가 접수됐어요. 검토 후 조치할게요.' : '댓글 신고가 접수됐어요.');
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
const modalState={i:null};

function escapeHtml(s){
  return s.replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function openModal(i){
  modalState.i=i;
  const v=VOTES[i];
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
  $('#modalSegLabel').textContent=' (체형・스타일・나이)';
  const note=v.authorNote||noteFor(i);
  $('#modalNoteName').textContent=note.name;
  $('#modalNote').textContent=note.text;
  closeAiModal();
  updateModalVote();
  renderComments();
  $('#modalOverlay').classList.add('on');
  document.body.style.overflow='hidden';
}
function closeModal(){
  $('#modalOverlay').classList.remove('on');
  document.body.style.overflow='';
  modalState.i=null;
  closeAiModal();
}

function updateModalVote(){
  const i=modalState.i; if(i===null)return;
  const v=VOTES[i];
  const votesShown=v.votes+(v.voted!==null?1:0);
  $('#modalCntAll').textContent=v.closed
    ? `${fmtNum(votesShown)}표 · 투표 종료`
    : `${fmtNum(votesShown)}표 · 마감까지 ${fmtHours(v.hours)}`;
  /* 한쪽이 크게 이겨도 진 쪽 %가 잘려 사라지지 않게 tight 를 같이 걸어 둔다 */
  const setPair=(bar,a)=>{
    const b=$('.buy',bar), n=$('.no',bar);
    b.style.width=a+'%';       b.textContent='살 '+a+'%';
    n.style.width=(100-a)+'%'; n.textContent=(100-a)+'% 말';
    b.classList.toggle('tight',a<28); n.classList.toggle('tight',(100-a)<28);
  };
  setPair($('#modalBarAll'), v.a);
  setPair($('#modalBarSim'), simA(v));

  if($('#aiChatBubble').classList.contains('on')) buildAIReport(i);
}

function buildAIReport(i){
  const v=VOTES[i], sim=simA(v), sat=satisfaction(v);
  const verdictBuy=v.a>=55;
  const el=$('#aiVerdict');
  el.textContent=verdictBuy?'지금 사도 좋아요':'조금 더 지켜보세요';
  el.classList.toggle('buy',verdictBuy);
  $('#aiWhy').textContent=
    `전체 투표에서 ${v.a>=50?'살':'말'} 의견이 우세하고, 취향이 비슷한 사용자 사이에서는 ${sim}%가 구매에 동의했습니다. `+
    `실제 구매자 만족도는 ${sat}%로 ${sat>=80?'높은 편':sat>=60?'무난한 편':'다소 낮은 편'}이며, `+
    `마감까지 ${fmtHours(v.hours)} 남아 지금이 결정하기 좋은 시점입니다.`;
  $('#aiStats').innerHTML=`
    <div><div class="k">전체 살 비율</div><div class="v">${v.a}%</div></div>
    <div><div class="k">유사 세그먼트</div><div class="v">${sim}%</div></div>
    <div><div class="k">구매자 만족도</div><div class="v">${sat}%</div></div>`;
}

function renderComments(){
  const i=modalState.i; if(i===null)return;
  const list=VOTES[i].comments;
  $('#commentCount').textContent=list.length;
  $('#commentsList').innerHTML=list.map(c=>{
    const rk=rkClamp(c.rk!=null?c.rk:0);
    return `
    <div class="cItem">
      <div class="cAvatar rkAv rk${rk+1}">${rkRingHTML(rk)}${rk>=3?'<b class="rkGloss"></b>':''}<span>${c.name[0]}</span></div>
      <div class="cBody">
        <div class="cHead">
          <b>${c.name}</b>
          <span class="cTime">${c.time}</span>
          <button class="cMenuBtn" data-comment-id="${c.id}" aria-label="더보기">⋯</button>
        </div>
        <div class="cText">${escapeHtml(c.text)}</div>
      </div>
    </div>`;
  }).join('');
}

function sendComment(){
  const i=modalState.i; if(i===null)return;
  const ta=$('#commentInput');
  const text=ta.value.trim();
  if(!text)return;
  VOTES[i].comments.unshift({name:'나', rk:ME.rank, text, time:'방금 전', id:nextCommentId()});
  ta.value='';
  renderComments();
  $('#commentsList').scrollTop=0;
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
  if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); sendComment(); }
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
(function(){
  const sel=$('#cBrand');
  BRAND_LIST.forEach(b=>{
    const opt=document.createElement('option');
    opt.value=b; opt.textContent=b;
    sel.appendChild(opt);
  });
  const other=document.createElement('option');
  other.value='기타'; other.textContent='기타 (직접 입력 예정)';
  sel.appendChild(other);
})();

let createImgURL=null;
function resetCreateForm(){
  $('#cTitle').value='';
  $('#cBrand').value='';
  $('#cPrice').value='';
  $('#cNote').value='';
  $('#imgInput').value='';
  if(createImgURL){ URL.revokeObjectURL(createImgURL); createImgURL=null; }
  $('#imgPreview').hidden=true;
  $('#imgPreview').src='';
  $('#imgDropInner').style.display='';
  $('#imgDrop').classList.remove('has-img');
}
function openCreateModal(){
  resetCreateForm();
  $('#createOverlay').classList.add('on');
  document.body.style.overflow='hidden';
}
function closeCreateModal(){
  $('#createOverlay').classList.remove('on');
  document.body.style.overflow='';
}
$('#addItemBtn').addEventListener('click',openCreateModal);
$('#createClose').addEventListener('click',closeCreateModal);
$('#createOverlay').addEventListener('click',e=>{ if(e.target.id==='createOverlay') closeCreateModal(); });

$('#imgDrop').addEventListener('click',()=>$('#imgInput').click());
$('#imgInput').addEventListener('change',e=>{
  const file=e.target.files[0];
  if(!file)return;
  if(createImgURL) URL.revokeObjectURL(createImgURL);
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

$('#createSubmit').addEventListener('click',()=>{
  const title=$('#cTitle').value.trim();
  const brand=$('#cBrand').value;
  const priceRaw=$('#cPrice').value.trim();
  const note=$('#cNote').value.trim();

  if(!title){ showToast('상품명을 입력해주세요'); return; }
  if(!brand){ showToast('브랜드를 선택해주세요'); return; }
  if(!priceRaw){ showToast('가격을 입력해주세요'); return; }

  const seq=VOTES.length?VOTES[VOTES.length-1].seq+1:0;
  const item={
    t:title, b:brand, p:parseInt(priceRaw,10),
    base:50, a:50, votes:0, hours:48, taste:70,
    tone:randomTone(), voted:null, comments:[], closed:false, seq,
    imgURL:createImgURL||null,
    authorNote: note ? {name:'나', text:note} : null
  };
  createImgURL=null; /* 소유권을 item으로 넘겨 reset 시 URL이 해제되지 않도록 함 */
  VOTES.push(item);

  closeCreateModal();
  showToast('살까말까 물어보기 등록 완료!');

  state.tab='latest'; state.page=1;
  $$('#smTabs button').forEach(b=>b.classList.toggle('on', b.dataset.tab==='latest'));
  renderGrid();
});

/* ── 실시간 인원 카운터 미세 변동 ────────────────────── */
setInterval(()=>{
  const el=$('#liveCount');
  const cur=+el.textContent;
  const next=Math.max(96, cur+(Math.random()>0.5?1:-1));
  if(HAS_A){
    const o={v:cur};
    aAnimate(o,{v:next,duration:520,ease:'out(2)',
      onUpdate:()=>{ el.textContent=Math.round(o.v) }});
    aAnimate(el,{keyframes:[{translateY:-2,duration:150,ease:'out(2)'},
      {translateY:0,duration:420,ease:aSpring({stiffness:150,damping:12})}]});
  }else el.textContent=next;
},2600);

/* ── 초기 렌더 ───────────────────────────────────────── */
renderGrid();
renderClosedGrid();

/* 이 화면을 다시 열 때 등장 모션만 되돌려 준다.
   salmalBoot 은 한 번만 도니까, 바깥에서 부를 손잡이를 남긴다.
   다시 그리지 않고 모션만 태워서 이미 누른 투표는 그대로 남는다. */
window.smReplay=()=>{ smCardsIn($('#voteGrid')); smCardsIn($('#closedGrid')) };
/* 바깥(내 피드 등)에서 특정 탭으로 열어 달라고 할 때 쓴다 */
window.smGoTab=(tab)=>{
  const b=$$('#smTabs button').filter(x=>x.dataset.tab===tab)[0];
  if(!b)return;
  $$('#smTabs button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');
  state.tab=tab; state.page=1; renderGrid();
};

}
