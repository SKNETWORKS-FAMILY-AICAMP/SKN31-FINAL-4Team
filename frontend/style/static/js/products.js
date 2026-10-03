export const ST_ITEM_PAGE_SIZE=24;   /* '더 보기' 한 번에 채우는 카드 수 */

/* 정렬 — 페이지를 나눠 받으므로 정렬은 반드시 서버(API)에서 한다.
   스타일 상세에 들어가면 기본은 FEEDiT 추천순(recommend). */
export const ST_SORTS=[
  ['recommend','FEEDiT 추천순'],['latest','최신순'],
  ['price_desc','가격 높은 순'],['price_asc','가격 낮은 순'],['discount','할인율 높은 순'],
  ['reviews','리뷰 많은 순'],['rating','평점 높은 순'],['likes','좋아요 많은 순'],['sales','판매량 많은 순']
];
/* 드롭다운의 ⓘ 버튼이 펼쳐 보여 주는 FEEDiT 추천순 기준 설명 — 세 줄로 줄여 둔다 */
export const ST_RECOMMEND_NOTE=[
  '리뷰·좋아요·판매량, 평점, 할인율, 상품 정보 충실도를',
  '합쳐 점수가 높은 순으로 보여 줍니다.',
  '쇼핑몰이 주지 않은 값은 0점으로 둡니다.'
];
export const ST_PICK_COUNT=6;   /* FEEDiT 추천순 최상단 몇 개에 'FEEDiT Pick!' 라벨을 붙일지 */

export function styleProductsURL(style,offset=0,limit=ST_ITEM_PAGE_SIZE,sort='latest',category='all'){
  const p=new URLSearchParams({style:String(style||''),offset:String(offset),limit:String(limit)});
  if(sort&&sort!=='latest'&&ST_SORTS.some(([k])=>k===sort))p.set('sort',sort);
  /* 카테고리는 이미 받은 한 페이지를 브라우저에서 잘라내는 조건이 아니다.
     서버가 먼저 거른 뒤 페이지를 나눠야, 아우터를 눌렀을 때 첫 24칸이
     아우터로 채워지고 다음 페이지를 누를 때도 같은 조건이 유지된다. */
  if(category&&category!=='all'&&ST_ITEM_CATS.some(([k])=>k===category)){
    p.set('category_group',category);
  }
  return '/api/products?'+p.toString();
}

function priceText(price){
  const value=price&&(price.sale!=null?price.sale:price.list);
  if(value==null)return '가격 정보 없음';
  const n=Number(value);
  return Number.isFinite(n)?n.toLocaleString('ko-KR')+'원':'가격 정보 없음';
}

const numOr=v=>{ const n=Number(v); return v!=null&&Number.isFinite(n)?n:null };

export function styleProductCard(item,styleName){
  return {
    id:'db-'+String(item.product_source_id||item.id||''),
    img:item.image||'',
    br:item.brand||item.source||'브랜드 정보 없음',
    nm:item.name||'상품명 없음',
    pr:priceText(item.price),
    url:item.url||'',
    /* 찜한 키워드 화면이 쓰는 값 — 어느 스타일에서 찜했는지, 숫자 가격, 카테고리 */
    styleName:styleName||'',
    cat:item.category||'',
    price:numOr(item.price&&(item.price.sale!=null?item.price.sale:item.price.list)),
    listPrice:numOr(item.price&&item.price.list)
  };
}

/* ══════════════════════════════════════════════════════
   아이템 카테고리 (2026-09-23)
   '이 스타일의 아이템' 아래에 두는 여섯 칸. 쇼핑몰이 준 카테고리 문자열은
   몰마다 제각각이라('아웃터', '자켓/코트', 'OUTER'…) 여기서 한 갈래로 묶는다.
   카테고리가 비어 있으면 상품명으로 한 번 더 본다 — 그래도 모르면 '전체' 에만 남는다.
   ══════════════════════════════════════════════════════ */
export const ST_ITEM_CATS=[
  ['all','전체'],['outer','아우터'],['top','상의'],
  ['bottom','하의'],['dress','원피스'],['shoes','신발']
];
const ST_CAT_RULES=[
  ['shoes', /신발|슈즈|스니커|운동화|부츠|로퍼|샌들|힐|플랫|슬리퍼|더비|첼시|shoes|sneaker|boots|loafer|sandal/i],
  ['dress', /원피스|드레스|점프수트|셋업|jumpsuit|dress|onepiece/i],
  ['outer', /아우터|아웃터|자켓|재킷|코트|점퍼|블루종|패딩|다운|플리스|무스탕|가디건|베스트|조끼|바람막이|파카|트렌치|블레이저|jacket|coat|outer|parka|blouson|fleece|vest|cardigan/i],
  ['bottom',/하의|바지|팬츠|슬랙스|데님|진|청바지|스커트|치마|반바지|쇼츠|조거|레깅스|pants|denim|jeans|skirt|shorts|slacks|jogger|legging/i],
  ['top',   /상의|티셔츠|티|반팔|긴팔|맨투맨|스웨트|후디|후드|셔츠|블라우스|니트|스웨터|폴로|탑|나시|피케|tee|t-shirt|shirt|blouse|knit|sweater|hood|sweat|polo|top/i]
];
/* 카드 하나가 속하는 카테고리 열쇠 — 못 가리면 '' (전체에서만 보인다) */
export function itemCatKey(card){
  const text=[card&&card.cat, card&&card.nm].filter(Boolean).join(' ');
  if(!text)return '';
  for(const [key,re] of ST_CAT_RULES){ if(re.test(text))return key }
  return '';
}
