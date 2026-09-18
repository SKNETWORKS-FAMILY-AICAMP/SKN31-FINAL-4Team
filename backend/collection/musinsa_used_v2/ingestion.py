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

    return []


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

    return (
        value
        .replace(
            "등급",
            "",
        )
        .strip()
        or None
    )


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

    obj = (
        ProductSource.objects
        .filter(
            source=source,
            source_product_id=(
                source_product_id
            ),
        )
        .first()
    )

    created = (
        obj is None
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

    if obj is None:
        kwargs = {
            "source":
                source,
            "source_product_id":
                source_product_id,
        }

        if "product" in fields:
            kwargs["product"] = None

        obj = ProductSource(
            **kwargs
        )

    assignments = {
        "source_brand":
            brand_source,
        "source_category":
            category_source,
        "source_name":
            source_name,
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
    }

    # None top-level 제거.
    market_metrics = {
        key:
            value
        for key, value
        in market_metrics.items()
        if value is not None
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
                # 현재 필터 1상품 = listing 1개 관측.
                "listing_count":
                    1,
                "available_count":
                    (
                        0
                        if is_sold_out
                        is True
                        else 1
                    ),
                "min_price":
                    sale_price,
                "max_price":
                    sale_price,
                "avg_price":
                    sale_price,
                "median_price":
                    sale_price,
                "market_metrics":
                    market_metrics,
            },
        )
    )

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
                else "snapshot_updated"
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
