# analysis/metrics/pipeline.py

from __future__ import annotations

from datetime import date, timedelta

from .common import METRIC_VERSION

from .reaction import (
    apply_reaction_metrics,
)

from .commerce import (
    apply_commerce_metrics,
)

from .content import (
    apply_content_metrics,
)

from .aggregate import (
    aggregate_all_sources,
    attach_search_signal,
    calculate_final_signal_scores,
    compute_source_raw_and_percentiles,
    compute_temporal_metrics,
)


# ============================================================
# SINGLE DAY PIPELINE
# ============================================================

def run_term_metric_pipeline(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
    reaction: bool = True,
    commerce: bool = True,
    content: bool = True,
    search: bool = False,
) -> dict:
    """
    FEEDIT L2 Term Metric Pipeline

    순서
    ----------------------------------------------------------
    1. Reaction
    2. Commerce
    3. Content
    4. Source raw / percentile
    5. ALL source aggregate
    6. Monthly search attach
    7. Final signal / level
    8. Temporal metrics
       - MA7
       - MA28
       - Momentum
       - Trend Temperature
    ----------------------------------------------------------
    """

    result = {
        "metric_date": str(metric_date),
        "metric_version": metric_version,
    }

    # ========================================================
    # 1. REACTION
    # ========================================================

    if reaction:
        result["reaction"] = (
            apply_reaction_metrics(
                metric_date=metric_date,
                metric_version=metric_version,
            )
        )
    else:
        result["reaction"] = {
            "skipped": True,
        }

    # ========================================================
    # 2. COMMERCE
    # ========================================================

    if commerce:
        result["commerce"] = (
            apply_commerce_metrics(
                metric_date=metric_date,
                metric_version=metric_version,
            )
        )
    else:
        result["commerce"] = {
            "skipped": True,
        }

    # ========================================================
    # 3. CONTENT
    # ========================================================

    if content:
        result["content"] = (
            apply_content_metrics(
                metric_date=metric_date,
                metric_version=metric_version,
            )
        )
    else:
        result["content"] = {
            "skipped": True,
        }

    # ========================================================
    # 4. SOURCE RAW / PERCENTILE
    # ========================================================

    result["source_normalize"] = (
        compute_source_raw_and_percentiles(
            metric_date=metric_date,
            metric_version=metric_version,
        )
    )

    # ========================================================
    # 5. ALL SOURCE AGGREGATE
    # ========================================================

    result["all_sources"] = (
        aggregate_all_sources(
            metric_date=metric_date,
            metric_version=metric_version,
        )
    )

    # ========================================================
    # 6. SEARCH
    # ========================================================

    if search:
        result["search"] = (
            attach_search_signal(
                metric_date=metric_date,
                metric_version=metric_version,
            )
        )
    else:
        result["search"] = {
            "skipped": True,
        }

    # ========================================================
    # 7. FINAL SIGNAL / LEVEL
    # ========================================================

    result["signals"] = (
        calculate_final_signal_scores(
            metric_date=metric_date,
            metric_version=metric_version,
        )
    )

    # ========================================================
    # 8. TEMPORAL
    # ========================================================

    result["temporal"] = (
        compute_temporal_metrics(
            metric_date=metric_date,
            metric_version=metric_version,
        )
    )

    return result


# ============================================================
# DATE RANGE PIPELINE
# ============================================================

def run_term_metric_range(
    start_date: date,
    end_date: date,
    *,
    metric_version: str = METRIC_VERSION,
    reaction: bool = True,
    commerce: bool = True,
    content: bool = True,
    search: bool = False,
) -> list[dict]:
    """
    과거 날짜 순서대로 metric pipeline 실행.

    MA7 / MA28 / Momentum 계산 때문에
    반드시 과거 -> 현재 순으로 실행.
    """

    if start_date > end_date:
        raise ValueError(
            "start_date must be <= end_date"
        )

    results = []

    current = start_date

    while current <= end_date:

        result = run_term_metric_pipeline(
            metric_date=current,
            metric_version=metric_version,
            reaction=reaction,
            commerce=commerce,
            content=content,
            search=search,
        )

        results.append(
            result
        )

        current += timedelta(days=1)

    return results