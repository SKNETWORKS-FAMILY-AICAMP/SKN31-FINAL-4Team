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

from analysis.source_ingestion.common import (
    clean_text,
    normalize_brand_name,
    normalize_category_name,
)

from analysis.source_ingestion.product_name_preprocessor import (
    ProductNamePreprocessor,
)


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

        name = clean_text(
            brand_data.get("name_ko")
            or brand_data.get("brand_name")
            or brand_data.get("name_en")
        )

        english_name = clean_text(
            brand_data.get("name_en")
        )

        image_url = clean_text(
            brand_data.get("logo_url")
        )

        country_code = clean_text(
            brand_data.get("nation_code")
        )

        description = clean_text(
            brand_data.get("description")
        )

        if (
            source_brand_id is None
            and name is None
        ):
            return {
                "matched": False,
                "matched_by": "NO_BRAND",
                "brand": None,
                "brand_source": None,
                "source_brand": None,
            }

        # 무신사는 보통 brand_code가 존재한다.
        # 예외적으로 없으면 이름을 source 식별자로 사용한다.
        if source_brand_id is None:
            source_brand_id = f"NAME:{name}"

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

        brand = self._find_brand(
            name=name,
            english_name=english_name,
        )

        attributes = {}

        nation_name = brand_data.get(
            "nation_name"
        )
        since_year = brand_data.get(
            "since_year"
        )

        if nation_name is not None:
            attributes["nation_name"] = nation_name

        if since_year is not None:
            attributes["since_year"] = since_year

        if brand_source is None:
            brand_source = BrandSource.objects.create(
                brand=brand,
                source=self.source,
                source_brand_id=source_brand_id,
                name=(
                    name
                    or source_brand_id
                ),
                english_name=english_name,
                image_url=image_url,
                country_code=country_code,
                description=description,
                target_gender=None,
                target_age=None,
                website_url=None,
                source_profile_url=None,
                attributes=attributes or None,
                mapping_status=(
                    BrandSource.MappingStatus.AUTO_MAPPED
                    if brand is not None
                    else BrandSource.MappingStatus.UNMAPPED
                ),
                mapping_method=(
                    BrandSource.MappingMethod.EXACT_NAME
                    if brand is not None
                    else None
                ),
                mapping_confidence=(
                    1
                    if brand is not None
                    else None
                ),
                detected_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )

            created = True

        else:
            created = False

            # 새 수집값이 NULL이면 기존 프로필을 지우지 않는다.
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
                brand_source.attributes
                if isinstance(brand_source.attributes, dict)
                else {}
            )
            existing_attributes.update(attributes)
            brand_source.attributes = (
                existing_attributes
                or None
            )

            brand_source.last_seen_at = now
            brand_source.detected_count = (
                (brand_source.detected_count or 0)
                + 1
            )

            # 이미 연결된 FEEDIT Brand는 보존한다.
            # 미매핑 상태일 때만 exact-name 자동 매핑을 시도한다.
            if brand_source.brand_id is None:
                if brand is not None:
                    brand_source.brand = brand
                    brand_source.mapping_status = (
                        BrandSource.MappingStatus.AUTO_MAPPED
                    )
                    brand_source.mapping_method = (
                        BrandSource.MappingMethod.EXACT_NAME
                    )
                    brand_source.mapping_confidence = 1
                else:
                    brand_source.mapping_status = (
                        BrandSource.MappingStatus.UNMAPPED
                    )
                    brand_source.mapping_method = None
                    brand_source.mapping_confidence = None

            brand_source.save()

        return {
            "created": created,
            "matched": (
                brand_source.brand_id
                is not None
            ),
            "matched_by": (
                brand_source.mapping_method
                or "UNMAPPED"
            ),
            "brand": brand_source.brand,
            "brand_source": brand_source,
            "source_brand": {
                "id": source_brand_id,
                "name": name,
                "name_en": english_name,
                "image_url": image_url,
                "country_code": country_code,
            },
        }

    @staticmethod
    def _find_brand(
        *,
        name: str | None,
        english_name: str | None,
    ) -> Brand | None:

        name_key = normalize_brand_name(
            name
        )
        english_key = normalize_brand_name(
            english_name
        )

        if (
            not name_key
            and not english_key
        ):
            return None

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
            brand_name_key = normalize_brand_name(
                brand.name
            )
            brand_english_key = normalize_brand_name(
                brand.english_name
            )

            keys = {
                value
                for value in (
                    brand_name_key,
                    brand_english_key,
                )
                if value
            }

            if (
                name_key in keys
                or english_key in keys
            ):
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
                    "normalized_name": None,
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
            "brand_result": brand_result,
            "category_result": category_result,
            "source_brand": source_brand,
            "source_category": source_category,
        }
