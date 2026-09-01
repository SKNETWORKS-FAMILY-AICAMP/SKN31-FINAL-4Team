# backend/analysis/vision/category_map.py

FASHIONPEDIA_TO_FEEDIT = {
    # =========================
    # TOP
    # =========================
    "shirt, blouse": "TOP",
    "top, t-shirt, sweatshirt": "TOP",
    "sweater": "TOP",
    "cardigan": "TOP",
    "vest": "TOP",

    # =========================
    # OUTER
    # =========================
    "jacket": "OUTER",
    "coat": "OUTER",
    "cape": "OUTER",

    # =========================
    # BOTTOM
    # =========================
    "pants": "BOTTOM",
    "shorts": "BOTTOM",

    # =========================
    # DRESS / SKIRT
    # =========================
    "skirt": "DRESS_SKIRT",
    "dress": "DRESS_SKIRT",
    "jumpsuit": "DRESS_SKIRT",
}


SUPPORTED_CATEGORIES = {
    "TOP",
    "OUTER",
    "BOTTOM",
    "DRESS_SKIRT",
}


def normalize_fashion_label(label: str) -> str | None:
    """
    Fashionpedia class → FEEDIT 대분류
    """

    if not label:
        return None

    return FASHIONPEDIA_TO_FEEDIT.get(
        label.strip().lower()
    )


def is_target_category(
    detected_label: str,
    target_category: str,
) -> bool:

    normalized = normalize_fashion_label(
        detected_label
    )

    return normalized == target_category.upper()