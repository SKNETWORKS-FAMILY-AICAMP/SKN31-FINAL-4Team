from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import boto3

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    Brand,
    BrandSource,
    Category,
    CategoryAlias,
    CrawlRun,
    Product,
    ProductSource,
    ProductSourceSnapshot,
    RawDocument,
)

from analysis.commerce.musinsa.normalizer import (
    MusinsaNormalizer,
)
from analysis.commerce.zigzag.normalizer import (
    ZigzagNormalizer,
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
    allow_auto_match: bool = True,
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

    if allow_auto_match:
        (
            matched_brand,
            mapping_method,
        ) = _find_brand_exact(
            name=source_brand_name,
            english_name=source_brand_name_en,
        )
    else:
        matched_brand = None
        mapping_method = None

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


# =========================================================
# ZIGZAG L0 -> L1 NORMALIZE AND PERSIST
# =========================================================


def _extract_zigzag_shop_payload(
    item: dict[str, Any],
) -> dict | None:
    """Return a Zigzag shop as a BrandSource payload."""

    shop = item.get("brand") or {}
    source_brand_id = shop.get("source_brand_id") or item.get("shop_domain")

    if not source_brand_id:
        return None

    source_brand_id = str(source_brand_id).strip()
    if not source_brand_id:
        return None

    return {
        "source_brand_id": source_brand_id,
        "source_brand_name": shop.get("source_brand_name") or item.get("shop_name"),
        "source_brand_name_en": shop.get("source_brand_name_en"),
        "source_brand_url": shop.get("source_brand_url"),
    }


def _as_observed_at(
    value: Any,
    *,
    default,
):
    """Keep a collection timestamp when present and fall back to RawDocument."""

    if isinstance(value, datetime):
        observed_at = value
    elif isinstance(value, str) and value:
        observed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return default

    if timezone.is_naive(observed_at):
        return timezone.make_aware(observed_at, timezone.get_current_timezone())

    return observed_at


def _find_category_dictionary_exact(
    *,
    source,
    source_category_name: str,
) -> Category | None:
    """Match a product category only by a unique canonical or alias exact match."""

    canonical = list(
        Category.objects.filter(
            category_type=Category.CategoryType.PRODUCT,
            status=Category.Status.ACTIVE,
            name__iexact=source_category_name.strip(),
        ).order_by("id")[:2]
    )
    if len(canonical) == 1:
        return canonical[0]

    category_ids = list(
        CategoryAlias.objects.filter(
            source=source,
            source_category_name__iexact=source_category_name.strip(),
            category__category_type=Category.CategoryType.PRODUCT,
            category__status=Category.Status.ACTIVE,
        ).values_list("category_id", flat=True).distinct()[:2]
    )
    if len(category_ids) == 1:
        return Category.objects.get(pk=category_ids[0])

    return None


def _resolve_zigzag_category_mapping(
    *,
    source,
    source_category_name: str | None,
    source_category_code: str | None,
) -> tuple[CategoryAlias | None, bool]:
    """Resolve a Zigzag category with the existing CategoryAlias table."""

    if not source_category_name:
        return None, False

    source_category_id = str(
        source_category_code or normalize_text(source_category_name)
    )[:255]
    mapping = (
        CategoryAlias.objects
        .select_related("category")
        .filter(
            source=source,
            source_category_id=source_category_id,
        )
        .first()
    )
    if mapping:
        return mapping, False

    category = _find_category_dictionary_exact(
        source=source,
        source_category_name=source_category_name,
    )
    if category is None:
        return None, True

    mapping, created = CategoryAlias.objects.update_or_create(
        source=source,
        source_category_id=source_category_id,
        defaults={
            "source_category_name": source_category_name,
            "category": category,
        },
    )
    return mapping, created


def _upsert_zigzag_brand_source(
    *,
    source,
    payload: dict[str, Any],
    detected_count: int,
) -> tuple[BrandSource, bool, bool]:
    """Store and exact-match a Zigzag shop in the existing BrandSource schema."""

    brand_source, created = _upsert_brand_source(
        source=source,
        source_brand_id=payload["source_brand_id"],
        source_brand_name=payload.get("source_brand_name"),
        source_brand_name_en=payload.get("source_brand_name_en"),
        source_brand_url=payload.get("source_brand_url"),
        detected_count=detected_count,
        # Existing Brand names are matched only when the shop name is exact.
        allow_auto_match=True,
    )

    # Existing Zigzag rows may have been created before auto matching was
    # enabled. Retry only ordinary UNMAPPED rows; preserve manual decisions.
    if brand_source.mapping_status == BrandSource.MappingStatus.UNMAPPED:
        matched_brand, mapping_method = _find_brand_exact(
            name=payload.get("source_brand_name"),
            english_name=payload.get("source_brand_name_en"),
        )
        if matched_brand:
            brand_source.brand = matched_brand
            brand_source.mapping_status = BrandSource.MappingStatus.AUTO_MAPPED
            brand_source.mapping_method = mapping_method
            brand_source.mapping_confidence = 1
            brand_source.save(
                update_fields=[
                    "brand",
                    "mapping_status",
                    "mapping_method",
                    "mapping_confidence",
                    "updated_at",
                ]
            )

    return brand_source, created, False


def _upsert_zigzag_product(
    *,
    source,
    item: dict[str, Any],
    brand_source: BrandSource | None,
    category_mapping: CategoryAlias | None,
    default_observed_at,
) -> tuple[bool, bool]:
    """Persist one source-owned product and its combined price/ranking snapshot.

    The current schema has one ``ProductSourceSnapshot`` table for both price
    and ranking observation data, so one upsert is used for the two concerns.
    """

    source_uid = str(item["source_uid"])
    observed_at = _as_observed_at(
        item.get("observed_at"),
        default=default_observed_at,
    )
    category = category_mapping.category if category_mapping else None
    canonical_name = item.get("name") or source_uid
    normalized_name = item.get("normalized_name") or normalize_text(canonical_name)

    product_source = (
        ProductSource.objects
        .select_related("product")
        .filter(source=source, source_product_id=source_uid)
        .first()
    )
    product_created = False

    product_attributes = {
        "source": "ZIGZAG",
        "source_uid": source_uid,
        "product_key": item["product_key"],
        "match_method": item["match_method"],
        "match_score": item["match_score"],
        "source_category_code": item.get("source_category_code"),
        "source_category_path": item.get("source_category_path") or [],
        "source_category_name": item.get("source_category_name"),
        "category_mapping_status": "MAPPED" if category_mapping else "UNMAPPED",
        "category_code": category.code if category else None,
        "thumbnail_url": item.get("thumbnail_url"),
        "brand_source_id": brand_source.id if brand_source else None,
        "brand_mapping_status": brand_source.mapping_status if brand_source else None,
    }

    if product_source is None:
        # This is deliberately source-scoped identity.  A Zigzag product is
        # never matched to a product from a different platform here.
        product = Product.objects.create(
            brand=brand_source.brand if brand_source and brand_source.brand_id else None,
            category=category,
            canonical_name=canonical_name,
            normalized_name=normalized_name,
            attributes=product_attributes,
        )
        product_source = ProductSource.objects.create(
            product=product,
            source=source,
            source_product_id=source_uid,
            product_url=item.get("source_url"),
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            status=ProductSource.Status.ACTIVE,
        )
        product_created = True
    else:
        product = product_source.product
        product_update_fields = []

        resolved_brand = brand_source.brand if brand_source and brand_source.brand_id else None
        if product.brand_id != (resolved_brand.id if resolved_brand else None):
            product.brand = resolved_brand
            product_update_fields.append("brand")

        if item.get("name") and product.canonical_name != canonical_name:
            product.canonical_name = canonical_name
            product_update_fields.append("canonical_name")
        if item.get("name") and product.normalized_name != normalized_name:
            product.normalized_name = normalized_name
            product_update_fields.append("normalized_name")
        if (
            category_mapping is not None
            and product.category_id != (category.id if category else None)
        ):
            product.category = category
            product_update_fields.append("category")

        attributes = dict(product.attributes or {})
        attributes.update(product_attributes)
        if attributes != product.attributes:
            product.attributes = attributes
            product_update_fields.append("attributes")

        if product_update_fields:
            product_update_fields.append("updated_at")
            product.save(update_fields=product_update_fields)

        source_update_fields = []
        if item.get("source_url") and product_source.product_url != item["source_url"]:
            product_source.product_url = item["source_url"]
            source_update_fields.append("product_url")
        if product_source.last_seen_at != observed_at:
            product_source.last_seen_at = observed_at
            source_update_fields.append("last_seen_at")
        if product_source.status != ProductSource.Status.ACTIVE:
            product_source.status = ProductSource.Status.ACTIVE
            source_update_fields.append("status")
        if not product_source.first_seen_at:
            product_source.first_seen_at = observed_at
            source_update_fields.append("first_seen_at")
        if source_update_fields:
            source_update_fields.append("updated_at")
            product_source.save(update_fields=source_update_fields)

    ranking_category_id = item.get("ranking_category_id")
    snapshot_defaults = {
        "list_price": item.get("regular_price"),
        "sale_price": item.get("sale_price"),
        "discount_rate": item.get("discount_rate"),
        "rank_position": item.get("rank"),
        "ranking_scope": str(ranking_category_id) if ranking_category_id is not None else None,
        "ranking_context": {
            "ranking_category_id": ranking_category_id,
        },
        "rating": item.get("review_score"),
        "review_count": item.get("review_count"),
        "stock_status": item.get("sales_status"),
        "platform_metrics": {
            "shop_domain": item.get("shop_domain"),
            "shop_bookmark_count": item.get("shop_bookmark_count"),
            "store_sale_price": item.get("store_sale_price"),
            "source_category_code": item.get("source_category_code"),
            "source_category_path": item.get("source_category_path") or [],
        },
    }

    _, snapshot_created = ProductSourceSnapshot.objects.update_or_create(
        product_source=product_source,
        observed_at=observed_at,
        defaults=snapshot_defaults,
    )

    return product_created, snapshot_created


def _normalize_zigzag_raw_document(
    *,
    raw_document: RawDocument,
    normalizer: ZigzagNormalizer,
    s3_client,
) -> dict:
    """Normalize one Zigzag RawDocument and persist its L1 entities."""

    raw = _load_raw_json(raw_document=raw_document, s3_client=s3_client)

    if raw_document.document_type == "RANKING":
        products = normalizer.normalize_ranking(
            raw,
            observed_at=raw_document.collected_at,
        ).get("products", [])
    elif raw_document.document_type == "PRODUCT":
        products = [
            normalizer.normalize_product(
                raw,
                observed_at=raw_document.collected_at,
            )
        ]
    else:
        raise ValueError(f"Unsupported document_type: {raw_document.document_type}")

    source = raw_document.source
    grouped_shops: dict[str, dict[str, Any]] = {}
    for item in products:
        payload = _extract_zigzag_shop_payload(item)
        if payload is None:
            continue
        source_brand_id = payload["source_brand_id"]
        grouped = grouped_shops.setdefault(
            source_brand_id,
            {**payload, "count": 0},
        )
        grouped["count"] += 1
        for key in ("source_brand_name", "source_brand_name_en", "source_brand_url"):
            if not grouped.get(key) and payload.get(key):
                grouped[key] = payload[key]

    brand_sources: dict[str, BrandSource] = {}
    created = updated = brand_mapped = brand_pending = 0
    for payload in grouped_shops.values():
        brand_source, was_created, _ = _upsert_zigzag_brand_source(
            source=source,
            payload=payload,
            detected_count=payload["count"],
        )
        brand_sources[payload["source_brand_id"]] = brand_source
        if was_created:
            created += 1
        else:
            updated += 1

        if brand_source.mapping_status in {
            BrandSource.MappingStatus.MANUAL_MAPPED,
            BrandSource.MappingStatus.AUTO_MAPPED,
        }:
            brand_mapped += 1
        else:
            brand_pending += 1

    category_mappings: dict[str, CategoryAlias] = {}
    category_mapped = category_pending = 0
    for item in products:
        source_category_name = item.get("source_category_name")
        if not source_category_name:
            continue
        normalized_name = normalize_text(source_category_name)
        if normalized_name in category_mappings:
            continue
        mapping, _ = _resolve_zigzag_category_mapping(
            source=source,
            source_category_name=source_category_name,
            source_category_code=item.get("source_category_code"),
        )
        if mapping is None:
            category_pending += 1
            continue
        category_mappings[normalized_name] = mapping
        category_mapped += 1

    product_created = snapshots_created = 0
    for item in products:
        shop = _extract_zigzag_shop_payload(item)
        brand_source = brand_sources.get(shop["source_brand_id"]) if shop else None
        category_mapping = category_mappings.get(
            normalize_text(item.get("source_category_name"))
        ) if item.get("source_category_name") else None
        was_created, snapshot_was_created = _upsert_zigzag_product(
            source=source,
            item=item,
            brand_source=brand_source,
            category_mapping=category_mapping,
            default_observed_at=raw_document.collected_at,
        )
        product_created += int(was_created)
        snapshots_created += int(snapshot_was_created)

    return {
        "raw_document_id": raw_document.id,
        "products": len(products),
        "product_created": product_created,
        "shops": len(grouped_shops),
        "brand_source_created": created,
        "brand_source_updated": updated,
        "brand_mapped": brand_mapped,
        "brand_pending": brand_pending,
        "category_mapped": category_mapped,
        "category_pending": category_pending,
        "snapshots": len(products),
        "snapshots_created": snapshots_created,
    }


def normalize_pending_zigzag_raw_documents(
    *,
    limit: int | None = None,
) -> dict:
    """Process pending Zigzag L0 documents one transaction at a time."""

    queryset = (
        RawDocument.objects
        .select_related("source", "crawl_run", "crawl_run__source")
        .filter(
            crawl_run__status=CrawlRun.Status.SUCCESS,
            source__code__iexact="ZIGZAG",
            normalization_status=RawDocument.NormalizationStatus.PENDING,
            document_type__in=["RANKING", "PRODUCT"],
        )
        .order_by("id")
    )
    if limit is not None:
        queryset = queryset[:limit]

    raw_documents = list(queryset)
    normalizer = ZigzagNormalizer()
    s3_client = _get_s3_client()
    summary = {
        "source": "ZIGZAG",
        "target_raw_documents": len(raw_documents),
        "success": 0,
        "failed": 0,
        "products": 0,
        "product_created": 0,
        "shops": 0,
        "brand_source_created": 0,
        "brand_source_updated": 0,
        "brand_mapped": 0,
        "brand_pending": 0,
        "category_mapped": 0,
        "category_pending": 0,
        # One ProductSourceSnapshot stores both price and ranking fields.
        "price_snapshots": 0,
        "ranking_snapshots": 0,
        "errors": [],
    }

    for raw_document in raw_documents:
        RawDocument.objects.filter(pk=raw_document.pk).update(
            normalization_status=RawDocument.NormalizationStatus.PROCESSING,
            normalization_error=None,
        )
        raw_document.normalization_status = RawDocument.NormalizationStatus.PROCESSING

        try:
            with transaction.atomic():
                result = _normalize_zigzag_raw_document(
                    raw_document=raw_document,
                    normalizer=normalizer,
                    s3_client=s3_client,
                )
                RawDocument.objects.filter(pk=raw_document.pk).update(
                    normalization_status=RawDocument.NormalizationStatus.SUCCESS,
                    normalization_error=None,
                    normalized_at=timezone.now(),
                )
        except Exception as exc:
            RawDocument.objects.filter(pk=raw_document.pk).update(
                normalization_status=RawDocument.NormalizationStatus.FAILED,
                normalization_error=str(exc),
            )
            summary["failed"] += 1
            summary["errors"].append({"raw_document_id": raw_document.id, "error": str(exc)})
            continue

        summary["success"] += 1
        for key in (
            "products",
            "product_created",
            "shops",
            "brand_source_created",
            "brand_source_updated",
            "brand_mapped",
            "brand_pending",
            "category_mapped",
            "category_pending",
        ):
            summary[key] += result[key]
        summary["price_snapshots"] += result["snapshots"]
        summary["ranking_snapshots"] += result["snapshots"]

    return summary


def retry_failed_zigzag_raw_documents(
    *,
    limit: int | None = None,
) -> int:
    """Return failed Zigzag documents to PENDING for a later explicit rerun."""

    queryset = (
        RawDocument.objects
        .filter(
            crawl_run__status=CrawlRun.Status.SUCCESS,
            source__code__iexact="ZIGZAG",
            normalization_status=RawDocument.NormalizationStatus.FAILED,
            document_type__in=["RANKING", "PRODUCT"],
        )
        .order_by("id")
    )
    if limit is not None:
        ids = list(queryset.values_list("id", flat=True)[:limit])
        queryset = RawDocument.objects.filter(id__in=ids)

    return queryset.update(
        normalization_status=RawDocument.NormalizationStatus.PENDING,
        normalization_error=None,
        normalized_at=None,
    )
