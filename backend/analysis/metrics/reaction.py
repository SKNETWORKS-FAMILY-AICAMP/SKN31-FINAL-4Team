from __future__ import annotations

from datetime import date

from apps.core.models import Source, TermMetricDaily

from .common import (
    METRIC_VERSION,
    build_term_lookup,
    ensure_metric,
    execute_query,
    merge_json,
    normalize_term_key,
    safe_rate,
    source_lookup,
)


def get_latest_comment_metric_date():
    sql = """
    SELECT
        MAX(_product_term_filter
            NULLIF(
                analysis_metadata->>'published_at',
                ''
            )::timestamptz::date
        ) AS latest_date
    FROM analysis.text_document
    WHERE document_type = 'COMMENT'
      AND COALESCE(
            analysis_metadata->>'keep',
            'true'
          ) = 'true'
      AND jsonb_array_length(
            COALESCE(
                analysis_metadata->'mentions',
                '[]'::jsonb
            )
          ) > 0;
    """

    rows = execute_query(sql)
    return rows[0]["latest_date"] if rows else None

def collect_text_reaction_rows(metric_date: date) -> list[dict]:
    """
    analysis.text_document 전체를 대상으로
    term × source × day 집계.

    - 모든 document_type:
      mention/document raw signal 반영

    - COMMENT:
      intent / polarity 반응 지표 반영

    - 같은 문서 안에서 같은 term 중복 mention은 1회 처리

    - 날짜:
      analysis_metadata.published_at 기준
    """

    sql = """
    WITH expanded AS (
        SELECT DISTINCT
            td.id AS document_id,
            td.source_id,
            td.document_type,

            td.analysis_metadata->>'intent'
                AS intent,

            mention->>'term'
                AS term_name,

            mention->>'slot'
                AS slot,

            mention->>'polarity'
                AS polarity,

            NULLIF(
                td.analysis_metadata->>'published_at',
                ''
            )::timestamptz::date
                AS metric_date

        FROM analysis.text_document td

        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(
                td.analysis_metadata->'mentions',
                '[]'::jsonb
            )
        ) AS mention

        WHERE
            COALESCE(
                td.analysis_metadata->>'keep',
                'true'
            ) = 'true'

            AND mention->>'term' IS NOT NULL

            AND BTRIM(
                mention->>'term'
            ) <> ''

            AND NULLIF(
                td.analysis_metadata->>'published_at',
                ''
            ) IS NOT NULL

            AND NULLIF(
                td.analysis_metadata->>'published_at',
                ''
            )::timestamptz::date = %s
    ),

    per_term_doc AS (
        SELECT DISTINCT
            document_id,
            source_id,
            document_type,
            intent,
            term_name,
            polarity

        FROM expanded

        WHERE metric_date = %s
    )

    SELECT
        source_id,
        term_name,

        COUNT(*) AS mention_count,

        COUNT(
            DISTINCT document_id
        ) AS document_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type IN (
                'CONTENT',
                'VIDEO',
                'POST'
            )
        ) AS content_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
        ) AS comment_document_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND intent = 'QUESTION'
        ) AS question_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND intent = 'PURCHASE'
        ) AS purchase_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND intent = 'EXPERIENCE'
        ) AS experience_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND intent = 'PRAISE'
        ) AS praise_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND intent = 'CRITIQUE'
        ) AS critique_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND intent = 'CHITCHAT'
        ) AS chitchat_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND polarity = 'POS'
        ) AS positive_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND polarity = 'NEU'
        ) AS neutral_count,

        COUNT(
            DISTINCT document_id
        ) FILTER (
            WHERE document_type = 'COMMENT'
              AND polarity = 'NEG'
        ) AS negative_count

    FROM per_term_doc

    GROUP BY
        source_id,
        term_name

    ORDER BY
        source_id,
        mention_count DESC;
    """

    return execute_query(
        sql,
        [
            metric_date,
            metric_date,
        ],
    )

def apply_reaction_metrics(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
) -> dict:
    """
    실제 text_document의 mention / COMMENT 반응 데이터를
    source별 TermMetricDaily에 저장한다.
    """
    rows = collect_text_reaction_rows(metric_date)
    terms = build_term_lookup()
    sources = source_lookup()

    saved = 0
    skipped_terms = set()

    for row in rows:
        term_name = row.get("term_name")
        term = terms.get(normalize_term_key(term_name))
        if term is None:
            skipped_terms.add(str(term_name))
            continue

        source = sources.get(row.get("source_id"))

        mention_count = int(row.get("mention_count") or 0)
        document_count = int(row.get("document_count") or 0)
        comment_count = int(row.get("comment_document_count") or 0)

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

        # 이 단계에서는 text/reaction 계층 값만 갱신한다.
        metric.mention_count = mention_count
        metric.document_count = document_count
        metric.content_count = int(row.get("content_count") or 0)

        for field, value in {
            "positive_count": positive_count,
            "neutral_count": neutral_count,
            "negative_count": negative_count,
            "question_count": question_count,
            "purchase_count": purchase_count,
            "experience_count": experience_count,
            "praise_count": praise_count,
            "critique_count": critique_count,
            "chitchat_count": chitchat_count,
            "positive_rate": safe_rate(positive_count, comment_count),
            "neutral_rate": safe_rate(neutral_count, comment_count),
            "negative_rate": safe_rate(negative_count, comment_count),
            "question_rate": safe_rate(question_count, comment_count),
            "purchase_rate": safe_rate(purchase_count, comment_count),
            "experience_rate": safe_rate(experience_count, comment_count),
            "praise_rate": safe_rate(praise_count, comment_count),
            "critique_rate": safe_rate(critique_count, comment_count),
        }.items():
            if hasattr(metric, field):
                setattr(metric, field, value)

        metric.metrics = merge_json(
            metric.metrics,
            {
                "reaction": {
                    "comment_document_count": comment_count,
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
            },
        )

        metric.save()
        saved += 1

    return {
        "saved": saved,
        "skipped_term_count": len(skipped_terms),
        "skipped_terms": sorted(skipped_terms)[:100],
    }
