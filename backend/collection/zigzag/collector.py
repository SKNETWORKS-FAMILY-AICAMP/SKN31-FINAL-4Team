from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from .client import ZigzagClient
from .constants import (
    DEFAULT_LIMIT,
    DEFAULT_PAGE_ID,
    DEFAULT_SORT,
    GOODS_CARD_TYPE,
    PRODUCT_BASE_URL,
    SEARCH_RESULT_QUERY,
)
from .exceptions import ZigzagCollectError
from bs4 import BeautifulSoup


class ZigzagCollector:
    """
    ZIGZAG 카테고리 랭킹 Collector.

    핵심:
    - GetSearchResult GraphQL 사용
    - cursor pagination
    - 광고 제외 기본
    - source_product_id 중복 제거
    - 최종 limit 기준으로 정확히 TOP N 반환
    - rank는 필터/중복 제거 이후 1부터 다시 부여

    Collector는 DB/S3/Celery를 모른다.
    """

    def __init__(
        self,
        *,
        client: ZigzagClient | None = None,
    ):
        self.client = client or ZigzagClient()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ============================================================
    # PAGE ITERATOR
    # ============================================================

    def iter_category_pages(
        self,
        *,
        category_id: str,
        sort: str = DEFAULT_SORT,
        page_id: str = DEFAULT_PAGE_ID,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """
        한 페이지씩 반환한다.

        반환:
        {
            "page": 1,
            "variables": {...},
            "raw": {...},
            "items": [...],
            "has_next": bool,
            "end_cursor": "...",
        }
        """
        category_id = str(category_id).strip()

        if not category_id:
            raise ValueError("ZIGZAG category_id가 없습니다.")

        after: str | None = None
        page_no = 0

        while True:
            page_no += 1

            variables = self._build_variables(
                category_id=category_id,
                sort=str(sort),
                page_id=str(page_id),
                after=after,
            )

            body = self.client.post_graphql(
                query=SEARCH_RESULT_QUERY,
                variables=variables,
            )

            search_result = (
                (body.get("data") or {})
                .get("search_result")
                or {}
            )

            ui_item_list = search_result.get("ui_item_list") or []

            parsed_items: list[dict[str, Any]] = []

            for raw_item in ui_item_list:
                if not isinstance(raw_item, dict):
                    continue

                if raw_item.get("type") != GOODS_CARD_TYPE:
                    continue

                parsed = self._parse_goods_card(raw_item)

                if parsed is not None:
                    parsed_items.append(parsed)

            has_next = bool(search_result.get("has_next"))
            end_cursor = search_result.get("end_cursor")

            yield {
                "page": page_no,
                "variables": variables,
                "raw": body,
                "items": parsed_items,
                "has_next": has_next,
                "end_cursor": end_cursor,
            }

            if not has_next or not end_cursor:
                break

            if max_pages is not None and page_no >= max_pages:
                break

            after = str(end_cursor)

    # ============================================================
    # TOP N RANKING
    # ============================================================

    def collect_category_ranking(
        self,
        *,
        category_id: str,
        limit: int = DEFAULT_LIMIT,
        sort: str = DEFAULT_SORT,
        page_id: str = DEFAULT_PAGE_ID,
        max_pages: int | None = None,
        include_ads: bool = False,
    ) -> dict[str, Any]:
        """
        카테고리 TOP N을 수집한다.

        raw_pages:
            실제 GraphQL 원본 응답을 페이지별로 보존한다.

        items:
            FEEDIT가 이후 정규화하기 편한 최소 파싱 결과.
        """
        limit = int(limit)

        if limit <= 0:
            raise ValueError(
                "ZIGZAG ranking limit은 1 이상이어야 합니다."
            )

        items: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []

        seen_product_ids: set[str] = set()

        for page in self.iter_category_pages(
            category_id=category_id,
            sort=sort,
            page_id=page_id,
            max_pages=max_pages,
        ):
            raw_pages.append(
                {
                    "page": page["page"],
                    "variables": page["variables"],
                    "response": page["raw"],
                }
            )

            for item in page["items"]:
                source_product_id = item.get("source_product_id")

                if not source_product_id:
                    continue

                source_product_id = str(source_product_id)

                if source_product_id in seen_product_ids:
                    continue

                if not include_ads and item.get("is_ad"):
                    continue

                seen_product_ids.add(source_product_id)

                ranked_item = {
                    **item,
                    "rank": len(items) + 1,
                }

                items.append(ranked_item)

                if len(items) >= limit:
                    break

            if len(items) >= limit:
                break

            if not page["has_next"]:
                break

        return {
            "category_id": str(category_id),
            "sort": str(sort),
            "page_id": str(page_id),
            "requested_limit": limit,
            "include_ads": bool(include_ads),
            "count": len(items),
            "items": items,
            "raw_pages": raw_pages,
        }

    def collect_product_detail(
        self,
        source_product_id: str,
    ) -> dict:

        product_id = str(
            source_product_id
        ).strip()

        url = (
            "https://store.zigzag.kr/"
            f"catalog/products/{product_id}"
        )

        response = self.session.get(
            url,
            timeout=20,
        )

        response.raise_for_status()

        html = response.text

        # ========================================================
        # __NEXT_DATA__
        # ========================================================

        match = re.search(
            r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>'
            r'(.*?)'
            r'</script>',
            html,
            re.DOTALL,
        )

        if not match:
            raise RuntimeError(
                f"__NEXT_DATA__ 없음: "
                f"{product_id}"
            )

        next_data = json.loads(
            match.group(1)
        )

        queries = (
            next_data
            .get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )

        product = None

        for query in queries:

            data = (
                query
                .get("state", {})
                .get("data")
            )

            if not isinstance(
                data,
                dict,
            ):
                continue

            candidate = (
                data.get("product")
            )

            if not isinstance(
                candidate,
                dict,
            ):
                continue

            if str(
                candidate.get("id")
            ) == product_id:

                product = candidate
                break

        if product is None:
            raise RuntimeError(
                f"product 데이터 없음: "
                f"{product_id}"
            )

        # ========================================================
        # DESCRIPTION
        # ========================================================

        description_html = (
            product.get(
                "description"
            )
            or ""
        )

        soup = BeautifulSoup(
            description_html,
            "html.parser",
        )

        # 지금은 저장만.
        # OCR/분석은 절대 하지 않음.
        description_text = (
            soup.get_text(
                "\n",
                strip=True,
            )
            if description_html
            else ""
        )

        # ========================================================
        # DETAIL IMAGE URLs
        # description 내부 이미지
        # ========================================================

        detail_image_urls = []

        for img in soup.find_all("img"):

            src = img.get("src")

            if not src:
                continue

            src = str(src).strip()

            if src.startswith("//"):
                src = (
                    "https:"
                    + src
                )

            if (
                src
                and src
                not in detail_image_urls
            ):
                detail_image_urls.append(
                    src
                )

        # ========================================================
        # PRODUCT IMAGE LIST
        # ========================================================

        product_image_urls = []

        for image in (
            product.get(
                "product_image_list"
            )
            or []
        ):

            if not isinstance(
                image,
                dict,
            ):
                continue

            image_url = (
                image.get(
                    "origin_url"
                )
                or image.get(
                    "url"
                )
            )

            if (
                image_url
                and image_url
                not in product_image_urls
            ):
                product_image_urls.append(
                    image_url
                )

        # ========================================================
        # RETURN
        # ========================================================

        return {
            "collected": True,

            "source_product_id":
                product_id,

            "description_html":
                description_html,

            "description_text":
                description_text,

            "detail_image_urls":
                detail_image_urls,

            "product_image_urls":
                product_image_urls,

            "sales_status":
                product.get(
                    "sales_status"
                ),

            "display_status":
                product.get(
                    "display_status"
                ),

            "category_key":
                product.get(
                    "category_key"
                ),
        }

    def enrich_ranking_details(
        self,
        items: list[dict],
        *,
        detail_limit: int | None = None,
    ) -> dict:

        enriched_items = []

        detail_success_count = 0
        detail_failure_count = 0

        if detail_limit is None:
            detail_limit = len(items)

        detail_limit = max(
            0,
            int(detail_limit),
        )

        for index, item in enumerate(
            items
        ):

            enriched = dict(
                item
            )

            # detail_limit 이후는
            # 랭킹 데이터만 보관
            if index >= detail_limit:

                enriched["detail"] = {
                    "collected": False,
                    "skipped": True,
                }

                enriched_items.append(
                    enriched
                )

                continue

            try:

                detail = (
                    self.collect_product_detail(
                        item[
                            "source_product_id"
                        ]
                    )
                )

                enriched[
                    "detail"
                ] = detail

                detail_success_count += 1

            except Exception as exc:

                enriched[
                    "detail"
                ] = {
                    "collected": False,
                    "skipped": False,
                    "error_type": (
                        exc.__class__.__name__
                    ),
                    "error": str(exc),
                }

                detail_failure_count += 1

            enriched_items.append(
                enriched
            )

        return {
            "items": enriched_items,

            "detail_success_count":
                detail_success_count,

            "detail_failure_count":
                detail_failure_count,
        }

    # ============================================================
    # PARSER
    # ============================================================

    @classmethod
    def _parse_goods_card(
        cls,
        item: dict[str, Any],
    ) -> dict[str, Any] | None:
        goods_id = cls._to_int(item.get("goods_id"))

        if goods_id is None:
            return None

        managed_categories = item.get("managed_category_list") or []

        category_path: list[dict[str, Any]] = []

        if isinstance(managed_categories, list):
            category_path = sorted(
                [
                    category
                    for category in managed_categories
                    if isinstance(category, dict)
                ],
                key=lambda category: category.get("depth") or 0,
            )

        leaf_category = (
            category_path[-1]
            if category_path
            else {}
        )

        return {
            "source_product_id": str(goods_id),
            "catalog_product_id": cls._to_text(
                item.get("catalog_product_id")
            ),

            "product_name": item.get("title"),

            "store_id": cls._to_text(item.get("shop_id")),
            "store_name": item.get("shop_name"),
            "is_brand": bool(item.get("is_brand")),

            "category_id": cls._to_text(
                leaf_category.get("id")
            ),
            "category_name": leaf_category.get("value"),
            "category_path": [
                {
                    "id": cls._to_text(category.get("id")),
                    "name": category.get("value"),
                    "key": category.get("key"),
                    "depth": category.get("depth"),
                }
                for category in category_path
            ],

            "product_url": (
                item.get("product_url")
                or PRODUCT_BASE_URL.format(goods_id=goods_id)
            ),
            "thumbnail_url": item.get("image_url"),

            "regular_price": cls._to_int(item.get("price")),
            "sale_price": cls._to_int(item.get("final_price")),
            "discount_rate": cls._to_float(
                item.get("discount_rate")
            ),

            "review_score": cls._to_float(
                item.get("review_score")
            ),
            "review_count": cls._to_int(
                str(
                    item.get("display_review_count")
                    or ""
                ).replace(",", "")
            ),

            "sellable_status": item.get("sellable_status"),
            "is_ad": bool(item.get("is_ad")),
        }

    # ============================================================
    # REQUEST VARIABLES
    # ============================================================

    @staticmethod
    def _build_variables(
        *,
        category_id: str,
        sort: str,
        page_id: str,
        after: str | None = None,
    ) -> dict[str, Any]:
        input_data: dict[str, Any] = {
            "display_category_id_list": [str(category_id)],
            "page_id": str(page_id),
            "filter_id_list": [str(sort)],
        }

        if after:
            input_data["after"] = after

        return {
            "input": input_data,
        }

    # ============================================================
    # CAST
    # ============================================================

    @staticmethod
    def _to_text(value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip()

        return text or None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

        text = str(value).strip().replace(",", "")

        if not text:
            return None

        try:
            return int(float(text))

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or value == "":
            return None

        try:
            return round(float(value), 2)

        except (TypeError, ValueError):
            return None
