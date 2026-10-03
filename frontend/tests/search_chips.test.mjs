/* 검색 칩 — "고르지도 않은 조건이 같이 걸린다" 를 막는다.
 *
 * ★ 이 시험이 잡아낸 것 (2026-09-22)
 *   ① 검색창은 조건을 **쌓기만** 했다. '가디건' 을 쳤는데 지난 검색의
 *      브랜드 칩이 그대로 남아, 고른 적 없는 브랜드가 결과·제목에 섞였다.
 *   ② 세부 검색은 한 축에 여러 값을 쌓았다(push). 브랜드를 두 번 고르면
 *      칩이 두 개가 됐다 — 칸은 넷인데 칩은 계속 늘었다.
 *   ③ 할인률 변화는 축 이름이 다른데(카테고리·상품명) 조건을 들고
 *      넘어가서, 그 탭 칸에는 없는 축이 칩으로만 남았다.
 *
 * 돌리는 법:  node tests/search_chips.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'), {url:'http://localhost:5173/'});
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement',
                 'KeyboardEvent','MouseEvent','CustomEvent','MutationObserver'])
  globalThis[k] = k==='window'?dom.window:dom.window[k];
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
/* 서버는 없다 — 화면에 박아 둔 목록(FTREE)으로 돈다. 칩 규칙은 그것과 무관하다. */
globalThis.fetch = async () => { throw new Error('ECONNREFUSED') };

await import(`${F}/main.js`);
const S = await import(`${F}/style/static/js/search.js`);
const { trRender } = await import(`${F}/trend/static/js/dispatch.js`);

let pass=0, fail=0;
const t=async(n,f)=>{try{await f();console.log('✅',n);pass++}catch(e){console.log('❌',n,'\n   ',e.message);fail++}};
const wait=(ms=60)=>new Promise(r=>setTimeout(r,ms));
const inp=()=>document.getElementById('fsInput');
const chips=()=>[...document.querySelectorAll('#fsChips .fsChip')]
  .map(c=>c.querySelector('small').textContent+'|'+c.childNodes[1].textContent);
const type=async(q)=>{
  const i=inp(); i.value=q;
  i.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
  i.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  await wait();
};

await t('검색 한 번 = 칩 하나', async () => {
  trRender('life'); await wait();
  await type('가디건');
  assert.equal(chips().length, 1, '칩은 하나여야 한다 — 지금 '+JSON.stringify(chips()));
});

await t('★ 다시 검색하면 앞 조건이 남지 않는다 (고르지 않은 브랜드가 따라오던 자리)', async () => {
  await type('스투시');
  const c=chips();
  assert.equal(c.length, 1, '앞 조건이 남았다 — '+JSON.stringify(c));
  assert.match(c[0], /스투시/);
});

await t('★ 스타일을 쳐도 앞 브랜드가 따라오지 않는다', async () => {
  await type('고프코어');
  const c=chips();
  assert.equal(c.length, 1, '브랜드가 같이 남았다 — '+JSON.stringify(c));
  assert.match(c[0], /^스타일\|고프코어$/);
});

await t('걸려 있는 말을 다시 치면 빠진다', async () => {
  await type('고프코어');
  assert.equal(chips().length, 0, '토글이 안 된다 — '+JSON.stringify(chips()));
});

await t('세부 검색 — 고른 칸 수만큼만 칩이 선다 (넷이면 넷)', async () => {
  S.fsReset();
  S.fsToggle('스타일','고프코어'); S.fsToggle('브랜드','아크테릭스');
  S.fsToggle('종류','테크 셸');   S.fsToggle('아이템명','베타 LT');
  S.fsChipsPaint();
  assert.equal(chips().length, 4, '칸은 넷인데 칩이 '+chips().length+'개 — '+JSON.stringify(chips()));
});

await t('★ 한 칸에 두 값을 고르면 갈아 끼운다 (쌓이지 않는다)', async () => {
  S.fsToggle('브랜드','노스페이스');
  S.fsChipsPaint();
  const c=chips();
  assert.equal(c.length, 4, '브랜드가 쌓였다 — '+JSON.stringify(c));
  assert.ok(c.some(x=>x==='브랜드|노스페이스'), '마지막에 고른 것이 남아야 한다');
  assert.ok(!c.some(x=>x==='브랜드|아크테릭스'), '앞의 브랜드가 남아 있다');
});

await t('칩의 × 는 그 조건만 뗀다', async () => {
  const before=chips().length;
  document.querySelector('#fsChips .fsChip button').dispatchEvent(
    new dom.window.MouseEvent('click',{bubbles:true}));
  await wait();
  assert.equal(chips().length, before-1, '하나만 빠져야 한다 — '+JSON.stringify(chips()));
});

await t('★ 할인률 변화는 칩을 세우지 않고 상품 이름만 적는다', async () => {
  trRender('stock'); await wait();
  S.fsStockSelect({id:17,label:'베타 LT 자켓',brand:'아크테릭스',source:'무신사'});
  S.fsChipsPaint();
  const box=document.getElementById('fsChips');
  assert.equal(box.querySelectorAll('.fsChip').length, 0, '칩이 서 있다');
  assert.ok(box.querySelector('.fsPickName'), '상품 이름이 없다');
  assert.match(box.textContent, /베타 LT 자켓/);
});

await t('★ 할인률에서 나가면 그 탭 조건이 따라가지 않는다', async () => {
  S.fsToggle('브랜드','아크테릭스');      /* 할인률 팝업에서 후보를 좁힌 상태 */
  trRender('life'); await wait();
  assert.equal(S.fsCount(), 0, '할인률에서 고른 조건이 넘어왔다 — '+JSON.stringify(S.FS.pick));
  assert.equal(chips().length, 0);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail?1:0);
