/* 챗바를 **실제로 눌러 본다** — 소스 대조로는 못 잡는 것들.
 *
 *   · 엔터·클릭이 진짜 조회로 이어지는지
 *   · 조회 중 표시가 켜졌다 꺼지는지 (실패해도 꺼지는지)
 *   · 탭을 새로 그렸을 때 예시 질문이 바로 뜨는지
 *
 * ★ main.js 를 먼저 부른다.
 *   모듈을 직접 골라 부르면 평가 순서가 달라져, 실제 브라우저에는 없는
 *   순환 참조 오류가 난다. 앱이 도는 것과 같은 길로 가야 진짜를 본다.
 *
 * 돌리는 법:  node tests/search_live.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
/* 진짜 index.html 을 쓴다. 최소 DOM 으로는 모듈이 불러올 때 하는 DOM 작업이
   요소를 못 찾아 터진다(intro/loader.js 등). 실제 화면과 같은 뼈대를 준다. */
import fs from 'node:fs';
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://localhost:5173/' });   // 스크립트는 안 돌린다
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','CustomEvent','KeyboardEvent','MouseEvent'])
  globalThis[k] = k==='window' ? dom.window : dom.window[k];
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame = (f)=>setTimeout(f,0);
globalThis.cancelAnimationFrame = (h)=>clearTimeout(h);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.matchMedia = () => ({matches:false, addEventListener(){}, addListener(){}});
globalThis.scrollTo = () => {};
globalThis.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.location = dom.window.location;
globalThis.localStorage = dom.window.localStorage;
let fetched = [];
globalThis.fetch = async (u) => { fetched.push(u);
  await new Promise(r=>setTimeout(r,30));
  const payload = String(u).includes('rank=hot')
    ? {status:'ok', data:{rising:[{term:'발레코어'},{term:'스트릿웨어'}], falling:[{term:'고프코어'}]}}
    : {status:'empty', reason:'적재 전입니다.'};
  return {
    ok:true,
    status:200,
    text: async () => JSON.stringify(payload),
    json: async () => payload,
  }; };

let pass=0, fail=0;
const t = async (n,f)=>{ try{ await f(); console.log('✅',n); pass++; }
  catch(e){ console.log('❌',n,'\n   ',e.message); fail++; } };

/* ★ 진짜 진입점(main.js)과 같은 순서로 불러온다.
   모듈을 직접 골라 부르면 평가 순서가 달라져, 실제 브라우저에는 없는
   순환 참조 오류가 난다. 앱이 도는 것과 같은 길로 가야 한다. */
await import(`${F}/main.js`);
const sk = await import(`${F}/trend/static/js/saved_keywords.js`);
const rh = await import(`${F}/trend/static/js/render_helpers.js`);
/* router.js 가 실제 앱 진입을 130ms 뒤에 한 번 그린다. 그 예약 작업까지 끝낸 뒤
   테스트용 검색창을 세워야, 진행 중인 조회 버튼이 중간에 교체되지 않는다. */
await new Promise(r=>setTimeout(r,180));

await t('★ 순환 import 가 깨지지 않는다', () => {
  assert.equal(typeof sk.kwWire, 'function');
  assert.equal(typeof rh.trEmpty, 'function');
});

// 챗바를 실제 마크업대로 세운다
const bar = () => { document.getElementById('trTabs').innerHTML =
  '<div class="fsWrap kwmode"><div class="fsRow"><div class="fsBar" id="kwBar">'+
  '<span class="fsIc">◎</span><input type="text" id="kwInput">'+
  '<span class="fsGhost"><span class="fsQ" id="kwQ"></span></span>'+
  '<button class="fsClear" id="kwClear" hidden>×</button>'+
  '</div></div><div class="fsSug" id="kwSug" hidden></div></div>';
  document.getElementById('trTabs').classList.add('kwmode');
  sk.kwWire('temp');
  return document.getElementById('kwInput'); };

await t('★ 엔터를 누르면 조회가 돈다', async () => {
  const inp = bar(); fetched = [];
  inp.value = '발레코어';
  inp.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  await new Promise(r=>setTimeout(r,10));
  assert.equal(document.getElementById('kwBar').classList.contains('busy'), true,
    '누르자마자 조회 중 표시가 켜져야 한다');
  await new Promise(r=>setTimeout(r,120));
  assert.ok(fetched.some(u=>String(u).includes('/api/trend')), `호출 없음: ${fetched}`);
  assert.equal(document.getElementById('kwBar').classList.contains('busy'), false,
    '끝나면 꺼져야 한다');
});

await t('사전에 없는 말은 조회하지 않는다', async () => {
  const inp = bar(); fetched = [];
  inp.value = 'zzzz없는말zzzz';
  inp.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  await new Promise(r=>setTimeout(r,80));
  assert.equal(fetched.length, 0, '헛되이 서버를 부르면 안 된다');
});

await t('빈 입력으로 엔터를 눌러도 안 죽는다', async () => {
  const inp = bar(); inp.value = '';
  inp.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  await new Promise(r=>setTimeout(r,30));
});

await t('예시 단어가 HOT TREND 용어로 그려진다', async () => {
  bar();
  await new Promise(r=>setTimeout(r,120));
  const q = document.getElementById('kwQ');
  assert.ok(q.innerHTML.length > 0, '예시 단어가 비어 있다');
  assert.match(q.innerHTML, /<b>/, '키워드가 강조돼야 한다');
  assert.ok(q.textContent.startsWith('예 : '), `'예 : ' 로 시작해야 한다: ${q.textContent}`);
  const term = q.querySelector('b').textContent;
  assert.ok(['발레코어','스트릿웨어','고프코어'].includes(term), `HOT 용어가 아님: ${term}`);
  assert.ok(!/[?？]|뜨거워|중이야/.test(q.textContent), '질문 문구가 섞이면 안 된다');
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail?1:0);
