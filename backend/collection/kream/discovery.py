from __future__ import annotations

import json
from uuid import uuid4

from .constants import KREAM_API_BASE_URL, KREAM_BASE_URL


class KreamDiscoveryCollector:
    def __init__(self, client):
        self.client = client

    def collect_page(
        self,
        *,
        tab_id: int,
        cursor: str | int = 1,
        sort: str = "popular_score",
    ) -> dict:
        url = f"{KREAM_API_BASE_URL}/api/fetch/shop/{tab_id}"

        return self.client.get(
            url,
            params={
                "sort": sort,
                "cursor": str(cursor),
                "request_key": str(uuid4()),
            },
            referer=f"{KREAM_BASE_URL}/categories/{tab_id}",
        )

    @staticmethod
    def extract_products(payload: dict) -> list[dict]:
        products = {}

        def add_product(data: dict):
            product_id = data.get("product_id")

            try:
                product_id = int(product_id)
            except (TypeError, ValueError):
                return

            if not (
                data.get("product_name_en")
                or data.get("product_name_ko")
                or data.get("brand_name")
            ):
                return

            products[product_id] = {
                "product_id": product_id,
                "product_url": f"{KREAM_BASE_URL}/products/{product_id}",
                "name_en": data.get("product_name_en"),
                "name_ko": data.get("product_name_ko"),
                "style_code": data.get("product_style_code"),
                "brand_id": data.get("brand_id"),
                "brand_name": data.get("brand_name"),
                "category_id": data.get("shop_category_id"),
                "category_depth1": data.get("shop_category_name_1d"),
                "category_depth2": data.get("shop_category_name_2d"),
                "product_type": data.get("product_type"),
                "product_gender": data.get("product_gender"),
                "price": data.get("price"),
                "original_price": data.get("original_price"),
                "discount_rate": data.get("display_discount_rate"),
                "has_immediate_delivery_item": data.get(
                    "has_immediate_delivery_item"
                ),
                "sort_type": data.get("sort_type"),
            }

        def walk(obj):
            if isinstance(obj, dict):
                if obj.get("product_id"):
                    add_product(obj)

                properties = obj.get("properties")

                if isinstance(properties, list):
                    for raw in properties:
                        if isinstance(raw, dict):
                            add_product(raw)
                            continue

                        if not isinstance(raw, str):
                            continue

                        if "product_id" not in raw:
                            continue

                        try:
                            decoded = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        if isinstance(decoded, dict):
                            add_product(decoded)

                for child in obj.values():
                    walk(child)

            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        walk(payload)

        return list(products.values())

    @staticmethod
    def extract_pagination(payload: dict) -> dict | None:
        def walk(obj):
            if isinstance(obj, dict):
                pagination = obj.get("pagination")

                if isinstance(pagination, dict):
                    return pagination

                for child in obj.values():
                    result = walk(child)

                    if result:
                        return result

            elif isinstance(obj, list):
                for child in obj:
                    result = walk(child)

                    if result:
                        return result

            return None

        return walk(payload)

    def collect_products(
        self,
        *,
        tab_id: int,
        limit: int = 100,
        sort: str = "popular_score",
        max_pages: int = 20,
    ) -> list[dict]:
        products = {}

        cursor = "1"
        page_count = 0

        while (
            cursor
            and len(products) < limit
            and page_count < max_pages
        ):
            payload = self.collect_page(
                tab_id=tab_id,
                cursor=cursor,
                sort=sort,
            )

            page_products = self.extract_products(payload)

            print(
                f"[KREAM] cursor={cursor} "
                f"products={len(page_products)}"
            )

            for item in page_products:
                products[item["product_id"]] = item

                if len(products) >= limit:
                    break

            pagination = self.extract_pagination(payload)

            print(
                "[KREAM] pagination:",
                pagination,
            )

            if not pagination:
                break

            cursor = pagination.get("next_cursor")
            page_count += 1

        result = list(products.values())[:limit]

        for rank, item in enumerate(result, start=1):
            item["feed_rank"] = rank
            item["tab_id"] = tab_id
            item["sort"] = sort

        return result
