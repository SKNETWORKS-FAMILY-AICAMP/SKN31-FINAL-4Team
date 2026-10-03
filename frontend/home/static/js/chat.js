import { $, $$, HAS_A, aAnimate, aSpring, aStagger, aTimeline, aUtils } from '../../../core/static/js/dom.js';
import { cpKeyFor, openChatWith } from './chat_popup.js';
import { MAX_IMAGES, imageFileToDataURL, bindImageDrop } from './chat_api.js';
import { savedAll, saveLiked } from '../../../account/static/js/account_api.js';

/* ============================================================
   메인 — 홈(챗봇) / 트렌드 분석 / 살!말? / Style / 요금제
   ============================================================ */
export const IMG=n=>'assets/hi/f'+String(n).padStart(2,'0')+'.jpg';

export const M_QUESTIONS=[
  ['트렌드 TOP 10','알려줘'],['발레코어','아직 유효해?'],['스웨이드','이번 겨울도 갈까?'],
  ['오늘 날씨에','뭐 입어야 해?'],['블록코어','다음은 뭐야?']
];
/* ★ 2026-09-19 — HOT TREND TOP 10 은 하드코딩 목록을 끊고 /api/trend?rank=hot 을 읽는다.
   [표시명, 변화율(%), 스타일 id(스타일 용어일 때만), 축 이름] — 상승 8 + 하락 2.
   못 불러오면 숫자를 지어내지 않고 '순위를 불러오지 못했습니다' 로 둔다. */
let HOT=[];
let HOT_STATE='loading';   /* loading | ok | empty | error */
/* 살!말? 모드에서는 같은 자리가 'LIVE 투표 TOP 10' 이 된다 — 진행 중 카드를 투표 수 순으로.
   [카드 제목, 살 비율(%), 투표 수, 카드 id] */
let HOT_VOTE=[];
let HOT_VOTE_STATE='loading';
const hotCur=()=>SM_ON?HOT_VOTE:HOT;
const hotCurState=()=>SM_ON?HOT_VOTE_STATE:HOT_STATE;
let HOT_META=null;         /* {as_of, rule, basis} */
const HOT_FACET={STYLE:'STYLE',ITEM:'ITEM',COLOR:'COLOR',MATERIAL:'MATERIAL',DETAIL:'DETAIL',TPO:'TPO',BRAND:'BRAND'};
const M_ANSWERS={
  rise:{ url:'feedit.ai / trend / 2026-08-W2', title:'이번 주 급상승 키워드',
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

/* ── 스타일(코어) 데이터 ─────────────────────────────── */
/* ══════════════════════════════════════════════════════════════
   스타일 12종 — 두 층으로 나눈다.
   코어(7) : 지금 이름이 붙어 도는 흐름. 생겨난 해와 진원지가 뚜렷하다.
   원형(5) : 코어들이 갈라져 나온 뿌리. 시작은 오래됐고 사라지지 않는다.
   g 는 그 층, pk 는 수명주기상 현재 위치.
   ══════════════════════════════════════════════════════════════ */
export const STYLES=[
  /* ── 코어 ───────────────────────────────────────────── */
  /* 2026-09-16 · 스타일 페이지 기준 10종으로 축소
     (고프코어 · 블록코어 · 바이크코어 · 놈코어 · 애슬레저 · 클래식 · 아메카지 · 그런지 · 페미닌 · 스트릿웨어).
     발레코어 · 긱시크 · 비즈니스코어 · Y2K는 뺐다. */
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
  {id:'norm',   n:'놈코어',      en:'Normcore',    g:'코어', ph:'assets/look/norm.jpg', img:23, st:'2013 · 뉴욕',   pk:'잔존', by:'K-HOLE 리포트',
   ab:'의도적으로 평범한 옷으로, 2013년 트렌드 예측 그룹 K-HOLE이 제안한 개념에서 출발했습니다.',
   ab2:'무지 티셔츠와 치노, 뉴발란스 운동화처럼 눈에 띄지 않는 기본 아이템으로 구성되며 절제된 색상 조합이 특징입니다.',
   kw:['무지 티','치노','뉴발란스','플리스 집업']},
  {id:'ath',    n:'애슬레저',    en:'Athleisure',  g:'코어', ph:'assets/look/ath.jpg', img:10, st:'2014 · LA',     pk:'재점화', by:'룰루레몬 · 요가 웨어',
   ab:'운동복을 운동 밖으로 끌어낸 코어로, 2014년 요가·필라테스 확산과 함께 자리를 잡았고 레깅스와 조거가 하의의 기본값이 됐습니다.',
   ab2:'레깅스와 조거 팬츠, 크롭 집업이 기본이며 러닝화로 마무리해 활동성과 편안함을 동시에 강조합니다.',
   kw:['레깅스','조거','크롭 집업','러닝화']},

  /* ── 원형 ───────────────────────────────────────────── */
  {id:'classic',n:'클래식',      en:'Classic',     g:'원형', ph:'assets/look/classic.jpg', img:24, st:'상시',          pk:'안정', by:'올드머니',
   ab:'유행을 타지 않는 형태와 소재로, 특정 유행에 기대지 않고 계절과 무관하게 꾸준한 수요를 유지합니다.',
   ab2:'트렌치코트와 캐시미어 니트, 스웨이드 소재, 옥스퍼드 슈즈처럼 고급스러운 소재감이 중심이 되는 조합입니다.',
   kw:['트렌치','캐시미어','스웨이드','옥스퍼드']},
  {id:'ameka',  n:'아메카지',    en:'Amekaji',     g:'원형', ph:'assets/look/ameka.jpg', img:13, st:'1980s · 일본',  pk:'확산', by:'아메리칸 카주얼',
   ab:'미국 워크웨어를 일본식으로 다시 짠 원형으로, 셀비지 데님과 워크 자켓이 축입니다.',
   ab2:'셀비지 데님과 워크 자켓, 치노 팬츠, 부츠로 구성되며 튼튼한 소재와 클래식한 워크웨어 디테일이 특징입니다.',
   kw:['셀비지 데님','워크 자켓','치노','부츠']},
  {id:'grunge', n:'그런지',      en:'Grunge',      g:'원형', ph:'assets/look/grunge.jpg', img:30, st:'1990s · 시애틀',pk:'재점화 대기', by:'시애틀 록 신',
   ab:'90년대 시애틀 록 신에서 나온 원형으로, 플란넬·워싱 데님·컴뱃 부츠가 축입니다.',
   ab2:'플란넬 셔츠와 워싱 데님, 컴뱃 부츠를 겹쳐 입는 레이어드 스타일링이 핵심이며 낡고 헤진 듯한 질감이 특유의 무드를 만듭니다.',
   kw:['플란넬','워싱 데님','컴뱃 부츠','레이어드']},
  {id:'feminine',n:'페미닌',     en:'Feminine',    g:'원형', ph:'assets/look/feminine.jpg', img:14, st:'상시',          pk:'확산', by:'로맨틱 무드',
   ab:'곡선과 부드러운 소재를 앞세우는 원형으로, 시즌마다 실루엣과 소재만 바뀌며 꾸준히 다시 나타납니다.',
   ab2:'코르셋 라인과 새틴 소재, 플로럴 패턴이 핵심이며 버건디처럼 짙은 컬러가 로맨틱한 무드를 완성합니다.',
   kw:['코르셋','새틴','플로럴','버건디']},
  {id:'street', n:'스트릿웨어',  en:'Streetwear',  g:'원형', ph:'assets/look/street.jpg', img:16, st:'1990s · 도쿄 · 뉴욕', pk:'재상승', by:'스투시 · 슈프림',
   ab:'스케이트와 힙합에서 출발해 하이패션과 섞인 원형으로, 로고 티셔츠와 배기 실루엣에서 시작해 지금의 형태로 넓어졌습니다.',
   ab2:'카고 팬츠와 오버핏 상의, 스케이트 슈즈, 비니로 구성되며 헐렁한 실루엣과 편안한 무드가 핵심입니다.',
   kw:['카고','오버핏','스케이트 슈즈','비니']}
];
export const INF_NAMES=['@seoul.layer','@quiet_wardrobe','@rok.archive','@fitcheck.kr','@daily.core',
                 '@wovenmood','@studio.plain','@thread.note'];
export const ITEM_BRANDS=['NIKE','MUSINSA STANDARD','ETCE','POLO','ADIDAS','LEMAIRE','ANDERSSON BELL','AMOMENTO'];

/* ── 아이템 카드 — '스타일' 상세의 '이 스타일의 아이템'과 마이페이지 '오늘의 추천'
   두 곳에서 그대로 재사용하는 공용 컴포넌트. match 를 넘긴 경우(마이페이지 추천)에만
   왼쪽 위에 매칭률 뱃지가 붙고, 하단은 브랜드 · 상품명 · 가격이 항상 세로로 쌓인다. */
export const LIKED = new Map();      /* 찜 저장소 — id → 카드 데이터. 마이페이지 '찜'이 여기서 나온다 */
const ITEM_REGISTRY = new Map();     /* 하트를 누를 때 어떤 카드였는지 되찾기 위한 등록부 */
const cardEsc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
}[c]));
const cardImage=v=>/^(https?:\/\/|\/|assets\/)/i.test(String(v||''))?String(v):'';
const cardLink=v=>/^https?:\/\//i.test(String(v||''))?String(v):'';
/* ★ 2026-09-19 — 찜의 원본은 서버(/api/auth/saved?view=all)다.
   localStorage 는 화면을 빨리 그리기 위한 사본이고, 누구의 사본인지(owner)를 같이 적는다.
   · 로그인하면 likedSync(uid) 가 서버 목록으로 갈아 끼운다.
   · 예전 형식(owner 없는 배열)은 서버 도입 전 이 브라우저에 쌓인 찜이다 —
     처음 로그인한 계정으로 한 번만 옮긴다(likedSync). 다른 계정의 사본은 옮기지 않는다.
   · 로그아웃하면 비운다(likedClear) — 다음 사람이 앞 사람의 찜을 보지 않게. */
const LIKED_KEY='feedit.liked.v1';
let LIKED_OWNER=null;     /* 사본의 주인 (app_user id). null 이면 예전 형식 */
let LIKED_LEGACY=false;   /* 예전 형식에서 읽었나 — 서버로 한 번 옮길 대상 */
function likedSave(){
  try{ localStorage.setItem(LIKED_KEY, JSON.stringify({v:2, owner:LIKED_OWNER, entries:[...LIKED.entries()]})); }
  catch(e){ /* 저장소를 못 쓰는 환경(시크릿 창 등)은 이번 세션 메모리로만 유지한다 */ }
}
function likedLoad(){
  try{
    const raw=JSON.parse(localStorage.getItem(LIKED_KEY)||'null');
    const arr=Array.isArray(raw)?raw:(raw&&Array.isArray(raw.entries)?raw.entries:null);
    if(!arr) return false;
    LIKED_LEGACY=Array.isArray(raw);
    LIKED_OWNER=Array.isArray(raw)?null:(raw.owner??null);
    arr.forEach(e=>{ if(Array.isArray(e)&&e[0]&&e[1]) LIKED.set(e[0], e[1]); });
    return true;
  }catch(e){ return false; }
}
function savedToCard(it){
  const st=STYLES.find(s=>s.n===it.style);
  const price=Number.isFinite(it.sale_price)?it.sale_price:(Number.isFinite(it.list_price)?it.list_price:null);
  return { img:it.image||'', br:it.brand||'', nm:it.name||'', pr:price!=null?price.toLocaleString('ko-KR')+'원':'',
           style:st?st.id:'', styleName:it.style||'', cat:it.category||'', price, listPrice:it.list_price??null,
           url:it.url||'', likedAt:Date.parse(it.liked_at)||Date.now(),
           same:Number.isFinite(it.same_count)?it.same_count:null };
}
/* 로그인한 사용자의 찜을 서버에서 받아 LIKED 를 갈아 끼운다. 실패하면 사본을 그대로 둔다. */
export async function likedSync(uid){
  let data;
  try{ data=await savedAll(); }catch(e){ return false; }
  const server=new Map((data.items||[]).map(it=>[it.item_id, savedToCard(it)]));
  /* 예전 형식 사본은 이 브라우저에서 처음 로그인한 계정으로 한 번만 옮긴다 */
  if(LIKED_LEGACY||(LIKED_OWNER==null&&LIKED.size)){
    const local=[...LIKED.entries()].filter(([id])=>!server.has(id));
    await Promise.all(local.map(([id,d])=>saveLiked({itemId:id,liked:true,name:d.nm||'',brand:d.br||'',style:d.styleName||''})));
    local.forEach(([id,d])=>server.set(id,{...d,same:null}));
  }
  LIKED.clear(); server.forEach((v,k)=>LIKED.set(k,v));
  LIKED_OWNER=uid??null; LIKED_LEGACY=false; likedSave();
  document.dispatchEvent(new CustomEvent('feedit:liked-sync'));
  return true;
}
export function likedClear(){
  LIKED.clear(); LIKED_OWNER=null; LIKED_LEGACY=false; likedSave();
  document.dispatchEvent(new CustomEvent('feedit:liked-sync'));
}
likedLoad();
export function toggleLike(id){
  if(LIKED.has(id)){ LIKED.delete(id); likedSave(); return false; }
  const d = ITEM_REGISTRY.get(id); if(!d) return false;
  LIKED.set(id, { ...d, likedAt: Date.now() });   /* 찜한 시각 — 'n일 전 찜' 계산에 쓴다 */
  likedSave();
  return true;
}
export function itemCard(o){
  if(o.id) ITEM_REGISTRY.set(o.id, { img: o.img, br: o.br, nm: o.nm, pr: o.pr, tag: o.tag, style: o.style, url: o.url,
    /* 찜한 키워드 화면용 부가 정보 — 실데이터 상품 카드에서만 채워진다 */
    styleName: o.styleName, cat: o.cat, price: o.price, listPrice: o.listPrice });
  const liked = !!(o.id && LIKED.has(o.id));
  const img=cardImage(o.img), url=cardLink(o.url);
  return '<div class="itemCard"' + (o.style ? ' data-style="' + cardEsc(o.style) + '"' : '') +
    /* 스타일 상세의 카테고리 필터가 읽는 값 (2026-09-23) */
    (o.catKey ? ' data-cat-key="' + cardEsc(o.catKey) + '"' : '') +
    (url ? ' data-product-url="' + cardEsc(url) + '" role="link" tabindex="0"' : '') + '>' +
    '<div class="itemFig">' +
      /* ★ 쇼핑몰 CDN 일부(무신사 등)는 Referer 가 붙으면 핫링크를 막아 사진이 깨진다 —
         referrerpolicy 로 주소를 떼고 부르고, 그래도 실패하면 '이미지 없음' 판으로 바꾼다. */
      (img?'<img src="'+cardEsc(img)+'" alt="'+cardEsc(o.nm||'')+'" loading="lazy" '+
        'referrerpolicy="no-referrer" '+
        'onerror="this.onerror=null;this.insertAdjacentHTML(\'afterend\',\'&lt;div class=&quot;itemNoImage&quot;&gt;이미지 없음&lt;/div&gt;\');this.remove()">'
        :'<div class="itemNoImage">이미지 없음</div>') +
      (o.tag ? '<span class="matchTag">' + cardEsc(o.tag) + '</span>' : '') +
      (o.pick ? '<span class="pickTag">FEEDiT Pick!</span>' : '') +
      (o.id ? '<button type="button" class="likeBtn' + (liked ? ' on' : '') + '" data-like-id="' + cardEsc(o.id) + '" aria-label="찜하기">' +
        '<svg viewBox="0 0 24 24"><path d="M12 21s-7.6-4.6-10.3-9.1C.2 9 1 5.5 4 4.1c2.4-1.1 5-.2 6.5 1.8L12 8l1.5-2.1c1.5-2 4.1-2.9 6.5-1.8 3 1.4 3.8 4.9 2.3 7.8C19.6 16.4 12 21 12 21z"/></svg></button>' : '') +
    '</div>' +
    '<div class="itemBody"><div class="br">' + cardEsc(o.br) + '</div>' +
      '<div class="nm">' + cardEsc(o.nm) + '</div>' +
      '<div class="pr">' + cardEsc(o.pr) + '</div></div></div>';
}

/* ── Hot Trend Top 10 ───────────────────────────────── */
var hotI=0, hotOpen=false;
function hotStep(){
  const roll=$('#hotRoll'); if(!roll)return;
  const L=hotCur();
  if(!L.length){
    roll.innerHTML='<i>'+(hotCurState()==='loading'?'순위를 불러오는 중…'
      :hotCurState()==='empty'?(SM_ON?'진행 중인 투표가 없습니다':'순위를 낼 지표가 없습니다')
      :'순위를 불러오지 못했습니다')+'</i>';
    return;
  }
  if(SM_ON){
    const t=L[hotI%L.length];
    const el=document.createElement('i');
    el.innerHTML='<b>'+String((hotI%L.length)+1).padStart(2,'0')+'</b>'+cardEsc(t[0])+'<em>살 '+t[1]+'%</em>';
    roll.innerHTML=''; roll.appendChild(el);
    if(HAS_A)aAnimate(el,{opacity:[0,1],translateY:['110%','0%'],duration:620,
      ease:aSpring({stiffness:88,damping:16})});
    hotI++;
    return;
  }
  const t=HOT[hotI%HOT.length];
  const el=document.createElement('i');
  /* ★ 펼친 목록(.d.up)과 같은 규칙 — 상승은 코랄, 하락은 회색 */
  el.innerHTML='<b>'+String((hotI%HOT.length)+1).padStart(2,'0')+'</b>'+t[0]+
    '<em class="'+(t[1]>0?'up':'dn')+'">'+(t[1]>0?'▲':'▼')+Math.abs(t[1])+'%</em>';
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
function hotPaint(){
  const list=$('#hotList'); if(!list)return;
  if(SM_ON){
    list.innerHTML=HOT_VOTE.length
      ? HOT_VOTE.map((t,i)=>
          '<button data-v="salmal" data-sm="popular"><span class="n">'+String(i+1).padStart(2,'0')+'</span>'+
          '<span class="k">'+cardEsc(t[0])+'</span>'+
          '<span class="d '+(t[1]>=50?'up':'dn')+'">살 '+t[1]+'% · '+t[2]+'표</span></button>').join('')+
        '<div class="hotNote">진행 중인 투표 · 참여 많은 순</div>'
      : '<div class="hotNote">'+(HOT_VOTE_STATE==='loading'?'투표 순위를 불러오는 중입니다.'
          :HOT_VOTE_STATE==='empty'?'진행 중인 투표가 없습니다.':'지금은 투표 순위를 불러오지 못했습니다.')+'</div>';
    return;
  }
  if(!HOT.length){
    list.innerHTML='<div class="hotNote">'+(HOT_STATE==='loading'?'순위를 불러오는 중입니다.'
      :'지금은 순위를 불러오지 못했습니다. 잠시 뒤 다시 확인해 주세요.')+'</div>';
    return;
  }
  list.innerHTML=HOT.map((t,i)=>
    '<button '+(t[2]?'data-style="'+cardEsc(t[2])+'"':'data-hot-q="'+cardEsc(t[0])+'"')+'>'+
    '<span class="n">'+String(i+1).padStart(2,'0')+'</span>'+
    '<span class="k">'+cardEsc(t[0])+'</span><span class="ph">'+cardEsc(HOT_FACET[t[3]]||t[3]||'')+'</span>'+
    '<span class="d '+(t[1]>0?'up':'dn')+'">'+(t[1]>0?'▲':'▼')+Math.abs(t[1])+'%</span></button>').join('')+
    (HOT_META?'<div class="hotNote">'+cardEsc(HOT_META.as_of)+' 기준 · '+
      (HOT_META.basis&&HOT_META.basis.source==='ALL'?'전 플랫폼 합산':'YouTube 댓글')+
      ' · 최근 7일 평균 vs 28일 평균'+
      (HOT_META.basis&&HOT_META.basis.refresh==='daily'?' · 매일 갱신':'')+'</div>':'');
}
async function hotLoad(){
  try{
    const r=await fetch('/api/trend?rank=hot&limit=8',{headers:{Accept:'application/json'}});
    const j=await r.json();
    if(!r.ok||j.status!=='ok'){ HOT_STATE=j&&j.status==='empty'?'empty':'error'; return; }
    const d=j.data||{};
    const styleId=n=>(STYLES.find(s=>s.n===n)||{}).id||'';
    const pick=[...(d.rising||[]).slice(0,8),...(d.falling||[]).slice(0,2)];
    HOT=pick.map(x=>[x.term,x.change_pct,x.facet==='STYLE'?styleId(x.term):'',x.facet]);
    HOT_META={as_of:d.as_of,rule:d.rule,basis:d.basis};
    HOT_STATE=HOT.length?'ok':'empty';
  }catch(e){ HOT_STATE='error'; }
}
async function hotVoteLoad(){
  try{
    /* 투표 수는 그때그때 바뀐다 — 브라우저 캐시를 쓰지 않는다(살!말? 화면 vote_app 과 같다) */
    const r=await fetch('/api/salmal/cards?tab=popular',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
    const j=await r.json();
    if(!r.ok||j.status!=='ok'){ HOT_VOTE_STATE='error'; return; }
    const items=(j.data&&j.data.items)||[];
    HOT_VOTE=items.filter(c=>!c.closed&&(c.vote_summary||{}).total>0).slice(0,10)
      .map(c=>[c.title,c.vote_summary.buy_pct,c.vote_summary.total,c.id]);
    HOT_VOTE_STATE=HOT_VOTE.length?'ok':'empty';
  }catch(e){ HOT_VOTE_STATE='error'; }
}
/* ── 자동 갱신 (2026-10-01) ─────────────────────────────
   ★ 예전엔 페이지를 열 때 한 번만 읽었다. 투표 순위는 모드를 처음 켤 때 한 번 읽고 끝이었다.
   · 트렌드 TOP 10 — 지표가 하루 한 번(매일 새벽) 다시 계산된다. 30분마다 확인해서
     기준일이나 순위가 바뀌었을 때만 다시 그린다. 탭을 오래 열어 둬도 다음 날 순위로 바뀐다.
   · 투표 TOP 10 — 투표는 그때그때 바뀐다. 홈에서 살!말? 모드를 보는 동안 20초마다 읽고,
     내가 투표하면(feedit:vote) 바로 다시 읽는다.
   · 안 보이는 탭 · 다른 화면에서는 읽지 않는다. 돌아오면 그때 확인한다. */
const HOT_REFRESH_MS=30*60*1000;
const VOTE_REFRESH_MS=20*1000;
let hotLoadedAt=0, voteLoadedAt=0;
const hotOnHome=()=>!document.hidden&&(!document.body.dataset.view||document.body.dataset.view==='home');
const hotSig=()=>JSON.stringify([HOT,HOT_META&&HOT_META.as_of]);
const voteSig=()=>JSON.stringify(HOT_VOTE);
async function hotReload(){
  const before=hotSig();
  await hotLoad(); hotLoadedAt=Date.now();
  if(!SM_ON&&hotSig()!==before){ hotI=0; hotPaint(); hotStep(); }
}
async function hotVoteReload(){
  const before=voteSig();
  await hotVoteLoad(); voteLoadedAt=Date.now();
  if(SM_ON&&voteSig()!==before){ hotI=0; hotPaint(); hotStep(); }
}
function hotTick(){
  if(!hotOnHome())return;
  if(Date.now()-hotLoadedAt>=HOT_REFRESH_MS)hotReload();
  if(SM_ON&&Date.now()-voteLoadedAt>=VOTE_REFRESH_MS)hotVoteReload();
}
/* 모드가 바뀌면 같은 자리를 다시 그린다 (smSwitch 에서 부른다) */
export function hotRefresh(){
  hotI=0; hotPaint(); hotStep();
  /* 살!말? 모드로 들어올 때마다 다시 읽는다 — 예전엔 처음 한 번만 읽어 옛 순위가 남았다 */
  if(SM_ON)hotVoteReload();
}
export function hotBuild(){
  const list=$('#hotList'); if(!list)return;
  hotPaint(); hotStep();
  hotLoad().then(()=>{ hotLoadedAt=Date.now(); if(!SM_ON){ hotI=0; hotPaint(); hotStep(); } });
  setInterval(()=>{ if(!hotOpen)hotStep() },2400);
  setInterval(hotTick,VOTE_REFRESH_MS);
  document.addEventListener('visibilitychange',hotTick);
  document.addEventListener('feedit:vote',()=>{ voteLoadedAt=0; if(SM_ON)hotVoteReload(); });
  $('#hotBar').addEventListener('click',hotToggle);
  /* 스타일이 아닌 용어(아이템·소재·색 …)는 챗봇에 바로 물어본다 */
  list.addEventListener('click',e=>{
    const b=e.target.closest('[data-hot-q]'); if(!b)return;
    const q=b.dataset.hotQ+' 요즘 어때?';
    openChatWith(q, cpKeyFor(q), {forceNew:true});
  });
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
/* 스타일 페이지에 없는 스타일(발레코어)은 버튼을 달지 않는다 */
const SAY_STYLE={rise:'block',gorp:'gorp',ballet:'',plat:'street',body:'classic'};
export function ansCardHTML(key){
  const a=M_ANSWERS[key]||M_ANSWERS.rise;
  return '<div class="skillReport skillReport--legacy">'+
    '<div class="skillReportHead"><span>FEEDiT / LIVE REPORT</span><em>02 SIGNALS</em></div>'+
    '<div class="skillLegacyCanvas">'+
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
    '</div></div></div>';
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
    '<div class="act">'+(SAY_STYLE[key]?'<button class="pill ghost" data-style="'+SAY_STYLE[key]+'">'+
    'Style 탭에서 자세히 <i>→</i></button>':'')+
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
export const SM_QUESTIONS=[
  ['이 코트','지금 사도 될까?'],['발레 플랫','품절 전에 사야 하나?'],
  ['스투시 후디','정가 주고 살 값어치 있어?'],['카고 팬츠','내년에도 입을까?'],
  ['이 가격','기다리면 더 내려가?']
];
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

/* ── 모드 전환 본체 ──
   smBusy 는 **연출용 잠금**이다(스윕이 겹쳐 돌지 않게 0.9초). 사용자가 직접 누른
   전환까지 이 잠금에 막히면 "한 번 눌러선 안 바뀐다" 가 된다 — 팝업의 Tab·마크
   전환은 force=true 로 부른다. 잠금 해제도 finally 로 옮겼다: 아래 연출 중 하나가
   던지면 예전에는 smBusy 가 true 로 굳어 그 뒤 전환이 통째로 죽었다. (2026-09-13) */
export function smSwitch(on,ev,force){
  if(on===SM_ON)return;
  if(smBusy&&!force)return;
  smBusy=true;
  const btn=$('#smToggle'), home=$('#v-home');

  const commit=()=>{
    SM_ON=on;
    if(home)home.classList.toggle('smMode',on);
    document.body.classList.toggle('smOn',on);
    if(btn){
      /* 켜고 끄는 동작은 이 한 줄이 전부다 — 썸 슬라이드·트랙 색·문구 자리·
         문구 색까지 전부 [aria-pressed] 기준으로 CSS가 한다(chat.css).
         회전·링 같은 곁다리 모션은 두지 않는다(2026-09-10). */
      btn.setAttribute('aria-pressed',String(on));
      /* 문구는 상태 이름 그대로 — ON(주황)이면 살!말?, OFF(회색)면 일반 */
      const tx=btn.querySelector('.tx');
      if(tx)tx.textContent=on?'살!말?':'일반';
    }
    /* 챗바·버튼 테두리를 빛이 세 바퀴 돌며 감속해 상주 회전으로 이어진다.
       연속으로 눌렸을 때 클래스가 이미 붙어 있으면 애니메이션이 다시 시작되지 않아
       빛이 중간에 멈춰 보였다 — 한 번 떼고 리플로우를 강제해 처음부터 돌린다. */
    if(smSwT)clearTimeout(smSwT);
    if(home){
      home.classList.remove('smSweep','smOut');
      if(on){
        void home.offsetWidth;               /* 리플로우 — 연타해도 스윕이 처음부터 돈다 */
        home.classList.add('smSweep');
        smSwT=setTimeout(()=>{ home.classList.remove('smSweep'); smSwT=0 },2520);
      }else{
        /* 돌던 빛을 그 자리에서 멈추지 않고, 계속 돌린 채로 잦아들게 한다 */
        home.classList.add('smOut');
        smSwT=setTimeout(()=>{ home.classList.remove('smOut'); smSwT=0 },900);
      }
    }
    smStatement(on);
    /* 예시 질문 세트 교체 — 별이 한 박자 빠르게 돌며 넘어간다 */
    qI=0; qStep();
    const lbl=$('.hotTop .lbl');
    if(lbl)lbl.innerHTML=on?'<u>LIVE</u> 투표 TOP 10':'<u>HOT</u> TREND TOP 10';
    hotRefresh();
    const inp=$('#mInput');
    if(inp)inp.placeholder='';
  };
  /* 가리는 것 없이 바로 바꾼다. 색은 CSS 전이가 0.62초에 걸쳐 따라온다. */
  try{ commit(); smBarBeat(); smRoomBeat(); }
  finally{ setTimeout(()=>{smBusy=false},900); }
}

/* ── 홈 챗바 이미지 첨부 ──────────────────────────────
   + 버튼 → 숨긴 file input을 대신 눌러 준다. 고른 사진은 곧장 서버로
   가지 않고 여기서 들고 있다가, sendChat()이 질문과 함께 팝업으로 넘긴다. */
export let mImages=[];
function mImgPaint(){
  const box=$('#mImgAttach'); if(!box)return;
  box.hidden = mImages.length===0;
  box.innerHTML = mImages.map((im,i)=>
    '<span class="imgChip"><img src="'+im.url+'" alt=""><button type="button" data-rm="'+i+'" aria-label="사진 삭제">×</button></span>').join('');
}
export function mImgClear(){ mImages=[]; mImgPaint(); }
async function mImgPick(files){
  for(const f of files){
    if(mImages.length>=MAX_IMAGES)break;
    try{ const url=await imageFileToDataURL(f); mImages.push({url}); }catch(e){ /* 이미지가 아니면 조용히 건너뛴다 */ }
  }
  mImgPaint();
}
export function mImgInit(){
  const add=$('#mImgAdd'), input=$('#mImgFile'), box=$('#mImgAttach');
  if(add&&input){
    add.addEventListener('click', ()=>input.click());
    input.addEventListener('change', ()=>{
      if(input.files&&input.files.length)mImgPick([...input.files]);
      input.value='';
    });
  }
  if(box)box.addEventListener('click', e=>{
    const rm=e.target.closest('[data-rm]'); if(!rm)return;
    mImages.splice(+rm.dataset.rm,1); mImgPaint();
  });
  /* 챗바 위에 사진을 그대로 끌어다 놓아도 + 버튼과 같은 경로로 들어간다 */
  bindImageDrop($('.chatbar'), files=>mImgPick(files));
}

export function sendChat(){
  const inp=$('#mInput'); const v=(inp&&inp.value.trim())||'';
  if(!v && !mImages.length)return;
  const images=mImages.map(im=>im.url);
  /* 홈 챗바에서 치는 질문은 이전에 닫아 둔 세션과 이어지면 안 된다 — 매번 새 대화로 연다 */
  openChatWith(v, cpKeyFor(v), {forceNew:true, images});
  if(inp){ inp.value=''; $('#ghostQ').classList.remove('hide') }
  mImgClear();
}
