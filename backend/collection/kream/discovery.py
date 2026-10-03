from __future__ import annotations

import json
import re
from uuid import uuid4
from .constants import KREAM_API_BASE_URL, KREAM_BASE_URL


class KreamDiscoveryCollector:
    PRODUCT_RE = re.compile(r"/products/(\d+)")

    def __init__(self, client):
        self.client = client

    def collect_page(self, *, tab_id: int, category_id: int | str = "all", cursor: str | int = "1", sort: str = "popular_score", pagination_path: str | None = None) -> dict:
        category_id = "all" if category_id is None else str(category_id)
        referer = f"{KREAM_BASE_URL}/categories/{tab_id}/{category_id}"
        if pagination_path is None:
            url = f"{KREAM_API_BASE_URL}/api/screens/categories/{tab_id}/{category_id}"
            params = {"request_key": str(uuid4())}
        else:
            if not pagination_path.startswith("fetch/categories/"):
                raise ValueError(f"예상하지 못한 KREAM pagination path: {pagination_path}")
            url = f"{KREAM_API_BASE_URL}/api/{pagination_path}"
            params = {"cursor": str(cursor), "request_key": str(uuid4())}
        return self.client.get(url, params=params, referer=referer)

    @classmethod
    def extract_products(cls, payload: dict) -> list[dict]:
        products = {}

        def walk(obj):
            if isinstance(obj, dict):
                if obj.get("display_type") == "product_card":
                    properties = {}
                    product_url = None
                    for action in obj.get("actions") or []:
                        if not isinstance(action, dict):
                            continue
                        if action.get("type") == "url":
                            product_url = action.get("value")
                        parameters = action.get("parameters") or {}
                        for raw in parameters.get("properties") or []:
                            if not isinstance(raw, str):
                                continue
                            try:
                                parsed = json.loads(raw)
                            except (ValueError, TypeError):
                                continue
                            if isinstance(parsed, dict) and parsed.get("product_id"):
                                properties = parsed
                                break
                        if properties:
                            break
                    product_id = properties.get("product_id")
                    if not product_id and product_url:
                        match = cls.PRODUCT_RE.search(product_url)
                        if match:
                            product_id = match.group(1)
                    if product_id:
                        product_id = int(product_id)
                        products.setdefault(product_id, {
                            "product_id": product_id,
                            "product_url": product_url or f"{KREAM_BASE_URL}/products/{product_id}",
                            "name_en": properties.get("product_name_en"),
                            "name_ko": properties.get("product_name_ko"),
                            "style_code": properties.get("product_style_code"),
                            "brand_id": properties.get("brand_id"),
                            "brand_name": properties.get("brand_name"),
                            "category_id": properties.get("shop_category_id"),
                            "category_depth1": properties.get("shop_category_name_1d"),
                            "category_depth2": properties.get("shop_category_name_2d"),
                            "product_type": properties.get("product_type"),
                            "product_gender": properties.get("product_gender"),
                            "price": properties.get("price"),
                            "original_price": properties.get("original_price"),
                            "discount_rate": properties.get("display_discount_rate"),
                            "has_immediate_delivery_item": properties.get("has_immediate_delivery_item"),
                            "sort_type": properties.get("sort_type"),
                        })
                    return
                for child in obj.values():
                    walk(child)
            elif isinstance(obj, list):
                for child in obj:
                    walk(child)
        walk(payload.get("content", payload))
        return list(products.values())

    @staticmethod
    def extract_pagination(payload: dict) -> dict | None:
        content = payload.get("content") or {}
        if isinstance(content, dict) and isinstance(content.get("pagination"), dict):
            return content["pagination"]
        return None

    def collect_products(self, *, tab_id: int, category_id: int | str = "all", limit: int = 100, sort: str = "popular_score", max_pages: int = 20) -> list[dict]:
        if limit < 1:
            return []
        products = {}
        cursor = "1"
        pagination_path = None
        seen_pages = set()
        for page in range(1, max_pages + 1):
            page_key = (pagination_path, cursor)
            if page_key in seen_pages:
                break
            seen_pages.add(page_key)
            payload = self.collect_page(tab_id=tab_id, category_id=category_id, cursor=cursor, sort=sort, pagination_path=pagination_path)
            page_products = self.extract_products(payload)
            print(f"[KREAM] tab={tab_id} category={category_id} page={page} cursor={cursor} products={len(page_products)}")
            for product in page_products:
                products.setdefault(product["product_id"], product)
                if len(products) >= limit:
                    break
            if len(products) >= limit:
                break
            pagination = self.extract_pagination(payload) or {}
            next_cursor = pagination.get("next_cursor")
            next_path = pagination.get("path")
            if not next_cursor or not next_path:
                break
            pagination_path = next_path
            cursor = str(next_cursor)
        result = list(products.values())[:limit]
        for rank, item in enumerate(result, 1):
            item.update(feed_rank=rank, tab_id=tab_id, category_id=category_id, sort=sort)
        return result
