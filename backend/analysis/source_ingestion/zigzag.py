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
)

from analysis.source_ingestion.common import (
    clean_text,
    normalize_brand_name,
    normalize_category_name,
)

from analysis.source_ingestion.product_name_preprocessor import (
    ProductNamePreprocessor,
)


class ZigzagNormalizer:
    """
    Zigzag schema 3.x ranking/store payload -> FEEDIT DB.

    기준
    ------------------------------------------------------------
    BrandSource.source_brand_id = Zigzag shop_id
    BrandSource.attributes["main_domain"] = Zigzag main_domain
    BrandSource.source_profile_url = https://zigzag.kr/{main_domain}

    Ranking item 예:
    {
        "rank": 1,
        "source_product_id": "...",
        "product_name": "...",
        "store": {
            "source_brand_id": "88",
            "name": "케이클럽",
            "main_domain": "kclub",
            "source_profile_url": "https://zigzag.kr/kclub"
        },
        "category_id": "435",
        "category_name": "롱원피스",
        "category_path": [...],
        "regular_price": 27400,
        "sale_price": 24110,
        "discount_rate": 58.0,
        "review_score": 4.9,
        "review_count": 208,
        ...
    }

    중요:
    - canonical Brand / Product를 억지로 생성하지 않는다.
    - source 레이어는 UNMAPPED여도 반드시 보존한다.
    - 이미 수동 매핑된 BrandSource / ProductSource 연결은 보존한다.
    """

    def __init__(self, *, source):
        self.source = source

    # ============================================================
    # PUBLIC
    # ============================================================

    @transaction.atomic
    def normalize_ranking_payload(
        self,
        raw: dict[str, Any],
        *,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:
        """
        S3 raw JSON 또는 pipeline payload 모두 허용.

        create_snapshot=False이면
        BrandSource / CategorySource / ProductSource까지만 저장하고
        ProductSourceSnapshot은 생성하지 않는다.

        지원:
        1)
        {
            "payload": {
                "ranking": {
                    "items": [...]
                }
            }
        }

        2)
        {
            "ranking": {
                "items": [...]
            }
        }

        3)
        {
            "products": [...]
        }
        """

        if not isinstance(raw, dict):
            raise ValueError(
                "ZIGZAG raw payload는 dict여야 합니다."
            )

        payload = raw.get("payload")
        if isinstance(payload, dict):
            data = payload
        else:
            data = raw

        ranking = (
            data.get("ranking")
            if isinstance(
                data.get("ranking"),
                dict,
            )
            else {}
        )

        items = (
            ranking.get("items")
            if isinstance(
                ranking.get("items"),
                list,
            )
            else data.get("products")
        )

        if not isinstance(items, list):
            items = []

        observed_at = self._parse_datetime(
            raw.get("collected_at")
            or data.get("collected_at")
        )

        ranking_context = {
            "category_id": (
                ranking.get("category_id")
                or (
                    data.get("target") or {}
                ).get("category_id")
            ),
            "sort": (
                ranking.get("sort")
                or (
                    data.get("target") or {}
                ).get("sort")
            ),
            "page_id": (
                ranking.get("page_id")
                or (
                    data.get("target") or {}
                ).get("page_id")
            ),
            "source_url": (
                ranking.get("source_url")
                or (
                    data.get("target") or {}
                ).get("target_url")
                or raw.get("source_url")
            ),
        }

        brand_created = 0
        brand_updated = 0
        product_created = 0
        product_updated = 0
        snapshot_created = 0
        snapshot_updated = 0
        category_created = 0
        category_updated = 0
        errors = []

        results = []

        for index, item in enumerate(
            items,
            start=1,
        ):
            if not isinstance(item, dict):
                continue

            try:
                result = self.normalize_ranking_item(
                    item,
                    observed_at=observed_at,
                    ranking_context=ranking_context,
                    fallback_rank=index,
                    create_snapshot=create_snapshot,
                )

                results.append(result)

                if result["brand_source_created"]:
                    brand_created += 1
                elif result["brand_source"] is not None:
                    brand_updated += 1

                if result["category_source_created"]:
                    category_created += 1
                elif result["category_source"] is not None:
                    category_updated += 1

                if result["product_source_created"]:
                    product_created += 1
                else:
                    product_updated += 1

                if create_snapshot:
                    if result["snapshot_created"]:
                        snapshot_created += 1
                    else:
                        snapshot_updated += 1

            except Exception as exc:
                errors.append(
                    {
                        "index": index,
                        "source_product_id": (
                            item.get("source_product_id")
                            or item.get(
                                "catalog_product_id"
                            )
                        ),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

        return {
            "source": self.source.code,
            "observed_at": observed_at,
            "count": len(results),
            "brand_sources": {
                "created": brand_created,
                "updated": brand_updated,
            },
            "category_sources": {
                "created": category_created,
                "updated": category_updated,
            },
            "product_sources": {
                "created": product_created,
                "updated": product_updated,
            },
            "snapshots": {
                "created": snapshot_created,
                "updated": snapshot_updated,
            },
            "errors": errors,
            "items": results,
        }

    @transaction.atomic
    def normalize_ranking_item(
        self,
        item: dict[str, Any],
        *,
        observed_at: datetime | None = None,
        ranking_context: dict[str, Any] | None = None,
        fallback_rank: int | None = None,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:

        observed_at = (
            observed_at
            or timezone.now()
        )

        ranking_context = (
            dict(ranking_context)
            if isinstance(
                ranking_context,
                dict,
            )
            else {}
        )

        brand_result = (
            self.normalize_brand_source(
                self._extract_store(item)
            )
        )

        category_result = (
            self.normalize_category_source(
                item
            )
        )

        product_result = (
            self.normalize_product_source(
                item,
                brand_source=(
                    brand_result[
                        "brand_source"
                    ]
                ),
                category_source=(
                    category_result[
                        "category_source"
                    ]
                ),
                observed_at=observed_at,
            )
        )

        snapshot_result = {
            "created": False,
            "snapshot": None,
        }

        if create_snapshot:
            snapshot_result = (
                self.normalize_snapshot(
                    item,
                    product_source=(
                        product_result[
                            "product_source"
                        ]
                    ),
                    observed_at=observed_at,
                    ranking_context=ranking_context,
                    fallback_rank=fallback_rank,
                )
            )

        return {
            "source_product_id": (
                product_result[
                    "product_source"
                ].source_product_id
            ),
            "brand_source": (
                brand_result[
                    "brand_source"
                ]
            ),
            "brand_source_created": (
                brand_result["created"]
            ),
            "category_source": (
                category_result[
                    "category_source"
                ]
            ),
            "category_source_created": (
                category_result["created"]
            ),
            "product_source": (
                product_result[
                    "product_source"
                ]
            ),
            "product_source_created": (
                product_result["created"]
            ),
            "snapshot": (
                snapshot_result["snapshot"]
            ),
            "snapshot_created": (
                snapshot_result["created"]
            ),
        }

    # ============================================================
    # BRAND SOURCE
    # ============================================================

    @transaction.atomic
    def normalize_brand_source(
        self,
        store: dict[str, Any] | None,
    ) -> dict[str, Any]:

        store = (
            store
            if isinstance(store, dict)
            else {}
        )

        source_brand_id = clean_text(
            store.get("source_brand_id")
            or store.get("shop_id")
            or store.get("store_id")
            or store.get("id")
        )

        name = clean_text(
            store.get("name")
            or store.get("shop_name")
            or store.get("store_name")
        )

        if (
            source_brand_id is None
            and name is None
        ):
            return {
                "created": False,
                "brand_source": None,
                "matched": False,
                "matched_by": "NO_STORE",
            }

        # shop_id가 없는 예외 케이스만 이름 fallback
        if source_brand_id is None:
            source_brand_id = (
                "name:"
                + normalize_brand_name(
                    name
                )
            )

        main_domain = clean_text(
            store.get("main_domain")
            or store.get("shop_domain")
            or store.get("domain")
        )

        source_profile_url = clean_text(
            store.get("source_profile_url")
            or store.get("profile_url")
        )

        if (
            not source_profile_url
            and main_domain
        ):
            source_profile_url = (
                f"https://zigzag.kr/"
                f"{main_domain}"
            )

        english_name = clean_text(
            store.get("english_name")
        )

        image_url = clean_text(
            store.get("image_url")
        )

        description = clean_text(
            store.get("description")
        )

        now = timezone.now()

        brand_source = (
            BrandSource.objects
            .select_related("brand")
            .filter(
                source=self.source,
                source_brand_id=(
                    str(source_brand_id)
                ),
            )
            .first()
        )

        created = (
            brand_source is None
        )

        if created:
            canonical_brand = (
                self._find_brand(
                    name
                )
            )

            defaults = {
                "brand": canonical_brand,
                "source": self.source,
                "source_brand_id": (
                    str(source_brand_id)
                ),
                "name": name,
                "english_name": english_name,
                "image_url": image_url,
                "description": description,
                "source_profile_url": (
                    source_profile_url
                ),
                "attributes": (
                    self._build_store_attributes(
                        store,
                        current=None,
                        main_domain=main_domain,
                    )
                ),
                "first_seen_at": now,
                "last_seen_at": now,
                "detected_count": 1,
            }

            if canonical_brand is not None:
                defaults[
                    "mapping_status"
                ] = (
                    BrandSource
                    .MappingStatus
                    .AUTO_MAPPED
                )
                defaults[
                    "mapping_method"
                ] = (
                    BrandSource
                    .MappingMethod
                    .EXACT_NAME
                )
                defaults[
                    "mapping_confidence"
                ] = Decimal("1.0000")
            else:
                defaults[
                    "mapping_status"
                ] = (
                    BrandSource
                    .MappingStatus
                    .UNMAPPED
                )

            brand_source = (
                BrandSource.objects.create(
                    **defaults
                )
            )

        else:
            # 기존 canonical 매핑은 절대 덮어쓰지 않는다.
            if name:
                brand_source.name = name

            if english_name:
                brand_source.english_name = (
                    english_name
                )

            if image_url:
                brand_source.image_url = (
                    image_url
                )

            if description:
                brand_source.description = (
                    description
                )

            if source_profile_url:
                brand_source.source_profile_url = (
                    source_profile_url
                )

            brand_source.attributes = (
                self._build_store_attributes(
                    store,
                    current=(
                        brand_source.attributes
                    ),
                    main_domain=main_domain,
                )
            )

            if (
                brand_source.first_seen_at
                is None
            ):
                brand_source.first_seen_at = (
                    now
                )

            brand_source.last_seen_at = now

            brand_source.detected_count = (
                (
                    brand_source.detected_count
                    or 0
                )
                + 1
            )

            brand_source.save()

        return {
            "created": created,
            "brand_source": brand_source,
            "matched": (
                brand_source.brand_id
                is not None
            ),
            "matched_by": (
                brand_source.mapping_method
                if brand_source.brand_id
                else "UNMAPPED"
            ),
        }

    # ============================================================
    # CATEGORY SOURCE
    # ============================================================

    @transaction.atomic
    def normalize_category_source(
        self,
        item: dict[str, Any],
    ) -> dict[str, Any]:

        category_path = (
            item.get("category_path")
            if isinstance(
                item.get("category_path"),
                list,
            )
            else []
        )

        category_id = clean_text(
            item.get("category_id")
        )

        category_name = clean_text(
            item.get("category_name")
        )

        if (
            category_path
            and (
                category_id is None
                or category_name is None
            )
        ):
            leaf = self._deepest_category(
                category_path
            )

            category_id = (
                category_id
                or clean_text(
                    leaf.get("id")
                    or leaf.get(
                        "category_id"
                    )
                )
            )

            category_name = (
                category_name
                or clean_text(
                    leaf.get("name")
                    or leaf.get("value")
                )
            )

        if (
            category_id is None
            and category_name is None
        ):
            return {
                "created": False,
                "category_source": None,
                "category": None,
                "matched": False,
            }

        if category_id is None:
            category_id = (
                "name:"
                + normalize_category_name(
                    category_name
                )
            )

        path_names = []

        for node in category_path:
            if not isinstance(
                node,
                dict,
            ):
                continue

            value = clean_text(
                node.get("name")
                or node.get("value")
            )

            if value:
                path_names.append(value)

        source_category_path = (
            " > ".join(path_names)
            if path_names
            else category_name
        )

        normalized_name = (
            normalize_category_name(
                category_name
            )
        )

        now = timezone.now()

        category_source = (
            CategorySource.objects
            .select_related("category")
            .filter(
                source=self.source,
                source_category_id=(
                    str(category_id)
                ),
            )
            .first()
        )

        created = (
            category_source is None
        )

        if created:
            category = (
                self._find_category(
                    normalized_name
                )
            )

            category_source = (
                CategorySource.objects.create(
                    category=category,
                    source=self.source,
                    source_category_id=(
                        str(category_id)
                    ),
                    source_category_name=(
                        category_name
                    ),
                    source_category_path=(
                        source_category_path
                    ),
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )

        else:
            category_source.source_category_name = (
                category_name
            )
            category_source.source_category_path = (
                source_category_path
            )

            if (
                category_source.first_seen_at
                is None
            ):
                category_source.first_seen_at = (
                    now
                )

            category_source.last_seen_at = now
            category_source.save()

        return {
            "created": created,
            "category_source": (
                category_source
            ),
            "category": (
                category_source.category
            ),
            "matched": (
                category_source.category_id
                is not None
            ),
        }

    # ============================================================
    # PRODUCT SOURCE
    # ============================================================

    @transaction.atomic
    def normalize_product_source(
        self,
        item: dict[str, Any],
        *,
        brand_source: BrandSource | None,
        category_source: CategorySource | None,
        observed_at: datetime,
    ) -> dict[str, Any]:

        source_product_id = clean_text(
            item.get("source_product_id")
            or item.get(
                "catalog_product_id"
            )
            or item.get("goods_id")
        )

        if source_product_id is None:
            raise ValueError(
                "ZIGZAG source_product_id가 없습니다."
            )

        raw_source_name = clean_text(
            item.get("product_name")
            or item.get("title")
            or item.get("name")
        )

        source_tags = item.get("tags") or []

        if not isinstance(
            source_tags,
            (list, tuple),
        ):
            source_tags = []

        name_result = (
            ProductNamePreprocessor.parse(
                raw_source_name,
                existing_tags=source_tags,
                source_code="ZIGZAG",
            )
        )

        source_name = name_result[
            "source_name"
        ]

        product_url = clean_text(
            item.get("product_url")
        )

        thumbnail_url = clean_text(
            item.get("thumbnail_url")
            or item.get("image_url")
        )

        source_attributes = {
            "is_brand": item.get(
                "is_brand"
            ),
            "catalog_product_id": (
                clean_text(
                    item.get(
                        "catalog_product_id"
                    )
                )
            ),
            "category_path": (
                item.get(
                    "category_path"
                )
                or []
            ),
            "sellable_status": (
                clean_text(
                    item.get(
                        "sellable_status"
                    )
                )
            ),
            "tags": name_result["tags"],
            "source_name_meta": (
                name_result[
                    "source_name_meta"
                ]
            ),
        }

        product_source = (
            ProductSource.objects
            .filter(
                source=self.source,
                source_product_id=(
                    str(source_product_id)
                ),
            )
            .first()
        )

        created = (
            product_source is None
        )

        if created:
            product_source = (
                ProductSource.objects.create(
                    product=None,
                    source=self.source,
                    source_product_id=(
                        str(source_product_id)
                    ),
                    source_brand=brand_source,
                    source_category=(
                        category_source
                    ),
                    source_name=source_name,
                    source_name_en=None,
                    normalized_name=None,
                    style_no=None,
                    thumbnail_url=(
                        thumbnail_url
                    ),
                    product_url=product_url,
                    gender_scope=None,
                    attributes=source_attributes,
                    market_type=(
                        ProductSource
                        .MarketType
                        .RETAIL
                    ),
                    mapping_status=(
                        ProductSource
                        .MappingStatus
                        .UNMAPPED
                    ),
                    first_seen_at=(
                        observed_at
                    ),
                    last_seen_at=(
                        observed_at
                    ),
                    detected_count=1,
                    status=(
                        ProductSource
                        .Status
                        .ACTIVE
                    ),
                )
            )

        else:
            # canonical product 매핑은 유지하고
            # source 정보만 갱신
            product_source.source_brand = (
                brand_source
            )

            product_source.source_category = (
                category_source
            )

            product_source.source_name = (
                source_name
            )

            # 기존 normalized_name이 옛날 STEP 1 잔재라면 제거.
            # 실제 Product Enrichment 결과(feedit_analysis)가 있을 때만 보존.
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

            product_source.thumbnail_url = (
                thumbnail_url
            )

            product_source.product_url = (
                product_url
            )

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

            if (
                product_source.first_seen_at
                is None
            ):
                product_source.first_seen_at = (
                    observed_at
                )

            product_source.last_seen_at = (
                observed_at
            )

            product_source.detected_count = (
                (
                    product_source.detected_count
                    or 0
                )
                + 1
            )

            product_source.status = (
                ProductSource.Status.ACTIVE
            )

            product_source.save()

        return {
            "created": created,
            "product_source": (
                product_source
            ),
        }

    # ============================================================
    # SNAPSHOT
    # ============================================================

    @transaction.atomic
    def normalize_snapshot(
        self,
        item: dict[str, Any],
        *,
        product_source: ProductSource,
        observed_at: datetime,
        ranking_context: dict[str, Any],
        fallback_rank: int | None = None,
    ) -> dict[str, Any]:

        rank = self._to_int(
            item.get("rank")
        )

        if rank is None:
            rank = fallback_rank

        platform_metrics = {
            # JSONField에는 Decimal을 직접 넣지 않는다.
            # DB DecimalField인 rating에는 Decimal을 사용하고,
            # platform_metrics(JSON)에는 float로 저장한다.
            "review_score": (
                self._to_float(
                    item.get(
                        "review_score"
                    )
                )
            ),
            "interest_count": (
                self._to_int(
                    item.get(
                        "interest_count"
                    )
                )
            ),
            "fomo_text": clean_text(
                item.get("fomo_text")
            ),
            "is_ad": item.get("is_ad"),
            "is_brand": item.get(
                "is_brand"
            ),
            "sellable_status": (
                clean_text(
                    item.get(
                        "sellable_status"
                    )
                )
            ),
        }

        defaults = {
            "list_price": (
                self._to_decimal(
                    item.get(
                        "regular_price"
                    )
                    or item.get(
                        "list_price"
                    )
                )
            ),
            "sale_price": (
                self._to_decimal(
                    item.get(
                        "sale_price"
                    )
                )
            ),
            "discount_rate": (
                self._to_decimal(
                    item.get(
                        "discount_rate"
                    )
                )
            ),
            "rank_position": rank,
            "ranking_scope": "CATEGORY",
            "ranking_context": (
                ranking_context
            ),
            "rating": (
                self._to_decimal(
                    item.get(
                        "review_score"
                    )
                )
            ),
            "review_count": (
                self._to_int(
                    item.get(
                        "review_count"
                    )
                )
            ),
            "like_count": (
                self._to_int(
                    item.get(
                        "interest_count"
                    )
                )
            ),
            "stock_status": (
                clean_text(
                    item.get(
                        "sellable_status"
                    )
                )
            ),
            "platform_metrics": (
                platform_metrics
            ),
        }

        snapshot, created = (
            ProductSourceSnapshot
            .objects
            .update_or_create(
                product_source=(
                    product_source
                ),
                observed_at=observed_at,
                defaults=defaults,
            )
        )

        return {
            "created": created,
            "snapshot": snapshot,
        }

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _extract_store(
        item: dict[str, Any],
    ) -> dict[str, Any]:

        store = (
            item.get("store")
            if isinstance(
                item.get("store"),
                dict,
            )
            else {}
        )

        # schema 2.x / 과거 raw 호환
        if not store:
            store = {
                "source_brand_id": (
                    item.get("store_id")
                    or item.get("shop_id")
                ),
                "name": (
                    item.get("store_name")
                    or item.get("shop_name")
                ),
                "main_domain": (
                    item.get("main_domain")
                    or item.get("shop_domain")
                ),
                "source_profile_url": (
                    item.get(
                        "source_profile_url"
                    )
                ),
            }

        return store

    @staticmethod
    def _build_store_attributes(
        store: dict[str, Any],
        *,
        current: dict | None,
        main_domain: str | None,
    ) -> dict[str, Any]:

        result = (
            dict(current)
            if isinstance(
                current,
                dict,
            )
            else {}
        )

        if main_domain:
            result["main_domain"] = (
                main_domain
            )

        for key in (
            "bookmark_count",
            "seller_badges",
            "total_product_count",
            "is_brand",
        ):
            value = store.get(key)

            if value not in (
                None,
                "",
                [],
                {},
            ):
                result[key] = value

        return result

    @staticmethod
    def _deepest_category(
        path: list[dict[str, Any]],
    ) -> dict[str, Any]:

        candidates = [
            item
            for item in path
            if isinstance(item, dict)
        ]

        if not candidates:
            return {}

        return max(
            candidates,
            key=lambda item: (
                ZigzagNormalizer._to_int(
                    item.get("depth")
                )
                or 0
            ),
        )

    @staticmethod
    def _find_brand(
        name: str | None,
    ) -> Brand | None:

        if not name:
            return None

        normalized = (
            normalize_brand_name(name)
        )

        if not normalized:
            return None

        matches = []

        for brand in (
            Brand.objects
            .filter(
                status=Brand.Status.ACTIVE
            )
            .only(
                "id",
                "name",
                "english_name",
            )
        ):
            for candidate in (
                brand.name,
                brand.english_name,
            ):
                if (
                    candidate
                    and normalize_brand_name(
                        candidate
                    )
                    == normalized
                ):
                    matches.append(brand)
                    break

        if len(matches) != 1:
            return None

        return matches[0]

    @staticmethod
    def _find_category(
        normalized_name: str | None,
    ) -> Category | None:

        if not normalized_name:
            return None

        matches = []

        for category in (
            Category.objects
            .filter(
                category_type=(
                    Category
                    .CategoryType
                    .PRODUCT
                ),
                status=(
                    Category.Status.ACTIVE
                ),
            )
            .only(
                "id",
                "name",
            )
        ):
            if (
                normalize_category_name(
                    category.name
                )
                == normalized_name
            ):
                matches.append(
                    category
                )

        if len(matches) != 1:
            return None

        return matches[0]

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

        if timezone.is_naive(dt):
            dt = timezone.make_aware(
                dt,
                timezone.get_current_timezone(),
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
    def _to_float(
        value: Any,
    ) -> float | None:

        if value in (
            None,
            "",
        ):
            return None

        try:
            return float(
                str(value)
                .replace(",", "")
                .replace("%", "")
                .strip()
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
