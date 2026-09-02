import { $, $$, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';
import { IMG } from '../../../home/static/js/chat.js';

/* ── 금주의 리포트 데이터 ──
   시장 지표가 아니라 이 사람의 한 주다. 내가 뭘 했고, 그게 맞았나. */
export const WK={
  range:'2026 · W33 · 8/13 – 8/19',
  hit:78,                     /* 판단 적중률 — 참을 것/살 것을 얼마나 맞췄나 */
  saved:214500, missed:2, decided:9, streak:6,
  /* 최근 6주 아낀 돈 — 이 서비스를 계속 쓸 이유를 숫자로 보여준다 */
  savedHist:[86000,41000,132000,98000,176000,214500],
  savedTotal:747500, planMonths:7.2, planMonthsAll:24.9,
  /* 놓친 2건이 왜 놓쳤나 — 다음 주 행동으로 이어지는 분해 */
  missReason:[['재고 소진',78],['가격 반등',14],['판단 지연',8]],
  percentile:12, peerGap:63400,
  note:'가격 판단은 안정적이었습니다. 다음 주의 개선 포인트는 <b>“가격보다 먼저 움직이는 재고 신호”</b>입니다.',
  noteTag:'NEXT ACTION · STOCK ALERT',
  search:34, searchD:11, fav:5, favTotal:23, vote:12, voteHit:83, read:18, readMin:4.2,
  days:[6,11,9,14,21,17,8], today:'수', bestDay:'금', peak:'21시 – 23시',
  taste:[['발레코어',42,6],['아메카지',28,-3],['워크웨어',18,2],['고프코어',12,5]],
  newTaste:'고프코어',
  /* 내가 내린 결정과 그 뒤에 실제로 벌어진 일 */
  log:[
    {act:'미룸', k:"ARC'TERYX 감마 SL 셸", when:'8/14 참기 선택',
     res:'−12% · 412,000 → 362,500원', badge:'safe',
     msg:'잘 참았습니다. 지금 사면 49,500원을 덜 냅니다. 할인 초반이라 한 주 더 볼 여지도 있습니다.'},
    {act:'찜', k:'스투시 8볼 후디', when:'8/15 찜',
     res:'M · L 사이즈 품절', badge:'danger',
     msg:'가격이 아니라 재고가 먼저 빠졌습니다. 이런 아이템은 재입고 알림을 함께 걸어두는 편이 낫습니다.'},
    {act:'구매', k:'아디다스 삼바 OG', when:'8/16 구매',
     res:'+3% 정가 인상', badge:'safe',
     msg:'구매 직후 정가가 올랐습니다. 수명주기 확산 구간에서 산 것이 맞았습니다.'},
    {act:'미룸', k:'미우미우 발레 플랫', when:'8/12 참기 선택',
     res:'변동 없음', badge:'warn',
     msg:'아직 움직임이 없습니다. 정점 구간이라 할인보다 품절이 먼저 올 수 있어 지켜보는 중입니다.'},
    {act:'찜', k:'디스이즈네버댓 나일론 카고', when:'8/17 찜',
     res:'수명주기 정점 진입', badge:'danger',
     msg:'정점에 들어섰습니다. 오래 입을 생각이라면 지금 담기보다 다음 것을 보시는 편이 낫습니다.'}
  ],
  /* 찜해둔 것 중 이번 주에 상태가 바뀐 것만 */
  watch:[
    ['고프코어','할인률 +9%p (평균 24% → 33%)',1,'지금이 매수 구간'],
    ['발레코어','트렌드 온도 −7° (89 → 82)',0,'정점 통과 · 신규 구매 보류'],
    ['스투시','재고 소진 속도 2.1배',0,'재입고 알림 설정'],
    ['새틴','연관어 12건 신규 진입',1,'확산 초반 · 계속 추적'],
    ['카고 팬츠','리세일 지수 −0.08',0,'되팔 계획이면 이번 달 안'],
  ],
  /* 다음 주 예고 */
  next:[
    ['고프코어','D+3','할인률이 최대치에 근접합니다. 다음 주 중반이 이번 사이클의 바닥일 가능성이 높습니다.'],
    ['포엣코어','D+5','태동 구간에서 확산으로 넘어가는 신호가 잡혔습니다. 선점하려면 지금이 마지막 조용한 구간입니다.'],
    ['발레 플랫','D+6','재입고 주기상 다음 주 후반에 물량이 풀립니다. 알림을 걸어두세요.']
  ]
};

/* ── 내 피드 · 살!말? 취향 매칭 큐레이션 ────────────────────────
   살!말? 페이지의 VOTES는 salmalBoot() 함수 안에 갇힌 지역 변수라 다른
   곳에서 참조할 수 없다 — 여기서는 그 "내 취향" 탭(취향 매칭도 순
   정렬) 기준 상위 4개와 정확히 같은 값을 옮겨 적었다. 이렇게 해야 내
   피드에서 본 카드를 살!말?에서 다시 검색할 필요 없이 그대로 찾을 수
   있다. VOTES 쪽 데이터가 바뀌면 이 배열도 같이 맞춰야 한다. */
export const FEED_SM_PICKS=[
  {t:'삼바 OG', b:'ADIDAS', p:139000, votes:2210, hours:3, a:88, tone:['#2f2b2b','#726358'],
   seg:94,itemTag:'블록코어 · 스니커',
   title:'삼바 OG',
   tags:['#블록코어','#스니커','#스트릿']},
  {t:'스웨이드 블루종 (버건디)', b:'ANDERSSON BELL', p:329000, votes:842, hours:6, a:81, tone:['#3a332f','#6b5c52'],
   seg:90,itemTag:'워크웨어 · 아우터',
   title:'스웨이드 블루종 (버건디)',
   tags:['#워크웨어','#아우터','#올드머니']},
  {t:'스퀘어 토 로퍼', b:'RANDOM IDENTITIES', p:268000, votes:1104, hours:24, a:73, tone:['#2b2b2b','#585858'],
   seg:89,itemTag:'아메카지 · 로퍼',
   title:'스퀘어 토 로퍼',
   tags:['#아메카지','#로퍼','#캐주얼']},
  {t:'캐시미어 머플러', b:'LE 17 SEPTEMBRE', p:98000, votes:602, hours:5, a:71, tone:['#2e2a2c','#5c5459'],
   seg:87,itemTag:'워크웨어 · 아메카지',
   title:'캐시미어 머플러',
   tags:['#워크웨어','#아메카지','#머플러']}
];

/* ── 내 피드 추천 풀 ──
   태그는 필터 칩과 같은 말을 쓴다. risk 는 0(무난) ~ 100(실험). */
const MF_TAGS=['발레코어','아메카지','캐주얼','포멀','고프코어','워크웨어',
               'Y2K','미니멀','스트릿','프레피','시티보이','올드머니'];
const MF_POOL=[
  {b:'ANDERSSON BELL', n:'스웨이드 블루종 자켓', p:329000, img:1,  t:['워크웨어','올드머니'],  r:72, m:96},
  {b:'INSILENCE',      n:'램스울 라운드 니트',   p:118000, img:14, t:['미니멀','프레피'],      r:18, m:93},
  {b:'SOLEW',          n:'와이드 코듀로이 팬츠', p:139000, img:7,  t:['아메카지','캐주얼'],    r:34, m:91},
  {b:'RANDOM IDENT.',  n:'스퀘어 토 페니 로퍼',  p:268000, img:19, t:['포멀','프레피'],        r:44, m:88},
  {b:'MUSINSA STANDARD',n:'옥스퍼드 셔츠',       p:39900,  img:11, t:['미니멀','포멀'],        r:8,  m:86},
  {b:'DE PAUL',        n:'헤비 스웻 후디',       p:89000,  img:8,  t:['스트릿','캐주얼'],      r:26, m:84},
  {b:'MIU MIU',        n:'리본 크롭 캐미솔',     p:790000, img:2,  t:['발레코어','Y2K'],       r:92, m:83},
  {b:'ARC\'TERYX',     n:'감마 SL 셸 자켓',      p:412000, img:23, t:['고프코어'],             r:66, m:81},
  {b:'CARHARTT WIP',   n:'디트로이트 자켓',      p:298000, img:5,  t:['워크웨어','아메카지'],  r:38, m:79},
  {b:'THISISNEVERTHAT',n:'나일론 카고 팬츠',     p:129000, img:27, t:['스트릿','고프코어'],    r:58, m:77},
  {b:'POLO RALPH L.',  n:'클래식 피케 셔츠',     p:149000, img:19, t:['프레피','시티보이'],    r:14, m:75},
  {b:'LEMAIRE',        n:'크로아상 백',          p:1290000,img:30, t:['미니멀','올드머니'],    r:88, m:74},
  {b:'ADIDAS',         n:'삼바 OG',              p:139000, img:12, t:['블록코어','스트릿'],    r:30, m:73},
  {b:'UNIQLO',         n:'와이드 치노',          p:49900,  img:16, t:['캐주얼','시티보이'],    r:6,  m:71},
  {b:'LEVI\'S',        n:'501 오리지널',         p:118000, img:21, t:['아메카지','캐주얼'],    r:12, m:70},
  {b:'ADER ERROR',     n:'디스트로이드 니트',    p:259000, img:25, t:['스트릿','Y2K'],         r:80, m:68}
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
