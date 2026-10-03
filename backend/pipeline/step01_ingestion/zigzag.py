from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo
from django.db import transaction
from django.utils import timezone
from apps.core.models import (
    BrandSource,
    CategorySource,
    ProductSource,
    ProductSourceSnapshot,
    RawDocument,
)
from .common import (
    base_cleaning,
    extract_payload,
    get_s3_client,
    load_raw_json,
)
KST = ZoneInfo("Asia/Seoul")
class ZigzagIngestion:
    SOURCE_CODE = "zigzag"
    def __init__(self):
        self.s3 = get_s3_client()
    def run(self, raw_document_id: int) -> dict:
        raw_document = (
            RawDocument.objects
            .select_related("source", "crawl_run")
            .get(pk=raw_document_id)
        )
        self._validate_raw_document(raw_document)

        raw_data = load_raw_json(raw_document, s3_client=self.s3)
        payload = extract_payload(raw_data)

        entity_type = (base_cleaning(payload.get("entity_type")) or "").upper()

        if entity_type == "RANKING":
            return self._run_ranking(
                raw_document=raw_document,
                payload=payload,
            )

        if entity_type == "CNV_CATEGORY":
            return self._run_cnv_category(
                raw_document=raw_document,
                payload=payload,
            )

        raise ValueError(
            "ZIGZAG STEP01이 지원하지 않는 entity_type입니다. "
            f"entity_type={entity_type}"
        )

    def _run_ranking(
        self,
        *,
        raw_document: RawDocument,
        payload: dict,
    ) -> dict:
        ranking_mode = base_cleaning(payload.get("ranking_mode"))

        if (ranking_mode or "").lower() != "detail_category":
            raise ValueError(
                "ZIGZAG RANKING STEP01은 detail_category만 지원합니다. "
                f"ranking_mode={ranking_mode}"
            )

        rows = self._extract_ranking_rows(payload)
        result = self._empty_result(raw_document.id)
        result["entity_type"] = "RANKING"

        for index, row in enumerate(rows, start=1):
            result["products"] += 1
            try:
                one = self._ingest_product(
                    raw_document=raw_document,
                    row=row,
                )
                self._merge_result(result, one)
            except Exception as exc:
                result["failed"] += 1
                result["errors"].append(
                    {
                        "product_index": index,
                        "source_product_id": row["product"].get("product_id"),
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    }
                )

        return result

    def _run_cnv_category(
        self,
        *,
        raw_document: RawDocument,
        payload: dict,
    ) -> dict:
        rows = self._extract_cnv_rows(payload)
        result = self._empty_result(raw_document.id)

        result["entity_type"] = "CNV_CATEGORY"
        result["product_occurrences"] = len(rows)
        result["unique_products"] = len(
            {
                base_cleaning(row["product"].get("product_id"))
                for row in rows
                if base_cleaning(row["product"].get("product_id"))
            }
        )

        for index, row in enumerate(rows, start=1):
            result["products"] += 1
            try:
                one = self._ingest_cnv_product(
                    raw_document=raw_document,
                    row=row,
                )
                self._merge_result(result, one)
            except Exception as exc:
                result["failed"] += 1
                result["errors"].append(
                    {
                        "product_index": index,
                        "source_product_id": row["product"].get("product_id"),
                        "tag_attribute": row["context"].get("tag_attribute"),
                        "tag_name": row["context"].get("tag_name"),
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    }
                )

        return result

    @transaction.atomic
    def _ingest_product(
        self,
        *,
        raw_document: RawDocument,
        row: dict,
    ) -> dict:
        product_data = self._dict(row.get("product"))
        context = self._dict(row.get("context"))
        observed_at = raw_document.collected_at or timezone.now()
        brand_source, brand_created = self._save_brand_source(
            raw_document=raw_document,
            product_data=product_data,
            observed_at=observed_at,
        )
        category_source, category_created = self._save_category_source(
            raw_document=raw_document,
            context=context,
            observed_at=observed_at,
        )
        product_source, product_created = self._save_product_source(
            raw_document=raw_document,
            product_data=product_data,
            context=context,
            brand_source=brand_source,
            category_source=category_source,
            observed_at=observed_at,
        )
        snapshot, snapshot_created = self._save_snapshot(
            product_source=product_source,
            product_data=product_data,
            context=context,
            observed_at=observed_at,
        )
        return {
            "brand_created": int(brand_source is not None and brand_created),
            "brand_updated": int(brand_source is not None and not brand_created),
            "brand_missing": int(brand_source is None),
            "category_created": int(category_source is not None and category_created),
            "category_updated": int(category_source is not None and not category_created),
            "category_missing": int(category_source is None),
            "product_created": int(product_created),
            "product_updated": int(not product_created),
            "snapshot_created": int(snapshot_created),
            "snapshot_unchanged": int(not snapshot_created),
            "product_source_id": product_source.id,
            "snapshot_id": snapshot.id if snapshot else None,
        }
    @transaction.atomic
    def _ingest_cnv_product(
        self,
        *,
        raw_document: RawDocument,
        row: dict,
    ) -> dict:
        product_data = self._dict(row.get("product"))
        context = self._dict(row.get("context"))
        observed_at = raw_document.collected_at or timezone.now()

        brand_source, brand_created = self._save_brand_source(
            raw_document=raw_document,
            product_data=product_data,
            observed_at=observed_at,
        )

        product_source, product_created = self._save_cnv_product_source(
            raw_document=raw_document,
            product_data=product_data,
            context=context,
            brand_source=brand_source,
            observed_at=observed_at,
        )

        snapshot, snapshot_created = self._save_cnv_snapshot(
            product_source=product_source,
            product_data=product_data,
            context=context,
            observed_at=observed_at,
        )

        return {
            "brand_created": int(brand_source is not None and brand_created),
            "brand_updated": int(brand_source is not None and not brand_created),
            "brand_missing": int(brand_source is None),
            "category_created": 0,
            "category_updated": 0,
            "category_missing": 0,
            "product_created": int(product_created),
            "product_updated": int(not product_created),
            "snapshot_created": int(snapshot_created),
            "snapshot_unchanged": int(not snapshot_created),
            "product_source_id": product_source.id,
            "snapshot_id": snapshot.id if snapshot else None,
        }

    def _validate_raw_document(self, raw_document: RawDocument) -> None:
        source_code = (raw_document.source.code or "").strip().lower()
        if source_code != self.SOURCE_CODE:
            raise ValueError(
                "ZIGZAG RawDocument가 아닙니다. "
                f"source={source_code}"
            )
    @staticmethod
    def _extract_ranking_rows(payload: dict) -> list[dict]:
        groups = payload.get("groups")
        if not isinstance(groups, dict):
            return []
        blocks = groups.get("detail_category")
        if not isinstance(blocks, list):
            return []
        rows: list[dict] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            context = {
                "category_id": block.get("category_id"),
                "category_name": block.get("category_name"),
                "parent_category_id": block.get("parent_category_id"),
                "parent_category_name": block.get("parent_category_name"),
                "group_name": block.get("group_name"),
                "ranking_mode": block.get("ranking_mode") or "DETAIL_CATEGORY",
                "tag_group": block.get("tag_group"),
                "tag_attribute": block.get("tag_attribute"),
                "tag_name": block.get("tag_name"),
                "order": block.get("order"),
            }
            products = block.get("products")
            if not isinstance(products, list):
                continue
            for product in products:
                if isinstance(product, dict):
                    rows.append(
                        {
                            "product": product,
                            "context": context,
                        }
                    )
        return rows
    
    @staticmethod
    def _extract_cnv_rows(payload: dict) -> list[dict]:
        groups = payload.get("groups")
        if not isinstance(groups, dict):
            return []

        cnv = payload.get("cnv")
        cnv = cnv if isinstance(cnv, dict) else {}

        rows: list[dict] = []

        for group_key in ("trend", "style"):
            blocks = groups.get(group_key)
            if not isinstance(blocks, list):
                continue

            for block in blocks:
                if not isinstance(block, dict):
                    continue

                tag_attribute = (
                    base_cleaning(block.get("tag_attribute"))
                    or group_key
                ).lower()

                if tag_attribute == "styles":
                    tag_attribute = "style"

                if tag_attribute not in {"trend", "style"}:
                    continue

                context = {
                    "category_id": block.get("category_id") or cnv.get("category_id"),
                    "tag_group": block.get("tag_group"),
                    "tag_attribute": tag_attribute,
                    "tag_name": block.get("tag_name"),
                    "order": block.get("order") or cnv.get("order"),
                }

                products = block.get("products")
                if not isinstance(products, list):
                    continue

                for product in products:
                    if isinstance(product, dict):
                        rows.append(
                            {
                                "product": product,
                                "context": context,
                            }
                        )

        return rows

    def _save_brand_source(
        self,
        *,
        raw_document: RawDocument,
        product_data: dict,
        observed_at: datetime,
    ) -> tuple[BrandSource | None, bool]:
        source_brand_id = base_cleaning(product_data.get("shop_id"))
        if not source_brand_id:
            return None, False
        name = base_cleaning(product_data.get("shop_name"))
        brand_source, created = (
            BrandSource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_brand_id=source_brand_id,
                defaults={
                    "brand": None,
                    "name": name,
                    "mapping_status": BrandSource.MappingStatus.UNMAPPED,
                    "first_seen_at": observed_at,
                    "last_seen_at": observed_at,
                    "detected_count": 1,
                },
            )
        )
        if created:
            return brand_source, True
        update_fields: list[str] = []
        if name is not None and brand_source.name != name:
            brand_source.name = name
            update_fields.append("name")
        if brand_source.last_seen_at is None or observed_at > brand_source.last_seen_at:
            brand_source.last_seen_at = observed_at
            update_fields.append("last_seen_at")
        if update_fields:
            update_fields.append("updated_at")
            brand_source.save(update_fields=update_fields)
        return brand_source, False
    def _save_category_source(
        self,
        *,
        raw_document: RawDocument,
        context: dict,
        observed_at: datetime,
    ) -> tuple[CategorySource | None, bool]:
        source_category_id = base_cleaning(context.get("category_id"))
        if not source_category_id:
            return None, False
        category_name = base_cleaning(context.get("category_name"))
        parent_name = base_cleaning(context.get("parent_category_name"))
        path_parts = [value for value in (parent_name, category_name) if value]
        category_path = " > ".join(path_parts) if path_parts else None
        category_source, created = (
            CategorySource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_category_id=source_category_id,
                defaults={
                    "category": None,
                    "source_category_name": category_name,
                    "source_category_path": category_path,
                    "first_seen_at": observed_at,
                    "last_seen_at": observed_at,
                },
            )
        )
        if created:
            return category_source, True
        update_fields: list[str] = []
        if category_name is not None and category_source.source_category_name != category_name:
            category_source.source_category_name = category_name
            update_fields.append("source_category_name")
        if category_path is not None and category_source.source_category_path != category_path:
            category_source.source_category_path = category_path
            update_fields.append("source_category_path")
        if category_source.last_seen_at is None or observed_at > category_source.last_seen_at:
            category_source.last_seen_at = observed_at
            update_fields.append("last_seen_at")
        if update_fields:
            update_fields.append("updated_at")
            category_source.save(update_fields=update_fields)
        return category_source, False
    def _save_product_source(
        self,
        *,
        raw_document: RawDocument,
        product_data: dict,
        context: dict,
        brand_source: BrandSource | None,
        category_source: CategorySource | None,
        observed_at: datetime,
    ) -> tuple[ProductSource, bool]:
        source_product_id = base_cleaning(product_data.get("product_id"))
        if not source_product_id:
            raise ValueError("ZIGZAG product_id가 없습니다.")
        source_name = base_cleaning(product_data.get("product_name"))
        incoming_tags = self._build_observed_tags(context)
        defaults = {
            "product": None,
            "source_brand": brand_source,
            "source_category": category_source,
            "source_name": source_name,
            "normalized_name": None,
            "thumbnail_url": product_data.get("image_url"),
            "product_url": None,
            "attributes": {"tags": incoming_tags} if incoming_tags else {},
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "detected_count": 1,
        }
        product_source, created = (
            ProductSource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_product_id=source_product_id,
                defaults=defaults,
            )
        )
        if created:
            return product_source, True
        # 태그는 관측 이력이므로 과거 RAW를 재처리해도 누적한다.
        current_attributes = (
            dict(product_source.attributes)
            if isinstance(product_source.attributes, dict)
            else {}
        )
        merged_attributes = self._merge_attributes_tags(
            current_attributes,
            incoming_tags,
        )
        update_fields: list[str] = []
        if merged_attributes != current_attributes:
            product_source.attributes = merged_attributes
            update_fields.append("attributes")
        current_last_seen = product_source.last_seen_at
        # 과거 RAW라면 현재 상품 상태는 되돌리지 않고 태그/first_seen만 보강한다.
        if current_last_seen is not None and observed_at <= current_last_seen:
            if product_source.first_seen_at is None or observed_at < product_source.first_seen_at:
                product_source.first_seen_at = observed_at
                update_fields.append("first_seen_at")
            if update_fields:
                update_fields.append("updated_at")
                product_source.save(update_fields=list(dict.fromkeys(update_fields)))
            return product_source, False
        product_source.source_brand = brand_source
        product_source.source_category = category_source
        product_source.source_name = source_name
        product_source.thumbnail_url = product_data.get("image_url")
        product_source.last_seen_at = observed_at
        update_fields.extend(
            [
                "source_brand",
                "source_category",
                "source_name",
                "thumbnail_url",
                "last_seen_at",
            ]
        )
        update_fields.append("updated_at")
        product_source.save(update_fields=list(dict.fromkeys(update_fields)))
        return product_source, False
    def _save_cnv_product_source(
        self,
        *,
        raw_document: RawDocument,
        product_data: dict,
        context: dict,
        brand_source: BrandSource | None,
        observed_at: datetime,
    ) -> tuple[ProductSource, bool]:
        source_product_id = base_cleaning(product_data.get("product_id"))
        if not source_product_id:
            raise ValueError("ZIGZAG CNV product_id가 없습니다.")

        source_name = base_cleaning(product_data.get("product_name"))
        incoming_tags = self._build_cnv_tags(context)

        defaults = {
            "product": None,
            "source_brand": brand_source,
            "source_category": None,
            "source_name": source_name,
            "normalized_name": None,
            "thumbnail_url": product_data.get("image_url"),
            "product_url": None,
            "attributes": {"tags": incoming_tags} if incoming_tags else {},
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "detected_count": 1,
        }

        product_source, created = (
            ProductSource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_product_id=source_product_id,
                defaults=defaults,
            )
        )

        if created:
            return product_source, True

        current_attributes = (
            dict(product_source.attributes)
            if isinstance(product_source.attributes, dict)
            else {}
        )
        merged_attributes = self._merge_attributes_tags(
            current_attributes,
            incoming_tags,
        )

        update_fields: list[str] = []

        if merged_attributes != current_attributes:
            product_source.attributes = merged_attributes
            update_fields.append("attributes")

        current_last_seen = product_source.last_seen_at

        # CNV에는 상품별 세부 카테고리가 없으므로
        # 기존 source_category를 절대 덮어쓰지 않는다.
        if current_last_seen is not None and observed_at <= current_last_seen:
            if (
                product_source.first_seen_at is None
                or observed_at < product_source.first_seen_at
            ):
                product_source.first_seen_at = observed_at
                update_fields.append("first_seen_at")

            if update_fields:
                update_fields.append("updated_at")
                product_source.save(
                    update_fields=list(dict.fromkeys(update_fields))
                )

            return product_source, False

        product_source.source_brand = brand_source
        product_source.source_name = source_name
        product_source.thumbnail_url = product_data.get("image_url")
        product_source.last_seen_at = observed_at

        update_fields.extend(
            [
                "source_brand",
                "source_name",
                "thumbnail_url",
                "last_seen_at",
            ]
        )

        update_fields.append("updated_at")
        product_source.save(
            update_fields=list(dict.fromkeys(update_fields))
        )

        return product_source, False

    def _save_snapshot(
        self,
        *,
        product_source: ProductSource,
        product_data: dict,
        context: dict,
        observed_at: datetime,
    ) -> tuple[ProductSourceSnapshot, bool]:
        category_id = base_cleaning(context.get("category_id"))
        if not category_id:
            raise ValueError("ZIGZAG ranking category_id가 없습니다.")
        ranking_scope = f"ZIGZAG:DETAIL_CATEGORY:{category_id}"
        ranking_context = {
            "ranking_mode": "DETAIL_CATEGORY",
            "category_id": category_id,
            "category_name": base_cleaning(context.get("category_name")),
            "parent_category_id": base_cleaning(context.get("parent_category_id")),
            "parent_category_name": base_cleaning(context.get("parent_category_name")),
            "group_name": base_cleaning(context.get("group_name")),
            "order": base_cleaning(context.get("order")),
        }
        ranking_context = {
            key: value
            for key, value in ranking_context.items()
            if value is not None
        }
        values = {
            "list_price": self._to_decimal(product_data.get("max_price")),
            "sale_price": self._to_decimal(product_data.get("final_price")),
            "discount_rate": self._to_decimal(product_data.get("discount_rate")),
            "rank_position": self._to_int(product_data.get("rank")),
            "ranking_context": ranking_context,
            "rating": self._to_decimal(product_data.get("review_score")),
            "review_count": self._to_int(product_data.get("review_count")),
            "like_count": None,
            "view_count": None,
            "sales_count": None,
            "stock_status": base_cleaning(product_data.get("sales_status")),
            "platform_metrics": {},
        }
        snapshot_date = observed_at.astimezone(KST).date()
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
                **values,
            )
            return snapshot, True
        if snapshot.observed_at >= observed_at:
            return snapshot, False
        for key, value in values.items():
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
    def _save_cnv_snapshot(
        self,
        *,
        product_source: ProductSource,
        product_data: dict,
        context: dict,
        observed_at: datetime,
    ) -> tuple[ProductSourceSnapshot, bool]:
        tag_attribute = base_cleaning(context.get("tag_attribute"))
        tag_name = base_cleaning(context.get("tag_name"))

        if not tag_attribute or tag_attribute.lower() not in {"trend", "style"}:
            raise ValueError(
                "ZIGZAG CNV tag_attribute가 올바르지 않습니다. "
                f"tag_attribute={tag_attribute}"
            )

        if not tag_name:
            raise ValueError("ZIGZAG CNV tag_name이 없습니다.")

        tag_attribute = tag_attribute.lower()
        ranking_scope = f"ZIGZAG:CNV:{tag_attribute.upper()}:{tag_name}"

        ranking_context = {
            "ranking_mode": "CNV_CATEGORY",
            "category_id": base_cleaning(context.get("category_id")),
            "tag_group": base_cleaning(context.get("tag_group")),
            "tag_attribute": tag_attribute,
            "tag_name": tag_name,
            "order": base_cleaning(context.get("order")),
        }
        ranking_context = {
            key: value
            for key, value in ranking_context.items()
            if value is not None
        }

        values = {
            "list_price": self._to_decimal(product_data.get("max_price")),
            "sale_price": self._to_decimal(product_data.get("final_price")),
            "discount_rate": self._to_decimal(product_data.get("discount_rate")),
            "rank_position": self._to_int(product_data.get("rank")),
            "ranking_context": ranking_context,
            "rating": self._to_decimal(product_data.get("review_score")),
            "review_count": self._to_int(product_data.get("review_count")),
            "like_count": None,
            "view_count": None,
            "sales_count": None,
            "stock_status": base_cleaning(product_data.get("sales_status")),
            "platform_metrics": {},
        }

        snapshot_date = observed_at.astimezone(KST).date()
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
                **values,
            )
            return snapshot, True

        if snapshot.observed_at >= observed_at:
            return snapshot, False

        for key, value in values.items():
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

    @classmethod
    def _build_cnv_tags(cls, context: dict) -> dict:
        tag_attribute = base_cleaning(context.get("tag_attribute"))
        tag_name = base_cleaning(context.get("tag_name"))

        if not tag_attribute or not tag_name:
            return {}

        tag_attribute = tag_attribute.lower()
        if tag_attribute not in {"trend", "style"}:
            return {}

        return {
            tag_attribute: [
                {
                    "id": None,
                    "name": tag_name,
                }
            ]
        }

    @classmethod
    def _build_observed_tags(cls, context: dict) -> dict:
        tags: dict[str, list[dict[str, str | None]]] = {}
        category_rows: list[dict[str, str | None]] = []
        for source_id, name in (
            (context.get("parent_category_id"), context.get("parent_category_name")),
            (context.get("category_id"), context.get("category_name")),
        ):
            clean_id = base_cleaning(source_id)
            clean_name = base_cleaning(name)
            if not clean_id and not clean_name:
                continue
            row = {"id": clean_id, "name": clean_name}
            if row not in category_rows:
                category_rows.append(row)
        if category_rows:
            tags["category"] = category_rows
        return tags
    @classmethod
    def _merge_attributes_tags(
        cls,
        current_attributes: dict,
        incoming_tags: dict,
    ) -> dict:
        merged = dict(current_attributes)
        current_tags = merged.get("tags")
        current_tags = dict(current_tags) if isinstance(current_tags, dict) else {}
        for tag_type, incoming_values in incoming_tags.items():
            existing_values = current_tags.get(tag_type)
            existing_values = list(existing_values) if isinstance(existing_values, list) else []
            seen: set[tuple[str | None, str | None]] = set()
            combined: list[dict[str, str | None]] = []
            for value in [*existing_values, *incoming_values]:
                if not isinstance(value, dict):
                    continue
                row = {
                    "id": base_cleaning(value.get("id")),
                    "name": base_cleaning(value.get("name")),
                }
                key = (row["id"], row["name"])
                if key == (None, None) or key in seen:
                    continue
                seen.add(key)
                combined.append(row)
            if combined:
                current_tags[tag_type] = combined
        if current_tags:
            merged["tags"] = current_tags
        return merged
    @staticmethod
    def _empty_result(raw_document_id: int) -> dict:
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
        
    @staticmethod
    def _merge_result(
        result: dict,
        one: dict,
    ) -> None:
        # --------------------------------------------------------
        # Count merge
        # --------------------------------------------------------

        for key in (
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
        ):
            result[key] += (
                one.get(key, 0)
                or 0
            )

        # --------------------------------------------------------
        # ProductSource ID merge
        # --------------------------------------------------------

        product_source_id = one.get(
            "product_source_id"
        )

        if product_source_id is None:
            return

        product_source_id = int(
            product_source_id
        )

        product_source_ids = result.setdefault(
            "product_source_ids",
            [],
        )

        if (
            product_source_id
            not in product_source_ids
        ):
            product_source_ids.append(
                product_source_id
            )
            
    @staticmethod
    def _dict(value: Any) -> dict:
        return value if isinstance(value, dict) else {}
    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in (None, "") or isinstance(value, bool):
            return None
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None
    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value in (None, "") or isinstance(value, bool):
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
def ingest_zigzag_raw_document(raw_document_id: int) -> dict:
    return ZigzagIngestion().run(raw_document_id)
