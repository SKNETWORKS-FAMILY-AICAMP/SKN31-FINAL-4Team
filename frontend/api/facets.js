/* GET /api/facets?style=스트릿&brand=스투시&limit=200
 * ── 세부 검색 네 칸(STYLE · 종류 · 브랜드 · 아이템명)의 후보 ─────────
 *
 * ★ 왜 새로 만들었나
 *   세부 검색은 스타일 › 종류 › 브랜드 › 아이템명 을 **위에서부터 차례로
 *   좁히는** 방식이었다. 브랜드만 알아도 스타일부터 골라야 했고, 그 계층은
 *   `style/static/js/search.js` 에 손으로 박아 둔 것이라 RDS 와 상관이 없었다.
 *
 *   이제 네 칸은 **서로 독립된 필터**다. 겹쳐 고르면 교집합이다 —
 *   스타일만 고르면 그 스타일 전부, 브랜드까지 고르면 그 스타일의 그 브랜드만.
 *
 * ★ 무엇을 세는가
 *   commerce.product  한 줄이 브랜드(brand_id)와 종류(item_term_id)를 들고 있고,
 *   commerce.product_term 이 그 상품에 붙은 스타일을 들고 있다.
 *   그래서 "이 스타일에 실제로 있는 브랜드" 를 지어내지 않고 셀 수 있다.
 *
 * ★ 자기 축은 자기를 좁히지 않는다
 *   브랜드 후보를 셀 때 브랜드 선택은 빼고 센다. 안 그러면 브랜드를 하나
 *   고르는 순간 그 칸에 하나만 남아 칩을 바꿔 낄 수가 없다. 패싯 검색의 기본이다.
 *
 * ★ 상품이 없으면 좁히지 못한다고 말한다
 *   commerce.product 가 비어 있으면 교차 계산은 거짓말이다. 사전만 내려보내고
 *   `narrowed:false` 로 밝힌다. 화면은 그 문장을 그대로 적는다.
 *
 * 길은 dictionary.js 와 같다 — BACKEND_API_URL(Django) 이 있으면 그쪽으로,
 * 없으면 pg 직결.
 */

import { q, viaBackend } from './_lib/db.js';
import { ok, empty, failed } from './_lib/reply.js';

const AXES = ['style', 'kind', 'brand', 'item'];
const MAX_LIMIT = 1000;

/* ★ 상품이 이만큼은 있어야 "축끼리 좁혔다" 고 말할 수 있다.
 *   2026-09-09 실측: commerce.product 에 1행밖에 없었다. 그 상태로 교차
 *   계산을 하면 어느 칸에도 한 개씩만 남아 "고를 게 없는 고장" 처럼 보인다.
 *   이보다 적으면 좁히기를 포기하고 사전을 준다 — narrowed:false 로 밝힌다.
 *   (Django 쪽 MIN_PRODUCTS_FOR_FACETS 와 같은 값이어야 한다.) */
const MIN_PRODUCTS = 20;

/** ?style=A&style=B (또는 style=A,B) → ['A','B'] */
function pick(url, name) {
  const out = [];
  const seen = new Set();
  for (const raw of url.searchParams.getAll(name)) {
    for (const v of String(raw).split(',')) {
      const s = v.trim();
      if (!s || seen.has(s)) continue;
      seen.add(s);
      out.push(s);
    }
  }
  return out;
}

/* 조건절을 만든다. `skip` 축 하나는 뺀다(자기 축 제외).
   args 배열에 값을 밀어 넣으면서 $n 번호를 붙인다 — 문자열 이어붙이기로
   값을 넣지 않는다(주입 방지). */
function where(sel, skip, args) {
  const w = [`p.status = 'ACTIVE'`];
  const put = (v) => `$${args.push(v)}`;

  if (skip !== 'style' && sel.style.length) {
    w.push(
      `p.id IN (SELECT pt.product_id FROM commerce.product_term pt
                  JOIN dictionary.dictionary_term t ON t.id = pt.term_id
                 WHERE t.term_type = 'STYLE' AND t.canonical_name = ANY(${put(sel.style)}))`,
    );
  }
  if (skip !== 'kind' && sel.kind.length) {
    w.push(
      `p.item_term_id IN (SELECT id FROM dictionary.dictionary_term
                           WHERE canonical_name = ANY(${put(sel.kind)}))`,
    );
  }
  if (skip !== 'brand' && sel.brand.length) {
    w.push(
      `p.brand_id IN (SELECT id FROM dictionary.brand WHERE name = ANY(${put(sel.brand)}))`,
    );
  }
  if (skip !== 'item' && sel.item.length) {
    w.push(`p.canonical_name = ANY(${put(sel.item)})`);
  }
  return w.join(' AND ');
}

/* 이미 고른 것은 후보에서 밀려나도 남긴다 — 그래야 칩을 다시 뺄 수 있다. */
function keepPicked(rows, picked) {
  const have = new Set(rows.map((r) => r.label));
  for (const k of picked) {
    if (!have.has(k)) rows.push({ label: k, count: 0, picked_only: true });
  }
  return rows;
}

const toRows = (r) =>
  r.rows.map((x) => ({ label: x.label, count: Number(x.n) }));

export default async function handler(req, res) {
  // Django 가 설정돼 있으면 그쪽이 먼저다 (RDS 를 열지 않아도 된다).
  const qs = req.url.includes('?') ? '?' + req.url.split('?')[1] : '';
  const relayed = await viaBackend('/facets' + qs);
  if (relayed) {
    res.statusCode = 200;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    // 조건마다 답이 다르다 — 사전만큼 길게 캐시하면 안 된다.
    /* ★ 2026-09-22 — 성공한 응답만 캐시한다.
       viaBackend 는 실패해도 {status:'error'} 를 돌려주는데 그것도 truthy 라,
       예전에는 백엔드가 잠깐 죽은 사이의 에러가 엣지에 박혔다. */
    res.setHeader('Cache-Control', relayed && relayed.status === 'ok'
      ? 's-maxage=120, stale-while-revalidate=600'
      : 'no-store');
    return res.end(JSON.stringify(relayed));
  }

  const url = new URL(req.url, 'http://x');
  const limit = Math.min(
    MAX_LIMIT,
    Math.max(1, Number(url.searchParams.get('limit') || 200)),
  );
  const sel = {};
  for (const a of AXES) sel[a] = pick(url, a);

  /* 상품이 몇 개나 있는가 — 너무 적으면 교차 계산이 의미가 없다. */
  const probe = await q(
    `SELECT count(*) AS n FROM commerce.product WHERE status='ACTIVE'`,
  );
  if (!probe.ok) {
    return failed(res, `AWS RDS 에 연결하지 못했습니다 (${probe.code}).`, {
      detail: probe.error,
    });
  }
  const nProducts = Number(probe.rows[0].n);

  if (nProducts < MIN_PRODUCTS) {
    const t = await q(
      `SELECT canonical_name AS label, term_type AS facet
         FROM dictionary.dictionary_term
        WHERE status='ACTIVE' AND term_type IN ('STYLE','ITEM')
        LIMIT $1`,
      [limit * 2],
    );
    const b = await q(
      `SELECT name AS label FROM dictionary.brand
        WHERE status='ACTIVE' AND name IS NOT NULL AND name <> '' LIMIT $1`,
      [limit],
    );
    const data = {
      style: (t.ok ? t.rows : [])
        .filter((x) => x.facet === 'STYLE')
        .map((x) => ({ label: x.label, count: null })),
      kind: (t.ok ? t.rows : [])
        .filter((x) => x.facet === 'ITEM')
        .map((x) => ({ label: x.label, count: null })),
      brand: (b.ok ? b.rows : []).map((x) => ({ label: x.label, count: null })),
      item: [], // 아이템명(상품명)은 상품이 있어야 나온다
    };
    if (!AXES.some((a) => data[a].length)) {
      return empty(
        res,
        '상품도 사전도 비어 있습니다. commerce.product · dictionary_term · brand 적재를 확인하세요.',
        { narrowed: false, products: nProducts },
      );
    }
    return ok(res, data, {
      matched: 0,
      narrowed: false,
      products: nProducts,
      note:
        `commerce.product 가 ${nProducts}개뿐이라 축끼리 좁히지 못했습니다 ` +
        `— 사전 목록을 그대로 보냅니다. 상품이 ${MIN_PRODUCTS}개를 넘으면 ` +
        '자동으로 좁히기 시작합니다.',
    });
  }

  /* ── 축별 후보 ────────────────────────────────────────────
     쿼리마다 args 를 새로 만든다. where() 가 $n 을 붙이며 밀어 넣기 때문에
     하나를 돌려 쓰면 번호가 어긋난다. */
  const runs = {
    style: () => {
      const a = [];
      const w = where(sel, 'style', a);
      return q(
        `SELECT t.canonical_name AS label, count(DISTINCT pt.product_id) AS n
           FROM commerce.product_term pt
           JOIN dictionary.dictionary_term t ON t.id = pt.term_id
           JOIN commerce.product p ON p.id = pt.product_id
          WHERE t.term_type = 'STYLE' AND ${w}
          GROUP BY 1 ORDER BY n DESC, 1 LIMIT $${a.push(limit)}`,
        a,
      );
    },
    kind: () => {
      const a = [];
      const w = where(sel, 'kind', a);
      return q(
        `SELECT t.canonical_name AS label, count(*) AS n
           FROM commerce.product p
           JOIN dictionary.dictionary_term t ON t.id = p.item_term_id
          WHERE ${w}
          GROUP BY 1 ORDER BY n DESC, 1 LIMIT $${a.push(limit)}`,
        a,
      );
    },
    brand: () => {
      const a = [];
      const w = where(sel, 'brand', a);
      return q(
        `SELECT b.name AS label, count(*) AS n
           FROM commerce.product p
           JOIN dictionary.brand b ON b.id = p.brand_id
          WHERE ${w} AND b.name IS NOT NULL AND b.name <> ''
          GROUP BY 1 ORDER BY n DESC, 1 LIMIT $${a.push(limit)}`,
        a,
      );
    },
    item: () => {
      const a = [];
      const w = where(sel, 'item', a);
      return q(
        `SELECT p.canonical_name AS label, count(*) AS n
           FROM commerce.product p
          WHERE ${w} AND p.canonical_name IS NOT NULL AND p.canonical_name <> ''
          GROUP BY 1 ORDER BY n DESC, 1 LIMIT $${a.push(limit)}`,
        a,
      );
    },
  };

  const countArgs = [];
  const countWhere = where(sel, null, countArgs);
  const [cnt, ...results] = await Promise.all([
    q(`SELECT count(*) AS n FROM commerce.product p WHERE ${countWhere}`, countArgs),
    runs.style(),
    runs.kind(),
    runs.brand(),
    runs.item(),
  ]);

  const data = {};
  const broke = [];
  AXES.forEach((axis, i) => {
    const r = results[i];
    if (!r.ok) {
      broke.push(`${axis}(${r.code})`);
      data[axis] = keepPicked([], sel[axis]);
      return;
    }
    data[axis] = keepPicked(toRows(r), sel[axis]);
  });

  if (broke.length === AXES.length) {
    return failed(res, `AWS RDS 질의가 모두 실패했습니다 (${broke.join(' · ')}).`);
  }
  if (!AXES.some((a) => data[a].length)) {
    return empty(res, '고른 조건에 맞는 상품이 없습니다. 조건을 하나 빼고 다시 보세요.', {
      matched: 0,
      narrowed: true,
    });
  }

  const extra = {
    matched: cnt.ok ? Number(cnt.rows[0].n) : null,
    narrowed: true,
    selected: sel,
    products: nProducts,
  };
  if (broke.length) extra.note = `일부 축을 못 읽었습니다: ${broke.join(' · ')}`;
  return ok(res, data, extra);
}
