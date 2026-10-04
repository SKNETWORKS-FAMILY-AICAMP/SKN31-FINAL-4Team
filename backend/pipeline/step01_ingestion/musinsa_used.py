from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    BrandSource,
    CategorySource,
    ProductSource,
    ProductSourceRelation,
    ProductSourceSnapshot,
    RawDocument,
    ResaleSnapshot,
    Source,
)

from .common import base_cleaning, extract_payload, get_s3_client, load_raw_json


KST = ZoneInfo("Asia/Seoul")


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("%", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _model_fields(model) -> set[str]:
    return {field.name for field in model._meta.fields}


def _filtered_values(model, values: dict) -> dict:
    fields = _model_fields(model)
    return {key: value for key, value in values.items() if key in fields}


def _clean_list(values: Any) -> list:
    if values in (None, ""):
        return []
    if not isinstance(values, list):
        values = [values]

    result = []
    seen = set()
    for value in values:
        if value in (None, ""):
            continue
        cleaned = base_cleaning(value) if isinstance(value, str) else value
        if cleaned in (None, ""):
            continue
        marker = str(cleaned)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(cleaned)
    return result


def _merge_attribute_maps(current: Any, incoming: Any) -> dict:
    result: dict[str, list] = {}

    for source in (_dict(current), _dict(incoming)):
        for key, value in source.items():
            clean_key = base_cleaning(key) if isinstance(key, str) else str(key)
            if not clean_key:
                continue
            merged = _clean_list([*result.get(clean_key, []), *_clean_list(value)])
            if merged:
                result[clean_key] = merged

    return result

def _build_clean_attributes(
    *,
    attr_data: dict,
    filter_context: dict | None = None,
) -> dict:
    """
    ProductSource.attributes 전용 정제.

    저장 형태:
    {
        "tags": [],
        "options": {},
        "attributes": {
            "패턴/무늬": ["단색"],
            "주요소재": ["데님"],
        }
    }

    FILTER RAW는 payload.ranking에 한 번만 저장하고,
    STEP01에서 해당 observation의 USED 상품들에 attribute로 반영한다.
    """

    attr_data = _dict(attr_data)
    filter_context = _dict(filter_context)

    tags = []
    options = {}
    attributes = {}

    # ---------------------------------------------------------
    # 1. 기존 tags
    # ---------------------------------------------------------
    raw_tags = attr_data.get("tags")

    if isinstance(raw_tags, list):
        for value in raw_tags:
            value = base_cleaning(value)

            if value and value not in tags:
                tags.append(value)

    # ---------------------------------------------------------
    # 2. 기존 options
    # ---------------------------------------------------------
    raw_options = attr_data.get("options")

    if isinstance(raw_options, dict):
        for key, values in raw_options.items():
            clean_key = base_cleaning(key)

            if not clean_key:
                continue

            if not isinstance(values, list):
                values = [values]

            cleaned = []

            for value in values:
                value = base_cleaning(value)

                if value and value not in cleaned:
                    cleaned.append(value)

            if cleaned:
                options[clean_key] = cleaned

    # ---------------------------------------------------------
    # 3. 기존 source attributes
    # ---------------------------------------------------------
    raw_attributes = (
        attr_data.get("attributes")
        or attr_data.get("source_attributes")
        or {}
    )

    if isinstance(raw_attributes, dict):
        for key, values in raw_attributes.items():
            clean_key = base_cleaning(key)

            if not clean_key:
                continue

            if not isinstance(values, list):
                values = [values]

            cleaned = []

            for value in values:
                value = base_cleaning(value)

                if value and value not in cleaned:
                    cleaned.append(value)

            if cleaned:
                attributes[clean_key] = cleaned

    # ---------------------------------------------------------
    # 4. FILTER observation -> attribute
    # ---------------------------------------------------------
    observation_type = str(
        filter_context.get("observation_type") or ""
    ).upper()

    if observation_type == "FILTER":
        filter_key = base_cleaning(
            filter_context.get("filter_label")
            or filter_context.get("filter_type")
        )

        filter_value = base_cleaning(
            filter_context.get("filter_name")
        )

        if filter_key and filter_value:
            attributes.setdefault(filter_key, [])

            if filter_value not in attributes[filter_key]:
                attributes[filter_key].append(filter_value)

    return {
        "tags": tags,
        "options": options,
        "attributes": attributes,
    }

def _merge_clean_product_attributes(current: Any, incoming: Any) -> dict:
    current = _dict(current)
    incoming = _dict(incoming)

    current_options = _dict(current.get("options"))
    incoming_options = _dict(incoming.get("options"))

    merged_options: dict[str, list] = {}
    for key in set(current_options) | set(incoming_options):
        values = _clean_list([
            *_clean_list(current_options.get(key)),
            *_clean_list(incoming_options.get(key)),
        ])
        if values:
            merged_options[key] = values

    return {
        "tags": _clean_list([
            *_clean_list(current.get("tags")),
            *_clean_list(incoming.get("tags")),
        ]),
        "options": merged_options,
        "attributes": _merge_attribute_maps(
            current.get("attributes"),
            incoming.get("attributes"),
        ),
    }


def _daily_upsert(model, lookup: dict, values: dict, observed_at: datetime) -> str:
    values = _filtered_values(model, values)

    obj = (
        model.objects
        .select_for_update()
        .filter(**lookup)
        .first()
    )

    if obj is None:
        model.objects.create(
            **lookup,
            observed_at=observed_at,
            **values,
        )
        return "created"

    if obj.observed_at is not None and obj.observed_at >= observed_at:
        return "unchanged"

    for key, value in values.items():
        setattr(obj, key, value)

    obj.observed_at = observed_at
    update_fields = ["observed_at", *values.keys()]
    obj.save(update_fields=list(dict.fromkeys(update_fields)))
    return "updated"


class MusinsaUsedIngestion:
    SOURCE_CODE = "musinsa_used"

    def __init__(self):
        self.s3 = get_s3_client()

    def run(self, raw_document_id: int) -> dict[str, Any]:
        raw_document = (
            RawDocument.objects
            .select_related("source", "crawl_run")
            .get(pk=raw_document_id)
        )

        source_code = (raw_document.source.code or "").strip().lower()
        if source_code != self.SOURCE_CODE:
            raise ValueError(
                "MUSINSA_USED RawDocument가 아닙니다. "
                f"source={source_code}"
            )

        raw_data = load_raw_json(raw_document, s3_client=self.s3)
        payload = extract_payload(raw_data)
        ranking_context = _dict(
            payload.get("ranking")
        )

        direct_products = [
            row for row in _list(payload.get("products"))
            if isinstance(row, dict)
        ]

        related = _dict(payload.get("related_products"))
        related_used_products = [
            row for row in _list(related.get("musinsa_used"))
            if isinstance(row, dict)
        ]

        products = [*direct_products, *related_used_products]

        stats = {
            "raw_document_id": raw_document.id,
            "direct_products": len(direct_products),
            "related_used_products": len(related_used_products),
            "products": 0,
            "brand_created": 0,
            "brand_updated": 0,
            "brand_missing": 0,
            "category_created": 0,
            "category_updated": 0,
            "category_missing": 0,
            "product_created": 0,
            "product_updated": 0,
            "product_snapshot_created": 0,
            "product_snapshot_updated": 0,
            "product_snapshot_unchanged": 0,
            "resale_snapshot_created": 0,
            "resale_snapshot_updated": 0,
            "resale_snapshot_unchanged": 0,
            "failed": 0,
            "errors": [],
            "relations_in_raw": len(_list(payload.get("relations"))),
            "original_musinsa_products_in_raw": len(
                _list(related.get("musinsa"))
            ),
        }

        for index, parsed in enumerate(products, start=1):
            try:
                one = self._ingest_one(
                    raw_document=raw_document,
                    parsed=parsed,
                )
                stats["products"] += 1
                for key, value in one.items():
                    if key in stats and isinstance(value, int):
                        stats[key] += value
            except Exception as exc:
                stats["failed"] += 1
                stats["errors"].append({
                    "product_index": index,
                    "goods_no": _dict(parsed.get("product")).get("goods_no"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                })

        # 상품을 먼저 적재해야 관계의 양 끝(유즈드 매물 · 무신사 원상품)을 찾을 수 있다.
        try:
            relation_stats = persist_product_source_relations(
                _list(payload.get("relations"))
            )
        except Exception as exc:
            relation_stats = {"created": 0, "existing": 0, "skipped": 0}
            stats["errors"].append({
                "stage": "relations",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            })
        stats["relation_created"] = relation_stats["created"]
        stats["relation_existing"] = relation_stats["existing"]
        stats["relation_skipped"] = relation_stats["skipped"]

        return stats

    @transaction.atomic
    def _ingest_one(
        self,
        *,
        raw_document: RawDocument,
        parsed: dict,
    ) -> dict[str, int]:
        observed_at = raw_document.collected_at or timezone.now()
        product_data = _dict(parsed.get("product"))
        brand_data = _dict(parsed.get("brand"))
        attr_data = _dict(parsed.get("attributes"))
        snapshot_data = _dict(parsed.get("snapshot"))
        ranking_context = _dict(parsed.get("ranking_context"))
        price_history = _dict(parsed.get("used_price_history"))

        goods_no = product_data.get("goods_no")
        if goods_no in (None, ""):
            raise ValueError("MUSINSA_USED goods_no가 없습니다.")
        source_product_id = str(goods_no)

        brand_source, brand_created = self._save_brand(
            raw_document=raw_document,
            brand_data=brand_data,
            observed_at=observed_at,
        )

        category_source, category_created = self._save_category(
            raw_document=raw_document,
            product_data=product_data,
            ranking_context=ranking_context,
            observed_at=observed_at,
        )

        product_source, product_created = self._save_product(
            raw_document=raw_document,
            source_product_id=source_product_id,
            product_data=product_data,
            attr_data=attr_data,
            ranking_context=ranking_context,
            brand_source=brand_source,
            category_source=category_source,
            observed_at=observed_at,
        )

        product_snapshot_state = self._save_product_snapshot(
            product_source=product_source,
            snapshot_data=snapshot_data,
            ranking_context=ranking_context,
            observed_at=observed_at,
        )

        resale_snapshot_state = self._save_resale_snapshot(
            product_source=product_source,
            snapshot_data=snapshot_data,
            price_history=price_history,
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
            f"product_snapshot_{product_snapshot_state}": 1,
            f"resale_snapshot_{resale_snapshot_state}": 1,
        }

    def _save_brand(
        self,
        *,
        raw_document: RawDocument,
        brand_data: dict,
        observed_at: datetime,
    ) -> tuple[BrandSource | None, bool]:
        source_brand_id = base_cleaning(
            brand_data.get("brand_code") or brand_data.get("brand_id")
        )
        if not source_brand_id:
            return None, False

        name = base_cleaning(
            brand_data.get("name_ko")
            or brand_data.get("brand_name")
            or brand_data.get("name_en")
        )
        english_name = base_cleaning(brand_data.get("name_en"))

        defaults = _filtered_values(BrandSource, {
            "brand": None,
            "name": name,
            "english_name": english_name,
            "mapping_status": BrandSource.MappingStatus.UNMAPPED,
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "detected_count": 1,
        })

        obj, created = (
            BrandSource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_brand_id=source_brand_id,
                defaults=defaults,
            )
        )
        if created:
            return obj, True

        update_fields = []
        if name is not None and getattr(obj, "name", None) != name:
            obj.name = name
            update_fields.append("name")
        if english_name is not None and getattr(obj, "english_name", None) != english_name:
            obj.english_name = english_name
            update_fields.append("english_name")
        if "last_seen_at" in _model_fields(BrandSource):
            current = getattr(obj, "last_seen_at", None)
            if current is None or observed_at > current:
                obj.last_seen_at = observed_at
                update_fields.append("last_seen_at")
        if update_fields:
            if "updated_at" in _model_fields(BrandSource):
                update_fields.append("updated_at")
            obj.save(update_fields=list(dict.fromkeys(update_fields)))
        return obj, False

    def _save_category(
        self,
        *,
        raw_document: RawDocument,
        product_data: dict,
        ranking_context: dict,
        observed_at: datetime,
    ) -> tuple[CategorySource | None, bool]:
        category = _dict(product_data.get("category"))

        candidates: list[tuple[str, str | None]] = []
        for depth in range(1, 6):
            code = base_cleaning(category.get(f"depth{depth}_code"))
            name = base_cleaning(category.get(f"depth{depth}_name"))
            if code:
                candidates.append((code, name))

        if candidates:
            source_category_id, source_category_name = candidates[-1]
            path = " > ".join(name for _, name in candidates if name) or None
        elif str(ranking_context.get("observation_type") or "").upper() == "FILTER":
            # FILTER 직접 결과에 한해서 타깃 카테고리를 evidence fallback으로 사용한다.
            source_category_id = base_cleaning(ranking_context.get("category_id"))
            source_category_name = base_cleaning(ranking_context.get("category_name"))
            path = source_category_name
        else:
            return None, False

        if not source_category_id:
            return None, False

        defaults = _filtered_values(CategorySource, {
            "category": None,
            "source_category_name": source_category_name,
            "source_category_path": path,
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
        })

        obj, created = (
            CategorySource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_category_id=source_category_id,
                defaults=defaults,
            )
        )
        if created:
            return obj, True

        update_fields = []
        for field, value in (
            ("source_category_name", source_category_name),
            ("source_category_path", path),
        ):
            if value is not None and getattr(obj, field, None) != value:
                setattr(obj, field, value)
                update_fields.append(field)
        if "last_seen_at" in _model_fields(CategorySource):
            current = getattr(obj, "last_seen_at", None)
            if current is None or observed_at > current:
                obj.last_seen_at = observed_at
                update_fields.append("last_seen_at")
        if update_fields:
            if "updated_at" in _model_fields(CategorySource):
                update_fields.append("updated_at")
            obj.save(update_fields=list(dict.fromkeys(update_fields)))
        return obj, False

    def _save_product(
        self,
        *,
        raw_document: RawDocument,
        source_product_id: str,
        product_data: dict,
        attr_data: dict,
        ranking_context: dict,
        brand_source: BrandSource | None,
        category_source: CategorySource | None,
        observed_at: datetime,
    ) -> tuple[ProductSource, bool]:
        attributes = _build_clean_attributes(
            attr_data=attr_data,
            filter_context=ranking_context,
        )

        product_url = (
            ranking_context.get("product_url")
            or f"https://www.musinsa.com/products/{source_product_id}"
        )

        genders = [
            str(value) for value in _list(product_data.get("genders"))
            if value not in (None, "")
        ]

        defaults = _filtered_values(ProductSource, {
            "product": None,
            "source_brand": brand_source,
            "source_category": category_source,
            "style_no": base_cleaning(product_data.get("style_no")),
            "source_name": base_cleaning(product_data.get("name")),
            "source_name_en": base_cleaning(product_data.get("name_en")),
            "normalized_name": None,
            "thumbnail_url": product_data.get("thumbnail_url"),
            "product_url": product_url,
            "gender_scope": ",".join(genders) if genders else None,
            "source_genders": genders,
            "attributes": attributes,
            "market_type": "RESALE",
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "detected_count": 1,
        })

        obj, created = (
            ProductSource.objects
            .select_for_update()
            .get_or_create(
                source=raw_document.source,
                source_product_id=source_product_id,
                defaults=defaults,
            )
        )
        if created:
            return obj, True

        # 같은 USED 상품이 여러 FILTER 타깃에서 발견될 수 있으므로
        # clean attributes는 누적한다. 원본 evidence는 S3 RAW에만 남긴다.
        current_attributes = _dict(getattr(obj, "attributes", None))
        attributes = _merge_clean_product_attributes(
            current_attributes,
            attributes,
        )

        # 과거 RAW 재처리: 최신 상품 상태는 되돌리지 않되,
        # 새로 발견된 정제 attribute 값은 누적할 수 있다.
        current_last_seen = getattr(obj, "last_seen_at", None)
        if current_last_seen is not None and observed_at <= current_last_seen:
            if attributes != current_attributes:
                obj.attributes = attributes
                update_fields = ["attributes"]
                if "updated_at" in _model_fields(ProductSource):
                    update_fields.append("updated_at")
                obj.save(update_fields=update_fields)
            return obj, False

        for field, value in defaults.items():
            if field in {"product", "normalized_name", "first_seen_at", "detected_count"}:
                continue
            if field == "attributes":
                value = attributes
            setattr(obj, field, value)

        if getattr(obj, "first_seen_at", None) is None or observed_at < obj.first_seen_at:
            obj.first_seen_at = observed_at

        update_fields = [
            field for field in defaults
            if field not in {"product", "normalized_name", "first_seen_at", "detected_count"}
        ]
        if "first_seen_at" in _model_fields(ProductSource):
            update_fields.append("first_seen_at")
        if "updated_at" in _model_fields(ProductSource):
            update_fields.append("updated_at")
        obj.save(update_fields=list(dict.fromkeys(update_fields)))
        return obj, False

    def _ranking_scope(self, ranking_context: dict) -> str:
        observation_type = str(
            ranking_context.get("observation_type") or ""
        ).upper()

        if observation_type == "FILTER":
            filter_type = (
                base_cleaning(ranking_context.get("filter_type"))
                or "FILTER"
            )
            filter_name = (
                base_cleaning(ranking_context.get("filter_name"))
                or "UNKNOWN"
            )

            scope = f"USED:F:{filter_type}:{filter_name}"

            # DB ranking_scope가 varchar(50)이므로 방어
            return scope[:50]

        return "USED:DETAIL"

    def _save_product_snapshot(
        self,
        *,
        product_source: ProductSource,
        snapshot_data: dict,
        ranking_context: dict,
        observed_at: datetime,
    ) -> str:
        ranking_scope = self._ranking_scope(ranking_context)
        snapshot_date = observed_at.astimezone(KST).date()

        rank_position = _integer(
            ranking_context.get("rank")
            or ranking_context.get("rank_position")
        )

        context = {
            key: ranking_context.get(key)
            for key in (
                "observation_type",
                "category_id",
                "category_name",
                "filter_type",
                "filter_label",
                "filter_name",
                "filter_parameter",
                "filter_value",
                "gender",
                "sort",
                "sort_code",
            )
            if ranking_context.get(key) not in (None, "")
        }

        values = {
            "list_price": _decimal(snapshot_data.get("regular_price")),
            "sale_price": _decimal(snapshot_data.get("sale_price")),
            "discount_rate": _decimal(snapshot_data.get("discount_rate")),
            "rank_position": rank_position,
            "ranking_context": context,
            "rating": _decimal(snapshot_data.get("satisfaction_score")),
            "review_count": _integer(snapshot_data.get("review_count")),
            "like_count": _integer(snapshot_data.get("like_count")),
            "view_count": _integer(snapshot_data.get("view_count")),
            "sales_count": _integer(snapshot_data.get("purchase_total")),
            "stock_status": (
                "SOLD_OUT" if snapshot_data.get("is_sold_out") is True
                else base_cleaning(snapshot_data.get("availability")) or "AVAILABLE"
            ),
            "platform_metrics": {
                key: value
                for key, value in {
                    "currency": snapshot_data.get("currency") or "KRW",
                    "used_condition_grade": snapshot_data.get("used_condition_grade"),
                    "is_sold_out": snapshot_data.get("is_sold_out"),
                }.items()
                if value not in (None, "")
            },
        }

        return _daily_upsert(
            ProductSourceSnapshot,
            {
                "product_source": product_source,
                "snapshot_date": snapshot_date,
                "ranking_scope": ranking_scope,
            },
            values,
            observed_at,
        )

    def _save_resale_snapshot(
        self,
        *,
        product_source: ProductSource,
        snapshot_data: dict,
        price_history: dict,
        observed_at: datetime,
    ) -> str:
        snapshot_date = observed_at.astimezone(KST).date()
        sale_price = _decimal(snapshot_data.get("sale_price"))
        sold_out = snapshot_data.get("is_sold_out") is True

        history_rows = _list(price_history.get("price_change_histories"))
        history_prices = [
            price
            for row in history_rows
            if isinstance(row, dict)
            if (price := _decimal(
                row.get("price")
                or row.get("sale_price")
                or row.get("changed_price")
            )) is not None
        ]

        values = {
            "listing_count": 1,
            "available_count": 0 if sold_out else 1,
            "sold_count": 1 if sold_out else 0,
            "min_price": sale_price,
            "max_price": sale_price,
            "avg_price": sale_price,
            "median_price": sale_price,
            "lowest_ask": sale_price if not sold_out else None,
            "highest_bid": None,
            "last_trade_price": None,
            "trade_volume": None,
            "resale_price_ratio": None,
            "resale_index": None,
            "market_metrics": {
                "currency": snapshot_data.get("currency") or "KRW",
                "used_condition_grade": snapshot_data.get("used_condition_grade"),
                "is_sold_out": snapshot_data.get("is_sold_out"),
                "price_anchor_type": price_history.get("price_anchor_type"),
                "first_sale_start": price_history.get("first_sale_start"),
                "discount_scheduled_at": price_history.get("discount_scheduled_at"),
                "price_history_count": len(history_rows),
                "price_history_min": float(min(history_prices)) if history_prices else None,
                "price_history_max": float(max(history_prices)) if history_prices else None,
                "price_history_median": float(median(history_prices)) if history_prices else None,
            },
        }

        return _daily_upsert(
            ResaleSnapshot,
            {
                "product_source": product_source,
                "snapshot_date": snapshot_date,
            },
            values,
            observed_at,
        )


def _source_code_key(value: Any) -> str:
    # Source.code 는 'musinsa_used' · 'musinsa-used' · 'MUSINSA' 처럼 표기가 섞여 있다.
    return str(value or "").strip().lower().replace("-", "_")


@transaction.atomic
def persist_product_source_relations(relations: list[dict]) -> dict:
    """RAW 의 relations(유즈드 매물 → 무신사 원상품)를 ProductSourceRelation 에 적재한다.

    표준 상품(Product) 매핑과는 별개로, 플랫폼 상품끼리의 근거 관계만 남긴다.
    양 끝 ProductSource 가 아직 적재되지 않았으면 건너뛴다 — 무신사 원상품은
    무신사 수집이 따로 적재하므로, 다음 RAW 재처리 때 다시 연결된다.
    이미 있는 관계는 그대로 두므로 같은 RAW 를 여러 번 돌려도 된다.
    """
    valid_types = set(ProductSourceRelation.RelationType.values)
    skipped: list[dict] = []
    normalized = []
    lookup_keys: set[tuple[str, str]] = set()

    for relation in relations or []:
        if not isinstance(relation, dict):
            skipped.append({"relation": relation, "skip_reason": "INVALID_RELATION"})
            continue
        relation_type = (
            relation.get("relation_type")
            or ProductSourceRelation.RelationType.RESALE_OF
        )
        if relation_type not in valid_types:
            skipped.append({**relation, "skip_reason": "INVALID_RELATION_TYPE"})
            continue
        from_key = (
            _source_code_key(relation.get("from_source")),
            str(relation.get("from_source_product_id") or "").strip(),
        )
        to_key = (
            _source_code_key(relation.get("to_source")),
            str(relation.get("to_source_product_id") or "").strip(),
        )
        if not all((*from_key, *to_key)) or from_key == to_key:
            skipped.append({**relation, "skip_reason": "MISSING_SOURCE_KEY"})
            continue
        normalized.append((relation, from_key, to_key, relation_type))
        lookup_keys.update((from_key, to_key))

    if not normalized:
        return {"created": 0, "existing": 0, "skipped": len(skipped),
                "skipped_relations": skipped}

    source_codes = {code for code, _ in lookup_keys}
    source_ids = {
        source.pk: _source_code_key(source.code)
        for source in Source.objects.all()
        if _source_code_key(source.code) in source_codes
    }
    product_sources = (
        ProductSource.objects
        .filter(
            source_id__in=source_ids.keys(),
            source_product_id__in={pid for _, pid in lookup_keys},
        )
        .only("id", "source_id", "source_product_id")
    )
    by_key = {
        (source_ids[ps.source_id], str(ps.source_product_id)): ps.pk
        for ps in product_sources
    }

    requested: dict[tuple[int, int, str], dict] = {}
    for relation, from_key, to_key, relation_type in normalized:
        from_id = by_key.get(from_key)
        to_id = by_key.get(to_key)
        if from_id is None or to_id is None:
            skipped.append({**relation, "skip_reason": "PRODUCT_SOURCE_NOT_FOUND"})
            continue
        requested.setdefault((from_id, to_id, relation_type), relation)

    involved_ids = {pk for from_id, to_id, _ in requested for pk in (from_id, to_id)}
    existing = set(
        ProductSourceRelation.objects
        .filter(
            from_product_source_id__in=involved_ids,
            to_product_source_id__in=involved_ids,
        )
        .values_list("from_product_source_id", "to_product_source_id", "relation_type")
    ) if involved_ids else set()

    missing = [key for key in requested if key not in existing]
    ProductSourceRelation.objects.bulk_create(
        [
            ProductSourceRelation(
                from_product_source_id=from_id,
                to_product_source_id=to_id,
                relation_type=relation_type,
                evidence_source=(
                    requested[(from_id, to_id, relation_type)].get("evidence_source")
                    or "MUSINSA_RELATED_GOODS"
                )[:100],
            )
            for from_id, to_id, relation_type in missing
        ],
        batch_size=1000,
        ignore_conflicts=True,
    )

    return {
        "created": len(missing),
        "existing": len(requested) - len(missing),
        "skipped": len(skipped),
        "skipped_relations": skipped,
    }
