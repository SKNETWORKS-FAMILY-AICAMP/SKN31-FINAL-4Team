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
  '.svFill b','.svRest','.svIdx b','.svIdx em','.svPrice b',   /* 찜한 키워드 */
  '.concl .vRow .meta span:last-child'   /* 앞 칸은 날짜라 굴리지 않는다 */
].map(s=>'#trBody '+s).join(', ');
const CU_RE=/(\d[\d,]*(?:\.\d+)?)/g;
function cuFmt(v,spec){
  let s=spec.dec?v.toFixed(spec.dec):String(Math.round(v));
  if(!spec.comma)return s;
  const p=s.split('.');
  return (+p[0]).toLocaleString('en-US')+(p[1]?'.'+p[1]:'');
}
export function trCountUp(){
  if(!HAS_A)return;
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
    const r=el.getBoundingClientRect();
    if(r&&r.width)el.style.minWidth=r.width+'px';  /* 자릿수가 변해도 안 출렁이게 */
    items.push({el,parts:parts.slice(),nums});
  });
  if(!items.length)return;
  const paint=(it,t)=>{
    const p=it.parts.slice();
    it.nums.forEach(n=>{ p[n.i]=cuFmt(n.v*t,n) });
    it.el.innerHTML=p.join('');
  };
  items.forEach(it=>paint(it,0));
  const px=items.map(()=>({t:0}));
  aAnimate(px,{t:1,duration:1000,delay:aStagger(38),ease:'out(3)',
    onUpdate:()=>items.forEach((it,i)=>paint(it,px[i].t)),
    onComplete:()=>items.forEach(it=>{ paint(it,1); it.el.style.minWidth='' })});
}
