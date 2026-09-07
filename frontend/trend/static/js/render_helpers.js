import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';
import { FS } from '../../../style/static/js/search.js';
import { gChart } from './chart_engine.js';

/* 화면 안의 모든 차트를 한 번에 세운다 */
export function gMount(){ $$('#trBody [data-chart]').forEach(el=>{
  const cfg=G_CFG[el.dataset.chart]; if(!cfg)return;
  gChart(el,typeof cfg==='function'?cfg(fsItem()):cfg) }) }
export var G_CFG={};

/* 조회 대상 — 검색으로 좁힌 것 중 가장 구체적인 것 */
export function fsItem(){
  return FS.sel[3]||FS.sel[2]||FS.sel[1]||FS.mat||FS.sel[0]||'발레코어';
}
export function fsItemFull(){
  const b=FS.sel[2], i=FS.sel[3];
  return (b&&i)?(b+' '+i):fsItem();
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
export var KW={q:'발레코어',sug:[],cur:-1,part:'temp',asked:{}};
