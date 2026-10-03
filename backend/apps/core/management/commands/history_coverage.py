"""과거 데이터 누적 현황 점검 (읽기 전용).

수명주기처럼 긴 기간이 필요한 지표를 RDS 안의 데이터만으로 만들 수 있는지 본다.
SQLite 는 보지 않는다. 쓰기는 하지 않는다 (READ ONLY 트랜잭션).

    python manage.py history_coverage            # 표로 출력
    python manage.py history_coverage --json     # JSON 으로 출력 (공유용)

보는 것
  1. snapshot.* 세 표 — 며칠치가 쌓였나, 대상별로 며칠씩 이어지나
  2. analysis.term_metric_daily — 날짜 · 버전 · 플랫폼 분포
  3. 언급 이력 재구성 가능성 — text_term_mention 을 '글이 쓰인 날'로 되돌리면
     용어별로 며칠치 이력이 나오나 (댓글: metadata.published_at, 그 외: 콘텐츠 게시일)
"""
import json

from django.core.management.base import BaseCommand
from django.db import connection

TZ = "Asia/Seoul"
TS_RE = r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"

QUERIES = {
    # ── 1. 스냅샷 ─────────────────────────────────────────────
    "snapshot_days": f"""
        SELECT tbl, rows, entities, first_day, last_day, days,
               round(rows::numeric / nullif(days,0)) AS rows_per_day
        FROM (
          SELECT 'product_source_snapshot' tbl, count(*) rows,
                 count(DISTINCT product_source_id) entities,
                 min((observed_at AT TIME ZONE '{TZ}')::date) first_day,
                 max((observed_at AT TIME ZONE '{TZ}')::date) last_day,
                 count(DISTINCT (observed_at AT TIME ZONE '{TZ}')::date) days
          FROM snapshot.product_source_snapshot
          UNION ALL
          SELECT 'resale_snapshot', count(*), count(DISTINCT product_source_id),
                 min((observed_at AT TIME ZONE '{TZ}')::date), max((observed_at AT TIME ZONE '{TZ}')::date),
                 count(DISTINCT (observed_at AT TIME ZONE '{TZ}')::date)
          FROM snapshot.resale_snapshot
          UNION ALL
          SELECT 'content_snapshot', count(*), count(DISTINCT content_item_id),
                 min((observed_at AT TIME ZONE '{TZ}')::date), max((observed_at AT TIME ZONE '{TZ}')::date),
                 count(DISTINCT (observed_at AT TIME ZONE '{TZ}')::date)
          FROM snapshot.content_snapshot
        ) t
    """,
    # 대상(상품·콘텐츠) 하나가 며칠치 관측을 갖고 있나 — 7·14·28일 이상 몇 개
    "snapshot_depth": f"""
        WITH d AS (
          SELECT 'product_source_snapshot' tbl, product_source_id id,
                 count(DISTINCT (observed_at AT TIME ZONE '{TZ}')::date) n
          FROM snapshot.product_source_snapshot GROUP BY 2
          UNION ALL
          SELECT 'resale_snapshot', product_source_id,
                 count(DISTINCT (observed_at AT TIME ZONE '{TZ}')::date)
          FROM snapshot.resale_snapshot GROUP BY 2
          UNION ALL
          SELECT 'content_snapshot', content_item_id,
                 count(DISTINCT (observed_at AT TIME ZONE '{TZ}')::date)
          FROM snapshot.content_snapshot GROUP BY 2
        )
        SELECT tbl, count(*) entities, max(n) max_days,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY n) median_days,
               count(*) FILTER (WHERE n >= 7) ge7, count(*) FILTER (WHERE n >= 14) ge14,
               count(*) FILTER (WHERE n >= 28) ge28
        FROM d GROUP BY tbl ORDER BY tbl
    """,
    # 날짜별 행 수 — 빠진 날이 있는지
    "snapshot_daily": f"""
        SELECT 'product' tbl, (observed_at AT TIME ZONE '{TZ}')::date AS dt, count(*) rows,
               string_agg(DISTINCT ranking_scope, ',') scopes
        FROM snapshot.product_source_snapshot GROUP BY 2
        UNION ALL
        SELECT 'resale', (observed_at AT TIME ZONE '{TZ}')::date, count(*), NULL
        FROM snapshot.resale_snapshot GROUP BY 2
        UNION ALL
        SELECT 'content', (observed_at AT TIME ZONE '{TZ}')::date, count(*), NULL
        FROM snapshot.content_snapshot GROUP BY 2
        ORDER BY 1, 2
    """,
    # ── 2. 지표 표 ────────────────────────────────────────────
    "term_metric_daily": """
        SELECT metric_date, metric_version, coalesce(s.code, '(합산)') source,
               count(*) rows, count(DISTINCT term_id) terms,
               count(*) FILTER (WHERE trend_temperature IS NOT NULL) has_temp,
               count(*) FILTER (WHERE ma28 IS NOT NULL) has_ma28
        FROM analysis.term_metric_daily m
        LEFT JOIN collection.source s ON s.id = m.source_id
        GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
    """,
    # ── 3. 언급 이력 재구성 ───────────────────────────────────
    # 문서 종류별로 '쓰인 날'을 얼마나 알 수 있나
    "doc_dates": f"""
        SELECT d.document_type, s.code source, count(*) docs,
               count(*) FILTER (WHERE d.analysis_metadata->>'published_at' ~ '{TS_RE}') own_date,
               count(*) FILTER (WHERE c.published_at IS NOT NULL) content_date,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM analysis.text_term_mention x
                                              WHERE x.document_id = d.id)) with_mention
        FROM analysis.text_document d
        JOIN collection.source s ON s.id = d.source_id
        LEFT JOIN content.content_item c ON c.id = d.content_item_id
        GROUP BY 1, 2 ORDER BY 3 DESC
    """,
    "mention_monthly": f"""
        WITH ev AS (
          SELECT x.term_id,
                 (CASE WHEN d.analysis_metadata->>'published_at' ~ '{TS_RE}'
                       THEN (d.analysis_metadata->>'published_at')::timestamptz
                       ELSE c.published_at END AT TIME ZONE '{TZ}')::date AS dt
          FROM analysis.text_term_mention x
          JOIN analysis.text_document d ON d.id = x.document_id
          LEFT JOIN content.content_item c ON c.id = d.content_item_id
        )
        SELECT to_char(date_trunc('month', dt), 'YYYY-MM') AS mon,
               count(*) mentions, count(DISTINCT term_id) terms, count(DISTINCT dt) days
        FROM ev WHERE dt IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """,
    # 용어별로 최근 365일 안에 언급이 있는 날이 며칠인가 — 수명주기(28일 이상)가 가능한 용어 수
    "term_history_depth": f"""
        WITH ev AS (
          SELECT x.term_id,
                 (CASE WHEN d.analysis_metadata->>'published_at' ~ '{TS_RE}'
                       THEN (d.analysis_metadata->>'published_at')::timestamptz
                       ELSE c.published_at END AT TIME ZONE '{TZ}')::date AS dt
          FROM analysis.text_term_mention x
          JOIN analysis.text_document d ON d.id = x.document_id
          LEFT JOIN content.content_item c ON c.id = d.content_item_id
        ), per AS (
          SELECT term_id, min(dt) first_day, max(dt) last_day,
                 count(DISTINCT dt) FILTER (WHERE dt > current_date - 365) days_365,
                 count(DISTINCT date_trunc('week', dt)) FILTER (WHERE dt > current_date - 365) weeks_365,
                 count(*) mentions
          FROM ev WHERE dt IS NOT NULL GROUP BY term_id
        )
        SELECT count(*) terms,
               count(*) FILTER (WHERE days_365 >= 28) days_ge28,
               count(*) FILTER (WHERE weeks_365 >= 12) weeks_ge12,
               count(*) FILTER (WHERE weeks_365 >= 26) weeks_ge26,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY days_365) median_days_365,
               min(first_day) first_day, max(last_day) last_day
        FROM per
    """,
    "top_terms_depth": f"""
        WITH ev AS (
          SELECT x.term_id,
                 (CASE WHEN d.analysis_metadata->>'published_at' ~ '{TS_RE}'
                       THEN (d.analysis_metadata->>'published_at')::timestamptz
                       ELSE c.published_at END AT TIME ZONE '{TZ}')::date AS dt
          FROM analysis.text_term_mention x
          JOIN analysis.text_document d ON d.id = x.document_id
          LEFT JOIN content.content_item c ON c.id = d.content_item_id
        )
        SELECT t.canonical_name term, t.term_type, count(*) mentions,
               count(DISTINCT dt) FILTER (WHERE dt > current_date - 365) days_365,
               count(DISTINCT date_trunc('week', dt)) FILTER (WHERE dt > current_date - 365) weeks_365,
               min(dt) first_day, max(dt) last_day
        FROM ev JOIN dictionary.dictionary_term t ON t.id = ev.term_id
        WHERE dt IS NOT NULL
        GROUP BY 1, 2 ORDER BY mentions DESC LIMIT 30
    """,
    # 스타일 용어만 따로 — 화면의 수명주기는 주로 스타일로 묻는다
    "style_terms_depth": f"""
        WITH ev AS (
          SELECT x.term_id,
                 (CASE WHEN d.analysis_metadata->>'published_at' ~ '{TS_RE}'
                       THEN (d.analysis_metadata->>'published_at')::timestamptz
                       ELSE c.published_at END AT TIME ZONE '{TZ}')::date AS dt
          FROM analysis.text_term_mention x
          JOIN analysis.text_document d ON d.id = x.document_id
          LEFT JOIN content.content_item c ON c.id = d.content_item_id
        )
        SELECT t.canonical_name term, count(ev.dt) mentions,
               count(DISTINCT ev.dt) FILTER (WHERE ev.dt > current_date - 365) days_365,
               count(DISTINCT date_trunc('week', ev.dt)) FILTER (WHERE ev.dt > current_date - 365) weeks_365,
               min(ev.dt) first_day, max(ev.dt) last_day
        FROM dictionary.dictionary_term t
        LEFT JOIN ev ON ev.term_id = t.id
        WHERE t.term_type = 'STYLE'
        GROUP BY 1 ORDER BY 2 DESC
    """,
    # 리뷰 — 작성일이 있으므로 상품 쪽 장기 이력 후보
    "review_monthly": f"""
        SELECT to_char(date_trunc('month', source_created_at AT TIME ZONE '{TZ}'), 'YYYY-MM') AS mon,
               count(*) reviews, count(DISTINCT product_source_id) products
        FROM commerce.product_review WHERE source_created_at IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """,
    # ── 4. 최근 수집·분석이 실제로 돌고 있나 (출처별 · 최근 21일) ──
    "pipeline_recent": f"""
        SELECT 'crawl_run' what, s.code src, (r.started_at AT TIME ZONE '{TZ}')::date AS dt,
               count(*) n, sum(r.success_count) ok, sum(r.failure_count) fail
        FROM collection.crawl_run r JOIN collection.source s ON s.id = r.source_id
        WHERE r.started_at > now() - interval '21 days' GROUP BY 1,2,3
        UNION ALL
        SELECT 'raw_document', s.code, (d.collected_at AT TIME ZONE '{TZ}')::date, count(*), NULL, NULL
        FROM collection.raw_document d JOIN collection.source s ON s.id = d.source_id
        WHERE d.collected_at > now() - interval '21 days' GROUP BY 1,2,3
        UNION ALL
        SELECT 'content_item(new)', s.code, (c.first_seen_at AT TIME ZONE '{TZ}')::date, count(*), NULL, NULL
        FROM content.content_item c JOIN collection.source s ON s.id = c.source_id
        WHERE c.first_seen_at > now() - interval '21 days' GROUP BY 1,2,3
        UNION ALL
        SELECT 'text_document(new)', s.code, (d.created_at AT TIME ZONE '{TZ}')::date, count(*), NULL, NULL
        FROM analysis.text_document d JOIN collection.source s ON s.id = d.source_id
        WHERE d.created_at > now() - interval '21 days' GROUP BY 1,2,3
        UNION ALL
        SELECT 'text_term_mention(new)', NULL, (x.created_at AT TIME ZONE '{TZ}')::date, count(*), NULL, NULL
        FROM analysis.text_term_mention x
        WHERE x.created_at > now() - interval '21 days' GROUP BY 1,2,3
        UNION ALL
        SELECT 'product_review(new)', NULL, (r.created_at AT TIME ZONE '{TZ}')::date, count(*), NULL, NULL
        FROM commerce.product_review r
        WHERE r.created_at > now() - interval '21 days' GROUP BY 1,2,3
        ORDER BY 1, 2, 3
    """,
}


class Command(BaseCommand):
    help = "RDS 안의 과거 데이터 누적 현황 (읽기 전용)"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--only", nargs="*", help="특정 항목만 (예: snapshot_days doc_dates)")

    def handle(self, *args, **opts):
        names = opts.get("only") or list(QUERIES)
        out = {}
        with connection.cursor() as cur:
            cur.execute("BEGIN READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '120s'")
            try:
                for name in names:
                    try:
                        cur.execute(QUERIES[name])
                        cols = [c[0] for c in cur.description]
                        out[name] = {"cols": cols, "rows": [list(r) for r in cur.fetchall()]}
                    except Exception as exc:  # 한 항목이 실패해도 나머지는 본다
                        out[name] = {"error": f"{exc.__class__.__name__}: {exc}"}
                        cur.execute("ROLLBACK")
                        cur.execute("BEGIN READ ONLY")
                        cur.execute("SET LOCAL statement_timeout = '120s'")
            finally:
                cur.execute("ROLLBACK")

        if opts["json"]:
            self.stdout.write(json.dumps(out, ensure_ascii=False, default=str, indent=1))
            return
        for name, res in out.items():
            self.stdout.write(f"\n## {name}")
            if "error" in res:
                self.stdout.write("  ERROR " + res["error"])
                continue
            self.stdout.write("  " + " | ".join(res["cols"]))
            for r in res["rows"]:
                self.stdout.write("  " + " | ".join("" if v is None else str(v) for v in r))
