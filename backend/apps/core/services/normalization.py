from __future__ import annotations

import json
from typing import Any

import boto3

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    Brand,
    BrandSource,
    CrawlRun,
    RawDocument,
)

from analysis.commerce.musinsa.normalizer import (
    MusinsaNormalizer,
)


# =========================================================
# TEXT NORMALIZE
# =========================================================


def normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    return " ".join(
        str(value)
        .strip()
        .lower()
        .split()
    )


# =========================================================
# S3
# =========================================================


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
    )


def _load_raw_json(
    *,
    raw_document: RawDocument,
    s3_client,
) -> dict:
    """
    RawDocument에 저장된 S3 위치에서 JSON 원본을 읽는다.
    """

    response = s3_client.get_object(
        Bucket=raw_document.s3_bucket,
        Key=raw_document.s3_key,
    )

    body = (
        response["Body"]
        .read()
        .decode("utf-8")
    )

    return json.loads(body)


# =========================================================
# BRAND MATCH
# =========================================================


def _find_single_brand(
    queryset,
) -> Brand | None:
    """
    후보가 정확히 1개일 때만 자동 매핑한다.

    동일 이름의 Brand가 2개 이상이면
    잘못된 FK를 걸지 않고 미매핑으로 남긴다.
    """

    candidates = list(
        queryset[:2]
    )

    if len(candidates) == 1:
        return candidates[0]

    return None


def _find_brand_exact(
    *,
    name: str | None,
    english_name: str | None,
) -> tuple[Brand | None, str | None]:
    """
    처음 보는 플랫폼 브랜드에 대해서만 호출.

    1. Brand.name exact
    2. Brand.english_name exact

    반환:
        (Brand, mapping_method)
        또는
        (None, None)
    """

    if name:
        matched = _find_single_brand(
            Brand.objects.filter(
                status=Brand.Status.ACTIVE,
                name__iexact=name.strip(),
            )
            .order_by("id")
        )

        if matched:
            return (
                matched,
                BrandSource.MappingMethod.EXACT_NAME,
            )

    if english_name:
        matched = _find_single_brand(
            Brand.objects.filter(
                status=Brand.Status.ACTIVE,
                english_name__iexact=(
                    english_name.strip()
                ),
            )
            .order_by("id")
        )

        if matched:
            return (
                matched,
                BrandSource.MappingMethod.EXACT_NAME,
            )

    return None, None


# =========================================================
# MUSINSA BRAND EXTRACT
# =========================================================


def _extract_brand_payload(
    item: dict[str, Any],
) -> dict | None:
    """
    MusinsaNormalizer의 상품 결과에서
    BrandSource에 필요한 공통 브랜드 정보를 만든다.
    """

    brand_data = (
        item.get("brand")
        or {}
    )

    source_brand_id = (
        brand_data.get("source_brand_code")
        or brand_data.get("source_brand_id")
        or brand_data.get("brand_code")
    )

    if not source_brand_id:
        return None

    source_brand_id = str(
        source_brand_id
    ).strip()

    if not source_brand_id:
        return None

    source_brand_name = (
        brand_data.get("name_ko")
        or brand_data.get("name")
        or None
    )

    source_brand_name_en = (
        brand_data.get("name_en")
        or brand_data.get("english_name")
        or None
    )

    source_brand_url = (
        brand_data.get("url")
        or brand_data.get("brand_url")
        or None
    )

    return {
        "source_brand_id": source_brand_id,
        "source_brand_name": source_brand_name,
        "source_brand_name_en": (
            source_brand_name_en
        ),
        "source_brand_url": (
            source_brand_url
        ),
    }


# =========================================================
# BRAND SOURCE UPSERT
# =========================================================


@transaction.atomic
def _upsert_brand_source(
    *,
    source,
    source_brand_id: str,
    source_brand_name: str | None,
    source_brand_name_en: str | None,
    source_brand_url: str | None,
    detected_count: int = 1,
) -> tuple[BrandSource, bool]:
    """
    BrandSource 핵심 로직.

    1. source + source_brand_id 조회
    2. 있으면 정보만 갱신
    3. 없으면 그때만 Brand exact match
    4. 성공하면 AUTO_MAPPED
    5. 실패하면 UNMAPPED + brand=NULL

    반환:
        brand_source
        created
    """

    now = timezone.now()

    # -----------------------------------------------------
    # FAST PATH
    #
    # 이미 플랫폼 브랜드를 알고 있으면
    # 이름 매칭을 다시 하지 않는다.
    # -----------------------------------------------------

    brand_source = (
        BrandSource.objects
        .filter(
            source=source,
            source_brand_id=source_brand_id,
        )
        .first()
    )

    if brand_source:
        update_fields = []

        if (
            source_brand_name
            and brand_source.source_brand_name
            != source_brand_name
        ):
            brand_source.source_brand_name = (
                source_brand_name
            )

            brand_source.normalized_name = (
                normalize_text(
                    source_brand_name
                )
            )

            update_fields.extend([
                "source_brand_name",
                "normalized_name",
            ])

        if (
            source_brand_name_en
            and brand_source.source_brand_name_en
            != source_brand_name_en
        ):
            brand_source.source_brand_name_en = (
                source_brand_name_en
            )

            brand_source.normalized_name_en = (
                normalize_text(
                    source_brand_name_en
                )
            )

            update_fields.extend([
                "source_brand_name_en",
                "normalized_name_en",
            ])

        if (
            source_brand_url
            and brand_source.source_brand_url
            != source_brand_url
        ):
            brand_source.source_brand_url = (
                source_brand_url
            )

            update_fields.append(
                "source_brand_url"
            )

        brand_source.detected_count += (
            detected_count
        )

        brand_source.last_seen_at = now

        update_fields.extend([
            "detected_count",
            "last_seen_at",
            "updated_at",
        ])

        if not brand_source.first_seen_at:
            brand_source.first_seen_at = now

            update_fields.append(
                "first_seen_at"
            )

        brand_source.save(
            update_fields=list(
                dict.fromkeys(
                    update_fields
                )
            )
        )

        return (
            brand_source,
            False,
        )

    # -----------------------------------------------------
    # NEW PLATFORM BRAND
    #
    # 처음 발견했을 때만 FEEDIT Brand 검색
    # -----------------------------------------------------

    (
        matched_brand,
        mapping_method,
    ) = _find_brand_exact(
        name=source_brand_name,
        english_name=source_brand_name_en,
    )

    if matched_brand:
        mapping_status = (
            BrandSource
            .MappingStatus
            .AUTO_MAPPED
        )

        mapping_confidence = 1

    else:
        mapping_status = (
            BrandSource
            .MappingStatus
            .UNMAPPED
        )

        mapping_method = None
        mapping_confidence = None

    brand_source = (
        BrandSource.objects.create(
            brand=matched_brand,

            source=source,

            source_brand_id=(
                source_brand_id
            ),

            source_brand_name=(
                source_brand_name
            ),

            normalized_name=(
                normalize_text(
                    source_brand_name
                )
                if source_brand_name
                else None
            ),

            source_brand_name_en=(
                source_brand_name_en
            ),

            normalized_name_en=(
                normalize_text(
                    source_brand_name_en
                )
                if source_brand_name_en
                else None
            ),

            source_brand_url=(
                source_brand_url
            ),

            mapping_status=(
                mapping_status
            ),

            mapping_method=(
                mapping_method
            ),

            mapping_confidence=(
                mapping_confidence
            ),

            detected_count=(
                detected_count
            ),

            first_seen_at=now,
            last_seen_at=now,
        )
    )

    return (
        brand_source,
        True,
    )


# =========================================================
# NORMALIZE ONE RAW DOCUMENT
# =========================================================


def _normalize_musinsa_raw_document(
    *,
    raw_document: RawDocument,
    normalizer: MusinsaNormalizer,
    s3_client,
) -> dict:
    """
    RawDocument 하나를 처리한다.

    RawDocument
        ↓
    S3 JSON
        ↓
    MusinsaNormalizer
        ↓
    상품 목록
        ↓
    브랜드 그룹화
        ↓
    BrandSource UPSERT
    """

    raw = _load_raw_json(
        raw_document=raw_document,
        s3_client=s3_client,
    )

    # -----------------------------------------------------
    # RANKING
    # -----------------------------------------------------

    if raw_document.document_type == "RANKING":
        normalized = (
            normalizer
            .normalize_ranking(raw)
        )

        products = (
            normalized.get("products")
            or []
        )

    # -----------------------------------------------------
    # PRODUCT
    # -----------------------------------------------------

    elif raw_document.document_type == "PRODUCT":
        product = (
            normalizer
            .normalize_product(raw)
        )

        products = (
            [product]
            if product
            else []
        )

    else:
        raise ValueError(
            (
                "지원하지 않는 "
                "document_type: "
                f"{raw_document.document_type}"
            )
        )

    # -----------------------------------------------------
    # 같은 RawDocument 내 브랜드 그룹화
    # -----------------------------------------------------

    grouped: dict[str, dict] = {}

    for item in products:
        if not item:
            continue

        payload = (
            _extract_brand_payload(
                item
            )
        )

        if not payload:
            continue

        source_brand_id = (
            payload[
                "source_brand_id"
            ]
        )

        if source_brand_id not in grouped:
            grouped[
                source_brand_id
            ] = {
                **payload,
                "count": 0,
            }

        grouped[
            source_brand_id
        ]["count"] += 1

        # 기존 값이 비어 있고 뒤에서 값이 발견되면 보완
        for key in (
            "source_brand_name",
            "source_brand_name_en",
            "source_brand_url",
        ):
            if (
                not grouped[
                    source_brand_id
                ].get(key)
                and payload.get(key)
            ):
                grouped[
                    source_brand_id
                ][key] = payload[key]

    # -----------------------------------------------------
    # BrandSource
    # -----------------------------------------------------

    created = 0
    updated = 0
    mapped = 0
    unmapped = 0

    source = (
        raw_document
        .crawl_run
        .source
    )

    for data in grouped.values():

        (
            brand_source,
            was_created,
        ) = _upsert_brand_source(
            source=source,

            source_brand_id=(
                data[
                    "source_brand_id"
                ]
            ),

            source_brand_name=(
                data[
                    "source_brand_name"
                ]
            ),

            source_brand_name_en=(
                data[
                    "source_brand_name_en"
                ]
            ),

            source_brand_url=(
                data[
                    "source_brand_url"
                ]
            ),

            detected_count=(
                data["count"]
            ),
        )

        if was_created:
            created += 1
        else:
            updated += 1

        if brand_source.brand_id:
            mapped += 1
        else:
            unmapped += 1

    return {
        "raw_document_id": (
            raw_document.id
        ),
        "products": len(products),
        "brands": len(grouped),
        "created": created,
        "updated": updated,
        "mapped": mapped,
        "unmapped": unmapped,
    }


# =========================================================
# OPERATING PIPELINE
# =========================================================


def normalize_pending_musinsa_raw_documents(
    *,
    limit: int | None = None,
) -> dict:
    """
    운영용 MUSINSA 정규화 진입점.

    대상:
    - MUSINSA
    - CrawlRun SUCCESS
    - RawDocument PENDING
    - document_type RANKING / PRODUCT

    각 RawDocument는 독립적으로 처리한다.

    성공:
        normalization_status = SUCCESS

    실패:
        normalization_status = FAILED
        normalization_error 저장
    """

    queryset = (
        RawDocument.objects
        .select_related(
            "crawl_run",
            "crawl_run__source",
            "crawl_run__crawl_target",
        )
        .filter(
            crawl_run__status=(
                CrawlRun.Status.SUCCESS
            ),
            crawl_run__source__code__iexact=(
                "MUSINSA"
            ),
            normalization_status=(
                RawDocument
                .NormalizationStatus
                .PENDING
            ),
            document_type__in=[
                "RANKING",
                "PRODUCT",
            ],
        )
        .order_by("id")
    )

    if limit is not None:
        queryset = queryset[:limit]

    raw_documents = list(
        queryset
    )

    normalizer = MusinsaNormalizer()
    s3_client = _get_s3_client()

    total = len(raw_documents)

    success_count = 0
    failed_count = 0

    total_products = 0
    total_brands = 0

    created = 0
    updated = 0
    mapped = 0
    unmapped = 0

    errors = []

    for raw_document in raw_documents:

        # -------------------------------------------------
        # PROCESSING
        # -------------------------------------------------

        raw_document.normalization_status = (
            RawDocument
            .NormalizationStatus
            .PROCESSING
        )

        raw_document.normalization_error = None

        raw_document.save(
            update_fields=[
                "normalization_status",
                "normalization_error",
            ]
        )

        try:
            result = (
                _normalize_musinsa_raw_document(
                    raw_document=raw_document,
                    normalizer=normalizer,
                    s3_client=s3_client,
                )
            )

            # ---------------------------------------------
            # SUCCESS
            # ---------------------------------------------

            raw_document.normalization_status = (
                RawDocument
                .NormalizationStatus
                .SUCCESS
            )

            raw_document.normalized_at = (
                timezone.now()
            )

            raw_document.normalization_error = (
                None
            )

            raw_document.save(
                update_fields=[
                    "normalization_status",
                    "normalized_at",
                    "normalization_error",
                ]
            )

            success_count += 1

            total_products += (
                result["products"]
            )

            total_brands += (
                result["brands"]
            )

            created += (
                result["created"]
            )

            updated += (
                result["updated"]
            )

            mapped += (
                result["mapped"]
            )

            unmapped += (
                result["unmapped"]
            )

        except Exception as exc:

            # ---------------------------------------------
            # FAILED
            # ---------------------------------------------

            raw_document.normalization_status = (
                RawDocument
                .NormalizationStatus
                .FAILED
            )

            raw_document.normalization_error = (
                str(exc)
            )

            raw_document.save(
                update_fields=[
                    "normalization_status",
                    "normalization_error",
                ]
            )

            failed_count += 1

            errors.append({
                "raw_document_id": (
                    raw_document.id
                ),
                "error": str(exc),
            })

    return {
        "source": "MUSINSA",

        "target_raw_documents": (
            total
        ),

        "success": (
            success_count
        ),

        "failed": (
            failed_count
        ),

        "products": (
            total_products
        ),

        "brands": (
            total_brands
        ),

        "brand_source_created": (
            created
        ),

        "brand_source_updated": (
            updated
        ),

        "mapped": (
            mapped
        ),

        "unmapped": (
            unmapped
        ),

        "errors": errors,
    }


# =========================================================
# RETRY FAILED
# =========================================================


def retry_failed_musinsa_raw_documents(
    *,
    limit: int | None = None,
) -> int:
    """
    FAILED RawDocument를 다시 PENDING으로 돌린다.

    실제 정규화는
    normalize_pending_musinsa_raw_documents()
    를 다시 실행하면 된다.
    """

    queryset = (
        RawDocument.objects
        .filter(
            crawl_run__status=(
                CrawlRun.Status.SUCCESS
            ),
            crawl_run__source__code__iexact=(
                "MUSINSA"
            ),
            normalization_status=(
                RawDocument
                .NormalizationStatus
                .FAILED
            ),
            document_type__in=[
                "RANKING",
                "PRODUCT",
            ],
        )
        .order_by("id")
    )

    if limit is not None:
        ids = list(
            queryset.values_list(
                "id",
                flat=True,
            )[:limit]
        )

        queryset = (
            RawDocument.objects
            .filter(
                id__in=ids,
            )
        )

    return queryset.update(
        normalization_status=(
            RawDocument
            .NormalizationStatus
            .PENDING
        ),
        normalization_error=None,
        normalized_at=None,
    )