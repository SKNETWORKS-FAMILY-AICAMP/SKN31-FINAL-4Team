from __future__ import annotations

from apps.core.models import RawDocument

from analysis.source_ingestion.musinsa import (
    MusinsaNormalizer,
)

from .common import (
    extract_payload,
    get_raw_documents,
    get_s3_client,
    load_raw_json,
)


def extract_products(
    payload: dict,
) -> list[dict]:
    """
    MUSINSA Ranking:
        {"products": [{...}, ...]}

    단일 상품:
        {
            "brand": {...},
            "product": {...}
        }
    """

    products = payload.get(
        "products"
    )

    if isinstance(
        products,
        list,
    ):
        return [
            item
            for item in products
            if isinstance(
                item,
                dict,
            )
        ]

    if isinstance(
        payload.get("product"),
        dict,
    ):
        return [
            payload
        ]

    return []


def ingest_musinsa_raw_document(
    *,
    raw_document_id: int,
) -> dict:
    """
    MUSINSA RawDocument 하나를 source layer로 적재한다.

    흐름:

        RawDocument
        -> BrandSource
        -> CategorySource
        -> ProductSource
        -> ProductSourceSnapshot
    """

    # ============================================================
    # RAW DOCUMENT
    # ============================================================

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
        raw_document
        .source
        .code
        .upper()
        != "MUSINSA"
    ):
        raise ValueError(
            "MUSINSA RawDocument가 아닙니다."
        )

    # ============================================================
    # LOAD S3 RAW
    # ============================================================

    s3 = get_s3_client()

    raw_data = load_raw_json(
        raw_document,
        s3_client=s3,
    )

    payload = extract_payload(
        raw_data
    )

    products = extract_products(
        payload
    )

    # ============================================================
    # NORMALIZER
    # ============================================================

    normalizer = (
        MusinsaNormalizer(
            source=raw_document.source,
        )
    )

    # ============================================================
    # RESULT
    # ============================================================

    result = {
        "raw_document_id":
            raw_document.id,

        "products":
            0,

        "product_created":
            0,

        "product_updated":
            0,

        "snapshot_created":
            0,

        "snapshot_updated":
            0,

        "brand_linked":
            0,

        "brand_unmapped":
            0,

        "brand_missing":
            0,

        "category_linked":
            0,

        "category_unmapped":
            0,

        "category_missing":
            0,

        "failed":
            0,

        "errors":
            [],
    }

    # ============================================================
    # PRODUCTS
    # ============================================================

    for index, parsed in enumerate(
        products,
        start=1,
    ):
        result[
            "products"
        ] += 1

        try:

            # ====================================================
            # 1. BRAND SOURCE
            # ====================================================

            brand_data = (
                parsed.get("brand")
                if isinstance(
                    parsed.get("brand"),
                    dict,
                )
                else {}
            )

            product_data = (
                parsed.get("product")
                if isinstance(
                    parsed.get("product"),
                    dict,
                )
                else {}
            )

            # parser에 따라 brand 정보가 product 쪽에만
            # 들어있는 케이스가 있으므로 보강한다.
            merged_brand_data = dict(
                brand_data
            )

            if not (
                merged_brand_data.get(
                    "brand_code"
                )
                or merged_brand_data.get(
                    "brand_id"
                )
            ):
                fallback_brand_code = (
                    product_data.get(
                        "brand_code"
                    )
                    or product_data.get(
                        "brand_id"
                    )
                )

                if fallback_brand_code:
                    merged_brand_data[
                        "brand_code"
                    ] = (
                        fallback_brand_code
                    )

            if not (
                merged_brand_data.get(
                    "name_ko"
                )
                or merged_brand_data.get(
                    "brand_name"
                )
                or merged_brand_data.get(
                    "name_en"
                )
            ):
                fallback_brand_name = (
                    product_data.get(
                        "brand_name"
                    )
                    or product_data.get(
                        "brand_name_ko"
                    )
                )

                if fallback_brand_name:
                    merged_brand_data[
                        "brand_name"
                    ] = (
                        fallback_brand_name
                    )

            brand_result = (
                normalizer
                .normalize_brand(
                    merged_brand_data
                )
            )

            source_brand = (
                brand_result.get(
                    "brand_source"
                )
            )

            # ====================================================
            # BRAND RESULT
            # ====================================================

            if source_brand is None:
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


            # ====================================================
            # 2. CATEGORY SOURCE
            # ====================================================

            category_result = (
                normalizer
                .normalize_category(
                    product_data
                )
            )

            source_category = (
                category_result.get(
                    "category_source"
                )
            )

            # ====================================================
            # CATEGORY RESULT
            # ====================================================

            if source_category is None:
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


            # ====================================================
            # 3. PRODUCT SOURCE
            # ====================================================

            normalized = (
                normalizer
                .normalize_product_source(
                    parsed,
                    source_brand=(
                        source_brand
                    ),
                    source_category=(
                        source_category
                    ),
                )
            )

            product_source = (
                normalized.get(
                    "product_source"
                )
            )

            if product_source is None:
                raise ValueError(
                    "ProductSource 생성 결과가 없습니다."
                )

            if normalized.get(
                "created"
            ):
                result[
                    "product_created"
                ] += 1

            else:
                result[
                    "product_updated"
                ] += 1


            # ====================================================
            # 4. PRODUCT SOURCE SNAPSHOT
            # ====================================================

            snapshot_result = (
                normalizer
                .normalize_snapshot(
                    parsed,
                    product_source=(
                        product_source
                    ),
                )
            )

            if snapshot_result.get(
                "created"
            ):
                result[
                    "snapshot_created"
                ] += 1

            else:
                result[
                    "snapshot_updated"
                ] += 1


        except Exception as exc:

            result[
                "failed"
            ] += 1

            result[
                "errors"
            ].append(
                {
                    "raw_document_id":
                        raw_document.id,

                    "product_index":
                        index,

                    "error_type":
                        exc
                        .__class__
                        .__name__,

                    "error_message":
                        str(exc),
                }
            )

    return result


def ingest_all_musinsa_rankings(
    *,
    limit: int | None = None,
    crawl_run_id: int | None = None,
) -> dict:
    """
    MUSINSA Ranking RawDocument들을 일괄 재적재한다.
    """

    raw_documents = (
        get_raw_documents(
            source_code="MUSINSA",
            document_type="RANKING",
            limit=limit,
            crawl_run_id=(
                crawl_run_id
            ),
        )
    )

    result = {
        "raw_documents":
            0,

        "success":
            0,

        "failed":
            0,

        "products":
            0,

        "product_created":
            0,

        "product_updated":
            0,

        "snapshot_created":
            0,

        "snapshot_updated":
            0,

        "errors":
            [],
    }

    for raw_document in (
        raw_documents
    ):
        result[
            "raw_documents"
        ] += 1

        try:

            one = (
                ingest_musinsa_raw_document(
                    raw_document_id=(
                        raw_document.id
                    )
                )
            )

            result[
                "products"
            ] += (
                one.get(
                    "products",
                    0,
                )
                or 0
            )

            result[
                "product_created"
            ] += (
                one.get(
                    "product_created",
                    0,
                )
                or 0
            )

            result[
                "product_updated"
            ] += (
                one.get(
                    "product_updated",
                    0,
                )
                or 0
            )

            result[
                "snapshot_created"
            ] += (
                one.get(
                    "snapshot_created",
                    0,
                )
                or 0
            )

            result[
                "snapshot_updated"
            ] += (
                one.get(
                    "snapshot_updated",
                    0,
                )
                or 0
            )

            if one.get(
                "failed",
                0,
            ):
                result[
                    "failed"
                ] += 1

            else:
                result[
                    "success"
                ] += 1

            if one.get(
                "errors"
            ):
                result[
                    "errors"
                ].extend(
                    one[
                        "errors"
                    ]
                )

        except Exception as exc:

            result[
                "failed"
            ] += 1

            result[
                "errors"
            ].append(
                {
                    "raw_document_id":
                        raw_document.id,

                    "error_type":
                        exc
                        .__class__
                        .__name__,

                    "error_message":
                        str(exc),
                }
            )

    return result