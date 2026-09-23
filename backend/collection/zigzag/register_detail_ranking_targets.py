from __future__ import annotations

from apps.core.models import CrawlTarget, Source

from .config import (
    DEFAULT_ACTION_ID,
    DEFAULT_LAYOUT_ID,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
    DEFAULT_MODULE_SLOT_ID,
    DEFAULT_ORDER,
)
from .detail_categories import iter_zigzag_detail_categories
from .detail_ranking import DEFAULT_DETAIL_MAX_RANK
from .reviews import (
    DEFAULT_REVIEW_LIMIT,
    DEFAULT_REVIEW_MAX_DELAY,
    DEFAULT_REVIEW_MIN_DELAY,
)


def upsert_zigzag_detail_ranking_targets() -> list[CrawlTarget]:
    """Create one daily top-100 target per Zigzag fashion detail category."""

    source = Source.objects.get(code__iexact="ZIGZAG")
    targets: list[CrawlTarget] = []

    for category in iter_zigzag_detail_categories():
        target_url = (
            "https://zigzag.kr/pages/srp-clp-category"
            f"?category_id={category['parent_id']}"
            f"&sub_category_id={category['category_id']}"
        )
        target, _ = CrawlTarget.objects.update_or_create(
            source=source,
            name=(
                "ZIGZAG 세부카테고리 랭킹 "
                f"[{category['group_name']}>{category['category_name']}]"
            ),
            defaults={
                "target_type": CrawlTarget.TargetType.RANKING,
                "target_url": target_url,
                "collection_mode": CrawlTarget.CollectionMode.LIVE,
                "params": {
                    "ranking_mode": "detail_category",
                    "group_name": category["group_name"],
                    "parent_category_id": str(category["parent_id"]),
                    "parent_category_name": category["parent_name"],
                    "sub_category_id": str(category["category_id"]),
                    "detail_category_name": category["category_name"],
                    "max_rank": DEFAULT_DETAIL_MAX_RANK,
                    "order": DEFAULT_ORDER,
                    "layout_id": DEFAULT_LAYOUT_ID,
                    "action_id": DEFAULT_ACTION_ID,
                    "module_slot_id": DEFAULT_MODULE_SLOT_ID,
                    "min_delay": DEFAULT_MIN_DELAY,
                    "max_delay": DEFAULT_MAX_DELAY,
                    "collect_reviews": True,
                    "review_limit": DEFAULT_REVIEW_LIMIT,
                    "review_min_delay": DEFAULT_REVIEW_MIN_DELAY,
                    "review_max_delay": DEFAULT_REVIEW_MAX_DELAY,
                },
                "interval_minutes": 1440,
                "priority": 5,
                "is_active": True,
            },
        )
        targets.append(target)

    return targets
