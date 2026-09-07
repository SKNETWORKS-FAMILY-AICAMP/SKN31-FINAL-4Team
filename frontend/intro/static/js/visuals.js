import { $, $$, A, HAS_A, aAnimate, aDrawable, aSpring, aStagger, aTimeline, aUtils } from '../../../core/static/js/dom.js';
import { GAP_W, running, slot } from './loader.js';

/* ============================================================
   패널 비주얼
   ============================================================ */
/* 01 화보 — q1~q4(=f33·f08·f34·f35) + x1~x4(=g05~g08) */
const SHOT_A=['f33','f08','f34','f35','g05','g06','g07','g08'];
/* 05 화보 — 흑백·무채색 무드만 남긴다. 컬러가 튀는 컷(f09 f05 f17 f25)은 전부 뺐다.
   앞 넷은 무채색, 뒤 둘(f04 f30)은 어둡게 눌린 컷.
   밝은 컷과 어두운 컷이 번갈아 오도록 순서를 짰다. */
const SHOT_B=['f22','f04','f28','f31','f12','f30'];
/* 04 아이템 — 사진이 준비되면 img 경로만 갈아끼우면 된다 */
/* 04 DECIDE 에서 한 장씩 넘어가는 아이템 — 실제 상품 사진을 쓴다 */
const ITEMS=[
  {n:'AIR FORCE 1 · 07',   b:'NIKE',     img:'assets/item/airforce.jpg'},
  {n:'STORM RIDER 101J',   b:'LEE',      img:'assets/item/denim_jacket.jpg'},
  {n:'HARRINGTON BLOUSON', b:'ETCE',     img:'assets/item/blouson.jpg'},
  {n:'SHORT PUFFER',       b:'ANDERSSON',img:'assets/item/puffer.jpg'},
  {n:'CLASSIC BALL CAP',   b:'POLO',     img:'assets/item/ballcap.jpg'}
];
/* ── 02 COLLECT — 폰 한 대 안에서 앱이 지나가고, 홈으로 나갔다가
   FEEDiT 아이콘을 눌러 들어간다. 상태바·아일랜드·홈바는 계속 남는다.
   ──────────────────────────────────────────────────────────── */
const IMGF=n=>'assets/hi/f'+String(n).padStart(2,'0')+'.jpg';
const TAB=(a,b,c,e)=>'<div class="tabBar"><i class="'+a+'"></i><i class="'+b+'"></i>'+
  '<i class="'+c+'"></i><i class="'+e+'"></i></div>';
const VROW=(n,t,v)=>'<div class="vRow"><u><img src="'+IMGF(n)+'" alt=""></u>'+
  '<div><b>'+t+'</b><span>'+v+'</span></div></div>';
const NROW=(n,t,p,r)=>'<div class="nRow"><img src="'+IMGF(n)+'" alt=""><div><b>'+t+'</b>'+
  '<span class="nP">'+p+'<em>원</em></span><span class="nS">리뷰 '+r+'</span></div></div>';
const MCARD=(n,t,p)=>'<div class="pCard"><img src="'+IMGF(n)+'" alt=""><b>'+t+'</b><span>'+p+'</span></div>';

/* iOS 홈 화면 */
/* 클래스에 a- 접두사를 붙인다. ph · mu 같은 짧은 이름은 다른 규칙과 부딪힌다. */
const HOME_APPS=[
  {k:'a-yt', n:'YouTube'},  {k:'a-ig',n:'Instagram'},{k:'a-mu',n:'무신사'}, {k:'a-nv',n:'네이버'},
  {k:'a-fe', n:'FEEDiT', me:1},{k:'a-tt',n:'TikTok'},{k:'a-zz',n:'지그재그'},{k:'a-ph',n:'사진'},
  {k:'a-mp', n:'지도'},     {k:'a-mu2',n:'음악'},    {k:'a-nt',n:'메모'},   {k:'a-st',n:'설정'}
];
const DOCK=[{k:'a-ph2'},{k:'a-mg'},{k:'a-sf'},{k:'a-mu3'}];
/* FEEDiT 아이콘은 로고를 그대로 새긴다 (의사요소로 그리면 어긋난다) */
const FE_ICON='<svg viewBox="29 27 64 64" aria-hidden="true">'+
  '<path d="M88 32V80C88 84.4183 84.4183 88 80 88H32V32H88Z" fill="none" stroke="#0a0a0a" stroke-width="4"/><path d="M49.8546 77V42.92H71.9826V47.672H52.3026L55.0386 44.84V60.488L52.3026 58.04H71.1186V62.648H52.3026L55.0386 60.2V77H49.8546Z" fill="#0a0a0a"/><path d="M91 29V39H81V29H91Z" fill="#ff6b4a" stroke="#f1efea" stroke-width="2"/></svg>';
const HOME_HTML=
  '<div class="iosHome">'+
    '<div class="wall"></div>'+
    '<div class="grid">'+HOME_APPS.map(a=>
      '<span class="ic '+a.k+(a.me?' me':'')+'">'+
      '<u>'+(a.me?FE_ICON:'')+'</u><em>'+a.n+'</em></span>').join('')+'</div>'+
    '<div class="dock">'+DOCK.map(a=>'<span class="ic '+a.k+'"><u></u></span>').join('')+'</div>'+
    '<span class="tapRing"></span>'+
  '</div>';

/* FEEDiT — 모바일 전용. 가운데 챗바 하나, 위에 문구, 아래 로고. */
const FE_MIN=
  `<div class="feLoad"><span class="feMark"><svg viewBox="29 27 64 64">
     <path d="M88 32V80C88 84.4183 84.4183 88 80 88H32V32H88Z" fill="none" stroke="#0a0a0a" stroke-width="4"/><path d="M49.8546 77V42.92H71.9826V47.672H52.3026L55.0386 44.84V60.488L52.3026 58.04H71.1186V62.648H52.3026L55.0386 60.2V77H49.8546Z" fill="#0a0a0a"/><path d="M91 29V39H81V29H91Z" fill="#ff6b4a" stroke="#f1efea" stroke-width="2"/></svg></span></div>
   <div class="feWrap"><div class="feMin">
     <div class="feMinTx">스크롤 속 패션을,<br>하나의 <i>트렌드</i>로.</div>
     <div class="feBar"><span class="feSm">◑</span><span class="feQ">✧ “발레코어 아직 유효해?”</span>
       <span class="feGo">→</span></div>
     <div class="feMinLogo"><svg viewBox="29 27 64 64">
       <path d="M88 32V80C88 84.4183 84.4183 88 80 88H32V32H88Z" fill="none" stroke="#0a0a0a" stroke-width="4"/><path d="M49.8546 77V42.92H71.9826V47.672H52.3026L55.0386 44.84V60.488L52.3026 58.04H71.1186V62.648H52.3026L55.0386 60.2V77H49.8546Z" fill="#0a0a0a"/><path d="M91 29V39H81V29H91Z" fill="#ff6b4a" stroke="#f1efea" stroke-width="2"/></svg>
       <b>FEED<span class="dotI">ı<span class="tit"></span></span>T</b></div>
   </div></div>`;

const COLL=[
 {n:'YOUTUBE', html:
  `<div class="aTop yt"><span class="ytL"><i></i>YouTube</span><span class="dots3"></span></div>
   <div class="aBody">
     <div class="vThumb"><img src="${IMGF(2)}" alt=""><b>14:32</b></div>
     <div class="vTitle">이번 시즌 발레코어 총정리</div>
     <div class="vMeta"><i></i>STYLE ARCHIVE · 42만회</div>
     <div class="vSub"><i></i><span>구독자 24.8만</span><u>구독</u></div>
     ${VROW(11,'스웨이드 자켓 3만원대','19만회 · 2일 전')}
     ${VROW(5,'블록코어 데일리 룩북','8.4만회 · 5일 전')}
     ${VROW(13,'버건디 니트 코디 7','5.2만회 · 1주 전')}
     ${VROW(9,'가을 셋업 실패 없는 법','3.9만회 · 2주 전')}
   </div>`+TAB('on','','','')},
 {n:'SHORTS', full:1, html:
  `<img class="full" src="${IMGF(11)}" alt="">
   <div class="fTop">Shorts</div>
   <div class="fSide"><b>♡<em>3.2만</em></b><b>◌<em>842</em></b><b>↗<em>공유</em></b><b>⋯<em></em></b></div>
   <div class="fCap"><b>@fitcheck.kr</b><span>가을 셋업 3분 룩북 #발레코어</span></div>`},
 {n:'INSTAGRAM', html:
  `<div class="aTop ig"><span class="igL">Instagram</span><span class="dots3"></span></div>
   <div class="aBody">
     <div class="stories"><u></u><u></u><u></u><u></u><u></u></div>
     <div class="post"><div class="pHead"><i></i>@quiet_wardrobe</div>
       <div class="pImg"><img src="${IMGF(5)}" alt=""></div>
       <div class="pAct"><i></i><i></i><i></i></div>
       <div class="pTx">좋아요 1,204개 · 스웨이드 자켓 어디 거예요?</div></div>
     <div class="igGrid"><u><img src="${IMGF(13)}" alt=""></u><u><img src="${IMGF(7)}" alt=""></u>
       <u><img src="${IMGF(4)}" alt=""></u><u><img src="${IMGF(15)}" alt=""></u>
       <u><img src="${IMGF(9)}" alt=""></u><u><img src="${IMGF(12)}" alt=""></u></div>
   </div>`+TAB('','on','','')},
 {n:'REELS', full:1, html:
  `<img class="full" src="${IMGF(13)}" alt="">
   <div class="fTop">Reels</div>
   <div class="fSide"><b>♡<em>5.1만</em></b><b>◌<em>1.2천</em></b><b>↗<em>공유</em></b><b>⋯<em></em></b></div>
   <div class="fCap"><b>@seoul.layer</b><span>블록코어 데일리 · 삼바 코디</span></div>`},
 {n:'MUSINSA', html:
  `<div class="aTop mu"><span class="muL">MUSINSA</span><span class="dots3 lt"></span></div>
   <div class="aBody">
     <div class="muBan"><b>8월 시즌오프</b><span>최대 70%</span></div>
     <div class="tabs"><u class="on">랭킹</u><u>신상</u><u>세일</u><u>브랜드</u></div>
     <div class="pGrid">
       ${MCARD(4,'워크 자켓','129,000')}${MCARD(6,'셀비지 데님','159,000')}
       ${MCARD(8,'스웨이드 봄버','289,000')}${MCARD(9,'케이블 니트','98,000')}
       ${MCARD(12,'카고 팬츠','79,000')}${MCARD(15,'플리스 집업','119,000')}
     </div>
   </div>`+TAB('','','on','')},
 {n:'NAVER', html:
  `<div class="aTop nv"><span class="nvL">N</span><span class="nvS">스웨이드 자켓</span></div>
   <div class="aBody">
     <div class="tabs nvT"><u class="on">전체</u><u>랭킹순</u><u>낮은가격</u><u>리뷰많은</u></div>
     ${NROW(3,'스웨이드 오버 블루종','189,000',1284)}
     ${NROW(7,'미니멀 셋업 자켓','214,000',732)}
     ${NROW(14,'버건디 케이블 니트','96,000',2109)}
     ${NROW(18,'클래식 트렌치 코트','268,000',541)}
     ${NROW(10,'하프 더플 코트','179,000',890)}
   </div>`+TAB('','','','on')},
 {n:'HOME', home:1, html:HOME_HTML},
 {n:'FEEDiT', fee:1, html:FE_MIN}
];

function phoneBuild(stageId, capId){
  const stage=document.getElementById(stageId); if(!stage||stage.dataset.built)return;
  stage.dataset.built='1';
  stage.innerHTML=
    '<span class="halo"></span>'+
    '<div class="phone">'+
      '<div class="island"><i class="art"></i><i class="wave"><b></b><b></b><b></b><b></b></i></div>'+
      '<div class="status"><span>9:41</span><span class="sIco"><i></i><i></i><i></i></span></div>'+
      '<div class="screen">'+
        COLL.map((s,i)=>'<div class="app'+(s.full?' fullApp':'')+(s.fee?' feeApp':'')+
          (s.home?' homeApp':'')+(i?'':' on')+'" data-n="'+s.n+'">'+s.html+'</div>').join('')+
      '</div>'+
      '<span class="homebar"></span>'+
    '</div>';

  const cap=document.getElementById(capId);
  const phone=$('.phone',stage), bar=$('.homebar',stage), halo=$('.halo',stage);
  const scr=$('.screen',stage), apps=$$('.app',stage);
  const HOME_I=COLL.findIndex(s=>s.home), FEE_I=COLL.findIndex(s=>s.fee);
  let i=0;
  const paint=()=>{ if(cap)cap.innerHTML='<b>'+COLL[i].n+'</b><span>'+
    String(i+1).padStart(2,'0')+'/'+String(COLL.length).padStart(2,'0')+'</span>' };
  paint();
  if(!HAS_A)return;

  aUtils.set(apps,{opacity:0,translateX:'0%',scale:1,borderRadius:'0px'});
  aUtils.set(apps[0],{opacity:1});
  const IOS=(A&&typeof A.cubicBezier==='function')?A.cubicBezier(.32,.72,0,1):'out(4)';
  const PW=()=>phone.getBoundingClientRect().width||250;
  const CARD=()=>Math.round(PW()*0.09)+'px';

  /* 아이콘 ↔ 전체화면 사이의 좌표 변환 */
  function iconGeo(icon){
    const sb=scr.getBoundingClientRect(), ib=icon.getBoundingClientRect();
    if(!sb.width||!ib.width)return {s:.2,x:0,y:0};
    return { s:ib.width/sb.width,
      x:(ib.left+ib.width/2)-(sb.left+sb.width/2),
      y:(ib.top+ib.height/2)-(sb.top+sb.height/2) };
  }

  /* 앱 → 홈 : 쓰던 앱이 아이콘 자리로 빨려 들어간다 */
  function toHome(cur,home){
    const icon=$('.ic.a-nv u',home)||$('.ic u',home);
    const g=iconGeo(icon);
    aUtils.set(home,{opacity:1,scale:1.1,translateX:'0%',translateY:0});
    aAnimate(home,{opacity:[0,1],scale:[1.1,1],duration:560,ease:IOS});
    aAnimate(cur,{scale:[1,g.s],translateX:[0,g.x],translateY:[0,g.y],
      borderRadius:['0px','18%'],opacity:[1,0],duration:600,ease:IOS,
      onComplete:()=>{ aUtils.set(cur,{opacity:0,scale:1,translateX:'0%',translateY:0,
        borderRadius:'0px'}) }});
    if(bar)aAnimate(bar,{keyframes:[{translateY:-6,scaleX:.7,duration:200,ease:'out(3)'},
      {translateY:0,scaleX:1,duration:420,ease:aSpring({stiffness:150,damping:14})}]});
  }

  /* 홈 → FEEDiT : 아이콘을 눌러 열린다 */
  function openFeedit(home,app){
    const icon=$('.ic.me u',home), ring=$('.tapRing',home);
    const g=iconGeo(icon);
    const t=aTimeline();
    if(ring){
      const sb=scr.getBoundingClientRect(), ib=icon.getBoundingClientRect();
      ring.style.left=(ib.left-sb.left+ib.width/2)+'px';
      ring.style.top=(ib.top-sb.top+ib.height/2)+'px';
      t.add(ring,{opacity:[0,.85,0],scale:[.3,2.1],duration:620,ease:'out(3)'},0);
    }
    t.add(icon,{keyframes:[{scale:.86,duration:130,ease:'out(2)'},
        {scale:1,duration:260,ease:aSpring({stiffness:180,damping:12})}]},0);
    aUtils.set(app,{opacity:0,scale:g.s,translateX:g.x,translateY:g.y,borderRadius:'18%'});
    t.add(app,{opacity:[0,1],scale:[g.s,1],translateX:[g.x,0],translateY:[g.y,0],
        borderRadius:['18%','0px'],duration:680,ease:IOS},300)
     .add(home,{scale:[1,1.14],opacity:[1,0],duration:520,ease:'in(2)',
        onComplete:()=>{ aUtils.set(home,{opacity:0,scale:1}) }},300);
    /* 1초 남짓 로고만 뜨는 로딩 후 챗 화면 */
    const ld=$('.feLoad',app), wr=$('.feWrap',app);
    if(ld&&wr){
      aUtils.set(ld,{opacity:1});
      aUtils.set($('.feMark',app),{opacity:0,scale:.82});
      aUtils.set(wr,{opacity:0,translateY:12});
      t.add($('.feMark',app),{opacity:[0,1],scale:[.82,1],duration:420,
          ease:aSpring({stiffness:110,damping:13})},560)
       .add(ld,{opacity:[1,0],duration:320,ease:'in(2)'},1560)
       .add(wr,{opacity:[0,1],translateY:[12,0],duration:560,
          ease:aSpring({stiffness:96,damping:16})},1660);
    }
    setTimeout(hit,1700);
  }

  const hit=()=>{
    phone.classList.add('hit');
    aAnimate(phone,{keyframes:[{scale:1.035,duration:260,ease:'out(2)'},
      {scale:1,duration:620,ease:aSpring({stiffness:130,damping:11})}]});
    aUtils.set(halo,{opacity:0,scale:.86});
    aAnimate(halo,{opacity:[0,.9,0],scale:[.86,1.24],duration:1600,ease:'out(3)'});
    setTimeout(()=>phone.classList.remove('hit'),3400);
  };

  /* 기본 전환 — 홈바를 옆으로 쓸어 다음 앱으로 */
  function swipe(cur,nxt){
    const cr=CARD();
    aUtils.set(nxt,{opacity:1,translateX:'104%',scale:.9,borderRadius:cr});
    const t=aTimeline();
    t.add(cur,{scale:[1,.9],borderRadius:['0px',cr],duration:210,ease:'out(3)'},0)
     .add(cur,{translateX:['0%','-104%'],duration:560,ease:IOS},210)
     .add(nxt,{translateX:['104%','0%'],duration:560,ease:IOS},210)
     .add(nxt,{scale:[.9,1],borderRadius:[cr,'0px'],duration:340,
        ease:aSpring({stiffness:124,damping:15})},700)
     .call(()=>{ aUtils.set(cur,{opacity:0,translateX:'0%',scale:1,borderRadius:'0px'}) },820);
    if(bar)t.add(bar,{keyframes:[
        {translateX:-15,scaleX:.6,duration:210,ease:'out(3)'},
        {translateX:15,scaleX:.6,duration:520,ease:IOS},
        {translateX:0,scaleX:1,duration:300,ease:aSpring({stiffness:150,damping:14})}
      ]},0);
  }

  const next=()=>{
    const cur=apps[i], ni=(i+1)%apps.length, nxt=apps[ni];
    let hold=1700;
    if(ni===HOME_I){ toHome(cur,nxt); hold=1500 }
    else if(ni===FEE_I){ openFeedit(cur,nxt); hold=5000 }
    else { swipe(cur,nxt); if(i===FEE_I)aUtils.set(cur,{opacity:0}) }
    i=ni; paint();
    setTimeout(next,hold);
  };
  setTimeout(next,1700);
}
function collBuild(){ phoneBuild('collStage','collCap') }

/* ── 03 ANALYZE — 우리 대시보드를 쓰는 장면 ─────────────────────
   커서가 사이드바를 하나씩 눌러 지표 화면을 갈아 끼운다.
   ──────────────────────────────────────────────────────────── */
/* 사이드바는 실제 트렌드 분석 화면(S_FEED · S_EDIT)과 같은 순서·같은 이름으로 둔다.
   앞 3개가 FEED, 뒤 6개가 EDIT — anzBuild 의 slice(0,3) / slice(3) 이 그대로 먹는다. */
const ANZ_SIDE=[
  {ic:'◧',t:'내 피드'},{ic:'◔',t:'금주의 리포트'},{ic:'♡',t:'찜한 키워드'},
  {ic:'◉',t:'언급량 · 온도'},{ic:'✳',t:'연관어'},{ic:'⇅',t:'긍부정'},
  {ic:'▤',t:'할인률 변화'},{ic:'◇',t:'리세일 시세 지수'},{ic:'◠',t:'수명주기'}
];
const K=(l,v,u,d,up)=>'<div class="zk"><span>'+l+'</span><b>'+v+(u?'<u>'+u+'</u>':'')+
  '</b><em class="'+(up?'up':'dn')+'">'+d+'</em></div>';
const BAR=(n,w,c,r)=>'<div class="zb"><span>'+n+'</span><u><i style="width:'+w+
  '%"'+(c?' class="c"':'')+'></i></u><em>'+r+'</em></div>';
/* 시연 화면 4장 — 실제 앱에서 지금 보이는 그대로를 축소해 옮겼다.
   FEED 두 장(내 피드 · 찜한 키워드)과 EDIT 두 장(언급량·온도 · 수명주기). */
const ANZ=[
 /* ── 내 피드 : 취향 브리핑 두 장 + 취향 맞춤 살!말? ── */
 {i:0, t:'내 피드', d:'취향 벡터와 최근 행동을 합쳐 오늘 볼 만한 것만 골랐습니다.',
  k:'',
  b:'<div class="zbrief">'+
      '<div class="zp zbig">'+
        '<span class="zlbl">TREND ALIGNMENT</span>'+
        '<div class="znum">84<i>°</i></div>'+
        '<b>내 관심 코어의 시장 화제성</b>'+
        '<p>블록코어와 아메카지가 동시에 상승 중입니다.</p>'+
        '<div class="zchips"><u class="on">블록코어</u><u class="on">아메카지</u>'+
          '<u>워크웨어</u><u>스트릿</u></div>'+
      '</div>'+
      '<div class="zp zdark">'+
        '<span class="zlbl">NEW SIGNALS DETECTED</span>'+
        '<div class="znum">14<i>signals</i></div>'+
        '<b>내 관심 키워드 관련 신규 신호</b>'+
        '<p>내 취향 태그와 직접 연결되는 변화만 추렸습니다.</p>'+
        '<div class="zchips"><u>블록코어 <s>+6</s></u><u>아메카지 <s>+4</s></u>'+
          '<u>워크웨어 <s>+3</s></u></div>'+
      '</div>'+
    '</div>'+
    '<div class="zp" style="margin-top:6px"><div class="zh"><b>내 취향 맞춤 살!말?</b>'+
      '<em>TOP 4</em></div><div class="zf zf4">'+
      [[11,'스웨이드 봄버','매치 96'],[7,'와이드 셀비지','매치 92'],
       [20,'모노 테일러드','매치 89'],[25,'케이블 니트','매치 87']]
      .map(c=>'<div class="zc"><img src="'+IMGF(c[0])+'" alt="">'+
        '<b>'+c[1]+'</b><span>'+c[2]+'</span></div>').join('')+
    '</div></div>'},

 /* ── 찜한 키워드 : 오늘의 이슈 히어로 ── */
 {i:2, t:'찜한 키워드', d:'찜해둔 것에 오늘 무슨 일이 있었는지부터 보여드립니다.',
  k:K('찜해둔 것','9','개','이번 주 +2',1)+K('오늘 움직인 것','7','건','어제 3건',1)+
    K('최저가 도달','1','건','알림 받음',1)+K('조용한 것','2','건','정리 후보',0),
  b:'<div class="zp zhero">'+
      '<div class="zshot"><img src="'+IMGF(20)+'" alt="">'+
        '<span>ETCE 모노 테일러드 자켓</span></div>'+
      '<div class="zhx">'+
        '<span class="zlbl">찜한 것 중에서 · 오늘</span>'+
        '<b>트렌드 지수 폭등</b>'+
        '<p>셋업 재킷 언급이 사흘 만에 2.4배가 됐습니다.<br>지금 사도 되는 구간입니다.</p>'+
        '<div class="zbar"><i style="width:91%"><u>트렌드 지수 91</u></i>'+
          '<em>지난주 대비 +29</em></div>'+
        '<div class="zacts"><u>수명주기에서 보기</u><u>살!말?에 올리기</u></div>'+
      '</div>'+
    '</div>'},

 /* ── 언급량 · 온도 : 판정 다이얼이 맨 위 ── */
 {i:3, t:'언급량 · 온도', d:'지금 얼마나 뜨거운지를 먼저 말하고, 근거를 아래에 깝니다.',
  k:K('트렌드 온도','82','°','+6° 이번 주',1)+K('플랫폼 점유율','4.8','%','+0.6%p',1)+
    K('전년 대비','+128','%','계절성 보정',1)+K('신규 진입','포엣코어','','이번 주 감지',1),
  b:'<div class="zg"><div class="zp zvd">'+
      '<svg class="zcv zdial" viewBox="0 0 96 96">'+
        '<circle class="zdt" cx="48" cy="48" r="40"/>'+
        '<path class="zdv" d="M48 8 A40 40 0 1 1 11.8 31"/></svg>'+
      '<div class="zvx"><b>발레코어는 지금 <s>뜨거움</s> 구간</b>'+
        '<p>언급량이 꾸준히 오르는 중입니다. 지금 붙잡을 만한 온도입니다.</p>'+
        '<div class="zs">'+['차가움','미지근','따뜻함','과열'].map((x,j)=>
          '<div'+(j===2?' class="on"':'')+'>'+x+'</div>').join('')+'</div></div>'+
    '</div>'+
    '<div class="zp"><div class="zh"><b>언급량 추이</b><em>일 · 주 · 월</em></div>'+
      '<div class="ztg"><u class="on">일별</u><u>주별</u><u>월별</u></div>'+
      '<svg class="zcv" viewBox="0 0 420 132"><line class="zx" x1="12" y1="112" x2="416" y2="112"/>'+
      '<path class="zl2" d="M12 100 C 70 96, 118 86, 168 72 S 268 40, 320 28 S 392 16, 416 12"/>'+
      '</svg></div></div>'},

 /* ── 수명주기 : 곡선 + 단계 ── */
 {i:8, t:'수명주기', d:'정점을 지난 시점과 남은 기간을 같이 봅니다.',
  k:K('추적 키워드','1,248','개','+62',1)+K('정점 통과','34','개','주의',0)+
    K('태동 감지','11','개','선점 구간',1)+K('평균 잔존','7.2','주','−0.8주',0),
  b:'<div class="zg"><div class="zp"><div class="zh"><b>수명주기 곡선</b><em>정점 이후 잔존</em></div>'+
    '<svg class="zcv" viewBox="0 0 420 150"><rect class="zn" x="266" y="6" width="150" height="122"/>'+
    '<line class="zx" x1="12" y1="128" x2="416" y2="128"/>'+
    '<path class="zl1" d="M12 122 C 82 118, 130 96, 172 66 S 240 14, 266 18"/>'+
    '<path class="zl2" d="M266 18 C 300 22, 328 54, 362 86 S 404 118, 416 122"/>'+
    '<circle class="zd" cx="266" cy="18" r="3.6"/></svg>'+
    '<div class="zs">'+['태동','확산','정점','쇠퇴'].map((s,j)=>
      '<div'+(j===2?' class="on"':'')+'>'+s+'</div>').join('')+'</div></div>'+
    '<div class="zp"><div class="zh"><b>키워드별 단계</b><em>지금</em></div><div class="zbs">'+
    BAR('포엣코어',14,0,'태동')+BAR('블록코어',62,0,'확산')+BAR('발레코어',96,1,'정점')+
    BAR('아메카지',58,0,'확산')+BAR('고프코어',34,1,'쇠퇴')+'</div></div></div>'}
];

var anzI=0, anzTimer=null;
function anzBuild(){
  const host=$('#anzStage'); if(!host||host.dataset.built)return;
  host.dataset.built='1';
  host.innerHTML=
    '<div class="win" id="anzWin">'+
      '<div class="wbar"><i></i><i></i><i></i><span>feedit.ai / trend</span></div>'+
      '<div class="wnav"><span class="wlogo"><svg viewBox="0 0 120 120">'+
        '<path d="M88 32V80C88 84.4183 84.4183 88 80 88H32V32H88Z" fill="none" stroke="#0a0a0a" stroke-width="4"/><path d="M49.8546 77V42.92H71.9826V47.672H52.3026L55.0386 44.84V60.488L52.3026 58.04H71.1186V62.648H52.3026L55.0386 60.2V77H49.8546Z" fill="#0a0a0a"/><path d="M91 29V39H81V29H91Z" fill="#ff6b4a" stroke="#f7f8fa" stroke-width="2"/></svg>'+
        '<b>FEED<span class="dotI">ı<span class="tit"></span></span>T</b></span>'+
        '<span class="wtabs"><u>홈</u><u class="on">트렌드 분석</u><u>살!말?</u><u>스타일</u></span></div>'+
      '<div class="wbody">'+
        '<aside class="zside" id="anzSide">'+
          '<span class="zlab">FEED</span>'+
          ANZ_SIDE.slice(0,3).map((s,j)=>'<button class="zi'+(j?'':' on')+'" data-j="'+j+'">'+
            '<i>'+s.ic+'</i><b>'+s.t+'</b></button>').join('')+
          '<span class="zlab">EDIT</span>'+
          ANZ_SIDE.slice(3).map((s,j)=>'<button class="zi" data-j="'+(j+3)+'">'+
            '<i>'+s.ic+'</i><b>'+s.t+'</b></button>').join('')+
        '</aside>'+
        '<div class="zmain"><div class="ztitle"><b id="anzT"></b><span id="anzD"></span></div>'+
          '<div class="ztabs"><u class="on">통합</u><u>무신사</u><u>지그재그</u><u>29CM</u></div>'+
          '<div class="zks" id="anzK"></div><div class="zbd" id="anzB"></div></div>'+
      '</div>'+
    '</div>'+
    '<span class="zcur" id="anzCur"><svg viewBox="0 0 20 24">'+
      '<path d="M2 1.5 L2 19 L6.6 14.6 L9.6 21.6 L12.6 20.3 L9.7 13.6 L16 13.4 Z" '+
      'fill="#0c1116" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>'+
      '<em class="ring"></em></span>';
  anzPaint(0);
  if(!HAS_A)return;
  anzTimer=setTimeout(anzStep,1400);
}

function anzPaint(n){
  const a=ANZ[n];
  $('#anzT').textContent=a.t; $('#anzD').textContent=a.d;
  $('#anzK').innerHTML=a.k;   $('#anzB').innerHTML=a.b;
  $$('#anzSide .zi').forEach(b=>b.classList.toggle('on',+b.dataset.j===a.i));
  /* 막대는 목표 폭을 기억해 두고 0 에서 채운다 — 히어로의 지수 막대도 같이 */
  const bars=$$('#anzB .zb i, #anzB .zbar i');
  if(HAS_A&&bars.length){
    const wv=bars.map(b=>b.style.width);
    aUtils.set(bars,{width:'0%'});
    aAnimate(bars,{width:(el,i)=>wv[i],duration:820,delay:aStagger(70,{start:180}),
      ease:aSpring({stiffness:70,damping:16})});
  }
  const lines=$$('#anzB .zcv path');
  if(HAS_A&&lines.length&&aDrawable){
    try{ const dr=aDrawable('#anzB .zcv path');
      aUtils.set(dr,{draw:'0 0'});
      aAnimate(dr,{draw:'0 1',duration:1000,delay:aStagger(200,{start:220}),ease:'inOut(2)'});
    }catch(e){}
  }
}

/* 커서가 항목으로 가서 누르고, 화면이 갈아 끼워진다 */
function anzStep(){
  const cur=$('#anzCur'), side=$('#anzSide');
  const ni=(anzI+1)%ANZ.length, tgt=ANZ[ni];
  const btn=$$('#anzSide .zi').filter(b=>+b.dataset.j===tgt.i)[0];
  if(!cur||!btn){ anzTimer=setTimeout(anzStep,2600); return }
  const hb=$('#anzStage').getBoundingClientRect(), bb=btn.getBoundingClientRect();
  const x=bb.left-hb.left+bb.width*0.62, y=bb.top-hb.top+bb.height*0.55;
  const t=aTimeline();
  t.add(cur,{opacity:[cur.style.opacity||0,1],translateX:x,translateY:y,
      duration:720,ease:aSpring({stiffness:64,damping:17})},0)
   /* 클릭 */
   .add(cur,{keyframes:[{scale:.84,duration:110,ease:'out(2)'},
      {scale:1,duration:280,ease:aSpring({stiffness:180,damping:12})}]},760)
   .add('#anzCur .ring',{opacity:[.7,0],scale:[.4,2.2],duration:620,ease:'out(3)'},760)
   /* 화면 교체 */
   .add('#anzStage .zmain',{opacity:[1,0],translateY:[0,10],duration:240,ease:'in(2)',
      onComplete:()=>{ anzI=ni; anzPaint(ni) }},860)
   .add('#anzStage .zmain',{opacity:[0,1],translateY:[10,0],duration:520,
      ease:aSpring({stiffness:96,damping:16})},1120);
  anzTimer=setTimeout(anzStep,3200);
}

let shotTimers=[];

export function buildVisuals(){
  /* ── 01 · 05 화보 배경 ── */
  [['a',SHOT_A],['b',SHOT_B]].forEach(([key,set])=>{
    const box=document.querySelector('.ph[data-shots="'+key+'"]');
    if(!box||box.dataset.built)return; box.dataset.built='1';
    const els=set.map(f=>{
      const im=document.createElement('img');
      im.src='assets/hi/'+f+'.jpg'; im.alt=''; im.decoding='async';
      box.appendChild(im); return im;
    });
    let i=0;
    const show=()=>{
      const cur=els[i], nxt=els[(i+1)%els.length];
      if(HAS_A){
        aAnimate(nxt,{opacity:[0,1],scale:[1.12,1.02],duration:2600,ease:'out(2)'});
        aAnimate(cur,{opacity:[1,0],duration:2000,ease:'inOut(2)'});
      }else{els.forEach((e,k)=>e.style.opacity=k===(i+1)%els.length?1:0)}
      i=(i+1)%els.length;
    };
    if(HAS_A)aUtils.set(els[0],{opacity:1,scale:1.02});
    else els[0].style.opacity=1;
    shotTimers.push(setInterval(show,3400));
  });

  /* ── 02 화면 슬라이드 ── */
  collBuild();

  /* ── 03 대시보드 시연 ── */
  anzBuild();

  /* ── 04 아이템 ── */
  const it=$('#itm');
  if(it&&!it.dataset.built){
    it.dataset.built='1';
    const els=ITEMS.map((o,k)=>{
      const d=document.createElement('div');
      d.className='item';
      d.innerHTML='<img src="'+o.img+'" alt="" decoding="async">'+
        '<span class="tag"><b>'+o.n+'</b><span>'+o.b+'</span></span>';
      it.appendChild(d); return d;
    });
    if(HAS_A)aUtils.set(els[0],{opacity:1,scale:1});
    else els[0].style.opacity=1;
    let i=0;
    shotTimers.push(setInterval(()=>{
      const cur=els[i], nxt=els[(i+1)%els.length];
      if(HAS_A){
        aAnimate(nxt,{opacity:[0,1],translateX:[46,0],scale:[.97,1],
          duration:900,ease:aSpring({stiffness:78,damping:14})});
        aAnimate(cur,{opacity:[1,0],translateX:[0,-40],scale:[1,.97],
          duration:760,ease:'in(2)'});
      }else{els.forEach((e,k)=>e.style.opacity=k===(i+1)%els.length?1:0)}
      i=(i+1)%els.length;
    },2800));
  }
}

/* 리사이즈 시 슬롯 폭 보정 */
addEventListener('resize',()=>{ if(running&&slot.style.width!=='0px'&&parseFloat(slot.style.width)>1)
  slot.style.width=GAP_W()+'px'; });
