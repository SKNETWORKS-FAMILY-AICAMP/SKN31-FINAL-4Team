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

/* 오른쪽 하단 버튼은 챗봇만 연다 (2026-10-05) — 메뉴·안내 말풍선이 없어야 한다. */
assert.equal(document.querySelectorAll('[data-assist]').length, 0, '버튼 메뉴가 남아 있으면 안 된다');
assert.equal(document.getElementById('assistMenu'), null);
assert.equal(document.getElementById('assistHint'), null);
assert.equal(document.getElementById('chatFab').getAttribute('aria-label'), '챗봇 열기');
const P = await import(`${F}/account/static/js/profile.js`);
P.AUTH.in = true;
for(const view of ['home', 'trend', 'style', 'salmal']){
  document.body.dataset.view = view;
  document.getElementById('cpOverlay').classList.remove('on');
  click(document.getElementById('chatFab'));
  await wait(5);
  assert.ok(document.getElementById('cpOverlay').classList.contains('on'), view + ' 화면에서 버튼이 챗봇을 열지 않았다');
}
document.getElementById('cpOverlay').classList.remove('on');
document.body.dataset.view = 'home';

await HUB.startContextGuide();
await wait(10);
assert.ok(document.querySelector('.guideTour'), '홈 화면 가이드가 열리지 않았다');
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 4$/, '홈 가이드는 네 단계여야 한다');
assert.equal(document.querySelector('.guidePrev').disabled, true, '첫 단계에서는 이전 화살표를 누를 수 없어야 한다');
const homeIcon = document.querySelector('.guideIcon').innerHTML;
assert.match(homeIcon, /<svg/, '설명창 아이콘은 페이지 아이콘(svg)이어야 한다');
click(document.querySelector('.guideNext'));
await wait(20);
assert.equal(document.querySelector('.guidePrev').disabled, false, '2단계부터 이전 화살표를 누를 수 있어야 한다');
assert.equal(document.querySelector('.guideIcon').innerHTML, homeIcon, '아이콘은 단계마다 바뀌지 않고 페이지마다 고정이어야 한다');
assert.equal(document.querySelector('.guideNext').getAttribute('aria-label'), '다음 설명');
assert.ok(document.querySelector('.guideFoot').firstElementChild.classList.contains('guideSkip'), '건너뛰기는 아래 줄 맨 왼쪽이어야 한다');
assert.ok(document.querySelector('.guideNav .guideNext') && document.querySelector('.guideNav .guidePrev'), '진행 번호 양옆에 화살표가 있어야 한다');
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

/* 내 피드 — 메뉴 구조 → FEED 묶음 → 내 피드 → EDIT 묶음 → 언급량·온도(가을) (2026-10-05).
 * FEED·EDIT 를 각각 대표 화면으로 보여 준다. EDIT 대표는 실제 언급량·온도 화면을
 * 저장된 '가을' 응답으로 그리고, 탭 버튼을 누르지 않으며 API 도 부르지 않는다. */
await HUB.startContextGuide();
await wait(10);
const stepIs = (n, phase) => {
  assert.match(document.querySelector('.guideCount').textContent, new RegExp('^'+n+' \\/ 7$'));
  assert.match(document.querySelector('.guidePhase').textContent, phase);
};
stepIs(1, /^1단계 · 메뉴 구조/);
assert.ok(document.getElementById('side').classList.contains('open'), '내 피드 공통 설명 중에는 사이드바가 보여야 한다');
click(document.querySelector('.guideNext')); await wait(60);
stepIs(2, /^2단계 · FEED/);
const feedList = [...document.querySelectorAll('.guidePreview .tgList b')].map(b => b.textContent);
assert.deepEqual(feedList, ['내 피드','금주의 리포트','찜한 키워드'], 'FEED 설명은 FEED 메뉴 세 개를 모두 소개해야 한다');
click(document.querySelector('.guideNext')); await wait(60);
stepIs(3, /^3단계 · FEED 대표 — 내 피드/);
assert.equal(document.querySelectorAll('.tgPreviewGrid.all article').length, 4, '내 피드 카드 네 장을 한 번에 보여 줘야 한다');
assert.equal(document.querySelector('.sItem.on')?.dataset.tr, 'myfeed');
click(document.querySelector('.guideNext')); await wait(60);
stepIs(4, /^4단계 · EDIT/);
const editList = [...document.querySelectorAll('.guidePreview .tgList b')].map(b => b.textContent);
assert.deepEqual(editList, ['언급량 · 온도','연관어','긍부정','수명주기','할인률 변화','리세일 지수'], 'EDIT 설명은 EDIT 메뉴 여섯 개를 모두 소개해야 한다');
const callsBeforeSample = apiCalls;
click(document.querySelector('.guideNext')); await wait(60);
stepIs(5, /^5단계 · EDIT 대표 — 언급량 · 온도/);
assert.equal(document.querySelector('.sItem.on')?.dataset.tr, 'temp', 'EDIT 대표 단계에서는 언급량·온도 탭이 선택돼 보여야 한다');
assert.equal(document.getElementById('kwInput').value, '가을', '예시 검색어는 가을이어야 한다');
assert.match(document.getElementById('trBody').textContent, /가을/, '언급량·온도 결과는 가을 기준이어야 한다');
assert.match(document.querySelector('.guideBody').textContent, /2026-10-01 기준/, '저장된 응답의 기준일을 밝혀야 한다');
click(document.querySelector('.guideNext')); await wait(60);
stepIs(6, /^6단계 · 온도와 핵심 지표/);
assert.ok(document.querySelector('#trBody .verdict') && document.querySelector('#trBody .kpis'), '온도 판정과 핵심 지표 카드가 실제로 그려져야 한다');
click(document.querySelector('.guideNext')); await wait(60);
stepIs(7, /^7단계 · 추이와 플랫폼/);
assert.equal(document.querySelector('.guideNext').getAttribute('aria-label'), '가이드 마치기', '하단 버튼 가이드는 트렌드 분석 안에서 끝나야 한다');
assert.equal(apiCalls, callsBeforeSample, 'EDIT 대표 화면은 저장된 응답만 써야 한다');
click(document.querySelector('.guidePrev')); await wait(60);
click(document.querySelector('.guidePrev')); await wait(60);
click(document.querySelector('.guidePrev')); await wait(60);
stepIs(4, /^4단계 · EDIT/);
assert.equal(document.querySelector('.sItem.on')?.dataset.tr, 'myfeed', 'EDIT 묶음으로 돌아오면 내 피드 화면으로 돌아가야 한다');
assert.ok(!document.getElementById('kwInput')?.value, '내 피드로 돌아오면 예시 검색어가 남으면 안 된다');
click(document.querySelector('.guideNext')); await wait(60);
assert.equal(document.querySelector('.sItem.on')?.dataset.tr, 'temp');
click(document.querySelector('.guideSkip'));
assert.ok(!document.getElementById('side').classList.contains('open'), '가이드를 닫으면 기존 사이드바 상태로 돌아가야 한다');
assert.equal(document.querySelector('.sItem.on')?.dataset.tr, 'myfeed', '가이드를 닫으면 내 피드 탭으로 돌아와야 한다');
assert.ok(!document.body.classList.contains('trend-guide-demo'), '가이드를 닫으면 안전 모드가 해제돼야 한다');

/* FEED의 다른 두 화면은 자기 메뉴 설명 뒤 카드 설명으로 간다. */
for(const [id,label] of trendItems.slice(1,3)){
  document.querySelectorAll('.sItem').forEach(el => el.classList.toggle('on', el.dataset.tr === id));
  await HUB.startContextGuide();
  await wait(5);
  assert.match(document.querySelector('.guidePhase').textContent, /^1단계 · 현재 메뉴/);
  assert.match(document.querySelector('.guideCount').textContent, /^1 \/ /, `${label}는 해당 화면 설명부터 1단계로 시작해야 한다`);
  assert.match(document.querySelector('.guideTitle, #guideTitle').textContent, new RegExp(label.replace(' · ', ' \\· ')));
  assert.equal(document.querySelector('.guidePreview').hidden, true, `${label}의 2단계는 메뉴 설명이어야 한다`);
  click(document.querySelector('.guideNext'));
  await wait(40);
  assert.match(document.querySelector('.guidePhase').textContent, new RegExp('2단계 · '+label.replace(' · ', ' \\· ')+' 카드'));
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
  assert.match(document.querySelector('.guidePhase').textContent, /^1단계 · 현재 메뉴/);
  assert.doesNotMatch(document.getElementById('guideTitle').textContent, /온도은|변화은|지수은|연관어은|주기은/, '조사가 받침에 맞아야 한다');
  click(document.querySelector('.guideNext'));
  await wait(40);
  assert.match(document.querySelector('.guidePhase').textContent, /^2단계 · 검색 시작/);
  assert.doesNotMatch(document.querySelector('.guideBody').textContent, /API/, '사용자 문구에 API 같은 내부 용어를 쓰지 않는다');
  const actualInput=document.querySelector(id==='temp'||id==='assoc'||id==='sentiment'?'#kwInput':'#fsInput');
  assert.equal(actualInput?.value,demos[id][0],`${label} 실제 검색창에 가이드 검색어가 보여야 한다`);
  click(document.querySelector('.guideNext'));
  await wait(40);
  assert.match(document.querySelector('.guidePhase').textContent, new RegExp('3단계 · '+demos[id][1]));
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

/* 전체 가이드 (2026-10-05) — 헤더 알림 오른쪽 조이스틱 버튼이 모든 페이지 가이드를 한 흐름으로 잇는다.
 * 하단 버튼은 챗봇만 여는 단일 버튼 그대로이고, 왼쪽 목차에서 장을 고르면 그 페이지로 옮겨 간다. */
const tourBtn = document.getElementById('tourBtn');
assert.ok(tourBtn, '헤더에 전체 가이드 버튼이 있어야 한다');
assert.equal(tourBtn.parentElement.id, 'mHeadR', '전체 가이드 버튼은 헤더 오른쪽 묶음 안에 있어야 한다');
assert.equal(tourBtn.previousElementSibling?.id, 'notiWrap', '전체 가이드 버튼은 알림 버튼 바로 오른쪽이어야 한다');
assert.equal(document.querySelectorAll('[data-assist]').length, 0, '하단 버튼은 메뉴 없이 챗봇만 여는 단일 버튼이어야 한다');

/* 위 단계들은 body.dataset.view 만 바꿨다. 라우터도 실제로 트렌드 분석에 둔 채 시작해,
 * 다른 페이지에서 눌러도 홈부터 시작하는지 본다. */
const ROUTER = await import(`${F}/app_shell/static/js/router.js`);
ROUTER.goView('trend', true);
await wait(20);
assert.equal(document.body.dataset.view, 'trend');
const CHAT = await import(`${F}/home/static/js/chat.js`);
const PROFILE = await import(`${F}/account/static/js/profile.js`);
const chatOpen = () => document.getElementById('cpOverlay').classList.contains('on');
const shown = id => document.getElementById(id).style.display !== 'none';
const next = async (ms = 30) => { click(document.querySelector('.guideNext')); await wait(ms); };

click(tourBtn);
await wait(150);
const tocButtons = [...document.querySelectorAll('.tourToc [data-tour-chapter]')];
assert.deepEqual(tocButtons.map(b => b.querySelector('.tcTx b').textContent),
  ['홈','챗봇','트렌드 분석','살!말?','스타일','마이페이지','요금제'], '목차는 홈 → 챗봇 → 상단 탭 → 마이페이지 → 요금제 순서여야 한다');
assert.equal(document.body.dataset.view, 'home', '전체 가이드는 홈에서 시작해야 한다');
assert.ok(tocButtons[0].classList.contains('on'));
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 3$/, '전체 가이드의 홈은 도움말 버튼 안내를 빼고 3단계여야 한다');
assert.equal(document.querySelector('.guidePrev').disabled, true, '전체 가이드 첫 단계에는 이전으로 갈 곳이 없어야 한다');
assert.equal(document.querySelector('.guideClose')?.textContent, '중단하기', '오른쪽 위에 가이드를 끝내는 ‘중단하기’ 버튼이 있어야 한다');
click(document.querySelector('.guideScrim'));
assert.ok(document.querySelector('.guideTour'), '전체 가이드는 바깥을 눌러도 닫히지 않아야 한다');
await next(); await next();
assert.match(document.querySelector('.guideNext').getAttribute('aria-label'), /다음 장: 챗봇/, '장의 마지막 단계는 다음 장으로 넘어간다고 알려야 한다');
const tourHomeIcon = document.querySelector('.guideIcon').innerHTML;

/* 챗봇 장 — 실제 팝업을 열고, 일반 모드 → (로고·Tab 안내) → 살말 모드 순서로 바꿔 보여 준다. */
await next(150);
assert.ok(chatOpen(), '챗봇 장은 실제 챗봇 팝업을 열어야 한다');
assert.equal(CHAT.SM_ON, false, '챗봇 설명은 일반 모드부터 시작해야 한다');
assert.match(document.querySelector('.guidePhase').textContent, /^1단계 · 일반 모드/);
assert.ok(tocButtons[0].classList.contains('done'), '끝낸 장은 완료로 표시해야 한다');
assert.notEqual(document.querySelector('.guideIcon').innerHTML, tourHomeIcon, '장이 바뀌면 그 페이지 아이콘으로 바뀌어야 한다');
await next(); await next();
assert.match(document.querySelector('.guideBody').textContent, /로고를 누르거나[\s\S]*Tab 키/, '모드 전환은 로고와 Tab 키를 모두 알려야 한다');
await next();
assert.match(document.querySelector('.guidePhase').textContent, /^4단계 · 살말 모드/);
assert.equal(CHAT.SM_ON, true, '살말 모드 단계에서는 실제로 살말 모드로 바뀌어야 한다');
assert.ok(document.getElementById('cpOverlay').classList.contains('sm'));
await next();
assert.match(document.querySelector('.guidePhase').textContent, /^5단계 · Virtual Try On/, '살말 모드에서는 왼쪽 아래 Virtual Try On 을 설명해야 한다');
assert.match(document.getElementById('guideTitle').textContent, /Virtual Try On/);
await next();
assert.match(document.querySelector('.guideNext').getAttribute('aria-label'), /다음 장: 트렌드 분석/);

await next(150);
assert.ok(!chatOpen(), '다음 장으로 가면 가이드가 연 챗봇 팝업을 닫아야 한다');
assert.equal(CHAT.SM_ON, false, '다음 장으로 가면 원래 모드로 되돌려야 한다');
assert.equal(document.body.dataset.view, 'trend', '다음 장으로 넘어가면 트렌드 분석 페이지로 이동해야 한다');
assert.equal(document.querySelector('.sItem.on')?.dataset.tr, 'myfeed', '트렌드 분석 장은 내 피드에서 설명해야 한다');
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 7$/);
assert.match(tocButtons[2].querySelector('.tcMeta').textContent, /^1 \/ 7 단계$/, '지금 장에는 진행 단계가 보여야 한다');
click(document.querySelector('.guidePrev'));
await wait(150);
assert.ok(chatOpen() && CHAT.SM_ON, '장 첫 단계에서 이전을 누르면 앞 장(챗봇)의 마지막 단계로 돌아가야 한다');
assert.match(document.querySelector('.guideCount').textContent, /^6 \/ 6$/);

/* 살!말? 목업의 댓글 프로필에도 운영 화면처럼 레벨 띠가 있어야 한다. */
click(tocButtons[3]);
await wait(150);
assert.ok(!chatOpen() && !CHAT.SM_ON, '목차로 장을 옮겨도 챗봇 상태를 되돌려야 한다');
assert.equal(document.body.dataset.view, 'salmal', '목차에서 고른 페이지로 이동해야 한다');
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 11$/);
await next(); await next();
assert.equal(document.querySelectorAll('#salmalGuideDemo .commentsList .cAvatar.rkAv').length, 8, '목업 댓글 여덟 개 모두 레벨 띠가 있어야 한다');
assert.equal(document.querySelectorAll('#salmalGuideDemo .commentsList .cAvatar > .rkRing').length, 8);
assert.match(document.querySelector('.guideBody').textContent, /레벨/, '상세 설명에서 레벨 띠를 알려야 한다');

/* 스타일 장 — 목록 → 첫 스타일 상세(설명 · Virtual Fitting · 실제 상품). */
click(tocButtons[4]);
await wait(150);
assert.equal(document.getElementById('salmalGuideDemo'), null, '장을 옮기면 살!말? 목업을 치워야 한다');
assert.equal(document.body.dataset.view, 'style');
assert.match(document.querySelector('.guideCount').textContent, /^1 \/ 5$/, '스타일 장은 목록 두 단계와 상세 세 단계여야 한다');
assert.ok(shown('styleHome') && !shown('styleDetail'));
await next(); await next();
assert.ok(shown('styleDetail') && !shown('styleHome'), '세 번째 단계부터는 예시 스타일 상세를 열어야 한다');
assert.match(document.getElementById('guideTitle').textContent, /어떻게 시작됐는지/);
await next();
assert.match(document.getElementById('guideTitle').textContent, /Virtual Fitting/);
await next();
assert.match(document.getElementById('guideTitle').textContent, /실제 상품/);
click(document.querySelector('.guidePrev')); await wait(30);
click(document.querySelector('.guidePrev')); await wait(30);
click(document.querySelector('.guidePrev')); await wait(30);
assert.ok(shown('styleHome') && !shown('styleDetail'), '목록 단계로 돌아오면 스타일 목록을 다시 보여야 한다');
for(let i = 0; i < 3; i += 1) await next();
assert.ok(PROFILE.AUTH.in, '이 테스트는 로그인한 상태를 가정한다');
assert.match(document.querySelector('.guideNext').getAttribute('aria-label'), /다음 장: 마이페이지/);

/* 마이페이지 장 — 프로필 · 즐겨입는 스타일(최대 3개) · 오늘의 추천 · 살!말? 피드백. */
await next(150);
assert.ok(shown('styleHome') && !shown('styleDetail'), '스타일 장을 떠나면 원래 보던 스타일 목록으로 돌려놔야 한다');
assert.equal(document.body.dataset.view, 'mypage');
const myTitles = [];
for(let i = 0; i < 4; i += 1){ myTitles.push(document.getElementById('guideTitle').textContent); if(i < 3) await next(); }
assert.match(myTitles[0], /프로필/);
assert.match(myTitles[1], /즐겨입는 스타일은 최대 3개/);
assert.match(myTitles[2], /오늘의 추천/);
assert.match(myTitles[3], /살!말\? 피드백/);
assert.match(document.querySelector('.guideNext').getAttribute('aria-label'), /다음 장: 요금제/);

await next(150);
assert.equal(document.body.dataset.view, 'price');
for(let i = 0; i < 3; i += 1) await next(20);
assert.match(document.getElementById('guideTitle').textContent, /다시 볼 수 있어요/, '마지막 단계는 가이드를 다시 여는 방법을 알려야 한다');
assert.equal(document.querySelector('.guideClose').hidden, true, '조이스틱을 강조하는 마지막 단계에서는 ‘중단하기’를 숨겨야 한다');
assert.match(document.querySelector('.guideIcon').innerHTML, /M3\.5 15\.3/, '마지막 단계 아이콘은 원화가 아니라 조이스틱이어야 한다');
click(document.querySelector('.guidePrev')); await wait(30);
assert.equal(document.querySelector('.guideClose').hidden, false, '앞 단계로 돌아가면 ‘중단하기’가 다시 보여야 한다');
assert.doesNotMatch(document.querySelector('.guideIcon').innerHTML, /M3\.5 15\.3/, '요금제 단계는 요금제 아이콘이어야 한다');
await next();
assert.equal(document.querySelector('.guideNext').getAttribute('aria-label'), '가이드 마치기');
await next(20);
assert.equal(document.querySelector('.guideTour'), null, '완료를 누르면 전체 가이드가 닫혀야 한다');
assert.ok(!document.body.classList.contains('guide-open'), '가이드를 닫으면 로그인 안내 숨김도 풀어야 한다');

/* 로그인 전에는 마이페이지 장이 잠기고, 흐름은 그 장을 건너뛴다. */
PROFILE.AUTH.in = false;
click(tourBtn);
await wait(150);
const lockedToc = [...document.querySelectorAll('.tourToc [data-tour-chapter]')];
assert.ok(lockedToc[5].disabled, '로그인 전에는 마이페이지 장을 누를 수 없어야 한다');
assert.match(lockedToc[5].querySelector('.tcMeta').textContent, /로그인하면 볼 수 있어요/, '잠긴 이유를 보여 줘야 한다');
click(lockedToc[4]);
await wait(150);
for(let i = 0; i < 4; i += 1) await next();
assert.match(document.querySelector('.guideNext').getAttribute('aria-label'), /다음 장: 요금제/, '로그인 전에는 스타일 다음이 요금제여야 한다');
/* 건너뛰기는 가이드를 끝내지 않고 지금 장만 넘긴다(잠긴 마이페이지는 건너뛴다). */
click(document.querySelector('.guideSkip'));
await wait(150);
assert.ok(document.querySelector('.guideTour'), '건너뛰기는 가이드를 끝내면 안 된다');
assert.equal(document.body.dataset.view, 'price', '건너뛰기는 다음 장으로 넘어가야 한다');
assert.ok(!lockedToc[4].classList.contains('done'), '건너뛴 장은 완료로 표시하지 않는다');
click(document.querySelector('.guideClose'));
assert.equal(document.querySelector('.guideTour'), null, '‘중단하기’는 가이드를 바로 끝내야 한다');
PROFILE.AUTH.in = true;

/* 챗봇 팝업이 떠 있을 때 하단 버튼 가이드는 챗봇을 설명하고, 닫으면 팝업과 모드를 그대로 둔다. */
document.getElementById('cpOverlay').classList.add('on');
await HUB.startContextGuide();
await wait(60);
assert.match(document.querySelector('.guidePhase').textContent, /^1단계 · 일반 모드/, '챗봇이 열려 있으면 챗봇 가이드를 보여 줘야 한다');
for(let i = 0; i < 3; i += 1) await next();
assert.equal(CHAT.SM_ON, true);
click(document.querySelector('.guideSkip'));
assert.ok(chatOpen(), '원래 열려 있던 챗봇 팝업은 닫지 않아야 한다');
assert.equal(CHAT.SM_ON, false, '가이드를 닫으면 원래 모드로 돌아가야 한다');
document.getElementById('cpOverlay').classList.remove('on');

console.log('✅ 전역 도움말 허브와 페이지별 무조회 트렌드 가이드');
process.exit(0);
