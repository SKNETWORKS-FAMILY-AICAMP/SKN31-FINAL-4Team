from __future__ import annotations

import json

import boto3
from django.conf import settings

from apps.core.models import RawDocument, Source


def get_source(
    source_code: str,
) -> Source:
    return Source.objects.get(
        code__iexact=source_code,
    )


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=getattr(
            settings,
            "AWS_REGION",
            "ap-northeast-2",
        ),
    )


def load_raw_json(
    raw_document: RawDocument,
    *,
    s3_client=None,
) -> dict:
    s3_client = (
        s3_client
        or get_s3_client()
    )

    response = s3_client.get_object(
        Bucket=raw_document.s3_bucket,
        Key=raw_document.s3_key,
    )

    body = response["Body"].read()

    data = json.loads(
        body.decode("utf-8")
    )

    if not isinstance(data, dict):
        raise ValueError(
            f"RawDocument #{raw_document.id} "
            "JSON root가 dict가 아닙니다."
        )

    return data


def extract_payload(
    raw_data: dict,
) -> dict:
    payload = raw_data.get("payload")

    if isinstance(payload, dict):
        return payload

    data = raw_data.get("data")

    if isinstance(data, dict):
        return data

    return raw_data


def get_raw_documents(
    *,
    source_code: str,
    document_type: str = "RANKING",
    limit: int | None = None,
    crawl_run_id: int | None = None,
):
    queryset = (
        RawDocument.objects
        .select_related(
            "source",
            "crawl_run",
        )
        .filter(
            source__code__iexact=source_code,
            document_type__iexact=document_type,
        )
        .order_by("id")
    )

    if crawl_run_id is not None:
        queryset = queryset.filter(
            crawl_run_id=crawl_run_id,
        )

    if limit is not None:
        queryset = queryset[:limit]

    return queryset
