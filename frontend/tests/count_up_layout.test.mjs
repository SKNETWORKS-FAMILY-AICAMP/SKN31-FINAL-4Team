/* 카운트업이 도는 1초 동안 레이아웃이 흔들리지 않는가.
 *
 * 왜 jsdom 이 아닌가 — jsdom 에는 레이아웃 엔진이 없다.
 *   getBoundingClientRect() 가 전부 0 을 돌려주므로 '찌그러짐' 자체를 잴 수 없다.
 *   이 버그는 표 자동 레이아웃과 인라인 요소의 min-width 규칙에서 나왔고,
 *   둘 다 실제 렌더러가 있어야 재현된다. 그래서 여기만 playwright 를 쓴다.
 *
 * 돌리는 법:  npx playwright install chromium  후  node tests/count_up_layout.test.mjs
 * playwright 가 없으면 조용히 건너뛴다 — 다른 검증까지 막지 않는다.
 *
 * 이 테스트가 잡는 것 (2026-09-02 에 실제로 잡았다, 폭 360px 기준)
 *   · 표 셀에 min-width 를 걸면 자동 레이아웃이 그 열에 남는 폭까지 얹어 준다
 *     → 숫자칸 62.7px → 181.3px, 막대칸 130.2px → 74.2px 로 찌그러졌다
 *   · min-width 는 인라인 요소에 걸리지 않는다 (CSS 2.1 §10.4)
 *     → <b> 로 둔 KPI 숫자는 잠근 셈 쳤지만 28.9px → 14.5px 로 줄었다
 */
let chromium;
try{ ({ chromium } = await import('playwright')) }
catch(e){ console.log('· playwright 없음 — 건너뜀'); process.exit(0) }

import fs from 'node:fs';
import path from 'node:path';
const SRC = path.resolve(import.meta.dirname, '../trend/static/js/count_up.js');
const body = fs.readFileSync(SRC,'utf8');
/* 폭 잠금 함수와 실제 DOM 조회 도우미를 함께 브라우저에 넣는다. */
const domBody = fs.readFileSync(path.resolve(import.meta.dirname, '../core/static/js/dom.js'), 'utf8');
const queryAll = domBody.split('\n').find(line => line.startsWith('export const $$=')).replace('export ', '');
const lock = body.slice(body.indexOf('export function lockWidths'),
                        body.indexOf('export function trCountUp'))
                 .replace('export function','function');

const PAGE = `<!doctype html><meta charset=utf-8><style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:sans-serif}.wrap{width:360px}
.mTable{width:100%;border-collapse:collapse;font-size:12.5px}
.mTable th:last-child,.mTable td:last-child{text-align:right;padding-right:0}
.mTable td{padding:11px 10px 11px 0}
.mTable .bar{position:relative;height:5px;border-radius:99px;background:#eee;min-width:60px}
.kpi b{font-size:26px}
.tpBrief{display:grid;grid-template-columns:auto 1fr auto;gap:18px;align-items:center}
.tpBriefScore b{font-size:20px}
</style><div class=wrap>
<table class="mTable">
<tr><th>신호</th><th></th><th>건수</th></tr>
<tr><td>가격 만족</td><td><span class="bar" style="display:block"><i></i></span></td><td class="n">1,240</td></tr>
<tr><td>사이즈 불만</td><td><span class="bar" style="display:block"><i></i></span></td><td class="n">512</td></tr>
<tr><td>배송</td><td><span class="bar" style="display:block"><i></i></span></td><td class="n">88</td></tr>
</table>
<div class="kpi"><span>온도</span><b>86</b></div>
<div class="tpBrief"><div>01</div><div class="tpBriefText"><b>브리핑</b></div>
  <div class="tpBriefScore"><b>86</b>점</div></div>
</div><script type="module">
${queryAll}
${lock}
window.__run = () => {
  const els=[...document.querySelectorAll('.mTable .n'),
             document.querySelector('.kpi b'), document.querySelector('.tpBriefScore b')];
  const g=e=>+e.getBoundingClientRect().width.toFixed(1);
  const row=document.querySelectorAll('.mTable tr')[1];
  const snap=()=>({name:g(row.children[0]), bar:g(row.querySelector('.bar')),
                   num:g(row.children[2]), kpi:g(document.querySelector('.kpi b')),
                   score:g(document.querySelector('.tpBriefScore'))});
  const orig=els.map(e=>e.textContent);
  const final=snap();
  const undo=lockWidths(els.map(el=>({el})));
  els.forEach(e=>e.textContent='0');           /* 카운트업 첫 프레임 */
  const atZero=snap();
  els.forEach((e,i)=>e.textContent=orig[i]);
  undo();
  return {final, atZero, atEnd:snap()};
};
</script>`;

const b = await chromium.launch();
const p = await (await b.newContext()).newPage();
await p.setContent(PAGE);
await p.waitForFunction(()=>window.__run);
const r = await p.evaluate(()=>window.__run());
await b.close();

let fail = 0;
const TOL = 1.5;                    /* 서브픽셀 반올림까지만 봐준다 */
for (const k of Object.keys(r.final)) {
  const d0 = Math.abs(r.atZero[k]  - r.final[k]);
  const d1 = Math.abs(r.atEnd[k]   - r.final[k]);
  const ok = d0 <= TOL && d1 <= TOL;
  if (!ok) fail++;
  console.log(`  ${ok?'OK ':'X!!'} ${k.padEnd(6)} 최종 ${r.final[k]} · 0일 때 ${r.atZero[k]} · 끝난 뒤 ${r.atEnd[k]}`);
}
console.log(fail ? `\n실패 ${fail}건 — 카운트업 중에 레이아웃이 움직인다` : '\n전부 통과');
process.exit(fail ? 1 : 0);
