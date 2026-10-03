from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from apps.core.models import CrawlTarget, Source

from .config import (
    CATEGORY_MAP,
    DEFAULT_ACTION_ID,
    DEFAULT_GROUPS,
    DEFAULT_LAYOUT_ID,
    DEFAULT_LIMITS,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
    DEFAULT_MODULE_SLOT_ID,
    DEFAULT_ORDER,
)
from .collector import ZigzagCnvCollector
from .detail_ranking import DEFAULT_DETAIL_MAX_RANK
from .reviews import (
    DEFAULT_REVIEW_LIMIT,
    DEFAULT_REVIEW_MAX_DELAY,
    DEFAULT_REVIEW_MIN_DELAY,
)


def upsert_zigzag_cnv_targets() -> list[CrawlTarget]:
    source = Source.objects.get(code__iexact="zigzag")
    targets: list[CrawlTarget] = []

    for category_name, category_id in CATEGORY_MAP.items():
        target_url = (
            "https://zigzag.kr/pages/srp-clp-category"
            f"?category_id={category_id}"
        )
        target, created = CrawlTarget.objects.update_or_create(
            source=source,
            name=f"zigzag [CNV>{category_name}]",
            defaults={
                "target_type": CrawlTarget.TargetType.RANKING,
                "target_url": target_url,
                "collection_mode": CrawlTarget.CollectionMode.LIVE,
                "params": {
                    "collection_type": "CNV",
                    "category_id": str(category_id),
                    "groups": list(DEFAULT_GROUPS),
                    "limits": dict(DEFAULT_LIMITS),
                    "order": DEFAULT_ORDER,
                    "layout_id": DEFAULT_LAYOUT_ID,
                    "action_id": DEFAULT_ACTION_ID,
                    "module_slot_id": DEFAULT_MODULE_SLOT_ID,
                    "min_delay": DEFAULT_MIN_DELAY,
                    "max_delay": DEFAULT_MAX_DELAY,
                },
                "interval_minutes": 1440,
                "priority": 5,
                "is_active": True,
            },
        )
        targets.append(target)
        print("CREATED" if created else "UPDATED", target.id, target.name)

    return targets


def upsert_zigzag_detail_ranking_target(
    *,
    parent_category_id: str | int,
    parent_category_name: str,
    detail_category_id: str | int,
    detail_category_name: str,
    group_name: str | None = None,
    max_rank: int = DEFAULT_DETAIL_MAX_RANK,
    collect_reviews: bool = True,
    review_limit: int = DEFAULT_REVIEW_LIMIT,
) -> CrawlTarget:
    source = Source.objects.get(code__iexact="zigzag")
    parent_id = str(parent_category_id)
    detail_id = str(detail_category_id)
    group = group_name or parent_category_name
    target_url = (
        "https://zigzag.kr/pages/srp-clp-category"
        f"?category_id={parent_id}&sub_category_id={detail_id}"
    )

    target, created = CrawlTarget.objects.update_or_create(
        source=source,
        name=(
            "ZIGZAG 세부카테고리 랭킹 "
            f"[{group}>{detail_category_name}]"
        ),
        defaults={
            "target_type": CrawlTarget.TargetType.RANKING,
            "target_url": target_url,
            "collection_mode": CrawlTarget.CollectionMode.LIVE,
            "params": {
                "collection_type": "RANKING",
                "ranking_mode": "detail_category",
                "group_name": group,
                "parent_category_id": parent_id,
                "parent_category_name": parent_category_name,
                "sub_category_id": detail_id,
                "detail_category_name": detail_category_name,
                "max_rank": int(max_rank),
                "order": DEFAULT_ORDER,
                "layout_id": DEFAULT_LAYOUT_ID,
                "action_id": DEFAULT_ACTION_ID,
                "module_slot_id": DEFAULT_MODULE_SLOT_ID,
                "min_delay": DEFAULT_MIN_DELAY,
                "max_delay": DEFAULT_MAX_DELAY,
                "collect_reviews": bool(collect_reviews),
                "review_limit": int(review_limit),
                "review_min_delay": DEFAULT_REVIEW_MIN_DELAY,
                "review_max_delay": DEFAULT_REVIEW_MAX_DELAY,
            },
            "interval_minutes": 1440,
            "priority": 5,
            "is_active": True,
        },
    )
    print("CREATED" if created else "UPDATED", target.id, target.name)
    return target


def discover_zigzag_detail_categories() -> list[dict[str, str]]:
    """
    Discover current detail categories from Zigzag GetCnvPage CATEGORY_TAB
    for every parent category configured in CATEGORY_MAP.
    """
    discovered: list[dict[str, str]] = []

    with ZigzagCnvCollector(
        min_delay=DEFAULT_MIN_DELAY,
        max_delay=DEFAULT_MAX_DELAY,
    ) as collector:
        for parent_name, parent_id in CATEGORY_MAP.items():
            print(
                f"[DISCOVERY] {parent_name} "
                f"(category_id={parent_id})"
            )

            rows = collector.discover_detail_categories(
                category_id=str(parent_id),
            )

            if not rows:
                print(
                    f"[DISCOVERY] {parent_name}: "
                    "세부 카테고리 0개"
                )
                continue

            print(
                f"[DISCOVERY] {parent_name}: "
                f"{len(rows)}개 발견"
            )

            for row in rows:
                if not row.get("parent_name"):
                    row["parent_name"] = str(parent_name)

                print(
                    "  - "
                    f"{row['category_id']} "
                    f"{row['category_name']}"
                )
                discovered.append(row)

    return discovered


def upsert_zigzag_detail_ranking_targets(
    categories: Iterable[dict[str, Any]] | None = None,
    *,
    max_rank: int = DEFAULT_DETAIL_MAX_RANK,
    collect_reviews: bool = True,
    review_limit: int = DEFAULT_REVIEW_LIMIT,
) -> list[CrawlTarget]:
    """
    Register detail-category ranking targets.

    If categories is omitted, the current category catalog is discovered
    directly from Zigzag GetCnvPage CATEGORY_TAB.
    """
    if categories is None:
        categories = discover_zigzag_detail_categories()

    targets: list[CrawlTarget] = []

    for category in categories:
        targets.append(
            upsert_zigzag_detail_ranking_target(
                parent_category_id=category["parent_id"],
                parent_category_name=category["parent_name"],
                detail_category_id=category["category_id"],
                detail_category_name=category["category_name"],
                group_name=category.get("group_name"),
                max_rank=max_rank,
                collect_reviews=collect_reviews,
                review_limit=review_limit,
            )
        )

    return targets


def upsert_zigzag_targets(
    *,
    include_cnv: bool = True,
    include_detail_ranking: bool = True,
    max_rank: int = DEFAULT_DETAIL_MAX_RANK,
    collect_reviews: bool = True,
    review_limit: int = DEFAULT_REVIEW_LIMIT,
) -> list[CrawlTarget]:
    """
    Register all Zigzag collection targets.

    1. CNV targets from CATEGORY_MAP
    2. Detail ranking targets discovered from live CATEGORY_TAB
    """
    targets: list[CrawlTarget] = []

    if include_cnv:
        targets.extend(
            upsert_zigzag_cnv_targets()
        )

    if include_detail_ranking:
        targets.extend(
            upsert_zigzag_detail_ranking_targets(
                max_rank=max_rank,
                collect_reviews=collect_reviews,
                review_limit=review_limit,
            )
        )

    print(
        "[ZIGZAG TARGETS] "
        f"total={len(targets)}"
    )

    return targets
