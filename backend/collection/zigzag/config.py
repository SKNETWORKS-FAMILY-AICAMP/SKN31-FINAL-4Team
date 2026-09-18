from __future__ import annotations


CNV_ENDPOINT = "https://api.zigzag.kr/api/2/graphql/batch/GetCnvPageAction"

# 2026-09-16 browser capture defaults.
# Zigzag 쪽에서 변경되면 CrawlTarget.params 또는 여기만 교체하면 됩니다.
DEFAULT_LAYOUT_ID = "301"
DEFAULT_ACTION_ID = "a061b462-576a-4991-9146-62b2166c132a"
DEFAULT_MODULE_SLOT_ID = "s6C9txhfmfIi"

DEFAULT_ORDER = "SCORE_DESC"
DEFAULT_MIN_DELAY = 1.5
DEFAULT_MAX_DELAY = 3.0


CATEGORY_MAP = {
    "상의": 474,
    "팬츠": 547,
    "아우터": 436,
    "스커트": 560,
    "니트/카디건": 2757,
    "트레이닝": 833,
    "원피스": 507,
    "투피스/세트": 538,
}


TREND_TAGS = [
    "블록코어",
    "고프코어",
    "모리룩",
    "발레코어",
    "그런지",
    "긱시크",
    "해적코어",
    "카우보이",
    "Y2K",
    "코티지코어",
    "올드머니",
]


STYLE_TAGS = [
    "캐주얼",
    "러블리",
    "미니멀",
    "스트릿",
    "글램",
    "시크",
    "레트로",
    "프레피",
    "모던",
    "엘레강스",
    "비즈니스 캐주얼",
    "애슬레저",
    "클래식",
]


TPO_TAGS = [
    "데일리",
    "출근룩",
    "홈웨어",
    "운동",
    "파티",
    "여행",
    "휴양지",
    "클럽룩",
    "워터 페스티벌",
    "하객룩",
    "페스티벌",
    "아웃도어",
    "바디프로필",
    "크리스마스",
    "면접",
    "웨딩",
    "프로필",
    "할로윈",
]


GROUP_CONFIG = {
    "trend": {
        "label": "트렌드",
        "attribute": "trend",
        "tags": TREND_TAGS,
        "default_limit": 100,
    },
    "style": {
        "label": "스타일",
        "attribute": "styles",
        "tags": STYLE_TAGS,
        "default_limit": 30,
    },
    "tpo": {
        "label": "상황",
        "attribute": "tpo",
        "tags": TPO_TAGS,
        "default_limit": 30,
    },
}


DEFAULT_GROUPS = ["trend", "style", "tpo"]

DEFAULT_LIMITS = {
    group: config["default_limit"]
    for group, config in GROUP_CONFIG.items()
}
