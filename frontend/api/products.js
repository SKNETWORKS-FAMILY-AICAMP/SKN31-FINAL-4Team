/* GET /api/products?style=고프코어&gender=FEMALE&limit=16&offset=0
 *
 * 상품 목록 — 지금 RDS 에 **실제로 들어 있는** 데이터다.
 * 2026-09-02 실측으로 commerce.product 3,375건 · product_source 3,375건.
 * 지표(analysis.*)가 비어 있어도 이 화면은 실값으로 보여 줄 수 있다.
 *
 * 가격은 `snapshot.product_source_snapshot` 의 **가장 최근 한 줄**을 붙인다.
 * 스냅샷이 없는 상품은 가격 자리를 null 로 두고 이유를 함께 보낸다 —
 * 0원으로 채우면 화면이 "공짜"라고 말하게 된다.
 */

import { q, viaBackend } from './_lib/db.js';
import { absoluteImageUrl } from './_lib/image.js';
import { ok, empty, failed } from './_lib/reply.js';

export default async function handler(req, res) {
  // Django API 가 설정돼 있으면 그쪽이 먼저다 (RDS 를 열지 않아도 된다).
  const relayed = await viaBackend('/products' + (req.url.includes('?') ? '?' + req.url.split('?')[1] : ''));
  if (relayed) {
    res.statusCode = 200;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    /* ★ 2026-09-22 — 성공한 응답만 캐시한다.
       viaBackend 는 실패해도 {status:'error'} 를 돌려주는데 그것도 truthy 라,
       예전에는 백엔드가 잠깐 죽은 사이의 에러가 엣지에 박혔다. */
    res.setHeader('Cache-Control', relayed && relayed.status === 'ok'
      ? 's-maxage=300, stale-while-revalidate=600'
      : 'no-store');
    return res.end(JSON.stringify(relayed));
  }

  const url = new URL(req.url, 'http://x');
  const kw = (url.searchParams.get('q') || '').trim();
  const brand = (url.searchParams.get('brand') || '').trim();
  const style = (url.searchParams.get('style') || '').trim();
  const gender = (url.searchParams.get('gender') || '').trim().toUpperCase();
  if (gender && gender !== 'FEMALE' && gender !== 'MALE')
    return failed(res, '성별은 FEMALE 또는 MALE 중에서 선택해 주세요.');
  const categoryGroup = (url.searchParams.get('category_group') || '').trim().toLowerCase();
  const limit = Math.min(200, Math.max(1, Number(url.searchParams.get('limit') || 40)));
  const offset = Math.min(1000000, Math.max(0, Number(url.searchParams.get('offset') || 0)));
  // 정렬 — 값은 모두 최신 스냅샷 한 줄에서 온다. 값이 없는 상품은 어느 정렬이든 맨 뒤.
  //  recommend(FEEDiT 추천순, 기본): 리뷰·좋아요·판매량(로그) + 평점 + 할인율 + 이미지·가격 보유 가산점
  const DISC = `(CASE WHEN s.discount_rate <= 1 THEN s.discount_rate * 100 ELSE s.discount_rate END)`;
  const SCORE = `(COALESCE(LN(1 + s.review_count), 0) * 1.0
     + COALESCE(LN(1 + s.like_count), 0) * 0.8
     + COALESCE(LN(1 + s.sales_count), 0) * 0.8
     + COALESCE(s.rating, 0) * 0.6
     + COALESCE(${DISC}, 0) * 0.03
     + CASE WHEN ps.thumbnail_url IS NOT NULL THEN 0.5 ELSE 0 END
     + CASE WHEN s.observed_at IS NOT NULL THEN 0.5 ELSE 0 END)`;
  const TAIL = 'ps.last_seen_at DESC NULLS LAST, ps.id DESC';
  const ORDER = {
    recommend: `${SCORE} DESC, ${TAIL}`,
    latest: TAIL,
    price_desc: `COALESCE(s.sale_price, s.list_price) DESC NULLS LAST, ps.id DESC`,
    price_asc: `COALESCE(s.sale_price, s.list_price) ASC NULLS LAST, ps.id DESC`,
    discount: `${DISC} DESC NULLS LAST, ${TAIL}`,
    reviews: `s.review_count DESC NULLS LAST, ${TAIL}`,
    rating: `s.rating DESC NULLS LAST, s.review_count DESC NULLS LAST, ${TAIL}`,
    likes: `s.like_count DESC NULLS LAST, ${TAIL}`,
    sales: `s.sales_count DESC NULLS LAST, ${TAIL}`,
  };
  const orderBy = ORDER[url.searchParams.get('sort')] || ORDER.latest;

  const where = ["ps.status = 'ACTIVE'"];
  const args = [];
  if (gender) {
    /* 수집 원본의 명시적 성별과 공용 상품만. 숫자 코드와 빈 값은 추측하지 않는다. */
    const own = gender === 'FEMALE' ? 'W|F|WOMEN|FEMALE' : 'M|MEN|MALE';
    args.push(`(^|[,:[:space:]])(${own}|U|UNISEX)([,:[:space:]]|$)`);
    where.push(`COALESCE(NULLIF(ps.gender_scope, ''), p.gender_scope, '') ~* $${args.length}`);
  }
  if (kw) {
    args.push(`%${kw}%`);
    where.push(`(p.canonical_name ILIKE $${args.length} OR ps.source_name ILIKE $${args.length})`);
  }
  if (brand) {
    args.push(brand);
    where.push(`(b.name = $${args.length} OR LOWER(b.english_name) = LOWER($${args.length})
                 OR bs.name = $${args.length} OR LOWER(bs.english_name) = LOWER($${args.length}))`);
  }
  if (style) {
    /* ★ 2026-09-21 — 스타일은 상품마다 여러 개 달린다. 연결 표(product_term)만 본다.
       예전에는 표준 상품의 단일 스타일 FK(p.style_id)도 같이 봤는데, 그 칸이 없어졌다. */
    args.push(style);
    where.push(`EXISTS (
        SELECT 1
          FROM commerce.product_term pt
          JOIN dictionary.dictionary_term tagged_style ON tagged_style.id = pt.term_id
         WHERE pt.product_source_id = ps.id
           AND tagged_style.term_type = 'STYLE'
           AND tagged_style.canonical_name = $${args.length}
      )`);
  }
  /* 스타일 페이지의 큰 카테고리는 페이지를 나누기 전에 적용한다.
     첫 24개를 받은 뒤 브라우저에서 아우터만 남기면 1~2개씩 보이는 문제가 생긴다.
     규칙 순서는 브라우저 itemCatKey와 동일하며, 먼저 걸리는 분류를 우선한다. */
  const CATEGORY_PATTERNS = {
    shoes: '신발|슈즈|스니커|운동화|부츠|워커|로퍼|모카신|샌들|슬리퍼|더비|옥스포드|힐|플랫|메리제인|첼시|shoes|sneaker|boots|loafer|sandal',
    dress: '원피스|드레스|점프수트|셋업|jumpsuit|dress|onepiece',
    outer: '아우터|아웃터|자켓|재킷|코트|점퍼|블루종|봄버|패딩|다운|플리스|무스탕|가디건|베스트|조끼|바람막이|파카|트렌치|블레이저|jacket|coat|outer|parka|blouson|fleece|vest|cardigan',
    bottom: '하의|바지|팬츠|슬랙스|데님|진|청바지|스커트|치마|반바지|쇼츠|조거|레깅스|pants|denim|jeans|skirt|shorts|slacks|jogger|legging',
    top: '상의|티셔츠|티|반팔|긴팔|맨투맨|스웨트|후디|후드|셔츠|블라우스|니트|스웨터|폴로|탑|나시|피케|tee|t-shirt|shirt|blouse|knit|sweater|hood|sweat|polo|top',
  };
  const categoryOrder = Object.keys(CATEGORY_PATTERNS);
  const categoryText = `COALESCE(cs.source_category_name, '') || ' ' || COALESCE(p.canonical_name, ps.source_name, '')`;
  if (CATEGORY_PATTERNS[categoryGroup]) {
    args.push(CATEGORY_PATTERNS[categoryGroup]);
    where.push(`(${categoryText}) ~* $${args.length}`);
    for (const earlier of categoryOrder.slice(0, categoryOrder.indexOf(categoryGroup))) {
      args.push(CATEGORY_PATTERNS[earlier]);
      where.push(`NOT ((${categoryText}) ~* $${args.length})`);
    }
  }
  args.push(limit + 1);
  const limitArg = args.length;
  args.push(offset);
  const offsetArg = args.length;

  const FROM_SQL = `
       FROM commerce.product_source ps
       LEFT JOIN commerce.product p ON p.id = ps.product_id
       LEFT JOIN dictionary.brand b ON b.id = p.brand_id
       LEFT JOIN dictionary.brand_source bs ON bs.id = ps.source_brand_id
       LEFT JOIN dictionary.category_source cs ON cs.id = ps.source_category_id
       LEFT JOIN collection.source src ON src.id = ps.source_id
       LEFT JOIN LATERAL (
            SELECT list_price, sale_price, discount_rate, stock_status, observed_at,
                   rating, review_count, like_count, sales_count
              FROM snapshot.product_source_snapshot sn
             WHERE sn.product_source_id = ps.id
             ORDER BY observed_at DESC LIMIT 1) s ON true
      WHERE ${where.join(' AND ')}`;

  const r = await q(
    `SELECT p.id, ps.id AS product_source_id,
            COALESCE(p.canonical_name, ps.source_name) AS name,
            COALESCE(b.name, bs.name) AS brand, b.english_name AS brand_en,
            ps.source_product_id, ps.product_url, ps.thumbnail_url, ps.market_type,
            cs.source_category_name,
            src.code AS source_code, src.name AS source_name,
            s.list_price, s.sale_price, s.discount_rate, s.stock_status, s.observed_at
       ${FROM_SQL}
      ORDER BY ${orderBy}
      LIMIT $${limitArg} OFFSET $${offsetArg}`,
    args,
  );

  if (!r.ok) return failed(res, `AWS RDS 에 연결하지 못했습니다 (${r.code}).`, { detail: r.error });
  if (!r.rows.length) {
    return empty(
      res,
      kw || brand || style
        ? `조건에 맞는 상품이 없습니다 (검색어 ‘${kw || brand || style}’).`
        : 'AWS RDS 의 commerce.product 가 비어 있습니다.',
    );
  }

  // '더 보기' 버튼에 쓸 전체 개수 — 목록과 같은 조건으로 한 번 더 센다.
  const cnt = await q(`SELECT COUNT(*)::int AS n ${FROM_SQL}`, args.slice(0, args.length - 2));
  const total = cnt.ok && cnt.rows.length ? cnt.rows[0].n : null;

  const hasMore = r.rows.length > limit;
  const items = r.rows.slice(0, limit).map((x) => ({
    id: x.id || x.product_source_id,
    product_source_id: x.product_source_id,
    name: x.name || '(이름 없음)',
    brand: x.brand || null,
    brand_en: x.brand_en || null,
    source: x.source_code || null,
    source_label: x.source_name || null,
    market: x.market_type || null,
    url: x.product_url || null,
    /* 상대 경로로 저장된 사진에 베이스를 붙인다(_lib/image.js).
       전체의 38%가 그 모양이라, 그대로 내보내면 카드 사진이 안 뜬다. */
    image: absoluteImageUrl(x.thumbnail_url, x.source_code),
    category: x.source_category_name || null,
    price: {
      list: numOrNull(x.list_price),
      sale: numOrNull(x.sale_price),
      discount: numOrNull(x.discount_rate),
      stock: x.stock_status || null,
      as_of: x.observed_at ? String(x.observed_at).slice(0, 10) : null,
      // 스냅샷이 없으면 0 으로 채우지 않고 이유를 남긴다.
      unavailable: x.observed_at ? null : '이 상품은 아직 가격 스냅샷이 없습니다.',
    },
  }));

  const 가격없음 = items.filter((i) => i.price.unavailable).length;
  return ok(
    res,
    {
      count: items.length,
      items,
      offset,
      next_offset: offset + items.length,
      has_more: hasMore,
      total,
      style: style ? [style] : [],
      category_group: CATEGORY_PATTERNS[categoryGroup] ? categoryGroup : null,
    },
    가격없음 ? { note: `${가격없음}건은 가격 기록이 아직 없습니다.` } : {},
  );
}

function numOrNull(v) {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
