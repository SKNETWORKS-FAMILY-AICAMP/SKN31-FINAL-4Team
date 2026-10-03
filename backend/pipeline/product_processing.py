from __future__ import annotations

from typing import Any

from apps.core.models import ProductSource
from pipeline.step01_ingestion.registry import run_step01_ingestion
from pipeline.step02_normalization.pipeline import ProductNormalizationPipeline
from pipeline.step02_normalization.writer import save_step02_result
from pipeline.text_processing import run_text_step02


STEP02_SUPPORTED_SOURCES = {
    "musinsa",
    "musinsa_used",
    "zigzag",
    "kream",
    "ably",
}


def run_step01_step02(
    *,
    source_code: str,
    raw_document_id: int,
) -> dict[str, Any]:
    code = str(source_code or "").strip().lower()

    step01 = run_step01_ingestion(
        source_code=code,
        raw_document_id=raw_document_id,
    )

    if step01 is None:
        return {
            "step01": None,
            "step02": None,
        }

    product_source_ids = list(dict.fromkeys(
        int(value)
        for value in (step01.get("product_source_ids") or [])
        if value not in (None, "")
    ))

    if code not in STEP02_SUPPORTED_SOURCES:
        return {
            "step01": step01,
            "step02": {
                "status": "SKIPPED",
                "reason": "UNSUPPORTED_SOURCE",
                "source_code": code,
                "target_count": len(product_source_ids),
            },
        }

    if not product_source_ids:
        return {
            "step01": step01,
            "step02": {
                "status": "SKIPPED",
                "reason": "NO_PRODUCT_SOURCE",
                "source_code": code,
                "target_count": 0,
            },
        }

    # STEP01 결과에 포함된 ID만 처리한다.
    existing_ids = set(
        ProductSource.objects.filter(
            id__in=product_source_ids,
            source__code__iexact=code,
        ).values_list("id", flat=True)
    )

    pipeline = ProductNormalizationPipeline(source_code=code)

    success = 0
    failed = 0
    errors: list[dict[str, Any]] = []

    for product_source_id in product_source_ids:
        if product_source_id not in existing_ids:
            failed += 1
            errors.append({
                "product_source_id": product_source_id,
                "error_type": "ProductSourceNotFound",
                "error_message": "STEP01 결과 ProductSource를 찾을 수 없습니다.",
            })
            continue

        try:
            result = pipeline.run_by_id(product_source_id)
            save_step02_result(
                product_source_id=product_source_id,
                result=result,
            )
            success += 1
        except Exception as exc:
            failed += 1
            errors.append({
                "product_source_id": product_source_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })

    text_document_ids = list(dict.fromkeys(
        int(value)
        for value in (step01.get("text_document_ids") or [])
        if value not in (None, "")
    ))
    text_step02 = (
        run_text_step02(text_document_ids=text_document_ids)
        if text_document_ids
        else None
    )

    return {
        "step01": step01,
        "step02": {
            "status": "SUCCESS" if failed == 0 else "PARTIAL",
            "source_code": code,
            "target_count": len(product_source_ids),
            "success": success,
            "failed": failed,
            "errors": errors,
        },
        "text_step02": text_step02,
    }
