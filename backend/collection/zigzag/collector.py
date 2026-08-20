from collections.abc import Iterator

import requests

from collection.core.http import (
    DEFAULT_HEADERS,
)

from .constant import (
    DEFAULT_PAGE_ID,
    GOODS_CARD_TYPE,
    PRODUCT_BASE_URL,
    REQUEST_TIMEOUT,
    SEARCH_RESULT_API_URL,
    SEARCH_RESULT_QUERY,
    ZIGZAG_BASE_URL,
)


class ZigzagCollectError(Exception):
    """지그재그 GraphQL API 수집 실패 시 사용하는 예외."""

    pass


class ZigzagCollector:
    """
    지그재그 수집 전용 Collector.

    무신사와 달리 지그재그는 카테고리 목록 GraphQL(GetSearchResult) 응답 안에
    상품 카드 정보가 전부 들어있어서, "목록 → 상세 재요청" 2단계가 필요 없음.

    책임:
    - 카테고리별 상품 리스트 수집 (GraphQL GetSearchResult, 커서 페이지네이션)
    - 상품 카드(UX_GOODS_CARD_ITEM) 파싱

    하지 않는 일:
    - Django ORM 저장
    - RawObject / CrawlJob 생성·수정
    - Celery 상태 변경
    - observed_at / rank 결정 (rank는 리스트 순서를 그대로 신뢰하는 상위 레이어가 부여)
    """

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout or REQUEST_TIMEOUT

        self.session = session or requests.Session()

        self.session.headers.update(DEFAULT_HEADERS)

        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Origin": ZIGZAG_BASE_URL,
                "Referer": f"{ZIGZAG_BASE_URL}/",
            }
        )

    # ============================================================
    # CONTEXT MANAGER
    # ============================================================

    def close(
        self,
    ):
        self.session.close()

    def __enter__(
        self,
    ):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        self.close()

    # ============================================================
    # COMMON REQUEST
    # ============================================================

    def _post_graphql(
        self,
        url: str,
        query: str,
        variables: dict,
    ) -> dict:
        try:
            response = self.session.post(
                url,
                json={
                    "query": query,
                    "variables": variables,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            raise ZigzagCollectError(f"POST 요청 실패: " f"{url} / {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ZigzagCollectError("JSON 응답 파싱 실패: " f"{url}") from exc

        if not isinstance(
            body,
            dict,
        ):
            raise ZigzagCollectError(f"JSON 응답 형식이 object가 아닙니다: {url}")

        errors = body.get("errors")

        if errors:
            raise ZigzagCollectError(f"GraphQL 응답 에러: {errors}")

        return body

    # ============================================================
    # CATEGORY PRODUCT LIST (PAGE-BY-PAGE)
    # ============================================================

    def iter_category_pages(
        self,
        *,
        category_id: str,
        sort: str = "200",
        page_id: str = DEFAULT_PAGE_ID,
        max_pages: int | None = None,
    ) -> Iterator[tuple[dict, list[dict], bool]]:
        """
        페이지 단위로 (raw_body, parsed_items, has_next)를 순서대로 yield.

        raw_body를 그대로 넘겨주는 이유:
        상위 레이어(pipeline)가 RawObject로 원본 응답을 보존해야 하기 때문.
        Collector 자체는 저장 방식(S3 등)을 모름.
        """
        after = None

        page = 0

        while True:
            variables = self._build_variables(
                category_id=category_id,
                sort=sort,
                page_id=page_id,
                after=after,
            )

            body = self._post_graphql(
                SEARCH_RESULT_API_URL,
                SEARCH_RESULT_QUERY,
                variables,
            )

            search_result = (body.get("data") or {}).get("search_result") or {}

            ui_item_list = search_result.get("ui_item_list") or []

            parsed_items = []

            for item in ui_item_list:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                if item.get("type") != GOODS_CARD_TYPE:
                    continue

                parsed = self._parse_goods_card(item)

                if parsed is not None:
                    parsed_items.append(parsed)

            has_next = bool(search_result.get("has_next"))

            end_cursor = search_result.get("end_cursor")

            yield body, parsed_items, has_next

            page += 1

            if not has_next or not end_cursor:
                break

            if max_pages is not None and page >= max_pages:
                break

            after = end_cursor

    def discover_category_products(
        self,
        *,
        category_id: str,
        sort: str = "200",
        page_id: str = DEFAULT_PAGE_ID,
        max_pages: int | None = None,
    ) -> list[dict]:
        """
        raw_body 없이 파싱된 상품 리스트만 전부 모아서 반환하는 단순 버전.
        RawObject 저장이 필요 없는 단발성 수집/디버깅에 사용.
        """
        results = []

        for _, parsed_items, _ in self.iter_category_pages(
            category_id=category_id,
            sort=sort,
            page_id=page_id,
            max_pages=max_pages,
        ):
            results.extend(parsed_items)

        return results

    # ============================================================
    # UTIL
    # ============================================================

    @staticmethod
    def _build_variables(
        *,
        category_id: str,
        sort: str,
        page_id: str,
        after: str | None = None,
    ) -> dict:
        input_data = {
            "display_category_id_list": [category_id],
            "page_id": page_id,
            "filter_id_list": [sort],
        }

        if after:
            input_data["after"] = after

        return {"input": input_data}

    @classmethod
    def _parse_goods_card(
        cls,
        item: dict,
    ) -> dict | None:
        goods_id = cls._to_int(item.get("goods_id"))

        if goods_id is None:
            return None

        managed_category_list = item.get("managed_category_list") or []

        # depth가 가장 큰(가장 구체적인) 카테고리를 대표 카테고리로 사용
        leaf_category = None

        if (
            isinstance(
                managed_category_list,
                list,
            )
            and managed_category_list
        ):
            candidates = [c for c in managed_category_list if isinstance(c, dict)]

            if candidates:
                leaf_category = max(
                    candidates,
                    key=lambda c: c.get("depth") or 0,
                )

        leaf_category = leaf_category or {}

        return {
            "source_product_id": str(goods_id),
            "product_name": item.get("title"),
            "store_id": item.get("shop_id"),
            "store_name": item.get("shop_name"),
            "is_brand": bool(item.get("is_brand")),
            "category_id": leaf_category.get("id"),
            "category_name": leaf_category.get("value"),
            "product_url": (
                item.get("product_url") or PRODUCT_BASE_URL.format(goods_id=goods_id)
            ),
            "thumbnail_url": item.get("image_url"),
            "regular_price": cls._to_int(item.get("price")),
            "sale_price": cls._to_int(item.get("final_price")),
            "discount_rate": cls._to_decimal(item.get("discount_rate")),
            "review_count": cls._to_int(
                str(item.get("display_review_count") or "").replace(",", "")
            ),
            "sellable_status": item.get("sellable_status"),
            "is_ad": bool(item.get("is_ad")),
        }

    @staticmethod
    def _to_int(
        value,
    ) -> int | None:
        if value is None or isinstance(
            value,
            bool,
        ):
            return None

        if isinstance(
            value,
            int,
        ):
            return value

        if isinstance(
            value,
            float,
        ):
            return int(value)

        text = str(value).strip().replace(",", "")

        if not text:
            return None

        try:
            return int(float(text))
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_decimal(
        value,
    ) -> float | None:
        if value is None:
            return None

        try:
            return round(
                float(value),
                2,
            )
        except (
            TypeError,
            ValueError,
        ):
            return None
