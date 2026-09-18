from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

ZIGZAG_BASE_URL = "https://zigzag.kr"

DEFAULT_TIMEOUT = 20

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": f"{ZIGZAG_BASE_URL}/",
}


class ZigzagStoreCollectError(Exception):
    pass


class ZigzagStoreCollector:
    """
    FEEDIT Zigzag STORE profile 전용 collector.

    목적
    ------------------------------------------------------------
    현재 CNV collector와 완전히 분리해서 아래 두 기능만 담당한다.

    1. collect_product_detail()
       ProductSource.product_url 한 건에서
       store main_domain / profile URL을 복구한다.

    2. collect_shop()
       https://zigzag.kr/{main_domain} STORE 페이지에서
       브랜드 승격에 필요한 프로필을 수집한다.

    반환 profile
    ------------------------------------------------------------
    - source_brand_id
    - name
    - english_name
    - english_name_source
    - main_domain
    - source_profile_url
    - image_url
    - description
    - target_age
    - style_list
    - bookmark_count
    - seller_badges
    - total_product_count

    english_name 처리
    ------------------------------------------------------------
    지그재그 HTML에 명시적 영문명이 있으면 그 값을 사용한다.

    명시 필드가 없으면 main_domain을 fallback으로 반환한다.
    이 경우 english_name_source="MAIN_DOMAIN_FALLBACK"으로 표시한다.
    """

    ENGLISH_NAME_KEYS = (
        "english_name",
        "englishName",
        "name_en",
        "nameEn",
        "eng_name",
        "engName",
        "english_shop_name",
        "shop_name_en",
    )

    MAIN_DOMAIN_KEYS = (
        "main_domain",
        "mainDomain",
        "shop_domain",
        "shopDomain",
        "domain",
    )

    SHOP_ID_KEYS = (
        "id",
        "shop_id",
        "shopId",
        "store_id",
        "storeId",
    )

    SHOP_NAME_KEYS = (
        "name",
        "shop_name",
        "shopName",
        "store_name",
        "storeName",
    )

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    # ========================================================
    # CONTEXT MANAGER
    # ========================================================

    def close(self) -> None:
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ========================================================
    # HTTP
    # ========================================================

    def _get_html(
        self,
        url: str,
    ) -> tuple[str, requests.Response]:
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ZigzagStoreCollectError(
                f"GET 실패: {url} / {exc}"
            ) from exc

        return response.text, response

    # ========================================================
    # PUBLIC: PRODUCT DETAIL
    # ========================================================

    def collect_product_detail(
        self,
        ranking_item: dict[str, Any],
    ) -> dict[str, Any]:
        """
        대표 상품 상세 페이지에서 store 정보를 찾는다.

        입력 예:
        {
            "product_url": "...",
            "store_id": "202",
            "store_name": "다이먼트",
            "store": {
                "source_brand_id": "202",
                "name": "다이먼트",
            }
        }
        """

        url = self._clean(
            ranking_item.get("product_url")
        )

        if not url:
            raise ZigzagStoreCollectError(
                "product_url이 없습니다."
            )

        page_html, response = self._get_html(url)

        fallback_store = (
            ranking_item.get("store")
            if isinstance(
                ranking_item.get("store"),
                dict,
            )
            else {}
        )

        fallback_shop_id = self._clean(
            fallback_store.get("source_brand_id")
            or ranking_item.get("store_id")
            or ranking_item.get("shop_id")
        )

        fallback_shop_name = self._clean(
            fallback_store.get("name")
            or ranking_item.get("store_name")
            or ranking_item.get("shop_name")
        )

        store = self._extract_store_from_product_html(
            page_html,
            fallback_shop_id=fallback_shop_id,
            fallback_shop_name=fallback_shop_name,
        )

        return {
            "source_url": str(
                getattr(response, "url", url)
            ),
            "http_status": response.status_code,
            "store": store,
        }

    # ========================================================
    # PUBLIC: SHOP
    # ========================================================

    def collect_shop(
        self,
        shop_url: str,
        *,
        collect_products: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """
        STORE 프로필만 수집한다.

        backfill 호환 때문에 collect_products 인자를 받지만
        이 collector에서는 상품 목록을 수집하지 않는다.
        """

        source_url = self._normalize_shop_url(
            shop_url
        )

        page_html, response = self._get_html(
            source_url
        )

        page_data = self._extract_store_page_data(
            page_html
        )

        shop = self._parse_shop_profile(
            page_data,
            source_url=source_url,
            page_html=page_html,
        )

        if not shop.get("source_brand_id"):
            raise ZigzagStoreCollectError(
                f"STORE 페이지에서 shop_id를 찾지 못했습니다: {source_url}"
            )

        return {
            "source_url": source_url,
            "collected_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "http_status": response.status_code,
            "content_type": response.headers.get(
                "Content-Type"
            ),
            "shop": shop,
            "raw_profile": (
                page_data.get(
                    "raw_shop_information"
                )
            ),
            "products": [],
        }

    # ========================================================
    # STORE PAGE PARSING
    # ========================================================

    def _extract_store_page_data(
        self,
        page_html: str,
    ) -> dict[str, Any]:
        result = {
            "raw_shop_information": None,
            "total_product_count": None,
        }

        shop_info = (
            self._extract_json_object_after_key(
                page_html,
                "shop_information",
            )
            or self._extract_json_object_after_key(
                page_html,
                "shopInformation",
            )
        )

        if not isinstance(shop_info, dict):
            # Next / dehydrated state 전체 JSON에서 재탐색
            shop_info = self._find_shop_information_in_scripts(
                page_html
            )

        if isinstance(shop_info, dict):
            result[
                "raw_shop_information"
            ] = shop_info

        result[
            "total_product_count"
        ] = self._extract_first_int_by_keys(
            page_html,
            (
                "total_product_count",
                "totalProductCount",
                "product_count",
                "productCount",
                "total_count",
                "totalCount",
            ),
        )

        return result

    def _parse_shop_profile(
        self,
        page_data: dict[str, Any],
        *,
        source_url: str,
        page_html: str,
    ) -> dict[str, Any]:

        info = (
            page_data.get(
                "raw_shop_information"
            )
            or {}
        )

        main_domain = self._first_clean(
            *(
                info.get(key)
                for key in self.MAIN_DOMAIN_KEYS
            )
        )

        if not main_domain:
            main_domain = self._domain_from_url(
                source_url
            )

        source_brand_id = self._first_clean(
            *(
                info.get(key)
                for key in self.SHOP_ID_KEYS
            )
        )

        name = self._first_clean(
            *(
                info.get(key)
                for key in self.SHOP_NAME_KEYS
            )
        )

        explicit_english_name = (
            self._first_clean(
                *(
                    info.get(key)
                    for key
                    in self.ENGLISH_NAME_KEYS
                )
            )
        )

        if explicit_english_name:
            english_name = (
                explicit_english_name
            )
            english_name_source = (
                "STORE_PROFILE"
            )
        elif main_domain:
            # 지그재그 store slug는 영문/로마자 브랜드 식별자로
            # 활용 가능하지만 명시적 공식 영문명과는 구분한다.
            english_name = main_domain
            english_name_source = (
                "MAIN_DOMAIN_FALLBACK"
            )
        else:
            english_name = None
            english_name_source = None

        logo = (
            info.get("logo_image")
            or info.get("logoImage")
            or {}
        )

        logo_url = (
            logo.get("url")
            if isinstance(logo, dict)
            else None
        )

        if isinstance(
            logo_url,
            dict,
        ):
            logo_value = self._first_clean(
                logo_url.get("normal"),
                logo_url.get("original"),
                logo_url.get("large"),
                logo_url.get("small"),
            )
        else:
            logo_value = self._clean(
                logo_url
            )

        image_url = self._first_clean(
            info.get(
                "typical_image_url"
            ),
            info.get(
                "typicalImageUrl"
            ),
            info.get("image_url"),
            info.get("imageUrl"),
            logo_value,
            self._extract_meta_content(
                page_html,
                property_name="og:image",
            ),
        )

        description = self._first_clean(
            info.get("comment"),
            info.get("description"),
            info.get("introduction"),
            info.get("bio"),
        )

        style_list = self._extract_value_list(
            info.get("style_list")
            or info.get("styleList")
            or info.get("styles")
        )

        target_age = self._extract_value_list(
            info.get("age_list")
            or info.get("ageList")
            or info.get("target_age")
            or info.get("targetAge")
        )

        seller_badges = (
            self._extract_badges(
                info.get("seller_badge")
                or info.get("sellerBadge")
                or info.get("seller_badges")
                or info.get("sellerBadges")
            )
        )

        bookmark_count = self._first_int(
            info.get("bookmark_count"),
            info.get("bookmarkCount"),
            info.get("favorite_count"),
            info.get("favoriteCount"),
        )

        source_profile_url = (
            f"{ZIGZAG_BASE_URL}/{main_domain}"
            if main_domain
            else source_url
        )

        return {
            "source_brand_id":
                source_brand_id,

            "name":
                name,

            "english_name":
                english_name,

            "english_name_source":
                english_name_source,

            "main_domain":
                main_domain,

            "source_profile_url":
                source_profile_url,

            "image_url":
                image_url,

            "description":
                description,

            "target_age":
                target_age or None,

            "style_list":
                style_list,

            "bookmark_count":
                bookmark_count,

            "seller_badges":
                seller_badges,

            "total_product_count":
                page_data.get(
                    "total_product_count"
                ),
        }

    # ========================================================
    # PRODUCT PAGE -> STORE
    # ========================================================

    def _extract_store_from_product_html(
        self,
        page_html: str,
        *,
        fallback_shop_id: str | None,
        fallback_shop_name: str | None,
    ) -> dict[str, Any]:

        # 1) store/shop 계열 JSON object 직접 탐색
        candidate = None

        for key in (
            "shop_information",
            "shopInformation",
            "shop",
            "store",
        ):
            obj = self._extract_json_object_after_key(
                page_html,
                key,
            )

            if (
                isinstance(obj, dict)
                and self._looks_like_store(
                    obj
                )
            ):
                candidate = obj
                break

        # 2) script JSON 전체 recursive 탐색
        if candidate is None:
            candidate = (
                self._find_store_dict_in_scripts(
                    page_html
                )
            )

        candidate = (
            candidate
            if isinstance(
                candidate,
                dict,
            )
            else {}
        )

        main_domain = self._first_clean(
            *(
                candidate.get(key)
                for key in self.MAIN_DOMAIN_KEYS
            ),
            self._extract_first_string_by_keys(
                page_html,
                self.MAIN_DOMAIN_KEYS,
            ),
        )

        source_brand_id = self._first_clean(
            *(
                candidate.get(key)
                for key in self.SHOP_ID_KEYS
            ),
            fallback_shop_id,
        )

        name = self._first_clean(
            *(
                candidate.get(key)
                for key in self.SHOP_NAME_KEYS
            ),
            fallback_shop_name,
        )

        return {
            "source_brand_id":
                source_brand_id,

            "name":
                name,

            "main_domain":
                main_domain,

            "source_profile_url":
                (
                    f"{ZIGZAG_BASE_URL}/{main_domain}"
                    if main_domain
                    else None
                ),
        }

    # ========================================================
    # SCRIPT JSON SEARCH
    # ========================================================

    def _find_shop_information_in_scripts(
        self,
        page_html: str,
    ) -> dict[str, Any] | None:

        for payload in self._iter_script_json(
            page_html
        ):
            found = self._recursive_find_dict(
                payload,
                predicate=(
                    self._looks_like_shop_information
                ),
            )
            if found is not None:
                return found

        return None

    def _find_store_dict_in_scripts(
        self,
        page_html: str,
    ) -> dict[str, Any] | None:

        for payload in self._iter_script_json(
            page_html
        ):
            found = self._recursive_find_dict(
                payload,
                predicate=self._looks_like_store,
            )
            if found is not None:
                return found

        return None

    @staticmethod
    def _iter_script_json(
        page_html: str,
    ):
        soup = BeautifulSoup(
            page_html,
            "html.parser",
        )

        for script in soup.find_all("script"):
            text = script.string or script.get_text()

            if not text:
                continue

            text = text.strip()

            if not text:
                continue

            # 순수 JSON script
            if (
                text.startswith("{")
                or text.startswith("[")
            ):
                try:
                    yield json.loads(text)
                    continue
                except Exception:
                    pass

            # Next.js self.__next_f.push(...) 안 JSON 문자열
            for raw in re.findall(
                r'JSON\.parse\((["\'])(.*?)\1\)',
                text,
                flags=re.DOTALL,
            ):
                try:
                    decoded = json.loads(
                        f'"{raw[1]}"'
                    )
                    yield json.loads(decoded)
                except Exception:
                    continue

    @classmethod
    def _recursive_find_dict(
        cls,
        value: Any,
        *,
        predicate,
    ) -> dict[str, Any] | None:

        if isinstance(value, dict):
            if predicate(value):
                return value

            for child in value.values():
                found = cls._recursive_find_dict(
                    child,
                    predicate=predicate,
                )
                if found is not None:
                    return found

        elif isinstance(value, list):
            for child in value:
                found = cls._recursive_find_dict(
                    child,
                    predicate=predicate,
                )
                if found is not None:
                    return found

        return None

    @classmethod
    def _looks_like_shop_information(
        cls,
        value: dict[str, Any],
    ) -> bool:
        keys = set(value.keys())

        score = 0

        if any(
            key in keys
            for key in cls.MAIN_DOMAIN_KEYS
        ):
            score += 2

        if any(
            key in keys
            for key in cls.SHOP_ID_KEYS
        ):
            score += 1

        if any(
            key in keys
            for key in cls.SHOP_NAME_KEYS
        ):
            score += 1

        if (
            "style_list" in keys
            or "styleList" in keys
            or "bookmark_count" in keys
            or "bookmarkCount" in keys
            or "logo_image" in keys
            or "logoImage" in keys
        ):
            score += 2

        return score >= 3

    @classmethod
    def _looks_like_store(
        cls,
        value: dict[str, Any],
    ) -> bool:
        keys = set(value.keys())

        has_id = any(
            key in keys
            for key in cls.SHOP_ID_KEYS
        )

        has_domain = any(
            key in keys
            for key in cls.MAIN_DOMAIN_KEYS
        )

        has_name = any(
            key in keys
            for key in cls.SHOP_NAME_KEYS
        )

        return (
            has_domain
            and (
                has_id
                or has_name
            )
        )

    # ========================================================
    # BALANCED JSON OBJECT EXTRACTION
    # ========================================================

    @classmethod
    def _extract_json_object_after_key(
        cls,
        text: str,
        key: str,
    ) -> dict[str, Any] | None:
        """
        HTML/JS 문자열에서
        "key": {...}
        뒤의 balanced JSON object를 파싱한다.
        """

        patterns = (
            f'"{key}"',
            f"'{key}'",
        )

        start_key = -1

        for pattern in patterns:
            start_key = text.find(pattern)
            if start_key >= 0:
                break

        if start_key < 0:
            return None

        colon = text.find(
            ":",
            start_key,
        )

        if colon < 0:
            return None

        brace = text.find(
            "{",
            colon,
        )

        if brace < 0:
            return None

        raw = cls._slice_balanced_object(
            text,
            brace,
        )

        if not raw:
            return None

        # HTML escaped JSON 방어
        raw = html_lib.unescape(raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # JS object 중 일부가 JSON strict가 아닐 때는 실패.
            return None

    @staticmethod
    def _slice_balanced_object(
        text: str,
        start: int,
    ) -> str | None:

        if (
            start < 0
            or start >= len(text)
            or text[start] != "{"
        ):
            return None

        depth = 0
        in_string = False
        quote_char = ""
        escaped = False

        for index in range(
            start,
            len(text),
        ):
            char = text[index]

            if in_string:
                if escaped:
                    escaped = False
                    continue

                if char == "\\":
                    escaped = True
                    continue

                if char == quote_char:
                    in_string = False

                continue

            if char in ('"', "'"):
                in_string = True
                quote_char = char
                continue

            if char == "{":
                depth += 1

            elif char == "}":
                depth -= 1

                if depth == 0:
                    return text[
                        start:index + 1
                    ]

        return None

    # ========================================================
    # GENERIC HTML / JSON HELPERS
    # ========================================================

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
            attrs={
                "property": property_name
            },
        )

        if tag is None:
            tag = soup.find(
                "meta",
                attrs={
                    "name": property_name
                },
            )

        if tag is None:
            return None

        value = tag.get("content")
        return (
            str(value).strip()
            if value
            else None
        )

    @classmethod
    def _extract_first_string_by_keys(
        cls,
        text: str,
        keys,
    ) -> str | None:

        for key in keys:
            pattern = re.compile(
                rf'["\']{re.escape(key)}["\']'
                r'\s*:\s*'
                r'["\']([^"\']+)["\']',
                flags=re.IGNORECASE,
            )

            match = pattern.search(text)

            if match:
                return cls._clean(
                    html_lib.unescape(
                        match.group(1)
                    )
                )

        return None

    @classmethod
    def _extract_first_int_by_keys(
        cls,
        text: str,
        keys,
    ) -> int | None:

        for key in keys:
            pattern = re.compile(
                rf'["\']{re.escape(key)}["\']'
                r'\s*:\s*'
                r'["\']?([0-9][0-9,]*)',
                flags=re.IGNORECASE,
            )

            match = pattern.search(text)

            if match:
                return cls._to_int(
                    match.group(1)
                )

        return None

    @classmethod
    def _extract_value_list(
        cls,
        value: Any,
    ) -> list[str]:

        if value is None:
            return []

        if not isinstance(
            value,
            list,
        ):
            value = [value]

        result = []

        for item in value:
            if isinstance(item, dict):
                raw = (
                    item.get("value")
                    or item.get("name")
                    or item.get("text")
                    or item.get("id")
                )
            else:
                raw = item

            cleaned = cls._clean(raw)

            if (
                cleaned
                and cleaned not in result
            ):
                result.append(cleaned)

        return result

    @classmethod
    def _extract_badges(
        cls,
        value: Any,
    ) -> list[str]:

        if not value:
            return []

        if not isinstance(
            value,
            list,
        ):
            value = [value]

        result = []

        for item in value:
            if isinstance(item, dict):
                text_obj = (
                    item.get("text")
                    or item.get("name")
                    or item.get("value")
                )

                if isinstance(
                    text_obj,
                    dict,
                ):
                    raw = (
                        text_obj.get("text")
                        or text_obj.get("value")
                    )
                else:
                    raw = text_obj
            else:
                raw = item

            cleaned = cls._clean(raw)

            if (
                cleaned
                and cleaned not in result
            ):
                result.append(cleaned)

        return result

    @classmethod
    def _first_clean(
        cls,
        *values,
    ) -> str | None:

        for value in values:
            cleaned = cls._clean(value)
            if cleaned:
                return cleaned

        return None

    @classmethod
    def _first_int(
        cls,
        *values,
    ) -> int | None:

        for value in values:
            parsed = cls._to_int(value)
            if parsed is not None:
                return parsed

        return None

    @staticmethod
    def _clean(
        value: Any,
    ) -> str | None:

        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @staticmethod
    def _to_int(
        value: Any,
    ) -> int | None:

        if (
            value is None
            or isinstance(value, bool)
        ):
            return None

        if isinstance(value, int):
            return value

        text = str(value).strip()

        if not text:
            return None

        # "1.2만", "3천" 대응
        count_match = re.fullmatch(
            r"([0-9]+(?:\.[0-9]+)?)\s*([천만]?)",
            text.replace(",", ""),
        )

        if count_match:
            number = float(
                count_match.group(1)
            )
            unit = count_match.group(2)

            if unit == "천":
                number *= 1_000
            elif unit == "만":
                number *= 10_000

            return int(number)

        try:
            return int(
                float(
                    text.replace(",", "")
                )
            )
        except ValueError:
            return None

    @staticmethod
    def _normalize_shop_url(
        url: str,
    ) -> str:

        url = str(url or "").strip()

        if not url:
            raise ZigzagStoreCollectError(
                "shop_url이 비어 있습니다."
            )

        if url.startswith("/"):
            url = (
                f"{ZIGZAG_BASE_URL}{url}"
            )

        parsed = urlparse(url)

        if not parsed.scheme:
            url = (
                f"{ZIGZAG_BASE_URL}/"
                f"{url.lstrip('/')}"
            )

        return (
            url.split("?")[0]
            .rstrip("/")
        )

    @staticmethod
    def _domain_from_url(
        url: str,
    ) -> str | None:

        parsed = urlparse(url)
        path = parsed.path.strip("/")

        if not path:
            return None

        first = path.split("/")[0]

        # 일반 라우트는 domain으로 쓰지 않는다.
        if first.lower() in {
            "search",
            "categories",
            "category",
            "products",
            "product",
            "ranking",
            "event",
        }:
            return None

        return first or None


# 기존 backfill 코드와의 호환 alias.
# import 한 줄만 바꾸기 싫으면 아래 이름을 써도 된다.
ZigzagCollector = ZigzagStoreCollector


__all__ = [
    "ZigzagStoreCollector",
    "ZigzagStoreCollectError",
    "ZigzagCollector",
]
