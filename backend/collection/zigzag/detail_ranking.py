from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from .collector import ZigzagCnvCollector
from .config import (
    DEFAULT_ACTION_ID,
    DEFAULT_LAYOUT_ID,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
    DEFAULT_MODULE_SLOT_ID,
    DEFAULT_ORDER,
)
from .reviews import (
    DEFAULT_REVIEW_LIMIT,
    DEFAULT_REVIEW_MAX_DELAY,
    DEFAULT_REVIEW_MIN_DELAY,
    ZigzagReviewCollector,
    ZigzagReviewError,
)


DEFAULT_DETAIL_MAX_RANK = 100


def collect_detail_category_ranking(
    *,
    target_url: str | None,
    params: dict,
) -> dict:
    """Collect a plain top-N ranking for one Zigzag detail category."""

    detail_category_id = _resolve_detail_category_id(target_url, params)
    parent_category_id = str(params.get("parent_category_id") or "").strip()
    parent_category_name = str(params.get("parent_category_name") or "").strip()
    detail_category_name = str(params.get("detail_category_name") or "").strip()
    group_name = str(params.get("group_name") or parent_category_name).strip()
    limit = _positive_int(
        params.get("max_rank", DEFAULT_DETAIL_MAX_RANK),
        name="max_rank",
    )
    order = str(params.get("order") or DEFAULT_ORDER).strip()
    collect_reviews = bool(params.get("collect_reviews", False))
    review_limit = ZigzagReviewCollector._validate_limit(
        params.get("review_limit", DEFAULT_REVIEW_LIMIT)
    )

    with ZigzagCnvCollector(
        min_delay=float(params.get("min_delay", DEFAULT_MIN_DELAY)),
        max_delay=float(params.get("max_delay", DEFAULT_MAX_DELAY)),
    ) as collector:
        snapshot = collector.collect_snapshot(
            category_id=detail_category_id,
            layout_id=str(params.get("layout_id") or DEFAULT_LAYOUT_ID),
            action_id=str(params.get("action_id") or DEFAULT_ACTION_ID),
            module_slot_id=str(
                params.get("module_slot_id") or DEFAULT_MODULE_SLOT_ID
            ),
            order=order,
            limit=limit,
        )

    review_errors: list[dict] = []
    if collect_reviews:
        with ZigzagReviewCollector(
            min_delay=float(
                params.get("review_min_delay", DEFAULT_REVIEW_MIN_DELAY)
            ),
            max_delay=float(
                params.get("review_max_delay", DEFAULT_REVIEW_MAX_DELAY)
            ),
        ) as review_collector:
            for product in snapshot.get("products") or []:
                product_id = product.get("product_id")
                if not product_id:
                    continue
                try:
                    product["reviews"] = review_collector.collect_reviews(
                        product_id,
                        limit=review_limit,
                    )
                except ZigzagReviewError as exc:
                    review_errors.append(
                        {
                            "stage": "REVIEW",
                            "source_product_id": str(product_id),
                            "error_type": exc.__class__.__name__,
                            "error_message": str(exc),
                        }
                    )

    collected_at = datetime.now(timezone.utc).isoformat()
    row = {
        **snapshot,
        "category_id": detail_category_id,
        "category_name": detail_category_name,
        "parent_category_id": parent_category_id,
        "parent_category_name": parent_category_name,
        "group_name": group_name,
        "ranking_mode": "DETAIL_CATEGORY",
        "tag_group": "세부 카테고리",
        "tag_attribute": "category",
        "tag_name": detail_category_name,
    }
    collected_count = int(snapshot.get("collected_count") or 0)

    payload = {
        "schema_version": "1.0",
        "source": "ZIGZAG",
        "entity_type": "CNV_CATEGORY",
        "collected_at": collected_at,
        "ranking_mode": "detail_category",
        "cnv": {
            "category_id": detail_category_id,
            "category_name": detail_category_name,
            "parent_category_id": parent_category_id,
            "parent_category_name": parent_category_name,
            "group_name": group_name,
            "order": order,
            "requested_max_rank": limit,
            "tag_snapshot_count": 1,
            "product_occurrence_count": collected_count,
            "unique_product_count": collected_count,
            "group_stats": {
                "detail_category": {
                    "tag_snapshot_count": 1,
                    "product_occurrence_count": collected_count,
                }
            },
            "collect_reviews": collect_reviews,
            "review_limit": review_limit if collect_reviews else 0,
        },
        "groups": {"detail_category": [row]},
        "errors": review_errors,
    }

    return {
        "entity_type": "CNV_CATEGORY",
        "source_entity_id": (
            "zigzag-detail-ranking:"
            f"{parent_category_id or 'unknown'}:{detail_category_id}"
        ),
        "source_url": target_url,
        "collected_at": collected_at,
        "http_status": 200,
        "content_type": "application/json",
        "payload": payload,
        "discovered_count": collected_count,
        "success_count": collected_count,
        "failure_count": len(review_errors),
    }


def _resolve_detail_category_id(target_url: str | None, params: dict) -> str:
    value = params.get("sub_category_id") or params.get("detail_category_id")
    if value not in (None, ""):
        return str(value)

    if target_url:
        query = parse_qs(urlparse(target_url).query)
        values = query.get("sub_category_id")
        if values and values[0]:
            return str(values[0])

    raise ValueError(
        "Zigzag detail category target requires params.sub_category_id "
        "or a target_url sub_category_id query parameter."
    )


def _positive_int(value, *, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed
