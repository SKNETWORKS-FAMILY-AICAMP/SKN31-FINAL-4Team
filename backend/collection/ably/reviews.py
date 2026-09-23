from __future__ import annotations

from typing import Any

from .constants import DEFAULT_REVIEW_LIMIT
from .exceptions import AblyParseError


def normalize_review_bundle(
    reviews_body: dict,
    summary_body: dict,
    *,
    limit: int = DEFAULT_REVIEW_LIMIT,
) -> dict:
    """Normalize one ABLY product's review responses without trusting their shape."""

    if not isinstance(reviews_body, dict):
        raise AblyParseError("ABLY reviews 응답이 object가 아닙니다.")
    raw_reviews = reviews_body.get("reviews")
    if not isinstance(raw_reviews, list):
        raise AblyParseError("ABLY reviews 응답에 reviews list가 없습니다.")

    summary_source = (
        summary_body.get("review") if isinstance(summary_body, dict) else None
    )
    summary_source = summary_source if isinstance(summary_source, dict) else {}

    return {
        "summary": {
            "total_count": _to_int(summary_source.get("count")),
            "positive_percent": _to_float(
                summary_source.get("positive_percent")
            ),
        },
        "items": [normalize_review(item) for item in raw_reviews[:limit]],
    }


def normalize_review(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise AblyParseError("ABLY review 항목이 object가 아닙니다.")

    review_id = raw.get("sno")
    if review_id in (None, ""):
        raise AblyParseError("ABLY review.sno가 없습니다.")

    body_info = raw.get("body_info")
    body_info = body_info if isinstance(body_info, dict) else {}
    option = raw.get("goods_option")
    option = option if isinstance(option, list) else []

    return {
        "source_review_id": str(review_id),
        "source_product_id": _clean_id(raw.get("goods_sno")),
        "review_type": "PHOTO" if raw.get("images") else "TEXT",
        "content": _clean_text(raw.get("contents")),
        # ABLY eval은 별점과 의미가 다르므로 grade로 오인하지 않고 원본 의미를 보존한다.
        "evaluation": _to_int(raw.get("eval")),
        "delivery_evaluation": _to_int(raw.get("delivery_eval")),
        "like_count": _to_int(raw.get("review_likes_count")),
        "created_at": raw.get("created_at"),
        "goods_option": option,
        "images": raw.get("images") if isinstance(raw.get("images"), list) else [],
        "images_webp": (
            raw.get("images_webp")
            if isinstance(raw.get("images_webp"), list)
            else []
        ),
        "reviewer": {
            "name": _clean_text(raw.get("writer")),
            "height": _first_value(body_info.get("height"), raw.get("height")),
            "weight": _first_value(body_info.get("weight"), raw.get("weight")),
            "size": _clean_text(body_info.get("size")),
        },
        "survey": {
            "size_rate": raw.get("size_rate"),
            "color_rate": raw.get("color_rate"),
            "top": raw.get("top"),
            "bottom": raw.get("bottom"),
            "shoes": raw.get("shoes"),
        },
    }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_id(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _first_value(*values: Any) -> Any:
    return next((value for value in values if value not in (None, "")), None)


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
