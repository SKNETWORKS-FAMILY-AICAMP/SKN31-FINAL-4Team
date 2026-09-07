import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aUtils } from '../../../core/static/js/dom.js';
import { ASSOC_BALLET, PLATFORM_TEMP, SENT_NEG, SENT_POS, TEMP_KW } from './data.js';
import { FEED_SM_PICKS, WK } from './my_feed.js';
import { FS, fsBuild, fsHideSug } from '../../../style/static/js/search.js';
import { G_CFG, KW, fsItem, fsItemFull, gMount, josa, trFillBars } from './render_helpers.js';
import { ME, bioPaint } from '../../../account/static/js/profile.js';
import { S_EDIT, S_FEED, TR_META } from './nav_meta.js';
import { assocClosePop, assocOpenPop } from './assoc_popover.js';
import { gChart, gDraw, gSeed } from './chart_engine.js';
import { kwWire } from './saved_keywords.js';
import { rkChip, rkPaintAv } from '../../../account/static/js/rank.js';
import { smBarFill, svRender } from './discount_resale.js';
import { trCountUp } from './count_up.js';
import { trDial, wkAnimate } from './weekly_report.js';
import { trSideOpen } from '../../../app_shell/static/js/router.js';

/* 탭 자리 — 키워드 검색바 / 커머스 탭 / 없음 세 가지로 갈린다 */
function trTabsRender(id){
  const el=$('#trTabs'); if(!el)return;
  const kwMode=(id==='temp'||id==='assoc'||id==='sentiment');
  el.classList.toggle('kwmode',kwMode);
  if(kwMode){
    el.hidden=false;
    /* 할인률 파트의 챗바와 완전히 같은 골격(.fsWrap/.fsRow/.fsBar).
       세부 검색 버튼만 빼고, 안에서 굴러가는 예시 질문만 파트별로 다르다. */
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
        '</div>'+
        '<div class="fsSug" id="kwSug" hidden></div>'+
      '</div>';
    return;
  }
  if(id==='stock'){
    el.hidden=false;
    const list=['통합','무신사','지그재그','에이블리'];
    if(list.indexOf(TR_TAB)<0)TR_TAB='통합';
    el.innerHTML=list.map(t=>'<button data-t="'+t+'"'+(t===TR_TAB?' class="on"':'')+'>'+t+'</button>').join('');
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

export function trRender(id){
  if(typeof assocClosePop==='function')assocClosePop();
  const m=TR_META[id]||TR_META.myfeed;
  $('#trTitle').textContent=m[0];
  $('#trDesc').textContent=m[1]; $('#trDesc').hidden=!m[1];
  /* 탭 자리는 파트마다 쓰임이 다르다.
     언급량·연관어·긍부정 → 자유 키워드 입력창
     할인률                → 커머스 탭
     그 외                 → 비워 둔다 */
  trTabsRender(id);
  /* 검색은 할인률 · 리세일 · 수명주기 세 파트에서만 쓴다 */
  /* 내 피드만 타이틀/설명 대신 프로필(아바타·이름·등급·소개)을 보여준다 */
  const isMyFeed=(id==='myfeed');
  const tw=$('#trTitleWrap'), tp=$('#trProfile');
  if(tw)tw.hidden=isMyFeed;
  if(tp)tp.hidden=!isMyFeed;
  const kk=$('#trKicker'); if(kk)kk.hidden=(id!=='report');
  const wkSpan=$('.trHead>span'); if(wkSpan)wkSpan.hidden=(id==='report');
  const sw=$('#trSearch');
  if(sw){
    const useSearch=['stock','resale','life'].indexOf(id)>=0;
    sw.hidden=!useSearch;
    if(!useSearch){ FS.sel=[null,null,null,null]; FS.mat=null; fsHideSug();
      const cb=$('#fsChips'); if(cb){cb.hidden=true;cb.innerHTML=''} }
    FS.id=useSearch?id:null;
  }
  const body=$('#trBody'); if(!body)return;
  const kpi=(l,v,u,d,up)=>'<div class="kpi"><span>'+l+'</span><b>'+v+(u?'<u>'+u+'</u>':'')+
    '</b><div class="dl '+(up?'up':'dn')+'">'+d+'</div></div>';

  /* ══════════════ 내 피드 — 취향 펄스 & 살!말? 큐레이션 ══════════════
     (feedit-my-feed.html 디자인 이식) 판정(리포트)과 역할을 분리 —
     여기는 ① 관심 코어의 시장 화제성 + 신규 신호 브리핑,
     ② 세그먼트(체형·스타일 태그)와 아이템 태그가 모두 맞는 살!말?만
     선별 노출한다. 큐레이션 카드는 실제 VOTES 데이터(투표율·마감·매치
     점수)를 그대로 쓰고, 게시자 페르소나만 표시용으로 얹었다. */
  if(id==='myfeed'){
    const won=n=>n.toLocaleString('ko-KR')+'원';
    const hoursTx=h=>h>=24?Math.round(h/24)+'일':h+'시간';
    /* 카드 자체는 실제 살!말? .voteCard 구조를 그대로 쓰고(이미지는 실제
       카드처럼 톤 그라디언트로 대체 — 이 목업엔 실물 이미지가 없다) 매칭
       이유 · 태그는 카드 박스 밖, 그 아래에 별도 블록으로 붙인다. */
    const salCard=p=>
      '<div class="tpPickWrap">'+
        '<article class="voteCard in">'+
          '<div class="fig">'+
            '<div class="plate" style="background:linear-gradient(150deg,'+p.tone[0]+','+p.tone[1]+')"></div>'+
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
          '<div class="tpReasonLine"><span class="tpCheck">✓</span>'+
            '<span><strong>세그먼트 일치</strong> · 체형/스타일 유사도 '+p.seg+'%</span></div>'+
          '<div class="tpReasonLine"><span class="tpCheck">✓</span>'+
            '<span><strong>아이템 취향 일치</strong> · '+p.itemTag+'</span></div>'+
        '</div>'+
        '<div class="tpTags">'+p.tags.map((t,i)=>'<span'+(i<2?' class="hit"':'')+'>'+t+'</span>').join('')+'</div>'+
      '</div>';
    body.innerHTML=
      '<div class="tpSection">'+
        '<div class="tpSecLabel"><h3>내 취향 브리핑</h3><span>TASTE PULSE / LIVE</span></div>'+
        '<div class="tpPulseGrid">'+
          '<article class="tpCard tpHero">'+
            '<div class="tpPulseTop"><span class="tpTag">TREND ALIGNMENT</span>'+
              '<span class="tpDelta">▲ 6° 이번 주</span></div>'+
            '<div class="tpBigDeg">84<em>°</em></div>'+
            '<div class="tpPulseCopy"><strong>내 관심 코어의 시장 화제성</strong>'+
              '<p>블록코어와 아메카지가 동시에 상승 중입니다. 특히 스니커 · 워크 재킷 카테고리에서 반응이 빠르게 붙고 있어요.</p>'+
              '<div class="tpTasteTags"><span class="on">블록코어</span><span class="on">아메카지</span>'+
                '<span>워크웨어</span><span>스트릿</span></div>'+
            '</div>'+
          '</article>'+
          '<article class="tpCard tpSignal">'+
            '<div class="tpSignalHead"><span>NEW SIGNALS DETECTED</span><i class="tpLiveDot"></i></div>'+
            '<div class="tpSignalNum">14<em>signals</em></div>'+
            '<div><h4>내 관심 키워드 관련 신규 신호</h4>'+
              '<p>최근 수집 데이터 중 내 취향 태그와 직접 연결되는 변화만 추렸습니다.</p>'+
              '<div class="tpSignalList"><span>블록코어 <b>+6</b></span><span>아메카지 <b>+4</b></span>'+
                '<span>워크웨어 <b>+3</b></span><span>삼바 <b>+1</b></span></div>'+
            '</div>'+
          '</article>'+
        '</div>'+
        '<article class="tpCard tpBrief">'+
          '<div class="tpBriefNo">01</div>'+
          '<div class="tpBriefText"><b>오늘의 취향 브리핑</b>'+
            '<p>블록코어는 화제성 84°로 확산 구간, 아메카지는 커머스 반응이 강해지는 중입니다. '+
            '지금은 "완전 유행 전" 아이템을 고르기 좋은 타이밍이에요.</p></div>'+
          '<div class="tpBriefScore"><b>2</b> CORE RISING</div>'+
        '</article>'+
      '</div>'+
      '<div class="tpSection" style="padding-top:0">'+
        '<div class="tpSalHead"><div><h3>내 취향 맞춤 <em>살!말?</em></h3>'+
          '<p>전체 살!말? 목록 중 나와 체형·스타일 세그먼트가 유사하고,'+
          '동시에 고민 중인 아이템도 내 취향 태그와 겹치는 글만 선별했습니다.</p></div>'+
          '<div class="tpFilterLogic"><span class="tpLogicChip">TOP 4</span></div>'+
        '</div>'+
        '<div class="tpSalGrid">'+FEED_SM_PICKS.map(salCard).join('')+'</div>'+
        '<div class="tpEmptyMore">취향 조건을 동시에 만족한 고민 4건만 표시 중</div>'+
      '</div>';
    /* 버튼을 눌러도 여기서 투표를 완결시키지 않는다 — 살!/말! 버튼은
       data-v="salmal" 을 달아 살!말? 페이지로 보내고, 실제 투표는
       거기서만 일어난다(문서 전역 [data-v] 클릭 위임을 그대로 탄다). */
    /* 프로필은 우리 계정(ME)과 뱃지 시스템을 따른다 */
    const pv=$('#trProfAv'), pn=$('#trProfNm'), pr=$('#trProfRk');
    if(pv){ pv.textContent=ME.initial; rkPaintAv(pv, ME.rank) }
    if(pn)pn.textContent=ME.name;
    if(pr)pr.outerHTML=rkChip(ME.rank).replace('class="rk','id="trProfRk" class="rk');
    bioPaint();
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
      aAnimate($$('#trBody .tpTasteTags span, #trBody .tpSignalList span'),
        {opacity:[0,1],scale:[.9,1],duration:520,delay:aStagger(36,{start:420}),
         ease:aSpring({stiffness:120,damping:14})});
    }
  }

  else if(id==='report'){
    const hit=WK.hit, band=hit>=85?3:hit>=70?2:hit>=50?1:0;   /* 0 아쉬움 → 3 아주 좋음 */
    const ST=[['POOR','아쉬웠습니다','서두른 구매가 많았습니다. 다음 주엔 수명주기 단계를 먼저 확인해 보세요.'],
              ['MIXED','반반이었습니다','참은 게 맞은 만큼 놓친 것도 있었습니다. 품절 알림을 함께 쓰면 나아집니다.'],
              ['GOOD','괜찮았습니다','대체로 맞았습니다. 놓친 건 대부분 가격보다 재고가 먼저 빠진 경우였습니다. 다음 주에는 할인 신호와 함께 재고 속도를 같이 보세요.'],
              ['EXCELLENT','아주 좋았습니다','참을 것과 살 것을 거의 다 맞췄습니다. 지금 판단 기준을 그대로 유지하셔도 됩니다.']][band];
    const SCALE=['아쉬움','반반','괜찮음','아주 좋음'];
    const maxAct=Math.max.apply(null,WK.days), DAY=['월','화','수','목','금','토','일'];
    const mSum=WK.missReason.reduce((a,r)=>a+r[1],0);
    /* 절약 추이 스파크라인 */
    const H=WK.savedHist, hw=560, hh=96, hp=10;
    const hMax=Math.max.apply(null,H)*1.14;
    const HX=i=>hp+(hw-hp*2)*(i/(H.length-1));
    const HY=v=>hh-6-(hh-22)*(v/hMax);
    const hLine=H.map((v,i)=>(i?'L':'M')+HX(i).toFixed(1)+' '+HY(v).toFixed(1)).join(' ');
    const hArea=hLine+' L'+HX(H.length-1).toFixed(1)+' '+(hh-6)+' L'+hp+' '+(hh-6)+' Z';

    body.innerHTML='<div class="wkReport" id="wkReport">'+
      /* ── 한 줄 요약 — 문서 머리는 위 제목줄이 대신한다 ── */
      '<div class="wkLine">'+
        '<h2>이번 주, <em>'+WK.saved.toLocaleString()+'원</em>을 아끼고 '+
          '<em>'+WK.missed+'건</em>을 놓쳤습니다.</h2>'+
        '<span>'+WK.range+'</span>'+
      '</div>'+
      /* ── 히어로 ── */
      '<section class="wkHero">'+
        '<div class="wkScore">'+
          '<div class="wkEyebrow"><span>WEEKLY DECISION SCORE</span><em>PERSONAL</em></div>'+
          '<div>'+
            '<div class="wkScoreMain"><strong>'+hit+'</strong><small>%</small>'+
              '<span class="lb">판단 적중률</span></div>'+
            '<div class="wkTrack"><i class="fill" data-w="'+hit+'"></i>'+
              '<i class="dot" data-w="'+hit+'"></i></div>'+
            '<div class="wkScale">'+SCALE.map((s,i)=>
              '<span'+(i===band?' class="on"':'')+'>'+s+'</span>').join('')+'</div>'+
          '</div>'+
        '</div>'+
        '<div class="wkCopy">'+
          '<div class="wkState">THIS WEEK · '+ST[0]+'</div>'+
          '<h3>이번 주 판단은 <em>'+ST[1]+'</em></h3>'+
          '<p>'+ST[2]+'</p>'+
          '<div class="wkLedger">'+
            '<div class="ac"><span>아낀 돈</span><b>'+WK.saved.toLocaleString()+'원</b></div>'+
            '<div><span>내린 결정</span><b>'+WK.decided+'건</b></div>'+
            '<div><span>놓친 기회</span><b>'+WK.missed+'건</b></div>'+
            '<div><span>연속 기록</span><b>'+WK.streak+'주</b></div>'+
          '</div>'+
        '</div>'+
      '</section>'+
      /* ── 컨설팅 노트 ── */
      '<section class="wkConsult">'+
        '<div class="mk">AI</div>'+
        '<div class="tx"><span>FEEDiT CONSULTING NOTE</span>'+
          '<p>'+WK.note+'</p></div>'+
        '<span class="tag">'+WK.noteTag+'</span>'+
      '</section>'+
      /* ── 지표 4칸 ── */
      '<section class="wkMetrics">'+
        [['검색한 키워드',WK.search,'개','+'+WK.searchD+' · 지난주 대비',1],
         ['새로 찜한 것',WK.fav,'개','총 '+WK.favTotal+'개 추적 중',0],
         ['살!말? 투표',WK.vote,'표','적중 '+WK.voteHit+'%',1],
         ['읽은 분석',WK.read,'건','평균 '+WK.readMin+'분 열람',0]]
        .map((m,i)=>'<div class="wkMetric'+(m[4]?' hot':'')+'">'+
          '<span class="idx">'+String(i+1).padStart(2,'0')+'</span>'+
          '<span class="lb">'+m[0]+'</span>'+
          '<strong>'+m[1]+'<small>'+m[2]+'</small></strong>'+
          '<em>'+m[3]+'</em></div>').join('')+
      '</section>'+
      /* ── 요일별 활동 · 취향 지분 ── */
      '<section class="wkG2">'+
        '<article class="wkCard">'+
          '<div class="wkCardHead"><h3>요일별 활동</h3><em>PEAK · '+WK.peak+'</em></div>'+
          '<div class="wkDays"><div class="wkBarset">'+
          DAY.map((d,i)=>{const v=WK.days[i];
            return '<div class="wkDay'+(v===maxAct?' peak':'')+(d===WK.today?' today':'')+'">'+
              '<span class="v">'+v+'</span>'+
              '<span class="t"><i data-h="'+Math.round(v/maxAct*100)+'"></i></span>'+
              '<span class="l">'+d+'</span></div>'}).join('')+
          '</div></div>'+
          '<div class="wkNote"><i>◆</i><span><b>'+WK.bestDay+'요일</b>에 가장 많이 보셨습니다. '+
            '주말에 몰아보는 편이라면 금요일 저녁 리포트 알림이 잘 맞습니다.</span></div>'+
        '</article>'+
        '<article class="wkCard">'+
          '<div class="wkCardHead"><h3>내 취향 지분</h3><em>VS. LAST WEEK</em></div>'+
          '<div class="wkTasteList">'+WK.taste.map((t,i)=>
            '<div class="wkTaste'+(i===0?' primary':'')+'"><span>'+t[0]+'</span>'+
            '<span class="rail"><i data-w="'+t[1]+'"></i></span>'+
            '<b>'+t[1]+'%</b>'+
            '<em class="'+(t[2]>=0?'up':'')+'">'+(t[2]>0?'+':'')+t[2]+'%p</em></div>').join('')+
          '</div>'+
          '<div class="wkNote"><i>◆</i><span>이번 주 새로 유입된 축은 <b>'+WK.newTaste+'</b>입니다. '+
            '추천에 반영되기 시작했습니다.</span></div>'+
        '</article>'+
      '</section>'+
      /* ── 놓친 이유 · 또래 비교 ── */
      '<section class="wkG2 wkG2b">'+
        '<article class="wkCard">'+
          '<div class="wkCardHead"><h3>놓친 이유</h3><em>'+WK.missed+' MISSED</em></div>'+
          '<div class="wkStack">'+WK.missReason.map(r=>
            '<i data-w="'+Math.round(r[1]/mSum*100)+'"></i>').join('')+'</div>'+
          '<div class="wkLegend">'+WK.missReason.map((r,i)=>
            '<span><i style="background:'+['var(--coral)','rgba(10,10,10,.42)','rgba(10,10,10,.16)'][i]+
            '"></i>'+r[0]+' <b>'+r[1]+'%</b></span>').join('')+'</div>'+
          '<div class="wkNote"><i>◆</i><span>놓친 것의 대부분은 가격이 아니라 <b>재고</b>였습니다. '+
            '재입고 알림을 함께 쓰면 다음 주엔 줄어듭니다.</span></div>'+
        '</article>'+
        '<article class="wkCard">'+
          '<div class="wkCardHead"><h3>또래 비교</h3><em>SAME TASTE GROUP</em></div>'+
          '<div class="wkPeer">'+
            '<div class="bar"><i data-w="'+(100-WK.percentile)+'"></i>'+
              '<u data-l="'+(100-WK.percentile)+'"></u></div>'+
            '<p>취향이 비슷한 사용자 중 <b>상위 '+WK.percentile+'%</b>입니다. '+
              '평균보다 주당 <b>'+WK.peerGap.toLocaleString()+'원</b> 더 아꼈습니다.</p>'+
          '</div>'+
        '</article>'+
      '</section>'+
      /* ── 결정 원장 ── */
      '<section class="wkDecision">'+
        '<div class="wkDecHead"><h3>내가 내린 결정 · 그 뒤에 벌어진 일</h3>'+
          '<em>'+WK.range.split(' · ')[0]+' · '+WK.range.split(' · ')[1]+'</em></div>'+
        WK.log.map(v=>{const lb={danger:'놓침',warn:'지켜보는 중',safe:'잘한 판단'}[v.badge];
          const cls={danger:'missed',warn:'watch',safe:'good'}[v.badge];
          return '<div class="wkRow"><div class="wkRowTop">'+
            '<span class="wkItem"><span class="wkAction">'+v.act+'</span>'+v.k+'</span>'+
            '<span class="wkBadge '+cls+'">'+lb+'</span></div>'+
            '<div class="wkMeta"><span>'+v.when+'</span><span>'+v.res+'</span></div>'+
            '<div class="wkMsg">'+v.msg+'</div></div>'}).join('')+
      '</section>'+
      /* ── 찜 변화 ── */
      '<section class="wkCard" style="margin-top:10px">'+
        '<div class="wkCardHead"><h3>찜한 키워드에 생긴 변화</h3>'+
          '<em>'+WK.watch.length+' SIGNALS DETECTED</em></div>'+
        '<table class="wkTable"><thead><tr><th>키워드</th><th>무슨 일이 있었나</th>'+
          '<th>지금 할 일</th></tr></thead><tbody>'+
        WK.watch.map(r=>'<tr><td><b>'+r[0]+'</b></td>'+
          '<td class="'+(r[2]?'up':'dn')+'">'+r[1]+'</td>'+
          '<td>'+r[3]+'</td></tr>').join('')+
        '</tbody></table>'+
        '<div class="wkNote"><i>◆</i><span>변화가 생긴 것만 모았습니다. 나머지 <b>'+
          (WK.favTotal-WK.watch.length)+'개</b>는 지난주와 같습니다.</span></div>'+
      '</section>'+
      /* ── 다음 주 ── */
      '<section class="wkCard" style="margin-top:10px">'+
        '<div class="wkCardHead"><h3>다음 주에 볼 것</h3><em>EXPECTED INFLECTION</em></div>'+
        '<div class="wkNextGrid">'+WK.next.map(n=>
          '<div class="wkNextCard"><div class="wkNextHead"><i></i><b>'+n[0]+'</b>'+
          '<span>'+n[1]+'</span></div><p>'+n[2]+'</p></div>').join('')+
        '</div></section>'+
      '<div class="wkFoot">'+
        '<span>FEEDiT · FASHION TREND ANALYSIS &amp; RECOMMENDATION CONSULTING</span>'+
        '<span>PERSONAL REPORT · W33 / 2026</span>'+
      '</div>'+
    '</div>';
    wkAnimate();
  }
  else if(id==='saved'){ svRender(body) }
  /* ══════════════ 언급량 · 온도 ══════════════
     결론(지금 얼마나 뜨거운가)을 맨 위에 놓고 근거를 아래에 깐다 — 할인률 변화 페이지와 같은 구성. */
  else if(id==='temp'){
    const kw=KW.q||'발레코어';
    const sd=gSeed(kw+'temp');
    const temp=kw==='발레코어'?82:Math.round(26+sd*70);
    const share=+(2.2+sd*6.4).toFixed(1);
    const yoy=Math.round(40+sd*180);
    const wk=Math.round((gSeed(kw+'twk')-.35)*20);
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
          '<h4><b>'+kw+'</b>'+josa(kw,'은','는')+' 지금 <em>'+BAND[1]+'</em> 구간 — 온도 '+temp+'°</h4>'+
          '<p>'+BAND[2]+'</p>'+
          '<div class="vdBand">'+['차가움','미지근','따뜻함','과열'].map((s,i)=>'<div'+(i===(3-band)?' class="on"':'')+
            '><span>'+s+'</span></div>').join('')+'</div>'+
          '<div class="vdMeta">'+
            '<div><b>'+(wk>0?'+':'')+wk+'°</b><span>이번 주 온도 변화</span></div>'+
          '</div>'+
        '</div></div>'+
      '<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">'+kpi('플랫폼 점유율',share+'','%','+0.6%p 전주 대비',1)+
        kpi('전년 동기 대비','+'+yoy,'%','계절성 보정',1)+
        kpi('신규 진입 키워드',TEMP_KW[TEMP_KW.length-1].k,'','이번 주 새로 감지',1)+'</div>'+
      '<div class="trGrid">'+
        '<div class="panelC"><div class="gHead"><h3>언급량 · 온도 추이</h3></div>'+
          '<div data-chart="tempMain"></div>'+
          '<div class="note"><i>◆</i>정규화된 언급량과 트렌드 온도를 나란히 겹쳐 계절성을 걷어내고 봅니다.</div></div>'+
        '<div class="panelC"><div class="ph"><h3>플랫폼별 온도</h3><em>0–100</em></div>'+
          '<table class="mTable"><tr><th>플랫폼</th><th></th><th>온도</th></tr>'+
          PLATFORM_TEMP.map(t=>'<tr><td>'+(t.v>=85?'<b>'+t.k+'</b>':t.k)+'</td>'+
            '<td><span class="bar" style="display:block"><i class="'+(t.v>=85?'c':'')+'" style="width:'+t.v+'%"></i></span></td>'+
            '<td class="n '+(t.v>=65?'up':'dn')+'">'+t.v+'°</td></tr>').join('')+
          '</table><div class="note"><i>◆</i>플랫폼마다 온도차가 있다면 아직 확산 초반 구간입니다.</div></div>'+
      '</div>';
    G_CFG.tempMain={key:kw+'temp',min:0,max:100,
      sets:[{id:'m',name:'언급량 지수',shape:temp>=65?'rise':temp>=40?'peak':'late',lo:8,hi:96,unit:''},
            {id:'t',name:'트렌드 온도 (°)',shape:temp>=65?'rise':'peak',lo:Math.max(6,temp-30),hi:Math.min(100,temp+12),unit:'°',accent:1}]};
    gChart('[data-chart="tempMain"]',G_CFG.tempMain); trDial(); trFillBars();
    kwWire('temp');
  }
  /* ══════════════ 연관어 ══════════════
     "지금 무엇과 함께 언급되나 · 얼마나 빠르게 번지고 있나"를 결론 카드로 먼저 답한다. */
  else if(id==='assoc'){
    const kw=KW.q||'발레코어';
    const ALL_TAGS=Object.keys(ASSOC_BALLET).reduce((a,cat)=>a.concat(ASSOC_BALLET[cat]),[]);
    const MAX_TAGS=50; /* 축 5개 × 축당 최대 10개 */
    const density=Math.round(ALL_TAGS.length/MAX_TAGS*100);
    const topTag=ALL_TAGS.slice().sort((a,b)=>b.v-a.v)[0];
    const catTotals=Object.keys(ASSOC_BALLET).map(cat=>[cat,ASSOC_BALLET[cat].reduce((s,a)=>s+a.v,0)]);
    const topCat=catTotals.slice().sort((a,b)=>b[1]-a[1])[0][0];
    const band=ALL_TAGS.length>=38?0:ALL_TAGS.length>=25?1:ALL_TAGS.length>=13?2:3;
    const RAMP=['#b23b3b','#c98a1b','#3d7fd6','#1f9e6e'].slice(0,4-band);
    const BAND=[['#1f9e6e','폭발적 확산','5개 축 전반에 걸쳐 연관어가 최대치에 가깝게 쌓였습니다. 소비자 언어가 이미 풍부하게 형성된 상태입니다.'],
                ['#3d7fd6','활발한 확산','연관어가 절반 이상 채워졌습니다. 축마다 고르게 늘고 있는지 확인해볼 때입니다.'],
                ['#c98a1b','완만한 확산','연관어가 서서히 쌓이고 있지만 아직 절반에 못 미칩니다. 확산 초반 구간입니다.'],
                ['#b23b3b','정체','연관어 수가 아직 적어 판단하기엔 이릅니다. 소재가 한정적으로 소비되고 있을 가능성이 있습니다.']][band];
    const badgeHtml=ch=>ch==='new'?'<span class="axChg new">NEW</span>':
      ch>0?'<span class="axChg up">▲'+ch+'</span>':ch<0?'<span class="axChg">▼'+Math.abs(ch)+'</span>':
      '<span class="axChg">–</span>';
    body.innerHTML=
      '<div class="verdict" style="--sc:'+BAND[0]+'">'+
        '<div class="dial"><svg viewBox="0 0 120 120">'+
          '<circle class="trk" cx="60" cy="60" r="50"/>'+
          '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+density+'" '+
            'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
          '<span class="num"><b data-count="'+density+'">0</b><small>연관어 포화도 %</small></span></div>'+
        '<div class="vdTx">'+
          '<h4><b>'+kw+'</b>'+josa(kw,'은','는')+' 지금 <em>'+BAND[1]+'</em> 단계입니다.</h4>'+
          '<p>'+BAND[2]+'</p>'+
          '<div class="vdBand">'+['정체','완만','활발','폭발'].map((s,i)=>'<div'+(i===(3-band)?' class="on"':'')+
            '><span>'+s+'</span></div>').join('')+'</div>'+
          '<div class="vdMeta">'+
            '<div><b>'+ALL_TAGS.length+'건</b><span>연관어 총량</span></div>'+
          '</div>'+
        '</div></div>'+
      '<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">'+
        kpi('최다 언급 연관어',topTag.n,'','현재 최고 언급량',1)+
        kpi('가장 뜨거운 축',topCat,'','축별 언급량 합산 1위',1)+
        kpi('축당 평균 다양성',(ALL_TAGS.length/Object.keys(ASSOC_BALLET).length).toFixed(1),'개','핵심 연관어 수',1)+'</div>'+
      '<div class="trGrid">'+
        '<div class="panelC"><div class="gHead"><h3>연관어 총량 추이</h3></div>'+
          '<div data-chart="assocMain"></div>'+
          '<div class="note"><i>◆</i>총량이 온도보다 먼저 꺾이면 화제성은 남았지만 다양성이 좁아지고 있다는 신호입니다.</div></div>'+
        '<div class="panelC"><div class="ph"><h3>축별 비중</h3><em>KEYWORDS</em></div>'+
          '<table class="mTable"><tr><th>축</th><th></th><th>키워드 수</th></tr>'+
          catTotals.map(c=>{const cnt=ASSOC_BALLET[c[0]].length;
            const pct=Math.round(cnt/ALL_TAGS.length*100);
            return '<tr><td>'+(c[0]===topCat?'<b>'+c[0]+'</b>':c[0])+'</td>'+
              '<td><span class="bar" style="display:block"><i class="'+(c[0]===topCat?'c':'')+'" style="width:'+(pct*3)+'%"></i></span></td>'+
              '<td class="n">'+cnt+'개</td></tr>'}).join('')+
          '</table><div class="note"><i>◆</i>축 하나에 몰릴수록 유행이 아니라 단일 아이템 소비일 확률이 높습니다.</div></div>'+
      '</div>'+
      '<div class="assocGrid" style="margin-top:12px">'+
      Object.keys(ASSOC_BALLET).map((cat,ci)=>{const arr=ASSOC_BALLET[cat];
        const max=Math.max.apply(null,arr.map(a=>a.v));
        return '<div class="panelC"><div class="axHead"><span class="dot"></span><h3>'+cat+'</h3></div>'+
          '<div class="axList">'+arr.map((a,ai)=>{const pct=Math.round(a.v/max*100);
            return '<button class="axRow'+(ai===0?' top':'')+'" data-ci="'+ci+'" data-ai="'+ai+'">'+
              '<span class="axNum">'+(ai+1)+'</span>'+
              '<span class="axName">'+a.n+'</span>'+
              '<span class="axBar"><i class="'+(ai===0?'c':'')+'" style="width:'+pct+'%"></i></span>'+
              badgeHtml(a.ch)+
            '</button>'}).join('')+
          '</div></div>'}).join('')+'</div>';
    G_CFG.assocMain={key:kw+'assoc',
      sets:[{id:'a',name:'연관어 총량',shape:band<=1?'rise':'peak',lo:Math.max(6,ALL_TAGS.length*30-200),hi:ALL_TAGS.length*30+120,unit:'건'}]};
    gChart('[data-chart="assocMain"]',G_CFG.assocMain); trDial();
    kwWire('assoc');
    $$('#trBody .axList .axRow').forEach(btn=>{
      btn.addEventListener('click',e=>{
        e.stopPropagation();
        const cat=Object.keys(ASSOC_BALLET)[+btn.dataset.ci];
        const item=ASSOC_BALLET[cat][+btn.dataset.ai];
        assocOpenPop(btn,cat,item);
      });
    });
  }
  /* ══════════════ 긍부정 ══════════════
     "사려는 사람이 많은가 · 망설이게 하는 게 뭔가"를 결론 카드로 먼저 답한다. */
  else if(id==='sentiment'){
    const kw=KW.q||'발레코어';
    const posSum=SENT_POS.reduce((s,p)=>s+p[1],0), negSum=SENT_NEG.reduce((s,p)=>s+p[1],0);
    const score=68, posPct=82, negPct=18;
    const restock=640, wow=5;
    const band=score>=75?0:score>=55?1:score>=35?2:3;
    const RAMP=['#b23b3b','#c98a1b','#3d7fd6','#1f9e6e'].slice(0,4-band);
    const BAND=[['#1f9e6e','강한 구매 신호','긍정 신호가 압도적입니다. 지금 재고·물량을 걱정할 시점입니다.'],
                ['#3d7fd6','구매 신호 우세','긍정 쪽이 앞서 있습니다. 부정 신호가 늘지 않는지만 함께 지켜보세요.'],
                ['#c98a1b','팽팽한 신호','긍정과 부정이 비슷하게 맞섭니다. 부정 신호의 종류를 먼저 확인해야 합니다.'],
                ['#b23b3b','구매 저해 신호 우세','부정 신호가 앞섭니다. 가격·실물 관련 이슈부터 해소돼야 반등합니다.']][band];
    body.innerHTML=
      '<div class="verdict" style="--sc:'+BAND[0]+'">'+
        '<div class="dial"><svg viewBox="0 0 120 120">'+
          '<circle class="trk" cx="60" cy="60" r="50"/>'+
          '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+score+'" '+
            'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
          '<span class="num"><b data-count="'+score+'">0</b><small>구매의향 지수</small></span></div>'+
        '<div class="vdTx">'+
          '<h4><b>'+kw+'</b>'+josa(kw,'은','는')+' 지금 <em>'+BAND[1]+'</em>입니다.</h4>'+
          '<p>'+BAND[2]+'</p>'+
          '<div class="vdBand">'+['저해우세','팽팽','우세','강한신호'].map((s,i)=>'<div'+(i===(3-band)?' class="on"':'')+
            '><span>'+s+'</span></div>').join('')+'</div>'+
          '<div class="vdMeta">'+
            '<div><b>'+posPct+'%</b><span>긍정 신호 비중</span></div>'+
            '<div><b>'+negPct+'%</b><span>부정 신호 비중</span></div>'+
          '</div>'+
        '</div></div>'+
      '<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">'+
        kpi('총 신호량',(posSum+negSum).toLocaleString(),'건','긍정+부정 합산',1)+
        kpi('최다 긍정 신호',SENT_POS[0][0],'',SENT_POS[0][1].toLocaleString()+'건',1)+
        kpi('최다 부정 신호',SENT_NEG[0][0],'',SENT_NEG[0][1].toLocaleString()+'건',0)+'</div>'+
      '<div class="trGrid">'+
        '<div class="panelC"><div class="gHead"><h3>구매의향 지수 추이</h3></div>'+
          '<div data-chart="sentMain"></div>'+
          '<div class="note"><i>◆</i>두 선이 벌어질수록 구매 의향이 뚜렷해지는 구간이고, 좁아지면 망설임이 커지는 구간입니다.</div></div>'+
        '<div class="panelC"><div class="ph"><h3>신호 유형별 건수</h3><em>POS · NEG</em></div>'+
          '<table class="mTable"><tr><th>신호</th><th></th><th>건수</th></tr>'+
          SENT_POS.concat(SENT_NEG).sort((a,b)=>b[1]-a[1]).map(p=>{const isPos=SENT_POS.indexOf(p)>=0;
            return '<tr><td>'+p[0]+'</td>'+
              '<td><span class="bar" style="display:block"><i class="'+(isPos?'c':'')+'" style="width:'+Math.round(p[1]/1240*100)+'%"></i></span></td>'+
              '<td class="n '+(isPos?'up':'dn')+'">'+p[1].toLocaleString()+'</td></tr>'}).join('')+
          '</table><div class="note"><i>◆</i>주황이 긍정, 회색이 부정 신호입니다.</div></div>'+
      '</div>';
    G_CFG.sentMain={key:kw+'sent',min:0,max:100,
      sets:[{id:'p',name:'긍정 신호 비중 (%)',shape:'rise',lo:Math.max(10,posPct-30),hi:posPct+8,unit:'%',accent:1},
            {id:'n',name:'부정 신호 비중 (%)',shape:'fall',lo:Math.max(4,negPct-6),hi:negPct+22,unit:'%'}]};
    gChart('[data-chart="sentMain"]',G_CFG.sentMain); trDial(); trFillBars();
    kwWire('sentiment');
  }
  else if(id==='stock'){
    const it=fsItem(), full=fsItemFull(), sd=gSeed(it);
    const disc=Math.round(12+sd*38);                 /* 현재 할인률 */
    const temp=Math.round(24+gSeed(it+'t')*72);      /* 트렌드 온도 0~100 */
    const dUp=Math.round((gSeed(it+'d')-.35)*26);    /* 최근 2주 변화 %p */
    const rising=dUp>0;
    /* 점수 = 싸게 사는 정도(할인률) − 식어가는 정도(온도 낮음).
       할인이 커도 온도가 죽었으면 좋은 매수가 아니다. */
    const score=Math.max(4,Math.min(98,Math.round(disc*0.9+temp*0.45-(rising?dUp*1.1:0))));
    const band=score>=75?0:score>=55?1:score>=35?2:3;
    const RAMP=['#b23b3b','#e0642f','#c98a1b','#1f9e6e'].slice(0,4-band);
    const BAND=[['#1f9e6e','지금이 적기','할인이 충분히 붙었는데 트렌드 온도는 아직 살아 있습니다. 가격과 수요가 겹치는 구간입니다.'],
                ['#c98a1b','사도 괜찮음','나쁘지 않은 시점입니다. 다만 조금 더 기다리면 할인폭이 커질 여지가 남아 있습니다.'],
                ['#e0642f','조금 더 대기','할인은 시작됐지만 아직 초반입니다. 2~3주 뒤 재확인을 권합니다.'],
                ['#b23b3b','지금은 비추천','트렌드가 이미 식은 뒤에 붙는 할인입니다. 싸 보여도 오래 입지 못할 확률이 높습니다.']][band];
    const SITES=[['무신사',Math.round(disc+3+sd*6)],['지그재그',Math.round(disc-2+sd*4)],
                 ['에이블리',Math.round(disc+1+sd*5)]].sort((x,y)=>y[1]-x[1]);
    const best=SITES[0];
    const price=Math.round((69000+sd*180000)/1000)*1000;
    const now=Math.round(price*(1-best[1]/100)/100)*100;

    if(TR_TAB==='통합'){
      /* 검색바 바로 아래 한 줄 — 별도 장치 없이 문구로만, 강조는 확실히 */
      body.innerHTML=
        '<p class="cheapest"><b>'+full+'</b>'+josa(full,'은','는')+' 지금 <u>'+best[0]+'</u>가 가장 저렴합니다 '+
          '<s>'+price.toLocaleString()+'원 → '+now.toLocaleString()+'원 · '+best[1]+'% 할인</s></p>'+
        /* ── 결론 카드 ── */
        '<div class="verdict" style="--sc:'+BAND[0]+'">'+
          '<div class="dial"><svg viewBox="0 0 120 120">'+
            '<circle class="trk" cx="60" cy="60" r="50"/>'+
            '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+score+'" '+
              'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
            '<span class="num"><b data-count="'+score+'">0</b><small>구매 점수</small></span></div>'+
          '<div class="vdTx">'+
            '<h4><b>'+full+'</b>'+josa(full,'은','는')+' 현재 <em>'+(rising?'할인 상승세':'할인 하락세')+'</em>입니다.<br>'+
              '트렌드 지수 '+temp+'°와 비교하면 — <em>'+BAND[1]+'</em>.</h4>'+
            '<p>'+BAND[2]+'</p>'+
            '<div class="vdBand">'+[0,1,2,3].map(i=>'<div'+(i===band?' class="on"':'')+'>'+
              '<span>'+['적기','양호','대기','비추천'][i]+'</span></div>').join('')+'</div>'+
            '<div class="vdMeta">'+
              '<div><b>'+disc+'%</b><span>현재 할인률</span></div>'+
              '<div><b>'+temp+'°</b><span>트렌드 온도</span></div>'+
              '<div><b>'+(dUp>0?'+':'')+dUp+'%p</b><span>최근 2주</span></div>'+
              '<div><b>'+now.toLocaleString()+'원</b><span>최저가</span></div>'+
            '</div>'+
          '</div></div>'+
        '<div class="kpis">'+kpi('할인 시작','D-'+Math.round(6+sd*40),'','처음 감지된 시점',0)+
          kpi('정가 유지 비율',Math.round(64-disc)+'','%','판매처 기준',0)+
          kpi('최대 할인폭',Math.round(disc+8+sd*12)+'','%','기간 내 최고',0)+
          kpi('재입고 횟수',Math.round(1+sd*5)+'','회','최근 8주',1)+'</div>'+
        '<div class="trGrid">'+
          '<div class="panelC"><div class="gHead"><h3>할인률 · 트렌드 온도</h3></div>'+
            '<div data-chart="stockMain"></div>'+
            '<div class="note"><i>◆</i>두 선이 벌어질수록 "식은 뒤 붙는 할인"입니다. '+
              '겹쳐 움직이면 아직 수요가 남아 있는 정상 세일입니다.</div></div>'+
          '<div class="panelC"><div class="ph"><h3>판매처별 최저가</h3><em>실시간</em></div>'+
            '<table class="mTable"><tr><th>판매처</th><th>할인률</th><th>최저가</th></tr>'+
            SITES.map((s,i)=>{const pv=Math.round(price*(1-s[1]/100)/100)*100;
              return '<tr><td>'+(i===0?'<b>'+s[0]+'</b>':s[0])+'</td>'+
                '<td class="n '+(i===0?'up':'dn')+'">'+s[1]+'%</td>'+
                '<td class="n">'+pv.toLocaleString()+'원</td></tr>'}).join('')+'</table>'+
            '<div class="note"><i>◆</i>같은 상품이라도 판매처별 할인률이 '+
              (SITES[0][1]-SITES[SITES.length-1][1])+'%p 차이 납니다.</div></div>'+
        '</div>';
    } else {
      /* ── 플랫폼별 세부 분석 ── */
      const ps=gSeed(it+TR_TAB);
      const pd=Math.round(disc+(ps-.5)*14), cnt=Math.round(120+ps*1400);
      const sizes=['XS','S','M','L','XL'].map((z,i)=>[z,Math.round(4+gSeed(it+TR_TAB+z)*92)]);
      const soldout=sizes.filter(z=>z[1]<18);
      body.innerHTML=
        '<div class="kpis">'+kpi(TR_TAB+' 할인률',pd+'','%',(pd>disc?'통합 평균보다 높음':'통합 평균보다 낮음'),pd>disc?1:0)+
          kpi('판매 상품 수',cnt.toLocaleString(),'개','이 키워드 기준',1)+
          kpi('품절 사이즈',soldout.length+'','개',soldout.length?soldout.map(z=>z[0]).join(' · '):'없음',0)+
          kpi('쿠폰 중복',(ps>.5?'가능':'불가'),'',(ps>.5?'카드 할인 별도':'단독 적용만'),ps>.5?1:0)+'</div>'+
        '<div class="trGrid">'+
          '<div class="panelC"><div class="gHead"><h3>'+TR_TAB+' 할인률 추이</h3></div>'+
            '<div data-chart="stockPlat"></div>'+
            '<div class="note"><i>◆</i>주황 선이 '+TR_TAB+', 검정 선이 전체 평균입니다.</div></div>'+
          '<div class="panelC"><div class="ph"><h3>사이즈별 재고</h3><em>'+TR_TAB+'</em></div>'+
            '<table class="mTable"><tr><th>사이즈</th><th>재고</th><th>상태</th></tr>'+
            sizes.map(z=>'<tr><td><b>'+z[0]+'</b></td>'+
              '<td><span class="bar" style="display:block"><i class="'+(z[1]<18?'c':'')+'" style="width:'+z[1]+'%"></i></span></td>'+
              '<td class="n '+(z[1]<18?'up':'dn')+'">'+(z[1]<18?'품절 임박':z[1]<50?'보통':'여유')+'</td></tr>').join('')+
            '</table>'+
            '<div class="note"><i>◆</i>재고가 빠질수록 할인이 멈출 확률이 올라갑니다.</div></div>'+
        '</div>'+
        '<div class="panelC" style="margin-top:12px"><div class="ph"><h3>'+TR_TAB+' 세부 지표</h3>'+
          '<em>통합 대비</em></div><div class="statRow">'+
          [['평균 배송일',(1+Math.round(ps*3))+'<u>일</u>','주문에서 도착까지'],
           ['리뷰 평점',(3.6+ps*1.3).toFixed(1)+'<u>/5</u>','최근 3개월 리뷰'],
           ['반품률',Math.round(4+ps*14)+'<u>%</u>','사이즈 이슈 비중 높음']]
          .map(x=>'<div class="bigStat"><b>'+x[1]+'</b><span>'+x[0]+' — '+x[2]+'</span></div>').join('')+
        '</div></div>';
    }
    G_CFG.stockMain=item=>({key:item+'stock',min:0,max:100,
      sets:[{id:'d',name:'할인률 (%)',shape:'late',lo:6,hi:disc+6,unit:'%'},
            {id:'t',name:'트렌드 온도 (°)',shape:'fall',lo:Math.max(10,temp-28),hi:temp+14,unit:'°',accent:1}]});
    G_CFG.stockPlat=item=>({key:item+TR_TAB,min:0,max:100,
      sets:[{id:'a',name:'전체 평균 (%)',shape:'late',lo:6,hi:disc+6,unit:'%'},
            {id:'p',name:TR_TAB+' (%)',shape:'late',lo:8,hi:disc+12,unit:'%',accent:1}]});
    gMount(); trDial();
  }

  /* ══════════════ 리세일 시세 지수 ══════════════
     "지금 팔면 얼마 받나 · 사면 손해인가"를 먼저 답한다. */
  else if(id==='resale'){
    const it=fsItem(), full=fsItemFull(), sd=gSeed(it+'r');
    const idx=+(0.48+sd*0.95).toFixed(2);            /* 중고가 ÷ 정가 */
    const wow=+((gSeed(it+'w')-.5)*0.22).toFixed(2); /* 전주 대비 */
    const retail=Math.round((79000+sd*260000)/1000)*1000;
    const used=Math.round(retail*idx/1000)*1000;
    const keep=Math.round(idx*100);
    const lead=Math.round(3+sd*11);                  /* 소셜보다 며칠 먼저 움직였나 */
    const vol=Math.round(40+sd*760);
    const days=Math.round(3+sd*26);                  /* 평균 거래 소요일 */
    const prem=idx>=1;
    const RAMP=['#b23b3b','#c98a1b','#1f9e6e'].slice(0,(prem?3:idx>=.7?2:1));
    const SZ=['XS','S','M','L','XL'].map(z=>[z,+(idx*(0.82+gSeed(it+z+'p')*0.42)).toFixed(2)]);
    const best=SZ.slice().sort((a,b)=>b[1]-a[1])[0];
    body.innerHTML=
      '<div class="verdict" style="--sc:'+(prem?'#1f9e6e':idx>=.7?'#c98a1b':'#b23b3b')+'">'+
        '<div class="dial"><svg viewBox="0 0 120 120">'+
          '<circle class="trk" cx="60" cy="60" r="50"/>'+
          '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+keep+'" '+
            'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
          '<span class="num"><b data-count="'+keep+'">0</b><small>가치 유지율 %</small></span></div>'+
        '<div class="vdTx">'+
          '<h4><b>'+full+'</b>'+josa(full,'을','를')+' 지금 되팔면 <em>정가의 '+keep+'%</em>'+
            (prem?' — <em>프리미엄</em>이 붙어 있습니다.':'를 받습니다.')+'</h4>'+
          '<p>'+(prem
            ? '발매가보다 비싸게 거래되는 상태입니다. 지금 사면 정가 이상을 지불하게 되고, 갖고 있다면 파는 쪽이 유리합니다.'
            : idx>=.7
              ? '중고 가치가 잘 버티고 있습니다. 몇 시즌 입고 되팔아도 손실이 크지 않은 구간입니다.'
              : '가치 하락이 빠른 구간입니다. 되팔 생각이라면 지금이 마지노선에 가깝습니다.')+'</p>'+
          '<div class="vdMeta">'+
            '<div><b>'+retail.toLocaleString()+'원</b><span>정가</span></div>'+
            '<div><b>'+used.toLocaleString()+'원</b><span>중고 시세</span></div>'+
            '<div><b>'+(wow>0?'+':'')+(wow*100).toFixed(0)+'%p</b><span>전주 대비</span></div>'+
            '<div><b>'+days+'일</b><span>평균 판매 소요</span></div>'+
          '</div>'+
        '</div></div>'+
      '<div class="kpis">'+
        kpi('거래량',vol.toLocaleString(),'건','최근 4주',vol>300?1:0)+
        kpi('소셜 대비 선행',lead+'','일','시세가 먼저 움직임',1)+
        kpi('실수령액',Math.round(used*0.945/100*100).toLocaleString(),'원','수수료 5.5% 차감',0)+
        kpi('손익분기',Math.round(retail*0.945/(used||1)*100)>100?'미달':'달성','',
            '정가 대비 회수 가능성',Math.round(retail*0.945/(used||1)*100)>100?0:1)+'</div>'+
      '<div class="trGrid">'+
        '<div class="panelC"><div class="gHead"><h3>중고 시세 vs 언급 온도</h3></div>'+
          '<div data-chart="resMain"></div>'+
          '<div class="note"><i>◆</i>시세(검정)가 온도(주황)보다 <b>'+lead+'일</b> 먼저 꺾이는 패턴입니다. '+
            '되팔 계획이라면 온도가 아니라 이 선을 보세요.</div></div>'+
        '<div class="panelC"><div class="ph"><h3>사이즈별 시세 배수</h3><em>정가=1.00</em></div>'+
          '<table class="mTable"><tr><th>사이즈</th><th>배수</th><th>실거래가</th></tr>'+
          SZ.map(z=>'<tr><td>'+(z[0]===best[0]?'<b>'+z[0]+'</b>':z[0])+'</td>'+
            '<td class="n '+(z[1]>=1?'up':'dn')+'">×'+z[1].toFixed(2)+'</td>'+
            '<td class="n">'+(Math.round(retail*z[1]/1000)*1000).toLocaleString()+'원</td></tr>').join('')+
          '</table><div class="note"><i>◆</i>흔한 사이즈일수록 배수가 낮습니다. '+
            '<b>'+best[0]+'</b>가 가장 잘 받습니다.</div></div>'+
      '</div>'+
      '<div class="trGrid" style="margin-top:12px">'+
        '<div class="panelC"><div class="gHead"><h3>상태별 가격대</h3></div>'+
          '<table class="mTable"><tr><th>상태</th><th>비중</th><th>시세</th></tr>'+
          [['미착용 (택 포함)',1.14,18],['S급 (착용 3회 이하)',1.0,34],
           ['A급 (생활 사용감)',0.84,31],['B급 (하자 있음)',0.62,17]]
          .map(r=>'<tr><td>'+r[0]+'</td>'+
            '<td><span class="bar" style="display:block"><i style="width:'+(r[2]*2.6)+'%"></i></span></td>'+
            '<td class="n">'+(Math.round(used*r[1]/1000)*1000).toLocaleString()+'원</td></tr>').join('')+
          '</table><div class="note"><i>◆</i>택만 살려도 <b>'+
            Math.round((1.14/0.84-1)*100)+'%</b> 더 받습니다.</div></div>'+
        '<div class="panelC"><div class="ph"><h3>되팔기 체크리스트</h3><em>지금 기준</em></div>'+
          '<div class="statRow" style="grid-template-columns:1fr">'+
          [['언제 팔면 가장 비싼가', (idx>=1?'지금':'약 '+Math.round(2+sd*7)+'주 내'),
            prem?'프리미엄 구간은 평균 5주를 넘기지 않습니다.':'시세 하락 속도가 붙기 전 구간입니다.'],
           ['어디서 가장 빨리 팔리나', ['크림','번개장터','당근'][Math.floor(sd*3)],
            '이 카테고리 평균 '+days+'일 · 수수료 5.5%'],
           ['얼마에 올려야 팔리나', (Math.round(used*1.06/1000)*1000).toLocaleString()+'원',
            '실거래가보다 6% 높게 올려 협상 여지를 둡니다.']]
          .map(x=>'<div class="bigStat" style="padding:11px 0;border-bottom:1px solid var(--pink-3)">'+
            '<span style="font-size:11.5px;color:var(--pink-2)">'+x[0]+'</span>'+
            '<b style="font-size:20px">'+x[1]+'</b>'+
            '<span>'+x[2]+'</span></div>').join('')+
          '</div></div>'+
      '</div>';
    G_CFG.resMain=item=>({key:item+'res',
      sets:[{id:'r',name:'중고 시세 배수',shape:'fall',lo:Math.max(.3,idx-.3),hi:idx+.35,unit:'배'},
            {id:'t',name:'언급 온도 (°)',shape:'peak',lo:18,hi:92,unit:'°',accent:1}]});
    gMount(); trDial();
  }

  /* ══════════════ 수명주기 ══════════════
     "지금 사도 되나 · 언제까지 입을 수 있나" 로만 답한다. */
  else{
    const it=fsItem(), full=fsItemFull(), sd=gSeed(it+'l');
    const stages=['태동','확산','정점','쇠퇴'];
    const si=Math.min(3,Math.floor(sd*4));
    const weeks=[Math.round(38+sd*40),Math.round(22+sd*30),Math.round(9+sd*14),Math.round(2+sd*6)][si];
    const age=Math.round(6+sd*80);                    /* 이 유행이 시작된 지 몇 주 */
    const wear=[Math.round(3+sd*2),Math.round(2+sd*2),Math.round(1+sd*2),1][si];  /* 몇 시즌 더 */
    const SC=['#3d7fd6','#1f9e6e','#c98a1b','#b23b3b'][si];
    const RAMP=['#3d7fd6','#1f9e6e','#c98a1b','#b23b3b'].slice(0,si+1);
    const pct=[22,58,92,40][si];
    const MSG=[
      ['아직 아무도 모릅니다','지금 사면 남들보다 먼저 입는 구간입니다. 다만 물량이 적어 선택지가 좁고, 그대로 사라질 위험도 함께 있습니다.'],
      ['가장 안전한 구간입니다','올라가는 중이라 앞으로 '+weeks+'주는 더 입을 수 있습니다. 물량도 충분해 고르기 좋습니다.'],
      ['지금이 마지막입니다','정점입니다. 사도 되지만 오래 못 갑니다. 오래 입을 옷이라면 다음 것을 보세요.'],
      ['이미 지났습니다','내려온 지 꽤 됐습니다. 싸게 나와도 올해 안에 안 입게 될 확률이 높습니다.']][si];
    const ALT=[['블록코어',62],['아메카지',58],['포엣코어',34],['놈코어',48],['발레코어',88]]
      .filter(x=>x[0]!==it).slice(0,3);
    body.innerHTML=
      '<div class="verdict" style="--sc:'+SC+'">'+
        '<div class="dial"><svg viewBox="0 0 120 120">'+
          '<circle class="trk" cx="60" cy="60" r="50"/>'+
          '<circle class="val" cx="60" cy="60" r="50" data-ramp="'+RAMP.join(',')+'" data-score="'+pct+'" '+
            'stroke-dasharray="314.16" stroke-dashoffset="314.16"/></svg>'+
          '<span class="num"><b data-count="'+pct+'">0</b><small>유행 진행도 %</small></span></div>'+
        '<div class="vdTx">'+
          '<h4><b>'+full+'</b>'+josa(full,'은','는')+' <em>'+stages[si]+'</em> 단계 — '+MSG[0]+'</h4>'+
          '<p>'+MSG[1]+'</p>'+
          '<div class="vdBand">'+stages.map((s,i)=>'<div'+(i===si?' class="on"':'')+
            '><span>'+s+'</span></div>').join('')+'</div>'+
          '<div class="vdMeta">'+
            '<div><b>'+age+'주</b><span>유행 시작 후</span></div>'+
            '<div><b>'+weeks+'주</b><span>남은 기간</span></div>'+
            '<div><b>'+wear+'시즌</b><span>더 입을 수 있음</span></div>'+
            '<div><b>'+(si<2?'상승':'하강')+'</b><span>현재 방향</span></div>'+
          '</div>'+
        '</div></div>'+
      '<div class="kpis">'+
        kpi('지금 사도 되나',(si===3?'아니오':'예'),'',MSG[0],si===3?0:1)+
        kpi('되팔 때 가치',['높음','높음','보통','낮음'][si],'','1년 뒤 기준',si<2?1:0)+
        kpi('비슷한 옷 보유',Math.round(2+sd*7)+'','벌','옷장 기준 추정',0)+
        kpi('회당 비용',Math.round(2400+sd*9000).toLocaleString(),'원','예상 착용 횟수로 나눈 값',0)+'</div>'+
      '<div class="trGrid">'+
        '<div class="panelC"><div class="gHead"><h3>유행 곡선 · 지금 위치</h3></div>'+
          '<div data-chart="lifeMain"></div>'+
          '<div class="note"><i>◆</i>주황 구간이 <b>지금</b>입니다. '+
            (si<2?'아직 올라가는 중이라 여유가 있습니다.':'꼭짓점을 지나면 회복하지 않습니다.')+'</div></div>'+
        '<div class="panelC"><div class="ph"><h3>계절 · 착용 예측</h3><em>앞으로 12개월</em></div>'+
          '<table class="mTable"><tr><th>시기</th><th>착용 가능성</th><th></th></tr>'+
          [['이번 시즌',[70,96,88,44][si]],['다음 시즌',[88,82,52,18][si]],
           ['1년 뒤',[74,54,26,7][si]],['2년 뒤',[46,28,11,3][si]]]
          .map(r=>'<tr><td>'+r[0]+'</td>'+
            '<td><span class="bar" style="display:block"><i class="'+(r[1]>=60?'c':'')+'" style="width:'+r[1]+'%"></i></span></td>'+
            '<td class="n">'+r[1]+'%</td></tr>').join('')+
          '</table><div class="note"><i>◆</i>같은 카테고리 아이템들의 실제 착용 로그로 계산한 값입니다.</div></div>'+
      '</div>'+
      '<div class="trGrid" style="margin-top:12px">'+
        '<div class="panelC"><div class="gHead"><h3>언급량 · 실착 비율</h3></div>'+
          '<div data-chart="lifeGap"></div>'+
          '<div class="note"><i>◆</i>말만 많고 실제로 안 입는 구간은 거품입니다. '+
            '두 선이 붙어 갈수록 진짜 유행입니다.</div></div>'+
        '<div class="panelC"><div class="ph"><h3>대신 볼 만한 것</h3><em>더 오래 갑니다</em></div>'+
          '<div class="flow">'+ALT.map(x=>'<div class="st"><span>'+x[0]+'</span>'+
            '<u><i data-w="'+x[1]+'" '+(x[1]>=60?'class="c"':'')+'></i></u>'+
            '<em>'+(x[1]>=60?'상승':'유지')+'</em></div>').join('')+'</div>'+
          '<div class="note"><i>◆</i>'+(si>=2
            ? '지금 것이 내려오는 중이라 대체 후보를 같이 봅니다.'
            : '지금 것으로 충분합니다. 참고용입니다.')+'</div></div>'+
      '</div>';
    G_CFG.lifeMain=item=>({key:item+'life',band:[si*.25,si*.25+.25],
      sets:[{id:'l',name:'언급량 지수',shape:['rise','rise','peak','fall'][si],lo:8,hi:96,unit:''}]});
    G_CFG.lifeGap=item=>({key:item+'gap',
      sets:[{id:'m',name:'언급량',shape:['rise','rise','peak','fall'][si],lo:10,hi:94,unit:''},
            {id:'w',name:'실착 비율 (%)',shape:['rise','rise','rise','fall'][si],lo:6,hi:62,unit:'%',accent:1}]});
    gMount(); trFillBars(); trDial();
  }
  if(HAS_A)aAnimate($$('#trBody .kpi, #trBody .panelC, #trBody .concl, #trBody .verdict, #trBody .cheapest, #trBody .svAlso'),
    {opacity:[0,1],translateY:[16,0],duration:760,delay:aStagger(60),ease:'out(3)'});
  trCountUp();   /* 카드가 올라오는 동안 숫자도 같이 굴러 올라간다 */
}
function trAnimateSvg(){ gDraw($$('#trBody .lifeSvg path'),1250,320) }
var TR_TAB='통합';

export function trBuild(){
  const mk=(a,host)=>{ const el=$(host); if(!el)return;
    el.innerHTML=a.map(s=>'<button class="sItem" data-tr="'+s.id+'">'+
      '<span class="ic">'+s.ic+'</span><span class="tx">'+s.t+'</span></button>').join('') };
  mk(S_FEED,'#sFeed'); mk(S_EDIT,'#sEdit');
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
  /* 사이드바 하단 프로필 — 운영자 계정이라 최고 등급이 붙는다 */
  const sf=$('#sFoot');
  if(sf){
    const sav=sf.querySelector('.av');
    sav.textContent=ME.initial;          /* 링은 아래 rkPaintAv 가 다시 얹는다 */
    rkPaintAv(sav, ME.rank);
    sf.querySelector('.who b').textContent=ME.name;
    const plan=$('#sFootPlan'); if(plan)plan.textContent=ME.plan;
    const rk=$('#sFootRk');   if(rk)rk.innerHTML=rkChip(ME.rank);   /* 뱃지는 오른쪽 끝에 따로 선다 */
  }
  /* 본문은 여기서 그리지 않는다. 숨어 있는 동안 그리면 등장 애니메이션이
     아무도 안 볼 때 다 끝나버려서, 탭을 열었을 땐 이미 정지 화면이 된다.
     실제로 여는 순간(goView) 에 처음 한 번 그린다. */
}
