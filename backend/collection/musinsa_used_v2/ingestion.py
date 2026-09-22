from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

import boto3

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import (
    BrandSource,
    CategorySource,
    ProductSource,
    ProductSourceRelation,
    RawDocument,
    ResaleSnapshot,
    Source,
)


SOURCE_CODE = "MUSINSA_USED"


def _field_names(model) -> set[str]:
    return {
        field.name
        for field
        in model._meta.fields
    }


def _first(
    data: dict,
    *keys: str,
):
    for key in keys:
        value = data.get(key)
        if value not in (
            None,
            "",
        ):
            return value
    return None


def _text(value) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    return (
        value
        if value
        else None
    )


def _decimal(value):
    if value in (
        None,
        "",
    ):
        return None

    try:
        return Decimal(
            str(value)
            .replace(
                ",",
                "",
            )
        )
    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return None


def _int(value):
    if value in (
        None,
        "",
    ):
        return None

    try:
        return int(
            float(value)
        )
    except (
        ValueError,
        TypeError,
    ):
        return None


def _json_safe(value):
    if isinstance(
        value,
        Decimal,
    ):
        return float(value)

    if isinstance(
        value,
        dict,
    ):
        return {
            key:
                _json_safe(item)
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    return value


def _extract_payload(
    raw_data: dict,
) -> dict:
    payload = raw_data.get(
        "payload"
    )

    if isinstance(
        payload,
        dict,
    ):
        return payload

    data = raw_data.get(
        "data"
    )

    if isinstance(
        data,
        dict,
    ) and (
        "products" in data
        or "ranking" in data
    ):
        return data

    return raw_data


def _extract_products(
    payload: dict,
) -> list[dict]:
    products = payload.get(
        "products"
    )

    if isinstance(
        products,
        list,
    ):
        return [
            item
            for item in products
            if isinstance(
                item,
                dict,
            )
        ]

    if isinstance(payload.get("product"), dict):
        return [payload]

    return []


def _as_ingestion_product(record: dict) -> dict:
    """Adapt a detailed PRODUCT RAW to the existing v2 writer shape."""
    nested = record.get("product")
    if not isinstance(nested, dict):
        return record

    brand = record.get("brand")
    brand = brand if isinstance(brand, dict) else {}
    snapshot = record.get("snapshot")
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    category = nested.get("category")
    category = category if isinstance(category, dict) else {}
    deepest = None
    for depth in range(4, 0, -1):
        code = category.get(f"depth{depth}_code")
        name = category.get(f"depth{depth}_name")
        if code or name:
            deepest = {
                "source_category_id": code or name,
                "name": name or code,
                "source_category_path": ">".join(
                    str(category.get(f"depth{i}_name"))
                    for i in range(1, depth + 1)
                    if category.get(f"depth{i}_name")
                ),
            }
            break

    genders = nested.get("genders")
    return {
        "source_product_id": nested.get("goods_no"),
        "goods_no": nested.get("goods_no"),
        "goodsName": nested.get("name"),
        "product_name": nested.get("name"),
        "source_name_en": nested.get("name_en"),
        "style_no": nested.get("style_no"),
        "thumbnail_url": nested.get("thumbnail_url"),
        "product_url": (record.get("meta") or {}).get("final_url"),
        "gender": ",".join(genders) if isinstance(genders, list) else genders,
        "brand": brand.get("brand_code") or nested.get("brand_code"),
        "brandName": brand.get("name_ko"),
        "category": deepest or {},
        "normal_price": snapshot.get("regular_price"),
        "sale_price": snapshot.get("sale_price"),
        "discount_rate": snapshot.get("discount_rate"),
        "reviewCount": snapshot.get("review_count"),
        "reviewScore": snapshot.get("satisfaction_score"),
        "used_condition_grade": snapshot.get("used_condition_grade"),
        "is_sold_out": snapshot.get("is_sold_out"),
        "size": nested.get("size"),
        "ranking_context": record.get("ranking_context") or {},
        "detail_snapshot": snapshot,
        "source_attributes": nested.get("source_attributes") or {},
        "used_price_history": record.get("used_price_history") or {},
    }


def _observed_at(
    raw_document: RawDocument,
):
    value = (
        raw_document.collected_at
        or timezone.now()
    )

    if isinstance(
        value,
        str,
    ):
        parsed = parse_datetime(
            value
        )

        if parsed is not None:
            value = parsed

    return value


def _load_raw_json(
    raw_document: RawDocument,
) -> dict:
    s3 = boto3.client("s3")

    response = s3.get_object(
        Bucket=raw_document.s3_bucket,
        Key=raw_document.s3_key,
    )

    value = json.loads(
        response[
            "Body"
        ]
        .read()
        .decode(
            "utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "MUSINSA_USED raw JSON root가 "
            "dict가 아닙니다."
        )

    return value


def _build_ranking_context(
    *,
    product: dict,
    payload: dict,
) -> dict:
    payload_ranking = (
        payload.get(
            "ranking"
        )
        if isinstance(
            payload.get(
                "ranking"
            ),
            dict,
        )
        else {}
    )

    item_context = (
        product.get(
            "ranking_context"
        )
        if isinstance(
            product.get(
                "ranking_context"
            ),
            dict,
        )
        else {}
    )

    context = {
        **payload_ranking,
        **item_context,
    }

    context.setdefault(
        "rank",
        product.get(
            "rank"
        ),
    )

    context.setdefault(
        "goods_no",
        _first(
            product,
            "goodsNo",
            "goods_no",
            "source_product_id",
            "goods_id",
        ),
    )

    context.setdefault(
        "product_name",
        _first(
            product,
            "goodsName",
            "product_name",
            "name",
        ),
    )

    context.setdefault(
        "product_url",
        _first(
            product,
            "goodsLinkUrl",
            "product_url",
        ),
    )

    context.setdefault(
        "thumbnail_url",
        _first(
            product,
            "thumbnail",
            "thumbnail_url",
            "image_url",
        ),
    )

    context.setdefault(
        "brand_code",
        _first(
            product,
            "brand",
            "brand_code",
        ),
    )

    context.setdefault(
        "brand_name",
        _first(
            product,
            "brandName",
            "brand_name",
        ),
    )

    context.setdefault(
        "normal_price",
        _first(
            product,
            "normalPrice",
            "normal_price",
            "regular_price",
            "list_price",
        ),
    )

    context.setdefault(
        "price",
        _first(
            product,
            "finalPrice",
            "price",
            "sale_price",
            "final_price",
        ),
    )

    context.setdefault(
        "discount_rate",
        _first(
            product,
            "finalDiscount",
            "discount_rate",
            "saleRate",
        ),
    )

    context.setdefault(
        "used_condition_grade",
        _first(
            product,
            "usedConditionGrade",
            "used_condition_grade",
        ),
    )

    context.setdefault(
        "is_sold_out",
        product.get(
            "isSoldOut",
            product.get(
                "is_sold_out"
            ),
        ),
    )

    return {
        key:
            _json_safe(value)
        for key, value
        in context.items()
        if value is not None
    }


def _condition_short(
    value,
) -> str | None:
    value = _text(
        value
    )

    if value is None:
        return None

    for grade in ("S+", "A+", "S", "A", "B"):
        if value.upper().startswith(grade):
            return grade
    return None


def _upsert_brand_source(
    *,
    source: Source,
    product: dict,
    observed_at,
):
    source_brand_id = _text(
        _first(
            product,
            "brand",
            "brand_code",
        )
    )

    source_brand_name = _text(
        _first(
            product,
            "brandName",
            "brand_name",
        )
    )

    if (
        source_brand_id is None
        and source_brand_name is None
    ):
        return None, False

    if source_brand_id is None:
        source_brand_id = (
            source_brand_name
        )

    fields = _field_names(
        BrandSource
    )

    obj = (
        BrandSource.objects
        .filter(
            source=source,
            source_brand_id=(
                source_brand_id
            ),
        )
        .first()
    )

    created = (
        obj is None
    )

    if obj is None:
        kwargs = {
            "source":
                source,
            "source_brand_id":
                source_brand_id,
        }

        if (
            "brand" in fields
        ):
            kwargs["brand"] = None

        obj = BrandSource(
            **kwargs
        )

    # 프로젝트 버전별 field alias 대응.
    assignments = {
        "name":
            source_brand_name,
        "source_brand_name":
            source_brand_name,
        "normalized_name":
            source_brand_name,
        "source_profile_url":
            product.get(
                "brandLinkUrl"
            ),
        "first_seen_at":
            (
                observed_at
                if created
                else getattr(
                    obj,
                    "first_seen_at",
                    None,
                )
            ),
        "last_seen_at":
            observed_at,
        "status":
            "ACTIVE",
    }

    for field, value in (
        assignments.items()
    ):
        if (
            field in fields
            and value is not None
        ):
            setattr(
                obj,
                field,
                value,
            )

    if (
        "detected_count"
        in fields
    ):
        if created:
            obj.detected_count = 1
        else:
            obj.detected_count = (
                (
                    obj.detected_count
                    or 0
                )
                + 1
            )

    obj.save()

    return obj, created


def _upsert_category_source(
    *,
    source: Source,
    product: dict,
    ranking_context: dict,
    observed_at,
):
    category = (
        product.get(
            "category"
        )
        if isinstance(
            product.get(
                "category"
            ),
            dict,
        )
        else {}
    )

    source_category_id = _text(
        _first(
            category,
            "source_category_id",
            "category_id",
        )
        or ranking_context.get(
            "category_id"
        )
    )

    source_category_name = _text(
        _first(
            category,
            "name",
            "source_category_name",
            "category_name",
        )
        or ranking_context.get(
            "category_name"
        )
    )

    if (
        source_category_id is None
        and source_category_name is None
    ):
        return None, False

    if source_category_id is None:
        source_category_id = (
            source_category_name
        )

    fields = _field_names(
        CategorySource
    )

    obj = (
        CategorySource.objects
        .filter(
            source=source,
            source_category_id=(
                source_category_id
            ),
        )
        .first()
    )

    created = (
        obj is None
    )

    if obj is None:
        kwargs = {
            "source":
                source,
            "source_category_id":
                source_category_id,
        }

        if (
            "category" in fields
        ):
            kwargs["category"] = None

        obj = CategorySource(
            **kwargs
        )

    assignments = {
        "name":
            source_category_name,
        "source_category_name":
            source_category_name,
        "normalized_name":
            source_category_name,
        "source_category_path":
            (
                category.get(
                    "source_category_path"
                )
                or (
                    f"USED>{source_category_name}"
                    if source_category_name
                    else None
                )
            ),
        "first_seen_at":
            (
                observed_at
                if created
                else getattr(
                    obj,
                    "first_seen_at",
                    None,
                )
            ),
        "last_seen_at":
            observed_at,
        "status":
            "ACTIVE",
    }

    for field, value in (
        assignments.items()
    ):
        if (
            field in fields
            and value is not None
        ):
            setattr(
                obj,
                field,
                value,
            )

    if (
        "detected_count"
        in fields
    ):
        if created:
            obj.detected_count = 1
        else:
            obj.detected_count = (
                (
                    obj.detected_count
                    or 0
                )
                + 1
            )

    obj.save()

    return obj, created


def _upsert_product_source(
    *,
    source: Source,
    product: dict,
    brand_source,
    category_source,
    ranking_context: dict,
    observed_at,
):
    fields = _field_names(
        ProductSource
    )

    source_product_id = _text(
        _first(
            product,
            "source_product_id",
            "goodsNo",
            "goods_no",
            "goods_id",
        )
    )

    if source_product_id is None:
        raise ValueError(
            "MUSINSA_USED source_product_id가 "
            "없습니다."
        )

    source_name = _text(
        _first(
            product,
            "goodsName",
            "product_name",
            "name",
        )
    )

    product_url = _text(
        _first(
            product,
            "goodsLinkUrl",
            "product_url",
        )
    )

    thumbnail_url = _text(
        _first(
            product,
            "thumbnail",
            "thumbnail_url",
            "image_url",
        )
    )

    gender = _text(
        _first(
            product,
            "displayGenderText",
            "gender",
        )
        or ranking_context.get(
            "gender"
        )
    )

    create_defaults = {}
    if "product" in fields:
        create_defaults["product"] = None
    obj, created = (
        ProductSource.objects
        .select_for_update()
        .get_or_create(
            source=source,
            source_product_id=source_product_id,
            defaults=create_defaults,
        )
    )

    observed_filter = {
        key:
            ranking_context.get(
                key
            )
        for key in (
            "observation_type",
            "filter_type",
            "filter_label",
            "filter_name",
            "filter_parameter",
            "filter_value",
            "category_id",
            "category_name",
            "gender",
            "sort_code",
        )
        if ranking_context.get(
            key
        ) is not None
    }

    attributes = {}

    if (
        obj is not None
        and isinstance(
            getattr(
                obj,
                "attributes",
                None,
            ),
            dict,
        )
    ):
        attributes.update(
            obj.attributes
        )

    if isinstance(product.get("source_attributes"), dict):
        attributes["source_attributes"] = product["source_attributes"]
    if isinstance(product.get("used_price_history"), dict):
        attributes["used_price_history"] = product["used_price_history"]

    # ProductSource에는 "단색이다"를 확정 속성으로 넣지 않고
    # 관측 metadata 목록만 둔다.
    observations = attributes.get(
        "musinsa_used_filter_observations"
    )

    if not isinstance(
        observations,
        list,
    ):
        observations = []

    if observed_filter:
        signature = (
            observed_filter.get(
                "filter_type"
            ),
            observed_filter.get(
                "filter_name"
            ),
            observed_filter.get(
                "category_id"
            ),
            observed_filter.get(
                "sort_code"
            ),
        )

        existing_signatures = {
            (
                item.get(
                    "filter_type"
                ),
                item.get(
                    "filter_name"
                ),
                item.get(
                    "category_id"
                ),
                item.get(
                    "sort_code"
                ),
            )
            for item in observations
            if isinstance(
                item,
                dict,
            )
        }

        if (
            signature
            not in existing_signatures
        ):
            observations.append(
                observed_filter
            )

        attributes[
            "musinsa_used_filter_observations"
        ] = observations

        # 조회 편의를 위한 집계 view.
        # 이것도 필터 검색에서 발견됐다는 positive evidence일 뿐,
        # 미발견을 속성 부재로 해석하지 않는다.
        filter_type = _text(
            observed_filter.get(
                "filter_type"
            )
        )
        filter_name = _text(
            observed_filter.get(
                "filter_name"
            )
        )

        if filter_type and filter_name:
            filter_attributes = attributes.get(
                "musinsa_used_filter_attributes"
            )

            if not isinstance(
                filter_attributes,
                dict,
            ):
                filter_attributes = {}

            values = filter_attributes.get(
                filter_type
            )

            if not isinstance(values, list):
                values = []

            if filter_name not in values:
                values.append(
                    filter_name
                )

            filter_attributes[
                filter_type
            ] = values

            attributes[
                "musinsa_used_filter_attributes"
            ] = filter_attributes

    assignments = {
        "source_brand":
            brand_source,
        "source_category":
            category_source,
        "source_name":
            source_name,
        "source_name_en":
            _text(product.get("source_name_en")),
        "style_no":
            _text(product.get("style_no")),
        "thumbnail_url":
            thumbnail_url,
        "product_url":
            product_url,
        "gender_scope":
            gender,
        "attributes":
            attributes,
        "market_type":
            "RESALE",
        "first_seen_at":
            (
                observed_at
                if created
                else getattr(
                    obj,
                    "first_seen_at",
                    None,
                )
            ),
        "last_seen_at":
            observed_at,
        "status":
            "ACTIVE",
    }

    for field, value in (
        assignments.items()
    ):
        if (
            field in fields
            and value is not None
        ):
            setattr(
                obj,
                field,
                value,
            )

    # FK id가 아닌 문자열 source brand/category 컬럼이 있는 버전 대응.
    if (
        "source_brand_name"
        in fields
    ):
        obj.source_brand_name = (
            ranking_context.get(
                "brand_name"
            )
        )

    if (
        "source_category_id"
        in fields
    ):
        obj.source_category_id = (
            ranking_context.get(
                "category_id"
            )
        )

    if (
        "source_category_name"
        in fields
    ):
        obj.source_category_name = (
            ranking_context.get(
                "category_name"
            )
        )

    if (
        "detected_count"
        in fields
    ):
        if created:
            obj.detected_count = 1
        else:
            obj.detected_count = (
                (
                    obj.detected_count
                    or 0
                )
                + 1
            )

    # mapping_status는 기존 값 보존.
    if (
        created
        and "mapping_status"
        in fields
    ):
        try:
            obj.mapping_status = (
                ProductSource
                .MappingStatus
                .UNMAPPED
            )
        except Exception:
            obj.mapping_status = (
                "UNMAPPED"
            )

    obj.save()

    return obj, created


def _upsert_resale_snapshot(
    *,
    product_source: ProductSource,
    product: dict,
    ranking_context: dict,
    observed_at,
):
    regular_price = _decimal(
        _first(
            product,
            "normalPrice",
            "normal_price",
            "regular_price",
            "list_price",
        )
    )

    sale_price = _decimal(
        _first(
            product,
            "finalPrice",
            "price",
            "sale_price",
            "final_price",
        )
    )

    discount_rate = _decimal(
        _first(
            product,
            "finalDiscount",
            "discount_rate",
            "saleRate",
        )
    )

    condition_raw = _text(
        _first(
            product,
            "usedConditionGrade",
            "used_condition_grade",
        )
    )

    rank = _int(
        ranking_context.get(
            "rank"
        )
        or product.get(
            "rank"
        )
    )

    is_sold_out = product.get(
        "isSoldOut",
        product.get(
            "is_sold_out"
        ),
    )

    market_metrics = {
        "size":
            product.get(
                "size"
            ),
        "currency":
            "KRW",
        "sale_price":
            (
                float(sale_price)
                if sale_price is not None
                else None
            ),
        "is_sold_out":
            is_sold_out,
        "discount_rate":
            (
                float(discount_rate)
                if discount_rate
                is not None
                else None
            ),
        "rank_position":
            rank,
        "regular_price":
            (
                float(regular_price)
                if regular_price
                is not None
                else None
            ),
        "condition_grade":
            _condition_short(
                condition_raw
            ),
        "condition_grade_raw":
            condition_raw,
        "ranking_context":
            _json_safe(
                ranking_context
            ),

        # API 원본에서 나중에 쓸 수 있는 값을 보존.
        "raw_market": {
            key:
                _json_safe(
                    product.get(key)
                )
            for key in (
                "reviewCount",
                "reviewScore",
                "displayGenderText",
                "brand",
                "brandName",
                "brandLinkUrl",
                "goodsLinkUrl",
                "thumbnail",
            )
            if product.get(
                key
            ) is not None
        },
        "detail_snapshot": _json_safe(product.get("detail_snapshot") or {}),
        "used_price_history": _json_safe(
            product.get("used_price_history") or {}
        ),
    }

    # None top-level 제거.
    market_metrics = {
        key:
            value
        for key, value
        in market_metrics.items()
        if value is not None
    }

    defaults = {
                # 현재 필터 1상품 = listing 1개 관측.
                "listing_count":
                    1,
                "available_count":
                    (
                        0
                        if is_sold_out
                        is True
                        else (
                            1 if is_sold_out is False else None
                        )
                    ),
                "min_price":
                    sale_price,
                "max_price":
                    sale_price,
                "avg_price":
                    sale_price,
                "median_price":
                    sale_price,
                "lowest_ask":
                    (
                        sale_price
                        if is_sold_out is False
                        else None
                    ),
                "market_metrics":
                    market_metrics,
            }

    latest = (
        ResaleSnapshot.objects
        .filter(product_source=product_source)
        .order_by("-observed_at", "-id")
        .first()
    )
    compare_fields = (
        "listing_count",
        "available_count",
        "min_price",
        "max_price",
        "avg_price",
        "median_price",
        "sold_count",
        "lowest_ask",
        "highest_bid",
        "last_trade_price",
        "trade_volume",
        "resale_price_ratio",
        "resale_index",
    )
    comparable_metrics = dict(market_metrics)
    comparable_metrics.pop("ranking_context", None)
    comparable_metrics.pop("rank_position", None)
    unchanged = latest is not None and all(
        getattr(latest, field) == defaults.get(field)
        for field in compare_fields
    )
    if unchanged:
        previous_metrics = dict(latest.market_metrics or {})
        previous_metrics.pop("ranking_context", None)
        previous_metrics.pop("rank_position", None)
        unchanged = previous_metrics == comparable_metrics
    if unchanged:
        return latest, False

    snapshot = ResaleSnapshot.objects.create(
        product_source=product_source,
        observed_at=observed_at,
        **defaults,
    )
    created = True

    return snapshot, created


def _mark_normalization(
    raw_document: RawDocument,
    *,
    success: bool,
    error: str | None = None,
):
    fields = _field_names(
        RawDocument
    )

    update_fields = []

    if (
        "normalization_status"
        in fields
    ):
        status = (
            RawDocument
            .NormalizationStatus
            .SUCCESS
            if success
            else RawDocument
            .NormalizationStatus
            .FAILED
        )

        raw_document.normalization_status = (
            status
        )

        update_fields.append(
            "normalization_status"
        )

    for candidate in (
        "normalization_error",
        "normalization_error_message",
    ):
        if candidate in fields:
            setattr(
                raw_document,
                candidate,
                (
                    None
                    if success
                    else error
                ),
            )
            update_fields.append(
                candidate
            )

    if update_fields:
        raw_document.save(
            update_fields=(
                update_fields
            )
        )


@transaction.atomic
def ingest_musinsa_used_v2_raw_document(
    *,
    raw_document_id: int,
) -> dict:
    """
    MUSINSA_USED FILTER v2 전용:

    RawDocument(S3)
      -> BrandSource
      -> CategorySource
      -> ProductSource(RESALE)
      -> ResaleSnapshot

    old collection.musinsa_used / old MUSINSA_USED normalizer에 의존하지 않는다.
    """

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

    if (
        raw_document.source.code
        .upper()
        != SOURCE_CODE
    ):
        raise ValueError(
            "MUSINSA_USED RawDocument가 "
            "아닙니다."
        )

    raw_data = _load_raw_json(
        raw_document
    )

    payload = _extract_payload(
        raw_data
    )

    products = _extract_products(
        payload
    )

    source = (
        Source.objects
        .get(
            pk=raw_document.source_id
        )
    )

    observed_at = _observed_at(
        raw_document
    )

    result = {
        "raw_document_id":
            raw_document.id,
        "products":
            0,
        "product_source_ids":
            [],

        "brand_created":
            0,
        "brand_updated":
            0,

        "category_created":
            0,
        "category_updated":
            0,

        "product_created":
            0,
        "product_updated":
            0,

        "snapshot_created":
            0,
        "snapshot_updated":
            0,

        "snapshot_unchanged":
            0,

        "failed":
            0,
        "errors":
            [],
    }

    for index, product in enumerate(
        products,
        start=1,
    ):
        result["products"] += 1

        try:
            product = _as_ingestion_product(product)
            ranking_context = (
                _build_ranking_context(
                    product=product,
                    payload=payload,
                )
            )

            (
                brand_source,
                brand_created,
            ) = _upsert_brand_source(
                source=source,
                product=product,
                observed_at=observed_at,
            )

            if brand_source is not None:
                result[
                    "brand_created"
                    if brand_created
                    else "brand_updated"
                ] += 1

            (
                category_source,
                category_created,
            ) = _upsert_category_source(
                source=source,
                product=product,
                ranking_context=(
                    ranking_context
                ),
                observed_at=observed_at,
            )

            if category_source is not None:
                result[
                    "category_created"
                    if category_created
                    else "category_updated"
                ] += 1

            (
                product_source,
                product_created,
            ) = _upsert_product_source(
                source=source,
                product=product,
                brand_source=brand_source,
                category_source=(
                    category_source
                ),
                ranking_context=(
                    ranking_context
                ),
                observed_at=observed_at,
            )

            result[
                "product_created"
                if product_created
                else "product_updated"
            ] += 1

            result[
                "product_source_ids"
            ].append(
                product_source.id
            )

            (
                _snapshot,
                snapshot_created,
            ) = _upsert_resale_snapshot(
                product_source=(
                    product_source
                ),
                product=product,
                ranking_context=(
                    ranking_context
                ),
                observed_at=observed_at,
            )

            result[
                "snapshot_created"
                if snapshot_created
                else "snapshot_unchanged"
            ] += 1

        except Exception as exc:
            result[
                "failed"
            ] += 1

            result[
                "errors"
            ].append({
                "product_index":
                    index,
                "source_product_id":
                    _first(
                        product,
                        "source_product_id",
                        "goodsNo",
                    ),
                "error_type":
                    exc
                    .__class__
                    .__name__,
                "error_message":
                    str(exc),
            })

    if result["failed"]:
        _mark_normalization(
            raw_document,
            success=False,
            error=str(
                result["errors"][:3]
            ),
        )
    else:
        _mark_normalization(
            raw_document,
            success=True,
        )

    result["product_source_ids"] = sorted(
        set(result["product_source_ids"])
    )

    return result


def ingest_pending_musinsa_used_v2_raw_documents(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    queryset = (
        RawDocument.objects
        .filter(
            source__code__iexact=(
                SOURCE_CODE
            ),
            document_type__in=[
                "RANKING",
                "PRODUCT",
            ],
        )
        .order_by("id")
    )

    if crawl_run_id is not None:
        queryset = queryset.filter(
            crawl_run_id=(
                crawl_run_id
            )
        )

    if limit is not None:
        queryset = queryset[:limit]

    summary = {
        "raw_documents":
            0,
        "success":
            0,
        "failed":
            0,
        "products":
            0,
        "errors":
            [],
    }

    for raw_document in queryset:
        summary[
            "raw_documents"
        ] += 1

        try:
            one = (
                ingest_musinsa_used_v2_raw_document(
                    raw_document_id=(
                        raw_document.id
                    )
                )
            )

            summary[
                "products"
            ] += (
                one.get(
                    "products",
                    0,
                )
                or 0
            )

            if one.get(
                "failed"
            ):
                summary[
                    "failed"
                ] += 1
                summary[
                    "errors"
                ].extend(
                    one.get(
                        "errors",
                        [],
                    )
                )
            else:
                summary[
                    "success"
                ] += 1

        except Exception as exc:
            summary[
                "failed"
            ] += 1

            summary[
                "errors"
            ].append({
                "raw_document_id":
                    raw_document.id,
                "error_type":
                    exc
                    .__class__
                    .__name__,
                "error_message":
                    str(exc),
            })

    return summary


@transaction.atomic
def persist_product_source_relations(
    relations: list[dict],
) -> dict:
    """Persist MUSINSA evidence relations without canonical product mapping."""
    skipped = []
    valid_relation_types = {
        value
        for value, _label in ProductSourceRelation.RelationType.choices
    }
    normalized_relations = []
    lookup_keys: set[tuple[str, str]] = set()
    for relation in relations or []:
        relation_type = (
            relation.get("relation_type")
            or ProductSourceRelation.RelationType.RESALE_OF
        )
        if relation_type not in valid_relation_types:
            skipped.append({**relation, "skip_reason": "INVALID_RELATION_TYPE"})
            continue
        from_key = (
            str(relation.get("from_source") or "").upper(),
            str(relation.get("from_source_product_id") or ""),
        )
        to_key = (
            str(relation.get("to_source") or "").upper(),
            str(relation.get("to_source_product_id") or ""),
        )
        if not all((*from_key, *to_key)):
            skipped.append({**relation, "skip_reason": "MISSING_SOURCE_KEY"})
            continue
        normalized_relations.append((relation, from_key, to_key, relation_type))
        lookup_keys.update((from_key, to_key))

    source_codes = {source_code for source_code, _source_id in lookup_keys}
    source_product_ids = {source_id for _source_code, source_id in lookup_keys}
    source_ids_by_code = {
        source.code.upper(): source.pk
        for source in Source.objects.all()
        if source.code.upper() in source_codes
    }
    locked_sources = list(
        ProductSource.objects.select_for_update()
        .select_related("source")
        .filter(
            source_id__in=source_ids_by_code.values(),
            source_product_id__in=source_product_ids,
        )
    )
    sources_by_key = {
        (source.source.code.upper(), str(source.source_product_id)): source
        for source in locked_sources
    }
    edges: list[tuple[int, int]] = []
    resolved_relations = []
    for relation, from_key, to_key, relation_type in normalized_relations:
        from_source = sources_by_key.get(from_key)
        to_source = sources_by_key.get(to_key)
        if from_source is None or to_source is None:
            skipped.append({**relation, "skip_reason": "PRODUCT_SOURCE_NOT_FOUND"})
            continue
        resolved_relations.append((relation, from_source, to_source, relation_type))
        edges.append((from_source.pk, to_source.pk))

    requested_keys = {
        (from_source.pk, to_source.pk, relation_type)
        for _relation, from_source, to_source, relation_type
        in resolved_relations
    }
    involved_ids = {source_id for edge in edges for source_id in edge}
    existing_keys = set(
        ProductSourceRelation.objects.filter(
            from_product_source_id__in=involved_ids,
            to_product_source_id__in=involved_ids,
            relation_type__in=valid_relation_types,
        ).values_list(
            "from_product_source_id",
            "to_product_source_id",
            "relation_type",
        )
    ) if involved_ids else set()
    relation_by_key = {
        (from_source.pk, to_source.pk, relation_type): relation
        for relation, from_source, to_source, relation_type
        in resolved_relations
    }
    missing_keys = requested_keys - existing_keys
    ProductSourceRelation.objects.bulk_create(
        [
            ProductSourceRelation(
                from_product_source_id=from_id,
                to_product_source_id=to_id,
                relation_type=relation_type,
                evidence_source=(
                    relation_by_key[(from_id, to_id, relation_type)].get(
                        "evidence_source"
                    )
                    or "MUSINSA_RELATED_GOODS"
                ),
            )
            for from_id, to_id, relation_type in missing_keys
        ],
        batch_size=1000,
        ignore_conflicts=True,
    )
    created = len(missing_keys)
    existing = len(requested_keys) - created

    return {
        "created": created,
        "existing": existing,
        "skipped": len(skipped),
        "skipped_relations": skipped,
    }


def persist_resale_of_relations(relations: list[dict]) -> dict:
    """Backward-compatible entry point for all MUSINSA related-goods relations."""
    return persist_product_source_relations(relations)
