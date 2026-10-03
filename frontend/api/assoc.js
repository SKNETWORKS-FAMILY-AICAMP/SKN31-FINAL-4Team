/* GET /api/assoc?term=발레코어&limit=20
 *
 * 연관어 — `analysis.term_assoc_daily` 를 읽는다.
 * 최근 28일의 일별 연관어를 합쳐서 돌려준다.
 *
 * ★ lift·PMI는 크롤러가 일별로 계산한 값의 28일 평균이다.
 *   동시언급 수는 합하고 백분위는 기간 중 최고값을 쓴다.
 *   Django API가 설정돼 있으면 위에서 그 응답을 그대로 중계하며,
 *   아래 SQL은 중계가 없는 배포의 대체 경로다.
 */

import { q, viaBackend } from './_lib/db.js';
import { ok, empty, failed } from './_lib/reply.js';

export default async function handler(req, res) {
  // Django API 가 설정돼 있으면 그쪽이 먼저다 (RDS 를 열지 않아도 된다).
  const relayed = await viaBackend('/assoc' + (req.url.includes('?') ? '?' + req.url.split('?')[1] : ''));
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
  const term = (url.searchParams.get('term') || '').trim();
  const limit = Math.min(200, Math.max(5, Number(url.searchParams.get('limit') || 200)));

  if (!term) return empty(res, 'term 을 지정해 주세요. 예: /api/assoc?term=발레코어');

  const r = await q(
    `WITH src AS (
       SELECT id FROM dictionary.dictionary_term
        WHERE canonical_name = $1 OR normalized_name = lower($1)
        ORDER BY id LIMIT 1
     ), latest AS (
       SELECT DISTINCT ON (a.basis)
              a.basis, a.metric_version, a.metric_date
         FROM analysis.term_assoc_daily a
         JOIN src ON src.id = a.source_term_id
        ORDER BY a.basis, a.metric_date DESC, a.id DESC
     ), rolled AS (
       SELECT a.target_term_id, a.basis,
              sum(a.cooccurrence_count)::bigint AS cooccurrence_count,
              avg(a.lift) AS lift,
              avg(a.pmi) AS pmi,
              max(a.association_percentile) AS association_percentile,
              max(a.metric_date) AS metric_date,
              max(a.metric_version) AS metric_version
         FROM analysis.term_assoc_daily a
         JOIN src ON src.id = a.source_term_id
         JOIN latest l ON l.basis = a.basis AND l.metric_version = a.metric_version
        WHERE a.metric_date BETWEEN l.metric_date - 27 AND l.metric_date
        GROUP BY a.target_term_id, a.basis
     )
     SELECT tgt.canonical_name AS term, tgt.term_type AS facet,
            sum(r.cooccurrence_count)::bigint AS cooccurrence_count,
            avg(r.lift) AS lift, avg(r.pmi) AS pmi,
            max(r.association_percentile) AS association_percentile,
            array_agg(DISTINCT lower(r.basis)) AS basis,
            least(100, max(r.association_percentile)
              + CASE WHEN count(DISTINCT r.basis) > 1 THEN 10 ELSE 0 END) AS score,
            max(r.metric_date) AS metric_date,
            max(r.metric_version) AS metric_version
       FROM rolled r
       JOIN dictionary.dictionary_term tgt ON tgt.id = r.target_term_id
      GROUP BY r.target_term_id, tgt.canonical_name, tgt.term_type
      ORDER BY score DESC NULLS LAST, cooccurrence_count DESC
      LIMIT $2`,
    [term, limit],
  );

  if (!r.ok) return failed(res, `AWS RDS 에 연결하지 못했습니다 (${r.code}).`, { detail: r.error });
  if (!r.rows.length) {
    const any = await q('SELECT count(*) n FROM analysis.term_assoc_daily');
    const 전체 = any.ok ? Number(any.rows[0].n) : null;
    return empty(
      res,
      전체 === 0
        ? 'AWS RDS 의 연관어 표(analysis.term_assoc_daily)가 통째로 비어 있습니다. ' +
            '크롤러가 아직 이 표로 보내지 않습니다.'
        : `‘${term}’ 의 연관어가 아직 없습니다. 함께 나온 글이 모자랍니다.`,
      { term, total_rows: 전체 },
    );
  }

  return ok(res, {
    term,
    as_of: String(r.rows[0].metric_date).slice(0, 10),
    window_days: 28,
    ranking_scope: 'cumulative',
    metric_version: r.rows[0].metric_version || null,
    items: r.rows.map((x, index) => ({
      term: x.term,
      facet: x.facet,
      facet_ko: ({ITEM:'아이템',MATERIAL:'소재',COLOR:'색',DETAIL:'디테일',TPO:'TPO',STYLE:'스타일',BRAND:'브랜드',PERSON:'인물'})[x.facet] || x.facet,
      cooccurrence: Number(x.cooccurrence_count ?? 0),
      recent_cooccurrence: Number(x.cooccurrence_count ?? 0),
      lift: x.lift === null ? null : Number(x.lift),
      pmi: x.pmi === null ? null : Number(x.pmi),
      percentile: x.association_percentile === null ? null : Number(x.association_percentile),
      score: x.score === null ? null : Number(x.score),
      rank: index + 1,
      feature_rank: index + 1,
      feature_change: null,
      cooc_rank: null,
      cooc_change: null,
      change: null,
      basis: Array.isArray(x.basis) ? x.basis : [],
      recent_bases: Array.isArray(x.basis) ? x.basis : [],
      is_historical: false,
      weekly_counts: [],
      evidence: [],
    })),
  });
}
