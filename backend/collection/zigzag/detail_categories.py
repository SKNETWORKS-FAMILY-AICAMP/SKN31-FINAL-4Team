from __future__ import annotations

from typing import Iterator, TypedDict


class ZigzagDetailCategory(TypedDict):
    group_name: str
    parent_id: int
    parent_name: str
    category_id: int
    category_name: str


# Source: Zigzag GlobalNavigationPage GraphQL response captured on 2026-09-22.
# Promotional pseudo-categories such as "연휴 전 도착 보장" are excluded.
ZIGZAG_DETAIL_CATEGORY_GROUPS: tuple[dict[str, object], ...] = (
    {
        "group_name": "상의",
        "parent_id": 474,
        "parent_name": "상의",
        "details": {
            "긴소매 티셔츠": 2792,
            "반소매 티셔츠": 2791,
            "셔츠": 489,
            "블라우스": 498,
            "니트/스웨터": 482,
            "맨투맨": 494,
            "후드": 495,
            "슬리브리스": 499,
        },
    },
    {
        "group_name": "팬츠",
        "parent_id": 547,
        "parent_name": "팬츠",
        "details": {
            "데님팬츠": 2796,
            "일자팬츠": 548,
            "슬랙스팬츠": 549,
            "와이드팬츠": 551,
            "스키니팬츠": 552,
            "부츠컷팬츠": 553,
            "조거팬츠": 554,
            "숏팬츠": 550,
            "점프수트": 556,
            "레깅스": 559,
            "기타팬츠": 2756,
        },
    },
    {
        "group_name": "원피스/세트",
        "parent_id": 507,
        "parent_name": "원피스",
        "details": {
            "미니원피스": 508,
            "미디원피스": 518,
            "롱원피스": 528,
        },
    },
    {
        "group_name": "원피스/세트",
        "parent_id": 538,
        "parent_name": "투피스/세트",
        "details": {
            "스커트 세트": 539,
            "팬츠 세트": 540,
            "원피스 세트": 541,
            "시밀러룩": 546,
        },
    },
    {
        "group_name": "스커트",
        "parent_id": 560,
        "parent_name": "스커트",
        "details": {
            "미니스커트": 561,
            "미디스커트": 568,
            "롱스커트": 575,
        },
    },
    {
        "group_name": "아우터",
        "parent_id": 436,
        "parent_name": "아우터",
        "details": {
            "카디건": 437,
            "재킷": 438,
            "점퍼": 454,
            "레더재킷": 442,
            "트렌치코트": 447,
            "트위드재킷": 441,
            "사파리재킷": 460,
            "베스트": 461,
            "숏코트": 2787,
            "하프코트": 2788,
            "롱코트": 2789,
            "숏패딩": 463,
            "롱패딩": 464,
            "경량 패딩": 466,
            "퍼코트": 451,
            "무스탕": 445,
            "레인코트": 453,
        },
    },
)


def iter_zigzag_detail_categories() -> Iterator[ZigzagDetailCategory]:
    for group in ZIGZAG_DETAIL_CATEGORY_GROUPS:
        details = group["details"]
        if not isinstance(details, dict):
            raise TypeError("Zigzag details must be a dict")

        for category_name, category_id in details.items():
            yield {
                "group_name": str(group["group_name"]),
                "parent_id": int(group["parent_id"]),
                "parent_name": str(group["parent_name"]),
                "category_id": int(category_id),
                "category_name": str(category_name),
            }
