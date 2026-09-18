from __future__ import annotations

import json

import boto3
from django.conf import settings

from apps.core.models import RawDocument

from analysis.source_ingestion.kream import (
    KreamNormalizer,
)


def normalize_kream_raw_document(
    *,
    raw_document_id: int,
) -> dict:

    raw_document = (
        RawDocument.objects
        .select_related(
            "source",
            "crawl_run",
        )
        .get(
            pk=raw_document_id
        )
    )

    if (
        raw_document.source.code.upper()
        != "KREAM"
    ):
        raise ValueError(
            "KREAM RawDocument가 아닙니다."
        )

    # ============================================================
    # S3 RAW LOAD
    # ============================================================

    s3 = boto3.client(
        "s3",
        region_name=getattr(
            settings,
            "AWS_REGION",
            "ap-northeast-2",
        ),
    )

    response = s3.get_object(
        Bucket=raw_document.s3_bucket,
        Key=raw_document.s3_key,
    )

    raw = json.loads(
        response["Body"]
        .read()
        .decode("utf-8")
    )

    if not isinstance(raw, dict):
        raise ValueError(
            "KREAM S3 JSON root가 dict가 아닙니다."
        )

    # ============================================================
    # NORMALIZE
    # ============================================================

    normalizer = KreamNormalizer(
        source=raw_document.source,
    )

    result = normalizer.normalize_payload(
        raw,
        create_snapshot=True,
    )

    errors = (
        result.get("errors")
        or []
    )

    if errors:
        raise RuntimeError(
            f"KREAM 정규화 실패 "
            f"{len(errors)}건 | "
            f"first={errors[0]}"
        )

    return {
        "raw_document_id": (
            raw_document.id
        ),
        "processed": result.get(
            "processed",
            0,
        ),
        "success": result.get(
            "success",
            0,
        ),
        "failed": result.get(
            "failed",
            0,
        ),
        "errors": [],
    }


