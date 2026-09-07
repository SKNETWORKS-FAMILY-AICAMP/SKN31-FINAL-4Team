# backend/apps/core/services/normalization.py

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


# ============================================================
# NORMALIZATION SERVICE
# ============================================================


class NormalizationService:

    @staticmethod
    def _get_source(
        source_code: str,
    ) -> Source:
        return Source.objects.get(
            code__iexact=source_code,
        )

    @classmethod
    def normalize_product_source(
        cls,
        *,
        source_code: str,
        parsed: dict,
    ) -> dict:

        source = cls._get_source(
            source_code
        )

        normalizer = MusinsaNormalizer(
            source=source,
        )

        return (
            normalizer
            .normalize_product_source(
                parsed
            )
        )


# ============================================================
# S3
# ============================================================


def _get_s3_client():
    return boto3.client("s3")


def _load_raw_json(
    raw_document: RawDocument,
    *,
    s3_client,
) -> dict:

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
            "JSON이 dict가 아닙니다."
        )

    return data


def _extract_payload(
    raw_data: dict,
) -> dict:
    """
    지원 형태:

    {
        "payload": {...}
    }

    {
        "data": {...}
    }

    {
        ...원본...
    }
    """

    payload = raw_data.get("payload")

    if isinstance(payload, dict):
        return payload

    data = raw_data.get("data")

    if isinstance(data, dict):
        if (
            "products" in data
            or "brand" in data
            or "product" in data
        ):
            return data

    return raw_data


def _extract_products(
    payload: dict,
) -> list[dict]:
    """
    Ranking 문서:
        {"products": [{...}, {...}]}

    단일 상품 문서:
        {"brand": {...}, "product": {...}}
    """
    products = payload.get("products")

    if isinstance(products, list):
        return [
            item
            for item in products
            if isinstance(item, dict)
        ]

    if isinstance(
        payload.get("product"),
        dict,
    ):
        return [payload]

    return []


# ============================================================
# RAW DOCUMENT QUERY
# ============================================================


def _get_musinsa_raw_documents(
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
            crawl_run_id=crawl_run_id,
        )

    if limit is not None:
        queryset = queryset[:limit]

    return queryset


# ============================================================
# ONE-PASS S3 -> SOURCE DB
# ============================================================


def normalize_pending_musinsa(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    """
    MUSINSA RawDocument(S3) -> DB source layer.

    상품 하나마다 한 번만 실행:

        BrandSource
            ↓
        CategorySource
            ↓
        ProductSource

    별도의 brand/category/product_source batch를
    순서대로 따로 돌릴 필요가 없다.
    """

    raw_documents = (
        _get_musinsa_raw_documents(
            limit=limit,
            crawl_run_id=crawl_run_id,
        )
    )

    s3 = _get_s3_client()

    result = {
        "raw_documents": 0,
        "products": 0,
        "product_created": 0,
        "product_updated": 0,

        "brand_linked": 0,
        "brand_unmapped": 0,
        "brand_missing": 0,

        "category_linked": 0,
        "category_unmapped": 0,
        "category_missing": 0,

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

            products = _extract_products(
                payload
            )

            print(
                f"[RAW #{raw_document.id}] "
                f"products={len(products)}"
            )

            for parsed in products:
                result["products"] += 1

                try:
                    normalized = (
                        NormalizationService
                        .normalize_product_source(
                            source_code="MUSINSA",
                            parsed=parsed,
                        )
                    )

                    if normalized.get("created"):
                        result[
                            "product_created"
                        ] += 1
                    else:
                        result[
                            "product_updated"
                        ] += 1

                    brand_result = (
                        normalized.get(
                            "brand_result"
                        )
                        or {}
                    )

                    category_result = (
                        normalized.get(
                            "category_result"
                        )
                        or {}
                    )

                    if (
                        brand_result.get(
                            "brand_source"
                        )
                        is None
                    ):
                        result[
                            "brand_missing"
                        ] += 1
                    elif brand_result.get(
                        "matched"
                    ):
                        result[
                            "brand_linked"
                        ] += 1
                    else:
                        result[
                            "brand_unmapped"
                        ] += 1

                    if (
                        category_result.get(
                            "category_source"
                        )
                        is None
                    ):
                        result[
                            "category_missing"
                        ] += 1
                    elif category_result.get(
                        "matched"
                    ):
                        result[
                            "category_linked"
                        ] += 1
                    else:
                        result[
                            "category_unmapped"
                        ] += 1

                    product_source = (
                        normalized.get(
                            "product_source"
                        )
                    )

                    print(
                        "[NORMALIZED]",
                        getattr(
                            product_source,
                            "source_product_id",
                            None,
                        ),
                        "|",
                        getattr(
                            product_source,
                            "source_name",
                            None,
                        ),
                        "| brand=",
                        brand_result.get(
                            "matched_by"
                        ),
                        "| category=",
                        category_result.get(
                            "matched_by"
                        ),
                    )

                except Exception as exc:
                    result["failed"] += 1

                    result["errors"].append(
                        {
                            "raw_document_id": (
                                raw_document.id
                            ),
                            "error_type": (
                                exc
                                .__class__
                                .__name__
                            ),
                            "error_message": (
                                str(exc)
                            ),
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
                        exc
                        .__class__
                        .__name__
                    ),
                    "error_message": str(exc),
                }
            )

    return result


# ============================================================
# BACKWARD-COMPATIBILITY WRAPPERS
# ============================================================
# 예전 shell/test 코드가 아래 함수를 import하고 있어도
# 당장 깨지지 않게 둔다.
# 단, 새 코드에서는 normalize_pending_musinsa()만 사용한다.


def normalize_pending_musinsa_product_sources(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    return normalize_pending_musinsa(
        limit=limit,
        crawl_run_id=crawl_run_id,
    )


def normalize_pending_musinsa_brands(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    return normalize_pending_musinsa(
        limit=limit,
        crawl_run_id=crawl_run_id,
    )


def normalize_pending_musinsa_categories(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    return normalize_pending_musinsa(
        limit=limit,
        crawl_run_id=crawl_run_id,
    )
