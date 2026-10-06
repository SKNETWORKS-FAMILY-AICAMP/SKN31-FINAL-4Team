import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';
import { WK, feedSmPicks, feedSmLoad } from './my_feed.js';
import { STYLES } from '../../../home/static/js/chat.js';
import { SIMG } from '../../../style/static/js/style_page.js';
import { FS, getFsCols, fsBuild, fsChipsPaint, fsDropDisallowed, fsHideSug, fsLoadDictionary, fsOpenPop, fsReset, fsPaintPop, fsStockSelect, fsStockClear, fsResaleSelect } from '../../../style/static/js/search.js';
import { G_CFG, KW, fsItem, fsItemFull, fsSelectionLabel, gMount, josa, trEmpty, trFillBars, trToast } from './render_helpers.js';
import { ME, bioPaint } from '../../../account/static/js/profile.js';
import { S_EDIT, S_FEED, TR_META } from './nav_meta.js';
import { assocClosePop, assocOpenPop } from './assoc_popover.js';
import { paintRegionHeat } from './region_heatmap.js';
import { entryOf, prime, primeUrl, sentimentUrl, stateOf, stateOfUrl, summaryOf, unavailableHTML } from './live_data.js';
import { gChart, gDraw } from './chart_engine.js';
import { paintStockPriceChart } from './stock_price_chart.js';
import { kwWire } from './saved_keywords.js';
import './dict_popup.js';
import { rkChip, rkPaintAv } from '../../../account/static/js/rank.js';
import { jobBadgeHTML, jobPlanText, jobShown } from '../../../account/static/js/job.js';
import { smBarFill, svRender } from './discount_resale.js';
import { trCountUp } from './count_up.js';
import { trDial, wkAnimate } from './weekly_report.js';
import { buildXlsx, canvasToPdf, canvasToPng, captureElement, saveBlob, shareImage } from './report_export.js';
import { metricXlsx } from './metric_export.js';
import { trSideOpen } from '../../../app_shell/static/js/router.js';
import { weeklyReport, weeklyVideos, savedProducts, setSavedProduct } from '../../../account/static/js/account_api.js';
import { PLAN_EVENT, planEditAllowed, planGuard, planLockHTML } from '../../../account/static/js/plan.js';

/* 탭 자리 — 키워드 검색바 / 커머스 탭 / 없음 세 가지로 갈린다 */
function trTabsRender(id){
  const el=$('#trTabs'); if(!el)return;
  const kwMode=(id==='temp'||id==='assoc'||id==='sentiment');
  el.classList.toggle('kwmode',kwMode);
  if(kwMode){
    el.hidden=false;
    /* 할인률 파트의 챗바와 완전히 같은 골격(.fsWrap/.fsRow/.fsBar).
       세부 검색 버튼 대신 사전 버튼만 둔다. */
    el.innerHTML=
      '<div class="fsWrap kwWrap">'+
        '<div class="fsRow">'+
          '<div class="fsBar'+(KW.q?' typing':'')+'" id="kwBar">'+
            '<span class="fsIc">◎</span>'+
            '<input type="text" id="kwInput" autocomplete="off" spellcheck="false" value="'+KW.q+'" '+
              'placeholder="소재 · 아이템 · 스타일 · 브랜드로 검색">'+
            '<span class="fsGhost"><span class="fsQ" id="kwQ"></span></span>'+
            '<button class="fsClear" id="kwClear" type="button"'+(KW.q?'':' hidden')+'>×</button>'+
          '</div>'+
          /* 세부 검색 버튼 자리 — 여기는 사전 버튼 하나 */
          '<div class="fsSide"><button class="fsMore fsDictBtn" type="button" data-dict-open>사전</button></div>'+
        '</div>'+
        '<div class="fsSug" id="kwSug" hidden></div>'+
      '</div>';
    return;
  }
  if(id==='stock'){
    /* 단일 상품의 가격 지표에는 플랫폼 집계 탭이 맞지 않는다. */
    el.hidden=true; el.innerHTML=''; TR_TAB='통합';
  }else{
    el.hidden=true; el.innerHTML=''; TR_TAB='통합';
  }
}
function trFillBarsV(){
  const fl=$$('#trBody .pbars i');
  if(HAS_A){ aUtils.set(fl,{height:'0%'});
    aAnimate(fl,{height:el=>el.dataset.h+'%',duration:1050,delay:aStagger(90),
      ease:aSpring({stiffness:64,damping:16})}); }
  else fl.forEach(x=>x.style.height=x.dataset.h+'%');
}

let TR_CUR=null;
const TR_EDIT_IDS=S_EDIT.map(s=>s.id);
/* 요금제로 잠긴 EDIT 탭 — 머리글만 그 탭 것으로 두고, 검색창 · 저장/공유 대신 안내를 세운다 */
function trRenderLocked(id){
  const m=TR_META[id]||TR_META.myfeed;
  $('#trTitle').textContent=m[0];
  $('#trDesc').textContent=m[1]; $('#trDesc').hidden=!m[1];
  trTabsRender('');                 /* 키워드 검색창을 세우지 않는다 */
  const tw=$('#trTitleWrap'), tp=$('#trProfile');
  if(tw)tw.hidden=false;
  if(tp)tp.hidden=true;
  const kk=$('#trKicker'); if(kk)kk.hidden=true;
  const acts=$('#trHeadActs'); if(acts)acts.hidden=true;
  const dm=$('#trDlMenu'); if(dm)dm.hidden=true;
  const sw=$('#trSearch'); if(sw){ sw.hidden=true; fsHideSug(); }
  const body=$('#trBody'); if(body)body.innerHTML=planLockHTML(m[0]);
}
/* 사이드바 EDIT 항목에 잠금 표시 — 베타 동안에는 붙지 않는다 */
function trPaintLocks(){
  $$('#sEdit .sItem').forEach(b=>{
    const locked=!planEditAllowed(b.dataset.tr);
    b.classList.toggle('planLocked',locked);
    if(locked)b.title='프로 요금제부터 볼 수 있어요'; else b.removeAttribute('title');
  });
}
document.addEventListener(PLAN_EVENT,()=>{
  trPaintLocks();
  /* 요금제가 바뀌었는데 보고 있던 탭의 잠금이 달라졌으면 그 자리에서 다시 그린다 */
  if(document.body.dataset.view==='trend'&&TR_CUR&&TR_EDIT_IDS.indexOf(TR_CUR)>=0){
    const locked=!!($('#trBody')&&$('#trBody .planLock'));
    if(locked===planEditAllowed(TR_CUR))trRender(TR_CUR);
  }
});
const TR_TRIED={};   /* 용어 → 마지막으로 물어본 때 */
const STOCK_SAVED={items:[],status:'idle',error:'',loadedAt:0,promise:null};
let stockSavedSeq=0, stockSavePending=false, stockSaveError='', stockCurrentProduct=null;
let stockLastSelectionId=null;
function stockLoadSaved(background=false){
  if(STOCK_SAVED.promise||STOCK_SAVED.status!=='idle'&&Date.now()-STOCK_SAVED.loadedAt<30000)return;
  const seq=++stockSavedSeq;
  if(!background)STOCK_SAVED.status='loading';
  STOCK_SAVED.promise=savedProducts().then(data=>{
    if(seq!==stockSavedSeq)return;
    STOCK_SAVED.items=Array.isArray(data.items)?data.items:[];
    STOCK_SAVED.status='ok'; STOCK_SAVED.error=''; STOCK_SAVED.loadedAt=Date.now();
  }).catch(e=>{
    if(seq!==stockSavedSeq)return;
    if(!background){
      STOCK_SAVED.status='error'; STOCK_SAVED.error=e.message||'찜목록을 읽지 못했습니다.';
    }
    STOCK_SAVED.loadedAt=Date.now();
  }).finally(()=>{
    if(seq!==stockSavedSeq)return;
    STOCK_SAVED.promise=null;
    if(TR_CUR==='stock')trRender('stock');
  });
}
document.addEventListener('feedit:saved',()=>{
  stockSavedSeq++;
  STOCK_SAVED.loadedAt=0; STOCK_SAVED.promise=null;
  if(TR_CUR==='stock')stockLoadSaved(STOCK_SAVED.status==='ok');
});
/* 찜이 서버 원본으로 바뀌면(로그인·로그아웃) 찜한 키워드 화면을 다시 그린다 */
document.addEventListener('feedit:liked-sync',()=>{ if(TR_CUR==='saved')trRender('saved'); });
document.addEventListener('feedit:auth',()=>{
  stockSavedSeq++;
  STOCK_SAVED.items=[]; STOCK_SAVED.status='idle'; STOCK_SAVED.error='';
  STOCK_SAVED.loadedAt=0; STOCK_SAVED.promise=null;
  fsStockClear();
  stockCurrentProduct=null; stockSaveError=''; stockSavePending=false;
});
const stockSafeImg=url=>/^(https?:\/\/|\/|assets\/)/i.test(String(url||''))?String(url):'';
function stockCardDiscount(item){
  const regular=Number(item.list_price), sale=Number(item.sale_price);
  if(Number.isFinite(regular)&&regular>0&&Number.isFinite(sale)&&sale>=0&&sale<=regular)
    return Math.round((regular-sale)/regular*100);
  const rate=item.discount_rate==null?null:Number(item.discount_rate);
  return Number.isFinite(rate)&&rate>=0&&rate<=100?Math.round(rate):null;
}
function stockWishlistHTML(){
  if(STOCK_SAVED.status==='loading'||STOCK_SAVED.status==='idle')
    return '<p class="stockWishMessage">DB 찜목록을 불러오는 중입니다…</p>';
  if(STOCK_SAVED.status==='error')
    return '<p class="stockWishMessage">'+trEsc(STOCK_SAVED.error)+
      '<br><button type="button" class="stockWishRetry" data-stock-retry>다시 시도</button></p>';
  if(!STOCK_SAVED.items.length)
    return '<p class="stockWishMessage">일반 판매 상품 찜이 아직 없습니다.<br>스타일 페이지에서 상품을 찜해 보세요.</p>';
  return STOCK_SAVED.items.map(item=>{
    const discount=stockCardDiscount(item);
    const selected=FS.stockItem?.id===Number(item.id);
    /* ★ 2026-09-19 — 카드 안에 찜 해제 버튼이 들어가므로 카드는 div(role=button)로 둔다.
       버튼 안에 버튼은 넣을 수 없다. 클릭으로 고르고, 같은 카드를 다시 누르면 선택이 풀린다. */
    /* ★ 2026-09-19 — 카드는 사진 한 장이다. 브랜드 · 상품명은 사진 왼쪽 위에 얹고,
       가격은 고르면 오른쪽 요약에서 보이므로 카드에서는 뺀다.
       하트는 스타일 페이지 아이템 카드와 같은 모양(.likeBtn)으로 오른쪽 위에 둔다. */
    return '<div class="wlItem'+(selected?' on':'')+'" role="button" tabindex="0" draggable="true"'+
      ' data-source-id="'+Number(item.id)+'" aria-pressed="'+(selected?'true':'false')+'"'+
      ' title="'+trEsc([item.brand||item.source,item.name].filter(Boolean).join(' · '))+
        (discount==null?'':' · '+discount+'%')+'"'+
      ' aria-label="'+trEsc(item.name)+' 할인률 분석">'+
      '<span class="wlPic">'+(stockSafeImg(item.image)?'<img src="'+trEsc(item.image)+'" alt="" loading="lazy">':'이미지 없음')+
        '<button type="button" class="likeBtn wlHeart on" data-wish-off="'+Number(item.id)+'"'+
          ' aria-label="'+trEsc(item.name)+' 찜 해제" title="찜 해제">'+
          '<svg viewBox="0 0 24 24"><path d="M12 21s-7.6-4.6-10.3-9.1C.2 9 1 5.5 4 4.1c2.4-1.1 5-.2 6.5 1.8L12 8l1.5-2.1c1.5-2 4.1-2.9 6.5-1.8 3 1.4 3.8 4.9 2.3 7.8C19.6 16.4 12 21 12 21z"/></svg>'+
        '</button></span>'+
      /* 브랜드 · 상품명은 사진을 가리지 않게 사진 아래에 적는다 */
      '<span class="wlTag"><b>'+trEsc(item.brand||item.source||'상품')+'</b>'+
        '<span>'+trEsc(item.name)+'</span></span></div>';
  }).join('');
}
function stockDiscountDial(product, selected){
  if(!selected)return '<button type="button" class="stockPickerDialEmpty" data-stock-add'+
    ' aria-label="세부 검색에서 할인률 상품 추가"><b>+</b><small>상품 추가</small></button>';
  const rate=product?.discount_rate==null?null:Number(product.discount_rate);
  const hasRate=Number.isFinite(rate)&&rate>=0&&rate<=100;
  const image=stockSafeImg(product?.image||selected?.thumb||selected?.image);
  return '<button type="button" class="'+(hasRate?'dial ':'')+'stockPickerDial'+(hasRate?'':' no-rate')+'"'+
    ' data-stock-clear aria-label="선택한 상품 해제" title="한 번 더 누르면 선택 해제">'+
    '<span class="stockDialPhoto">'+(image?'<img src="'+trEsc(image)+'" alt="'+trEsc(product?.name||selected?.label||'선택 상품')+'">':'')+'</span>'+
    '<svg viewBox="0 0 120 120">'+
    '<circle class="trk" cx="60" cy="60" r="56"/>'+
    (hasRate?'<circle class="val" cx="60" cy="60" r="56" data-ramp="#ff6b4a" data-score="'+rate+'" '+
      'stroke-dasharray="351.86" stroke-dashoffset="351.86"/>':'')+'</svg>'+
    '<span class="num"><b>'+(hasRate?'0':'–')+'</b><small>'+(hasRate?'% OFF':product?'할인율 없음':'가격 확인 중')+'</small></span></button>';
}
function stockSummaryHTML(product, selected){
  if(!selected)return '<p class="stockSummaryEmpty">상품을 고르면 이곳에 정가·할인가·관측 기간 최저가가 표시됩니다.</p>';
  if(!product)return '<p class="stockSummaryEmpty">선택한 상품의 가격 정보를 확인 중입니다.</p>';
  const discount=product.discount_rate;
  const days=product.observed_days||0;
  const asOf=String(product.observed_at||'').slice(0,10);
  return '<div class="stockSummaryContent">'+
    '<span class="stockEyebrow">'+trEsc([product.brand,product.source].filter(Boolean).join(' · '))+'</span>'+
    '<h4 title="'+trEsc(product.name)+'">'+trEsc(product.name)+'</h4>'+
    '<p class="stockSummaryStatus"><em>'+(discount==null?'할인율 확인 중입니다.':discount+'% 할인 중입니다.')+'</em></p>'+
    '<p class="stockSummaryPrices">정가 '+trWon(product.list_price)+' → 현재 판매가 <strong>'+trWon(product.sale_price)+'</strong></p>'+
    '<div class="stockSummaryMetrics">'+
      '<div><b>'+trWon(product.list_price)+'</b><span>정가</span></div>'+
      '<div><b>'+trWon(product.sale_price)+'</b><span>할인가</span></div>'+
      '<div><b>'+(discount==null?'–':discount+'%')+'</b><span>할인율</span></div>'+
      '<div><b>'+(days>=2?trWon(product.history_min_price):'–')+'</b><span>관측 기간 최저가</span></div></div>'+
    '<p class="stockSummaryAsOf">'+(asOf?trEsc(asOf)+' 기준 · ':'관측일 미확인 · ')+'가격 관측 '+days+'일</p></div>';
}
function stockPaintSaveButton(){
  const button=$('#dzSaveBtn'), error=$('#dzSaveError'), selected=FS.stockItem;
  if(!button){
    if(error){ error.hidden=!stockSaveError; error.textContent=stockSaveError; }
    return;
  }
  const saved=!!selected&&STOCK_SAVED.items.some(item=>Number(item.id)===selected.id);
  button.hidden=!selected;
  button.disabled=stockSavePending||STOCK_SAVED.status!=='ok';
  button.classList.toggle('on',saved);
  button.setAttribute('aria-pressed',String(saved));
  button.textContent=stockSavePending?'저장 중…':STOCK_SAVED.status==='error'?'찜 사용 불가':
    STOCK_SAVED.status!=='ok'?'찜 확인 중':saved?'♥ 찜목록에서 제거':'♡ 찜목록에 추가';
  button.title=STOCK_SAVED.status==='error'?STOCK_SAVED.error:'';
  const message=stockSaveError||(selected&&STOCK_SAVED.status==='error'?STOCK_SAVED.error:'');
  if(error){error.hidden=!message;error.textContent=message;}
}
function stockPaintPicker(product=null){
  const selected=FS.stockItem;
  const list=$('#dzWishListBody');
  const dial=$('#stockDiscountSlot'), summary=$('#stockPickerSummary');
  if(stockLastSelectionId!==selected?.id){stockSaveError='';stockLastSelectionId=selected?.id||null;}
  if(product)stockCurrentProduct=product;
  else if(!selected||stockCurrentProduct?.id!==selected.id)stockCurrentProduct=null;
  product=product||stockCurrentProduct;
  if(list){
    const scrollTop=list.scrollTop;
    list.innerHTML=stockWishlistHTML();
    list.scrollTop=scrollTop;
    /* 높이는 CSS 가 잡는다 — 상자는 왼쪽 지표와 같은 세로 길이를 유지하고,
       카드가 넘치면 이 안에서만 스크롤한다. */
    list.style.maxHeight='';
  }
  if(dial)dial.innerHTML=stockDiscountDial(product,selected);
  if(summary)summary.innerHTML=stockSummaryHTML(product,selected);
  stockPaintSaveButton();
}
async function stockToggleSaved(){
  const selected=FS.stockItem;
  if(!selected||stockSavePending||STOCK_SAVED.status!=='ok')return;
  const saved=STOCK_SAVED.items.some(item=>Number(item.id)===selected.id);
  const product=stockCurrentProduct?.id===selected.id?stockCurrentProduct:null;
  stockSavePending=true; stockSaveError=''; stockPaintSaveButton();
  try{
    const result=await setSavedProduct({itemId:'db-'+selected.id,liked:!saved,
      name:product?.name||selected.label,brand:product?.brand||selected.brand});
    if(!saved){
      STOCK_SAVED.items=[{id:selected.id,name:product?.name||selected.label,
        brand:product?.brand||selected.brand,source:product?.source||selected.source,
        image:product?.image||selected.thumb,list_price:product?.list_price,
        sale_price:product?.sale_price,discount_rate:product?.discount_rate},...STOCK_SAVED.items];
    }else STOCK_SAVED.items=STOCK_SAVED.items.filter(item=>Number(item.id)!==selected.id);
    if(Number.isFinite(Number(result.saved_count)))ME.saved=Number(result.saved_count);
    if(FS.stockItem?.id===selected.id)stockPaintPicker(product);
    document.dispatchEvent(new CustomEvent('feedit:saved'));
  }catch(e){
    stockSaveError=e.message||'찜 상태를 바꾸지 못했습니다. 다시 시도해 주세요.';
  }finally{
    stockSavePending=false; stockPaintSaveButton();
  }
}
/* ★ 2026-09-19 — 찜 목록 카드의 하트. 스타일 페이지와 같게 다시 누르면 찜이 풀린다.
   풀린 상품이 지금 고른 상품이면 선택도 같이 푼다. */
async function stockUnsave(item){
  if(!item||stockSavePending)return;
  stockSavePending=true; stockSaveError='';
  try{
    const result=await setSavedProduct({itemId:'db-'+item.id,liked:false,
      name:item.name,brand:item.brand});
    STOCK_SAVED.items=STOCK_SAVED.items.filter(x=>Number(x.id)!==Number(item.id));
    if(Number.isFinite(Number(result.saved_count)))ME.saved=Number(result.saved_count);
    const wasPicked=FS.stockItem?.id===Number(item.id);
    stockSavePending=false;
    if(wasPicked){ fsStockClear(); fsChipsPaint(); trRender('stock'); }
    else stockPaintPicker();
    document.dispatchEvent(new CustomEvent('feedit:saved'));
  }catch(e){
    stockSaveError=e.message||'찜 상태를 바꾸지 못했습니다. 다시 시도해 주세요.';
    stockSavePending=false;
    stockPaintPicker();
  }finally{ stockSavePending=false }
}
function stockChoose(item){
  if(!item||!Number.isSafeInteger(Number(item.id)))return;
  /* 같은 카드를 다시 누르면 선택을 푼다 */
  if(FS.stockItem&&FS.stockItem.id===Number(item.id)){
    fsStockClear(); fsChipsPaint(); trRender('stock'); return;
  }
  FS.pick={}; FS.colq={};
  const input=$('#fsInput'); if(input)input.value='';
  const clear=$('#fsClear'); if(clear)clear.hidden=true;
  if(!fsStockSelect(item))return;
  fsChipsPaint();
  trRender('stock');
}
function stockWirePicker(){
  /* 찜 카드는 클릭하거나 현재 할인율 원형으로 드래그해서 고른다. */
  const list=$('#dzWishListBody');
  if(!list)return;
  const slot=$('#stockDiscountSlot');
  const itemOf=id=>STOCK_SAVED.items.find(item=>item.id===Number(id));
  list.addEventListener('click',event=>{
    if(event.target.closest('[data-stock-retry]')){
      STOCK_SAVED.status='idle'; STOCK_SAVED.loadedAt=0; stockLoadSaved(); return;
    }
    const heart=event.target.closest('[data-wish-off]');
    if(heart){ event.stopPropagation(); stockUnsave(itemOf(heart.dataset.wishOff)); return; }
    const row=event.target.closest('[data-source-id]');
    if(row)stockChoose(itemOf(row.dataset.sourceId));
  });
  list.addEventListener('keydown',event=>{
    const row=event.target.closest('[data-source-id]');
    if(!row||(event.key!=='Enter'&&event.key!==' '))return;
    event.preventDefault();
    stockChoose(itemOf(row.dataset.sourceId));
  });
  list.addEventListener('dragstart',event=>{
    const row=event.target.closest('[data-source-id]');
    if(!row||!event.dataTransfer)return;
    event.dataTransfer.effectAllowed='copy';
    event.dataTransfer.setData('text/feedit-stock-id',row.dataset.sourceId);
    event.dataTransfer.setData('text/plain',row.dataset.sourceId);
    row.classList.add('dragging');
  });
  list.addEventListener('dragend',event=>{
    event.target.closest('[data-source-id]')?.classList.remove('dragging');
    slot?.classList.remove('dragover');
  });
  if(slot){
    slot.addEventListener('click',event=>{
      if(event.target.closest('[data-stock-add]'))fsOpenPop();
      else if(event.target.closest('[data-stock-clear]')){
        fsStockClear(); fsChipsPaint(); trRender('stock');
      }
    });
    slot.addEventListener('dragenter',event=>{ event.preventDefault(); slot.classList.add('dragover'); });
    slot.addEventListener('dragover',event=>{
      event.preventDefault();
      if(event.dataTransfer)event.dataTransfer.dropEffect='copy';
      slot.classList.add('dragover');
    });
    slot.addEventListener('dragleave',event=>{
      if(!slot.contains(event.relatedTarget))slot.classList.remove('dragover');
    });
    slot.addEventListener('drop',event=>{
      event.preventDefault(); slot.classList.remove('dragover');
      const id=event.dataTransfer?.getData('text/feedit-stock-id')||event.dataTransfer?.getData('text/plain');
      const item=itemOf(id);
      if(item&&FS.stockItem?.id!==Number(item.id))stockChoose(item);
    });
  }
  $('#dzSaveBtn')?.addEventListener('click',stockToggleSaved);
}

/* 조회를 이미 한 번 보냈다고 표시한다.
   kwGo 가 직접 prime 을 부른 뒤 이걸 찍어 두면, 이어서 도는 trRender 의
   선반입이 **같은 것을 또 묻지 않는다.** (한 번 눌렀는데 두 번 나가던 자리) */
export function markTried(kw){ if(kw) TR_TRIED[kw]=Date.now(); }

/* ── 내 피드 · 내 관심 코어의 시장 화제성 ──
   '즐겨입는 스타일'(ME.styles, 가입 팝업 · 마이페이지에서 고른 것)만 버튼으로 세우고,
   누른 한 개의 화제성만 보여 준다. 다른 스타일은 섞지 않는다.
   ★ 2026-09-17 · 시드 난수를 걷어내고 실데이터로 바꿨다.
     화제성 = /api/trend 의 트렌드 온도(term_metric_daily.trend_temperature)
     주간 변화 = 7일 전 대비 온도 차 · 단계 = /api/lifecycle 의 수명주기 판정
     값이 없으면 숫자를 지어내지 않고 '–' 와 사유를 적는다. */
let TP_PICK=null;
const TP_RISE=['태동','확산'];   /* /api/lifecycle 단계 중 '올라가는' 구간 */
/* 받침 조사 — 영문 이름(Y2K)은 끝 글자를 읽는 소리로 고른다 (L·M·N·R 은 받침) */
const tpJosa=(w,a,b)=>/[A-Za-z0-9]$/.test(w)?(/[LMNRlmnr1368]$/.test(w)?a:b):josa(w,a,b);
function tpMine(){ return STYLES.filter(s=>ME.styles.has(s.id)) }
const lcUrl=n=>'/api/lifecycle?term='+encodeURIComponent(n);

/* 스타일 하나의 실지표를 캐시에서 꺼낸다 (받는 건 tpLoad 가 한다).
   state: loading(아직 안 받음) · none(지표 없음) · ok */
function tpLive(s){
  const st=stateOf(s.n), L=stateOfUrl(lcUrl(s.n));
  if(st.status==='unknown'||L.status==='unknown')return {state:'loading'};
  const S=summaryOf(s.n);
  if(!S||S.temp==null)return {state:'none',reason:st.status==='ok'?'트렌드 온도가 아직 계산되지 않았습니다.':(st.reason||'측정된 자료가 없습니다.')};
  /* 최근 7일 · 그 전 7일 언급량 합 (마지막 적재일 기준) */
  const E=entryOf(s.n), rows=E&&E.byDate?[...E.byDate.values()]:[];
  const inWin=(r,lo,hi)=>{ const d=trDayDiff(r.date,S.asOf); return d>=lo&&d<hi };
  const m7=rows.filter(r=>inWin(r,0,7)).reduce((a,r)=>a+(+r.mention||0),0);
  const m7p=rows.filter(r=>inWin(r,7,14)).reduce((a,r)=>a+(+r.mention||0),0);
  return {state:'ok',temp:Math.round(S.temp),wk:S.tempWk==null?null:Math.round(S.tempWk),
    stage:L.status==='ok'&&L.data?L.data.stage:null,m7,m7p,asOf:S.asOf};
}
/* 고른 스타일들의 온도 · 수명주기를 한꺼번에 받아 두고, 다 받으면 done 을 부른다 */
function tpLoad(list,done){
  if(!list.length)return;
  Promise.allSettled(list.flatMap(s=>[prime(s.n),primeUrl(lcUrl(s.n))])).then(()=>done&&done());
}
function tpHeroHTML(){
  const mine=tpMine();
  if(!mine.length){
    return '<div class="tpPulseTop"><span class="tpTag">TREND ALIGNMENT</span></div>'+
      '<div class="tpPulseCopy"><strong>내 관심 코어의 시장 화제성</strong>'+
        '<p>아직 고른 즐겨입는 스타일이 없습니다.<br>마이페이지에서 스타일을 고르면 여기서 하나씩 확인할 수 있어요.</p>'+
        '<div class="tpTasteTags"><button type="button" data-v="mypage">스타일 고르러 가기 →</button></div>'+
      '</div>';
  }
  if(!mine.some(s=>s.id===TP_PICK))TP_PICK=mine[0].id;
  const cur=mine.find(s=>s.id===TP_PICK);
  const L=tpLive(cur);
  const tabs='<div class="tpTasteTags" role="tablist">'+mine.map(s=>
        '<button type="button" role="tab" data-tp-style="'+s.id+'" aria-selected="'+(s.id===TP_PICK)+'"'+
        (s.id===TP_PICK?' class="on"':'')+'>'+s.n+'</button>').join('')+'</div>';
  let delta='', deg='–', copy;
  if(L.state==='loading'){
    copy='<b>'+cur.n+'</b>의 트렌드 온도를 불러오는 중입니다…';
  } else if(L.state==='none'){
    copy='<b>'+cur.n+'</b>'+tpJosa(cur.n,'은','는')+' 아직 화제성을 잴 자료가 없습니다.<br>'+trEsc(L.reason);
  } else {
    deg=L.temp;
    delta=L.wk==null?'<span class="tpDelta">지난주 비교 불가</span>'
      :'<span class="tpDelta">'+(L.wk>0?'▲ ':L.wk<0?'▼ ':'– ')+Math.abs(L.wk)+'° 지난주 대비</span>';
    copy='<b>'+cur.n+'</b>'+tpJosa(cur.n,'은','는')+' '+
      (L.stage?'지금 <b>'+L.stage+'</b> 구간입니다. ':'수명주기 단계는 아직 판정할 자료가 부족합니다. ')+
      '최근 7일 언급 '+L.m7.toLocaleString()+'건(지난주 '+L.m7p.toLocaleString()+'건) · '+trEsc(L.asOf)+' 기준';
  }
  return '<div class="tpPulseTop"><span class="tpTag">TREND ALIGNMENT · '+cur.en.toUpperCase()+'</span>'+delta+'</div>'+
    '<div class="tpBigDeg">'+deg+(deg==='–'?'':'<em>°</em>')+'</div>'+
    '<div class="tpPulseCopy"><strong>내 관심 코어의 시장 화제성</strong>'+
      '<p>'+copy+'</p>'+tabs+
    '</div>';
}
/* ── 내 관심 스타일 최근 7일 언급량 ──
   화제성 카드와 같은 출처(ME.styles · /api/trend)를 쓴다. 지난주 같은 기간 대비 증감을 붙인다. */
function tpSignalHTML(){
  const mine=tpMine();
  const lives=mine.map(s=>[s,tpLive(s)]);
  const loading=lives.some(x=>x[1].state==='loading');
  const ok=lives.filter(x=>x[1].state==='ok');
  const total=ok.reduce((a,x)=>a+x[1].m7,0);
  const head='<div class="tpSignalHead"><span>LAST 7 DAYS · MENTIONS</span><i class="tpLiveDot"></i></div>';
  let num, p, list='';
  if(!mine.length){ num='–'; p='즐겨입는 스타일을 고르면 그 스타일의 최근 언급량을 모아 보여 드립니다.' }
  else if(loading){ num='–'; p='내 관심 스타일의 언급량을 불러오는 중입니다…' }
  else if(!ok.length){ num='–'; p='고른 스타일에 측정된 언급량이 아직 없습니다.' }
  else {
    num=total.toLocaleString();
    p='수집된 글·영상·리뷰에서 내 관심 스타일이 언급된 건수입니다. 옆 숫자는 지난주 같은 기간 대비 증감입니다.';
    list='<div class="tpSignalList">'+lives.map(([s,L])=>{
      if(L.state!=='ok')return '<span>'+s.n+' <b>–</b></span>';
      const d=L.m7-L.m7p;
      return '<span>'+s.n+' '+L.m7.toLocaleString()+'건 <b>'+(d>0?'+':'')+d.toLocaleString()+'</b></span>';
    }).join('')+'</div>';
  }
  return head+'<div class="tpSignalNum">'+num+'<em>mentions</em></div>'+
    '<div><h4>내 관심 스타일 최근 7일 언급량</h4><p>'+p+'</p>'+list+'</div>';
}
function tpBriefHTML(){
  const mine=tpMine();
  const lives=mine.map(s=>[s,tpLive(s)]);
  const ok=lives.filter(x=>x[1].state==='ok');
  const rise=ok.filter(x=>TP_RISE.includes(x[1].stage));
  let tx;
  if(!mine.length){
    tx='아직 고른 즐겨입는 스타일이 없습니다. 스타일을 고르면 매일 이 자리에서 취향 브리핑을 드립니다.';
  }else if(lives.some(x=>x[1].state==='loading')){
    tx='내 관심 스타일의 트렌드 지표를 불러오는 중입니다…';
  }else if(!ok.length){
    tx='고른 스타일에 측정된 트렌드 지표가 아직 없어 브리핑을 만들지 못했습니다.';
  }else{
    tx=lives.map(([s,L])=>L.state==='ok'
        ? s.n+tpJosa(s.n,'은','는')+' 온도 '+L.temp+'°'+(L.stage?'로 '+L.stage+' 구간':'')
        : s.n+tpJosa(s.n,'은','는')+' 지표 없음').join(', ')+'입니다. '+
      (rise.length
        ? '지금은 '+rise.map(x=>x[0].n).join(' · ')+' 쪽이 올라가는 구간이라 "완전 유행 전" 아이템을 고르기 좋은 타이밍이에요.'
        : '고른 스타일 중 올라가는(태동·확산) 구간은 없어, 새로 사기보다 가진 옷을 활용하기 좋은 시기예요.');
  }
  return '<div class="tpBriefNo">01</div>'+
    '<div class="tpBriefText"><b>오늘의 취향 브리핑</b><p>'+tx+'</p></div>'+
    '<div class="tpBriefScore"><b>'+rise.length+'</b> CORE RISING</div>';
}
/* 받아 온 뒤 카드 세 장 안만 갈아 끼운다 */
function tpRepaint(){
  const h=$('#tpHero'); if(h)h.innerHTML=tpHeroHTML();
  const g=$('#tpSignal'); if(g)g.innerHTML=tpSignalHTML();
  const b=$('#tpBrief'); if(b)b.innerHTML=tpBriefHTML();
}
/* 즐겨입는 스타일이 바뀌면(가입 팝업 · 마이페이지) 내 피드 카드 세 장을 다시 채운다 */
document.addEventListener('feedit:styles',()=>{
  /* 내 피드가 열려 있으면 맞춤 살!말? 카드까지 통째로 다시 고른다 */
  if($('#tpSalGrid')){ trRender('myfeed'); return }
  tpRepaint(); tpLoad(tpMine(),tpRepaint);
});

/* 버튼을 누르면 카드 안만 갈아 끼운다 — 본문 전체를 다시 그리면 등장 애니메이션이 또 돈다 */
document.addEventListener('click',e=>{
  const b=e.target.closest('#tpHero [data-tp-style]'); if(!b)return;
  TP_PICK=b.dataset.tpStyle;
  const h=$('#tpHero'); if(h)h.innerHTML=tpHeroHTML();
});

/* ══════════════════════════════════════════════════════
   실데이터 공용 도우미 — 할인률 · 리세일 · 수명주기 · 연관어
   ══════════════════════════════════════════════════════ */
/* DB 에서 온 글자는 반드시 이스케이프해서 넣는다 */
function trEsc(v){ return String(v==null?'':v).replace(/[&<>"']/g,m=>(
  {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])) }
let RESALE_MODE='buy', RESALE_REC_OFFSET=0, RESALE_REC_KEY='';
document.addEventListener('error',e=>{
  if(e.target&&e.target.matches&&e.target.matches('.resaleIdentityImg img,.resaleRecImg img')){
    e.target.parentElement?.classList.add('imageError');
  }
},true);
document.addEventListener('click',e=>{
  const more=e.target.closest&&e.target.closest('[data-resale-more]');
  if(more){
    RESALE_REC_OFFSET+=5;
    if(TR_CUR==='resale')trRender('resale');
    return;
  }
  const rec=e.target.closest&&e.target.closest('[data-resale-rec-id]');
  if(rec){
    fsResaleSelect({id:Number(rec.dataset.resaleRecId),type:rec.dataset.resaleRecType,
      name:rec.dataset.resaleRecName,brand:rec.dataset.resaleRecBrand||'',
      image:rec.dataset.resaleRecImage||'',model_code:rec.dataset.resaleRecCode||'',platforms:[]});
    fsChipsPaint();
    if(TR_CUR==='resale')trRender('resale');
    return;
  }
  const b=e.target.closest&&e.target.closest('[data-resale-mode]');
  if(!b||!['buy','sell'].includes(b.dataset.resaleMode))return;
  RESALE_MODE=b.dataset.resaleMode;
  if(TR_CUR==='resale')trRender('resale');
});
/* 검색/언급 출처는 내부 계산용이다. 예전 적재값에 꼬리표가 문자열로 남아 있어도
   사용자가 보는 연관어 이름에는 노출하지 않는다. */
function assocDisplayTerm(v){
  return String(v==null?'':v).replace(/\s*\((?:검색|둘\s*다)\)\s*$/u,'').trim();
}
const wkMetric = value => Number(value||0).toLocaleString('ko-KR');
async function wkLoadVideo(term){
  const host=$('#wkVideoRec');
  if(!host)return;
  const badge0=$('#wkVideoBadge'); if(badge0)badge0.textContent=term||'취향 기반';
  try{
    const data=await weeklyVideos(term);
    if(!host.isConnected)return;
    const video=(data.items||[])[0];
    if(!video)throw new Error('추천할 수 있는 영상이 아직 없습니다.');
    const metrics=video.metrics||{};
    host.innerHTML=
      '<div class="wkVideoFrame"><iframe src="'+trEsc(video.embed_url)+'" '+
        'title="'+trEsc(video.title)+'" loading="lazy" allow="accelerometer; autoplay; clipboard-write; '+
        'encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>'+
      '<div class="wkVideoInfo"><span><b>'+trEsc(video.channel||'YouTube')+'</b>'+trEsc(video.title)+'</span>'+
        '<a href="'+trEsc(video.url)+'" target="_blank" rel="noopener">YouTube에서 보기 ↗</a></div>'+
      '<div class="wkNote"><i>◆</i><span><b>'+trEsc(video.reason)+'</b> 취향과 맞고, '+
        '조회 '+wkMetric(metrics.views)+'회 · 좋아요 '+wkMetric(metrics.likes)+'개 · 댓글 '+
        wkMetric(metrics.comments)+'개인 영상입니다.</span></div>';
    const badge=$('#wkVideoBadge');
    if(badge)badge.textContent=term||video.reason||'취향 기반';
  }catch(error){
    if(!host.isConnected)return;
    host.innerHTML='<div class="wkVideoEmpty"><b>추천 영상을 불러오지 못했습니다.</b><span>'+trEsc(error.message||'잠시 뒤 다시 확인해 주세요.')+'</span></div>';
  }
}
/* ── 금주의 리포트 · 활동 지표 (/api/auth/weekly-report) ──
   ★ 2026-09-17 · 검색 수 · 챗봇 시간 · 요일별 활동 · 취향 지분을 WK 목업에서 실기록으로 바꿨다.
     서버가 user_event(검색·투표·찜·챗봇)와 chat_session 으로 이번 주(월~일, KST)를 집계한다.
     받기 전에는 '…', 실패하면 사유를 적는다. 숫자를 지어내지 않는다. */
let WR={state:'loading',data:null,reason:''};
const WK_DAY=['월','화','수','목','금','토','일'];
/* ★ 2026-09-19 — 기다리는 자리에 '…' · '–' 같은 글자를 박아 두지 않는다.
   점 세 개가 차례로 뛰는 표시(wkDots)와, 값 자리를 지키는 뼈대(wkSkel)로 대신하고
   실제 값이 오면 그 자리에서 숫자가 굴러 올라온다(trCountUp). */
const WK_DOTS=(cls)=>'<span class="wkDots'+(cls?' '+cls:'')+'"><i></i><i></i><i></i></span>';
/* 히어로 이미지 로딩 — 원형 스피너 + 작은 안내 문구 */
const WK_HERO_LOAD='<span class="wkHeroSpin" aria-hidden="true"></span>'+
  '<small>키워드 이미지를 불러오고 있어요</small>';
/* 값 자리 로딩 — 회색 뼈대 대신 점 세 개를 둔다 */
const WK_SKEL=(cls)=>WK_DOTS('val'+(cls?' '+cls:''));
const wkSign=n=>(n>0?'+':'')+n;
/* ── 이번 주 리포트의 축 = 가장 많이 검색한 키워드 ──
   ★ 2026-09-17 · 한 줄 요약 · 히어로 카드 · 추천 영상 · 추천 웹매거진이 모두 같은 키워드를 말한다.
     키워드는 스타일만이 아니다 — 브랜드 · 아이템 · 색상 · TPO 등 검색창에서 확정한 모든 말이 된다.
     이번 주 검색 기록이 없으면 내 첫 번째 관심 스타일(없으면 대표 스타일)로 대신하고, 그렇다고 적는다.
     (내 취향 지분은 같은 검색 기록 중 스타일만 따로 나눠 본다 — activity.py _taste_block) */
let WKEY=null;   /* {label, facet, style:STYLES 항목|null, from:'search'|'style'} */
function wkKeyword(fallback){
  const d=WR.data, top=d&&d.search&&d.search.top;
  const norm=x=>String(x||'').trim();
  const byName=n=>STYLES.find(s=>norm(s.n)===norm(n))||null;
  if(top&&top.label)return {label:top.label,facet:top.facet||(byName(top.label)?'스타일':''),style:byName(top.label),from:'search'};
  return {label:fallback.n,facet:'스타일',style:fallback,from:'style'};
}
function wkLineHTML(K,rp){
  const h=!K?'<h2>이번 주 가장 관심 있었던 키워드를 확인하고 있습니다…</h2>'
    :K.from==='search'?'<h2>이번 주 가장 관심 있었던 키워드는 <em>'+trEsc(K.label)+'</em>입니다.</h2>'
    :'<h2>이번 주 검색 기록이 없어 관심 스타일 <em>'+trEsc(K.label)+'</em>의 흐름을 보여 드립니다.</h2>';
  return h+'<span>'+rp.join(' · ')+' · 매주 '+WK.updateDay+' 갱신</span>';
}
/* 히어로 카드 — 이미지 · 키워드 이름 · 트렌드 온도 3칸 · 더 보기 버튼 */
function wkHeroHTML(K){
  if(!K)return '<div class="wkHeroImg wkHeroType wkHeroLoad">'+WK_HERO_LOAD+'</div>'+
    '<div class="wkCopy"><div class="wkState">THIS WEEK</div><h3>'+WK_DOTS('md')+'</h3>'+
    '<div class="wkLedger c3">'+wkLedgerHTML(null)+'</div>'+
    '<button type="button" class="pill sm wkBtnWait" style="margin-top:20px" disabled>→ 언급량 · 온도에서 보기</button>'+
    '</div>';
  const sub=K.style?K.style.en:(K.facet||'KEYWORD');
  /* 스타일은 스타일 대표 사진, 그 밖의 키워드는 관련 상품 사진을 받아 온 뒤 채운다(wkHeroImage) */
  const img=K.style
    ? '<div class="wkHeroImg"><img src="'+SIMG(K.style)+'" alt="'+trEsc(K.label)+'" loading="lazy"></div>'
    : '<div class="wkHeroImg wkHeroType wkHeroLoad" id="wkHeroImg">'+WK_HERO_LOAD+'</div>';
  const btn=K.style
    ? '<button type="button" class="pill sm" style="margin-top:20px" data-fit-style="'+K.style.id+'">→ 이 스타일 더 보기</button>'
    : '<button type="button" class="pill sm" style="margin-top:20px" data-tr="temp" data-wk-kw="'+trEsc(K.label)+'" data-wk-facet="'+trEsc(K.facet||'')+'">→ 언급량 · 온도에서 보기</button>';
  return img+
    '<div class="wkCopy">'+
      '<div class="wkState">THIS WEEK · '+(K.from==='search'?'가장 많이 검색한 키워드':'내 관심 스타일')+'</div>'+
      '<h3>'+trEsc(K.label)+' <em>'+trEsc(sub)+'</em></h3>'+
      '<div class="wkLedger c3" id="wkHeroLedger">'+wkLedgerHTML({n:K.label})+'</div>'+
      btn+
    '</div>';
}
/* 스타일이 아닌 키워드의 히어로 사진 — /api/products 의 첫 상품 사진. 없으면 글자 판을 그대로 둔다 */
/* ★ 상품 사진이 없을 때 — 글자판 대신 '이 키워드와 가장 가까운 스타일'의 대표컷을 세운다.
   색 · TPO · 시즌처럼 상품 한 장으로 설명되지 않는 말도 옷 사진으로 받는다.
   ① /api/assoc 의 연관어 중 STYLE 을 먼저 찾고 ② 없으면 스타일 키워드(kw)에 그 말이 든 스타일,
   ③ 그래도 없으면 키워드 글자를 씨앗으로 늘 같은 스타일을 고른다(새로고침해도 안 바뀐다). */
async function wkAssocStyle(label){
  try{
    const r=await fetch('/api/assoc?term='+encodeURIComponent(label)+'&limit=20',{headers:{Accept:'application/json'}});
    const j=await r.json();
    const rows=(j&&j.status==='ok'&&(j.data&&(j.data.items||j.data)))||[];
    for(const row of rows){
      const hit=STYLES.find(st=>st.n===(row.term||row.label));
      if(hit)return hit;
    }
  }catch(e){}
  /* 스타일 키워드(kw)에 그 말이 실제로 들어 있을 때만 — 없으면 null 을 돌려준다.
     근거 없이 아무 스타일이나 골라 '연관 스타일'이라 적으면 거짓말이 된다. */
  return STYLES.find(st=>(st.kw||[]).some(k=>k===label))
      || STYLES.find(st=>(st.kw||[]).some(k=>k.length>1&&(k.indexOf(label)>=0||label.indexOf(k)>=0)))
      || null;
}
async function wkHeroFallback(K){
  const el=$('#wkHeroImg'); if(!el||WKEY!==K)return;
  const st=await wkAssocStyle(K.label);
  if(!el.isConnected||WKEY!==K)return;
  if(!st){
    /* 근거가 없으면 사진을 지어내지 않는다 — 키워드와 facet 만 담은 조용한 판 */
    el.classList.remove('wkHeroLoad','wkHeroType');
    el.classList.add('wkHeroPlain');
    el.innerHTML='<span class="wkHeroPlainFacet">'+trEsc(K.facet||'KEYWORD')+'</span>'+
      '<b>'+trEsc(K.label)+'</b>'+
      '<span class="wkHeroPlainNote">이 키워드를 대표할 사진을 아직 찾지 못했어요</span>';
    return;
  }
  el.classList.remove('wkHeroType','wkHeroLoad');
  el.classList.add('wkHeroAlt');
  el.innerHTML='<img src="'+trEsc(SIMG(st))+'" alt="'+trEsc(st.n)+'" loading="lazy">'+
    '<span class="wkHeroAltTag">연관 스타일 · '+trEsc(st.n)+'</span>';
}
async function wkHeroImage(K){
  if(!K||K.style)return;
  const p=new URLSearchParams({limit:'1'});
  p.set(K.facet==='브랜드'?'brand':'q',K.label);
  try{
    const r=await fetch('/api/products?'+p.toString(),{headers:{Accept:'application/json'}});
    const j=await r.json();
    const it=j&&j.status==='ok'&&j.data&&(j.data.items||j.data)[0];
    const src=it&&(it.image||it.thumbnail_url);
    if(src&&!/^https?:\/\//.test(src))return wkHeroFallback(K);
    const el=$('#wkHeroImg');
    if(src&&el&&WKEY===K){
      el.classList.remove('wkHeroType','wkHeroLoad');
      el.innerHTML='<img src="'+trEsc(src)+'" alt="'+trEsc(K.label)+'" loading="lazy" referrerpolicy="no-referrer">';
      return;
    }
    await wkHeroFallback(K);
  }catch(e){ await wkHeroFallback(K) }
}
/* '언급량 · 온도에서 보기' — 라우터가 화면을 바꾸기 전에(capture) 검색어를 넘겨 둔다 */
document.addEventListener('click',e=>{
  const b=e.target.closest&&e.target.closest('[data-wk-kw]'); if(!b)return;
  KW.q=b.dataset.wkKw; KW.f=b.dataset.wkFacet||''; KW.part='temp';
  setTimeout(()=>{ const it=$('.sItem[data-tr="temp"]'); if(it){ $$('.sItem').forEach(x=>x.classList.remove('on')); it.classList.add('on') } },0);
},true);
function wkMetricsHTML(){
  const d=WR.data, wait=WR.state!=='ok';
  const v=x=>wait?WK_SKEL():x;   /* ★ 2026-09-19 — 로딩 중에는 '–' 대신 뼈대만 두고, 값이 오면 숫자가 굴러 올라온다(trCountUp) */
  const rows=wait
    ? [['검색한 키워드','','개'],['새로 찜한 것','','개'],['살!말? 투표','','표'],['트렌드 분석','','분']]
        .map(r=>[r[0],v(),r[2],WR.state==='loading'?'불러오는 중':trEsc(WR.reason||'기록을 불러오지 못했습니다.'),0])
    : [['검색한 키워드',d.search.keywords,'개',wkSign(d.search.delta)+' · 지난주 대비',1],
       ['새로 찜한 것',d.saved.new,'개','총 '+d.saved.total+'개 추적 중',0],
       ['살!말? 투표',d.vote.count,'표',wkSign(d.vote.delta)+' · 지난주 대비',1],
       ['트렌드 분석',d.chat.minutes,'분',d.chat.sessions?'평균 사용 시간 '+d.chat.avg_minutes+'분':'이번 주 챗봇 사용 기록 없음',0]];
  return rows.map((m,i)=>'<div class="wkMetric'+(m[4]?' hot':'')+'">'+
    '<span class="idx">'+String(i+1).padStart(2,'0')+'</span>'+
    '<span class="lb">'+m[0]+'</span>'+
    '<strong>'+m[1]+'<small>'+m[2]+'</small></strong>'+
    '<em>'+m[3]+'</em></div>').join('');
}
/* 활동이 가장 몰린 2시간 구간 — '21시 – 23시' */
function wkPeakHours(hours){
  let best=-1,at=0;
  for(let h=0;h<24;h++){ const n=hours[h]+hours[(h+1)%24]; if(n>best){best=n;at=h} }
  return best>0?at+'시 – '+((at+2)%24)+'시':'–';
}
function wkDaysHTML(){
  const head=peak=>'<div class="wkCardHead"><h3>요일별 활동</h3><em>PEAK · '+peak+'</em></div>';
  if(WR.state!=='ok')return head(WR.state==='loading'?WK_DOTS('xs'):'–')+'<div class="wkNote"><i>◆</i><span>'+
    (WR.state==='loading'?'이번 주 활동 기록을 불러오는 중입니다…':trEsc(WR.reason||'활동 기록을 불러오지 못했습니다.'))+'</span></div>';
  const days=WR.data.activity.days, max=Math.max(...days), total=days.reduce((a,b)=>a+b,0);
  const today=WK_DAY[(new Date().getDay()+6)%7];
  const best=max>0?WK_DAY[days.indexOf(max)]:null;
  return head(wkPeakHours(WR.data.activity.hours))+
    '<div class="wkDays"><div class="wkBarset">'+
    WK_DAY.map((d,i)=>{const n=days[i];
      return '<div class="wkDay'+(max>0&&n===max?' peak':'')+(d===today?' today':'')+'">'+
        '<span class="v">'+n+'</span>'+
        '<span class="t"><i data-h="'+(max?Math.round(n/max*100):0)+'"></i></span>'+
        '<span class="l">'+d+'</span></div>'}).join('')+
    '</div></div>'+
    '<div class="wkNote"><i>◆</i><span>'+(total
      ? '<b>'+best+'요일</b>에 가장 많이 활동하셨습니다. 검색 · 투표 · 찜 · 챗봇 기록 '+total+'건 기준입니다. '+
        '<em class="wkNoteSub">30초 안에 취소한 찜 · 투표는 세지 않습니다.</em>'
      : '이번 주 활동 기록이 아직 없습니다. 검색 · 투표 · 찜 · 챗봇을 이용하면 이곳에 쌓입니다.')+'</span></div>';
}
function wkTasteHTML(){
  const head='<div class="wkCardHead"><h3>내 취향 지분</h3><em>VS. LAST WEEK</em></div>';
  if(WR.state!=='ok')return head+'<div class="wkNote"><i>◆</i><span>'+
    (WR.state==='loading'?'취향 지분을 계산하는 중입니다…':trEsc(WR.reason||'취향 기록을 불러오지 못했습니다.'))+'</span></div>';
  const T=WR.data.taste;
  if(!T.items.length)return head+'<div class="wkNote"><i>◆</i><span>이번 주 검색한 키워드 중 스타일이 아직 없습니다. '+
    '스타일을 검색하면 비중이 계산됩니다.</span></div>';
  return head+'<div class="wkTasteList">'+T.items.map((t,i)=>
      '<div class="wkTaste'+(i===0?' primary':'')+'"><span>'+trEsc(t.label)+'</span>'+
      '<span class="rail"><i data-w="'+t.share+'"></i></span>'+
      '<b>'+t.share+'%</b>'+
      (t.delta==null?'<em>비교 전</em>':'<em class="'+(t.delta>=0?'up':'')+'">'+wkSign(t.delta)+'%p</em>')+'</div>').join('')+
    '</div>'+
    '<div class="wkNote"><i>◆</i><span>'+(T.new_style
      ? '이번 주 새로 유입된 축은 <b>'+trEsc(T.new_style)+'</b>입니다. '
      : '')+'이번 주 검색한 스타일 '+T.signals+'건'+(T.prev_signals?' · 지난주 '+T.prev_signals+'건':' · 지난주 기록이 없어 증감은 다음 주부터 표시됩니다')+'.</span></div>';
}
/* 받아 온 뒤 칸만 다시 채운다 — 본문 전체를 다시 그리면 등장 애니메이션이 또 돈다 */
function wkActivityPaint(K,rp){
  const put=(sel,html)=>{ const el=$(sel); if(el)el.innerHTML=html; return el };
  /* ★ 2026-09-19 — 다섯 칸이 API(weekly-report) 응답 하나를 같이 기다리다 보니
     '…' 만 보이던 화면이 받는 순간 전부 한꺼번에 바뀌어 보였다. 데이터가 오는
     시점은 실제로 하나뿐이라 서버 스트리밍으로 바꿀 수는 없지만, 화면에서는
     위에서 아래로 순서대로 살아나게 해 '팝' 하고 한 번에 뜨는 느낌을 없앤다. */
  const els=[
    put('#wkLine',wkLineHTML(K,rp)),
    put('#wkHero',wkHeroHTML(K)),
    put('#wkMetrics',wkMetricsHTML()),
    put('#wkDaysCard',wkDaysHTML()),
    put('#wkTasteCard',wkTasteHTML())
  ].filter(Boolean);
  $$('#wkReport .wkDay .t i').forEach(e=>e.style.height=e.dataset.h+'%');
  $$('#wkReport .wkTaste .rail i').forEach(e=>e.style.width=e.dataset.w+'%');
  $$('#wkReport .wkMetric').forEach(e=>e.style.setProperty('--u',e.classList.contains('hot')?'38px':'22px'));
  /* ★ 2026-09-19 — 처음 들어올 때 이미 아래에서 위로 올라오는 동작(wkAnimate)을 한 번 보여 줬다.
     값이 채워질 때 또 올리면 같은 카드가 두 번 솟아 보여 산만하다 — 여기서는 은은하게 밝아지기만 한다. */
  if(HAS_A&&els.length){
    aUtils.set(els,{opacity:.45});
    aAnimate(els,{opacity:[.45,1],duration:420,delay:aStagger(70),ease:'out(3)'});
  }
  /* ★ 2026-09-19 — 내 피드 · 찜한 키워드와 같은 느낌: '…' 로 기다리게 하는 대신
     실제 값이 들어온 순간 0에서 그 값까지 숫자가 굴러 올라가다 멈춘다. */
  trCountUp();
}
async function wkActivityLoad(fallback,rp){
  WR={state:'loading',data:null,reason:''};
  try{ WR={state:'ok',data:await weeklyReport(),reason:''} }
  catch(error){
    const msg=error&&error.message||'';
    /* 404 면 서버(Django)에 /api/auth/weekly-report 가 아직 배포되지 않은 것이다 */
    WR={state:'error',data:null,reason:/\(404\)/.test(msg)?'리포트 서버에 활동 기록 기능이 아직 배포되지 않았습니다 (404).':(msg||'활동 기록을 불러오지 못했습니다.')};
  }
  if(!$('#wkReport'))return;
  /* 키워드가 정해진 뒤에 한 줄 요약 · 히어로 · 영상 · 웹매거진을 같은 키워드로 채운다 */
  const K=WKEY=wkKeyword(fallback);
  wkActivityPaint(K,rp);
  wkHeroImage(K);
  tpLoad([{n:K.label}],()=>{ const l=$('#wkHeroLedger'); if(l&&WKEY===K){ l.innerHTML=wkLedgerHTML({n:K.label}); trCountUp() } });
  wkLoadVideo(K.label);
  wkMagLoad(K.label);
  const g=$('#wkNextGrid'); if(g)g.innerHTML=wkNextHTML(K.style||{id:null});
}
/* ── 추천 웹매거진 (/api/v1/magazines) ──
   ★ 2026-09-17 · 매체 사이트 검색 링크(google site:)를 걷어내고, 관심 키워드를 다룬
     매거진 **기사로 바로** 연결한다. DB 에 매거진 자료가 없어 챗봇 서버가 웹 검색으로 찾는다.
     기준 키워드 = 이번 주 가장 많이 검색한 키워드 → 없으면 히어로 스타일.
     웹 검색은 10~20초 걸리므로 먼저 '찾는 중'을 띄우고, 도착하면 이 카드만 갈아 끼운다. */
let WM={term:'',state:'loading',items:[],reason:''};
const WM_ARROW='<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8">'+
  '<path d="M7 17L17 7M9 7h8v8"/></svg>';
function wkMagHTML(term){
  const head='<div class="wkCardHead"><h3>추천 웹매거진</h3><em>'+trEsc(term||'…')+'</em></div>';
  if(!term||WM.state==='loading')return head+
    '<div class="wkMagLoading"><i></i><span>'+(term?'‘'+trEsc(term)+'’을 다룬<br>웹매거진 기사를 찾고 있습니다.':'관심 키워드를 확인하고 있습니다.')+'</span></div>';
  if(WM.state!=='ok'||!WM.items.length)return head+
    '<div class="wkMagEmpty"><b>추천할 웹매거진 기사를 찾지 못했습니다.</b>'+
      '<span>'+trEsc(WM.reason||'잠시 뒤 다시 확인해 주세요.')+'</span>'+
      /* 웹 검색이 잘려도 챗봇은 뒤늦게 끝내고 결과를 캐시해 둔다.
         그래서 한 번 더 부르면 바로 나오는 일이 많다 — 새로고침 대신 이 버튼을 준다. */
      '<button type="button" class="wkMagRetry" data-wk-mag="'+trEsc(term||'')+'">다시 찾기</button>'+
    '</div>';
  return head+'<div class="wkMagList">'+WM.items.map(a=>
    '<a class="wkMagRow" target="_blank" rel="noopener noreferrer" href="'+trEsc(a.url)+'">'+
    '<span class="tx"><b>'+trEsc(a.magazine)+'</b><span>'+trEsc(a.title)+'</span></span>'+WM_ARROW+'</a>').join('')+
  '</div>';
}
async function wkMagLoad(term){
  WM={term,state:'loading',items:[],reason:''};
  const paint=()=>{ const el=$('#wkMagCard'); if(el&&WM.term===term)el.innerHTML=wkMagHTML(term) };
  paint();
  let next;
  try{
    /* ★ 스스로도 시간을 끊는다. 이게 없으면 중계가 매달릴 때 카드가 '찾는 중'에서
         영영 멈춰 있다 — 사용자는 고장인지 기다리는 중인지 알 수 없다.
         버셀 함수 한도(60초)보다 조금 짧게 둔다. */
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(),58000);
    let r;
    try{ r=await fetch('/api/v1/magazines?term='+encodeURIComponent(term),
      {headers:{Accept:'application/json'},signal:ctrl.signal}) }
    finally{ clearTimeout(timer) }
    const j=await r.json().catch(()=>null);
    next=j&&Array.isArray(j.articles)&&j.articles.length
      ? {term,state:'ok',items:j.articles.filter(a=>/^https?:\/\//.test(String(a.url||''))),reason:''}
      : {term,state:'empty',items:[],reason:(j&&j.error==='NOT_FOUND')
          ? '웹 검색 서버(챗봇)에 웹매거진 기능이 아직 배포되지 않았습니다.'   /* 옛 챗봇 서버는 /v1/magazines 를 모른다 */
          : (j&&(j.reason||j.error))||'웹 검색 결과가 없습니다.'};
  }catch(e){
    next={term,state:'error',items:[],
      reason:(e&&e.name==='AbortError')
        ? '웹 검색이 오래 걸려 기다리기를 멈췄습니다. 다시 찾기를 누르면 찾아 둔 결과가 나옵니다.'
        : '웹 검색 서버에 연결하지 못했습니다.'};
  }
  if(WM.term!==term)return;   /* 그사이 다른 키워드로 다시 불렀다 */
  WM=next; paint();
}
/* '다시 찾기' — 같은 키워드로 한 번 더 부른다 */
document.addEventListener('click',e=>{
  const b=e.target.closest('.wkMagRetry'); if(!b)return;
  const term=b.dataset.wkMag; if(term)wkMagLoad(term);
});

/* ── 금주의 리포트 실데이터 도우미 ── */
/* 이번 주(월~일) — ['2026.09', 'W3 · 9/14 – 9/20'] 의 두 조각 */
function wkRange(now=new Date()){
  const mon=new Date(now); mon.setDate(now.getDate()-((now.getDay()+6)%7));
  const sun=new Date(mon); sun.setDate(mon.getDate()+6);
  const md=d=>(d.getMonth()+1)+'/'+d.getDate();
  /* ★ 2026-10-01 — 월·주차는 월요일이 아니라 그 주가 끝나는 일요일 기준으로 센다.
     월요일 기준이면 달이 넘어가는 주(9/28~10/4)가 '2026.09 · W4' 로 찍혔다. */
  const wn=Math.ceil(sun.getDate()/7);
  return [sun.getFullYear()+'.'+String(sun.getMonth()+1).padStart(2,'0'),'W'+wn+' · '+md(mon)+' – '+md(sun)];
}
/* 히어로 3칸 — 트렌드 온도 · 지난주 대비 · 수명주기 단계 */
function wkLedgerHTML(s){
  const L=s?tpLive(s):{state:'loading'};
  const cell=(lb,v,ac)=>'<div'+(ac?' class="ac"':'')+'><span>'+lb+'</span><b>'+v+'</b></div>';
  if(L.state!=='ok'){
    const v=WK_SKEL('sm');   /* ★ 2026-09-19 — '–' 대신 뼈대만 두고, 값이 오면 숫자가 굴러 올라온다(trCountUp) */
    return cell('트렌드 온도',v,1)+cell('지난주 대비',v)+cell('수명주기 단계',v);
  }
  return cell('트렌드 온도',L.temp+'°',1)+
    cell('지난주 대비',L.wk==null?'–':(L.wk>0?'+':'')+L.wk+'°')+
    cell('수명주기 단계',L.stage||'판정 전');
}
/* 같이 지켜볼 스타일 3개 — 올라가는(태동·확산) 구간 먼저, 그 안에서 온도 높은 순 */
function wkNextHTML(top){
  const lives=STYLES.filter(s=>s.id!==top.id).map(s=>[s,tpLive(s)]);
  if(lives.some(x=>x[1].state==='loading'))
    return '<div class="note" data-live="loading"><i>◆</i><span>스타일별 트렌드 온도를 불러오는 중입니다…</span></div>';
  const ok=lives.filter(x=>x[1].state==='ok')
    .sort((a,b)=>(TP_RISE.includes(b[1].stage)-TP_RISE.includes(a[1].stage))||(b[1].temp-a[1].temp)).slice(0,3);
  if(!ok.length)return unavailableHTML('스타일별 트렌드 지표가 아직 없습니다.','');
  return ok.map(([s,L])=>
    '<div class="wkNextCard" data-style="'+s.id+'" style="cursor:pointer">'+
    /* ★ 2026-09-19 — 스타일 페이지(SIMG)와 같은 사진을 써서, 이름만 보고 어떤
       스타일인지 못 알아보던 카드에 얼굴을 붙였다. */
    '<div class="wkNextImg"><img src="'+SIMG(s)+'" alt="'+s.n+'" loading="lazy"></div>'+
    '<div class="wkNextHead"><i></i><b>'+s.n+'</b><span>'+(L.stage?L.stage+' · ':'')+L.temp+'°</span></div>'+
    '<p>'+s.ab+'</p></div>').join('');
}
function trWon(v){ return v==null?'–':Math.round(v).toLocaleString('ko-KR')+'원' }
function trDayDiff(a,b){ return Math.round((new Date(b)-new Date(a))/864e5) }
function trLoading(what){
  return '<div class="note" data-live="loading"><i>◆</i><span>'+what+' 불러오는 중입니다…</span></div>';
}
/* 날짜별 행 두 묶음을 날짜 기준으로 합친다 (차트에 두 계열을 겹칠 때) */
function trMergeRows(a,b){
  const m=new Map();
  (a||[]).concat(b||[]).forEach(r=>{ if(!r||!r.date)return;
    const k=String(r.date).slice(0,10); m.set(k,Object.assign(m.get(k)||{date:k},r)); });
  return [...m.values()].sort((x,y)=>x.date<y.date?-1:1);
}
/* 지표(온도)를 물을 대표 용어 — 상품명에는 지표가 없으므로 브랜드 › 종류 › 스타일 › 속성 순 */
function fsTerm(){
  const p=FS.pick||{};
  for(const ax of ['브랜드','종류','스타일','소재','색','디테일','TPO']){ const a=p[ax]; if(a&&a.length)return a[0]; }
  return '';
}
/* 세부 검색에서 고른 조건을 그대로 API 주소로 옮긴다 */
const EDIT_API = { stock: '/api/discount', resale: '/api/resale', life: '/api/lifecycle' };
function editUrl(id) {
  const p = new URLSearchParams();
  if(id==='stock'&&FS.stockItem){
    /* ★ 2026-09-22 — 할인률은 **고른 상품 하나**로만 조회한다.
       세부 검색의 스타일·브랜드·카테고리는 후보를 좁히는 체일 뿐이라
       대표 용어(term)로 넘기지 않는다 — 넘기면 고르지도 않은 브랜드가
       이 상품의 지표인 것처럼 섞인다. */
    p.set('source_id',String(FS.stockItem.id));
    return EDIT_API[id]+'?'+p.toString();
  }
  if(id==='resale'&&FS.resaleItem){
    p.set(FS.resaleItem.type==='product'?'product_id':'source_id',String(FS.resaleItem.id));
    return EDIT_API[id]+'?'+p.toString();
  }
  getFsCols().forEach(c => (FS.pick[c.ax] || []).forEach(v => p.append(c.param, v)));
  const t = fsTerm(); if (t) p.set('term', t);
  return EDIT_API[id] + '?' + p.toString();
}
/* 받아 둔 값이 있으면 data 를, 아니면 '불러오는 중' / '측정 불가' 를 그리고 null 을 준다 */
function editGate(body,url,what){
  const st=stateOfUrl(url);
  if(st.status==='unknown'){ body.innerHTML=trLoading(what); return null; }
  if(st.status!=='ok'){
    body.innerHTML=unavailableHTML(st.reason,
      st.detail || (st.status==='error'?'연결이 되면 자동으로 실제 값이 뜹니다.':''));
    return null;
  }
  return st.data;
}
/* 한 번만 묻고, 도착하면 그 탭이 아직 열려 있을 때만 다시 그린다 */
function primeOnce(id,url){
  const now=Date.now();
  if(stateOfUrl(url).status==='unknown' && now-(TR_TRIED[url]||0)>3000){
    TR_TRIED[url]=now;
    primeUrl(url).then(()=>{ if(TR_CUR===id) trRender(id); });
  }
}

/* 검색 지표 주소 — 창은 화면 기본(7일)보다 넉넉히 받아 두고 그릴 때 자른다. */
function searchUrl(term){
  return '/api/search?term='+encodeURIComponent(term)+'&days=90';
}

/* 검색량 카드. 값이 없으면 지어내지 않고 '아직 없음'을 적는다. */
function searchCardHTML(term){
  if(!term) return '';
  const st=stateOfUrl(searchUrl(term));
  const head='<div class="panelC" style="margin-top:12px"><div class="ph">'+
    '<h3>검색량</h3><em>네이버 · 구글</em></div>';
  if(st.status==='unknown')
    return head+'<div class="note" data-live="loading"><i>◆</i><span>검색 지표를 불러오는 중입니다…</span></div></div>';
  if(st.status!=='ok')
    return head+unavailableHTML(st.reason||'검색 지표가 아직 없습니다.',
      st.detail||'수집(collect_search_signals)이 돌면 채워집니다.')+'</div>';

  const D=st.data||{}, V=D.volume||{}, by=V.by_source||{};
  const n=by.naver, g=by.google, sh=V.share;
  const num=v=>v==null?'–':Number(v).toLocaleString('ko-KR');

  /* 절대 검색량 — 두 플랫폼은 집계 방식이 달라 **합계가 의미 없다**.
     ★ 2026-09-23 — 표를 걷어냈다. 값이 두 개뿐이라 표는 과하고, 정작 중요한
       '어느 쪽에서 더 찾는가'가 숫자 사이에 묻혔다.
       절대값은 숫자 그대로 세우고(스탯 타일), 비교는 100% 비중 막대 한 줄로 끝낸다.
       색만으로 읽히지 않게 이름과 %를 반드시 함께 단다. */
  let rows='';
  if(n||g){
    const tile=(label,d,pct)=>'<div class="svcKpi"><span>'+label+'</span>'+
      '<b>'+num(d&&d.total)+'</b>'+(pct==null?'':'<em>'+pct+'%</em>')+'</div>';
    rows='<div class="svcColsHead"><h4>플랫폼별</h4></div>'+
      '<div class="svcKpis">'+
      tile('네이버',n,sh&&sh.naver)+tile('구글',g,sh&&sh.google)+'</div>';
    /* (아래에서 svcPlat 으로 한 번 더 감싼다) */
    /* 비중을 모를 때는 막대를 그리지 않는다 — 반반으로 그리면 거짓말이 된다 */
    if(sh&&sh.naver!=null&&sh.google!=null){
      rows+='<div class="svcShare">'+
        '<i class="nv" style="width:'+sh.naver+'%"></i>'+
        '<i class="gg" style="width:'+sh.google+'%"></i></div>'+
        '<div class="svcShareLb">'+
          '<span><u class="nv"></u>네이버 <b>'+sh.naver+'%</b></span>'+
          '<span><u class="gg"></u>구글 <b>'+sh.google+'%</b></span>'+
        '</div>';
    }
    rows='<div class="svcPlat">'+rows+'</div>';
  }

  /* 시즌성 — 12개월 절대값이라 "작년 이맘때" 비교가 된다.
     ★ 2026-09-23 — 가로 막대를 위아래로 쌓던 것을 세로 컬럼으로 바꿨다.
       시간이 위에서 아래로 흐르면 12개월이 계절 리듬이 아니라 '순위표'로 읽힌다.
       시간은 왼쪽에서 오른쪽이어야 한다.
       색은 열두 개를 쓰지 않는다 — 가장 높은 달만 코랄, 나머지는 회색.
       이 카드가 하는 말은 '어느 달이 튀었나' 하나뿐이기 때문이다(강조형).
       숫자도 피크에만 단다 — 모든 막대에 숫자를 달면 아무도 읽지 않는다. */
  let season='';
  const S=D.seasonality||[];
  if(S.length>=3){
    const mx=Math.max.apply(null,S.map(x=>x.volume||0))||1;
    const top=S.reduce((a,b)=>(b.volume||0)>(a.volume||0)?b:a,S[0]);
    /* 축 이름은 'YYYY-MM' 중 월만 쓴다 — 열두 칸에 연도까지 넣으면 글자가 겹친다.
       해가 바뀌는 1월만 연도를 같이 적어 어느 해인지 잃지 않게 한다. */
    const tick=m=>{
      const t=String(m||''), mm=t.slice(-2);
      return mm==='01'? t.slice(2,4)+'.01' : mm;
    };
    season='<div class="svcSeason">'+
      '<div class="svcColsHead"><h4>월별</h4>'+
        '<span>최고 '+trEsc(top.month)+' · '+num(top.volume)+'</span></div>'+
      '<div class="svcCols">'+S.map(x=>{
        const peak=x.month===top.month, h=Math.max(2,Math.round((x.volume||0)/mx*100));
        /* 값은 data-* 로 실어 둔다 — 브라우저 기본 title 은 1초쯤 기다려야 뜨고
           모양도 제각각이라, 아래에서 직접 그리는 말풍선이 읽는다. */
        return '<div class="svcCol'+(peak?' on':'')+'"'+
          ' data-m="'+trEsc(x.month)+'" data-v="'+num(x.volume)+'">'+
          (peak?'<u>'+num(x.volume)+'</u>':'')+
          '<i style="height:'+(peak?h*0.86:h*0.92)+'%"></i></div>';
      }).join('')+'</div>'+
      '<div class="svcTip" hidden></div>'+
      '<div class="svcXax">'+S.map(x=>
        '<span'+(x.month===top.month?' class="on"':'')+'>'+trEsc(tick(x.month))+'</span>').join('')+
      '</div>'+
      '<div class="note"><i>◆</i>12개월 중 <b>'+trEsc(top.month)+'</b> 이 가장 높습니다. '+
      '나머지 달의 값은 막대에 마우스를 올리면 나옵니다.</div>'+
    '</div>';
  }

  /* 지역 — 값은 '그 시·도 검색량 대비 비율'이라 인구 보정이 이미 들어가 있다.
     ★ 2026-09-23 — 상위 3곳을 줄글로 적던 것을 지도 히트맵으로 바꿨다.
       값이 곧 '온도'라, 어디가 뜨거운지는 숫자보다 지도가 한눈에 읽힌다.
       여기서는 자리만 만들고, 실제 그리기는 본문이 붙은 뒤 paintRegionHeat 가 한다. */
  /* ★ 2026-09-23 — 예전에는 R 이 비면 이 블록을 통째로 빼서 **지도 칸 자체가 사라졌다.**
     자료가 적은 키워드일수록 카드 폭이 들쭉날쭉해 화면이 무너지고, 사용자는
     '지도가 없는 화면'인지 '자료가 없는 것'인지 구분할 수 없었다.
     이제 칸은 늘 서고, 안에서 빈 지도(칠하지 않은 남한)와 사유를 보여 준다. */
  const R=D.regions||[];
  const rgTop=R.length
    ? R.slice(0,3).map(r=>trEsc(r.region)+' '+r.value).join(' · ')
    : '아직 없음';
  const rgNote=R.length
    ? '가장 높은 시·도를 기준으로 상대 온도를 칠합니다.'
    : '이 키워드는 시·도별 검색 비중이 아직 잡히지 않았습니다. 관측이 쌓이면 이 지도에 칠해집니다.';
  const region='<div class="rgWrap"><div class="rgHead"><h4>지역별</h4>'+
    '<span>'+rgTop+'</span></div>'+
    '<div data-region-heat></div>'+
    '<div class="note" style="margin-top:8px"><i>◆</i>'+rgNote+'</div></div>';

  const miss=(st.extra&&st.extra.unavailable&&st.extra.unavailable.fields)||[];
  const note=miss.length
    ? '<div class="note"><i>◆</i>아직 없는 항목: '+miss.map(trEsc).join(' · ')+'</div>'
    : '';

  /* ★ 배치 — 셋을 세로로 쌓으면 카드가 한없이 길어지고, 지도는 폭 400px 이면 충분한데
       가로를 통째로 비워 둔다. 그래서
         1층: 플랫폼 비중 (가로 한 줄이면 끝나는 정보)
         2층: [ 월별 컬럼 차트 | 시·도 지도 ]  — 넓은 쪽을 차트가 갖는다
       좁은 화면에서는 svcGrid 가 한 줄로 풀린다(CSS). */
  const left=(rows||unavailableHTML('절대 검색량이 아직 없습니다.',''))+season;
  return head+'<div class="svcGrid"><div class="svcLeft">'+left+'</div>'+region+'</div>'+note+'</div>';
}

export function trRender(id){
  TR_CUR=id;
  const guideDemo=document.body.classList.contains('trend-guide-demo');
  if(FS.id==='stock'&&id!=='stock')fsStockClear();
  sFootPaint();   /* 가입·정보수정·인증 승인 뒤에 들어와도 이름·직위가 최신이게 */
  if(typeof assocClosePop==='function')assocClosePop();
  /* 요금제 (2026-10-03) — 베타가 끝나면 프리는 EDIT 중 언급량·온도만 연다.
     베타 동안 planEditAllowed 는 언제나 true 라 이 줄은 아무것도 하지 않는다.
     잠긴 탭은 지표를 받으러 가지도 않는다 — 아래 prime 보다 먼저 끊는다. */
  if(TR_EDIT_IDS.indexOf(id)>=0&&!planEditAllowed(id)){ trRenderLocked(id); return }

  /* ★ 그리기 **전에** 지표를 받아 둔다.
     gChart 는 동기 함수라 그 안에서 기다릴 수가 없다. 그래서 여기서 미리
     받아 캐시에 넣고, 도착하면 그 탭만 다시 그린다.
     같은 용어를 여러 번 열어도 요청은 한 번만 나간다(live_data 가 막는다).

     받아 오기 전에는 stateOf() 가 'unknown' 이라 예전처럼 씨드 난수로 그린다.
     받아 온 뒤 다시 그리면서 실값 또는 '측정 불가'로 바뀐다. */
  if(!guideDemo&&(id==='temp'||id==='assoc')){
    const kw=KW.q||fsItem();
    /* ★ 한 번 시도한 말은 잠깐 다시 안 묻는다.
       실패는 캐시하지 않기로 했는데(고친 뒤 재시도가 돼야 하니까),
       그러면 stateOf() 가 계속 'unknown' 이라
       prime → trRender → prime … 으로 **끝없이 돈다.**
       그래서 '방금 물어봤나'를 따로 기억한다. 사람이 다시 누르면
       3초는 지나므로 재시도는 그대로 된다. */
    const now=Date.now();
    if(kw && stateOf(kw).status==='unknown' && now-(TR_TRIED[kw]||0)>3000){
      TR_TRIED[kw]=now;
      prime(kw).then(()=>{
        /* 사용자가 그새 다른 탭으로 갔으면 다시 그리지 않는다 */
        if(TR_CUR===id) trRender(id);
      });
    }
  }
  /* 연관어 · 할인률 · 리세일 · 수명주기는 URL 단위로 받는다 */
  if(!guideDemo&&id==='assoc'&&KW.q) primeOnce(id,'/api/assoc?term='+encodeURIComponent(KW.q));
  /* ★ 2026-09-22 — 검색 지표는 언급 지표(/api/trend)와 **다른 주소**다.
     '뭐라고 말했나'와 '뭘 찾아봤나'를 한 카드에 섞지 않기로 해서 호출도 따로 간다. */
  if(!guideDemo&&id==='temp'&&KW.q) primeOnce(id,searchUrl(KW.q));
  if(!guideDemo&&id==='sentiment'&&KW.q) primeOnce(id,sentimentUrl(KW.q,KW.f));
  if(!guideDemo&&EDIT_API[id]&&(id==='stock'?!!FS.stockItem:fsItem())) primeOnce(id,editUrl(id));
  const m=TR_META[id]||TR_META.myfeed;
  $('#trTitle').textContent=m[0];
  $('#trDesc').textContent=m[1]; $('#trDesc').hidden=!m[1];
  /* 탭 자리는 파트마다 쓰임이 다르다.
     언급량·연관어·긍부정 → 자유 키워드 입력창
     할인률                → 커머스 탭
     그 외                 → 비워 둔다 */
  trTabsRender(id);
  /* ★ 검색창 배선은 **여기 한 곳에서** 붙인다.
     trTabsRender 가 챗바를 통째로 새로 그리므로 매번 다시 붙여야 하는데,
     예전엔 각 탭 블록 맨 끝에 있었다. 그래서 값이 없거나 못 붙어서
     중간에 return 하면 배선이 안 붙었고, **한 번 검색한 뒤로는
     두 번째 검색이 아예 안 먹었다.**
     여기 두면 어느 분기로 빠져나가도 검색은 살아 있다.
     (두 번 부르면 이벤트가 겹쳐 한 번에 두 번 조회된다 — 그래서 한 곳뿐이다.) */
  if (id === 'temp' || id === 'assoc' || id === 'sentiment') kwWire(id);
  /* 검색은 할인률 · 리세일 · 수명주기 세 파트에서만 쓴다 */
  /* 내 피드만 타이틀/설명 대신 프로필(아바타·이름·등급·소개)을 보여준다 */
  const isMyFeed=(id==='myfeed');
  const tw=$('#trTitleWrap'), tp=$('#trProfile');
  if(tw)tw.hidden=isMyFeed;
  if(tp)tp.hidden=!isMyFeed;
  const kk=$('#trKicker'); if(kk)kk.hidden=(id!=='report');
  /* ★ 2026-09-19 — 헤더의 주차 표시가 '2026.08 · W2' 로 박혀 있었다.
     금주의 리포트와 같은 계산(wkRange)으로 오늘이 속한 주를 적는다. */
  /* 저장 · 공유 버튼 — 금주의 리포트, 그리고 EDIT 6탭은 검색한 지표가 화면에 떴을 때만 선다.
     값이 도착하면 trRender 가 다시 불리므로 그때 켜진다. */
  const showActs=id==='report'||!!metricCtx(id);
  const acts=$('#trHeadActs'); if(acts)acts.hidden=!showActs;
  if(!showActs){ const m=$('#trDlMenu'); if(m)m.hidden=true }
  const wkSpan=$('#trWeek');
  if(wkSpan){
    wkSpan.hidden=(id==='report');
    const rg=wkRange();
    wkSpan.textContent=rg[0]+' · '+rg[1].split(' · ')[0];
  }
  const sw=$('#trSearch');
  if(sw){
    const useSearch=['stock','resale','life'].indexOf(id)>=0;
    sw.hidden=!useSearch;
    /* 검색을 안 쓰는 탭으로 나가면 걸린 조건도 함께 푼다 —
       돌아왔을 때 안 보이는 조건이 결과에 남아 있으면 안 된다. */
    if (!useSearch) {
      fsReset(); fsHideSug();
      const cb = $('#fsChips'); if (cb) { cb.hidden = true; cb.innerHTML = '' }
    }
    if (FS.id !== (useSearch ? id : null)) {
      const from = FS.id, to = useSearch ? id : null;
      /* ★ 2026-09-22 — 할인률 변화는 다른 두 탭과 축 이름이 다르다
         (카테고리·상품명 ↔ 종류·아이템명). 그대로 들고 넘어가면 그 탭 칸에는
         없는 축이 칩으로만 남아, **고른 적 없는 조건**이 결과에 섞였다.
         할인률을 드나들 때는 걸린 조건을 비우고 새로 시작한다.
         (리세일 ↔ 수명주기는 축이 같으므로 조건을 들고 옮겨 다닐 수 있다.) */
      if (from === 'stock' || to === 'stock' || (from==='resale'&&FS.resaleItem) || (to==='resale'&&FS.resaleItem)) {
        fsReset(); fsHideSug();
        const cb2 = $('#fsChips'); if (cb2) { cb2.hidden = true; cb2.innerHTML = '' }
        const fi2 = $('#fsInput'); if (fi2) fi2.value = '';
        const fc2 = $('#fsClear'); if (fc2) fc2.hidden = true;
      }
      FS.opts = {};
      FS.id = to;
      if (FS.id) fsPaintPop(); /* 미리 칸 모양을 바꿔 둔다 */
    }
    /* 탭마다 허용 축이 달라질 경우 보이지 않는 조건을 제거한다. */
    if(useSearch&&fsDropDisallowed())fsChipsPaint();
    /* 수명주기는 세부 검색 없이 검색창과 사전만, 할인률·리세일은 사전 없이 세부 검색만 쓴다 */
    const mb=$('#fsMore'); if(mb)mb.hidden=(id==='life');
    const db=$('#trSearch [data-dict-open]'); if(db)db.hidden=(id!=='life');
    const fi=$('#fsInput');
    if(fi)fi.placeholder=id==='stock'?'상품명을 입력하고 Enter · 또는 찜에서 선택':
      id==='resale'?'상품명 · 모델번호를 검색하세요 (예: 살로몬 XT-6)':
      '스타일 · 브랜드 · 카테고리 · 상품명으로 검색';
  }
  const body=$('#trBody'); if(!body)return;

  /* ★ 검색 전에는 아무 숫자도 그리지 않는다.
     전에는 '발레코어' 가 기본값이라, 들어오자마자 화면이 지표로 가득 찼다.
     묻지도 않았는데 답이 떠 있으면 그게 진짜 측정값인 줄 알기 쉽다.

     키워드 탭(언급량·연관어·긍부정)  → KW.q
     검색 탭(할인률·리세일·수명주기)  → fsItem()
     둘 다 비어 있으면 여기서 끝낸다. */
  const KW_TABS = ['temp', 'assoc', 'sentiment'];
  const SEARCH_TABS = ['stock', 'resale', 'life'];
  if (KW_TABS.indexOf(id) >= 0 && !KW.q) {
    body.innerHTML = trEmpty(
      '무엇의 ' + (TR_META[id] ? TR_META[id][0] : '지표') + '을(를) 볼까요?',
      '위 검색창에 스타일·소재·아이템·브랜드를 넣어 주세요.');
    return;
  }
  if (SEARCH_TABS.indexOf(id) >= 0 && id !== 'stock' && !fsItem()) {
    body.innerHTML = trEmpty(
      '먼저 볼 대상을 고르세요',
      id==='resale'
        ? '상품명이나 모델번호로 표준상품을 고르세요.\n세부 검색에서는 브랜드 전체 흐름도 볼 수 있습니다.'
        : '위 검색창이나 사전에서 스타일·소재·아이템·브랜드를 골라 주세요.\n고른 것에 맞춰 지표를 불러옵니다.');
    return;
  }

  const kpi=(l,v,u,d,up,attrs='')=>'<div class="kpi"'+attrs+'><span>'+l+'</span><b>'+v+(u?'<u>'+u+'</u>':'')+
    '</b><div class="dl '+(up?'up':'dn')+'">'+d+'</div></div>';

  /* ══════════════ 내 피드 — 취향 펄스 & 살!말? 큐레이션 ══════════════
     (feedit-my-feed.html 디자인 이식) 판정(리포트)과 역할을 분리 —
     여기는 ① 관심 코어의 시장 화제성 + 신규 신호 브리핑,
     ② 세그먼트(체형·스타일 태그)와 아이템 태그가 모두 맞는 살!말?만
     선별 노출한다. 큐레이션 카드는 실제 VOTES 데이터(투표율·마감·매치
     점수)를 그대로 쓰고, 게시자 페르소나만 표시용으로 얹었다. */
  if(id==='myfeed'){
    /* 가격 · 마감이 비어 있는 카드도 있다 — 살!말? 본 화면(vote_app.js fmtWon · fmtHours)과 같은 말로 쓴다 */
    const won=n=>Number.isFinite(n)?n.toLocaleString('ko-KR')+'원':'가격 정보 없음';
    const hoursTx=h=>Number.isFinite(h)?(h>=24?Math.round(h/24)+'일':h+'시간'):'기간 정보 없음';
    /* 카드 구조와 상품 정보는 살!말? 본 화면과 같은 JSON 값을 쓴다.
       매칭 이유와 태그만 카드 바깥의 내 취향 전용 정보로 덧붙인다. */
    const salCard=p=>
      '<div class="tpPickWrap">'+
        '<article class="voteCard in" role="button" tabindex="0" data-v="salmal" data-sm="taste">'+
          '<div class="fig">'+
            '<div class="plate" style="background-image:url('+p.imgURL+');background-size:cover;background-position:center"></div>'+
            '<div class="vig"></div>'+
            '<span class="pricep">'+won(p.p)+'</span>'+
            '<span class="tagp"><b>'+p.b+'</b></span>'+
          '</div>'+
          '<div class="body">'+
            '<h4>'+p.title+'</h4>'+
            '<div class="cap">'+p.votes.toLocaleString('ko-KR')+'표 · 마감까지 '+hoursTx(p.hours)+'</div>'+
            '<div class="smBar">'+
              '<i class="buy" data-w="'+p.a+'" style="width:'+p.a+'%"><span>살 '+p.a+'%</span></i>'+
              '<i class="no" data-w="'+(100-p.a)+'" style="width:'+(100-p.a)+'%"><span>'+(100-p.a)+'% 말</span></i>'+
            '</div>'+
            '<div class="smBtns">'+
              '<button type="button" class="buy" data-v="salmal" data-sm="taste">살!</button>'+
              '<button type="button" data-v="salmal" data-sm="taste">말?</button>'+
            '</div>'+
          '</div>'+
        '</article>'+
        '<div class="tpReason">'+
          /* ★ 유사도 %를 지어내지 않는다. 실제로 이 카드에 투표한 사람 중
               나와 성별·체형·나이·취향이 겹치는 사람 수와 그들의 살 비율만 쓴다.
               표본이 없으면 그렇다고 말한다(API 의 reason 을 그대로). */
          (p.simHas
            ? '<div class="tpReasonLine"><span class="tpCheck">✓</span>'+
                '<span><strong>나와 비슷한 사용자 '+p.simUsers+'명</strong> · 살 '+p.simPct+'%</span></div>'
            : '<div class="tpReasonLine"><span class="tpCheck">·</span>'+
                '<span><strong>비슷한 사용자 표본 없음</strong></span></div>')+
          (p.matched
            ? '<div class="tpReasonLine"><span class="tpCheck">✓</span>'+
                '<span><strong>아이템 취향 일치</strong> · '+trEsc(p.itemTag)+'</span></div>'
            : '<div class="tpReasonLine"><span class="tpCheck">·</span>'+
                '<span><strong>인기 카드</strong> · 내 스타일과 겹치는 카드</span></div>')+
        '</div>'+
        '<div class="tpTags">'+p.tags.map(t=>'<span'+(t.hit?' class="hit"':'')+'>'+t.tx+'</span>').join('')+'</div>'+
      '</div>';
    body.innerHTML=
      '<div class="tpSection">'+
        '<div class="tpSecLabel"><h3>내 취향 브리핑</h3><span>TASTE PULSE / LIVE</span></div>'+
        '<div class="tpPulseGrid">'+
          '<article class="tpCard tpHero" id="tpHero">'+tpHeroHTML()+'</article>'+
          '<article class="tpCard tpSignal" id="tpSignal">'+tpSignalHTML()+'</article>'+
        '</div>'+
        '<article class="tpCard tpBrief" id="tpBrief">'+tpBriefHTML()+'</article>'+
      '</div>'+
      '<div class="tpSection" style="padding-top:0">'+
        '<div class="tpSalHead"><div><h3>내 취향 맞춤 <em>살!말?</em></h3>'+
          '<p class="tpSalDesc">전체 살!말? 목록 중 나와 체형·스타일 세그먼트가 유사하고, '+
          '동시에 고민 중인 아이템도 내 취향 태그와 겹치는 글만 선별했습니다.</p></div>'+
          '<div class="tpFilterLogic"><span class="tpLogicChip">TOP 4</span></div>'+
        '</div>'+
        '<div class="tpSalGrid" id="tpSalGrid">'+
          '<div class="tpSalState">살!말? 카드를 불러오는 중입니다…</div></div>'+
        '<div class="tpEmptyMore" id="tpSalNote"></div>'+
      '</div>';
    /* ★ 살!말? 카드는 본 화면과 같은 API(/api/salmal/cards)에서 온다.
         목업 JSON을 쓰지 않으므로 여기서만 값이 다를 일이 없다.
         못 불러오면 카드를 그리지 않고 이유를 쓴다 — 빈 화면도, 가짜 카드도 아니다. */
    feedSmLoad().then(pool=>{
      const grid=$('#tpSalGrid'), note=$('#tpSalNote');
      if(!grid)return;
      const picks=feedSmPicks(ME.styles,pool);
      if(!picks.length){
        grid.innerHTML='<div class="tpSalState">지금 진행 중인 살!말? 고민이 없습니다.</div>';
        if(note)note.textContent='';
        return;
      }
      grid.innerHTML=picks.map(salCard).join('');
      if(note)note.textContent=ME.styles.size
        ? STYLES.filter(s=>ME.styles.has(s.id)).map(s=>s.n).join(' · ')+' 기준으로 고른 고민 '+picks.length+'건 표시 중'
        : '즐겨입는 스타일이 없어 인기 고민 '+picks.length+'건을 표시 중';
      if(HAS_A){
        aAnimate($$('#tpSalGrid .tpPickWrap'),
          {opacity:[0,1],translateY:[16,0],duration:620,delay:aStagger(52),ease:'out(3)'});
        smBarFill($$('#tpSalGrid .smBar i'),{duration:920,step:44,start:120});
      }
    }).catch(error=>{
      const grid=$('#tpSalGrid'), note=$('#tpSalNote');
      if(grid)grid.innerHTML='<div class="tpSalState">살!말? 카드를 불러오지 못했습니다.<br>'+
        trEsc(String(error&&error.message||error))+'</div>';
      if(note)note.textContent='';
    });
    /* 버튼을 눌러도 여기서 투표를 완결시키지 않는다 — 살!/말! 버튼은
       data-v="salmal" 을 달아 살!말? 페이지로 보내고, 실제 투표는
       거기서만 일어난다(문서 전역 [data-v] 클릭 위임을 그대로 탄다). */
    /* 프로필은 우리 계정(ME)과 뱃지 시스템을 따른다 */
    trProfPaint();
    tpLoad(tpMine(),tpRepaint);   /* 온도·수명주기를 받아 오면 카드 세 장만 다시 채운다 */
    if(HAS_A){
      aAnimate($$('#trBody .tpCard, #trBody .tpPickWrap'),
        {opacity:[0,1],translateY:[16,0],duration:720,delay:aStagger(52),ease:'out(3)'});
      /* 살/말 비율 막대 — 인라인 폭을 목표값으로 기억해 두고 0 에서 채운다 */
      /* 사이드바가 66→236px 로 열리는 동안에는 본문 폭이 매 프레임 바뀐다.
         그때 % 폭을 함께 굴리면 프레임마다 레이아웃이 다시 잡혀 뚝뚝 끊긴다.
         탭에 막 들어온 참이면 그 전환이 끝난 뒤에 채우기 시작한다. */
      const since=Date.now()-(window.__trEnterAt||0);
      smBarFill($$('#trBody .smBar i'),
        {duration:920,step:44,start:Math.max(300,780-since)});
      /* 취향 태그 · 로직 칩도 순서대로 */
      aAnimate($$('#trBody .tpTasteTags button, #trBody .tpSignalList span'),
        {opacity:[0,1],scale:[.9,1],duration:520,delay:aStagger(36,{start:420}),
         ease:aSpring({stiffness:120,damping:14})});
    }
  }

  else if(id==='report'){
    /* ★ 2026-09-17 실데이터로 바꾼 칸
         · 기간 — 오늘 날짜로 이번 주(월~일)를 계산
         · 한 줄 요약 · 히어로 · 추천 영상 · 웹매거진 — 이번 주 가장 많이 검색한 키워드(없으면 첫 관심 스타일)
         · 히어로 지표 — /api/lifecycle 의 트렌드 온도 · 7일 전 대비 · 수명주기 단계
         · 지표 4칸 · 요일별 활동 · 취향 지분(검색한 스타일만) — /api/auth/weekly-report
         · 같이 지켜볼 스타일 — 스타일 10종의 /api/lifecycle 단계 · 온도로 고른다
       WK 에서 아직 쓰는 것은 갱신 요일뿐이다. 추천 웹매거진은 /api/v1/magazines(웹 검색). */
    const mine=tpMine();
    const fallback=mine[0]||STYLES[0];   /* 이번 주 검색 기록이 없을 때만 쓴다 */
    const rp=wkRange();
    WR={state:'loading',data:null,reason:''}; WKEY=null;

    body.innerHTML='<div class="wkReport" id="wkReport">'+
      /* ── 한 줄 요약 — 이번 주 가장 많이 검색한 키워드가 리포트의 축이다 ── */
      '<div class="wkLine" id="wkLine">'+wkLineHTML(null,rp)+'</div>'+
      /* ── 키워드 히어로 (키워드가 정해지면 wkActivityLoad 가 채운다) ── */
      '<section class="wkHero" id="wkHero">'+wkHeroHTML(null)+'</section>'+
      /* ── 지표 4칸 — 실제로 셀 수 있는 로그만 (/api/auth/weekly-report) ── */
      '<section class="wkMetrics" id="wkMetrics">'+wkMetricsHTML()+'</section>'+
      /* ── 요일별 활동 · 취향 지분 ── */
      '<section class="wkG2">'+
        '<article class="wkCard" id="wkDaysCard">'+wkDaysHTML()+'</article>'+
        '<article class="wkCard" id="wkTasteCard">'+wkTasteHTML()+'</article>'+
      '</section>'+
      /* ── 추천 영상 · 웹매거진 — 지어낸 기사가 아니라, 실제 검색 결과로 바로 연결한다 ── */
      '<section class="wkG2 wkG2b">'+
        '<article class="wkCard">'+
          '<div class="wkCardHead"><h3>이번 주 추천 영상</h3><em id="wkVideoBadge">취향 분석 중</em></div>'+
          '<div id="wkVideoRec"><div class="wkVideoLoading"><i></i><span>이번 주 관심 키워드로<br>콘텐츠 DB를 찾고 있습니다.</span></div></div>'+
        '</article>'+
        '<article class="wkCard" id="wkMagCard">'+wkMagHTML(null)+'</article>'+
      '</section>'+
      /* ── 같이 지켜볼 만한 스타일 ── */
      '<section class="wkCard" style="margin-top:10px">'+
        '<div class="wkCardHead"><h3>같이 지켜볼 만한 스타일</h3><em>HOT NOW</em></div>'+
        '<div class="wkNextGrid" id="wkNextGrid">'+wkNextHTML({id:null})+'</div>'+
      '</section>'+
      '<div class="wkFoot">'+
        '<span>FEEDiT · FASHION TREND ANALYSIS &amp; RECOMMENDATION CONSULTING</span>'+
        '<span>PERSONAL REPORT · '+rp[1]+' / '+rp[0]+'</span>'+
      '</div>'+
    '</div>';
    wkAnimate();
    /* 활동 기록을 받으면 키워드를 정하고 한 줄 요약 · 히어로 · 지표 · 영상 · 웹매거진을 채운다 */
    wkActivityLoad(fallback,rp);
    /* 스타일 10종의 온도 · 수명주기를 받아 오면 '같이 지켜볼 스타일'만 다시 채운다 */
    tpLoad(STYLES,()=>{
      const g=$('#wkNextGrid'); if(g)g.innerHTML=wkNextHTML(WKEY&&WKEY.style||{id:null});
    });
  }
  else if(id==='saved'){ svRender(body) }
  /* ══════════════ 언급량 · 온도 ══════════════
     결론(지금 얼마나 뜨거운가)을 맨 위에 놓고 근거를 아래에 깐다.
     값: /api/trend → analysis.term_metric_daily (전체 합산 행 · 플랫폼별 행) */
  else if(id==='temp'){
    const kw=KW.q;

    /* ★ 실값만 그린다. 받아 오는 동안에는 숫자를 지어내지 않고 '불러오는 중'을 적는다. */
    const st=stateOf(kw), S=summaryOf(kw);
    if(st.status==='unknown'){ body.innerHTML=trLoading('‘'+trEsc(kw)+'’ 의 지표를'); return; }
    if(st.status==='empty'||st.status==='error'){
      body.innerHTML=unavailableHTML(st.reason,
        st.detail || (st.status==='error'?'연결이 되면 자동으로 실제 값이 뜹니다.':''));
      return;
    }
    if(st.status==='ok' && (!S || S.temp===null)){
      body.innerHTML=unavailableHTML(
        '‘'+kw+'’ 의 트렌드 온도가 아직 계산되지 않았습니다.',
        (S&&S.missing.length)?('비어 있는 값: '+S.missing.join('·')):'');
      return;
    }

    const E=entryOf(kw), ED=(E&&E.data)||{};
    const temp=S?Math.round(S.temp):0;
    const share=S&&S.share!=null?+S.share.toFixed(1):null;
    const yoy=S?(S.yoyPct===null?null:Math.round(S.yoyPct)):null;
    const wk=S?(S.tempWk===null?null:Math.round(S.tempWk)):null;
    const nOr=v=>v===null||v===undefined?'–':v;   /* 없는 값은 대시로 */
    const newKw=(ED.new_terms||[]).filter(x=>x.term!==kw)[0]||null;
    /* ★ 2026-09-22 — 옛 지표 버전(feedit-l2-v2) 행은 언급 수가 0 인데 온도만 차 있다.
       언급 0 에서 나온 82도를, 댓글 24건에서 나온 유튜브 86.8도 옆에 세우면
       "무신사가 약간 낮네" 라는 틀린 해석을 부른다. 계산 근거가 아예 다른 값이다.
       → 빼 두고, 뺐다는 사실을 아래 각주에 밝힌다. 틀린 숫자를 띄우느니 빈칸이 낫다. */
    const platsAll=(ED.platforms||[]).filter(p=>p.temp!=null);
    const plats=platsAll.filter(p=>!(p.legacy && !p.mention));
    const band=temp>=85?0:temp>=65?1:temp>=40?2:3;
    /* 색은 가장 낮은 구간에서 시작해 최종 구간까지 걸어 올라간다 */
    const RAMP=['#3d7fd6','#c98a1b','#1f9e6e','#b23b3b'].slice(0,4-band);
    const BAND=[['#b23b3b','과열','이미 정점을 지나는 신호가 섞여 있습니다. 지금부터는 식는 속도를 지켜볼 구간입니다.'],
                ['#1f9e6e','뜨거움','언급량이 꾸준히 오르는 중입니다. 지금 붙잡을 만한 온도입니다.'],
                ['#c98a1b','달아오르는 중','막 올라오기 시작한 단계입니다. 조금 더 지켜보면 방향이 뚜렷해집니다.'],
                ['#3d7fd6','아직 잠잠','절대 언급량이 적어 판단하기엔 이릅니다. 추적만 걸어두는 편이 안전합니다.']][band];
    body.innerHTML=
      '<div class="verdict" style="--sc:'+BAND[0]+'">'+
        '<div class="dial"><svg viewBox="0 0 120 120">'+
          '<circle class="trk" cx="60" cy="60" r="50"/>'+
          '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+temp+'" '+
            'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
          '<span class="num"><b data-count="'+temp+'">0</b><small>트렌드 온도 °</small></span></div>'+
        '<div class="vdTx">'+
          '<h4><b>'+trEsc(kw)+'</b>'+josa(kw,'은','는')+' 지금 <em>'+BAND[1]+'</em> 구간 — 온도 '+temp+'°</h4>'+
          '<p>'+BAND[2]+'</p>'+
          '<div class="vdBand">'+['차가움','미지근','따뜻함','과열'].map((s,i)=>'<div'+(i===(3-band)?' class="on"':'')+
            '><span>'+s+'</span></div>').join('')+'</div>'+
          '<div class="vdMeta">'+
            '<div><b>'+(wk===null?'–':(wk>0?'+':'')+wk)+(wk===null?'':'°')+'</b>'+
              '<span>이번 주 온도 변화'+(wk===null?' (자료 부족)':'')+'</span></div>'+
            '<div><b>'+(S.level==null?'–':Math.round(S.level))+'</b><span>화제성 레벨</span></div>'+
            '<div><b>'+(S.momentum==null?'–':Math.round(S.momentum))+'</b><span>성장 모멘텀 (50=보합)</span></div>'+
          '</div>'+
        '</div></div>'+
      '<div class="note" style="margin:0 0 12px"><i>◆</i>'+
          (S.dataAsOf||S.asOf)+' 기준 · <span data-win-label>최근 7일</span>'+
          (S.thin?' — 자료가 짧아 변화값은 참고만 하세요':'')+'</div>'+
      '<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">'+kpi('플랫폼 점유율',nOr(share),share===null?'':'%',
              share===null?'아직 계산 전':'같은 날 전체 언급 중 비중',1)+
        kpi('전년 동기 대비',yoy===null?'–':(yoy>0?'+':'')+yoy,yoy===null?'':'%',
              yoy===null?'1년치가 모여야 나옵니다':'같은 날 언급량 차이',yoy===null||yoy>=0?1:0)+
        kpi('신규 진입 키워드',newKw?trEsc(newKw.term):'–','',newKw?'최근 7일 새로 감지 · '+Math.round(newKw.temp||0)+'°':'최근 7일 새로 잡힌 말 없음',1)+'</div>'+
      '<div class="trGrid">'+
        '<div class="panelC"><div class="gHead"><h3>'+trEsc(kw)+' · 언급량 지수 · 트렌드 온도 추이</h3></div>'+
          /* ★ 2026-09-22 — 기본 단위를 '일별' 로. 차트 엔진 기본값은 'w'(26주) 라
             그대로 두면 최근 1주가 아니라 반년치가 뜬다. 여기서 못 박는다.
             사용자가 주별·월별을 누르면 그때 바뀐다(토글은 그대로 동작). */
          '<div data-chart="tempMain" data-g="d"></div>'+
          '<div class="note"><i>◆</i>언급량(최대=100 지수)과 트렌드 온도를 나란히 겹쳐 봅니다.</div></div>'+
        '<div class="panelC"><div class="ph"><h3>플랫폼별 온도</h3><em>0–100</em></div>'+
          (plats.length
            ? '<table class="mTable"><tr><th>플랫폼</th><th></th><th>온도</th></tr>'+
              plats.map(t=>{const v=Math.round(t.temp);
                /* ★ 2026-09-21 — 커머스 리뷰는 '리뷰가 쓰인 날'로 쌓여 최신 행이 몇 달 전일 수 있다.
                   그런 값을 날짜 없이 "70°"로만 띄우면 오늘자 같이 보인다 — 기준일을 밝힐다. */
                const age=t.stale?'<small style="display:block;opacity:.55;font-size:11px;font-weight:400">'+trEsc(t.date)+' 기준</small>':'';
                return '<tr><td>'+(v>=85?'<b>'+trEsc(t.name)+'</b>':trEsc(t.name))+age+'</td>'+
                '<td><span class="bar" style="display:block"><i class="'+(v>=85?'c':'')+'" style="width:'+v+'%"></i></span></td>'+
                '<td class="n '+(v>=65?'up':'dn')+'">'+v+'°</td></tr>'}).join('')+
              /* ★ 2026-09-23 — '옛 지표 버전이라 온도를 빼 뒀습니다' 안내는 뺐다.
                 온도를 빼 둔 플랫폼은 애초에 표에 서지 않으므로, 화면에 없는 것을
                 설명하는 줄이었다. */
              '</table><div class="note"><i>◆</i>'+(
                  plats.some(p=>p.stale)
                    ? '기준일이 적힌 플랫폼은 그날의 값입니다 — 리뷰는 쓰인 날로 쌓여 유튜브보다 달력이 느립니다.'
                    : '플랫폼마다 온도차가 있다면 아직 확산 초반 구간입니다.')+'</div>'
            : unavailableHTML('플랫폼별 지표 행이 아직 없습니다.','전체 합산 행만 적재돼 있습니다.'))+
        '</div>'+
      '</div>'+
      /* ══ 검색량 — 언급량과 **다른 카드**로 둔다 ══
         언급(유튜브 댓글·커머스 리뷰)은 "뭐라고 말했나",
         검색(네이버·구글)은 "뭘 찾아봤나"다. 계산 근거가 달라
         한 막대그래프에 세우면 "무신사 82도 / 구글 56도"처럼
         비교 불가능한 숫자가 나란히 서게 된다. 그래서 칸을 나눈다. */
      (guideDemo?'':searchCardHTML(KW.q));
    /* 월별 컬럼 — 막대에 올리면 그 달의 값을 말풍선으로 띄운다.
       (피크 말고는 숫자를 달지 않으므로, 나머지 값을 읽는 길은 이것과 표 보기다) */
    (function(){
      const wrap=$('#trBody .svcSeason'); if(!wrap)return;
      const cols=wrap.querySelector('.svcCols'), tip=wrap.querySelector('.svcTip');
      if(!cols||!tip)return;
      const hide=()=>{ tip.hidden=true };
      cols.addEventListener('mousemove',e=>{
        const col=e.target.closest('.svcCol');
        if(!col){ hide(); return }
        tip.innerHTML='<b>'+col.dataset.m+'</b><span>'+col.dataset.v+'</span>';
        tip.hidden=false;
        /* 말풍선은 마우스가 아니라 **막대 위**에 붙인다 — 값이 어느 막대의 것인지 분명하게 */
        const bar=col.querySelector('i')||col;
        const wr=wrap.getBoundingClientRect(), br=bar.getBoundingClientRect();
        let x=br.left-wr.left+br.width/2-tip.offsetWidth/2;
        x=Math.max(0,Math.min(wr.width-tip.offsetWidth,x));
        tip.style.left=x+'px';
        tip.style.top=Math.max(0,br.top-wr.top-tip.offsetHeight-8)+'px';
      });
      cols.addEventListener('mouseleave',hide);
    })();
    /* 검색량 카드 안의 시·도별 관심도를 지도로 칠한다 (본문이 붙은 뒤에) */
    (function(){
      const host=$('#trBody [data-region-heat]');
      if(!host)return;
      const rg=(stateOfUrl(searchUrl(KW.q)).data||{}).regions||[];
      paintRegionHeat(host, rg);
    })();
    /* ★ term 을 넘겨야 실데이터를 본다. field 는 API 가 돌려주는 열 이름이다 — mention(언급량) · temp(온도). */
    G_CFG.tempMain={key:kw+'temp',term:kw,min:0,max:100,
      sets:[{id:'m',name:'언급량 지수',field:'mention',index:true,unit:''},
            {id:'t',name:'트렌드 온도 (°)',field:'temp',unit:'°',accent:1}]};
    gChart('[data-chart="tempMain"]',G_CFG.tempMain); trDial(); trFillBars();
    /* ★ 2026-09-22 — 차트가 실제로 어떤 창을 썼는지 각주에 적는다.
       1주에 관측이 적으면 차트가 알아서 30일로 넓히는데,
       각주가 계속 '최근 7일' 이면 화면이 거짓말을 한다. */
    (function(){
      const box=$('#trBody [data-chart="tempMain"]'), lab=$('#trBody [data-win-label]');
      if(!box||!lab)return;
      const paintWin=()=>{
        const win=+box.dataset.window||7, unit=box.dataset.unit||'d';
        const u=unit==='d'?'일':unit==='w'?'주':'개월';
        lab.textContent='최근 '+win+u+(box.dataset.widened
          ? ' (1주는 관측이 적어 넓혔습니다)' : '');
      };
      paintWin();
      box.addEventListener('gwin',paintWin);   /* 일별·주별·월별 토글에도 따라온다 */
    })();
  }
  /* ══════════════ 연관어 ══════════════
     값: /api/assoc → analysis.term_assoc_daily (lift · PMI · 백분위 · 순위) + 근거 문장 */
  else if (id === 'assoc') {
    const kw = KW.q;
    const A = editGate(body, '/api/assoc?term=' + encodeURIComponent(kw), '‘' + trEsc(kw) + '’ 의 연관어를');
    if (!A) return;
    const AX_ORDER = ['아이템', '소재', '색', '디테일', 'TPO', '스타일', '브랜드', '인물'];
    const groups = {};
    (A.items || []).forEach(it => { const c = it.facet_ko || it.facet; (groups[c] = groups[c] || []).push(it) });
    const cats = AX_ORDER.filter(c => groups[c]).concat(Object.keys(groups).filter(c => AX_ORDER.indexOf(c) < 0));
    const ALL = cats.reduce((a, c) => a.concat(groups[c]), []);
    if (!ALL.length) {
      body.innerHTML = unavailableHTML('‘' + kw + '’ 의 연관어가 아직 없습니다.', '함께 언급된 문서가 모자랍니다.');
      return;
    }
    /* 포화도는 API 반환 개수나 더보기 행 수에 따라 100%가 되면 안 된다.
       사전에 정의된 8개 축 × 축당 10칸을 분모로 두고, 한 축이 30개여도
       최대 10칸만 기여시켜 다양성과 축 분산을 함께 본다. */
    const MAX_TAGS = AX_ORDER.length * 10;
    const filledSlots = AX_ORDER.reduce((sum, c) => sum + Math.min(10, (groups[c] || []).length), 0);
    const density = Math.min(100, Math.round(filledSlots / MAX_TAGS * 100));
    /* 최다 연관어도 목록과 같은 통합 점수를 쓴다.
       예전처럼 하루 최고 백분위만 보면 2건뿐인 '시계'가 489건+검색 신호의
       '청바지'보다 위에 뜨는 모순이 생긴다. */
    const strength = a => a.score != null ? a.score
      : (a.percentile != null ? a.percentile : (a.lift != null ? a.lift * 10 : a.cooccurrence));
    /* ★ 2026-09-21 — 연관어 출처가 두 갈래가 됐다.
         text   같은 문서 안에서 함께 언급 (유튜브 댓글 · 커머스 리뷰)
         search 같은 검색에서 함께 찾아짐 (구글 related queries · 네이버 연관검색어)
       검색 기반 행에는 '동시 언급 문서 수'가 없어 0 이다 — 그대로 쓰면 막대가 전부 0이 된다.
       그래서 막대 길이는 언급 수가 있으면 그걸로, 없으면 섞은 점수(score)로 그린다. */
    const axWeight = a => (a.cooccurrence || 0) || (a.score || 0);
    const topTag = ALL.slice().sort((a, b) => strength(b) - strength(a))[0];
    const catTotals = cats.map(c => [c, groups[c].reduce((s, a) => s + (a.cooccurrence || 0), 0)]);
    const topCat = catTotals.slice().sort((a, b) => b[1] - a[1])[0][0];
    const newCnt = ALL.filter(a => a.change === 'new').length;
    const band = density >= 75 ? 0 : density >= 50 ? 1 : density >= 25 ? 2 : 3;
    const RAMP = ['#b23b3b', '#c98a1b', '#3d7fd6', '#1f9e6e'].slice(0, 4 - band);
    const BAND = [['#1f9e6e', '폭발적 확산', '여러 축에 걸쳐 연관어가 최대치에 가깝게 쌓였습니다. 소비자 언어가 이미 풍부하게 형성된 상태입니다.'],
    ['#3d7fd6', '활발한 확산', '연관어가 절반 이상 채워졌습니다. 축마다 고르게 늘고 있는지 확인해볼 때입니다.'],
    ['#c98a1b', '완만한 확산', '연관어가 서서히 쌓이고 있지만 아직 절반에 못 미칩니다. 확산 초반 구간입니다.'],
    ['#b23b3b', '정체', '연관어 수가 아직 적어 판단하기엔 이릅니다. 소재가 한정적으로 소비되고 있을 가능성이 있습니다.']][band];
    const badgeHtml = ch => ch === 'new' ? '<span class="axChg up">NEW</span>' :
      ch == null ? '' : ch > 0 ? '<span class="axChg up">▲' + ch + '</span>' : ch < 0 ? '<span class="axChg">▼' + Math.abs(ch) + '</span>' :
        '<span class="axChg">–</span>';
    /* 축마다 처음에는 5개, '+ 더 보기' 뒤에는 10개까지만 보여 준다.
       11위부터는 카드 아래 화살표로 10개씩 넘겨 카드가 끝없이 길어지지 않게 한다. */
    const AX_SHOW = 5;
    const AX_PAGE = 10;
    const axRowsHTML = (arr, ci, badge, page = 0, expanded = false, sort = 'feature') => {
      const max = Math.max.apply(null, arr.map(axWeight)) || 1;
      const start = page * AX_PAGE;
      const visible = page === 0 && !expanded ? AX_SHOW : AX_PAGE;
      const rows = arr.slice(start, start + visible).map((a, offset) => {
        const ai = start + offset;
        const pct = Math.round(axWeight(a) / max * 100);
        const change = sort === 'cooc' ? a.cooc_change
          : (Object.prototype.hasOwnProperty.call(a, 'feature_change') ? a.feature_change : a.change);
        return '<button class="axRow' + (ai === 0 ? ' top' : '') + '"' +
          ' data-ci="' + ci + '" data-ai="' + ai + '">' +
          '<span class="axNum">' + (ai + 1) + '</span>' +
          '<span class="axName">' + trEsc(assocDisplayTerm(a.term)) + '</span>' +
          '<span class="axBar"><i class="' + (ai === 0 ? 'c' : '') + '" style="width:' + pct + '%"></i></span>' +
          (badge ? badge(change) : '') +
          '</button>';
      }).join('');
      if (!expanded && page === 0 && arr.length > AX_SHOW) {
        const more = Math.min(AX_PAGE - AX_SHOW, arr.length - AX_SHOW);
        return rows + '<button type="button" class="axMoreBtn">+ 더 보기 (' + more + ')</button>';
      }
      const pages = Math.ceil(arr.length / AX_PAGE);
      if (pages <= 1) {
        return expanded
          ? rows + '<button type="button" class="axCollapseBtn">− 접기</button>'
          : rows;
      }
      return rows + '<div class="axPager" aria-label="연관어 순위 페이지">' +
        '<span class="axPagerSlot">' + (page > 0
          ? '<button type="button" class="axPageBtn" data-page-dir="prev" aria-label="이전 순위">←</button>' : '') + '</span>' +
        (page === 0
          ? '<button type="button" class="axCollapseBtn">− 접기</button>'
          : '<span class="axPageNow">' + (page + 1) + ' / ' + pages + '</span>') +
        '<span class="axPagerSlot next">' + (page + 1 < pages
          ? '<button type="button" class="axPageBtn" data-page-dir="next" aria-label="다음 순위">→</button>' : '') + '</span>' +
        '</div>';
    };
    const renderAxList = (list, page = 0, expanded = false) => {
      const ci = +list.dataset.ci;
      const cat = cats[ci];
      const arr = groups[cat] || [];
      const last = Math.max(0, Math.ceil(arr.length / AX_PAGE) - 1);
      const safePage = Math.min(Math.max(0, page), last);
      list.dataset.page = String(safePage);
      list.dataset.expanded = expanded ? '1' : '0';
      list.innerHTML = axRowsHTML(arr, ci, badgeHtml, safePage, expanded, list.dataset.sort || 'feature');
    };
    const openAxRow = row => {
      const cat = cats[+row.dataset.ci];
      const a = groups[cat] && groups[cat][+row.dataset.ai];
      if (!a) return;
      const activity = (a.basis || []).indexOf('search') >= 0 && !(a.cooccurrence)
        ? '연관검색 신호' : '언급량 ' + (a.cooccurrence || 0) + '건';
      const stat = [a.lift != null ? 'lift ' + a.lift.toFixed(2) : '', a.pmi != null ? 'PMI ' + a.pmi.toFixed(2) : '',
      activity].filter(Boolean).join(' · ');
      assocOpenPop(row, cat, {
        n: a.term, spark: a.weekly_counts || null,
        src: [{ tag: '지표', text: stat }].concat(a.evidence || [])
      });
    };
    /* 목록 자체에 한 번만 연결해 다시 그린 행과 페이지 버튼도 같은 동작을 쓴다. */
    const axWireLists = root => {
      root.querySelectorAll('.axList').forEach(list => {
        list.addEventListener('click', ev => {
          const more = ev.target.closest('.axMoreBtn');
          const collapse = ev.target.closest('.axCollapseBtn');
          const pageBtn = ev.target.closest('.axPageBtn');
          const row = ev.target.closest('.axRow');
          if (!more && !collapse && !pageBtn && !row) return;
          ev.stopPropagation();
          if (more) return renderAxList(list, 0, true);
          if (collapse) return renderAxList(list, 0, false);
          if (pageBtn) {
            const page = +(list.dataset.page || 0);
            assocClosePop();
            return renderAxList(list, page + (pageBtn.dataset.pageDir === 'next' ? 1 : -1), true);
          }
          openAxRow(row);
        });
      });
    };
    body.innerHTML =
      '<div class="verdict" style="--sc:' + BAND[0] + '">' +
      '<div class="dial"><svg viewBox="0 0 120 120">' +
      '<circle class="trk" cx="60" cy="60" r="50"/>' +
      '<circle class="val" cx="60" cy="60" r="50" data-ramp="' + RAMP.join(',') + '" data-score="' + density + '" ' +
      'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>' +
      '<span class="num"><b data-count="' + density + '">0</b><small>연관어 포화도 %</small></span></div>' +
      '<div class="vdTx">' +
      '<h4><b>' + trEsc(kw) + '</b>' + josa(kw, '은', '는') +
      (A.window_days ? ' 최근 ' + A.window_days + '일 기준으로 ' : ' 지금 ') +
      '<em>' + BAND[1] + '</em> 단계입니다.</h4>' +
      '<p>' + BAND[2] + '</p>' +
      '<div class="vdBand">' + ['정체', '완만', '활발', '폭발'].map((s, i) => '<div' + (i === (3 - band) ? ' class="on"' : '') +
        '><span>' + s + '</span></div>').join('') + '</div>' +
      '<div class="vdMeta">' +
      '<div><b>' + ALL.length + '건</b><span>연관어 총량</span></div>' +
      '<div><b>' + newCnt + '건</b><span>신규 연관어</span></div>' +
      '<div><b>' + (A.window_days ? '최근 ' + A.window_days + '일' : trEsc(A.data_as_of || A.as_of)) +
      '</b><span>' + (A.window_days ? trEsc(A.as_of) + ' 기준' : '기준일') + '</span></div>' +
      '</div>' +
      '</div></div>' +
      '<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">' +
      kpi('최다 연관어', trEsc(topTag.term), '',
        topTag.lift != null ? 'lift ' + topTag.lift.toFixed(2) + (topTag.percentile != null ? ' · 상위 ' + Math.max(1, Math.round(100 - topTag.percentile)) + '%' : '') : '동시 언급 ' + topTag.cooccurrence + '건', 1) +
      kpi('가장 뜨거운 축', trEsc(topCat), '', '축별 동시 언급 문서 합산 1위', 1) +
      kpi('축당 평균 다양성', (ALL.length / cats.length).toFixed(1), '개', '핵심 연관어 수', 1) + '</div>' +
      '<div class="trGrid">' +
      '<div class="panelC"><div class="gHead"><h3>' + trEsc(kw) + ' · 연관어 수 추이</h3></div>' +
      '<div data-chart="assocMain"></div>' +
      '<div class="note"><i>◆</i>날마다 ' + trEsc(kw) + josa(kw, '과', '와') + ' 함께 언급된 연관어의 개수입니다. 이 수가 트렌드 온도보다 먼저 꺾이면 화제성은 남았지만 다양성이 좁아지고 있다는 신호입니다.</div></div>' +
      '<div class="panelC"><div class="ph"><h3>축별 비중</h3><em>KEYWORDS</em></div>' +
      '<table class="mTable"><tr><th>축</th><th></th><th>키워드 수</th></tr>' +
      catTotals.map(c => {
        const cnt = groups[c[0]].length;
        const pct = Math.round(cnt / ALL.length * 100);
        return '<tr><td>' + (c[0] === topCat ? '<b>' + trEsc(c[0]) + '</b>' : trEsc(c[0])) + '</td>' +
          '<td><span class="bar" style="display:block"><i class="' + (c[0] === topCat ? 'c' : '') + '" style="width:' + Math.min(100, pct * 2) + '%"></i></span></td>' +
          '<td class="n">' + cnt + '개</td></tr>'
      }).join('') +
      '</table><div class="note"><i>◆</i>축 하나에 몰릴수록 유행이 아니라 단일 아이템 소비일 확률이 높습니다.</div></div>' +
      '</div>' +
      '<div class="assocGrid" style="margin-top:12px">' +
      cats.map((cat, ci) => {
        const arr = groups[cat];
        const max = Math.max.apply(null, arr.map(axWeight)) || 1;
        return '<div class="panelC" data-cat="' + trEsc(cat) + '" data-ci="' + ci + '">' +
          '<div class="axHead">' +
          '<span class="dot"></span><h3>' + trEsc(cat) + '</h3>' +
          '<div class="axSortToggle">' +
          '<button class="axSortBtn on" data-sort="feature" data-ci="' + ci + '">연관도순</button>' +
          '<button class="axSortBtn" data-sort="cooc" data-ci="' + ci + '">언급량순</button>' +
          '</div>' +
          '</div>' +
          '<div class="axList" data-ci="' + ci + '" data-sort="feature">' + axRowsHTML(arr, ci, badgeHtml) +
          '</div></div>'
      }).join('') + '</div>';
    axWireLists(body);
    /* ── 클라이언트 사이드 정렬용 데이터 저장 ── */
    window._assocGroups = groups;
    window._assocCats = cats;
    window._assocBadgeHtml = badgeHtml;

    G_CFG.assocMain={key:kw+'assoc',term:kw,rows:A.history||[],
      emptyReason:'연관어 적재 이력이 아직 없습니다.',
      sets:[{id:'a',name:'연관어 수',field:'count',unit:'개'}]};
    gChart('[data-chart="assocMain"]', G_CFG.assocMain); trDial();

    /* ── 각 카테고리 토글 클릭 핸들러 ── */
    $$('#trBody .axSortBtn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const ci = +btn.dataset.ci;
        const sort = btn.dataset.sort;
        const cat = window._assocCats[ci];
        const grps = window._assocGroups;
        if (!cat || !grps[cat]) return;

        /* 토글 버튼 활성 상태 변경 (같은 카테고리 내에서만) */
        const panel = btn.closest('.panelC');
        panel.querySelectorAll('.axSortBtn').forEach(b => {
          b.classList.toggle('on', b === btn);
        });

        /* 정렬: pmi=기존 association_rank 순, cooc=동시출현 횟수 내림차순 */
        const arr = grps[cat].slice();
        if (sort === 'cooc') {
          arr.sort((a, b) => (b.cooccurrence || 0) - (a.cooccurrence || 0));
        } else {
          arr.sort((a, b) => {
            const ra = a.rank != null ? a.rank : 999999;
            const rb = b.rank != null ? b.rank : 999999;
            if (ra !== rb) return ra - rb;
            return (b.pmi || 0) - (a.pmi || 0);
          });
        }

        /* 해당 카테고리의 axList만 다시 그리기 (페이지 초기화 없음) */
        const list = panel.querySelector('.axList');

        /* 정렬된 데이터 기준으로 groups 업데이트 (팝업에서도 맞게) */
        grps[cat] = arr;
        list.dataset.sort = sort;
        renderAxList(list, 0, false);
      });
    });
  }
  /* ══════════════ 긍부정 ══════════════
     "사려는 사람이 많은가 · 망설이게 하는 게 뭔가"를 결론 카드로 먼저 답한다.
     값: /api/trend 의 긍정·부정 비율, 반응 유형 건수, 구매의향 지수(purchase_intent_index) */
  else if(id==='sentiment'){
    const kw=KW.q;
    const sentUrl=sentimentUrl(kw,KW.f);
    const st=stateOfUrl(sentUrl);
    if(st.status==='unknown'){ body.innerHTML=trLoading('‘'+trEsc(kw)+'’ 의 긍부정 지표를'); return; }
    if(st.status==='empty'||st.status==='error'){
      body.innerHTML=unavailableHTML(st.reason,
        st.detail || (st.status==='error'?'연결이 되면 자동으로 실제 값이 뜹니다.':''));
      return;
    }
    const D=st.data||{}, rows=Array.isArray(D.series)?D.series:[];
    const last=rows[rows.length-1]||{};
    /* '계산이 안 됐다'와 '계산했는데 분류된 반응이 0건이다'는 다른 말이다.
       행은 있는데 긍정·중립·부정·의도 건수가 전부 0 이면 그렇게 적는다. */
    const CNT=['pos_n','neu_n','neg_n','question_n','purchase_n','experience_n','praise_n','critique_n','chitchat_n'];
    const anyCount=rows.some(r=>CNT.some(f=>(+r[f]||0)>0));
    if(last.intent==null && last.pos_rate==null && !anyCount){
      const counted=rows.some(r=>CNT.some(f=>r[f]!=null));
      body.innerHTML=counted
        ? unavailableHTML('‘'+kw+'’ 에 분류된 반응이 아직 0건입니다.',
            '지표 행('+trEsc(last.date)+' 기준)은 있지만 긍정·중립·부정, 질문·구매·경험·호평·비판·잡담이 모두 0 입니다.<br>'+
            '댓글·리뷰 반응 분류가 이 용어에 붙으면 채워집니다.')
        : unavailableHTML('‘'+kw+'’ 의 긍부정·구매의향 지표가 아직 계산되지 않았습니다.',
            '반응 분류(긍정·부정·의도) 적재가 돌면 채워집니다.');
      return;
    }
    const recent=rows.filter(r=>trDayDiff(r.date,last.date)<28);
    const sum=f=>recent.reduce((a,r)=>a+(+r[f]||0),0);
    /* 신호 유형 = analysis.term_metric_daily 의 의도(intent) 칸 6개 그대로.
         question_count · purchase_count · experience_count · praise_count · critique_count · chitchat_count
       순서는 DB 칸 순서로 고정한다(건수로 줄 세우면 날마다 자리가 바뀌어 비교가 안 된다).
       0건도 지우지 않고 0 으로 보여 준다 — '없었다'도 결과다.
       [이름, 최근 28일 건수, 극성(1 긍정 계열 · 0 중립 · -1 부정 계열)] */
    const SIG_ALL=[['질문',sum('question_n'),0],['구매',sum('purchase_n'),1],['경험',sum('experience_n'),1],
                   ['호평',sum('praise_n'),1],['비판',sum('critique_n'),-1],['잡담',sum('chitchat_n'),0]];
    /* 응답에 의도 칸이 아예 없으면(예전 API) 0 으로 채워 보여 주지 않는다 */
    const hasIntent=recent.some(r=>['question_n','purchase_n','experience_n','praise_n','critique_n','chitchat_n']
      .some(f=>r[f]!=null));
    const SIG=hasIntent&&SIG_ALL.some(x=>x[1]>0)?SIG_ALL:[];
    const total=sum('pos_n')+sum('neu_n')+sum('neg_n');
    const byCount=SIG.filter(x=>x[1]>0).slice().sort((a,b)=>b[1]-a[1]);
    const topPos=byCount.find(x=>x[2]>0), topNeg=byCount.find(x=>x[2]<0);
    /* ── 판정 기준 ──
       ① 구매의향 지수(purchase_intent_index)가 있으면 그 값을 그대로 쓴다.
       ② 없으면 '긍정 비율'로 대신하지 않는다.
          긍정 비율은 중립까지 분모에 들어가서, 긍정 3 · 중립 3 · 부정 0 이 50% → '팽팽'으로 잘못 판정됐다.
          대신 긍정과 부정만 맞대 본 '긍정 우위' = 긍정 ÷ (긍정+부정) × 100 (최근 28일 합)을 쓴다.
       ③ 최근 28일 반응이 SENT_MIN_N 건 미만이면 판정하지 않는다. 몇 건으로 '강한 신호'라 말하지 않는다. */
    const SENT_MIN_N=20;
    const posS=sum('pos_n'), neuS=sum('neu_n'), negS=sum('neg_n');
    const pct=(v)=>total>0?Math.round(v/total*100):null;
    const posPct=total>0?pct(posS):(last.pos_rate!=null?Math.round(last.pos_rate):null);
    const negPct=total>0?pct(negS):(last.neg_rate!=null?Math.round(last.neg_rate):null);
    const score=last.intent!=null?Math.round(last.intent):null;
    const lead=(posS+negS)>0?Math.round(posS/(posS+negS)*100):null;
    const thin=score==null&&(total<SENT_MIN_N||lead==null);
    const dialV=score!=null?score:(lead!=null?lead:0);
    const band=thin?-1:dialV>=75?0:dialV>=55?1:dialV>=35?2:3;
    const RAMP=thin?['#9a968f']:['#b23b3b','#c98a1b','#3d7fd6','#1f9e6e'].slice(0,4-band);
    const BAND=thin
      ? ['#9a968f','판단 보류',
         '최근 28일 반응이 '+total.toLocaleString()+'건뿐이라 판정하기엔 자료가 적습니다.<br>'+
         '긍정 '+posS+' · 중립 '+neuS+' · 부정 '+negS+'건입니다. '+SENT_MIN_N+'건 이상 모이면 판정합니다.']
      : [['#1f9e6e','강한 구매 신호','긍정 신호가 압도적입니다. 지금 재고·물량을 걱정할 시점입니다.'],
         ['#3d7fd6','구매 신호 우세','긍정 쪽이 앞서 있습니다. 부정 신호가 늘지 않는지만 함께 지켜보세요.'],
         ['#c98a1b','팽팽한 신호','긍정과 부정이 비슷하게 맞섭니다. 부정 신호의 종류를 먼저 확인해야 합니다.'],
         ['#b23b3b','구매 저해 신호 우세','부정 신호가 앞섭니다. 가격·실물 관련 이슈부터 해소돼야 반등합니다.']][band];
    const dialLabel=score!=null?'구매의향 지수':'긍정 우위 %';
    const maxSig=Math.max(1,...SIG.map(x=>x[1]));
    body.innerHTML=
      '<div class="verdict" style="--sc:'+BAND[0]+'">'+
        '<div class="dial"><svg viewBox="0 0 120 120">'+
          '<circle class="trk" cx="60" cy="60" r="50"/>'+
          '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+dialV+'" '+
            'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
          '<span class="num"><b data-count="'+dialV+'">0</b><small>'+(dialV===0&&lead==null&&score==null?'–':dialLabel)+'</small></span></div>'+
        '<div class="vdTx">'+
          (thin
            ? '<h4><b>'+trEsc(kw)+'</b>'+josa(kw,'은','는')+' 아직 <em>'+BAND[1]+'</em>입니다.</h4>'
            : '<h4><b>'+trEsc(kw)+'</b>'+josa(kw,'은','는')+' 지금 <em>'+BAND[1]+'</em>입니다.</h4>')+
          '<p>'+BAND[2]+'</p>'+
          '<div class="vdBand">'+['저해우세','팽팽','우세','강한신호'].map((s,i)=>'<div'+(!thin&&i===(3-band)?' class="on"':'')+
            '><span>'+s+'</span></div>').join('')+'</div>'+
          '<div class="vdMeta">'+
            '<div><b>'+(posPct==null?'–':posPct+'%')+'</b><span>긍정 반응 비율 · 28일</span></div>'+
            '<div><b>'+(negPct==null?'–':negPct+'%')+'</b><span>부정 반응 비율 · 28일</span></div>'+
            '<div><b>'+trEsc(D.data_as_of||last.date)+'</b><span>기준일</span></div>'+
          '</div>'+
        '</div></div>'+
      '<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">'+
        kpi('총 반응 수',total.toLocaleString(),'건','최근 28일 · '+trEsc(D.scope_label||'용어 직접 언급'),1)+
        kpi('최다 긍정 신호',topPos?topPos[0]:'–','',topPos?topPos[1].toLocaleString()+'건':'아직 없음',1)+
        kpi('최다 부정 신호',topNeg?topNeg[0]:'–','',topNeg?topNeg[1].toLocaleString()+'건':'아직 없음',0)+'</div>'+
      '<div class="trGrid" style="align-items:start">'+
        '<div class="panelC" id="sentChartCard"><div class="gHead"><h3>긍정 · 중립 · 부정 반응 비중</h3></div>'+
          '<div data-chart="sentMain"></div>'+
          '<div class="note"><i>◆</i>기준일로부터 최근 7일(주별) · 30일(월별) 반응을 합쳐 긍정·중립·부정 비중으로 나눈 값입니다.</div></div>'+
        '<div class="panelC" id="sentSigCard"><div class="ph"><h3>신호 유형별 건수</h3><em>최근 28일</em></div>'+
          '<div class="sigWrap" id="sigWrap">'+(SIG.length
          ? '<table class="mTable"><tr><th>신호</th><th></th><th>건수</th></tr>'+
            SIG.map(p=>'<tr data-sig="'+p[0]+'" style="cursor:pointer"><td>'+p[0]+'</td>'+
              '<td><span class="bar" style="display:block"><i class="'+(p[2]>0?'c':'')+'" style="width:'+Math.round(p[1]/maxSig*100)+'%"></i></span></td>'+
              '<td class="n '+(p[2]>0?'up':p[2]<0?'dn':'')+'">'+p[1].toLocaleString()+'</td></tr>').join('')+'</table>'
          : unavailableHTML('반응 유형(질문·구매·경험·호평·비판·잡담) 건수가 아직 없습니다.',''))+'</div>'+
          '<button class="sigMore" id="sigMoreBtn" type="button" hidden>+ 더보기</button>'+
          '<div class="note"><i>◆</i>주황이 긍정 계열(구매·경험·호평), 검정이 중립(질문·잡담)·부정(비판) 계열입니다.</div></div>'+
      '</div>';
    /* 날짜별 막대 → 기간 통합 원형(파이) 차트. 주별 = 최근 7일 합, 월별 = 최근 30일 합 (기준일 포함) */
    /* G_CFG 에 올리지 않는다 — gMount 가 선·막대 엔진(gChart)으로 다시 그리면 원형이 사라진다 */
    sentPie($('[data-chart="sentMain"]'),{key:kw+'sent',rows:rows,lastDate:last.date}); trDial(); trFillBars();
    sentFitSignals();   /* 왼쪽 차트 카드 높이에 맞춰 넘치는 신호 목록을 접고 '+더보기' 로 연다 */
    /* 신호 행 클릭 → 해당 유형의 실제 근거 문장 */
    const intentMap={'질문':'QUESTION','구매':'PURCHASE','경험':'EXPERIENCE',
      '호평':'PRAISE','비판':'CRITIQUE','잡담':'CHITCHAT'};
    $$('#sigWrap tr[data-sig]').forEach(row=>{
      row.addEventListener('click',e=>{
        e.stopPropagation();
        const intent=intentMap[row.dataset.sig];
        const evList=(D.evidence||{})[intent]||[];
        assocOpenPop(row,'긍부정 신호',{
          n:row.dataset.sig,spark:null,
          src:evList.length?evList:[{tag:'안내',text:'해당 신호로 분류된 최근 근거 문장이 없습니다.'}]
        });
      });
    });
  }
  /* ══════════════ 할인률 변화 ══════════════
     값: /api/discount → snapshot.product_source_snapshot (세부 검색 조건에 걸린 상품) + 대표 용어 온도 */
  else if (id === 'stock') {
    if(!guideDemo)stockLoadSaved();
    if (!document.getElementById('dzDashboard')) {
      const dashHTML = `
        <section class="stockPicker panelC" id="dzDashboard">
          <div class="stockPickerGrid">
            <div class="stockPickerRate"><span class="stockPickerRateLabel">현재 할인율</span>
              <div id="stockDiscountSlot"></div>
              <button type="button" class="dzSaveBtn" id="dzSaveBtn" hidden></button></div>
            <div class="stockPickerSummary" id="stockPickerSummary" aria-live="polite"></div>
            <div class="dzWishlist"><div class="wlHead"><b>내 찜목록</b><span>클릭하거나 왼쪽 원형으로 드래그</span>
                <span class="dzSaveError" id="dzSaveError" role="alert" hidden></span></div>
              <div class="wlBody" id="dzWishListBody"></div></div>
          </div>
        </section>
        <div id="stockAnalyticsBody"></div>
      `;
      body.innerHTML = dashHTML;
      stockWirePicker();
    }

    stockPaintPicker();
    const aBody = document.getElementById('stockAnalyticsBody');
    if (!aBody) return;

    if (!FS.stockItem) {
      aBody.innerHTML = trEmpty(
        '할인률을 볼 상품을 고르세요',
        '위 세부 검색에서 상품명을 고르거나 찜목록의 상품을 선택해 주세요.');
      return;
    }

    const D = editGate(aBody, editUrl('stock'), '할인률 지표를'); if (!D) return;
    stockPaintPicker(D.product);
    if(D.product){
      const P=D.product, discount=P.discount_rate;
      const days=P.observed_days||0;
      const change=D.change_2w;
      const comparable=Array.isArray(D.matched_platforms)?D.matched_platforms:[];
      const maxCompareDiscount=Math.max(1,...comparable.map(item=>Number(item.discount_rate)||0));
      aBody.innerHTML=
        '<div class="kpis stockKpis">'+
          kpi('할인율 변화',change==null?'–':(change>0?'+':'')+change,change==null?'':'%p',
              change==null?'2주 전 비교 기록 없음':'2주 전 대비',change>0)+
          kpi('첫 할인 관측',D.first_discount_at||'–','','현재 보유한 기록 기준',0)+
          kpi('관측 최고 할인율',D.max_discount_period==null?'–':D.max_discount_period,
              D.max_discount_period==null?'':'%','최근 '+D.days+'일 기록',0)+
          kpi('가격 관측일',days,'일','이력이 부족하면 추이를 그리지 않습니다',0)+'</div>'+
        '<div class="trGrid stockPriceGrid">'+
          '<div class="panelC stockTrendPanel"><div class="gHead"><h3>정가 · 판매가 변동 추이</h3><em>최근 '+D.days+'일 관측</em></div>'+
            '<div id="stockPriceChart"></div>'+
            '<div class="note"><i>◆</i>날짜별 마지막 관측 가격입니다. 관측일 사이의 실제 변경 시각은 알 수 없습니다.</div></div>'+
          '<div class="panelC stockComparePanel"><div class="ph"><h3>판매처별 가격 비교</h3><em>매칭된 동일 상품</em></div>'+
            (comparable.length?'<table class="mTable stockCompareTable"><tr><th>판매처</th><th>할인율</th><th>최근 관측가</th></tr>'+
              comparable.map((item,index)=>{
                const rate=item.discount_rate;
                const width=rate==null?0:Math.max(0,Math.min(100,rate/maxCompareDiscount*100));
                return '<tr'+(item.source_id===P.id?' class="selected"':'')+'><td><b>'+trEsc(item.name)+'</b>'+
                  '<small>'+trEsc(String(item.observed_at||'').slice(0,10))+' 기준</small></td>'+
                  '<td class="n '+(index===0?'up':'')+'">'+(rate==null?'–':rate+'%')+
                  '<span class="bar"><i class="'+(index===0?'c':'')+'" style="width:'+width+'%"></i></span></td>'+
                  '<td class="n">'+trWon(item.sale_price)+'</td></tr>';
              }).join('')+'</table>':unavailableHTML('비교할 판매처 가격이 없습니다.','이 상품의 가격 스냅샷을 확인해 주세요.'))+
            '<div class="note"><i>◆</i>'+(comparable.length<2
              ? '현재 DB에는 동일 표준 상품으로 연결된 다른 판매처가 없습니다.'
              : '동일 표준 상품으로 확인된 판매처만 비교합니다. 판매처마다 관측일이 다를 수 있습니다.')+'</div></div>'+
        '</div>';
      paintStockPriceChart(aBody.querySelector('#stockPriceChart'),D.price_series);
      if(discount!=null)trDial();
      return;
    }
    aBody.innerHTML=unavailableHTML('선택한 상품의 가격 응답을 받지 못했습니다.',
      '상품 ID로 조회되는 할인률 API가 필요합니다.');
    return;
  }

  /* ══════════════ 리세일 시세 지수 ══════════════
     "지금 팔면 얼마 받나 · 사면 손해인가"를 먼저 답한다.
     값: /api/resale → snapshot.resale_snapshot (중고·리셀 매물) ÷ 정가 */
  else if(id==='resale'){
    const D=editGate(body,editUrl('resale'),'리세일 시세를'); if(!D)return;
    const full=(D.product&&D.product.name)||fsSelectionLabel()||D.label||fsItemFull();
    const hasKeep=D.keep_pct!=null, keep=hasKeep?Math.round(D.keep_pct):null;
    const buyDelta=hasKeep?100-keep:null;
    const RAMP=['#b23b3b','#c98a1b','#1f9e6e'];
    const confidence=D.confidence&&D.confidence.label||'낮음';
    const product=D.product||null;
    const exact=D.analysis_scope==='product'||D.analysis_scope==='platform_only';
    const resalePlatformCards=(D.platform_cards||[]).filter(card=>card.market==='resale');
    const noCurrentListings=exact&&resalePlatformCards.length>0&&resalePlatformCards.every(card=>
      card.listing_count===0||(card.listing_count==null&&card.median_price==null));
    const currentListingCount=exact&&D.current_listing_count!=null?Number(D.current_listing_count):null;
    const currentListingLabel=currentListingCount==null?'–':currentListingCount.toLocaleString()+(D.current_listing_count_partial?'+':'');
    const scopeLabel={brand:'브랜드',category:'카테고리',style:'스타일',selection:'조건'}[D.analysis_scope]||'상품';
    const dialScore=exact&&RESALE_MODE==='buy'?Math.max(0,Math.min(100,buyDelta)):Math.max(0,Math.min(100,keep||0));
    const dialLabel=exact?(RESALE_MODE==='buy'?'정가 대비 절약 %':'정가 회수율 %'):'가치 유지율 %';
    const flow=D.keep_change_pp==null?null:(D.keep_change_pp<-1?'down':D.keep_change_pp>1?'up':'flat');
    let headline='', explanation='';
    if(hasKeep&&!exact){
      headline='<b>'+trEsc(full)+'</b> '+scopeLabel+'의 중고 가치는 정가 대비 <em>'+keep+'%</em> 수준이에요.';
      explanation=flow==='down'?'최근 가치 유지율이 내려가는 구간입니다. 매입·재고 판단은 보수적으로 확인하세요.':
        flow==='up'?'최근 가치 유지율이 오르는 구간입니다. 수요와 매물 증가가 함께 나타나는지 확인하세요.':
        flow==='flat'?'최근 가치 유지율은 큰 변화 없이 유지되고 있습니다.':'현재 시장 수준은 확인되지만 이전 기간 비교 자료가 부족합니다.';
    }else if(hasKeep&&RESALE_MODE==='buy'){
      headline=buyDelta>=0
        ? '<b>'+trEsc(full)+'</b>, 지금 사면 정가보다 <em>'+Math.round(buyDelta)+'% 저렴해요.</em>'
        : '<b>'+trEsc(full)+'</b>, 현재 정가보다 <em>'+Math.abs(Math.round(buyDelta))+'% 비싸요.</em>';
      explanation=flow==='down'?'최근 중고 가치가 내려가고 있어 서두르지 않아도 괜찮습니다.':
        flow==='up'?'최근 중고 가치가 오르고 있어 원하는 조건의 매물이 있다면 비교해 보세요.':
        flow==='flat'?'최근 가격 흐름은 큰 변화 없이 유지되고 있습니다.':
        '가격 흐름을 판단할 이전 관측이 부족해 현재 시세만 보여 드립니다.';
    }else if(hasKeep){
      headline='<b>'+trEsc(full)+'</b>, 지금 팔면 정가의 <em>'+keep+'%를 회수할 수 있어요.</em>';
      explanation=flow==='down'?'최근 중고 가치가 내려가고 있어 판매를 생각한다면 시기를 늦추지 않는 편이 좋습니다.':
        flow==='up'?'최근 중고 가치가 오르고 있어 조금 더 지켜볼 여지가 있습니다.':
        flow==='flat'?'최근 가격 흐름은 큰 변화 없이 유지되고 있습니다.':
        '가격 흐름을 판단할 이전 관측이 부족해 현재 시세만 보여 드립니다.';
    }
    const identity=product?'<section class="resaleIdentity">'+
      '<div class="resaleIdentityImg"><span>F</span>'+(product.image?'<img src="'+trEsc(product.image)+'" alt="" loading="lazy" referrerpolicy="no-referrer">':'')+'</div>'+
      '<div><small>'+(product.mapped===false?'플랫폼 단독 상품':'FEEDiT 표준상품')+'</small><h3>'+trEsc(product.name||full)+'</h3>'+
      '<p>'+trEsc([product.brand,product.model_code,product.code,product.category].filter(Boolean).join(' · ')||'상품 부가정보 없음')+'</p></div>'+
      '<div class="resaleIdentityMeta"><b>'+((D.mapping&&D.mapping.platform_count)||0)+'개 플랫폼</b><span>'+
        trEsc((D.mapping&&D.mapping.platforms||[]).join(' · ')||'연결 플랫폼 집계 중')+'</span></div></section>':'';
    const verdict=noCurrentListings?'<div class="panelC resaleNoRatio"><b>현재 판매 중인 중고 매물이 없어요.</b>'+
      '<p>새 매물이 확인되면 현재 시세와 정가 대비 비율을 함께 보여 드릴게요.</p></div>':
      hasKeep?'<div class="verdict resaleVerdict" style="--sc:'+(dialScore>=60?'#1f9e6e':dialScore>=35?'#c98a1b':'#b23b3b')+'">'+
      '<div class="dial"><svg viewBox="0 0 120 120"><circle class="trk" cx="60" cy="60" r="50"/>'+
        '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+dialScore+'" stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
        '<span class="num"><b data-count="'+dialScore+'">0</b><small>'+dialLabel+'</small></span></div>'+
      '<div class="vdTx"><h4>'+headline+'</h4><p>'+explanation+'</p>'+
        (D.basis_note?'<p class="vdBasis">'+trEsc(D.basis_note)+'</p>':'')+'</div></div>':
      '<div class="panelC resaleNoRatio"><b>현재 시세는 확인했지만 정가 대비 비율은 계산하지 않았어요.</b>'+
        '<p>같은 상품의 정가가 연결되면 구매 절약률과 판매 회수율이 자동으로 표시됩니다.</p></div>';
    const hasTradeVolume=D.volume_basis!=='observed_listings';
    const kpis=[
      kpi('정가',D.regular_price==null?'–':trWon(D.regular_price),'','현재 할인 판매가 중앙값',D.regular_price!=null),
      kpi('중고가',noCurrentListings||D.used_price==null?'–':trWon(D.used_price),'','최근 관측 중고가 중앙값',!noCurrentListings&&D.used_price!=null),
      kpi('현재 매물 수',currentListingLabel,currentListingCount==null?'':'건',currentListingCount==null?'현재 수량 미적재':'최신 판매 매물 기준',currentListingCount>0,
        ' data-current-listings="'+(currentListingCount==null?'':currentListingCount)+'"'),
      kpi('4주간 중고거래량',hasTradeVolume&&D.volume_4w!=null?Number(D.volume_4w).toLocaleString():'측정 전',hasTradeVolume&&D.volume_4w!=null?'건':'',
        hasTradeVolume?'최근 4주 실제 거래 기준':'실거래량 미적재',hasTradeVolume&&D.volume_4w!=null),
    ];
    /* 무신사 · 크림 카드는 값이 없어도 항상 둔다 — 없는 쪽은 '없음' 문구로 채운다 */
    const platformCards=(D.platform_cards||[]).slice();
    [['무신사','신상품'],['크림','중고·리셀']].forEach(([nm,kind])=>{
      if(!platformCards.some(c=>String(c.name||'').includes(nm)))platformCards.push({name:nm,empty:kind});
    });
    platformCards.sort((a,b)=>(a.name.includes('크림')?1:0)-(b.name.includes('크림')?1:0));
    const cards=platformCards.map(card=>{
      if(card.empty)return '<article class="resalePlatformCard empty"><div><span>'+trEsc(card.name)+'</span><em>'+card.empty+'</em></div>'+
        '<b>가격 정보 없음</b><p>이 플랫폼에서 확인된 가격이 없어요</p><small>&nbsp;</small></article>';
      const isResale=card.market==='resale';
      const noListing=isResale&&card.listing_count===0;
      const main=noListing?'현재 판매 중인 중고 매물이 없어요':isResale?(card.median_price!=null?trWon(card.median_price):'가격 집계 중'):
        (card.sale_price!=null?trWon(card.sale_price):card.list_price!=null?trWon(card.list_price):'가격 집계 중');
      const facts=[];
      if(noListing)facts.push('새 매물이 등록되면 시세를 다시 확인할 수 있어요');
      else if(isResale&&card.listing_count!=null)facts.push('매물 '+card.listing_count+'건'+(card.listing_count_partial?'+':''));
      if(isResale&&card.min_price!=null)facts.push('최저 '+trWon(card.min_price));
      if(!isResale&&card.discount_rate!=null)facts.push('정가 대비 '+card.discount_rate+'% 할인');
      if(card.product_sources>1)facts.push('연결 상품 '+card.product_sources+'건');
      return '<article class="resalePlatformCard"><div><span>'+trEsc(card.name)+'</span><em>'+(isResale?'중고·리셀':'신상품')+'</em></div>'+
        '<b>'+main+'</b><p>'+trEsc(facts.join(' · ')||'최신 관측 가격')+'</p><small>'+trEsc(String(card.as_of||'').slice(0,10))+' 기준</small></article>';
    }).join('');
    const recommendationPool=D.recommendations||[];
    const recommendationKey=[D.analysis_scope,full,recommendationPool.map(item=>item.source_id).join(',')].join('|');
    if(RESALE_REC_KEY!==recommendationKey){ RESALE_REC_KEY=recommendationKey; RESALE_REC_OFFSET=0; }
    const recommendationSlice=recommendationPool.length<=5?recommendationPool:
      Array.from({length:5},(_,index)=>recommendationPool[(RESALE_REC_OFFSET+index)%recommendationPool.length]);
    const recommendations=recommendationSlice.map(rec=>{
      const type=rec.product_id?'product':'platform_only', id=rec.product_id||rec.source_id;
      const noListing=rec.listing_count===0;
      const facts=[rec.platform,noListing?'현재 판매 중인 매물 없음':rec.listing_count!=null?'관측 매물 '+rec.listing_count+'건'+(rec.listing_count_partial?'+':''):'',rec.model_code].filter(Boolean).join(' · ');
      return '<button type="button" class="resaleRecCard" data-resale-rec-id="'+trEsc(id)+'" data-resale-rec-type="'+type+'"'+
        ' data-resale-rec-name="'+trEsc(rec.name)+'" data-resale-rec-brand="'+trEsc(rec.brand||'')+'" data-resale-rec-code="'+trEsc(rec.model_code||'')+'" data-resale-rec-image="'+trEsc(rec.image||'')+'">'+
        '<span class="resaleRecImg"><i>F</i>'+(rec.image?'<img src="'+trEsc(rec.image)+'" alt="" loading="lazy" referrerpolicy="no-referrer">':'')+'</span>'+
        '<span class="resaleRecTx"><small>'+trEsc(rec.brand||scopeLabel+' 추천')+'</small><b>'+trEsc(rec.name)+'</b><em>'+trEsc(facts)+'</em>'+
        '<strong>'+(noListing?'현재 판매 중인 중고 매물이 없어요':rec.price!=null?trWon(rec.price):'가격 집계 중')+'</strong></span></button>';
    }).join('');
    const mdSignals=(D.md_signals||[]).slice(0,3).map(signal=>'<article class="resaleMdCard '+trEsc(signal.tone||'neutral')+'"><small>'+trEsc(signal.label)+'</small>'+
      '<b>'+trEsc(signal.value)+'</b><p>'+trEsc(signal.description)+'</p></article>').join('');
    const panels=[];
    const resaleSeries=Array.isArray(D.series)?D.series:[];
    panels.push('<div class="panelC"><div class="gHead"><h3>가치 변화</h3></div><div data-chart="resMain"></div>'+
      '<div class="note"><i>◆</i>날짜별 정가 대비 중고 가치의 중앙값입니다.</div></div>');
    const temperatureRows=D.temperature&&Array.isArray(D.temperature.series)?D.temperature.series:[];
    panels.push('<div class="panelC"><div class="gHead"><h3>가치 유지율 vs 트렌드 온도</h3></div><div data-chart="resValueTrend"></div>'+
      '<div class="note"><i>◆</i>가치가 먼저 움직이는지, 관심 온도가 먼저 움직이는지 함께 봅니다.</div></div>');
    if((D.grades||[]).length)panels.push('<div class="panelC"><div class="gHead"><h3>상태별 가격대</h3></div>'+
      '<table class="mTable"><tr><th>상태</th><th>비중</th><th>시세</th></tr>'+D.grades.map(r=>'<tr><td>'+trEsc(r.label)+'</td>'+
        '<td><span class="bar" style="display:block"><i style="width:'+Math.round(r.share_pct)+'%"></i></span></td><td class="n">'+trWon(r.price)+'</td></tr>').join('')+'</table></div>');
    if((D.sizes||[]).length)panels.push('<div class="panelC"><div class="ph"><h3>사이즈별 시세</h3><em>자료가 있는 사이즈만</em></div>'+
      '<table class="mTable lg"><tr><th>사이즈</th><th>정가 대비</th><th>시세</th></tr>'+D.sizes.map(z=>'<tr><td>'+trEsc(z.label)+'</td>'+
        '<td class="n '+((z.ratio||0)>=1?'up':'dn')+'">'+(z.ratio==null?'–':'×'+z.ratio.toFixed(2))+'</td><td class="n">'+trWon(z.price)+'</td></tr>').join('')+'</table></div>');
    const spreadHTML=exact&&D.spread?'<section class="resaleSpread"><div class="gHead"><h3>현재 매물과 최근 거래</h3></div><div class="panelC svSpread">'+
      '<div class="svSpreadRow"><span>현재 최저 매물 중앙값</span><b>'+trWon(D.spread.ask)+'</b></div>'+
      '<div class="svSpreadRow"><span>최근 거래 사례 중앙값</span><b>'+trWon(D.spread.trade)+'</b></div>'+
      '<div class="note"><i>◆</i>동일 표준상품으로 연결된 자료만 사용하며 상태·사이즈 차이는 남아 있을 수 있습니다.</div></div></section>':'';
    body.innerHTML=
      (exact?'<div class="resaleMode" role="group" aria-label="리세일 지수 목적"><button type="button" data-resale-mode="buy" class="'+(RESALE_MODE==='buy'?'on':'')+'">사려고 해요</button>'+
        '<button type="button" data-resale-mode="sell" class="'+(RESALE_MODE==='sell'?'on':'')+'">팔려고 해요</button></div>':'')+
      identity+verdict+
      '<div class="note resaleBasis"><i>◆</i>'+trEsc(String(D.as_of).slice(0,10))+' 기준 · 최근 '+D.days+'일 · 판단 신뢰도 '+trEsc(confidence)+
        (product&&product.mapped===false?' · 아직 다른 플랫폼과 표준상품 매핑 전':'')+'</div>'+
      (kpis.length?'<div class="kpis">'+kpis.join('')+'</div>':'')+
      ((cards||spreadHTML)?'<div class="resaleTop">':'')+
      (cards?'<section class="resalePlatforms"><div class="gHead"><h3>플랫폼별 현재 가격</h3></div><div class="resalePlatformGrid">'+cards+'</div></section>':'')+spreadHTML+
      ((cards||spreadHTML)?'</div>':'')+
      (recommendations?'<section class="resaleRecommendations"><div class="gHead"><div><h3>'+trEsc(full)+' 중고 추천 상품</h3><p>USED·크림에서 실제 관측된 상품을 5개씩 보여 줍니다.</p></div>'+
        (recommendationPool.length>5?'<button type="button" class="resaleMore" data-resale-more>다른 상품 보기 <span>↻</span></button>':'')+'</div><div class="resaleRecGrid">'+recommendations+'</div></section>':'')+
      (mdSignals?'<section class="resaleMd"><div class="gHead"><div><h3>리세일 시장 한눈에 보기</h3><p>가격 방어율·거래량 변화·정가 프리미엄이 얼마나 이어졌는지 보여 드립니다.</p></div></div><div class="resaleMdGrid">'+mdSignals+'</div></section>':'')+
      (panels.length?'<div class="trGrid resaleEvidence">'+panels.join('')+'</div>':'');
    delete G_CFG.resMain;
    delete G_CFG.resValueTrend;
    G_CFG.resMain={key:full+'res',rows:resaleSeries,
      emptyReason:'가치 변화를 그릴 만큼 날짜별 관측이 쌓이지 않았습니다.',
      sets:[{id:'r',name:'정가 대비 중고 가치 (%)',field:'keep_pct',unit:'%'}]};
    G_CFG.resValueTrend={key:full+'res-compare',rows:resaleSeries,min:0,max:100,
      sets:[{id:'r',name:'가치 유지율',field:'keep_pct',unit:'%'},
        {id:'t',name:'트렌드 온도',field:'temp',unit:'°',rows:temperatureRows}]};
    gMount();
    if(hasKeep)trDial();
  }

  /* ══════════════ 수명주기 ══════════════
     "지금 사도 되나" 로만 답한다.
     값: /api/lifecycle → 대표 용어의 level·ma28·momentum 으로 단계를 판정(규칙은 응답의 rule) */
  else{
    const D=editGate(body,editUrl('life'),'수명주기 지표를'); if(!D)return;
    const full=fsSelectionLabel()||D.label||fsItemFull();
    const stages=['태동','확산','정점','쇠퇴'];
    const si=stages.indexOf(D.stage);
    if(si<0){
      body.innerHTML=unavailableHTML('‘'+full+'’ 은 관측이 모자라 수명주기를 판정하지 않았습니다 (관측 '+D.points+'일).',D.rule);
      return;
    }
    const SC=['#3d7fd6','#1f9e6e','#c98a1b','#b23b3b'][si];
    const RAMP=['#3d7fd6','#1f9e6e','#c98a1b','#b23b3b'].slice(0,si+1);
    const pct=D.progress==null?0:D.progress;
    const timing=['적기','적기','주의','비추천'][si];
    /* ★ 2026-09-27 — 발주 판별은 서버(/api/lifecycle order_timing)가 정한 값을 그대로 쓴다 (METRIC-002) */
    const OT=D.order_timing||null;
    const mom=D.momentum==null?null:Math.round(D.momentum-50);
    const MSG=[
      ['아직 아무도 모릅니다','지금 사면 남들보다 먼저 입는 구간입니다. 다만 물량이 적어 선택지가 좁고, 그대로 사라질 위험도 함께 있습니다.'],
      ['가장 안전한 구간입니다','화제성이 올라가는 중입니다. 물량도 충분해 고르기 좋습니다.'],
      ['지금이 마지막입니다','정점 부근입니다. 사도 되지만 오래 못 갑니다. 오래 입을 옷이라면 다음 것을 보세요.'],
      ['이미 지났습니다','최고점에서 내려오는 중입니다. 싸게 나와도 올해 안에 안 입게 될 확률이 높습니다.']][si];
    const wkRows=(D.weekly_temp||[]).slice(0,8);
    body.innerHTML=
      '<div class="verdict" style="--sc:'+SC+'">'+
        '<div class="dial"><svg viewBox="0 0 120 120">'+
          '<circle class="trk" cx="60" cy="60" r="50"/>'+
          '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+pct+'" '+
            'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
          '<span class="num"><b data-count="'+pct+'">0</b><small>유행 진행도 %</small></span></div>'+
        '<div class="vdTx">'+
          '<h4><b>'+trEsc(full)+'</b>'+josa(full,'은','는')+' <em>'+stages[si]+'</em> 단계 — '+MSG[0]+'</h4>'+
          '<p>'+MSG[1]+'</p>'+
          '<div class="vdBand">'+stages.map((s,i)=>'<div'+(i===si?' class="on"':'')+
            '><span>'+s+'</span></div>').join('')+'</div>'+
          '<div class="vdMeta">'+
            '<div><b>'+D.age_weeks+'주</b><span>화제성 시작 후</span></div>'+
            '<div><b>'+trEsc(D.peak_date||'–')+'</b><span>최고점 (28일 평균)</span></div>'+
            '<div><b>'+(D.temp==null?'–':Math.round(D.temp)+'°')+'</b><span>현재 온도</span></div>'+
            '<div><b>'+(mom==null?'–':mom>=0?'상승':'하강')+'</b><span>현재 방향</span></div>'+
          '</div>'+
        '</div></div>'+
      '<div class="note" style="margin:0 0 12px"><i>◆</i>'+trEsc(D.data_as_of||D.as_of)+' 기준 · ‘'+trEsc(D.term)+'’ 관측 '+D.points+'일</div>'+
      (OT?'<div class="note lcOrder" data-order="'+trEsc(OT.code)+'" style="margin:0 0 12px"><i>◆</i><b>발주 관점 · '+trEsc(OT.label)+'</b> — '+trEsc(OT.reason)+'</div>':'')+
      '<div class="kpis">'+
        kpi('구매 타이밍',timing,'',MSG[0],si<2?1:0)+
        kpi('신규 유입률',D.inflow_pct==null?'–':(D.inflow_pct>0?'+':'')+Math.round(D.inflow_pct),D.inflow_pct==null?'':'%','최근 4주 언급 · 직전 4주 대비',(D.inflow_pct||0)>0?1:0)+
        kpi('성장 모멘텀',mom==null?'–':(mom>0?'+':'')+mom,'','모멘텀 지수 50 = 보합',(mom||0)>0?1:0)+
        kpi('시장 포화도',D.level==null?'–':Math.round(D.level),D.level==null?'':'%','화제성 레벨 기준',(D.level||0)>=60?1:0)+'</div>'+
      '<div class="trGrid">'+
        '<div class="panelC"><div class="gHead"><h3>유행 곡선 · 지금 위치</h3></div>'+
          '<div data-chart="lifeMain"></div>'+
          '<div class="note"><i>◆</i>화제성 레벨의 흐름입니다. 오른쪽 끝 음영이 <b>지금</b>입니다. '+
            (si<2?'아직 올라가는 중이라 여유가 있습니다.':'꼭짓점을 지나면 회복하지 않는 경우가 많습니다.')+'</div></div>'+
        '<div class="panelC lcWk"><div class="ph"><h3>주별 온도</h3><em>최근 8주</em></div>'+
          '<div class="lcWkBody">'+(wkRows.length
          ? '<table class="mTable lg"><tr><th>시기</th><th>온도</th><th></th></tr>'+
            wkRows.map(r=>'<tr><td>'+(r.weeks_ago===0?'이번 주':r.weeks_ago+'주 전')+'</td>'+
              '<td><span class="bar" style="display:block"><i class="'+(r.temp>=60?'c':'')+'" style="width:'+Math.round(r.temp)+'%"></i></span></td>'+
              '<td class="n">'+Math.round(r.temp)+'°</td></tr>').join('')+
            '</table>'
          : unavailableHTML('최근 8주 온도 값이 없습니다.',''))+'</div>'+
          '<button type="button" class="lcWkMore" hidden>더보기</button></div>'+
      '</div>'+
      '<div class="trGrid one" style="margin-top:12px">'+
        '<div class="panelC"><div class="gHead"><h3>언급량 · 판매량</h3></div>'+
          '<div data-chart="lifeGap"></div>'+
          ((D.sales_series||[]).length
            ? '<div class="note"><i>◆</i>언급량만 많고 실제로 구매하지 않는 구간은 거품입니다. '+
              '두 선이 붙어 갈수록 진짜 유행입니다. (둘 다 최대=100 지수)</div>'
            : '<div class="note"><i>◆</i>판매량은 아직 측정 전입니다 — 같은 상품의 판매수가 여러 날 쌓여야 선이 생깁니다. '+
              '지금은 언급량만 보여 드립니다.'+(D.basis?' (언급량: YouTube 댓글 기준)':'')+'</div>')+
          '</div>'+
      '</div>';
    G_CFG.lifeMain={key:full+'life',h:300,rows:D.series,band:[.88,1],min:0,max:100,
      emptyReason:'화제성 레벨 시계열이 비어 있습니다.',
      sets:[{id:'l',name:'화제성 레벨',field:'level',unit:''}]};
    const sales=D.sales_series||[];
    /* ★ 2026-09-19 — 판매량이 없으면 카드 전체를 '측정 불가'로 비우지 않고 언급량만 그린다.
       판매량은 같은 상품을 매일 추적한 판매수 스냅샷이 쌓여야 생긴다(지금은 상품당 1~2일).
       두 계열을 섞어 그리지 않는다는 규칙은 그대로 — 판매량 선 자체를 빼고, 빠졌다고 적는다. */
    const gapSets=[{id:'m',name:'언급량',field:'mention',index:true,unit:''}];
    if(sales.length) gapSets.push({id:'w',name:'판매량',field:'sales',index:true,unit:'',accent:1,rows:sales});
    G_CFG.lifeGap={key:full+'gap',wide:true,min:0,max:100,
      rows:trMergeRows(D.series.map(p=>({date:p.date,mention:p.mention})),sales),
      emptyReason:'언급량 시계열이 비어 있습니다.',
      sets:gapSets};
    gMount(); trFillBars(); trDial();
    /* 주별 온도 카드 — 왼쪽 카드 높이에 맞추고, 넘치는 행은 더보기로 펼친다 */
    const wkCard=body.querySelector('.lcWk'), wkBody=wkCard&&wkCard.querySelector('.lcWkBody'), wkBtn=wkCard&&wkCard.querySelector('.lcWkMore');
    if(wkCard&&wkBtn){
      const fit=()=>{
        const h=wkCard.previousElementSibling.offsetHeight;
        wkCard.classList.remove('open'); wkCard.style.maxHeight=h+'px';
        wkBtn.hidden=wkBody.scrollHeight<=wkBody.clientHeight+1;
      };
      wkBtn.onclick=()=>{ const o=wkCard.classList.toggle('open'); wkCard.style.maxHeight=o?'none':''; if(!o)fit(); wkBtn.textContent=o?'접기':'더보기'; };
      requestAnimationFrame(fit);
    }
  }
  if(HAS_A)aAnimate($$('#trBody .kpi, #trBody .panelC, #trBody .concl, #trBody .verdict, #trBody .cheapest, #trBody .svAlso'),
    {opacity:[0,1],translateY:[16,0],duration:760,delay:aStagger(60),ease:'out(3)'});
  trCountUp();   /* 카드가 올라오는 동안 숫자도 같이 굴러 올라간다 */
}
/* 긍부정 - 반응 비중 원형(파이) 차트.
   날짜별로 나누지 않고 선택한 기간(주별 7일 · 월별 30일)의 긍정·중립·부정 건수를 합쳐 한 원에 보여 준다.
   건수 칸(pos_n·neu_n·neg_n)이 없는 응답이면 조각을 지어내지 않는다. */
const SENT_PIE_G=[['w','주별',7],['m','월별',30]];
function sentPie(el,cfg){
  if(!el)return;
  const g=SENT_PIE_G.some(x=>x[0]===el.dataset.g)?el.dataset.g:'w';
  el.dataset.g=g;
  const days=SENT_PIE_G.find(x=>x[0]===g)[2];
  const rows=(cfg.rows||[]).filter(r=>r&&r.date&&trDayDiff(r.date,cfg.lastDate)<days&&trDayDiff(r.date,cfg.lastDate)>=0);
  const hasCnt=rows.some(r=>['pos_n','neu_n','neg_n'].some(f=>r[f]!=null));
  const sum=f=>rows.reduce((a,r)=>a+(+r[f]||0),0);
  const parts=[['p','긍정',sum('pos_n'),'var(--coral)'],['u','중립',sum('neu_n'),'#c9c7c2'],['n','부정',sum('neg_n'),'var(--pink-0)']];
  const total=parts.reduce((a,x)=>a+x[2],0);
  const sel='<div class="gSel">'+SENT_PIE_G.map(x=>'<button type="button" data-g="'+x[0]+'"'+
    (x[0]===g?' class="on"':'')+'>'+x[1]+'</button>').join('')+'</div>';
  if(!hasCnt||total===0){
    el.dataset.live=hasCnt?'zero':'none';
    el.innerHTML=sel+unavailableHTML(hasCnt?'최근 '+days+'일 동안 분류된 반응이 0건입니다.':'긍정·중립·부정 건수가 아직 없습니다.','');
  } else {
    el.dataset.live='ok';
    /* 채워진 원형(파이) 차트 — 조각 사이는 흰 틈으로 가르고, 가장 큰 조각을 바깥으로 살짝 띄워 강조한다.
       12시 방향에서 시계 방향으로 긍정 → 중립 → 부정 순서로 그린다. */
    const CX=100, CY=100, R=86, POP=7;
    const pct=v=>Math.round(v/total*100);
    const live=parts.filter(x=>x[2]>0);
    const big=live.reduce((m,x)=>x[2]>m[2]?x:m,live[0]);
    const pt=(ang,r)=>[CX+r*Math.sin(ang),CY-r*Math.cos(ang)];
    let a0=0;
    const segs=live.map(x=>{
      const sweep=x[2]/total*Math.PI*2, a1=a0+sweep, mid=a0+sweep/2;
      const off=(x===big&&live.length>1)?POP:0;
      const dx=off*Math.sin(mid), dy=-off*Math.cos(mid);
      const tip='<title>'+x[1]+' '+x[2].toLocaleString()+'건 · '+pct(x[2])+'%</title>';
      let shape;
      if(live.length===1){
        shape='<circle class="pieSeg" data-s="'+x[0]+'" cx="'+CX+'" cy="'+CY+'" r="'+R+'" fill="'+x[3]+'">'+tip+'</circle>';
      } else {
        const [x0,y0]=pt(a0,R), [x1,y1]=pt(a1,R);
        shape='<path class="pieSeg" data-s="'+x[0]+'" transform="translate('+dx.toFixed(2)+' '+dy.toFixed(2)+')" '+
          'd="M'+CX+' '+CY+' L'+x0.toFixed(2)+' '+y0.toFixed(2)+' A'+R+' '+R+' 0 '+(sweep>Math.PI?1:0)+' 1 '+
          x1.toFixed(2)+' '+y1.toFixed(2)+' Z" fill="'+x[3]+'">'+tip+'</path>';
      }
      /* 조각 안 퍼센트 — 큰 조각일수록 글자도 크게, 너무 얇은 조각(5% 미만)은 범례에만 둔다 */
      const p=pct(x[2]);
      let label='';
      if(p>=5){
        const lr=live.length===1?0:R*(p>=40?.5:.62);
        const [lx,ly]=pt(mid,lr);
        const fs=p>=40?22:p>=15?15:11;
        label='<text class="pieTx" x="'+(lx+dx).toFixed(2)+'" y="'+(ly+dy).toFixed(2)+'" font-size="'+fs+'" '+
          'fill="'+(x[0]==='u'?'#0a0a0a':'#fff')+'" text-anchor="middle" dominant-baseline="central">'+p+'%</text>';
      }
      a0=a1; return shape+label;
    }).join('');
    el.innerHTML=sel+
      '<div class="sentPie">'+
        '<div class="pieBox"><svg viewBox="-8 -8 216 216">'+segs+'</svg></div>'+
        '<div class="pieSide"><div class="pieSum"><b>'+total.toLocaleString()+'</b><small>건 · 최근 '+days+'일 반응</small></div>'+
        '<ul class="pieLg">'+parts.map(x=>'<li data-s="'+x[0]+'"><i style="background:'+x[3]+'"></i>'+
          '<span>'+x[1]+'</span><b>'+pct(x[2])+'%</b><em>'+x[2].toLocaleString()+'건</em></li>').join('')+'</ul></div>'+
      '</div>';
    if(HAS_A)aAnimate(el.querySelectorAll('.pieSeg,.pieTx'),{opacity:[0,1],duration:520,delay:aStagger(90),ease:'out(3)'});
  }
  el.querySelector('.gSel').addEventListener('click',ev=>{
    const b=ev.target.closest('button'); if(!b)return;
    el.dataset.g=b.dataset.g; sentPie(el,cfg); sentFitSignals();
  });
}
function trAnimateSvg(){ gDraw($$('#trBody .lifeSvg path'),1250,320) }
/* 긍부정 - '신호 유형별 건수' 카드는 왼쪽 '구매의향 지수 추이' 차트 카드 높이에 '정확히' 맞아야 한다.
   신호가 8개(POS 4 + NEG 4)라 표가 차트보다 자연 높이가 더 큰 경우가 있는데, 이걸 grid stretch 에
   맡기면 반대로 차트 카드가 늘어나며 차트 쪽에 빈 공백이 생긴다(오른쪽이 원인 제공, 왼쪽이 피해).
   그래서 이 trGrid 는 align-items:start 로 두고(둘 다 각자 내용 높이로 따로 계산), 왼쪽 차트 카드의
   '있는 그대로'(공백 없는) 높이를 잰 뒤 그 값을 오른쪽 카드 height 로 직접 강제한다.
   오른쪽 목록이 그 높이에 안 들어가면 잘라내고 '+더보기' 로 나머지를 연다(펼치면 카드도 같이 자란다).
   차트 높이는 자기 칼럼 너비에 따라 바뀌므로(뷰포트 리사이즈) 창 크기 변경 시에도 다시 잰다. */
function sentFitSignals(){
  const chart=$('#sentChartCard'), card=$('#sentSigCard'), wrap=$('#sigWrap'), btn=$('#sigMoreBtn');
  if(!chart||!card||!wrap||!btn)return;
  const wasOpen=btn.dataset.state==='open';   /* 리사이즈로 다시 잴 때 펼친 상태는 유지한다 */
  card.style.height='';wrap.style.maxHeight='';wrap.style.overflow='';btn.hidden=true;btn.onclick=null;
  const targetH=chart.offsetHeight;   /* 차트 카드 자체의 공백 없는 높이 */
  const cs=getComputedStyle(card);
  const padV=parseFloat(cs.paddingTop)+parseFloat(cs.paddingBottom);
  let used=padV;
  card.querySelectorAll(':scope > *').forEach(ch=>{ if(ch===wrap)return;
    const m=getComputedStyle(ch); used+=ch.offsetHeight+parseFloat(m.marginTop)+parseFloat(m.marginBottom); });
  const full=wrap.scrollHeight;
  if(full+used<=targetH){ card.style.height=targetH+'px'; return; }

  const btnH=btn.offsetHeight||34, gap=12;   /* .sigMore 의 margin-top 과 맞춘 값 */
  const avail=Math.max(40,targetH-used-btnH-gap);
  const openH=used+full+btnH+gap;            /* 펼쳤을 때 카드가 필요로 하는 자연 높이 */

  /* 접힘·펼침 전환을 anime.js 로 부드럽게 잇는다 — 그냥 값만 바꾸면 뚝뚝 끊겨서 정적으로 보인다 */
  const setTo=(wrapH,cardH,animated)=>{
    wrap.style.overflow='hidden';
    const curW=parseFloat(wrap.style.maxHeight)||wrap.getBoundingClientRect().height;
    const curC=parseFloat(card.style.height)||card.getBoundingClientRect().height;
    if(HAS_A&&animated){
      aAnimate(wrap,{maxHeight:[curW,wrapH],duration:380,ease:'out(3)'});
      aAnimate(card,{height:[curC,cardH],duration:380,ease:'out(3)',
        onComplete:()=>{ if(cardH>targetH+2)wrap.style.overflow='visible'; }});
      aAnimate(btn,{opacity:[.35,1],duration:320,ease:'out(2)'});
    } else {
      wrap.style.maxHeight=wrapH+'px'; card.style.height=cardH+'px';
      if(cardH>targetH+2)wrap.style.overflow='visible';
    }
  };
  const collapse=animated=>{ btn.textContent='+ 더보기'; btn.dataset.state='closed'; setTo(avail,targetH,animated); };
  const expand  =animated=>{ btn.textContent='- 줄이기'; btn.dataset.state='open';   setTo(full,openH,animated); };

  btn.hidden=false;
  btn.onclick=()=>{ if(btn.dataset.state==='open') collapse(true); else expand(true); };
  if(wasOpen) expand(false); else collapse(false);
}
var __sentFitT=null;
window.addEventListener('resize',()=>{
  clearTimeout(__sentFitT);
  __sentFitT=setTimeout(sentFitSignals,140);
});
var TR_TAB='통합';

/* 사이드바 하단 프로필 — [아바타] [닉네임 / 직위] [등급 뱃지]
   직위 줄: 운영자 계정은 'ADMIN · 서울' 그대로, 일반 가입자는 승인된 직업(없으면 Basic).
   승인 대기 중이면 ' · 인증 대기' 가 붙는다 (account/static/js/job.js). */
function sFootPaint(){
  const sf=$('#sFoot'); if(!sf)return;
  const sav=sf.querySelector('.av');
  if(sav){ sav.textContent=ME.initial; rkPaintAv(sav, ME.rank) }   /* 링은 rkPaintAv 가 다시 얹는다 */
  const nb=sf.querySelector('.who b'); if(nb)nb.textContent=ME.name;
  const plan=$('#sFootPlan'); if(plan)plan.textContent=jobPlanText(ME);
  const rk=$('#sFootRk');   if(rk)rk.innerHTML=rkChip(ME.rank);   /* 뱃지는 오른쪽 끝에 따로 선다 */
}
document.addEventListener('feedit:job',()=>{ sFootPaint(); trProfPaint() });

/* 내 피드 머리 — [아바타] [닉네임][직업 배지] / 소개글
   ★ 2026-09-19 — 등급(LV) 칩 자리에 직업 배지를 단다. 운영 계정은 검정 ADMIN.
     승인 전이면 Basic(검정), 승인된 패션 직종은 주황. */
function trProfPaint(){
  const pv=$('#trProfAv'), pn=$('#trProfNm'), pr=$('#trProfRk');
  if(pv){ pv.textContent=ME.initial; rkPaintAv(pv, ME.rank) }
  if(pn)pn.textContent=ME.name;
  if(pr)pr.innerHTML=ME.role==='admin'
    ? '<span class="jobBadge basic" title="운영 계정">ADMIN</span>'
    : jobBadgeHTML(jobShown(ME));
  bioPaint();
}
/* ★ 2026-09-19 — 계정이 바뀌면(로그아웃 → 다른 계정 로그인, 새로고침 복구) 앞 계정의 화면을 버린다.
   트렌드 화면은 다시 들어올 때 기존 DOM 을 재사용(router seamless)하므로, 여기서 비워 두지 않으면
   앞 사람의 이름·피드·리포트가 그대로 남는다. 보고 있는 중이면 그 자리에서 다시 그린다. */
function trAccountChanged(){
  sFootPaint(); trProfPaint();
  if(document.body.dataset.view==='trend'&&TR_CUR){ trRender(TR_CUR); return }
  const b=$('#trBody'); if(b)b.innerHTML='';
}
document.addEventListener('feedit:auth',trAccountChanged);
document.addEventListener('feedit:account',()=>{ sFootPaint(); trProfPaint() });

export function trBuild(){
  /* ★ 진짜 사전을 받아 둔다.
     이게 없으면 검색이 이 파일에 박힌 146개로만 돌아서, RDS 에 있는 말도
     "사전에서 찾지 못했습니다" 가 된다(스투시·키르시·엄브로가 그랬다).
     못 받아도 그냥 넘어간다 — 박아 둔 목록으로 화면은 계속 돈다. */
  fsLoadDictionary().catch(()=>{});
  const mk=(a,host)=>{ const el=$(host); if(!el)return;
    el.innerHTML=a.map(s=>'<button class="sItem" data-tr="'+s.id+'">'+
      '<span class="ic">'+s.ic+'</span><span class="tx">'+s.t+'</span></button>').join('') };
  mk(S_FEED,'#sFeed'); mk(S_EDIT,'#sEdit');
  trPaintLocks();
  const first=$('.sItem'); if(first)first.classList.add('on');
  $('#sToggle').addEventListener('click',()=>{
    trSideOpen(!$('#side').classList.contains('open'));
  });
  /* 커머스 탭만 여기서 받는다. 같은 자리에 뜨는 키워드 검색 버튼(.kwGo)은
     자기 핸들러가 따로 있으므로 여기서 가로채면 안 된다. */
  $('#trTabs').addEventListener('click',e=>{
    const b=e.target.closest('button[data-t]'); if(!b)return;
    $$('#trTabs button[data-t]').forEach(x=>x.classList.remove('on')); b.classList.add('on');
    TR_TAB=b.dataset.t; trRender('stock');   /* 탭이 바뀌면 본문을 다시 짠다 */
  });
  fsBuild();
  sFootPaint();
  /* 본문은 여기서 그리지 않는다. 숨어 있는 동안 그리면 등장 애니메이션이
     아무도 안 볼 때 다 끝나버려서, 탭을 열었을 땐 이미 정지 화면이 된다.
     실제로 여는 순간(goView) 에 처음 한 번 그린다. */
}


/* ══════════════ 금주의 리포트 — 저장 · 공유 ══════════════
   요구사항 정의서의 '파일 저장 · 링크 공유'를 실제 동작으로 붙였다(2026-09-23).
   엑셀에는 화면에 실제로 떠 있는 값만 넣는다 — 아직 못 받은 값은 빈칸으로 둔다. */
function wkSheets(){
  const rp=wkRange();
  const K=WKEY, d=WR.state==='ok'?WR.data:null;
  /* ★ 2026-09-23 — 표를 시트 다섯 장으로 나눴더니, 파일을 열면 첫 장만 보이고
     지표 · 요일별 활동 · 취향 지분은 아래 탭에 숨어 '내용이 없는 파일'로 보였다.
     한 장에 위에서 아래로 전부 쌓는다 — 화면에서 읽는 순서 그대로다. */
  const rows=[];
  const put=r=>rows.push(r||[]);
  const section=t=>{ put([]); put(['── '+t+' ──']) };

  put(['FEEDiT 금주의 리포트']);
  put(['기간', rp[0]+' '+rp[1]]);
  put(['내려받은 시각', new Date().toLocaleString('ko-KR')]);
  put(['사용자', ME.name||'']);

  section('이번 주 키워드');
  put(['키워드', K?K.label:'']);
  put(['축', K?(K.facet||''):'']);
  put(['선정 근거', K?(K.from==='search'?'이번 주 가장 많이 검색한 키워드':'검색 기록이 없어 관심 스타일로 대신함'):'']);

  section('지표');
  put(['항목','값','단위','비고']);
  if(d){
    put(['검색한 키워드', d.search.keywords, '개', wkSign(d.search.delta)+' · 지난주 대비']);
    put(['새로 찜한 것', d.saved.new, '개', '총 '+d.saved.total+'개 추적 중']);
    put(['살!말? 투표', d.vote.count, '표', wkSign(d.vote.delta)+' · 지난주 대비']);
    put(['트렌드 분석', d.chat.minutes, '분', d.chat.sessions?('평균 사용 시간 '+d.chat.avg_minutes+'분'):'이번 주 챗봇 사용 기록 없음']);
  }else{
    put(['(활동 기록 없음)','','', WR.reason||'활동 기록을 불러오지 못했습니다.']);
  }

  section('요일별 활동');
  put(['요일','활동 수']);
  if(d)WK_DAY.forEach((day,i)=>put([day, d.activity.days[i]]));
  else put(['(기록 없음)','']);

  section('취향 지분');
  put(['스타일','비중(%)','지난주 대비(%p)']);
  if(d&&d.taste&&d.taste.items.length)d.taste.items.forEach(t=>put([t.label, t.share, t.delta==null?'':t.delta]));
  else put(['(이번 주 검색한 스타일 없음)','','']);

  section('추천 웹매거진');
  put(['매체','기사 제목','주소']);
  if(WM.state==='ok'&&WM.items.length)WM.items.forEach(a=>put([a.magazine||'', a.title||'', a.url||'']));
  else put(['(추천 기사 없음)','','']);

  /* 말머리 칸이 좁으면 '내려받은 시각' 같은 글자가 잘린다 */
  return [{name:'금주의 리포트', rows, widths:[22, 42, 12, 34]}];
}

/* ══════════════ EDIT 지표 — 저장 · 공유 (2026-10-02) ══════════════
   언급량·온도 / 연관어 / 긍부정 / 수명주기 / 할인률 변화 / 리세일 지수에서
   검색한 지표가 뜨면 오른쪽 위 아이콘이 선다. 엑셀은 metric_export.js 가 기획 리포트 양식으로 만들고,
   이미지 · PDF 는 금주의 리포트와 같은 방식으로 화면을 찍는다.
   값은 화면이 이미 받아 둔 캐시만 쓴다 — 아직 없으면 null(버튼을 세우지 않는다). */
const METRIC_TABS=['temp','assoc','sentiment','life','stock','resale'];
const METRIC_NAME={temp:'언급량온도',assoc:'연관어',sentiment:'긍부정',life:'수명주기',stock:'할인율변화',resale:'리세일지수'};
function metricCtx(id){
  if(METRIC_TABS.indexOf(id)<0)return null;
  const rp=wkRange(), period=rp[0].replace('.','-')+'-'+rp[1].split(' · ')[0];
  const src=u=>new URL(u, globalThis.location?.origin || 'http://localhost:5173').href;
  if(id==='temp'||id==='assoc'||id==='sentiment'){
    const kw=KW.q; if(!kw)return null;
    if(id==='temp'){
      const st=stateOf(kw), S=summaryOf(kw);
      if(st.status!=='ok'||!S||S.temp===null)return null;
      return {id,kw,period,entry:st,summary:S,search:stateOfUrl(searchUrl(kw)),
        source:src('/api/trend?term='+encodeURIComponent(kw)+'&days=400')};
    }
    const url=id==='assoc'?'/api/assoc?term='+encodeURIComponent(kw):sentimentUrl(kw,KW.f);
    const st=stateOfUrl(url);
    if(st.status!=='ok'||!st.data)return null;
    if(id==='assoc'&&!(st.data.items||[]).length)return null;
    if(id==='sentiment'&&!(st.data.series||[]).length)return null;
    return {id,kw,period,data:st.data,trend:stateOf(kw),source:src(url)};
  }
  if(id==='stock'?!FS.stockItem:!fsItem())return null;
  const url=editUrl(id), st=stateOfUrl(url);
  if(st.status!=='ok'||!st.data)return null;
  if(id==='stock'&&!st.data.product)return null;
  if(id==='life'&&['태동','확산','정점','쇠퇴'].indexOf(st.data.stage)<0)return null;
  return {id,period,data:st.data,label:fsSelectionLabel()||st.data.label||fsItemFull(),
    mode:RESALE_MODE,source:src(url)};
}
/* 이미지 · PDF 파일 이름 — 엑셀과 같은 규칙 */
function metricFileBase(ctx){
  const who=ctx.kw||(ctx.id==='stock'&&ctx.data.product&&ctx.data.product.name)||
    (ctx.id==='resale'&&ctx.data.product&&(ctx.data.product.model_code||ctx.data.product.name))||ctx.label||'';
  return 'FEEDiT_'+METRIC_NAME[ctx.id]+'_'+String(who).replace(/[\\/:*?"<>|\s]+/g,'_').slice(0,40)+'_'+ctx.period;
}
/* 찍을 때 빼는 것 — 저장·공유 버튼, 검색 추천 목록 */
const METRIC_SHOT_IGNORE='#trHeadActs, .fsSug, .fsClear';
async function metricDownload(fmt){
  const ctx=metricCtx(TR_CUR);
  if(!ctx){ trToast('먼저 검색해 지표를 띄워 주세요.'); return }
  if(fmt==='xlsx'){
    try{
      const out=metricXlsx(ctx);
      saveBlob(out.blob, out.filename);
      trToast('엑셀 파일로 저장했습니다.');
    }catch(err){
      trToast('엑셀 파일을 만들지 못했습니다 ('+(err&&err.message||err)+').');
    }
    return;
  }
  const label=fmt==='pdf'?'PDF':'이미지';
  const items=$$('#trDlMenu button'); items.forEach(b=>b.disabled=true);
  trToast(label+'를 만드는 중입니다…');
  try{
    const canvas=await captureElement($('.trMain'),{ignore:METRIC_SHOT_IGNORE});
    const base=metricFileBase(ctx);
    if(fmt==='pdf')saveBlob(await canvasToPdf(canvas), base+'.pdf');
    else saveBlob(await canvasToPng(canvas), base+'.png');
    trToast(label+' 파일로 저장했습니다.');
  }catch(err){
    trToast(label+' 파일을 만들지 못했습니다 ('+(err&&err.message||err)+').');
  }finally{ items.forEach(b=>b.disabled=false) }
}

/* 다운로드 — 아이콘을 누르면 엑셀 · PDF · 이미지 중 고르는 드롭다운이 열린다 */
const wkMenu=()=>$('#trDlMenu');
function wkMenuSet(open){
  const m=wkMenu(), b=$('#trDownloadBtn'); if(!m)return;
  m.hidden=!open;
  if(b)b.setAttribute('aria-expanded',open?'true':'false');
}
function wkFileBase(){
  const rp=wkRange();
  return 'FEEDiT_금주의리포트_'+rp[0].replace('.','-')+'_'+rp[1].split(' · ')[0];
}
async function wkDownload(fmt){
  /* 아직 데이터를 기다리는 중이면 빈 파일을 주지 않는다 */
  if(WR.state==='loading'){ trToast('리포트를 아직 불러오는 중입니다. 잠시 뒤 다시 눌러 주세요.'); return }
  const base=wkFileBase();
  if(fmt==='xlsx'){
    try{
      saveBlob(buildXlsx(wkSheets()), base+'.xlsx');
      trToast('엑셀 파일로 저장했습니다.');
    }catch(err){
      trToast('엑셀 파일을 만들지 못했습니다 ('+(err&&err.message||err)+').');
    }
    return;
  }
  const label=fmt==='pdf'?'PDF':'이미지';
  const items=$$('#trDlMenu button'); items.forEach(b=>b.disabled=true);
  trToast(label+'를 만드는 중입니다…');
  try{
    /* 제목부터 리포트 본문까지 — 저장·공유 버튼은 그림에서 뺀다 */
    const canvas=await captureElement($('.trMain'),{ignore:'#trHeadActs'});
    if(fmt==='pdf')saveBlob(await canvasToPdf(canvas), base+'.pdf');
    else saveBlob(await canvasToPng(canvas), base+'.png');
    trToast(label+' 파일로 저장했습니다.');
  }catch(err){
    trToast(label+' 파일을 만들지 못했습니다 ('+(err&&err.message||err)+').');
  }finally{ items.forEach(b=>b.disabled=false) }
}
document.addEventListener('keydown', e=>{ if(e.key==='Escape')wkMenuSet(false) });
document.addEventListener('click', async e=>{
  const t=e.target.closest?e.target:null;
  /* 요금제 (2026-10-03) — 리포트 내보내기(저장 · 공유)는 프로부터. 베타 동안 planGuard 는 언제나 통과한다. */
  if(t&&t.closest('#trDownloadBtn, #trDlMenu [data-dl-fmt], #trShareBtn')&&!planGuard('report_export',trToast)){
    wkMenuSet(false); return;
  }
  const dl=t&&t.closest('#trDownloadBtn');
  if(dl){ const m=wkMenu(); wkMenuSet(!!m&&m.hidden); return }
  const pick=t&&t.closest('[data-dl-fmt]');
  if(pick){ wkMenuSet(false); (TR_CUR==='report'?wkDownload:metricDownload)(pick.dataset.dlFmt); return }
  /* 메뉴 밖을 누르면 닫는다 */
  if(wkMenu()&&!wkMenu().hidden)wkMenuSet(false);
  const sh=e.target.closest&&e.target.closest('#trShareBtn');
  if(sh&&TR_CUR!=='report'){
    /* EDIT 지표 — 화면을 PNG 로 찍어 공유한다 */
    const ctx=metricCtx(TR_CUR);
    if(!ctx){ trToast('먼저 검색해 지표를 띄워 주세요.'); return }
    if(sh.disabled)return;
    sh.disabled=true;
    trToast('공유할 이미지를 만드는 중입니다…');
    try{
      const png=captureElement($('.trMain'),{ignore:METRIC_SHOT_IGNORE}).then(canvasToPng);
      const msg=await shareImage(png, metricFileBase(ctx)+'.png', 'FEEDiT '+(TR_META[TR_CUR]?TR_META[TR_CUR][0]:'지표'));
      if(msg)trToast(msg.replace('리포트 이미지','지표 이미지'));
    }catch(err){
      trToast('이미지를 만들지 못했습니다 ('+(err&&err.message||err)+').');
    }finally{ sh.disabled=false }
    return;
  }
  if(sh){
    if(WR.state==='loading'){ trToast('리포트를 아직 불러오는 중입니다. 잠시 뒤 다시 눌러 주세요.'); return }
    if(sh.disabled)return;
    sh.disabled=true;
    trToast('공유할 이미지를 만드는 중입니다…');
    try{
      /* 다운로드(이미지)와 같은 그림 — 제목부터 본문까지, 저장·공유 버튼은 뺀다 */
      const png=captureElement($('.trMain'),{ignore:'#trHeadActs'}).then(canvasToPng);
      const msg=await shareImage(png, wkFileBase()+'.png', 'FEEDiT 금주의 리포트');
      if(msg)trToast(msg);
    }catch(err){
      trToast('이미지를 만들지 못했습니다 ('+(err&&err.message||err)+').');
    }finally{ sh.disabled=false }
  }
});
