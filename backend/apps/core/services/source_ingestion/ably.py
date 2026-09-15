from __future__ import annotations

from collection.ably.normalization import normalize_ably_preview
from apps.core.models import RawDocument

from .common import ingest_preview_raw_document


def ingest_ably_raw_document(*, raw_document_id: int) -> dict:
    def build_preview(product, raw_document, payload):
        ranking = dict(payload.get("ranking") or {})
        ranking["collected_at"] = raw_document.collected_at.isoformat()
        return normalize_ably_preview(product, ranking)

    return ingest_preview_raw_document(
        raw_document_id=raw_document_id,
        source_code="ABLY",
        preview_builder=build_preview,
    )


def ingest_pending_ably_raw_documents(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    queryset = RawDocument.objects.filter(
        source__code__iexact="ABLY",
        document_type__iexact="RANKING",
        normalization_status__in=[
            RawDocument.NormalizationStatus.PENDING,
            RawDocument.NormalizationStatus.FAILED,
        ],
    ).order_by("id")
    if crawl_run_id is not None:
        queryset = queryset.filter(crawl_run_id=crawl_run_id)
    if limit is not None:
        queryset = queryset[:limit]
    return _ingest_many(queryset)


def _ingest_many(raw_documents) -> dict:
    result = {"source": "ABLY", "success": 0, "failed": 0, "products": 0, "errors": []}
    for raw_document in raw_documents:
        try:
            one = ingest_ably_raw_document(raw_document_id=raw_document.id)
            result["success"] += 1
            result["products"] += one["products"]
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append({"raw_document_id": raw_document.id, "error": str(exc)})
    return result
