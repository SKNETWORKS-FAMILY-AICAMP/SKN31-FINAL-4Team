/* 웹 검색 블록 + 출처 링크 검증 */
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
const dom = new JSDOM('<!doctype html><body></body>',{url:'http://localhost:5173/',pretendToBeVisual:true});
for(const k of ['location','requestAnimationFrame','HTMLElement','Node','TextDecoder','AbortController'])
  { try{ global[k]=dom.window[k]??global[k] }catch(e){} }
global.window=dom.window; global.document=dom.window.document;
global.fetch=async()=>{throw new Error('no net')};

const api = await import('./chat_api.js');
const FX = JSON.parse(fs.readFileSync('_chat_fixtures.json','utf8'));

const rep = JSON.parse(JSON.stringify(FX.pro_level));
rep.intent='knowledge.origin';
rep.web={ answer:'고프코어는 등산·트레일 장비를 도심에서 입는 흐름입니다.\n2017년 뉴욕 매거진이 이름을 붙였습니다.',
  sources:[{title:'Gorpcore, explained',url:'https://www.thecut.com/2017/gorpcore.html'},
           {title:'아크테릭스가 패션이 된 이유',url:'https://www.vogue.co.kr/?p=1'},
           {title:'"><img src=x onerror=alert(1)>',url:'https://evil.example.com/x?a=1&b=2'}] };

const box=document.createElement('div'); box.innerHTML=api.reportHTML(rep);
let fail=0; const ok=(c,m)=>{console.log((c?'  OK  ':'  X!! ')+m); if(!c)fail++;};

console.log('=== 웹 검색 카드 ===');
ok(box.querySelectorAll('.ansBody > div').length===2, `.ansBody 2칸 (실제 ${box.querySelectorAll('.ansBody > div').length})`);
ok(box.textContent.includes('고프코어는 등산'), '웹 답변이 왼쪽에');
ok(box.textContent.includes('우리 지표'), '우리 지표가 오른쪽에');
const rows=[...box.querySelectorAll('[data-href]')];
ok(rows.length===3, `출처 ${rows.length}개`);
ok(rows[0].dataset.href==='https://www.thecut.com/2017/gorpcore.html', 'URL 보존');
ok(box.textContent.includes('thecut.com'), '도메인 표시');
ok(box.querySelectorAll('img,script').length===0, `제목의 주입 태그가 죽었다 (img/script ${box.querySelectorAll('img,script').length})`);
ok(rows[2].textContent.includes('<img'), '주입 시도는 글자로 보인다');

console.log('\n=== 쓰는 클래스가 CSS 에 다 있나 ===');
const cssText=fs.readdirSync('css').map(f=>fs.readFileSync('css/'+f,'utf8')).join('\n');
const declared=new Set(); for(const m of cssText.matchAll(/\.([A-Za-z][A-Za-z0-9_-]*)/g)) declared.add(m[1]);
const used=new Set(); for(const m of box.innerHTML.matchAll(/class="([^"]+)"/g)) m[1].split(/\s+/).forEach(c=>c&&used.add(c));
const miss=[...used].filter(c=>!declared.has(c));
ok(miss.length===0, `사용 ${used.size}개 / 없는 것: ${miss.join(', ')||'없음'}`);

console.log('\n=== 출처 없을 때 ===');
const r2=JSON.parse(JSON.stringify(rep)); r2.web.sources=[];
const b2=document.createElement('div'); b2.innerHTML=api.reportHTML(r2);
ok(b2.textContent.includes('확인된 출처가 없습니다'), '출처 없다고 말한다');
ok(!b2.querySelector('[data-href]'), '빈 링크를 만들지 않는다');

console.log(fail?`\n실패 ${fail}건`:'\n전부 통과');
process.exit(fail?1:0);
