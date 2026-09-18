# analysis/metrics/commerce.py

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import (
    Avg,
    Count,
    Max,
    Min,
    Q,
)
from django.utils import timezone

from apps.core.models import (
    DictionaryTerm,
    ProductSourceSnapshot,
    Source,
)

from .common import (
    METRIC_VERSION,
    ensure_metric,
    merge_json,
)


# ============================================================
# DATE
# ============================================================

def _day_bounds(metric_date: date):
    """
    metric_date 하루의 timezone-aware 시작/종료 시각.
    """

    tz = timezone.get_current_timezone()

    start = timezone.make_aware(
        datetime.combine(
            metric_date,
            time.min,
        ),
        tz,
    )

    end = start + timedelta(days=1)

    return start, end


# ============================================================
# HELPERS
# ============================================================

def _to_int(value: Any) -> int:
    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float_or_none(value: Any):
    if value is None:
        return None

    try:
        return round(
            float(value),
            4,
        )
    except (TypeError, ValueError):
        return None


def _snapshot_field_names() -> set[str]:
    """
    ProductSourceSnapshot에 실제 존재하는 필드 목록.
    프로젝트 버전별 필드 차이를 안전하게 처리.
    """

    return {
        field.name
        for field in ProductSourceSnapshot._meta.get_fields()
        if getattr(
            field,
            "concrete",
            False,
        )
    }


# ============================================================
# COMMERCE METRIC
# ============================================================

def apply_commerce_metrics(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
) -> dict:
    """
    ProductTerm 기반 commerce 지표 적재.

    공식 연결 경로:

        DictionaryTerm
              ↑
              │ term
         ProductTerm
              ↑
              │ product_source
        ProductSource
              ↑
              │ product_source
    ProductSourceSnapshot


    즉 상품명 / attributes.tags / 문자열 검색을
    L2 metric 계산에는 사용하지 않는다.
    """

    start, end = _day_bounds(
        metric_date
    )

    snapshot_fields = (
        _snapshot_field_names()
    )

    # --------------------------------------------------------
    # 해당 날짜 전체 snapshot
    # --------------------------------------------------------

    base_qs = (
        ProductSourceSnapshot.objects
        .filter(
            observed_at__gte=start,
            observed_at__lt=end,
        )
        .select_related(
            "product_source",
            "product_source__source",
        )
    )

    # --------------------------------------------------------
    # 실제 snapshot 존재 source만
    # --------------------------------------------------------

    source_ids = (
        base_qs
        .values_list(
            "product_source__source_id",
            flat=True,
        )
        .distinct()
    )

    sources = (
        Source.objects
        .filter(
            id__in=source_ids
        )
        .order_by("id")
    )

    # --------------------------------------------------------
    # 활성 DictionaryTerm
    # --------------------------------------------------------

    terms = (
        DictionaryTerm.objects
        .filter(
            status="ACTIVE"
        )
        .order_by("id")
    )

    saved = 0
    skipped = 0

    source_results: dict[str, int] = {}

    # ========================================================
    # SOURCE LOOP
    # ========================================================

    for source in sources:

        source_qs = (
            base_qs
            .filter(
                product_source__source=source
            )
        )

        source_saved = 0

        # ====================================================
        # TERM LOOP
        # ====================================================

        for term in terms.iterator(
            chunk_size=500
        ):

            # ------------------------------------------------
            # ★ 핵심
            #
            # ProductSourceSnapshot
            #   -> product_source
            #   -> product_terms
            #   -> term
            #
            # Product는 전혀 거치지 않음.
            # ------------------------------------------------

            qs = (
                source_qs
                .filter(
                    product_source__product_terms__term_id=term.id
                )
                .distinct()
            )

            # 해당 term 상품이 없으면 skip
            if not qs.exists():
                continue

            # ------------------------------------------------
            # 기본 aggregation
            # ------------------------------------------------

            aggregate_kwargs = {
                "snapshot_count": Count(
                    "id",
                    distinct=True,
                ),

                "product_count": Count(
                    "product_source_id",
                    distinct=True,
                ),

                "ranked_product_count": Count(
                    "product_source_id",
                    filter=Q(
                        rank_position__isnull=False
                    ),
                    distinct=True,
                ),

                "best_rank": Min(
                    "rank_position"
                ),

                "avg_rank": Avg(
                    "rank_position"
                ),

                "avg_rating": Avg(
                    "rating"
                ),

                "max_review_count": Max(
                    "review_count"
                ),

                "max_like_count": Max(
                    "like_count"
                ),
            }

            # ------------------------------------------------
            # 모델에 존재하는 경우에만 추가
            # ------------------------------------------------

            if "view_count" in snapshot_fields:
                aggregate_kwargs[
                    "max_view_count"
                ] = Max(
                    "view_count"
                )

            if "sales_count" in snapshot_fields:
                aggregate_kwargs[
                    "max_sales_count"
                ] = Max(
                    "sales_count"
                )

            agg = qs.aggregate(
                **aggregate_kwargs
            )

            # ------------------------------------------------
            # JSON commerce payload
            # ------------------------------------------------

            commerce_data = {
                "snapshot_count": _to_int(
                    agg.get(
                        "snapshot_count"
                    )
                ),

                "product_count": _to_int(
                    agg.get(
                        "product_count"
                    )
                ),

                "ranked_product_count": _to_int(
                    agg.get(
                        "ranked_product_count"
                    )
                ),

                "best_rank": (
                    _to_int(
                        agg.get(
                            "best_rank"
                        )
                    )
                    if agg.get(
                        "best_rank"
                    ) is not None
                    else None
                ),

                "avg_rank": _to_float_or_none(
                    agg.get(
                        "avg_rank"
                    )
                ),

                "avg_rating": _to_float_or_none(
                    agg.get(
                        "avg_rating"
                    )
                ),

                "max_review_count": _to_int(
                    agg.get(
                        "max_review_count"
                    )
                ),

                "max_like_count": _to_int(
                    agg.get(
                        "max_like_count"
                    )
                ),
            }

            if (
                "max_view_count"
                in agg
            ):
                commerce_data[
                    "max_view_count"
                ] = _to_int(
                    agg.get(
                        "max_view_count"
                    )
                )

            if (
                "max_sales_count"
                in agg
            ):
                commerce_data[
                    "max_sales_count"
                ] = _to_int(
                    agg.get(
                        "max_sales_count"
                    )
                )

            # ------------------------------------------------
            # TermMetricDaily
            # ------------------------------------------------

            metric = ensure_metric(
                term=term,
                source=source,
                metric_date=metric_date,
                metric_version=metric_version,
            )

            metric.metrics = merge_json(
                metric.metrics,
                {
                    "commerce": (
                        commerce_data
                    )
                },
            )

            metric.save(
                update_fields=[
                    "metrics",
                    "updated_at",
                ]
            )

            saved += 1
            source_saved += 1

        source_results[
            source.code
        ] = source_saved

    return {
        "metric_date": str(
            metric_date
        ),
        "saved": saved,
        "skipped": skipped,
        "sources": source_results,
    }