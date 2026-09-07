from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    Brand,
    BrandSource,
    Category,
    CategorySource,
    ProductSource,
)

from analysis.normalization.common import (
    clean_text,
    extract_deepest_category,
    normalize_brand_name,
    normalize_category_name,
    normalize_product_name,
)


class MusinsaNormalizer:
    """
    MUSINSA parsed data -> FEEDIT source/master mapping.

    핵심 원칙:
    1. 플랫폼에서 관측한 BrandSource / CategorySource는
       FEEDIT 표준 매핑 성공 여부와 상관없이 보존한다.
    2. UNMAPPED는 정상 상태다.
    3. ProductSource는 반드시 먼저 확보한
       BrandSource / CategorySource를 FK로 연결한다.
    """

    def __init__(self, *, source):
        self.source = source

    # ============================================================
    # BRAND
    # ============================================================

    @transaction.atomic
    def normalize_brand(
        self,
        brand_data: dict | None,
    ) -> dict:

        if not isinstance(brand_data, dict):
            brand_data = {}

        source_brand_id = clean_text(
            brand_data.get("brand_code")
            or brand_data.get("brand_id")
        )

        source_brand_name = clean_text(
            brand_data.get("name_ko")
            or brand_data.get("brand_name")
            or brand_data.get("name_en")
        )

        source_brand_name_en = clean_text(
            brand_data.get("name_en")
        )

        if (
            source_brand_id is None
            and source_brand_name is None
        ):
            return {
                "matched": False,
                "matched_by": "NO_BRAND",
                "brand": None,
                "brand_source": None,
                "source_brand": None,
            }

        # 브랜드 코드가 없는 예외 케이스에서는
        # 정규화 이름을 source id fallback으로 사용.
        if source_brand_id is None:
            source_brand_id = normalize_brand_name(
                source_brand_name
            )

        normalized_name = normalize_brand_name(
            source_brand_name
        )

        normalized_name_en = normalize_brand_name(
            source_brand_name_en
        )

        now = timezone.now()

        brand_source = (
            BrandSource.objects
            .select_related("brand")
            .filter(
                source=self.source,
                source_brand_id=source_brand_id,
            )
            .first()
        )

        if brand_source is not None:
            brand_source.source_brand_name = (
                source_brand_name
            )
            brand_source.normalized_name = (
                normalized_name
            )
            brand_source.source_brand_name_en = (
                source_brand_name_en
            )
            brand_source.normalized_name_en = (
                normalized_name_en
            )
            brand_source.last_seen_at = now
            brand_source.detected_count = (
                (brand_source.detected_count or 0)
                + 1
            )

            # 이미 FEEDIT Brand에 매핑된 source면
            # 기존 연결을 우선 보존한다.
            if brand_source.brand_id is not None:
                if (
                    brand_source.mapping_status
                    == BrandSource.MappingStatus.UNMAPPED
                ):
                    brand_source.mapping_status = (
                        BrandSource.MappingStatus.AUTO_MAPPED
                    )

                if not brand_source.mapping_method:
                    brand_source.mapping_method = (
                        BrandSource.MappingMethod.SOURCE_ID
                    )

                brand_source.save()

                return {
                    "matched": True,
                    "matched_by": "SOURCE_ID",
                    "brand": brand_source.brand,
                    "brand_source": brand_source,
                    "source_brand": {
                        "id": source_brand_id,
                        "name": source_brand_name,
                        "name_en": source_brand_name_en,
                        "normalized_name": normalized_name,
                    },
                }

        brand = self._find_brand(
            normalized_name=normalized_name,
            normalized_name_en=normalized_name_en,
        )

        if brand_source is not None:
            if brand is not None:
                brand_source.brand = brand
                brand_source.mapping_status = (
                    BrandSource.MappingStatus.AUTO_MAPPED
                )
                brand_source.mapping_method = (
                    BrandSource.MappingMethod.NORMALIZED_NAME
                )
                brand_source.mapping_confidence = 1
            else:
                brand_source.brand = None
                brand_source.mapping_status = (
                    BrandSource.MappingStatus.UNMAPPED
                )
                brand_source.mapping_method = None
                brand_source.mapping_confidence = None

            brand_source.save()

        else:
            brand_source = BrandSource.objects.create(
                brand=brand,
                source=self.source,
                source_brand_id=source_brand_id,
                source_brand_name=source_brand_name,
                normalized_name=normalized_name,
                source_brand_name_en=source_brand_name_en,
                normalized_name_en=normalized_name_en,
                mapping_status=(
                    BrandSource.MappingStatus.AUTO_MAPPED
                    if brand is not None
                    else BrandSource.MappingStatus.UNMAPPED
                ),
                mapping_method=(
                    BrandSource.MappingMethod.NORMALIZED_NAME
                    if brand is not None
                    else None
                ),
                mapping_confidence=(
                    1 if brand is not None else None
                ),
                detected_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )

        return {
            "matched": brand is not None,
            "matched_by": (
                "NORMALIZED_NAME"
                if brand is not None
                else "UNMAPPED"
            ),
            "brand": brand,
            "brand_source": brand_source,
            "source_brand": {
                "id": source_brand_id,
                "name": source_brand_name,
                "name_en": source_brand_name_en,
                "normalized_name": normalized_name,
            },
        }

    @staticmethod
    def _find_brand(
        *,
        normalized_name: str | None,
        normalized_name_en: str | None,
    ) -> Brand | None:

        brands = (
            Brand.objects
            .filter(
                status=Brand.Status.ACTIVE,
            )
            .only(
                "id",
                "brand_code",
                "name",
                "english_name",
            )
        )

        matches = []

        for brand in brands:
            brand_name = normalize_brand_name(
                brand.name
            )
            brand_name_en = normalize_brand_name(
                brand.english_name
            )

            matched = False

            if (
                normalized_name
                and brand_name == normalized_name
            ):
                matched = True

            if (
                normalized_name_en
                and brand_name_en == normalized_name_en
            ):
                matched = True

            if (
                normalized_name
                and brand_name_en == normalized_name
            ):
                matched = True

            if matched:
                matches.append(brand)

        if len(matches) != 1:
            return None

        return matches[0]

    # ============================================================
    # CATEGORY
    # ============================================================

    @transaction.atomic
    def normalize_category(
        self,
        product_data: dict | None,
    ) -> dict:

        extracted = extract_deepest_category(
            product_data
        )

        if extracted is None:
            return {
                "matched": False,
                "matched_by": "NO_CATEGORY",
                "category": None,
                "category_source": None,
                "source_category": None,
            }

        source_category_id = extracted[
            "source_category_id"
        ]
        source_category_name = extracted[
            "source_category_name"
        ]
        source_category_path = extracted[
            "source_category_path"
        ]
        normalized_name = extracted[
            "normalized_name"
        ]

        now = timezone.now()

        category_source = (
            CategorySource.objects
            .select_related("category")
            .filter(
                source=self.source,
                source_category_id=source_category_id,
            )
            .first()
        )

        if category_source is not None:
            category_source.source_category_name = (
                source_category_name
            )
            category_source.source_category_path = (
                source_category_path
            )
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
                "matched": (
                    category_source.category_id
                    is not None
                ),
                "matched_by": (
                    "SOURCE_ID"
                    if category_source.category_id
                    else "SOURCE_ID_UNMAPPED"
                ),
                "category": category_source.category,
                "category_source": category_source,
                "source_category": {
                    "id": source_category_id,
                    "name": source_category_name,
                    "path": source_category_path,
                    "normalized_name": normalized_name,
                },
            }

        category = self._find_category(
            normalized_name
        )

        # 중요:
        # FEEDIT Category 매핑 실패여도
        # CategorySource 자체는 반드시 저장한다.
        category_source = CategorySource.objects.create(
            category=category,
            source=self.source,
            source_category_id=source_category_id,
            source_category_name=source_category_name,
            source_category_path=source_category_path,            first_seen_at=now,
            last_seen_at=now,
        )

        return {
            "matched": category is not None,
            "matched_by": (
                "NORMALIZED_NAME"
                if category is not None
                else "UNMAPPED"
            ),
            "category": category,
            "category_source": category_source,
            "source_category": {
                "id": source_category_id,
                "name": source_category_name,
                "path": source_category_path,
                "normalized_name": normalized_name,
            },
        }

    @staticmethod
    def _find_category(
        normalized_name: str | None,
    ) -> Category | None:

        if normalized_name is None:
            return None

        categories = (
            Category.objects
            .filter(
                category_type=(
                    Category.CategoryType.PRODUCT
                ),
                status=Category.Status.ACTIVE,
            )
            .only(
                "id",
                "code",
                "name",
            )
        )

        matches = []

        for category in categories:
            category_name = normalize_category_name(
                category.name
            )

            if category_name == normalized_name:
                matches.append(category)

        if len(matches) != 1:
            return None

        return matches[0]

    # ============================================================
    # PRODUCT SOURCE
    # ============================================================

    @transaction.atomic
    def normalize_product_source(
        self,
        parsed: dict,
    ) -> dict:
        """
        한 상품의 source 레이어를 한 번에 완성한다.

        순서:
        1. BrandSource 확보
        2. CategorySource 확보
        3. ProductSource 생성/갱신

        따라서 ProductSource만 먼저 저장되어
        source_brand/source_category가 NULL이 되는 문제를 막는다.
        """

        if not isinstance(parsed, dict):
            raise ValueError(
                "parsed는 dict여야 합니다."
            )

        product_data = (
            parsed.get("product")
            if isinstance(
                parsed.get("product"),
                dict,
            )
            else {}
        )

        brand_data = (
            parsed.get("brand")
            if isinstance(
                parsed.get("brand"),
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

        goods_no = product_data.get("goods_no")

        if goods_no is None:
            raise ValueError(
                "goods_no가 없습니다."
            )

        # --------------------------------------------------------
        # brand payload 보강
        # --------------------------------------------------------
        # parser에 따라 product에만 brand_code가 있는 케이스 대응
        merged_brand_data = dict(brand_data)

        if not (
            merged_brand_data.get("brand_code")
            or merged_brand_data.get("brand_id")
        ):
            fallback_brand_code = (
                product_data.get("brand_code")
                or product_data.get("brand_id")
            )

            if fallback_brand_code:
                merged_brand_data[
                    "brand_code"
                ] = fallback_brand_code

        if not (
            merged_brand_data.get("name_ko")
            or merged_brand_data.get("brand_name")
            or merged_brand_data.get("name_en")
        ):
            fallback_brand_name = (
                product_data.get("brand_name")
                or product_data.get(
                    "brand_name_ko"
                )
            )

            if fallback_brand_name:
                merged_brand_data[
                    "brand_name"
                ] = fallback_brand_name

        # --------------------------------------------------------
        # 반드시 먼저 source master 확보
        # --------------------------------------------------------
        brand_result = self.normalize_brand(
            merged_brand_data
        )

        category_result = self.normalize_category(
            product_data
        )

        source_brand = brand_result.get(
            "brand_source"
        )

        source_category = category_result.get(
            "category_source"
        )

        # --------------------------------------------------------
        # ProductSource
        # --------------------------------------------------------
        source_product_id = str(goods_no)

        source_name = clean_text(
            product_data.get("name")
        )

        source_name_en = clean_text(
            product_data.get("name_en")
        )

        normalized_name = normalize_product_name(
            source_name
        )

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

        attributes = {
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
            "tags": (
                product_data.get("tags")
                or []
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
                    "normalized_name": normalized_name,
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
                    "attributes": attributes,
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
            product_source.normalized_name = (
                normalized_name
            )
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
            product_source.attributes = (
                attributes
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
            "brand_result": brand_result,
            "category_result": category_result,
            "source_brand": source_brand,
            "source_category": source_category,
        }
