from __future__ import annotations

from typing import Any

from apps.core.models import TextDocument
from pipeline.step02_normalization.text.pipeline import TextNormalizationPipeline


def run_text_step02(*, text_document_ids: list[int]) -> dict[str, Any]:
    """LIVE TextDocument -> Text STEP02 -> TextTermMention 진입점."""
    document_ids = list(dict.fromkeys(
        int(value)
        for value in (text_document_ids or [])
        if value not in (None, "")
    ))

    if not document_ids:
        return {
            "status": "SKIPPED",
            "reason": "NO_TEXT_DOCUMENT",
            "target_count": 0,
            "success": 0,
            "failed": 0,
            "deleted": 0,
            "created": 0,
            "errors": [],
        }

    existing_ids = set(
        TextDocument.objects.filter(id__in=document_ids)
        .values_list("id", flat=True)
    )

    pipeline = TextNormalizationPipeline()
    success = 0
    failed = 0
    total_deleted = 0
    total_created = 0
    errors: list[dict[str, Any]] = []

    for document_id in document_ids:
        if document_id not in existing_ids:
            failed += 1
            errors.append({
                "document_id": document_id,
                "error_type": "TextDocumentNotFound",
                "error_message": "TextDocument를 찾을 수 없습니다.",
            })
            continue

        try:
            result = pipeline.run_by_id(document_id)
            success += 1
            total_deleted += int(result.deleted or 0)
            total_created += int(result.created or 0)
        except Exception as exc:
            failed += 1
            errors.append({
                "document_id": document_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })

    status = "SUCCESS" if failed == 0 else ("PARTIAL" if success else "FAILED")
    return {
        "status": status,
        "target_count": len(document_ids),
        "success": success,
        "failed": failed,
        "deleted": total_deleted,
        "created": total_created,
        "errors": errors,
    }
