from __future__ import annotations

from apps.core.models import RawDocument

from analysis.source_ingestion.zigzag import ZigzagNormalizer

from .common import (
    get_raw_documents,
    get_s3_client,
    load_raw_json,
)


def ingest_zigzag_raw_document(
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
        != "ZIGZAG"
    ):
        raise ValueError(
            "ZIGZAG RawDocument가 아닙니다."
        )

    if (
        raw_document.document_type.upper()
        != "RANKING"
    ):
        raise ValueError(
            "ZIGZAG RANKING RawDocument가 아닙니다."
        )

    s3 = get_s3_client()

    raw = load_raw_json(
        raw_document,
        s3_client=s3,
    )

    normalizer = ZigzagNormalizer(
        source=raw_document.source,
    )

    result = (
        normalizer
        .normalize_ranking_payload(
            raw
        )
    )

    errors = (
        result.get("errors")
        or []
    )

    if errors:
        raise RuntimeError(
            "ZIGZAG source ingestion 실패 "
            f"{len(errors)}건 | "
            f"first={errors[0]}"
        )

    return {
        "raw_document_id": (
            raw_document.id
        ),
        "count": result.get(
            "count",
            0,
        ),
        "brand_sources": result.get(
            "brand_sources",
            {},
        ),
        "category_sources": result.get(
            "category_sources",
            {},
        ),
        "product_sources": result.get(
            "product_sources",
            {},
        ),
        "errors": [],
    }


def ingest_all_zigzag_rankings(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    raw_documents = get_raw_documents(
        source_code="ZIGZAG",
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
            normalized = (
                ingest_zigzag_raw_document(
                    raw_document_id=(
                        raw_document.id
                    )
                )
            )

            result["success"] += 1
            result["products"] += (
                normalized.get(
                    "count",
                    0,
                )
                or 0
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
