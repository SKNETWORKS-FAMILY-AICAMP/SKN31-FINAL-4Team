import { JSDOM } from 'jsdom';
import fs from 'node:fs';

/* 진짜 브라우저 환경을 만든다. node --check 는 정의되지 않은 이름을 통과시킨다. */
const dom = new JSDOM('<!doctype html><body></body>', {pretendToBeVisual:true});
global.window = dom.window; global.document = dom.window.document;
global.location = dom.window.location;
global.requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
global.fetch = async () => { throw new Error('네트워크 없음 (의도됨)') };
global.TextDecoder = global.TextDecoder || dom.window.TextDecoder;
global.AbortController = global.AbortController || dom.window.AbortController;

const api = await import('./chat_api.js');
const FX = JSON.parse(fs.readFileSync('_chat_fixtures.json','utf8'));

/* CSS 에 실제로 있는 선택자를 모은다 */
const cssText = fs.readdirSync('css').map(f=>fs.readFileSync('css/'+f,'utf8')).join('\n');
const declared = new Set();
for (const m of cssText.matchAll(/\.([A-Za-z][A-Za-z0-9_-]*)/g)) declared.add(m[1]);

let fail = 0;
const ok = (c,msg)=>{ console.log((c?'  OK  ':'  X!! ')+msg); if(!c) fail++; };

console.log('=== 1. 렌더링이 실제로 도는가 ===');
const cases = Object.fromEntries(Object.entries(FX)
  .filter(([k,v]) => v && typeof v === 'object')
  .map(([k,v]) => [k, v.ok === false ? api.refusalHTML(v) : api.reportHTML(v)]));
for (const [k,html] of Object.entries(cases)) ok(html && html.length>50, `${k} 렌더 (${html.length}자)`);

console.log('\n=== 2. 쓰는 클래스가 CSS 에 다 있는가 ===');
const used = new Set();
for (const html of Object.values(cases))
  for (const m of html.matchAll(/class="([^"]+)"/g))
    m[1].split(/\s+/).forEach(c=>c&&used.add(c));
const missing = [...used].filter(c=>!declared.has(c));
ok(missing.length===0, `사용 ${used.size}개 / 없는 것: ${missing.length?missing.join(', '):'없음'}`);
console.log('     사용:', [...used].sort().join(' '));

console.log('\n=== 3. DOM 으로 파싱했을 때 구조가 맞는가 ===');
const box = document.createElement('div');
box.innerHTML = cases.level;
ok(box.querySelector('.skillReport--legacy'), '이전 지표도 LIVE REPORT 프레임 사용');
ok(box.textContent.includes('FEEDiT / LIVE REPORT'), 'LIVE REPORT 메타 헤더 표시');
ok(!box.querySelector('.ansBar'), '브라우저형 메타 바 제거');
ok(box.querySelectorAll('.ansBody > div').length===2, `.ansBody 자식 2칸 (실제 ${box.querySelectorAll('.ansBody > div').length}) — 3칸이면 그리드가 깨진다`);
ok(box.querySelectorAll('.rank .row').length>=2, `.rank 행 ${box.querySelectorAll('.rank .row').length}개`);
ok(box.querySelectorAll('.bars .b').length>0, `.bars 막대 ${box.querySelectorAll('.bars .b').length}개`);
const fb = document.createElement('div'); fb.innerHTML = cases.level_free;
ok(fb.querySelectorAll('.ansBody > div').length===2, 'FREE 도 2칸');
ok(!!fb.querySelector('.kwReq .ask button'), 'FREE 에는 업셀 버튼');
ok(!fb.querySelector('.bars'), 'FREE 에는 플랫폼 막대가 없다 (서버가 잘랐다)');

console.log('\n=== 4. 이스케이프 ===');
const evil = JSON.parse(JSON.stringify(FX.level));
/* 블록 안에 주입을 심는다 — 서버가 오염된 값을 보내도 화면이 안 뚫려야 한다 */
evil.blocks = [
  {type:'rank', slot:'left', title:'<img src=x onerror=alert(1)>', meta:'x',
   rows:[{k:'<script>bad()</script>', small:'<b>x</b>', v:'1', up:true}]},
  {type:'quotes', slot:'right', title:'q', items:[{src:'"><script>y()</script>',kind:'댓글',body:'<img src=x>'}]},
];
const eb = document.createElement('div'); eb.innerHTML = api.reportHTML(evil);
ok(eb.querySelectorAll('img,script').length===0, `주입된 태그가 살아남지 않음 (img/script ${eb.querySelectorAll('img,script').length}개)`);
ok(eb.textContent.includes('<img src=x'), '원문은 글자로 보인다');

console.log('\n=== 5. fillBars 가 실제로 도는가 ===');
const bb = document.createElement('div'); bb.innerHTML = cases.level; document.body.appendChild(bb);
api.fillBars(bb);
const bars = bb.querySelectorAll('i[data-w]');
ok(bars.length>0, `대상 ${bars.length}개`);
ok([...bars].every(i=>i.style.width!==''), '너비가 설정됨');

console.log('\n=== 6. 서버가 없을 때 ===');
const up = await api.isUp();
ok(up===false, `isUp() = ${up} (네트워크 없음 → false 여야 폴백이 돈다)`);
let threw=false; try{ await api.askStream({question:'x'},{}) }catch(e){ threw=true }
ok(threw, 'askStream 은 던진다 (부르는 쪽이 폴백)');

console.log('\n=== 7. API_BASE ===');
/* 버셀 릴레이를 붙이면서 같은 출처의 /api 로 바꿨다(chat_api.js 머리말).
   주소를 직접 쓰는 건 file:// 로 열었을 때뿐이다 — jsdom 은 about:blank 라
   여기서는 '/api' 가 맞다. 8770 을 기대하던 옛 단언이 계속 실패하고 있었다. */
ok(api.API_BASE==='/api', `기본 ${api.API_BASE} (file:// 가 아니면 같은 출처)`);

console.log(fail? `\n실패 ${fail}건` : '\n전부 통과');
process.exit(fail?1:0);
