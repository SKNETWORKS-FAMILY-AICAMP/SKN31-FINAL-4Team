from __future__ import annotations

import json
from typing import Any

import boto3
from django.conf import settings

from apps.core.models import RawDocument

from analysis.source_ingestion.zigzag import (
    ZigzagNormalizer,
)


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=getattr(
            settings,
            "AWS_REGION",
            "ap-northeast-2",
        ),
    )


def _load_raw_json(
    raw_document: RawDocument,
) -> dict[str, Any]:
    if not raw_document.s3_key:
        raise ValueError(
            f"RawDocument #{raw_document.id} s3_key가 없습니다."
        )

    bucket = (
        raw_document.s3_bucket
        or getattr(
            settings,
            "AWS_STORAGE_BUCKET_NAME",
            None,
        )
    )

    if not bucket:
        raise ValueError(
            f"RawDocument #{raw_document.id} S3 bucket을 찾지 못했습니다."
        )

    s3 = _get_s3_client()

    response = s3.get_object(
        Bucket=bucket,
        Key=raw_document.s3_key,
    )

    raw = json.loads(
        response["Body"]
        .read()
        .decode("utf-8")
    )

    if not isinstance(raw, dict):
        raise ValueError(
            f"RawDocument #{raw_document.id} S3 JSON root가 dict가 아닙니다."
        )

    return raw


def ingest_zigzag_raw_document(
    *,
    raw_document_id: int,
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """
    Zigzag CNV RawDocument 1건을 source layer에 적재한다.

    RawDocument
      -> S3 JSON
      -> ZigzagNormalizer.normalize_cnv_payload()
      -> BrandSource
      -> CategorySource
      -> ProductSource
      -> ProductSourceSnapshot
    """

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

    source_code = (
        raw_document.source.code
        or ""
    ).upper().strip()

    if source_code != "ZIGZAG":
        raise ValueError(
            f"RawDocument #{raw_document.id}는 "
            f"ZIGZAG가 아닙니다. "
            f"source={raw_document.source.code}"
        )

    document_type = (
        raw_document.document_type
        or ""
    ).upper().strip()

    if document_type not in {
        "CNV_CATEGORY",
        "RANKING",
    }:
        raise ValueError(
            "지원하지 않는 Zigzag "
            f"RawDocument type입니다: {document_type}"
        )

    raw = _load_raw_json(
        raw_document
    )

    normalizer = ZigzagNormalizer(
        source=raw_document.source
    )

    result = (
        normalizer
        .normalize_cnv_payload(
            raw,
            create_snapshot=create_snapshot,
        )
    )

    errors = (
        result.get("errors")
        or []
    )

    if errors:
        raise RuntimeError(
            "ZIGZAG CNV source ingestion 실패 "
            f"{len(errors)}건 | "
            f"first={errors[0]}"
        )

    return {
        "raw_document_id":
            raw_document.id,

        "document_type":
            document_type,

        "source":
            raw_document.source.code,

        "schema":
            result.get("schema"),

        "observed_at":
            result.get("observed_at"),

        "category_id":
            result.get("category_id"),

        "category_name":
            result.get("category_name"),

        "order":
            result.get("order"),

        "observation_count":
            result.get(
                "observation_count",
                0,
            ),

        "unique_product_count":
            result.get(
                "unique_product_count",
                0,
            ),

        "processed_count":
            result.get(
                "processed_count",
                0,
            ),

        "brand_sources":
            result.get(
                "brand_sources",
                {},
            ),

        "category_sources":
            result.get(
                "category_sources",
                {},
            ),

        "product_sources":
            result.get(
                "product_sources",
                {},
            ),

        "snapshots":
            result.get(
                "snapshots",
                {},
            ),

        "errors": [],
    }


def ingest_latest_zigzag_raw_document(
    *,
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """
    가장 최근 Zigzag CNV RawDocument 1건을 수동 재처리.
    smoke test용.
    """

    raw_document = (
        RawDocument.objects
        .filter(
            source__code__iexact="ZIGZAG",
            document_type__iexact="CNV_CATEGORY",
        )
        .order_by(
            "-collected_at",
            "-id",
        )
        .first()
    )

    if raw_document is None:
        raise RuntimeError(
            "ZIGZAG CNV_CATEGORY RawDocument가 없습니다."
        )

    return ingest_zigzag_raw_document(
        raw_document_id=raw_document.id,
        create_snapshot=create_snapshot,
    )


def ingest_zigzag_crawl_run(
    *,
    crawl_run_id: int,
    create_snapshot: bool = True,
) -> dict[str, Any]:
    """
    특정 CrawlRun에서 생성된 Zigzag CNV RawDocument를 전부 재처리.
    """

    raw_documents = (
        RawDocument.objects
        .filter(
            source__code__iexact="ZIGZAG",
            document_type__iexact="CNV_CATEGORY",
            crawl_run_id=crawl_run_id,
        )
        .order_by("id")
    )

    summary = {
        "crawl_run_id":
            crawl_run_id,

        "raw_documents":
            0,

        "success":
            0,

        "failed":
            0,

        "processed_products":
            0,

        "errors":
            [],
    }

    for raw_document in raw_documents:

        summary[
            "raw_documents"
        ] += 1

        try:
            result = ingest_zigzag_raw_document(
                raw_document_id=(
                    raw_document.id
                ),
                create_snapshot=(
                    create_snapshot
                ),
            )

            summary[
                "success"
            ] += 1

            summary[
                "processed_products"
            ] += (
                result.get(
                    "processed_count",
                    0,
                )
                or 0
            )

        except Exception as exc:

            summary[
                "failed"
            ] += 1

            summary[
                "errors"
            ].append(
                {
                    "raw_document_id":
                        raw_document.id,

                    "error_type":
                        type(exc).__name__,

                    "error":
                        str(exc),
                }
            )

    return summary
