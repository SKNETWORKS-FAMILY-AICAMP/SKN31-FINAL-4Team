from __future__ import annotations

from apps.core.models import RawDocument

from analysis.source_ingestion.musinsa import (
    MusinsaNormalizer,
)

from .common import (
    extract_payload,
    get_raw_documents,
    get_s3_client,
    load_raw_json,
)


def extract_products(
    payload: dict,
) -> list[dict]:
    """
    MUSINSA Ranking:
        {"products": [{...}, ...]}

    단일 상품:
        {"brand": {...}, "product": {...}}
    """
    products = payload.get("products")

    if isinstance(products, list):
        return [
            item
            for item in products
            if isinstance(item, dict)
        ]

    if isinstance(
        payload.get("product"),
        dict,
    ):
        return [payload]

    return []


def ingest_musinsa_raw_document(
    *,
    raw_document_id: int,
) -> dict:
    raw_document = (
        RawDocument.objects
        .select_related(
            "source",
            "crawl_run",
        )
        .get(pk=raw_document_id)
    )

    if (
        raw_document.source.code.upper()
        != "MUSINSA"
    ):
        raise ValueError(
            "MUSINSA RawDocument가 아닙니다."
        )

    s3 = get_s3_client()

    raw_data = load_raw_json(
        raw_document,
        s3_client=s3,
    )

    payload = extract_payload(
        raw_data
    )

    products = extract_products(
        payload
    )

    normalizer = MusinsaNormalizer(
        source=raw_document.source,
    )

    result = {
        "raw_document_id": raw_document.id,
        "products": 0,
        "product_created": 0,
        "product_updated": 0,
        "brand_linked": 0,
        "brand_unmapped": 0,
        "brand_missing": 0,
        "category_linked": 0,
        "category_unmapped": 0,
        "category_missing": 0,
        "failed": 0,
        "errors": [],
    }

    for parsed in products:
        result["products"] += 1

        try:
            normalized = (
                normalizer
                .normalize_product_source(
                    parsed
                )
            )

            if normalized.get("created"):
                result["product_created"] += 1
            else:
                result["product_updated"] += 1

            brand_result = (
                normalized.get(
                    "brand_result"
                )
                or {}
            )

            category_result = (
                normalized.get(
                    "category_result"
                )
                or {}
            )

            if (
                brand_result.get(
                    "brand_source"
                )
                is None
            ):
                result["brand_missing"] += 1
            elif brand_result.get("matched"):
                result["brand_linked"] += 1
            else:
                result["brand_unmapped"] += 1

            if (
                category_result.get(
                    "category_source"
                )
                is None
            ):
                result[
                    "category_missing"
                ] += 1
            elif category_result.get(
                "matched"
            ):
                result[
                    "category_linked"
                ] += 1
            else:
                result[
                    "category_unmapped"
                ] += 1

        except Exception as exc:
            result["failed"] += 1
            result["errors"].append({
                "raw_document_id": (
                    raw_document.id
                ),
                "error_type": (
                    exc.__class__.__name__
                ),
                "error_message": str(exc),
            })

    return result


def ingest_all_musinsa_rankings(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    raw_documents = get_raw_documents(
        source_code="MUSINSA",
        document_type="RANKING",
        limit=limit,
        crawl_run_id=crawl_run_id,
    )

    result = {
        "raw_documents": 0,
        "success": 0,
        "failed": 0,
        "products": 0,
        "errors": [],
    }

    for raw_document in raw_documents:
        result["raw_documents"] += 1

        try:
            one = ingest_musinsa_raw_document(
                raw_document_id=(
                    raw_document.id
                )
            )

            result["success"] += 1
            result["products"] += (
                one.get("products", 0)
                or 0
            )

            if one.get("errors"):
                result["errors"].extend(
                    one["errors"]
                )

        except Exception as exc:
            result["failed"] += 1
            result["errors"].append({
                "raw_document_id": (
                    raw_document.id
                ),
                "error_type": (
                    exc.__class__.__name__
                ),
                "error_message": str(exc),
            })

    return result
