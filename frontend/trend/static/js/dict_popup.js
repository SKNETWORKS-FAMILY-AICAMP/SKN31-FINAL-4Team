/* 사전 팝업 — EDIT 검색바 오른쪽 '사전' 버튼.
   /api/dictionary(dictionary_term + brand)를 term_type 별 칸으로 나눠 보여 준다.
   세부 검색 팝업과 같은 틀이지만, 칸을 통틀어 용어를 **하나만** 고른다(다른 칸을 누르면 옮겨 간다).
   고른 용어는 '이 용어로 검색'으로 지금 보고 있는 탭의 검색에 넣는다.
   버튼은 data-dict-open 으로 찾는다 — 검색바가 탭마다 새로 그려져도 리스너는 한 번이면 된다.
   (data-v 는 router.js 의 전역 클릭 위임이 화면 전환으로 읽으니 쓰지 않는다.) */
import { $ } from '../../../core/static/js/dom.js';

/* 서버 facet → 칸. 순서가 곧 칸 순서다. */
const COLS=[['스타일','스타일'],['아이템','아이템'],['소재','소재'],['디테일','디테일'],
            ['색','색깔'],['TPO','TPO'],['브랜드','브랜드']];
const SHOW_MAX=300;   /* 브랜드처럼 많은 칸은 이만큼만 그리고 칸 위 검색으로 좁히게 한다 */

/* 세부 검색(search.js fsPaintPop)이 `.fsCol` 을 통째로 숨기므로 이 팝업의 칸은 .dictCol 을 쓴다 */
let ROWS=null, loading=null, built=false, failed=false;
let sel=null;            /* {f,label} — 사전 전체에서 하나 */
const find={};           /* 칸별 찾기 글자 */
let guideSnapshot=null;  /* 가이드가 닫히면 실제 사전 상태를 그대로 돌려놓는다 */
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>String(s||'').replace(/\s/g,'').toLowerCase();

function build(){
  if(built)return; built=true;
  const bg=document.createElement('div');
  bg.className='fsPopBg'; bg.id='dictPopBg'; bg.setAttribute('inert','');
  bg.innerHTML=
    '<div class="fsPop dictPop" role="dialog" aria-label="사전">'+
      '<div class="fsPopHead"><div><h3>사전</h3>'+
        '<p>FEEDiT에서 쓰는 패션 용어를 분류별로 확인합니다. 용어는 하나만 고를 수 있습니다.</p></div>'+
      '<button class="fsX" id="dictX" type="button" aria-label="닫기">×</button></div>'+
      '<div class="fsCols" id="dictCols">'+COLS.map(([f,name])=>
        '<div class="dictCol" data-df="'+f+'">'+
          '<div class="fsColH">'+name+'<em></em></div>'+
          '<div class="fsColFind"><input type="text" data-dfind="'+f+'" autocomplete="off" spellcheck="false" '+
            'placeholder="'+name+' 찾기" aria-label="'+name+' 찾기"></div>'+
          '<div class="fsList"></div>'+
        '</div>').join('')+'</div>'+
      '<div class="fsPopFoot">'+
        '<div class="fsPicked" id="dictPicked"></div>'+
        '<div class="fsActs">'+
          '<button class="fsReset" id="dictReset" type="button">선택 해제</button>'+
          '<button class="fsApply" id="dictApply" type="button">이 용어로 검색 <u>→</u></button>'+
        '</div>'+
      '</div>'+
    '</div>';
  document.body.appendChild(bg);
  bg.addEventListener('click',e=>{ if(e.target===bg)close() });
  $('#dictX').addEventListener('click',close);
  $('#dictReset').addEventListener('click',()=>{ sel=null; paintAll() });
  $('#dictApply').addEventListener('click',apply);
  $('#dictCols').addEventListener('input',e=>{
    const i=e.target.closest('[data-dfind]'); if(!i)return;
    find[i.dataset.dfind]=i.value; paintCol(i.dataset.dfind);
  });
  $('#dictCols').addEventListener('click',e=>{
    const b=e.target.closest('[data-dv]'); if(!b)return;
    const col=b.closest('[data-df]'), f=col.dataset.df, label=b.dataset.dv;
    /* 같은 용어를 다시 누르면 해제, 다른 용어(다른 칸이어도)를 누르면 그쪽으로 옮겨 간다 */
    sel=(sel&&sel.f===f&&sel.label===label)?null:{f,label};
    paintAll();
  });
  document.addEventListener('keydown',e=>{ if(e.key==='Escape'&&bg.classList.contains('on'))close() });
}

function load(){
  if(ROWS)return Promise.resolve();
  if(loading)return loading;
  return loading=fetch('/api/dictionary?limit=12000',{headers:{Accept:'application/json'}})
    .then(r=>r.json())
    .then(j=>{ ROWS=(j&&j.status==='ok'&&Array.isArray(j.data))?j.data:null; failed=!ROWS })
    .catch(()=>{ ROWS=null; failed=true })
    .finally(()=>{ loading=null });
}

function paintCol(f){
  const col=$('#dictCols [data-df="'+f+'"]'); if(!col)return;
  const list=col.querySelector('.fsList'), cnt=col.querySelector('.fsColH em');
  if(!ROWS){ cnt.textContent=''; list.innerHTML='<div class="hint">'+(failed?'사전을 불러오지 못했습니다.':'불러오는 중…')+'</div>'; return }
  const all=ROWS.filter(r=>r.facet===f);
  cnt.textContent=all.length.toLocaleString();
  const q=norm(find[f]);
  const rows=all.filter(r=>!q||norm(r.label).includes(q)||norm(r.en).includes(q))
    .sort((a,b)=>String(a.label).localeCompare(String(b.label),'ko'));
  if(!rows.length){ list.innerHTML='<div class="hint">'+(q?'찾는 용어가 없습니다.':'아직 용어가 없습니다.')+'</div>'; return }
  list.innerHTML=rows.slice(0,SHOW_MAX).map(r=>
    '<button type="button" data-dv="'+esc(r.label)+'"'+(sel&&sel.f===f&&sel.label===r.label?' class="on"':'')+'>'+
    '<span>'+esc(r.label)+'</span></button>').join('')+
    (rows.length>SHOW_MAX?'<div class="hint">외 '+(rows.length-SHOW_MAX).toLocaleString()+'개 — 위 칸에서 찾아 보세요.</div>':'');
}
function paintAll(){
  COLS.forEach(([f])=>paintCol(f));
  const nm=(COLS.find(c=>c[0]===sel?.f)||[])[1];
  $('#dictPicked').innerHTML=sel
    ? '<span class="fsChip"><small>'+esc(nm)+'</small>'+esc(sel.label)+'</span>'
    : '<span class="ph2">아직 고른 용어가 없습니다. 아무 용어나 눌러 보세요.</span>';
  $('#dictApply').disabled=!sel;
  $('#dictApply').style.opacity=sel?'':'.4';
}

/* 고른 용어를 지금 탭의 검색에 넣는다 — 직접 쳐서 Enter 한 것과 같다 */
function apply(){
  if(!sel)return;
  const label=sel.label;
  close();
  if($('#trTabs')&&$('#trTabs').classList.contains('kwmode')){
    if(window.feeditKwGo)window.feeditKwGo(label);
    return;
  }
  const inp=$('#fsInput'); if(!inp)return;
  inp.value=label;
  inp.dispatchEvent(new Event('input',{bubbles:true}));
  inp.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
}

function open(){
  build();
  const bg=$('#dictPopBg');
  bg.classList.add('on'); bg.removeAttribute('inert');
  failed=false;   /* 다시 열 때마다 새로 시도한다 — 지난 실패가 '불러오지 못했습니다' 로 남지 않게 */
  paintAll();
  load().then(paintAll);
}
function close(){
  const bg=$('#dictPopBg'); if(!bg)return;
  bg.classList.remove('on'); bg.setAttribute('inert','');
}

/* 온보딩 전용: 실제 사전 API를 부르지 않고 저장된 용어로 같은 모달을 연다. */
export function openDictionaryGuideDemo(rows, selected){
  build();
  if(!guideSnapshot)guideSnapshot={ROWS,failed,sel:sel?{...sel}:null,find:{...find}};
  ROWS=Array.isArray(rows)?rows:[];
  failed=false;
  sel=selected&&selected.f&&selected.label?{f:selected.f,label:selected.label}:null;
  paintAll();
  const bg=$('#dictPopBg');
  bg.classList.add('on'); bg.removeAttribute('inert');
}

export function closeDictionaryGuideDemo(){
  close();
  if(!guideSnapshot)return;
  ROWS=guideSnapshot.ROWS;
  failed=guideSnapshot.failed;
  sel=guideSnapshot.sel;
  Object.keys(find).forEach(key=>delete find[key]);
  Object.assign(find,guideSnapshot.find);
  guideSnapshot=null;
  /* 다음 실제 사전 열기 전에 DOM도 실제 상태로 되돌린다. */
  paintAll();
}

document.addEventListener('click',e=>{
  if(e.target.closest('[data-dict-open]'))open();
});
