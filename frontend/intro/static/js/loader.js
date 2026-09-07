import { $, $$, A, HAS_A, aAnimate, aSpring, aStagger, aTimeline, aUtils, clamp } from '../../../core/static/js/dom.js';
import { openSite } from './deck.js';

/* ============================================================
   시대별 트렌드 이미지 매니페스트
   ------------------------------------------------------------
   ※ 새 사진을 올려주시면 아래 imgs 경로만 갈아끼우면 됩니다.
     (지금은 기존 assets/f01~f19.jpg 를 시대별로 나눠 임시 배치)
   from : 해당 시대가 시작되는 연·월  ·  tag : 슬롯 아래 라벨
   ============================================================ */
const ERAS=[
  {from:[2000,0],  tag:'Y2K · LOW RISE',        imgs:['assets/f02.jpg','assets/f11.jpg','assets/f16.jpg','assets/f22.jpg','assets/f34.jpg']},
  {from:[2005,0],  tag:'INDIE SLEAZE · SKINNY', imgs:['assets/f04.jpg','assets/f13.jpg','assets/f18.jpg','assets/f26.jpg','assets/f29.jpg']},
  {from:[2010,0],  tag:'NORMCORE · MINIMAL',    imgs:['assets/f06.jpg','assets/f09.jpg','assets/f15.jpg','assets/f23.jpg','assets/f32.jpg']},
  {from:[2015,0],  tag:'STREET · ATHLEISURE',   imgs:['assets/f05.jpg','assets/f12.jpg','assets/f17.jpg','assets/f20.jpg','assets/f35.jpg']},
  {from:[2020,0],  tag:'GORPCORE · Y2K REVIVAL',imgs:['assets/f03.jpg','assets/f08.jpg','assets/f14.jpg','assets/f28.jpg','assets/f31.jpg']},
  {from:[2024,0],  tag:'AMEKAJI · OLD MONEY',   imgs:['assets/f01.jpg','assets/f07.jpg','assets/f10.jpg','assets/f19.jpg','assets/f21.jpg','assets/f25.jpg','assets/f27.jpg','assets/f30.jpg','assets/f33.jpg']}
];
const MONTHS=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
const START=[2000,0], END=[2026,7];                       /* 2000 Jan → 2026 Aug */
const TOTAL_M=(END[0]-START[0])*12+(END[1]-START[1]);     /* = 320 개월 */

/* 모든 이미지를 순서대로 펼쳐 슬롯에 심는다 */
const ALL=[];
ERAS.forEach((e,ei)=>e.imgs.forEach(src=>ALL.push({src,ei})));

export const slot=$('#slot');
const gY=$('#gY'), gM=$('#gM'), gRail=$('#gRail');
const stage=$('#stage');

ALL.forEach(o=>{
  const im=document.createElement('img');
  im.src=o.src; im.alt=''; im.decoding='async';
  slot.appendChild(im); o.el=im;
});

/* ---------- 커서 ---------- */
(function cursor(){
  const dot=$('#cur'), ring=$('#curRing');
  if(!dot||!window.matchMedia||!matchMedia('(hover:hover) and (pointer:fine)').matches){
    if(dot)dot.style.display='none'; if(ring)ring.style.display='none'; return;
  }
  let mx=innerWidth/2,my=innerHeight/2,rx=mx,ry=my;
  addEventListener('mousemove',e=>{mx=e.clientX;my=e.clientY});
  (function l(){requestAnimationFrame(l);
    rx+=(mx-rx)*.16; ry+=(my-ry)*.16;
    dot.style.transform='translate3d('+mx+'px,'+my+'px,0)';
    ring.style.transform='translate3d('+rx+'px,'+ry+'px,0)';
  })();
})();

/* ============================================================
   시퀀스
   ============================================================ */
export const GAP_W=()=>Math.min(innerWidth*0.30,420);   /* 벌어졌을 때 슬롯 너비 */
/* D 는 글자 폭이 넓어 슬롯에 걸치므로 왼쪽을 더 많이 밀어낸다 */
const PAD_L=28, PAD_R=14;
const SPREAD=6600;                               /* 트렌드가 바뀌는 구간 길이 */
/* 등속이면 단조로우므로 시간 → 진행률을 가속 곡선으로 매핑한다.
   1 = 등속, 값이 클수록 초반이 더 느리고 후반이 더 빨라진다.
   의미도 맞아떨어진다 — 2000년대 초반은 천천히 흐르고
   최근으로 올수록 트렌드 주기가 짧아져 정신없이 갈아치워진다. */
const ACCEL=1.9;
const accel=t=>Math.pow(t,ACCEL);
export let running=false, skipped=false, tl=null;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

function setYear(p){
  const m=Math.round(p*TOTAL_M);
  const y=START[0]+Math.floor(m/12), mo=m%12;
  gY.textContent=String(y);
  gM.textContent=MONTHS[mo];
  gRail.style.width=(p*100).toFixed(2)+'%';
  /* 연·월에 해당하는 시대 인덱스 (라벨은 표시하지 않고 내부 계산용) */
  let idx=0;
  ERAS.forEach((e,i)=>{ if(y>e.from[0]||(y===e.from[0]&&mo>=e.from[1]))idx=i });
  return idx;
}

function showShot(i){
  ALL.forEach((o,k)=>o.el.classList.toggle('on',k===i));
}

/* 텍스트를 한 글자씩 span 으로 — .half .ch 스타일이 이미 이 구조를 전제한다 */
function splitChars(el){
  if(!el)return;
  const t=(el.textContent||'').trim();
  el.textContent='';
  for(const c of t){
    const sp=document.createElement('span');
    sp.className='ch'; sp.setAttribute('data-char','');
    sp.textContent=c; el.appendChild(sp);
  }
}
async function run(){
  if(running)return; running=true; skipped=false;
  const halfL=$('#halfL'), halfR=$('#halfR');

  /* 초기화 */
  aUtils&&aUtils.set([halfL,halfR],{translateX:0,opacity:1});
  aUtils&&aUtils.set(slot,{width:0});
  aUtils&&aUtils.set('#gauge',{opacity:1});
  aUtils&&aUtils.set(stage,{opacity:1,scale:1,filter:'blur(0px)'});
  setYear(0); showShot(-1);

  /* 글자 단위 분해 (한 번만) — 직접 쪼갠다.
     라이브러리(splitText)는 폰트/레이아웃 상태에 따라 첫 실행에서 실패하는데
     그 예외가 catch 에 삼켜지면 chars 가 0 이 되어 로고가 통째로 사라진다. */
  if(!halfL.dataset.split){
    splitChars(halfL); splitChars(halfR);
    halfL.dataset.split='1';
  }
  const chars=$$('#halfL [data-char], #halfR [data-char]');
  /* 코랄은 소문자 i 의 점 하나에만. 점 없는 ı 로 바꾸고 그 위에 사각을 얹는다. */
  const rchars=$$('#halfR [data-char]');
  if(rchars.length===2&&!rchars[0].dataset.dot){
    rchars[0].dataset.dot='1'; rchars[0].textContent='ı';
    rchars[0].classList.add('dotI');
    rchars[0].insertAdjacentHTML('beforeend','<span class="tit"></span>');
  }

  /* 지난 회차가 남긴 변형을 완전히 지운다.
     finish() 가 글자에 scale(.72) 를, markDive() 가 마크에 opacity 0 을 남기므로
     지우지 않으면 다시보기에서 글자 크기가 어긋난 채로 다시 뜬다. */
  if(HAS_A){
    const idB=$$('#idSym .fr, #idSym .fl, #idSym .dt'), idC=[], ms=$('#markStage');
    A.utils.remove&&A.utils.remove([...chars,...idB,...idC,ms,$('#idLock')]);
    if(chars.length)aUtils.set(chars,{opacity:1,scale:1,translateY:0,filter:'blur(0px)'});
    aUtils.set(ms,{opacity:0,translateY:0});
    if(idB.length)aUtils.set(idB,{opacity:1,scale:1,translateY:0,transformOrigin:'50% 50%'});
    if(idC.length)aUtils.set(idC,{opacity:1,translateY:0});
    aUtils.set('#idLock',{scale:1});
    delete ms.dataset.dove;
  }

  if(!HAS_A){                                   /* anime 없으면 정적 완성형 */
    slot.style.width=GAP_W()+'px'; showShot(ALL.length-1); setYear(1);
    return finish();
  }

  /* ① 워드마크 등장 */
  if(chars.length){
    aUtils.set(chars,{opacity:0,translateY:46,filter:'blur(12px)'});
    aAnimate(chars,{opacity:[0,1],translateY:[46,0],filter:['blur(12px)','blur(0px)'],
      duration:820,ease:'out(4)',delay:aStagger(52)});
  }
  await sleep(1050); if(skipped)return;

  /* ② FEED 와 IT 사이가 벌어지고, 이음매가 그어진다
       D 의 글자 폭 때문에 왼쪽이 사진에 걸치므로 좌우로 한 번 더 밀어 여백을 준다 */
  const w=GAP_W();
  aAnimate(slot,{width:[0,w],duration:900,ease:aSpring({stiffness:64,damping:15})});
  aAnimate(halfL,{translateX:[0,-PAD_L],duration:900,ease:aSpring({stiffness:64,damping:15})});
  aAnimate(halfR,{translateX:[0, PAD_R],duration:900,ease:aSpring({stiffness:64,damping:15})});
  await sleep(300); if(skipped)return;

  /* ③ 연대가 흐르며 트렌드가 갈아끼워진다 */
  const t0=performance.now();
  let last=-1;
  await new Promise(res=>{
    (function tick(){
      if(skipped)return res();
      const raw=clamp((performance.now()-t0)/SPREAD,0,1);
      const p=accel(raw);                       /* 천천히 시작해 점점 빨라진다 */
      setYear(p);
      const idx=Math.min(ALL.length-1,Math.floor(p*ALL.length));
      if(idx!==last){
        last=idx; showShot(idx);
        /* 빨라질수록 반동이 세지고 짧아져서 가속이 눈에 보이게 */
        const punch=0.018+0.055*raw;
        aAnimate(slot,{scaleY:[1+punch,1],
          duration:300-150*raw, ease:'out(3)'});
      }
      if(raw>=1)return res();
      requestAnimationFrame(tick);
    })();
  });
  if(skipped)return;

  /* ④ 최후에 합쳐진다 — 벌려뒀던 여백도 같이 되돌린다 */
  aAnimate(slot,{width:[w,0],duration:640,ease:'inOut(3)'});
  aAnimate(halfL,{translateX:[-PAD_L,0],duration:640,ease:'inOut(3)'});
  aAnimate(halfR,{translateX:[ PAD_R,0],duration:640,ease:'inOut(3)'});
  aAnimate([halfL,halfR],{
    keyframes:[{scale:1.02,duration:220,ease:'out(2)'},
               {scale:1,duration:420,ease:aSpring({stiffness:150,damping:11})}]
  });
  await sleep(1000); if(skipped)return;

  await sleep(700);
  finish();
}

function finish(){
  running=false;
  if(!HAS_A){ stage.style.opacity=0; $('#gauge').style.opacity=0; openSite(); return }

  const halfL=$('#halfL'), halfR=$('#halfR');
  const chars=$$('#halfL [data-char], #halfR [data-char]');   /* F E E D | I T */
  const ms=$('#markStage');

  const t=aTimeline();
  /* 게이지부터 정리 */
  t.add('#gauge',{opacity:[1,0],translateY:[0,14],duration:520,ease:'in(2)'},0);

  /* ① 워드마크는 글자를 남기지 않고 통째로 물러난다.
       일부 글자만 남길 이유가 없다 — 뒤이어 나오는 로고가 따로 있기 때문. */
  if(chars.length){
    t.add(chars,{opacity:[1,0],translateY:[0,-18],duration:520,
        ease:'in(2)',delay:aStagger(46)},140);
  }
  t.add(stage,{opacity:[1,0],duration:460,ease:'in(2)'},420);

  /* ③ 로고 조립 — 세 줄이 중심에서 바깥으로 펼쳐지고, 워드마크가 아래에서 올라온다 */
  t.add(ms,{opacity:[0,1],duration:460,ease:'out(2)'},760);
  const idFr=$('#idSym .fr'), idFl=$$('#idSym .fl'), idDt=$('#idSym .dt');
  aUtils.set(idFr,{opacity:0,scale:.84,transformOrigin:'50% 50%'});
  aUtils.set(idFl,{opacity:0,translateY:5});
  aUtils.set(idDt,{opacity:0,scale:.2,transformOrigin:'86px 34px'});
  t.add(idFr,{opacity:[0,1],scale:[.84,1],duration:1000,
      ease:aSpring({stiffness:66,damping:15,mass:1.05})},820)
   .add(idFl,{opacity:[0,1],translateY:[5,0],duration:760,delay:aStagger(80),
      ease:'out(3)'},1120)
   .add(idDt,{opacity:[0,1],scale:[.2,1],duration:760,
      ease:aSpring({stiffness:150,damping:11})},1400)
   /* 자리잡는 순간의 미세한 반동 */
   .add('#idLock',{keyframes:[{scale:1.028,duration:190,ease:'out(2)'},
      {scale:1,duration:560,ease:aSpring({stiffness:150,damping:11})}]},1760);

  /* ④ 잠시 머문 뒤 설명 페이지를 뒤에 깔아둔다. 마크는 가운데 그대로. */
  t.call(()=>{ openSite(); },3200)
   .add('#again',{opacity:[0,1],duration:500,ease:'out(2)',
      onBegin:()=>$('#again').classList.add('on')},3400);
}

/* 로고 화면으로 되돌아올 때 — 마크가 조용히 다시 내려앉는다 */
export function markRise(){
  const ms=$('#markStage');
  if(!ms||!ms.dataset.dove)return;
  delete ms.dataset.dove;
  if(HAS_A)aAnimate(ms,{opacity:[0,1],translateY:[-26,0],duration:760,
    ease:aSpring({stiffness:76,damping:16})});
  else ms.style.opacity=1;
}

/* 첫 페이지로 넘어갈 때 — 로고 마크만 조용히 물러난다 */
export function markDive(){
  const ms=$('#markStage');
  if(!ms||ms.dataset.dove)return;
  ms.dataset.dove='1';
  if(HAS_A)aAnimate(ms,{opacity:[1,0],translateY:[0,-26],duration:620,ease:'in(2)'});
  else ms.style.opacity=0;
}

function skip(){
  if(!running)return;
  skipped=true; running=false;
  const halfL=$('#halfL'), halfR=$('#halfR');
  const chars=$$('#halfL [data-char], #halfR [data-char]');
  if(HAS_A&&A.utils.remove){
    /* 글자까지 포함해 진행 중인 것을 전부 끊는다.
       빼먹으면 스킵 뒤에도 이전 동작이 계속 돌아 화면이 어긋난다. */
    A.utils.remove([slot,stage,halfL,halfR,...chars]);
  }
  setYear(1); showShot(ALL.length-1);
  slot.style.width='0px';
  if(HAS_A){
    aUtils.set([halfL,halfR],{translateX:0,scale:1,opacity:1});
    if(chars.length)aUtils.set(chars,{opacity:1,scale:1,translateY:0,filter:'blur(0px)'});
    aUtils.set(stage,{opacity:1,scale:1,filter:'blur(0px)'});
  }else{
    halfL.style.transform=''; halfR.style.transform='';
  }
  finish();
}
$('#skip').addEventListener('click',skip);
addEventListener('keydown',e=>{if(e.key==='Escape'||e.key===' ')skip()});
$('#again').addEventListener('click',()=>{
  /* 로딩을 다시 보려면 설명 페이지를 접고 처음 상태로 되돌린다 */
  const back=()=>{
    scrollTo(0,0);
    document.body.classList.remove('loaded');
    $('#site').classList.remove('on');
    $('#wash').classList.remove('on');
    $('#again').classList.remove('on');
        run();
  };
  if(HAS_A)aAnimate('#again',{opacity:[1,0],duration:320,ease:'in(2)',onComplete:back});
  else back();
});

/* 이미지 + 폰트 프리로드 후 시작
   (Syne 이 늦게 오면 글자 분할 폭이 어긋나므로 폰트를 먼저 기다린다) */
(function boot(){
  let n=0, done=false;
  const start=()=>{
    const f=(document.fonts&&document.fonts.ready)?document.fonts.ready:Promise.resolve();
    f.then(run,run);
  };
  const go=()=>{if(!done){done=true;start()}};
  ALL.forEach(o=>{
    if(o.el.complete)  { if(++n>=ALL.length)go() }
    else { o.el.onload=o.el.onerror=()=>{ if(++n>=ALL.length)go() } }
  });
  setTimeout(go,2600);
})();
