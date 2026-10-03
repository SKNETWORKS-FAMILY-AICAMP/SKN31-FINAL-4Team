/* 상단 탭과 트렌드 분석 ↔ 살!말? 왕복에서 화면 전체가 다시 사라졌다 나타나지 않는다. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root=new URL('..',import.meta.url).href.replace(/\/$/,'');
const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
const dom=new JSDOM(html,{url:'http://localhost:5173/'});
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent'])
  globalThis[key]=key==='window'?dom.window:dom.window[key];
/* notify.js 가 본문을 기다릴 때 쓴다 — jsdom 전역에 없어서 이 시험들이 통째로 죽어 있었다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);
globalThis.cancelAnimationFrame=id=>clearTimeout(id);
globalThis.addEventListener=dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener=dom.window.removeEventListener.bind(dom.window);
globalThis.location=dom.window.location;
globalThis.history=dom.window.history;
globalThis.localStorage=dom.window.localStorage;
globalThis.innerWidth=1440;
globalThis.innerHeight=900;
globalThis.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
globalThis.scrollTo=()=>{};
globalThis.IntersectionObserver=class{observe(){} unobserve(){} disconnect(){}};
globalThis.ResizeObserver=class{observe(){} unobserve(){} disconnect(){}};

const viewAnimations=[];
globalThis.anime={
  animate(target,options){
    if(target?.classList?.contains('view'))viewAnimations.push({id:target.id,options});
    return {pause(){},cancel(){},play(){}};
  },
  createTimeline(){return {add(){return this},call(){return this}}},
  stagger(){return ()=>0},
  spring(){return 'linear'},
  utils:{set(){},remove(){}},
  createDrawable(){return []},
  splitText(){return {}},
};
const reply=payload=>({ok:true,status:200,text:async()=>JSON.stringify(payload),json:async()=>payload});
globalThis.fetch=async url=>{
  if(String(url).includes('/api/auth/me'))return reply({status:'ok',data:{authenticated:false,csrf_token:'csrf',user:null}});
  if(String(url).includes('/api/salmal/cards'))return reply({status:'ok',data:{items:[]}});
  return reply({status:'empty',reason:'테스트 데이터 없음',data:null});
};

await import(`${root}/main.js`);
const router=await import(`${root}/app_shell/static/js/router.js`);
document.getElementById('jumpBtn').click();
router.goView('trend');
await new Promise(resolve=>setTimeout(resolve,270));
assert.ok(viewAnimations.some(call=>call.id==='v-trend'),'첫 진입 모션은 유지한다');

const body=document.getElementById('trBody');
const marker=document.createElement('span');
marker.id='preserved-trend-content';
body.append(marker);
viewAnimations.length=0;
document.getElementById('v-trend').style.opacity='0';
document.getElementById('v-salmal').style.opacity='0';
router.goView('salmal');
router.goView('trend');
assert.equal(router.curView,'trend');
assert.ok(document.getElementById('side').classList.contains('open'),'돌아오면 사이드바가 바로 열린다');
assert.ok(body.contains(marker),'같은 트렌드 탭의 내용은 다시 그리지 않는다');
assert.equal(document.getElementById('v-trend').style.opacity,'','이전 뷰의 투명도 0을 지운다');
assert.equal(document.getElementById('v-salmal').style.opacity,'','살!말? 뷰의 투명도 0을 지운다');
assert.deepEqual(viewAnimations,[],'왕복 중 화면 전체에 페이드 모션을 다시 걸지 않는다');

document.querySelector('.sItem[data-tr="assoc"]').click();
body.append(marker);
router.goView('salmal');
router.goView('trend');
assert.equal(document.getElementById('trTitle').textContent,'내 피드','다른 트렌드 탭에서 돌아오면 내 피드로 되돌린다');
assert.ok(!body.contains(marker),'다른 트렌드 탭의 내용은 재사용하지 않는다');

router.goView('home');
router.goView('trend');
body.append(marker);
router.goView('salmal');
await new Promise(resolve=>setTimeout(resolve,270));
assert.ok(body.contains(marker),'떠난 화면의 예약된 다시 그리기는 실행하지 않는다');

viewAnimations.length=0;
for(const view of ['home','trend','salmal','style','style','price','home']){
  const target=document.getElementById('v-'+view);
  target.style.opacity='0';
  if(view==='home')document.querySelector('#v-home .mKicker').style.opacity='0';
  document.querySelector(`#mNav button[data-v="${view}"]`).click();
  assert.equal(router.curView,view,`상단 ${view} 탭으로 이동한다`);
  assert.ok(target.classList.contains('on'),`상단 ${view} 화면이 보인다`);
  assert.equal(target.style.opacity,'',`상단 ${view} 화면의 남은 투명도를 지운다`);
  if(view==='home')assert.equal(document.querySelector('#v-home .mKicker').style.opacity,'','홈 히어로의 남은 투명도도 지운다');
  if(view==='trend')assert.ok(document.getElementById('side').classList.contains('open'),'상단 탭에서 트렌드 사이드바가 바로 열린다');
}
assert.deepEqual(viewAnimations,[],'상단 탭 전환에서 화면 전체 페이드 모션을 실행하지 않는다');

globalThis.matchMedia=()=>({matches:true,addEventListener(){},addListener(){}});
router.goView('home');
router.goView('trend',true);
assert.ok(!document.getElementById('side').classList.contains('open'),'작은 화면에서는 사이드바가 자동으로 본문을 덮지 않는다');
router.trSideOpen(true);
assert.equal(document.getElementById('sToggle').getAttribute('aria-expanded'),'true');
window.dispatchEvent(new window.Event('resize'));
assert.ok(!document.getElementById('side').classList.contains('open'),'작은 화면으로 바꾸면 사이드바가 접힌다');
assert.equal(document.getElementById('sToggle').getAttribute('aria-expanded'),'false');

console.log('✅ 상단 탭과 트렌드 분석 ↔ 살!말? 빠른 전환에서 화면 깜빡임이 없습니다.');
process.exit(0);
