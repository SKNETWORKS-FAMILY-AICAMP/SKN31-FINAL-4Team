import { $, $$, HAS_A, aAnimate, aSpring, aTimeline } from '../../../core/static/js/dom.js';
import { prime, primeUrl, sentimentUrl } from './live_data.js';
import { FIDX, fsExact, fsMatch, fsNorm } from '../../../style/static/js/search.js';
import { KW, trToast } from './render_helpers.js';
import { markTried, trRender } from './dispatch.js';
import { KW_HOT, kwHotLoad } from './hot_terms.js';
import { logSearch } from '../../../account/static/js/account_api.js';

/* 할인률 챗바(fsQStep)와 같은 타임라인 — 문구만 HOT 용어다 */
var kwQI=0, kwQBooked=false;
function kwQStep(){
  const line=$('#kwQ'); if(!line)return;
  const job=kwHotLoad();   /* 30분이 지났으면 조용히 다시 읽는다 */
  if(!KW_HOT.length){ job.then(()=>{ if(KW_HOT.length&&!line.querySelector('b'))kwQStep() }); return }
  const q=KW_HOT[kwQI%KW_HOT.length]; kwQI++;
  /* '예 : ' 는 고정하고 용어만 바뀐다 — 첫 용어가 준비됐을 때 한 번만 깐다 */
  let term=line.querySelector('b');
  const first=!term;
  if(first){ line.innerHTML='<i>예 : <b></b></i>'; term=line.querySelector('b') }
  const paint=()=>{ term.textContent=q };
  if(!HAS_A){ paint(); return }
  if(first){ paint();
    aAnimate(term,{opacity:[0,1],translateY:[8,0],duration:520,ease:'out(3)'}); return }
  const t=aTimeline();
  t.add(term,{opacity:[1,0],translateY:[0,-8],duration:260,ease:'in(2)',onComplete:paint},0)
   .add(term,{opacity:[0,1],translateY:[8,0],duration:520,
      ease:aSpring({stiffness:94,damping:16})},260);
}
function kwQTick(){
  try{ const i=$('#kwInput');
    if(i&&!i.value&&$('#trTabs').classList.contains('kwmode'))kwQStep(); }catch(e){}
  setTimeout(kwQTick,3200);
}
/* ══════════════ 최근 검색어 ══════════════
   검색바를 눌렀을 때(아직 아무것도 치지 않았을 때) 최근에 찾아본 말을 보여 준다.
   · 최대 7개. 같은 말을 다시 찾으면 맨 위로 올라온다.
   · 각 줄 오른쪽 × 로 그 한 줄만 지운다.
   · 아래 줄에서 전체 삭제 · 자동저장 끄기/켜기.
   브라우저에만 남는다(localStorage) — 서버로 보내지 않는다. 끄면 그 즉시 지운다. */
const KWH_KEY='feedit.kwHistory.v1';
const KWH_ON_KEY='feedit.kwHistory.on.v1';
const KWH_MAX=7;

function kwHistOn(){
  try{ return localStorage.getItem(KWH_ON_KEY)!=='0' }catch(e){ return false }
}
function kwHistSetOn(on){
  try{
    localStorage.setItem(KWH_ON_KEY, on?'1':'0');
    if(!on){ localStorage.removeItem(KWH_KEY); localStorage.removeItem('feedit.fsHistory.v1'); }   /* 끄면 남은 기록도 함께 지운다 */
  }catch(e){}
}
function kwHistList(){
  if(!kwHistOn())return [];
  try{
    const raw=JSON.parse(localStorage.getItem(KWH_KEY)||'[]');
    return Array.isArray(raw)
      ? raw.filter(x=>x&&x.q).slice(0,KWH_MAX)
      : [];
  }catch(e){ return [] }
}
function kwHistSave(list){
  try{ localStorage.setItem(KWH_KEY, JSON.stringify(list.slice(0,KWH_MAX))) }catch(e){}
}
/* 검색이 실제로 이뤄졌을 때만 남긴다 — 사전에 없어 되돌아간 말은 기록이 아니다 */
function kwHistAdd(q,f){
  if(!kwHistOn()||!q)return;
  const list=kwHistList().filter(x=>x.q!==q);
  list.unshift({q,f:f||'',at:Date.now()});
  kwHistSave(list);
}
function kwHistRemove(q){
  kwHistSave(kwHistList().filter(x=>x.q!==q));
}
function kwHistClear(){ kwHistSave([]) }

const kwEsc=s=>String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

/* 검색바가 비어 있을 때 뜨는 패널. 보여 줄 것이 없으면 false 를 돌려준다. */
function kwPaintHist(){
  const box=$('#kwSug'); if(!box)return false;
  const on=kwHistOn(), list=on?kwHistList():[];
  /* 기록이 꺼져 있고 보여 줄 것도 없으면 패널을 띄우지 않는다 —
     빈 상자가 검색바 아래를 덮고 있으면 방해만 된다.
     다만 '다시 켜기'로 돌아올 길은 있어야 하므로, 꺼 둔 직후에는 안내를 남긴다. */
  if(!on){
    box.innerHTML='<div class="kwHist"><div class="kwHistFoot">'+
      '<span class="kwHistNote">검색 기록을 저장하지 않는 중입니다.</span>'+
      '<button type="button" data-hist-toggle="on">자동저장 켜기</button></div></div>';
    box.hidden=false; return true;
  }
  if(!list.length)return false;
  box.innerHTML='<div class="kwHist">'+
    '<div class="kwHistHead">최근 검색어</div>'+
    list.map(x=>'<div class="kwHistRow">'+
      '<button type="button" class="kwHistGo" data-hist="'+kwEsc(x.q)+'">'+
        (x.f?'<span class="fc">'+kwEsc(x.f)+'</span>':'<span class="fc">검색</span>')+
        '<span class="lb">'+kwEsc(x.q)+'</span>'+
      '</button>'+
      '<button type="button" class="kwHistDel" data-hist-del="'+kwEsc(x.q)+'" '+
        'aria-label="'+kwEsc(x.q)+' 기록 삭제" title="이 기록 삭제">\u00d7</button>'+
    '</div>').join('')+
    '<div class="kwHistFoot">'+
      '<button type="button" data-hist-clear>전체 삭제</button>'+
      '<button type="button" data-hist-toggle="off">자동저장 끄기</button>'+
    '</div></div>';
  box.hidden=false; return true;
}

export function kwHideSug(){ const b=$('#kwSug'); if(b){b.hidden=true;b.innerHTML=''} KW.sug=[]; KW.cur=-1 }
function kwPaintSug(){
  const box=$('#kwSug'), inp=$('#kwInput'); if(!box||!inp)return;
  const q=inp.value.trim();
  /* 아직 아무것도 치지 않았으면 최근 검색어를 보여 준다 */
  if(!q){ KW.sug=[]; KW.cur=-1; if(!kwPaintHist())kwHideSug(); return }
  /* ★ 2026-09-23 — 첫 줄을 미리 골라 두지 않는다. 미리 골라 두면 Enter 가
     친 말이 아니라 그 줄을 집어, '청바지' 를 치고 Enter 하면 연관어 '데님' 이 검색됐다.
     연관어는 드롭다운으로 보여 주되, 잡으려면 ↑↓ 나 클릭으로 직접 골라야 한다. */
  KW.sug=fsMatch(q,8); KW.cur=-1;
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
    /* ★ 예전엔 o.path(스타일 › 종류 › 브랜드)를 뒤에 붙였다.
       세부 검색이 단계식에서 축별 필터로 바뀌면서 FIDX 에서 path 를 뺐다 —
       계층이 없는 사전 항목에는 어차피 없던 값이고, 여기서 읽으면 터진다.
       축 이름(o.f)만으로도 무엇인지는 충분히 읽힌다. */
    return '<button class="sg" data-k="'+k+'" type="button">'+
      '<span class="fc">'+esc(o.f)+'</span><span class="lb">'+lb+'</span></button>';
  }).join('');
  box.hidden=false;
}
function kwMoveSug(d){
  if(!KW.sug.length)return;
  KW.cur=(KW.cur+d+KW.sug.length)%KW.sug.length;
  $$('#kwSug .sg').forEach((b,i)=>b.classList.toggle('on',i===KW.cur));
}
/* 검색어 확정 → 그 파트를 다시 그린다 */
/* 알림(용어 사전 등재)에서 그 용어를 바로 검색할 때 쓴다 — notify.js openTarget (2026-09-19) */
window.feeditKwGo=v=>kwGo(v);
function kwGo(v){
  const inp=$('#kwInput'); if(!inp)return;
  const selected=v&&typeof v==='object'?v:null;
  if(selected)inp.value=selected.label;
  else if(v)inp.value=v;
  /* 값을 코드로 넣은 경우(사전·최근 검색어·알림)에는 input 이벤트가 없다 —
     예시 용어(.fsGhost)가 그 위에 겹치지 않게 입력 중 상태와 × 를 직접 맞춘다 */
  const bar0=$('#kwBar'), clr0=$('#kwClear');
  if(bar0)bar0.classList.toggle('typing',!!inp.value);
  if(clr0)clr0.hidden=!inp.value;
  const typed=inp.value.trim();
  if(!typed){ kwPaintSug(); return }
  /* ★ 2026-09-23 — 친 말 그대로 간다. 연관어로 바꿔치기하지 않는다.
     예전에는 fsMatch 의 첫 줄을 집어서, '청바지' 를 치면 소재 '데님' 이 검색됐다.
     '후보가 하나뿐이면 그것으로' 라는 예외도 뒀다가 뺐다 — '클래식' 을 치면 그 말을 품은
     브랜드 '식스핏 클래식' 이 하나뿐이라 그리로 끌려갔다. 후보가 몇이든 친 말이 아니면 틀린 결과다. */
  const match=selected||fsExact(typed);
  if(!match){ kwPaintSug(); return }   /* 사전에 없으면 검색되지 않는다 — 목록에서 고르면 된다 */
  /* 실제로 조회하는 말은 사전의 대표 이름이다 — 화면·기록·API 가 서로 어긋나지 않게 한다 */
  const q=match.label||typed;
  inp.value=q;
  /* 금주의 리포트용 검색 기록 — 스타일 축이면 취향 지분 계산에도 쓴다 */
  logSearch(q, match.f||'', match.f==='스타일'?q:'');
  /* 이 브라우저의 최근 검색어 (검색바를 누르면 뜬다) */
  kwHistAdd(q, match.f||'');

  /* ★ 지표를 받아 오는 동안 돋보기를 돌린다.
     서버에 다녀오는 시간이 있는데 화면이 그대로면 눌린 줄을 모르고 또 누른다.
     받아 온 뒤에는 trRender 가 다시 그리므로 여기서 끄지 않아도 되지만,
     실패했을 때를 대비해 반드시 되돌린다(finally). */
  kwBusy(true);
  KW.q=q; KW.f=match.f||''; kwHideSug();
  /* 연관어 파트는 /api/assoc 도 새로 받는다 (사람이 직접 눌렀으니 캐시를 무시한다). */
  const assocUrl=KW.part==='assoc'?'/api/assoc?term='+encodeURIComponent(q):null;
  const sentUrl=KW.part==='sentiment'?sentimentUrl(q,KW.f):null;
  const jobs=sentUrl?[primeUrl(sentUrl,{force:true})]:[prime(q,undefined,{force:true})];
  if(assocUrl)jobs.push(primeUrl(assocUrl,{force:true}));
  Promise.all(jobs.map(j=>Promise.resolve(j).catch(()=>{}))).then(()=>{
    /* 내가 방금 물어봤다 — 이어서 도는 trRender 는 또 묻지 마라. */
    markTried(q); if(assocUrl)markTried(assocUrl); if(sentUrl)markTried(sentUrl);
    kwBusy(false);
    trRender(KW.part);
  });
}

/* 챗바를 '조회 중' 모양으로 바꾼다. CSS 가 회전을 맡는다. */
function kwBusy(on){
  const bar=$('#kwBar'), btn=$('#kwGoBtn');
  if(bar)bar.classList.toggle('busy',!!on);
  if(btn)btn.disabled=!!on;
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
  /* Enter 로 할 일 — 키를 눌렀을 때와 한글 조합이 끝난 뒤가 똑같아야 한다 */
  const kwEnterGo=()=>{
    if(KW.cur>=0&&KW.sug[KW.cur])kwGo(KW.sug[KW.cur]); else kwGo();
  };
  /* ★ 2026-09-23 — 한글을 치는 중의 Enter.
     '가을' 의 마지막 글자는 Enter 를 누르는 그 순간까지 **조합 중**이다. 그 상태에서
     검색하고 입력칸을 비우면, 브라우저가 조합을 끝내면서 그 글자를 빈 칸에 다시 써 넣는다 —
     검색은 됐는데 칸에는 '을' 만 남는다('나이키' → '키'). 영문은 조합이 없어 멀쩡했다.
     조합 중에 들어온 Enter 는 여기서 멈추고, compositionend 가 이어서 처리한다. */
  let kwEnterPending=false;
  inp.addEventListener('compositionend',()=>{
    if(!kwEnterPending)return;
    kwEnterPending=false;
    kwEnterGo();
  });
  inp.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'){ e.preventDefault(); kwMoveSug(1) }
    else if(e.key==='ArrowUp'){ e.preventDefault(); kwMoveSug(-1) }
    else if(e.key==='Escape'){ kwHideSug() }
    else if(e.key==='Enter'){ e.preventDefault();
      if(e.isComposing||e.keyCode===229){ kwEnterPending=true; return }
      kwEnterGo();
    }
  });
  /* 검색바를 누르면 — 친 글자가 있으면 연관어, 비어 있으면 최근 검색어 */
  inp.addEventListener('focus',()=>{ kwPaintSug() });
  $('#kwSug').addEventListener('click',e=>{
    /* ── 최근 검색어 ── */
    const del=e.target.closest('[data-hist-del]');
    if(del){ kwHistRemove(del.dataset.histDel); if(!kwPaintHist())kwHideSug(); return }
    const clr=e.target.closest('[data-hist-clear]');
    if(clr){ kwHistClear(); if(!kwPaintHist())kwHideSug(); return }
    const tg=e.target.closest('[data-hist-toggle]');
    if(tg){ kwHistSetOn(tg.dataset.histToggle==='on'); if(!kwPaintHist())kwHideSug(); return }
    const hg=e.target.closest('[data-hist]');
    if(hg){ kwGo(hg.dataset.hist); return }
    const sg=e.target.closest('.sg');
    if(sg){ kwGo(KW.sug[+sg.dataset.k]); return }
    const near=e.target.closest('[data-kw]');
    if(near){ kwGo(near.dataset.kw); return }
    const ask=e.target.closest('#kwAsk');
    if(ask&&!ask.disabled){
      KW.asked[inp.value.trim()]=1;
      ask.disabled=true; ask.textContent='요청 완료';
      trToast('“'+inp.value.trim()+'” 등록을 요청했습니다. 검토 후 사전에 추가됩니다.');
    }
  });
  const go=$('#kwGoBtn');
  if(go)go.addEventListener('click',()=>{ if(!go.disabled)kwGo() });
  clear.addEventListener('click',()=>{
    inp.value=''; bar.classList.remove('typing');
    /* 비우면 연관어 대신 최근 검색어가 그 자리에 선다 */
    clear.hidden=true; kwPaintSug(); inp.focus();
  });
  /* ★ 탭을 바꾸면 trTabsRender 가 챗바를 통째로 새로 그린다.
     그러면 #kwQ 도 새 요소라 비어 있는데, 예전엔 kwQBooked 가 이미 true 라
     아무것도 안 그리고 **다음 3.2초 틱까지 빈칸**이었다. 그 사이 사용자는
     "예시 질문이 없어졌다"고 본다.
     그래서 **그릴 때마다 한 번은 바로 찍고**, 타이머만 한 번 건다. */
  if(!inp.value) kwQStep();
  if(!kwQBooked){ kwQBooked=true; setTimeout(kwQTick,3200) }
}
