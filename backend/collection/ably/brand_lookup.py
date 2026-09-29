from __future__ import annotations

import logging

from .exceptions import AblyCollectError


logger = logging.getLogger(__name__)


def brand_name_from_home(payload: dict, brand_sno: str | int) -> str | None:
    """Read a brand name only from a profile that confirms the requested ID."""
    analytics = (payload.get("logging") or {}).get("analytics") or {}
    if str(analytics.get("BRAND_SNO")) != str(brand_sno):
        return None

    for component in payload.get("components") or []:
        if (component.get("type") or {}).get("item_list") != "PROFILE_INFO":
            continue
        for entry in (component.get("entity") or {}).get("item_list") or []:
            name = (entry.get("item") or {}).get("main_name")
            if isinstance(name, str) and name.strip():
                return name.strip()

    title = payload.get("title")
    return title.strip() if isinstance(title, str) and title.strip() else None


def enrich_missing_brand_names(products: list[dict], client) -> dict[str, int]:
    """Look up each missing brand name once per ranking collection."""
    cache: dict[str, str | None] = {}
    failed = 0
    enriched = 0
    for product in products:
        brand = product.get("brand") or {}
        brand_sno = brand.get("source_brand_id")
        if not brand_sno or brand.get("name"):
            continue
        brand_sno = str(brand_sno)
        if brand_sno not in cache:
            try:
                cache[brand_sno] = brand_name_from_home(
                    client.get_brand_home(brand_sno), brand_sno
                )
            except (AblyCollectError, ValueError) as exc:
                logger.warning(
                    "ABLY brand name lookup failed. brand_sno=%s error_type=%s",
                    brand_sno,
                    exc.__class__.__name__,
                )
                cache[brand_sno] = None
                failed += 1
        if cache[brand_sno]:
            brand["name"] = cache[brand_sno]
            enriched += 1
    return {
        "requested": len(cache),
        "enriched_products": enriched,
        "unresolved": sum(name is None for name in cache.values()),
        "failed": failed,
    }
