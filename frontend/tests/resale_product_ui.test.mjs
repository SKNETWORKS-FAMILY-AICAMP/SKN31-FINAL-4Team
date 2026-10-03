/* 리세일: 표준상품 검색 → product_id 분석, 연결된 플랫폼 카드만 표시. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root=new URL('..',import.meta.url).href.replace(/\/$/,'');
const dom=new JSDOM(fs.readFileSync(new URL('../index.html',import.meta.url),'utf8'),{url:'http://localhost:5173/'});
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement',
  'KeyboardEvent','MouseEvent','CustomEvent','MutationObserver'])
  globalThis[key]=key==='window'?dom.window:dom.window[key];
globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);
globalThis.cancelAnimationFrame=id=>clearTimeout(id);
globalThis.addEventListener=dom.window.addEventListener.bind(dom.window);
globalThis.localStorage=dom.window.localStorage;
globalThis.location=dom.window.location;
globalThis.innerWidth=1440; globalThis.innerHeight=900;
globalThis.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
globalThis.scrollTo=()=>{};
globalThis.IntersectionObserver=class{observe(){} unobserve(){} disconnect(){}};
globalThis.ResizeObserver=class{observe(){} unobserve(){} disconnect(){}};
globalThis.anime={animate(){return {pause(){},cancel(){},play(){}}},
  createTimeline(){return {add(){return this},call(){return this}}},stagger(){return ()=>0},
  spring(){return 'linear'},utils:{set(){},remove(){}},createDrawable(){return []},splitText(){return {}}};

const reply=value=>({ok:true,status:200,text:async()=>JSON.stringify(value),json:async()=>value});
const asked=[];
let sparseBrand=false;
let emptyKream=false;
globalThis.fetch=async url=>{
  url=String(url); asked.push(url);
  if(url.includes('/api/resale/products'))return reply({status:'ok',data:{items:[{
    id:42,type:'product',name:'나이키 에어포스 1 07 화이트',brand:'나이키',code:'CW2288-111',
    image:'https://img.example/broken.jpg',images:['https://img.example/broken.jpg','https://img.example/42.jpg'],source_count:9,
    platforms:[{name:'무신사',count:1},{name:'무신사 USED',count:8}],
  }]}});
  if(url.includes('/api/resale?product_id=42'))return reply({status:'ok',data:{
    label:'나이키 에어포스 1 07 화이트',analysis_scope:'product',
    product:{id:42,name:'나이키 에어포스 1 07 화이트',brand:'나이키',code:'CW2288-111',
      image:'https://img.example/42.jpg',mapped:true},
    as_of:'2026-09-29T12:00:00+09:00',days:90,observed_days:8,listings:8,
    current_listing_count:emptyKream?0:8,current_listing_count_partial:false,
    confidence:{code:'medium',label:'보통'},mapping:{platform_count:2,platforms:['무신사','무신사 USED'],source_count:9},
    keep_pct:61,keep_change_pp:-3,regular_price:135000,used_price:50000,
    volume_4w:8,volume_change_pct:null,volume_basis:'observed_listings',sizes:[],grades:[],spread:null,
    series:[{date:'2026-09-22',keep_pct:64},{date:'2026-09-29',keep_pct:61}],
    temperature:{series:[{date:'2026-09-22',temp:52},{date:'2026-09-29',temp:58}]},
    recommendations:[],md_signals:[{label:'가격 방어력',value:'61%',tone:'neutral',description:'관측 중앙값'}],
    platform_cards:[
      {name:'무신사',market:'retail',product_sources:1,list_price:135000,sale_price:99000,discount_rate:26.7,as_of:'2026-09-29'},
      ...(emptyKream
        ? [{name:'크림',market:'resale',product_sources:1,listing_count:0,median_price:null,as_of:'2026-09-29'}]
        : [{name:'무신사 USED',market:'resale',product_sources:8,listing_count:8,median_price:50000,min_price:42000,max_price:68000,as_of:'2026-09-29'}]),
    ],
  }});
  if(url.includes('/api/resale?brand='))return reply({status:'ok',data:{
    label:'나이키',analysis_scope:'brand',product:null,as_of:'2026-09-29T12:00:00+09:00',days:90,
    observed_days:8,listings:12,confidence:{code:'medium',label:'보통'},mapping:{platform_count:0,platforms:[],source_count:12},
    keep_pct:66,keep_change_pp:2,regular_price:140000,used_price:72000,volume_4w:12,
    volume_change_pct:20,volume_basis:'observed_listings',sizes:[],grades:[],spread:null,platform_cards:[],
    series:sparseBrand?[]:[{date:'2026-09-22',keep_pct:63},{date:'2026-09-29',keep_pct:66}],
    temperature:{series:sparseBrand?[]:[{date:'2026-09-22',temp:51},{date:'2026-09-29',temp:57}]},
    recommendations:Array.from({length:7},(_,i)=>({product_id:42+i,source_id:2+i,name:'나이키 추천 상품 '+(i+1),brand:'나이키',
      model_code:'TEST-'+(i+1),image:'https://img.example/'+(42+i)+'.jpg',platform:i===0?'크림':'무신사 USED',
      price:50000+i*1000,listing_count:8-i,listing_count_partial:i===0})),
    md_signals:[
      {label:'가격 방어율',value:'66%',tone:'neutral',description:'관측 중고가의 정가 대비 중앙값입니다.'},
      {label:'거래량 증감률',value:'측정 전',tone:'neutral',description:'실제 거래량이 두 기간에 쌓이면 계산합니다.'},
      {label:'프리미엄 지속 기간',value:'0일',tone:'neutral',description:'정가보다 중고가가 높았던 최근 연속 기간입니다.'},
    ],
  }});
  return reply({status:'empty',reason:'테스트 데이터 없음',data:null});
};

await import(`${root}/main.js`);
const search=await import(`${root}/style/static/js/search.js`);
const dispatch=await import(`${root}/trend/static/js/dispatch.js`);
const liveData=await import(`${root}/trend/static/js/live_data.js`);
dispatch.trRender('resale');
const input=document.getElementById('fsInput');
input.value='에어포스';
input.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
await new Promise(resolve=>setTimeout(resolve,280));
const candidate=document.querySelector('#fsSug .resaleProduct');
assert.ok(candidate,'표준상품 후보를 보여 준다');
assert.match(candidate.textContent,/표준상품/);
assert.match(candidate.textContent,/무신사 USED 8건/);
const candidateImage=candidate.querySelector('img');
candidateImage.dispatchEvent(new dom.window.Event('error'));
assert.equal(candidateImage.getAttribute('src'),'https://img.example/42.jpg','첫 이미지가 깨지면 같은 상품의 다음 이미지로 넘어간다');
candidate.click();
await new Promise(resolve=>setTimeout(resolve,80));

assert.equal(search.FS.resaleItem.id,42,'선택한 표준상품 ID를 보관한다');
assert.ok(asked.some(url=>url.includes('/api/resale?product_id=42')),'분석은 이름이 아니라 product_id로 요청한다');
assert.equal(document.querySelectorAll('.resalePlatformCard').length,2,'응답에 있는 플랫폼만 카드로 그린다');
assert.doesNotMatch(document.getElementById('trBody').textContent,/크림/,'없는 플랫폼 카드를 만들지 않는다');
assert.match(document.getElementById('trBody').textContent,/정가보다 39% 저렴/,'구매 목적의 언어로 번역한다');
assert.equal(document.querySelector('[data-current-listings]').dataset.currentListings,'8','상품 요약에는 현재 실제 매물 수를 표시한다');
assert.match(document.querySelector('.kpis').textContent,/정가.*중고가.*현재 매물 수.*4주간 중고거래량/s,'상단 네 카드는 정가·중고가·현재 매물·4주 거래량 순서다');
assert.match(document.querySelector('.kpis').textContent,/측정 전/,'실거래량이 없으면 관측 매물을 거래량처럼 표시하지 않는다');
assert.equal(document.querySelectorAll('.resaleEvidence .panelC').length,2,'두 시계열 차트만 남기고 자료 없는 상태·사이즈 카드는 숨긴다');

emptyKream=true;
await liveData.primeUrl('/api/resale?product_id=42',{force:true});
dispatch.trRender('resale');
await new Promise(resolve=>setTimeout(resolve,80));
const kreamCard=[...document.querySelectorAll('.resalePlatformCard')].find(card=>card.textContent.includes('크림'));
assert.ok(kreamCard,'관측 플랫폼인 크림 카드는 유지한다');
assert.match(kreamCard.textContent,/현재 판매 중인 중고 매물이 없어요/,'매물 0건을 가격 집계 중으로 오해하게 하지 않는다');
assert.doesNotMatch(kreamCard.textContent,/가격 집계 중|매물 0건/);
assert.match(document.querySelector('.resaleNoRatio').textContent,/현재 판매 중인 중고 매물이 없어요/,'전체 결론도 정가 없음이 아니라 현재 매물 없음으로 안내한다');

emptyKream=false;
await liveData.primeUrl('/api/resale?product_id=42',{force:true});
dispatch.trRender('resale');
await new Promise(resolve=>setTimeout(resolve,80));
document.querySelector('[data-resale-mode="sell"]').click();
assert.match(document.getElementById('trBody').textContent,/정가의 61%를 회수/,'판매 목적 문구로 즉시 바꾼다');

document.getElementById('fsMore').click();
assert.match(document.querySelector('.fsPopHead h3').textContent,/세부 검색/);
assert.match(document.getElementById('fsPopLead').textContent,/상품명·모델번호/);
assert.match(document.getElementById('fsApply').textContent,/이 조건으로 분석/);
await new Promise(resolve=>setTimeout(resolve,280));
assert.ok(document.querySelector('#fsC3 .fsResaleOpt img'),'세부 검색 안에서도 이미지와 함께 개별 상품을 찾는다');
const facetUrl=asked.filter(url=>url.includes('/api/facets?')).at(-1);
assert.ok(facetUrl&&!facetUrl.includes('item='),'개별 상품을 고른 상태에서도 시장 조건 후보는 잠그지 않는다');

document.getElementById('fsPopX').click();
search.fsReset(); search.FS.pick['종류']=['쇼츠'];
search.fsOpenPop();
await new Promise(resolve=>setTimeout(resolve,280));
assert.ok(asked.some(url=>url.includes('/api/resale/products?')&&url.includes('kind=%EC%87%BC%EC%B8%A0')),
  '카테고리만 골라도 그 조건의 상품을 조회한다');
assert.ok(document.querySelector('#fsC3 .fsResaleOpt img'),'상품명을 입력하지 않아도 조건에 맞는 상품과 이미지를 보여 준다');
document.getElementById('fsPopX').click();

search.fsReset(); search.FS.pick['브랜드']=['나이키'];
dispatch.trRender('resale');
await new Promise(resolve=>setTimeout(resolve,80));
assert.equal(document.querySelectorAll('[data-resale-mode]').length,0,'브랜드 시장 분석은 구매·판매 모드와 구분한다');
assert.equal(document.querySelectorAll('.resaleRecCard').length,5,'브랜드 분석 아래 실제 관측 추천 상품을 다섯 장씩 보여 준다');
assert.match(document.querySelector('.resaleRecCard').textContent,/관측 매물 8건/);
assert.match(document.querySelector('.resaleRecCard').textContent,/관측 매물 8건\+/,'불완전한 KREAM 호가 표본은 전체 수처럼 보이지 않게 +를 붙인다');
assert.ok(document.querySelector('[data-resale-more]'),'추천 후보가 더 있으면 다른 상품 보기 버튼을 보여 준다');
assert.equal(document.querySelectorAll('.resaleMdCard').length,3,'시장 핵심 카드는 가격 방어력·거래/공급·유통 채널 세 개만 둔다');
assert.match(document.querySelector('.resaleMd').textContent,/가격 방어율.*거래량 증감률.*프리미엄 지속 기간/s,'리세일 시장은 방어율·거래량 증감·프리미엄 기간으로 구성한다');
assert.match(document.getElementById('trBody').textContent,/리세일 시장 한눈에 보기/,'소비자와 MD를 분리하지 않는 제목을 쓴다');
assert.doesNotMatch(document.getElementById('trBody').textContent,/MD 관점으로 보기/,'내부 사용자만을 위한 영역처럼 보이지 않게 한다');
assert.equal(document.querySelectorAll('.kpis .kpi').length,4,'관측 매물·매물 공급·관측 기간·신뢰도를 네 칸으로 고정한다');
assert.ok(document.querySelector('[data-chart="resMain"]'),'새 가치 변화 차트를 유지한다');
assert.ok(document.querySelector('[data-chart="resValueTrend"]'),'가치 유지율과 트렌드 온도 비교 차트를 함께 둔다');

sparseBrand=true;
search.FS.pick['브랜드']=['아디다스'];
dispatch.trRender('resale');
await new Promise(resolve=>setTimeout(resolve,80));
assert.equal(document.querySelectorAll('.resaleEvidence [data-chart]').length,2,'시계열이 부족해도 두 차트 영역은 사라지지 않는다');
assert.equal(document.querySelectorAll('.resaleEvidence [data-live="unavailable"]').length,2,'시계열이 부족한 이유를 각 차트에 표시한다');

console.log('✅ 리세일 세부 상품검색·시장 추천·시장 지표·비교 차트 통과');
process.exit(0);
