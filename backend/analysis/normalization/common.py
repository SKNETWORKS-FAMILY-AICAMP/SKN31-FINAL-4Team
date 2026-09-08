from __future__ import annotations

import re
from typing import Any

from apps.core.models import Brand, Style


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

def make_match_key(
    value: Any,
) -> str | None:
    """
    브랜드 / 스타일 비교용 임시 key.

    DB에 저장하지 않는다.
    """

    value = clean_text(value)

    if value is None:
        return None

    value = value.lower()

    value = (
        value
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
    )

    value = re.sub(
        r"[^0-9a-z가-힣]+",
        "",
        value,
    )

    return value or None


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

COUNTRY_CODE_MAP = {

    "대한민국": "KR",
    "한국": "KR",
    "KOREA": "KR",
    "SOUTH KOREA": "KR",
    "KR": "KR",

    "미국": "US",
    "USA": "US",
    "UNITED STATES": "US",
    "US": "US",

    "일본": "JP",
    "JAPAN": "JP",
    "JP": "JP",

    "프랑스": "FR",
    "FRANCE": "FR",
    "FR": "FR",

    "이탈리아": "IT",
    "ITALY": "IT",
    "IT": "IT",

    "영국": "GB",
    "UK": "GB",
    "UNITED KINGDOM": "GB",
    "GB": "GB",

    "독일": "DE",
    "GERMANY": "DE",
    "DE": "DE",

    "중국": "CN",
    "CHINA": "CN",
    "CN": "CN",

}


def normalize_country_code(
    value: Any,
) -> str | None:

    value = clean_text(value)

    if value is None:
        return None

    upper = value.upper()

    if upper in COUNTRY_CODE_MAP:
        return COUNTRY_CODE_MAP[upper]

    if value in COUNTRY_CODE_MAP:
        return COUNTRY_CODE_MAP[value]

    if len(upper) == 2:
        return upper

    return None


def clean_list(
    value: Any,
) -> list[str] | None:

    if value is None:
        return None

    if not isinstance(
        value,
        (list, tuple, set),
    ):
        value = [value]

    result = []

    seen = set()

    for item in value:

        # Zigzag:
        # {"value": "캐주얼"}
        if isinstance(item, dict):

            item = (
                item.get("value")
                or item.get("name")
                or item.get("label")
            )

        text = clean_text(item)

        if not text:
            continue

        if text in seen:
            continue

        seen.add(text)
        result.append(text)

    return result or None

def find_styles(
    values: Any,
) -> list[Style]:

    values = clean_list(values)

    if not values:
        return []

    wanted = {
        make_match_key(value)
        for value in values
        if make_match_key(value)
    }

    if not wanted:
        return []

    matches = []

    for style in Style.objects.all():

        candidates = [
            getattr(style, "name", None),
            getattr(style, "term", None),
        ]

        keys = {
            make_match_key(value)
            for value in candidates
            if make_match_key(value)
        }

        if wanted & keys:
            matches.append(style)

    return matches

def find_brand_exact(
    *,
    name: str | None,
    english_name: str | None = None,
) -> Brand | None:
    """
    FEEDIT Brand exact match.

    normalized 값을 DB에 저장하지 않고
    비교할 때만 key를 만든다.
    """

    name_key = make_match_key(name)

    en_key = make_match_key(
        english_name
    )

    if not name_key and not en_key:
        return None

    matches = []

    brands = (
        Brand.objects
        .filter(
            status=Brand.Status.ACTIVE,
        )
        .only(
            "id",
            "brand_code",
            "name",
            "english_name",
        )
    )

    for brand in brands:

        brand_name_key = (
            make_match_key(
                brand.name
            )
        )

        brand_en_key = (
            make_match_key(
                brand.english_name
            )
        )

        matched = False

        if (
            name_key
            and name_key
            in {
                brand_name_key,
                brand_en_key,
            }
        ):
            matched = True

        if (
            en_key
            and en_key
            in {
                brand_name_key,
                brand_en_key,
            }
        ):
            matched = True

        if matched:
            matches.append(
                brand
            )

    if len(matches) != 1:
        return None

    return matches[0]


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

# ============================================================
# ZIGZAG CATEGORY
# ============================================================


def extract_zigzag_categories(
    data: dict | None,
) -> list[dict]:
    """
    지그재그 raw / parsed 데이터에서
    카테고리 계층을 모두 추출한다.

    반환 예:
    [
        {
            "source_category_id": "100",
            "source_category_name": "상의",
            "source_category_path": "상의",
            "normalized_name": "상의",
            "depth": 1,
        },
        {
            "source_category_id": "101",
            "source_category_name": "티셔츠",
            "source_category_path": "상의 > 티셔츠",
            "normalized_name": "티셔츠",
            "depth": 2,
        },
    ]
    """
    if not isinstance(data, dict):
        return []

    category_data = (
        data.get("category")
        or data.get("categories")
        or {}
    )

    result = []

    # --------------------------------------------------------
    # case 1.
    # {
    #   "category": {
    #       "depth1_code": "...",
    #       "depth1_name": "...",
    #       ...
    #   }
    # }
    # --------------------------------------------------------
    if isinstance(category_data, dict):

        path_parts = []

        for depth in range(1, 6):
            code = clean_text(
                category_data.get(f"depth{depth}_code")
                or category_data.get(f"depth{depth}_id")
            )

            name = clean_text(
                category_data.get(f"depth{depth}_name")
            )

            if code is None:
                continue

            if name:
                path_parts.append(name)

            result.append(
                {
                    "source_category_id": code,
                    "source_category_name": name,
                    "source_category_path": (
                        " > ".join(path_parts)
                        if path_parts
                        else None
                    ),
                    "normalized_name": (
                        normalize_category_name(name)
                    ),
                    "depth": depth,
                }
            )

        if result:
            return result

    # --------------------------------------------------------
    # case 2.
    # {
    #   "categories": [
    #       {"id": "...", "name": "..."},
    #       {"id": "...", "name": "..."},
    #   ]
    # }
    # --------------------------------------------------------
    if isinstance(category_data, list):

        path_parts = []

        for index, item in enumerate(
            category_data,
            start=1,
        ):
            if not isinstance(item, dict):
                continue

            code = clean_text(
                item.get("id")
                or item.get("category_id")
                or item.get("code")
            )

            name = clean_text(
                item.get("name")
                or item.get("category_name")
            )

            if code is None:
                continue

            if name:
                path_parts.append(name)

            result.append(
                {
                    "source_category_id": code,
                    "source_category_name": name,
                    "source_category_path": (
                        " > ".join(path_parts)
                        if path_parts
                        else None
                    ),
                    "normalized_name": (
                        normalize_category_name(name)
                    ),
                    "depth": index,
                }
            )

    return result




def build_brand_source_payload(
    *,
    source_brand_id: Any,
    name: Any,
    english_name: Any = None,
    image_url: Any = None,
    country_code: Any = None,
    description: Any = None,
    target_gender: Any = None,
    target_age: Any = None,
    style_values: Any = None,
    website_url: Any = None,
    source_profile_url: Any = None,
    attributes: dict | None = None,
) -> dict:

    return {

        "source_brand_id": (
            clean_text(
                source_brand_id
            )
        ),

        "name": (
            clean_text(name)
        ),

        "english_name": (
            clean_text(
                english_name
            )
        ),

        "image_url": (
            clean_text(
                image_url
            )
        ),

        "country_code": (
            normalize_country_code(
                country_code
            )
        ),

        "description": (
            clean_text(
                description
            )
        ),

        "target_gender": (
            clean_list(
                target_gender
            )
        ),

        "target_age": (
            clean_list(
                target_age
            )
        ),

        "style_values": (
            clean_list(
                style_values
            )
        ),

        "website_url": (
            clean_text(
                website_url
            )
        ),

        "source_profile_url": (
            clean_text(
                source_profile_url
            )
        ),

        "attributes": (
            attributes
            if isinstance(
                attributes,
                dict,
            )
            else {}
        ),
    }