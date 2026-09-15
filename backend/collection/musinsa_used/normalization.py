from __future__ import annotations

from typing import Any

from collection.common.normalization import (
    TABLE_BRAND_SOURCE,
    TABLE_CATEGORY_SOURCE,
    TABLE_PRODUCT_SOURCE,
    TABLE_RESALE_SNAPSHOT,
    clean_text,
    gender_scope,
    source_key_text,
)


GRADE_MAP = {
    "S+등급": "S+",
    "S등급": "S",
    "A+등급": "A+",
    "A등급": "A",
    "B등급": "B",
}


def normalize_condition_grade(value: Any) -> str | None:
    return GRADE_MAP.get(str(value).strip()) if value is not None else None


def _source_identifier(value: Any, name: Any) -> str | None:
    if value is not None and str(value).strip():
        return str(value).strip()
    source_key = source_key_text(name)
    return f"NAME:{source_key}" if source_key else None


def _deepest_category(category: dict) -> tuple[str | None, str | None, str | None]:
    parts: list[tuple[str, str]] = []
    for depth in range(1, 5):
        code = category.get(f"depth{depth}_code")
        name = category.get(f"depth{depth}_name")
        if code or name:
            parts.append((str(code) if code is not None else str(name), name or str(code)))
    if not parts:
        return None, None, None
    code, name = parts[-1]
    return code, name, " > ".join(part_name for _, part_name in parts)


def _resale_snapshot(
    snapshot: dict,
    *,
    ranking_context: dict | None = None,
    observed_at: str | None = None,
) -> dict:
    price = snapshot.get("sale_price")
    sold_out = snapshot.get("is_sold_out")
    available_count = 0 if sold_out is True else 1 if sold_out is False else None
    lowest_ask = price if sold_out is False else None
    grade_raw = snapshot.get("used_condition_grade") or snapshot.get("condition_grade_raw")
    history = snapshot.get("used_price_history") or {}
    return {
        "_table": TABLE_RESALE_SNAPSHOT,
        "_operation": "WOULD_INSERT_SNAPSHOT",
        "_key": {
            "product_source_id": "<resolved later>",
            "observed_at": observed_at or "<collected_at>",
        },
        "_query_strategy": "UPDATE_OR_CREATE",
        "product_source_id": None,
        "observed_at": observed_at,
        "listing_count": 1,
        "available_count": available_count,
        "min_price": price,
        "max_price": price,
        "avg_price": price,
        "median_price": price,
        "sold_count": None,
        "lowest_ask": lowest_ask,
        "highest_bid": None,
        "last_trade_price": None,
        "trade_volume": None,
        "resale_price_ratio": None,
        "resale_index": None,
        "market_metrics": {
            "currency": snapshot.get("currency") or "KRW",
            "regular_price": snapshot.get("regular_price"),
            "sale_price": price,
            "discount_rate": snapshot.get("discount_rate"),
            "goods_page_view_count": snapshot.get("view_count"),
            "age_view_total": snapshot.get("age_view_total"),
            "page_view_total": snapshot.get("page_view_total"),
            "purchase_total": snapshot.get("purchase_total"),
            "condition_grade_raw": grade_raw,
            "condition_grade": normalize_condition_grade(grade_raw),
            "size": snapshot.get("size"),
            "is_sold_out": sold_out,
            "price_anchor_type": history.get("price_anchor_type"),
            "first_sale_start": history.get("first_sale_start"),
            "price_change_histories": history.get("price_change_histories") or [],
            "discount_scheduled_at": history.get("discount_scheduled_at"),
            "rank_position": (ranking_context or {}).get("rank"),
            "ranking_context": ranking_context or {},
        },
    }


def _related_candidate(
    item: dict,
    parent_goods_no: str | None,
    observed_at: str | None,
) -> dict:
    snapshot = {
        "regular_price": item.get("regular_price"),
        "sale_price": item.get("sale_price"),
        "discount_rate": item.get("discount_rate"),
        "currency": "KRW",
        "used_condition_grade": item.get("condition_grade_raw"),
        "is_sold_out": item.get("sold_out"),
        "size": item.get("size"),
        "used_price_history": {},
    }
    source_brand_id = _source_identifier(
        item.get("brand_code"),
        item.get("brand_name"),
    )
    source_product_id = item.get("goods_no")
    product_source = {
        "_table": TABLE_PRODUCT_SOURCE,
        "_operation": "WOULD_UPSERT",
        "_key": {
            "source_code": "MUSINSA_USED",
            "source_product_id": source_product_id,
        },
        "_query_strategy": "GET_OR_CREATE_THEN_UPDATE",
        "source_id": None,
        "source_product_id": source_product_id,
        "source_name": clean_text(item.get("name")),
        "source_name_en": None,
        "source_brand_id": None,
        "source_category_id": None,
        "style_no": None,
        "thumbnail_url": item.get("thumbnail_url"),
        "product_url": item.get("product_url"),
        "gender_scope": gender_scope(item.get("gender_text")),
        "market_type": "RESALE",
        "mapping_status": "UNMAPPED",
        "product_id": None,
        "_references": {
            "source": {"code": "MUSINSA_USED"},
            "source_brand": {
                "source_code": "MUSINSA_USED",
                "source_brand_id": source_brand_id,
            },
            "source_category": None,
        },
        "attributes": {
            "used": {
                "original_goods_no": None,
                "condition_grade_raw": item.get("condition_grade_raw"),
                "condition_grade": item.get("condition_grade"),
                "size": item.get("size"),
            },
            "source_attributes": {
                "is_option_visible": item.get("is_option_visible"),
                "on_sale": item.get("on_sale"),
                "coupon_price": item.get("coupon_price"),
                "coupon_discount_rate": item.get("coupon_discount_rate"),
                "has_option_price": item.get("has_option_price"),
            },
        },
    }
    return {
        "source_product_id": item.get("goods_no"),
        "product_source_payload": product_source,
        "resale_snapshot_payload": _resale_snapshot(
            snapshot,
            observed_at=observed_at,
        ),
        "relation": {
            "type": "MUSINSA_USED_RELATED_GOODS",
            "discovered_from": parent_goods_no,
        },
    }


def normalize_musinsa_used_preview(
    parsed: dict,
    observed_at: str | None = None,
) -> dict:
    brand = parsed.get("brand") or {}
    product = parsed.get("product") or {}
    snapshot = parsed.get("snapshot") or {}
    history = parsed.get("used_price_history") or {}
    ranking_context = parsed.get("ranking_context") or {}
    meta = parsed.get("meta") or {}
    category = product.get("category") or {}
    category_id, category_name, category_path = _deepest_category(category)
    grade_raw = snapshot.get("used_condition_grade")
    source_brand_id = _source_identifier(
        brand.get("brand_code"),
        brand.get("name_ko") or brand.get("name_en"),
    )
    source_product_id = product.get("goods_no")
    product_source = {
        "_table": TABLE_PRODUCT_SOURCE,
        "_operation": "WOULD_UPSERT",
        "_key": {
            "source_code": "MUSINSA_USED",
            "source_product_id": source_product_id,
        },
        "_query_strategy": "GET_OR_CREATE_THEN_UPDATE",
        "source_id": None,
        "source_product_id": source_product_id,
        "source_name": clean_text(product.get("name")),
        "source_name_en": product.get("name_en"),
        "source_brand_id": None,
        "source_category_id": None,
        "style_no": product.get("style_no"),
        "thumbnail_url": product.get("thumbnail_url"),
        "product_url": ranking_context.get("product_url") or meta.get("final_url") or meta.get("request_url"),
        "gender_scope": gender_scope(product.get("genders")),
        "market_type": "RESALE",
        "mapping_status": "UNMAPPED",
        "product_id": None,
        "_references": {
            "source": {"code": "MUSINSA_USED"},
            "source_brand": {
                "source_code": "MUSINSA_USED",
                "source_brand_id": source_brand_id,
            },
            "source_category": {
                "source_code": "MUSINSA_USED",
                "source_category_id": category_id,
            },
        },
        "attributes": {
            "used": {
                "original_goods_no": product.get("original_goods_no"),
                "condition_grade_raw": grade_raw,
                "condition_grade": normalize_condition_grade(grade_raw),
                "size": product.get("size"),
            },
            "measurements": product.get("measurements") or {},
            "source_attributes": product.get("source_attributes") or {},
            "tags": product.get("tags") or [],
        },
    }
    resale_input = {
        **snapshot,
        "size": product.get("size"),
        "used_price_history": history,
    }
    related = parsed.get("related_goods") or {}
    related_candidates = [
        _related_candidate(item, product.get("goods_no"), observed_at)
        for item in related.get("used_products") or []
        if isinstance(item, dict)
    ]
    warnings = []
    if not source_product_id:
        warnings.append("product.goods_no is missing")
    if not source_brand_id:
        warnings.append("source brand is missing")
    if not category_id:
        warnings.append("source category is missing")
    return {
        "source": "MUSINSA_USED",
        "db_write": False,
        "db_write_operations": 0,
        "targets": {
            "brand_source": {
                "_table": TABLE_BRAND_SOURCE,
                "_operation": "WOULD_UPSERT",
                "_key": {
                    "source_code": "MUSINSA_USED",
                    "source_brand_id": source_brand_id,
                },
                "_query_strategy": "SELECT_THEN_CREATE_OR_UPDATE",
                "source_id": None,
                "source_brand_id": source_brand_id,
                "name": brand.get("name_ko"),
                "english_name": brand.get("name_en"),
                "image_url": brand.get("logo_url"),
                "country_code": brand.get("nation_code"),
                "description": brand.get("description"),
                "brand_id": None,
                "mapping_status": "UNMAPPED",
                "_references": {"source": {"code": "MUSINSA_USED"}},
            },
            "category_source": {
                "_table": TABLE_CATEGORY_SOURCE,
                "_operation": "WOULD_UPSERT",
                "_key": {
                    "source_code": "MUSINSA_USED",
                    "source_category_id": category_id,
                },
                "_query_strategy": "SELECT_THEN_CREATE_OR_UPDATE",
                "source_id": None,
                "source_category_id": category_id,
                "source_category_name": category_name,
                "source_category_path": category_path,
                "category_id": None,
                "_references": {"source": {"code": "MUSINSA_USED"}},
            },
            "product_source": product_source,
            "resale_snapshot": _resale_snapshot(
                resale_input,
                ranking_context=ranking_context,
                observed_at=observed_at,
            ),
        },
        "related_listing_candidates": related_candidates,
        "warnings": warnings,
    }
