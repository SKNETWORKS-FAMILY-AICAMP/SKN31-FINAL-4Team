from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup


class MusinsaUsedProductParseError(ValueError):
    pass


class MusinsaUsedProductParser:
    """PRODUCT-only port of the former MusinsaUsedParser."""

    NEXT_DATA_PATTERN = re.compile(
        r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        re.DOTALL,
    )

    @classmethod
    def parse(
        cls,
        html: str,
        *,
        goods_no: str,
        sale_information: dict | None,
        related_goods_response: dict | None,
        price_anchor: dict | None,
        ranking_context: dict | None,
        meta: dict,
    ) -> dict:
        detail = cls._extract_detail(html, goods_no=str(goods_no))
        if not detail:
            raise MusinsaUsedProductParseError(
                f"MUSINSA_USED detail not found: goods_no={goods_no}"
            )

        used = detail.get("usedProduct")
        used = used if isinstance(used, dict) else {}
        grade = detail.get("usedConditionGrade") or used.get(
            "usedConditionGrade"
        )
        if grade is None:
            raise MusinsaUsedProductParseError(
                f"MUSINSA_USED grade not found: goods_no={goods_no}"
            )

        brand = detail.get("brandInfo")
        brand = brand if isinstance(brand, dict) else {}
        price = detail.get("goodsPrice")
        price = price if isinstance(price, dict) else {}
        review = detail.get("goodsReview")
        review = review if isinstance(review, dict) else {}
        related = cls.parse_related_goods(related_goods_response)

        return {
            "brand": {
                "brand_code": cls._text(
                    brand.get("brand")
                    or brand.get("brandCode")
                    or detail.get("brandCode")
                ),
                "name_ko": cls._text(
                    brand.get("brandName") or detail.get("brandName")
                ),
                "name_en": cls._text(brand.get("brandEnglishName")),
            },
            "product": {
                "goods_no": str(goods_no),
                "original_goods_no": (
                    related["original_goods"].get("goods_no")
                    if related.get("original_goods")
                    else None
                ),
                "style_no": cls._text(detail.get("styleNo")),
                "name": cls._text(
                    detail.get("goodsNm") or detail.get("goodsName")
                ),
                "name_en": cls._text(detail.get("goodsNmEng")),
                "brand_code": cls._text(
                    brand.get("brand")
                    or brand.get("brandCode")
                    or detail.get("brandCode")
                ),
                "category": cls._category(detail.get("category")),
                "genders": cls._genders(
                    detail.get("genders")
                    or detail.get("sex")
                    or detail.get("gender")
                ),
                "size": cls._text(detail.get("size") or detail.get("goodsSize")),
                "thumbnail_url": cls._text(
                    detail.get("thumbnailImageUrl")
                    or detail.get("thumbnail")
                    or (ranking_context or {}).get("thumbnail_url")
                ),
                "source_attributes": detail.get("sourceAttributes") or {},
                "tags": detail.get("tags") or [],
            },
            "snapshot": {
                "regular_price": cls._number(
                    cls._first(detail.get("normalPrice"), price.get("normalPrice"))
                ),
                "sale_price": cls._number(
                    cls._first(
                        detail.get("price"),
                        detail.get("finalPrice"),
                        price.get("finalPrice"),
                        price.get("salePrice"),
                    )
                ),
                "discount_rate": cls._number(
                    cls._first(
                        detail.get("saleRate"),
                        detail.get("finalDiscount"),
                        price.get("saleRate"),
                        price.get("discountRate"),
                    )
                ),
                "currency": cls._text(
                    detail.get("currency") or price.get("currency")
                ) or "KRW",
                "review_count": cls._integer(
                    cls._first(
                        detail.get("reviewCount"),
                        review.get("totalCount"),
                    )
                ),
                "satisfaction_score": cls._number(
                    cls._first(
                        detail.get("reviewScore"),
                        review.get("satisfactionScore"),
                    )
                ),
                "like_count": cls._integer(detail.get("likeCount")),
                "view_count": cls._integer(
                    cls._first(
                        detail.get("pageViewTotal"),
                        detail.get("goodsPageViewCount"),
                    )
                ),
                "purchase_total": cls._integer(detail.get("purchaseTotal")),
                "availability": cls._text(detail.get("availability")),
                "used_condition_grade": cls._text(grade),
                "is_sold_out": cls._boolean(
                    detail.get("isSoldOut")
                    if "isSoldOut" in detail
                    else detail.get("isOutOfStock")
                ),
            },
            "used_price_history": cls._price_history(
                sale_information,
                price_anchor,
            ),
            "related_goods": related,
            # Preserve the complete decoded API response before normalization.
            "related_goods_raw": related_goods_response,
            "ranking_context": ranking_context or {},
            "meta": meta,
        }

    @classmethod
    def parse_related_goods(cls, body: dict | None) -> dict:
        data = body.get("data") if isinstance(body, dict) else {}
        data = data if isinstance(data, dict) else {}
        original = data.get("originalGoods")
        original_goods = None
        if isinstance(original, dict) and original.get("goodsNo") is not None:
            original_goods = {"goods_no": str(original["goodsNo"])}

        used_products = []
        for item in data.get("usedProductsList") or []:
            if isinstance(item, dict) and item.get("goodsNo") is not None:
                used_products.append({"goods_no": str(item["goodsNo"])})
        return {
            "original_goods": original_goods,
            "used_products": used_products,
        }

    @classmethod
    def _extract_detail(cls, html: str, *, goods_no: str) -> dict:
        match = cls.NEXT_DATA_PATTERN.search(html or "")
        if match:
            try:
                root = json.loads(match.group(1))
            except (TypeError, json.JSONDecodeError):
                root = {}
            candidates: list[dict] = []
            cls._walk(root, candidates)
            for candidate in candidates:
                candidate_no = (
                    candidate.get("goodsNo")
                    or candidate.get("goods_no")
                    or candidate.get("productId")
                )
                if str(candidate_no) == goods_no and (
                    candidate.get("usedConditionGrade") is not None
                    or isinstance(candidate.get("usedProduct"), dict)
                ):
                    return candidate

        # JSON script fallback retained from the former parser.
        soup = BeautifulSoup(html or "", "html.parser")
        candidates = []
        for script in soup.find_all("script"):
            text = (script.string or script.get_text() or "").strip()
            if "goodsNo" not in text:
                continue
            try:
                cls._walk(json.loads(text), candidates)
            except (TypeError, json.JSONDecodeError):
                continue
        for candidate in candidates:
            if str(candidate.get("goodsNo")) == goods_no:
                return candidate
        return {}

    @classmethod
    def _walk(cls, value: Any, output: list[dict]) -> None:
        if isinstance(value, dict):
            if any(key in value for key in ("goodsNo", "goods_no", "productId")):
                output.append(value)
            for child in value.values():
                cls._walk(child, output)
        elif isinstance(value, list):
            for child in value:
                cls._walk(child, output)

    @classmethod
    def _price_history(cls, sale: dict | None, anchor: dict | None) -> dict:
        data = sale.get("data") if isinstance(sale, dict) else {}
        data = data if isinstance(data, dict) else {}
        root = data.get("usedProductPriceInfo") or {}
        anchor_data = anchor.get("data") if isinstance(anchor, dict) else {}
        anchor_data = anchor_data if isinstance(anchor_data, dict) else {}
        return {
            "price_anchor_type": (
                anchor_data.get("usedPriceAnchorType")
                or anchor_data.get("priceAnchorType")
                or root.get("priceAnchorType")
            ),
            "first_sale_start": root.get("firstSaleStartDate"),
            "price_change_histories": root.get("changeHistories") or [],
            "discount_scheduled_at": root.get("discountScheduledDate"),
        }

    @classmethod
    def _category(cls, value) -> dict:
        value = value if isinstance(value, dict) else {}
        return {
            f"depth{depth}_{suffix}": cls._text(
                value.get(f"categoryDepth{depth}{'Code' if suffix == 'code' else 'Name'}")
            )
            for depth in range(1, 5)
            for suffix in ("code", "name")
        }

    @classmethod
    def _genders(cls, value) -> list[str] | None:
        if value is None:
            return None
        values = value if isinstance(value, list) else [value]
        result = [cls._text(item) for item in values]
        return [item for item in result if item] or None

    @staticmethod
    def _first(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _text(value) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @staticmethod
    def _number(value):
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value).replace(",", "").replace("%", ""))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @classmethod
    def _integer(cls, value) -> int | None:
        number = cls._number(value)
        return int(number) if number is not None else None

    @staticmethod
    def _boolean(value) -> bool | None:
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return None
        lowered = str(value).strip().lower()
        if lowered in {"true", "1", "y", "yes"}:
            return True
        if lowered in {"false", "0", "n", "no"}:
            return False
        return None
