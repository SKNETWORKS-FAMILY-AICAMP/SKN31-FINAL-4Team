# backend/analysis/ocr/block_classifier.py

from __future__ import annotations

import re
from dataclasses import (
    asdict,
    dataclass,
)


# --------------------------------------------------
# Attribute keyword dictionary
# --------------------------------------------------

ATTRIBUTE_KEYWORDS = {

    "MATERIAL": [
        "코튼",
        "면",
        "cotton",
        "데님",
        "denim",
        "울",
        "wool",
        "캐시미어",
        "cashmere",
        "린넨",
        "linen",
        "폴리에스터",
        "polyester",
        "나일론",
        "nylon",
        "레이온",
        "rayon",
        "비스코스",
        "viscose",
        "아크릴",
        "acrylic",
        "레더",
        "가죽",
        "leather",
        "스웨이드",
        "suede",
        "텐셀",
        "tencel",
        "모달",
        "modal",
        "니트",
        "knit",
        "저지",
        "jersey",
        "트위드",
        "tweed",
        "코듀로이",
        "corduroy",
        "벨벳",
        "velvet",
        "벨루어",
        "velour",
        "새틴",
        "satin",
        "시폰",
        "chiffon",
        "레이스",
        "lace",
        "메시",
        "mesh",
        "폴리우레탄",
        "polyurethane",
        "스판",
        "span",
        "elastane",
    ],

    "FIT": [
        "오버핏",
        "오버사이즈",
        "oversized",
        "루즈핏",
        "loose fit",
        "레귤러핏",
        "regular fit",
        "슬림핏",
        "slim fit",
        "와이드핏",
        "wide fit",
        "와이드",
        "세미와이드",
        "테이퍼드",
        "tapered",
        "부츠컷",
        "bootcut",
        "플레어",
        "flare",
        "스트레이트",
        "straight",
        "실루엣",
        "silhouette",
        "여유로운 핏",
        "여유로운 실루엣",
        "루즈한",
        "여유있는",
        "여유 있는",
    ],

    "DETAIL": [
        "워싱",
        "washing",
        "washed",
        "피그먼트",
        "pigment",
        "디스트레스드",
        "distressed",
        "데미지",
        "damage",
        "자수",
        "embroidery",
        "프린팅",
        "printing",
        "플리츠",
        "pleats",
        "셔링",
        "shirring",
        "스티치",
        "stitch",
        "스티칭",
        "절개",
        "슬릿",
        "slit",
        "포켓",
        "pocket",
        "지퍼",
        "zipper",
        "버튼",
        "button",
        "스트링",
        "string",
        "배색",
        "패치",
        "patch",
        "크롭",
        "cropped",
        "컷오프",
        "cut off",
        "봉제",
        "seam",
        "턱",
        "tuck",
        "핀턱",
        "pintuck",
        "밴딩",
        "banding",
        "리브",
        "rib",
    ],

    "STYLE": [
        "캐주얼",
        "casual",
        "미니멀",
        "minimal",
        "클래식",
        "classic",
        "빈티지",
        "vintage",
        "레트로",
        "retro",
        "스트릿",
        "street",
        "스트리트",
        "시티보이",
        "city boy",
        "아메카지",
        "amekaji",
        "프레피",
        "preppy",
        "페미닌",
        "feminine",
        "걸리시",
        "girlish",
        "러블리",
        "lovely",
        "스포티",
        "sporty",
        "애슬레저",
        "athleisure",
        "고프코어",
        "gorpcore",
        "y2k",
        "워크웨어",
        "workwear",
        "시크",
        "chic",
        "포멀",
        "formal",
        "오피스",
        "office",
    ],

    "TPO": [
        "데일리",
        "daily",
        "출근",
        "오피스",
        "office",
        "비즈니스",
        "business",
        "데이트",
        "date",
        "여행",
        "travel",
        "휴양지",
        "vacation",
        "캠퍼스",
        "campus",
        "학교",
        "school",
        "하객",
        "웨딩",
        "wedding",
        "결혼식",
        "파티",
        "party",
        "페스티벌",
        "festival",
        "캠핑",
        "camping",
        "등산",
        "hiking",
        "골프",
        "golf",
        "운동",
        "sports",
        "홈웨어",
        "loungewear",
        "피크닉",
        "picnic",
        "공항",
        "airport",
    ],

    "COLOR": [
        "블랙",
        "black",
        "화이트",
        "white",
        "아이보리",
        "ivory",
        "크림",
        "cream",
        "그레이",
        "gray",
        "grey",
        "차콜",
        "charcoal",
        "베이지",
        "beige",
        "브라운",
        "brown",
        "레드",
        "red",
        "버건디",
        "burgundy",
        "오렌지",
        "orange",
        "옐로우",
        "yellow",
        "그린",
        "green",
        "카키",
        "khaki",
        "올리브",
        "olive",
        "블루",
        "blue",
        "네이비",
        "navy",
        "핑크",
        "pink",
        "퍼플",
        "purple",
        "라벤더",
        "lavender",
    ],

    "SEASON": [
        "봄",
        "spring",
        "여름",
        "summer",
        "가을",
        "autumn",
        "fall",
        "겨울",
        "winter",
        "간절기",
        "환절기",
    ],
}


# --------------------------------------------------
# Noise
# --------------------------------------------------

NOISE_KEYWORDS = [
    "copyright",
    "all rights reserved",
    "고객센터",
    "교환 및 반품",
    "교환/반품",
    "반품 안내",
    "배송 안내",
    "shipping",
    "delivery",
    "구매 전 확인",
    "구매전 확인",
    "주의사항",
    "브랜드 소개",
]


# --------------------------------------------------
# Evidence
# --------------------------------------------------

@dataclass
class Evidence:
    attribute: str
    text: str
    matched_keywords: list[str]
    ocr_confidence: float
    source_image_index: int | None = None
    score: float = 0.0

    def to_dict(
        self,
    ) -> dict:

        return asdict(
            self
        )


# --------------------------------------------------
# Classifier
# --------------------------------------------------

class FashionInfoBlockClassifier:

    def __init__(
        self,
        min_text_length: int = 2,
        max_text_length: int = 1000,
    ):
        self.min_text_length = (
            min_text_length
        )

        self.max_text_length = (
            max_text_length
        )

    # --------------------------------------------------
    # Normalize
    # --------------------------------------------------

    def _normalize_text(
        self,
        text: str,
    ) -> str:

        text = (
            text.strip()
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text

    # --------------------------------------------------
    # Noise
    # --------------------------------------------------

    def _is_noise(
        self,
        text: str,
    ) -> bool:

        lowered = (
            text.lower()
        )

        return any(
            keyword.lower()
            in lowered
            for keyword
            in NOISE_KEYWORDS
        )

    # --------------------------------------------------
    # Keyword match
    # --------------------------------------------------

    def _match_keywords(
        self,
        text: str,
        keywords: list[str],
    ) -> list[str]:

        lowered = (
            text.lower()
        )

        matched = []

        for keyword in keywords:

            if (
                keyword.lower()
                in lowered
            ):
                matched.append(
                    keyword
                )

        # 같은 keyword 중복 방지
        return list(
            dict.fromkeys(
                matched
            )
        )

    # --------------------------------------------------
    # Score
    # --------------------------------------------------

    def _calculate_score(
        self,
        matched_keywords: list[str],
        ocr_confidence: float,
        text: str,
    ) -> float:

        keyword_count = len(
            matched_keywords
        )

        keyword_score = min(
            keyword_count
            * 0.08,
            0.30,
        )

        confidence_score = (
            max(
                0.0,
                min(
                    float(
                        ocr_confidence
                    ),
                    1.0,
                ),
            )
            * 0.30
        )

        text_bonus = 0.0

        if len(text) >= 10:
            text_bonus += 0.05

        if len(text) >= 30:
            text_bonus += 0.05

        score = (
            0.35
            + keyword_score
            + confidence_score
            + text_bonus
        )

        return round(
            min(
                score,
                1.0,
            ),
            4,
        )

    # --------------------------------------------------
    # Public
    # --------------------------------------------------

    def classify(
        self,
        text: str,
        ocr_confidence: float = 1.0,
        source_image_index: int | None = None,
    ) -> list[Evidence]:

        text = self._normalize_text(
            text
        )

        if not text:
            return []

        if (
            len(text)
            < self.min_text_length
        ):
            return []

        if (
            len(text)
            > self.max_text_length
        ):
            text = text[
                : self.max_text_length
            ]

        if self._is_noise(
            text
        ):
            return []

        evidences = []

        for (
            attribute,
            keywords,
        ) in ATTRIBUTE_KEYWORDS.items():

            matched = (
                self._match_keywords(
                    text=text,
                    keywords=keywords,
                )
            )

            if not matched:
                continue

            score = (
                self._calculate_score(
                    matched_keywords=(
                        matched
                    ),
                    ocr_confidence=(
                        ocr_confidence
                    ),
                    text=text,
                )
            )

            evidences.append(
                Evidence(
                    attribute=(
                        attribute
                    ),

                    text=(
                        text
                    ),

                    matched_keywords=(
                        matched
                    ),

                    ocr_confidence=round(
                        float(
                            ocr_confidence
                        ),
                        4,
                    ),

                    source_image_index=(
                        source_image_index
                    ),

                    score=(
                        score
                    ),
                )
            )

        evidences.sort(
            key=lambda item: (
                item.score
            ),
            reverse=True,
        )

        return evidences