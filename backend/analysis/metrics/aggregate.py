from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from apps.core.models import (
    Source,
    TermMetricDaily,
)

from .common import (
    METRIC_VERSION,
    SOURCE_WEIGHTS,
    ensure_metric,
    log_compress,
    merge_json,
    momentum_score,
    moving_average,
    percentile_rank,
    safe_rate,
    trend_temperature_score,
)


# ============================================================
# SOURCE RAW SIGNAL
# ============================================================

def _commerce_signal(metrics: dict) -> float:
    row = (metrics or {}).get("commerce") or {}

    product_count = float(
        row.get("product_count") or 0
    )

    ranked = float(
        row.get("ranked_product_count") or 0
    )

    likes = float(
        row.get("max_like_count") or 0
    )

    reviews = float(
        row.get("max_review_count") or 0
    )

    return (
        0.60 * product_count
        + 0.80 * ranked
        + 0.10 * log_compress(likes)
        + 0.10 * log_compress(reviews)
    )


def _content_signal(metrics: dict) -> float:
    row = (metrics or {}).get("content") or {}

    content_count = float(
        row.get("content_count") or 0
    )

    creator_count = float(
        row.get("creator_count") or 0
    )

    views = float(
        row.get("max_view_count") or 0
    )

    likes = float(
        row.get("max_like_count") or 0
    )

    comments = float(
        row.get("max_comment_count") or 0
    )

    return (
        1.00 * content_count
        + 1.50 * creator_count
        + 0.10 * log_compress(views)
        + 0.20 * log_compress(likes)
        + 0.20 * log_compress(comments)
    )


def compute_source_raw(
    metric: TermMetricDaily,
) -> float:

    mention = float(
        metric.mention_count or 0
    )

    return round(
        mention
        + _commerce_signal(
            metric.metrics
        )
        + _content_signal(
            metric.metrics
        ),
        4,
    )


# ============================================================
# SOURCE NORMALIZATION
# ============================================================

@transaction.atomic
def compute_source_raw_and_percentiles(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
) -> dict:

    sources = Source.objects.all()

    updated = 0

    for source in sources:

        rows = list(
            TermMetricDaily.objects.filter(
                source=source,
                metric_date=metric_date,
                metric_version=metric_version,
            )
        )

        if not rows:
            continue

        values = {}

        # raw / log
        for metric in rows:

            raw = compute_source_raw(
                metric
            )

            log_value = log_compress(
                raw
            )

            metric.raw_count = Decimal(
                str(raw)
            )

            metric.log_count = Decimal(
                str(
                    round(
                        log_value,
                        6,
                    )
                )
            )

            metric.save(
                update_fields=[
                    "raw_count",
                    "log_count",
                    "updated_at",
                ]
            )

            values[
                metric.id
            ] = log_value

        # percentile
        percentiles = percentile_rank(
            values
        )

        for metric in rows:

            pct = percentiles.get(
                metric.id,
                0.0,
            )

            metric.percentile = Decimal(
                str(pct)
            )

            metric.level = Decimal(
                str(pct)
            )

            metric.save(
                update_fields=[
                    "percentile",
                    "level",
                    "updated_at",
                ]
            )

            updated += 1

    return {
        "updated": updated,
    }


# ============================================================
# ALL SOURCES
# ============================================================

@transaction.atomic
def aggregate_all_sources(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
) -> dict:

    source_rows = (
        TermMetricDaily.objects
        .filter(
            metric_date=metric_date,
            metric_version=metric_version,
            source__isnull=False,
        )
        .select_related(
            "source",
            "term",
        )
    )

    grouped = {}

    for row in source_rows:

        grouped.setdefault(
            row.term_id,
            [],
        ).append(
            row
        )

    saved = 0

    for term_id, rows in grouped.items():

        term = rows[0].term

        all_row = ensure_metric(
            term=term,
            source=None,
            metric_date=metric_date,
            metric_version=metric_version,
        )

        # --------------------------------------------
        # COUNT FIELDS
        # --------------------------------------------

        count_fields = [
            "mention_count",
            "document_count",
            "content_count",
            "creator_count",

            "positive_count",
            "neutral_count",
            "negative_count",

            "question_count",
            "purchase_count",
            "experience_count",
            "praise_count",
            "critique_count",
            "chitchat_count",
        ]

        for field in count_fields:

            if not hasattr(
                all_row,
                field,
            ):
                continue

            value = sum(
                int(
                    getattr(
                        row,
                        field,
                        0,
                    )
                    or 0
                )
                for row in rows
            )

            setattr(
                all_row,
                field,
                value,
            )

        # --------------------------------------------
        # RAW
        # --------------------------------------------

        raw_total = sum(
            float(
                row.raw_count or 0
            )
            for row in rows
        )

        all_row.raw_count = Decimal(
            str(
                round(
                    raw_total,
                    4,
                )
            )
        )

        all_row.log_count = Decimal(
            str(
                round(
                    log_compress(
                        raw_total
                    ),
                    6,
                )
            )
        )

        # --------------------------------------------
        # SOURCE PERCENTILES
        # --------------------------------------------

        source_percentiles = {
            row.source.code:
                float(
                    row.percentile or 0
                )

            for row in rows

            if row.source_id
        }

        level = 0.0

        for code, weight in (
            SOURCE_WEIGHTS.items()
        ):

            level += (
                float(weight)
                * float(
                    source_percentiles.get(
                        code,
                        0,
                    )
                )
            )

        level = max(
            0.0,
            min(
                100.0,
                level,
            ),
        )

        all_row.level = Decimal(
            str(
                round(
                    level,
                    4,
                )
            )
        )

        all_row.percentile = None

        # --------------------------------------------
        # COMMENT RATE
        # --------------------------------------------

        comment_count = sum(
            int(
                (
                    (
                        row.metrics
                        or {}
                    )
                    .get(
                        "reaction",
                        {},
                    )
                    .get(
                        "comment_document_count",
                        0,
                    )
                )
                or 0
            )
            for row in rows
        )

        rate_fields = (
            (
                "positive_rate",
                "positive_count",
            ),
            (
                "neutral_rate",
                "neutral_count",
            ),
            (
                "negative_rate",
                "negative_count",
            ),
            (
                "question_rate",
                "question_count",
            ),
            (
                "purchase_rate",
                "purchase_count",
            ),
            (
                "experience_rate",
                "experience_count",
            ),
            (
                "praise_rate",
                "praise_count",
            ),
            (
                "critique_rate",
                "critique_count",
            ),
        )

        for (
            rate_field,
            count_field,
        ) in rate_fields:

            if not (
                hasattr(
                    all_row,
                    rate_field,
                )
                and hasattr(
                    all_row,
                    count_field,
                )
            ):
                continue

            setattr(
                all_row,
                rate_field,
                safe_rate(
                    getattr(
                        all_row,
                        count_field,
                        0,
                    ),
                    comment_count,
                ),
            )

        # --------------------------------------------
        # METADATA
        # --------------------------------------------

        all_row.metrics = merge_json(
            all_row.metrics,
            {
                "all_sources": {
                    "source_count": len(
                        rows
                    ),

                    "source_percentiles":
                        source_percentiles,

                    "comment_document_count":
                        comment_count,

                    "source_raw": {
                        row.source.code:
                            float(
                                row.raw_count
                                or 0
                            )

                        for row in rows

                        if row.source_id
                    },
                }
            },
        )

        all_row.save()

        saved += 1

    return {
        "saved": saved,
    }


# ============================================================
# TEMPORAL
# ============================================================

@transaction.atomic
def compute_temporal_metrics(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
) -> dict:

    current_rows = list(
        TermMetricDaily.objects
        .filter(
            metric_date=metric_date,
            metric_version=metric_version,
        )
        .select_related(
            "source"
        )
    )

    updated = 0

    for current in current_rows:

        history = list(
            TermMetricDaily.objects
            .filter(
                term_id=current.term_id,
                source_id=current.source_id,
                metric_version=metric_version,

                metric_date__lte=(
                    metric_date
                ),

                metric_date__gte=(
                    metric_date
                    - timedelta(
                        days=27
                    )
                ),
            )
            .order_by(
                "metric_date"
            )
            .values_list(
                "raw_count",
                flat=True,
            )
        )

        ma7 = moving_average(
            history,
            7,
        )

        ma28 = moving_average(
            history,
            28,
        )

        momentum = momentum_score(
            ma7,
            ma28,
        )

        temperature = (
            trend_temperature_score(
                float(
                    current.level
                    or 0
                ),
                momentum,
            )
        )

        current.ma7 = Decimal(
            str(
                round(
                    ma7,
                    4,
                )
            )
        )

        current.ma28 = Decimal(
            str(
                round(
                    ma28,
                    4,
                )
            )
        )

        current.momentum = Decimal(
            str(
                round(
                    momentum,
                    4,
                )
            )
        )

        current.trend_temperature = (
            Decimal(
                str(
                    round(
                        temperature,
                        4,
                    )
                )
            )
        )

        current.metrics = merge_json(
            current.metrics,
            {
                "trend": {
                    "ma7": round(
                        ma7,
                        4,
                    ),
                    "ma28": round(
                        ma28,
                        4,
                    ),
                    "momentum": round(
                        momentum,
                        4,
                    ),
                    "trend_temperature": round(
                        temperature,
                        4,
                    ),
                }
            },
        )

        current.save()

        updated += 1

    return {
        "updated": updated,
    }




def attach_search_signal(
    *,
    metric_date,
    metric_version,
    search_metric_version="feedit-search-v1",
):
    from apps.core.models import (
        TermMetricDaily,
        TermSearchMetricMonthly,
    )

    metric_month = metric_date.replace(day=1)

    rows = (
        TermSearchMetricMonthly.objects
        .filter(
            metric_month=metric_month,
            metric_version=search_metric_version,
        )
        .select_related(
            "term",
            "source",
        )
    )

    by_term = {}

    for row in rows:
        item = by_term.setdefault(
            row.term_id,
            {},
        )

        code = (
            row.source.code
            or ""
        ).lower()

        item[code] = {
            "search_volume": int(
                row.search_volume or 0
            ),
            "percentile": (
                float(row.percentile)
                if row.percentile is not None
                else None
            ),
        }

    updated = 0

    all_rows = (
        TermMetricDaily.objects
        .filter(
            metric_date=metric_date,
            metric_version=metric_version,
            source__isnull=True,
        )
    )

    for metric in all_rows.iterator(
        chunk_size=500
    ):
        platforms = by_term.get(
            metric.term_id
        )

        if not platforms:
            continue

        pct_values = [
            v["percentile"]
            for v in platforms.values()
            if v.get("percentile") is not None
        ]

        score = (
            round(
                sum(pct_values)
                / len(pct_values),
                4,
            )
            if pct_values
            else None
        )

        payload = {
            "metric_month": str(
                metric_month
            ),
            "platforms": platforms,
            "score": score,
        }

        metric.metrics = merge_json(
            metric.metrics,
            {
                "search": payload,
            },
        )

        metric.save(
            update_fields=[
                "metrics",
                "updated_at",
            ]
        )

        updated += 1

    return {
        "updated": updated,
        "metric_month": str(
            metric_month
        ),
    }


# ============================================================
# FINAL SIGNAL SCORE
# ============================================================

SIGNAL_WEIGHTS = {
    "commerce": 0.35,
    "content": 0.30,
    "reaction": 0.20,
    "search": 0.15,
}


def _weighted_available(
    values: dict,
    weights: dict,
):
    available = {
        key: float(value)
        for key, value in values.items()
        if value is not None
    }

    if not available:
        return None

    total_weight = sum(
        weights[key]
        for key in available
    )

    if total_weight <= 0:
        return None

    value = sum(
        available[key]
        * weights[key]
        for key in available
    ) / total_weight

    return round(
        max(
            0.0,
            min(
                100.0,
                value,
            ),
        ),
        4,
    )


def calculate_final_signal_scores(
    *,
    metric_date,
    metric_version,
):
    """
    source=NULL ALL row 기준.

    현재 v1:
    - commerce: source percentile 평균
    - content: source percentile 평균
    - reaction: mention/intent/polarity 기반
    - search: Google/Naver percentile 평균
    """

    from apps.core.models import TermMetricDaily

    rows = (
        TermMetricDaily.objects
        .filter(
            metric_date=metric_date,
            metric_version=metric_version,
            source__isnull=True,
        )
    )

    updated = 0

    for metric in rows.iterator(
        chunk_size=500
    ):
        metrics = dict(
            metric.metrics or {}
        )

        # ----------------------------------------------------
        # SOURCE 기반 점수
        # ----------------------------------------------------

        all_source_data = (
            metrics.get(
                "all_sources",
                {}
            )
        )

        source_percentiles = (
            all_source_data.get(
                "source_percentiles",
                {}
            )
        )

        commerce_values = []
        content_values = []

        for code, pct in (
            source_percentiles.items()
        ):
            code_lower = (
                code or ""
            ).lower()

            if code_lower in {
                "musinsa",
                "zigzag",
                "ably",
                "kream",
                "musinsa_used",
            }:
                commerce_values.append(
                    float(pct)
                )

            elif code_lower in {
                "youtube",
            }:
                content_values.append(
                    float(pct)
                )

        commerce_score = (
            round(
                sum(commerce_values)
                / len(commerce_values),
                4,
            )
            if commerce_values
            else None
        )

        content_score = (
            round(
                sum(content_values)
                / len(content_values),
                4,
            )
            if content_values
            else None
        )

        # ----------------------------------------------------
        # REACTION
        # ----------------------------------------------------

        reaction_data = (
            metrics.get(
                "reaction",
                {}
            )
        )

        reaction_parts = []

        mention_count = float(
            metric.mention_count or 0
        )

        if mention_count > 0:
            # mention volume 자체는 source percentile로 이미 어느 정도
            # 반영되므로 여기서는 반응률 중심
            pass

        for field in (
            "purchase_rate",
            "question_rate",
            "positive_rate",
        ):
            value = getattr(
                metric,
                field,
                None,
            )

            if value is not None:
                reaction_parts.append(
                    float(value) * 100
                )

        reaction_score = (
            round(
                sum(reaction_parts)
                / len(reaction_parts),
                4,
            )
            if reaction_parts
            else None
        )

        # negative 감점
        negative_rate = getattr(
            metric,
            "negative_rate",
            None,
        )

        if (
            reaction_score is not None
            and negative_rate is not None
        ):
            reaction_score = max(
                0.0,
                reaction_score
                - float(
                    negative_rate
                )
                * 100
                * 0.15,
            )

        # ----------------------------------------------------
        # SEARCH
        # ----------------------------------------------------

        search_score = (
            metrics
            .get(
                "search",
                {}
            )
            .get(
                "score"
            )
        )

        # ----------------------------------------------------
        # FINAL LEVEL
        # ----------------------------------------------------

        final_level = (
            _weighted_available(
                {
                    "commerce": commerce_score,
                    "content": content_score,
                    "reaction": reaction_score,
                    "search": search_score,
                },
                SIGNAL_WEIGHTS,
            )
        )

        metrics["signals"] = {
            "commerce": {
                "score": commerce_score,
            },
            "content": {
                "score": content_score,
            },
            "reaction": {
                "score": reaction_score,
            },
            "search": {
                "score": search_score,
            },
        }

        metrics[
            "level_components"
        ] = {
            "weights": SIGNAL_WEIGHTS,
            "level": final_level,
        }

        metric.metrics = metrics

        if final_level is not None:
            metric.level = Decimal(
                str(final_level)
            )

        metric.save(
            update_fields=[
                "metrics",
                "level",
                "updated_at",
            ]
        )

        updated += 1

    return {
        "updated": updated,
    }