import { $, $$, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';
import { IMG, itemCard, STYLES } from '../../../home/static/js/chat.js';
import { ST_ITEM_CATS, ST_ITEM_PAGE_SIZE, ST_PICK_COUNT, ST_RECOMMEND_NOTE, ST_SORTS, itemCatKey, styleProductCard, styleProductsURL } from './products.js';

/* ── Style ──────────────────────────────────────────── */
export var stShowI=0, stItemPage=0, stCur=null;
let stSort='recommend';   /* 아이템 정렬 — 스타일에 들어갈 때마다 FEEDiT 추천순으로 돌아간다 */
/* 아이템 카테고리. 서버가 카테고리를 먼저 거른 뒤 페이지를 나눠 준다.
   예전처럼 첫 24개 안에서만 감추면 아우터가 1~2개씩 보이고, '더 보기'를
   누를 때마다 몇 개씩 생기는 잘못된 목록이 된다. */
let stCat='all';
function stCatsPaint(){
  const box=$('#stItemCats'); if(!box)return;
  box.innerHTML=ST_ITEM_CATS.map(([k,l])=>
    '<button type="button" class="itCat'+(k===stCat?' on':'')+'" data-item-cat="'+k+'">'+l+'</button>').join('');
}
/* 서버 결과를 방어적으로 한 번 더 확인한다. '전체'는 분류 불가 상품도 남긴다. */
function stCatsApply(){
  const host=$('#stItems'); if(!host)return;
  let shown=0;
  host.querySelectorAll('.itemCard').forEach(card=>{
    const ok=stCat==='all'||card.dataset.catKey===stCat;
    card.hidden=!ok;
    if(ok)shown++;
  });
  const none=host.querySelector('.itCatEmpty');
  if(!shown&&host.querySelector('.itemCard')){
    if(!none){
      const el=document.createElement('div');
      el.className='itState itCatEmpty';
      el.textContent='이 카테고리에 해당하는 상품이 아직 없습니다.';
      host.appendChild(el);
    }
  }else if(none)none.remove();
  const cnt=$('#stItemCount');
  if(cnt&&stCat!=='all')cnt.textContent=(stTotal??shown)+' ITEMS';
}
function stCatsWire(){
  const box=$('#stItemCats'); if(!box)return;
  box.addEventListener('click',e=>{
    const b=e.target.closest('button[data-item-cat]'); if(!b)return;
    if(b.dataset.itemCat===stCat)return;
    stCat=b.dataset.itemCat;
    stCatsPaint();
    /* 선택한 카테고리의 0페이지를 다시 받는다. 그래야 페이지 하나가 해당
       카테고리 상품으로 채워지고, 더보기도 같은 카테고리의 다음 페이지다. */
    stResetItems();
  });
}
/* 'FEEDiT Pick!' — 그 스타일의 추천순 최상단 6개. 스타일마다 한 번 받아 두고,
   다른 정렬로 바꿔도 같은 상품이면 라벨을 그대로 붙인다. */
let stPicks=Promise.resolve(new Set());
let stItemsLoading=false, stItemsDone=false, stItemsError=false, stRequestSeq=0;
let stTotal=null;   /* 이 스타일의 전체 상품 수 — '더 보기 (24 / 312)' 에 쓴다 */
/* 스타일 사진 — 전용 컷(ph)이 있으면 그걸 쓰고, 없으면 공용 라이브러리로 떨어진다 */
export const SIMG=s=>s.ph||IMG(s.img);
export function stBuild(){
  /* ★ 2026-09-20 — 스타일 홈을 [쇼케이스] + [코어 · 원형 인덱스] 둘로 합쳤다.
     예전의 사진 타일 그리드(#stGrid)와 알약 버튼 줄은 인덱스 한 칸(사진 + 번호 · 한/영 · 화살표)으로 들어왔다.
     누르면 그 스타일 상세로 간다(문서 전역 [data-style] 위임). */
  /* ★ 쇼케이스는 뺐다 — 스타일 홈은 코어 · 원형 인덱스만 둔다 */
  const GO='<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 11.5l7-7M5.5 4.5h6v6"/></svg>';
  let no=0;
  const cell=s=>{ const i=no++;
    return '<button type="button" class="stCat" data-style="'+s.id+'" style="--i:'+i+'" aria-label="'+s.n+' 스타일 보기">'+
      '<span class="stCatPh"><img src="'+SIMG(s)+'" alt="" loading="lazy"></span>'+
      '<span class="stCatMeta"><span class="stCatNo">'+String(i+1).padStart(2,'0')+'</span>'+
        '<span class="stCatTx"><b>'+s.n+'</b><em>'+s.en+'</em></span>'+
        '<i class="stCatGo">'+GO+'</i></span></button>'; };
  const group=(t,en,d,list)=>list.length?'<div class="stGroup">'+
    '<div class="stGroupHead"><b>'+t+'</b><em>'+en+'</em><span>'+d+'</span></div>'+
    '<div class="stGroupRow">'+list.map(cell).join('')+'</div></div>':'';
  const core=STYLES.filter(s=>s.g==='코어'), root=STYLES.filter(s=>s.g==='원형');
  const rest=STYLES.filter(s=>s.g!=='코어'&&s.g!=='원형');
  $('#stCats').innerHTML=
    group('코어','CORE','지금 이름이 붙어 도는 흐름',core)+
    group('원형','ROOTS','코어들이 갈라져 나온 뿌리',root.concat(rest));
  $('#stBack').addEventListener('click',()=>{
    $('#styleDetail').style.display='none'; $('#styleHome').style.display=''; scrollTo(0,0) });
  $('#stFitClose')&&$('#stFitClose').addEventListener('click',stCloseFit);
  $('#styleFitModal')&&$('#styleFitModal').addEventListener('click',e=>{
    if(e.target.id==='styleFitModal')stCloseFit();
  });
  stSortBuild();
  stCatsPaint(); stCatsWire();
  /* '더 보기' — 무한 스크롤 대신 누를 때만 다음 24개를 붙인다 */
  $('#stMore')&&$('#stMore').addEventListener('click',()=>{
    if(stItemsError){ stItemsError=false; stItemsDone=false }
    else if(stItemsDone||stItemsLoading)return;
    stMoreItems();
  });
}
/* '이 스타일 더 보기' — 스타일 상세로 이동하지 않고, 그 스타일의 Virtual Fitting
   카드만 팝업으로 보여준다 (금주의 리포트 히어로 버튼에서 연결) */
export function stOpenFit(id){
  const s=STYLES.find(x=>x.id===id)||STYLES[0];
  const t=$('#stFitTitle'); if(t)t.textContent=s.n+' · Virtual Fitting';
  const g=$('#stFitGrid'); if(g)g.innerHTML=infCards(s);
  const m=$('#styleFitModal'); if(m)m.classList.add('on');
}
export function stCloseFit(){
  const m=$('#styleFitModal'); if(m)m.classList.remove('on');
}
function stKeepAll(text,kwList){
  let t=text;
  kwList.forEach(k=>{ if(k.indexOf(' ')>-1) t=t.split(k).join(k.replace(/ /g,'\u00A0')); });
  return t;
}
function stSentences(text){
  return text.split(/(?<=[.!?])\s+/).map(t=>t.trim()).filter(Boolean).join('<br>');
}
/* 스타일별 Virtual Fitting 컷 — 실제 착장 이미지 2장(파일명이 스타일명과 일치) */
export const VFIT_IMG={
  gorp:    ['assets/vfit/gorp_1.jpg',    'assets/vfit/gorp_2.jpg'],
  grunge:  ['assets/vfit/grunge_1.jpg',  'assets/vfit/grunge_2.jpg'],
  geek:    ['assets/vfit/geek_1.jpg',    'assets/vfit/geek_2.jpg'],
  norm:    ['assets/vfit/norm_1.jpg',    'assets/vfit/norm_2.jpg'],
  bike:    ['assets/vfit/bike_1.jpg',    'assets/vfit/bike_2.jpg'],
  ballet:  ['assets/vfit/ballet_1.jpg',  'assets/vfit/ballet_2.jpg'],
  block:   ['assets/vfit/block_1.jpg',   'assets/vfit/block_2.jpg'],
  classic: ['assets/vfit/classic_2.jpg', 'assets/vfit/classic_3.jpg'],
  street:  ['assets/vfit/street_1.jpg',  'assets/vfit/street_3.jpg'],
  ameka:   ['assets/vfit/ameka_1.jpg',   'assets/vfit/ameka_2.jpg'],
  feminine:['assets/vfit/feminine_1.jpg','assets/vfit/feminine_2.jpg'],
  biz:     ['assets/vfit/biz_1.jpg',     'assets/vfit/biz_2.jpg'],
  ath:     ['assets/vfit/ath_1.jpg',     'assets/vfit/ath_2.jpg']
};
/* Virtual Fitting 카드 — 스타일 상세 페이지(#stInf)와 '이 스타일 더 보기' 팝업이
   같은 카드를 그대로 재사용한다. 인스타 피드가 아니므로 프로필/아이디/팔로워 없이
   사진만 채운다 — 전용 컷이 없는 스타일은 공용 라이브러리로 대체한다 */
export function infCards(s){
  const imgs=VFIT_IMG[s.id]||[IMG(((s.img)%35)+1),IMG(((s.img+3)%35)+1)];
  return imgs.map(src=>
    '<div class="infC"><div class="im"><img src="'+src+'" alt="'+s.n+'" loading="lazy"></div></div>').join('');
}
export function stOpen(id){
  const s=STYLES.find(x=>x.id===id)||STYLES[0];
  stCur=s; stSort='recommend'; stCat='all'; stCatsPaint(); stPicks=stLoadPicks(s.n); stTotal=null; stItemPage=0; stItemsLoading=false; stItemsDone=false; stItemsError=false;
  const requestSeq=++stRequestSeq;
  $('#styleHome').style.display='none'; $('#styleDetail').style.display='';
  $$('#stCats .stCat').forEach(b=>b.classList.toggle('on',b.dataset.style===s.id));
  $('#stHero').innerHTML='<img src="'+SIMG(s)+'" alt="'+s.n+'"><div class="vg"></div>'+
    '<div class="in"><em>'+s.en.toUpperCase()+'</em><h2>'+s.n+'</h2><div class="mt">'+
    '<div><b>'+s.st+'</b><span>시작</span></div>'+
    '<div><b>'+s.kw.length+'</b><span>핵심 키워드</span></div></div></div>';
  $('#stAbout').innerHTML=
    '<div><h3>이 스타일은 어떻게 시작됐나</h3><p>'+stSentences(stKeepAll(s.ab+' '+s.ab2,s.kw))+'</p></div>'+
    '<dl><div><dt>시작</dt><dd>'+s.st+'</dd></div>'+
    '<div><dt>확산 계기</dt><dd>'+s.by+'</dd></div>'+
    '<div><dt>핵심 키워드</dt><dd>'+s.kw.join(' · ')+'</dd></div></dl>';
  $('#stInf').innerHTML=infCards(s);
  stPaintSort();
  $('#stItems').innerHTML='<div class="itState">상품을 불러오는 중…</div>';
  $('#stItemCount').textContent='0 ITEMS';
  stMoreItems(requestSeq);
  if(HAS_A)aAnimate('#stHero .in',{opacity:[0,1],translateY:[22,0],duration:900,ease:'out(3)'});
  scrollTo(0,0);
}
/* 정렬 드롭다운 — 'FEEDiT 추천순' 줄에는 ⓘ 버튼을 달아 점수 기준을 펼쳐 보여 준다.
   기본 select 로는 줄 안에 버튼을 넣을 수 없어 목록을 직접 그린다. */
function stSortBuild(){
  const wrap=$('#stSort'), btn=$('#stSortBtn'), menu=$('#stSortMenu');
  if(!wrap||!btn||!menu)return;
  /* 안내창은 ⓘ 가 있는 줄 안에 두고, ⓘ 왼쪽 아래로 펼친다 */
  const info='<button type="button" class="stSortInfoBtn" id="stSortInfoBtn" aria-expanded="false"'+
    ' aria-label="FEEDiT 추천순 기준 보기">i</button>'+
    '<div class="stSortInfo" id="stSortInfo" role="tooltip" hidden>'+
    ST_RECOMMEND_NOTE.join('<br>')+'</div>';
  menu.innerHTML=ST_SORTS.map(([k,l])=>
    '<div class="stSortRow'+(k==='recommend'?' hasInfo':'')+'">'+
    (k==='recommend'?info:'')+
    '<button type="button" class="stSortOpt" role="option" data-sort="'+k+'">'+l+'</button>'+
    '</div>').join('');

  btn.addEventListener('click',()=>stSortOpen(!wrap.classList.contains('open')));
  menu.addEventListener('click',e=>{
    const info=e.target.closest('.stSortInfoBtn');
    if(info){   /* ⓘ 는 정렬을 고르는 것이 아니라 설명만 여닫는다 */
      const box=$('#stSortInfo'), on=box.hasAttribute('hidden');
      box.toggleAttribute('hidden',!on);
      info.setAttribute('aria-expanded',String(on));
      return;
    }
    const opt=e.target.closest('.stSortOpt');
    if(!opt)return;
    stSortOpen(false);
    if(opt.dataset.sort===stSort)return;
    stSort=opt.dataset.sort;
    stResetItems();
  });
  /* 바깥을 누르면 닫힌다 */
  addEventListener('click',e=>{ if(!e.target.closest('#stSort'))stSortOpen(false) });
  addEventListener('keydown',e=>{ if(e.key==='Escape')stSortOpen(false) });
  stPaintSort();
}
function stSortOpen(on){
  const wrap=$('#stSort'), btn=$('#stSortBtn');
  if(!wrap)return;
  wrap.classList.toggle('open',on);
  if(btn)btn.setAttribute('aria-expanded',String(on));
  if(!on){
    const box=$('#stSortInfo'), info=$('#stSortInfoBtn');
    if(box)box.setAttribute('hidden','');
    if(info)info.setAttribute('aria-expanded','false');
  }
}
function stPaintSort(){
  const wrap=$('#stSort'), label=$('#stSortLabel');
  const cur=ST_SORTS.find(([k])=>k===stSort)||ST_SORTS[0];
  if(wrap)wrap.dataset.sort=stSort;
  if(label)label.textContent=cur[1];
  $$('#stSortMenu .stSortOpt').forEach(b=>b.classList.toggle('on',b.dataset.sort===stSort));
}
function stLoadPicks(styleName){
  return fetch(styleProductsURL(styleName,0,ST_PICK_COUNT,'recommend'))
    .then(r=>r.ok?r.json():null)
    .then(j=>new Set((j&&j.status==='ok'&&j.data&&Array.isArray(j.data.items)?j.data.items:[])
      .slice(0,ST_PICK_COUNT).map(it=>styleProductCard(it,styleName).id)))
    .catch(()=>new Set());   /* 라벨을 못 받아도 상품 목록은 그대로 보여 준다 */
}
/* 정렬을 바꾸면 이미 받은 카드를 비우고 첫 페이지부터 다시 받는다 */
function stResetItems(){
  if(!stCur)return;
  stItemPage=0; stTotal=null; stItemsLoading=false; stItemsDone=false; stItemsError=false;
  const requestSeq=++stRequestSeq;
  stPaintSort();
  $('#stItems').innerHTML='<div class="itState">상품을 불러오는 중…</div>';
  $('#stItemCount').textContent='0 ITEMS';
  stMoreItems(requestSeq);
}
function stMoreState(text,{retry=false,disabled=false}={}){
  const more=$('#stMore'); if(!more)return;
  more.textContent=text;
  more.classList.toggle('retry',retry);
  more.disabled=disabled;
}
/* '더 보기 (24 / 312)' — 전체 개수를 모르면 개수 없이 '더 보기' 만 보여 준다 */
function stMorePaint(loaded){
  if(stItemsDone){ stMoreState('모든 상품을 불러왔습니다',{disabled:true}); return }
  stMoreState('더 보기'+(stTotal?' ('+loaded+' / '+stTotal+')':''));
}

export async function stMoreItems(requestSeq=stRequestSeq){
  const host=$('#stItems');
  if(!host||!stCur||stItemsLoading||stItemsDone)return;
  const styleName=stCur.n;
  const offset=stItemPage*ST_ITEM_PAGE_SIZE;
  stItemsLoading=true; stItemsError=false;
  stMoreState('상품을 불러오는 중…');
  try{
    const [res,picks]=await Promise.all([
      fetch(styleProductsURL(styleName,offset,ST_ITEM_PAGE_SIZE,stSort,stCat)),
      stPicks
    ]);
    const body=await res.text();
    if(!res.ok)throw new Error('HTTP '+res.status);
    let json;
    try{ json=JSON.parse(body) }catch(e){ throw new Error('JSON 응답이 아닙니다') }
    if(requestSeq!==stRequestSeq||!stCur||stCur.n!==styleName)return;   /* 스타일·정렬이 바뀐 뒤 늦게 온 응답은 버린다 */
    if(json.status==='error')throw new Error(json.reason||'상품 API 오류');

    const items=json.status==='ok'&&json.data&&Array.isArray(json.data.items)
      ?json.data.items:[];
    host.querySelectorAll('.itState').forEach(el=>el.remove());
    if(!items.length){
      stItemsDone=true;
      if(!host.querySelector('.itemCard')){
        host.innerHTML='<div class="itState">이 스타일 태그가 연결된 상품이 아직 없습니다.</div>';
      }
      stMoreState('불러올 상품이 없습니다',{disabled:true});
      return;
    }

    const frag=document.createElement('div');
    frag.innerHTML=items.map(item=>{
      const card=styleProductCard(item,styleName);
      return itemCard({...card,pick:picks.has(card.id),catKey:itemCatKey(card)});
    }).join('');
    const els=[...frag.children]; els.forEach(el=>host.appendChild(el));
    stItemPage++;
    if(Number.isFinite(json.data.total))stTotal=json.data.total;
    stItemsDone=json.data.has_more===false||items.length<ST_ITEM_PAGE_SIZE;
    const loaded=host.querySelectorAll('.itemCard').length;
    $('#stItemCount').textContent=(stTotal||loaded)+' ITEMS';
    stCatsApply();                 /* 새로 붙은 카드에도 지금 걸린 카테고리를 적용한다 */
    stMorePaint(loaded);
    if(HAS_A)aAnimate(els,{opacity:[0,1],translateY:[18,0],duration:760,delay:aStagger(50),ease:'out(3)'});
  }catch(e){
    if(requestSeq!==stRequestSeq)return;
    stItemsError=true; stItemsDone=true;
    host.querySelectorAll('.itState').forEach(el=>el.remove());
    if(!host.querySelector('.itemCard')){
      host.innerHTML='<div class="itState">상품을 불러오지 못했습니다.<br>'+
        String(e&&e.message||e).replace(/[<>&]/g,'')+'</div>';
    }
    stMoreState('다시 시도',{retry:true});
  }finally{
    if(requestSeq===stRequestSeq)stItemsLoading=false;
  }
}
