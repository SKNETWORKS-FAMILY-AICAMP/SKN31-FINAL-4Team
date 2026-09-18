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


CATEGORY_NAME_MAP = {
    "474": "상의",
    "547": "팬츠",
    "436": "아우터",
    "560": "스커트",
    "2757": "니트/카디건",
    "833": "트레이닝",
    "507": "원피스",
    "538": "투피스/세트",
}


class ZigzagNormalizer:
    """
    Zigzag CNV payload -> FEEDIT source layer.

    흐름:
        CNV Raw
        -> group/tag flatten
        -> product_id별 observation 병합
        -> BrandSource
        -> CategorySource
        -> ProductSource
        -> ProductSourceSnapshot

    원칙:
        - canonical Brand/Product를 억지로 만들지 않는다.
        - source layer는 UNMAPPED이어도 보존한다.
        - 기존 수동 매핑은 덮어쓰지 않는다.
        - 동일 상품의 trend/style/tpo 노출은 ProductSource 1개로 합친다.
        - tag/rank는 observed_tags로 모두 보존한다.
    """

    def __init__(self, *, source):
        self.source = source
        self._brand_lookup = None
        self._category_lookup = None

    @transaction.atomic
    def normalize_cnv_payload(
        self,
        raw: dict[str, Any],
        *,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("ZIGZAG raw payload는 dict여야 합니다.")

        data = self._unwrap_payload(raw)
        cnv = data.get("cnv") if isinstance(data.get("cnv"), dict) else {}
        groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}

        if not groups:
            raise ValueError("ZIGZAG CNV payload에 groups가 없습니다.")

        observed_at = self._parse_datetime(
            raw.get("collected_at") or data.get("collected_at")
        )

        category_id = clean_text(cnv.get("category_id"))
        if category_id is None:
            category_id = self._infer_category_id(groups)

        order = clean_text(cnv.get("order")) or "SCORE_DESC"

        observations = self.flatten_cnv_groups(
            groups=groups,
            category_id=category_id,
            order=order,
        )
        aggregated_products = self.aggregate_product_observations(observations)

        brand_created = brand_updated = 0
        category_created = category_updated = 0
        product_created = product_updated = 0
        snapshot_created = snapshot_updated = 0
        errors: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []

        for index, item in enumerate(aggregated_products, start=1):
            try:
                result = self.normalize_cnv_item(
                    item,
                    observed_at=observed_at,
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
                        "source_product_id": item.get("source_product_id"),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

        return {
            "source": self.source.code,
            "schema": "ZIGZAG_CNV",
            "observed_at": observed_at,
            "category_id": category_id,
            "category_name": CATEGORY_NAME_MAP.get(str(category_id)) if category_id else None,
            "order": order,
            "observation_count": len(observations),
            "unique_product_count": len(aggregated_products),
            "processed_count": len(results),
            "brand_sources": {"created": brand_created, "updated": brand_updated},
            "category_sources": {"created": category_created, "updated": category_updated},
            "product_sources": {"created": product_created, "updated": product_updated},
            "snapshots": {"created": snapshot_created, "updated": snapshot_updated},
            "error_count": len(errors),
            "errors": errors,
            "items": results,
        }

    def normalize_ranking_payload(
        self,
        raw: dict[str, Any],
        *,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:
        # 기존 source_ingestion service 호환 alias
        return self.normalize_cnv_payload(raw, create_snapshot=create_snapshot)

    def normalize_payload(
        self,
        raw: dict[str, Any],
        *,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:
        return self.normalize_cnv_payload(raw, create_snapshot=create_snapshot)

    def flatten_cnv_groups(
        self,
        *,
        groups: dict[str, Any],
        category_id: str | None,
        order: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for group_key, snapshots in groups.items():
            group_key = str(group_key).lower().strip()
            if not isinstance(snapshots, list):
                continue

            for snapshot in snapshots:
                if not isinstance(snapshot, dict):
                    continue

                tag_name = clean_text(snapshot.get("tag_name"))
                tag_group = clean_text(snapshot.get("tag_group"))
                tag_attribute = clean_text(snapshot.get("tag_attribute"))
                result_count = self._to_int(snapshot.get("result_count"))
                products = snapshot.get("products") if isinstance(snapshot.get("products"), list) else []

                for fallback_rank, product in enumerate(products, start=1):
                    if not isinstance(product, dict):
                        continue

                    source_product_id = clean_text(product.get("product_id"))
                    if source_product_id is None:
                        continue

                    rank = self._to_int(product.get("rank")) or fallback_rank
                    resolved_category_id = clean_text(category_id or snapshot.get("category_id"))

                    row = dict(product)
                    row.update(
                        {
                            "source_product_id": source_product_id,
                            "category_id": resolved_category_id,
                            "category_name": CATEGORY_NAME_MAP.get(str(resolved_category_id or "")),
                            "order": clean_text(snapshot.get("order")) or order,
                            "tag_group_key": group_key,
                            "tag_group": tag_group,
                            "tag_attribute": tag_attribute,
                            "tag_name": tag_name,
                            "tag_result_count": result_count,
                            "rank": rank,
                        }
                    )
                    rows.append(row)

        return rows

    def aggregate_product_observations(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_product: dict[str, dict[str, Any]] = {}

        for row in rows:
            source_product_id = clean_text(row.get("source_product_id"))
            if source_product_id is None:
                continue

            current = by_product.get(source_product_id)
            if current is None:
                current = dict(row)
                current["observed_tags"] = []
                by_product[source_product_id] = current
            else:
                self._merge_non_null_fields(current, row)

            observation = {
                "group": clean_text(row.get("tag_group_key")),
                "group_label": clean_text(row.get("tag_group")),
                "attribute": clean_text(row.get("tag_attribute")),
                "tag": clean_text(row.get("tag_name")),
                "rank": self._to_int(row.get("rank")),
                "result_count": self._to_int(row.get("tag_result_count")),
                "order": clean_text(row.get("order")),
            }

            if observation not in current["observed_tags"]:
                current["observed_tags"].append(observation)

        for item in by_product.values():
            ranks = [
                obs.get("rank")
                for obs in item["observed_tags"]
                if obs.get("rank") is not None
            ]
            item["best_rank"] = min(ranks) if ranks else None

        return list(by_product.values())

    def normalize_cnv_item(
        self,
        item: dict[str, Any],
        *,
        observed_at: datetime,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:
        brand_result = self.normalize_brand_source(self._extract_store(item))
        category_result = self.normalize_category_source(item)
        product_result = self.normalize_product_source(
            item,
            brand_source=brand_result["brand_source"],
            category_source=category_result["category_source"],
            observed_at=observed_at,
        )

        snapshot_result = {"created": False, "snapshot": None}
        if create_snapshot:
            snapshot_result = self.normalize_snapshot(
                item,
                product_source=product_result["product_source"],
                observed_at=observed_at,
            )

        return {
            "source_product_id": product_result["product_source"].source_product_id,
            "brand_source": brand_result["brand_source"],
            "brand_source_created": brand_result["created"],
            "category_source": category_result["category_source"],
            "category_source_created": category_result["created"],
            "product_source": product_result["product_source"],
            "product_source_created": product_result["created"],
            "snapshot": snapshot_result["snapshot"],
            "snapshot_created": snapshot_result["created"],
            "observed_tag_count": len(item.get("observed_tags") or []),
        }

    def normalize_brand_source(
        self,
        store: dict[str, Any] | None,
    ) -> dict[str, Any]:
        store = store if isinstance(store, dict) else {}

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

        if source_brand_id is None and name is None:
            return {
                "created": False,
                "brand_source": None,
                "matched": False,
                "matched_by": "NO_STORE",
            }

        if source_brand_id is None:
            source_brand_id = "name:" + normalize_brand_name(name)

        now = timezone.now()

        brand_source = (
            BrandSource.objects.select_related("brand")
            .filter(source=self.source, source_brand_id=str(source_brand_id))
            .first()
        )
        created = brand_source is None

        if created:
            canonical_brand = self._find_brand(name)
            defaults = {
                "brand": canonical_brand,
                "source": self.source,
                "source_brand_id": str(source_brand_id),
                "name": name,
                "first_seen_at": now,
                "last_seen_at": now,
                "detected_count": 1,
                "attributes": {"zigzag_shop_id": str(source_brand_id)},
            }

            if canonical_brand is not None:
                defaults["mapping_status"] = BrandSource.MappingStatus.AUTO_MAPPED
                defaults["mapping_method"] = BrandSource.MappingMethod.EXACT_NAME
                defaults["mapping_confidence"] = Decimal("1.0000")
            else:
                defaults["mapping_status"] = BrandSource.MappingStatus.UNMAPPED

            brand_source = BrandSource.objects.create(**defaults)
        else:
            if name:
                brand_source.name = name

            current_attributes = (
                dict(brand_source.attributes)
                if isinstance(brand_source.attributes, dict)
                else {}
            )
            current_attributes["zigzag_shop_id"] = str(source_brand_id)
            brand_source.attributes = current_attributes

            if brand_source.first_seen_at is None:
                brand_source.first_seen_at = now

            brand_source.last_seen_at = now
            brand_source.detected_count = (brand_source.detected_count or 0) + 1
            brand_source.save()

        return {
            "created": created,
            "brand_source": brand_source,
            "matched": brand_source.brand_id is not None,
            "matched_by": brand_source.mapping_method if brand_source.brand_id else "UNMAPPED",
        }

    def normalize_category_source(
        self,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        category_id = clean_text(item.get("category_id"))
        category_name = clean_text(item.get("category_name"))

        if category_name is None and category_id is not None:
            category_name = CATEGORY_NAME_MAP.get(str(category_id))

        if category_id is None and category_name is None:
            return {
                "created": False,
                "category_source": None,
                "category": None,
                "matched": False,
            }

        if category_id is None:
            category_id = "name:" + normalize_category_name(category_name)

        normalized_name = normalize_category_name(category_name) if category_name else None
        now = timezone.now()

        category_source = (
            CategorySource.objects.select_related("category")
            .filter(source=self.source, source_category_id=str(category_id))
            .first()
        )
        created = category_source is None

        if created:
            category = self._find_category(normalized_name)
            category_source = CategorySource.objects.create(
                category=category,
                source=self.source,
                source_category_id=str(category_id),
                source_category_name=category_name,
                source_category_path=category_name,
                first_seen_at=now,
                last_seen_at=now,
            )
        else:
            if category_name:
                category_source.source_category_name = category_name
                category_source.source_category_path = category_name

            if category_source.first_seen_at is None:
                category_source.first_seen_at = now

            category_source.last_seen_at = now
            category_source.save()

        return {
            "created": created,
            "category_source": category_source,
            "category": category_source.category,
            "matched": category_source.category_id is not None,
        }

    def normalize_product_source(
        self,
        item: dict[str, Any],
        *,
        brand_source: BrandSource | None,
        category_source: CategorySource | None,
        observed_at: datetime,
    ) -> dict[str, Any]:
        source_product_id = clean_text(
            item.get("source_product_id") or item.get("product_id")
        )
        if source_product_id is None:
            raise ValueError("ZIGZAG source_product_id가 없습니다.")

        raw_source_name = clean_text(
            item.get("product_name") or item.get("title") or item.get("name")
        )

        name_result = ProductNamePreprocessor.parse(
            raw_source_name,
            existing_tags=[],
            source_code="ZIGZAG",
        )
        source_name = name_result["source_name"]

        thumbnail_url = clean_text(item.get("image_url") or item.get("thumbnail_url"))
        product_url = clean_text(item.get("product_url"))
        if product_url is None:
            product_url = f"https://zigzag.kr/catalog/products/{source_product_id}"

        observed_tags = (
            item.get("observed_tags")
            if isinstance(item.get("observed_tags"), list)
            else []
        )

        source_attributes = {
            "zigzag": {
                "shop_id": clean_text(item.get("shop_id")),
                "shop_name": clean_text(item.get("shop_name")),
                "sales_status": clean_text(item.get("sales_status")),
                "shipping_type": clean_text(item.get("shipping_type")),
                "arrival_text": clean_text(item.get("arrival_text")),
                "fomo_text": clean_text(item.get("fomo_text")),
                "social_proof_value": self._to_int(item.get("social_proof_value")),
                "is_new": self._to_bool(item.get("is_new")),
                "is_ad": self._to_bool(item.get("is_ad")),
                "badge_list": item.get("badge_list") or [],
                "server_log": (
                    item.get("server_log")
                    if isinstance(item.get("server_log"), dict)
                    else {}
                ),
                "category_id": clean_text(item.get("category_id")),
                "order": clean_text(item.get("order")),
            },
            "observed_tags": observed_tags,
            "tags": name_result["tags"],
            "source_name_meta": name_result["source_name_meta"],
        }

        product_source = (
            ProductSource.objects
            .filter(source=self.source, source_product_id=str(source_product_id))
            .first()
        )
        created = product_source is None

        if created:
            product_source = ProductSource.objects.create(
                product=None,
                source=self.source,
                source_product_id=str(source_product_id),
                source_brand=brand_source,
                source_category=category_source,
                source_name=source_name,
                source_name_en=None,
                normalized_name=None,
                style_no=None,
                thumbnail_url=thumbnail_url,
                product_url=product_url,
                gender_scope=None,
                attributes=source_attributes,
                market_type=ProductSource.MarketType.RETAIL,
                mapping_status=ProductSource.MappingStatus.UNMAPPED,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
                detected_count=1,
                status=ProductSource.Status.ACTIVE,
            )
        else:
            # canonical product 연결은 유지
            product_source.source_brand = brand_source
            product_source.source_category = category_source
            product_source.source_name = source_name

            existing_attributes = (
                product_source.attributes
                if isinstance(product_source.attributes, dict)
                else {}
            )

            if not existing_attributes.get("feedit_analysis"):
                product_source.normalized_name = None

            product_source.thumbnail_url = thumbnail_url
            product_source.product_url = product_url

            current_attributes = dict(existing_attributes)
            current_attributes.update(source_attributes)
            product_source.attributes = current_attributes

            if product_source.first_seen_at is None:
                product_source.first_seen_at = observed_at

            product_source.last_seen_at = observed_at
            product_source.detected_count = (product_source.detected_count or 0) + 1
            product_source.status = ProductSource.Status.ACTIVE
            product_source.save()

        return {"created": created, "product_source": product_source}


    def normalize_snapshot(
        self,
        item: dict[str, Any],
        *,
        product_source: ProductSource,
        observed_at: datetime,
    ) -> dict[str, Any]:
        observed_tags = (
            item.get("observed_tags")
            if isinstance(item.get("observed_tags"), list)
            else []
        )
        best_rank = self._to_int(item.get("best_rank"))

        best_observations = [
            obs
            for obs in observed_tags
            if self._to_int(obs.get("rank")) == best_rank
        ]

        ranking_context = {
            "source": "ZIGZAG_CNV",
            "category_id": clean_text(item.get("category_id")),
            "category_name": clean_text(item.get("category_name")),
            "order": clean_text(item.get("order")),
            "observations": observed_tags,
            "best_observations": best_observations,
        }

        platform_metrics = {
            "review_score": self._to_float(item.get("review_score")),
            "review_count": self._to_int(item.get("review_count")),
            "fomo_text": clean_text(item.get("fomo_text")),
            "social_proof_value": self._to_int(item.get("social_proof_value")),
            "sales_status": clean_text(item.get("sales_status")),
            "shipping_type": clean_text(item.get("shipping_type")),
            "arrival_text": clean_text(item.get("arrival_text")),
            "is_new": self._to_bool(item.get("is_new")),
            "is_ad": self._to_bool(item.get("is_ad")),
            "badge_list": item.get("badge_list") or [],
            "tag_observations": observed_tags,
            "tag_count": len(observed_tags),
        }

        defaults = {
            "list_price": self._to_decimal(item.get("max_price")),
            "sale_price": self._to_decimal(item.get("final_price")),
            "discount_rate": self._to_decimal(item.get("discount_rate")),
            "rank_position": best_rank,
            "ranking_scope": "CNV_TAG",
            "ranking_context": ranking_context,
            "rating": self._to_decimal(item.get("review_score")),
            "review_count": self._to_int(item.get("review_count")),
            # social_proof_value를 like로 단정하지 않는다.
            "like_count": None,
            "stock_status": clean_text(item.get("sales_status")),
            "platform_metrics": platform_metrics,
        }

        snapshot, created = ProductSourceSnapshot.objects.update_or_create(
            product_source=product_source,
            observed_at=observed_at,
            defaults=defaults,
        )
        return {"created": created, "snapshot": snapshot}

    @staticmethod
    def _unwrap_payload(raw: dict[str, Any]) -> dict[str, Any]:
        payload = raw.get("payload")
        return payload if isinstance(payload, dict) else raw

    @staticmethod
    def _extract_store(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_brand_id": item.get("shop_id"),
            "shop_id": item.get("shop_id"),
            "name": item.get("shop_name"),
            "shop_name": item.get("shop_name"),
        }

    @staticmethod
    def _infer_category_id(groups: dict[str, Any]) -> str | None:
        for snapshots in groups.values():
            if not isinstance(snapshots, list):
                continue
            for snapshot in snapshots:
                if not isinstance(snapshot, dict):
                    continue
                category_id = clean_text(snapshot.get("category_id"))
                if category_id:
                    return category_id
        return None

    @staticmethod
    def _merge_non_null_fields(
        current: dict[str, Any],
        incoming: dict[str, Any],
    ) -> None:
        for key, value in incoming.items():
            if key == "observed_tags":
                continue
            if value in (None, "", [], {}):
                continue
            if current.get(key) in (None, "", [], {}):
                current[key] = value

    def _find_brand(
        self,
        name: str | None,
    ) -> Brand | None:

        if not name:
            return None

        normalized = normalize_brand_name(
            name
        )

        if not normalized:
            return None

        # 최초 1회만 Brand 전체 조회
        if self._brand_lookup is None:

            lookup = {}

            brands = (
                Brand.objects
                .filter(
                    status=Brand.Status.ACTIVE
                )
                .only(
                    "id",
                    "name",
                    "english_name",
                )
            )

            for brand in brands:

                for candidate in (
                    brand.name,
                    brand.english_name,
                ):

                    if not candidate:
                        continue

                    key = normalize_brand_name(
                        candidate
                    )

                    if not key:
                        continue

                    # 같은 이름이 여러 canonical brand에
                    # 존재하면 자동매핑하지 않도록 None 처리
                    if key in lookup:
                        lookup[key] = None
                    else:
                        lookup[key] = brand

            self._brand_lookup = lookup

        return self._brand_lookup.get(
            normalized
        )
    
    def _find_category(
        self,
        normalized_name: str | None,
    ) -> Category | None:

        if not normalized_name:
            return None

        if self._category_lookup is None:

            lookup = {}

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
                    "name",
                )
            )

            for category in categories:

                key = normalize_category_name(
                    category.name
                )

                if not key:
                    continue

                if key in lookup:
                    lookup[key] = None
                else:
                    lookup[key] = category

            self._category_lookup = lookup

        return self._category_lookup.get(
            normalized_name
        )
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
            dt = timezone.make_aware(dt, timezone.get_current_timezone())

        return dt

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return int(value)
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", "").replace("%", "").strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value).replace(",", "").replace("%", "").strip())
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _to_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if value is None:
            return None

        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n"}:
            return False
        return None
