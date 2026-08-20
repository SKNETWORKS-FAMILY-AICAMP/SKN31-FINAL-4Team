# collection/musinsa/collector.py

import re
from urllib.parse import (
    parse_qs,
    urljoin,
    urlparse,
)

import requests
from bs4 import BeautifulSoup

from collection.core.http import (
    DEFAULT_HEADERS,
)

from .constants import (
    ARCHIVE_CATEGORIES_API_URL,
    ARCHIVE_GOODS_API_URL,
    LIKE_API_URL,
    LIKE_BATCH_SIZE,
    MUSINSA_BASE_URL,
    PRODUCT_BASE_URL,
    RANKING_API_URL,
    REQUEST_TIMEOUT,
    STAT_API_URL,
    TAG_API_URL,
)

from .parser import MusinsaParser


class MusinsaCollectError(Exception):
    """무신사 HTTP/API 수집 실패 시 사용하는 예외."""

    pass


class MusinsaCollector:
    """
    무신사 수집 전용 Collector.

    책임:
    - 상품 URL 발견
    - 상품 상세 HTML 수집
    - MusinsaParser 실행
    - 태그 / 통계 / 좋아요 API 수집
    - 현재 랭킹 상품 URL 수집
    - 월간 랭킹 Archive API 수집

    하지 않는 일:
    - Django ORM 저장
    - CrawlJob 생성/수정
    - Celery 상태 변경
    - observed_at 결정
    """

    PRODUCT_PATTERN = re.compile(r"/products/(\d+)")

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout or REQUEST_TIMEOUT

        self.session = session or requests.Session()

        self.session.headers.update(DEFAULT_HEADERS)

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

    def fetch(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> requests.Response:
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )

            response.raise_for_status()

            return response

        except requests.RequestException as exc:
            raise MusinsaCollectError(f"GET 요청 실패: " f"{url} / {exc}") from exc

    def _get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        response = self.fetch(
            url,
            params=params,
            headers=headers,
        )

        try:
            body = response.json()
        except ValueError as exc:
            raise MusinsaCollectError(
                "JSON 응답 파싱 실패: " f"{response.url}"
            ) from exc

        if not isinstance(
            body,
            dict,
        ):
            raise MusinsaCollectError(
                "JSON 응답 형식이 " f"object가 아닙니다: {response.url}"
            )

        return body

    # ============================================================
    # PRODUCT URL DISCOVERY
    # ============================================================

    def discover_product_urls(
        self,
        target_url: str,
    ) -> list[str]:
        if not target_url:
            return []

        # 상품 상세
        if self.PRODUCT_PATTERN.search(target_url):
            return [self._normalize_product_url(target_url)]

        # 랭킹
        if "/ranking" in target_url:
            return self.discover_ranking_products(target_url)

        # 일반 HTML
        response = self.fetch(target_url)

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        urls = []
        seen = set()

        for tag in soup.find_all(
            "a",
            href=True,
        ):
            href = tag.get("href")

            if not href:
                continue

            if not self.PRODUCT_PATTERN.search(href):
                continue

            product_url = urljoin(
                response.url,
                href,
            )

            product_url = self._normalize_product_url(product_url)

            if product_url in seen:
                continue

            seen.add(product_url)

            urls.append(product_url)

        return urls

    # ============================================================
    # PRODUCT DETAIL
    # ============================================================

    def collect_product(
        self,
        url: str,
    ) -> dict:
        product_url = self._normalize_product_url(url)

        response = self.fetch(product_url)

        parsed = MusinsaParser.parse_product(response.text)

        product_data = parsed.get("product") or {}

        snapshot_data = parsed.get("snapshot") or {}

        meta_data = parsed.get("meta") or {}

        goods_no = self._to_int(product_data.get("goods_no"))

        if goods_no is None:
            raise MusinsaCollectError(
                "상품번호를 확인할 수 없습니다: " f"{product_url}"
            )

        # --------------------------------------------------------
        # TAG API
        # --------------------------------------------------------

        try:
            tags = self.collect_tags(goods_no)
        except MusinsaCollectError:
            tags = None

        # API 성공 시 덮어쓰고,
        # API 실패 시 parser의 __NEXT_DATA__ 태그 유지
        if tags is not None:
            product_data["tags"] = tags

        # --------------------------------------------------------
        # STAT API
        # --------------------------------------------------------

        try:
            stat = self.collect_stat(goods_no)
        except MusinsaCollectError:
            stat = {
                "view_count": None,
                "sales_count": None,
            }

        snapshot_data["view_count"] = stat.get("view_count")

        snapshot_data["sales_count"] = stat.get("sales_count")

        # 좋아요는 여러 상품 batch 처리
        snapshot_data["like_count"] = None

        # --------------------------------------------------------
        # META
        # --------------------------------------------------------

        meta_data.update(
            {
                "request_url": (product_url),
                "final_url": (response.url),
                "http_status": (response.status_code),
                "content_type": (response.headers.get("Content-Type")),
            }
        )

        parsed["product"] = product_data

        parsed["snapshot"] = snapshot_data

        parsed["meta"] = meta_data

        return parsed

    def collect_products(
        self,
        urls: list[str],
        *,
        collect_likes: bool = True,
    ) -> list[dict]:
        results = []

        for url in urls:
            result = self.collect_product(url)

            results.append(result)

        if not collect_likes or not results:
            return results

        goods_nos = [
            item["product"]["goods_no"]
            for item in results
            if (item.get("product") and item["product"].get("goods_no") is not None)
        ]

        try:
            like_counts = self.collect_like_counts(goods_nos)
        except MusinsaCollectError:
            like_counts = {}

        for item in results:
            goods_no = item["product"].get("goods_no")

            item["snapshot"]["like_count"] = like_counts.get(goods_no)

        return results

    # ============================================================
    # TAG API
    # ============================================================

    def collect_tags(
        self,
        goods_no: int,
    ) -> list[str] | None:
        url = TAG_API_URL.format(goods_no=goods_no)

        body = self._get_json(
            url,
            headers={
                "Referer": (PRODUCT_BASE_URL.format(goods_no=goods_no)),
            },
        )

        data = body.get("data") or {}

        if not isinstance(
            data,
            dict,
        ):
            return None

        tags = data.get("tags")

        if not isinstance(
            tags,
            list,
        ):
            return None

        cleaned = [
            str(tag).strip() for tag in tags if (tag is not None and str(tag).strip())
        ]

        return list(dict.fromkeys(cleaned)) or None

    # ============================================================
    # STAT API
    # ============================================================

    def collect_stat(
        self,
        goods_no: int,
    ) -> dict:
        url = STAT_API_URL.format(goods_no=goods_no)

        body = self._get_json(
            url,
            headers={
                "Referer": (PRODUCT_BASE_URL.format(goods_no=goods_no)),
            },
        )

        data = body.get("data") or {}

        if not isinstance(
            data,
            dict,
        ):
            data = {}

        return {
            "view_count": self._to_int(data.get("pageViewTotal")),
            "sales_count": self._to_int(data.get("purchaseTotal")),
        }

    # ============================================================
    # LIKE API
    # ============================================================

    def _collect_like_batch(
        self,
        goods_nos: list[int],
    ) -> dict[int, int | None]:
        if not goods_nos:
            return {}

        relation_ids = [int(goods_no) for goods_no in goods_nos]

        try:
            response = self.session.post(
                LIKE_API_URL,
                json={
                    "relationIds": (relation_ids),
                },
                headers={
                    "Origin": (MUSINSA_BASE_URL),
                    "Referer": (f"{MUSINSA_BASE_URL}/"),
                },
                timeout=self.timeout,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            raise MusinsaCollectError("좋아요 API 요청 실패: " f"{exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise MusinsaCollectError("좋아요 API JSON 파싱 실패") from exc

        if not isinstance(
            body,
            dict,
        ):
            return {}

        contents = body.get("data", {}).get("contents", {})

        if not isinstance(
            contents,
            dict,
        ):
            return {}

        items = contents.get("items") or []

        if not isinstance(
            items,
            list,
        ):
            return {}

        result = {}

        for item in items:
            if not isinstance(
                item,
                dict,
            ):
                continue

            relation_id = self._to_int(item.get("relationId"))

            if relation_id is None:
                continue

            result[relation_id] = self._to_int(item.get("count"))

        return result

    def collect_like_counts(
        self,
        goods_nos: list[int],
    ) -> dict[int, int | None]:
        if not goods_nos:
            return {}

        normalized_goods_nos = []

        for goods_no in goods_nos:
            value = self._to_int(goods_no)

            if value is not None:
                normalized_goods_nos.append(value)

        normalized_goods_nos = list(dict.fromkeys(normalized_goods_nos))

        result = {}

        for start in range(
            0,
            len(normalized_goods_nos),
            LIKE_BATCH_SIZE,
        ):
            batch = normalized_goods_nos[start : start + LIKE_BATCH_SIZE]

            batch_result = self._collect_like_batch(batch)

            result.update(batch_result)

        return result

    # ============================================================
    # CURRENT RANKING
    # ============================================================

    def discover_ranking_items(
        self,
        target_url: str,
    ) -> list[dict]:
        """
        현재 무신사 랭킹 API에서 상품 + 랭킹 문맥을 함께 반환한다.

        반환 예:
        [
            {
                "rank": 1,
                "product_url": "...",
                "ranking_period": "DAILY",
                "ranking_gender": "M",
                "ranking_category_depth1_code": "001000",
                "ranking_age_band": "AGE_BAND_MINOR",
            },
            ...
        ]
        """

        parsed_url = urlparse(target_url)
        query = parse_qs(parsed_url.query)

        ranking_period = query.get(
            "period",
            ["DAILY"],
        )[0]

        ranking_gender = query.get(
            "gf",
            ["A"],
        )[0]

        ranking_category_code = query.get(
            "categoryCode",
            [""],
        )[0]

        ranking_age_band = query.get(
            "ageBand",
            ["AGE_BAND_ALL"],
        )[0]

        params = {
            "storeCode": query.get(
                "storeCode",
                ["musinsa"],
            )[0],
            "subPan": query.get(
                "subPan",
                ["product"],
            )[0],
            "sectionId": query.get(
                "sectionId",
                ["200"],
            )[0],
            "gf": ranking_gender,
            "contentsId": query.get(
                "contentsId",
                [""],
            )[0],
            "categoryCode": ranking_category_code,
            "ageBand": ranking_age_band,
            # 기존 코드에 빠져있던 값
            "period": ranking_period,
        }

        body = self._get_json(
            RANKING_API_URL,
            params=params,
            headers={
                "Referer": target_url,
            },
        )

        modules = body.get("data", {}).get("modules", [])

        if not isinstance(
            modules,
            list,
        ):
            return []

        results = []
        seen = set()

        # API가 보내준 상품 순서가 현재 랭킹 순서.
        # 실제 rank 값이 item 안에 있으면 그것을 우선하고,
        # 없으면 순서를 rank로 사용한다.
        fallback_rank = 1

        for module in modules:

            if not isinstance(
                module,
                dict,
            ):
                continue

            if module.get("type") != "MULTICOLUMN":
                continue

            items = module.get("items") or []

            if not isinstance(
                items,
                list,
            ):
                continue

            for item in items:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                onclick = item.get("onClick") or {}

                if not isinstance(
                    onclick,
                    dict,
                ):
                    continue

                product_url = onclick.get("url")

                if not product_url:
                    continue

                if not self.PRODUCT_PATTERN.search(product_url):
                    continue

                product_url = self._normalize_product_url(product_url)

                if product_url in seen:
                    continue

                seen.add(product_url)

                # 응답에 명시적인 rank가 있으면 우선 사용.
                rank = self._to_int(item.get("rank"))

                if rank is None:
                    rank = fallback_rank

                results.append(
                    {
                        "rank": rank,
                        "product_url": (product_url),
                        "ranking_period": (ranking_period),
                        "ranking_gender": (ranking_gender),
                        "ranking_category_depth1_code": (ranking_category_code or None),
                        # 아직 Snapshot 모델에 필드가 없다면
                        # Pipeline meta 용도로만 유지.
                        "ranking_age_band": (ranking_age_band),
                    }
                )

                fallback_rank += 1

        return results

    def discover_ranking_products(
        self,
        target_url: str,
    ) -> list[str]:
        """
        기존 코드와의 호환성을 위한 wrapper.

        기존 호출부에서 URL 목록만 필요할 때 사용.
        """

        ranking_items = self.discover_ranking_items(target_url)

        return [item["product_url"] for item in ranking_items]

    # ============================================================
    # ARCHIVE RANKING
    # ============================================================

    def collect_archive_categories(
        self,
        *,
        year_month: str,
        gender_code: str,
    ) -> list[dict]:
        body = self._get_json(
            ARCHIVE_CATEGORIES_API_URL,
            params={
                "yearMonth": (year_month),
                "gf": (gender_code),
            },
        )

        data = body.get("data") or {}

        if not isinstance(
            data,
            dict,
        ):
            return []

        items = data.get("list") or []

        if not isinstance(
            items,
            list,
        ):
            return []

        return items

    def collect_archive_ranking(
        self,
        *,
        year_month: str,
        gender_code: str,
        category_code: str,
    ) -> list[dict]:
        body = self._get_json(
            ARCHIVE_GOODS_API_URL,
            params={
                "yearMonth": (year_month),
                "gf": (gender_code),
                "category": (category_code),
            },
        )

        data = body.get("data") or {}

        if not isinstance(
            data,
            dict,
        ):
            return []

        items = data.get("list") or []

        if not isinstance(
            items,
            list,
        ):
            return []

        result = []

        for item in items:
            if not isinstance(
                item,
                dict,
            ):
                continue

            goods_no = self._to_int(item.get("goodsNo"))

            rank = self._to_int(item.get("rank"))

            if goods_no is None or rank is None:
                continue

            result.append(
                {
                    "rank": rank,
                    "goods_no": (goods_no),
                    "goods_name": (item.get("goodsName")),
                    "brand": (item.get("brand")),
                    "brand_name": (item.get("brandName")),
                    "image_url": (item.get("imageUrl")),
                    "is_permanent_stopped": (
                        self._to_bool(
                            item.get("isPermanentStopped"),
                            default=False,
                        )
                    ),
                    "product_url": (PRODUCT_BASE_URL.format(goods_no=goods_no)),
                    # archive 요청 문맥
                    "ranking_year_month": (year_month),
                    "ranking_gender": (gender_code),
                    "ranking_category_code": (category_code),
                }
            )

        return result

    # ============================================================
    # UTIL
    # ============================================================

    @classmethod
    def _normalize_product_url(
        cls,
        url: str,
    ) -> str:
        absolute_url = urljoin(
            MUSINSA_BASE_URL,
            url,
        )

        match = cls.PRODUCT_PATTERN.search(absolute_url)

        if not match:
            return absolute_url.split("?")[0]

        goods_no = match.group(1)

        return PRODUCT_BASE_URL.format(goods_no=goods_no)

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

        text = str(value).strip()

        if not text:
            return None

        text = text.replace(",", "").replace("원", "").replace("%", "").strip()

        try:
            return int(float(text))
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_bool(
        value,
        *,
        default: bool = False,
    ) -> bool:
        if value is None:
            return default

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            (int, float),
        ):
            return bool(value)

        text = str(value).strip().lower()

        if text in {
            "true",
            "1",
            "yes",
            "y",
        }:
            return True

        if text in {
            "false",
            "0",
            "no",
            "n",
            "",
        }:
            return False

        return default
