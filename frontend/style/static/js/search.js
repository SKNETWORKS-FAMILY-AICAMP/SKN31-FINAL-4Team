import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aTimeline } from '../../../core/static/js/dom.js';
import { kwHideSug } from '../../../trend/static/js/saved_keywords.js';
import { trRender } from '../../../trend/static/js/dispatch.js';

/* ══════════════════════════════════════════════════════
   패션 특화 검색 — 종합 검색이 아니다.
   어휘 트리에 걸리는 말만 통과시키고, 나머지는 실패시킨다.
   색인(태깅)과 질의가 같은 어휘를 쓰기 때문에 별도 차단 목록이 필요 없다.
   구조 : Style › 종류 › 브랜드 › 아이템명
   ══════════════════════════════════════════════════════ */
const FTREE={
  '스트릿':{
    '후디'    :{'스투시':['베이직 아치 로고 후디','8볼 후디'],
                '디스이즈네버댓':['아크 로고 후디'],'슈프림':['박스 로고 후디']},
    '크롭티'  :{'아더에러':['크롭 저지 탑'],'널디':['시그니처 크롭 티']},
    '카고 팬츠':{'디스이즈네버댓':['나일론 카고 팬츠'],'스투시':['빈티지 카고']},
    '스니커'  :{'나이키':['덩크 로우','에어포스 1'],'아디다스':['삼바 OG','가젤']}
  },
  '아메카지':{
    '워크 자켓':{'칼하트':['디트로이트 자켓','액티브 자켓'],'폴로 랄프로렌':['치노 워크 자켓']},
    '치노'    :{'폴로 랄프로렌':['클래식 핏 치노'],'유니클로':['와이드 치노']},
    '카라티'  :{'폴로 랄프로렌':['클래식 피케 셔츠'],'유니클로':['드라이 피케 폴로']},
    '데님'    :{'리바이스':['501 오리지널','505 레귤러'],'오어슬로우':['107 아이비 핏']}
  },
  '그런지':{
    '플란넬 셔츠':{'유니클로':['플란넬 체크 셔츠'],'아더에러':['오버사이즈 플란넬']},
    '니트'    :{'아더에러':['디스트로이드 니트'],'무신사 스탠다드':['루즈핏 크루넥']},
    '와이드 데님':{'리바이스':['배기 데드스탁'],'오어슬로우':['1950 와이드']},
    '부츠'    :{'닥터마틴':['1460 8홀','제이든 첼시']}
  },
  '포멀':{
    '셔츠'    :{'무신사 스탠다드':['옥스퍼드 셔츠'],'폴로 랄프로렌':['커스텀 핏 포플린']},
    '테일러드 자켓':{'무신사 스탠다드':['셋업 블레이저'],'아더에러':['언스트럭처드 블레이저']},
    '슬랙스'  :{'무신사 스탠다드':['테이퍼드 슬랙스'],'유니클로':['스마트 앵클 팬츠']},
    '로퍼'    :{'닥터마틴':['에이드리언 태슬'],'폴로 랄프로렌':['페니 로퍼']}
  },
  '발레코어':{
    '크롭티'  :{'미우미우':['리본 크롭 캐미솔'],'널디':['새틴 크롭 탑']},
    '랩 스커트':{'미우미우':['새틴 랩 스커트'],'아더에러':['튤 레이어 스커트']},
    '플랫 슈즈':{'미우미우':['발레 플랫'],'레페토':['상드리용']},
    '가디건'  :{'유니클로':['크롭 볼레로'],'미우미우':['리본 크롭 가디건']}
  },
  '고프코어':{
    '테크 셸' :{'아크테릭스':['베타 LT','감마 SL'],'노스페이스':['마운틴 자켓']},
    '플리스'  :{'파타고니아':['레트로-X'],'노스페이스':['데날리']},
    '트레일 러너':{'살로몬':['XT-6','스피드크로스'],'호카':['스피드고트']},
    '카고 팬츠':{'아크테릭스':['감마 팬츠'],'파타고니아':['백컨트리 팬츠']}
  },
  '블록코어':{
    '저지'    :{'아디다스':['빈티지 트레포일 저지'],'나이키':['레트로 풋볼 저지']},
    '트랙 자켓':{'아디다스':['비컨스 트랙탑'],'나이키':['윈드러너']},
    '스니커'  :{'아디다스':['삼바 OG','스페자'],'뉴발란스':['550']}
  },
  '놈코어':{
    '무지 티' :{'무신사 스탠다드':['베이직 크루넥'],'유니클로':['에어리즘 코튼 T']},
    '치노'    :{'유니클로':['슬림핏 치노'],'무신사 스탠다드':['와이드 치노']},
    '스니커'  :{'뉴발란스':['992','990v6'],'아디다스':['스탠스미스']},
    '플리스 집업':{'파타고니아':['신칠라 스냅-T'],'유니클로':['플러피 플리스']}
  }
};
/* 소재는 트리와 직교한다 — 어느 가지에서도 붙을 수 있어 별도 축으로 둔다 */
const FMAT=['새틴','튤','데님','코튼','린넨','캐시미어','울','플리스','고어텍스','나일론',
            '코듀로이','스웨이드','가죽','메쉬','저지','벨벳','트위드','시어서커'];
/* 오타·다른 이름으로 치는 경우가 실패의 대부분이다 */
const FALIAS={
  '아메토라':'아메카지','ametora':'아메카지','스트릿웨어':'스트릿','스트리트':'스트릿',
  '발레코':'발레코어','고프':'고프코어','블로크코어':'블록코어','블로크':'블록코어',
  '노멀코어':'놈코어','비즈니스캐주얼':'포멀','오피스룩':'포멀',
  '맨투맨':'후디','스웨트셔츠':'후디','후드티':'후디','후드':'후디',
  '반팔':'무지 티','폴로티':'카라티','피케셔츠':'카라티','카라 티셔츠':'카라티',
  '조거':'카고 팬츠','청바지':'데님','진':'데님',
  '스투시':'스투시','stussy':'스투시','carhartt':'칼하트','arcteryx':'아크테릭스',
  'salomon':'살로몬','nike':'나이키','adidas':'아디다스','miumiu':'미우미우',
  '뉴발':'뉴발란스','뉴발란스':'뉴발란스','노페':'노스페이스','파타':'파타고니아'
};

/* 트리를 한 줄짜리 항목들로 펼쳐 둔다. 검색은 전부 이 배열 위에서 일어난다. */
export const FIDX=(function(){
  const out=[], push=(f,label,path)=>out.push({f,label,path,key:label.replace(/\s/g,'').toLowerCase()});
  FMAT.forEach(m=>push('소재',m,[]));
  Object.keys(FTREE).forEach(st=>{
    push('스타일',st,[st]);
    Object.keys(FTREE[st]).forEach(kd=>{
      if(!out.some(o=>o.f==='종류'&&o.label===kd))push('종류',kd,[null,kd]);
      Object.keys(FTREE[st][kd]).forEach(br=>{
        if(!out.some(o=>o.f==='브랜드'&&o.label===br))push('브랜드',br,[null,null,br]);
        FTREE[st][kd][br].forEach(it=>push('아이템',it,[st,kd,br,it]));
      });
    });
  });
  return out;
})();
const FLV=['스타일','종류','브랜드','아이템'];

export function fsNorm(s){ return String(s||'').replace(/\s/g,'').toLowerCase() }
/* 어휘 해석 — 별칭까지 본다. 여기서 못 걸리면 그 말은 패션어가 아니다. */
export function fsMatch(q,limit){
  const n=fsNorm(q); if(!n)return [];
  const al=FALIAS[q.trim()]||FALIAS[n]; const an=al?fsNorm(al):null;
  const hit=[];
  FIDX.forEach(o=>{
    let i=o.key.indexOf(n);
    if(i<0&&an)i=o.key.indexOf(fsNorm(an));
    if(i<0)return;
    /* 앞에서 걸릴수록, 짧을수록 위로 */
    hit.push({o,rank:i*100+o.label.length+(o.f==='아이템'?20:0)});
  });
  if(!hit.length&&/\s/.test(q.trim())){
    /* "스투시 후디" 같은 조합어 — 통째로는 없어도 토큰은 사전에 있다 */
    const seen={};
    q.trim().split(/\s+/).forEach((tk,ti)=>{
      if(fsNorm(tk).length<2)return;
      fsMatch(tk,4).forEach((o,k)=>{
        if(seen[o.label])return; seen[o.label]=1;
        hit.push({o,rank:1000+ti*100+k});
      });
    });
  }
  hit.sort((a,b)=>a.rank-b.rank);
  /* 같은 아이템이 여러 스타일 밑에 걸려 있어 이름이 두 번 나올 수 있다 — 한 번만 보여준다 */
  const seenLb={}, out=[];
  for(const h of hit){
    if(seenLb[h.o.f+'|'+h.o.label])continue;
    seenLb[h.o.f+'|'+h.o.label]=1; out.push(h.o);
    if(out.length>=(limit||8))break;
  }
  return out;
}
/* 항목 하나를 팝업 선택 상태로 바꾼다 (부분 검색 → 팝업 인계에 쓰인다) */
function fsPathOf(o){
  if(o.f==='소재')return {mat:o.label,sel:[null,null,null,null]};
  if(o.f==='스타일')return {sel:[o.label,null,null,null]};
  if(o.f==='종류'){
    const st=Object.keys(FTREE).find(s=>FTREE[s][o.label]);
    return {sel:[st||null,o.label,null,null]};
  }
  if(o.f==='브랜드'){
    for(const st of Object.keys(FTREE))for(const kd of Object.keys(FTREE[st]))
      if(FTREE[st][kd][o.label])return {sel:[st,kd,o.label,null]};
    return {sel:[null,null,o.label,null]};
  }
  return {sel:o.path.slice()};
}

/* ── 상태 ── */
export var FS={sel:[null,null,null,null],mat:null,sug:[],cur:-1,open:false,id:null};
const FS_Q=[
  ['고프코어 테크 셸','할인률 언제부터 올랐어?'],
  ['살로몬 XT-6','리세일 시세 아직 버텨?'],
  ['새틴','수명주기 어디쯤이야?'],
  ['스투시 후디','지금 사도 되는 시점이야?'],
  ['삼바','정점 지났어?']
];
var fsQI=0, fsQBooked=false;

function fsQStep(){
  const line=$('#fsQ'); if(!line)return;
  const q=FS_Q[fsQI%FS_Q.length]; fsQI++;
  const paint=()=>{ line.innerHTML='<i>“<b>'+q[0]+'</b>&nbsp;'+q[1]+'”</i>' };
  if(!HAS_A){ paint(); return }
  if(!line.firstElementChild){ paint();
    aAnimate(line,{opacity:[0,1],translateY:[8,0],duration:520,ease:'out(3)'}); return }
  const t=aTimeline();
  t.add(line,{opacity:[1,0],translateY:[0,-8],duration:260,ease:'in(2)',onComplete:paint},0)
   .add(line,{opacity:[0,1],translateY:[8,0],duration:520,
      ease:aSpring({stiffness:94,damping:16})},260);
}
function fsQTick(){
  try{ const i=$('#fsInput'), w=$('#trSearch');
    if(i&&!i.value&&w&&!w.hidden)fsQStep(); }catch(e){}
  setTimeout(fsQTick,3200);
}

/* ── 연관 검색어 ── */
function fsPaintSug(){
  const box=$('#fsSug'), q=$('#fsInput').value.trim();
  if(!box)return;
  if(!q){ box.hidden=true; box.innerHTML=''; FS.sug=[]; FS.cur=-1; return }
  FS.sug=fsMatch(q,8); FS.cur=FS.sug.length?0:-1;
  if(!FS.sug.length){
    const near=FIDX.filter(o=>o.key[0]===fsNorm(q)[0]).slice(0,3);
    box.innerHTML='<div class="none">패션 어휘로 인식하지 못했습니다.<br>'+
      '이 검색은 소재 · 아이템 · 스타일 · 브랜드만 다룹니다.'+
      (near.length?'<br><br>혹시 <b>'+near.map(o=>o.label).join('</b>, <b>')+'</b> 인가요?':'')+'</div>';
    box.hidden=false; return;
  }
  const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const n=fsNorm(q);
  box.innerHTML=FS.sug.map((o,k)=>{
    /* 친 글자만 코랄로 — 어디가 걸렸는지 보이게 */
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
function fsMoveSug(d){
  if(!FS.sug.length)return;
  FS.cur=(FS.cur+d+FS.sug.length)%FS.sug.length;
  $$('#fsSug .sg').forEach((b,i)=>b.classList.toggle('on',i===FS.cur));
  const el=$$('#fsSug .sg')[FS.cur]; if(el&&el.scrollIntoView)el.scrollIntoView({block:'nearest'});
}
export function fsHideSug(){ const b=$('#fsSug'); if(b){b.hidden=true;b.innerHTML=''} FS.sug=[]; FS.cur=-1 }

/* 어휘 하나를 확정 — 완전히 짚은 것은 바로 반영, 덜 짚은 것은 팝업으로 넘긴다 */
function fsPick(o,fromKey){
  const p=fsPathOf(o);
  if(p.mat)FS.mat=p.mat; else FS.sel=p.sel;
  $('#fsInput').value=''; $('#fsBar').classList.remove('typing');
  $('#fsClear').hidden=true; fsHideSug();
  /* 아이템명까지 특정됐으면 그대로 분석, 아니면 남은 단계를 팝업에서 고르게 한다 */
  if(o.f==='아이템'||o.f==='소재'){ fsApply(); }
  else fsOpenPop();
}

/* ── 세부 검색 팝업 ── */
function fsOpenPop(){
  FS.open=true; $('#fsPopBg').classList.add('on'); $('#fsMore').classList.add('on');
  fsPaintPop();
}
function fsClosePop(){ FS.open=false; $('#fsPopBg').classList.remove('on'); $('#fsMore').classList.remove('on') }
function fsOpts(lv){
  const [st,kd,br]=FS.sel;
  if(lv===0)return Object.keys(FTREE);
  if(lv===1)return st?Object.keys(FTREE[st]||{}):[];
  if(lv===2)return (st&&kd)?Object.keys((FTREE[st]||{})[kd]||{}):[];
  return (st&&kd&&br)?(((FTREE[st]||{})[kd]||{})[br]||[]):[];
}
function fsPaintPop(){
  for(let lv=0;lv<4;lv++){
    const host=$('#fsC'+lv); if(!host)continue;
    const opts=fsOpts(lv);
    if(!opts.length){
      host.innerHTML='<div class="hint">'+
        (lv===1?'STYLE 을 먼저 고르세요.':lv===2?'종류를 먼저 고르세요.':'브랜드를 먼저 고르세요.')+'</div>';
      continue;
    }
    host.innerHTML=opts.map(o=>{
      const cnt = lv===0?Object.keys(FTREE[o]).length
                : lv===1?Object.keys(FTREE[FS.sel[0]][o]).length
                : lv===2?FTREE[FS.sel[0]][FS.sel[1]][o].length : 0;
      return '<button type="button" data-lv="'+lv+'" data-v="'+o+'"'+
        (FS.sel[lv]===o?' class="on"':'')+'>'+o+(cnt?'<i>'+cnt+'</i>':'')+'</button>';
    }).join('');
  }
  const chips=[];
  if(FS.mat)chips.push(['소재',FS.mat,'mat']);
  FS.sel.forEach((v,i)=>{ if(v)chips.push([FLV[i],v,i]) });
  $('#fsPicked').innerHTML=chips.length
    ? chips.map(c=>'<span class="fsChip"><small>'+c[0]+'</small>'+c[1]+
        '<button type="button" data-drop="'+c[2]+'">×</button></span>').join('')
    : '<span class="ph2">아직 고른 조건이 없습니다.</span>';
}
function fsDrop(k){
  if(k==='mat'){ FS.mat=null; return }
  const lv=+k; for(let i=lv;i<4;i++)FS.sel[i]=null;   /* 아래 단계는 같이 풀린다 */
}
function fsChipsPaint(){
  const box=$('#fsChips'); if(!box)return;
  const chips=[];
  if(FS.mat)chips.push(['소재',FS.mat,'mat']);
  FS.sel.forEach((v,i)=>{ if(v)chips.push([FLV[i],v,i]) });
  if(!chips.length){ box.hidden=true; box.innerHTML=''; return }
  box.innerHTML=chips.map(c=>'<span class="fsChip"><small>'+c[0]+'</small>'+c[1]+
    '<button type="button" data-drop="'+c[2]+'">×</button></span>').join('');
  box.hidden=false;
}
/* 조건을 화면에 반영 — 목업이므로 헤더 문구와 칩으로 결과를 보여준다 */
function fsApply(){
  fsClosePop(); fsChipsPaint();
  const chips=[]; if(FS.mat)chips.push(FS.mat);
  FS.sel.forEach(v=>{ if(v)chips.push(v) });
  const d=$('#trDesc'); if(!d)return;
  if(!chips.length){ trRender(FS.id||'life'); return }
  trRender(FS.id||'life');
  fsChipsPaint();
  d.textContent=chips.join(' · ')+' 조건으로 좁혀 분석했습니다. '+
    '조건을 빼면 그만큼 범위가 다시 넓어집니다.';
  if(HAS_A)aAnimate('#fsChips .fsChip',{opacity:[0,1],translateY:[8,0],
    duration:520,delay:aStagger(60),ease:'out(3)'});
}

export function fsBuild(){
  const inp=$('#fsInput'), bar=$('#fsBar'); if(!inp)return;
  inp.addEventListener('input',()=>{
    bar.classList.toggle('typing',!!inp.value);
    $('#fsClear').hidden=!inp.value;
    fsPaintSug();
  });
  inp.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'){ e.preventDefault(); fsMoveSug(1) }
    else if(e.key==='ArrowUp'){ e.preventDefault(); fsMoveSug(-1) }
    else if(e.key==='Escape'){ fsHideSug() }
    else if(e.key==='Enter'){
      e.preventDefault();
      if(FS.cur>=0&&FS.sug[FS.cur]){ fsPick(FS.sug[FS.cur],true); return }
      /* 고른 것 없이 엔터 — 가장 가까운 어휘를 잡아 팝업으로 넘긴다 */
      const m=fsMatch(inp.value,1)[0];
      if(m)fsPick(m,true);
      else { fsPaintSug(); }
    }
  });
  $('#fsSug').addEventListener('click',e=>{
    const b=e.target.closest('.sg'); if(!b)return;
    fsPick(FS.sug[+b.dataset.k]);
  });
  $('#fsClear').addEventListener('click',()=>{
    inp.value=''; bar.classList.remove('typing'); $('#fsClear').hidden=true; fsHideSug(); inp.focus();
  });
  $('#fsMore').addEventListener('click',()=>{ FS.open?fsClosePop():fsOpenPop() });
  $('#fsChips').addEventListener('click',e=>{
    const b=e.target.closest('[data-drop]'); if(!b)return;
    fsDrop(b.dataset.drop); fsApply();
  });
  $('.fsCols').addEventListener('click',e=>{
    const b=e.target.closest('button[data-lv]'); if(!b)return;
    const lv=+b.dataset.lv, v=b.dataset.v;
    if(FS.sel[lv]===v)fsDrop(lv); else { FS.sel[lv]=v; for(let i=lv+1;i<4;i++)FS.sel[i]=null }
    fsPaintPop();
  });
  $('#fsPicked').addEventListener('click',e=>{
    const b=e.target.closest('[data-drop]'); if(!b)return;
    fsDrop(b.dataset.drop); fsPaintPop();
  });
  $('#fsReset').addEventListener('click',()=>{ FS.sel=[null,null,null,null]; FS.mat=null; fsPaintPop() });
  $('#fsApply').addEventListener('click',fsApply);
  $('#fsPopX').addEventListener('click',fsClosePop);
  $('#fsPopBg').addEventListener('click',e=>{ if(e.target===$('#fsPopBg'))fsClosePop() });
  document.addEventListener('keydown',e=>{ if(e.key==='Escape'&&FS.open)fsClosePop() });
  document.addEventListener('click',e=>{ if(!e.target.closest('.fsWrap'))fsHideSug();
    if(!e.target.closest('.kwWrap'))kwHideSug(); });
  if(!fsQBooked){ fsQBooked=true; fsQStep(); setTimeout(fsQTick,3200) }
  fsPaintPop();
}
