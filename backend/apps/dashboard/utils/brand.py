import re


def generate_brand_code(english_name: str) -> str:
    """
    FEEDIT 브랜드 코드 생성

    GAP             -> BRAND_GAP
    Ghost Republic  -> BRAND_GHOST_REPUBLIC
    GOLDEN BEAR     -> BRAND_GOLDEN_BEAR
    A.P.C.          -> BRAND_APC
    """

    if not english_name:
        return ""

    value = english_name.strip().upper()

    value = re.sub(
        r"[\s\-/&]+",
        "_",
        value,
    )

    value = re.sub(
        r"[^A-Z0-9_]",
        "",
        value,
    )

    value = re.sub(
        r"_+",
        "_",
        value,
    )

    value = value.strip("_")

    if not value:
        return ""

    return f"BRAND_{value}"