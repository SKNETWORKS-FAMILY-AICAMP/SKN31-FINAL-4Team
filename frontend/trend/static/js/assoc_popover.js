import { $, $$ } from '../../../core/static/js/dom.js';

export function assocOpenPop(triggerEl,cat,item){
  $$('#trBody .axList .axRow').forEach(t=>t.classList.remove('on'));
  triggerEl.classList.add('on');
  const pop=$('#assocPop');
  $('#apWord').textContent=item.n; $('#apCat').textContent=cat;
  const pts=item.spark, max=Math.max.apply(null,pts), min=Math.min.apply(null,pts), span=(max-min)||1;
  const xs=[10,73,136,190];
  const coords=pts.map((v,i)=>xs[i]+','+(40-((v-min)/span)*32).toFixed(1));
  $('#apSparkLine').setAttribute('points',coords.join(' '));
  $('#apSrc').innerHTML=item.src.map(s=>
    '<div class="apSrcItem"><span class="apSrcTag">'+s.tag+'</span><span class="apSrcText">'+s.text+'</span></div>'
  ).join('');
  pop.classList.add('on');
  const r=triggerEl.getBoundingClientRect();
  const pw=pop.offsetWidth||272, ph=pop.offsetHeight||180;
  const vw=window.innerWidth, vh=window.innerHeight, pad=10;
  let left=r.left, top=r.bottom+8;
  if(left+pw>vw-pad) left=vw-pad-pw;
  if(left<pad) left=pad;
  if(top+ph>vh-pad) top=r.top-ph-8;
  pop.style.left=left+'px'; pop.style.top=top+'px';
}
export function assocClosePop(){
  $('#assocPop').classList.remove('on');
  $$('#trBody .axList .axRow').forEach(t=>t.classList.remove('on'));
}
$('#apClose').addEventListener('click',assocClosePop);
document.addEventListener('click',e=>{
  const pop=$('#assocPop');
  if(!pop.classList.contains('on'))return;
  if(e.target.closest('#assocPop')||e.target.closest('.axList .axRow'))return;
  assocClosePop();
});
document.addEventListener('keydown',e=>{ if(e.key==='Escape') assocClosePop(); });
window.addEventListener('resize',()=>{ if($('#assocPop').classList.contains('on')) assocClosePop(); });
