/* GET /api/trend?term=발레코어&days=90
 *   또는 /api/trend            → 지금 값이 있는 용어 목록
 *
 * ── 무엇을 돌려주나 ───────────────────────────────────────
 * `analysis.term_metric_daily` 를 날짜순으로 그대로 돌려준다.
 * **여기서 지표를 계산하지 않는다.** 온도·모멘텀의 정의는
 * `FEEDiT_지표계산_설계서.md` 가 원본이고, 계산은 크롤러가 한다.
 * 여기서 다시 계산하면 화면과 챗봇이 서로 다른 숫자를 말하게 된다.
 *
 * ── ★ 없는 값을 지어내지 않는다 ──────────────────────────
 * RDS 의 이 표에는 **온도(temp)·모멘텀·ma7·ma28 컬럼이 없다.**
 * 있는 것은 mention_count · document_count · source_count ·
 * sentiment_avg · growth_rate · trend_score · metrics(JSON) 뿐이다.
 *
 * 그래서 온도를 달라고 하면 계산해서 만들어 내지 않고,
 * `unavailable` 에 "이 값은 아직 RDS 에 없습니다" 라고 적어 보낸다.
 * 화면은 그 자리를 '측정 불가'로 그린다.
 * (metrics JSON 안에 들어 있으면 그건 꺼내 쓴다 — 아래 pick() 참고.)
 */

import { q, viaBackend } from './_lib/db.js';
import { ok, empty, failed } from './_lib/reply.js';

// 설계서가 쓰는 이름 ← RDS 컬럼. 없는 것은 null 로 두고 사유를 붙인다.
const WANTED = ['temp', 'momentum', 'ma7', 'ma28', 'level', 'pct_rank'];

export default async function handler(req, res) {
  // Django API 가 설정돼 있으면 그쪽이 먼저다 (RDS 를 열지 않아도 된다).
  const relayed = await viaBackend('/trend' + (req.url.includes('?') ? '?' + req.url.split('?')[1] : ''));
  if (relayed) {
    res.statusCode = 200;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    /* ★ 2026-09-22 — 성공한 응답만 캐시한다. viaBackend 는 실패해도
       {status:'error'} 를 돌려주는데 그것도 truthy 라, 예전에는 백엔드가
       잠깐 죽은 사이의 에러가 엣지에 5분간 박혔다. 배포 직후가 특히 위험하다. */
    res.setHeader('Cache-Control', relayed.status === 'ok'
      ? 's-maxage=300, stale-while-revalidate=600'
      : 'no-store');
    return res.end(JSON.stringify(relayed));
  }

  const url = new URL(req.url, 'http://x');
  const term = (url.searchParams.get('term') || '').trim();
  const days = Math.min(365, Math.max(7, Number(url.searchParams.get('days') || 90)));

  if (!term) return listTerms(res);

  const r = await q(
    `SELECT m.metric_date,
            m.mention_count, m.document_count, m.source_count,
            m.sentiment_avg, m.growth_rate, m.trend_score, m.metrics,
            t.canonical_name, t.term_type
       FROM analysis.term_metric_daily m
       JOIN dictionary.dictionary_term t ON t.id = m.term_id
      WHERE (t.canonical_name = $1 OR t.normalized_name = lower($1))
        AND m.metric_date >= current_date - $2::int
      ORDER BY m.metric_date`,
    [term, days],
  );

  if (!r.ok) {
    return failed(res, `AWS RDS 에 연결하지 못했습니다 (${r.code}).`, { detail: r.error });
  }
  if (!r.rows.length) {
    // 용어 자체가 없는 것과, 용어는 있는데 지표가 없는 것을 구별한다.
    const known = await q(
      `SELECT 1 FROM dictionary.dictionary_term
        WHERE canonical_name = $1 OR normalized_name = lower($1) LIMIT 1`,
      [term],
    );
    const 있나 = known.ok && known.rows.length > 0;
    return empty(
      res,
      있나
        ? `‘${term}’ 은 사전에 있지만 최근 ${days}일 안에 측정된 지표가 없습니다.`
        : `‘${term}’ 을 사전에서 찾지 못했습니다.`,
      { term, known: 있나 },
    );
  }

  const series = r.rows.map((row) => {
    const j = row.metrics && typeof row.metrics === 'object' ? row.metrics : {};
    return {
      date: String(row.metric_date).slice(0, 10),
      mention: num(row.mention_count),
      document: num(row.document_count),
      source: num(row.source_count),
      sentiment: num(row.sentiment_avg),
      growth: num(row.growth_rate),
      score: num(row.trend_score),
      // 설계서의 값이 metrics JSON 안에 들어 있으면 꺼내 쓴다.
      ...pick(j),
    };
  });

  const last = series[series.length - 1] || {};
  const missing = WANTED.filter((k) => last[k] === undefined || last[k] === null);

  return ok(
    res,
    {
      term: r.rows[0].canonical_name,
      facet: r.rows[0].term_type,
      days,
      points: series.length,
      series,
    },
    missing.length
      ? {
          unavailable: {
            fields: missing,
            reason:
              `이 값들은 AWS RDS 의 analysis.term_metric_daily 에 없습니다 ` +
              `(${missing.join('·')}). 지금 있는 것은 언급량·문서수·출처수·감성·증가율·` +
              `trend_score 입니다. 온도·모멘텀을 쓰려면 크롤러가 metrics(JSON) 에 ` +
              `실어 보내거나 스키마에 컬럼을 더해야 합니다.`,
          },
        }
      : {},
  );
}

/** 지금 지표가 실제로 있는 용어들 — 화면의 검색 후보로 쓴다. */
async function listTerms(res) {
  const r = await q(
    `SELECT t.canonical_name, t.term_type,
            count(*) AS points, max(m.metric_date) AS last_date
       FROM analysis.term_metric_daily m
       JOIN dictionary.dictionary_term t ON t.id = m.term_id
      GROUP BY t.canonical_name, t.term_type
      HAVING count(*) >= 3
      ORDER BY count(*) DESC
      LIMIT 500`,
  );
  if (!r.ok) return failed(res, `AWS RDS 에 연결하지 못했습니다 (${r.code}).`, { detail: r.error });
  if (!r.rows.length) {
    return empty(
      res,
      'AWS RDS 의 analysis.term_metric_daily 가 비어 있습니다. ' +
        '크롤러의 rds_sync 는 상품·브랜드·사전만 보내고 지표는 보내지 않습니다 — ' +
        '보내는 코드가 아직 없는 것이지 연결이 끊긴 것이 아닙니다.',
    );
  }
  return ok(
    res,
    r.rows.map((x) => ({
      term: x.canonical_name,
      facet: x.term_type,
      points: Number(x.points),
      last_date: String(x.last_date).slice(0, 10),
    })),
  );
}

function num(v) {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** metrics JSON 안에 설계서 값이 들어 있으면 꺼낸다. 없으면 넣지 않는다. */
function pick(j) {
  const out = {};
  for (const k of WANTED) if (j[k] !== undefined) out[k] = num(j[k]);
  return out;
}
