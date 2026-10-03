import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';
import { FS, FS_ORDER } from '../../../style/static/js/search.js';
import { gChart } from './chart_engine.js';

/* 화면 안의 모든 차트를 한 번에 세운다 */
export function gMount(){ $$('#trBody [data-chart]').forEach(el=>{
  const cfg=G_CFG[el.dataset.chart]; if(!cfg)return;
  gChart(el,typeof cfg==='function'?cfg(fsItem()):cfg) }) }
export var G_CFG={};

/* 조회 대상 — 걸린 조건 중 가장 구체적인 것 하나.
   아무것도 안 고르면 **빈 문자열**을 준다. 예전처럼 '발레코어' 로 떨어지지 않는다.

   ★ 2026-09-09 — 세부 검색이 단계식에서 축별 필터로 바뀌었다.
     FS.sel[4] 은 없어졌고, FS.pick 이 축 → 고른 값들을 들고 있다.
     FS_ORDER 가 구체적인 것부터의 순서다(아이템명 › 브랜드 › 종류 › 스타일 › 속성).
     한 축에 여러 개를 걸었으면 그중 처음 것을 대표로 삼는다 —
     지표는 말 하나에만 붙기 때문이다. */
export function fsItem(){
  const p=FS.pick||{};
  for(const ax of FS_ORDER){
    const a=p[ax];
    if(a&&a.length)return a[0];
  }
  return '';
}
/* 브랜드와 아이템명이 같이 걸려 있으면 "스투시 8볼 후디" 처럼 붙여 부른다 */
export function fsItemFull(){
  const p=FS.pick||{};
  const b=(p['브랜드']||[])[0], i=(p['아이템명']||[])[0];
  return (b&&i)?(b+' '+i):fsItem();
}
/* 화면 제목은 API가 고른 대표 용어 하나가 아니라 사용자가 고른 조건 전체를 적는다.
   지표 계산의 대표 용어와 검색 범위를 같은 말처럼 보이게 하지 않는다. */
export function fsSelectionLabel(){
  const p=FS.pick||{}, out=[];
  ['스타일','종류','브랜드','아이템명'].concat(FS_ORDER.filter(ax=>
    !['스타일','종류','브랜드','아이템명','카테고리','상품명'].includes(ax)))
    .forEach(ax=>(p[ax]||[]).forEach(v=>{ if(!out.includes(v))out.push(v) }));
  return out.join(' · ');
}
/* 받침 유무로 조사를 고른다 */
export function josa(w,a,b){
  const c=String(w).trim().slice(-1).charCodeAt(0);
  if(c<0xAC00||c>0xD7A3)return a;
  return ((c-0xAC00)%28)?a:b;
}

export function trFillBars(){
  const fl=$$('#trBody .flow i, #trBody .tasteRow i');
  if(HAS_A){ aUtils.set(fl,{width:'0%'});
    aAnimate(fl,{width:el=>el.dataset.w+'%',duration:1050,delay:aStagger(90),
      ease:aSpring({stiffness:64,damping:16})}); }
  else fl.forEach(x=>x.style.width=x.dataset.w+'%');
}
/* ── 키워드 파트 공용 검색 ──────────────────────────────
   할인률 쪽 챗바와 같은 몸통. 다만 세부 검색은 없고,
   사전(FIDX)에 걸리는 말만 통과시켜 연관 키워드를 아래로 깐다.
   세 파트가 입력값을 공유하므로 검색어를 들고 파트를 옮겨 다닐 수 있다. */
/* 살!말? 쪽 showToast 는 그 블록 안에 갇혀 있어 여기서 보이지 않는다.
   같은 #toast 를 쓰는 최상위 헬퍼를 따로 둔다. */
var trToastT;
export function trToast(msg){
  const t=$('#toast'); if(!t)return;
  t.textContent=msg; t.classList.add('on');
  clearTimeout(trToastT);
  trToastT=setTimeout(()=>t.classList.remove('on'),2600);
}
/* ★ 처음 들어오면 비어 있다.
   전에는 '발레코어' 가 기본값이라, 아무것도 검색하지 않았는데 화면에 숫자가
   가득 떠 있었다. 그게 진짜 데이터인 줄 알기 쉽다. 검색해야 나오게 바꿨다. */
export var KW={q:'',f:'',sug:[],cur:-1,part:'temp',asked:{}};


/* ── 검색 전 빈 화면 ────────────────────────────────────────
   왜 두는가: 아무것도 안 물었는데 숫자가 떠 있으면 그게 진짜인 줄 안다.
   무엇을 하면 되는지만 말하고, 값은 하나도 그리지 않는다.

   실존 클래스만 쓴다 — `.note` (trend/static/css/weekly_report.css).
   나머지는 인라인 + 실제 있는 CSS 변수(--line ·--ink ·--coral ·--ease). */
export function trEmpty(what, hint){
  return '<div class="trEmptyWrap" style="display:flex;flex-direction:column;'+
      'align-items:center;justify-content:center;text-align:center;'+
      'min-height:340px;padding:40px 24px">'+
    '<div style="width:46px;height:46px;border-radius:50%;border:1px solid var(--line);'+
        'display:flex;align-items:center;justify-content:center;margin:0 0 18px;'+
        'font-size:19px;opacity:.55">⌕</div>'+
    '<b style="font-size:15.5px;letter-spacing:-.01em">'+esc(what)+'</b>'+
    '<p style="margin:9px 0 0;font-size:13px;line-height:1.75;opacity:.6;'+
        'max-width:380px;white-space:pre-line">'+esc(hint)+'</p>'+
  '</div>';
}

function esc(s){
  return String(s==null?'':s).replace(/[&<>"']/g,m=>(
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
