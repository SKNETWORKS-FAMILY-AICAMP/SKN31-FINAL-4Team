from __future__ import annotations

from collections import defaultdict
from typing import Any

from .client import AblyClient
from .constants import (
    BRAND_DEPARTMENT_CATEGORIES,
    BRAND_DEPARTMENT_INITIAL_TOKEN,
    BRAND_DEPARTMENT_MAX_REQUESTS,
)


def _analytics_value(analytics: dict, key: str, fallback=None):
    value = analytics.get(key)
    return fallback if value is None else value


def _explicit_sold_out(item: dict, analytics: dict):
    """명시적인 품절 필드만 사용한다. closed_reason으로 추론하지 않는다."""
    for source, keys in (
        (item, ("is_sold_out", "is_soldout")),
        (analytics, ("IS_SOLD_OUT", "IS_SOLDOUT")),
    ):
        for key in keys:
            if key not in source:
                continue
            value = source[key]
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "y", "yes"}
            if value is None:
                return None
            return bool(value)
    return None


def normalize_goods_entry(entry: dict[str, Any]) -> dict[str, Any]:
    item = entry.get("item") if isinstance(entry.get("item"), dict) else {}
    logging = entry.get("logging") if isinstance(entry.get("logging"), dict) else {}
    analytics = (
        logging.get("analytics")
        if isinstance(logging.get("analytics"), dict)
        else {}
    )
    render = entry.get("render") if isinstance(entry.get("render"), dict) else {}
    render_data = render.get("data") if isinstance(render.get("data"), dict) else {}
    first_render = (
        item.get("first_page_rendering")
        if isinstance(item.get("first_page_rendering"), dict)
        else {}
    )

    goods_sno = _analytics_value(analytics, "GOODS_SNO", item.get("sno"))
    try:
        goods_sno = int(goods_sno) if goods_sno is not None else None
    except (TypeError, ValueError):
        pass

    return {
        "goods_sno": goods_sno,
        "goods_name": _analytics_value(analytics, "GOODS_NAME", item.get("name")),
        "brand": {
            "brand_sno": analytics.get("BRAND_SNO"),
            "brand_name": analytics.get("BRAND_NAME"),
        },
        "market": {
            "market_sno": _analytics_value(analytics, "MARKET_SNO", item.get("market_sno")),
            "market_name": _analytics_value(analytics, "MARKET_NAME", item.get("market_name")),
            "market_type": _analytics_value(analytics, "MARKET_TYPE", item.get("market_type")),
            "market_type_sno": analytics.get("MARKET_TYPE_SNO"),
        },
        "category": {
            "category_sno": analytics.get("CATEGORY_SNO"),
            "category_name": _analytics_value(analytics, "CATEGORY_NAME", item.get("category_name")),
        },
        "standard_category": {
            "standard_category_sno": analytics.get("STANDARD_CATEGORY_SNO"),
            "standard_category_name": analytics.get("STANDARD_CATEGORY_NAME"),
        },
        "rank": render_data.get("ranking"),
        "original_price": first_render.get("original_price"),
        "price": _analytics_value(analytics, "SALES_PRICE", item.get("price")),
        "discount_rate": _analytics_value(analytics, "DISCOUNT_RATE", item.get("discount_rate")),
        "sell_count": item.get("sell_count"),
        "review_count": analytics.get("REVIEW_COUNT"),
        "review_rating": analytics.get("REVIEW_RATING"),
        "likes_count": analytics.get("LIKES_COUNT"),
        "is_new": item.get("is_new"),
        "is_sold_out": _explicit_sold_out(item, analytics),
        "closed_reason": render_data.get("closed_reason"),
        "delivery_type": _analytics_value(analytics, "DELIVERY_TYPE", item.get("delivery_type")),
        "image": item.get("image") or (render_data.get("image") or {}).get("url"),
        "promotion_tags": analytics.get("PROMOTION_TAG") or [],
        "image_badges": analytics.get("IMAGE_BADGE_LIST") or render_data.get("image_badge_list") or [],
        "badges": {
            "chips": render_data.get("chips") or [],
            "emblems": render_data.get("emblems") or [],
            "image_badge": render_data.get("image_badge"),
            "has_award": analytics.get("HAS_AWARD"),
            "is_only_ably": analytics.get("IS_ONLY_ABLY"),
            "price_label_type": analytics.get("PRICE_LABEL_TYPE"),
            "price_label": analytics.get("PRICE_LABEL"),
        },
    }


class AblyStoreProfileCollector:
    """브랜드관 상품 랭킹을 STORE 프로필 보강용 RAW로 수집한다."""

    def __init__(
        self,
        *,
        client=None,
        max_requests: int | None = BRAND_DEPARTMENT_MAX_REQUESTS,
    ):
        if max_requests is not None and max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        self.client = client or AblyClient()
        self.max_requests = max_requests
        self._owns_client = client is None

    def close(self):
        if self._owns_client:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    @staticmethod
    def _entries(page: dict) -> list[dict]:
        components = page.get("components")
        if not isinstance(components, list):
            raise ValueError("ABLY COMPONENT_LIST components must be a list")

        entries = []
        goods_component_found = False
        for component in components:
            if not isinstance(component, dict):
                continue
            component_type = component.get("type") or {}
            if not isinstance(component_type, dict):
                continue
            if component_type.get("item_list") != "TWO_COL_GOODS_LIST":
                continue
            goods_component_found = True
            entity = component.get("entity") or {}
            if not isinstance(entity, dict):
                continue
            entries.extend(
                entry for entry in (entity.get("item_list") or [])
                if isinstance(entry, dict)
            )
        if not goods_component_found:
            raise ValueError("ABLY TWO_COL_GOODS_LIST component is missing")
        return entries

    def collect_category(self, category_sno: int) -> dict[str, Any]:
        if category_sno not in BRAND_DEPARTMENT_CATEGORIES:
            raise ValueError(f"unsupported BRAND_DEPARTMENT category_sno: {category_sno}")

        next_token = BRAND_DEPARTMENT_INITIAL_TOKEN
        seen_tokens: set[str] = set()
        raw_pages = []
        products = []
        crawl_complete = False
        stop_reason = None

        while True:
            if (
                self.max_requests is not None
                and len(raw_pages) >= self.max_requests
            ):
                stop_reason = "max_requests"
                break

            seen_tokens.add(next_token)
            page = self.client.get_component_list(
                category_sno=category_sno,
                next_token=next_token,
            )
            if not isinstance(page, dict):
                raise ValueError("ABLY COMPONENT_LIST response must be a dict")
            raw_pages.append(page)
            products.extend(normalize_goods_entry(entry) for entry in self._entries(page))

            response_token = page.get("next_token")
            if not response_token:
                crawl_complete = True
                stop_reason = "next_token_absent"
                break
            if response_token in seen_tokens:
                stop_reason = "repeated_next_token"
                break
            next_token = response_token

        return {
            "category_sno": category_sno,
            "category_name": BRAND_DEPARTMENT_CATEGORIES[category_sno],
            "request_count": len(raw_pages),
            "product_count": len(products),
            "crawl_complete": crawl_complete,
            "stop_reason": stop_reason,
            "products": products,
            "raw_pages": raw_pages,
        }

    def collect_all(self, *, category_snos=None) -> dict[str, Any]:
        selected = list(category_snos or BRAND_DEPARTMENT_CATEGORIES.keys())
        categories = [self.collect_category(int(category_sno)) for category_sno in selected]
        products = [product for category in categories for product in category["products"]]

        brand_products = defaultdict(lambda: {"brand_name": None, "markets": {}, "appearances": []})
        for category in categories:
            for product in category["products"]:
                brand = product["brand"]
                brand_sno = brand.get("brand_sno")
                if brand_sno is None:
                    continue
                profile = brand_products[str(brand_sno)]
                if not profile["brand_name"] and brand.get("brand_name"):
                    profile["brand_name"] = brand["brand_name"]
                market = product["market"]
                market_sno = market.get("market_sno")
                if market_sno is not None:
                    market_key = str(market_sno)
                    existing_market = profile["markets"].get(market_key, {})
                    profile["markets"][market_key] = {
                        **existing_market,
                        **{
                            key: value
                            for key, value in market.items()
                            if value not in (None, "")
                        },
                    }
                profile["appearances"].append({
                    "goods_sno": product.get("goods_sno"),
                    "ranking_category_sno": category["category_sno"],
                    "ranking_category_name": category["category_name"],
                    "rank": product.get("rank"),
                })

        brand_profiles = [
            {
                "brand_sno": brand_sno,
                "brand_name": value["brand_name"],
                "markets": list(value["markets"].values()),
                "appearances": value["appearances"],
            }
            for brand_sno, value in brand_products.items()
        ]
        return {
            "categories": categories,
            "brand_profiles": brand_profiles,
            "products_count": len(products),
            "brand_count": len(brand_profiles),
            "request_count": sum(category["request_count"] for category in categories),
            "failure_count": sum(not category["crawl_complete"] for category in categories),
        }
