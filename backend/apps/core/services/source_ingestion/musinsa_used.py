from __future__ import annotations

from collection.musinsa_used.normalization import normalize_musinsa_used_preview
from apps.core.models import RawDocument

from .common import ingest_preview_raw_document


def ingest_musinsa_used_raw_document(*, raw_document_id: int) -> dict:
    def build_preview(product, raw_document, payload):
        return normalize_musinsa_used_preview(
            product,
            observed_at=raw_document.collected_at.isoformat(),
        )

    return ingest_preview_raw_document(
        raw_document_id=raw_document_id,
        source_code="MUSINSA_USED",
        preview_builder=build_preview,
    )


def ingest_pending_musinsa_used_raw_documents(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    queryset = RawDocument.objects.filter(
        source__code__iexact="MUSINSA_USED",
        document_type__in=["RANKING", "PRODUCT"],
        normalization_status__in=[
            RawDocument.NormalizationStatus.PENDING,
            RawDocument.NormalizationStatus.FAILED,
        ],
    ).order_by("id")
    if crawl_run_id is not None:
        queryset = queryset.filter(crawl_run_id=crawl_run_id)
    if limit is not None:
        queryset = queryset[:limit]
    result = {"source": "MUSINSA_USED", "success": 0, "failed": 0, "products": 0, "errors": []}
    for raw_document in queryset:
        try:
            one = ingest_musinsa_used_raw_document(raw_document_id=raw_document.id)
            result["success"] += 1
            result["products"] += one["products"]
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append({"raw_document_id": raw_document.id, "error": str(exc)})
    return result
