from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .constants import (
    IMAGE_BASE_URL,
    PRODUCT_CARD_SELECTOR,
    PRODUCT_LINK_SELECTOR,
    ZIGZAG_BASE_URL,
)
from .exceptions import ZigzagParseError


class ZigzagParser:
    """
    ZIGZAG Parser.

    PRODUCT:
    - __NEXT_DATA__
    - dehydratedState
    - getPdpBaseInfo

    RANKING:
    - Playwright로 렌더링된 HTML
    - product-card
    - product-card-link

    저장/S3/DB 처리는 하지 않는다.
    """

    # ============================================================
    # PRODUCT
    # ============================================================

    @classmethod
    def parse_product(
        cls,
        html: str,
        *,
        product_id: int | None = None,
    ) -> dict:
        if not html or not html.strip():
            raise ZigzagParseError(
                "상품 HTML이 비어 있습니다."
            )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        next_data = cls._extract_next_data(
            soup
        )

        state = cls._extract_product_state(
            next_data,
            product_id=product_id,
        )

        product = cls._as_dict(
            state.get("product")
        )

        shop = cls._as_dict(
            state.get("shop")
        )

        resolved_product_id = cls._to_int(
            product.get("id")
        )

        if resolved_product_id is None:
            raise ZigzagParseError(
                "상품 ID를 찾을 수 없습니다."
            )

        if not cls._clean_text(
            product.get("name")
        ):
            raise ZigzagParseError(
                "상품명이 없습니다."
            )

        return {
            "product": cls._parse_product(
                product,
                shop=shop,
            ),
        }

    # ============================================================
    # RANKING
    # ============================================================

    @classmethod
    def parse_ranking(
        cls,
        html: str,
    ) -> list[dict]:
        """
        Playwright로 렌더링된 ZIGZAG 목록 HTML에서
        인기순 상품 목록을 추출한다.

        반환 예:
        {
            "rank": 1,
            "product_id": 169628128,
            "product_url": "...",
            "shop_name": "...",
            "name": "...",
            "list_price": 28800,
            "list_discount_rate": 37.0,
            "review_score": 4.8,
            "review_count": 601,
            "image_url": "..."
        }
        """

        if not html or not html.strip():
            raise ZigzagParseError(
                "RANKING HTML이 비어 있습니다."
            )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        cards = soup.select(
            PRODUCT_CARD_SELECTOR
        )

        result: list[dict] = []
        seen: set[int] = set()

        fallback_rank = 1

        for card in cards:
            link = card.select_one(
                PRODUCT_LINK_SELECTOR
            )

            if link is None:
                continue

            href = cls._clean_text(
                link.get("href")
            )

            if not href:
                continue

            product_id = (
                cls._extract_product_id(
                    href
                )
            )

            if product_id is None:
                continue

            if product_id in seen:
                continue

            seen.add(
                product_id
            )

            texts = cls._leaf_texts(
                card
            )

            result.append(
                {
                    "rank":
                        fallback_rank,

                    "product_id":
                        product_id,

                    "product_url":
                        urljoin(
                            ZIGZAG_BASE_URL,
                            href,
                        ),

                    "shop_name": (
                        texts[0]
                        if len(texts) > 0
                        else None
                    ),

                    "name": (
                        texts[1]
                        if len(texts) > 1
                        else None
                    ),

                    "list_price":
                        cls._find_price(
                            texts
                        ),

                    "list_discount_rate":
                        cls._find_discount(
                            texts
                        ),

                    "review_score":
                        cls._find_review_score(
                            texts
                        ),

                    "review_count":
                        cls._find_review_count(
                            texts
                        ),

                    "image_url":
                        cls._find_card_image(
                            card
                        ),
                }
            )

            fallback_rank += 1

        return result

    # ============================================================
    # RANKING HELPERS
    # ============================================================

    @classmethod
    def _leaf_texts(
        cls,
        card,
    ) -> list[str]:
        """
        기존 config.yaml의 leaf:true 동작.

        div/span/p 중에서
        하위에 또 div/span/p가 없는 요소만 사용한다.
        """

        result: list[str] = []

        for tag in card.select(
            "div, span, p"
        ):
            has_child = any(
                getattr(
                    child,
                    "name",
                    None,
                )
                in {
                    "div",
                    "span",
                    "p",
                }
                for child in tag.children
            )

            if has_child:
                continue

            text = cls._clean_text(
                tag.get_text(
                    " ",
                    strip=True,
                )
            )

            if not text:
                continue

            if text in result:
                continue

            result.append(
                text
            )

        return result

    @staticmethod
    def _extract_product_id(
        url: str,
    ) -> int | None:
        if not url:
            return None

        match = re.search(
            r"/catalog/products/(\d+)",
            str(url),
        )

        if not match:
            return None

        return int(
            match.group(1)
        )

    @classmethod
    def _find_price(
        cls,
        texts: list[str],
    ) -> int | None:
        """
        예:
        18,000
        36000
        """

        for text in texts:
            value = str(
                text
            ).strip()

            if not re.fullmatch(
                r"[\d,]{3,}",
                value,
            ):
                continue

            number = cls._to_int(
                value
            )

            if (
                number is not None
                and number >= 1000
            ):
                return number

        return None

    @classmethod
    def _find_discount(
        cls,
        texts: list[str],
    ) -> float | None:
        """
        예:
        22%
        37%
        """

        for text in texts:
            match = re.fullmatch(
                r"(\d{1,3})%",
                str(text).strip(),
            )

            if not match:
                continue

            return cls._to_float(
                match.group(1)
            )

        return None

    @classmethod
    def _find_review_score(
        cls,
        texts: list[str],
    ) -> float | None:
        """
        예:
        4.8
        5
        """

        for text in texts:
            value = str(
                text
            ).strip()

            if not re.fullmatch(
                r"[0-5](?:\.\d)?",
                value,
            ):
                continue

            number = cls._to_float(
                value
            )

            if (
                number is not None
                and 0 <= number <= 5
            ):
                return number

        return None

    @classmethod
    def _find_review_count(
        cls,
        texts: list[str],
    ) -> int | None:
        """
        예:
        (601)
        (1,203)
        """

        for text in texts:
            match = re.fullmatch(
                r"\(([\d,]+)\)",
                str(text).strip(),
            )

            if not match:
                continue

            return cls._to_int(
                match.group(1)
            )

        return None

    @classmethod
    def _find_card_image(
        cls,
        card,
    ) -> str | None:
        image = card.select_one(
            'img[src*="product-image"]'
        )

        if image is None:
            return None

        return cls._normalize_image_url(
            image.get("src")
        )

    # ============================================================
    # NEXT DATA
    # ============================================================

    @staticmethod
    def _extract_next_data(
        soup: BeautifulSoup,
    ) -> dict:
        script = soup.find(
            "script",
            id="__NEXT_DATA__",
        )

        if script is None:
            raise ZigzagParseError(
                "__NEXT_DATA__ script를 "
                "찾을 수 없습니다."
            )

        raw = (
            script.string
            or script.get_text()
            or ""
        )

        try:
            data = json.loads(
                raw
            )

        except json.JSONDecodeError as exc:
            raise ZigzagParseError(
                "__NEXT_DATA__ JSON "
                f"파싱 실패: {exc}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise ZigzagParseError(
                "__NEXT_DATA__가 "
                "object 형식이 아닙니다."
            )

        return data

    # ============================================================
    # PRODUCT STATE
    # ============================================================

    @classmethod
    def _extract_product_state(
        cls,
        next_data: dict,
        *,
        product_id: int | None,
    ) -> dict:
        queries = cls._get_path(
            next_data,
            (
                "props.pageProps."
                "dehydratedState.queries"
            ),
        )

        if not isinstance(
            queries,
            list,
        ):
            raise ZigzagParseError(
                "dehydratedState queries를 "
                "찾을 수 없습니다."
            )

        fallback = None

        for query in queries:
            if not isinstance(
                query,
                dict,
            ):
                continue

            query_key = query.get(
                "queryKey"
            )

            if (
                not isinstance(
                    query_key,
                    list,
                )
                or not query_key
                or query_key[0]
                != "getPdpBaseInfo"
            ):
                continue

            data = cls._get_path(
                query,
                "state.data",
            )

            if not isinstance(
                data,
                dict,
            ):
                continue

            if fallback is None:
                fallback = data

            if (
                product_id is None
                or any(
                    str(value)
                    == str(product_id)
                    for value
                    in query_key[1:]
                )
            ):
                return data

        if fallback is not None:
            return fallback

        raise ZigzagParseError(
            "getPdpBaseInfo 상품 상태를 "
            "찾을 수 없습니다."
        )

    # ============================================================
    # PRODUCT NORMALIZE
    # ============================================================

    @classmethod
    def _parse_product(
        cls,
        data: dict,
        *,
        shop: dict,
    ) -> dict:
        categories = data.get(
            "managed_category_list"
        )

        if not isinstance(
            categories,
            list,
        ):
            categories = []

        detail_content = cls._parse_detail_content(
            data.get("description")
        )

        return {
            "shop": {
                "domain": cls._clean_text(
                    shop.get("main_domain")
                ),
                "bookmark_count": cls._to_int(
                    shop.get("bookmark_count")
                ),
            },

            "category_path": [
                value
                for value in (
                    cls._category_value(categories, index)
                    for index in range(len(categories))
                )
                if value
            ],

            "category_code": cls._clean_text(
                data.get("category_key")
            ),

            "pricing": cls._parse_snapshot(data),

            "thumbnail_url":
                cls._normalize_image_url(
                    cls._get_path(
                        data,
                        (
                            "product_image_list."
                            "0.url"
                        ),
                    )
                ),

            "description": cls._clean_text(
                data.get("description")
            ),

            "detail_image_urls": [
                item["image_url"]
                for item in detail_content["images"]
            ],

            "sales_status":
                cls._clean_text(
                    data.get(
                        "sales_status"
                    )
                ),

        }

    # ============================================================
    # SNAPSHOT
    # ============================================================

    @classmethod
    def _parse_snapshot(
        cls,
        data: dict,
    ) -> dict:
        price = cls._as_dict(
            data.get(
                "product_price"
            )
        )

        final = cls._as_dict(
            price.get(
                "final_discount_info"
            )
        )

        store = cls._as_dict(
            price.get(
                "store_discount_info"
            )
        )

        sale_price = cls._to_int(
            final.get(
                "discount_price"
            )
        )

        discount_amount = cls._to_int(
            final.get(
                "discount_amount"
            )
        )

        return {
            "calculated_regular_price": (
                sale_price
                + discount_amount
                if (
                    sale_price
                    is not None
                    and discount_amount
                    is not None
                )
                else None
            ),

            "final_sale_price":
                sale_price,

            "store_sale_price":
                cls._to_int(
                    store.get(
                        "discount_price"
                    )
                ),

            "final_discount_rate":
                cls._to_float(
                    final.get(
                        "discount_rate"
                    )
                ),

        }

    # ============================================================
    # PRODUCT IMAGES
    # ============================================================

    @classmethod
    def _parse_product_images(
        cls,
        images: list,
    ) -> list[dict]:
        result = []
        seen = set()

        for sequence, item in enumerate(
            images
        ):
            item = cls._as_dict(
                item
            )

            image_url = (
                cls._normalize_image_url(
                    item.get("url")
                    or item.get(
                        "image_url"
                    )
                    or item.get(
                        "imageUrl"
                    )
                )
            )

            if (
                not image_url
                or image_url in seen
            ):
                continue

            seen.add(
                image_url
            )

            result.append(
                {
                    "sequence":
                        sequence,

                    "image_url":
                        image_url,

                    "image_type":
                        "PRODUCT",
                }
            )

        return result

    # ============================================================
    # DETAIL CONTENT
    # ============================================================

    @classmethod
    def _parse_detail_content(
        cls,
        description: str | None,
    ) -> dict:
        html = (
            description
            or ""
        ).strip()

        if not html:
            return {
                "html": None,
                "images": [],
                "videos": [],
            }

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        images = []
        videos = []

        seen_images = set()
        seen_videos = set()

        for sequence, tag in enumerate(
            soup.find_all("img")
        ):
            image_url = (
                cls._normalize_image_url(
                    tag.get("src")
                    or tag.get(
                        "data-src"
                    )
                    or tag.get(
                        "data-original"
                    )
                )
            )

            if (
                not image_url
                or image_url
                in seen_images
            ):
                continue

            seen_images.add(
                image_url
            )

            images.append(
                {
                    "sequence":
                        sequence,

                    "image_url":
                        image_url,

                    "image_type":
                        "DETAIL",

                    "alt": (
                        tag.get("alt")
                        or ""
                    ).strip()
                    or None,
                }
            )

        for tag in soup.find_all(
            [
                "iframe",
                "video",
                "source",
            ]
        ):
            video_url = (
                cls._normalize_image_url(
                    tag.get("src")
                )
            )

            if (
                not video_url
                or video_url
                in seen_videos
            ):
                continue

            seen_videos.add(
                video_url
            )

            videos.append(
                video_url
            )

        return {
            "html": html,
            "images": images,
            "videos": videos,
        }

    # ============================================================
    # UTILS
    # ============================================================

    @staticmethod
    def _as_dict(
        value,
    ) -> dict:
        return (
            value
            if isinstance(
                value,
                dict,
            )
            else {}
        )

    @classmethod
    def _category_value(
        cls,
        categories: list,
        index: int,
    ) -> str | None:
        if index >= len(
            categories
        ):
            return None

        return cls._clean_text(
            cls._as_dict(
                categories[index]
            ).get(
                "value"
            )
        )

    @staticmethod
    def _get_path(
        value,
        path: str,
    ):
        current = value

        for part in path.split(
            "."
        ):
            if isinstance(
                current,
                dict,
            ):
                current = (
                    current.get(
                        part
                    )
                )

            elif (
                isinstance(
                    current,
                    list,
                )
                and part.isdigit()
            ):
                index = int(
                    part
                )

                current = (
                    current[index]
                    if index
                    < len(current)
                    else None
                )

            else:
                return None

            if current is None:
                return None

        return current

    @staticmethod
    def _normalize_image_url(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        url = str(
            value
        ).strip()

        if not url:
            return None

        if url.startswith(
            "//"
        ):
            return (
                f"https:{url}"
            )

        if url.startswith(
            "/"
        ):
            return (
                f"{IMAGE_BASE_URL}{url}"
            )

        return url

    @staticmethod
    def _clean_text(
        value,
    ) -> str | None:
        if value is None:
            return None

        text = str(
            value
        ).strip()

        return (
            text
            or None
        )

    @staticmethod
    def _to_int(
        value,
    ) -> int | None:
        if (
            value is None
            or isinstance(
                value,
                bool,
            )
        ):
            return None

        try:
            return int(
                float(
                    str(value)
                    .replace(
                        ",",
                        "",
                    )
                    .replace(
                        "원",
                        "",
                    )
                    .replace(
                        "%",
                        "",
                    )
                    .strip()
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_float(
        value,
    ) -> float | None:
        if (
            value is None
            or isinstance(
                value,
                bool,
            )
        ):
            return None

        try:
            return float(
                str(value)
                .replace(
                    ",",
                    "",
                )
                .replace(
                    "%",
                    "",
                )
                .strip()
            )

        except (
            TypeError,
            ValueError,
        ):
            return None
