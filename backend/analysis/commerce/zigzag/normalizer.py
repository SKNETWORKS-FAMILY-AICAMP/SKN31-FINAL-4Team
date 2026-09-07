"""Transform Zigzag L0 collection documents into the project's L1 shape.

Zigzag's "brand" in the source payload identifies the selling shop. It is
stored as a BrandSource and may be auto-matched to a canonical Brand only when
its name exactly matches an existing Brand record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class ZigzagNormalizer:
    """Normalize ranking and product L0 JSON without any database access."""

    source_code = "ZIGZAG"

    def normalize_ranking(
        self,
        raw: dict[str, Any],
        *,
        observed_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Join ranking items and product details by Zigzag product ID.

        Ranking order is preserved.  A ranking item without a detail response is
        still useful and is kept; a detail document not present in ranking is
        appended after the ranking items.
        """

        ranking = raw.get("ranking") or {}
        ranking_items = ranking.get("items") or []
        detail_items = self._detail_items(raw)

        details_by_id: dict[str, dict[str, Any]] = {}
        detail_order: list[str] = []
        for detail in detail_items:
            source_uid = self._detail_source_uid(detail)
            if source_uid and source_uid not in details_by_id:
                details_by_id[source_uid] = detail
                detail_order.append(source_uid)

        products: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for ranking_item in ranking_items:
            source_uid = self._ranking_source_uid(ranking_item)
            if not source_uid or source_uid in seen_ids:
                continue
            seen_ids.add(source_uid)
            products.append(
                self.normalize_product(
                    details_by_id.get(source_uid),
                    ranking_item=ranking_item,
                    observed_at=observed_at or raw.get("collected_at"),
                )
            )

        for source_uid in detail_order:
            if source_uid in seen_ids:
                continue
            seen_ids.add(source_uid)
            products.append(
                self.normalize_product(
                    details_by_id[source_uid],
                    observed_at=observed_at or raw.get("collected_at"),
                )
            )

        return {
            "source": self.source_code,
            "entity_type": "RANKING",
            "products": products,
        }

    def normalize_product(
        self,
        raw_product: dict[str, Any] | None,
        *,
        ranking_item: dict[str, Any] | None = None,
        observed_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Normalize one product detail, optionally enriched by its rank item."""

        raw_product = raw_product or {}
        ranking_item = ranking_item or {}
        product = raw_product.get("product") or raw_product

        source_uid = self._detail_source_uid(raw_product) or self._ranking_source_uid(ranking_item)
        if not source_uid:
            raise ValueError("Zigzag product has no source product ID")

        shop = product.get("shop") or {}
        legacy_shop = product.get("brand") or raw_product.get("brand") or {}
        shop_domain = self._first_value(
            shop.get("domain"),
            shop.get("main_domain"),
            legacy_shop.get("shop_domain"),
            legacy_shop.get("domain"),
        )
        shop_name = self._first_value(
            ranking_item.get("shop_name"),
            ranking_item.get("brand"),
            shop.get("name"),
            legacy_shop.get("name_ko"),
            legacy_shop.get("name"),
        )
        shop_bookmark_count = self._first_value(
            shop.get("bookmark_count"),
            legacy_shop.get("bookmark_count"),
        )

        category_path, category_name, category_code = self._category(product, raw_product)
        pricing = product.get("pricing") or raw_product.get("pricing") or raw_product.get("snapshot") or {}
        regular_price = self._first_value(
            pricing.get("calculated_regular_price"),
            pricing.get("regular_price"),
        )
        sale_price = self._first_value(
            pricing.get("final_sale_price"),
            pricing.get("sale_price"),
            ranking_item.get("list_price"),
            ranking_item.get("price"),
        )
        store_sale_price = self._first_value(pricing.get("store_sale_price"))
        discount_rate = self._first_value(
            pricing.get("final_discount_rate"),
            pricing.get("discount_rate"),
            ranking_item.get("list_discount_rate"),
            ranking_item.get("discount"),
        )

        name = self._first_value(
            product.get("name"),
            raw_product.get("name"),
            ranking_item.get("name"),
        )
        source_url = self._first_value(
            raw_product.get("source_url"),
            raw_product.get("product_url"),
            ranking_item.get("product_url"),
        )
        thumbnail_url = self._first_value(
            product.get("thumbnail_url"),
            product.get("image_url"),
            raw_product.get("thumbnail_url"),
            ranking_item.get("image_url"),
        )
        return {
            "source": self.source_code,
            "source_uid": source_uid,
            "source_url": source_url,
            "product_key": f"s:{self.source_code}:{source_uid}",
            "match_method": "self",
            "match_score": 0.0,
            "name": name,
            "normalized_name": self._normalize_text(name),
            # Canonical Brand linkage is resolved during BrandSource persistence.
            "brand_name": None,
            "brand": {
                "source_brand_id": str(shop_domain) if shop_domain else None,
                "source_brand_name": shop_name,
                "source_brand_name_en": None,
                "source_brand_url": None,
            },
            "shop_name": shop_name,
            "shop_domain": shop_domain,
            "shop_bookmark_count": self._as_int(shop_bookmark_count),
            "source_category_path": category_path,
            "source_category_name": category_name,
            "source_category_code": category_code,
            "regular_price": self._as_number(regular_price),
            "sale_price": self._as_number(sale_price),
            "store_sale_price": self._as_number(store_sale_price),
            "discount_rate": self._as_number(discount_rate),
            "rank": self._as_int(ranking_item.get("rank")),
            "ranking_category_id": self._first_value(ranking_item.get("ranking_category_id")),
            "review_score": self._as_number(ranking_item.get("review_score")),
            "review_count": self._as_int(ranking_item.get("review_count")),
            "thumbnail_url": thumbnail_url,
            "sales_status": self._first_value(product.get("sales_status"), raw_product.get("sales_status")),
            "observed_at": self._first_value(raw_product.get("collected_at"), observed_at),
        }

    @staticmethod
    def _detail_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
        products = raw.get("products")
        if isinstance(products, list):
            return [item for item in products if isinstance(item, dict)]
        if isinstance(raw.get("product"), dict):
            return [raw]
        return []

    @staticmethod
    def _detail_source_uid(detail: dict[str, Any]) -> str | None:
        product = detail.get("product") or {}
        value = ZigzagNormalizer._first_value(
            detail.get("source_product_id"),
            detail.get("source_uid"),
            detail.get("product_id"),
            product.get("id"),
        )
        return str(value) if value is not None else None

    @staticmethod
    def _ranking_source_uid(item: dict[str, Any]) -> str | None:
        value = ZigzagNormalizer._first_value(item.get("product_id"), item.get("source_product_id"))
        return str(value) if value is not None else None

    @staticmethod
    def _category(
        product: dict[str, Any],
        raw_product: dict[str, Any],
    ) -> tuple[list[str], str | None, str | None]:
        path = product.get("category_path") or raw_product.get("category_path") or []
        code = product.get("category_code") or raw_product.get("category_code")
        if path:
            normalized_path = [
                str(value).strip()
                for value in path
                if value is not None and str(value).strip()
            ]
            return (
                normalized_path,
                normalized_path[-1] if normalized_path else None,
                str(code) if code else None,
            )

        legacy = product.get("category") or raw_product.get("category") or {}
        path = [
            legacy.get(f"depth{depth}_name") or legacy.get(f"depth{depth}")
            for depth in range(1, 5)
        ]
        normalized_path = [
            str(value).strip()
            for value in path
            if value is not None and str(value).strip()
        ]
        return (
            normalized_path,
            ZigzagNormalizer.get_deepest_category(legacy),
            str(legacy.get("category_code") or legacy.get("code"))
            if legacy.get("category_code") or legacy.get("code")
            else None,
        )

    @staticmethod
    def get_deepest_category(category: dict[str, Any]) -> str | None:
        """Return the deepest non-empty category without guessing a parent."""

        for depth in range(4, 0, -1):
            value = category.get(f"depth{depth}_name") or category.get(f"depth{depth}")
            if value and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _first_value(*values: Any) -> Any:
        return next((value for value in values if value is not None and value != ""), None)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return " ".join(str(value or "").lower().split())

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_number(value: Any) -> int | float | None:
        if value is None or value == "":
            return None
        try:
            number = float(str(value).replace(",", "").replace("%", ""))
        except (TypeError, ValueError):
            return None
        return int(number) if number.is_integer() else number
