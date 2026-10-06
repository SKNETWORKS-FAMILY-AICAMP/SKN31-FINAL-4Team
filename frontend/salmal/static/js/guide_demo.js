/* 살!말? 온보딩용 숨은 목업 페이지.
 * 운영 카드·VOTES·회원·API와 분리된 정적 DOM만 만든다.
 * 기존 클래스를 재사용해 디자인만 같고, 저장 동작은 전혀 없다. */

import { RANK_ON, rkClamp, rkRingHTML } from '../../../account/static/js/rank.js';

const ROOT_ID='salmalGuideDemo';
const IMAGE='https://image.msscdn.net/images/goods_img/20260804/6987937/6987937_17866909077012_500.jpg';

/* 마지막 값은 예시 작성자의 레벨(0=Lv.1 … 4=Lv.Max). 운영 댓글처럼 프로필 둘레에 레벨 띠를 그린다. */
const comments=[
  ['도윤','Student','9월 18일','브이넥이 과하게 깊지 않아 맨살에도 부담 없고 셔츠 위에 겹쳐 입기도 좋아 보여요.',1],
  ['현우','Creator','9월 17일','3만 원대라 기본색 하나와 포인트색 하나를 같이 골라도 부담이 덜하겠어요.',3],
  ['준서','MD','9월 17일','두께가 얇은 니트라 재킷 안에 입어도 팔이 끼지 않을 것 같아요.',2],
  ['시우','Student','9월 17일','여섯 가지 색이 있어서 이미 가진 하의에 맞춰 고르기 좋아 보여요.',0],
  ['태현','Buyer','9월 17일','크루넥보다 목선이 열려 있어 체격이 있는 사람도 답답해 보이지 않겠어요.',4],
  ['건우','Basic','9월 17일','가격이 합리적이라 기본 브라운으로 오래 입어보고 싶어요.',0],
  ['재윤','Stylist','9월 16일','가격은 괜찮지만 얇은 니트는 보풀과 늘어남을 더 확인해볼 것 같아요.',2],
  ['성민','Basic','9월 16일','브이넥 깊이와 어깨 핏이 애매하면 이너 없이 입기 어려울 수 있어요.',1],
];

/* 아바타 마크업은 운영 상세 화면(vote_app.js renderComments)과 같다. */
function commentHTML([name,job,time,text,level]){
  const rk=rkClamp(level);
  const avatar='<div class="cAvatar'+(RANK_ON?' rkAv rk'+(rk+1):'')+'">'+rkRingHTML(rk)+
    (RANK_ON&&rk>=3?'<b class="rkGloss"></b>':'')+'<span>'+name[0]+'</span></div>';
  return '<div class="cItem">'+avatar+'<div class="cBody">'+
    '<div class="cHead"><b>'+name+'</b><span class="jobBadge">'+job+'</span><span class="cTime">'+time+'</span><button class="cMenuBtn" type="button" tabindex="-1">⋯</button></div>'+
    '<div class="cText">'+text+'</div></div></div>';
}

function pageHTML(){
  return '<section class="smGuidePage" data-sm-guide="page"><div class="smPage">'+
    '<section class="smHero" data-sm-guide="hero"><div class="liveNow"><span class="dot"></span>최근 24시간 <b>0</b>명 참여</div>'+
      '<h1 class="smStatement">살까, <em>말까</em>.</h1><div class="smHeroRow"><p>리뷰보다 빠르고, 친구보다 솔직합니다.</p></div>'+
      '<div class="smTabsRow"><div class="smTabs"><button>인기순</button><button>최신순</button><button class="on">내 취향</button><button>마감임박</button><button>내 카드</button></div>'+
      '<button class="addItemBtn" type="button" data-sm-guide="add">+ 살까말까 물어보기</button></div></section>'+
    '<section class="voteSection"><div class="voteGrid smGuideGrid"><article class="voteCard in" data-sm-guide="card">'+
      '<div class="fig"><div class="plate" style="background-image:url(\''+IMAGE+'\');background-size:cover;background-position:center"></div><div class="vig"></div>'+
      '<span class="pricep">25,480원</span><span class="tagp"><b>수아레</b></span></div>'+
      '<div class="body"><h4>데일리 브이넥 니트 - 6 COLOR</h4><div class="cap">20표 · 마감까지 6일</div>'+
      '<div class="smBar"><i class="buy" style="width:65%"><span>살 65%</span></i><i class="no"><span>35% 말</span></i></div>'+
      '<div class="smBtns"><button class="buy" type="button">살!</button><button type="button">말?</button></div></div></article></div></section>'+
    '</div></section>';
}

function detailHTML(){
  return '<div class="modalOverlay smGuideDetail" data-sm-guide="detail"><div class="modalShell"><div class="modalBox"><div class="modalGrid">'+
    '<div class="modalLeft"><div class="modalFig"><div class="plate" style="background-image:url(\''+IMAGE+'\');background-size:cover;background-position:center"></div><div class="vig"></div>'+
      '<button class="aiBtn" type="button" tabindex="-1"><span class="dotc"></span>AI 살!말? 리포트</button></div>'+
      '<div class="modalInfo"><h3>데일리 브이넥 니트 - 6 COLOR</h3><div class="modalMeta"><b>수아레</b> · <span>25,480원</span> · <span>클래식</span></div></div>'+
      '<div class="modalPost"><span class="postName">피딧</span><p class="postText">브이넥 니트를 자주 입어서 색을 하나 더 사고 싶어요. 3만 원대라 부담은 적지만 너무 얇거나 세탁 후 줄어들지는 않을지, 기본 니트로 괜찮은지 궁금합니다.</p></div></div>'+
    '<div class="modalRight"><div class="voteBlock"><div class="voteBlockHead"><span>전체 투표</span><span class="cnt">20표 · 마감까지 6일</span></div>'+
      '<div class="smBar"><i class="buy" style="width:65%"><span>살 65%</span></i><i class="no"><span>35% 말</span></i></div></div>'+
      '<div class="voteBlock similar"><div class="voteBlockHead"><span>나와 비슷한 사용자들 <em>(체형 · 스타일 · 나이)</em></span></div>'+
      '<div class="smBar"><i class="buy" style="width:59%"><span>살 59%</span></i><i class="no"><span>41% 말</span></i></div></div>'+
      '<div class="commentsHead">댓글 <span>8</span></div><div class="commentsList">'+comments.map(commentHTML).join('')+'</div>'+
      '<div class="commentForm"><div class="commentInputRow"><textarea maxlength="1000" placeholder="댓글을 남겨보세요"></textarea><button class="commentSend" type="button" tabindex="-1">→</button></div></div>'+
    '</div></div></div></div></div>';
}

function createHTML(){
  return '<div class="modalOverlay smGuideCreate" data-sm-guide="create"><div class="modalShell"><div class="modalBox createBox"><div class="createGrid">'+
    '<div class="createLeft"><h3 class="createTitle">살까말까 물어보기</h3><p class="createSub">고민되는 아이템을 올리면 취향이 비슷한 사람들이 살지 말지 투표해드려요.</p>'+
      '<div class="cField"><label class="cLabel">상품 이미지</label><div class="imgDrop" data-sm-guide="image"><div class="imgDropInner"><span class="imgDropIcon">+</span><span>이미지를 선택하세요</span></div></div></div></div>'+
    '<div class="createRight"><div class="cField" data-sm-guide="title"><label class="cLabel">상품명</label><input class="cInput" placeholder="예: 스웨이드 블루종 (버건디)" readonly></div>'+
      '<div class="cField" data-sm-guide="brand"><label class="cLabel">브랜드</label><input class="cInput" placeholder="브랜드를 검색하세요" readonly></div>'+
      '<div class="cRow2"><div class="cField" data-sm-guide="price"><label class="cLabel">가격</label><input class="cInput" placeholder="숫자만 입력 (원)" readonly></div>'+
      '<div class="cField" data-sm-guide="style"><label class="cLabel">스타일</label><select class="cInput" tabindex="-1"><option>스타일 선택</option></select></div></div>'+
      '<div class="cField grow" data-sm-guide="story"><label class="cLabel">사연</label><textarea class="cInput cTextarea" placeholder="이 아이템을 왜 올리는지 알려주세요. 예) 이 가격에 사도 될지 궁금해서 올려봅니다." readonly></textarea></div>'+
      '<button class="pill big coral createSubmit" type="button" tabindex="-1">물어보기</button></div>'+
    '</div></div></div></div>';
}

function root(){ return document.getElementById(ROOT_ID); }

function setOverlayState(overlay, open){
  if(!overlay) return;
  overlay.classList.toggle('on', open);
  /* 운영 모달의 전환 상태와 무관하게 가이드 목업의 표시 여부를 확정한다.
   * 이렇게 해야 CSS 로드 순서가 바뀌어도 단계 타깃이 숨김으로 오인되지 않는다. */
  overlay.style.visibility=open?'visible':'hidden';
  overlay.style.opacity=open?'1':'0';
  overlay.setAttribute('aria-hidden', open?'false':'true');
}

export function mountSalmalGuideDemo(){
  unmountSalmalGuideDemo();
  const host=document.createElement('div');
  host.id=ROOT_ID;
  host.className='smGuideStage';
  host.innerHTML=pageHTML()+detailHTML()+createHTML();
  document.body.appendChild(host);
  showSalmalGuideFeed();
  return unmountSalmalGuideDemo;
}

export function showSalmalGuideFeed(){
  const host=root(); if(!host)return;
  setOverlayState(host.querySelector('[data-sm-guide="detail"]'),false);
  setOverlayState(host.querySelector('[data-sm-guide="create"]'),false);
  host.scrollTop=0;
}

export function showSalmalGuideDetail(){
  const host=root(); if(!host)return;
  setOverlayState(host.querySelector('[data-sm-guide="create"]'),false);
  setOverlayState(host.querySelector('[data-sm-guide="detail"]'),true);
}

export function showSalmalGuideCreate(){
  const host=root(); if(!host)return;
  setOverlayState(host.querySelector('[data-sm-guide="detail"]'),false);
  setOverlayState(host.querySelector('[data-sm-guide="create"]'),true);
}

export function unmountSalmalGuideDemo(){
  const host=root();
  if(host)host.remove();
}
