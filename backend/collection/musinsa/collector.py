from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .client import MusinsaClient
from .constants import MUSINSA_BASE_URL, PRODUCT_BASE_URL
from .exceptions import MusinsaCollectError
from .product import MusinsaProductCollector
from .ranking import MusinsaRankingCollector
from .review import MusinsaReviewCollector
from .schemas import build_raw_record


class MusinsaCollector:
    PRODUCT_PATTERN = re.compile(r"/products/(\d+)")

    def __init__(self, *, timeout: int | float | None = None, session=None):
        self.client = MusinsaClient(timeout=timeout, session=session)
        self.products = MusinsaProductCollector(self.client)
        self.ranking = MusinsaRankingCollector(self.client)
        self.reviews = MusinsaReviewCollector(self.client)

    def close(self): self.client.close()
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): self.close()

    def discover_product_urls(self, target_url: str) -> list[str]:
        if not target_url: return []
        if self.PRODUCT_PATTERN.search(target_url): return [self._normalize_product_url(target_url)]
        if "/ranking" in target_url:
            return [item["product_url"] for item in self.ranking.discover_current(target_url)]
        response = self.client.get(target_url)
        soup = BeautifulSoup(response.text, "html.parser")
        result, seen = [], set()
        for tag in soup.find_all("a", href=True):
            href = tag.get("href")
            if not href or not self.PRODUCT_PATTERN.search(href): continue
            url = self._normalize_product_url(urljoin(response.url, href))
            if url in seen: continue
            seen.add(url); result.append(url)
        return result

    def collect_product(self, url: str, *, ranking_context: dict | None = None, collect_options: bool = True, collect_reviews: bool = False, review_limit: int = 50) -> dict:
        product_url = self._normalize_product_url(url)
        parsed = self.products.collect_detail(product_url)
        product = parsed.get("product") or {}
        snapshot = parsed.get("snapshot") or {}
        goods_no = self._to_int(product.get("goods_no"))
        if goods_no is None:
            raise MusinsaCollectError(f"상품번호를 확인할 수 없습니다: {product_url}")

        try:
            tags = self.products.collect_tags(goods_no)
            if tags is not None: product["tags"] = tags
        except MusinsaCollectError:
            pass

        try:
            stat = self.products.collect_stat(goods_no)
            snapshot.update(stat)
        except MusinsaCollectError:
            pass

        try:
            snapshot["like_count"] = self.products.collect_like_counts([goods_no]).get(goods_no)
        except MusinsaCollectError:
            snapshot["like_count"] = None

        if collect_options:
            try:
                parsed["options"] = self.products.collect_options(goods_no)
            except MusinsaCollectError:
                parsed["options"] = None

        try:
            review_summary = self.reviews.collect_summary(goods_no)
            snapshot["review_count"] = review_summary.get("total_count") or snapshot.get("review_count")
            snapshot["satisfaction_score"] = review_summary.get("satisfaction_score") or snapshot.get("satisfaction_score")
        except MusinsaCollectError:
            review_summary = None

        if collect_reviews:
            try:
                review_items = self.reviews.collect_reviews(goods_no, limit=review_limit)
            except MusinsaCollectError:
                review_items = []
            parsed["reviews"] = {"summary": review_summary, "items": review_items}
        elif review_summary is not None:
            parsed["reviews"] = {"summary": review_summary, "items": []}

        parsed["product"] = product
        parsed["snapshot"] = snapshot
        return build_raw_record(product_url=product_url, parsed=parsed, ranking_context=ranking_context)

    def collect_products(self, urls: list[str], *, collect_options: bool = True, collect_reviews: bool = False, review_limit: int = 50) -> list[dict]:
        result = []
        for url in urls:
            result.append(self.collect_product(url, collect_options=collect_options, collect_reviews=collect_reviews, review_limit=review_limit))
        return result

    def collect_ranking_products(self, ranking_url: str, *, collect_options: bool = False, collect_reviews: bool = False, review_limit: int = 20) -> list[dict]:
        result = []
        for context in self.ranking.discover_current(ranking_url):
            result.append(self.collect_product(context["product_url"], ranking_context=context, collect_options=collect_options, collect_reviews=collect_reviews, review_limit=review_limit))
        return result

    @classmethod
    def _normalize_product_url(cls, url: str) -> str:
        absolute = urljoin(MUSINSA_BASE_URL, url)
        match = cls.PRODUCT_PATTERN.search(absolute)
        return PRODUCT_BASE_URL.format(goods_no=match.group(1)) if match else absolute.split("?")[0]

    @staticmethod
    def _to_int(value):
        try: return int(float(value))
        except (TypeError, ValueError): return None
