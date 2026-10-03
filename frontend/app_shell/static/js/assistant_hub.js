/* 전 페이지 도움말 허브.
 * 기존 챗봇·트렌드·스타일 구현은 건드리지 않고 공개 진입 함수만 호출한다.
 * 화면 가이드는 alpha.js 와 분리해, 알파 계정 여부와 무관하게 사용할 수 있다. */
import { goView, trSideOpen } from './router.js';
import { openChatWith } from '../../../home/static/js/chat_popup.js';
import { trRender } from '../../../trend/static/js/dispatch.js';
import { KW } from '../../../trend/static/js/render_helpers.js';
import { installGuideDemo, sentimentUrl } from '../../../trend/static/js/live_data.js';
import { openDictionaryGuideDemo, closeDictionaryGuideDemo } from '../../../trend/static/js/dict_popup.js';
import {
  mountSalmalGuideDemo, showSalmalGuideFeed, showSalmalGuideDetail, showSalmalGuideCreate,
} from '../../../salmal/static/js/guide_demo.js';
import {
  FS, fsReset, fsStockSelect, fsResaleSelect, fsOpenGuidePop, fsCloseGuidePop, fsPaintPop,
} from '../../../style/static/js/search.js';
import tempDemo from '../../../trend/static/demo/temp.json' with { type:'json' };
import assocDemo from '../../../trend/static/demo/assoc.json' with { type:'json' };
import sentimentDemo from '../../../trend/static/demo/sentiment.json' with { type:'json' };
import lifeDemo from '../../../trend/static/demo/life.json' with { type:'json' };
import stockDemo from '../../../trend/static/demo/stock.json' with { type:'json' };
import resaleDemo from '../../../trend/static/demo/resale.json' with { type:'json' };

const HINT_KEY = 'feedit.assist.hint.v1';

let guide = null;
let guideStep = 0;
let guideRaf = 0;

function hintSeen(){
  try { return localStorage.getItem(HINT_KEY) === '1'; } catch (_) { return false; }
}
function markHintSeen(){
  try { localStorage.setItem(HINT_KEY, '1'); } catch (_) {}
}

export function setAssistOpen(open){
  const hub = document.getElementById('assistHub');
  const toggle = document.getElementById('chatFab');
  const menu = document.getElementById('assistMenu');
  if(!hub || !toggle || !menu) return;
  hub.classList.toggle('open', !!open);
  toggle.setAttribute('aria-expanded', String(!!open));
  toggle.setAttribute('aria-label', open ? 'FEEDiT 도움말 메뉴 닫기' : 'FEEDiT 도움말 메뉴 열기');
  menu.setAttribute('aria-hidden', String(!open));
  if(open){
    markHintSeen();
    const hint = document.getElementById('assistHint');
    if(hint) hint.hidden = true;
    requestAnimationFrame(() => {
      const first = menu.querySelector('.assistAction');
      if(first) first.focus({ preventScroll:true });
    });
  }
}

function currentView(){ return document.body.dataset.view || 'home'; }

function isVisible(el){
  if(!el || el.hidden) return false;
  const style = typeof getComputedStyle === 'function' ? getComputedStyle(el) : null;
  return !style || (style.display !== 'none' && style.visibility !== 'hidden');
}

function firstTarget(selectors){
  for(const selector of selectors){
    const el = document.querySelector(selector);
    /* 살!말? 가이드 모달은 운영 화면과 분리된 고정 목업이다. 전환 직후
     * getComputedStyle이 이전 visibility 값을 한 프레임 돌려줘도 단계를
     * 건너뛰지 않도록, 목업 오버레이의 명시적 open 상태를 우선한다. */
    if(el?.closest('#salmalGuideDemo .modalOverlay.on')) return el;
    if(isVisible(el)) return el;
  }
  return null;
}

const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

/* 트렌드 가이드는 실제 탭을 누르거나 검색을 실행하지 않는다.
 * 저장된 응답을 기존 렌더러에 잠시 주입해 실제 화면을 보여 주고, 닫을 때 원상복구한다. */
const TREND_GUIDE_ITEMS = [
  {
    id:'myfeed', icon:'◧', title:'내 피드',
    summary:'내 취향 태그와 최근 행동을 합쳐, 지금 나에게 의미 있는 시장 신호와 살!말? 고민만 모아 보는 개인화 화면입니다.',
    sections:[
      ['취향 브리핑','관심 스타일의 현재 온도와 수명주기 위치를 한 문장으로 요약합니다.'],
      ['시장 신호','내 취향 안에서 새로 오르거나 빠지는 키워드를 보여 줍니다.'],
      ['왜 추천했는지','취향 태그·행동 기록 중 어떤 근거가 추천에 쓰였는지 밝힙니다.'],
      ['맞춤 살!말?','나와 조건이 비슷한 사용자의 투표와 아이템 취향이 겹치는 고민만 선별합니다.'],
    ],
  },
  {
    id:'report', icon:'◔', title:'금주의 리포트',
    summary:'이번 주에 내가 많이 본 키워드와 행동을 한 장의 주간 보고서로 정리하는 화면입니다.',
    sections:[
      ['이번 주 핵심 키워드','검색·관심 행동이 가장 많이 모인 키워드를 리포트의 축으로 잡습니다.'],
      ['주간 핵심 지표','검색, 찜, 살!말? 같은 이번 주 활동을 숫자로 요약합니다.'],
      ['요일별 활동·취향 지분','언제 많이 탐색했고 어떤 스타일에 관심이 쏠렸는지 비교합니다.'],
      ['추천 콘텐츠','핵심 키워드와 연결된 실제 영상·웹 매거진을 이어서 볼 수 있습니다.'],
      ['같이 지켜볼 스타일','현재 온도와 수명주기를 기준으로 다음 관찰 후보를 제안합니다.'],
    ],
  },
  {
    id:'saved', icon:'♡', title:'찜한 키워드',
    summary:'찜한 상품과 키워드를 단순 목록이 아니라, 가격·온도 변화가 생긴 순서대로 지켜보는 워치리스트입니다.',
    sections:[
      ['오늘의 이슈','찜한 것 중 최저가·급등·급락처럼 가장 먼저 볼 변화를 크게 보여 줍니다.'],
      ['오늘 더 있었던 일','같은 날 움직인 다른 찜 항목을 짧은 카드로 이어서 보여 줍니다.'],
      ['워치리스트 요약','찜한 수, 움직인 수, 최저가 도달, 조용한 항목을 빠르게 비교합니다.'],
      ['찜한 것 전체','급등·최저가·급락·잠잠·측정 전으로 필터링해 다시 확인합니다.'],
    ],
  },
  {
    id:'temp', icon:'℃', title:'언급량 · 온도',
    demo:{mode:'dict',term:'니트',facet:'아이템'},
    summary:'한 키워드가 얼마나 많이 이야기되고 얼마나 빠르게 뜨거워지는지 0–100 온도와 시계열로 보는 화면입니다.',
    sections:[
      ['현재 온도 판정','차가움·미지근·따뜻함·과열 중 현재 위치와 해석을 먼저 보여 줍니다.'],
      ['핵심 지표','주간 온도 변화, 화제성 레벨, 성장 모멘텀을 함께 읽습니다.'],
      ['언급량·온도 추이','말하는 양과 열기의 방향이 같이 움직이는지 날짜별로 비교합니다.'],
      ['플랫폼별 온도','플랫폼마다 확산 속도가 다른지, 값의 기준일이 오래되지는 않았는지 확인합니다.'],
    ],
  },
  {
    id:'assoc', icon:'◎', title:'연관어',
    demo:{mode:'dict',term:'발레코어',facet:'스타일'},
    summary:'검색한 키워드가 아이템·소재·색·디테일·TPO·스타일과 어떤 조합으로 함께 불리는지 보는 화면입니다.',
    sections:[
      ['확산 상태','연관어가 여러 축에 얼마나 고르게 쌓였는지 정체–폭발적 확산으로 요약합니다.'],
      ['핵심 연관어','통합 점수가 가장 높은 조합과 새로 진입한 표현을 먼저 보여 줍니다.'],
      ['연관어 수 추이','연관어 종류가 시간에 따라 넓어지는지 줄어드는지 확인해 확산의 지속성을 봅니다.'],
      ['축별 TOP 연관어','아이템·소재·색·디테일·TPO·스타일별 순위와 강도를 비교합니다.'],
      ['근거 문장','연관어를 누르면 실제로 함께 등장한 문장과 최근 주차 흐름을 확인합니다.'],
      ['정렬 기준','특징 점수와 동시 출현 건수를 바꿔 보며 강한 조합과 대중적인 조합을 구분합니다.'],
    ],
  },
  {
    id:'sentiment', icon:'⇅', title:'긍부정',
    demo:{mode:'dict',term:'스키니',facet:'디테일'},
    summary:'단순한 기분 분석이 아니라, 사람들이 사려는지 망설이는지와 그 이유를 반응 유형으로 읽는 화면입니다.',
    sections:[
      ['구매의향 판정','구매의향 지수를 중심으로 지금 반응이 구매 쪽인지 관망 쪽인지 먼저 설명합니다.'],
      ['핵심 반응 지표','총 반응 수와 가장 많이 나타난 긍정·부정 신호를 함께 봅니다. 표본 규모와 호평·비판 같은 주된 이유를 먼저 확인하는 카드입니다.'],
      ['긍정·중립·부정','최근 반응의 세 비중과 표본 수를 함께 보여 과대해석을 막습니다.'],
      ['반응 신호 6종','질문·구매·경험·호평·비판·잡담 건수를 실제 분류 결과로 비교합니다.'],
      ['근거 문장','호평이나 비판 신호를 누르면 판단에 쓰인 실제 문장을 확인합니다.'],
    ],
  },
  {
    id:'life', icon:'∞', title:'수명주기',
    demo:{mode:'dict',term:'민트',facet:'색'},
    summary:'트렌드가 태동·확산·정점·쇠퇴 중 어디에 있는지와 상품 기획 시기를 판단하는 화면입니다.',
    sections:[
      ['현재 단계','유행 진행도와 함께 태동·확산·정점·쇠퇴 판정을 가장 먼저 보여 줍니다.'],
      ['기획 지표','신규 유입률, 성장 모멘텀, 시장 포화도로 앞으로의 여지를 봅니다.'],
      ['유행 곡선','화제성 흐름 위에서 현재 위치와 정점 통과 여부를 확인합니다.'],
      ['주별 온도','최근 8주의 온도를 주차별로 비교해 일시적인 급등인지 꾸준한 상승인지 확인합니다.'],
      ['언급량·판매량','언급량과 실제 판매가 함께 움직이는지 비교해 관심만 높은 거품인지 실제 수요인지 봅니다.'],
    ],
  },
  {
    id:'stock', icon:'%', title:'할인률 변화',
    demo:{mode:'detail',term:'[우연X후브스] 밀리터리 슬림 헨리넥 롱슬리브[딥네이비]',facet:'상품명'},
    summary:'개별 상품의 정가·현재 판매가·할인률과 가격 변화를 확인해 구매 타이밍을 비교하는 화면입니다.',
    sections:[
      ['선택 상품','이미지·브랜드·상품명·모델번호로 지금 분석하는 대상을 명확히 확인합니다.'],
      ['가격 요약','정가, 현재 판매가, 할인률, 첫 할인 관측과 기간 최고 할인률을 보여 줍니다.'],
      ['가격·할인률 추이','판매가가 언제 내려갔고 할인 폭이 어떻게 변했는지 날짜별로 봅니다.'],
      ['플랫폼 비교','같은 표준상품으로 연결된 판매처만 비교하고, 없는 플랫폼 카드는 숨깁니다.'],
      ['찜 연결','분석 상품을 찜해 이후 최저가와 가격 변화를 워치리스트에서 이어 봅니다.'],
    ],
  },
  {
    id:'resale', icon:'±', title:'리세일 지수',
    demo:{mode:'detail',term:'프로 드라이 핏 타이트 반소매 피트니스 탑 - 블랙:화이트',facet:'상품명'},
    summary:'표준상품 매핑을 바탕으로 중고가·현재 매물·거래량과 사거나 팔 때의 가격 근거를 보는 화면입니다.',
    sections:[
      ['상품·매핑 상태','같은 표준상품으로 연결된 플랫폼과 단독 플랫폼 상품 여부를 먼저 밝힙니다.'],
      ['구매·판매 모드','같은 가치 유지율을 구매 시 절약률, 판매 시 회수율의 언어로 바꿔 설명합니다.'],
      ['핵심 4지표','정가 중앙값, 중고가 중앙값, 현재 매물 수, 최근 4주 중고거래량을 봅니다.'],
      ['플랫폼별 현재 가격','무신사·USED·크림 등 실제로 매핑되고 값이 있는 플랫폼만 비교합니다.'],
      ['현재 매물과 최근 거래','현재 올라온 최저 매물 중앙값과 최근 거래 사례 중앙값을 비교해 호가와 실제 체결 가격의 차이를 봅니다.'],
      ['추천 중고 상품','세부 검색에서 개별 상품이 아니라 브랜드만 검색했을 때 나타나는 영역입니다. 해당 브랜드에서 현재 관측되는 추천 중고 상품을 이미지·가격·매물 수로 비교합니다.'],
      ['리세일 시장 지표','가격 방어율, 거래량 증감률, 정가보다 비쌌던 프리미엄 지속 기간을 각각 확인합니다.'],
      ['가치 변화','날짜별 정가 대비 중고 가치의 중앙값을 보여 주며, 시간이 지나도 가격이 얼마나 유지되는지 확인합니다.'],
      ['가치 유지율과 트렌드 온도','중고 가치 유지율과 관심 온도를 한 카드에서 비교해 가격과 관심 중 어느 쪽이 먼저 움직이는지 봅니다.'],
    ],
  },
];

function trendPreview(item, activeIndex){
  return '<div class="tgPreviewHead"><span>고정 화면 미리보기</span><em>검색·개인화 기록에 저장되지 않음</em></div>'+
    '<div class="tgPreviewTitle"><i>'+item.icon+'</i><div><b>'+item.title+'</b><span>'+item.summary+'</span></div></div>'+
    '<div class="tgPreviewGrid">'+item.sections.map((section,index)=>
      '<article class="'+(index === activeIndex ? 'active' : '')+'"><small>'+String(index+1).padStart(2,'0')+'</small><div><b>'+section[0]+'</b><p>'+section[1]+'</p></div></article>'
    ).join('')+'</div>';
}

function activeTrendItem(){
  const id=document.querySelector('.sItem.on[data-tr]')?.dataset.tr || 'myfeed';
  return TREND_GUIDE_ITEMS.find(item=>item.id===id) || TREND_GUIDE_ITEMS[0];
}

const DEMO_PAYLOADS={temp:tempDemo,assoc:assocDemo,sentiment:sentimentDemo,life:lifeDemo,stock:stockDemo,resale:resaleDemo};
const DICTIONARY_DEMO_ROWS=[
  {facet:'스타일',label:'발레코어'},{facet:'스타일',label:'고프코어'},{facet:'스타일',label:'시티보이'},
  {facet:'아이템',label:'니트'},{facet:'아이템',label:'카디건'},{facet:'아이템',label:'스커트'},
  {facet:'소재',label:'코튼'},{facet:'소재',label:'울'},{facet:'소재',label:'데님'},
  {facet:'디테일',label:'스키니'},{facet:'디테일',label:'리본'},{facet:'디테일',label:'핀턱'},
  {facet:'색',label:'민트'},{facet:'색',label:'딥네이비'},{facet:'색',label:'블랙'},
  {facet:'TPO',label:'데일리'},{facet:'TPO',label:'출근'},{facet:'TPO',label:'여행'},
  {facet:'브랜드',label:'나이키'},{facet:'브랜드',label:'아디다스'},{facet:'브랜드',label:'스투시'},
];

function plainClone(value){
  if(typeof structuredClone==='function') return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function replaceState(target,snapshot){
  Object.keys(target).forEach(key=>delete target[key]);
  Object.assign(target,plainClone(snapshot));
}

function guidePayload(id){
  const payload=plainClone(DEMO_PAYLOADS[id]);
  const data=payload?.data;
  if(!data)return payload;
  /* 실제 저장 응답의 결측만 가이드 설명용으로 보완한다. 구조와 렌더러는 운영 화면과 동일하다. */
  if(id==='life'&&(!Array.isArray(data.sales_series)||!data.sales_series.length)){
    data.sales_series=(data.series||[]).slice(-12).map((row,index)=>({date:row.date,sales:8+index*2+(index%3)*3}));
  }
  if(id==='resale'){
    data.volume_basis='transactions';
    data.volume_change_pct=12.5;
    if(data.md_signals?.[1]){
      data.md_signals[1].value='+12.5%';
      data.md_signals[1].tone='positive';
      data.md_signals[1].description='가이드 예시에서 최근 4주와 이전 4주의 거래량을 비교한 값입니다.';
    }
    const product=data.product||{};
    if(!data.recommendations?.length){
      data.recommendations=(product.images||[]).slice(0,5).map((image,index)=>({
        product_id:product.id,source_id:71000+index,name:product.name,brand:product.brand,
        model_code:product.model_code,image,platform:index%2?'크림':'무신사 USED',
        listing_count:Math.max(1,12-index*2),listing_count_partial:index%2===1,price:17600+index*1600,
      }));
    }
    if(!data.temperature?.series?.length){
      data.temperature={term:product.name,status:'ok',series:(data.series||[]).map((row,index)=>({
        date:row.date,temp:52+((index*7)%31),
      }))};
    }
  }
  return payload;
}

function stockDemoItem(){
  const product=stockDemo?.data?.product||{};
  return {id:product.id,label:product.name,brand:product.brand,source:product.source,thumb:product.image};
}

function resaleDemoItem(){
  const product=resaleDemo?.data?.product||{};
  const mapping=resaleDemo?.data?.mapping||{};
  return {id:product.id,type:'product',name:product.name,brand:product.brand,code:product.code,
    model_code:product.model_code,image:product.image,images:product.images,
    platforms:mapping.platforms,source_count:mapping.source_count};
}

/* 가이드가 쓰는 것은 별도 화면이 아니라 현재 페이지의 실제 렌더러다.
 * API 응답을 미리 저장해 둔 JSON으로 캐시만 잠시 바꿔 끼우므로 네트워크·DB·검색 기록은 건드리지 않는다. */
function mountTrendGuideDemo(item){
  if(!item.demo)return null;
  const beforeKW=plainClone(KW), beforeFS=plainClone(FS);
  const beforeInputs={kw:document.getElementById('kwInput')?.value||'',fs:document.getElementById('fsInput')?.value||''};
  const who=document.querySelector('#sFoot .who b');
  const beforeWho=who?.textContent||'';
  const payload=guidePayload(item.id);
  let restoreCache=()=>{};
  document.body.classList.add('trend-guide-demo');

  if(['temp','assoc','sentiment'].includes(item.id)){
    KW.q=item.demo.term; KW.f=item.demo.facet; KW.part=item.id; KW.sug=[]; KW.cur=-1;
    const url=item.id==='assoc'?'/api/assoc?term='+encodeURIComponent(item.demo.term):
      item.id==='sentiment'?sentimentUrl(item.demo.term,item.demo.facet):null;
    restoreCache=installGuideDemo(item.id==='temp'
      ? {trends:[{term:item.demo.term,payload}]}
      : {urls:[{url,payload}]});
  }else{
    fsReset(); FS.id=item.id; FS.sug=[]; FS.cur=-1; FS.err=''; FS.note=''; FS.loading=false;
    if(item.id==='life'){
      FS.pick={[item.demo.facet]:[item.demo.term]};
      FS.opts={색:['민트','딥네이비','블랙'],스타일:['발레코어','고프코어'],종류:['니트','카디건'],브랜드:['나이키','스투시'],아이템명:['민트 니트']};
      restoreCache=installGuideDemo({urls:[{url:'/api/lifecycle?term='+encodeURIComponent(item.demo.term),payload}]});
    }else if(item.id==='stock'){
      const selected=stockDemoItem();
      fsStockSelect(selected);
      FS.opts={
        style:[{label:'캐주얼',count:1}], brand:[{label:selected.brand,count:1}], kind:[{label:'상의',count:1}],
        item:[{...selected,count:1,name:selected.label,image:selected.thumb}],
      };
      restoreCache=installGuideDemo({urls:[{url:'/api/discount?source_id='+selected.id,payload}]});
    }else{
      const selected=resaleDemoItem();
      fsResaleSelect(selected); FS.resaleModalItems=[selected];
      FS.opts={
        style:[{label:'애슬레저',count:1},{label:'스포티',count:1}],
        kind:[{label:'티셔츠',count:1},{label:'피트니스 탑',count:1}],
        brand:[{label:selected.brand,count:1}], item:[{label:selected.name,count:1}],
      };
      restoreCache=installGuideDemo({urls:[{url:'/api/resale?product_id='+selected.id,payload}]});
    }
  }
  trRender(item.id);
  const input=document.getElementById(['temp','assoc','sentiment'].includes(item.id)?'kwInput':'fsInput');
  if(input)input.value=item.demo.term;
  if(who)who.textContent='피딧';
  return ()=>{
    closeDictionaryGuideDemo(); fsCloseGuidePop();
    restoreCache(); replaceState(KW,beforeKW); replaceState(FS,beforeFS);
    fsPaintPop();
    if(who)who.textContent=beforeWho;
    /* 복원 렌더도 demo 플래그가 켜진 동안 실행해 불필요한 API 호출을 막는다. */
    trRender(item.id);
    const kwInput=document.getElementById('kwInput'), fsInput=document.getElementById('fsInput');
    if(kwInput)kwInput.value=beforeInputs.kw;
    if(fsInput)fsInput.value=beforeInputs.fs;
    document.body.classList.remove('trend-guide-demo');
  };
}

const GUIDE_TARGETS={
  temp:[['#trBody .verdict'],['#trBody .kpis'],['#trBody [data-chart="tempMain"]'],['#trBody .svcGrid','#trBody .trGrid .panelC:last-child']],
  assoc:[['#trBody .verdict'],['#trBody .kpis'],['#trBody [data-chart="assocMain"]'],['#trBody .assocGrid'],['#trBody .assocGrid .axRow'],['#trBody .assocGrid .axSortToggle','#trBody .assocGrid']],
  sentiment:[['#trBody .verdict'],['#trBody .kpis'],['#sentChartCard'],['#sentSigCard'],['#sigWrap tr[data-sig]','#sigWrap']],
  life:[['#trBody .verdict'],['#trBody .kpis'],['#trBody [data-chart="lifeMain"]'],['#trBody .lcWk'],['#trBody [data-chart="lifeGap"]']],
  stock:[['#stockAnalyticsBody .productIdentity','#stockAnalyticsBody'],['#stockAnalyticsBody .stockKpis'],['#stockAnalyticsBody .stockTrendPanel'],['#stockAnalyticsBody .stockComparePanel'],['#stockWishBtn','#stockAnalyticsBody']],
  resale:[['#trBody .resaleIdentity'],['#trBody .resaleMode'],['#trBody .kpis'],['#trBody .resalePlatforms'],['#trBody .resaleSpread'],['#trBody .resaleRecommendations'],['#trBody .resaleMd'],['#trBody .resaleEvidence .panelC:nth-child(1)'],['#trBody .resaleEvidence .panelC:nth-child(2)']],
};

/* 한 번의 투어에서는 현재 보고 있는 분석 페이지만 설명한다.
 * 1단계 전체 구조는 최초 진입 화면인 내 피드에서만 보여 주고,
 * 모든 메뉴는 각 화면에서 2단계 역할 설명 → 3단계 카드 읽기 순서로 진행한다. */
function trendSteps(item){
  if(item.demo){
    const total=item.sections.length+4;
    const modeName=item.demo.mode==='dict'?'사전':'세부 검색';
    const modeBody=item.demo.mode==='dict'
      ? '오른쪽 사전 버튼을 누르면 스타일·아이템·소재·디테일·색·TPO·브랜드 칸이 열립니다. 칸 전체에서 용어 하나를 고른 뒤 “이 용어로 검색”을 누르는 흐름입니다.'
      : (item.id==='resale'
        ? '세부 검색에서는 스타일·종류·브랜드·상품명을 독립적으로 고릅니다. 상품을 고르면 정확한 시세를, 브랜드만 고르면 그 브랜드의 추천 중고 아이템 흐름을 볼 수 있습니다.'
        : '세부 검색에서는 스타일·종류·브랜드·상품명을 독립적으로 고릅니다. 할인률 변화는 상품명을 골라야 정가와 현재 판매가를 같은 상품 기준으로 비교할 수 있습니다.');
    const menuStep={
      targets:['.sItem[data-tr="'+item.id+'"]','#side'], icon:item.icon, kind:'trend-nav',
      phase:'2단계 · 현재 메뉴', counter:'2 / '+total,
      title:item.title+'은 무엇인가요?', body:item.summary,
      enter(){ closeDictionaryGuideDemo(); fsCloseGuidePop(); },
    };
    const searchStep={
      targets:[item.demo.mode==='dict'&&item.id!=='life'?'#kwBar':'#fsBar','#trTabs','#trSearch'], icon:'⌕', kind:'trend-search',
      phase:'3단계 · 검색 시작', counter:'3 / '+total,
      title:'예시 검색어는 “'+item.demo.term+'”입니다',
      body:'지금 보이는 검색창과 결과 카드는 실제 FEEDiT 화면입니다. 다만 가이드 동안에는 저장해 둔 실제 분석 응답을 사용해 API를 다시 부르지 않고, 검색·개인화 기록에도 남기지 않습니다.',
      enter(){ closeDictionaryGuideDemo(); fsCloseGuidePop(); },
    };
    const modalStep={
      targets:[item.demo.mode==='dict'?'#dictPopBg .dictPop':'#fsPopBg .fsPop'], icon:item.demo.mode==='dict'?'▦':'⌘', kind:'trend-modal',
      phase:'4단계 · '+modeName, counter:'4 / '+total,
      title:modeName+'은 이렇게 사용합니다', body:modeBody,
      enter(){
        if(item.demo.mode==='dict') openDictionaryGuideDemo(DICTIONARY_DEMO_ROWS,{f:item.demo.facet,label:item.demo.term});
        else fsOpenGuidePop();
      },
    };
    const charts=item.sections.map((section,index)=>({
      targets:GUIDE_TARGETS[item.id]?.[index]||['#trBody'], icon:item.icon, kind:'trend-chart',
      phase:'결과 읽기 · '+(index+1)+' / '+item.sections.length, counter:(index+5)+' / '+total,
      title:section[0]+'은 이렇게 읽어요', body:section[1],
      enter(){ closeDictionaryGuideDemo(); fsCloseGuidePop(); },
    }));
    return [menuStep,searchStep,modalStep].concat(charts);
  }
  const total=item.sections.length+2;
  const details=item.sections.map((section,index)=>({
    targets:['#trBody','.trMain'], icon:item.icon, kind:'trend-detail',
    phase:'3단계 · '+item.title+' 카드 '+(index+1)+' / '+item.sections.length,
    counter:(index+3)+' / '+total,
    title:section[0]+'은 이렇게 읽어요',
    body:section[1],
    preview:trendPreview(item,index),
  }));
  const menuStep={
    targets:['.sItem[data-tr="'+item.id+'"]','#side'], icon:item.icon, kind:'trend-nav',
    phase:'2단계 · 현재 메뉴', counter:'2 / '+total,
    title:item.title+'은 무엇인가요?', body:item.summary,
  };
  if(item.id!=='myfeed') return [menuStep].concat(details);
  return [{
    targets:['#side'], icon:'↕', kind:'trend-intro', phase:'1단계 · 트렌드 분석 메뉴', counter:'1 / '+total,
    title:'왼쪽 메뉴는 FEED와 EDIT로 나뉩니다',
    body:'FEED는 나에게 모인 관심과 행동을 정리하고, EDIT는 시장 데이터를 목적별로 골라 분석합니다. 가이드는 탭을 이동하거나 검색 API를 실행하지 않습니다.',
  },menuStep].concat(details);
}

function salmalSteps(){
  return [
    {
      targets:['#salmalGuideDemo [data-sm-guide="hero"]'], icon:'S', kind:'salmal-page', phase:'1단계 · 살!말? 둘러보기',
      title:'다른 사람의 구매 고민을 함께 판단해요',
      body:'인기순·최신순·내 취향·마감임박 탭으로 고민 카드를 고르고, 내가 올린 카드도 한자리에서 확인할 수 있어요.', enter:showSalmalGuideFeed,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="card"]'], icon:'▣', kind:'salmal-page', phase:'2단계 · 예시 카드',
      title:'상품과 현재 의견을 카드에서 먼저 봐요',
      body:'상품 사진·브랜드·가격과 현재 살/말 비율, 마감까지 남은 시간을 함께 보여 줍니다. 이 카드는 가이드 안에서만 보이는 예시예요.', enter:showSalmalGuideFeed,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="detail"] .modalGrid'], icon:'▣', kind:'salmal-modal-left', phase:'3단계 · 상세·참여',
      title:'카드를 누르면 상세 화면에서 참여해요',
      body:'상품·사연과 함께 전체 투표, 나와 비슷한 사용자의 결과, 댓글을 한 화면에서 봐요. 살/말 판단 이유는 댓글로 남길 수 있고, 목업에서는 아무것도 저장되지 않아요.', enter:showSalmalGuideDetail,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="add"]'], icon:'+', kind:'salmal-page', phase:'4단계 · 고민 등록',
      title:'내 구매 고민도 직접 물어볼 수 있어요',
      body:'“살까말까 물어보기”를 누르면 등록 모달이 열려요. 다음 단계에서는 운영 데이터와 완전히 분리된 예시 모달로 작성 순서를 보여 드릴게요.', enter:showSalmalGuideFeed,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="create"] .createBox'], icon:'+', kind:'salmal-modal-left', phase:'5단계 · 등록 모달',
      title:'등록 모달에서 한 화면으로 작성해요',
      body:'왼쪽에 상품 이미지, 오른쪽에 상품 정보와 사연을 적는 구조예요. 지금 보이는 값은 전부 가이드용 목업이며 서버에 올라가지 않아요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="image"]'], icon:'▣', kind:'salmal-modal-left', phase:'6단계 · 상품 이미지',
      title:'고민 중인 상품 사진을 선택해요',
      body:'JPEG·PNG·WebP 이미지를 올리면 카드와 상세 화면의 대표 이미지로 사용돼요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="title"]'], icon:'T', kind:'salmal-modal-right', phase:'7단계 · 상품명',
      title:'검색하기 쉬운 정확한 상품명을 적어요',
      body:'색상·옵션이 있다면 상품명과 함께 적어 같은 상품을 쉽게 구분해요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="brand"]'], icon:'B', kind:'salmal-modal-right', phase:'8단계 · 브랜드',
      title:'브랜드를 검색해 선택하거나 직접 적어요',
      body:'입력하는 동안 비슷한 브랜드가 나타나며, 목록에 없는 브랜드도 그대로 적을 수 있어요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="price"]'], icon:'₩', kind:'salmal-modal-right', phase:'9단계 · 가격',
      title:'실제로 고민 중인 구매 가격을 적어요',
      body:'할인이 적용된 상태라면 정가가 아닌 지금 결제할 금액을 숫자로 입력해요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="style"]'], icon:'S', kind:'salmal-modal-right', phase:'10단계 · 스타일',
      title:'상품에 가장 가까운 스타일을 골라요',
      body:'스타일을 고르면 취향이 비슷한 사용자에게 카드를 보여 주는 데 활용할 수 있어요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="story"]'], icon:'✎', kind:'salmal-modal-right', phase:'11단계 · 사연·등록',
      title:'마지막으로 왜 고민인지 적고 물어봐요',
      body:'핏·소재·가격·활용도 중 궁금한 점을 구체적으로 적으면 더 유용한 댓글을 받을 수 있어요. 작성을 마친 뒤 “물어보기”를 누르면 등록돼요.', enter:showSalmalGuideCreate,
    },
  ];
}

function genericSteps(view){
  if(view === 'home') return [
    { targets:['#hotBar', '.hot'], icon:'F', title:'오늘의 흐름을 먼저 훑어보세요', body:'홈에서는 지금 주목받는 패션 흐름과 추천 질문을 빠르게 확인할 수 있습니다.' },
    { targets:['.chatWrap'], icon:'✦', title:'자연어로 바로 물어보세요', body:'궁금한 아이템이나 코디를 문장으로 입력하면 FEEDiT이 관련 데이터를 찾아 답합니다.' },
    { targets:['#mNav'], icon:'↗', title:'목적에 맞는 화면으로 이동하세요', body:'트렌드 분석, 살!말?, 스타일 메뉴가 각각 다른 질문을 해결합니다.' },
    { targets:['#chatFab'], icon:'?', title:'이 버튼에서 다시 시작할 수 있어요', body:'챗봇과 주요 화면, 가이드라인을 언제든 다시 불러올 수 있습니다.' },
  ];
  if(view === 'style') return [
    { targets:['.styleTitle', '#styleHome'], icon:'S', title:'취향에 가까운 코어를 골라보세요', body:'스타일을 고르면 배경 설명부터 현재 아이템까지 한 흐름으로 볼 수 있습니다.' },
    { targets:['#stCats', '#styleHome'], icon:'↗', title:'카테고리를 눌러 상세로 들어가세요', body:'관심 스타일을 선택하면 관련 상품과 Virtual Fitting으로 이어집니다.' },
    { targets:['#chatFab'], icon:'?', title:'도움이 필요하면 다시 열어보세요', body:'챗봇·트렌드 분석·가이드를 이곳에서 바로 실행할 수 있습니다.' },
  ];
  if(view === 'price') return [
    {
      targets:['#prGrid .prCard:nth-child(1)','#prGrid'], icon:'0',
      title:'프리는 개인용 기본 플랜이에요',
      body:'월 0원으로 살!말? 참여와 FEED 분석을 이용할 수 있어요. AI 챗은 하루 20회, EDIT는 언급량·온도까지 제공하며 리포트 내보내기는 포함되지 않아요.',
    },
    {
      targets:['#prGrid .prCard:nth-child(2)','#prGrid'], icon:'P',
      title:'프로는 매일 분석하는 실무자용이에요',
      body:'월 19,900원으로 AI 챗과 EDIT 전체 트렌드 분석을 이용해요. 분석 결과를 실무용 리포트로 내보낼 수 있는 추천 플랜이에요.',
    },
    {
      targets:['#prGrid .prCard:nth-child(3)','#prGrid'], icon:'B',
      title:'비즈니스는 팀 협업과 연동을 위한 플랜이에요',
      body:'프로의 분석·리포트 기능에 데이터 API 연동을 더해 팀 단위 업무에 맞춥니다. 요금과 연동 범위는 문의를 통해 조정해요.',
    },
  ];
  return [
    { targets:[`#v-${view}`, '#mNav'], icon:'F', title:'현재 화면의 핵심 기능을 둘러보세요', body:'화면 안의 주요 카드와 버튼을 따라가면 FEEDiT의 분석 흐름을 사용할 수 있습니다.' },
    { targets:['#mNav'], icon:'↗', title:'다른 기능도 바로 이어서 볼 수 있어요', body:'상단 메뉴에서 분석, 커뮤니티, 스타일 화면을 오갈 수 있습니다.' },
    { targets:['#chatFab'], icon:'?', title:'필요할 때 가이드를 다시 여세요', body:'현재 화면에서 언제든 이 도움말 허브를 사용할 수 있습니다.' },
  ];
}

function stopGuideSync(){
  if(guideRaf) cancelAnimationFrame(guideRaf);
  guideRaf = 0;
}

function guideTarget(){
  if(!guide) return null;
  const step = guide.steps[guideStep];
  return step ? firstTarget(step.targets) : null;
}

function placeGuide(){
  if(!guide) return;
  const step = guide.steps[guideStep];
  const target = guideTarget();
  if(!target) return;
  const raw = target.getBoundingClientRect();
  if(!raw.width && !raw.height) return;
  const isSalmalModal = step?.kind?.startsWith('salmal-modal');
  const isTrendGuide = step?.kind?.startsWith('trend-');
  const padX = isSalmalModal ? 34 : isTrendGuide ? 26 : 9;
  const padY = isSalmalModal ? 18 : isTrendGuide ? 17 : 9;
  const vw = window.innerWidth || document.documentElement.clientWidth || 1280;
  const vh = window.innerHeight || document.documentElement.clientHeight || 800;
  const left = Math.max(8, raw.left - padX);
  const top = Math.max(8, raw.top - padY);
  const right = Math.min(vw - 8, raw.right + padX);
  const bottom = Math.min(vh - 8, raw.bottom + padY);
  Object.assign(guide.spot.style, {
    left:left+'px', top:top+'px', width:Math.max(1,right-left)+'px', height:Math.max(1,bottom-top)+'px',
  });

  const cardRect = guide.card.getBoundingClientRect();
  const isTrendDetail = step?.kind === 'trend-detail';
  const isTrendModal = step?.kind === 'trend-modal';
  const isTrendSide = (step?.kind === 'trend-intro' || step?.kind === 'trend-nav') && vw > 760;
  if(isTrendModal){
    guide.card.classList.remove('above','sideTarget');
    guide.card.classList.add('detached');
    guide.card.style.left=Math.max(16,vw-cardRect.width-28)+'px';
    guide.card.style.top=Math.max(16,vh-cardRect.height-28)+'px';
    return;
  }
  if(isSalmalModal){
    guide.card.classList.remove('above','sideTarget');
    guide.card.classList.add('detached');
    /* 입력칸이 왼쪽/오른쪽 어느 열에 있든 설명창 위치는 흔들리지 않는다. */
    guide.card.style.left=Math.max(16,vw-cardRect.width-28)+'px';
    guide.card.style.top=Math.max(16,vh-cardRect.height-28)+'px';
    return;
  }
  if(isTrendDetail){
    const cardLeft=Math.max(16,Math.min((vw-cardRect.width)/2,vw-cardRect.width-16));
    const cardTop=Math.max(16,Math.min((vh-cardRect.height)/2,vh-cardRect.height-16));
    guide.card.classList.remove('above','sideTarget');
    guide.card.classList.add('detached');
    guide.card.style.left=cardLeft+'px';
    guide.card.style.top=cardTop+'px';
    return;
  }
  if(isTrendSide){
    const cardLeft=Math.max(16,Math.min(right+20,vw-cardRect.width-16));
    const cardTop=Math.max(16,Math.min(raw.top+raw.height/2-cardRect.height/2,vh-cardRect.height-16));
    guide.card.classList.remove('above','detached');
    guide.card.classList.add('sideTarget');
    guide.card.style.left=cardLeft+'px';
    guide.card.style.top=cardTop+'px';
    return;
  }
  const below = bottom + 18;
  const useAbove = below + cardRect.height > vh - 16;
  const cardTop = useAbove ? Math.max(16, top - cardRect.height - 18) : below;
  let cardLeft = raw.left + raw.width / 2 - cardRect.width / 2;
  cardLeft = Math.max(16, Math.min(cardLeft, vw - cardRect.width - 16));
  guide.card.classList.remove('sideTarget','detached');
  guide.card.classList.toggle('above', useAbove);
  guide.card.style.left = cardLeft+'px';
  guide.card.style.top = cardTop+'px';
}

function startGuideSync(){
  stopGuideSync();
  const tick = () => { placeGuide(); guideRaf = requestAnimationFrame(tick); };
  guideRaf = requestAnimationFrame(tick);
}

function closeGuide(){
  stopGuideSync();
  const restore=guide?.restoreSide;
  const restoreDemo=guide?.restoreDemo;
  if(guide && guide.root) guide.root.remove();
  if(restoreDemo) restoreDemo();
  if(restore && !restore.wasOpen) trSideOpen(false);
  guide = null;
  guideStep = 0;
}

function paintGuideStep(){
  if(!guide) return;
  const step = guide.steps[guideStep];
  if(step && guide.enteredStep!==guideStep){
    if(typeof step.enter==='function')step.enter();
    guide.enteredStep=guideStep;
  }
  const target = guideTarget();
  if(!step || !target){
    guideStep += 1;
    if(guideStep >= guide.steps.length) return closeGuide();
    return paintGuideStep();
  }
  guide.icon.textContent = step.icon || 'F';
  guide.title.textContent = step.title;
  guide.body.textContent = step.body;
  guide.phase.textContent = step.phase || '';
  guide.phase.hidden = !step.phase;
  guide.preview.innerHTML = step.preview || '';
  guide.preview.hidden = !step.preview;
  guide.card.classList.toggle('trendGuideCard', !!step.kind?.startsWith('trend-'));
  guide.card.classList.toggle('trendDetail', step.kind === 'trend-detail');
  guide.card.classList.toggle('trendWalkthrough', ['trend-search','trend-modal','trend-chart'].includes(step.kind));
  guide.card.classList.toggle('salmalWalkthrough', !!step.kind?.startsWith('salmal-'));
  guide.spot.classList.toggle('salmalModalSpot', !!step.kind?.startsWith('salmal-modal'));
  guide.spot.classList.toggle('trendGuideSpot', !!step.kind?.startsWith('trend-'));
  guide.count.textContent = step.counter || `${guideStep + 1} / ${guide.steps.length}`;
  guide.prev.hidden = guideStep === 0;
  guide.prev.disabled = guideStep === 0;
  guide.next.innerHTML = guideStep === guide.steps.length - 1 ? '완료 <i>✓</i>' : '다음 <i>→</i>';
  guide.card.style.visibility = 'hidden';
  const activeGuide=guide;
  requestAnimationFrame(() => {
    if(guide!==activeGuide)return;
    if(step.kind==='trend-chart' && target.scrollIntoView) target.scrollIntoView({block:'center',behavior:'instant'});
    placeGuide();
    if(guide===activeGuide)guide.card.style.visibility = 'visible';
    startGuideSync();
  });
}

function buildGuide(steps){
  const root = document.createElement('div');
  root.className = 'guideTour';
  root.innerHTML =
    '<button type="button" class="guideScrim" aria-label="가이드 닫기"></button>' +
    '<div class="guideSpot" aria-hidden="true"></div>' +
    '<section class="guideCard" role="dialog" aria-modal="true" aria-labelledby="guideTitle">' +
      '<div class="guidePhase" hidden></div>' +
      '<div class="guideHead"><span class="guideIcon"></span><h3 id="guideTitle"></h3><em>FEEDiT</em></div>' +
      '<p class="guideBody"></p><div class="guidePreview" hidden></div><div class="guideLine"></div>' +
      '<div class="guideFoot"><div class="guideProgress"><button type="button" class="guidePrev" aria-label="이전 설명으로">←</button>' +
      '<span class="guideCount"></span></div><button type="button" class="guideSkip">건너뛰기</button>' +
      '<button type="button" class="guideNext"></button></div>' +
    '</section>';
  document.body.appendChild(root);
  const built = {
    root, steps,
    spot:root.querySelector('.guideSpot'), card:root.querySelector('.guideCard'),
    icon:root.querySelector('.guideIcon'), title:root.querySelector('h3'), body:root.querySelector('.guideBody'),
    phase:root.querySelector('.guidePhase'), preview:root.querySelector('.guidePreview'),
    count:root.querySelector('.guideCount'), prev:root.querySelector('.guidePrev'), next:root.querySelector('.guideNext'),
  };
  root.querySelector('.guideScrim').addEventListener('click', closeGuide);
  root.querySelector('.guideSkip').addEventListener('click', event => { event.stopPropagation(); closeGuide(); });
  built.prev.addEventListener('click', event => {
    event.stopPropagation();
    if(!guide || guideStep <= 0) return;
    guideStep -= 1;
    guide.enteredStep = -1;
    paintGuideStep();
  });
  built.next.addEventListener('click', event => {
    event.stopPropagation();
    const step = guide && guide.steps[guideStep];
    if(step && typeof step.after === 'function') step.after();
    guideStep += 1;
    if(!guide || guideStep >= guide.steps.length) return closeGuide();
    paintGuideStep();
  });
  return built;
}

export async function startContextGuide(){
  closeGuide();
  setAssistOpen(false);
  const view = currentView();
  let restoreSide=null;
  let steps;
  if(view === 'trend'){
    const item=activeTrendItem();
    const side=document.getElementById('side');
    const wasOpen=!!side?.classList.contains('open');
    if(!wasOpen){ trSideOpen(true); await frame(); }
    restoreSide={ wasOpen };
    const restoreDemo=mountTrendGuideDemo(item);
    steps=trendSteps(item);
    guideStep = 0;
    guide = buildGuide(steps);
    guide.restoreSide=restoreSide;
    guide.restoreDemo=restoreDemo;
    paintGuideStep();
    return;
  }else if(view === 'salmal'){
    const restoreDemo=mountSalmalGuideDemo();
    steps=salmalSteps();
    guideStep = 0;
    guide = buildGuide(steps);
    guide.restoreDemo=restoreDemo;
    paintGuideStep();
    return;
  }else steps=genericSteps(view);
  guideStep = 0;
  guide = buildGuide(steps);
  guide.restoreSide=restoreSide;
  paintGuideStep();
}

function onAssistAction(action){
  setAssistOpen(false);
  if(action === 'chat') return openChatWith('', null);
  if(action === 'trend') return goView('trend');
  if(action === 'style') return goView('style');
  if(action === 'guide') return startContextGuide();
}

function boot(){
  const hub = document.getElementById('assistHub');
  const toggle = document.getElementById('chatFab');
  const menu = document.getElementById('assistMenu');
  const hint = document.getElementById('assistHint');
  if(!hub || !toggle || !menu) return;
  if(hint) hint.hidden = hintSeen();
  toggle.addEventListener('click', e => {
    e.stopPropagation();
    setAssistOpen(!hub.classList.contains('open'));
  });
  menu.addEventListener('click', e => {
    const button = e.target.closest('[data-assist]');
    if(button) onAssistAction(button.dataset.assist);
  });
  document.addEventListener('click', e => {
    if(!hub.contains(e.target)) setAssistOpen(false);
  });
  document.addEventListener('keydown', e => {
    if(e.key !== 'Escape') return;
    if(guide) closeGuide();
    else setAssistOpen(false);
  });
}

if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
