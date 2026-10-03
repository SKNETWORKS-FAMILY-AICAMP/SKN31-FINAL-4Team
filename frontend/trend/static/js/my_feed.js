import { $, $$, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';
import { IMG, STYLES } from '../../../home/static/js/chat.js';

/* ── 금주의 리포트 데이터 ──
   실제로 셀 수 없는 것(판단 적중률 · 아낀 돈 · 재고 변화 · 내 결정이 옳았는지)은
   전부 뺐다. 대신 이 사람이 사이트에서 실제로 한 행동 — 무엇을 검색했고,
   무엇에 투표했고, 어떤 스타일을 오래 봤는지 — 그 로그만으로 채운다. */
export const WK={
  updateDay:'일요일',                 /* 지표는 매주 이 요일에 갱신된다 */
  /* 이번 주 가장 많이 검색·투표한 스타일 — 리포트 전체가 이 스타일을 중심으로 짜인다 */
  topStyle:'block',
  topSearchN:14, topVoteN:5,
  search:34, searchD:11, fav:5, favTotal:23, vote:12, voteD:4,
  /* 트렌드 분석 — 이번 주 챗봇 사용 시간(분) 합계와 1회 평균(분) */
  chatMin:76, chatAvgMin:4.2,
  days:[6,11,9,14,21,17,8], today:'수', bestDay:'금', peak:'21시 – 23시',
  taste:[['발레코어',42,6],['아메카지',28,-3],['워크웨어',18,2],['고프코어',12,5]],
  newTaste:'고프코어'
  /* 추천 웹매거진은 목업 목록 대신 /api/v1/magazines(웹 검색)로 기사를 찾는다 — dispatch.js wkMagLoad */
};

/* ── 내 피드 · 살!말? 취향 매칭 큐레이션 ────────────────────────
 *
 * ★ 2026-09-18 — 목업 JSON을 끊고 살!말? 본 화면과 같은 API를 읽는다.
 *
 *   전에는 `salmal/data/youtube_salmal_cards.json` 을 import 해서 썼다.
 *   그 파일은 유튜브 댓글에서 뽑은 **고정값**이라, 같은 상품인데도
 *   살!말? 페이지(실제 투표)는 62%, 내 피드(JSON)는 100% 로 갈렸다.
 *   이제 둘 다 `/api/salmal/cards` 하나만 본다.
 *
 *   ★ 값이 없으면 지어내지 않는다. API가 실패하면 카드를 그리지 않고
 *     왜 못 그렸는지를 말한다(dispatch.js 의 salmalGridHTML).
 */
const SALMAL_API='/api/salmal/cards?tab=latest';
let FEED_SM_CACHE=null;      /* 성공한 목록 — 탭을 오갈 때 다시 부르지 않는다 */
/* 계정이 바뀌면 '내 투표'가 섞이지 않게 버린다 (2026-09-19) */
document.addEventListener('feedit:auth',()=>{ FEED_SM_CACHE=null; });

function smCardFromApi(card,seq){
  const summary=card.vote_summary||{};
  const similar=card.similar_user_summary||{};
  return {
    t:card.title,
    b:card.brand||'브랜드 미확인',
    p:card.price,
    votes:summary.total||0,
    hours:card.hours_remaining,
    a:summary.buy_pct??50,
    tone:['#302d2b','#6e6660'],
    st:Array.isArray(card.style_tags)?card.style_tags:[],
    cat:card.category||'',
    imgURL:card.image_url,
    catalogId:card.product_source_id??card.id,
    /* 나와 비슷한 사용자들 — 표본이 없으면 has_sample:false 다.
       그때 비율(simPct)은 null 이고, 화면은 숫자 대신 이유를 쓴다. */
    simHas:Boolean(similar.has_sample),
    simPct:similar.has_sample?similar.buy_pct:null,
    simUsers:similar.sample_users||0,
    simReason:similar.reason||'',
    tasteHits:Array.isArray(card.taste_match_tags)?card.taste_match_tags:[],
    seq,
    closed:Boolean(card.closed)
  };
}

/** 살!말? 카드 목록을 한 번만 불러 온다. 실패하면 이유를 담아 던진다. */
export async function feedSmLoad(){
  if(FEED_SM_CACHE)return FEED_SM_CACHE;
  const response=await fetch(SALMAL_API,
    {credentials:'same-origin',headers:{Accept:'application/json'}});
  /* 배포본에서 백엔드가 안 붙으면 여기로 HTML(404 페이지)이 온다.
     그대로 JSON.parse 하면 "Unexpected token '<'" 만 남아 원인을 못 찾는다. */
  const type=response.headers.get('content-type')||'';
  if(!type.includes('json'))
    throw new Error('살말 서버가 JSON을 주지 않았습니다 ('+response.status+').');
  const payload=await response.json();
  if(!response.ok||payload.status!=='ok')
    throw new Error(payload.reason||'살말 데이터를 불러오지 못했습니다.');
  const items=(payload.data&&payload.data.items)||[];
  const cards=items.map(smCardFromApi).filter(card=>!card.closed);
  /* 같은 상품은 한 번만 둔다 */
  FEED_SM_CACHE=[...new Map(cards.map(card=>[card.catalogId,card])).values()];
  return FEED_SM_CACHE;
}

/* 내 취향 태그(STYLES id)와 카드 태그를 맞춘다.
   카드 태그는 DB 에 한글 이름('클래식')으로 들어갈 수도, id('classic')로
   들어갈 수도 있어 양쪽을 다 본다. */
const styleLabel=id=>(STYLES.find(s=>s.id===id)||{}).n||id;
function cardHits(card,ids){
  const wanted=new Set();
  ids.forEach(id=>{ wanted.add(id); wanted.add(styleLabel(id)) });
  return card.st.filter(tag=>wanted.has(tag));
}

/* 고른 스타일 순서대로 한 장씩 돌아가며 뽑는다 — 한 스타일이 4장을 독차지하지 않게.
   각 스타일 안에서는 투표가 많은 카드부터. 맞는 카드가 모자라면 인기순으로 채우되
   그 카드에는 '일치' 표시를 붙이지 않는다(맞지 않는 것을 맞는다고 쓰지 않는다). */
export function feedSmPicks(styleIds,pool){
  const cards=pool||FEED_SM_CACHE||[];
  if(!cards.length)return [];
  const ids=STYLES.map(s=>s.id).filter(id=>styleIds.has(id)).slice(0,3);
  const byVotes=cards.slice().sort((x,y)=>y.votes-x.votes);
  const used=new Set(), out=[];
  for(let round=0; out.length<4 && round<cards.length; round++){
    let added=false;
    for(const id of ids){
      if(out.length>=4)break;
      const want=new Set([id,styleLabel(id)]);
      const c=byVotes.find(o=>!used.has(o)&&o.st.some(tag=>want.has(tag)));
      if(c){ used.add(c); out.push(c); added=true }
    }
    if(!added)break;
  }
  for(const o of byVotes){ if(out.length>=4)break; if(!used.has(o)){ used.add(o); out.push(o) } }
  return out.map(o=>{
    const hit=cardHits(o,ids);
    const main=hit[0]||o.st[0]||o.cat;
    const tags=[
      {tx:'#'+styleLabel(main), hit:hit.length>0},
      {tx:'#'+(o.cat||o.b), hit:false},
      {tx:'#'+styleLabel(hit[1]||o.st.find(s=>s!==main)||o.b), hit:hit.length>1}
    ].filter(t=>t.tx!=='#');
    return Object.assign({},o,{
      title:o.t,
      itemTag:hit.map(styleLabel).join(' · ')||styleLabel(main),
      matched:hit.length>0,
      tags
    });
  });
}

/* ── 내 피드 추천 풀 ──
   태그는 필터 칩과 같은 말을 쓴다. risk 는 0(무난) ~ 100(실험). */
const MF_TAGS=['발레코어','아메카지','캐주얼','포멀','고프코어','워크웨어',
               '페미닌','미니멀','스트릿','프레피','시티보이','올드머니'];
const MF_POOL=[
  {b:'ANDERSSON BELL', n:'스웨이드 블루종 자켓', p:329000, img:1,  t:['워크웨어','올드머니'],  r:72, m:96},
  {b:'INSILENCE',      n:'램스울 라운드 니트',   p:118000, img:14, t:['미니멀','프레피'],      r:18, m:93},
  {b:'SOLEW',          n:'와이드 코듀로이 팬츠', p:139000, img:7,  t:['아메카지','캐주얼'],    r:34, m:91},
  {b:'RANDOM IDENT.',  n:'스퀘어 토 페니 로퍼',  p:268000, img:19, t:['포멀','프레피'],        r:44, m:88},
  {b:'MUSINSA STANDARD',n:'옥스퍼드 셔츠',       p:39900,  img:11, t:['미니멀','포멀'],        r:8,  m:86},
  {b:'DE PAUL',        n:'헤비 스웻 후디',       p:89000,  img:8,  t:['스트릿','캐주얼'],      r:26, m:84},
  {b:'MIU MIU',        n:'리본 크롭 캐미솔',     p:790000, img:2,  t:['발레코어','페미닌'],    r:92, m:83},
  {b:'ARC\'TERYX',     n:'감마 SL 셸 자켓',      p:412000, img:23, t:['고프코어'],             r:66, m:81},
  {b:'CARHARTT WIP',   n:'디트로이트 자켓',      p:298000, img:5,  t:['워크웨어','아메카지'],  r:38, m:79},
  {b:'THISISNEVERTHAT',n:'나일론 카고 팬츠',     p:129000, img:27, t:['스트릿','고프코어'],    r:58, m:77},
  {b:'POLO RALPH L.',  n:'클래식 피케 셔츠',     p:149000, img:19, t:['프레피','시티보이'],    r:14, m:75},
  {b:'LEMAIRE',        n:'크로아상 백',          p:1290000,img:30, t:['미니멀','올드머니'],    r:88, m:74},
  {b:'ADIDAS',         n:'삼바 OG',              p:139000, img:12, t:['블록코어','스트릿'],    r:30, m:73},
  {b:'UNIQLO',         n:'와이드 치노',          p:49900,  img:16, t:['캐주얼','시티보이'],    r:6,  m:71},
  {b:'LEVI\'S',        n:'501 오리지널',         p:118000, img:21, t:['아메카지','캐주얼'],    r:12, m:70},
  {b:'ADER ERROR',     n:'디스트로이드 니트',    p:259000, img:25, t:['스트릿'],               r:80, m:68}
];
var MF={tags:['발레코어','아메카지','워크웨어'],risk:22};

/* 필터를 반영해 오른쪽 두 칸만 다시 짠다 */
function mfPick(){
  const t=MF.tags;
  const scored=MF_POOL.map(o=>{
    const tagHit=t.length?o.t.filter(x=>t.indexOf(x)>=0).length:0;
    /* 태그가 맞을수록, 성향 슬라이더와 가까울수록 위로 */
    const near=1-Math.abs(o.r-MF.risk)/100;
    return {o,s:tagHit*2.2+near*1.6+o.m/100};
  }).sort((a,b)=>b.s-a.s);
  const top=scored.filter(x=>!t.length||x.o.t.some(y=>t.indexOf(y)>=0));
  const pick=(top.length?top:scored).slice(0,4);
  /* 매칭도는 고정값이 아니라 지금 조건에서의 점수다 — 항상 내림차순으로 읽힌다 */
  const hi=pick.length?pick[0].s:1;
  return {
    rec:pick.map((x,i)=>Object.assign({},x.o,
      {mm:Math.max(64,Math.min(98,Math.round(96-(hi-x.s)*4.6-i*0.8)))})),
    safe:MF_POOL.slice().sort((a,b)=>a.r-b.r).slice(0,4)      /* 성향과 무관한 기본템 */
  };
}
function mfCard(o,tag,accent){
  const st=MF_TAGS.filter(x=>o.t.indexOf(x)>=0)[0]||o.t[0];
  return '<div class="pItem">'+
    '<span class="tg'+(accent?' c':'')+'">'+tag+'</span>'+
    '<span class="im"><img src="'+IMG(o.img)+'" alt="" loading="lazy"></span>'+
    '<span class="tx"><u>'+o.b+'</u><b>'+o.n+'</b>'+
      '<s>'+o.p.toLocaleString()+'원</s>'+
      '<span class="why">'+(accent?'저장하신 '+st+'와 같은 흐름':'실패 확률이 낮은 기본 아이템')+'</span>'+
    '</span></div>';
}
function mfPaint(){
  const host=$('#mfRight'); if(!host)return;
  const {rec,safe}=mfPick();
  const tagTx=MF.tags.length?MF.tags.join(' · '):'전체';
  host.innerHTML=
    '<div class="mfSec"><div class="ph"><h3>오늘의 추천</h3>'+
      '<em>'+tagTx+' · 매칭도 순</em></div>'+
      (rec.length?'<div class="mfGrid">'+rec.map(o=>mfCard(o,'매칭 '+o.mm+'%',1)).join('')+'</div>'
        :'<div class="mfEmpty">고른 조건에 맞는 것이 없습니다.<br>스타일을 하나 더 풀어보세요.</div>')+
    '</div>'+
    '<div class="mfSec"><div class="ph"><h3>무난템 · 국밥템</h3>'+
      '<em>실패 확률이 낮은 기본 아이템</em></div>'+
      '<div class="mfGrid">'+safe.map((o,i)=>mfCard(o,i%3?'국밥템':'무난템',0)).join('')+'</div>'+
    '</div>';
  if(HAS_A)aAnimate($$('#mfRight .pItem'),{opacity:[0,1],translateY:[14,0],
    duration:620,delay:aStagger(46),ease:'out(3)'});
}
