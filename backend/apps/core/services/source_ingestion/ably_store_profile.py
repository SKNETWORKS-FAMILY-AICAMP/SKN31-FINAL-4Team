from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import BrandSource, RawDocument
from collection.ably.store_profile_normalization import (
    build_brand_source_candidates,
    choose_brand_source_name,
    merge_brand_source_attributes,
)

from .common import extract_payload, get_s3_client, load_raw_json
from .ably_brand_mapping import auto_map_ably_brand_sources


def _upsert_brand_source(*, source, candidate: dict, observed_at) -> dict:
    source_brand_id = str(candidate["source_brand_id"])[:255]
    incoming_name = candidate.get("name")
    brand_source, created = BrandSource.objects.select_for_update().get_or_create(
        source=source,
        source_brand_id=source_brand_id,
        defaults={
            "name": incoming_name,
            "attributes": {},
            "detected_count": 0,
            "first_seen_at": observed_at,
            "mapping_status": BrandSource.MappingStatus.UNMAPPED,
        },
    )

    name_enriched = False
    if not created:
        brand_source.name, name_enriched = choose_brand_source_name(
            brand_source.name,
            incoming_name,
        )

    brand_source.attributes = merge_brand_source_attributes(
        brand_source.attributes,
        candidate.get("attributes") or {},
    )
    if brand_source.first_seen_at is None:
        brand_source.first_seen_at = observed_at
    brand_source.last_seen_at = observed_at
    brand_source.detected_count = (brand_source.detected_count or 0) + 1
    brand_source.save()
    return {
        "brand_source_id": brand_source.id,
        "source_brand_id": source_brand_id,
        "created": created,
        "name_enriched": name_enriched,
    }


def ingest_ably_store_profile_raw_document(*, raw_document_id: int) -> dict:
    raw_document = RawDocument.objects.select_related("source", "crawl_run").get(
        pk=raw_document_id
    )
    if raw_document.source.code.upper() != "ABLY":
        raise ValueError("ABLY RawDocument가 아닙니다.")
    if raw_document.document_type.upper() != "STORE_PROFILE":
        raise ValueError("ABLY STORE_PROFILE RawDocument가 아닙니다.")

    RawDocument.objects.filter(pk=raw_document.id).update(
        normalization_status=RawDocument.NormalizationStatus.PROCESSING,
        normalization_error=None,
        normalized_at=None,
    )
    try:
        raw_data = load_raw_json(raw_document, s3_client=get_s3_client())
        payload = extract_payload(raw_data)
        candidates = build_brand_source_candidates(payload)
        observed_at = raw_document.collected_at or timezone.now()
        with transaction.atomic():
            rows = [
                _upsert_brand_source(
                    source=raw_document.source,
                    candidate=candidate,
                    observed_at=observed_at,
                )
                for candidate in candidates
            ]
            mapping = auto_map_ably_brand_sources(
                brand_source_ids=[row["brand_source_id"] for row in rows]
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

    return {
        "raw_document_id": raw_document.id,
        "brand_sources": len(rows),
        "brand_source_ids": [row["brand_source_id"] for row in rows],
        "created": sum(int(row["created"]) for row in rows),
        "existing": sum(int(not row["created"]) for row in rows),
        "names_enriched": sum(int(row["name_enriched"]) for row in rows),
        "auto_mapping": mapping,
        "product_source_ids": [],
    }
