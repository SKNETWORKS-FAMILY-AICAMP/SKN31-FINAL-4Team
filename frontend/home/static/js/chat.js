import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aTimeline, aUtils } from '../../../core/static/js/dom.js';
import { cpKeyFor, openChatWith } from './chat_popup.js';

/* ============================================================
   메인 — 홈(챗봇) / 트렌드 분석 / 살!말? / Style / 요금제
   ============================================================ */
export const IMG=n=>'assets/hi/f'+String(n).padStart(2,'0')+'.jpg';

const M_QUESTIONS=[
  ['고프코어','언제 꺾였어?'],['발레코어','아직 유효해?'],['스웨이드','이번 겨울도 갈까?'],
  ['무신사 vs 29CM','지금 온도차가 어때?'],['블록코어','다음은 뭐야?']
];
const HOT=[
  ['발레코어',248,'ballet'],['스웨이드 자켓',186,'classic'],['버건디 니트',142,'classic'],
  ['블록코어',131,'block'],['로퍼',97,'biz'],['바이크코어',88,'bike'],
  ['아메카지',74,'ameka'],['카고 스커트',63,'street'],['고프코어',-42,'gorp'],['오버핏 후드',-31,'street']
];
const M_ANSWERS={
  rise:{ url:'feedit.ai / trend / 2026-W33', title:'이번 주 급상승 키워드',
    rank:[['발레코어','키워드',248,1],['스웨이드 자켓','아이템',186,1],['버건디 니트','컬러',142,1],
          ['로퍼','슈즈',97,1],['고프코어','키워드',-42,0],['오버핏 후드','아이템',-31,0]] },
  ballet:{ url:'feedit.ai / trend / 발레코어', title:'발레코어 — 아직 유효한가',
    rank:[['리본 디테일','서브',214,1],['플랫 슈즈','아이템',168,1],['새틴 스커트','아이템',121,1],
          ['튤 소재','소재',88,1],['핑크 톤','컬러',-18,0],['레그워머','아이템',-36,0]] },
  gorp:{ url:'feedit.ai / trend / 고프코어', title:'고프코어 — 언제 꺾였나',
    rank:[['테크 셸','아이템',-12,0],['트레일 러너','슈즈',-24,0],['플리스','아이템',-38,0],
          ['카라비너','액세서리',-47,0],['고프코어','키워드',-42,0],['등산 자켓','아이템',-55,0]] },
  plat:{ url:'feedit.ai / compare / 무신사 vs 29CM', title:'무신사 vs 29CM — 온도차',
    rank:[['워크 자켓','무신사 우세',132,1],['미니멀 셋업','29CM 우세',119,1],['카고 팬츠','무신사 우세',94,1],
          ['실크 블라우스','29CM 우세',77,1],['로고 티셔츠','무신사 하락',-28,0],['오버핏 코트','양쪽 하락',-41,0]] },
  body:{ url:'feedit.ai / recommend / 코트', title:'내 체형에 맞는 코트',
    rank:[['숄더 발마칸','어깨 좁음',96,1],['싱글 체스터','기장 105',88,1],['하프 더플','캐주얼',64,1],
          ['오버핏 트렌치','주의',-22,0],['박스 더블','주의',-35,0],['크롭 코트','비추천',-58,0]] }
};
const M_PLATFORMS=[['인스타그램',92],['무신사',78],['틱톡',64],['지그재그',51],['29CM',37],['W컨셉',22]];
export const M_CHIPS=[['이번 주 급상승','rise'],['고프코어 꺾였어?','gorp'],['발레코어 유효해?','ballet'],
               ['무신사 vs 29CM','plat'],['체형 맞는 코트','body']];

/* ── 스타일(코어) 데이터 ─────────────────────────────── */
/* ══════════════════════════════════════════════════════════════
   스타일 12종 — 두 층으로 나눈다.
   코어(7) : 지금 이름이 붙어 도는 흐름. 생겨난 해와 진원지가 뚜렷하다.
   원형(5) : 코어들이 갈라져 나온 뿌리. 시작은 오래됐고 사라지지 않는다.
   g 는 그 층, pk 는 수명주기상 현재 위치.
   ══════════════════════════════════════════════════════════════ */
export const STYLES=[
  /* ── 코어 ───────────────────────────────────────────── */
  {id:'ballet', n:'발레코어',    en:'Balletcore',  g:'코어', ph:'assets/look/ballet.jpg', img:4,  st:'2022 · 파리',   pk:'정점 통과', by:'미우미우 22FW 발레 리허설 룩',
   ab:'발레 연습복의 요소를 일상복으로 옮긴 코어로, 미우미우가 2022년 컬렉션에서 리본과 발레 플랫을 전면에 세우면서 시작됐습니다.',
   ab2:'리본 디테일과 새틴 소재, 발레 플랫이 핵심 아이템이며 은은한 발레 핑크 톤이 전체 무드를 완성합니다.',
   kw:['리본','새틴','발레 플랫','튤','발레 핑크']},
  {id:'gorp',   n:'고프코어',    en:'Gorpcore',    g:'코어', ph:'assets/look/gorp.jpg', img:6,  st:'2017 · 뉴욕',   pk:'하락', by:'뉴욕 매거진이 붙인 이름',
   ab:'등산·트레일 장비를 도심에서 입는 코어로, 2017년 뉴욕 매거진이 이름을 붙였고 살로몬과 아크테릭스가 패션 채널로 넘어오면서 폭발했습니다.',
   ab2:'방수 셸 자켓과 트레일 러너, 다용도 포켓이 달린 조끼가 핵심이며 기능성과 실용성을 그대로 드러내는 것이 특징입니다.',
   kw:['테크 셸','트레일 러너','플리스','카라비너']},
  {id:'block',  n:'블록코어',    en:'Blokecore',   g:'코어', ph:'assets/look/block.jpg', img:18, st:'2021 · 런던',   pk:'확산', by:'빈티지 축구 저지 · 틱톡',
   ab:'90년대 영국 축구 팬(bloke)의 옷차림인 빈티지 저지, 트랙 자켓, 스니커에서 시작해 틱톡에서 이름이 붙어 번졌습니다.',
   ab2:'빈티지 축구 저지에 트랙 자켓과 스카프를 겹쳐 입는 레이어드가 핵심이며 클럽 로고와 스폰서 마크가 포인트로 작용합니다.',
   kw:['축구 저지','트랙 자켓','삼바','스카프']},
  {id:'bike',   n:'바이크코어',  en:'Bikercore',   g:'코어', ph:'assets/look/bike.jpg', img:19, st:'2024 · 뉴욕',   pk:'확산', by:'라이더 재킷의 귀환',
   ab:'오토바이를 타지 않아도 바이커의 옷을 입는 코어로, 뿌리는 말론 브란도의 라이더 재킷까지 거슬러 올라가고 최근 셀럽 스트리트 룩을 타고 다시 올라왔습니다.',
   ab2:'가죽 라이더 재킷과 바이커 부츠가 중심이며 스터드와 워싱 데님 같은 장식 요소가 더해져 거친 무드를 냅니다.',
   kw:['라이더 재킷','바이커 부츠','스터드','워싱 데님']},
  {id:'geek',   n:'긱시크',      en:'Geek Chic',   g:'코어', ph:'assets/look/geek.jpg', img:15, st:'2013 · 옥스퍼드 등재', pk:'재상승', by:'2015 구찌 런웨이',
   ab:'괴짜(geek)와 세련됨(chic)의 합성어로, 어설퍼 보이는 조합을 의도적으로 짜 개성으로 뒤집는 코어입니다. ',
   ab2:'2013년 옥스퍼드 사전에 오르고 2015년 구찌 런웨이가 본격적으로 불러냈으며, 뿔테 안경을 매치하는 것이 핵심으로 로퍼로 마무리해 지적인 인상을 완성합니다.',
   kw:['뿔테 안경','가디건','체크 셔츠','로퍼']},
  {id:'norm',   n:'놈코어',      en:'Normcore',    g:'코어', ph:'assets/look/norm.jpg', img:23, st:'2013 · 뉴욕',   pk:'잔존', by:'K-HOLE 리포트',
   ab:'의도적으로 평범한 옷으로, 2013년 트렌드 예측 그룹 K-HOLE이 제안한 개념에서 출발했습니다.',
   ab2:'무지 티셔츠와 치노, 뉴발란스 운동화처럼 눈에 띄지 않는 기본 아이템으로 구성되며 절제된 색상 조합이 특징입니다.',
   kw:['무지 티','치노','뉴발란스','플리스 집업']},
  {id:'biz',    n:'비즈니스코어',en:'Businesscore',g:'코어', ph:'assets/look/biz.jpg', img:20, st:'2023 · 서울',   pk:'확산', by:'오피스 사이렌',
   ab:'사무실 옷을 일상으로 끌어낸 코어로, 셔츠·펜슬 스커트·로퍼가 축입니다.',
   ab2:'셔츠와 펜슬 스커트, 로퍼, 토트백으로 이어지는 오피스 무드를 갖추되 정장보다는 힘을 뺀 실루엣이 특징입니다.',
   kw:['셔츠','펜슬 스커트','로퍼','토트백']},
  {id:'ath',    n:'애슬레저',    en:'Athleisure',  g:'코어', ph:'assets/look/ath.jpg', img:10, st:'2014 · LA',     pk:'재점화', by:'룰루레몬 · 요가 웨어',
   ab:'운동복을 운동 밖으로 끌어낸 코어로, 2014년 요가·필라테스 확산과 함께 자리를 잡았고 레깅스와 조거가 하의의 기본값이 됐습니다.',
   ab2:'레깅스와 조거 팬츠, 크롭 집업이 기본이며 러닝화로 마무리해 활동성과 편안함을 동시에 강조합니다.',
   kw:['레깅스','조거','크롭 집업','러닝화']},

  /* ── 원형 ───────────────────────────────────────────── */
  {id:'classic',n:'클래식',      en:'Classic',     g:'원형', ph:'assets/look/classic.jpg', img:24, st:'상시',          pk:'안정', by:'올드머니',
   ab:'유행을 타지 않는 형태와 소재로, 특정 유행에 기대지 않고 계절과 무관하게 꾸준한 수요를 유지합니다.',
   ab2:'트렌치코트와 캐시미어 니트, 스웨이드 소재, 옥스퍼드 슈즈처럼 고급스러운 소재감이 중심이 되는 조합입니다.',
   kw:['트렌치','캐시미어','스웨이드','옥스퍼드']},
  {id:'street', n:'스트릿웨어',  en:'Streetwear',  g:'원형', ph:'assets/look/street.jpg', img:16, st:'1990s · 도쿄 · 뉴욕', pk:'재상승', by:'스투시 · 슈프림',
   ab:'스케이트와 힙합에서 출발해 하이패션과 섞인 원형으로, 로고 티셔츠와 배기 실루엣에서 시작해 지금의 형태로 넓어졌습니다.',
   ab2:'카고 팬츠와 오버핏 상의, 스케이트 슈즈, 비니로 구성되며 헐렁한 실루엣과 편안한 무드가 핵심입니다.',
   kw:['카고','오버핏','스케이트 슈즈','비니']},
  {id:'ameka',  n:'아메카지',    en:'Amekaji',     g:'원형', ph:'assets/look/ameka.jpg', img:13, st:'1980s · 일본',  pk:'확산', by:'아메리칸 카주얼',
   ab:'미국 워크웨어를 일본식으로 다시 짠 원형으로, 셀비지 데님과 워크 자켓이 축입니다.',
   ab2:'셀비지 데님과 워크 자켓, 치노 팬츠, 부츠로 구성되며 튼튼한 소재와 클래식한 워크웨어 디테일이 특징입니다.',
   kw:['셀비지 데님','워크 자켓','치노','부츠']},
  {id:'grunge', n:'그런지',      en:'Grunge',      g:'원형', ph:'assets/look/grunge.jpg', img:30, st:'1990s · 시애틀',pk:'재점화 대기', by:'시애틀 록 신',
   ab:'90년대 시애틀 록 신에서 나온 원형으로, 플란넬·워싱 데님·컴뱃 부츠가 축입니다.',
   ab2:'플란넬 셔츠와 워싱 데님, 컴뱃 부츠를 겹쳐 입는 레이어드 스타일링이 핵심이며 낡고 헤진 듯한 질감이 특유의 무드를 만듭니다.',
   kw:['플란넬','워싱 데님','컴뱃 부츠','레이어드']},
  {id:'y2k',    n:'Y2K',         en:'Y2K',         g:'원형', ph:'assets/look/y2k.jpg', img:14, st:'1999–2003',     pk:'정점 통과', by:'세기말 · 2020 재유행',
   ab:'세기말 전후의 옷차림이 20년 만에 돌아온 원형으로, 로우라이즈·벨벳 트랙수트·베이비 티·작은 어깨 가방이 핵심입니다.',
   ab2:'로우라이즈 팬츠와 벨벳 트랙수트, 베이비 티, 미니 백처럼 몸에 붙는 실루엣과 반짝이는 소재가 특징입니다.',
   kw:['로우라이즈','벨벳 트랙수트','베이비 티','미니 백']},
  {id:'feminine',n:'페미닌',     en:'Feminine',    g:'원형', ph:'assets/look/feminine.jpg', img:14, st:'상시',          pk:'확산', by:'로맨틱 무드',
   ab:'곡선과 부드러운 소재를 앞세우는 원형으로, 시즌마다 실루엣과 소재만 바뀌며 꾸준히 다시 나타납니다.',
   ab2:'코르셋 라인과 새틴 소재, 플로럴 패턴이 핵심이며 버건디처럼 짙은 컬러가 로맨틱한 무드를 완성합니다.',
   kw:['코르셋','새틴','플로럴','버건디']}
];
export const INF_NAMES=['@seoul.layer','@quiet_wardrobe','@rok.archive','@fitcheck.kr','@daily.core',
                 '@wovenmood','@studio.plain','@thread.note'];
export const ITEM_BRANDS=['NIKE','MUSINSA STANDARD','ETCE','POLO','ADIDAS','LEMAIRE','ANDERSSON BELL','AMOMENTO'];

/* ── Hot Trend Top 10 ───────────────────────────────── */
var hotI=0, hotOpen=false;
function hotStep(){
  const roll=$('#hotRoll'); if(!roll)return;
  const t=HOT[hotI%HOT.length];
  const el=document.createElement('i');
  el.innerHTML='<b>'+String((hotI%HOT.length)+1).padStart(2,'0')+'</b>'+t[0]+
    '<em>'+(t[1]>0?'▲':'▼')+Math.abs(t[1])+'%</em>';
  roll.innerHTML=''; roll.appendChild(el);
  if(HAS_A)aAnimate(el,{opacity:[0,1],translateY:['110%','0%'],duration:620,
    ease:aSpring({stiffness:88,damping:16})});
  hotI++;
}
/* 실제 내용 높이를 재서 스프링으로 연다. max-height 로 여닫으면
   내용보다 큰 값까지 이징이 흘러 끝이 뚝 끊긴 것처럼 보인다. */
function hotToggle(){
  const box=$('#hot'), list=$('#hotList'); if(!box||!list)return;
  hotOpen=!hotOpen;
  box.classList.toggle('open',hotOpen);
  const rows=$$('#hotList button');
  if(!HAS_A){ list.style.height=hotOpen?'auto':'0';
    rows.forEach(r=>r.style.opacity=hotOpen?1:0); return }
  if(hotOpen)list.style.height='auto';
  const full=hotOpen?list.scrollHeight:0;
  list.style.height=(hotOpen?0:list.getBoundingClientRect().height)+'px';
  aAnimate(list,{height:full+'px',duration:hotOpen?820:520,
    ease:hotOpen?aSpring({stiffness:96,damping:18,mass:.9}):'in(2)',
    onComplete:()=>{ if(hotOpen)list.style.height='auto' }});
  aAnimate(rows,{opacity:hotOpen?[0,1]:[1,0],translateX:hotOpen?[-10,0]:[0,-6],
    duration:hotOpen?520:280,delay:aStagger(hotOpen?34:12,{from:'last'}),ease:'out(3)'});
}
export function hotBuild(){
  const list=$('#hotList'); if(!list)return;
  list.innerHTML=HOT.map((t,i)=>
    '<button data-style="'+t[2]+'"><span class="n">'+String(i+1).padStart(2,'0')+'</span>'+
    '<span class="k">'+t[0]+'</span><span class="ph">STYLE</span>'+
    '<span class="d '+(t[1]>0?'up':'dn')+'">'+(t[1]>0?'▲':'▼')+Math.abs(t[1])+'%</span></button>').join('');
  hotStep();
  setInterval(()=>{ if(!hotOpen)hotStep() },2400);
  $('#hotBar').addEventListener('click',hotToggle);
}

/* ── 챗바 안에서 굴러가는 예시 질문 ─────────────────────
   탭을 다녀와도 멈추지 않도록 스스로 다음 회차를 예약한다. */
var qI=0, qBooked=false, qSpin=0;
function qStep(){
  const line=$('#qline'), spark=$('.ghostQ .spark');
  if(!line)return;
  const SET=SM_ON?SM_QUESTIONS:M_QUESTIONS;
  const q=SET[qI%SET.length]; qI++;
  const paint=()=>{ line.innerHTML='<i>“<b>'+q[0]+'</b>&nbsp;'+q[1]+'”</i>' };
  if(!HAS_A){ paint(); return }
  const first=!line.firstElementChild;
  const t=aTimeline();
  /* 이전 문구가 나가고 새 문구가 들어오는 구간 위에
     별의 반 바퀴가 같은 길이로 겹친다. 한 타임라인이라 박자가 어긋나지 않는다. */
  if(first)paint();
  else t.add(line,{opacity:[1,0],translateY:[0,-9],duration:280,ease:'in(2)',onComplete:paint},0);
  const inAt=first?0:280;
  t.add(line,{opacity:[0,1],translateY:[9,0],duration:560,
      ease:aSpring({stiffness:94,damping:16})},inAt)
   .add(spark,{rotate:[qSpin,qSpin+180],scale:[.86,1.16],opacity:[.55,1],
      duration:inAt+430,ease:'inOut(3)'},0)
   .add(spark,{scale:[1.16,1],opacity:[1,.7],duration:410,ease:'out(2)'},inAt+430);
  qSpin+=180;
}
function qTick(){
  try{
    const inp=$('#mInput');
    if(inp&&!inp.value&&!$('#v-home').classList.contains('asking'))qStep();
  }catch(e){}
  setTimeout(qTick,3000);
}
export function qRoll(){ if(qBooked)return; qBooked=true; qStep(); setTimeout(qTick,3000) }

/* ── 대화 ───────────────────────────────────────────────
   답을 따로 마련한 섹션이 아니라 대화 안에서 카드로 돌려준다. */
export const SAY={
  rise :'이번 주는 <b>발레코어</b>가 가장 크게 올랐습니다. 다만 정점 직전 구간이라 신규 발주는 권하지 않습니다.',
  gorp :'<b>고프코어</b>는 2023년 3분기에 정점을 지났습니다. 로고 중심 아이템이 먼저 빠졌고, 테크 셸만 남아 있습니다.',
  ballet:'<b>발레코어</b>는 아직 유효합니다. 다만 튤·레그워머는 빠지고 리본과 새틴만 남는 형태로 좁혀지는 중입니다.',
  plat :'같은 주에도 <b>무신사</b>는 워크 자켓, <b>29CM</b>는 미니멀 셋업이 앞섭니다. 이 온도차가 기회 구간입니다.',
  body :'저장하신 어깨 라인과 기장을 기준으로 보면 <b>숄더 발마칸</b>이 가장 잘 맞습니다. 오버핏 트렌치는 피하세요.'
};
const SAY_STYLE={rise:'ballet',gorp:'gorp',ballet:'ballet',plat:'street',body:'classic'};
export function ansCardHTML(key){
  const a=M_ANSWERS[key]||M_ANSWERS.rise;
  return '<div class="ansCard">'+
    '<div class="ansBar"><u></u><u></u><u></u><span>'+a.url+'</span></div>'+
    '<div class="ansBody">'+
      '<div><div class="ansH"><h3>'+a.title+'</h3><em>통합 · 8/7–8/13</em></div><div class="rank">'+
      a.rank.map((r,i)=>'<div class="row"><span class="n">'+String(i+1).padStart(2,'0')+'</span>'+
        '<span class="k">'+r[0]+'<small>'+r[1]+'</small></span>'+
        '<span class="d '+(r[3]?'up':'dn')+'">'+(r[2]>0?'▲ ':'▼ ')+Math.abs(r[2])+'%</span></div>').join('')+
      '</div></div>'+
      '<div><div class="ansH"><h3>플랫폼 언급량</h3><em>최근 30일</em></div><div class="bars">'+
      M_PLATFORMS.map(pl=>'<div class="b"><span>'+pl[0]+'</span><u><i data-w="'+pl[1]+'"></i></u>'+
        '<em>'+pl[1]+'</em></div>').join('')+
      '</div></div>'+
    '</div></div>';
}
function ask(text,key){
  const th=$('#thread'), home=$('#v-home'); if(!th)return;
  home.classList.add('asking');
  document.body.classList.add('asking');
  const me=document.createElement('div');
  me.className='msg me'; me.innerHTML='<div class="bub">'+text+'</div>';
  th.appendChild(me);
  const ai=document.createElement('div');
  ai.className='msg ai';
  ai.innerHTML='<div class="who"><i>✧</i>'+(SM_ON?'FEEDiT 살!말?':'FEEDiT')+'</div>'+
    '<div class="say">'+(SM_SAY[key]||SAY[key]||SAY.rise)+'</div>'+ansCardHTML(key)+
    '<div class="act"><button class="pill ghost" data-style="'+(SAY_STYLE[key]||'ballet')+'">'+
    'Style 탭에서 자세히 <i>→</i></button>'+
    '<button class="pill ghost" data-v="trend">지표로 보기 <i>→</i></button></div>';
  th.appendChild(ai);
  const fills=$$('i[data-w]',ai);
  if(HAS_A){
    aAnimate([me,ai],{opacity:[0,1],translateY:[16,0],duration:760,
      delay:aStagger(140),ease:aSpring({stiffness:76,damping:16})});
    aAnimate($$('.rank .row',ai),{opacity:[0,1],translateY:[10,0],duration:560,
      delay:aStagger(42,{start:420}),ease:'out(3)'});
    aUtils.set(fills,{width:'0%'});
    aAnimate(fills,{width:el=>el.dataset.w+'%',duration:1100,delay:aStagger(80,{start:520}),
      ease:aSpring({stiffness:62,damping:16})});
  }else fills.forEach(f=>f.style.width=f.dataset.w+'%');
  setTimeout(()=>{ ai.scrollIntoView({behavior:'smooth',block:'center'}) },260);
  const inp=$('#mInput'); if(inp){ inp.value=''; $('#ghostQ').classList.remove('hide') }
}
export function newChat(){
  $('#thread').innerHTML='';
  $('#v-home').classList.remove('asking');
  document.body.classList.remove('asking');
  scrollTo(0,0);
  const inp=$('#mInput'); if(inp){ inp.value=''; $('#ghostQ').classList.remove('hide') }
}
/* ══════════════════════════════════════════════════════
   살!말? 챗봇 모드
   ------------------------------------------------------
   구조는 그대로 두고 지면만 뒤집는다. 같은 챗바, 다른 모델.
   전환은 버튼에서 시작해 화면 전체로 번지고, 그 뒤 챗바 테두리를
   빛이 한 바퀴 돌며 "모드가 바뀌었다"를 마무리한다.
   ══════════════════════════════════════════════════════ */
export var SM_ON=false, smBusy=false, smSwT=0;

/* 이 모드만의 문구 — 트렌드를 묻는 말이 아니라 결정을 묻는 말 */
const SM_STATEMENT=[['살까 말까,'],['혼자 ','고민','하지 마세요.']];
/* 이 모드는 사람에게 묻는 게 아니라, 지표로 점수를 매겨 판단을 내려 준다 */
const SM_LEAD='온도 · 가격 · 수명주기를 계산해 사도 되는지 답합니다.';
const SM_QUESTIONS=[
  ['이 코트','지금 사도 될까?'],['발레 플랫','품절 전에 사야 하나?'],
  ['스투시 후디','정가 주고 살 값어치 있어?'],['카고 팬츠','내년에도 입을까?'],
  ['이 가격','기다리면 더 내려가?']
];
const SM_CHIPS=[['이거 사도 될까?','smBuy'],['지금이 최저가야?','smPrice'],
                ['내년에도 입어?','smLife'],['비슷한 거 더 싼 거','smAlt'],
                ['다들 뭐라고 해?','smVote']];
/* 살!말? 전용 응답 — 판단을 대신 내려주는 어조 */
export const SM_SAY={
  smBuy :'지금 <b>사도 됩니다</b>. 취향이 겹치는 사람 <b>1,284명</b> 중 <b>73%</b>가 "산다"에 투표했고, 수명주기도 확산 구간입니다.',
  smPrice:'아직 <b>최저가가 아닙니다</b>. 할인율이 오르기 시작한 지 9일째라 2~3주 더 내려갈 여지가 있습니다.',
  smLife:'<b>내년에도 입습니다</b>. 정점까지 18주 남았고, 정점 이후에도 잔존이 9주로 긴 편입니다.',
  smAlt :'같은 실루엣에 <b>38% 저렴한</b> 대안이 3개 있습니다. 소재만 새틴에서 저지로 바뀝니다.',
  smVote:'투표는 <b>살다 73% · 말다 27%</b>입니다. "말다"를 고른 쪽은 대부분 <b>가격</b>을 이유로 들었습니다.'
};

/* ── 챗바가 제자리에서 모드를 갈아입는다 ──
   화면을 덮는 레이어 없이, 바 자체가 한 번 눌렸다 펴지며
   테두리를 빛이 한 바퀴 돈다. 색은 CSS 전이가 같은 박자로 따라온다. */
function smBarBeat(){
  const bar=$('#v-home .chatbar'); if(!bar||!HAS_A)return;
  aAnimate(bar,{keyframes:[
      {scaleX:1.012,scaleY:.92,duration:190,ease:'out(2)'},
      {scaleX:1,scaleY:1,duration:720,ease:aSpring({stiffness:110,damping:13})}]});
}
/* 히어로 두 칸이 아주 살짝 내려앉았다 올라온다 — 방의 공기가 바뀐 느낌 */
function smRoomBeat(){
  if(!HAS_A)return;
  const cols=[$('#v-home .heroL'),$('#v-home .heroR')].filter(Boolean);
  if(!cols.length)return;
  aAnimate(cols,{keyframes:[
      {translateY:5,duration:210,ease:'out(2)'},
      {translateY:0,duration:760,ease:aSpring({stiffness:88,damping:15})}],
    delay:aStagger(70)});
}

/* ── 좌측 선언문 교체 — 단어 단위로 빠져나가고 들어온다 ── */
function smStatement(on){
  const st=$('#mState'); if(!st)return;
  const lines=on?SM_STATEMENT:[['스크롤 속 패션을,'],['하나의 ','트렌드','로.']];
  const paint=()=>{
    /* 살!말? 모드에선 색이 뒤집힌다 — 문장이 코랄, 강조어('고민')가 잉크 */
    st.classList.toggle('inv',!!on);
    st.innerHTML=lines.map(parts=>'<span class="ln">'+parts.map((t,i)=>
      (parts.length===3&&i===1)?'<em class="ul">'+t+'</em>':t).join('')+'</span>').join('');
    /* 홈의 단어 리빌이 쓰는 .wd 구조를 그대로 다시 만든다 */
    $$('#mState .ln').forEach(ln=>{
      const kids=[...ln.childNodes]; ln.innerHTML='';
      kids.forEach(node=>{
        if(node.nodeType===3){
          node.textContent.split(/(\s+)/).forEach(tk=>{
            if(!tk)return;
            if(/^\s+$/.test(tk)){ ln.appendChild(document.createTextNode(' ')); return }
            const s=document.createElement('span'); s.className='wd'; s.textContent=tk; ln.appendChild(s);
          });
        }else{ const s=document.createElement('span'); s.className='wd'; s.appendChild(node); ln.appendChild(s) }
      });
    });
    const wds=$$('#mState .wd');
    if(HAS_A&&wds.length){
      aUtils.set(wds,{opacity:0,translateY:'62%',rotate:2.2});
      aAnimate(wds,{opacity:[0,1],translateY:['62%','0%'],rotate:[2.2,0],
        duration:900,delay:aStagger(46),ease:aSpring({stiffness:74,damping:16})});
    }
  };
  const old=$$('#mState .wd');
  const p=$('.heroL p');
  if(p){
    const swapP=()=>{ p.innerHTML=on?SM_LEAD
      :'매거진보다 빠르고, 피드보다 선명하게.' };
    if(HAS_A)aAnimate(p,{opacity:[1,0],translateY:[0,-8],duration:260,ease:'in(2)',
      onComplete:()=>{ swapP(); aAnimate(p,{opacity:[0,1],translateY:[8,0],duration:620,delay:180,ease:'out(3)'}) }});
    else swapP();
  }
  if(HAS_A&&old.length){
    aAnimate(old,{opacity:[1,0],translateY:[0,'-58%'],rotate:[0,-2],
      duration:380,delay:aStagger(28),ease:'in(2)',
      onComplete:(a)=>{ if(a&&a.completed!==false){} }});
    setTimeout(paint,380+old.length*28);
  }else paint();
}

/* ── 예시 질문 · 칩 교체 ── */
function smChips(on){
  const ch=$('#mChips'); if(!ch)return;
  const list=on?SM_CHIPS:M_CHIPS;
  const build=()=>{
    ch.innerHTML=list.map((c,i)=>
      '<button class="chip'+(i?'':' on')+'" data-ans="'+c[1]+'">'+c[0]+'</button>').join('');
    if(HAS_A)aAnimate($$('#mChips .chip'),{opacity:[0,1],translateY:[10,0],scale:[.94,1],
      duration:560,delay:aStagger(48),ease:aSpring({stiffness:96,damping:15})});
  };
  const cur=$$('#mChips .chip');
  if(HAS_A&&cur.length){
    aAnimate(cur,{opacity:[1,0],translateY:[0,-10],scale:[1,.94],
      duration:280,delay:aStagger(34),ease:'in(2)'});
    setTimeout(build,280+cur.length*34);
  }else build();
}

/* ── 모드 전환 본체 ── */
export function smSwitch(on,ev){
  if(smBusy||on===SM_ON)return; smBusy=true;
  const btn=$('#smToggle'), home=$('#v-home');
  /* 눌린 자리에서 링 하나가 먼저 튀고, 버튼이 제자리에서 한 바퀴 휘리릭 돈다 */
  if(btn&&HAS_A){
    const r=document.createElement('span'); r.className='rip'; btn.appendChild(r);
    aAnimate(r,{scale:[1,26],opacity:[.9,0],duration:760,ease:'out(3)',
      onComplete:()=>r.remove()});
    aAnimate(btn,{
      rotateY:[0,360],
      scale:[{to:.93,duration:130,ease:'out(2)'},
             {to:1,duration:690,ease:aSpring({stiffness:150,damping:11})}],
      duration:820,ease:'out(3)'
    });
  }
  const b=btn?btn.getBoundingClientRect():{left:innerWidth/2,top:innerHeight/2,width:0,height:0};
  const cx=b.left+b.width/2, cy=b.top+b.height/2;

  const commit=()=>{
    SM_ON=on;
    home.classList.toggle('smMode',on);
    document.body.classList.toggle('smOn',on);
    if(btn){
      btn.setAttribute('aria-pressed',String(on));
      const tx=btn.querySelector('.tx'), ic=btn.querySelector('.ic'), lb=btn.querySelector('.lbl');
      const swapLabel=()=>{ if(tx)tx.textContent=on?'일반 모드':'살!말?';
                            if(ic)ic.textContent=on?'←':'◑' };
      /* 버튼이 옆면을 보이는 구간(≈75~300ms)에 맞춰 문구를 숨겼다가 바꿔 단다.
         그래야 뒤집힌 글자가 보이지 않는다. */
      if(HAS_A&&lb){
        aAnimate(lb,{opacity:[1,0],duration:110,ease:'in(2)',
          onComplete:()=>{ swapLabel();
            aAnimate(lb,{opacity:[0,1],duration:380,delay:190,ease:'out(3)'}) }});
      }else swapLabel();
    }
    /* 챗바·버튼 테두리를 빛이 세 바퀴 돌며 감속해 상주 회전으로 이어진다.
       연속으로 눌렸을 때 클래스가 이미 붙어 있으면 애니메이션이 다시 시작되지 않아
       빛이 중간에 멈춰 보였다 — 한 번 떼고 리플로우를 강제해 처음부터 돌린다. */
    if(smSwT)clearTimeout(smSwT);
    home.classList.remove('smSweep','smOut');
    if(on){
      void home.offsetWidth;                 /* 리플로우 — 연타해도 스윕이 처음부터 돈다 */
      home.classList.add('smSweep');
      smSwT=setTimeout(()=>{ home.classList.remove('smSweep'); smSwT=0 },2520);
    }else{
      /* 돌던 빛을 그 자리에서 멈추지 않고, 계속 돌린 채로 잦아들게 한다 */
      home.classList.add('smOut');
      smSwT=setTimeout(()=>{ home.classList.remove('smOut'); smSwT=0 },900);
    }
    smStatement(on); smChips(on);
    /* 예시 질문 세트 교체 — 별이 한 박자 빠르게 돌며 넘어간다 */
    qI=0; qStep();
    const lbl=$('.hotTop .lbl');
    if(lbl)lbl.innerHTML=on?'<u>LIVE</u> 투표 TOP 10':'<u>HOT</u> TREND TOP 10';
    const inp=$('#mInput');
    if(inp)inp.placeholder='';
  };
  /* 가리는 것 없이 바로 바꾼다. 색은 CSS 전이가 0.62초에 걸쳐 따라온다. */
  commit(); smBarBeat(); smRoomBeat();
  setTimeout(()=>{smBusy=false},900);
}

export function sendChat(){
  const inp=$('#mInput'); const v=(inp&&inp.value.trim())||'';
  if(!v)return;
  openChatWith(v, cpKeyFor(v));
  if(inp){ inp.value=''; $('#ghostQ').classList.remove('hide') }
}
