import { $, $$, HAS_A, aAnimate, aSpring, aTimeline } from '../../../core/static/js/dom.js';
import { FIDX, fsMatch, fsNorm } from '../../../style/static/js/search.js';
import { KW, trToast } from './render_helpers.js';
import { trRender } from './dispatch.js';

/* 예시 질문 — 스타일 룩 · 아이템 위주. 전부 사전에 실제로 있는 말이라 그대로 검색된다. */
const KW_Q={
  temp:[['발레코어','지금 얼마나 뜨거워?'],['스트릿','아직 오르는 중이야?'],
        ['스투시 후디','언제 정점 찍었어?'],['고프코어','어느 플랫폼이 제일 뜨거워?'],
        ['삼바 OG','작년보다 많이 언급돼?']],
  assoc:[['발레코어','뭐랑 같이 언급돼?'],['아메카지','어떤 아이템이 많이 나와?'],
         ['카고 팬츠','같이 입는 게 뭐야?'],['블록코어','새로 붙은 연관어 있어?'],
         ['디트로이트 자켓','어떤 룩으로 소비돼?']],
  sentiment:[['발레코어','사려는 사람 많아?'],['스투시 후디','반응 어때?'],
             ['트랙 자켓','부정 반응은 뭐야?'],['그런지','가격 부담 얘기 많아?'],
             ['발레 플랫','재입고 문의 늘었어?']]
};
/* 할인률 챗바(fsQStep)와 같은 타임라인 — 문구만 파트별로 다르다 */
var kwQI=0, kwQBooked=false;
function kwQStep(){
  const line=$('#kwQ'); if(!line)return;
  const arr=KW_Q[KW.part]||KW_Q.temp;
  const q=arr[kwQI%arr.length]; kwQI++;
  const paint=()=>{ line.innerHTML='<i>“<b>'+q[0]+'</b>&nbsp;'+q[1]+'”</i>' };
  if(!HAS_A){ paint(); return }
  if(!line.firstElementChild){ paint();
    aAnimate(line,{opacity:[0,1],translateY:[8,0],duration:520,ease:'out(3)'}); return }
  const t=aTimeline();
  t.add(line,{opacity:[1,0],translateY:[0,-8],duration:260,ease:'in(2)',onComplete:paint},0)
   .add(line,{opacity:[0,1],translateY:[8,0],duration:520,
      ease:aSpring({stiffness:94,damping:16})},260);
}
function kwQTick(){
  try{ const i=$('#kwInput');
    if(i&&!i.value&&$('#trTabs').classList.contains('kwmode'))kwQStep(); }catch(e){}
  setTimeout(kwQTick,3200);
}
export function kwHideSug(){ const b=$('#kwSug'); if(b){b.hidden=true;b.innerHTML=''} KW.sug=[]; KW.cur=-1 }
function kwPaintSug(){
  const box=$('#kwSug'), inp=$('#kwInput'); if(!box||!inp)return;
  const q=inp.value.trim();
  if(!q){ kwHideSug(); return }
  KW.sug=fsMatch(q,8); KW.cur=KW.sug.length?0:-1;
  if(!KW.sug.length){
    /* 실패로 끝내지 않는다 — 가까운 말을 보여주고, 없으면 등록을 받는다 */
    const n=fsNorm(q);
    let near=FIDX.filter(o=>o.key[0]===n[0]||o.key.indexOf(n.slice(0,1))>=0).slice(0,3);
    const fallback=!near.length;
    if(fallback)near=['발레코어','고프코어','카고 팬츠'].map(x=>({label:x}));
    const done=KW.asked[q];
    box.innerHTML='<div class="kwReq"><p><b>'+q+'</b>… 아직 사전에 없는 말입니다.<br>'+
      '이 검색은 소재 · 아이템 · 스타일 · 브랜드만 다룹니다.</p>'+
      (near.length?'<div class="near"><em>'+(fallback?'많이 찾는 키워드':'혹시 이건가요?')+'</em>'+
        near.map(o=>'<button type="button" data-kw="'+o.label+'">'+o.label+'</button>').join('')+'</div>':'')+
      '<div class="ask"><span>패션 용어가 맞다면 등록을 요청해 주세요. 검토 후 사전에 추가됩니다.</span>'+
      '<button type="button" id="kwAsk"'+(done?' disabled':'')+'>'+
      (done?'요청 완료':'등록 요청')+'</button></div></div>';
    box.hidden=false; return;
  }
  const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const n=fsNorm(q);
  box.innerHTML=KW.sug.map((o,k)=>{
    let lb=esc(o.label); const i=fsNorm(o.label).indexOf(n);
    if(i>=0){ let c=0,s=-1,e=-1;
      for(let p=0;p<o.label.length;p++){ if(!/\s/.test(o.label[p])){ if(c===i)s=p; if(c===i+n.length-1)e=p; c++ } }
      if(s>=0&&e>=s)lb=esc(o.label.slice(0,s))+'<em>'+esc(o.label.slice(s,e+1))+'</em>'+esc(o.label.slice(e+1));
    }
    const path=o.path.filter(Boolean).slice(0,-1).join(' › ');
    return '<button class="sg'+(k===0?' on':'')+'" data-k="'+k+'" type="button">'+
      '<span class="fc">'+o.f+'</span><span class="lb">'+lb+'</span>'+
      (path?'<span class="pt">'+esc(path)+'</span>':'')+'</button>';
  }).join('');
  box.hidden=false;
}
function kwMoveSug(d){
  if(!KW.sug.length)return;
  KW.cur=(KW.cur+d+KW.sug.length)%KW.sug.length;
  $$('#kwSug .sg').forEach((b,i)=>b.classList.toggle('on',i===KW.cur));
}
/* 검색어 확정 → 그 파트를 다시 그린다 */
function kwGo(v){
  const inp=$('#kwInput'); if(!inp)return;
  if(v)inp.value=v;
  const q=inp.value.trim();
  if(!q){ kwPaintSug(); return }
  if(!fsMatch(q,1).length){ kwPaintSug(); return }   /* 사전에 없으면 검색되지 않는다 */
  KW.q=q; kwHideSug(); trRender(KW.part);
}
export function kwWire(part){
  const inp=$('#kwInput'); if(!inp)return;
  KW.part=part;
  const bar=$('#kwBar'), clear=$('#kwClear');
  inp.addEventListener('input',()=>{
    bar.classList.toggle('typing',!!inp.value);   /* 입력 중엔 예시 질문이 비켜난다 */
    clear.hidden=!inp.value;
    kwPaintSug();
  });
  inp.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'){ e.preventDefault(); kwMoveSug(1) }
    else if(e.key==='ArrowUp'){ e.preventDefault(); kwMoveSug(-1) }
    else if(e.key==='Escape'){ kwHideSug() }
    else if(e.key==='Enter'){ e.preventDefault();
      if(KW.cur>=0&&KW.sug[KW.cur])kwGo(KW.sug[KW.cur].label); else kwGo();
    }
  });
  inp.addEventListener('focus',()=>{ if(inp.value)kwPaintSug() });
  $('#kwSug').addEventListener('click',e=>{
    const sg=e.target.closest('.sg');
    if(sg){ kwGo(KW.sug[+sg.dataset.k].label); return }
    const near=e.target.closest('[data-kw]');
    if(near){ kwGo(near.dataset.kw); return }
    const ask=e.target.closest('#kwAsk');
    if(ask&&!ask.disabled){
      KW.asked[inp.value.trim()]=1;
      ask.disabled=true; ask.textContent='요청 완료';
      trToast('“'+inp.value.trim()+'” 등록을 요청했습니다. 검토 후 사전에 추가됩니다.');
    }
  });
  clear.addEventListener('click',()=>{
    inp.value=''; bar.classList.remove('typing');
    clear.hidden=true; kwHideSug(); inp.focus();
  });
  if(!kwQBooked){ kwQBooked=true; kwQStep(); setTimeout(kwQTick,3200) }
}
