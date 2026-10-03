from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.core.models import ProductSource, ProductTerm


# ============================================================
# ProductTerm relation mapping
# ============================================================

RELATION_BY_TERM_TYPE = {
    "ITEM": "HAS_ITEM",
    "MATERIAL": "HAS_MATERIAL",
    "COLOR": "HAS_COLOR",
    "STYLE": "HAS_STYLE",
    "TPO": "HAS_TPO",
}


RELATION_BY_ATTRIBUTE_TYPE = {
    "FIT": "HAS_FIT",
    "SILHOUETTE": "HAS_SILHOUETTE",
    "NECKLINE": "HAS_NECKLINE",
    "SLEEVE": "HAS_SLEEVE",
    "LENGTH": "HAS_LENGTH",
    "SHAPE": "HAS_SHAPE",
    "DETAIL": "HAS_DETAIL",
    "PATTERN": "HAS_DETAIL",
}


# ============================================================
# ProductSource.attributes["normalized"]에 저장할
# FEEDIT 표준 semantic attribute
#
# color_count 같은 structural/meta 값은 저장하지 않는다.
# ============================================================

NORMALIZED_ATTRIBUTE_KEYS = {
    "item",
    "material",
    "color",
    "fit",
    "silhouette",
    "neckline",
    "sleeve",
    "length",
    "shape",
    "detail",
    "style",
    "tpo",
    "gender",
    "season",
    "size",
    "production_type",
    "pattern",
}


# ============================================================
# Normalized attributes cleaner
# ============================================================

def _clean_normalized_attributes(
    result: dict[str, Any],
) -> dict[str, list[Any]]:

    raw_attributes = (
        result.get("product_attributes")
        or {}
    )

    if not isinstance(raw_attributes, dict):
        return {}

    cleaned: dict[str, list[Any]] = {}

    for raw_key, rows in raw_attributes.items():

        key = str(raw_key).strip().lower()

        if not key:
            continue

        # color_count 등의 structural/meta 필드 제외
        if key not in NORMALIZED_ATTRIBUTE_KEYS:
            continue

        # 기존 코드는 rows가 항상 list라고 가정했기 때문에
        # color_count=3 같은 scalar에서 TypeError가 발생했다.
        #
        # semantic attribute에서도 혹시 scalar가 들어오는 경우를
        # 안전하게 단일 원소 iterable로 처리한다.
        if isinstance(rows, (list, tuple, set)):
            iterable = rows

        else:
            iterable = [rows]

        values: list[Any] = []

        for row in iterable:

            if isinstance(row, dict):
                value = row.get("value")

                if value in (None, ""):
                    value = (
                        row.get("canonical_name")
                        or row.get("canonical")
                        or row.get("name")
                    )

            else:
                value = row

            if value in (None, ""):
                continue

            if value in values:
                continue

            values.append(value)

        if values:
            cleaned[key] = values

    return cleaned


# ============================================================
# ProductTerm relation type
# ============================================================

def _relation_type(
    evidence: dict[str, Any],
) -> str | None:

    attribute_type = str(
        evidence.get("attribute_type")
        or ""
    ).strip().upper()

    term_type = str(
        evidence.get("term_type")
        or ""
    ).strip().upper()

    return (
        RELATION_BY_ATTRIBUTE_TYPE.get(
            attribute_type
        )
        or RELATION_BY_TERM_TYPE.get(
            term_type
        )
        or (
            "HAS_DETAIL"
            if term_type == "DETAIL"
            else None
        )
    )


# ============================================================
# STEP02 writer
# ============================================================
@transaction.atomic
def save_step02_result(
    *,
    product_source_id: int,
    result: dict[str, Any],
) -> dict[str, Any]:

    product_source = (
        ProductSource.objects
        .select_for_update()
        .get(
            id=product_source_id
        )
    )

    # ========================================================
    # 1. normalized_name
    #
    # 최종 상품명은 core_name을 우선 사용한다.
    # core_name이 없으면 normalized_name,
    # 그것도 없으면 source_name으로 fallback.
    # ========================================================

    normalized_name = str(
        result.get("core_name")
        or result.get("normalized_name")
        or ""
    ).strip()

    if not normalized_name:
        normalized_name = (
            product_source.source_name
            or ""
        ).strip()

    # ========================================================
    # 2. 기존 attributes
    # ========================================================

    attributes = dict(
        product_source.attributes
        or {}
    )

    # 과거 STEP02 분석 결과 제거
    attributes.pop(
        "feedit_analysis",
        None,
    )

    attributes.pop(
        "normalized",
        None,
    )

    # ========================================================
    # 3. 현재 STEP02 normalized attributes
    # ========================================================

    normalized_attributes = (
        _clean_normalized_attributes(
            result
        )
    )

    # ========================================================
    # 4. PRODUCT_CODE 추출
    #
    # _extract_product_codes()에서 이미:
    #
    # - structural blocked span 적용
    # - SIZE 제외
    # - COLOR_COUNT 제외
    # - PRODUCT_META 제외
    # - SEASON 등 구조값 제외
    # - HIGH confidence만 허용
    #
    # 된 결과만 들어온다고 가정한다.
    # ========================================================

    product_codes = (
        _extract_product_codes(
            result
        )
    )

    selected_product_code = None
    style_no_updated = False

    if product_codes:

        meta = dict(
            normalized_attributes.get(
                "meta"
            )
            or {}
        )

        # ----------------------------------------------------
        # 단일 후보
        # ----------------------------------------------------

        if len(product_codes) == 1:

            candidate = (
                product_codes[0]
            )

            selected_product_code = str(
                candidate.get("code")
                or ""
            ).strip()

            if selected_product_code:

                meta[
                    "product_code"
                ] = selected_product_code

                meta[
                    "product_code_type"
                ] = (
                    candidate.get(
                        "type"
                    )
                )

                meta[
                    "product_code_confidence"
                ] = (
                    candidate.get(
                        "confidence"
                    )
                )

        # ----------------------------------------------------
        # 복수 후보
        #
        # 어느 코드가 대표 style_no인지 판단하지 않는다.
        # evidence만 보존한다.
        # ----------------------------------------------------

        else:

            meta[
                "product_codes"
            ] = product_codes

        normalized_attributes[
            "meta"
        ] = meta

    # ========================================================
    # 5. attributes.normalized 저장
    # ========================================================

    attributes[
        "normalized"
    ] = normalized_attributes

    # ========================================================
    # 6. style_no 보완
    #
    # 우선순위:
    #
    # 플랫폼 원본 style_no
    #     >
    # STEP02 단일 PRODUCT_CODE
    #
    # 기존 style_no가 있으면 절대 덮어쓰지 않는다.
    # ========================================================

    existing_style_no = (
        product_source.style_no
        or ""
    ).strip()

    if (
        not existing_style_no
        and selected_product_code
    ):
        product_source.style_no = (
            selected_product_code
        )

        style_no_updated = True

    # ========================================================
    # 7. ProductSource 저장
    # ========================================================

    product_source.normalized_name = (
        normalized_name
    )

    product_source.attributes = (
        attributes
    )

    update_fields = [
        "normalized_name",
        "attributes",
    ]

    if style_no_updated:
        update_fields.append(
            "style_no"
        )

    update_fields.append(
        "updated_at"
    )

    product_source.save(
        update_fields=update_fields
    )

    # ========================================================
    # 8. ProductTerm 재구축
    #
    # STEP02 분석 결과를 현재 ProductTerm의
    # source of truth로 사용한다.
    # ========================================================

    ProductTerm.objects.filter(
        product_source=product_source
    ).delete()

    term_rows: list[
        ProductTerm
    ] = []

    seen: set[
        tuple[int, str]
    ] = set()

    for evidence in (
        result.get(
            "known_evidence"
        )
        or []
    ):

        if not isinstance(
            evidence,
            dict,
        ):
            continue

        term_id = evidence.get(
            "term_id"
        )

        relation_type = (
            _relation_type(
                evidence
            )
        )

        if not term_id:
            continue

        if not relation_type:
            continue

        try:
            term_id = int(
                term_id
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        key = (
            term_id,
            relation_type,
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        term_rows.append(
            ProductTerm(
                product_source=product_source,
                term_id=term_id,
                relation_type=relation_type,
            )
        )

    if term_rows:
        ProductTerm.objects.bulk_create(
            term_rows,
            ignore_conflicts=True,
        )

    # ========================================================
    # 9. Result
    # ========================================================

    return {
        "product_source_id":
            product_source.id,

        "source_name":
            product_source.source_name,

        "normalized_name":
            normalized_name,

        "style_no":
            product_source.style_no,

        "style_no_updated":
            style_no_updated,

        "product_code":
            selected_product_code,

        "product_codes":
            product_codes,

        "normalized_attributes":
            normalized_attributes,

        "product_terms":
            len(term_rows),
    }
    
def _extract_product_codes(
    result: dict[str, Any],
) -> list[dict[str, str]]:

    structural_attributes = (
        result.get(
            "structural_attributes"
        )
        or {}
    )

    if not isinstance(
        structural_attributes,
        dict,
    ):
        return []

    rows = (
        structural_attributes.get(
            "product_codes"
        )
        or []
    )

    if not isinstance(
        rows,
        list,
    ):
        return []

    result_rows = []
    seen = set()

    for row in rows:

        if not isinstance(
            row,
            dict,
        ):
            continue

        code = str(
            row.get("code")
            or ""
        ).strip()

        code_type = str(
            row.get("type")
            or ""
        ).strip().upper()

        confidence = str(
            row.get("confidence")
            or ""
        ).strip().upper()

        if not code:
            continue

        # 자동 승격은 HIGH만 허용
        if confidence != "HIGH":
            continue

        if code_type not in {
            "PRODUCT_CODE",
            "STYLE_CODE",
        }:
            continue

        key = code.casefold()

        if key in seen:
            continue

        seen.add(key)

        result_rows.append({
            "code": code,
            "type": code_type,
            "confidence": confidence,
        })

    return result_rows