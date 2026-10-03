from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import (
    BrandSource,
    CategorySource,
    ProductSource,
    ProductSourceSnapshot,
    RawDocument,
)

from .common import (
    base_cleaning,
    extract_detail_text,
    extract_payload,
    extract_products,
    get_s3_client,
    load_raw_json,
)


KST = ZoneInfo("Asia/Seoul")


# ============================================================
# RESULT
# ============================================================

def _empty_result(
    raw_document_id: int,
) -> dict:

    return {
        "raw_document_id": raw_document_id,

        "products": 0,

        "brand_created": 0,
        "brand_updated": 0,
        "brand_missing": 0,

        "category_created": 0,
        "category_updated": 0,
        "category_missing": 0,

        "product_created": 0,
        "product_updated": 0,

        "snapshot_created": 0,
        "snapshot_unchanged": 0,

        "failed": 0,
        "errors": [],
        "product_source_ids": [],
    }


# ============================================================
# CATEGORY
# ============================================================

def extract_deepest_category(
    product_data: dict,
) -> dict | None:

    category_data = product_data.get(
        "category"
    )

    if not isinstance(
        category_data,
        dict,
    ):
        return None

    categories = []

    for depth in range(1, 5):

        code = base_cleaning(
            category_data.get(
                f"depth{depth}_code"
            )
        )

        name = base_cleaning(
            category_data.get(
                f"depth{depth}_name"
            )
        )

        if not code:
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
        "source_category_id":
            deepest["code"],

        "source_category_name":
            deepest["name"],

        "source_category_path":
            (
                " > ".join(path_parts)
                if path_parts
                else None
            ),

        "depth":
            deepest["depth"],
    }


# ============================================================
# MUSINSA INGESTION
# ============================================================

class MusinsaIngestion:

    SOURCE_CODE = "musinsa"

    def __init__(self):
        self.s3 = get_s3_client()

    # ========================================================
    # PUBLIC
    # ========================================================

    def run(
        self,
        raw_document_id: int,
    ) -> dict:

        raw_document = (
            RawDocument.objects
            .select_related(
                "source",
                "crawl_run",
            )
            .get(
                pk=raw_document_id
            )
        )

        self._validate_raw_document(
            raw_document
        )

        raw_data = load_raw_json(
            raw_document,
            s3_client=self.s3,
        )

        payload = extract_payload(
            raw_data
        )

        products = extract_products(
            payload
        )

        result = _empty_result(
            raw_document.id
        )

        for index, parsed in enumerate(
            products,
            start=1,
        ):

            result["products"] += 1

            try:
                one = self._ingest_product(
                    raw_document=raw_document,
                    parsed=parsed,
                )

                self._merge_result(
                    result,
                    one,
                )

            except Exception as exc:

                result["failed"] += 1

                result["errors"].append(
                    {
                        "product_index":
                            index,

                        "error_type":
                            exc.__class__.__name__,

                        "error_message":
                            str(exc),
                    }
                )

        return result

    # ========================================================
    # ONE PRODUCT
    # ========================================================

    @transaction.atomic
    def _ingest_product(
        self,
        *,
        raw_document: RawDocument,
        parsed: dict,
    ) -> dict:

        product_data = self._dict(
            parsed.get("product")
        )

        brand_data = self._build_brand_data(
            parsed
        )

        observed_at = (
            raw_document.collected_at
            or timezone.now()
        )

        brand_source, brand_created = (
            self._save_brand_source(
                raw_document=raw_document,
                brand_data=brand_data,
                observed_at=observed_at,
            )
        )

        (
            category_source,
            category_created,
        ) = self._save_category_source(
            raw_document=raw_document,
            product_data=product_data,
            observed_at=observed_at,
        )

        (
            product_source,
            product_created,
        ) = self._save_product_source(
            raw_document=raw_document,
            parsed=parsed,
            product_data=product_data,
            brand_source=brand_source,
            category_source=category_source,
            observed_at=observed_at,
        )

        (
            snapshot,
            snapshot_created,
        ) = self._save_snapshot(
            raw_document=raw_document,
            parsed=parsed,
            product_source=product_source,
            observed_at=observed_at,
        )

        return {
            "brand_created":
                int(
                    brand_source is not None
                    and brand_created
                ),

            "brand_updated":
                int(
                    brand_source is not None
                    and not brand_created
                ),

            "brand_missing":
                int(
                    brand_source is None
                ),

            "category_created":
                int(
                    category_source is not None
                    and category_created
                ),

            "category_updated":
                int(
                    category_source is not None
                    and not category_created
                ),

            "category_missing":
                int(
                    category_source is None
                ),

            "product_created":
                int(product_created),

            "product_updated":
                int(not product_created),

            "snapshot_created":
                int(snapshot_created),

            "snapshot_unchanged":
                int(not snapshot_created),

            "product_source_id":
                product_source.id,

            "snapshot_id":
                snapshot.id
                if snapshot
                else None,
        }

    # ========================================================
    # VALIDATION
    # ========================================================

    def _validate_raw_document(
        self,
        raw_document: RawDocument,
    ) -> None:

        source_code = (
            raw_document.source.code
            or ""
        ).strip().lower()

        if source_code != self.SOURCE_CODE:
            raise ValueError(
                "MUSINSA RawDocument가 아닙니다. "
                f"source={source_code}"
            )

    # ========================================================
    # BRAND
    # ========================================================

    @staticmethod
    def _build_brand_data(
        parsed: dict,
    ) -> dict:
        """
        parser 버전에 따라 brand 정보가
        product 안에 들어있는 경우까지 대응한다.
        """

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

        merged = dict(
            brand_data
        )

        if not (
            merged.get("brand_code")
            or merged.get("brand_id")
        ):
            fallback = (
                product_data.get("brand_code")
                or product_data.get("brand_id")
            )

            if fallback:
                merged["brand_code"] = (
                    fallback
                )

        if not (
            merged.get("name_ko")
            or merged.get("brand_name")
            or merged.get("name_en")
        ):
            fallback = (
                product_data.get(
                    "brand_name"
                )
                or product_data.get(
                    "brand_name_ko"
                )
            )

            if fallback:
                merged["brand_name"] = (
                    fallback
                )

        return merged

    def _save_brand_source(
        self,
        *,
        raw_document: RawDocument,
        brand_data: dict,
        observed_at: datetime,
    ) -> tuple[BrandSource | None, bool]:
        """
        MUSINSA 브랜드 정보를 BrandSource에 저장한다.

        원칙
        ----
        1. (source, source_brand_id) 기준으로 기존 BrandSource를 재사용한다.
        2. 없으면 새로 생성한다.
        3. 기존 BrandSource가 있으면 이번 수집에서 얻은 source 정보로 보강한다.
        4. 이번 RAW에 값이 없다고 기존 값을 None으로 덮어쓰지 않는다.
        5. STEP01에서는 FEEDIT 매핑 정보는 절대 수정하지 않는다.

        STEP01에서 수정하지 않는 정보
        -----------------------------
        - brand
        - mapping_status
        - mapping_method
        - mapping_confidence
        - styles

        Returns
        -------
        tuple[BrandSource | None, bool]
            (brand_source, created)
        """

        # ========================================================
        # 1. Source Brand ID
        # ========================================================

        source_brand_id = base_cleaning(
            brand_data.get("brand_code")
            or brand_data.get("brand_id")
        )

        if not source_brand_id:
            return None, False

        # ========================================================
        # 2. 이번 RAW에서 수집된 정보
        # ========================================================

        name = base_cleaning(
            brand_data.get("name_ko")
            or brand_data.get("brand_name")
            or brand_data.get("name_en")
        )

        english_name = base_cleaning(
            brand_data.get("name_en")
        )

        image_url = brand_data.get(
            "logo_url"
        )

        country_code = base_cleaning(
            brand_data.get("nation_code")
        )

        description = base_cleaning(
            brand_data.get("description")
        )

        nation_name = base_cleaning(
            brand_data.get("nation_name")
        )

        since_year = brand_data.get(
            "since_year"
        )

        # ========================================================
        # 3. 플랫폼 고유 추가 정보
        # ========================================================

        incoming_attributes = {}

        if nation_name is not None:
            incoming_attributes["nation_name"] = (
                nation_name
            )

        if since_year is not None:
            incoming_attributes["since_year"] = (
                since_year
            )

        # ========================================================
        # 4. 기존 BrandSource 조회 / 신규 생성
        # ========================================================

        brand_source, created = (
            BrandSource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_brand_id=source_brand_id,
                defaults={
                    "brand": None,
                    "name": name,
                    "english_name": english_name,
                    "image_url": image_url,
                    "country_code": country_code,
                    "description": description,
                    "attributes": (
                        incoming_attributes
                        or None
                    ),
                    "mapping_status": (
                        BrandSource
                        .MappingStatus
                        .UNMAPPED
                    ),
                    "first_seen_at": observed_at,
                    "last_seen_at": observed_at,
                    "detected_count": 1,
                },
            )
        )

        # ========================================================
        # 5. 신규 생성
        # ========================================================

        if created:
            return brand_source, True

        # ========================================================
        # 6. 기존 BrandSource 보강
        # ========================================================
        #
        # 주의:
        #
        # brand
        # mapping_status
        # mapping_method
        # mapping_confidence
        # styles
        #
        # 위 필드는 여기서 절대 건드리지 않는다.
        # ========================================================

        update_fields = []

        # --------------------------------------------------------
        # 이름
        # --------------------------------------------------------

        if (
            name is not None
            and brand_source.name != name
        ):
            brand_source.name = name
            update_fields.append("name")

        # --------------------------------------------------------
        # 영문명
        # --------------------------------------------------------

        if (
            english_name is not None
            and brand_source.english_name
            != english_name
        ):
            brand_source.english_name = (
                english_name
            )
            update_fields.append(
                "english_name"
            )

        # --------------------------------------------------------
        # 이미지
        # --------------------------------------------------------

        if (
            image_url
            and brand_source.image_url
            != image_url
        ):
            brand_source.image_url = (
                image_url
            )
            update_fields.append(
                "image_url"
            )

        # --------------------------------------------------------
        # 국가 코드
        # --------------------------------------------------------

        if (
            country_code is not None
            and brand_source.country_code
            != country_code
        ):
            brand_source.country_code = (
                country_code
            )
            update_fields.append(
                "country_code"
            )

        # --------------------------------------------------------
        # 브랜드 설명
        # --------------------------------------------------------

        if (
            description is not None
            and brand_source.description
            != description
        ):
            brand_source.description = (
                description
            )
            update_fields.append(
                "description"
            )

        # --------------------------------------------------------
        # attributes
        # 기존 값 + 이번에 새로 수집된 값
        # --------------------------------------------------------

        current_attributes = (
            dict(brand_source.attributes)
            if isinstance(
                brand_source.attributes,
                dict,
            )
            else {}
        )

        merged_attributes = {
            **current_attributes,
            **incoming_attributes,
        }

        if (
            merged_attributes
            != current_attributes
        ):
            brand_source.attributes = (
                merged_attributes
                or None
            )
            update_fields.append(
                "attributes"
            )

        # ========================================================
        # 7. 관측 시각
        # ========================================================

        if (
            brand_source.last_seen_at
            != observed_at
        ):
            brand_source.last_seen_at = (
                observed_at
            )
            update_fields.append(
                "last_seen_at"
            )

        # ========================================================
        # 8. 실제 변경된 경우만 UPDATE
        # ========================================================

        if update_fields:
            update_fields.append(
                "updated_at"
            )

            brand_source.save(
                update_fields=update_fields
            )

        return brand_source, False
    # ========================================================
    # CATEGORY
    # ========================================================

    def _save_category_source(
        self,
        *,
        raw_document: RawDocument,
        product_data: dict,
        observed_at: datetime,
    ) -> tuple[
        CategorySource | None,
        bool,
    ]:

        extracted = (
            extract_deepest_category(
                product_data
            )
        )

        if extracted is None:
            return None, False

        source_category_id = (
            extracted[
                "source_category_id"
            ]
        )

        category_source, created = (
            CategorySource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_category_id=(
                    source_category_id
                ),
                defaults={
                    "category": None,

                    "source_category_name":
                        extracted[
                            "source_category_name"
                        ],

                    "source_category_path":
                        extracted[
                            "source_category_path"
                        ],

                    "first_seen_at":
                        observed_at,

                    "last_seen_at":
                        observed_at,
                },
            )
        )

        if created:
            return (
                category_source,
                True,
            )

        # FEEDIT Category 연결은 건드리지 않는다.

        category_source.source_category_name = (
            extracted[
                "source_category_name"
            ]
        )

        category_source.source_category_path = (
            extracted[
                "source_category_path"
            ]
        )

        category_source.last_seen_at = (
            observed_at
        )

        category_source.save(
            update_fields=[
                "source_category_name",
                "source_category_path",
                "last_seen_at",
                "updated_at",
            ]
        )

        return (
            category_source,
            False,
        )

    # ========================================================
    # PRODUCT SOURCE
    # ========================================================

    def _save_product_source(
        self,
        *,
        raw_document: RawDocument,
        parsed: dict,
        product_data: dict,
        brand_source: BrandSource | None,
        category_source: CategorySource | None,
        observed_at: datetime,
    ) -> tuple[
        ProductSource,
        bool,
    ]:

        goods_no = product_data.get(
            "goods_no"
        )

        if goods_no in (
            None,
            "",
        ):
            raise ValueError(
                "MUSINSA goods_no가 없습니다."
            )

        source_product_id = str(
            goods_no
        )

        ranking_context = self._dict(
            parsed.get(
                "ranking_context"
            )
        )

        meta = self._dict(
            parsed.get("meta")
        )

        options_data = self._dict(
            parsed.get("options")
        )

        source_name = base_cleaning(
            product_data.get("name")
        )

        source_name_en = base_cleaning(
            product_data.get("name_en")
        )

        source_tags = self._list(
            product_data.get("tags")
        )

        source_attributes = (
            product_data.get(
                "source_attributes"
            )
        )
        detail_text = extract_detail_text(
            product_data.get(
                "detail_content"
            )
        )

        if not isinstance(
            source_attributes,
            dict,
        ):
            source_attributes = {}

        attributes = {
            "attributes":
                source_attributes,

            "tags":
                source_tags,

            "options":
                self._extract_options(
                    options_data
                ),
        }

        if detail_text:
            attributes[
                "detail_text"
            ] = detail_text
            
        product_url = (
            ranking_context.get(
                "product_url"
            )
            or meta.get(
                "final_url"
            )
            or meta.get(
                "request_url"
            )
            or (
                "https://www.musinsa.com/products/"
                f"{source_product_id}"
            )
        )

        genders = [
            str(value)
            for value in self._list(
                product_data.get(
                    "genders"
                )
            )
            if value not in (
                None,
                "",
            )
        ]

        gender_scope = (
            ",".join(genders)
            if genders
            else None
        )

        defaults = {
            "product": None,

            "source_brand":
                brand_source,

            "source_category":
                category_source,

            "style_no":
                base_cleaning(
                    product_data.get(
                        "style_no"
                    )
                ),

            "source_name":
                source_name,

            "source_name_en":
                source_name_en,

            # STEP02 책임
            "normalized_name":
                None,

            "thumbnail_url":
                product_data.get(
                    "thumbnail_url"
                ),

            "product_url":
                product_url,

            "gender_scope":
                gender_scope,

            "source_genders":
                genders,

            "season_year":
                self._to_int(
                    product_data.get(
                        "season_year"
                    )
                ),

            "season":
                base_cleaning(
                    product_data.get(
                        "season"
                    )
                ),

            "sell_start_at":
                self._parse_optional_datetime(
                    product_data.get(
                        "sell_start_date"
                    )
                ),

            "sell_end_at":
                self._parse_optional_datetime(
                    product_data.get(
                        "sell_end_date"
                    )
                ),

            "attributes":
                attributes,

            "first_seen_at":
                observed_at,

            "last_seen_at":
                observed_at,

            "detected_count":
                    1,
        }

        product_source, created = (
            ProductSource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_product_id=(
                    source_product_id
                ),
                defaults=defaults,
            )
        )

        if created:
            return (
                product_source,
                True,
            )

        # 과거 RAW를 재처리하더라도 최신 ProductSource 상태를
        # 오래된 값으로 되돌리지 않는다.
        current_last_seen = product_source.last_seen_at

        if (
            current_last_seen is not None
            and observed_at <= current_last_seen
        ):
            # 더 오래된 RAW라면 최초 관측 시각만 보정할 수 있다.
            if (
                product_source.first_seen_at is None
                or observed_at < product_source.first_seen_at
            ):
                product_source.first_seen_at = observed_at
                product_source.save(
                    update_fields=[
                        "first_seen_at",
                        "updated_at",
                    ]
                )

            return product_source, False

        product_source.source_brand = brand_source
        product_source.source_category = category_source
        product_source.style_no = defaults["style_no"]
        product_source.source_name = defaults["source_name"]
        product_source.source_name_en = defaults["source_name_en"]
        product_source.thumbnail_url = defaults["thumbnail_url"]
        product_source.product_url = defaults["product_url"]
        product_source.gender_scope = defaults["gender_scope"]
        product_source.source_genders = defaults["source_genders"]
        product_source.season_year = defaults["season_year"]
        product_source.season = defaults["season"]
        product_source.sell_start_at = defaults["sell_start_at"]
        product_source.sell_end_at = defaults["sell_end_at"]

        # 이번 최신 RAW에서 수집한 source 정보가 현재 상태다.
        product_source.attributes = defaults["attributes"]
        product_source.last_seen_at = observed_at

        product_source.save(
            update_fields=[
                "source_brand",
                "source_category",
                "style_no",
                "source_name",
                "source_name_en",
                "thumbnail_url",
                "product_url",
                "gender_scope",
                "source_genders",
                "season_year",
                "season",
                "sell_start_at",
                "sell_end_at",
                "attributes",
                "last_seen_at",
                "updated_at",
            ]
        )

        return product_source, False

    # ========================================================
    # SNAPSHOT
    # ========================================================
    def _save_snapshot(
        self,
        *,
        raw_document: RawDocument,
        parsed: dict,
        product_source: ProductSource,
        observed_at: datetime,
    ) -> tuple[
        ProductSourceSnapshot,
        bool,
    ]:
        """
        MUSINSA 일별 상품 Snapshot을 저장한다.

        기준
        ----
        1. snapshot_date는 KST 기준 수집 날짜다.
        2. 동일 product_source + snapshot_date + ranking_scope는 1행만 유지한다.
        3. 같은 키가 여러 번 수집되면 가장 최신 observed_at 값으로 갱신한다.
        4. 과거 RAW를 재처리해도 더 최신 Snapshot을 덮어쓰지 않는다.
        """

        snapshot_data = self._dict(
            parsed.get("snapshot")
        )

        raw_ranking_context = self._dict(
            parsed.get("ranking_context")
        )

        rank_position = self._first_int(
            raw_ranking_context,
            "rank",
            "rank_position",
            "ranking",
        )

        ranking_category_code = base_cleaning(
            raw_ranking_context.get(
                "ranking_category_code"
            )
        )

        ranking_gender = base_cleaning(
            raw_ranking_context.get(
                "ranking_gender"
            )
        )

        ranking_age_band = base_cleaning(
            raw_ranking_context.get(
                "ranking_age_band"
            )
        )

        ranking_period = base_cleaning(
            raw_ranking_context.get(
                "ranking_period"
            )
        )

        scope_parts = [
            ranking_category_code,
            ranking_gender,
            ranking_age_band,
            ranking_period,
        ]

        if (
            rank_position is not None
            and any(scope_parts)
        ):
            ranking_scope = ":".join(
                value
                for value in scope_parts
                if value
            )
        else:
            # PRODUCT 상세 수집도 일별 1행으로 관리한다.
            ranking_scope = "MUSINSA:DETAIL"

        if rank_position is not None:
            ranking_context = {
                "category_code": ranking_category_code,
                "gender": ranking_gender,
                "age_band": ranking_age_band,
                "period": ranking_period,
            }
            ranking_context = {
                key: value
                for key, value in ranking_context.items()
                if value is not None
            }
        else:
            ranking_context = {}

        values = {
            "list_price": self._first_decimal(
                snapshot_data,
                "regular_price",
                "list_price",
                "original_price",
                "normal_price",
            ),
            "sale_price": self._first_decimal(
                snapshot_data,
                "sale_price",
                "discount_price",
                "final_price",
                "price",
            ),
            "discount_rate": self._first_decimal(
                snapshot_data,
                "discount_rate",
                "discount_percent",
                "discount_percentage",
            ),
            "rank_position": rank_position,
            "ranking_scope": ranking_scope,
            "ranking_context": ranking_context,
            "rating": self._first_decimal(
                snapshot_data,
                "satisfaction_score",
                "review_score",
                "rating",
            ),
            "review_count": self._first_int(
                snapshot_data,
                "review_count",
                "reviews_count",
            ),
            "like_count": self._first_int(
                snapshot_data,
                "like_count",
                "interest_count",
                "wish_count",
            ),
            "view_count": self._first_int(
                snapshot_data,
                "view_count",
            ),
            "sales_count": self._first_int(
                snapshot_data,
                "sales_count",
                "purchase_total",
            ),
            "stock_status": self._first_text(
                snapshot_data,
                "availability",
                "stock_status",
                "sellable_status",
            ),
            "platform_metrics": self._build_platform_metrics(
                snapshot_data
            ),
        }

        snapshot_date = observed_at.astimezone(
            KST
        ).date()

        lookup = {
            "product_source": product_source,
            "snapshot_date": snapshot_date,
            "ranking_scope": ranking_scope,
        }

        snapshot = (
            ProductSourceSnapshot.objects
            .select_for_update()
            .filter(**lookup)
            .first()
        )

        if snapshot is None:
            snapshot = ProductSourceSnapshot.objects.create(
                **lookup,
                observed_at=observed_at,
                **{
                    key: value
                    for key, value in values.items()
                    if key != "ranking_scope"
                },
            )
            return snapshot, True

        # 같은 날짜/scope에 이미 더 최신 관측이 있으면 그대로 둔다.
        if snapshot.observed_at >= observed_at:
            return snapshot, False

        for key, value in values.items():
            if key == "ranking_scope":
                continue
            setattr(snapshot, key, value)

        snapshot.observed_at = observed_at
        snapshot.save(
            update_fields=[
                "observed_at",
                "list_price",
                "sale_price",
                "discount_rate",
                "rank_position",
                "ranking_context",
                "rating",
                "review_count",
                "like_count",
                "view_count",
                "sales_count",
                "stock_status",
                "platform_metrics",
            ]
        )

        return snapshot, False

    # ========================================================
    # OPTIONS
    # ========================================================

    @staticmethod
    def _extract_options(
        options_data: dict,
    ) -> dict:

        basic = options_data.get(
            "basic"
        )

        if not isinstance(
            basic,
            list,
        ):
            return {}

        result = {}

        for option in basic:

            if not isinstance(
                option,
                dict,
            ):
                continue

            option_name = base_cleaning(
                option.get("name")
            )

            if not option_name:
                continue

            raw_values = (
                option.get(
                    "optionValues"
                )
            )

            if not isinstance(
                raw_values,
                list,
            ):
                continue

            values = []

            for item in raw_values:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                if (
                    item.get(
                        "isDeleted"
                    )
                    is True
                ):
                    continue

                value = base_cleaning(
                    item.get("name")
                )

                if (
                    value
                    and value
                    not in values
                ):
                    values.append(
                        value
                    )

            if values:
                result[
                    option_name
                ] = values

        return result

    # ========================================================
    # SNAPSHOT HELPERS
    # ========================================================
    @staticmethod
    def _build_platform_metrics(
        snapshot_data: dict,
    ) -> dict:

        metrics = {}

        for key in (
            "currency",
            "availability",
            "is_out_of_stock",
        ):
            value = snapshot_data.get(
                key
            )

            if value not in (
                None,
                "",
            ):
                metrics[key] = value

        return metrics

    # ========================================================
    # COMMON HELPERS
    # ========================================================

    @staticmethod
    def _dict(
        value: Any,
    ) -> dict:

        if isinstance(
            value,
            dict,
        ):
            return value

        return {}

    @staticmethod
    def _list(
        value: Any,
    ) -> list:

        if isinstance(
            value,
            list,
        ):
            return value

        return []

    @staticmethod
    def _first_value(
        data: dict,
        *keys: str,
    ):

        if not isinstance(
            data,
            dict,
        ):
            return None

        for key in keys:

            value = data.get(
                key
            )

            if value not in (
                None,
                "",
            ):
                return value

        return None

    @classmethod
    def _first_int(
        cls,
        data: dict,
        *keys: str,
    ) -> int | None:

        return cls._to_int(
            cls._first_value(
                data,
                *keys,
            )
        )

    @classmethod
    def _first_decimal(
        cls,
        data: dict,
        *keys: str,
    ) -> Decimal | None:

        return cls._to_decimal(
            cls._first_value(
                data,
                *keys,
            )
        )

    @classmethod
    def _first_text(
        cls,
        data: dict,
        *keys: str,
    ) -> str | None:

        return base_cleaning(
            cls._first_value(
                data,
                *keys,
            )
        )

    @staticmethod
    def _to_int(
        value: Any,
    ) -> int | None:

        if value in (
            None,
            "",
        ):
            return None

        try:
            return int(
                float(
                    str(value)
                    .replace(",", "")
                    .strip()
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_decimal(
        value: Any,
    ) -> Decimal | None:

        if value in (
            None,
            "",
        ):
            return None

        try:
            return Decimal(
                str(value)
                .replace(",", "")
                .replace("%", "")
                .strip()
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _parse_optional_datetime(
        value: Any,
    ) -> datetime | None:

        if value in (
            None,
            "",
        ):
            return None

        if isinstance(
            value,
            datetime,
        ):
            parsed = value

        else:
            parsed = parse_datetime(
                str(value)
            )

        if parsed is None:
            return None

        if timezone.is_naive(
            parsed
        ):
            parsed = timezone.make_aware(
                parsed,
                timezone.get_current_timezone(),
            )

        return parsed

    @staticmethod
    def _merge_result(
        result: dict,
        one: dict,
    ) -> None:

        count_keys = (
            "brand_created",
            "brand_updated",
            "brand_missing",
            "category_created",
            "category_updated",
            "category_missing",
            "product_created",
            "product_updated",
            "snapshot_created",
            "snapshot_unchanged",
        )

        for key in count_keys:
            result[key] += (
                one.get(
                    key,
                    0,
                )
                or 0
            )
        product_source_id = one.get(
        "product_source_id"
        )

        if product_source_id not in (
            None,
            "",
        ):
            product_source_id = int(
                product_source_id
            )

            if (
                product_source_id
                not in result[
                    "product_source_ids"
                ]
            ):
                result[
                    "product_source_ids"
                ].append(
                    product_source_id
                )


# ============================================================
# CONVENIENCE
# ============================================================

def ingest_musinsa_raw_document(
    raw_document_id: int,
) -> dict:

    return MusinsaIngestion().run(
        raw_document_id
    )