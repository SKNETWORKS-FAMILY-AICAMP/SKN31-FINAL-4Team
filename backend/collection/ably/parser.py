from __future__ import annotations

import html
import re
from typing import Any

from bs4 import BeautifulSoup

from .constants import PRODUCT_URL_TEMPLATE
from .exceptions import AblyParseError


class AblyParser:
    """ABLY ranking API 상품을 source 중간 형태로 변환한다."""

    @classmethod
    def parse_goods_page(cls, body: dict) -> list[dict]:
        if not isinstance(body, dict):
            raise AblyParseError("ABLY 응답이 dict가 아닙니다.")

        goods = body.get("goods")
        if not isinstance(goods, list):
            raise AblyParseError("ABLY 응답의 goods가 list가 아닙니다.")

        return goods

    @classmethod
    def parse_goods(cls, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise AblyParseError("ABLY goods 항목이 dict가 아닙니다.")

        goods_sno = cls._to_int(raw.get("sno"))
        if goods_sno is None:
            raise AblyParseError("ABLY goods.sno가 없습니다.")

        market = raw.get("market") if isinstance(raw.get("market"), dict) else {}
        category = (
            raw.get("category") if isinstance(raw.get("category"), dict) else {}
        )
        standard_category = (
            raw.get("standard_category")
            if isinstance(raw.get("standard_category"), dict)
            else {}
        )
        linked_option = (
            raw.get("linked_option")
            if isinstance(raw.get("linked_option"), dict)
            else {}
        )

        brand_sno = cls._to_int(raw.get("brand_sno"))
        brand_name = cls._clean_text(raw.get("brand_name"))

        return {
            "source_product_id": str(goods_sno),
            "name": cls._clean_text(raw.get("name")),
            "sku_code": cls._clean_text(raw.get("sku_code")),
            "product_url": PRODUCT_URL_TEMPLATE.format(goods_sno=goods_sno),
            "brand": (
                {
                    "source_brand_id": str(brand_sno),
                    "name": brand_name,
                }
                if brand_sno is not None
                else None
            ),
            "market": {
                "source_market_id": cls._clean_id(
                    market.get("sno") or raw.get("market_sno")
                ),
                "name": cls._clean_text(market.get("name")),
            },
            "category": {
                "source_category_id": cls._clean_id(category.get("sno")),
                "name": cls._clean_text(category.get("name")),
                "depth": cls._to_int(category.get("depth")),
                "standard_category_id": cls._clean_id(
                    standard_category.get("sno")
                    or raw.get("standard_category_sno")
                ),
                "standard_category_name": cls._clean_text(
                    standard_category.get("name")
                ),
            },
            "snapshot": {
                "regular_price": cls._to_int(linked_option.get("original_price")),
                "sale_price": cls._to_int(raw.get("price")),
                "discount_rate": cls._to_float(raw.get("discount_rate")),
                "sales_count": cls._to_int(raw.get("sell_count")),
                "review_count": cls._to_int(raw.get("total_review_count")),
                "positive_review_count": cls._to_int(
                    raw.get("positive_review_count")
                ),
                "positive_review_rate": cls._to_float(
                    raw.get("positive_review_rate")
                ),
                "is_sold_out": cls._to_bool(raw.get("is_soldout")),
                "is_buyable": cls._to_bool(raw.get("is_buyable")),
                "is_open": cls._to_bool(raw.get("is_open")),
            },
            "ranking": {
                "rank": cls._to_int(raw.get("ranking")),
            },
            "images": {
                "image": cls._clean_text(raw.get("image")),
                "image_webp": cls._clean_text(raw.get("image_webp")),
            },
            "attributes": {
                "delivery_type": cls._clean_text(raw.get("delivery_type")),
                "is_new": cls._to_bool(raw.get("is_new")),
                "is_sale": cls._to_bool(raw.get("is_sale")),
                "is_accessible_detail": cls._to_bool(
                    raw.get("is_accessible_detail")
                ),
                "like": raw.get("like"),
                "linked_option_sno": cls._clean_id(linked_option.get("sno")),
            },
        }

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None

        decoded = html.unescape(str(value))
        text = (
            BeautifulSoup(decoded, "html.parser").get_text(" ")
            if "<" in decoded and ">" in decoded
            else decoded
        )
        text = html.unescape(text).replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()

        return text or None

    @classmethod
    def _clean_id(cls, value: Any) -> str | None:
        number = cls._to_int(value)
        return str(number) if number is not None else None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(str(value).replace(",", "").replace("%", "").strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n", ""}:
            return False
        return None
