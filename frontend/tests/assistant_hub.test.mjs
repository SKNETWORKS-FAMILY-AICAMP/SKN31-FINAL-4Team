/* 전역 도움말 허브 · 화면별 가이드 (2026-10-03)
 * 실행: node tests/assistant_hub.test.mjs */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost:5173/' });
for(const k of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement',
                'KeyboardEvent','MouseEvent','CustomEvent','Event','MutationObserver','history'])
  globalThis[k] = k === 'window' ? dom.window : dom.window[k];
globalThis.requestAnimationFrame = f => setTimeout(f, 0);
globalThis.cancelAnimationFrame = h => clearTimeout(h);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.location = dom.window.location;
globalThis.localStorage = dom.window.localStorage;
globalThis.sessionStorage = dom.window.sessionStorage;
globalThis.matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
globalThis.scrollTo = () => {};
globalThis.innerWidth = 1440;
globalThis.innerHeight = 900;
globalThis.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };

const ok = body => ({ ok:true, status:200, text:async()=>JSON.stringify(body), json:async()=>body });
let apiCalls = 0;
globalThis.fetch = async url => {
  apiCalls += 1;
  const u = decodeURIComponent(String(url));
  if(u.includes('/api/auth/me')) return ok({ status:'ok', data:{ authenticated:true, user:{ nickname:'테스터' } } });
  if(u.includes('/api/dictionary')) return ok({ status:'ok', data:[{ facet:'디테일', label:'와이드' }] });
  return ok({ status:'ok', data:[] });
};

localStorage.setItem('feedit.introSeen.v1', '1');
localStorage.setItem('feedit.alpha.asked.v1', '1');

const HUB = await import(`${F}/app_shell/static/js/assistant_hub.js`);
document.dispatchEvent(new dom.window.Event('DOMContentLoaded', { bubbles:true }));
document.body.classList.add('mainmode');
document.body.dataset.view = 'home';

const click = el => el.dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
const wait = (ms=0) => new Promise(resolve => setTimeout(resolve, ms));

assert.equal(document.querySelectorAll('[data-assist]').length, 4, '허브 메뉴는 정확히 네 개여야 한다');
assert.equal(document.querySelectorAll('[data-assist] > svg').length, 4, '각 메뉴에는 기능별 픽토그램이 있어야 한다');
click(document.getElementById('chatFab'));
assert.ok(document.getElementById('assistHub').classList.contains('open'), '원형 버튼을 누르면 메뉴가 열려야 한다');
assert.equal(document.getElementById('assistMenu').getAttribute('aria-hidden'), 'false');
assert.equal(document.getElementById('assistHint').hidden, true, '처음 연 뒤에는 사전 안내 말풍선이 사라져야 한다');

await HUB.startContextGuide();
await wait(10);
assert.ok(document.querySelector('.guideTour'), '홈 화면 가이드가 열리지 않았다');
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 4$/, '홈 가이드는 네 단계여야 한다');
assert.equal(document.querySelector('.guidePrev').hidden, true, '첫 단계에서는 이전 화살표가 보이면 안 된다');
click(document.querySelector('.guideNext'));
await wait(20);
assert.equal(document.querySelector('.guidePrev').hidden, false, '2단계부터 이전 화살표가 보여야 한다');
click(document.querySelector('.guidePrev'));
await wait(20);
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 4$/, '이전 화살표로 앞 설명으로 돌아가야 한다');
click(document.querySelector('.guideSkip'));

/* 살!말? 가이드는 운영 데이터·모달을 건드리지 않는 숨은 목업만 사용한다. */
document.body.dataset.view='salmal';
document.getElementById('voteGrid').innerHTML='<article data-live-card="preserve">운영 카드 그대로</article>';
const liveVoteGrid=document.getElementById('voteGrid').innerHTML;
document.getElementById('createOverlay').classList.remove('on');
document.getElementById('modalOverlay').classList.remove('on');
await HUB.startContextGuide();
await wait(10);
assert.ok(document.getElementById('salmalGuideDemo'),'살!말? 전용 목업 페이지가 생성되어야 한다');
assert.match(document.querySelector('.guideCount').textContent,/^1 \/ 11$/,'살!말? 가이드는 요청한 순서의 11단계여야 한다');
assert.equal(document.getElementById('voteGrid').innerHTML,liveVoteGrid,'가이드 시작이 운영 카드 목록을 바꾸면 안 된다');
click(document.querySelector('.guideNext')); await wait(20);
assert.match(document.getElementById('guideTitle').textContent,/카드/,'2단계는 목업 카드 설명이어야 한다');
assert.match(document.querySelector('#salmalGuideDemo [data-sm-guide="card"] h4').textContent,/데일리 브이넥 니트/);
click(document.querySelector('.guideNext')); await wait(20);
assert.ok(document.querySelector('#salmalGuideDemo [data-sm-guide="detail"]').classList.contains('on'),'3단계는 목업 상세 화면을 열어야 한다');
assert.ok(!document.getElementById('modalOverlay').classList.contains('on'),'운영 상세 모달은 열면 안 된다');
assert.match(document.querySelector('#salmalGuideDemo [data-sm-guide="detail"] .postName').textContent,/피딧/,'예시 작성자는 피딧이어야 한다');
click(document.querySelector('.guideNext')); await wait(20);
assert.ok(!document.querySelector('#salmalGuideDemo [data-sm-guide="detail"]').classList.contains('on'),'4단계는 목업 목록으로 돌아와야 한다');
click(document.querySelector('.guideNext')); await wait(20);
assert.ok(document.querySelector('#salmalGuideDemo [data-sm-guide="create"]').classList.contains('on'),'5단계는 목업 등록 모달을 열어야 한다');
assert.ok(!document.getElementById('createOverlay').classList.contains('on'),'운영 등록 모달은 열면 안 된다');
for(let step=6;step<=11;step+=1){
  click(document.querySelector('.guideNext')); await wait(20);
  assert.match(document.querySelector('.guideCount').textContent,new RegExp('^'+step+' \\/ 11$'));
}
click(document.querySelector('.guidePrev')); await wait(20);
assert.match(document.querySelector('.guideCount').textContent,/^10 \/ 11$/,'마지막 단계에서도 이전 설명으로 돌아갈 수 있어야 한다');
assert.ok(document.querySelector('#salmalGuideDemo [data-sm-guide="create"]').classList.contains('on'),'이전 이동 후에도 목업 등록 모달이 유지되어야 한다');
click(document.querySelector('.guideSkip'));
assert.equal(document.getElementById('salmalGuideDemo'),null,'가이드를 닫으면 숨은 목업 페이지를 제거해야 한다');
assert.equal(document.getElementById('voteGrid').innerHTML,liveVoteGrid,'가이드를 닫은 뒤에도 운영 카드 목록이 그대로여야 한다');
assert.ok(!document.getElementById('modalOverlay').classList.contains('on'),'운영 상세 모달 상태를 바꾸면 안 된다');
assert.ok(!document.getElementById('createOverlay').classList.contains('on'),'운영 등록 모달 상태를 바꾸면 안 된다');

/* 요금제 가이드는 실제 프리·프로·비즈니스 카드를 순서대로 설명한다. */
document.body.dataset.view = 'price';
document.getElementById('prGrid').innerHTML = '<div class="prCards">' +
  '<div class="prCard">프리</div><div class="prCard">프로</div><div class="prCard">비즈니스</div></div>';
await HUB.startContextGuide();
await wait(10);
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 3$/, '요금제 가이드는 세 플랜을 설명해야 한다');
assert.match(document.getElementById('guideTitle').textContent, /프리/);
click(document.querySelector('.guideNext'));
await wait(20);
assert.match(document.getElementById('guideTitle').textContent, /프로/);
click(document.querySelector('.guideNext'));
await wait(20);
assert.match(document.getElementById('guideTitle').textContent, /비즈니스/);
click(document.querySelector('.guidePrev'));
await wait(20);
assert.match(document.getElementById('guideTitle').textContent, /프로/, '요금제 설명도 이전 화살표로 돌아가야 한다');
click(document.querySelector('.guideSkip'));

/* 트렌드 가이드는 현재 선택한 메뉴 하나만 설명하며 검색·탭 이동을 일으키지 않는다. */
document.body.dataset.view = 'trend';
const trendItems = [
  ['myfeed','내 피드','sFeed'], ['report','금주의 리포트','sFeed'], ['saved','찜한 키워드','sFeed'],
  ['temp','언급량 · 온도','sEdit'], ['assoc','연관어','sEdit'], ['sentiment','긍부정','sEdit'],
  ['life','수명주기','sEdit'], ['stock','할인률 변화','sEdit'], ['resale','리세일 지수','sEdit'],
];
document.getElementById('sFeed').innerHTML = '';
document.getElementById('sEdit').innerHTML = '';
let tabClicks = 0;
for(const [id,label,group] of trendItems){
  const button = document.createElement('button');
  button.className = 'sItem' + (id === 'myfeed' ? ' on' : '');
  button.dataset.tr = id;
  button.textContent = label;
  button.addEventListener('click', () => { tabClicks += 1; });
  document.getElementById(group).appendChild(button);
}
document.getElementById('trTabs').innerHTML =
  '<div class="fsBar" id="kwBar"><input id="kwInput"><button id="kwClear"></button></div><div id="kwSug"></div>';
let searchCalls = 0;
window.feeditKwGo = () => { searchCalls += 1; };

await HUB.startContextGuide();
await wait(10);
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 6$/, '내 피드에서만 공통 1단계부터 시작해야 한다');
assert.ok(document.getElementById('side').classList.contains('open'), '내 피드 공통 설명 중에는 사이드바가 보여야 한다');
click(document.querySelector('.guideNext'));
await wait(60);
assert.match(document.querySelector('.guideCount').textContent, /^2 \/ 6$/, '공통 설명 뒤 내 피드 자체 설명으로 넘어가야 한다');
assert.match(document.querySelector('.guidePhase').textContent, /^2단계 · 현재 메뉴/);
assert.match(document.querySelector('.guideTitle, #guideTitle').textContent, /내 피드/);
click(document.querySelector('.guideNext'));
await wait(60);
assert.match(document.querySelector('.guideCount').textContent, /^3 \/ 6$/, '내 피드 설명 뒤 카드 설명으로 넘어가야 한다');
assert.match(document.querySelector('.guidePhase').textContent, /^3단계 · 내 피드 카드/);
assert.equal(document.querySelector('.guidePreview').hidden, false, '카드 설명에는 고정 미리보기가 보여야 한다');
assert.match(document.querySelector('.guidePreview').textContent, /검색·개인화 기록에 저장되지 않음/);
assert.equal(document.querySelectorAll('.tgPreviewGrid article.active').length, 1, '현재 설명 중인 카드 하나만 강조해야 한다');
click(document.querySelector('.guideSkip'));
assert.ok(!document.getElementById('side').classList.contains('open'), '가이드를 닫으면 기존 사이드바 상태로 돌아가야 한다');

/* FEED의 다른 두 화면은 자기 메뉴 설명 뒤 카드 설명으로 간다. */
for(const [id,label] of trendItems.slice(1,3)){
  document.querySelectorAll('.sItem').forEach(el => el.classList.toggle('on', el.dataset.tr === id));
  await HUB.startContextGuide();
  await wait(5);
  assert.match(document.querySelector('.guidePhase').textContent, /^2단계 · 현재 메뉴/);
  assert.match(document.querySelector('.guideCount').textContent, /^2 \/ /, `${label}는 해당 화면 설명부터 시작해야 한다`);
  assert.match(document.querySelector('.guideTitle, #guideTitle').textContent, new RegExp(label.replace(' · ', ' \\· ')));
  assert.equal(document.querySelector('.guidePreview').hidden, true, `${label}의 2단계는 메뉴 설명이어야 한다`);
  click(document.querySelector('.guideNext'));
  await wait(40);
  assert.match(document.querySelector('.guidePhase').textContent, new RegExp('3단계 · '+label.replace(' · ', ' \\· ')+' 카드'));
  assert.equal(document.querySelector('.guidePreview').hidden, false, `${label} 카드 고정 미리보기가 필요하다`);
  click(document.querySelector('.guideSkip'));
}

/* EDIT 여섯 화면은 별도 목업 화면이 아니라 기존 검색창·모달·카드 렌더러를 그대로 걷는다. */
const demos = {
  temp:['니트','사전'], assoc:['발레코어','사전'], sentiment:['스키니','사전'], life:['민트','사전'],
  stock:['[우연X후브스] 밀리터리 슬림 헨리넥 롱슬리브[딥네이비]','세부 검색'],
  resale:['프로 드라이 핏 타이트 반소매 피트니스 탑 - 블랙:화이트','세부 검색'],
};
const detailedResultTitles={
  sentiment:['구매의향 판정','핵심 반응 지표','긍정·중립·부정','반응 신호 6종','근거 문장'],
  life:['현재 단계','기획 지표','유행 곡선','주별 온도','언급량·판매량'],
  resale:['상품·매핑 상태','구매·판매 모드','핵심 4지표','플랫폼별 현재 가격','현재 매물과 최근 거래','추천 중고 상품','리세일 시장 지표','가치 변화','가치 유지율과 트렌드 온도'],
};
for(const [id,label] of trendItems.slice(3)){
  document.querySelectorAll('.sItem').forEach(el => el.classList.toggle('on', el.dataset.tr === id));
  const beforeCalls=apiCalls;
  await HUB.startContextGuide();
  await wait(5);
  assert.equal(document.querySelector('.trendGuideDemo'), null, `${label}에 별도 가짜 화면을 만들면 안 된다`);
  assert.ok(document.body.classList.contains('trend-guide-demo'), `${label} 가이드 안전 모드가 켜져야 한다`);
  assert.match(document.getElementById('trBody').textContent, new RegExp(demos[id][0].replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.match(document.querySelector('.guidePhase').textContent, /^2단계 · 현재 메뉴/);
  click(document.querySelector('.guideNext'));
  await wait(40);
  assert.match(document.querySelector('.guidePhase').textContent, /^3단계 · 검색 시작/);
  const actualInput=document.querySelector(id==='temp'||id==='assoc'||id==='sentiment'?'#kwInput':'#fsInput');
  assert.equal(actualInput?.value,demos[id][0],`${label} 실제 검색창에 가이드 검색어가 보여야 한다`);
  click(document.querySelector('.guideNext'));
  await wait(40);
  assert.match(document.querySelector('.guidePhase').textContent, new RegExp('4단계 · '+demos[id][1]));
  const modalBg=document.getElementById(demos[id][1]==='사전'?'dictPopBg':'fsPopBg');
  assert.ok(modalBg?.classList.contains('on'), `${label} 실제 ${demos[id][1]} 모달이 열려야 한다`);
  assert.ok(modalBg.querySelector('.fsPop'), `${label} 기존 모달 컴포넌트를 사용해야 한다`);
  if(id==='stock') assert.match(modalBg.textContent,/밀리터리 슬림 헨리넥/, '할인률 세부검색 모달에 선택 상품이 보여야 한다');
  click(document.querySelector('.guideNext'));
  await wait(40);
  assert.match(document.querySelector('.guidePhase').textContent, /^결과 읽기 · 1/);
  assert.ok(!modalBg.classList.contains('on'), `${label} 결과 설명에서는 검색 모달이 닫혀야 한다`);
  assert.ok(document.querySelector('#trBody .verdict, #stockAnalyticsBody, #trBody .resaleMode'), `${label} 실제 결과 카드가 필요하다`);
  if(id==='temp') assert.doesNotMatch(document.getElementById('trBody').textContent, /네이버|구글/, '언급량 가이드에서 고장 난 검색 관심도는 제외해야 한다');
  const detailed=detailedResultTitles[id];
  if(detailed){
    assert.match(document.getElementById('guideTitle').textContent,new RegExp(detailed[0]));
    for(let index=1;index<detailed.length;index+=1){
      click(document.querySelector('.guideNext'));
      await wait(20);
      assert.match(document.querySelector('.guidePhase').textContent,new RegExp('결과 읽기 · '+(index+1)));
      assert.match(document.getElementById('guideTitle').textContent,new RegExp(detailed[index].replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
    }
  }
  assert.equal(apiCalls,beforeCalls,`${label} 가이드가 API를 호출하면 안 된다`);
  click(document.querySelector('.guideSkip'));
  assert.ok(!document.body.classList.contains('trend-guide-demo'), '가이드를 닫으면 안전 모드가 해제돼야 한다');
  if(id==='stock') assert.doesNotMatch(document.getElementById('fsPopBg').textContent,/밀리터리 슬림 헨리넥/, '가이드 상품이 실제 세부검색 모달에 남으면 안 된다');
}

/* 가이드용 사전 행을 실제 사전 전역 상태에 남기지 않는다. */
document.body.insertAdjacentHTML('beforeend','<button type="button" data-dict-open id="realDictOpen">사전 확인</button>');
click(document.getElementById('realDictOpen'));
await wait(30);
assert.match(document.getElementById('dictPopBg').textContent,/와이드/, '가이드 뒤 실제 사전은 API 원본 후보를 다시 사용해야 한다');
assert.doesNotMatch(document.getElementById('dictPopBg').textContent,/시티보이/, '가이드 전용 사전 후보가 실제 사전에 남으면 안 된다');

assert.equal(document.getElementById('fsInput')?.value||'', '', '가이드를 닫으면 임시 검색어가 남으면 안 된다');
assert.equal(searchCalls, 0, '가이드가 실제 검색 API 진입점을 호출하면 안 된다');
assert.equal(tabClicks, 0, '가이드가 다른 분석 탭으로 이동하면 안 된다');

console.log('✅ 전역 도움말 허브와 페이지별 무조회 트렌드 가이드');
process.exit(0);
