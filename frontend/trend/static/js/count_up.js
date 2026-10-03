import { $$, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';

/* ══════════════════════════════════════════════════════
   숫자 카운트업 — 화면에 뜬 수치가 0 에서 제 값까지 굴러 올라간다.
   문자열 안의 숫자만 골라 자리를 지키며 바꾸므로
   "412,000 → 362,500원", "+3%p", "D-9", "×0.82" 같은 표기가 그대로 유지된다.
   ══════════════════════════════════════════════════════ */
const CU_SEL=[
  '.kpi b','.vdMeta b','.mTable .n','.tasteRow .tr b','.tasteRow .tr em',
  '.bigStat b','.pbars .pv','.wkTop h3 em','.cheapest s','.axChg',
  '.pItem .tg','.pItem s','.mfStat b',
  '.tpBigDeg','.tpDelta','.tpSignalNum','.tpSignalList span','.tpBriefScore','.tpLogicChip',
  '.tpReasonLine span:last-child','.pricep','.voteCard .cap',
  /* .smBar i 는 여기서 뺀다 — 카운트업이 매 프레임 innerHTML 을 다시 써서
     ① 폭 애니메이션과 부딪혀 뚝뚝 끊기고 ② 안에 넣어 둔 <span> 라벨이 지워졌다.
     숫자는 막대가 차오르며 드러나는 것으로 충분하다. */
  '.wkLine h2 em','.wkScoreMain strong','.wkLedger b','.wkMetric strong','.wkMetric em',
  '.wkDay .v','.wkTaste b','.wkTaste em','.wkLegend b','.wkTable .up','.wkTable .dn',
  '.wkMeta span:last-child','.wkPeer p b',
  '.svIdx b','.svIdx em','.svPrice b',   /* 찜한 키워드 */
  '.concl .vRow .meta span:last-child'   /* 앞 칸은 날짜라 굴리지 않는다 */
].map(s=>'#trBody '+s).join(', ');
const CU_RE=/(\d[\d,]*(?:\.\d+)?)/g;
function cuFmt(v,spec){
  let s=spec.dec?v.toFixed(spec.dec):String(Math.round(v));
  if(!spec.comma)return s;
  const p=s.split('.');
  return (+p[0]).toLocaleString('en-US')+(p[1]?'.'+p[1]:'');
}
/* 카운트업이 도는 동안 표·줄이 안 출렁이게 폭을 잠근다. items 는 {el} 배열 —
   되돌리는 함수(undo)를 돌려준다. tests/count_up_layout.test.mjs 가 이 함수를
   실제 브라우저(playwright)에 그려 픽셀로 잰다 — jsdom 은 레이아웃 엔진이
   없어 이 버그(찌그러짐) 자체를 못 잡는다.

   ★ 셀 하나에 min-width 를 걸어도 안 잠긴다 — auto 표 레이아웃은 그 열의
     "선호 폭" 만 키운 뒤 남는 폭을 다른 열에 비율대로 나눠 준다. 숫자가
     줄면 그 칸이 오히려 넓어져 보이는 게 이거다(2026-09-02 실측: 숫자칸
     62.7px → 181.3px). 열 전체를, 그것도 굴리지 않는 행까지 포함해 width 로
     못박아야 열이 안 움직인다.
   ★ 인라인 요소(<b><em>)는 애초에 min-width 가 안 먹는다(CSS2.1 §10.4) —
     inline-block 으로 바꾼 뒤에만 잠긴다(같은 실측: KPI 28.9px → 14.5px). */
export function lockWidths(items){
  const lockedCols=new Map();     /* table → 이미 폭을 잠근 열 index 집합 */
  const restores=[];
  /* .tpPulseGrid(내 취향 브리핑 카드 두 개)는 fr 트랙 — 여기서 JS 로 폭을
     재던 시도(2026-09)는 측정 시점이 진입 애니메이션과 겹치면 오히려
     한쪽 트랙이 0에 가깝게 잡혀 다른 쪽이 뷰포트 밖으로 밀려나는 더 큰
     문제를 냈다. 원인 자체(fr 트랙의 자동 최소 크기가 내용의 min-content를
     따라가는 것)는 my_feed.css 의 grid-template-columns 를
     minmax(0,1.18fr) minmax(0,.82fr) 로 선언해 CSS 단에서 막아뒀다 —
     내용이 몇이든 트랙 비율이 항상 고정되므로 여기서는 더 손댈 게 없다. */
  items.forEach(({el})=>{
    const td=el.closest('td,th');
    if(td){
      const table=td.closest('table');
      const idx=td.cellIndex;
      if(!table||idx<0)return;
      let set=lockedCols.get(table);
      if(!set){ set=new Set(); lockedCols.set(table,set); }
      if(set.has(idx))return;
      set.add(idx);
      $$('tr',table).forEach(tr=>{
        const cell=tr.children[idx]; if(!cell)return;
        const w=cell.getBoundingClientRect().width;
        if(!w)return;
        const prev=cell.style.width;
        cell.style.width=w+'px';
        restores.push(()=>{ cell.style.width=prev; });
      });
      return;
    }
    const disp=getComputedStyle(el).display;
    const r=el.getBoundingClientRect();
    if(!r||!r.width)return;
    if(disp==='inline'){
      const prevDisp=el.style.display, prevMin=el.style.minWidth;
      el.style.display='inline-block';
      el.style.minWidth=r.width+'px';
      restores.push(()=>{ el.style.display=prevDisp; el.style.minWidth=prevMin; });
    }else{
      const prevMin=el.style.minWidth;
      el.style.minWidth=r.width+'px';
      restores.push(()=>{ el.style.minWidth=prevMin; });
    }
  });
  return ()=>restores.forEach(fn=>fn());
}
/* ★ 2026-09-19 — 앞선 카운트업이 도는 중에 다시 불리면, 굴러가던 중간값(0 에 가까운 수)을
   원래 값으로 오해해 그 자리에서 멈춰 버렸다(요일별 활동 숫자가 0 으로 굳던 버그).
   그래서 새로 시작하기 전에 돌고 있던 것을 제 값으로 끝맺어 둔다. */
let cuRun=null;
function cuFinish(){ if(cuRun){ const fn=cuRun; cuRun=null; fn(); } }
export function trCountUp(){
  if(!HAS_A)return;
  cuFinish();
  const items=[];
  $$(CU_SEL).forEach(el=>{
    if(el.closest('.dial'))return;                 /* 다이얼은 따로 돈다 */
    /* 캡처 그룹으로 쪼개면 홀수 자리가 곧 숫자다 — 자리표시자가 필요 없다 */
    const parts=el.innerHTML.split(CU_RE);
    if(parts.length<2)return;
    const nums=[];
    for(let i=1;i<parts.length;i+=2){
      const m=parts[i], dot=m.indexOf('.');
      nums.push({i:i,v:parseFloat(m.replace(/,/g,'')),
                 comma:m.indexOf(',')>=0,
                 dec:dot>=0?m.length-dot-1:0});
    }
    if(!nums.length)return;
    items.push({el,parts:parts.slice(),nums});
  });
  if(!items.length)return;
  const undo=lockWidths(items);
  const paint=(it,t)=>{
    const p=it.parts.slice();
    it.nums.forEach(n=>{ p[n.i]=cuFmt(n.v*t,n) });
    it.el.innerHTML=p.join('');
  };
  items.forEach(it=>paint(it,0));
  const px=items.map(()=>({t:0}));
  const done=()=>{ items.forEach(it=>paint(it,1)); undo(); };
  const anim=aAnimate(px,{t:1,duration:1000,delay:aStagger(38),ease:'out(3)',
    onUpdate:()=>items.forEach((it,i)=>paint(it,px[i].t)),
    onComplete:()=>{ cuRun=null; done(); }});
  cuRun=()=>{ try{ anim&&anim.pause&&anim.pause() }catch(e){} done(); };
}
