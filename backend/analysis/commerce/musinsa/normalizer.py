from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class NormalizedMusinsaProduct:
    brand: dict[str, Any]
    product: dict[str, Any]
    product_source: dict[str, Any]
    snapshot: dict[str, Any]
    source_attributes: list[dict[str, Any]]
    images: list[dict[str, Any]]


class MusinsaNormalizer:

    SOURCE_CODE = "MUSINSA"

    def normalize_ranking(
        self,
        raw: dict,
    ) -> dict:

        ranking = raw.get("ranking") or {}
        products = raw.get("products") or []

        observed_at = self._parse_datetime(
            ranking.get("collected_at")
        )

        normalized_products = []

        for item in products:
            normalized_products.append(
                self.normalize_product(
                    item,
                    observed_at=observed_at,
                )
            )

        return {
            "source": self.SOURCE_CODE,

            "ranking": {
                "store_code": ranking.get(
                    "store_code"
                ),
                "section_id": ranking.get(
                    "section_id"
                ),
                "category_code": ranking.get(
                    "category_code"
                ),
                "gender": ranking.get(
                    "gender"
                ),
                "age_band": ranking.get(
                    "age_band"
                ),
                "period": ranking.get(
                    "period"
                ),
                "source_url": ranking.get(
                    "source_url"
                ),
                "observed_at": observed_at,
            },

            "products": normalized_products,

            "summary": {
                "product_count": len(
                    normalized_products
                ),
                "error_count": len(
                    raw.get("errors") or []
                ),
            },
        }

    def normalize_product(
        self,
        item: dict,
        *,
        observed_at: datetime | None = None,
    ) -> dict:

        brand_raw = item.get("brand") or {}
        product_raw = item.get("product") or {}
        snapshot_raw = item.get("snapshot") or {}
        ranking_context = (
            item.get("ranking_context")
            or {}
        )
        meta = item.get("meta") or {}

        goods_no = product_raw.get(
            "goods_no"
        )

        if not goods_no:
            raise ValueError(
                "MUSINSA product에 goods_no가 없습니다."
            )

        # ======================================================
        # BRAND
        # ======================================================

        brand = {
            "source_brand_code": (
                brand_raw.get(
                    "brand_code"
                )
            ),

            "name": (
                brand_raw.get("name_ko")
                or brand_raw.get("name_en")
            ),

            "name_ko": (
                brand_raw.get("name_ko")
            ),

            "name_en": (
                brand_raw.get("name_en")
            ),

            "country_code": (
                brand_raw.get(
                    "nation_code"
                )
            ),

            "country_name": (
                brand_raw.get(
                    "nation_name"
                )
            ),

            "since_year": (
                brand_raw.get(
                    "since_year"
                )
            ),

            "logo_url": (
                brand_raw.get(
                    "logo_url"
                )
            ),

            "description": (
                brand_raw.get(
                    "description"
                )
            ),
        }

        # ======================================================
        # CATEGORY
        # ======================================================

        category_raw = (
            product_raw.get("category")
            or {}
        )

        source_category = {
            "depth1_code": (
                category_raw.get(
                    "depth1_code"
                )
            ),

            "depth1_name": (
                category_raw.get(
                    "depth1_name"
                )
            ),

            "depth2_code": (
                category_raw.get(
                    "depth2_code"
                )
            ),

            "depth2_name": (
                category_raw.get(
                    "depth2_name"
                )
            ),

            "depth3_code": (
                category_raw.get(
                    "depth3_code"
                )
            ),

            "depth3_name": (
                category_raw.get(
                    "depth3_name"
                )
            ),

            "depth4_code": (
                category_raw.get(
                    "depth4_code"
                )
            ),

            "depth4_name": (
                category_raw.get(
                    "depth4_name"
                )
            ),
        }

        # ======================================================
        # PRODUCT MASTER
        # ======================================================

        product = {
            "name": (
                product_raw.get("name")
            ),

            "name_en": (
                product_raw.get(
                    "name_en"
                )
            ),

            "style_no": (
                product_raw.get(
                    "style_no"
                )
            ),

            "genders": (
                product_raw.get(
                    "genders"
                )
                or []
            ),

            "season_year": (
                product_raw.get(
                    "season_year"
                )
            ),

            "season": (
                product_raw.get(
                    "season"
                )
            ),

            "thumbnail_url": (
                product_raw.get(
                    "thumbnail_url"
                )
            ),

            "tags": (
                product_raw.get(
                    "tags"
                )
                or []
            ),
        }

        # ======================================================
        # PRODUCT SOURCE
        # ======================================================

        product_source = {
            "source_code": (
                self.SOURCE_CODE
            ),

            "source_product_id": (
                str(goods_no)
            ),

            "source_name": (
                product_raw.get("name")
            ),

            "source_url": (
                ranking_context.get(
                    "product_url"
                )
                or meta.get(
                    "final_url"
                )
                or meta.get(
                    "request_url"
                )
            ),

            "source_brand_code": (
                product_raw.get(
                    "brand_code"
                )
            ),

            "source_category": (
                source_category
            ),

            "sell_start_date": (
                self._parse_datetime(
                    product_raw.get(
                        "sell_start_date"
                    )
                )
            ),

            "sell_end_date": (
                self._parse_datetime(
                    product_raw.get(
                        "sell_end_date"
                    )
                )
            ),

            "sale_start_date": (
                self._parse_datetime(
                    product_raw.get(
                        "sale_start_date"
                    )
                )
            ),

            "sale_end_date": (
                self._parse_datetime(
                    product_raw.get(
                        "sale_end_date"
                    )
                )
            ),
        }

        # ======================================================
        # SNAPSHOT
        # ======================================================

        snapshot = {
            "observed_at": observed_at,

            "list_price": (
                snapshot_raw.get(
                    "regular_price"
                )
            ),

            "sale_price": (
                snapshot_raw.get(
                    "sale_price"
                )
            ),

            "discount_rate": (
                snapshot_raw.get(
                    "discount_rate"
                )
            ),

            "currency": (
                snapshot_raw.get(
                    "currency"
                )
            ),

            "review_count": (
                snapshot_raw.get(
                    "review_count"
                )
            ),

            "rating": (
                snapshot_raw.get(
                    "satisfaction_score"
                )
            ),

            "like_count": (
                snapshot_raw.get(
                    "like_count"
                )
            ),

            "view_count": (
                snapshot_raw.get(
                    "view_count"
                )
            ),

            "sales_count": (
                snapshot_raw.get(
                    "sales_count"
                )
            ),

            "availability": (
                snapshot_raw.get(
                    "availability"
                )
            ),

            "is_out_of_stock": (
                snapshot_raw.get(
                    "is_out_of_stock"
                )
            ),

            "rank_position": (
                ranking_context.get(
                    "rank"
                )
            ),

            "ranking_scope": {
                "period": (
                    ranking_context.get(
                        "ranking_period"
                    )
                ),

                "gender": (
                    ranking_context.get(
                        "ranking_gender"
                    )
                ),

                "category_code": (
                    ranking_context.get(
                        "ranking_category_code"
                    )
                ),

                "age_band": (
                    ranking_context.get(
                        "ranking_age_band"
                    )
                ),
            },
        }

        # ======================================================
        # ATTRIBUTES
        # ======================================================

        attributes = []

        source_attributes = (
            product_raw.get(
                "source_attributes"
            )
            or {}
        )

        for key, values in (
            source_attributes.items()
        ):
            values = (
                values
                if isinstance(
                    values,
                    list,
                )
                else [values]
            )

            for value in values:
                attributes.append(
                    {
                        "source_attribute_name": (
                            key
                        ),
                        "source_attribute_value": (
                            value
                        ),
                    }
                )

        # ======================================================
        # IMAGES
        # ======================================================

        images = []

        thumbnail_url = (
            product_raw.get(
                "thumbnail_url"
            )
        )

        if thumbnail_url:
            images.append(
                {
                    "image_type": "THUMBNAIL",
                    "sequence": 0,
                    "image_url": (
                        thumbnail_url
                    ),
                }
            )

        for image in (
            product_raw.get(
                "product_images"
            )
            or []
        ):
            images.append(
                {
                    "image_type": (
                        "PRODUCT"
                    ),

                    "sequence": (
                        image.get(
                            "sequence"
                        )
                    ),

                    "image_url": (
                        image.get(
                            "image_url"
                        )
                    ),
                }
            )

        detail_content = (
            product_raw.get(
                "detail_content"
            )
            or {}
        )

        for image in (
            detail_content.get(
                "images"
            )
            or []
        ):
            images.append(
                {
                    "image_type": (
                        "DETAIL"
                    ),

                    "sequence": (
                        image.get(
                            "sequence"
                        )
                    ),

                    "image_url": (
                        image.get(
                            "image_url"
                        )
                    ),

                    "alt": (
                        image.get(
                            "alt"
                        )
                    ),
                }
            )

        return {
            "brand": brand,
            "product": product,
            "product_source": (
                product_source
            ),
            "snapshot": snapshot,
            "source_attributes": (
                attributes
            ),
            "images": images,
        }

    @staticmethod
    def _parse_datetime(
        value,
    ) -> datetime | None:

        if not value:
            return None

        if isinstance(
            value,
            datetime,
        ):
            return value

        try:
            return datetime.fromisoformat(
                str(value).replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError:
            return None