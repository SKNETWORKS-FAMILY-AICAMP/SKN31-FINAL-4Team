import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';

/* ══════════════════════════════════════════════════════
   금주의 리포트 — 문서가 위에서 아래로 한 번에 살아난다.
   섹션 리빌 → 숫자 카운트업 → 트랙/막대/레일 → 스파크라인 드로우 순.
   ══════════════════════════════════════════════════════ */
export function wkAnimate(){
  const root=$('#wkReport'); if(!root)return;
  if(!HAS_A){
    $$('#wkReport [data-w]').forEach(e=>e.style.width=e.dataset.w+'%');
    $$('#wkReport [data-h]').forEach(e=>e.style.height=e.dataset.h+'%');
    $$('#wkReport .wkMetric').forEach(e=>e.style.setProperty('--u','38px'));
    root.classList.add('lit'); return;
  }
  /* ① 섹션이 아래에서 올라온다 */
  const secs=[...root.children];
  aUtils.set(secs,{opacity:0,translateY:18});
  aAnimate(secs,{opacity:[0,1],translateY:[18,0],duration:820,
    delay:aStagger(58),ease:'out(3)'});
  /* ② 점수 트랙 — 채워지고 그 끝에 점이 앉는다 */
  const fill=$('#wkReport .wkTrack .fill'), dot=$('#wkReport .wkTrack .dot');
  if(fill){
    const w=+fill.dataset.w;
    aAnimate(fill,{width:['0%',w+'%'],duration:1250,delay:320,
      ease:aSpring({stiffness:58,damping:17})});
    aAnimate(dot,{left:['0%',w+'%'],opacity:[0,1],duration:1250,delay:320,
      ease:aSpring({stiffness:58,damping:17})});
  }
  /* ③ 지표 카드 하단 밑줄이 좌에서 우로 그어진다 */
  $$('#wkReport .wkMetric').forEach((m,i)=>{
    const o={v:0};
    aAnimate(o,{v:m.classList.contains('hot')?38:22,duration:680,delay:520+i*70,
      ease:'out(3)',onUpdate:()=>m.style.setProperty('--u',o.v.toFixed(1)+'px')});
  });
  /* ④ 요일 막대 · 취향 레일 · 누적 막대 */
  const bars=$$('#wkReport .wkDay .t i');
  if(bars.length)aAnimate(bars,{height:el=>el.dataset.h+'%',duration:900,
    delay:aStagger(64,{start:420}),ease:aSpring({stiffness:66,damping:16})});
  const rails=$$('#wkReport .wkTaste .rail i, #wkReport .wkStack i, #wkReport .wkPeer .bar i');
  if(rails.length)aAnimate(rails,{width:el=>el.dataset.w+'%',duration:980,
    delay:aStagger(70,{start:460}),ease:aSpring({stiffness:62,damping:17})});
  const mark=$('#wkReport .wkPeer .bar u');
  if(mark)aAnimate(mark,{left:['0%',mark.dataset.l+'%'],opacity:[0,1],duration:980,
    delay:520,ease:aSpring({stiffness:62,damping:17})});
  /* ⑥ 광택 · 펄스는 CSS 가 맡는다 — 진입 직후에만 한 번 */
  setTimeout(()=>root.classList.add('lit'),220);
  /* 숫자 카운트업은 trRender 끝에서 한 번만 — 여기서 또 부르면 0 에 멈춘다 */
}

/* 색 보간 — #rrggbb 두 개 사이를 k(0~1) 만큼 섞는다 */
function mixHex(a,b,k){
  const p=h=>[parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];
  const A=p(a),B=p(b);
  const c=A.map((v,i)=>Math.round(v+(B[i]-v)*k));
  return '#'+c.map(v=>v.toString(16).padStart(2,'0')).join('');
}
/* 점수 다이얼 — 링이 차오르고 숫자가 따라 오르는 동안
   색도 가장 낮은 구간에서 시작해 최종 구간까지 걸어 올라간다.
   data-ramp 에 낮은 구간 → 최종 구간 색을 순서대로 넘긴다. */
export function trDial(){
  const ring=$('#trBody .dial .val'), num=$('#trBody .dial .num b');
  if(!ring||!num)return;
  const card=ring.closest('.verdict');
  const sc=+ring.dataset.score, C=314.16, r=Math.max(0,Math.min(100,sc));
  const ramp=(ring.dataset.ramp||'').split(',').filter(Boolean);
  const paint=c=>{ if(card&&c)card.style.setProperty('--sc',c) };
  const at=t=>{
    if(ramp.length<2)return ramp[0]||null;
    const f=Math.max(0,Math.min(1,t))*(ramp.length-1);
    const i=Math.min(ramp.length-2,Math.floor(f));
    return mixHex(ramp[i],ramp[i+1],f-i);
  };
  if(!HAS_A){ ring.style.strokeDashoffset=C*(1-r/100); num.textContent=sc; paint(at(1)); return }
  paint(at(0));
  aAnimate(ring,{strokeDashoffset:[C,C*(1-r/100)],duration:1450,ease:'out(4)'});
  const o={v:0};
  aAnimate(o,{v:sc,duration:1450,ease:'out(4)',
    onUpdate:()=>{ num.textContent=Math.round(o.v); paint(at(sc?o.v/sc:1)) },
    onComplete:()=>paint(at(1))});
}
