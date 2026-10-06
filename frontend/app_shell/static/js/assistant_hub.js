/* 오른쪽 하단 챗봇 버튼 + 화면 가이드.
 * 하단 버튼은 어느 화면에서든 챗봇 팝업만 연다 (2026-10-05, 메뉴 허브에서 단일 버튼으로 되돌림).
 * 전체 가이드는 헤더 알림 오른쪽의 조이스틱 버튼(#tourBtn)에서 연다 (startGuideTour).
 * 화면 가이드는 alpha.js 와 분리해, 알파 계정 여부와 무관하게 사용할 수 있다. */
import { goView, trSideOpen } from './router.js';
import { AUTH } from '../../../account/static/js/profile.js';
import { SM_ON } from '../../../home/static/js/chat.js';
import { openChatWith, openChatPopup, closeChatPopup, cpToggleMode } from '../../../home/static/js/chat_popup.js';
import { stOpen } from '../../../style/static/js/style_page.js';
import { trRender } from '../../../trend/static/js/dispatch.js';
import { KW, josa } from '../../../trend/static/js/render_helpers.js';
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
/* 내 피드 가이드의 EDIT 대표 화면 — 로컬 Django /api/trend?term=가을&days=400 응답을 그대로 저장했다. */
import autumnDemo from '../../../trend/static/demo/temp_autumn.json' with { type:'json' };

let guide = null;
let guideStep = 0;
let guideRaf = 0;

function currentView(){ return document.body.dataset.view || 'home'; }

function isVisible(el){
  if(!el || el.hidden) return false;
  const style = typeof getComputedStyle === 'function' ? getComputedStyle(el) : null;
  return !style || (style.display !== 'none' && style.visibility !== 'hidden');
}

function usableTarget(el){
  /* 모달(.modalOverlay)은 연 직후 visibility 전환이 시작점에 있어
   * getComputedStyle 이 한 프레임 동안 hidden 을 돌려준다(살!말? 목업 · 챗봇 팝업).
   * 단계를 건너뛰지 않도록, 명시적으로 연 오버레이(.on) 안이면 열린 것으로 본다. */
  if(el?.closest?.('.modalOverlay.on')){
    if(el.hidden) return false;
    const style = typeof getComputedStyle === 'function' ? getComputedStyle(el) : null;
    return !style || style.display !== 'none';
  }
  return isVisible(el);
}

/* 단계의 targets 항목은 선택자, 또는 요소(여러 개면 배열)를 돌려주는 함수다.
 * 여러 요소는 한 덩어리로 묶어 강조한다(사이드바 FEED 라벨 + 메뉴 목록 등).
 * 앞 항목이 화면에 없으면 다음 항목으로 넘어가며, 찾은 요소를 배열로 돌려준다. */
function firstTarget(entries){
  for(const entry of entries){
    const value = typeof entry === 'function' ? entry() : entry;
    if(!value) continue;
    const elements = (Array.isArray(value) ? value : [value])
      .map(item => typeof item === 'string' ? document.querySelector(item) : item)
      .filter(Boolean);
    if(elements.length && elements.every(usableTarget)) return elements;
  }
  return null;
}

const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

/* 트렌드 가이드는 실제 탭을 누르거나 검색을 실행하지 않는다.
 * 저장된 응답을 기존 렌더러에 잠시 주입해 실제 화면을 보여 주고, 닫을 때 원상복구한다. */
const TREND_GUIDE_ITEMS = [
  {
    id:'myfeed', icon:'◧', title:'내 피드',
    summary:'내 취향 태그와 최근 행동을 합쳐\n나에게 맞는 시장 신호와 살!말? 고민을 모아 보는 화면이에요.',
    sections:[
      ['취향 브리핑','관심 스타일의 지금 온도와\n수명주기 위치를 한 문장으로 요약해요.'],
      ['시장 신호','내 취향 안에서 새로 오르거나\n빠지는 키워드를 보여 줘요.'],
      ['왜 추천했는지','취향 태그와 행동 기록 중\n어떤 근거로 추천했는지 밝혀요.'],
      ['맞춤 살!말?','나와 조건이 비슷한 사람들의 고민 중\n내 취향과 겹치는 것만 골라요.'],
    ],
  },
  {
    id:'report', icon:'◔', title:'금주의 리포트',
    summary:'이번 주에 많이 본 키워드와 행동을\n한 장의 주간 보고서로 정리하는 화면이에요.',
    sections:[
      ['이번 주 핵심 키워드','검색과 관심이 가장 많이 모인 키워드를\n리포트의 중심으로 잡아요.'],
      ['주간 핵심 지표','검색·찜·살!말? 같은 이번 주 활동을\n숫자로 요약해요.'],
      ['요일별 활동·취향 지분','언제 많이 둘러봤는지,\n어떤 스타일에 관심이 쏠렸는지 비교해요.'],
      ['추천 콘텐츠','핵심 키워드와 이어지는\n영상·웹 매거진을 볼 수 있어요.'],
      ['같이 지켜볼 스타일','지금 온도와 수명주기를 기준으로\n다음에 볼 스타일을 제안해요.'],
    ],
  },
  {
    id:'saved', icon:'♡', title:'찜한 키워드',
    summary:'찜한 상품과 키워드를\n가격·온도가 움직인 순서대로 지켜보는 화면이에요.',
    sections:[
      ['오늘의 이슈','찜한 것 중 최저가·급등·급락처럼\n먼저 볼 변화를 크게 보여 줘요.'],
      ['오늘 더 있었던 일','같은 날 움직인 다른 찜 항목을\n짧은 카드로 이어서 보여 줘요.'],
      ['워치리스트 요약','찜한 수, 움직인 수, 최저가 도달,\n조용한 항목을 한눈에 비교해요.'],
      ['찜한 것 전체','급등·최저가·급락·잠잠·측정 전으로\n걸러서 다시 볼 수 있어요.'],
    ],
  },
  {
    id:'temp', icon:'℃', title:'언급량 · 온도',
    demo:{mode:'dict',term:'니트',facet:'아이템'},
    summary:'키워드가 얼마나 이야기되고 얼마나 뜨거운지\n0–100 온도와 추이로 보는 화면이에요.',
    sections:[
      ['현재 온도 판정','차가움·미지근·따뜻함·과열 중\n지금 어디인지와 그 뜻을 먼저 보여 줘요.'],
      ['핵심 지표','플랫폼 점유율, 전년 같은 날과의 차이,\n새로 잡힌 키워드를 보여 줘요.'],
      ['언급량·온도 추이','말하는 양과 열기가\n함께 움직이는지 날짜별로 비교해요.'],
      ['플랫폼별 온도','플랫폼마다 온도가 다른지,\n값의 기준일이 오래되지 않았는지 봐요.'],
    ],
  },
  {
    id:'assoc', icon:'◎', title:'연관어',
    demo:{mode:'dict',term:'발레코어',facet:'스타일'},
    summary:'키워드가 아이템·소재·색·디테일·TPO·스타일과\n어떤 조합으로 함께 불리는지 보는 화면이에요.',
    sections:[
      ['확산 상태','연관어가 여러 축에 고르게 쌓였는지\n정체부터 폭발적 확산까지로 요약해요.'],
      ['핵심 연관어','점수가 가장 높은 조합과\n새로 들어온 표현을 먼저 보여 줘요.'],
      ['연관어 수 추이','연관어 종류가 늘어나는지 줄어드는지 보고\n확산이 이어지는지 판단해요.'],
      ['축별 TOP 연관어','아이템·소재·색·디테일·TPO·스타일별\n순위와 강도를 비교해요.'],
      ['근거 문장','연관어를 누르면 실제로 함께 나온 문장과\n최근 주차 흐름을 볼 수 있어요.'],
      ['정렬 기준','특징 점수와 함께 나온 횟수를 바꿔 보며\n강한 조합과 흔한 조합을 구분해요.'],
    ],
  },
  {
    id:'sentiment', icon:'⇅', title:'긍부정',
    demo:{mode:'dict',term:'스키니',facet:'디테일'},
    summary:'사람들이 사려는지 망설이는지,\n그 이유를 반응 유형으로 읽는 화면이에요.',
    sections:[
      ['구매의향 판정','구매의향 지수로 지금 반응이\n구매 쪽인지 관망 쪽인지 먼저 알려 줘요.'],
      ['핵심 반응 지표','총 반응 수와 가장 많은 긍정·부정 신호로\n표본 크기와 주된 이유를 확인해요.'],
      ['긍정·중립·부정','최근 반응의 세 비중을\n표본 수와 함께 보여 줘요.'],
      ['반응 신호 6종','질문·구매·경험·호평·비판·잡담 건수를\n실제 분류 결과로 비교해요.'],
      ['근거 문장','호평이나 비판 신호를 누르면\n판단에 쓰인 실제 문장을 볼 수 있어요.'],
    ],
  },
  {
    id:'life', icon:'∞', title:'수명주기',
    demo:{mode:'dict',term:'민트',facet:'색'},
    summary:'트렌드가 태동·확산·정점·쇠퇴 중 어디인지,\n언제 기획하면 좋을지 판단하는 화면이에요.',
    sections:[
      ['현재 단계','유행 진행도와 함께\n태동·확산·정점·쇠퇴 판정을 먼저 보여 줘요.'],
      ['기획 지표','신규 유입률, 성장 모멘텀, 시장 포화도로\n앞으로 남은 여지를 봐요.'],
      ['유행 곡선','화제성 흐름 위에서 지금 위치와\n정점을 지났는지 확인해요.'],
      ['주별 온도','최근 8주 온도를 비교해\n잠깐 튄 건지 꾸준히 오르는지 봐요.'],
      ['언급량·판매량','언급량과 실제 판매가 함께 움직이는지 보고\n관심만 높은지 실제 수요인지 가려요.'],
    ],
  },
  {
    id:'stock', icon:'%', title:'할인률 변화',
    demo:{mode:'detail',term:'[우연X후브스] 밀리터리 슬림 헨리넥 롱슬리브[딥네이비]',facet:'상품명'},
    summary:'개별 상품의 정가·판매가·할인률 변화를 보고\n살 때를 비교하는 화면이에요.',
    sections:[
      ['선택 상품','이미지·브랜드·상품명·모델번호로\n지금 보는 상품을 확인해요.'],
      ['가격 요약','정가, 판매가, 할인률과 함께\n첫 할인 시점과 최고 할인률을 보여 줘요.'],
      ['가격·할인률 추이','판매가가 언제 내려갔는지,\n할인 폭이 어떻게 변했는지 날짜별로 봐요.'],
      ['플랫폼 비교','같은 상품으로 연결된 판매처끼리 비교해요.\n없는 플랫폼은 숨겨요.'],
      ['찜 연결','찜해 두면 최저가와 가격 변화를\n찜한 키워드에서 이어 볼 수 있어요.'],
    ],
  },
  {
    id:'resale', icon:'±', title:'리세일 지수',
    demo:{mode:'detail',term:'프로 드라이 핏 타이트 반소매 피트니스 탑 - 블랙:화이트',facet:'상품명'},
    summary:'같은 상품의 중고가·매물·거래량으로\n사거나 팔 때의 가격 근거를 보는 화면이에요.',
    sections:[
      ['상품·매핑 상태','같은 상품으로 연결된 플랫폼과\n한 곳에만 있는 상품인지 먼저 밝혀요.'],
      ['구매·판매 모드','같은 가치 유지율을\n살 때는 절약률, 팔 때는 회수율로 보여 줘요.'],
      ['핵심 4지표','정가·중고가 중앙값, 현재 매물 수,\n최근 4주 중고 거래량을 봐요.'],
      ['플랫폼별 현재 가격','무신사·USED·크림 등\n값이 있는 플랫폼만 비교해요.'],
      ['현재 매물과 최근 거래','올라온 매물 가격과 실제 거래 가격을 비교해\n부르는 값과 팔린 값의 차이를 봐요.'],
      ['추천 중고 상품','브랜드만 검색했을 때 나오는 칸이에요.\n그 브랜드 중고 상품을\n가격·매물 수로 비교해요.'],
      ['리세일 시장 지표','가격 방어율, 거래량 증감률,\n정가보다 비쌌던 기간을 각각 봐요.'],
      ['가치 변화','날짜별로 정가 대비 중고 가치가\n얼마나 유지되는지 보여 줘요.'],
      ['가치 유지율과 트렌드 온도','가치 유지율과 관심 온도를 한 카드에서 비교해\n어느 쪽이 먼저 움직이는지 봐요.'],
    ],
  },
];

const TREND_ITEM=Object.fromEntries(TREND_GUIDE_ITEMS.map(item=>[item.id,item]));

/* FEED·EDIT 묶음 설명에서 메뉴마다 붙는 한 줄 요약.
 * 각 메뉴 summary 를 줄인 것이며, 새 기능을 설명하지 않는다. */
const TREND_BRIEF={
  myfeed:'내 취향에 맞는 시장 신호와 살!말? 고민',
  report:'이번 주 내 관심사를 한 장의 보고서로',
  saved:'찜한 상품·키워드의 가격·온도 변화',
  temp:'얼마나 이야기되고 얼마나 뜨거운지',
  assoc:'어떤 아이템·소재·색과 함께 불리는지',
  sentiment:'사려는지 망설이는지와 그 이유',
  life:'태동·확산·정점·쇠퇴 중 어디인지',
  stock:'정가 대비 할인률과 가격 변화',
  resale:'중고가·매물·거래량으로 본 가치',
};

const TREND_GROUPS={
  feed:[{ids:['myfeed','report','saved']}],
  edit:[
    {label:'키워드의 흐름',ids:['temp','assoc','sentiment','life']},
    {label:'상품의 가격',ids:['stock','resale']},
  ],
};

function trendGroupPreview(groups, note){
  return groups.map(group=>
    (group.label?'<div class="tgGroupHead">'+group.label+'</div>':'')+
    '<ul class="tgList">'+group.ids.map(id=>{
      const item=TREND_ITEM[id];
      return '<li><i>'+item.icon+'</i><b>'+item.title+'</b><span>'+TREND_BRIEF[id]+'</span></li>';
    }).join('')+'</ul>'
  ).join('')+(note?'<p class="tgNote">'+note+'</p>':'');
}

/* 사이드바 묶음은 라벨(FEED — 모으다)과 메뉴 목록을 한 덩어리로 강조한다. */
const sideGroup=listId=>()=>{
  const list=document.getElementById(listId);
  if(!list)return null;
  const label=list.previousElementSibling;
  return label?[label,list]:[list];
};

/* 메뉴 구조 설명은 펼침 버튼부터 EDIT 마지막 메뉴까지만 강조한다.
 * 아래쪽 빈 칸과 프로필(sFoot)까지 감싸면 메뉴가 아닌 곳까지 설명하는 것처럼 보였다. */
const sideMenu=()=>{
  const top=document.querySelector('#side .sTop'), edit=document.getElementById('sEdit');
  return top&&edit?[top,edit]:null;
};

/* EDIT 대표 화면 — 언급량·온도에서 ‘가을’을 검색한 결과. 응답은 저장해 둔 실제 값이라 API 를 부르지 않는다. */
const TREND_EDIT_SAMPLE={...TREND_ITEM.temp,demo:{mode:'dict',term:'가을',facet:'TPO'},payload:autumnDemo};
const SAMPLE_AS_OF=autumnDemo?.data?.data_as_of||autumnDemo?.data?.as_of||'';

/* 내 피드 가이드 안에서 보이는 화면만 내 피드 ↔ 언급량·온도로 바꾼다.
 * 가이드를 닫거나 다른 장으로 가면 내 피드로 돌아온다. */
function trendSceneSwitcher(){
  let restoreSample=null;
  const show=scene=>{
    if(scene==='temp'){
      if(restoreSample)return;
      restoreSample=mountTrendGuideDemo(TREND_EDIT_SAMPLE,{returnTo:'myfeed'});
      scrollTo(0,0);
      return;
    }
    if(!restoreSample)return;
    const restore=restoreSample;
    restoreSample=null;
    restore();
    scrollTo(0,0);
  };
  return {show,restore:()=>show('myfeed')};
}

/* activeIndex 가 -1 이면 카드 전체를 한 번에 보여 준다. */
function trendPreview(item, activeIndex){
  return '<div class="tgPreviewHead"><span>고정 화면 미리보기</span><em>검색·개인화 기록에 저장되지 않음</em></div>'+
    '<div class="tgPreviewTitle"><i>'+item.icon+'</i><div><b>'+item.title+'</b><span>'+item.summary+'</span></div></div>'+
    '<div class="tgPreviewGrid'+(activeIndex<0?' all':'')+'">'+item.sections.map((section,index)=>
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
function setActiveTrendTab(id){
  document.querySelectorAll('.sItem[data-tr]').forEach(el=>el.classList.toggle('on',el.dataset.tr===id));
}

/* returnTo 가 있으면 사이드바 강조만 item 으로 옮겨 그 화면을 보여 주고,
 * 되돌릴 때 returnTo 화면으로 돌아간다. 탭 버튼을 누르지 않아 router 의 현재 탭·방문 기록은 그대로다. */
function mountTrendGuideDemo(item, { returnTo = '' } = {}){
  if(!item.demo)return null;
  const beforeKW=plainClone(KW), beforeFS=plainClone(FS);
  const beforeInputs={kw:document.getElementById('kwInput')?.value||'',fs:document.getElementById('fsInput')?.value||''};
  const who=document.querySelector('#sFoot .who b');
  const beforeWho=who?.textContent||'';
  const payload=item.payload?plainClone(item.payload):guidePayload(item.id);
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
  if(returnTo)setActiveTrendTab(item.id);
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
    if(!returnTo)trRender(item.id);
    const kwInput=document.getElementById('kwInput'), fsInput=document.getElementById('fsInput');
    if(kwInput)kwInput.value=beforeInputs.kw;
    if(fsInput)fsInput.value=beforeInputs.fs;
    document.body.classList.remove('trend-guide-demo');
    if(returnTo){ setActiveTrendTab(returnTo); trRender(returnTo); }
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

/* 내 피드가 아닌 메뉴는 현재 보고 있는 분석 화면만 설명한다(2단계 역할 → 3단계 카드 읽기).
 * 1단계 전체 구조와 FEED·EDIT 대표 화면은 최초 진입 화면인 내 피드에서만 보여 준다.
 * scenes 는 내 피드 가이드가 EDIT 대표 화면을 잠시 띄울 때 쓰는 장면 전환이다(trendSceneSwitcher). */
function trendSteps(item, scenes=null){
  /* 조사는 받침에 맞춘다 — ‘언급량 · 온도은’처럼 어색하게 붙지 않게. */
  const topic=word=>word+josa(word,'은','는');
  const menuStep={
    targets:['.sItem[data-tr="'+item.id+'"]','#side'], kind:'trend-nav',
    phase:'1단계 · 현재 메뉴',
    title:topic(item.title)+' 무엇을 보나요?', body:item.summary,
    enter(){ closeDictionaryGuideDemo(); fsCloseGuidePop(); },
  };
  if(item.demo){
    const dict=item.demo.mode==='dict';
    const modeName=dict?'사전':'세부 검색';
    const modeBody=dict
      ? '오른쪽 사전 버튼을 누르면\n스타일·아이템·소재·디테일·색·TPO·브랜드 칸이 열려요.\n용어 하나를 고르고 ‘이 용어로 검색’을 누르면 돼요.'
      : (item.id==='resale'
        ? '스타일·종류·브랜드·상품명을 각각 골라요.\n상품을 고르면 그 상품의 시세를,\n브랜드만 고르면 추천 중고 상품을 보여 줘요.'
        : '스타일·종류·브랜드·상품명을 각각 골라요.\n할인률 변화는 상품명까지 골라야\n같은 상품의 정가와 판매가를 비교할 수 있어요.');
    const searchStep={
      targets:[dict&&item.id!=='life'?'#kwBar':'#fsBar','#trTabs','#trSearch'], kind:'trend-search',
      phase:'2단계 · 검색 시작',
      title:'예시로 “'+item.demo.term+'”'+josa(item.demo.term,'을','를')+' 검색했어요',
      body:'실제 FEEDiT 검색창과 결과 화면이에요.\n저장해 둔 실제 분석 결과를 보여 주며\n검색 기록에는 남지 않아요.',
      enter(){ closeDictionaryGuideDemo(); fsCloseGuidePop(); },
    };
    const modalStep={
      targets:[dict?'#dictPopBg .dictPop':'#fsPopBg .fsPop'], kind:'trend-modal',
      phase:'3단계 · '+modeName,
      title:topic(modeName)+' 이렇게 써요', body:modeBody,
      enter(){
        if(dict) openDictionaryGuideDemo(DICTIONARY_DEMO_ROWS,{f:item.demo.facet,label:item.demo.term});
        else fsOpenGuidePop();
      },
    };
    const charts=item.sections.map((section,index)=>({
      targets:GUIDE_TARGETS[item.id]?.[index]||['#trBody'], kind:'trend-chart',
      phase:'결과 읽기 · '+(index+1)+' / '+item.sections.length,
      title:topic(section[0])+' 이렇게 읽어요', body:section[1],
      enter(){ closeDictionaryGuideDemo(); fsCloseGuidePop(); },
    }));
    return [menuStep,searchStep,modalStep].concat(charts);
  }
  const details=item.sections.map((section,index)=>({
    targets:['#trBody','.trMain'], kind:'trend-detail',
    phase:'2단계 · '+item.title+' 카드 '+(index+1)+' / '+item.sections.length,
    title:topic(section[0])+' 이렇게 읽어요',
    body:section[1],
    preview:trendPreview(item,index),
  }));
  if(item.id!=='myfeed') return [menuStep].concat(details);
  /* 내 피드는 트렌드 분석의 첫 화면이다.
   * 메뉴 구조 → FEED 묶음 → FEED 대표(내 피드) → EDIT 묶음 → EDIT 대표(언급량·온도 · 가을) 순서로 걷는다.
   * 대표 화면은 실제로 그 탭 화면을 띄워 어떤 지표가 나오는지 보여 준다(scenes). */
  const onFeed=()=>scenes?.show('myfeed');
  const onSample=()=>scenes?.show('temp');
  return [
    {
      targets:[sideMenu,'#side'], kind:'trend-intro', phase:'1단계 · 메뉴 구조', enter:onFeed,
      title:'왼쪽 메뉴는 FEED와 EDIT로 나뉘어요',
      body:'위쪽 FEED는 나에게 모인 관심과 행동을,\n아래쪽 EDIT는 시장 데이터를 정리해요.\n묶음마다 대표 화면을 열어 볼게요.',
    },
    {
      targets:[sideGroup('sFeed'),'#side'], kind:'trend-group', phase:'2단계 · FEED — 모으다', enter:onFeed,
      title:'FEED는 나에게 모인 신호를 봐요',
      body:'내 취향과 검색·찜·살!말? 기록으로\n세 화면을 채워요.\n대표로 내 피드를 볼게요.',
      preview:trendGroupPreview(TREND_GROUPS.feed),
    },
    {
      targets:['#trBody','.trMain'], kind:'trend-detail', phase:'3단계 · FEED 대표 — 내 피드', enter:onFeed,
      title:'내 피드는 네 부분으로 나뉘어요',
      body:'각 부분이 무엇을 보여 주는지\n미리보기에서 확인하세요.',
      preview:trendPreview(item,-1),
    },
    {
      targets:[sideGroup('sEdit'),'#side'], kind:'trend-group', phase:'4단계 · EDIT — 고르다', enter:onFeed,
      title:'EDIT는 시장 데이터를 골라 봐요',
      body:'키워드나 상품을 직접 검색해\n시장 전체의 흐름을 분석해요.\n대표로 언급량·온도에서 ‘가을’을 찾아볼게요.',
      preview:trendGroupPreview(TREND_GROUPS.edit,'메뉴별 자세한 사용법은 각 화면에서\n오른쪽 아래 도움말 버튼 → 가이드라인으로 볼 수 있어요.'),
    },
    {
      targets:['#kwBar','#trTabs','#trSearch'], kind:'trend-search', phase:'5단계 · EDIT 대표 — 언급량 · 온도', enter:onSample,
      title:'‘가을’로 검색한 화면이에요',
      body:'EDIT 메뉴는 이렇게 검색해서 결과를 봐요.\n'+(SAMPLE_AS_OF?SAMPLE_AS_OF+' 기준으로 ':'')+'저장해 둔 실제 결과라\n검색 기록에는 남지 않아요.',
    },
    {
      targets:[()=>{
        const verdict=document.querySelector('#trBody .verdict'), kpis=document.querySelector('#trBody .kpis');
        return verdict&&kpis?[verdict,kpis]:null;
      },'#trBody .verdict'], kind:'trend-chart', phase:'6단계 · 온도와 핵심 지표', enter:onSample,
      title:'온도와 핵심 지표를 먼저 봐요',
      body:'0–100 온도와 차가움~과열 구간,\n주간 변화·화제성·성장 모멘텀,\n점유율·전년 대비·새 키워드를 보여 줘요.',
    },
    {
      targets:['#trBody .trGrid','#trBody [data-chart="tempMain"]'], kind:'trend-chart', phase:'7단계 · 추이와 플랫폼', enter:onSample,
      title:'추이와 플랫폼별 온도를 비교해요',
      body:'날짜별로 언급량과 온도가\n함께 움직이는지 보고,\n플랫폼마다 온도 차이를 비교해요.',
    },
  ];
}

function salmalSteps(){
  return [
    {
      targets:['#salmalGuideDemo [data-sm-guide="hero"]'], kind:'salmal-page', phase:'1단계 · 살!말? 둘러보기',
      title:'다른 사람의 구매 고민을 함께 판단해요',
      body:'인기순·최신순·내 취향·마감임박 탭으로\n고민 카드를 골라 보고,\n‘내 카드’에서 내가 올린 고민을 모아 봐요.', enter:showSalmalGuideFeed,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="card"]'], kind:'salmal-page', phase:'2단계 · 예시 카드',
      title:'카드에서 상품과 지금 의견을 봐요',
      body:'사진·브랜드·가격과 함께\n지금의 살/말 비율과 남은 시간을 보여 줘요.\n가이드용 예시 카드예요.', enter:showSalmalGuideFeed,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="detail"] .modalBox','#salmalGuideDemo [data-sm-guide="detail"] .modalGrid'], kind:'salmal-modal-left', phase:'3단계 · 상세·참여',
      title:'카드를 누르면 상세 화면이 열려요',
      body:'사연, 전체 투표, 나와 비슷한 사람들의 결과,\n댓글을 한 화면에서 봐요.\n프로필 둘레의 띠는 작성자의 레벨이에요.', enter:showSalmalGuideDetail,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="add"]'], kind:'salmal-page', phase:'4단계 · 고민 등록',
      title:'내 구매 고민도 물어볼 수 있어요',
      body:'‘살까말까 물어보기’를 누르면\n등록 창이 열려요.\n작성 순서를 예시로 보여 드릴게요.', enter:showSalmalGuideFeed,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="create"] .createBox'], kind:'salmal-modal-left', phase:'5단계 · 등록 창',
      title:'등록 창 하나에서 모두 적어요',
      body:'왼쪽에 상품 사진,\n오른쪽에 상품 정보와 사연을 적어요.\n가이드 화면이라 아무것도 올라가지 않아요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="image"]'], kind:'salmal-modal-left', phase:'6단계 · 상품 사진',
      title:'고민 중인 상품 사진을 올려요',
      body:'JPEG·PNG·WebP 사진을 올리면\n카드와 상세 화면의 대표 사진이 돼요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="title"]'], kind:'salmal-modal-right', phase:'7단계 · 상품명',
      title:'상품명을 정확히 적어요',
      body:'색상이나 옵션이 있다면 함께 적어 주세요.\n같은 상품을 구분하기 쉬워져요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="brand"]'], kind:'salmal-modal-right', phase:'8단계 · 브랜드',
      title:'브랜드를 고르거나 직접 적어요',
      body:'적는 동안 비슷한 브랜드가 떠요.\n목록에 없으면 그대로 적어도 돼요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="price"]'], kind:'salmal-modal-right', phase:'9단계 · 가격',
      title:'지금 결제할 가격을 적어요',
      body:'할인 중이라면 정가 말고\n실제로 낼 금액을 숫자로 적어요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="style"]'], kind:'salmal-modal-right', phase:'10단계 · 스타일',
      title:'가장 가까운 스타일을 골라요',
      body:'고른 스타일은 취향이 비슷한 사람에게\n카드를 보여 줄 때 쓰여요.', enter:showSalmalGuideCreate,
    },
    {
      targets:['#salmalGuideDemo [data-sm-guide="story"]'], kind:'salmal-modal-right', phase:'11단계 · 사연·등록',
      title:'왜 고민인지 적고 물어봐요',
      body:'핏·소재·가격 중 무엇이 고민인지 적어 주세요.\n구체적일수록 도움이 되는 댓글이 달려요.\n‘물어보기’를 누르면 등록돼요.', enter:showSalmalGuideCreate,
    },
  ];
}

/* 스타일 가이드는 목록에서 첫 스타일을 예시로 열어 상세 화면(설명 · Virtual Fitting · 아이템)까지 걷는다.
 * stOpen 은 방문 기록을 남기지 않는다. 가이드를 닫으면 원래 보던 화면(목록 또는 그 스타일)으로 돌아온다. */
function styleSceneSwitcher(){
  const home = document.getElementById('styleHome');
  const detail = document.getElementById('styleDetail');
  const detailShown = () => !!detail && detail.style.display !== 'none';
  const wasDetail = detailShown();
  const beforeId = document.querySelector('#stCats .stCat.on')?.dataset.style || '';
  let opened = wasDetail ? beforeId : '';
  const showHome = () => { if(home) home.style.display = ''; if(detail) detail.style.display = 'none'; };
  const show = scene => {
    if(scene === 'detail'){
      const id = document.querySelector('#stCats .stCat')?.dataset.style || '';
      if(id && (opened !== id || !detailShown())){ stOpen(id); opened = id; }
      return;
    }
    if(detailShown()){ showHome(); scrollTo(0, 0); }
  };
  const restore = () => {
    if(wasDetail && beforeId){
      if(opened !== beforeId || !detailShown()) stOpen(beforeId);
      return;
    }
    if(detailShown()){ showHome(); scrollTo(0, 0); }
  };
  return { show, restore };
}

/* 아이템 칸은 화면보다 길다 — 제목·정렬·종류 칩과 첫 줄 상품만 강조한다. */
function styleItemsTarget(){
  const grid = document.getElementById('stItems');
  if(!grid) return null;
  const head = grid.closest('.mwrap')?.querySelector('.mSecHead');
  const cards = [...grid.children].filter(isVisible);
  const firstTop = cards[0]?.offsetTop;
  const row = cards.filter(card => card.offsetTop === firstTop);
  return [head, document.getElementById('stItemCats'), ...row].filter(Boolean);
}

function styleSteps(scenes){
  const onHome = () => scenes?.show('home');
  const onDetail = () => scenes?.show('detail');
  return [
    {
      targets:['.styleTitle', '#styleHome'], enter:onHome,
      title:'코어별로 옷을 골라 봐요',
      body:'지금 이름이 붙어 도는 코어와\n그 뿌리가 된 원형 스타일로 나뉘어 있어요.',
    },
    {
      targets:['#stCats .stGroup', '#stCats', '#styleHome'], enter:onHome,
      title:'스타일을 누르면 상세로 들어가요',
      body:'설명, Virtual Fitting, 실제 상품까지\n한 화면에서 이어져요.\n첫 번째 스타일로 예를 들어 볼게요.',
    },
    {
      targets:['#stAbout', '#stHero'], enter:onDetail,
      title:'스타일이 어떻게 시작됐는지 읽어요',
      body:'생겨난 배경과 함께\n시작 시기·확산 계기·핵심 키워드를 정리했어요.',
    },
    {
      targets:[() => document.getElementById('stInf')?.closest('.mwrap'), '#stInf'], enter:onDetail,
      title:'Virtual Fitting으로 입은 모습을 봐요',
      body:'가상 모델이 이 스타일을 입은 모습이에요.\n실루엣과 조합을 사진으로 먼저 확인하세요.',
    },
    {
      targets:[styleItemsTarget, '#stItems'], enter:onDetail,
      title:'이 스타일의 실제 상품도 볼 수 있어요',
      body:'이 스타일 태그가 붙은 판매 상품이에요.\n종류별로 거르고 정렬을 바꿀 수 있어요.\n누르면 판매처로, 하트를 누르면 찜이 돼요.',
    },
    { ...FAB_HINT, enter:onDetail },
  ];
}

/* 챗봇 가이드는 실제 팝업을 열어 일반 → 살말 모드 순서로 걷는다.
 * 모드는 로고·Tab 과 같은 cpToggleMode 로 바꾸고, 가이드를 닫으면 처음 모드와 팝업 상태로 되돌린다. */
function chatSceneSwitcher(){
  const overlay = document.getElementById('cpOverlay');
  const wasOpen = !!overlay?.classList.contains('on');
  const wasSalmal = SM_ON;
  const open = () => {
    if(!overlay || overlay.classList.contains('on')) return;
    openChatPopup();
    /* 팝업은 열리면 입력칸에 초점을 준다. 가이드 동안 ← → 이동이 입력칸에 막히지 않게 풀어 둔다. */
    setTimeout(() => {
      const input = document.getElementById('cpInput');
      if(guide && document.activeElement === input) input.blur();
    }, 320);
  };
  const show = salmal => {
    open();
    if(SM_ON !== salmal) cpToggleMode();
  };
  const restore = () => {
    if(SM_ON !== wasSalmal) cpToggleMode();
    if(!wasOpen && overlay?.classList.contains('on')) closeChatPopup();
  };
  return { show, restore };
}

function chatSteps(scenes){
  const general = () => scenes?.show(false);
  const salmal = () => scenes?.show(true);
  return [
    {
      targets:['#cpOverlay .cpProfile', '#cpBox'], phase:'1단계 · 일반 모드', enter:general,
      title:'챗봇은 두 가지 모드로 답해요',
      body:'지금은 일반 모드예요.\n모은 데이터와 지표를 근거로\n트렌드 흐름과 코디를 알려 줘요.',
    },
    {
      targets:['#cpOverlay .cpInputWrap'], phase:'2단계 · 질문하기', enter:general,
      title:'문장으로 묻고 사진도 붙여요',
      body:'궁금한 아이템이나 키워드를 적어 보내세요.\n+ 버튼으로 사진을 붙일 수 있고,\n예시 질문을 눌러 바로 물어봐도 돼요.',
    },
    {
      targets:['#cpAv'], phase:'3단계 · 모드 전환', enter:general,
      title:'로고나 Tab 키로 모드를 바꿔요',
      body:'왼쪽 위 로고를 누르거나\nTab 키를 누르면\n일반 ↔ 살말 모드가 바뀌어요.',
    },
    {
      targets:['#cpOverlay .cpProfile', '#cpBox'], phase:'4단계 · 살말 모드', enter:salmal,
      title:'살말 모드는 살지 말지 판단해요',
      body:'고민 중인 아이템을 살지 말지 판단하고\n그렇게 본 이유를 함께 알려 줘요.',
    },
    {
      targets:['#cpVtonQuick'], phase:'5단계 · Virtual Try On', enter:salmal,
      title:'Virtual Try On으로 입혀 봐요',
      body:'입혀 보고 싶은 아이템 사진을 종류별로 올리면\n모델이 입은 모습으로 만들어 줘요.\n살말 모드 대화에서 열려요.',
    },
    {
      targets:[() => {
        const button = document.getElementById('cpNewBtn'), list = document.getElementById('cpList');
        return button && list ? [button, list] : null;
      }, '#cpList'], phase:'6단계 · 대화 목록', enter:salmal,
      title:'대화는 모드마다 따로 쌓여요',
      body:'‘새로운 대화’로 새 질문을 시작하고\n지난 대화는 목록에서 다시 열어요.\n일반·살말 대화는 따로 저장돼요.',
    },
  ];
}

/* 장마다 끝에 붙던 도움말 버튼 안내. 전체 가이드에서는 빼고 마지막 장(TOUR_OUTRO)에서 한 번만 알린다. */
const FAB_HINT = {
  targets:['#chatFab'], fabHint:true,
  title:'궁금하면 이 버튼으로 챗봇을 열어요',
  body:'어느 화면에서든 누르면\n챗봇에 바로 물어볼 수 있어요.',
};

function genericSteps(view){
  if(view === 'home') return [
    {
      targets:['#hotBar', '.hot'],
      title:'지금 뜨는 키워드부터 확인해요',
      body:'HOT TREND TOP 10이 차례로 지나가요.\n누르면 열 개를 한 번에 펼쳐 봐요.',
    },
    {
      targets:['.chatWrap .chatbar','.chatWrap'],
      title:'궁금한 건 문장으로 물어보세요',
      body:'평소 말하듯 적으면\nFEEDiT이 모은 데이터로 답해요.\n왼쪽 스위치로 살!말? 모드로 바꿀 수 있어요.',
    },
    {
      targets:['#mNav'],
      title:'위 메뉴로 다른 화면에 가요',
      body:'트렌드 분석은 시장 흐름을,\n살!말?은 구매 고민을,\n스타일은 코어별 옷을 보여 줘요.',
    },
    FAB_HINT,
  ];
  if(view === 'mypage') return [
    {
      targets:['#v-mypage .profilePanel'],
      title:'프로필에서 내 활동을 한눈에 봐요',
      body:'아바타를 눌러 아이콘을 바꿀 수 있어요.\n경험치 바에서 레벨과 남은 경험치를,\n아래에서 찜·투표·뱃지 수를 봐요.',
    },
    {
      targets:[() => document.getElementById('styleWrap')?.closest('.panel'), '#styleWrap'],
      title:'즐겨입는 스타일은 최대 3개까지 골라요',
      body:'여러 개를 고를 수 있고, 최대 3개까지예요.\n고르면 오늘의 추천이 바로 바뀌고\n‘저장’을 눌러야 계정에 남아요.',
    },
    {
      targets:['#todayRecPanel'],
      title:'오늘의 추천은 두 기준으로 골라요',
      body:'‘내 취향 기준’은 즐겨입는 스타일의 상품,\n‘지금 뜨는 코어 기준’은 확산·재상승 등\n지금 움직이는 스타일의 상품이에요.',
    },
    {
      targets:['#fbPanel', '#myColFb'],
      title:'살!말? 피드백으로 결과를 남겨요',
      body:'마감된 내 카드에 구매 여부와 후기를 남겨요.\n남긴 결과는 투표한 사람들의\n적중 기록에 쓰여요.',
    },
    FAB_HINT,
  ];
  if(view === 'price') return [
    {
      targets:['#prGrid .prCard:nth-child(1)','#prGrid'],
      title:'프리는 개인용 기본 플랜이에요',
      body:'월 0원이에요.\n살!말?과 FEED 분석을 쓸 수 있고,\nAI 챗은 하루 20회,\nEDIT는 언급량·온도까지예요.',
    },
    {
      targets:['#prGrid .prCard:nth-child(2)','#prGrid'],
      title:'프로는 매일 분석하는 분께 맞아요',
      body:'월 19,900원이에요.\nAI 챗과 EDIT 전체 분석을 쓰고\n결과를 리포트로 내보낼 수 있어요.',
    },
    {
      targets:['#prGrid .prCard:nth-child(3)','#prGrid'],
      title:'비즈니스는 팀과 연동을 위한 플랜이에요',
      body:'프로 기능에 데이터 API 연동이 더해져요.\n요금과 연동 범위는 문의로 정해요.',
    },
  ];
  return [
    {
      targets:[`#v-${view}`, '#mNav'],
      title:'이 화면의 주요 기능을 둘러보세요',
      body:'카드와 버튼을 따라가면\nFEEDiT의 분석 흐름을 쓸 수 있어요.',
    },
    {
      targets:['#mNav'],
      title:'위 메뉴로 다른 화면에 가요',
      body:'트렌드 분석, 살!말?, 스타일, 요금제를\n오갈 수 있어요.',
    },
    FAB_HINT,
  ];
}

/* ── 설명창 아이콘 ─────────────────────────────────────────
 * 아이콘은 단계마다 바꾸지 않고 페이지마다 하나로 고정한다(24 그리드 · 획 1.7, 헤더 알림·조이스틱과 같은 굵기). */
const svgIcon = d => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
const PAGE_ICONS = {
  home:svgIcon('<path d="M4 10.6 12 4l8 6.6V19a1 1 0 0 1-1 1h-4.4v-5.4H9.4V20H5a1 1 0 0 1-1-1z"/>'),
  chat:svgIcon('<path d="M4 5.5C4 4.67 4.67 4 5.5 4h13c.83 0 1.5.67 1.5 1.5v10c0 .83-.67 1.5-1.5 1.5H9l-4 3.5V17h.5C4.67 17 4 16.33 4 15.5z"/>'),
  trend:svgIcon('<path d="M4 19.5h16"/><path d="m5 15.5 4.5-5 3.5 3 6-7"/><path d="M15 6.5h4v4"/>'),
  salmal:svgIcon('<path d="M8 5v9"/><path d="M13 8.4a3 3 0 1 1 4.5 2.6c-.95.55-1.5 1.25-1.5 2.3v.7"/>' +
    '<circle cx="8" cy="18.6" r="1.05" fill="currentColor" stroke="none"/><circle cx="16" cy="18.6" r="1.05" fill="currentColor" stroke="none"/>'),
  style:svgIcon('<path d="M10 6.2a2 2 0 1 1 2.7 1.87c-.42.16-.7.56-.7 1V10"/><path d="M12 10 3.7 15.6a1.1 1.1 0 0 0 .62 2.02h15.36a1.1 1.1 0 0 0 .62-2.02z"/>'),
  price:svgIcon('<path d="m4.5 6 3.5 12 4-9.5 4 9.5 3.5-12"/><path d="M3.5 10.8h17M3.5 13.8h17"/>'),
  mypage:svgIcon('<circle cx="12" cy="8.5" r="3.6"/><path d="M5 19.6c1.1-3.4 3.8-5.2 7-5.2s5.9 1.8 7 5.2"/>'),
};
/* 마지막 단계(조이스틱 강조)만 단계 아이콘(step.icon)을 쓴다 — 헤더 조이스틱 버튼과 같은 그림. */
PAGE_ICONS.joystick = svgIcon('<path d="M3.5 15.3 12 11.5l8.5 3.8L12 19.1Z"/><path d="M3.5 15.3v2.3l8.5 3.8 8.5-3.8v-2.3M12 19.1v2.3"/>' +
  '<path d="M12 15.2V8.6"/><circle cx="12" cy="6" r="2.6" fill="currentColor"/>');
const pageIcon = key => PAGE_ICONS[key] || PAGE_ICONS.home;
const ICON_PREV = svgIcon('<path d="M19 12H5"/><path d="m11 6-6 6 6 6"/>');
const ICON_NEXT = svgIcon('<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>');
const ICON_DONE = svgIcon('<path d="m5 12.5 4.5 4.5L19 7.5"/>');

/* ── 전체 가이드(조이스틱 버튼) ─────────────────────────────
 * 상단 탭 순서대로 페이지 가이드를 한 흐름으로 잇는다.
 * 각 장은 하단 버튼 가이드와 같은 단계를 쓰고, 장이 바뀔 때 실제로 그 페이지로 이동한다.
 * 왼쪽 목차에서 장을 고르면 그 페이지로 옮겨 가 첫 단계부터 보여 준다. */
const TOUR_CHAPTERS = [
  { view:'home', title:'홈', sub:'오늘의 흐름 · 바로 묻기' },
  { view:'chat', title:'챗봇', sub:'일반 · 살말 모드' },
  { view:'trend', title:'트렌드 분석', sub:'FEED · EDIT' },
  { view:'salmal', title:'살!말?', sub:'구매 고민 함께 판단' },
  { view:'style', title:'스타일', sub:'코어 · 착장 · 상품' },
  /* 마이페이지는 로그인한 사람에게만 열린다(router.js goView 가 로그인 화면으로 보낸다). */
  { view:'mypage', title:'마이페이지', sub:'프로필 · 취향 · 피드백', auth:true },
  { view:'price', title:'요금제', sub:'프리 · 프로 · 비즈니스' },
];
const LOCKED_SUB = '로그인하면 볼 수 있어요';

const chapterOpen = index => !!TOUR_CHAPTERS[index] && (!TOUR_CHAPTERS[index].auth || !!AUTH.in);
/* 잠긴 장(로그인 전 마이페이지)은 건너뛰고 앞뒤로 열린 장을 찾는다. 없으면 -1. */
function neighborChapter(from, dir){
  for(let index = from + dir; index >= 0 && index < TOUR_CHAPTERS.length; index += dir){
    if(chapterOpen(index)) return index;
  }
  return -1;
}

/* 마지막 장 끝에 한 번만 붙인다. 장마다 반복되던 도움말 버튼 안내(fabHint)는 이 단계로 모은다. */
const TOUR_OUTRO = {
  targets:['#tourBtn'], icon:'joystick', hideClose:true,
  title:'가이드는 언제든 다시 볼 수 있어요',
  body:'조이스틱 버튼은 전체 가이드를,\n오른쪽 아래 도움말 버튼의 ‘가이드라인’은\n지금 화면 가이드를 열어요.',
};

const pad2 = n => String(n).padStart(2, '0');

function stopGuideSync(){
  if(guideRaf) cancelAnimationFrame(guideRaf);
  guideRaf = 0;
}

function guideTarget(){
  if(!guide) return null;
  const step = guide.steps[guideStep];
  return step ? firstTarget(step.targets) : null;
}

function viewportSize(){
  return {
    vw:window.innerWidth || document.documentElement.clientWidth || 1280,
    vh:window.innerHeight || document.documentElement.clientHeight || 800,
  };
}

function unionRect(elements){
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  for(const el of elements){
    const rect = el.getBoundingClientRect();
    if(!rect.width && !rect.height) continue;
    left = Math.min(left, rect.left); top = Math.min(top, rect.top);
    right = Math.max(right, rect.right); bottom = Math.max(bottom, rect.bottom);
  }
  if(left === Infinity) return null;
  return { left, top, right, bottom, width:right-left, height:bottom-top };
}

function cornerRadius(el, rect){
  let value = '0';
  try { value = getComputedStyle(el).borderTopLeftRadius || '0'; } catch (_) {}
  const size = parseFloat(value) || 0;
  return value.trim().endsWith('%') ? Math.min(rect.width, rect.height) * size / 100 : size;
}

/* 강조 테두리는 대상의 실제 모양을 따른다.
 * 예전에는 모든 대상에 999px 모서리와 넓은 좌우 여백을 씌워,
 * 넓은 카드 묶음이 타원으로 잘리고 실제 화면 비율과 어긋났다.
 *
 * - 여백은 작은 버튼 6px, 그 밖에는 10px로 네 변을 같게 둔다.
 * - 원·알약 모양 대상만 알약으로 감싸고, 나머지는 대상 모서리 + 여백만큼만 둥글린다.
 * - 화면 가장자리에 붙은 변(사이드바 왼쪽·아래 등)은 화면 밖으로 빼서 잘린 테두리가 보이지 않게 한다. */
/* 페이지 본문은 상단 고정 헤더(.mHead) 밑으로 스크롤된다. 헤더에 가린 부분은 보이지 않는 곳으로 본다.
 * 헤더 자체·고정 사이드바·모달·가이드 목업 안의 대상은 헤더와 상관없다. */
const OVERLAY_SCOPES = '.mHead, #side, .modalOverlay, .smGuideStage, .guideTour, #dictPopBg, #fsPopBg, .acctModal';
function headerInset(el){
  if(!el || el.closest(OVERLAY_SCOPES)) return 0;
  const head = document.querySelector('.mHead');
  const rect = head && isVisible(head) ? head.getBoundingClientRect() : null;
  return rect && rect.bottom > 0 ? rect.bottom : 0;
}

function spotBox(elements, rect, vw, vh, inset = 0){
  const small = rect.width < 180 && rect.height < 80;
  const pad = small ? 6 : 10;
  const left = rect.left <= 1 ? -12 : Math.max(6, rect.left - pad);
  /* 헤더 밑으로 들어간 대상은 헤더 바로 아래에서 강조를 시작한다 — 강조 구멍으로 헤더가 비쳐 보이지 않게. */
  const top = inset && rect.top - pad < inset ? inset : rect.top <= 1 ? -12 : Math.max(6, rect.top - pad);
  const right = rect.right >= vw - 1 ? vw + 12 : Math.min(vw - 6, rect.right + pad);
  const bottom = rect.bottom >= vh - 1 ? vh + 12 : Math.min(vh - 6, rect.bottom + pad);
  const width = Math.max(1, right - left);
  const height = Math.max(1, bottom - top);
  const own = elements.length === 1 ? cornerRadius(elements[0], rect) : 0;
  const pill = own > 0 && own >= Math.min(rect.width, rect.height) / 2 - 1;
  const radius = pill ? Math.min(width, height) / 2 : Math.min(26, Math.max(10, own + pad));
  return { left, top, right, bottom, width, height, radius };
}

function overlaps(a, b, gap = 0){
  return a.left < b.right + gap && a.right > b.left - gap && a.top < b.bottom + gap && a.bottom > b.top - gap;
}

/* 목차는 강조 영역을 가리지 않는 자리를 찾는다.
 * 펼친 목차가 들어갈 자리가 없으면 번호만 남긴 좁은 막대로 접고,
 * 그래도 겹치면(트렌드 사이드바 설명처럼 왼쪽 끝을 강조할 때) 잠시 숨긴다. */
const TOC_WIDTH = { full:268, rail:64 };
/* 목차는 배경이 없어서, 글자가 많은 고정 화면 요소 위에 얹히면 글자끼리 뒤섞인다.
 * 트렌드 사이드바가 떠 있으면 그 오른쪽부터, 챗봇 팝업처럼 왼쪽을 다 덮는 창이 떠 있으면 자리가 없다(null). */
function tocLeftEdge(vw){
  const box = chatPopupOpen() ? document.getElementById('cpBox') : null;
  const boxRect = box?.getBoundingClientRect();
  if(boxRect?.width && boxRect.left < TOC_WIDTH.rail + 36) return null;
  const side = currentView() === 'trend' ? document.getElementById('side') : null;
  const sideRect = side && isVisible(side) ? side.getBoundingClientRect() : null;
  if(sideRect?.width && sideRect.right < vw / 2) return Math.round(sideRect.right + 18);
  return 18;
}

function placeTourToc(spot, vw, vh){
  const toc = guide?.toc;
  if(!toc) return null;
  /* 왼쪽 끝에 붙은 대상(트렌드 사이드바)을 강조할 때 목차가 그 위아래에 얹히면 사이드바와 뒤섞여 보인다. */
  const left = vw <= 760 || spot.left < 0 ? null : tocLeftEdge(vw);
  if(left === null){ toc.dataset.mode = 'tuck'; return null; }
  if(guide.tocLeft !== left){ guide.tocLeft = left; toc.style.left = left + 'px'; }
  const height = toc.offsetHeight || 480;
  const maxTop = Math.max(14, vh - height - 14);
  const tops = [guide.tocTop, (vh - height) / 2, spot.bottom + 16, spot.top - 16 - height, 76, vh - height - 18]
    .filter(Number.isFinite)
    .map(top => Math.round(Math.max(14, Math.min(top, maxTop))));
  for(const mode of ['full', 'rail']){
    for(const top of tops){
      const box = { left, top, right:left + TOC_WIDTH[mode], bottom:top + height };
      if(overlaps(box, spot, 12)) continue;
      if(toc.dataset.mode !== mode) toc.dataset.mode = mode;
      if(guide.tocTop !== top){ guide.tocTop = top; toc.style.top = top + 'px'; }
      return box;
    }
  }
  if(toc.dataset.mode !== 'tuck') toc.dataset.mode = 'tuck';
  return null;
}

function setCardSpot(card, kind, left, top){
  card.classList.remove('above', 'sideTarget', 'leftOf', 'detached');
  if(kind) card.classList.add(kind);
  card.style.left = Math.round(left) + 'px';
  card.style.top = Math.round(top) + 'px';
}

/* 설명창은 강조 영역 아래 → 위 → 오른쪽 → 왼쪽 순서로 들어갈 자리를 찾고(세로로 긴 대상은 옆부터),
 * 화살표는 설명창이 화면 끝에 밀려도 대상 가운데를 가리킨다. */
function placeCard(step, rect, spot, vw, vh, toc, close){
  const card = guide.card;
  const cw = card.offsetWidth, ch = card.offsetHeight;
  const gap = 16, edge = 16;
  const minLeft = toc ? toc.right + 14 : edge;
  const maxLeft = Math.max(minLeft, vw - cw - edge);
  const maxTop = Math.max(edge, vh - ch - edge);
  const clampX = x => Math.max(minLeft, Math.min(x, maxLeft));
  const clampY = y => Math.max(edge, Math.min(y, maxTop));
  const cx = (Math.max(rect.left, 0) + Math.min(rect.right, vw)) / 2;
  const cy = (Math.max(rect.top, 0) + Math.min(rect.bottom, vh)) / 2;
  const kind = step?.kind || '';
  /* 자리를 정한 뒤 오른쪽 위 ‘중단하기’와 겹치면 먼저 왼쪽으로 비킨다(대상과의 위아래 관계와 화살표를 지킨다).
   * 왼쪽에 자리가 없을 때만 그 아래로 내린다. 화살표는 옮긴 자리 기준으로 대상 가운데를 다시 가리킨다. */
  const clearClose = (left, top) => {
    if(!close || !overlaps({ left, top, right:left + cw, bottom:top + ch }, close, 10)) return [left, top];
    const shifted = close.left - 12 - cw;
    return shifted >= minLeft ? [shifted, top] : [left, Math.min(maxTop, close.bottom + 12)];
  };
  const place = (cls, x, y, axis) => {
    const [left, top] = clearClose(x, y);
    if(axis === 'x') card.style.setProperty('--guide-ax', Math.max(24, Math.min(cx - left, cw - 24)) + 'px');
    if(axis === 'y') card.style.setProperty('--guide-ay', Math.max(24, Math.min(cy - top, ch - 24)) + 'px');
    setCardSpot(card, cls, left, top);
    return true;
  };

  if(kind === 'trend-modal' || kind.startsWith('salmal-modal')){
    /* 모달 안 입력칸이 왼쪽/오른쪽 어느 열에 있든 설명창 위치는 흔들리지 않는다. */
    return place('detached', Math.max(minLeft, vw - cw - 28), Math.max(edge, vh - ch - 28));
  }
  if(kind === 'trend-detail'){
    return place('detached', clampX((minLeft + vw - edge - cw) / 2), clampY((vh - ch) / 2));
  }
  if(['trend-intro', 'trend-nav', 'trend-group'].includes(kind) && vw > 760){
    return place('sideTarget', clampX(spot.right + 20), clampY(cy - ch / 2), 'y');
  }
  const sides = {
    below:() => spot.bottom + gap + ch <= vh - edge && place('', clampX(cx - cw / 2), spot.bottom + gap, 'x'),
    above:() => spot.top - gap - ch >= edge && place('above', clampX(cx - cw / 2), spot.top - gap - ch, 'x'),
    right:() => spot.right + gap + cw <= vw - edge && place('sideTarget', Math.max(minLeft, spot.right + gap), clampY(cy - ch / 2), 'y'),
    left:() => spot.left - gap - cw >= minLeft && place('leftOf', spot.left - gap - cw, clampY(cy - ch / 2), 'y'),
  };
  /* 세로로 긴 대상(살!말? 카드 등)은 옆에 붙여야 화살표가 대상 한가운데를 가리킨다. */
  const tall = rect.height > vh * .45 && rect.width < vw * .5;
  const order = tall ? ['right', 'left', 'below', 'above'] : ['below', 'above', 'right', 'left'];
  for(const side of order) if(sides[side]()) return;
  /* 화면을 거의 채우는 대상은 강조 영역과 가장 덜 겹치는 모서리에 둔다(‘중단하기’를 피한 뒤의 자리로 비교). */
  const visible = { left:Math.max(spot.left, 0), top:Math.max(spot.top, 0), right:Math.min(spot.right, vw), bottom:Math.min(spot.bottom, vh) };
  const corners = [[maxLeft, maxTop], [minLeft, maxTop], [maxLeft, edge], [minLeft, edge]];
  let best = corners[0], bestArea = Infinity;
  for(const corner of corners){
    const [left, top] = clearClose(corner[0], corner[1]);
    const w = Math.max(0, Math.min(left + cw, visible.right) - Math.max(left, visible.left));
    const h = Math.max(0, Math.min(top + ch, visible.bottom) - Math.max(top, visible.top));
    if(w * h < bestArea){ bestArea = w * h; best = [left, top]; }
  }
  return place('detached', best[0], best[1]);
}

function placeGuide(){
  if(!guide) return;
  const step = guide.steps[guideStep];
  const elements = guideTarget();
  if(!step || !elements) return;
  const rect = unionRect(elements);
  if(!rect) return;
  const { vw, vh } = viewportSize();
  const spot = spotBox(elements, rect, vw, vh, headerInset(elements[0]));
  guide.spot.classList.remove('idle');
  Object.assign(guide.spot.style, {
    left:spot.left+'px', top:spot.top+'px', width:spot.width+'px', height:spot.height+'px', borderRadius:spot.radius+'px',
  });
  const toc = placeTourToc(spot, vw, vh);
  const close = step.hideClose ? null : placeClose(vw);
  placeCard(step, rect, spot, vw, vh, toc, close);
}

/* 오른쪽 위 ‘중단하기’ — 헤더 오른쪽 묶음(이름·알림·조이스틱) 줄 가운데에, 오른쪽 끝은 조이스틱 끝에 맞춘다.
 * 가이드 동안 헤더 아이콘은 눌리지 않으므로 그 위를 덮어도 된다.
 * 처음부터 끝까지 이 자리에 고정한다 — 강조 영역을 피해 옮겨 다니지 않는다.
 * 조이스틱을 강조하는 마지막 단계(TOUR_OUTRO.hideClose)에서만 숨긴다.
 * 설명창이 이 자리와 겹치면 설명창 쪽이 비키고(placeCard), 그래도 겹치면 설명창이 위에 놓인다(z-index). */
function placeClose(vw){
  const button = guide?.close;
  if(!button) return null;
  const width = button.offsetWidth || 92, height = button.offsetHeight || 38;
  const anchor = document.getElementById('mHeadR')?.getBoundingClientRect();
  const inHeader = anchor?.width && anchor.right > vw / 2 && anchor.bottom > 0;
  const left = Math.round((inHeader ? anchor.right : vw - 32) - width);
  const top = inHeader ? Math.round(anchor.top + (anchor.height - height) / 2) : 18;
  if(guide.closeLeft !== left){ guide.closeLeft = left; button.style.left = left + 'px'; }
  if(guide.closeTop !== top){ guide.closeTop = top; button.style.top = top + 'px'; }
  return { left, top, right:left + width, bottom:top + height };
}

/* 장을 옮기는 동안에는 강조 구멍을 화면 가운데로 닫아 두었다가 새 대상에서 다시 연다. */
function closeSpot(){
  if(!guide) return;
  const { vw, vh } = viewportSize();
  guide.spot.classList.add('idle');
  Object.assign(guide.spot.style, { left:(vw/2)+'px', top:(vh/2)+'px', width:'0px', height:'0px' });
}

function startGuideSync(){
  stopGuideSync();
  const tick = () => { placeGuide(); guideRaf = requestAnimationFrame(tick); };
  guideRaf = requestAnimationFrame(tick);
}

/* 화면 밖에 있는 대상은 가운데로 스크롤한다. 고정된 사이드바와 화면보다 큰 영역은 그대로 둔다. */
function revealTarget(step, elements){
  const el = elements[0];
  if(!el?.scrollIntoView || el.closest('#side')) return;
  const rect = unionRect(elements);
  if(!rect) return;
  const { vh } = viewportSize();
  const inset = headerInset(el);
  const room = vh - inset;
  const hidden = rect.top < inset || rect.bottom > vh;
  if(step.kind !== 'trend-chart' && !hidden) return;
  /* 헤더 높이만큼 위 여백을 두고 스크롤한다(scroll-margin). 끝나면 원래 값으로 돌린다. */
  const scrollTo = (block, margin) => {
    const before = el.style.scrollMarginTop;
    el.style.scrollMarginTop = margin + 'px';
    el.scrollIntoView({ block, behavior:'instant' });
    el.style.scrollMarginTop = before;
  };
  if(rect.height <= room * .85){
    /* 여러 요소를 묶은 대상은 묶음 전체가 헤더 아래 가운데에 오도록 첫 요소 위쪽 여백을 계산한다. */
    const margin = inset + Math.max(16, (room - rect.height) / 2) + (rect.top - el.getBoundingClientRect().top) * -1;
    scrollTo('start', Math.max(inset + 16, margin));
    return;
  }
  /* 화면보다 큰 대상은 위쪽 머리가 헤더 바로 아래에 오게 둔다. */
  if(rect.top < inset || rect.top > inset + room * .5) scrollTo('start', inset + 20);
}

/* 페이지마다 바꿔 둔 가이드용 상태(목업·임시 캐시·사이드바)를 되돌린다. */
function releasePageState(){
  if(!guide) return;
  const restoreDemo = guide.restoreDemo;
  const restoreSide = guide.restoreSide;
  guide.restoreDemo = null;
  guide.restoreSide = null;
  if(restoreDemo) restoreDemo();
  /* 좁은 화면에서는 단계마다 사이드바를 접고 폈으므로(syncTrendSide) 처음 상태 그대로 되돌린다. */
  if(restoreSide) trSideOpen(!!restoreSide.wasOpen);
}

function closeGuide(){
  stopGuideSync();
  if(guide?.tour) guide.tour.seq += 1;
  if(guide && guide.root) guide.root.remove();
  releasePageState();
  document.body.classList.remove('guide-open');
  guide = null;
  guideStep = 0;
}

function paintTour(){
  if(!guide) return;
  const tour = guide.tour;
  if(!tour){ guide.brand.textContent = 'FEEDiT'; return; }
  const total = guide.steps.length;
  const local = total ? Math.min(guideStep + 1, total) : 0;
  const progress = (tour.chapter + (total ? local / total : 0)) / TOUR_CHAPTERS.length;
  guide.root.style.setProperty('--tour-progress', (progress * 100).toFixed(1) + '%');
  guide.root.querySelectorAll('[data-tour-chapter]').forEach(button => {
    const index = Number(button.dataset.tourChapter);
    const current = index === tour.chapter;
    button.classList.toggle('on', current);
    button.classList.toggle('done', !current && tour.done.has(index));
    if(current) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
    const locked = !chapterOpen(index);
    button.disabled = locked;
    button.classList.toggle('locked', locked);
    if(locked) button.title = LOCKED_SUB;
    else button.removeAttribute('title');
    const meta = button.querySelector('.tcMeta');
    if(meta) meta.textContent = current && total ? local + ' / ' + total + ' 단계' : locked ? LOCKED_SUB : TOUR_CHAPTERS[index].sub;
  });
  /* 좁은 화면의 장 칩은 가로로 넘치므로 지금 장을 가운데로 끌어온다. */
  const chips = guide.root.querySelector('.tourChips');
  const chip = chips?.querySelector('[data-tour-chapter="' + tour.chapter + '"]');
  if(chips && chip && chips.clientWidth){
    /* offsetLeft 는 설명창 기준이라 칩 줄의 시작 위치를 빼 준다. */
    chips.scrollLeft = chip.offsetLeft - chips.offsetLeft - (chips.clientWidth - chip.offsetWidth) / 2;
  }
  const chapter = TOUR_CHAPTERS[tour.chapter];
  guide.brand.textContent = pad2(tour.chapter + 1) + ' ' + chapter.title;
}

function finishSteps(){
  const next = guide?.tour ? neighborChapter(guide.tour.chapter, 1) : -1;
  if(next >= 0){
    guide.tour.done.add(guide.tour.chapter);
    gotoChapter(next, 0);
    return;
  }
  closeGuide();
}

/* 좁은 화면(920px 이하, router.js 와 같은 기준)에서는 트렌드 사이드바가 본문 위를 덮는다.
 * 사이드바를 설명하는 단계에서만 펼치고, 결과 화면을 설명하는 단계에서는 접는다.
 * 가이드를 닫으면 releasePageState 가 처음 상태로 돌려놓는다. */
const SIDE_KINDS = ['trend-intro', 'trend-nav', 'trend-group'];
function syncTrendSide(step){
  if(!step.kind?.startsWith('trend-') || typeof matchMedia !== 'function' || !matchMedia('(max-width:920px)').matches) return;
  trSideOpen(SIDE_KINDS.includes(step.kind));
}

function paintGuideStep(dir = 1){
  if(!guide) return;
  const step = guide.steps[guideStep];
  if(step && guide.enteredStep!==guideStep){
    if(typeof step.enter==='function')step.enter();
    syncTrendSide(step);
    guide.enteredStep=guideStep;
  }
  const target = guideTarget();
  if(!step || !target){
    /* 대상이 없는 단계는 진행 방향으로 건너뛴다. */
    guideStep += dir < 0 ? -1 : 1;
    if(guideStep < 0){
      const prev = guide.tour ? neighborChapter(guide.tour.chapter, -1) : -1;
      if(prev >= 0) return gotoChapter(prev, -1);
      guideStep = 0;
      return paintGuideStep(1);
    }
    if(guideStep >= guide.steps.length) return finishSteps();
    return paintGuideStep(dir);
  }
  const iconKey = step.icon || guide.view;
  if(guide.iconView !== iconKey){
    guide.icon.innerHTML = pageIcon(iconKey);
    guide.iconView = iconKey;
  }
  guide.close.hidden = !!step.hideClose;
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
  guide.count.textContent = step.counter || `${guideStep + 1} / ${guide.steps.length}`;
  const tour = guide.tour;
  const canPrev = guideStep > 0 || !!(tour && neighborChapter(tour.chapter, -1) >= 0);
  guide.prev.disabled = !canPrev;
  const nextChapter = tour ? TOUR_CHAPTERS[neighborChapter(tour.chapter, 1)] || null : null;
  const lastStep = guideStep >= guide.steps.length - 1;
  const nextState = !lastStep ? 'next' : nextChapter ? 'chapter' : 'done';
  const nextLabel = nextState === 'next' ? '다음 설명' : nextState === 'chapter' ? '다음 장: ' + nextChapter.title : '가이드 마치기';
  if(guide.nextState !== nextState){
    guide.next.innerHTML = nextState === 'done' ? ICON_DONE : ICON_NEXT;
    guide.next.classList.toggle('done', nextState === 'done');
    guide.nextState = nextState;
  }
  guide.next.setAttribute('aria-label', nextLabel);
  guide.next.title = nextLabel;
  guide.skip.title = tour && nextChapter ? '이 장 건너뛰기' : '가이드 마치기';
  paintTour();
  guide.card.style.visibility = 'hidden';
  const activeGuide = guide;
  const seq = ++activeGuide.paintSeq;
  requestAnimationFrame(() => {
    if(guide!==activeGuide || activeGuide.paintSeq!==seq)return;
    revealTarget(step, target);
    placeGuide();
    guide.card.style.visibility = 'visible';
    guide.card.classList.remove('enter');
    void guide.card.offsetWidth;
    guide.card.classList.add('enter');
    startGuideSync();
  });
}

/* 건너뛰기 — 전체 가이드에서는 지금 장을 넘겨 다음 장으로 간다(완료 표시는 하지 않는다).
 * 페이지 하나만 보는 하단 버튼 가이드나 마지막 장에서는 가이드를 마친다. */
function skipChapter(){
  if(!guide) return;
  const next = guide.tour ? neighborChapter(guide.tour.chapter, 1) : -1;
  if(next >= 0) gotoChapter(next, 0);
  else closeGuide();
}

function goNext(){
  if(!guide || !guide.steps.length) return;
  const step = guide.steps[guideStep];
  if(step && typeof step.after === 'function') step.after();
  if(guideStep >= guide.steps.length - 1) return finishSteps();
  guideStep += 1;
  paintGuideStep(1);
}

function goPrev(){
  if(!guide || !guide.steps.length) return;
  if(guideStep <= 0){
    const prev = guide.tour ? neighborChapter(guide.tour.chapter, -1) : -1;
    if(prev >= 0) gotoChapter(prev, -1);
    return;
  }
  guideStep -= 1;
  guide.enteredStep = -1;
  paintGuideStep(-1);
}

function tourTocHTML(){
  return '<nav class="tourToc" data-mode="full" aria-label="전체 가이드 목차">' +
    '<div class="tourTocHead"><span class="tourTocMark" aria-hidden="true"></span>' +
      '<span class="tourTocName"><em>FEEDiT GUIDE</em><b>전체 가이드</b></span><span class="tourTocBar"><i></i></span></div>' +
    '<ol>' + TOUR_CHAPTERS.map((chapter, index) =>
      '<li><button type="button" data-tour-chapter="' + index + '" aria-label="' + chapter.title + ' 가이드로 이동">' +
        '<span class="tcNo">' + pad2(index + 1) + '</span>' +
        '<span class="tcTx"><b>' + chapter.title + '</b><em class="tcMeta">' + chapter.sub + '</em></span>' +
      '</button></li>'
    ).join('') + '</ol></nav>';
}

/* 좁은 화면에서는 왼쪽 목차 대신 설명창 위에 장 이름을 칩으로 늘어놓는다. */
function tourChipsHTML(){
  return '<div class="tourChips" aria-label="전체 가이드 목차">' + TOUR_CHAPTERS.map((chapter, index) =>
    '<button type="button" data-tour-chapter="' + index + '">' + pad2(index + 1) + ' ' + chapter.title + '</button>'
  ).join('') + '</div>';
}

function buildGuide(steps, { tour = false } = {}){
  const root = document.createElement('div');
  root.className = 'guideTour' + (tour ? ' isTour' : '');
  root.innerHTML =
    '<button type="button" class="guideScrim" aria-label="가이드 닫기"></button>' +
    '<div class="guideSpot idle" aria-hidden="true"></div>' +
    '<button type="button" class="guideClose">중단하기</button>' +
    (tour ? tourTocHTML() : '') +
    '<section class="guideCard" role="dialog" aria-modal="true" aria-labelledby="guideTitle">' +
      (tour ? tourChipsHTML() : '') +
      '<div class="guidePhase" hidden></div>' +
      '<div class="guideHead"><span class="guideIcon"></span><h3 id="guideTitle"></h3><em>FEEDiT</em></div>' +
      '<p class="guideBody"></p><div class="guidePreview" hidden></div><div class="guideLine"></div>' +
      /* 왼쪽 끝은 건너뛰기, 오른쪽은 ← 진행 번호 → (다음 화살표만 주황 원으로 강조) */
      '<div class="guideFoot"><button type="button" class="guideSkip">건너뛰기</button>' +
      '<div class="guideNav"><button type="button" class="guidePrev" aria-label="이전 설명">' + ICON_PREV + '</button>' +
      '<span class="guideCount"></span>' +
      '<button type="button" class="guideNext" aria-label="다음 설명">' + ICON_NEXT + '</button></div></div>' +
    '</section>';
  document.body.appendChild(root);
  document.body.classList.add('guide-open');
  const built = {
    root, steps, paintSeq:0, enteredStep:-1, tocTop:null,
    spot:root.querySelector('.guideSpot'), card:root.querySelector('.guideCard'), toc:root.querySelector('.tourToc'),
    icon:root.querySelector('.guideIcon'), title:root.querySelector('h3'), body:root.querySelector('.guideBody'),
    brand:root.querySelector('.guideHead em'),
    phase:root.querySelector('.guidePhase'), preview:root.querySelector('.guidePreview'),
    count:root.querySelector('.guideCount'), prev:root.querySelector('.guidePrev'), next:root.querySelector('.guideNext'),
    skip:root.querySelector('.guideSkip'), close:root.querySelector('.guideClose'),
    view:'', iconView:'', nextState:'', closeTop:null, closeLeft:null,
  };
  /* 목차 머리에는 헤더 조이스틱 아이콘을 그대로 옮겨 단다 — 번호만 남는 막대 모양에서도 무엇인지 보이게. */
  const mark = root.querySelector('.tourTocMark');
  const joystick = document.querySelector('#tourBtn svg');
  if(mark && joystick) mark.appendChild(joystick.cloneNode(true));
  const { vw, vh } = viewportSize();
  Object.assign(built.spot.style, { left:(vw/2)+'px', top:(vh/2)+'px', width:'0px', height:'0px' });
  /* 전체 가이드는 길어서, 어두운 바깥을 잘못 눌러 처음부터 다시 보는 일이 없게 한다.
   * 가이드를 그만둘 때는 오른쪽 위 ‘중단하기’나 Esc 를 쓴다. 건너뛰기는 지금 장만 넘긴다. */
  root.querySelector('.guideScrim').addEventListener('click', () => { if(!guide?.tour) closeGuide(); });
  built.close.addEventListener('click', event => { event.stopPropagation(); closeGuide(); });
  built.skip.addEventListener('click', event => { event.stopPropagation(); skipChapter(); });
  built.prev.addEventListener('click', event => { event.stopPropagation(); goPrev(); });
  built.next.addEventListener('click', event => { event.stopPropagation(); goNext(); });
  root.addEventListener('click', event => {
    const chapter = event.target.closest('[data-tour-chapter]');
    if(!chapter) return;
    event.stopPropagation();
    gotoChapter(Number(chapter.dataset.tourChapter), 0);
  });
  return built;
}

/* 페이지별 가이드 단계와, 가이드 동안 바꿔 둔 화면 상태를 되돌리는 함수를 함께 만든다.
 * 하단 버튼 가이드와 전체 가이드가 같은 단계를 쓴다. */
async function preparePageGuide(view, { tour = false } = {}){
  /* 전체 가이드는 장마다 반복되던 도움말 버튼 안내(fabHint)를 빼고, 마지막 장 끝에 한 번만 알린다. */
  const finish = steps => {
    if(!tour) return steps;
    const last = TOUR_CHAPTERS[TOUR_CHAPTERS.length - 1].view === view;
    return steps.filter(step => !step.fabHint).concat(last ? [TOUR_OUTRO] : []);
  };
  if(view === 'trend'){
    const item = tour ? TREND_ITEM.myfeed : activeTrendItem();
    const side = document.getElementById('side');
    const wasOpen = !!side?.classList.contains('open');
    if(!wasOpen){ trSideOpen(true); await frame(); }
    const restoreItem = mountTrendGuideDemo(item);
    const scenes = item.id === 'myfeed' ? trendSceneSwitcher() : null;
    const restoreDemo = () => { if(scenes) scenes.restore(); if(restoreItem) restoreItem(); };
    return { steps:trendSteps(item, scenes), restoreSide:{ wasOpen }, restoreDemo };
  }
  if(view === 'salmal'){
    const restoreDemo = mountSalmalGuideDemo();
    return { steps:salmalSteps(), restoreDemo };
  }
  if(view === 'style'){
    const scenes = styleSceneSwitcher();
    return { steps:finish(styleSteps(scenes)), restoreDemo:scenes.restore };
  }
  if(view === 'chat'){
    const scenes = chatSceneSwitcher();
    return { steps:finish(chatSteps(scenes)), restoreDemo:scenes.restore };
  }
  return { steps:finish(genericSteps(view)) };
}

/* 챗봇 팝업이 떠 있으면 하단 버튼 가이드는 뒤 화면 대신 챗봇을 설명한다. */
const chatPopupOpen = () => !!document.getElementById('cpOverlay')?.classList.contains('on');

/* 트렌드 분석 장은 언제나 첫 화면인 내 피드에서 설명한다.
 * 다른 화면에서 들어오면 router.js goView 가 내 피드에서 시작하고,
 * 이미 트렌드 분석에 있으면 내 피드 메뉴를 눌러 옮긴다. */
function openTourView(view){
  /* 챗봇 장은 홈 위에서 팝업을 연다. 팝업은 단계가 시작될 때(chatSceneSwitcher) 열린다. */
  if(view === 'chat'){ goView('home', true); return; }
  if(view === 'trend'){
    goView('trend', true);
    const feed = document.querySelector('.sItem[data-tr="myfeed"]');
    if(feed && !feed.classList.contains('on')) feed.click();
    return;
  }
  goView(view, true);
}

async function gotoChapter(index, at = 0){
  if(!guide?.tour || !chapterOpen(index)) return;
  const activeGuide = guide;
  const tour = activeGuide.tour;
  const seq = ++tour.seq;
  const stale = () => guide !== activeGuide || tour.seq !== seq;
  stopGuideSync();
  activeGuide.paintSeq += 1;
  activeGuide.card.style.visibility = 'hidden';
  closeSpot();
  releasePageState();
  tour.chapter = index;
  activeGuide.steps = [];
  guideStep = 0;
  activeGuide.enteredStep = -1;
  paintTour();
  openTourView(TOUR_CHAPTERS[index].view);
  await frame();
  if(stale()) return;
  const prepared = await preparePageGuide(TOUR_CHAPTERS[index].view, { tour:true });
  if(stale()){
    if(prepared.restoreDemo) prepared.restoreDemo();
    if(prepared.restoreSide && !prepared.restoreSide.wasOpen && !guide) trSideOpen(false);
    return;
  }
  activeGuide.steps = prepared.steps;
  activeGuide.view = TOUR_CHAPTERS[index].view;
  activeGuide.restoreDemo = prepared.restoreDemo || null;
  activeGuide.restoreSide = prepared.restoreSide || null;
  guideStep = at < 0 ? Math.max(0, prepared.steps.length - 1) : Math.min(at, Math.max(0, prepared.steps.length - 1));
  activeGuide.enteredStep = -1;
  paintGuideStep(at < 0 ? -1 : 1);
}

export async function startGuideTour(){
  closeGuide();
  guideStep = 0;
  guide = buildGuide([], { tour:true });
  guide.tour = { chapter:0, done:new Set(), seq:0 };
  paintTour();
  await gotoChapter(0, 0);
}

export async function startContextGuide(){
  closeGuide();
  const view = chatPopupOpen() ? 'chat' : currentView();
  const prepared = await preparePageGuide(view);
  guideStep = 0;
  guide = buildGuide(prepared.steps);
  guide.view = view;
  guide.restoreSide = prepared.restoreSide || null;
  guide.restoreDemo = prepared.restoreDemo || null;
  paintGuideStep();
}

function boot(){
  /* 헤더 알림 오른쪽의 조이스틱 버튼 — 전체 가이드를 연다. 하단 챗봇 버튼과는 따로 동작한다. */
  const tourBtn = document.getElementById('tourBtn');
  if(tourBtn) tourBtn.addEventListener('click', () => { startGuideTour(); });
  document.addEventListener('keydown', e => {
    if(e.key === 'Escape'){
      if(guide) closeGuide();
      return;
    }
    /* 가이드가 열려 있으면 ← → 로도 앞뒤 단계를 오간다. */
    if(!guide || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if(e.target?.closest?.('input, textarea, select, [contenteditable="true"]')) return;
    if(e.key === 'ArrowRight'){ e.preventDefault(); goNext(); }
    else if(e.key === 'ArrowLeft'){ e.preventDefault(); goPrev(); }
  });
  /* 브라우저 뒤로가기로 페이지가 바뀌면 전체 가이드의 흐름이 어긋나므로 닫는다. */
  addEventListener('popstate', () => { if(guide?.tour) closeGuide(); });

  const toggle = document.getElementById('chatFab');
  if(!toggle) return;
  toggle.addEventListener('click', e => {
    e.stopPropagation();
    openChatWith('', null);
  });
}

if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
