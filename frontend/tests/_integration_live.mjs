/* 통합 확인 — 로컬 Django(:8000, 실데이터 또는 시드 데이터)에 붙여 트렌드 분석 6개 탭을 실제로 그려 본다.
 *   cd backend && python manage.py runserver 8000   →   node tests/_integration_live.mjs
 *   (npm test 에는 넣지 않는다 — 떠 있는 백엔드가 필요하다) */
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
globalThis.scrollTo=()=>{}; globalThis.innerWidth=1280; globalThis.innerHeight=800;
globalThis.IntersectionObserver=class{observe(){}unobserve(){}disconnect(){}};
globalThis.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
const realFetch=globalThis.fetch;
globalThis.fetch=(u,o)=>realFetch(String(u).startsWith('/')?'http://127.0.0.1:8000'+u:u,o);
const errs=[]; process.on('unhandledRejection',e=>errs.push(String(e&&e.stack||e)));
await import(`${F}/main.js`);
const { trRender } = await import(`${F}/trend/static/js/dispatch.js`);
const { KW } = await import(`${F}/trend/static/js/render_helpers.js`);
const { FS } = await import(`${F}/style/static/js/search.js`);
const wait=(ms)=>new Promise(r=>setTimeout(r,ms));
const body=()=>document.getElementById('trBody');
async function show(id, label){
  try { trRender(id); } catch(e){ errs.push(id+': '+e.stack); }
  await wait(1500);
  const b=body(); const txt=b.textContent.replace(/\s+/g,' ');
  const charts=[...b.querySelectorAll('[data-chart]')].map(c=>c.dataset.chart+'='+c.dataset.live);
  console.log(`\n=== ${label} [${id}] charts: ${charts.join(', ')}`);
  console.log(txt.slice(0,700));
}
KW.q='고프코어';
await show('temp','언급량·온도'); await show('assoc','연관어'); await show('sentiment','긍부정');
FS.pick={'브랜드':['살로몬'],'종류':['스니커즈']};
await show('stock','할인률 통합');
await show('resale','리세일'); await show('life','수명주기');
KW.q='없는말'; await show('temp','없는 말');
console.log('\nERRORS:', errs.length? errs.join('\n'):'none');
process.exit(0);
