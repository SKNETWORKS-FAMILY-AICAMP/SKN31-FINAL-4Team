from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    BrandSource,
    CategorySource,
    ProductSource,
)

from analysis.normalization.common import (
    build_brand_source_payload,
    clean_list,
    clean_text,
    find_brand_exact,
    find_styles,
    normalize_product_name,
)


class ZigzagNormalizer:

    def __init__(
        self,
        *,
        source,
    ):
        self.source = source

    # ============================================================
    # BRAND / STORE PAYLOAD
    # ============================================================

    @staticmethod
    def extract_brand_payload(
        shop_data: dict | None,
    ) -> dict:

        if not isinstance(
            shop_data,
            dict,
        ):
            shop_data = {}

        shop_info = (
            shop_data.get(
                "shop_information"
            )
            if isinstance(
                shop_data.get(
                    "shop_information"
                ),
                dict,
            )
            else {}
        )

        # 경우에 따라 shop_data 자체가
        # shop_information일 수도 있음
        if not shop_info:
            shop_info = shop_data

        # --------------------------------------------------------
        # ID / NAME
        # --------------------------------------------------------

        shop_id = (
            shop_info.get("id")
            or shop_info.get(
                "shop_id"
            )
            or shop_data.get(
                "shop_id"
            )
            or shop_data.get(
                "store_id"
            )
        )

        shop_name = (
            shop_info.get("name")
            or shop_info.get(
                "shop_name"
            )
            or shop_data.get(
                "shop_name"
            )
            or shop_data.get(
                "store_name"
            )
        )

        # --------------------------------------------------------
        # LOGO
        # --------------------------------------------------------

        logo_data = (
            shop_info.get(
                "logo_image"
            )
        )

        logo_url = None

        if isinstance(
            logo_data,
            dict,
        ):

            url_data = (
                logo_data.get("url")
            )

            if isinstance(
                url_data,
                dict,
            ):

                logo_url = (
                    url_data.get(
                        "normal"
                    )
                    or url_data.get(
                        "dark"
                    )
                )

            elif isinstance(
                url_data,
                str,
            ):
                logo_url = url_data

            if not logo_url:

                logo_url = (
                    logo_data.get(
                        "normal"
                    )
                    or logo_data.get(
                        "image_url"
                    )
                )

        elif isinstance(
            logo_data,
            str,
        ):
            logo_url = logo_data

        # 대표 이미지가 있으면 대표이미지 우선,
        # 없으면 로고
        image_url = (
            shop_info.get(
                "typical_image_url"
            )
            or logo_url
        )

        # --------------------------------------------------------
        # STYLE
        # --------------------------------------------------------

        styles = clean_list(
            shop_info.get(
                "style_list"
            )
        )

        # --------------------------------------------------------
        # AGE
        # --------------------------------------------------------

        ages = clean_list(
            shop_info.get(
                "age_list"
            )
        )

        # --------------------------------------------------------
        # GENDER
        # --------------------------------------------------------

        genders = clean_list(
            shop_info.get(
                "gender_list"
            )
            or shop_info.get(
                "target_gender"
            )
        )

        # --------------------------------------------------------
        # DOMAIN
        # --------------------------------------------------------

        domain = clean_text(
            shop_info.get(
                "main_domain"
            )
            or shop_data.get(
                "main_domain"
            )
        )

        profile_url = None

        if domain:

            profile_url = (
                f"https://zigzag.kr/{domain}"
            )

        # --------------------------------------------------------
        # ATTRIBUTES
        # --------------------------------------------------------

        attributes = {

            "main_domain": domain,

            "is_brand": (
                shop_data.get(
                    "is_brand"
                )
                if "is_brand"
                in shop_data
                else shop_info.get(
                    "is_brand"
                )
            ),

            "logo_image": (
                shop_info.get(
                    "logo_image"
                )
            ),

            "typical_image_url": (
                shop_info.get(
                    "typical_image_url"
                )
            ),

            "representative_info": (
                shop_info.get(
                    "representative_info"
                )
            ),

            "representative_coupon_v2": (
                shop_info.get(
                    "representative_coupon_v2"
                )
            ),
        }

        return build_brand_source_payload(

            source_brand_id=(
                shop_id
            ),

            name=(
                shop_name
            ),

            english_name=(
                shop_info.get(
                    "english_name"
                )
            ),

            image_url=(
                image_url
            ),

            country_code=(
                shop_info.get(
                    "country_code"
                )
            ),

            description=(
                shop_info.get(
                    "comment"
                )
                or shop_info.get(
                    "description"
                )
            ),

            target_gender=(
                genders
            ),

            target_age=(
                ages
            ),

            style_values=(
                styles
            ),

            website_url=(
                shop_info.get(
                    "website_url"
                )
            ),

            source_profile_url=(
                profile_url
            ),

            attributes=(
                attributes
            ),
        )

    # ============================================================
    # BRAND
    # ============================================================

    @transaction.atomic
    def normalize_brand(
        self,
        shop_data: dict | None,
    ) -> dict:

        payload = (
            self.extract_brand_payload(
                shop_data
            )
        )

        source_brand_id = (
            payload[
                "source_brand_id"
            ]
        )

        name = payload["name"]

        if (
            source_brand_id is None
            and name is None
        ):
            return {
                "matched": False,
                "matched_by": (
                    "NO_BRAND"
                ),
                "brand": None,
                "brand_source": None,
            }

        # 지그재그 ranking 중 일부는
        # shop_id 없이 shop_name만 들어오는 경우 대응
        if source_brand_id is None:

            source_brand_id = (
                f"NAME:{name}"
            )

        brand = find_brand_exact(
            name=name,
            english_name=(
                payload[
                    "english_name"
                ]
            ),
        )

        now = timezone.now()

        brand_source = (
            BrandSource.objects
            .select_related(
                "brand"
            )
            .filter(
                source=self.source,
                source_brand_id=(
                    source_brand_id
                ),
            )
            .first()
        )

        created = False

        if brand_source is None:

            brand_source = (
                BrandSource.objects.create(

                    brand=brand,

                    source=self.source,

                    source_brand_id=(
                        source_brand_id
                    ),

                    name=(
                        name
                        or source_brand_id
                    ),

                    english_name=(
                        payload[
                            "english_name"
                        ]
                    ),

                    source_brand_name_en=(
                        payload[
                            "english_name"
                        ]
                    ),

                    image_url=(
                        payload[
                            "image_url"
                        ]
                    ),

                    country_code=(
                        payload[
                            "country_code"
                        ]
                    ),

                    description=(
                        payload[
                            "description"
                        ]
                    ),

                    target_gender=(
                        payload[
                            "target_gender"
                        ]
                    ),

                    target_age=(
                        payload[
                            "target_age"
                        ]
                    ),

                    website_url=(
                        payload[
                            "website_url"
                        ]
                    ),

                    source_profile_url=(
                        payload[
                            "source_profile_url"
                        ]
                    ),

                    attributes=(
                        payload[
                            "attributes"
                        ]
                    ),

                    mapping_status=(
                        BrandSource
                        .MappingStatus
                        .AUTO_MAPPED

                        if brand

                        else BrandSource
                        .MappingStatus
                        .UNMAPPED
                    ),

                    mapping_method=(
                        BrandSource
                        .MappingMethod
                        .EXACT_NAME

                        if brand

                        else None
                    ),

                    mapping_confidence=(
                        1
                        if brand
                        else None
                    ),

                    detected_count=1,

                    first_seen_at=now,

                    last_seen_at=now,
                )
            )

            created = True

        else:

            # 이미 관리자가 매핑한 Brand는
            # 새 자동매칭으로 덮어쓰지 않음
            existing_brand = (
                brand_source.brand
            )

            brand_source.name = (
                name
                or brand_source.name
            )

            brand_source.english_name = (
                payload[
                    "english_name"
                ]
            )

            brand_source.source_brand_name_en = (
                payload[
                    "english_name"
                ]
            )

            # 값 있을 때만 기존 상세값 보존/갱신
            if payload["image_url"]:
                brand_source.image_url = (
                    payload[
                        "image_url"
                    ]
                )

            if payload[
                "country_code"
            ]:
                brand_source.country_code = (
                    payload[
                        "country_code"
                    ]
                )

            if payload[
                "description"
            ]:
                brand_source.description = (
                    payload[
                        "description"
                    ]
                )

            if payload[
                "target_gender"
            ]:
                brand_source.target_gender = (
                    payload[
                        "target_gender"
                    ]
                )

            if payload[
                "target_age"
            ]:
                brand_source.target_age = (
                    payload[
                        "target_age"
                    ]
                )

            if payload[
                "website_url"
            ]:
                brand_source.website_url = (
                    payload[
                        "website_url"
                    ]
                )

            if payload[
                "source_profile_url"
            ]:
                brand_source.source_profile_url = (
                    payload[
                        "source_profile_url"
                    ]
                )

            # attributes merge
            attrs = (
                brand_source.attributes
                if isinstance(
                    brand_source.attributes,
                    dict,
                )
                else {}
            )

            attrs.update(
                payload["attributes"]
            )

            brand_source.attributes = (
                attrs
            )

            brand_source.last_seen_at = (
                now
            )

            brand_source.detected_count = (
                (
                    brand_source
                    .detected_count
                )
                or 0
            ) + 1

            if existing_brand is None:

                brand_source.brand = (
                    brand
                )

                if brand:

                    brand_source.mapping_status = (
                        BrandSource
                        .MappingStatus
                        .AUTO_MAPPED
                    )

                    brand_source.mapping_method = (
                        BrandSource
                        .MappingMethod
                        .EXACT_NAME
                    )

                    brand_source.mapping_confidence = 1

                else:

                    brand_source.mapping_status = (
                        BrandSource
                        .MappingStatus
                        .UNMAPPED
                    )

                    brand_source.mapping_method = None

                    brand_source.mapping_confidence = None

            brand_source.save()

        # --------------------------------------------------------
        # STYLE MAPPING
        # --------------------------------------------------------

        style_values = (
            payload[
                "style_values"
            ]
        )

        if style_values:

            styles = find_styles(
                style_values
            )

            # source에서 명시적으로 style_list가
            # 관측된 경우에는 그 결과로 맞춘다.
            brand_source.styles.set(
                styles
            )

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

            "brand": (
                brand_source.brand
            ),

            "brand_source": (
                brand_source
            ),
        }

    # ============================================================
    # CATEGORY SOURCE
    # ============================================================

    def get_category_source(
        self,
        category_id,
    ):

        category_id = clean_text(
            category_id
        )

        if not category_id:
            return None

        return (
            CategorySource.objects
            .select_related(
                "category"
            )
            .filter(
                source=self.source,
                source_category_id=(
                    category_id
                ),
            )
            .first()
        )

    # ============================================================
    # PRODUCT
    # ============================================================

    @transaction.atomic
    def normalize_product_source(
        self,
        product_data: dict,
        *,
        inherited_category_id=None,
    ) -> dict:

        if not isinstance(
            product_data,
            dict,
        ):
            raise ValueError(
                "product_data는 dict여야 합니다."
            )

        # --------------------------------------------------------
        # PRODUCT ID
        # --------------------------------------------------------

        source_product_id = clean_text(
            product_data.get(
                "product_id"
            )
            or product_data.get(
                "productId"
            )
            or product_data.get(
                "item_id"
            )
            or product_data.get(
                "itemId"
            )
            or product_data.get(
                "goods_id"
            )
            or product_data.get(
                "goodsId"
            )
            or product_data.get(
                "id"
            )
        )

        if not source_product_id:
            raise ValueError(
                "지그재그 product id가 없습니다."
            )

        # --------------------------------------------------------
        # PRODUCT NAME
        # --------------------------------------------------------

        source_name = clean_text(
            product_data.get(
                "product_name"
            )
            or product_data.get(
                "productName"
            )
            or product_data.get(
                "name"
            )
            or product_data.get(
                "title"
            )
        )

        # --------------------------------------------------------
        # SHOP
        # --------------------------------------------------------

        shop_data = {}

        nested_shop = (
            product_data.get("shop")
            or product_data.get("store")
            or product_data.get("seller")
        )

        if isinstance(
            nested_shop,
            dict,
        ):
            shop_data.update(
                nested_shop
            )

        # flat 값도 합침
        for key in [
            "shop_id",
            "shop_name",
            "store_id",
            "store_name",
            "is_brand",
            "main_domain",
            "shop_information",
        ]:

            if (
                key in product_data
                and key not in shop_data
            ):
                shop_data[key] = (
                    product_data[key]
                )

        brand_result = (
            self.normalize_brand(
                shop_data
            )
        )

        source_brand = (
            brand_result.get(
                "brand_source"
            )
        )

        # --------------------------------------------------------
        # CATEGORY
        # --------------------------------------------------------

        category_id = clean_text(
            product_data.get(
                "sub_category_id"
            )
            or product_data.get(
                "leaf_category_id"
            )
            or product_data.get(
                "category_id"
            )
            or inherited_category_id
        )

        source_category = (
            self.get_category_source(
                category_id
            )
        )

        # --------------------------------------------------------
        # IMAGE / URL
        # --------------------------------------------------------

        thumbnail_url = clean_text(
            product_data.get(
                "thumbnail_url"
            )
            or product_data.get(
                "thumbnail"
            )
            or product_data.get(
                "image_url"
            )
            or product_data.get(
                "imageUrl"
            )
        )

        product_url = clean_text(
            product_data.get(
                "product_url"
            )
            or product_data.get(
                "productUrl"
            )
            or product_data.get(
                "url"
            )
        )

        # --------------------------------------------------------
        # ATTRIBUTES
        # --------------------------------------------------------

        attributes = {

            "shop_id": (
                shop_data.get(
                    "shop_id"
                )
                or shop_data.get(
                    "id"
                )
            ),

            "shop_name": (
                shop_data.get(
                    "shop_name"
                )
                or shop_data.get(
                    "name"
                )
            ),

            "category_id": (
                category_id
            ),

            "regular_price": (
                product_data.get(
                    "regular_price"
                )
                or product_data.get(
                    "original_price"
                )
            ),

            "sale_price": (
                product_data.get(
                    "sale_price"
                )
                or product_data.get(
                    "price"
                )
            ),

            "discount_rate": (
                product_data.get(
                    "discount_rate"
                )
            ),

            "review_count": (
                product_data.get(
                    "review_count"
                )
            ),

            "rating": (
                product_data.get(
                    "rating"
                )
            ),
        }

        now = timezone.now()

        product_source, created = (
            ProductSource.objects
            .get_or_create(

                source=self.source,

                source_product_id=(
                    source_product_id
                ),

                defaults={

                    "product": None,

                    "source_brand": (
                        source_brand
                    ),

                    "source_category": (
                        source_category
                    ),

                    "source_name": (
                        source_name
                    ),

                    "normalized_name": (
                        normalize_product_name(
                            source_name
                        )
                    ),

                    "thumbnail_url": (
                        thumbnail_url
                    ),

                    "product_url": (
                        product_url
                    ),

                    "attributes": (
                        attributes
                    ),

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

                    "first_seen_at": (
                        now
                    ),

                    "last_seen_at": (
                        now
                    ),

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

            product_source.normalized_name = (
                normalize_product_name(
                    source_name
                )
            )

            product_source.thumbnail_url = (
                thumbnail_url
            )

            product_source.product_url = (
                product_url
            )

            product_source.attributes = (
                attributes
            )

            product_source.last_seen_at = (
                now
            )

            product_source.detected_count = (
                (
                    product_source
                    .detected_count
                )
                or 0
            ) + 1

            product_source.save()

        return {

            "created": created,

            "product_source": (
                product_source
            ),

            "brand_result": (
                brand_result
            ),

            "source_category": (
                source_category
            ),
        }