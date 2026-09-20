from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import (
    BrandSource,
    CategorySource,
    ProductSource,
    ProductSourceSnapshot,
)

from analysis.source_ingestion.common import (
    clean_text,
    normalize_brand_name,
    normalize_category_name,
)

from analysis.source_ingestion.product_name_preprocessor import (
    ProductNamePreprocessor,
)


_SNAPSHOT_TIME_KEYS = {
    "observed_at",
    "collected_at",
    "created_at",
    "updated_at",
}


def _snapshot_business_value(value):
    if isinstance(value, dict):
        return {
            key: _snapshot_business_value(item)
            for key, item in value.items()
            if key not in _SNAPSHOT_TIME_KEYS
        }
    if isinstance(value, list):
        return [_snapshot_business_value(item) for item in value]
    return value


def extract_deepest_category(
    product_data: dict | None,
) -> dict | None:
    """
    Musinsa product.category에서 가장 깊은 유효 카테고리를 추출한다.

    common.py 의존 없이 musinsa.py 내부에서 처리한다.

    반환:
    {
        "source_category_id": "003002",
        "source_category_name": "데님 팬츠",
        "source_category_path": "바지 > 데님 팬츠",
        "normalized_name": "데님 팬츠",
        "depth": 2,
    }
    """
    if not isinstance(product_data, dict):
        return None

    category_data = product_data.get("category")

    if not isinstance(category_data, dict):
        return None

    categories = []

    for depth in range(1, 5):
        code = clean_text(
            category_data.get(
                f"depth{depth}_code"
            )
        )

        name = clean_text(
            category_data.get(
                f"depth{depth}_name"
            )
        )

        # 플랫폼 원본 category code가 있는 depth만 사용.
        if code is None:
            continue

        categories.append(
            {
                "depth": depth,
                "code": code,
                "name": name,
            }
        )

    if not categories:
        return None

    deepest = categories[-1]

    path_parts = [
        row["name"]
        for row in categories
        if row["name"]
    ]

    return {
        "source_category_id": deepest["code"],
        "source_category_name": deepest["name"],
        "source_category_path": (
            " > ".join(path_parts)
            if path_parts
            else None
        ),
        "normalized_name": normalize_category_name(
            deepest["name"]
        ),
        "depth": deepest["depth"],
    }


class MusinsaNormalizer:
    """
    MUSINSA parsed data -> FEEDIT source layer normalization.

    이 모듈의 책임은 Source Layer 적재까지다.
    - BrandSource
    - CategorySource
    - ProductSource
    - ProductSourceSnapshot

    FEEDIT 표준 Brand / Category / Product 매핑은 여기서 수행하지 않는다.
    """

    def __init__(self, *, source):
        self.source = source

    # ============================================================
    # RUN
    # ============================================================

    @transaction.atomic
    def run(
        self,
        parsed: dict,
        *,
        observed_at: datetime | None = None,
    ) -> dict:
        """
        한 상품의 Source Normalization 전체 흐름.

        parsed
        -> BrandSource
        -> CategorySource
        -> ProductSource
        -> ProductSourceSnapshot

        여기서는 Brand / Category / Product 표준 매핑을 하지 않는다.
        """
        if not isinstance(parsed, dict):
            raise ValueError("parsed는 dict여야 합니다.")

        product_data = (
            parsed.get("product")
            if isinstance(parsed.get("product"), dict)
            else {}
        )

        brand_data = self._build_brand_data(parsed)

        brand_result = self.normalize_brand(brand_data)
        category_result = self.normalize_category(product_data)

        product_result = self.normalize_product_source(
            parsed,
            source_brand=brand_result.get("brand_source"),
            source_category=category_result.get("category_source"),
        )

        product_source = product_result["product_source"]

        snapshot_result = self.normalize_snapshot(
            parsed,
            product_source=product_source,
            observed_at=observed_at,
        )

        return {
            "brand": brand_result,
            "category": category_result,
            "product": product_result,
            "snapshot": snapshot_result,
        }

    @staticmethod
    def _build_brand_data(parsed: dict) -> dict:
        """
        parser 버전 차이 때문에 brand 정보가 product에만 있는 경우를 보강한다.
        """
        product_data = (
            parsed.get("product")
            if isinstance(parsed.get("product"), dict)
            else {}
        )
        brand_data = (
            parsed.get("brand")
            if isinstance(parsed.get("brand"), dict)
            else {}
        )

        merged = dict(brand_data)

        if not (merged.get("brand_code") or merged.get("brand_id")):
            fallback_brand_code = (
                product_data.get("brand_code")
                or product_data.get("brand_id")
            )
            if fallback_brand_code:
                merged["brand_code"] = fallback_brand_code

        if not (
            merged.get("name_ko")
            or merged.get("brand_name")
            or merged.get("name_en")
        ):
            fallback_brand_name = (
                product_data.get("brand_name")
                or product_data.get("brand_name_ko")
            )
            if fallback_brand_name:
                merged["brand_name"] = fallback_brand_name

        return merged

    # ============================================================
    # BRAND
    # ============================================================

    @transaction.atomic
    def normalize_brand(
        self,
        brand_data: dict | None,
    ) -> dict:
        """플랫폼 브랜드 원본을 BrandSource로만 정규화한다."""
        if not isinstance(brand_data, dict):
            brand_data = {}

        source_brand_id = clean_text(
            brand_data.get("brand_code")
            or brand_data.get("brand_id")
        )

        name = clean_text(
            brand_data.get("name_ko")
            or brand_data.get("brand_name")
            or brand_data.get("name_en")
        )
        english_name = clean_text(brand_data.get("name_en"))
        image_url = clean_text(brand_data.get("logo_url"))
        country_code = clean_text(brand_data.get("nation_code"))
        description = clean_text(brand_data.get("description"))

        if source_brand_id is None and name is None:
            return {
                "created": False,
                "brand_source": None,
                "source_brand": None,
            }

        # 무신사는 보통 brand_code가 있다. 없을 때만 정규화 이름을 fallback identity로 사용한다.
        if source_brand_id is None:
            normalized = normalize_brand_name(name)
            source_brand_id = f"NAME:{normalized or name}"

        attributes = {}
        nation_name = brand_data.get("nation_name")
        since_year = brand_data.get("since_year")
        if nation_name is not None:
            attributes["nation_name"] = nation_name
        if since_year is not None:
            attributes["since_year"] = since_year

        now = timezone.now()

        brand_source = BrandSource.objects.filter(
            source=self.source,
            source_brand_id=source_brand_id,
        ).first()

        if brand_source is None:
            brand_source = BrandSource.objects.create(
                brand=None,
                source=self.source,
                source_brand_id=source_brand_id,
                name=name or source_brand_id,
                english_name=english_name,
                image_url=image_url,
                country_code=country_code,
                description=description,
                target_gender=None,
                target_age=None,
                website_url=None,
                source_profile_url=None,
                attributes=attributes or None,
                mapping_status=BrandSource.MappingStatus.UNMAPPED,
                mapping_method=None,
                mapping_confidence=None,
                detected_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            created = True
        else:
            created = False

            # Source 정보만 갱신한다. 사람이 정한 brand/mapping_* 값은 절대 건드리지 않는다.
            if name:
                brand_source.name = name
            if english_name:
                brand_source.english_name = english_name
            if image_url:
                brand_source.image_url = image_url
            if country_code:
                brand_source.country_code = country_code
            if description:
                brand_source.description = description

            existing_attributes = (
                dict(brand_source.attributes)
                if isinstance(brand_source.attributes, dict)
                else {}
            )
            existing_attributes.update(attributes)
            brand_source.attributes = existing_attributes or None
            brand_source.last_seen_at = now
            brand_source.detected_count = (brand_source.detected_count or 0) + 1

            brand_source.save(
                update_fields=[
                    "name",
                    "english_name",
                    "image_url",
                    "country_code",
                    "description",
                    "attributes",
                    "last_seen_at",
                    "detected_count",
                    "updated_at",
                ]
            )

        return {
            "created": created,
            "brand_source": brand_source,
            "source_brand": {
                "id": source_brand_id,
                "name": name,
                "name_en": english_name,
                "image_url": image_url,
                "country_code": country_code,
            },
        }

    # ============================================================
    # CATEGORY
    # ============================================================

    @transaction.atomic
    def normalize_category(
        self,
        product_data: dict | None,
    ) -> dict:
        """플랫폼 카테고리 원본을 CategorySource로만 정규화한다."""
        extracted = extract_deepest_category(product_data)

        if extracted is None:
            return {
                "created": False,
                "category_source": None,
                "source_category": None,
            }

        source_category_id = extracted["source_category_id"]
        source_category_name = extracted["source_category_name"]
        source_category_path = extracted["source_category_path"]
        normalized_name = extracted["normalized_name"]
        now = timezone.now()

        category_source = CategorySource.objects.filter(
            source=self.source,
            source_category_id=source_category_id,
        ).first()

        if category_source is None:
            category_source = CategorySource.objects.create(
                category=None,
                source=self.source,
                source_category_id=source_category_id,
                source_category_name=source_category_name,
                source_category_path=source_category_path,
                first_seen_at=now,
                last_seen_at=now,
            )
            created = True
        else:
            created = False
            category_source.source_category_name = source_category_name
            category_source.source_category_path = source_category_path
            category_source.last_seen_at = now
            category_source.save(
                update_fields=[
                    "source_category_name",
                    "source_category_path",
                    "last_seen_at",
                    "updated_at",
                ]
            )

        return {
            "created": created,
            "category_source": category_source,
            "source_category": {
                "id": source_category_id,
                "name": source_category_name,
                "path": source_category_path,
                "normalized_name": normalized_name,
            },
        }

    # ============================================================
    # PRODUCT SOURCE
    # ============================================================

    @transaction.atomic
    @transaction.atomic
    def normalize_product_source(
        self,
        parsed: dict,
        *,
        source_brand: BrandSource | None,
        source_category: CategorySource | None,
    ) -> dict:
        """
        플랫폼 상품 원본을 ProductSource로 정규화한다.

        BrandSource / CategorySource는 앞 단계에서 이미 확보해서 전달한다.
        Product 매핑은 수행하지 않는다.
        """
        if not isinstance(parsed, dict):
            raise ValueError("parsed는 dict여야 합니다.")

        product_data = (
            parsed.get("product")
            if isinstance(parsed.get("product"), dict)
            else {}
        )
        ranking_context = (
            parsed.get("ranking_context")
            if isinstance(parsed.get("ranking_context"), dict)
            else {}
        )
        meta = (
            parsed.get("meta")
            if isinstance(parsed.get("meta"), dict)
            else {}
        )

        goods_no = product_data.get("goods_no")
        if goods_no is None:
            raise ValueError("goods_no가 없습니다.")

        source_product_id = str(goods_no)

        raw_source_name = clean_text(
            product_data.get("name")
        )

        source_name_en = clean_text(
            product_data.get("name_en")
        )

        source_tags = (
            product_data.get("tags")
            or []
        )

        if not isinstance(
            source_tags,
            (list, tuple),
        ):
            source_tags = []

        name_result = (
            ProductNamePreprocessor.parse(
                raw_source_name,
                existing_tags=source_tags,
                source_code="MUSINSA",
            )
        )

        source_name = name_result[
            "source_name"
        ]

        genders = product_data.get(
            "genders"
        ) or []

        if isinstance(genders, list):
            gender_scope = ",".join(
                str(x)
                for x in genders
            ) or None
        else:
            gender_scope = clean_text(
                genders
            )

        product_url = (
            ranking_context.get("product_url")
            or meta.get("final_url")
            or meta.get("request_url")
            or (
                "https://www.musinsa.com/products/"
                f"{source_product_id}"
            )
        )

        source_attributes = {
            "season_year": product_data.get(
                "season_year"
            ),
            "season": product_data.get(
                "season"
            ),
            "source_attributes": (
                product_data.get(
                    "source_attributes"
                )
                or {}
            ),
            # 무신사 원래 tags + 상품명에서 추가 추출한 tags
            "tags": name_result["tags"],
            # 원본 상품명 / 분리 근거 추적용
            "source_name_meta": (
                name_result[
                    "source_name_meta"
                ]
            ),
        }

        now = timezone.now()

        product_source, created = (
            ProductSource.objects.get_or_create(
                source=self.source,
                source_product_id=source_product_id,
                defaults={
                    "product": None,
                    "source_brand": source_brand,
                    "source_category": source_category,
                    "source_name": source_name,
                    "source_name_en": source_name_en,
                    "normalized_name": None,
                    "style_no": clean_text(
                        product_data.get(
                            "style_no"
                        )
                    ),
                    "thumbnail_url": (
                        product_data.get(
                            "thumbnail_url"
                        )
                    ),
                    "product_url": product_url,
                    "gender_scope": gender_scope,
                    "attributes": source_attributes,
                    "market_type": (
                        ProductSource
                        .MarketType
                        .RETAIL
                    ),
                    "mapping_status": (
                        ProductSource
                        .MappingStatus
                        .UNMAPPED
                    ),
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "detected_count": 1,
                    "status": (
                        ProductSource
                        .Status
                        .ACTIVE
                    ),
                },
            )
        )

        if not created:
            product_source.source_brand = (
                source_brand
            )
            product_source.source_category = (
                source_category
            )
            product_source.source_name = (
                source_name
            )
            product_source.source_name_en = (
                source_name_en
            )

            # 기존 DB의 normalized_name이 과거 STEP 1 산출물이라면 제거한다.
            # 실제 Product Enrichment가 수행된 흔적(feedit_analysis)이 있을 때만 보존.
            existing_attributes = (
                product_source.attributes
                if isinstance(
                    product_source.attributes,
                    dict,
                )
                else {}
            )

            if not existing_attributes.get(
                "feedit_analysis"
            ):
                product_source.normalized_name = None

            product_source.style_no = clean_text(
                product_data.get("style_no")
            )
            product_source.thumbnail_url = (
                product_data.get(
                    "thumbnail_url"
                )
            )
            product_source.product_url = (
                product_url
            )
            product_source.gender_scope = (
                gender_scope
            )
            # source 영역만 갱신하고, 기존 enrichment JSON은 보존한다.
            current_attributes = (
                dict(product_source.attributes)
                if isinstance(
                    product_source.attributes,
                    dict,
                )
                else {}
            )

            current_attributes.update(
                source_attributes
            )

            product_source.attributes = (
                current_attributes
            )
            product_source.last_seen_at = now
            product_source.detected_count = (
                (product_source.detected_count or 0)
                + 1
            )
            product_source.save()

        return {
            "created": created,
            "product_source": product_source,
        }

    # ============================================================
    # SNAPSHOT
    # ============================================================
    @transaction.atomic
    def normalize_snapshot(
        self,
        parsed: dict,
        *,
        product_source: ProductSource,
        observed_at: datetime | str | None = None,
    ) -> dict[str, Any]:

        if not isinstance(parsed, dict):
            raise ValueError("parsed는 dict여야 합니다.")

        # ============================================================
        # SOURCE DATA
        # ============================================================

        snapshot_data = (
            parsed.get("snapshot")
            if isinstance(
                parsed.get("snapshot"),
                dict,
            )
            else {}
        )

        ranking_context = (
            parsed.get("ranking_context")
            if isinstance(
                parsed.get("ranking_context"),
                dict,
            )
            else {}
        )

        meta = (
            parsed.get("meta")
            if isinstance(
                parsed.get("meta"),
                dict,
            )
            else {}
        )

        # ============================================================
        # OBSERVED AT
        # ============================================================

        observed_at = self._parse_datetime(
            observed_at
            or parsed.get("collected_at")
            or meta.get("collected_at")
            or meta.get("observed_at")
            or ranking_context.get("observed_at")
        )

        # ============================================================
        # RANKING
        # ============================================================

        rank_position = self._first_int(
            ranking_context,
            "rank",
            "rank_position",
            "ranking",
        )

        ranking_scope = (
            clean_text(
                ranking_context.get(
                    "ranking_scope"
                )
            )
            or "CATEGORY"
            if rank_position is not None
            else None
        )

        # ============================================================
        # PRICE
        # ============================================================

        list_price = self._first_decimal(
            snapshot_data,
            "regular_price",
            "list_price",
            "original_price",
            "normal_price",
        )

        sale_price = self._first_decimal(
            snapshot_data,
            "sale_price",
            "discount_price",
            "final_price",
            "price",
        )

        discount_rate = self._first_decimal(
            snapshot_data,
            "discount_rate",
            "discount_percent",
            "discount_percentage",
        )

        # ============================================================
        # REACTION
        # ============================================================

        rating = self._first_decimal(
            snapshot_data,
            "satisfaction_score",
            "review_score",
            "rating",
            "review_rating",
        )

        review_count = self._first_int(
            snapshot_data,
            "review_count",
            "reviews_count",
        )

        like_count = self._first_int(
            snapshot_data,
            "like_count",
            "interest_count",
            "wish_count",
            "favorite_count",
        )

        # ============================================================
        # STOCK
        # ============================================================

        stock_status = self._first_text(
            snapshot_data,
            "availability",
            "stock_status",
            "sellable_status",
            "sales_status",
        )

        # ============================================================
        # PLATFORM METRICS
        # ============================================================

        platform_metrics = {}

        for key in (
            "view_count",
            "sales_count",
            "currency",
            "is_out_of_stock",
        ):
            value = snapshot_data.get(key)

            if value not in (None, ""):
                platform_metrics[key] = value

        # 필요하면 원본 추가 상태도 보존
        for key in (
            "availability",
        ):
            value = snapshot_data.get(key)

            if value not in (None, ""):
                platform_metrics[key] = value

        # ============================================================
        # SAVE
        # ============================================================

        ProductSource.objects.select_for_update().get(pk=product_source.pk)

        defaults = {
            "list_price": list_price,
            "sale_price": sale_price,
            "discount_rate": discount_rate,

            "rank_position": rank_position,
            "ranking_scope": ranking_scope,
            "ranking_context": ranking_context,

            "rating": rating,
            "review_count": review_count,
            "like_count": like_count,
            "view_count": self._first_int(snapshot_data, "view_count"),
            "sales_count": self._first_int(
                snapshot_data,
                "sales_count",
                "purchase_total",
            ),

            "stock_status": stock_status,

            "platform_metrics": platform_metrics,
        }

        latest = (
            ProductSourceSnapshot.objects
            .filter(
                product_source=product_source,
                ranking_scope=ranking_scope,
            )
            .order_by("-observed_at", "-id")
            .first()
        )
        compare_fields = (
            "list_price",
            "sale_price",
            "discount_rate",
            "rank_position",
            "ranking_scope",
            "ranking_context",
            "rating",
            "review_count",
            "like_count",
            "view_count",
            "sales_count",
            "stock_status",
            "platform_metrics",
        )
        unchanged = latest is not None and all(
            _snapshot_business_value(getattr(latest, field))
            == _snapshot_business_value(defaults.get(field))
            for field in compare_fields
        )
        if unchanged:
            snapshot = latest
            created = False
        else:
            snapshot = ProductSourceSnapshot.objects.create(
                product_source=product_source,
                observed_at=observed_at,
                **defaults,
            )
            created = True

        return {
            "created": created,
            "unchanged": not created,
            "snapshot": snapshot,
            "observed_at": observed_at,
        }
    # ============================================================
    # SNAPSHOT HELPERS
    # ============================================================

    @staticmethod   
    def _first_value(data: dict, *keys: str):
        if not isinstance(data, dict):
            return None
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _first_int(cls, data: dict, *keys: str) -> int | None:
        return cls._to_int(cls._first_value(data, *keys))

    @classmethod
    def _first_decimal(cls, data: dict, *keys: str) -> Decimal | None:
        return cls._to_decimal(cls._first_value(data, *keys))

    @classmethod
    def _first_text(cls, data: dict, *keys: str) -> str | None:
        return clean_text(cls._first_value(data, *keys))

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            dt = value
        elif value:
            dt = parse_datetime(str(value))
        else:
            dt = None

        if dt is None:
            return timezone.now()

        if timezone.is_naive(dt):
            dt = timezone.make_aware(
                dt,
                timezone.get_current_timezone(),
            )
        return dt

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(
                str(value)
                .replace(",", "")
                .replace("%", "")
                .strip()
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(
                str(value)
                .replace(",", "")
                .replace("%", "")
                .strip()
            )
        except (InvalidOperation, TypeError, ValueError):
            return None

