from __future__ import annotations

from apps.core.models import CrawlTarget, Source

from .constants import BRAND_DEPARTMENT_CATEGORIES, COMPONENT_LIST_API_URL


def upsert_ably_store_profile_target() -> CrawlTarget:
    """Register the ABLY brand-department enrichment on the daily scheduler."""

    source = Source.objects.get(code__iexact="ABLY")
    target, _ = CrawlTarget.objects.update_or_create(
        source=source,
        name="ABLY 브랜드관 STORE 프로필 DAILY",
        defaults={
            "target_type": CrawlTarget.TargetType.STORE,
            "target_url": COMPONENT_LIST_API_URL,
            "collection_mode": CrawlTarget.CollectionMode.LIVE,
            "params": {"category_snos": list(BRAND_DEPARTMENT_CATEGORIES)},
            "interval_minutes": 1440,
            "priority": 5,
            "is_active": True,
        },
    )
    return target

