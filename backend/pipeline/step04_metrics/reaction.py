from __future__ import annotations

from datetime import date
from decimal import Decimal

from .common import (
    METRIC_VERSION,
    ensure_metric,
    execute_query,
    merge_json,
    safe_rate,
    source_lookup,
)

ALLOWED_INTENTS = (
    "QUESTION",
    "PURCHASE",
    "EXPERIENCE",
    "PRAISE",
    "CRITIQUE",
    "CHITCHAT",
)
REACTION_DOCUMENT_TYPES = ("COMMENT", "REVIEW")


def collect_text_reaction_rows(metric_date: date) -> list[dict]:
    """Aggregate canonical TextTermMention rows for COMMENT and REVIEW.

    Current production contract verified against real FEEDIT rows:
    - COMMENT date: TextDocument.analysis_metadata.published_at -> Asia/Seoul date
    - REVIEW date: ProductReview.source_created_at -> Asia/Seoul date
      (TextDocument.analysis_metadata.review_id links to ProductReview.id)
    - canonical mentions: TextTermMention only; metadata candidates are not metrics
    - COMMENT evidence_status lives in TextDocument.analysis_metadata.mentions[];
      it is upstream validation metadata, not a TextTermMention column
    - sentiment_score uses 0 / 0.5 / 1
    """
    sql = """
    WITH reaction_mentions AS (
        SELECT
            ttm.id AS mention_id,
            ttm.term_id,
            td.id AS document_id,
            td.source_id,
            td.document_type,
            ttm.sentiment_score,
            ttm.intent_code,
            CASE
                WHEN td.document_type = 'COMMENT' THEN
                    (
                        NULLIF(td.analysis_metadata->>'published_at', '')::timestamptz
                        AT TIME ZONE 'Asia/Seoul'
                    )::date
                WHEN td.document_type = 'REVIEW' THEN
                    (pr.source_created_at AT TIME ZONE 'Asia/Seoul')::date
                ELSE NULL
            END AS metric_date
        FROM analysis.text_term_mention ttm
        JOIN analysis.text_document td
          ON td.id = ttm.document_id
        LEFT JOIN commerce.product_review pr
          ON td.document_type = 'REVIEW'
         AND COALESCE(td.analysis_metadata->>'review_id', '') ~ '^[0-9]+$'
         AND pr.id = (td.analysis_metadata->>'review_id')::bigint
        WHERE td.analysis_status = 'DONE'
          AND td.document_type IN ('COMMENT', 'REVIEW')
    )
    SELECT
        source_id,
        term_id,
        COUNT(*) AS mention_count,
        COUNT(DISTINCT document_id) AS document_count,
        COUNT(DISTINCT document_id) AS reaction_document_count,

        COUNT(*) FILTER (WHERE sentiment_score = 1) AS positive_count,
        COUNT(*) FILTER (WHERE sentiment_score = 0.5) AS neutral_count,
        COUNT(*) FILTER (WHERE sentiment_score = 0) AS negative_count,

        COUNT(*) FILTER (WHERE intent_code = 'QUESTION') AS question_count,
        COUNT(*) FILTER (WHERE intent_code = 'PURCHASE') AS purchase_count,
        COUNT(*) FILTER (WHERE intent_code = 'EXPERIENCE') AS experience_count,
        COUNT(*) FILTER (WHERE intent_code = 'PRAISE') AS praise_count,
        COUNT(*) FILTER (WHERE intent_code = 'CRITIQUE') AS critique_count,
        COUNT(*) FILTER (WHERE intent_code = 'CHITCHAT') AS chitchat_count
    FROM reaction_mentions
    WHERE metric_date = %s
    GROUP BY source_id, term_id
    ORDER BY source_id, mention_count DESC
    """
    return execute_query(sql, [metric_date])


def apply_reaction_metrics(metric_date: date, *, metric_version: str = METRIC_VERSION) -> dict:
    rows = collect_text_reaction_rows(metric_date)
    sources = source_lookup()
    saved = 0
    missing_sources = set()

    from apps.core.models import DictionaryTerm
    terms = DictionaryTerm.objects.in_bulk({int(r["term_id"]) for r in rows if r.get("term_id")})

    for row in rows:
        term = terms.get(int(row["term_id"]))
        source = sources.get(row.get("source_id"))
        if term is None:
            continue
        if source is None:
            missing_sources.add(row.get("source_id"))
            continue

        reaction_count = int(row.get("reaction_document_count") or 0)
        positive_count = int(row.get("positive_count") or 0)
        neutral_count = int(row.get("neutral_count") or 0)
        negative_count = int(row.get("negative_count") or 0)
        question_count = int(row.get("question_count") or 0)
        purchase_count = int(row.get("purchase_count") or 0)
        experience_count = int(row.get("experience_count") or 0)
        praise_count = int(row.get("praise_count") or 0)
        critique_count = int(row.get("critique_count") or 0)
        chitchat_count = int(row.get("chitchat_count") or 0)

        metric = ensure_metric(
            term=term,
            source=source,
            metric_date=metric_date,
            metric_version=metric_version,
        )
        metric.mention_count = int(row.get("mention_count") or 0)
        metric.document_count = int(row.get("document_count") or 0)

        metric.positive_count = positive_count
        metric.neutral_count = neutral_count
        metric.negative_count = negative_count
        metric.question_count = question_count
        metric.purchase_count = purchase_count
        metric.experience_count = experience_count
        metric.praise_count = praise_count
        metric.critique_count = critique_count
        metric.chitchat_count = chitchat_count

        metric.positive_rate = safe_rate(positive_count, reaction_count)
        metric.neutral_rate = safe_rate(neutral_count, reaction_count)
        metric.negative_rate = safe_rate(negative_count, reaction_count)
        metric.question_rate = safe_rate(question_count, reaction_count)
        metric.purchase_rate = safe_rate(purchase_count, reaction_count)
        metric.experience_rate = safe_rate(experience_count, reaction_count)
        metric.praise_rate = safe_rate(praise_count, reaction_count)
        metric.critique_rate = safe_rate(critique_count, reaction_count)
        metric.purchase_intent_index = metric.purchase_rate

        sentiment_count = positive_count + neutral_count + negative_count
        metric.sentiment_avg = (
            Decimal(str(round((positive_count + 0.5 * neutral_count) / sentiment_count, 5)))
            if sentiment_count > 0
            else None
        )
        metric.metrics = merge_json(metric.metrics, {
            "reaction": {
                "reaction_document_count": reaction_count,
                "date_contract": {
                    "COMMENT": "text_document.analysis_metadata.published_at",
                    "REVIEW": "product_review.source_created_at",
                    "timezone": "Asia/Seoul",
                },
                "mention_basis": "analysis.text_term_mention",
                "question_count": question_count,
                "purchase_count": purchase_count,
                "experience_count": experience_count,
                "praise_count": praise_count,
                "critique_count": critique_count,
                "chitchat_count": chitchat_count,
                "positive_count": positive_count,
                "neutral_count": neutral_count,
                "negative_count": negative_count,
            }
        })
        metric.save()
        saved += 1

    return {
        "metric_date": str(metric_date),
        "saved": saved,
        "missing_source_ids": sorted(x for x in missing_sources if x is not None),
    }
