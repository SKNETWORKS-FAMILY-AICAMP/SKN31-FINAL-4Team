from __future__ import annotations

import re


# ============================================================
# BASIC TEXT
# ============================================================


def clean_text(value) -> str | None:
    """
    문자열 기본 정리.

    - None -> None
    - 앞뒤 공백 제거
    - 빈 문자열 -> None
    """
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def normalize_text(value) -> str | None:
    """
    일반 문자열 정규화.

    - clean_text
    - 소문자 변환
    - 연속 공백 1칸으로 통일
    """
    value = clean_text(value)

    if value is None:
        return None

    value = value.lower()
    value = re.sub(r"\s+", " ", value)

    return value.strip() or None


# ============================================================
# BRAND
# ============================================================


def normalize_brand_name(value) -> str | None:
    """
    브랜드명 비교용 정규화.

    예:
        "NIKE"        -> "nike"
        "Nike "       -> "nike"
        "New Balance" -> "newbalance"
        "New-Balance" -> "newbalance"
        "Levi's"      -> "levis"
    """
    value = clean_text(value)

    if value is None:
        return None

    value = value.lower()

    value = (
        value.replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
    )

    value = re.sub(
        r"[^0-9a-z가-힣]+",
        "",
        value,
    )

    return value or None


def extract_brand_data(
    brand_data: dict | None,
) -> dict | None:
    """
    플랫폼 parser가 반환한 brand dict에서 공통 필드를 추출한다.
    """
    if not isinstance(brand_data, dict):
        return None

    source_brand_id = clean_text(
        brand_data.get("brand_code")
        or brand_data.get("brand_id")
    )

    source_brand_name = clean_text(
        brand_data.get("name_ko")
        or brand_data.get("brand_name")
        or brand_data.get("name_en")
    )

    source_brand_name_en = clean_text(
        brand_data.get("name_en")
    )

    if (
        source_brand_id is None
        and source_brand_name is None
    ):
        return None

    return {
        "source_brand_id": source_brand_id,
        "source_brand_name": source_brand_name,
        "source_brand_name_en": source_brand_name_en,
        "normalized_name": normalize_brand_name(
            source_brand_name
            or source_brand_id
        ),
        "normalized_name_en": normalize_brand_name(
            source_brand_name_en
        ),
    }


# ============================================================
# CATEGORY
# ============================================================


def normalize_category_name(value) -> str | None:
    """
    카테고리명 비교용 정규화.
    """
    return normalize_text(value)


def normalize_category_path(value) -> str | None:
    """
    카테고리 path 문자열 정리.

    "바지>데님 팬츠" -> "바지 > 데님 팬츠"
    """
    value = clean_text(value)

    if value is None:
        return None

    parts = [
        clean_text(part)
        for part in re.split(
            r"\s*>\s*",
            value,
        )
    ]

    parts = [
        part
        for part in parts
        if part
    ]

    if not parts:
        return None

    return " > ".join(parts)


def extract_deepest_category(
    product_data: dict | None,
) -> dict | None:
    """
    parser 결과의 product.category에서
    가장 깊은 유효 플랫폼 카테고리를 선택한다.

    반환:
    {
        "source_category_id": "003002",
        "source_category_name": "데님 팬츠",
        "source_category_path": "바지 > 데님 팬츠",
        "normalized_name": "데님 팬츠",
        "depth": 2,
    }
    """
    if not isinstance(product_data, dict):
        return None

    category_data = product_data.get("category")

    if not isinstance(category_data, dict):
        return None

    categories = []

    for depth in range(1, 5):
        code = clean_text(
            category_data.get(
                f"depth{depth}_code"
            )
        )

        name = clean_text(
            category_data.get(
                f"depth{depth}_name"
            )
        )

        # source_category_id는 플랫폼 원본 ID이므로
        # code가 없는 depth를 임의 ID로 만들지 않는다.
        if code is None:
            continue

        categories.append(
            {
                "depth": depth,
                "code": code,
                "name": name,
            }
        )

    if not categories:
        return None

    deepest = categories[-1]

    path_parts = [
        item["name"]
        for item in categories
        if item["name"]
    ]

    source_category_path = (
        " > ".join(path_parts)
        if path_parts
        else None
    )

    return {
        "source_category_id": deepest["code"],
        "source_category_name": deepest["name"],
        "source_category_path": source_category_path,
        "normalized_name": normalize_category_name(
            deepest["name"]
        ),
        "depth": deepest["depth"],
    }


# ============================================================
# PRODUCT
# ============================================================


def normalize_product_name(value) -> str | None:
    return normalize_text(value)
