from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from collection.common.http import DEFAULT_HEADERS

from .constants import (
    DEFAULT_PAGE_ID,
    GOODS_CARD_TYPE,
    PRODUCT_BASE_URL,
    REQUEST_TIMEOUT,
    SEARCH_RESULT_API_URL,
    SEARCH_RESULT_QUERY,
    ZIGZAG_BASE_URL,
)


SHOP_COMPONENT_API_URL = (
    "https://api.zigzag.kr/api/2/graphql/GetComponentList"
)

SHOP_COMPONENT_QUERY = 'fragment ShopUxButton on ShopUxButton { text is_html_text style link_url } fragment ShopUxProductCardItem on ShopUxProductCardItem { product { shop_product_no catalog_product_id shop_id url image_url webp_image_url name price discount_rate payment_type shipping_fee_type sales_status } is_saved_product shop_name browsing_type is_zpay_discount discount_info { image_url title color } final_price_with_currency { currency decimal price_without_decimal display_currency is_currency_prefix } final_price max_price is_display_not_zpay ranking column_count review_count review_score fomo { ...ShopUxProductCardFomo } managed_category_list { id category_id value depth key } badge_list { ...ShopUxBadge } thumbnail_nudge_badge_list { ...ShopUxBadge } thumbnail_emblem_badge_list { ...ShopUxBadge } metadata_emblem_badge_list { ...ShopUxBadge } brand_name_badge_list { ...ShopUxBadge } one_day_delivery { text color { normal dark } html { normal dark } } is_plp_v2 } fragment ShopUxProductCardFomo on ShopUxProductCardFomo { icon_image_url text } fragment ShopUxBadge on ShopUxBadge { image_url dark_image_url small_image_url small_dark_image_url image_size { width height } small_image_size { width height } } fragment ShopUxText on ShopUxText { text is_html_text style } fragment ShopUxFilterItem on ShopUxFilterItem { id name description image_url selected disabled ubl { ...ShopUxUbl } } fragment ShopUxUbl on ShopUxUbl { object { section type id idx url } server_log } fragment ShopUxFilterChip on ShopUxFilterChip { id name selected icon { ...ShopUxCommonImage } type ubl { ...ShopUxUbl } } fragment ShopUxCommonImage on ShopUxCommonImage { url { normal dark } webp_url { normal dark } } fragment ShopUxCommonText on ShopUxCommonText { text color { ...ShopUxCommonTextColor } html { normal dark } } fragment ShopUxCommonTextColor on ShopUxCommonTextColor { normal dark } fragment ShopUxCommonColor on ShopUxCommonColor { normal dark } fragment ShopUxImage on ShopUxImage { image_url aspect_Ratio link_url } fragment ShopUxCommonButton on ShopUxCommonButton { text { ...ShopUxCommonText } image { ...ShopUxCommonImage } landing_url background_color { ...ShopUxCommonColor } ubl { ...ShopUxUbl } } fragment ShopUxHeaderComponent on ShopUxHeaderComponent { title { ...ShopUxCommonText } subtitle { ...ShopUxCommonText } image { ...ShopUxCommonImage } button { ...ShopUxCommonButton } } query GetComponentList( $shop_id: ID! $category_id: ID $after_id: ID $sorting_item_id: ID $check_button_item_ids: [ID] $sub_filter_id_list: [ID] $pdp_product_id: ID ) { shop_ux_component_list( shop_id: $shop_id category_id: $category_id after_id: $after_id sorting_item_id: $sorting_item_id check_button_item_ids: $check_button_item_ids sub_filter_id_list: $sub_filter_id_list pdp_product_id: $pdp_product_id ) { after_id has_next_page category_list { id name } item_list { type  ... on ShopUxLookBook { title image_url_list action_button { ...ShopUxButton } }  ... on ShopUxImageBannerAndList { title landing_url image_url product_list { ...ShopUxProductCardItem } action_button { ...ShopUxButton } }  ... on ShopUxProductCarousel { item_column_count component_list { ...ShopUxProductCardItem } more_button { ...ShopUxButton } }  ... on ShopUxChipAndSorting { main_title { ...ShopUxText } sub_title { ...ShopUxText } total_count sorting_item_list { ...ShopUxFilterItem } filter_chip_item_list { ...ShopUxFilterChip common_status_text { normal { ...ShopUxCommonText } selected { ...ShopUxCommonText } disabled { ...ShopUxCommonText } } } column_shifting_button_list { column_count icon_url { normal } ubl { ...ShopUxUbl } } }  ... on ShopUxBackgroundEntryBanner { common_title { ...ShopUxCommonText } landing_url background_color { ...ShopUxCommonColor } }  ... on ShopUxProductGroup { contents_type main_title { ...ShopUxText } sub_title { ...ShopUxText } image { ...ShopUxImage } product_carousel { item_column_count component_list { ...ShopUxProductCardItem } more_button { ...ShopUxButton } } more_button { ...ShopUxButton } title_icon_button { ...ShopUxCommonButton } background_color { ...ShopUxCommonColor } }  ... on ShopUxFullLookBook { common_title { ...ShopUxCommonText } header { ...ShopUxHeaderComponent } common_image { ...ShopUxCommonImage } landing_url ubl { ...ShopUxUbl } }  ... on ShopUxImageCard { header { ...ShopUxHeaderComponent } common_image { ...ShopUxCommonImage } product_list { ...ShopUxProductCardItem } ubl { ...ShopUxUbl } }  ... on ShopUxBestProductCarousel { header { ...ShopUxHeaderComponent } category_group_list { category { ...ShopUxFilterChip } item_list { ...ShopUxProductCardItem } ubl { ...ShopUxUbl } action_button { ...ShopUxButton ubl { ...ShopUxUbl } } item_column_count } }  ...ShopUxProductCardItem } } }'


class ZigzagCollectError(Exception):
    pass


class ZigzagCollector:
    """
    FEEDIT Zigzag collector.

    지원:
    1. 기존 지그재그 카테고리 GraphQL 상품 수집
    2. 지그재그 스토어 페이지 프로필 수집
    3. GetComponentList GraphQL 기반 스토어 상품 전체 페이지네이션
    4. 상품 관심도(FOMO), 리뷰, 랭킹, 배지, 카테고리, 배송/결제 정보 수집

    저장/ORM/Celery는 하지 않는다.
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

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ============================================================
    # COMMON
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
            raise ZigzagCollectError(
                f"POST 요청 실패: {url} / {exc}"
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ZigzagCollectError(
                f"JSON 응답 파싱 실패: {url}"
            ) from exc

        if not isinstance(body, dict):
            raise ZigzagCollectError(
                f"JSON 응답 형식이 object가 아닙니다: {url}"
            )

        if body.get("errors"):
            raise ZigzagCollectError(
                f"GraphQL 응답 에러: {body['errors']}"
            )

        return body

    def _get_html(
        self,
        url: str,
    ) -> tuple[str, object]:
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ZigzagCollectError(
                f"스토어 페이지 요청 실패: {url} / {exc}"
            ) from exc

        return response.text, response

    # ============================================================
    # SHOP
    # ============================================================

    def collect_shop(
        self,
        shop_url: str,
        *,
        product_limit: int | None = 100,
        max_pages: int | None = None,
        collect_products: bool = True,
    ) -> dict:
        """
        예:
            https://zigzag.kr/naeni

        반환:
            shop
            categories
            banners
            coupon
            products
            component_summary
        """
        source_url = self._normalize_shop_url(shop_url)
        page_html, response = self._get_html(source_url)

        page_data = self._extract_store_page_data(page_html)
        shop = self._parse_shop_profile(
            page_data,
            source_url=source_url,
            page_html=page_html,
        )

        shop_id = shop.get("source_brand_id")
        if not shop_id:
            raise ZigzagCollectError(
                f"shop_id를 찾지 못했습니다: {source_url}"
            )

        products = []
        component_summary = {}
        graphql_categories = []

        if collect_products:
            (
                products,
                component_summary,
                graphql_categories,
            ) = self.collect_shop_products(
                shop_id=str(shop_id),
                limit=product_limit,
                max_pages=max_pages,
            )

        raw_categories = self._merge_categories(
            page_data.get("categories") or [],
            graphql_categories,
        )

        shop_id_text = str(
            shop.get("source_brand_id") or ""
        )

        categories = []

        for item in raw_categories:

            if not isinstance(
                item,
                dict,
            ):
                continue

            category_id = self._clean_text(
                item.get("id")
            )

            category_name = self._clean_text(
                item.get("name")
            )

            if not category_id:
                continue

            if not category_name:
                continue

            # 전체 탭 제거
            if category_id == "0":
                continue

            if category_name == "전체":
                continue

            # shop 자체가 category 후보로 잘못 잡힌 경우 제거
            if (
                shop_id_text
                and category_id
                == shop_id_text
            ):
                continue

            if (
                shop.get("name")
                and category_name
                == shop.get("name")
            ):
                continue

            categories.append(
                {
                    "id": category_id,
                    "name": category_name,
                }
            )

        return {
            "source_url": source_url,
            "collected_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "http_status": getattr(
                response,
                "status_code",
                None,
            ),
            "content_type": (
                getattr(
                    response,
                    "headers",
                    {},
                ).get("Content-Type")
                if getattr(response, "headers", None)
                else None
            ),
            "shop": shop,
            "categories": categories,
            "banners": page_data.get("banners") or [],
            "coupon": self._clean_coupon(
                page_data.get("coupon")
            ),
            "products": products,
            "raw_profile": page_data.get("raw_shop_information"),
        }

    def collect_shop_products(
        self,
        *,
        shop_id: str,
        limit: int | None = 100,
        max_pages: int | None = None,
        category_id: str | None = None,
        sorting_item_id: str | None = None,
    ) -> tuple[list[dict], dict, list[dict]]:
        """
        스토어 GetComponentList 전체 페이지네이션.

        중복 product id 제거.
        """
        products = []
        seen = set()
        component_counter = {}
        categories_by_id = {}

        for page_no, body in enumerate(
            self.iter_shop_component_pages(
                shop_id=shop_id,
                category_id=category_id,
                sorting_item_id=sorting_item_id,
                max_pages=max_pages,
            ),
            start=1,
        ):
            root = (
                (body.get("data") or {})
                .get("shop_ux_component_list")
                or {}
            )

            for cat in root.get("category_list") or []:
                if not isinstance(cat, dict):
                    continue
                cat_id = self._clean_text(cat.get("id"))
                if cat_id:
                    categories_by_id[cat_id] = {
                        "id": cat_id,
                        "name": self._clean_text(cat.get("name")),
                    }

            item_list = root.get("item_list") or []
            for item in item_list:
                if not isinstance(item, dict):
                    continue

                item_type = self._clean_text(
                    item.get("type")
                ) or "UNKNOWN"

                component_counter[item_type] = (
                    component_counter.get(item_type, 0)
                    + 1
                )

                # 일반 PRODUCT
                if item_type == "PRODUCT":
                    parsed = self._parse_shop_product_item(
                        item,
                        fallback_shop_id=shop_id,
                        product_section="GENERAL",
                    )
                    if parsed:
                        pid = parsed["source_product_id"]
                        if pid not in seen:
                            seen.add(pid)
                            products.append(parsed)

                # BEST_PRODUCT_CAROUSEL 내부 상품도 수집
                elif item_type == "BEST_PRODUCT_CAROUSEL":
                    for card in self._walk_product_cards(item):
                        parsed = self._parse_shop_product_item(
                            card,
                            fallback_shop_id=shop_id,
                            product_section="BEST",
                        )
                        if parsed:
                            pid = parsed["source_product_id"]
                            if pid not in seen:
                                seen.add(pid)
                                products.append(parsed)

                if (
                    limit is not None
                    and len(products) >= limit
                ):
                    return (
                        products[:limit],
                        component_counter,
                        list(categories_by_id.values()),
                    )

        return (
            products,
            component_counter,
            list(categories_by_id.values()),
        )

    def iter_shop_component_pages(
        self,
        *,
        shop_id: str,
        category_id: str | None = None,
        sorting_item_id: str | None = None,
        check_button_item_ids: list[str] | None = None,
        sub_filter_id_list: list[str] | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict]:
        after_id = None
        page = 0

        while True:
            variables = {
                "shop_id": str(shop_id),
                "check_button_item_ids": (
                    check_button_item_ids or []
                ),
                "sub_filter_id_list": (
                    sub_filter_id_list or []
                ),
                "sorting_item_id": sorting_item_id,
            }

            if category_id:
                variables["category_id"] = str(
                    category_id
                )

            if after_id:
                variables["after_id"] = after_id

            body = self._post_graphql(
                SHOP_COMPONENT_API_URL,
                SHOP_COMPONENT_QUERY,
                variables,
            )

            yield body
            page += 1

            root = (
                (body.get("data") or {})
                .get("shop_ux_component_list")
                or {}
            )

            if not root.get("has_next_page"):
                break

            after_id = root.get("after_id")
            if not after_id:
                break

            if (
                max_pages is not None
                and page >= max_pages
            ):
                break

    # ============================================================
    # SHOP PAGE PROFILE PARSING
    # ============================================================

    def _extract_store_page_data(
        self,
        page_html: str,
    ) -> dict:
        result = {
            "raw_shop_information": None,
            "categories": [],
            "banners": [],
            "coupon": None,
            "total_product_count": None,
        }

        shop_info = self._extract_json_object_after_key(
            page_html,
            "shop_information",
        )

        if isinstance(shop_info, dict):
            result["raw_shop_information"] = shop_info

            banner_group = (
                self._extract_json_object_after_key(
                    page_html,
                    "banner_group",
                )
            )

            if isinstance(banner_group, dict):
                result["banners"] = (
                    banner_group.get("banner_list")
                    or []
                )

            coupon = (
                shop_info.get("representative_coupon_v2")
                or shop_info.get("representative_coupon")
            )
            if isinstance(coupon, dict):
                result["coupon"] = coupon

        categories = self._extract_category_candidates(
            page_html
        )
        result["categories"] = categories

        total_count = self._extract_first_int_by_keys(
            page_html,
            [
                "total_count",
                "totalCount",
                "product_count",
                "productCount",
            ],
        )
        result["total_product_count"] = total_count

        return result

    def _parse_shop_profile(
        self,
        page_data: dict,
        *,
        source_url: str,
        page_html: str,
    ) -> dict:
        info = (
            page_data.get("raw_shop_information")
            or {}
        )

        main_domain = self._clean_text(
            info.get("main_domain")
        )

        logo = info.get("logo_image") or {}
        logo_url = logo.get("url") or {}

        typical_image_url = self._clean_text(
            info.get("typical_image_url")
        )

        image_url = (
            typical_image_url
            or self._clean_text(
                logo_url.get("normal")
                if isinstance(logo_url, dict)
                else None
            )
            or self._extract_meta_content(
                page_html,
                property_name="og:image",
            )
        )

        style_list = []
        for item in info.get("style_list") or []:
            if isinstance(item, dict):
                value = self._clean_text(
                    item.get("value")
                )
            else:
                value = self._clean_text(item)
            if value and value not in style_list:
                style_list.append(value)

        age_list = []
        for item in info.get("age_list") or []:
            if isinstance(item, dict):
                value = self._clean_text(
                    item.get("value")
                    or item.get("name")
                    or item.get("id")
                )
            else:
                value = self._clean_text(item)
            if value and value not in age_list:
                age_list.append(value)

        seller_badges = []
        for badge in info.get("seller_badge") or []:
            if not isinstance(badge, dict):
                continue
            text_obj = badge.get("text") or {}
            text = (
                self._clean_text(text_obj.get("text"))
                if isinstance(text_obj, dict)
                else self._clean_text(text_obj)
            )
            if text:
                seller_badges.append(text)

        profile_url = (
            f"https://zigzag.kr/{main_domain}"
            if main_domain
            else source_url
        )

        return {
            "source_brand_id": self._clean_text(
                info.get("id")
            ),
            "name": self._clean_text(
                info.get("name")
            ),
            "english_name": None,
            "main_domain": main_domain,
            "image_url": image_url,
            "description": self._clean_text(
                info.get("comment")
            ),
            "target_age": age_list or None,
            "style_list": style_list,
            "source_profile_url": profile_url,
            "bookmark_count": self._to_int(
                info.get("bookmark_count")
            ),
            "seller_badges": seller_badges,
            "total_product_count": page_data.get(
                "total_product_count"
            ),
        }

    # ============================================================
    # PRODUCT PARSING
    # ============================================================

    def _walk_product_cards(
        self,
        value,
    ):
        if isinstance(value, dict):
            if isinstance(value.get("product"), dict):
                yield value

            for child in value.values():
                yield from self._walk_product_cards(
                    child
                )

        elif isinstance(value, list):
            for child in value:
                yield from self._walk_product_cards(
                    child
                )

    def _parse_shop_product_item(
        self,
        item: dict,
        *,
        fallback_shop_id: str | None = None,
        product_section: str = "GENERAL",
    ) -> dict | None:
        product = item.get("product") or {}
        if not isinstance(product, dict):
            return None

        source_product_id = self._clean_text(
            product.get("catalog_product_id")
            or product.get("shop_product_no")
        )

        if not source_product_id:
            return None

        managed_categories = (
            item.get("managed_category_list")
            or []
        )

        leaf = self._deepest_category(
            managed_categories
        )

        fomo = item.get("fomo") or {}
        fomo_text = (
            self._clean_text(fomo.get("text"))
            if isinstance(fomo, dict)
            else None
        )

        currency_obj = (
            item.get("final_price_with_currency")
            or {}
        )

        one_day_delivery = (
            item.get("one_day_delivery")
            or {}
        )

        return {
            "source_product_id": source_product_id,
            "product_section": product_section,
            "shop_product_no": self._clean_text(
                product.get("shop_product_no")
            ),
            "store_id": self._clean_text(
                product.get("shop_id")
            ) or fallback_shop_id,
            "store_name": self._clean_text(
                item.get("shop_name")
            ),
            "product_name": self._clean_text(
                product.get("name")
            ),
            "product_url": self._clean_text(
                product.get("url")
            ),
            "thumbnail_url": self._clean_text(
                product.get("image_url")
            ),
            "webp_thumbnail_url": self._clean_text(
                product.get("webp_image_url")
            ),
            "regular_price": self._to_int(
                product.get("price")
            ),
            "sale_price": self._to_int(
                item.get("final_price")
            ),
            "max_price": self._to_int(
                item.get("max_price")
            ),
            "discount_rate": self._to_decimal(
                product.get("discount_rate")
            ),
            "currency": self._clean_text(
                currency_obj.get("currency")
            ),
            "payment_type": self._clean_text(
                product.get("payment_type")
            ),
            "shipping_fee_type": self._clean_text(
                product.get("shipping_fee_type")
            ),
            "sales_status": self._clean_text(
                product.get("sales_status")
            ),
            "is_zpay_discount": bool(
                item.get("is_zpay_discount")
            ),
            "ranking": self._to_int(
                item.get("ranking")
            ),
            "review_count": self._to_int(
                item.get("review_count")
            ),
            "review_score": self._to_decimal(
                item.get("review_score")
            ),
            "fomo_text": fomo_text,
            "interest_count": self._parse_korean_count(
                fomo_text
            ),
            "category_id": leaf.get("category_id")
            or leaf.get("id"),
            "category_name": leaf.get("value"),
            "category_path": managed_categories,
            "one_day_delivery": (
                one_day_delivery
                if isinstance(
                    one_day_delivery,
                    dict,
                )
                else None
            ),
            "badges": {
                "badge_list": item.get("badge_list") or [],
                "thumbnail_nudge": (
                    item.get(
                        "thumbnail_nudge_badge_list"
                    )
                    or []
                ),
                "thumbnail_emblem": (
                    item.get(
                        "thumbnail_emblem_badge_list"
                    )
                    or []
                ),
                "metadata_emblem": (
                    item.get(
                        "metadata_emblem_badge_list"
                    )
                    or []
                ),
                "brand_name_badge": (
                    item.get(
                        "brand_name_badge_list"
                    )
                    or []
                ),
            },
        }

    # ============================================================
    # EXISTING CATEGORY GRAPHQL
    # ============================================================

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

            search_result = (
                (body.get("data") or {})
                .get("search_result")
                or {}
            )

            parsed_items = []

            for item in (
                search_result.get("ui_item_list")
                or []
            ):
                if not isinstance(item, dict):
                    continue
                if item.get("type") != GOODS_CARD_TYPE:
                    continue

                parsed = self._parse_goods_card(item)
                if parsed is not None:
                    parsed_items.append(parsed)

            has_next = bool(
                search_result.get("has_next")
            )
            end_cursor = search_result.get(
                "end_cursor"
            )

            yield body, parsed_items, has_next

            page += 1

            if not has_next or not end_cursor:
                break

            if (
                max_pages is not None
                and page >= max_pages
            ):
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
    # HELPERS
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
            "display_category_id_list": [
                category_id
            ],
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
        goods_id = cls._to_int(
            item.get("goods_id")
        )

        if goods_id is None:
            return None

        managed_category_list = (
            item.get("managed_category_list")
            or []
        )

        leaf = cls._deepest_category(
            managed_category_list
        )

        return {
            "source_product_id": str(
                goods_id
            ),
            "product_name": item.get("title"),
            "store_id": item.get("shop_id"),
            "store_name": item.get("shop_name"),
            "is_brand": bool(
                item.get("is_brand")
            ),
            "category_id": (
                leaf.get("category_id")
                or leaf.get("id")
            ),
            "category_name": leaf.get("value"),
            "category_path": managed_category_list,
            "product_url": (
                item.get("product_url")
                or PRODUCT_BASE_URL.format(
                    goods_id=goods_id
                )
            ),
            "thumbnail_url": item.get(
                "image_url"
            ),
            "regular_price": cls._to_int(
                item.get("price")
            ),
            "sale_price": cls._to_int(
                item.get("final_price")
            ),
            "discount_rate": cls._to_decimal(
                item.get("discount_rate")
            ),
            "review_count": cls._to_int(
                str(
                    item.get(
                        "display_review_count"
                    )
                    or ""
                ).replace(",", "")
            ),
            "review_score": cls._to_decimal(
                item.get("review_score")
            ),
            "sellable_status": item.get(
                "sellable_status"
            ),
            "is_ad": bool(
                item.get("is_ad")
            ),
        }

    @staticmethod
    def _deepest_category(
        categories,
    ) -> dict:
        if not isinstance(categories, list):
            return {}

        candidates = [
            c
            for c in categories
            if isinstance(c, dict)
        ]

        if not candidates:
            return {}

        return max(
            candidates,
            key=lambda c: (
                ZigzagCollector._to_int(
                    c.get("depth")
                )
                or 0
            ),
        )

    @staticmethod
    def _normalize_shop_url(
        url: str,
    ) -> str:
        if not url:
            raise ZigzagCollectError(
                "shop_url이 비어 있습니다."
            )

        if url.startswith("/"):
            url = f"https://zigzag.kr{url}"

        parsed = urlparse(url)

        if not parsed.scheme:
            url = f"https://zigzag.kr/{url.lstrip('/')}"

        return url.split("?")[0].rstrip("/")

    @staticmethod
    def _clean_text(value):
        if value is None:
            return None

        text = str(value).strip()

        return text or None

    @staticmethod
    def _to_int(value):
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, int):
            return value

        try:
            return int(
                float(
                    str(value)
                    .strip()
                    .replace(",", "")
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_decimal(value):
        if value is None:
            return None

        try:
            return round(
                float(value),
                4,
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _parse_korean_count(
        text: str | None,
    ) -> int | None:
        if not text:
            return None

        value = (
            str(text)
            .replace("관심", "")
            .strip()
            .replace(",", "")
        )

        match = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*([천만]?)",
            value,
        )

        if not match:
            return None

        number = float(
            match.group(1)
        )

        unit = match.group(2)

        if unit == "천":
            number *= 1_000
        elif unit == "만":
            number *= 10_000

        return int(number)

    @classmethod
    def _clean_coupon(
        cls,
        coupon: dict | None,
    ) -> dict | None:

        if not isinstance(
            coupon,
            dict,
        ):
            return None

        badge_info = (
            coupon.get("badge_info")
            or {}
        )

        badge_text = (
            badge_info.get("text")
            or {}
        )

        main_title = (
            coupon.get("main_title")
            or {}
        )

        result = {
            "badge": cls._clean_text(
                badge_text.get("text")
                if isinstance(
                    badge_text,
                    dict,
                )
                else None
            ),
            "title": cls._clean_text(
                main_title.get("text")
                if isinstance(
                    main_title,
                    dict,
                )
                else None
            ),
            "day_limit": cls._to_int(
                coupon.get("day_limit")
            ),
            "date_issue_end": cls._to_int(
                coupon.get("date_issue_end")
            ),
        }

        return {
            key: value
            for key, value in result.items()
            if value is not None
        } or None

    @staticmethod
    def _extract_meta_content(
        page_html: str,
        *,
        property_name: str,
    ) -> str | None:
        soup = BeautifulSoup(
            page_html,
            "html.parser",
        )

        tag = soup.find(
            "meta",
            attrs={"property": property_name},
        )

        if not tag:
            return None

        return ZigzagCollector._clean_text(
            tag.get("content")
        )

    @staticmethod
    def _extract_json_object_after_key(
        text: str,
        key: str,
    ) -> dict | None:
        marker = f'"{key}":'
        index = text.find(marker)

        if index < 0:
            return None

        start = text.find(
            "{",
            index + len(marker),
        )

        if start < 0:
            return None

        decoder = json.JSONDecoder()

        try:
            value, _ = decoder.raw_decode(
                text[start:]
            )
        except json.JSONDecodeError:
            return None

        return (
            value
            if isinstance(value, dict)
            else None
        )

    @classmethod
    def _extract_category_candidates(
        cls,
        page_html: str,
    ) -> list[dict]:
        """
        페이지에 포함된 category id/name 후보를 보수적으로 수집.
        """
        result = []
        seen = set()

        pattern = re.compile(
            r'"id":"([^"]+)"\s*,\s*"name":"([^"]+)"'
        )

        for match in pattern.finditer(
            page_html
        ):
            category_id = cls._clean_text(
                match.group(1)
            )
            category_name = cls._clean_text(
                html_lib.unescape(
                    match.group(2)
                )
            )

            if not category_id or not category_name:
                continue

            # 너무 광범위한 일반 object 제외.
            if not category_id.isdigit():
                continue

            key = (
                category_id,
                category_name,
            )

            if key in seen:
                continue

            seen.add(key)

            result.append(
                {
                    "id": category_id,
                    "name": category_name,
                }
            )

        return result

    @staticmethod
    def _merge_categories(
        left: list[dict],
        right: list[dict],
    ) -> list[dict]:
        result = []
        seen = set()

        for item in [
            *(left or []),
            *(right or []),
        ]:
            if not isinstance(item, dict):
                continue

            category_id = (
                str(item.get("id")).strip()
                if item.get("id") is not None
                else None
            )

            name = (
                str(item.get("name")).strip()
                if item.get("name") is not None
                else None
            )

            key = (
                category_id,
                name,
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(item)

        return result

    @classmethod
    def _extract_first_int_by_keys(
        cls,
        text: str,
        keys: list[str],
    ) -> int | None:
        for key in keys:
            patterns = [
                rf'"{re.escape(key)}":\s*([0-9]+)',
                rf"'{re.escape(key)}':\s*([0-9]+)",
            ]

            for pattern in patterns:
                match = re.search(
                    pattern,
                    text,
                    flags=re.I,
                )
                if match:
                    return cls._to_int(
                        match.group(1)
                    )

        return None
