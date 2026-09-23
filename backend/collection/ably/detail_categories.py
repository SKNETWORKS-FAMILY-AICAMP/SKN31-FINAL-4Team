from __future__ import annotations

from typing import Iterator, TypedDict


class AblyDetailCategory(TypedDict):
    parent_id: int
    parent_name: str
    category_id: int
    category_name: str


# Source: ABLY /api/v2/configs/ categories response captured on 2026-09-22.
# "전체" entries are intentionally excluded: every row below gets its own top-100
# ranking target.
ABLY_DETAIL_CATEGORY_GROUPS: dict[str, dict[str, object]] = {
    "상의": {
        "parent_id": 8,
        "details": {
            "후드": 500,
            "맨투맨": 300,
            "니트": 299,
            "긴소매티셔츠": 498,
            "셔츠": 499,
            "조끼": 357,
            "블라우스": 298,
            "반소매티셔츠": 18,
            "민소매": 21,
        },
    },
    "팬츠": {
        "parent_id": 174,
        "details": {
            "데님": 501,
            "슬랙스": 178,
            "롱팬츠": 176,
            "숏팬츠": 177,
        },
    },
    "원피스/세트": {
        "parent_id": 10,
        "details": {
            "미니원피스": 206,
            "롱원피스": 207,
            "투피스": 208,
            "점프수트": 533,
        },
    },
    "스커트": {
        "parent_id": 203,
        "details": {
            "미니 스커트": 204,
            "미디/롱스커트": 205,
        },
    },
    "아우터": {
        "parent_id": 7,
        "details": {
            "가디건": 16,
            "자켓": 293,
            "집업/점퍼": 294,
            "바람막이": 497,
            "코트": 296,
            "플리스": 577,
            "야상": 496,
            "패딩": 297,
        },
    },
}


def iter_ably_detail_categories() -> Iterator[AblyDetailCategory]:
    for parent_name, group in ABLY_DETAIL_CATEGORY_GROUPS.items():
        parent_id = int(group["parent_id"])
        details = group["details"]
        if not isinstance(details, dict):
            raise TypeError(f"ABLY details must be a dict: {parent_name}")

        for category_name, category_id in details.items():
            yield {
                "parent_id": parent_id,
                "parent_name": parent_name,
                "category_id": int(category_id),
                "category_name": str(category_name),
            }


def build_ably_detail_target_name(category: AblyDetailCategory) -> str:
    """Return the admin-facing name used for one ABLY detail target."""

    return (
        f"[여성>{category['parent_name']}>"
        f"{category['category_name']}]"
    )
