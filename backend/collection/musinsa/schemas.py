from __future__ import annotations

from datetime import datetime, timezone

from .constants import SCHEMA_VERSION, SOURCE_CODE


def build_raw_record(*, product_url: str, parsed: dict, ranking_context: dict | None = None) -> dict:
    product = parsed.get("product") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_CODE,
        "entity_type": "PRODUCT",
        "external_id": str(product.get("goods_no")) if product.get("goods_no") is not None else None,
        "source_url": product_url,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "brand": parsed.get("brand"),
        "product": product,
        "snapshot": parsed.get("snapshot"),
        "options": parsed.get("options"),
        "reviews": parsed.get("reviews"),
        "ranking_context": ranking_context,
        "meta": parsed.get("meta") or {},
    }
