from __future__ import annotations

from apps.core.models import CrawlTarget, Source

from .constants import DEFAULT_MAX_RANK, DEFAULT_REVIEW_LIMIT, RANKING_PAGE_URL
from .detail_categories import (
    build_ably_detail_target_name,
    iter_ably_detail_categories,
)


def upsert_ably_detail_ranking_targets(
    *,
    source: Source | None = None,
) -> list[CrawlTarget]:
    """Create one daily top-100 target per ABLY fashion detail category."""

    source = source or Source.objects.get(code__iexact="ABLY")
    targets: list[CrawlTarget] = []

    for category in iter_ably_detail_categories():
        target, _ = CrawlTarget.objects.update_or_create(
            source=source,
            name=build_ably_detail_target_name(category),
            defaults={
                "target_type": CrawlTarget.TargetType.RANKING,
                "target_url": RANKING_PAGE_URL,
                "collection_mode": CrawlTarget.CollectionMode.LIVE,
                "params": {
                    "ranking_mode": "detail_category",
                    "filter": "best",
                    "period": "daily",
                    "market_type_sno": 1,
                    "category_sno": category["category_id"],
                    "parent_category_sno": category["parent_id"],
                    "parent_category_name": category["parent_name"],
                    "detail_category_name": category["category_name"],
                    "max_rank": DEFAULT_MAX_RANK,
                    "collect_reviews": True,
                    "review_limit": DEFAULT_REVIEW_LIMIT,
                },
                "interval_minutes": 1440,
                "priority": 5,
                "is_active": True,
            },
        )
        targets.append(target)

    return targets
