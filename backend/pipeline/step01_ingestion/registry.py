from __future__ import annotations

from typing import Any

from .brand_mapping import (
    resolve_step01_brands,
)


def run_step01_ingestion(
    *,
    source_code: str,
    raw_document_id: int,
) -> dict[str, Any] | None:

    code = (
        source_code
        or ""
    ).strip().lower()

    # ========================================================
    # Platform ingestion
    # ========================================================

    if code == "musinsa":
        from pipeline.step01_ingestion.musinsa import (
            MusinsaIngestion,
        )

        result = MusinsaIngestion().run(
            raw_document_id=raw_document_id,
        )

    elif code == "kream":
        from pipeline.step01_ingestion.kream import (
            KreamIngestion,
        )

        result = KreamIngestion().run(
            raw_document_id=raw_document_id,
        )

    elif code == "musinsa_used":
        from pipeline.step01_ingestion.musinsa_used import (
            MusinsaUsedIngestion,
        )

        result = MusinsaUsedIngestion().run(
            raw_document_id=raw_document_id,
        )

    elif code == "zigzag":
        from pipeline.step01_ingestion.zigzag import (
            ZigzagIngestion,
        )

        result = ZigzagIngestion().run(
            raw_document_id=raw_document_id,
        )

    elif code == "ably":
        from pipeline.step01_ingestion.ably import AblyIngestion
        result = AblyIngestion().run(raw_document_id=raw_document_id)

    else:
        return None

    if result is None:
        return None

    # ========================================================
    # ProductSource IDs
    # ========================================================

    product_source_ids = list(
        dict.fromkeys(
            int(value)
            for value in (
                result.get(
                    "product_source_ids"
                )
                or []
            )
            if value not in (
                None,
                "",
            )
        )
    )

    result[
        "product_source_ids"
    ] = product_source_ids

    # ========================================================
    # Commerce Review -> TextDocument(REVIEW)
    #
    # source_ingestion legacy path is not used.
    # The reviewed RAW is bridged inside current STEP01.
    # ========================================================
    if code in {"musinsa", "zigzag", "ably"}:
        from pipeline.step01_ingestion.reviews import (
            ingest_and_sync_raw_document_reviews,
        )

        review_result = ingest_and_sync_raw_document_reviews(
            raw_document_id=raw_document_id,
        )
        result["review_ingestion"] = review_result
        result["text_document_ids"] = list(dict.fromkeys(
            int(value)
            for value in (review_result.get("text_document_ids") or [])
            if value not in (None, "")
        ))
    else:
        result["text_document_ids"] = []

    # ========================================================
    # STEP01 Brand Mapping
    #
    # BrandSource 생성 직후
    # FEEDIT Brand를 즉시 resolve한다.
    # ========================================================

    brand_result = resolve_step01_brands(
        product_source_ids
    )

    result["brand_mapping"] = {
        "total":
            brand_result.total,

        "already_mapped":
            brand_result.already_mapped,

        "mapped_by_source_name":
            brand_result.mapped_by_source_name,

        "mapped_by_brand_exact":
            brand_result.mapped_by_brand_exact,

        "unmapped":
            brand_result.unmapped,
    }

    return result