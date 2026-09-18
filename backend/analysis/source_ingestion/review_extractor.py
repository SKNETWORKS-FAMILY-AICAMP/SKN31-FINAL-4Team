# analysis/source_ingestion/musinsa/review_extractor.py

from __future__ import annotations
from django.utils.dateparse import parse_datetime
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class MusinsaReviewRow:
    # --------------------------------------------------
    # PRODUCT
    # --------------------------------------------------
    goods_no: int
    product_name: str | None
    brand_code: str | None
    brand_name: str | None

    category_depth1: str | None
    category_depth2: str | None

    # --------------------------------------------------
    # REVIEW
    # --------------------------------------------------
    review_id: int
    review_type: str | None
    content: str
    grade: int | None
    goods_option: str | None
    like_count: int
    created_at: str | None

    # --------------------------------------------------
    # REVIEWER
    # --------------------------------------------------
    reviewer_sex: str | None
    reviewer_height: int | None
    reviewer_weight: int | None

    # --------------------------------------------------
    # SURVEY
    # --------------------------------------------------
    survey_size: str | None
    survey_color: str | None
    survey_quality: str | None
    survey_thickness: str | None
    survey_warmth: str | None

    # --------------------------------------------------
    # MEDIA
    # --------------------------------------------------
    image_count: int
    image_urls: list[str]


class MusinsaReviewExtractor:
    """
    Musinsa collector raw JSON
    -> 분석/DB 저장용 review row 추출
    """

    def extract(
        self,
        payload: dict[str, Any],
    ) -> list[MusinsaReviewRow]:

        result: list[MusinsaReviewRow] = []

        products = payload.get("products") or []

        for product_entry in products:
            result.extend(
                self._extract_product_reviews(product_entry)
            )

        return result

    def _extract_product_reviews(
        self,
        entry: dict[str, Any],
    ) -> list[MusinsaReviewRow]:

        product = entry.get("product") or {}
        brand = entry.get("brand") or {}
        reviews = entry.get("reviews") or {}

        goods_no = product.get("goods_no")

        if not goods_no:
            return []

        category = product.get("category") or {}

        rows: list[MusinsaReviewRow] = []

        for review in reviews.get("items") or []:

            content = self._normalize_content(
                review.get("content")
            )

            if not content:
                continue

            reviewer = review.get("reviewer") or {}
            survey = review.get("survey") or {}
            images = review.get("images") or []

            row = MusinsaReviewRow(
                # PRODUCT
                goods_no=int(goods_no),
                product_name=product.get("name"),
                brand_code=brand.get("brand_code"),
                brand_name=brand.get("name_ko"),

                category_depth1=category.get("depth1_name"),
                category_depth2=category.get("depth2_name"),

                # REVIEW
                review_id=int(review["review_id"]),
                review_type=review.get("review_type"),
                content=content,
                grade=self._to_int(review.get("grade")),
                goods_option=review.get("goods_option"),
                like_count=self._to_int(
                    review.get("like_count")
                ) or 0,
                created_at=review.get("created_at"),

                # REVIEWER
                reviewer_sex=reviewer.get("sex"),
                reviewer_height=self._to_int(
                    reviewer.get("height")
                ),
                reviewer_weight=self._to_int(
                    reviewer.get("weight")
                ),

                # SURVEY
                survey_size=self._survey_value(
                    survey,
                    "사이즈",
                ),
                survey_color=self._survey_value(
                    survey,
                    "화면 대비 색감",
                ),
                survey_quality=self._survey_value(
                    survey,
                    "퀄리티",
                ),
                survey_thickness=self._survey_value(
                    survey,
                    "두께감",
                ),
                survey_warmth=self._survey_value(
                    survey,
                    "보온성",
                ),

                # MEDIA
                image_count=len(images),
                image_urls=[
                    str(url)
                    for url in images
                    if url
                ],
            )

            rows.append(row)

        return rows

    @staticmethod
    def _normalize_content(
        value: Any,
    ) -> str:

        if not value:
            return ""

        text = str(value)

        # 개행/탭 등을 하나의 공백으로
        return " ".join(text.split())

    @staticmethod
    def _survey_value(
        survey: dict[str, Any],
        key: str,
    ) -> str | None:

        value = survey.get(key)

        if value is None:
            return None

        if isinstance(value, list):
            if not value:
                return None

            return str(value[0]).strip() or None

        return str(value).strip() or None

    @staticmethod
    def _to_int(
        value: Any,
    ) -> int | None:

        if value in (None, ""):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None


def extract_review_dicts(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:

    extractor = MusinsaReviewExtractor()

    return [
        asdict(row)
        for row in extractor.extract(payload)
    ]