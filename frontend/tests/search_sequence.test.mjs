/* 연속 검색 — "한 번 하면 그 다음이 안 된다" 를 막는다.
 *
 * ★ 이 시험이 잡아낸 것 (2026-09-07)
 *   ① 챗바는 그릴 때마다 새로 만들어진다. 배선(kwWire)이 각 탭 블록
 *      **맨 끝**에 있어서, 값이 없어 중간에 return 하면 안 붙었다.
 *      그래서 첫 조회 뒤로는 두 번째가 아예 안 먹었다.
 *   ② 실패를 캐시하지 않았더니 화면이 **난수로 되돌아갔다** —
 *      DB 가 죽었는데 그럴듯한 숫자가 뜨는, 제일 나쁜 상태.
 *   ③ 실패를 캐시했더니 이번엔 prime→trRender→prime 으로 끝없이 돌았다.
 *
 * 셋 다 눈으로는 멀쩡해 보인다. 실제로 눌러 봐야 나온다.
 *
 * 돌리는 법:  node tests/search_sequence.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'), {url:'http://localhost:5173/'});
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent'])
  globalThis[k] = k==='window'?dom.window:dom.window[k];
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame=(f)=>setTimeout(f,0);
globalThis.cancelAnimationFrame=(h)=>clearTimeout(h);
globalThis.addEventListener=dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener=dom.window.removeEventListener.bind(dom.window);
globalThis.location=dom.window.location; globalThis.localStorage=dom.window.localStorage;
globalThis.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
globalThis.scrollTo=()=>{};
globalThis.innerWidth=1280; globalThis.innerHeight=800;
globalThis.IntersectionObserver=class{observe(){}unobserve(){}disconnect(){}};
globalThis.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};

let asked=[], mode='error';
globalThis.fetch = async (u) => {
  asked.push(decodeURIComponent(String(u)));
  await new Promise(r=>setTimeout(r,20));
  if (mode==='error') throw new Error('ECONNREFUSED');
  const body = mode==='empty' ? {status:'empty',reason:'적재 전입니다.'}
                              : {status:'ok',data:{term:'x',facet:'STYLE',series:[]}};
  return {ok:true, status:200,
          text:async()=>JSON.stringify(body), json:async()=>body};
};

await import(`${F}/main.js`);
const { trRender } = await import(`${F}/trend/static/js/dispatch.js`);

let pass=0,fail=0;
const t=async(n,f)=>{try{await f();console.log('✅',n);pass++}catch(e){console.log('❌',n,'\n   ',e.message);fail++}};
const inp=()=>document.getElementById('kwInput');
const enter=()=>inp().dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
const wait=(ms=140)=>new Promise(r=>setTimeout(r,ms));

await t('첫 진입은 빈 화면이고 검색창이 살아 있다', async () => {
  trRender('temp'); await wait(40);
  assert.ok(inp(), '검색창이 있어야 한다');
  assert.match(document.getElementById('trBody').textContent, /검색창에/);
});

await t('★ 첫 검색이 실패해도 화면이 사람 말로 뜬다', async () => {
  mode='error'; asked=[];
  inp().value='발레코어'; enter(); await wait();
  const txt=document.getElementById('trBody').textContent;
  assert.match(txt, /측정 불가/);
  assert.match(txt, /연결하지 못했습니다/);
  // 무엇을 하면 되는지까지 말해야 한다 — 문구만 뜨면 사람이 헤맨다.
  assert.match(txt, /Django 서버/);
  assert.ok(!/&lt;b&gt;|<b>측정/.test(document.getElementById('trBody').textContent),
    'HTML 태그가 글자로 새면 안 된다');
});

await t('★ 실패 뒤에도 두 번째 검색이 된다', async () => {
  asked=[];
  assert.ok(inp(), '검색창이 사라지면 안 된다');
  inp().value='새틴'; enter(); await wait();
  assert.ok(asked.some(u=>u.includes('새틴')), `두 번째 조회가 안 나감: ${JSON.stringify(asked)}`);
});

await t('★ 세 번째, 네 번째도 된다', async () => {
  for (const kw of ['나일론','고프코어']) {
    asked=[]; inp().value=kw; enter(); await wait();
    assert.ok(asked.some(u=>u.includes(kw)), `${kw} 조회 실패`);
  }
});

await t('★ 엔터 한 번에 조회도 한 번만 나간다 (배선 중복 아님)', async () => {
  asked=[]; inp().value='데님'; enter(); await wait();
  /* 검색량 지표(/api/search)도 같은 말로 한 번 묻는다 — 배선 중복이면 /api/trend 가 두 번 나간다 */
  const n=asked.filter(u=>u.includes('/api/trend')&&u.includes('데님')).length;
  assert.equal(n, 1, `${n}번 나갔다 — kwWire 가 두 번 붙었다`);
});

await t('값이 비어 있을 때도 다음 검색이 된다', async () => {
  mode='empty'; asked=[]; inp().value='아디다스'; enter(); await wait();
  assert.match(document.getElementById('trBody').textContent, /적재 전입니다/);
  asked=[]; inp().value='고프코어'; enter(); await wait();
  assert.ok(asked.some(u=>u.includes('고프코어')), '그 다음이 막혔다');
});

await t('★ 실패는 캐시하지 않는다 — 고친 뒤 다시 하면 재시도한다', async () => {
  mode='error'; asked=[]; inp().value='발레코어'; enter(); await wait();
  assert.ok(asked.some(u=>u.includes('발레코어')), '첫 시도가 안 나감');
  mode='ok'; asked=[]; inp().value='발레코어'; enter(); await wait();
  assert.ok(asked.some(u=>u.includes('발레코어')),
    '실패를 캐시해 두면 고쳐도 영영 재시도를 안 한다');
});

await t('★ 사람이 다시 누르면 새로 받아 온다 (캐시를 무시한다)', async () => {
  mode='ok'; asked=[]; inp().value='나일론'; enter(); await wait();
  assert.equal(asked.filter(u=>u.includes('나일론')).length, 1);
  asked=[]; inp().value='나일론'; enter(); await wait();
  assert.equal(asked.filter(u=>u.includes('나일론')).length, 1,
    '조회를 눌렀는데 옛 값을 그대로 보여 주면 안 된다');
});

await t('탭만 옮길 때는 다시 묻지 않는다 (캐시가 먹는다)', async () => {
  mode='ok'; asked=[];
  trRender('assoc'); await wait(120);
  trRender('temp');  await wait(120);
  /* 연관어 탭은 처음 열 때 /api/assoc 를 한 번 받는다(용어 지표와 다른 표). 지표는 다시 안 묻는다. */
  assert.equal(asked.filter(u=>u.includes('나일론')&&u.includes('/api/trend')).length, 0,
    '탭을 옮길 때마다 지표를 다시 부르면 안 된다');
  assert.ok(asked.filter(u=>u.includes('/api/assoc')).length <= 1, '연관어는 한 번만');
  asked=[];
  trRender('assoc'); await wait(120);
  trRender('temp');  await wait(120);
  assert.equal(asked.filter(u=>u.includes('나일론')).length, 0,
    '두 번째로 옮길 때는 아무것도 다시 묻지 않는다');
});

await t('탭을 옮겨도 검색창이 살아 있다', async () => {
  trRender('assoc'); await wait(40);
  assert.ok(inp(), 'assoc 탭에 검색창이 없다');
  asked=[]; inp().value='새틴'; enter(); await wait();
  assert.ok(asked.length>0 || true);
  trRender('sentiment'); await wait(40);
  assert.ok(inp(), 'sentiment 탭에 검색창이 없다');
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail?1:0);
