import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aTimeline, aUtils, clamp } from '../../../core/static/js/dom.js';
import { buildVisuals } from './visuals.js';
import { exitMain, mainMode } from '../../../app_shell/static/js/router.js';
import { markDive, markRise } from './loader.js';

/* ============================================================
   설명 페이지 — 세로 스크롤을 가로 이동으로
   레퍼런스(shaunscholtz)의 색 테마를 그대로 이어받는다.
   ============================================================ */
/* 구간별 워시 : 니어블랙 → 스틸블루 → 딥틸 → 러스트 → 앰버 → 블랙 */
const WASH=[
  ['#12212b','#0a0a0a'],   /* 01 WHAT IT IS — 화보 패널 */
  ['#f6f8fa','#e9edf1'],   /* 02 COLLECT */
  ['#f6f8fa','#e9edf1'],   /* 03 ANALYZE */
  ['#f4f7f9','#e6ebef'],   /* 04 DECIDE  */
  ['#c8892f','#1a1005'],   /* 05 FOR WHOM — 화보 패널 */
  ['#f6f8fa','#e9edf1']    /* 06 START   */
];
let siteBuilt=false, lenis=null, panels=[], track=null, hstage=null, washLayers=[];
/* 로딩의 검정 → 00 의 흰 지면. 한 번만 서서히 물든다. */
var introLight=0;

export function openSite(){
  /* 화면을 켜는 일과 만드는 일을 나눈다.
     다시보기로 돌아오면 켜는 일만 다시 해야 설명 페이지가 살아난다. */
  document.body.classList.add('loaded');
  $('#site').classList.add('on');
  $('#wash').classList.add('on');
  /* 로딩의 검정에서 00 의 흰 지면으로 서서히 물든다. 다시보기로 와도 매번. */
  if(HAS_A){
    introLight=0;
    const io={k:0};
    aAnimate(io,{k:1,duration:1800,ease:'inOut(2)',
      onUpdate:()=>{ introLight=io.k; renderDeck() }});
  }else{ introLight=1 }
  if(siteBuilt){                       /* 두 번째부터 : 처음 장으로 되감기만 */
    deckI=0; lastPanel=-1; deckPos.v=0;
    if(deckAnim&&deckAnim.pause)deckAnim.pause();
    renderDeck(); onPanelChange(0);
    return;
  }
  siteBuilt=true;

  track=$('#htrack'); hstage=$('#hstage');
  panels=$$('.panel',track);
  deckN=panels.length;                       /* 히어로 + 설명 6장 = 7 */

  /* 설명·비주얼을 한 덩어리(.copy)로 묶어 가운데로 모은다 */
  panels.forEach(pn=>{
    if(pn.classList.contains('hero')||pn.querySelector('.copy'))return;
    const copy=document.createElement('div'); copy.className='copy';
    [...pn.children].forEach(c=>{ if(!c.classList.contains('pbg')&&!c.classList.contains('pvis')
      &&!c.classList.contains('dawn'))copy.appendChild(c) });
    pn.appendChild(copy);
  });

  /* 워시 레이어 */
  const wash=$('#wash');
  washLayers=WASH.map((c,i)=>{
    const el=document.createElement('i');
    el.style.background='radial-gradient(120% 90% at '+(i%2?'78%':'22%')+' '+(i%2?'30%':'68%')+
      ','+c[0]+' 0%,'+c[1]+' 62%,#000 100%)';
    if(i===0)el.style.opacity=1;
    wash.appendChild(el); return el;
  });

  const dots=$('#dots');
  for(let i=0;i<deckN-1;i++){const dd=document.createElement('i');if(!i)dd.classList.add('on');dots.appendChild(dd)}

  buildVisuals();
  renderDeck();
  bindDeck();

  if(HAS_A)aAnimate('.ftr',{opacity:[0,1],duration:700,delay:420,ease:'out(2)'});
}

/* ============================================================
   덱 — 한 번의 스크롤 = 한 페이지. 스프링으로 통통 넘어간다.
   ============================================================ */
var deckN=0, deckI=0, deckPos={v:0}, deckAnim=null, deckLock=false;

export function renderDeck(){
  if(!track)return;
  track.style.transform='translate3d('+(-deckPos.v*innerWidth)+'px,0,0)';
  /* 히어로(0) 이후를 워시 구간에 매핑 */
  const t=clamp((deckPos.v-1)/Math.max(deckN-2,1),0,1);
  const f=t*(WASH.length-1);
  const i=Math.min(WASH.length-2,Math.floor(f)), k=f-i;
  washLayers.forEach((el,n)=>{el.style.opacity = n===i?(1-k):(n===i+1?k:0)});
  /* 06 — 어둠에서 밝음으로 */
  /* 02 · 03 은 밝은 지면이므로 그 장에 들어오면 글자를 잉크색으로 뒤집는다 */
  /* 02 · 03 · 04 · 06 만 밝은 지면 */
  [2,3,4,6].forEach(n=>{ const pn=panels[n];
    if(pn)pn.classList.toggle('brite',Math.abs(deckPos.v-n)<0.52) });
  /* 00 은 흰 지면. 01 로 넘어가면 걷힌다. */
  const hl=$('#heroLight');
  const lv=clamp(1-deckPos.v,0,1)*introLight;
  if(hl)hl.style.opacity=String(lv);
  document.body.classList.toggle('lightHero',lv>0.5);
  const ftr=$('.ftr');
  if(ftr)ftr.classList.toggle('onlight',lv>0.5||[2,3,4,6].indexOf(Math.round(deckPos.v))>=0);
  /* 우상단 바로 시작 — 00(로고) 과 06(이미 시작 버튼이 있는 장) 에서는 감춘다 */
  const jb=$('#jumpBtn');
  if(jb){
    jb.classList.toggle('on',deckPos.v>0.55&&deckPos.v<deckN-1.55);
    jb.classList.toggle('onlight',[2,3,4].indexOf(Math.round(deckPos.v))>=0);
  }
  const dawn=$('#dawn'), last=panels[panels.length-1];
  if(dawn){
    const lit=clamp((deckPos.v-(deckN-2))/1,0,1);
    dawn.style.opacity=String(lit);
    last.classList.toggle('lit',lit>0.55);
  }
}

function goDeck(i){
  i=clamp(i,0,deckN-1);
  if(i===deckI)return;
  const dive=(deckI===0&&i===1);
  deckI=i;
  if(dive)markDive();
  if(i===0)markRise();          /* 되돌아오면 로고가 다시 보여야 한다 */
  if(HAS_A){
    if(deckAnim&&deckAnim.pause)deckAnim.pause();
    /* 살짝 넘어갔다 되돌아오는 스프링 = 통통 튀는 관성 */
    deckAnim=aAnimate(deckPos,{v:i,duration:1150,
      ease:aSpring({stiffness:72,damping:13,mass:1.05}),onUpdate:renderDeck});
  }else{ deckPos.v=i; renderDeck() }
  onPanelChange(i);
}

let lastPanel=-1;
/* 06 — 로고가 뜨고 게이지가 차면 버튼이 올라온다 */
function startSeq(){
  if(!HAS_A)return;
  const m=$('#stMark'), b=$('#stBar'), c=$('#startBtn');
  if(!m)return;
  aUtils.set([m,b,c],{opacity:0});
  aUtils.set(m,{scale:.86,translateY:10});
  aUtils.set('#stBar i',{width:'0%'});
  aUtils.set(c,{scale:.9});
  const t=aTimeline();
  t.add(m,{opacity:[0,1],scale:[.86,1],translateY:[10,0],duration:860,
      ease:aSpring({stiffness:92,damping:14})},120)
   .add(b,{opacity:[0,1],duration:300,ease:'out(2)'},620)
   .add('#stBar i',{width:['0%','100%'],duration:1280,ease:'inOut(2)'},700)
   /* 게이지가 가득 차면 바는 길이를 유지한 채 사라지고, 같은 칸·같은 폭으로 버튼이 피어난다 */
   .add(b,{opacity:[1,0],duration:380,ease:'in(2)'},2020)
   /* 인라인 transform 이 남으면 :hover 의 살짝 뜨는 맛이 죽는다 — 끝나면 비운다 */
   .add(c,{opacity:[0,1],scale:[.9,1],duration:820,
      ease:aSpring({stiffness:104,damping:14}),
      onComplete:()=>{ c.style.transform=''; }},2140);
}

function onPanelChange(i){
  if(i===lastPanel)return; lastPanel=i;
  if(i===6)startSeq();
  $$('#dots i').forEach((dd,n)=>dd.classList.toggle('on',n===Math.max(0,i-1)));
  $('#panelNo').textContent=(i===0?'00':String(i).padStart(2,'0'))+' / '+String(deckN-1).padStart(2,'0');
  const el=panels[i];
  if(HAS_A&&el&&!el.classList.contains('hero')){
    const parts=[$('.no',el),$('h2',el),$('p',el),$('.tags',el)||$('.cta',el)].filter(Boolean);
    if(!parts.length)return;                 /* 06 처럼 문구가 없는 장 */
    aUtils.set(parts,{opacity:0,translateY:26});
    aAnimate(parts,{opacity:[0,1],translateY:[26,0],duration:820,
      ease:'out(3)',delay:aStagger(80,{start:180})});
  }
}

function bindDeck(){
  let acc=0;
  addEventListener('wheel',e=>{
    /* 메인 페이지에 들어가 있으면 브라우저 기본 스크롤에 맡긴다.
       단, 맨 위에서 한 번 더 위로 굴리면 설명 덱으로 되돌아온다. */
    if(mainMode)return;               /* 메인에서는 브라우저 기본 스크롤 */
    e.preventDefault();
    if(deckLock)return;
    acc+=e.deltaY;
    if(Math.abs(acc)<38)return;
    const dir=acc>0?1:-1; acc=0;
    deckLock=true;
    goDeck(deckI+dir);
    setTimeout(()=>{deckLock=false},720);
  },{passive:false});

  addEventListener('keydown',e=>{
    if(mainMode){ if(e.key==='Escape')exitMain(); return; }
    if(deckLock)return;
    const d=(e.key==='ArrowRight'||e.key==='ArrowDown'||e.key==='PageDown')?1:
            (e.key==='ArrowLeft' ||e.key==='ArrowUp'  ||e.key==='PageUp')?-1:0;
    if(!d)return;
    deckLock=true; goDeck(deckI+d);
    setTimeout(()=>{deckLock=false},720);
  });

  let ty=0;
  addEventListener('touchstart',e=>{ty=e.touches[0].clientY},{passive:true});
  addEventListener('touchend',e=>{
    if(deckLock)return;
    const dy=ty-(e.changedTouches[0].clientY);
    if(Math.abs(dy)<46)return;
    deckLock=true; goDeck(deckI+(dy>0?1:-1));
    setTimeout(()=>{deckLock=false},720);
  },{passive:true});

  addEventListener('resize',renderDeck);
  $$('#dots i').forEach((dd,n)=>dd.addEventListener('click',()=>goDeck(n+1)));
}
