from __future__ import annotations

import json

import boto3

from apps.core.models import (
    RawDocument,
    Source,
)

from analysis.normalization.musinsa import (
    MusinsaNormalizer,
)


class NormalizationService:
    @staticmethod
    def _get_source(
        source_code: str,
    ) -> Source:
        return Source.objects.get(
            code__iexact=source_code,
        )

    @classmethod
    def normalize_brand(
        cls,
        *,
        source_code: str,
        parsed: dict,
    ) -> dict:
        source = cls._get_source(
            source_code
        )

        if source.code.upper() != "MUSINSA":
            raise NotImplementedError(
                f"지원하지 않는 source: {source.code}"
            )

        normalizer = MusinsaNormalizer(
            source=source
        )

        brand_data = (
            parsed.get("brand")
            or {}
        )

        return normalizer.normalize_brand(
            brand_data
        )

    @classmethod
    def normalize_category(
        cls,
        *,
        source_code: str,
        parsed: dict,
    ) -> dict:
        source = cls._get_source(
            source_code
        )

        if source.code.upper() != "MUSINSA":
            raise NotImplementedError(
                f"지원하지 않는 source: {source.code}"
            )

        normalizer = MusinsaNormalizer(
            source=source
        )

        product_data = (
            parsed.get("product")
            or {}
        )

        return normalizer.normalize_category(
            product_data
        )


def _get_s3_client():
    return boto3.client("s3")


def _load_raw_document_json(
    *,
    raw_document: RawDocument,
    s3_client=None,
) -> dict:
    s3 = (
        s3_client
        or _get_s3_client()
    )

    response = s3.get_object(
        Bucket=raw_document.s3_bucket,
        Key=raw_document.s3_key,
    )

    body = (
        response["Body"]
        .read()
        .decode("utf-8")
    )

    data = json.loads(body)

    if not isinstance(data, dict):
        raise ValueError(
            f"RawDocument #{raw_document.id}: "
            "S3 JSON 최상위 데이터가 dict가 아닙니다."
        )

    return data


def _extract_parsed_payload(
    raw_data: dict,
) -> dict:
    if not isinstance(
        raw_data,
        dict,
    ):
        return {}

    payload = raw_data.get(
        "payload"
    )

    if isinstance(
        payload,
        dict,
    ):
        return payload

    data = raw_data.get(
        "data"
    )

    if (
        isinstance(data, dict)
        and (
            "product" in data
            or "brand" in data
        )
    ):
        return data

    return raw_data


def _get_pending_musinsa_raw_documents(
    *,
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
            source__code__iexact="MUSINSA",
            document_type__iexact="RANKING",
        )
        .order_by("id")
    )

    if crawl_run_id is not None:
        queryset = queryset.filter(
            crawl_run_id=crawl_run_id
        )

    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def normalize_pending_musinsa_brands(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    raw_documents = (
        _get_pending_musinsa_raw_documents(
            limit=limit,
            crawl_run_id=crawl_run_id,
        )
    )

    s3 = _get_s3_client()

    result = {
        "detected": 0,
        "created": 0,
        "updated": 0,
        "matched": 0,
        "unmatched": 0,
        "failed": 0,
        "errors": [],
    }

    for raw_document in raw_documents:
        result["detected"] += 1

        try:
            raw_data = (
                _load_raw_document_json(
                    raw_document=raw_document,
                    s3_client=s3,
                )
            )

            parsed = (
                _extract_parsed_payload(
                    raw_data
                )
            )

            normalized = (
                NormalizationService
                .normalize_brand(
                    source_code="MUSINSA",
                    parsed=parsed,
                )
            )

            brand_source = (
                normalized.get(
                    "brand_source"
                )
            )

            matched_by = (
                normalized.get(
                    "matched_by"
                )
            )

            if normalized.get(
                "matched"
            ):
                result["matched"] += 1
            else:
                result["unmatched"] += 1

            if brand_source is not None:
                if matched_by in {
                    "NORMALIZED_NAME",
                    "UNMAPPED",
                }:
                    result["created"] += 1
                else:
                    result["updated"] += 1

        except Exception as exc:
            result["failed"] += 1

            result["errors"].append(
                {
                    "raw_document_id": (
                        raw_document.id
                    ),
                    "external_id": (
                        raw_document.external_id
                    ),
                    "error_type": (
                        exc.__class__.__name__
                    ),
                    "error_message": str(exc),
                }
            )

    return result


def normalize_pending_musinsa_categories(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:

    raw_documents = (
        _get_musinsa_raw_documents(
            limit=limit,
            crawl_run_id=crawl_run_id,
        )
    )

    s3 = _get_s3_client()

    result = {
        "raw_documents": 0,
        "detected": 0,
        "matched": 0,
        "unmatched": 0,
        "created": 0,
        "existing": 0,
        "failed": 0,
        "errors": [],
    }

    for raw_document in raw_documents:

        result["raw_documents"] += 1

        try:
            raw_data = _load_raw_json(
                raw_document,
                s3_client=s3,
            )

            payload = _extract_payload(
                raw_data
            )

            products = (
                payload.get("products")
                or []
            )

            print(
                f"[RAW #{raw_document.id}] "
                f"products={len(products)}"
            )

            for parsed in products:

                result["detected"] += 1

                try:
                    normalized = (
                        NormalizationService
                        .normalize_category(
                            source_code="MUSINSA",
                            parsed=parsed,
                        )
                    )

                    matched_by = (
                        normalized.get(
                            "matched_by"
                        )
                    )

                    source_category = (
                        normalized.get(
                            "source_category"
                        )
                    )

                    if normalized.get("matched"):
                        result["matched"] += 1
                    else:
                        result["unmatched"] += 1

                    if matched_by == "NORMALIZED_NAME":
                        result["created"] += 1

                    elif matched_by == "SOURCE_ID":
                        result["existing"] += 1

                    print(
                        "[CATEGORY]",
                        source_category,
                        "->",
                        normalized.get("category"),
                        f"({matched_by})",
                    )

                except Exception as exc:

                    result["failed"] += 1

                    result["errors"].append(
                        {
                            "raw_document_id": (
                                raw_document.id
                            ),
                            "error_type": (
                                exc.__class__.__name__
                            ),
                            "error_message": str(exc),
                        }
                    )

        except Exception as exc:

            result["failed"] += 1

            result["errors"].append(
                {
                    "raw_document_id": (
                        raw_document.id
                    ),
                    "error_type": (
                        exc.__class__.__name__
                    ),
                    "error_message": str(exc),
                }
            )

    return result