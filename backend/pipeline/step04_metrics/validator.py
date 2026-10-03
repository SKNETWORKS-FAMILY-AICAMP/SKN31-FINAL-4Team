from __future__ import annotations

from datetime import date
from django.db.models import Q

from apps.core.models import TermMetricDaily
from .common import execute_query
from .config import METRIC_VERSION

RANGE_FIELDS = (
    "percentile", "level", "ma7", "ma28", "momentum", "trend_temperature",
    "positive_rate", "neutral_rate", "negative_rate", "question_rate",
    "purchase_rate", "experience_rate", "praise_rate", "critique_rate",
    "purchase_intent_index",
)


def _upstream_contract_errors(metric_date: date) -> dict:
    sql = """
    WITH reaction_docs AS (
        SELECT td.id, td.document_type, td.analysis_metadata,
            CASE
                WHEN td.document_type = 'COMMENT' THEN
                    (NULLIF(td.analysis_metadata->>'published_at', '')::timestamptz AT TIME ZONE 'Asia/Seoul')::date
                WHEN td.document_type = 'REVIEW' THEN
                    (pr.source_created_at AT TIME ZONE 'Asia/Seoul')::date
                ELSE NULL
            END AS metric_date,
            CASE
                WHEN td.document_type = 'COMMENT' THEN NULLIF(td.analysis_metadata->>'published_at', '') IS NULL
                WHEN td.document_type = 'REVIEW' THEN pr.id IS NULL OR pr.source_created_at IS NULL
                ELSE FALSE
            END AS missing_source_date
        FROM analysis.text_document td
        LEFT JOIN commerce.product_review pr
          ON td.document_type = 'REVIEW'
         AND COALESCE(td.analysis_metadata->>'review_id', '') ~ '^[0-9]+$'
         AND pr.id = (td.analysis_metadata->>'review_id')::bigint
        WHERE td.analysis_status = 'DONE' AND td.document_type IN ('COMMENT', 'REVIEW')
    ),
    mention_checks AS (
        SELECT
            COUNT(*) FILTER (WHERE ttm.intent_code IS NOT NULL AND ttm.intent_code NOT IN
                ('QUESTION','PURCHASE','EXPERIENCE','PRAISE','CRITIQUE','CHITCHAT')) AS invalid_intent,
            COUNT(*) FILTER (WHERE ttm.sentiment_score IS NOT NULL AND ttm.sentiment_score NOT IN (0, 0.5, 1)) AS invalid_sentiment
        FROM analysis.text_term_mention ttm
        JOIN reaction_docs rd ON rd.id = ttm.document_id
        WHERE rd.metric_date = %s
    ),
    comment_evidence AS (
        SELECT COUNT(*) AS invalid_comment_evidence
        FROM reaction_docs rd
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(rd.analysis_metadata->'mentions') = 'array'
                 THEN rd.analysis_metadata->'mentions' ELSE '[]'::jsonb END
        ) AS mention
        WHERE rd.document_type = 'COMMENT' AND rd.metric_date = %s
          AND (mention->>'evidence_status' IS NULL OR mention->>'evidence_status' NOT IN ('EXACT','EXPANDED','LEGACY'))
    ),
    missing_dates AS (
        SELECT COUNT(*) AS missing_source_date FROM reaction_docs WHERE missing_source_date = TRUE
    )
    SELECT mc.invalid_intent, mc.invalid_sentiment, ce.invalid_comment_evidence, md.missing_source_date
    FROM mention_checks mc CROSS JOIN comment_evidence ce CROSS JOIN missing_dates md
    """
    rows = execute_query(sql, [metric_date, metric_date])
    return rows[0] if rows else {}


def validate_term_metrics(metric_date: date, *, metric_version: str = METRIC_VERSION) -> dict:
    qs = TermMetricDaily.objects.filter(metric_date=metric_date, metric_version=metric_version)
    range_errors = {}
    for field in RANGE_FIELDS:
        if not hasattr(TermMetricDaily, field):
            continue
        n = qs.filter(Q(**{f"{field}__lt": 0}) | Q(**{f"{field}__gt": 100})).count()
        if n:
            range_errors[field] = n

    negative_counts = qs.filter(Q(mention_count__lt=0) | Q(document_count__lt=0) | Q(content_count__lt=0)).count()
    source_term_ids = set(qs.filter(source__isnull=False).values_list("term_id", flat=True))
    all_term_ids = set(qs.filter(source__isnull=True).values_list("term_id", flat=True))
    missing_all_terms = sorted(source_term_ids - all_term_ids)

    unavailable_with_score = 0
    for row in qs.filter(source__isnull=False).iterator(chunk_size=2000):
        signals = (((row.metrics or {}).get("normalization") or {}).get("signals") or {})
        unavailable_with_score += sum(
            1 for payload in signals.values()
            if payload.get("available") is False and payload.get("score") is not None
        )

    upstream = _upstream_contract_errors(metric_date)
    upstream_error_count = sum(int(upstream.get(k) or 0) for k in (
        "invalid_intent", "invalid_sentiment", "invalid_comment_evidence", "missing_source_date",
    ))
    ok = (qs.exists() and not range_errors and negative_counts == 0 and not missing_all_terms
          and unavailable_with_score == 0 and upstream_error_count == 0)
    return {
        "metric_date": str(metric_date), "metric_version": metric_version,
        "rows": qs.count(), "source_rows": qs.filter(source__isnull=False).count(),
        "all_rows": qs.filter(source__isnull=True).count(),
        "missing_all_term_ids": missing_all_terms[:100], "range_errors": range_errors,
        "negative_count_rows": negative_counts,
        "unavailable_signal_with_score": unavailable_with_score,
        "upstream_contract_errors": upstream, "ok": ok,
    }
