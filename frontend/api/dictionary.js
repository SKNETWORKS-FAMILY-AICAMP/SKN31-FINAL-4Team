/* GET /api/dictionary?limit=4000 — 화면 검색이 쓸 사전 전체.
 *
 * ── 왜 필요한가 ───────────────────────────────────────────
 * 프론트(`style/static/js/search.js`)는 자기 파일에 박아 둔 146개로만
 * 검색했다. 그래서 **RDS 사전에 있는 말도 "찾지 못했습니다"** 가 됐다.
 * 실제로 스투시·키르시·엄브로가 그랬다.
 *
 * ── 브랜드는 다른 표에 산다 ───────────────────────────────
 *   dictionary.dictionary_term : 스타일·아이템·소재·색·디테일·TPO   (395행)
 *   dictionary.brand           : 브랜드                              (2,775행)
 * 화면에서는 둘 다 '검색해서 지표를 볼 대상' 이므로 여기서 합쳐 준다.
 * 어디서 왔는지는 `kind` 로 남긴다 — 지표가 없을 때 이유를 정확히
 * 말하려면(사전에 없는 것 / 사전엔 있는데 측정이 없는 것) 이 구분이 필요하다.
 *
 * ★ brand 의 이름 칸은 `name` 이다. `canonical_name` 이 아니다 —
 *   Django 마이그레이션 0014 가 그 칸을 지웠다. 표마다 이름 규칙이 다르다.
 */

import { q, viaBackend } from './_lib/db.js';
import { ok, empty, failed } from './_lib/reply.js';

/* 서버가 쓰는 코드 → 화면이 쓰는 축 이름. Django 쪽 FACET_KO 와 같아야 한다. */
const FACET_KO = {
  BRAND: '브랜드', STYLE: '스타일', ITEM: '아이템',
  MATERIAL: '소재', DETAIL: '디테일', COLOR: '색', TPO: 'TPO',
};

export default async function handler(req, res) {
  // Django API 가 설정돼 있으면 그쪽이 먼저다 (RDS 를 열지 않아도 된다).
  const qs = req.url.includes('?') ? '?' + req.url.split('?')[1] : '';
  const relayed = await viaBackend('/dictionary' + qs);
  if (relayed) {
    res.statusCode = 200;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    // 사전은 자주 안 바뀐다 — 트렌드보다 길게 잡아 둔다.
    /* ★ 2026-09-22 — 성공한 응답만 캐시한다.
       viaBackend 는 실패해도 {status:'error'} 를 돌려주는데 그것도 truthy 라,
       예전에는 백엔드가 잠깐 죽은 사이의 에러가 엣지에 박혔다. */
    res.setHeader('Cache-Control', relayed && relayed.status === 'ok'
      ? 's-maxage=3600, stale-while-revalidate=86400'
      : 'no-store');
    return res.end(JSON.stringify(relayed));
  }

  const url = new URL(req.url, 'http://x');
  const limit = Math.min(8000, Math.max(1, Number(url.searchParams.get('limit') || 4000)));

  const r = await q(
    `SELECT canonical_name AS label, term_type AS facet, 'term' AS kind,
            coalesce(english_name, '') AS en
       FROM dictionary.dictionary_term
      WHERE status = 'ACTIVE'
      LIMIT $1`,
    [limit],
  );
  if (!r.ok) {
    return failed(res, `AWS RDS 에 연결하지 못했습니다 (${r.code}).`, { detail: r.error });
  }

  const b = await q(
    `SELECT name AS label, 'BRAND' AS facet, 'brand' AS kind,
            coalesce(english_name, '') AS en
       FROM dictionary.brand
      WHERE status = 'ACTIVE' AND name IS NOT NULL AND name <> ''
      LIMIT $1`,
    [limit],
  );
  // 브랜드만 못 읽었다고 용어까지 버리지 않는다 — 반쪽이라도 검색은 되게 한다.
  const brandRows = b.ok ? b.rows : [];

  const rows = r.rows.concat(brandRows).map((x) => ({
    label: x.label,
    facet: FACET_KO[x.facet] || x.facet,
    kind: x.kind,
    en: x.en || '',
  }));

  if (!rows.length) {
    return empty(res, '사전이 비어 있습니다. dictionary_term·brand 적재를 확인하세요.');
  }

  const counts = {};
  for (const x of rows) counts[x.facet] = (counts[x.facet] || 0) + 1;

  const extra = { counts, total: rows.length };
  if (!b.ok) extra.note = `브랜드는 못 읽었습니다 (${b.code}). 용어만 보냅니다.`;
  return ok(res, rows, extra);
}
