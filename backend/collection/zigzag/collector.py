from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from collection.common.http import DEFAULT_HEADERS

from .constants import (
    DEFAULT_PAGE_ID,
    GOODS_CARD_TYPE,
    PRODUCT_BASE_URL,
    REQUEST_TIMEOUT,
    SEARCH_RESULT_API_URL,
    SEARCH_RESULT_QUERY,
    SHOP_COMPONENT_API_URL,
    SHOP_COMPONENT_QUERY,
    ZIGZAG_BASE_URL,
)
from .parser import ZigzagParser


class ZigzagCollectError(Exception):
    pass


class ZigzagCollector:
    """
    FINAL
    - ranking/category GraphQL
    - ranking item detail enrichment(main_domain)
    - store profile + store products
    - ORM/S3/Celery 책임 없음
    """

    def __init__(self, *, timeout=None, session=None):
        self.timeout = timeout or REQUEST_TIMEOUT
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Origin": ZIGZAG_BASE_URL,
            "Referer": f"{ZIGZAG_BASE_URL}/",
        })

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _post_graphql(self, url: str, query: str, variables: dict) -> dict:
        try:
            res = self.session.post(
                url,
                json={"query": query, "variables": variables},
                timeout=self.timeout,
            )
            res.raise_for_status()
            body = res.json()
        except Exception as exc:
            raise ZigzagCollectError(f"GraphQL 요청 실패: {url} / {exc}") from exc
        if not isinstance(body, dict):
            raise ZigzagCollectError("GraphQL 응답이 object가 아닙니다.")
        if body.get("errors"):
            raise ZigzagCollectError(f"GraphQL 응답 에러: {body['errors']}")
        return body

    def _get_html(self, url: str):
        try:
            res = self.session.get(url, timeout=self.timeout)
            res.raise_for_status()
            return res.text, res
        except Exception as exc:
            raise ZigzagCollectError(f"GET 실패: {url} / {exc}") from exc

    # ==========================================================
    # RANKING / CATEGORY
    # ==========================================================
    def iter_category_pages(
        self,
        *,
        category_id: str,
        sort: str = "200",
        page_id: str = DEFAULT_PAGE_ID,
        max_pages: int | None = None,
    ) -> Iterator[tuple[dict, list[dict], bool]]:
        after = None
        page = 0
        while True:
            input_data = {
                "display_category_id_list": [str(category_id)],
                "page_id": page_id,
                "filter_id_list": [str(sort)],
            }
            if after:
                input_data["after"] = after
            body = self._post_graphql(
                SEARCH_RESULT_API_URL,
                SEARCH_RESULT_QUERY,
                {"input": input_data},
            )
            result = (body.get("data") or {}).get("search_result") or {}
            parsed_items = []
            for item in result.get("ui_item_list") or []:
                if not isinstance(item, dict) or item.get("type") != GOODS_CARD_TYPE:
                    continue
                parsed = self._parse_goods_card(item)
                if parsed:
                    parsed_items.append(parsed)
            has_next = bool(result.get("has_next"))
            end_cursor = result.get("end_cursor")
            yield body, parsed_items, has_next
            page += 1
            if not has_next or not end_cursor:
                break
            if max_pages is not None and page >= max_pages:
                break
            after = end_cursor

    @classmethod
    def _parse_goods_card(cls, item: dict) -> dict | None:
        goods_id = ZigzagParser.to_int(item.get("goods_id"))
        if goods_id is None:
            return None
        categories = item.get("managed_category_list") or []
        candidates = [x for x in categories if isinstance(x, dict)]
        leaf = max(candidates, key=lambda x: ZigzagParser.to_int(x.get("depth")) or 0) if candidates else {}
        shop_id = ZigzagParser.clean_text(item.get("shop_id"))
        shop_name = ZigzagParser.clean_text(item.get("shop_name"))
        product_url = item.get("product_url") or PRODUCT_BASE_URL.format(goods_id=goods_id)
        return {
            "source_product_id": str(goods_id),
            "catalog_product_id": ZigzagParser.clean_text(item.get("catalog_product_id")) or str(goods_id),
            "product_name": ZigzagParser.clean_text(item.get("title")),
            "store": {
                "source_brand_id": shop_id,
                "name": shop_name,
                "main_domain": None,
                "source_profile_url": None,
            },
            # 구버전 코드 호환용 flat fields
            "store_id": shop_id,
            "store_name": shop_name,
            "is_brand": bool(item.get("is_brand")),
            "category_id": leaf.get("category_id") or leaf.get("id"),
            "category_name": leaf.get("value") or leaf.get("name"),
            "category_path": categories,
            "product_url": product_url,
            "thumbnail_url": item.get("image_url"),
            "regular_price": ZigzagParser.to_int(item.get("price")),
            "sale_price": ZigzagParser.to_int(item.get("final_price")),
            "discount_rate": ZigzagParser.to_float(item.get("discount_rate")),
            "review_score": ZigzagParser.to_float(item.get("review_score")),
            "review_count": ZigzagParser.to_int(str(item.get("display_review_count") or "").replace(",", "")),
            "sellable_status": item.get("sellable_status"),
            "is_ad": bool(item.get("is_ad")),
        }

    def collect_product_detail(self, ranking_item: dict) -> dict:
        url = ranking_item.get("product_url")
        if not url:
            raise ZigzagCollectError("product_url이 없습니다.")
        html, response = self._get_html(url)
        parsed = ZigzagParser.parse_product_detail_html(
            html,
            source_url=getattr(response, "url", url),
            fallback_shop_id=(ranking_item.get("store") or {}).get("source_brand_id") or ranking_item.get("store_id"),
            fallback_shop_name=(ranking_item.get("store") or {}).get("name") or ranking_item.get("store_name"),
        )
        parsed["http_status"] = getattr(response, "status_code", None)
        return parsed

    @staticmethod
    def enrich_ranking_item(ranking_item: dict, detail: dict | None) -> dict:
        result = dict(ranking_item)
        store = dict(result.get("store") or {})
        detail_store = (detail or {}).get("store") or {}
        for key in ("source_brand_id", "name", "main_domain", "source_profile_url", "image_url", "description", "target_age", "style_list", "bookmark_count"):
            value = detail_store.get(key)
            if value not in (None, "", []):
                store[key] = value
        result["store"] = store
        result["store_id"] = store.get("source_brand_id")
        result["store_name"] = store.get("name")
        return result

    # ==========================================================
    # STORE
    # ==========================================================
    def collect_shop(self, shop_url: str, *, product_limit=100, max_pages=None, collect_products=True) -> dict:
        source_url = self._normalize_shop_url(shop_url)
        html, response = self._get_html(source_url)
        shop = ZigzagParser.parse_store_html(html, source_url=source_url)
        shop_id = shop.get("source_brand_id")
        if not shop_id:
            raise ZigzagCollectError(f"shop_id를 찾지 못했습니다: {source_url}")
        products, categories = [], []
        if collect_products:
            products, categories = self.collect_shop_products(
                shop_id=str(shop_id), limit=product_limit, max_pages=max_pages
            )
        return {
            "source_url": source_url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "http_status": getattr(response, "status_code", None),
            "content_type": getattr(response, "headers", {}).get("Content-Type"),
            "shop": shop,
            "categories": [x for x in categories if str(x.get("id")) != "0" and x.get("name") != "전체"],
            "products": products,
        }

    def collect_shop_products(self, *, shop_id: str, limit=100, max_pages=None):
        products, seen = [], set()
        categories_by_id = {}
        for body in self.iter_shop_component_pages(shop_id=shop_id, max_pages=max_pages):
            root = (body.get("data") or {}).get("shop_ux_component_list") or {}
            for c in root.get("category_list") or []:
                if isinstance(c, dict) and c.get("id"):
                    categories_by_id[str(c["id"])] = {"id": str(c["id"]), "name": c.get("name")}
            for card in self._walk_product_cards(root.get("item_list") or []):
                parsed = self._parse_shop_product_item(card, fallback_shop_id=shop_id)
                if not parsed:
                    continue
                pid = parsed["source_product_id"]
                if pid in seen:
                    continue
                seen.add(pid); products.append(parsed)
                if limit is not None and len(products) >= int(limit):
                    return products, list(categories_by_id.values())
        return products, list(categories_by_id.values())

    def iter_shop_component_pages(self, *, shop_id: str, max_pages=None):
        after_id = None; page = 0
        while True:
            variables = {
                "shop_id": str(shop_id),
                "check_button_item_ids": [],
                "sub_filter_id_list": [],
                "sorting_item_id": None,
            }
            if after_id:
                variables["after_id"] = after_id
            body = self._post_graphql(SHOP_COMPONENT_API_URL, SHOP_COMPONENT_QUERY, variables)
            yield body
            page += 1
            root = (body.get("data") or {}).get("shop_ux_component_list") or {}
            if not root.get("has_next_page"):
                break
            after_id = root.get("after_id")
            if not after_id:
                break
            if max_pages is not None and page >= max_pages:
                break

    def _walk_product_cards(self, value):
        if isinstance(value, dict):
            if isinstance(value.get("product"), dict):
                yield value
            for child in value.values():
                yield from self._walk_product_cards(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._walk_product_cards(child)

    def _parse_shop_product_item(self, item: dict, *, fallback_shop_id=None):
        product = item.get("product") or {}
        if not isinstance(product, dict):
            return None
        pid = ZigzagParser.clean_text(product.get("catalog_product_id") or product.get("shop_product_no"))
        if not pid:
            return None
        return {
            "source_product_id": pid,
            "shop_product_no": ZigzagParser.clean_text(product.get("shop_product_no")),
            "store_id": ZigzagParser.clean_text(product.get("shop_id")) or fallback_shop_id,
            "store_name": ZigzagParser.clean_text(item.get("shop_name")),
            "product_name": ZigzagParser.clean_text(product.get("name")),
            "product_url": ZigzagParser.clean_text(product.get("url")),
            "thumbnail_url": ZigzagParser.clean_text(product.get("image_url")),
            "regular_price": ZigzagParser.to_int(product.get("price")),
            "sale_price": ZigzagParser.to_int(item.get("final_price")),
            "discount_rate": ZigzagParser.to_float(product.get("discount_rate")),
            "ranking": ZigzagParser.to_int(item.get("ranking")),
            "review_count": ZigzagParser.to_int(item.get("review_count")),
            "review_score": ZigzagParser.to_float(item.get("review_score")),
        }

    @staticmethod
    def _normalize_shop_url(url: str) -> str:
        if not url:
            raise ZigzagCollectError("shop_url이 비었습니다.")
        if url.startswith("/"):
            url = f"https://zigzag.kr{url}"
        if not urlparse(url).scheme:
            url = f"https://zigzag.kr/{url.lstrip('/')}"
        return url.split("?")[0].rstrip("/")
