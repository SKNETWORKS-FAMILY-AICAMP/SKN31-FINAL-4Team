from __future__ import annotations

from collection.common.normalization import (
    TABLE_BRAND_SOURCE,
    TABLE_CATEGORY_SOURCE,
    TABLE_PRODUCT_SOURCE,
    TABLE_PRODUCT_SOURCE_SNAPSHOT,
    clean_text,
    gender_scope,
    source_key_text,
)


def _present(values: dict) -> dict:
    return {key: value for key, value in values.items() if value is not None}


def _name_fallback(prefix: str, name) -> str | None:
    source_key = source_key_text(name)
    return f"{prefix}:{source_key}" if source_key else None


def normalize_ably_preview(product: dict, ranking_context: dict | None = None) -> dict:
    brand = product.get("brand") or {}
    category = product.get("category") or {}
    snapshot = product.get("snapshot") or {}
    ranking = product.get("ranking") or {}
    images = product.get("images") or {}
    attributes = dict(product.get("attributes") or {})
    scope = dict(ranking_context or {})
    scope_name = scope.get("filter") or scope.get("period")
    market = product.get("market")
    if not isinstance(market, dict) or not any(value is not None for value in market.values()):
        market = None
    attributes.update({
        "sku_code": product.get("sku_code"),
        "market": market,
    })
    source_brand = brand if brand.get("source_brand_id") or brand.get("name") else {}
    source_brand_kind = "BRAND"
    if not source_brand and market:
        source_brand = {
            "source_brand_id": (
                f"MARKET:{market.get('source_market_id')}"
                if market.get("source_market_id") is not None
                else None
            ),
            "name": market.get("name"),
        }
        source_brand_kind = "MARKET_FALLBACK"
    if source_brand and source_brand.get("source_brand_id") is None:
        prefix = "MARKET_NAME" if source_brand_kind == "MARKET_FALLBACK" else "NAME"
        source_brand = {
            **source_brand,
            "source_brand_id": _name_fallback(prefix, source_brand.get("name")),
        }
    source_category_id = category.get("source_category_id")
    source_category_name = category.get("name")
    category_kind = "SOURCE_CATEGORY"
    if source_category_id is None and category.get("standard_category_id") is not None:
        source_category_id = f"STANDARD:{category['standard_category_id']}"
        source_category_name = category.get("standard_category_name") or source_category_name
        category_kind = "STANDARD_CATEGORY_FALLBACK"
    stock_status = None
    if snapshot.get("is_sold_out") is True:
        stock_status = "SOLD_OUT"
    elif snapshot.get("is_buyable") is True:
        stock_status = "AVAILABLE"

    platform_metrics = _present({
        "sales_count": snapshot.get("sales_count"),
        "positive_review_count": snapshot.get("positive_review_count"),
        "positive_review_rate": snapshot.get("positive_review_rate"),
        "market": market,
    })
    warnings = []
    if not product.get("source_product_id"):
        warnings.append("source_product_id is missing")
    if not category.get("source_category_id"):
        if source_category_id is None:
            warnings.append("source category is missing")
    if not source_brand.get("source_brand_id"):
        warnings.append("source brand or market is missing")

    return {
        "source": "ABLY",
        "db_write": False,
        "db_write_operations": 0,
        "targets": {
            "brand_source": {
                "_table": TABLE_BRAND_SOURCE,
                "_operation": "WOULD_UPSERT",
                "_key": {
                    "source_code": "ABLY",
                    "source_brand_id": source_brand.get("source_brand_id"),
                },
                "_query_strategy": "SELECT_THEN_CREATE_OR_UPDATE",
                "source_id": None,
                "source_brand_id": source_brand.get("source_brand_id"),
                "name": source_brand.get("name"),
                "attributes": {"candidate_kind": source_brand_kind},
                "brand_id": None,
                "mapping_status": "UNMAPPED",
                "_references": {"source": {"code": "ABLY"}},
            },
            "category_source": {
                "_table": TABLE_CATEGORY_SOURCE,
                "_operation": "WOULD_UPSERT",
                "_key": {
                    "source_code": "ABLY",
                    "source_category_id": source_category_id,
                },
                "_query_strategy": "SELECT_THEN_CREATE_OR_UPDATE",
                "source_id": None,
                "source_category_id": source_category_id,
                "source_category_name": source_category_name,
                "source_category_path": source_category_name,
                "category_id": None,
                "_references": {"source": {"code": "ABLY"}},
                "_derived": {"candidate_kind": category_kind},
            },
            "product_source": {
                "_table": TABLE_PRODUCT_SOURCE,
                "_operation": "WOULD_UPSERT",
                "_key": {
                    "source_code": "ABLY",
                    "source_product_id": product.get("source_product_id"),
                },
                "_query_strategy": "GET_OR_CREATE_THEN_UPDATE",
                "source_id": None,
                "source_product_id": product.get("source_product_id"),
                "source_name": clean_text(product.get("name")),
                "source_brand_id": None,
                "source_category_id": None,
                "style_no": None,
                "source_name_en": None,
                "thumbnail_url": images.get("image_webp") or images.get("image"),
                "product_url": product.get("product_url"),
                "gender_scope": gender_scope(product.get("gender_scope") or product.get("genders")),
                "attributes": attributes,
                "market_type": "RETAIL",
                "mapping_status": "UNMAPPED",
                "product_id": None,
                "_references": {
                    "source": {"code": "ABLY"},
                    "source_brand": {
                        "source_code": "ABLY",
                        "source_brand_id": source_brand.get("source_brand_id"),
                    },
                    "source_category": {
                        "source_code": "ABLY",
                        "source_category_id": source_category_id,
                    },
                },
            },
            "product_source_snapshot": {
                "_table": TABLE_PRODUCT_SOURCE_SNAPSHOT,
                "_operation": "WOULD_INSERT_SNAPSHOT",
                "_key": {
                    "product_source_id": "<resolved later>",
                    "observed_at": scope.get("collected_at") or "<collected_at>",
                    "ranking_scope": scope_name,
                },
                "_query_strategy": "UPDATE_OR_CREATE",
                "product_source_id": None,
                "observed_at": scope.get("collected_at"),
                "list_price": snapshot.get("regular_price"),
                "sale_price": snapshot.get("sale_price"),
                "discount_rate": snapshot.get("discount_rate"),
                "rank_position": ranking.get("rank"),
                "ranking_scope": scope_name,
                "ranking_context": scope,
                "rating": None,
                "review_count": snapshot.get("review_count"),
                "like_count": None,
                "view_count": None,
                "sales_count": snapshot.get("sales_count"),
                "stock_status": stock_status,
                "platform_metrics": platform_metrics,
            },
        },
        "warnings": warnings,
    }
