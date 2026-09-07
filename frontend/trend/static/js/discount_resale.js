import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';
import { IMG } from '../../../home/static/js/chat.js';
import { trRender } from './dispatch.js';

/* ══════════════════════════════════════════════════════════════
   찜한 키워드
   --------------------------------------------------------------
   찜은 "모아둔 목록"이 아니라 "지켜보는 목록"이다.
   그래서 맨 위엔 목록이 아니라 오늘 벌어진 일 하나를 크게 세운다.
   ── 이슈 하나 → 오늘 더 있었던 일 → 요약 → 전체 목록 순.
   ══════════════════════════════════════════════════════════════ */
/* 이슈 유형 — [배지 문구, 큰 제목, 색] */
const SV_KIND={
  surge:['급등',     '트렌드 지수 폭등',   '#ff6b4a'],
  low  :['최저가',   '역대 최저가 경신',   '#1f9e6e'],
  stock:['품절 임박','재고가 얼마 안 남음','#c98a1b'],
  drop :['급락',     '열기가 빠지는 중',   '#3d7fd6'],
  calm :['잠잠',     '한 달째 조용함',     '#8a8781']
};
/* 찜해둔 것들. 위에서부터 오늘 시끄러운 순서다. */
export const SV=[
  {n:'모노 테일러드 자켓',b:'ETCE',      p:189000,lo:174000,img:20,d:9, idx:91,was:62,k:'surge',
   why:'미니멀 셋업',
   note:'셋업 재킷 언급이 사흘 만에 <b>2.4배</b>가 됐습니다. 같은 걸 찜해둔 사람도 하루 사이 <b>412명</b> 늘었습니다. 지금 사도 되는 구간입니다.'},
  {n:'스웨이드 블루종', b:'ANDERSSON',p:329000,lo:298000,img:21, d:23,idx:74,was:71,k:'low',
   why:'클래식',
   note:'298,000원 — 찜한 뒤 가장 낮습니다. 지난 최저가보다 9% 아래.'},
  {n:'와이드 셀비지',   b:'MUSINSA',  p:159000,lo:159000,img:19, d:14,idx:68,was:64,k:'stock',
   why:'아메카지',
   note:'내 사이즈(32) 재고가 두 자리에서 한 자리로 떨어졌습니다.'},
  {n:'후디 집업',       b:'OFF-WHITE',p:429000,lo:398000,img:18, d:31,idx:38,was:59,k:'drop',
   why:'스트릿',
   note:'2주 연속 내려오는 중입니다. 서두를 이유가 없어졌습니다.'},
  {n:'발레 플랫',       b:'REPETTO',  p:298000,lo:279000,img:28,d:6, idx:86,was:78,k:'surge',
   why:'발레코어',
   note:'발레코어가 다시 올라오면서 같이 붙었습니다.'},
  {n:'클래식 볼캡',     b:'POLO',     p:69000, lo:59000, img:16,d:47,idx:44,was:45,k:'calm',
   why:'프레피',
   note:'한 달 넘게 변화가 없습니다.'},
  {n:'에어 포스 1 · 07',b:'NIKE',     p:139000,lo:119000,img:11,d:52,idx:57,was:56,k:'calm',
   why:'스트릿',
   note:'스테디셀러라 지표가 거의 움직이지 않습니다.'},
  {n:'케이블 니트',     b:'COS',      p:119000,lo:98000, img:25, d:18,idx:72,was:60,k:'surge',
   why:'놈코어',
   note:'가을 초입 검색이 붙기 시작했습니다.'},
  {n:'카고 팬츠',       b:'STUSSY',   p:179000,lo:161000,img:30, d:38,idx:41,was:63,k:'drop',
   why:'고프코어',
   note:'고프코어 전반이 식는 흐름을 그대로 따라갑니다.'}
];
const SV_TABS=[['all','전체'],['surge','급등'],['low','최저가'],
               ['stock','품절 임박'],['drop','급락'],['calm','잠잠']];
var SV_F='all';

export const svWon=v=>v.toLocaleString('ko-KR')+'원';

export function svRender(body){
  /* kpi() 는 trRender 안쪽 지역 함수라 여기선 보이지 않는다. 같은 모양으로 하나 둔다. */
  const kpi=(l,v,u,d,up)=>'<div class="kpi"><span>'+l+'</span><b>'+v+(u?'<u>'+u+'</u>':'')+
    '</b><div class="dl '+(up?'up':'dn')+'">'+d+'</div></div>';
  const h=SV[0], hk=SV_KIND[h.k], dl=h.idx-h.was;
  const also=SV.slice(1,4);
  const moved=SV.filter(s=>s.k!=='calm').length;
  const lows =SV.filter(s=>s.p<=s.lo*1.02).length;
  const quiet=SV.filter(s=>s.k==='calm').length;

  body.innerHTML=
    /* ── 오늘의 이슈 ─────────────────────────────────
       좌: 아이템 한 장을 크게. 우: 무슨 일이 벌어졌는지. */
    '<section class="svHero">'+
      '<div class="svShot">'+
        '<img src="'+IMG(h.img)+'" alt="" loading="lazy">'+
        '<span class="svCap">'+h.b+' '+h.n+' · '+svWon(h.p)+'</span>'+
      '</div>'+
      '<div class="svSide">'+
        '<div class="svTop">'+
          '<span class="svKicker">찜한 것 중에서 · 오늘</span>'+
          '<i class="svMark" style="--k:'+hk[2]+'"></i>'+
        '</div>'+
        '<h2 class="svTitle">'+hk[1]+'</h2>'+
        '<p class="svLead">'+h.note+'</p>'+
        '<div class="svGauge">'+
          '<div class="svBar">'+
            '<i class="svFill" data-w="'+h.idx+'" style="--k:'+hk[2]+'"><b>트렌드 지수 '+h.idx+'</b></i>'+
            '<span class="svRest">지난주 대비 +'+dl+'</span>'+
            '<u class="svTick" data-x="'+h.was+'"><em>지난주 '+h.was+'</em></u>'+
          '</div>'+
        '</div>'+
        '<div class="svActs">'+
          '<button type="button" class="svBtn" data-go="life">수명주기에서 보기</button>'+
          '<button type="button" class="svBtn" data-v="salmal">살!말?에 올리기</button>'+
        '</div>'+
        '<div class="svMeta">'+h.d+'일 전 찜 · 같은 걸 찜한 사람 1,284명 · 오늘 04:12 감지</div>'+
      '</div>'+
    '</section>'+

    /* ── 오늘 더 있었던 일 ── */
    '<section class="svAlso">'+
      '<div class="svAlsoH"><h3>오늘 더 있었던 일</h3><em>'+also.length+' MORE</em></div>'+
      '<div class="svAlsoGrid">'+also.map(s=>{
        const k=SV_KIND[s.k];
        return '<div class="svAlsoCard" style="--k:'+k[2]+'">'+
          '<div class="svAlsoTop"><span class="svTag">'+k[0]+'</span>'+
            '<u><img src="'+IMG(s.img)+'" alt="" loading="lazy"></u></div>'+
          '<b>'+s.n+'</b><span class="svAlsoB">'+s.b+'</span>'+
          '<p>'+s.note.replace(/<\/?b>/g,'')+'</p></div>'}).join('')+
      '</div>'+
    '</section>'+

    /* ── 요약 ── */
    '<div class="kpis" style="margin-top:16px">'+
      kpi('찜해둔 것',String(SV.length),'개','이번 주 +2',1)+
      kpi('오늘 움직인 것',String(moved),'건','어제 3건',1)+
      kpi('최저가 도달',String(lows),'건','알림 받음',1)+
      kpi('한 달째 조용한 것',String(quiet),'건','정리 후보',0)+
    '</div>'+

    /* ── 전체 목록 ── */
    '<section class="panelC svList" style="margin-top:12px">'+
      '<div class="ph"><h3>찜한 것 전체</h3><em>WATCHLIST</em></div>'+
      '<div class="svFilter">'+SV_TABS.map(t=>{
        const c=t[0]==='all'?SV.length:SV.filter(s=>s.k===t[0]).length;
        return '<button type="button" class="svChip'+(t[0]===SV_F?' on':'')+'" data-sv="'+t[0]+'">'+
          t[1]+'<i>'+c+'</i></button>'}).join('')+'</div>'+
      '<div class="svRows" id="svRows">'+svRows()+'</div>'+
      '<div class="wkNote"><i>◆</i><span>'+quiet+'개는 한 달 넘게 아무 일도 없었습니다. '+
        '지켜볼 게 많아지면 정작 움직인 것을 놓칩니다. <b>정리를 권합니다.</b></span></div>'+
    '</section>';

  /* 사이드바를 거치지 않고 다른 파트로 건너뛴다 — 그쪽 항목도 같이 켜 준다 */
  const go=$('#trBody .svBtn[data-go]');
  if(go)go.addEventListener('click',()=>{
    const id=go.dataset.go;
    $$('.sItem').forEach(x=>x.classList.toggle('on',x.dataset.tr===id));
    trRender(id);
  });
  const fl=$('#trBody .svFilter');
  if(fl)fl.addEventListener('click',e=>{
    const b=e.target.closest('button[data-sv]'); if(!b)return;
    SV_F=b.dataset.sv;
    $$('#trBody .svChip').forEach(x=>x.classList.toggle('on',x.dataset.sv===SV_F));
    const host=$('#svRows'); if(!host)return;
    host.innerHTML=svRows(); svRowsIn();
  });
  svAnimate();
}

function svRows(){
  const list=SV_F==='all'?SV:SV.filter(s=>s.k===SV_F);
  if(!list.length)return '<div class="svEmpty">이 상태인 것이 없습니다.</div>';
  return list.map(s=>{
    const k=SV_KIND[s.k], d=s.idx-s.was, atLow=s.p<=s.lo*1.02;
    return '<div class="svRow" style="--k:'+k[2]+'">'+
      '<u class="svTh"><img src="'+IMG(s.img)+'" alt="" loading="lazy"></u>'+
      '<div class="svName"><b>'+s.n+'</b><span>'+s.b+' · '+s.why+'</span></div>'+
      '<div class="svAge">'+s.d+'일 전</div>'+
      '<div class="svIdx"><div class="svMini"><i data-w="'+s.idx+'"></i></div>'+
        '<b>'+s.idx+'</b><em class="'+(d>0?'up':d<0?'dn':'')+'">'+
        (d>0?'+':'')+(d||'—')+'</em></div>'+
      '<div class="svPrice"><b>'+svWon(s.p)+'</b>'+
        '<span>'+(atLow?'최저가':'최저 '+svWon(s.lo))+'</span></div>'+
      '<span class="svBadge">'+k[0]+'</span></div>'}).join('');
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
  const fill=$('#trBody .svFill'), tick=$('#trBody .svTick');
  if(tick)tick.style.left=tick.dataset.x+'%';
  if(!HAS_A){ if(fill)fill.style.width=fill.dataset.w+'%'; svRowsIn(); return }
  /* 카드가 먼저 조용히 나타나고, 그 안에서 이미지와 문구가 움직인다 */
  const card=$('#trBody .svHero');
  if(card)aAnimate(card,{opacity:[0,1],duration:520,ease:'out(2)'});
  /* 이미지는 아래에서 살짝 올라오며 열린다 */
  const shot=$('#trBody .svShot');
  if(shot)aAnimate(shot,{opacity:[0,1],translateY:[22,0],duration:1000,
    ease:aSpring({stiffness:62,damping:17})});
  const side=$$('#trBody .svTop, #trBody .svTitle, #trBody .svLead, '+
                '#trBody .svGauge, #trBody .svActs, #trBody .svMeta');
  aAnimate(side,{opacity:[0,1],translateY:[14,0],duration:760,
    delay:aStagger(70,{start:120}),ease:'out(3)'});
  if(fill){ aUtils.set(fill,{width:'0%'});
    aAnimate(fill,{width:fill.dataset.w+'%',duration:1180,delay:420,
      ease:aSpring({stiffness:58,damping:18})}); }
  if(tick)aAnimate(tick,{opacity:[0,1],duration:600,delay:1000,ease:'out(2)'});
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
   진 쪽 %가 통째로 사라져 버렸다. 이제는 숨기지 않고 tight 를 달아
   글씨가 칸 밖(=상대 막대 위)으로 넘쳐 나오게 둔다. 양쪽 다 항상 읽힌다. */
export function smBarLabels(bars){
  bars.forEach(b=>{
    const sp=b.querySelector('span');
    if(sp)sp.style.opacity='';               /* 혹시 남아 있을 옛 인라인 값 제거 */
    b.classList.toggle('tight', +b.dataset.w < 28);
  });
}
export function smBarFill(bars, opt){
  bars=(bars||[]).filter(Boolean);
  if(!bars.length)return;
  const o=opt||{};
  /* 차오르는 동안에는 칸 안에서 글씨가 드러나야 예쁘니 tight 는 끝나고 붙인다 */
  bars.forEach(b=>{ b.classList.remove('tight'); const sp=b.querySelector('span'); if(sp)sp.style.opacity='' });
  if(!HAS_A){ bars.forEach(b=>{ b.style.width=b.dataset.w+'%' }); smBarLabels(bars); return }
  aUtils.remove(bars);                        /* 돌고 있던 게 있으면 먼저 끊는다 */
  bars.forEach(b=>aUtils.set(b,{width:b.classList.contains('no')?'100%':'0%'}));
  aAnimate(bars,{width:el=>el.dataset.w+'%',
    duration:o.duration||1000,
    delay:aStagger(o.step==null?26:o.step,{start:o.start||180}),
    ease:aSpring({stiffness:66,damping:17}),
    onComplete:()=>smBarLabels(bars)});
}
