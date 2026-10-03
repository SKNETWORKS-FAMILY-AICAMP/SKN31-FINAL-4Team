/* 의도별 구조가 실제로 다르게 그려지는지 + 쓰는 클래스가 전부 CSS 에 있는지 */
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
const dom=new JSDOM('<!doctype html><body></body>',{url:'http://localhost:5173/',pretendToBeVisual:true});
for(const k of ['location','requestAnimationFrame','HTMLElement','Node','TextDecoder','AbortController'])
  { try{ global[k]=dom.window[k]??global[k] }catch(e){} }
global.window=dom.window; global.document=dom.window.document;
global.fetch=async()=>{throw new Error('no net')};

const api=await import('./chat_api.js');
const FX=JSON.parse(fs.readFileSync('_chat_fixtures.json','utf8'));
const cssText=fs.readdirSync('css').map(f=>fs.readFileSync('css/'+f,'utf8')).join('\n');
const declared=new Set(); for(const m of cssText.matchAll(/\.([A-Za-z][A-Za-z0-9_-]*)/g)) declared.add(m[1]);

let fail=0; const ok=(c,m)=>{console.log((c?'  OK  ':'  X!! ')+m); if(!c)fail++;};
const allUsed=new Set();
const shapes={};

console.log('=== 의도별 구조 ===');
for(const [k,rep] of Object.entries(FX)){
  if(rep.ok===false) continue;
  const html=api.reportHTML(rep);
  const box=document.createElement('div'); box.innerHTML=html;
  for(const m of html.matchAll(/class="([^"]+)"/g)) m[1].split(/\s+/).forEach(c=>c&&allUsed.add(c));
  const parts=[];
  if(box.querySelector('.rpFull')) parts.push('full');
  const bodies=box.querySelectorAll('.ansBody > div');
  const sig=[...box.querySelectorAll('.rank,.bars,.mTable,.kpis,.rpProse,.kwReq,.note')]
    .map(e=>e.className.split(' ')[0]||e.tagName.toLowerCase());
  shapes[k]=sig.join(',');
  console.log(`  ${k.padEnd(11)} ${rep.intent.padEnd(18)} ${sig.join(' → ')}`);
  ok(bodies.length===2 || bodies.length===0, `${k}: .ansBody 자식 ${bodies.length} (2 여야 한다)`);
}

console.log('\n=== 구조가 실제로 다른가 ===');
const uniq=new Set(Object.values(shapes));
ok(uniq.size>=5, `서로 다른 구조 ${uniq.size}종 / 케이스 ${Object.keys(shapes).length}개`);
ok(shapes.direction!==shapes.level, 'direction 과 level 이 다르다');
ok(shapes.assoc!==shapes.level, 'assoc 과 level 이 다르다');
ok(shapes.web!==shapes.level, 'web 과 level 이 다르다');
ok(shapes.level_free!==shapes.level, 'FREE 와 PRO 가 다르다');

console.log('\n=== 클래스 실재 ===');
const miss=[...allUsed].filter(c=>!declared.has(c));
ok(miss.length===0, `사용 ${allUsed.size}개 / 없는 것: ${miss.join(', ')||'없음'}`);
console.log('     ', [...allUsed].sort().join(' '));

console.log('\n=== 주입 방어 (web 출처 제목) ===');
const wb=document.createElement('div'); wb.innerHTML=api.reportHTML(FX.web);
ok(wb.querySelectorAll('img,script').length===0, '주입 태그 0개');
ok(wb.textContent.includes('<img'), '글자로만 보인다');

console.log('\n=== 모르는 블록 타입 ===');
const un=JSON.parse(JSON.stringify(FX.level));
un.blocks.push({type:'미래에생길블록',slot:'left',x:1});
let threw=false; let h2='';
try{ h2=api.reportHTML(un) }catch(e){ threw=true }
ok(!threw && h2.length>100, '건너뛰고 나머지는 그린다 (화면이 안 깨진다)');

console.log(fail?`\n실패 ${fail}건`:'\n전부 통과');
process.exit(fail?1:0);
