# collection/musinsa/brand_collector.py

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from collection.core.http import DEFAULT_HEADERS
from collection.musinsa.constants import (
    MUSINSA_BASE_URL,
    REQUEST_TIMEOUT,
)


class MusinsaBrandCollectError(Exception):
    """무신사 브랜드 목록/상세 수집 실패."""


class MusinsaBrandCollector:
    """
    무신사 브랜드 마스터 수집기.

    전체 브랜드 기본정보:
        static.msscdn.net/display/brand/brand-list.json

    브랜드 상세정보:
        https://www.musinsa.com/brand/{brand_id}?gf=A

    전략:
    1. 전체 동기화는 brand-list.json 한 번으로 처리
    2. nation / since_year / description 같은 상세값은
       필요한 브랜드만 상세 페이지에서 보강
    """

    BRAND_LIST_URL = "https://static.msscdn.net/" "display/brand/brand-list.json"

    BRAND_URL = f"{MUSINSA_BASE_URL}/brand/" "{brand_id}?gf=A"

    BRAND_PATH_PATTERN = re.compile(
        r"(?:https?://(?:www\.)?musinsa\.com)?" r"/brand/([a-zA-Z0-9._-]+)"
    )

    RESERVED_BRAND_IDS = {
        "products",
        "contents",
        "info",
        "snap",
    }

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout or REQUEST_TIMEOUT

        self.session = session or requests.Session()

        self.session.headers.update(DEFAULT_HEADERS)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        self.close()

    # ============================================================
    # HTTP
    # ============================================================

    def fetch(
        self,
        url: str,
        *,
        params: dict | None = None,
    ) -> requests.Response:
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )

            response.raise_for_status()

            return response

        except requests.RequestException as exc:
            raise MusinsaBrandCollectError(
                f"브랜드 요청 실패: " f"{url} / {exc}"
            ) from exc

    def _get_json(
        self,
        url: str,
    ):
        response = self.fetch(url)

        try:
            return response.json()

        except ValueError as exc:
            raise MusinsaBrandCollectError(
                f"브랜드 JSON 파싱 실패: " f"{response.url}"
            ) from exc

    # ============================================================
    # BRAND INDEX
    # ============================================================

    def collect_brand_index(
        self,
    ) -> list[dict]:
        """
        전체 브랜드 기본정보를 한 번에 수집.

        실제 응답 필드:
        - id
        - name
        - englishName
        - linkUrl
        - isExclusive
        - initialCodeKor
        - initialCodeEng
        - logoImageUrl
        - gender
        - categoryList
        - subCategoryList
        - label

        MusinsaBrand 모델에 필요한 필드만 정규화하여 반환한다.
        """
        body = self._get_json(self.BRAND_LIST_URL)

        if not isinstance(
            body,
            list,
        ):
            raise MusinsaBrandCollectError("브랜드 목록 응답이 list 형식이 아닙니다.")

        result = []

        for item in body:
            if not isinstance(
                item,
                dict,
            ):
                continue

            brand_id = self._normalize_brand_id(item.get("id"))

            if not brand_id:
                continue

            name_ko = self._clean_text(item.get("name"))

            name_en = self._clean_text(item.get("englishName"))

            logo_url = self._normalize_url(item.get("logoImageUrl"))

            result.append(
                {
                    "brand_id": brand_id,
                    "name_ko": (name_ko or name_en or brand_id),
                    "name_en": name_en,
                    "nation": None,
                    "since_year": None,
                    "logo_url": logo_url,
                    "description": None,
                }
            )

        return result

    def discover_brand_ids(
        self,
    ) -> list[str]:
        """
        전체 브랜드 ID만 필요할 때 사용.
        """
        return [item["brand_id"] for item in self.collect_brand_index()]

    # ============================================================
    # BRAND DETAIL
    # ============================================================

    def collect_brand(
        self,
        brand_id: str,
    ) -> dict:
        """
        브랜드 상세 1건 수집.

        반환:
        {
            "brand_id": "adidas",
            "name_ko": "아디다스",
            "name_en": "ADIDAS",
            "nation": "독일",
            "since_year": 1949,
            "logo_url": "...",
            "description": "...",
        }
        """
        brand_id = self._normalize_brand_id(brand_id)

        if not brand_id:
            raise ValueError("올바른 brand_id가 필요합니다.")

        response = self.fetch(self.BRAND_URL.format(brand_id=brand_id))

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        result = {
            "brand_id": brand_id,
            "name_ko": None,
            "name_en": None,
            "nation": None,
            "since_year": None,
            "logo_url": None,
            "description": None,
        }

        script_data = self._extract_brand_from_scripts(
            soup=soup,
            target_brand_id=brand_id,
        )

        if script_data:
            result.update(script_data)

        dom_data = self._extract_brand_from_dom(soup)

        for key in (
            "name_ko",
            "name_en",
            "nation",
            "since_year",
            "logo_url",
            "description",
        ):
            if result.get(key) in (
                None,
                "",
            ):
                result[key] = dom_data.get(key)

        # index API를 fallback으로 사용
        if not result["name_ko"] or not result["name_en"] or not result["logo_url"]:
            index_item = self._find_index_brand(brand_id)

            if index_item:
                for key in (
                    "name_ko",
                    "name_en",
                    "logo_url",
                ):
                    if result.get(key) in (
                        None,
                        "",
                    ):
                        result[key] = index_item.get(key)

        if not result["name_ko"]:
            result["name_ko"] = result["name_en"] or brand_id

        result["brand_id"] = brand_id

        return result

    def collect_brands(
        self,
        brand_ids: Iterable[str],
        *,
        limit: int | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """
        브랜드 상세 여러 건 수집.
        """
        normalized = []

        for brand_id in brand_ids:
            brand_id = self._normalize_brand_id(brand_id)

            if brand_id:
                normalized.append(brand_id)

        normalized = list(dict.fromkeys(normalized))

        if limit is not None:
            normalized = normalized[:limit]

        successes = []
        errors = []

        for brand_id in normalized:
            try:
                successes.append(self.collect_brand(brand_id))

            except Exception as exc:
                errors.append(
                    {
                        "brand_id": (brand_id),
                        "error": str(exc),
                    }
                )

        return successes, errors

    def collect_all_brands(
        self,
        *,
        detail: bool = False,
        limit: int | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """
        전체 브랜드 수집.

        detail=False:
            brand-list.json 한 번 호출.
            전체 브랜드 기본정보 반환.
            권장.

        detail=True:
            index에서 brand_id를 얻은 뒤
            각 상세 페이지까지 방문.
            요청량이 많으므로 필요한 경우만 사용.
        """
        index_brands = self.collect_brand_index()

        if limit is not None:
            index_brands = index_brands[:limit]

        if not detail:
            return (
                index_brands,
                [],
            )

        brand_ids = [item["brand_id"] for item in index_brands]

        return self.collect_brands(brand_ids)

    # ============================================================
    # INDEX FALLBACK
    # ============================================================

    def _find_index_brand(
        self,
        brand_id: str,
    ) -> dict | None:
        for item in self.collect_brand_index():
            if item["brand_id"] == brand_id:
                return item

        return None

    # ============================================================
    # SCRIPT
    # ============================================================

    def _extract_brand_from_scripts(
        self,
        *,
        soup: BeautifulSoup,
        target_brand_id: str,
    ) -> dict | None:
        for script in soup.find_all("script"):
            raw = (script.string or script.get_text() or "").strip()

            if not raw:
                continue

            if raw.startswith(("{", "[")):
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    body = None

                if body is not None:
                    found = self._find_brand_info_recursive(
                        body,
                        target_brand_id=(target_brand_id),
                    )

                    if found:
                        return found

            marker = '"brandInfo"'

            if marker not in raw:
                continue

            marker_index = raw.find(marker)

            colon_index = raw.find(
                ":",
                marker_index,
            )

            brace_index = raw.find(
                "{",
                colon_index,
            )

            if brace_index < 0:
                continue

            try:
                obj, _ = json.JSONDecoder().raw_decode(raw[brace_index:])

            except json.JSONDecodeError:
                obj = None

            if isinstance(
                obj,
                dict,
            ):
                found = self._normalize_brand_dict(
                    obj,
                    target_brand_id=(target_brand_id),
                )

                if found:
                    return found

        return None

    def _find_brand_info_recursive(
        self,
        value,
        *,
        target_brand_id: str,
    ) -> dict | None:
        if isinstance(
            value,
            dict,
        ):
            found = self._normalize_brand_dict(
                value,
                target_brand_id=(target_brand_id),
            )

            if found:
                return found

            for child in value.values():
                found = self._find_brand_info_recursive(
                    child,
                    target_brand_id=(target_brand_id),
                )

                if found:
                    return found

        elif isinstance(
            value,
            list,
        ):
            for child in value:
                found = self._find_brand_info_recursive(
                    child,
                    target_brand_id=(target_brand_id),
                )

                if found:
                    return found

        return None

    def _normalize_brand_dict(
        self,
        value: dict,
        *,
        target_brand_id: str,
    ) -> dict | None:
        brand_id = (
            value.get("brand")
            or value.get("brandId")
            or value.get("brandCode")
            or value.get("brand_id")
        )

        brand_id = self._normalize_brand_id(brand_id)

        if brand_id and brand_id != target_brand_id:
            return None

        data = {
            "brand_id": (brand_id or target_brand_id),
            "name_ko": (
                value.get("brandName")
                or value.get("brandNameKo")
                or value.get("nameKo")
                or value.get("name_ko")
            ),
            "name_en": (
                value.get("brandEnglishName")
                or value.get("brandNameEn")
                or value.get("englishName")
                or value.get("nameEn")
                or value.get("name_en")
            ),
            "nation": (
                value.get("brandNationName")
                or value.get("nationName")
                or value.get("countryName")
                or value.get("nation")
            ),
            "since_year": (
                self._to_int(
                    value.get("sinceYear")
                    or value.get("launchYear")
                    or value.get("since_year")
                )
            ),
            "logo_url": (
                self._normalize_url(
                    value.get("brandLogoImage")
                    or value.get("logoImageUrl")
                    or value.get("logoUrl")
                    or value.get("logo_url")
                )
            ),
            "description": (
                value.get("memo")
                or value.get("description")
                or value.get("brandDescription")
            ),
        }

        if not any(
            data.get(key)
            for key in (
                "name_ko",
                "name_en",
                "nation",
                "since_year",
                "logo_url",
                "description",
            )
        ):
            return None

        return data

    # ============================================================
    # DOM FALLBACK
    # ============================================================

    def _extract_brand_from_dom(
        self,
        soup: BeautifulSoup,
    ) -> dict:
        text = " ".join(soup.stripped_strings)

        title = (
            soup.title.get_text(
                " ",
                strip=True,
            )
            if soup.title
            else ""
        )

        name_ko = None
        name_en = None

        title_match = re.search(
            r"^\s*([^|(]+?)\s*" r"\(([^)]+)\)",
            title,
        )

        if title_match:
            name_ko = self._clean_text(title_match.group(1))

            name_en = self._clean_text(title_match.group(2))

        since_year = None

        since_match = re.search(
            r"\bSince\s+(\d{4})\b",
            text,
            re.IGNORECASE,
        )

        if since_match:
            since_year = int(since_match.group(1))

        nation = None

        nation_match = re.search(
            r"(한국|대한민국|미국|영국|프랑스|독일|"
            r"이탈리아|일본|중국|스페인|캐나다|호주|"
            r"덴마크|스웨덴|노르웨이|핀란드|"
            r"네덜란드|벨기에|스위스)"
            r"\s+Since\s+\d{4}",
            text,
        )

        if nation_match:
            nation = nation_match.group(1)

        logo_url = None

        og_image = soup.find(
            "meta",
            attrs={
                "property": "og:image",
            },
        )

        if og_image:
            logo_url = self._normalize_url(og_image.get("content"))

        description = None

        og_description = soup.find(
            "meta",
            attrs={
                "property": ("og:description"),
            },
        )

        if og_description:
            description = self._clean_text(og_description.get("content"))

        return {
            "name_ko": name_ko,
            "name_en": name_en,
            "nation": nation,
            "since_year": since_year,
            "logo_url": logo_url,
            "description": description,
        }

    # ============================================================
    # UTIL
    # ============================================================

    def _normalize_brand_id(
        self,
        value,
    ) -> str | None:
        value = self._clean_text(value)

        if not value:
            return None

        if "/brand/" in value:
            match = self.BRAND_PATH_PATTERN.search(value)

            if not match:
                return None

            value = match.group(1)

        value = value.strip("/").lower()

        if not value or value in self.RESERVED_BRAND_IDS:
            return None

        if not re.fullmatch(
            r"[a-z0-9._-]+",
            value,
        ):
            return None

        return value

    @staticmethod
    def _clean_text(
        value,
    ) -> str | None:
        if value is None:
            return None

        text = str(value).strip()

        return text or None

    @staticmethod
    def _to_int(
        value,
    ) -> int | None:
        if value is None:
            return None

        try:
            return int(str(value).strip())

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _normalize_url(
        value,
    ) -> str | None:
        if value is None:
            return None

        value = str(value).strip()

        if not value:
            return None

        if value.startswith("//"):
            return f"https:{value}"

        if value.startswith("/"):
            return urljoin(
                MUSINSA_BASE_URL,
                value,
            )

        return value
