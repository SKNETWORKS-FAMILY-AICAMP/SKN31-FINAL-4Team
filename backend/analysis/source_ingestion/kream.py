from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import (
    Brand,
    BrandSource,
    Category,
    CategorySource,
    ProductSource,
    ProductSourceSnapshot,
    ResaleSnapshot,
)

from analysis.source_ingestion.common import (
    clean_text,
    find_brand_exact,
    normalize_category_name,
)

from analysis.source_ingestion.product_name_preprocessor import (
    ProductNamePreprocessor,
)


class KreamNormalizer:
    """
    KREAM raw payload -> FEEDIT source layer.

    흐름
    ------------------------------------------------------------
    KREAM RAW
        -> BrandSource
        -> CategorySource
        -> ProductSource (RESALE)
        -> ProductSourceSnapshot
        -> ResaleSnapshot

    원칙
    ------------------------------------------------------------
    - canonical Product는 여기서 생성하지 않는다.
    - ProductSource.product는 초기 NULL.
    - KREAM 상품은 market_type=RESALE.
    - 상품 반응/랭킹은 ProductSourceSnapshot.
    - 거래/호가 데이터는 ResaleSnapshot.
    - 이미 수동/기존 매핑된 BrandSource 연결은 보존한다.
    """

    def __init__(
        self,
        *,
        source,
    ):
        self.source = source

    # ============================================================
    # PUBLIC ENTRY
    # ============================================================

    @transaction.atomic
    def normalize_payload(
        self,
        raw: dict[str, Any],
        *,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:

        if not isinstance(raw, dict):
            raise ValueError(
                "KREAM raw payload는 dict여야 합니다."
            )

        # ============================================================
        # S3 wrapper 해제
        #
        # BasePlatformPipeline 저장 결과:
        # {
        #     ...,
        #     "payload": {
        #         "entity_type": "...",
        #         ...
        #     }
        # }
        # ============================================================

        payload = raw.get("payload")

        if isinstance(payload, dict):
            data = payload
        else:
            data = raw

        entity_type = str(
            data.get("entity_type")
            or raw.get("entity_type")
            or ""
        ).upper()

        # ============================================================
        # DISCOVERY / 여러 상품
        # ============================================================

        if isinstance(
            data.get("details"),
            list,
        ):
            return self.normalize_discovery_payload(
                data,
                create_snapshot=create_snapshot,
            )

        # ============================================================
        # PRODUCT / 단일 상품
        # ============================================================

        if (
            entity_type == "PRODUCT"
            or isinstance(
                data.get("product"),
                dict,
            )
        ):
            try:
                result = self.normalize_detail_item(
                    {
                        "feed": {},
                        "detail": data,
                    },
                    create_snapshot=create_snapshot,
                )

                return {
                    "processed": 1,
                    "success": 1,
                    "failed": 0,
                    "results": [
                        result
                    ],
                    "errors": [],
                }

            except Exception as exc:
                return {
                    "processed": 1,
                    "success": 0,
                    "failed": 1,
                    "results": [],
                    "errors": [
                        {
                            "source_product_id": (
                                data.get(
                                    "source_product_id"
                                )
                            ),
                            "error_type": (
                                type(exc).__name__
                            ),
                            "error_message": (
                                str(exc)
                            ),
                        }
                    ],
                }

        raise ValueError(
            "지원하지 않는 KREAM payload 구조입니다. "
            f"entity_type={entity_type}, "
            f"keys={list(data.keys())}"
        )

    # ============================================================
    # DISCOVERY
    # ============================================================

    @transaction.atomic
    def normalize_discovery_payload(
        self,
        raw: dict[str, Any],
        *,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:

        if not isinstance(raw, dict):
            raise ValueError(
                "KREAM raw payload는 dict여야 합니다."
            )

        payload = (
            raw.get("payload")
            if isinstance(
                raw.get("payload"),
                dict,
            )
            else raw
        )

        details = (
            payload.get("details")
            or []
        )

        if not isinstance(
            details,
            list,
        ):
            details = []

        results = []
        errors = []

        for index, row in enumerate(
            details,
            start=1,
        ):
            try:
                result = (
                    self.normalize_detail_item(
                        row,
                        create_snapshot=(
                            create_snapshot
                        ),
                    )
                )

                results.append(
                    result
                )

            except Exception as exc:

                feed_rank = None

                if isinstance(
                    row,
                    dict,
                ):
                    feed_rank = (
                        row.get("feed_rank")
                    )

                    if feed_rank is None:
                        feed = (
                            row.get("feed")
                            if isinstance(
                                row.get("feed"),
                                dict,
                            )
                            else {}
                        )

                        feed_rank = (
                            feed.get(
                                "feed_rank"
                            )
                        )

                errors.append(
                    {
                        "index": index,
                        "feed_rank": feed_rank,
                        "error_type": (
                            type(exc).__name__
                        ),
                        "error_message": (
                            str(exc)
                        ),
                    }
                )

        return {
            "processed": len(details),
            "success": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        }

    # ============================================================
    # ONE DETAIL
    # ============================================================

    @transaction.atomic
    def normalize_detail_item(
        self,
        row: dict[str, Any],
        *,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:

        if not isinstance(
            row,
            dict,
        ):
            raise ValueError(
                "KREAM detail row는 dict여야 합니다."
            )

        # --------------------------------------------------------
        # FEED
        # --------------------------------------------------------
        feed = (
            dict(row.get("feed"))
            if isinstance(
                row.get("feed"),
                dict,
            )
            else {}
        )

        # discovery 버전에 따라 feed_rank가
        # row 최상위에 존재할 수 있음.
        if (
            feed.get("feed_rank")
            is None
            and row.get("feed_rank")
            is not None
        ):
            feed["feed_rank"] = (
                row.get("feed_rank")
            )

        # --------------------------------------------------------
        # DETAIL
        # --------------------------------------------------------
        detail = (
            row.get("detail")
            if isinstance(
                row.get("detail"),
                dict,
            )
            else {}
        )

        # 단일 PRODUCT raw 자체가 row로 넘어온 경우
        if (
            not detail
            and isinstance(
                row.get("product"),
                dict,
            )
        ):
            detail = row

        product_data = (
            detail.get("product")
            if isinstance(
                detail.get("product"),
                dict,
            )
            else {}
        )

        snapshot_data = (
            detail.get("snapshot")
            if isinstance(
                detail.get("snapshot"),
                dict,
            )
            else {}
        )

        ranking_signals = (
            detail.get(
                "ranking_signals"
            )
            if isinstance(
                detail.get(
                    "ranking_signals"
                ),
                list,
            )
            else []
        )

        options = (
            detail.get("options")
            if isinstance(
                detail.get("options"),
                list,
            )
            else []
        )

        market = (
            detail.get("market")
            if isinstance(
                detail.get("market"),
                dict,
            )
            else {}
        )

        # --------------------------------------------------------
        # PRODUCT SOURCE
        # --------------------------------------------------------
        product_result = (
            self.normalize_product_source(
                product_data=product_data,
                feed=feed,
                detail=detail,
            )
        )

        snapshot_result = None
        resale_result = None

        # --------------------------------------------------------
        # SNAPSHOTS
        # --------------------------------------------------------
        if create_snapshot:

            snapshot_result = (
                self.normalize_snapshot(
                    product_source=(
                        product_result[
                            "product_source"
                        ]
                    ),
                    feed=feed,
                    detail=detail,
                    snapshot_data=(
                        snapshot_data
                    ),
                    ranking_signals=(
                        ranking_signals
                    ),
                    options=options,
                )
            )

            resale_result = (
                self.normalize_resale_snapshot(
                    product_source=(
                        product_result[
                            "product_source"
                        ]
                    ),
                    detail=detail,
                    snapshot_data=(
                        snapshot_data
                    ),
                    market=market,
                    options=options,
                )
            )

        return {
            "product_source_id": (
                product_result[
                    "product_source"
                ].id
            ),
            "source_product_id": (
                product_result[
                    "product_source"
                ].source_product_id
            ),
            "product_source_created": (
                product_result[
                    "created"
                ]
            ),
            "snapshot_id": (
                snapshot_result[
                    "snapshot"
                ].id
                if snapshot_result
                else None
            ),
            "snapshot_created": (
                snapshot_result[
                    "created"
                ]
                if snapshot_result
                else None
            ),
            "resale_snapshot_id": (
                resale_result[
                    "snapshot"
                ].id
                if resale_result
                else None
            ),
            "resale_snapshot_created": (
                resale_result[
                    "created"
                ]
                if resale_result
                else None
            ),
        }

    # ============================================================
    # BRAND
    # ============================================================

    @transaction.atomic
    def normalize_brand(
        self,
        brand_data: dict | None,
    ) -> dict:

        if not isinstance(
            brand_data,
            dict,
        ):
            brand_data = {}

        source_brand_id = clean_text(
            brand_data.get(
                "brand_id"
            )
        )

        name = clean_text(
            brand_data.get(
                "name"
            )
        )

        if (
            source_brand_id is None
            and name is None
        ):
            return {
                "created": False,
                "matched": False,
                "matched_by": (
                    "NO_BRAND"
                ),
                "brand": None,
                "brand_source": None,
            }

        if source_brand_id is None:
            source_brand_id = (
                f"NAME:{name}"
            )

        now = timezone.now()

        brand_source = (
            BrandSource.objects
            .select_related("brand")
            .filter(
                source=self.source,
                source_brand_id=(
                    source_brand_id
                ),
            )
            .first()
        )

        # --------------------------------------------------------
        # EXISTING
        # --------------------------------------------------------
        if brand_source is not None:

            if name:
                brand_source.name = (
                    name
                )

                if not (
                    brand_source
                    .english_name
                ):
                    brand_source.english_name = (
                        name
                    )

            attributes = (
                dict(
                    brand_source.attributes
                )
                if isinstance(
                    brand_source.attributes,
                    dict,
                )
                else {}
            )

            attributes[
                "kream_brand_id"
            ] = source_brand_id

            brand_source.attributes = (
                attributes
            )

            if (
                brand_source.first_seen_at
                is None
            ):
                brand_source.first_seen_at = (
                    now
                )

            brand_source.last_seen_at = (
                now
            )

            brand_source.detected_count = (
                (
                    brand_source
                    .detected_count
                    or 0
                )
                + 1
            )

            brand_source.save()

            return {
                "created": False,
                "matched": (
                    brand_source.brand_id
                    is not None
                ),
                "matched_by": (
                    brand_source.mapping_method
                    if brand_source.brand_id
                    else None
                ),
                "brand": (
                    brand_source.brand
                ),
                "brand_source": (
                    brand_source
                ),
            }

        # --------------------------------------------------------
        # NEW
        # --------------------------------------------------------

        brand = find_brand_exact(
            name=name,
            english_name=name,
        )

        mapping_status = (
            BrandSource
            .MappingStatus
            .AUTO_MAPPED
            if brand is not None
            else BrandSource
            .MappingStatus
            .UNMAPPED
        )

        mapping_method = (
            BrandSource
            .MappingMethod
            .EXACT_NAME
            if brand is not None
            else None
        )

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
                english_name=name,
                image_url=None,
                country_code=None,
                description=None,
                target_gender=None,
                target_age=None,
                website_url=None,
                source_profile_url=None,
                attributes={
                    "kream_brand_id": (
                        source_brand_id
                    ),
                },
                mapping_status=(
                    mapping_status
                ),
                mapping_method=(
                    mapping_method
                ),
                mapping_confidence=(
                    Decimal("1.0000")
                    if brand is not None
                    else None
                ),
                detected_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
        )

        return {
            "created": True,
            "matched": (
                brand is not None
            ),
            "matched_by": (
                "EXACT_NAME"
                if brand is not None
                else "UNMAPPED"
            ),
            "brand": brand,
            "brand_source": (
                brand_source
            ),
        }

    # ============================================================
    # CATEGORY
    # ============================================================

    @transaction.atomic
    def normalize_category(
        self,
        category_data: dict | None,
    ) -> dict:

        if not isinstance(
            category_data,
            dict,
        ):
            category_data = {}

        source_category_id = (
            clean_text(
                category_data.get(
                    "source_category_id"
                )
            )
        )

        depth1 = clean_text(
            category_data.get(
                "depth1_name"
            )
        )

        depth2 = clean_text(
            category_data.get(
                "depth2_name"
            )
        )

        source_category_name = (
            depth2
            or depth1
        )

        if (
            source_category_id is None
            and source_category_name is None
        ):
            return {
                "created": False,
                "matched": False,
                "matched_by": (
                    "NO_CATEGORY"
                ),
                "category": None,
                "category_source": None,
            }

        # KREAM 일부 category는 ID 없이 이름만 내려올 수 있음.
        if source_category_id is None:
            source_category_id = (
                f"NAME:"
                f"{depth1 or ''}:"
                f"{depth2 or ''}"
            )

        source_category_path = (
            " > ".join(
                value
                for value in (
                    depth1,
                    depth2,
                )
                if value
            )
            or None
        )

        normalized_name = (
            normalize_category_name(
                source_category_name
            )
        )

        now = timezone.now()

        category_source = (
            CategorySource.objects
            .select_related(
                "category"
            )
            .filter(
                source=self.source,
                source_category_id=(
                    source_category_id
                ),
            )
            .first()
        )

        # --------------------------------------------------------
        # EXISTING
        # --------------------------------------------------------
        if category_source is not None:

            category_source.source_category_name = (
                source_category_name
            )

            category_source.source_category_path = (
                source_category_path
            )

            if (
                category_source
                .first_seen_at
                is None
            ):
                category_source.first_seen_at = (
                    now
                )

            category_source.last_seen_at = (
                now
            )

            category_source.save()

            return {
                "created": False,
                "matched": (
                    category_source.category_id
                    is not None
                ),
                "matched_by": (
                    "SOURCE_ID"
                    if category_source.category_id
                    else (
                        "SOURCE_ID_UNMAPPED"
                    )
                ),
                "category": (
                    category_source.category
                ),
                "category_source": (
                    category_source
                ),
            }

        # --------------------------------------------------------
        # NEW
        # --------------------------------------------------------

        category = self._find_category(
            normalized_name
        )

        category_source = (
            CategorySource.objects.create(
                category=category,
                source=self.source,
                source_category_id=(
                    source_category_id
                ),
                source_category_name=(
                    source_category_name
                ),
                source_category_path=(
                    source_category_path
                ),
                first_seen_at=now,
                last_seen_at=now,
            )
        )

        return {
            "created": True,
            "matched": (
                category is not None
            ),
            "matched_by": (
                "NORMALIZED_NAME"
                if category is not None
                else "UNMAPPED"
            ),
            "category": category,
            "category_source": (
                category_source
            ),
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
                    Category
                    .CategoryType
                    .PRODUCT
                ),
                status=(
                    Category
                    .Status
                    .ACTIVE
                ),
            )
            .only(
                "id",
                "code",
                "name",
            )
        )

        matches = []

        for category in categories:

            category_name = (
                normalize_category_name(
                    category.name
                )
            )

            if (
                category_name
                == normalized_name
            ):
                matches.append(
                    category
                )

        if len(matches) != 1:
            return None

        return matches[0]

    # ============================================================
    # PRODUCT SOURCE
    # ============================================================

    @transaction.atomic
    def normalize_product_source(
        self,
        *,
        product_data: dict,
        feed: dict,
        detail: dict,
    ) -> dict:

        product_id = (
            product_data.get(
                "product_id"
            )
            or feed.get(
                "product_id"
            )
            or detail.get(
                "source_product_id"
            )
        )

        if product_id is None:
            raise ValueError(
                "KREAM product_id가 없습니다."
            )

        source_product_id = str(
            product_id
        )

        # --------------------------------------------------------
        # SOURCE BRAND / CATEGORY
        # --------------------------------------------------------
        brand_result = (
            self.normalize_brand(
                product_data.get(
                    "brand"
                )
            )
        )

        category_result = (
            self.normalize_category(
                product_data.get(
                    "category"
                )
            )
        )

        source_brand = (
            brand_result.get(
                "brand_source"
            )
        )

        source_category = (
            category_result.get(
                "category_source"
            )
        )

        # --------------------------------------------------------
        # NAME
        # --------------------------------------------------------
        raw_source_name = (
            clean_text(
                product_data.get(
                    "name_ko"
                )
            )
            or clean_text(
                product_data.get(
                    "name_en"
                )
            )
            or clean_text(
                feed.get(
                    "name_ko"
                )
            )
            or clean_text(
                feed.get(
                    "name_en"
                )
            )
        )

        source_name_en = (
            clean_text(
                product_data.get(
                    "name_en"
                )
            )
            or clean_text(
                feed.get(
                    "name_en"
                )
            )
        )

        name_result = (
            ProductNamePreprocessor.parse(
                raw_source_name,
                existing_tags=[],
                source_code="KREAM",
            )
        )

        source_name = (
            name_result[
                "source_name"
            ]
        )

        # --------------------------------------------------------
        # IMAGE
        # --------------------------------------------------------
        image_urls = (
            product_data.get(
                "image_urls"
            )
            if isinstance(
                product_data.get(
                    "image_urls"
                ),
                list,
            )
            else []
        )

        thumbnail_url = (
            image_urls[0]
            if image_urls
            else None
        )

        # --------------------------------------------------------
        # FIXED ATTRIBUTES
        # --------------------------------------------------------
        style_no = clean_text(
            product_data.get(
                "style_code"
            )
            or feed.get(
                "style_code"
            )
        )

        product_gender = (
            product_data.get(
                "product_gender"
            )
        )

        gender_scope = (
            clean_text(
                product_gender
            )
            if product_gender
            not in (
                None,
                "",
            )
            else None
        )

        product_url = (
            clean_text(
                detail.get(
                    "source_url"
                )
            )
            or clean_text(
                feed.get(
                    "product_url"
                )
            )
            or (
                "https://kream.co.kr/"
                f"products/"
                f"{source_product_id}"
            )
        )

        category_data = (
            product_data.get(
                "category"
            )
            if isinstance(
                product_data.get(
                    "category"
                ),
                dict,
            )
            else {}
        )

        source_attributes = {
            "source_type": (
                category_data.get(
                    "source_type"
                )
            ),
            "color": (
                product_data.get(
                    "color"
                )
            ),
            "currency": (
                product_data.get(
                    "currency"
                )
            ),
            "product_type": (
                product_data.get(
                    "product_type"
                )
            ),
            "product_gender": (
                product_gender
            ),
            "image_urls": (
                image_urls
            ),
            "tags": (
                name_result.get(
                    "tags"
                )
                or []
            ),
            "source_name_meta": (
                name_result.get(
                    "source_name_meta"
                )
                or {}
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
                    "source_name_en": (
                        source_name_en
                    ),
                    "normalized_name": (
                        None
                    ),
                    "style_no": (
                        style_no
                    ),
                    "thumbnail_url": (
                        thumbnail_url
                    ),
                    "product_url": (
                        product_url
                    ),
                    "gender_scope": (
                        gender_scope
                    ),
                    "attributes": (
                        source_attributes
                    ),
                    "market_type": (
                        ProductSource
                        .MarketType
                        .RESALE
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

        # --------------------------------------------------------
        # UPDATE
        # --------------------------------------------------------
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

            product_source.style_no = (
                style_no
            )

            product_source.thumbnail_url = (
                thumbnail_url
            )

            product_source.product_url = (
                product_url
            )

            product_source.gender_scope = (
                gender_scope
            )

            product_source.market_type = (
                ProductSource
                .MarketType
                .RESALE
            )

            # enrichment 결과가 있다면 보존하고
            # source 영역만 merge.
            current_attributes = (
                dict(
                    product_source.attributes
                )
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

            if (
                product_source.first_seen_at
                is None
            ):
                product_source.first_seen_at = (
                    now
                )

            product_source.last_seen_at = (
                now
            )

            product_source.detected_count = (
                (
                    product_source
                    .detected_count
                    or 0
                )
                + 1
            )

            product_source.status = (
                ProductSource
                .Status
                .ACTIVE
            )

            product_source.save()

        return {
            "created": created,
            "product_source": (
                product_source
            ),
            "brand_result": (
                brand_result
            ),
            "category_result": (
                category_result
            ),
            "source_brand": (
                source_brand
            ),
            "source_category": (
                source_category
            ),
        }

    # ============================================================
    # PRODUCT SOURCE SNAPSHOT
    # ============================================================

    @transaction.atomic
    def normalize_snapshot(
        self,
        *,
        product_source: ProductSource,
        feed: dict,
        detail: dict,
        snapshot_data: dict,
        ranking_signals: list,
        options: list,
    ) -> dict:

        observed_at = (
            self._parse_datetime(
                detail.get(
                    "collected_at"
                )
            )
        )

        # --------------------------------------------------------
        # RANK
        # --------------------------------------------------------
        feed_rank = self._to_int(
            feed.get(
                "feed_rank"
            )
            or feed.get(
                "rank"
            )
        )

        # --------------------------------------------------------
        # PRICE
        # --------------------------------------------------------
        list_price = (
            self._to_decimal(
                feed.get(
                    "original_price"
                )
                or snapshot_data.get(
                    "original_price"
                )
            )
        )

        sale_price = (
            self._to_decimal(
                snapshot_data.get(
                    "current_price"
                )
                or feed.get(
                    "price"
                )
            )
        )

        discount_rate = (
            self._to_decimal(
                feed.get(
                    "discount_rate"
                )
            )
        )

        # --------------------------------------------------------
        # ENGAGEMENT
        # --------------------------------------------------------
        rating = (
            self._to_decimal(
                snapshot_data.get(
                    "review_rating"
                )
            )
        )

        review_count = (
            self._to_int(
                snapshot_data.get(
                    "total_review_count"
                )
                or snapshot_data.get(
                    "review_count"
                )
            )
        )

        wish_count = (
            self._to_int(
                snapshot_data.get(
                    "wish_count"
                )
            )
        )

        viewer_count = (
            self._to_int(
                snapshot_data.get(
                    "viewer_count"
                )
            )
        )

        # --------------------------------------------------------
        # RANKING CONTEXT
        # --------------------------------------------------------
        ranking_context = {
            "feed_rank": (
                feed_rank
            ),
            "tab_id": (
                feed.get(
                    "tab_id"
                )
            ),
            "sort": (
                feed.get(
                    "sort"
                )
            ),
            "sort_type": (
                feed.get(
                    "sort_type"
                )
            ),
            "ranking_signals": (
                ranking_signals
            ),
        }

        ranking_context = {
            key: value
            for key, value
            in ranking_context.items()
            if value not in (
                None,
                "",
                [],
            )
        }

        # --------------------------------------------------------
        # PLATFORM METRICS
        #
        # 시장/거래 데이터는 ResaleSnapshot으로 분리.
        # --------------------------------------------------------
        platform_metrics = {
            "viewer_count": (
                viewer_count
            ),
            "wish_count": (
                wish_count
            ),
            "total_review_count": (
                snapshot_data.get(
                    "total_review_count"
                )
            ),
            "max_benefit_price": (
                snapshot_data.get(
                    "max_benefit_price"
                )
            ),
            "availability": (
                snapshot_data.get(
                    "availability"
                )
            ),
            "is_active": (
                snapshot_data.get(
                    "is_active"
                )
            ),
            "has_immediate_delivery_item": (
                snapshot_data.get(
                    "has_immediate_delivery_item"
                )
            ),
            "options": (
                options
            ),
        }

        platform_metrics = {
            key: value
            for key, value
            in platform_metrics.items()
            if value is not None
        }

        stock_status = clean_text(
            snapshot_data.get(
                "status"
            )
        )

        defaults = {
            "list_price": (
                list_price
            ),
            "sale_price": (
                sale_price
            ),
            "discount_rate": (
                discount_rate
            ),
            "rank_position": (
                feed_rank
            ),
            "ranking_scope": (
                "FEED"
                if feed_rank is not None
                else None
            ),
            "ranking_context": (
                ranking_context
            ),
            "rating": (
                rating
            ),
            "review_count": (
                review_count
            ),
            "like_count": (
                wish_count
            ),
            "stock_status": (
                stock_status
            ),
            "platform_metrics": (
                platform_metrics
            ),
        }

        snapshot, created = (
            ProductSourceSnapshot.objects
            .update_or_create(
                product_source=(
                    product_source
                ),
                observed_at=(
                    observed_at
                ),
                defaults=(
                    defaults
                ),
            )
        )

        return {
            "created": created,
            "snapshot": snapshot,
            "observed_at": (
                observed_at
            ),
        }

    # ============================================================
    # RESALE SNAPSHOT
    # ============================================================

    @transaction.atomic
    def normalize_resale_snapshot(
        self,
        *,
        product_source: ProductSource,
        detail: dict,
        snapshot_data: dict,
        market: dict,
        options: list,
    ) -> dict:

        observed_at = (
            self._parse_datetime(
                detail.get(
                    "collected_at"
                )
            )
        )

        sales = (
            market.get("sales")
            if isinstance(
                market.get("sales"),
                list,
            )
            else []
        )

        asks = (
            market.get("asks")
            if isinstance(
                market.get("asks"),
                list,
            )
            else []
        )

        bids = (
            market.get("bids")
            if isinstance(
                market.get("bids"),
                list,
            )
            else []
        )

        listings = (
            market.get("listings")
            if isinstance(
                market.get("listings"),
                list,
            )
            else []
        )

        # --------------------------------------------------------
        # LOWEST ASK
        # --------------------------------------------------------
        ask_prices = [
            self._to_decimal(
                row.get("price")
            )
            for row in asks
            if isinstance(
                row,
                dict,
            )
        ]

        ask_prices = [
            value
            for value in ask_prices
            if value is not None
        ]

        lowest_ask = (
            min(ask_prices)
            if ask_prices
            else None
        )

        # --------------------------------------------------------
        # HIGHEST BID
        # --------------------------------------------------------
        bid_prices = [
            self._to_decimal(
                row.get("price")
            )
            for row in bids
            if isinstance(
                row,
                dict,
            )
        ]

        bid_prices = [
            value
            for value in bid_prices
            if value is not None
        ]

        highest_bid = (
            max(bid_prices)
            if bid_prices
            else None
        )

        # --------------------------------------------------------
        # LAST TRADE
        # --------------------------------------------------------
        last_trade_price = (
            self._to_decimal(
                snapshot_data.get(
                    "last_sale_price"
                )
            )
        )

        # --------------------------------------------------------
        # RAW MARKET METRICS
        #
        # 현재 asks/bids/sales는 일부 샘플일 수 있으므로
        # len() 값을 시장 전체 count로 저장하지 않는다.
        # --------------------------------------------------------
        market_metrics = {
            "asks": asks,
            "bids": bids,
            "sales": sales,
            "options": options,
            "listings": listings,
            "current_price": (
                snapshot_data.get(
                    "current_price"
                )
            ),
            "sample_counts": {
                "asks": len(asks),
                "bids": len(bids),
                "sales": len(sales),
                "listings": (
                    len(listings)
                ),
            },
            "last_sale_price": (
                snapshot_data.get(
                    "last_sale_price"
                )
            ),
            "has_immediate_delivery_item": (
                snapshot_data.get(
                    "has_immediate_delivery_item"
                )
            ),
        }

        snapshot, created = (
            ResaleSnapshot.objects
            .update_or_create(
                product_source=(
                    product_source
                ),
                observed_at=(
                    observed_at
                ),
                defaults={
                    # 현재 API만으로 전체 시장 건수라고
                    # 단정할 수 없으므로 NULL 유지.
                    "listing_count": None,
                    "available_count": (
                        None
                    ),

                    "min_price": None,
                    "max_price": None,
                    "avg_price": None,
                    "median_price": (
                        None
                    ),

                    "sold_count": None,

                    "lowest_ask": (
                        lowest_ask
                    ),
                    "highest_bid": (
                        highest_bid
                    ),
                    "last_trade_price": (
                        last_trade_price
                    ),

                    "trade_volume": None,

                    # 분석 후 계산
                    "resale_price_ratio": (
                        None
                    ),
                    "resale_index": None,

                    "market_metrics": (
                        market_metrics
                    ),
                },
            )
        )

        return {
            "created": created,
            "snapshot": snapshot,
            "observed_at": (
                observed_at
            ),
        }

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime:

        if isinstance(
            value,
            datetime,
        ):
            dt = value

        elif value:
            dt = parse_datetime(
                str(value)
            )

        else:
            dt = None

        if dt is None:
            return timezone.now()

        if timezone.is_naive(
            dt
        ):
            dt = (
                timezone.make_aware(
                    dt,
                    timezone.get_current_timezone(),
                )
            )

        return dt

    @staticmethod
    def _to_int(
        value: Any,
    ) -> int | None:

        if value in (
            None,
            "",
        ):
            return None

        if isinstance(
            value,
            bool,
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

        if isinstance(
            value,
            bool,
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