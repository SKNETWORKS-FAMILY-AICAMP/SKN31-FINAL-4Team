import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';
import { LIKED } from '../../../home/static/js/chat.js';
import { trRender } from './dispatch.js';
import { entryOf, prime, primeUrl, stateOf, stateOfUrl } from './live_data.js';

/* ══════════════════════════════════════════════════════════════
   찜한 키워드
   --------------------------------------------------------------
   찜은 "모아둔 목록"이 아니라 "지켜보는 목록"이다.
   그래서 맨 위엔 목록이 아니라 오늘 벌어진 일 하나를 크게 세운다.
   ── 이슈 하나 → 오늘 더 있었던 일 → 요약 → 전체 목록 순.
   ══════════════════════════════════════════════════════════════ */
/* 이슈 유형 — [배지 문구, 큰 제목, 색] */
const SV_KIND={
  surge:['급등',     '트렌드 온도 <em>상승</em>',     '#ff6b4a'],
  low  :['최저가',   '기록 중 <em>최저가</em>',       '#1f9e6e'],
  drop :['급락',     '열기가 <em>빠지는 중</em>',     '#3d7fd6'],
  calm :['잠잠',     '지난주와 <em>비슷함</em>',      '#8a8781'],
  none :['측정 전',  '지표 <em>측정 전</em>',         '#b5b1aa']
};
/* ══════════════════════════════════════════════════════════════
   ★ 데이터 출처 (2026-09)
   --------------------------------------------------------------
   찜 목록은 chat.js 의 LIKED 를 읽는다. 로그인하면 서버 원본(/api/auth/saved?view=all)으로
   맞춰진 사본이다 (2026-09-19).

   실데이터
   - 상품 정보 : 상품명 · 브랜드 · 이미지 · 가격 · 카테고리 · 링크 (/api/products)
   - 트렌드 온도 : 찜한 스타일의 trend_temperature — 최신값과 7일 전 값 (/api/trend)
                  ※ 상품 단위 지표는 없어서 '상품이 속한 스타일'의 온도다.
   - 최저가   : 상품 가격 스냅샷의 최저·최고·현재가 (/api/price-history)
   - 이슈 유형 : 위 두 실값으로 판정한다 (최저가 → 온도 ±5 이상 → 잠잠)

   - 같은 걸 찜한 사람 수 : 서버가 센 '지금 찜해 둔 사용자 수(나 포함)'. 모르면 적지 않는다.

   값이 없으면 지어내지 않고 '측정 전' · '—' 로 둔다.
   ══════════════════════════════════════════════════════════════ */
const svEsc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/* '189,000원' 같은 문자열에서도 숫자를 되찾는다 (예전에 저장된 찜 · 추천 카드) */
const svNum=v=>{ if(typeof v==='number')return Number.isFinite(v)?v:null;
  const n=Number(String(v||'').replace(/[^0-9]/g,'')); return n>0?n:null; };
/* 'db-17' → 17 (product_source_id). 실데이터 상품이 아니면 null */
const svSrcId=id=>{ const m=/^db-(\d+)$/.exec(String(id)); return m?m[1]:null; };

/* ── 실데이터 받아 두기 ─────────────────────────────────
   svRender 는 동기로 그린다. 그래서 여기서 받아 두고, 도착하면
   찜한 키워드 화면이 아직 열려 있을 때만 다시 그린다. */
const SV_TRIED={};
const svPriceUrl=ids=>'/api/price-history?ids='+ids.slice().sort((x,y)=>x-y).join(',');
function svLoad(items){
  const now=Date.now(), jobs=[];
  const styles=[...new Set(items.map(([,d])=>d.styleName).filter(Boolean))];
  styles.forEach(st=>{
    if(stateOf(st).status==='unknown'&&now-(SV_TRIED['t:'+st]||0)>3000){
      SV_TRIED['t:'+st]=now; jobs.push(prime(st));
    }
  });
  const ids=items.map(([id])=>svSrcId(id)).filter(Boolean);
  if(ids.length){
    const url=svPriceUrl(ids);
    if(stateOfUrl(url).status==='unknown'&&now-(SV_TRIED[url]||0)>3000){
      SV_TRIED[url]=now; jobs.push(primeUrl(url));
    }
  }
  if(!jobs.length)return false;
  Promise.all(jobs.map(j=>Promise.resolve(j).catch(()=>{}))).then(()=>{
    if($('#trBody [data-sv-root]'))trRender('saved');
  });
  return true;
}

/* 스타일 온도 — 최신값과 7일 전(가장 가까운 이전 날) 값 */
function svTemp(style){
  if(!style)return {state:'none',reason:'어느 스타일에서 찜했는지 기록이 없습니다.'};
  const st=stateOf(style);
  if(st.status==='unknown')return {state:'loading',reason:'트렌드 온도를 불러오는 중입니다.'};
  if(st.status!=='ok')return {state:'none',reason:st.reason||'측정된 지표가 없습니다.'};
  const e=entryOf(style);
  const rows=(e&&e.data&&e.data.series||[]).filter(r=>r&&r.temp!=null);
  if(!rows.length)return {state:'none',reason:'‘'+style+'’ 의 트렌드 온도 값이 비어 있습니다.'};
  const last=rows[rows.length-1];
  const lastT=new Date(last.date+'T00:00:00Z').getTime();
  let prev=null;
  for(let i=rows.length-2;i>=0;i--){
    const t=new Date(rows[i].date+'T00:00:00Z').getTime();
    if(lastT-t>=7*86400000){ prev=rows[i]; break; }
  }
  return {state:'ok', idx:Math.round(last.temp), was:prev?Math.round(prev.temp):null,
          asOf:last.date, wasDate:prev&&prev.date};
}

/* 가격 기록 — /api/price-history 응답에서 이 상품 몫 */
function svPrice(id){
  const src=svSrcId(id); if(!src)return null;
  const ids=[...LIKED.keys()].map(svSrcId).filter(Boolean);
  const st=stateOfUrl(svPriceUrl(ids));
  if(st.status!=='ok'||!st.data||!st.data.items)return null;
  return st.data.items[src]||null;
}

function svBuild(id,d){
  const why=d.styleName||d.cat||'찜한 아이템';
  const t=svTemp(d.styleName);
  const ph=svPrice(id);
  const p=(ph&&ph.current)||svNum(d.price)||svNum(d.pr)||0;
  const lo=ph?ph.min:null, hi=ph?ph.max:null;
  const idx=t.state==='ok'?t.idx:null, was=t.state==='ok'?t.was:null;
  const dl=idx!=null&&was!=null?idx-was:null;
  /* 최저가 판정: 가격 기록이 두 번 이상이고, 지금 가격이 기록 최저이며, 더 비쌌던 적이 있다 */
  const atLow=!!(ph&&ph.points>=2&&p<=lo&&hi>lo);
  let kind;
  if(atLow)kind='low';
  else if(dl!=null)kind=dl>=5?'surge':dl<=-5?'drop':'calm';
  else kind='none';
  const ks=[]; if(atLow)ks.push('low');
  if(dl!=null)ks.push(dl>=5?'surge':dl<=-5?'drop':'calm');
  if(!ks.length)ks.push('none');

  const likedAt=d.likedAt||Date.now();
  const days=Math.max(0,Math.floor((Date.now()-likedAt)/86400000));
  const W=svEsc(why);
  const tempLine=dl!=null?'<b>'+W+'</b> 트렌드 온도 지난주 <b>'+was+'</b> → 이번 주 <b>'+idx+'</b>.':'';
  const note={
    surge:tempLine+' 스타일 전체가 올라오는 중입니다.',
    drop :tempLine+' 열기가 내려오는 중이라 서두를 이유가 없습니다.',
    calm :tempLine+' 지난주와 거의 같습니다.',
    low  :svWon(p)+' — 기록된 가격 중 가장 낮습니다'+
          (hi?' (최고 '+svWon(hi)+' 대비 <b>'+Math.round((1-p/hi)*100)+'%</b> 아래)':'')+'.'+
          (dl!=null?'<br>'+tempLine:''),
    none :svEsc(t.reason||'지표가 아직 없습니다.')
  }[kind];
  return { id, n:d.nm||'상품명 없음', b:d.br||'', img:d.img||'', url:d.url||'',
           p, lo, hi, atLow, d:days, idx, was, dl, k:kind, ks, why, note, asOf:t.asOf||null,
           same:Number.isFinite(d.same)?d.same:null };
}

/* 찜 목록 → 화면 데이터. 위에서부터 오늘 시끄러운 순서(최저가 → 온도 변화 폭 → 잠잠 → 측정 전). */
function svList(){
  const w={low:4,surge:3,drop:2,calm:1,none:0};
  return [...LIKED.entries()].map(([id,d])=>svBuild(id,d))
    .sort((a,b)=>(w[b.k]-w[a.k])||(Math.abs(b.dl||0)-Math.abs(a.dl||0)));
}
var SV=[];
const SV_TABS=[['all','전체'],['surge','급등'],['low','최저가'],
               ['drop','급락'],['calm','잠잠'],['none','측정 전']];
var SV_F='all';
/* ★ 2026-09-23 — '찜한 것 전체' 는 한 번에 10개까지만 보여 주고,
   넘어가는 것은 아래 번호 페이징으로 넘긴다. 찜이 수십 개가 되면
   한 화면에 다 깔려서 지표를 훑기 어려웠다. */
const SV_PER=10;
var SV_PG=1;

export const svWon=v=>Number(v||0).toLocaleString('ko-KR')+'원';
const svAge=n=>n<=0?'오늘':n+'일 전';
const svPic=s=>s.img?'<img src="'+svEsc(s.img)+'" alt="" loading="lazy">':'';
const svV=v=>v==null?'—':String(v);

export function svRender(body){
  const entries=[...LIKED.entries()];
  const loading=svLoad(entries);
  SV=svList();
  /* kpi() 는 trRender 안쪽 지역 함수라 여기선 보이지 않는다. 같은 모양으로 하나 둔다. */
  const kpi=(l,v,u,d,up)=>'<div class="kpi"><span>'+l+'</span><b>'+v+(u?'<u>'+u+'</u>':'')+
    '</b><div class="dl '+(up?'up':'dn')+'">'+d+'</div></div>';

  /* 아직 찜한 게 없으면 — 스타일 페이지로 안내한다 */
  if(!SV.length){
    body.innerHTML=
      '<section class="panelC svList" data-sv-root>'+
        '<div class="ph"><h3>찜한 것 전체</h3><em>WATCHLIST</em></div>'+
        '<div class="svEmpty">아직 찜한 아이템이 없습니다.<br>'+
          '스타일 페이지의 ‘이 스타일의 아이템’에서 하트를 눌러 찜하면 이곳에서 지표를 지켜볼 수 있습니다.'+
          '<div style="margin-top:14px"><button type="button" class="pill" data-v="style"><i>→</i> 스타일 보러 가기</button></div>'+
        '</div>'+
      '</section>';
    return;
  }

  const h=SV[0], hk=SV_KIND[h.k];
  const also=SV.slice(1,4);
  const moved=SV.filter(s=>s.k==='surge'||s.k==='drop'||s.k==='low').length;
  const lows =SV.filter(s=>s.atLow).length;
  const quiet=SV.filter(s=>s.k==='calm').length;
  const none =SV.filter(s=>s.k==='none').length;
  const week =SV.filter(s=>s.d<7).length;
  const styles=new Set(SV.map(s=>s.why)).size;

  body.innerHTML=
    '<div data-sv-root>'+
    /* ── 오늘의 이슈 ─────────────────────────────────
       금주의 리포트 히어로와 같은 틀 — 사진은 카드 가장자리까지 꽉 차고,
       문구 칸은 wkCopy/wkLedger/.pill 을 그대로 재사용한다. */
    '<section class="svHero">'+
      '<div class="svShot"'+(h.url?' data-product-url="'+svEsc(h.url)+'" role="link" tabindex="0" style="cursor:pointer"':'')+'>'+svPic(h)+'</div>'+
      '<div class="wkCopy">'+
        '<div class="wkState">'+(h.asOf?h.asOf+' 기준':'오늘')+' · '+svEsc(h.why)+'</div>'+
        /* 제목 자리엔 브랜드, 그 아래엔 상품명 — 어떤 상품 이야기인지가 먼저다 */
        '<h3 class="svBrand">'+svEsc(h.b||'브랜드 정보 없음')+'</h3>'+
        '<p class="svLead svProd">'+svEsc(h.n)+'</p>'+
        '<div class="wkLedger c3">'+
          '<div class="ac"><span>스타일 온도</span><b>'+svV(h.idx)+'</b></div>'+
          '<div><span>지난주 온도</span><b>'+svV(h.was)+'</b></div>'+
          '<div><span>지난주 대비</span><b>'+(h.dl==null?'—':(h.dl>=0?'+':'')+h.dl)+'</b></div>'+
        '</div>'+
        '<div class="svMeta">'+[h.p?svWon(h.p):'', h.lo!=null?'기록 최저 '+svWon(h.lo):'',
          h.same!=null?'같은 걸 찜한 사람 '+h.same.toLocaleString('ko-KR')+'명':''].filter(Boolean).join(' · ')+'</div>'+
        '<button type="button" class="pill" style="margin-top:16px" id="svToSalmal"><i>→</i> 살!말?에 올리기</button>'+
      '</div>'+
    '</section>'+

    /* ── 오늘 더 있었던 일 ── */
    (also.length?
    '<section class="svAlso">'+
      '<div class="svAlsoH"><h3>오늘 더 있었던 일</h3><em>'+also.length+' MORE</em></div>'+
      '<div class="svAlsoGrid">'+also.map(s=>{
        const k=SV_KIND[s.k];
        return '<div class="svAlsoCard" style="--k:'+k[2]+'">'+
          '<div class="svAlsoTop"><span class="svTags">'+s.ks.map(x=>'<span class="svTag" style="--k:'+SV_KIND[x][2]+'">'+SV_KIND[x][0]+'</span>').join('')+'</span>'+
            '<u>'+svPic(s)+'</u></div>'+
          '<b>'+svEsc(s.n)+'</b><span class="svAlsoB">'+svEsc(s.b)+
            (s.same!=null?' · 찜 '+s.same.toLocaleString('ko-KR')+'명':'')+'</span>'+
          '<p>'+s.note.replace(/<\/?b>/g,'')+'</p></div>'}).join('')+
      '</div>'+
    '</section>':'')+

    /* ── 요약 ── */
    '<div class="kpis" style="margin-top:16px">'+
      kpi('찜해둔 것',String(SV.length),'개','이번 주 +'+week,1)+
      kpi('움직인 것',String(moved),'건',styles+'개 스타일에서',1)+
      kpi('최저가 도달',String(lows),'건','가격 기록 기준',1)+
      kpi('조용한 것',String(quiet),'건',none?'측정 전 '+none+'건':'정리 후보',0)+
    '</div>'+

    /* ── 전체 목록 ── */
    '<section class="panelC svList" style="margin-top:12px">'+
      '<div class="ph"><h3>찜한 것 전체</h3><em>WATCHLIST</em></div>'+
      '<div class="svFilter">'+SV_TABS.map(t=>{
        const c=t[0]==='all'?SV.length:SV.filter(s=>s.ks.includes(t[0])).length;
        if(t[0]==='none'&&!c)return '';
        return '<button type="button" class="svChip'+(t[0]===SV_F?' on':'')+'" data-sv="'+t[0]+'">'+
          t[1]+'<i>'+c+'</i></button>'}).join('')+'</div>'+
      '<div class="svRows" id="svRows">'+svRows()+'</div>'+
      /* ★ 2026-09-23 — 지표 설명 문구는 뺐다. 표 안의 값만으로 읽힌다.
         불러오는 중일 때만 그 사실을 한 줄로 남긴다. */
      (loading?'<div class="wkNote"><i>◆</i><span>실데이터를 불러오는 중입니다.</span></div>':'')+
    '</section>'+
    '</div>';

  /* 살!말?에 올리기 — 등록 카드에 상품명 · 브랜드 · 가격(· 이미지)을 한 번에 채워 연다.
     챗봇의 '살말에 올리기'와 같은 길(window.__salmalDraft → smOpenCreate)을 쓴다. */
  const toSm=$('#svToSalmal');
  if(toSm)toSm.addEventListener('click',()=>{
    window.__salmalDraft={title:h.n||'', brand:h.b||'', price:h.p||'', image:h.img||''};
    const nav=document.querySelector('#mNav [data-v="salmal"]');
    if(nav)nav.click();
    setTimeout(()=>{ if(window.smOpenCreate)window.smOpenCreate(window.__salmalDraft) },320);
  });

  const fl=$('#trBody .svFilter');
  if(fl)fl.addEventListener('click',e=>{
    const b=e.target.closest('button[data-sv]'); if(!b)return;
    SV_F=b.dataset.sv; SV_PG=1;          /* 상태를 바꾸면 첫 페이지부터 */
    $$('#trBody .svChip').forEach(x=>x.classList.toggle('on',x.dataset.sv===SV_F));
    const host=$('#svRows'); if(!host)return;
    host.innerHTML=svRows(); svRowsIn();
  });

  /* 번호 페이징 — 목록만 갈아 끼운다(화면 전체를 다시 그리지 않는다) */
  const rowsHost=$('#svRows');
  if(rowsHost)rowsHost.addEventListener('click',e=>{
    const b=e.target.closest('button[data-pg]'); if(!b||b.disabled)return;
    const pg=+b.dataset.pg;
    if(!pg||pg===SV_PG)return;
    SV_PG=pg;
    rowsHost.innerHTML=svRows(); svRowsIn();
  });
  svAnimate();
}

/* 번호 페이징 — 지금 페이지만 진하게, 한 장뿐이면 아예 그리지 않는다 */
function svPager(total){
  const pages=Math.ceil(total/SV_PER);
  if(pages<=1)return '';
  let out='<div class="svPager">';
  out+='<button type="button" class="svPg nav" data-pg="'+(SV_PG-1)+'"'+(SV_PG<=1?' disabled':'')+'>‹</button>';
  for(let i=1;i<=pages;i++)
    out+='<button type="button" class="svPg'+(i===SV_PG?' on':'')+'" data-pg="'+i+'">'+i+'</button>';
  out+='<button type="button" class="svPg nav" data-pg="'+(SV_PG+1)+'"'+(SV_PG>=pages?' disabled':'')+'>›</button>';
  return out+'</div>';
}
function svRows(){
  const all=SV_F==='all'?SV:SV.filter(s=>s.ks.includes(SV_F));
  if(!all.length)return '<div class="svEmpty">이 상태인 것이 없습니다.</div>';
  const pages=Math.max(1,Math.ceil(all.length/SV_PER));
  if(SV_PG>pages)SV_PG=pages;
  if(SV_PG<1)SV_PG=1;
  const list=all.slice((SV_PG-1)*SV_PER,SV_PG*SV_PER);
  return list.map(s=>{
    const k=SV_KIND[s.k], d=s.dl;
    return '<div class="svRow" style="--k:'+k[2]+(s.url?';cursor:pointer" data-product-url="'+svEsc(s.url)+'" role="link" tabindex="0':'')+'">'+
      '<u class="svTh">'+svPic(s)+'</u>'+
      '<div class="svName"><b>'+svEsc(s.n)+'</b><span>'+svEsc(s.b)+' · '+svEsc(s.why)+
        (s.same!=null?' · 찜 '+s.same.toLocaleString('ko-KR')+'명':'')+'</span></div>'+
      '<div class="svAge">'+svAge(s.d)+'</div>'+
      '<div class="svIdx" title="스타일 트렌드 온도(0~100) · 지난주 대비 변화"><div class="svMini"><i data-w="'+Math.max(0,Math.min(100,s.idx||0))+'"></i></div>'+
        '<b>'+svV(s.idx)+'</b><em class="'+(d>0?'up':d<0?'dn':'')+'">'+
        (d==null?'—':(d>0?'+':'')+(d||'±0'))+'</em></div>'+
      '<div class="svPrice"><b>'+(s.p?svWon(s.p):'가격 정보 없음')+'</b>'+
        '<span>'+(s.atLow?'지금이 최저가':s.lo!=null?'기록 최저 '+svWon(s.lo):'가격 기록 없음')+'</span></div>'+
      '<span class="svBadges">'+s.ks.map(x=>'<span class="svBadge" style="--k:'+SV_KIND[x][2]+'">'+SV_KIND[x][0]+'</span>').join('')+'</span></div>'}).join('')+svPager(all.length);
}

/* 목록 행이 아래에서 한 장씩 올라오고, 미니바가 뒤따라 찬다 */
function svRowsIn(){
  const rows=$$('#trBody .svRow'), bars=$$('#trBody .svMini i');
  if(!HAS_A){ bars.forEach(b=>b.style.width=b.dataset.w+'%'); return }
  if(rows.length)aAnimate(rows,{opacity:[0,1],translateY:[10,0],duration:620,
    delay:aStagger(38),ease:'out(3)'});
  aUtils.set(bars,{width:'0%'});
  aAnimate(bars,{width:el=>el.dataset.w+'%',duration:900,delay:aStagger(38,{start:120}),
    ease:aSpring({stiffness:70,damping:17})});
}

function svAnimate(){
  if(!HAS_A){ svRowsIn(); return }
  /* 금주의 리포트 히어로와 같은 방식 — 사진·문구를 따로 움직이지 않고
     카드 전체가 한 덩어리로 슬라이드+페이드된다(wkAnimate 의 섹션 리빌과 동일 값).
     따로 움직이면 그 사이로 카드 배경이 드러나 보였다. */
  const hero=$('#trBody .svHero');
  if(hero)aAnimate(hero,{opacity:[0,1],translateY:[18,0],duration:820,ease:'out(3)'});
  svRowsIn();
}

/* ── 살/말 막대 채우기 ─────────────────────────────────
   살(코랄)과 말(잉크)은 한 막대를 나눠 쓰는 두 조각이다.
   둘 다 0 에서 키우면 나란히 왼쪽에서 뻗어 나와 말이 안 된다.
   시작은 [말 100%] — 잉크가 막대를 꽉 채운 상태.
   거기서 코랄이 왼쪽에서 밀고 들어오고 잉크는 오른쪽으로 물러난다.
   경계 하나가 왼→오로 지나가는 한 동작으로 읽힌다.
   목표 폭은 언제나 마크업의 data-w — style.width 를 읽으면
   진행 중인 값을 목표로 잘못 삼는다. */
/* 좁은 쪽 라벨 처리.
   예전에는 20% 미만이면 글씨를 아예 숨겼는데, 88:12 처럼 한쪽이 크게 이기면
   진 쪽 %가 통째로 사라져 버렸다. .tight 로 글씨를 칸 밖(=상대 막대 위)으로
   넘기던 처리는 이제 CSS(.smBar i 기본 스타일)로 항상 켜져 있다 — 애니메이션이
   언제 끝났다고 "판정"되는지와 무관하게 어느 순간에 봐도 글씨가 안 묻힌다.
   이 함수는 그 판정에 쓰던 옛 인라인 opacity 값 정리 용도로만 남는다. */
export function smBarLabels(bars){
  bars.forEach(b=>{
    const sp=b.querySelector('span');
    if(sp)sp.style.opacity='';               /* 혹시 남아 있을 옛 인라인 값 제거 */
  });
}
export function smBarFill(bars, opt){
  bars=(bars||[]).filter(Boolean);
  if(!bars.length)return;
  const o=opt||{};
  /* .buy 와 .no 를 각자 따로(0%→목표, 100%→목표) 스프링으로 굴리면, 스프링 특유의
     오버슈트가 둘 사이에서 안 맞아떨어지는 프레임이 생긴다 — 그 순간 두 폭의 합이
     100%를 넘거나 모자라, .no 쪽이 밀려나거나 좁아져 안의 '말' 글씨가 잠깐 파묻혀
     보였다(2026-09 실측). .no 는 CSS 에서 flex:1 로 "나머지 전부"를 차지하게 두고,
     .buy 하나만 애니메이션하면 두 폭의 합은 매 프레임 항상 정확히 100%라 어긋날 수가 없다. */
  const buys=bars.filter(b=>b.classList.contains('buy'));
  if(!HAS_A){ buys.forEach(b=>{ b.style.width=b.dataset.w+'%' }); smBarLabels(bars); return }
  aUtils.remove(buys);                        /* 돌고 있던 게 있으면 먼저 끊는다 */
  buys.forEach(b=>aUtils.set(b,{width:'0%'}));
  aAnimate(buys,{width:el=>el.dataset.w+'%',
    duration:o.duration||1000,
    delay:aStagger(o.step==null?26:o.step,{start:o.start||180}),
    ease:aSpring({stiffness:66,damping:17}),
    onComplete:()=>smBarLabels(bars)});
}
