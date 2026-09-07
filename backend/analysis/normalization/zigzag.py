from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.core.models import Brand


class ZigzagNormalizer:
    source_code = "ZIGZAG"

    # 보세 / 비브랜드 쇼핑몰 fallback
    non_brand_code = "BRAND_NON_BRAND_SHOP"

    # =========================================================
    # RANKING NORMALIZE
    # =========================================================

    def normalize_ranking(
        self,
        raw: dict[str, Any],
        *,
        observed_at: datetime | str | None = None,
    ) -> dict[str, Any]:

        ranking = raw.get("ranking") or {}
        ranking_items = ranking.get("items") or []

        detail_items = self._detail_items(raw)

        details_by_id: dict[str, dict[str, Any]] = {}
        detail_order: list[str] = []

        for detail in detail_items:

            source_uid = self._detail_source_uid(
                detail
            )

            if (
                source_uid
                and source_uid not in details_by_id
            ):
                details_by_id[source_uid] = detail
                detail_order.append(source_uid)

        products: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # -----------------------------------------------------
        # 1. ranking 순서 우선
        # -----------------------------------------------------

        for ranking_item in ranking_items:

            if not isinstance(
                ranking_item,
                dict,
            ):
                continue

            source_uid = (
                self._ranking_source_uid(
                    ranking_item
                )
            )

            if (
                not source_uid
                or source_uid in seen_ids
            ):
                continue

            seen_ids.add(
                source_uid
            )

            products.append(
                self.normalize_product(
                    details_by_id.get(
                        source_uid
                    ),
                    ranking_item=ranking_item,
                    observed_at=(
                        observed_at
                        or raw.get(
                            "collected_at"
                        )
                    ),
                )
            )

        # -----------------------------------------------------
        # 2. ranking에는 없고 detail에만 있는 상품
        # -----------------------------------------------------

        for source_uid in detail_order:

            if source_uid in seen_ids:
                continue

            seen_ids.add(
                source_uid
            )

            products.append(
                self.normalize_product(
                    details_by_id[
                        source_uid
                    ],
                    observed_at=(
                        observed_at
                        or raw.get(
                            "collected_at"
                        )
                    ),
                )
            )

        return {
            "source": self.source_code,
            "entity_type": "RANKING",
            "products": products,
        }

    # =========================================================
    # PRODUCT NORMALIZE
    # =========================================================

    def normalize_product(
        self,
        raw_product: dict[str, Any] | None,
        *,
        ranking_item: dict[str, Any] | None = None,
        observed_at: datetime | str | None = None,
    ) -> dict[str, Any]:

        raw_product = (
            raw_product
            or {}
        )

        ranking_item = (
            ranking_item
            or {}
        )

        product = (
            raw_product.get(
                "product"
            )
            or raw_product
        )

        # -----------------------------------------------------
        # SOURCE PRODUCT ID
        # -----------------------------------------------------

        source_uid = (
            self._detail_source_uid(
                raw_product
            )
            or self._ranking_source_uid(
                ranking_item
            )
        )

        if not source_uid:

            raise ValueError(
                "ZIGZAG normalize failed: "
                "source product ID not found."
            )

        # -----------------------------------------------------
        # SHOP
        # -----------------------------------------------------

        shop_info = (
            self._extract_shop(
                product=product,
                raw_product=raw_product,
                ranking_item=ranking_item,
            )
        )

        # -----------------------------------------------------
        # BRAND
        # -----------------------------------------------------

        brand_info = (
            self._resolve_brand(
                shop_name=shop_info[
                    "shop_name"
                ]
            )
        )

        # -----------------------------------------------------
        # CATEGORY
        # -----------------------------------------------------

        (
            source_category_path,
            source_category_name,
            source_category_code,
        ) = self._category(
            product,
            raw_product,
        )

        # -----------------------------------------------------
        # PRICING
        # -----------------------------------------------------

        pricing = (
            product.get(
                "pricing"
            )
            or raw_product.get(
                "pricing"
            )
            or raw_product.get(
                "snapshot"
            )
            or {}
        )

        regular_price = (
            self._first_value(
                pricing.get(
                    "calculated_regular_price"
                ),
                pricing.get(
                    "regular_price"
                ),
            )
        )

        sale_price = (
            self._first_value(
                pricing.get(
                    "final_sale_price"
                ),
                pricing.get(
                    "sale_price"
                ),
                ranking_item.get(
                    "list_price"
                ),
                ranking_item.get(
                    "price"
                ),
            )
        )

        store_sale_price = (
            self._first_value(
                pricing.get(
                    "store_sale_price"
                )
            )
        )

        discount_rate = (
            self._first_value(
                pricing.get(
                    "final_discount_rate"
                ),
                pricing.get(
                    "discount_rate"
                ),
                ranking_item.get(
                    "list_discount_rate"
                ),
                ranking_item.get(
                    "discount"
                ),
            )
        )

        # -----------------------------------------------------
        # BASIC
        # -----------------------------------------------------

        name = (
            self._first_value(
                product.get(
                    "name"
                ),
                raw_product.get(
                    "name"
                ),
                ranking_item.get(
                    "name"
                ),
            )
        )

        source_url = (
            self._first_value(
                raw_product.get(
                    "source_url"
                ),
                raw_product.get(
                    "product_url"
                ),
                ranking_item.get(
                    "product_url"
                ),
            )
        )

        thumbnail_url = (
            self._first_value(
                product.get(
                    "thumbnail_url"
                ),
                product.get(
                    "image_url"
                ),
                raw_product.get(
                    "thumbnail_url"
                ),
                ranking_item.get(
                    "image_url"
                ),
            )
        )

        sales_status = (
            self._first_value(
                product.get(
                    "sales_status"
                ),
                raw_product.get(
                    "sales_status"
                ),
            )
        )

        # -----------------------------------------------------
        # RESULT
        # -----------------------------------------------------

        return {
            # SOURCE
            "source":
                self.source_code,

            "source_uid":
                source_uid,

            "source_url":
                source_url,

            "product_key":
                (
                    f"s:"
                    f"{self.source_code}:"
                    f"{source_uid}"
                ),

            # MATCH
            "match_method":
                "self",

            "match_score":
                0.0,

            # PRODUCT
            "name":
                name,

            "normalized_name":
                self._normalize_text(
                    name
                ),

            "thumbnail_url":
                thumbnail_url,

            # -------------------------------------------------
            # FEEDIT CANONICAL BRAND
            # -------------------------------------------------

            "brand_id":
                brand_info[
                    "brand_id"
                ],

            "brand_code":
                brand_info[
                    "brand_code"
                ],

            "brand_name":
                brand_info[
                    "brand_name"
                ],

            "brand_match_method":
                brand_info[
                    "brand_match_method"
                ],

            # -------------------------------------------------
            # ZIGZAG SOURCE SHOP
            # -------------------------------------------------

            "brand": {
                "source_brand_id":
                    shop_info[
                        "source_brand_id"
                    ],

                "source_brand_name":
                    shop_info[
                        "shop_name"
                    ],

                "source_brand_name_en":
                    None,

                "source_brand_url":
                    None,
            },

            "shop_name":
                shop_info[
                    "shop_name"
                ],

            "shop_domain":
                shop_info[
                    "shop_domain"
                ],

            "shop_bookmark_count":
                shop_info[
                    "shop_bookmark_count"
                ],

            # -------------------------------------------------
            # SOURCE CATEGORY
            # -------------------------------------------------

            "source_category_path":
                source_category_path,

            "source_category_name":
                source_category_name,

            "source_category_code":
                source_category_code,

            # -------------------------------------------------
            # SNAPSHOT
            # -------------------------------------------------

            "regular_price":
                self._as_number(
                    regular_price
                ),

            "sale_price":
                self._as_number(
                    sale_price
                ),

            "store_sale_price":
                self._as_number(
                    store_sale_price
                ),

            "discount_rate":
                self._as_number(
                    discount_rate
                ),

            "rank":
                self._as_int(
                    ranking_item.get(
                        "rank"
                    )
                ),

            "ranking_category_id":
                self._first_value(
                    ranking_item.get(
                        "ranking_category_id"
                    )
                ),

            "review_score":
                self._as_number(
                    ranking_item.get(
                        "review_score"
                    )
                ),

            "review_count":
                self._as_int(
                    ranking_item.get(
                        "review_count"
                    )
                ),

            "sales_status":
                sales_status,

            "observed_at":
                self._first_value(
                    raw_product.get(
                        "collected_at"
                    ),
                    observed_at,
                ),
        }

    # =========================================================
    # BRAND RESOLVE
    # =========================================================

    def _resolve_brand(
        self,
        *,
        shop_name: str | None,
    ) -> dict[str, Any]:

        matched_brand = None

        if shop_name:

            clean_name = (
                str(
                    shop_name
                )
                .strip()
            )

            if clean_name:

                # -------------------------------------------------
                # 1. 한국어 / 표준 브랜드명 EXACT
                # -------------------------------------------------

                matched_brand = (
                    Brand.objects
                    .filter(
                        name=clean_name
                    )
                    .first()
                )

                # -------------------------------------------------
                # 2. 영어 브랜드명 EXACT
                # -------------------------------------------------

                if (
                    matched_brand
                    is None
                ):

                    matched_brand = (
                        Brand.objects
                        .filter(
                            english_name__iexact=(
                                clean_name
                            )
                        )
                        .first()
                    )

        # -----------------------------------------------------
        # MATCH SUCCESS
        # -----------------------------------------------------

        if matched_brand is not None:

            return {
                "brand_id":
                    matched_brand.id,

                "brand_code":
                    matched_brand.brand_code,

                "brand_name":
                    matched_brand.name,

                "brand_match_method":
                    "EXACT_SHOP_NAME",
            }

        # -----------------------------------------------------
        # NON BRAND FALLBACK
        # -----------------------------------------------------

        non_brand = (
            Brand.objects
            .filter(
                brand_code=(
                    self.non_brand_code
                )
            )
            .first()
        )

        if non_brand is None:

            raise RuntimeError(
                "FEEDIT fallback Brand "
                f"'{self.non_brand_code}' "
                "not found."
            )

        return {
            "brand_id":
                non_brand.id,

            "brand_code":
                non_brand.brand_code,

            "brand_name":
                non_brand.name,

            "brand_match_method":
                "NON_BRAND_FALLBACK",
        }

    # =========================================================
    # SHOP EXTRACT
    # =========================================================

    def _extract_shop(
        self,
        *,
        product: dict[str, Any],
        raw_product: dict[str, Any],
        ranking_item: dict[str, Any],
    ) -> dict[str, Any]:

        shop = (
            product.get(
                "shop"
            )
            or {}
        )

        legacy_shop = (
            product.get(
                "brand"
            )
            or raw_product.get(
                "brand"
            )
            or {}
        )

        shop_domain = (
            self._first_value(
                shop.get(
                    "domain"
                ),
                shop.get(
                    "main_domain"
                ),
                legacy_shop.get(
                    "shop_domain"
                ),
                legacy_shop.get(
                    "domain"
                ),
            )
        )

        shop_name = (
            self._first_value(
                ranking_item.get(
                    "shop_name"
                ),
                ranking_item.get(
                    "brand"
                ),
                shop.get(
                    "name"
                ),
                legacy_shop.get(
                    "name_ko"
                ),
                legacy_shop.get(
                    "name"
                ),
            )
        )

        shop_bookmark_count = (
            self._first_value(
                shop.get(
                    "bookmark_count"
                ),
                legacy_shop.get(
                    "bookmark_count"
                ),
            )
        )

        return {
            "source_brand_id":
                (
                    str(
                        shop_domain
                    )
                    if shop_domain
                    else None
                ),

            "shop_name":
                (
                    str(
                        shop_name
                    ).strip()
                    if shop_name
                    else None
                ),

            "shop_domain":
                (
                    str(
                        shop_domain
                    ).strip()
                    if shop_domain
                    else None
                ),

            "shop_bookmark_count":
                self._as_int(
                    shop_bookmark_count
                ),
        }

    # =========================================================
    # DETAIL
    # =========================================================

    @staticmethod
    def _detail_items(
        raw: dict[str, Any],
    ) -> list[dict[str, Any]]:

        products = (
            raw.get(
                "products"
            )
        )

        if isinstance(
            products,
            list,
        ):

            return [
                item
                for item in products
                if isinstance(
                    item,
                    dict,
                )
            ]

        if isinstance(
            raw.get(
                "product"
            ),
            dict,
        ):

            return [
                raw
            ]

        return []

    @staticmethod
    def _detail_source_uid(
        detail: dict[str, Any],
    ) -> str | None:

        product = (
            detail.get(
                "product"
            )
            or {}
        )

        value = (
            ZigzagNormalizer
            ._first_value(
                detail.get(
                    "source_product_id"
                ),
                detail.get(
                    "source_uid"
                ),
                detail.get(
                    "product_id"
                ),
                product.get(
                    "id"
                ),
            )
        )

        if value is None:
            return None

        return str(
            value
        )

    # =========================================================
    # RANKING ID
    # =========================================================

    @staticmethod
    def _ranking_source_uid(
        item: dict[str, Any],
    ) -> str | None:

        value = (
            ZigzagNormalizer
            ._first_value(
                item.get(
                    "product_id"
                ),
                item.get(
                    "source_product_id"
                ),
            )
        )

        if value is None:
            return None

        return str(
            value
        )

    # =========================================================
    # CATEGORY
    # =========================================================

    @staticmethod
    def _category(
        product: dict[str, Any],
        raw_product: dict[str, Any],
    ) -> tuple[
        list[str],
        str | None,
        str | None,
    ]:

        path = (
            product.get(
                "category_path"
            )
            or raw_product.get(
                "category_path"
            )
            or []
        )

        code = (
            product.get(
                "category_code"
            )
            or raw_product.get(
                "category_code"
            )
        )

        # -----------------------------------------------------
        # NEW FORMAT
        # -----------------------------------------------------

        if path:

            normalized_path = [
                str(
                    value
                ).strip()

                for value
                in path

                if (
                    value is not None
                    and str(
                        value
                    ).strip()
                )
            ]

            return (
                normalized_path,

                (
                    normalized_path[
                        -1
                    ]
                    if normalized_path
                    else None
                ),

                (
                    str(
                        code
                    )
                    if code
                    else None
                ),
            )

        # -----------------------------------------------------
        # LEGACY FORMAT
        # -----------------------------------------------------

        legacy = (
            product.get(
                "category"
            )
            or raw_product.get(
                "category"
            )
            or {}
        )

        legacy_path = [
            (
                legacy.get(
                    f"depth{depth}_name"
                )
                or legacy.get(
                    f"depth{depth}"
                )
            )

            for depth
            in range(
                1,
                5,
            )
        ]

        normalized_path = [
            str(
                value
            ).strip()

            for value
            in legacy_path

            if (
                value is not None
                and str(
                    value
                ).strip()
            )
        ]

        legacy_code = (
            legacy.get(
                "category_code"
            )
            or legacy.get(
                "code"
            )
        )

        return (
            normalized_path,

            ZigzagNormalizer
            .get_deepest_category(
                legacy
            ),

            (
                str(
                    legacy_code
                )
                if legacy_code
                else None
            ),
        )

    @staticmethod
    def get_deepest_category(
        category: dict[str, Any],
    ) -> str | None:

        for depth in range(
            4,
            0,
            -1,
        ):

            value = (
                category.get(
                    f"depth{depth}_name"
                )
                or category.get(
                    f"depth{depth}"
                )
            )

            if (
                value
                and str(
                    value
                ).strip()
            ):

                return str(
                    value
                ).strip()

        return None

    # =========================================================
    # UTILS
    # =========================================================

    @staticmethod
    def _first_value(
        *values: Any,
    ) -> Any:

        return next(
            (
                value

                for value
                in values

                if (
                    value is not None
                    and value != ""
                )
            ),
            None,
        )

    @staticmethod
    def _normalize_text(
        value: Any,
    ) -> str:

        return " ".join(
            str(
                value
                or ""
            )
            .lower()
            .split()
        )

    @staticmethod
    def _as_int(
        value: Any,
    ) -> int | None:

        if (
            value is None
            or value == ""
        ):
            return None

        try:

            return int(
                str(
                    value
                )
                .replace(
                    ",",
                    "",
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

    @staticmethod
    def _as_number(
        value: Any,
    ) -> int | float | None:

        if (
            value is None
            or value == ""
        ):
            return None

        try:

            number = float(
                str(
                    value
                )
                .replace(
                    ",",
                    "",
                )
                .replace(
                    "%",
                    "",
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

        if number.is_integer():
            return int(
                number
            )

        return number