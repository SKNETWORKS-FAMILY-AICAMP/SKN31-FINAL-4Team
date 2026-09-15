from __future__ import annotations

import json
import logging
from typing import Callable

import boto3
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import (
    BrandSource,
    CategorySource,
    ProductSource,
    ProductSourceSnapshot,
    RawDocument,
    ResaleSnapshot,
    Source,
)


logger = logging.getLogger(__name__)


def get_source(
    source_code: str,
) -> Source:
    return Source.objects.get(
        code__iexact=source_code,
    )


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=getattr(
            settings,
            "AWS_REGION",
            "ap-northeast-2",
        ),
    )


def load_raw_json(
    raw_document: RawDocument,
    *,
    s3_client=None,
) -> dict:
    s3_client = (
        s3_client
        or get_s3_client()
    )

    response = s3_client.get_object(
        Bucket=raw_document.s3_bucket,
        Key=raw_document.s3_key,
    )

    body = response["Body"].read()

    data = json.loads(
        body.decode("utf-8")
    )

    if not isinstance(data, dict):
        raise ValueError(
            f"RawDocument #{raw_document.id} "
            "JSON root가 dict가 아닙니다."
        )

    return data


def extract_payload(
    raw_data: dict,
) -> dict:
    payload = raw_data.get("payload")

    if isinstance(payload, dict):
        return payload

    data = raw_data.get("data")

    if isinstance(data, dict):
        return data

    return raw_data


def extract_products(payload: dict) -> list[dict]:
    products = payload.get("products")
    if isinstance(products, list):
        return [item for item in products if isinstance(item, dict)]
    if isinstance(payload.get("product"), dict):
        return [payload]
    return []


def _observed_at(value, *, default):
    if hasattr(value, "tzinfo"):
        parsed = value
    elif value:
        parsed = parse_datetime(str(value))
    else:
        parsed = None
    parsed = parsed or default or timezone.now()
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _upsert_brand_source(*, source, target: dict, observed_at):
    source_brand_id = target.get("source_brand_id")
    if source_brand_id in (None, ""):
        return None, False

    source_brand_id = str(source_brand_id)[:255]
    brand_source, created = (
        BrandSource.objects.select_for_update().get_or_create(
            source=source,
            source_brand_id=source_brand_id,
            defaults={
                "detected_count": 0,
                "first_seen_at": observed_at,
                "mapping_status": BrandSource.MappingStatus.UNMAPPED,
            },
        )
    )
    for field in (
        "name",
        "english_name",
        "image_url",
        "country_code",
        "description",
    ):
        value = target.get(field)
        if value is not None:
            setattr(brand_source, field, value)
    incoming_attributes = target.get("attributes") or {}
    if incoming_attributes:
        brand_source.attributes = {
            **(brand_source.attributes or {}),
            **incoming_attributes,
        }
    brand_source.last_seen_at = observed_at
    brand_source.detected_count = (brand_source.detected_count or 0) + 1
    # Source ingestion ends at UNMAPPED. Existing operator mappings are
    # preserved, but ingestion never searches for or assigns a FEEDIT Brand.
    if brand_source.brand_id is None and (
        brand_source.mapping_status != BrandSource.MappingStatus.EXCLUDED
    ):
        brand_source.mapping_status = BrandSource.MappingStatus.UNMAPPED
        brand_source.mapping_method = None
        brand_source.mapping_confidence = None
    brand_source.save()
    return brand_source, created


def _upsert_category_source(*, source, target: dict, observed_at):
    source_category_id = target.get("source_category_id")
    if source_category_id in (None, ""):
        return None, False

    source_category_id = str(source_category_id)[:255]
    category_source, created = (
        CategorySource.objects.select_for_update().get_or_create(
            source=source,
            source_category_id=source_category_id,
            defaults={"first_seen_at": observed_at},
        )
    )
    category_source.source_category_name = target.get("source_category_name")
    category_source.source_category_path = target.get("source_category_path")
    category_source.last_seen_at = observed_at
    # FEEDIT Category matching belongs to the existing post-ingestion flow.
    category_source.save()
    return category_source, created


def _upsert_product_source(
    *,
    source,
    target: dict,
    brand_source,
    category_source,
    observed_at,
):
    source_product_id = target.get("source_product_id")
    if source_product_id in (None, ""):
        raise ValueError("source_product_id가 없습니다.")
    source_product_id = str(source_product_id)[:255]
    product_source, created = (
        ProductSource.objects.select_for_update().get_or_create(
            source=source,
            source_product_id=source_product_id,
            defaults={
                "first_seen_at": observed_at,
                "detected_count": 0,
                "mapping_status": ProductSource.MappingStatus.UNMAPPED,
            },
        )
    )
    # Product matching and normalized_name generation belong to the existing
    # post-ingestion flow. Preserve an existing mapping; otherwise keep the
    # source row UNMAPPED.
    if product_source.product_id is None and (
        product_source.mapping_status != ProductSource.MappingStatus.REJECTED
    ):
        product_source.mapping_status = ProductSource.MappingStatus.UNMAPPED

    product_source.source_brand = brand_source
    product_source.source_category = category_source
    product_source.source_name = target.get("source_name")
    for field in (
        "source_name_en",
        "style_no",
        "thumbnail_url",
        "product_url",
        "gender_scope",
        "market_type",
    ):
        value = target.get(field)
        if value is not None:
            setattr(product_source, field, value)
    product_source.attributes = {
        **(product_source.attributes or {}),
        **(target.get("attributes") or {}),
    }
    product_source.last_seen_at = observed_at
    product_source.detected_count = (product_source.detected_count or 0) + 1
    product_source.status = ProductSource.Status.ACTIVE
    product_source.save()
    return product_source, created


def _upsert_snapshot(*, product_source, target: dict, observed_at):
    table = target.get("_table")
    values = {
        key: value
        for key, value in target.items()
        if not key.startswith("_")
        and key not in {"product_source_id", "observed_at"}
    }
    if table == 'snapshot.product_source_snapshot':
        ranking_scope = values.pop("ranking_scope", None)
        _, created = ProductSourceSnapshot.objects.update_or_create(
            product_source=product_source,
            observed_at=observed_at,
            ranking_scope=ranking_scope,
            defaults=values,
        )
        return created
    if table == 'snapshot.resale_snapshot':
        _, created = ResaleSnapshot.objects.update_or_create(
            product_source=product_source,
            observed_at=observed_at,
            defaults=values,
        )
        return created
    raise ValueError(f"지원하지 않는 snapshot table입니다: {table}")


def persist_preview(*, source, preview: dict, default_observed_at) -> dict:
    targets = preview.get("targets") or {}
    observed_at = _observed_at(
        (targets.get("product_source_snapshot") or targets.get("resale_snapshot") or {}).get("observed_at"),
        default=default_observed_at,
    )
    brand_source, brand_created = _upsert_brand_source(
        source=source,
        target=targets.get("brand_source") or {},
        observed_at=observed_at,
    )
    category_source, category_created = _upsert_category_source(
        source=source,
        target=targets.get("category_source") or {},
        observed_at=observed_at,
    )
    product_source, product_created = _upsert_product_source(
        source=source,
        target=targets.get("product_source") or {},
        brand_source=brand_source,
        category_source=category_source,
        observed_at=observed_at,
    )
    snapshot_target = targets.get("product_source_snapshot") or targets.get("resale_snapshot")
    snapshot_created = _upsert_snapshot(
        product_source=product_source,
        target=snapshot_target or {},
        observed_at=observed_at,
    )
    related_created = 0
    for related in preview.get("related_listing_candidates") or []:
        related_target = related.get("product_source_payload") or {}
        references = related_target.get("_references") or {}
        related_brand = brand_source
        brand_ref = references.get("source_brand") or {}
        if brand_ref.get("source_brand_id"):
            related_brand = BrandSource.objects.filter(
                source=source,
                source_brand_id=str(brand_ref["source_brand_id"]),
            ).first()
        related_product, was_created = _upsert_product_source(
            source=source,
            target=related_target,
            brand_source=related_brand,
            category_source=None,
            observed_at=observed_at,
        )
        _upsert_snapshot(
            product_source=related_product,
            target=related.get("resale_snapshot_payload") or {},
            observed_at=observed_at,
        )
        related_created += int(was_created)
    return {
        "product_source_id": product_source.id,
        "product_created": product_created,
        "mapping_status": product_source.mapping_status,
        "brand_created": brand_created,
        "brand_mapped": bool(brand_source and brand_source.brand_id),
        "category_created": category_created,
        "category_mapped": bool(category_source and category_source.category_id),
        "snapshot_created": snapshot_created,
        "related_created": related_created,
    }


def ingest_preview_raw_document(
    *,
    raw_document_id: int,
    source_code: str,
    preview_builder: Callable[[dict, RawDocument, dict], dict],
) -> dict:
    raw_document = (
        RawDocument.objects.select_related("source", "crawl_run")
        .get(pk=raw_document_id)
    )
    if raw_document.source.code.upper() != source_code.upper():
        raise ValueError(f"{source_code} RawDocument가 아닙니다.")
    RawDocument.objects.filter(pk=raw_document.id).update(
        normalization_status=RawDocument.NormalizationStatus.PROCESSING,
        normalization_error=None,
        normalized_at=None,
    )
    try:
        raw_data = load_raw_json(raw_document, s3_client=get_s3_client())
        payload = extract_payload(raw_data)
        products = extract_products(payload)
        rows = []
        with transaction.atomic():
            for product in products:
                preview = preview_builder(product, raw_document, payload)
                rows.append(
                    persist_preview(
                        source=raw_document.source,
                        preview=preview,
                        default_observed_at=raw_document.collected_at,
                    )
                )
            RawDocument.objects.filter(pk=raw_document.id).update(
                normalization_status=RawDocument.NormalizationStatus.SUCCESS,
                normalization_error=None,
                normalized_at=timezone.now(),
            )
    except Exception as exc:
        RawDocument.objects.filter(pk=raw_document.id).update(
            normalization_status=RawDocument.NormalizationStatus.FAILED,
            normalization_error=str(exc),
            normalized_at=None,
        )
        raise

    summary = {
        "raw_document_id": raw_document.id,
        "products": len(rows),
        "product_created": sum(int(row["product_created"]) for row in rows),
        "product_mapped": sum(row["mapping_status"] == ProductSource.MappingStatus.MAPPED for row in rows),
        "product_review": sum(row["mapping_status"] == ProductSource.MappingStatus.REVIEW for row in rows),
        "product_unmapped": sum(row["mapping_status"] == ProductSource.MappingStatus.UNMAPPED for row in rows),
        "brand_created": sum(int(row["brand_created"]) for row in rows),
        "brand_mapped": sum(int(row["brand_mapped"]) for row in rows),
        "category_created": sum(int(row["category_created"]) for row in rows),
        "category_mapped": sum(int(row["category_mapped"]) for row in rows),
        "snapshots_created": sum(int(row["snapshot_created"]) for row in rows),
        "related_created": sum(row["related_created"] for row in rows),
    }
    logger.info(
        "[SOURCE_INGESTION][%s] DB_WRITE_EXECUTED=TRUE summary=%s",
        source_code.upper(),
        summary,
    )
    return summary


def get_raw_documents(
    *,
    source_code: str,
    document_type: str = "RANKING",
    limit: int | None = None,
    crawl_run_id: int | None = None,
):
    queryset = (
        RawDocument.objects
        .select_related(
            "source",
            "crawl_run",
        )
        .filter(
            source__code__iexact=source_code,
            document_type__iexact=document_type,
        )
        .order_by("id")
    )

    if crawl_run_id is not None:
        queryset = queryset.filter(
            crawl_run_id=crawl_run_id,
        )

    if limit is not None:
        queryset = queryset[:limit]

    return queryset
