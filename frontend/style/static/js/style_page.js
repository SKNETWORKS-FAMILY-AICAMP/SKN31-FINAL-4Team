import { $, $$, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';
import { IMG, INF_NAMES, ITEM_BRANDS, STYLES } from '../../../home/static/js/chat.js';

/* ── Style ──────────────────────────────────────────── */
export var stShowI=0, stItemPage=0, stCur=null;
/* 스타일 사진 — 전용 컷(ph)이 있으면 그걸 쓰고, 없으면 공용 라이브러리로 떨어진다 */
export const SIMG=s=>s.ph||IMG(s.img);
export function stBuild(){
  $('#stCats').innerHTML=STYLES.map((s,i)=>
    '<button class="stCat'+(i?'':' on')+'" data-style="'+s.id+'">'+s.n+'</button>').join('');
  const six=STYLES.slice(0,6);
  $('#stShow').innerHTML=six.map((s,i)=>
    '<div class="sl'+(i?'':' on')+'" data-style="'+s.id+'"><img src="'+SIMG(s)+'" alt="'+s.n+'">'+
    '<div class="vg"></div><div class="cap"><em>'+s.en.toUpperCase()+' · '+s.pk+'</em>'+
    '<b>'+s.n+'</b><span>'+s.kw.join(' · ')+'</span></div></div>').join('')+
    '<div class="dots">'+six.map((s,i)=>'<i'+(i?'':' class="on"')+'></i>').join('')+'</div>';
  /* 코어와 원형을 한 그리드 안에서 층으로 갈라 보여 준다 */
  const tile=s=>'<div class="stTile" data-style="'+s.id+'">'+
    '<img src="'+SIMG(s)+'" alt="'+s.n+'" loading="lazy">'+
    '<b>'+s.n+'</b><span class="stEn">'+s.en+'</span></div>';
  const band=(t,n,d)=>'<div class="stBand"><b>'+t+'</b><em>'+n+'</em><span>'+d+'</span></div>';
  const core=STYLES.filter(s=>s.g==='코어'), root=STYLES.filter(s=>s.g==='원형');
  $('#stGrid').innerHTML=
    band('코어',core.length+'종','지금 이름이 붙어 도는 흐름')+core.map(tile).join('')+
    band('원형',root.length+'종','코어들이 갈라져 나온 뿌리')+root.map(tile).join('');
  setInterval(()=>{
    const sl=$$('#stShow .sl'), dt=$$('#stShow .dots i');
    if(!sl.length)return;
    sl[stShowI%sl.length].classList.remove('on'); dt[stShowI%dt.length].classList.remove('on');
    stShowI++;
    sl[stShowI%sl.length].classList.add('on'); dt[stShowI%dt.length].classList.add('on');
  },3400);
  $('#stBack').addEventListener('click',()=>{
    $('#styleDetail').style.display='none'; $('#styleHome').style.display=''; scrollTo(0,0) });
}
function stKeepAll(text,kwList){
  let t=text;
  kwList.forEach(k=>{ if(k.indexOf(' ')>-1) t=t.split(k).join(k.replace(/ /g,'\u00A0')); });
  return t;
}
function stSentences(text){
  return text.split(/(?<=[.!?])\s+/).map(t=>t.trim()).filter(Boolean).join('<br>');
}
export function stOpen(id){
  const s=STYLES.find(x=>x.id===id)||STYLES[0];
  stCur=s; stItemPage=0;
  $('#styleHome').style.display='none'; $('#styleDetail').style.display='';
  $$('#stCats .stCat').forEach(b=>b.classList.toggle('on',b.dataset.style===id));
  $('#stHero').innerHTML='<img src="'+SIMG(s)+'" alt="'+s.n+'"><div class="vg"></div>'+
    '<div class="in"><em>'+s.en.toUpperCase()+'</em><h2>'+s.n+'</h2><div class="mt">'+
    '<div><b>'+s.st+'</b><span>시작</span></div>'+
    '<div><b>'+s.kw.length+'</b><span>핵심 키워드</span></div></div></div>';
  $('#stAbout').innerHTML=
    '<div><h3>이 스타일은 어떻게 시작됐나</h3><p>'+stSentences(stKeepAll(s.ab+' '+s.ab2,s.kw))+'</p></div>'+
    '<dl><div><dt>시작</dt><dd>'+s.st+'</dd></div>'+
    '<div><dt>확산 계기</dt><dd>'+s.by+'</dd></div>'+
    '<div><dt>핵심 키워드</dt><dd>'+s.kw.join(' · ')+'</dd></div></dl>';
  $('#stInf').innerHTML=INF_NAMES.slice(0,5).map((n,i)=>
    '<div class="infC"><div class="im"><img src="'+IMG(((s.img+i*3)%35)+1)+'" alt="" loading="lazy"></div>'+
    '<div class="bd"><span class="av">'+n[1].toUpperCase()+'</span>'+
    '<span><b>'+n+'</b><span>'+(12+i*7)+'.'+(i%9)+'k 팔로워</span></span></div></div>').join('');
  $('#stItems').innerHTML=''; stMoreItems(); stMoreItems();
  if(HAS_A)aAnimate('#stHero .in',{opacity:[0,1],translateY:[22,0],duration:900,ease:'out(3)'});
  scrollTo(0,0);
}
export function stMoreItems(){
  const host=$('#stItems'); if(!host||!stCur)return;
  const s=stCur, add=[];
  for(let i=0;i<8;i++){
    const k=stItemPage*8+i;
    add.push('<div class="itC"><div class="im"></div><div class="bd">'+
      '<em>'+ITEM_BRANDS[k%ITEM_BRANDS.length]+'</em>'+
      '<b>'+s.kw[(k+1)%s.kw.length]+'</b>'+
      '<span>'+(39+((k*17)%46))+'9,000원</span></div></div>');
  }
  stItemPage++;
  const frag=document.createElement('div'); frag.innerHTML=add.join('');
  const els=[...frag.children]; els.forEach(e=>host.appendChild(e));
  $('#stItemCount').textContent=host.children.length+' ITEMS';
  if(HAS_A)aAnimate(els,{opacity:[0,1],translateY:[18,0],duration:760,delay:aStagger(50),ease:'out(3)'});
}
