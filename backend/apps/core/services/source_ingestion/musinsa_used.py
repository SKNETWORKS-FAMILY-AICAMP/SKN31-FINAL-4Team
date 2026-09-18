from __future__ import annotations

from copy import deepcopy

from collection.musinsa_used_v2.filter_collector import (
    MusinsaUsedFilterCollector,
)
from apps.core.models import RawDocument

from .common import ingest_preview_raw_document


def _build_ranking_context(
    *,
    product: dict,
    payload: dict,
) -> dict:
    """
    기존 MUSINSA_USED 랭킹 context + 신규 FILTER context를 합친다.

    우선순위:
    payload["ranking"] < product["ranking_context"]

    즉 타깃 공통 정보는 payload.ranking에서 받고,
    상품별 rank 같은 값은 product.ranking_context가 덮어쓴다.
    """

    payload_ranking = (
        payload.get("ranking")
        if isinstance(
            payload.get("ranking"),
            dict,
        )
        else {}
    )


    product_context = (
        product.get("ranking_context")
        if isinstance(
            product.get("ranking_context"),
            dict,
        )
        else {}
    )

    context = {
        **payload_ranking,
        **product_context,
    }

    # FILTER 타깃에서 꼭 보존할 필드.
    # 기존 일반 MUSINSA_USED 랭킹에는 없어도 문제 없음.
    filter_keys = (
        "observation_type",
        "filter_type",
        "filter_label",
        "filter_name",
        "filter_parameter",
        "filter_value",
        "category_id",
        "category_name",
        "gender",
        "sort",
        "sort_code",
    )

    for key in filter_keys:
        if (
            context.get(key) in (None, "")
            and payload_ranking.get(key)
            not in (None, "")
        ):
            context[key] = (
                payload_ranking[key]
            )

    # 상품별 rank 보강
    if context.get("rank") is None:
        context["rank"] = (
            product.get("rank")
        )

    # 상품 식별/분석 편의를 위한 보강
    context.setdefault(
        "goods_no",
        product.get("goodsNo")
        or product.get("goods_no")
        or product.get("source_product_id"),
    )

    context.setdefault(
        "product_name",
        product.get("goodsName")
        or product.get("product_name")
        or product.get("name"),
    )

    context.setdefault(
        "product_url",
        product.get("goodsLinkUrl")
        or product.get("product_url"),
    )

    context.setdefault(
        "brand_code",
        product.get("brand"),
    )

    context.setdefault(
        "brand_name",
        product.get("brandName"),
    )

    context.setdefault(
        "normal_price",
        product.get("normalPrice")
        or product.get("normal_price")
        or product.get("regular_price"),
    )

    context.setdefault(
        "price",
        product.get("price")
        or product.get("sale_price")
        or product.get("final_price"),
    )

    context.setdefault(
        "discount_rate",
        (
            product.get("finalDiscount")
            if product.get("finalDiscount")
            is not None
            else (
                product.get("discount_rate")
                if product.get("discount_rate")
                is not None
                else product.get("saleRate")
            )
        ),
    )

    context.setdefault(
        "used_condition_grade",
        product.get("usedConditionGrade")
        or product.get(
            "used_condition_grade"
        ),
    )

    # None은 JSON을 괜히 더럽히므로 제거
    return {
        key: value
        for key, value
        in context.items()
        if value is not None
    }


def _attach_ranking_context_to_preview(
    *,
    preview: dict,
    ranking_context: dict,
) -> dict:
    """
    normalize_musinsa_used_preview() 결과에 FILTER context를 보강한다.

    현재 MUSINSA_USED는 ResaleSnapshot.market_metrics JSONB에
    플랫폼 고유 지표를 저장하므로 ranking_context를 거기에 넣는다.

    preview 구현 버전 차이를 견디도록
    resale_snapshot / snapshot / top-level market_metrics를 모두 지원한다.
    """

    if not isinstance(preview, dict):
        return preview

    result = deepcopy(preview)

    # 1) resale_snapshot 형태
    resale_snapshot = result.get(
        "resale_snapshot"
    )

    if isinstance(
        resale_snapshot,
        dict,
    ):
        metrics = (
            dict(
                resale_snapshot.get(
                    "market_metrics"
                )
            )
            if isinstance(
                resale_snapshot.get(
                    "market_metrics"
                ),
                dict,
            )
            else {}
        )

        existing_context = (
            metrics.get(
                "ranking_context"
            )
            if isinstance(
                metrics.get(
                    "ranking_context"
                ),
                dict,
            )
            else {}
        )

        metrics[
            "ranking_context"
        ] = {
            **existing_context,
            **ranking_context,
        }

        resale_snapshot[
            "market_metrics"
        ] = metrics

    # 2) snapshot 형태
    snapshot = result.get(
        "snapshot"
    )

    if isinstance(
        snapshot,
        dict,
    ):
        # 기존 writer가 snapshot.ranking_context를 읽는 경우
        existing_context = (
            snapshot.get(
                "ranking_context"
            )
            if isinstance(
                snapshot.get(
                    "ranking_context"
                ),
                dict,
            )
            else {}
        )

        snapshot[
            "ranking_context"
        ] = {
            **existing_context,
            **ranking_context,
        }

        # ResaleSnapshot writer가 market_metrics를 읽는 경우
        metrics = (
            dict(
                snapshot.get(
                    "market_metrics"
                )
            )
            if isinstance(
                snapshot.get(
                    "market_metrics"
                ),
                dict,
            )
            else {}
        )

        metric_context = (
            metrics.get(
                "ranking_context"
            )
            if isinstance(
                metrics.get(
                    "ranking_context"
                ),
                dict,
            )
            else {}
        )

        metrics[
            "ranking_context"
        ] = {
            **metric_context,
            **ranking_context,
        }

        snapshot[
            "market_metrics"
        ] = metrics

    # 3) top-level market_metrics 형태
    if isinstance(
        result.get("market_metrics"),
        dict,
    ):
        metrics = dict(
            result["market_metrics"]
        )

        existing_context = (
            metrics.get(
                "ranking_context"
            )
            if isinstance(
                metrics.get(
                    "ranking_context"
                ),
                dict,
            )
            else {}
        )

        metrics[
            "ranking_context"
        ] = {
            **existing_context,
            **ranking_context,
        }

        result[
            "market_metrics"
        ] = metrics

    return result


def ingest_musinsa_used_raw_document(
    *,
    raw_document_id: int,
) -> dict:

    def build_preview(
        product,
        raw_document,
        payload,
    ):
        product = (
            dict(product)
            if isinstance(
                product,
                dict,
            )
            else {}
        )

        payload = (
            payload
            if isinstance(
                payload,
                dict,
            )
            else {}
        )

        ranking_context = (
            _build_ranking_context(
                product=product,
                payload=payload,
            )
        )

        # normalizer가 item["ranking_context"]를 읽는 버전도 지원
        product[
            "ranking_context"
        ] = ranking_context

        preview = (
            MusinsaUsedFilterCollector(
                product,
                observed_at=(
                    raw_document
                    .collected_at
                    .isoformat()
                ),
            )
        )

        return (
            _attach_ranking_context_to_preview(
                preview=preview,
                ranking_context=(
                    ranking_context
                ),
            )
        )

    return ingest_preview_raw_document(
        raw_document_id=(
            raw_document_id
        ),
        source_code="MUSINSA_USED",
        preview_builder=build_preview,
    )


def ingest_pending_musinsa_used_raw_documents(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:

    queryset = (
        RawDocument.objects
        .filter(
            source__code__iexact=(
                "MUSINSA_USED"
            ),
            document_type__in=[
                "RANKING",
                "PRODUCT",
            ],
            normalization_status__in=[
                RawDocument
                .NormalizationStatus
                .PENDING,
                RawDocument
                .NormalizationStatus
                .FAILED,
            ],
        )
        .order_by("id")
    )

    if crawl_run_id is not None:
        queryset = queryset.filter(
            crawl_run_id=crawl_run_id
        )

    if limit is not None:
        queryset = queryset[:limit]

    result = {
        "source":
            "MUSINSA_USED",
        "success":
            0,
        "failed":
            0,
        "products":
            0,
        "errors":
            [],
    }

    for raw_document in queryset:
        try:
            one = (
                ingest_musinsa_used_raw_document(
                    raw_document_id=(
                        raw_document.id
                    )
                )
            )

            result[
                "success"
            ] += 1

            result[
                "products"
            ] += (
                one.get(
                    "products",
                    0,
                )
                or 0
            )

        except Exception as exc:
            result[
                "failed"
            ] += 1

            result[
                "errors"
            ].append({
                "raw_document_id":
                    raw_document.id,
                "error_type":
                    exc.__class__.__name__,
                "error":
                    str(exc),
            })

    return result
