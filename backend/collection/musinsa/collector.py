from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .client import MusinsaClient
from .constants import (
    DEFAULT_REVIEW_PAGE_SIZE,
    LIKE_API_URL,
    MUSINSA_BASE_URL,
    OPTIONS_API_URL,
    PRODUCT_BASE_URL,
    RANKING_API_URL,
    REVIEW_LIST_API_URL,
    REVIEW_SUMMARY_API_URL,
    STAT_API_URL,
    TAG_API_URL,
)
from .exceptions import MusinsaCollectError
from .images import normalize_image_url
from .parser import MusinsaParser


class MusinsaCollector:
    """
    MUSINSA source-level collector.

    PRODUCT:
    - 상품/브랜드/가격/통계
    - 상품 갤러리 이미지
    - 상세페이지 이미지/HTML
    - 옵션
    - 리뷰 요약/본문

    RANKING:
    - 랭킹 scope
    - 랭킹 상품 목록
    - 각 상품 상세 수집

    저장(S3/DB), Celery, FEEDIT 정규화는 하지 않는다.
    """

    PRODUCT_PATTERN = re.compile(r"/products/(\d+)")

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session=None,
    ):
        self.client = MusinsaClient(
            timeout=timeout,
            session=session,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ============================================================
    # PRODUCT URL DISCOVERY
    # ============================================================

    def discover_product_urls(self, target_url: str) -> list[str]:
        if not target_url:
            return []

        if self.PRODUCT_PATTERN.search(target_url):
            return [self._normalize_product_url(target_url)]

        if "/ranking" in target_url:
            return [
                item["product_url"]
                for item in self.discover_ranking(target_url)
            ]

        response = self.client.get_html(target_url)
        soup = BeautifulSoup(response.text, "html.parser")

        result: list[str] = []
        seen: set[str] = set()

        for tag in soup.find_all("a", href=True):
            href = tag.get("href")

            if not href or not self.PRODUCT_PATTERN.search(href):
                continue

            product_url = self._normalize_product_url(
                urljoin(response.url, href)
            )

            if product_url in seen:
                continue

            seen.add(product_url)
            result.append(product_url)

        return result

    # ============================================================
    # PRODUCT
    # ============================================================

    def collect_product(
        self,
        url: str,
        *,
        ranking_context: dict | None = None,
        collect_options: bool = True,
        collect_reviews: bool = True,
        review_limit: int = DEFAULT_REVIEW_PAGE_SIZE,
    ) -> dict:
        product_url = self._normalize_product_url(url)

        response = self.client.get_html(product_url)
        parsed = MusinsaParser.parse_product(response.text)

        product = parsed.get("product") or {}
        snapshot = parsed.get("snapshot") or {}
        meta = parsed.get("meta") or {}

        goods_no = self._to_int(product.get("goods_no"))

        if goods_no is None:
            raise MusinsaCollectError(
                f"상품번호를 찾을 수 없습니다: {product_url}"
            )

        # tags
        try:
            tags = self.collect_tags(goods_no)
            if tags is not None:
                product["tags"] = tags
        except MusinsaCollectError:
            pass

        # stat
        try:
            snapshot.update(self.collect_stat(goods_no))
        except MusinsaCollectError:
            snapshot["view_count"] = None
            snapshot["sales_count"] = None

        # like
        try:
            snapshot["like_count"] = self.collect_like_count(goods_no)
        except MusinsaCollectError:
            snapshot["like_count"] = None

        # review summary
        try:
            review_summary = self.collect_review_summary(goods_no)

            if review_summary.get("total_count") is not None:
                snapshot["review_count"] = review_summary["total_count"]

            if review_summary.get("satisfaction_score") is not None:
                snapshot["satisfaction_score"] = review_summary[
                    "satisfaction_score"
                ]
        except MusinsaCollectError:
            review_summary = None

        # review items
        review_items: list[dict] = []

        if collect_reviews:
            try:
                review_items = self.collect_reviews(
                    goods_no,
                    limit=review_limit,
                )
            except MusinsaCollectError:
                review_items = []

        # options
        options = None

        if collect_options:
            try:
                options = self.collect_options(goods_no)
            except MusinsaCollectError:
                options = None

        meta.update(
            {
                "request_url": product_url,
                "final_url": response.url,
                "http_status": response.status_code,
                "content_type": response.headers.get("Content-Type"),
            }
        )

        return {
            "brand": parsed.get("brand"),
            "product": product,
            "snapshot": snapshot,
            "options": options,
            "reviews": {
                "summary": review_summary,
                "items": review_items,
            },
            "ranking_context": ranking_context,
            "meta": meta,
        }

    # ============================================================
    # TAG
    # ============================================================

    def collect_tags(self, goods_no: int) -> list[str] | None:
        body = self.client.get_json(
            TAG_API_URL.format(goods_no=goods_no),
            referer=PRODUCT_BASE_URL.format(goods_no=goods_no),
        )

        data = body.get("data") or {}
        tags = data.get("tags")

        if not isinstance(tags, list):
            return None

        result = [
            str(tag).strip()
            for tag in tags
            if tag is not None and str(tag).strip()
        ]

        return list(dict.fromkeys(result)) or None

    # ============================================================
    # STAT
    # ============================================================

    def collect_stat(self, goods_no: int) -> dict:
        body = self.client.get_json(
            STAT_API_URL.format(goods_no=goods_no),
            referer=PRODUCT_BASE_URL.format(goods_no=goods_no),
        )

        data = body.get("data") or {}

        return {
            "view_count": self._to_int(data.get("pageViewTotal")),
            "sales_count": self._to_int(data.get("purchaseTotal")),
        }

    # ============================================================
    # LIKE
    # ============================================================

    def collect_like_count(self, goods_no: int) -> int | None:
        body = self.client.post_json(
            LIKE_API_URL,
            json={"relationIds": [goods_no]},
            headers={
                "Origin": MUSINSA_BASE_URL,
                "Referer": f"{MUSINSA_BASE_URL}/",
            },
        )

        items = (
            ((body.get("data") or {}).get("contents") or {}).get("items")
            or []
        )

        for item in items:
            if not isinstance(item, dict):
                continue

            relation_id = self._to_int(item.get("relationId"))

            if relation_id == goods_no:
                return self._to_int(item.get("count"))

        return None

    # ============================================================
    # OPTIONS
    # ============================================================

    def collect_options(self, goods_no: int) -> dict | None:
        body = self.client.get_json(
            OPTIONS_API_URL.format(goods_no=goods_no),
            params={
                "goodsSaleType": "SALE",
                "optKindCd": "CLOTHES",
            },
            referer=PRODUCT_BASE_URL.format(goods_no=goods_no),
        )

        data = body.get("data")

        # RAW 단계에서는 API data를 최대한 그대로 보존.
        return data if isinstance(data, dict) else None

    # ============================================================
    # REVIEWS
    # ============================================================

    def collect_review_summary(self, goods_no: int) -> dict:
        body = self.client.get_json(
            REVIEW_SUMMARY_API_URL.format(goods_no=goods_no),
            referer=PRODUCT_BASE_URL.format(goods_no=goods_no),
        )

        data = (
            body.get("data")
            if isinstance(body.get("data"), dict)
            else {}
        )

        return {
            "total_count": self._to_int(data.get("totalCount")),
            "general_count": self._to_int(data.get("generalCount")),
            "photo_count": self._to_int(data.get("photoCount")),
            "satisfaction_score": data.get("satisfactionScore"),
        }

    def collect_reviews(
        self,
        goods_no: int,
        *,
        limit: int = DEFAULT_REVIEW_PAGE_SIZE,
        sort: str = "up_cnt_desc",
    ) -> list[dict]:
        if limit <= 0:
            return []

        page_size = min(limit, 100)
        page = 0
        result: list[dict] = []

        while len(result) < limit:
            body = self.client.get_json(
                REVIEW_LIST_API_URL,
                params={
                    "page": page,
                    "pageSize": page_size,
                    "goodsNo": goods_no,
                    "sort": sort,
                    "selectedSimilarNo": goods_no,
                    "myFilter": "false",
                    "hasPhoto": "false",
                    "isExperience": "false",
                },
                referer=PRODUCT_BASE_URL.format(goods_no=goods_no),
            )

            data = (
                body.get("data")
                if isinstance(body.get("data"), dict)
                else {}
            )

            items = data.get("list") or []

            if not items:
                break

            for item in items:
                if not isinstance(item, dict):
                    continue

                profile = (
                    item.get("userProfileInfo")
                    if isinstance(item.get("userProfileInfo"), dict)
                    else {}
                )

                survey = (
                    item.get("reviewSurveySatisfaction")
                    if isinstance(
                        item.get("reviewSurveySatisfaction"),
                        dict,
                    )
                    else {}
                )

                survey_values: dict = {}

                for question in survey.get("questions") or []:
                    if not isinstance(question, dict):
                        continue

                    answers = question.get("answers") or []

                    values = [
                        answer.get("answerShortText")
                        for answer in answers
                        if (
                            isinstance(answer, dict)
                            and answer.get("answerShortText")
                        )
                    ]

                    attribute = question.get("attribute")

                    if attribute and values:
                        survey_values[attribute] = values

                images: list[str] = []

                for image in item.get("images") or []:
                    if not isinstance(image, dict):
                        continue

                    image_url = normalize_image_url(
                        image.get("imageUrl")
                    )

                    if image_url:
                        images.append(image_url)

                result.append(
                    {
                        "review_id": item.get("no"),
                        "review_type": item.get("type"),
                        "content": item.get("content"),
                        "grade": item.get("grade"),
                        "goods_option": item.get("goodsOption"),
                        "like_count": item.get("likeCount"),
                        "created_at": item.get("createDate"),
                        "images": images,
                        "reviewer": {
                            "sex": profile.get("reviewSex"),
                            "height": profile.get("userHeight"),
                            "weight": profile.get("userWeight"),
                        },
                        "survey": survey_values,
                    }
                )

                if len(result) >= limit:
                    break

            page_info = (
                data.get("page")
                if isinstance(data.get("page"), dict)
                else {}
            )

            total_pages = page_info.get("totalPages")
            page += 1

            if total_pages is not None and page >= total_pages:
                break

        return result[:limit]

    # ============================================================
    # RANKING
    # ============================================================

    def discover_ranking(self, target_url: str) -> list[dict]:
        query = parse_qs(
            urlparse(target_url).query,
            keep_blank_values=True,
        )

        period = query.get("period", ["DAILY"])[0]
        gender = query.get("gf", ["A"])[0]
        category_code = query.get("categoryCode", [""])[0]
        age_band = query.get("ageBand", ["AGE_BAND_ALL"])[0]

        body = self.client.get_json(
            RANKING_API_URL,
            params={
                "storeCode": query.get("storeCode", ["musinsa"])[0],
                "sectionId": query.get("sectionId", ["200"])[0],
                "contentsId": query.get("contentsId", [""])[0],
                "subPan": query.get("subPan", ["product"])[0],
                "gf": gender,
                "categoryCode": category_code,
                "ageBand": age_band,
                "period": period,
            },
            referer=target_url,
        )

        modules = (
            (body.get("data") or {}).get("modules")
            or []
        )

        result: list[dict] = []
        seen: set[int] = set()
        fallback_rank = 1

        for module in modules:
            if (
                not isinstance(module, dict)
                or module.get("type") != "MULTICOLUMN"
            ):
                continue

            for item in module.get("items") or []:
                if not isinstance(item, dict):
                    continue

                onclick = (
                    item.get("onClick")
                    if isinstance(item.get("onClick"), dict)
                    else {}
                )

                goods_no = self._extract_goods_no(
                    onclick.get("url")
                )

                if goods_no is None or goods_no in seen:
                    continue

                seen.add(goods_no)

                rank = (
                    self._to_int(item.get("rank"))
                    or fallback_rank
                )

                result.append(
                    {
                        "rank": rank,
                        "goods_no": goods_no,
                        "product_url": PRODUCT_BASE_URL.format(
                            goods_no=goods_no
                        ),
                        "ranking_period": period,
                        "ranking_gender": gender,
                        "ranking_category_code": (
                            category_code or None
                        ),
                        "ranking_age_band": age_band,
                    }
                )

                fallback_rank += 1

        return result

    # ============================================================
    # UTILS
    # ============================================================

    @classmethod
    def _normalize_product_url(cls, url: str) -> str:
        absolute = urljoin(MUSINSA_BASE_URL, url)
        match = cls.PRODUCT_PATTERN.search(absolute)

        if match:
            return PRODUCT_BASE_URL.format(
                goods_no=match.group(1)
            )

        return absolute.split("?")[0]

    @classmethod
    def _extract_goods_no(cls, url) -> int | None:
        if not url:
            return None

        match = cls.PRODUCT_PATTERN.search(str(url))

        if not match:
            return None

        return int(match.group(1))

    @staticmethod
    def _to_int(value) -> int | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
