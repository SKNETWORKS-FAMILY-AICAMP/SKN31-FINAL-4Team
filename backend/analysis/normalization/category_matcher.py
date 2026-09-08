from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from apps.core.models import Category


# ============================================================
# RESULT
# ============================================================


@dataclass
class CategoryMatchResult:
    category: Category | None
    matched: bool
    method: str
    score: float

    source_name: str | None = None
    target_name: str | None = None

    second_score: float = 0.0


# ============================================================
# NORMALIZE
# ============================================================


def normalize_category_match_text(
    value,
) -> str | None:
    """
    카테고리 유사도 비교 전용 정규화.

    예:
        "블루종 "       -> "블루종"
        "MA-1"          -> "ma1"
        "치노 팬츠"     -> "치노팬츠"
        "반소매 티셔츠" -> "반소매티셔츠"
    """

    if value is None:
        return None

    value = str(value).strip().lower()

    if not value:
        return None

    value = re.sub(
        r"[^0-9a-z가-힣]+",
        "",
        value,
    )

    return value or None


# ============================================================
# ALTERNATIVE LABELS
# ============================================================


def split_category_labels(
    value,
) -> list[str]:
    """
    FEEDIT 카테고리명 내부의 대체 명칭을 분리한다.

    예:
        블루종/MA-1
        ->
        [
            "블루종ma1",   # 전체
            "블루종",
            "ma1",
        ]

        민소매/슬리브리스
        ->
        [
            "민소매슬리브리스",
            "민소매",
            "슬리브리스",
        ]
    """

    if value is None:
        return []

    raw = str(value).strip()

    if not raw:
        return []

    result = []

    # 전체 이름
    full = normalize_category_match_text(
        raw
    )

    if full:
        result.append(full)

    # '/', ',', '|', 괄호 등으로
    # 별칭성 표현 분리
    parts = re.split(
        r"[/|,·]+",
        raw,
    )

    for part in parts:

        normalized = (
            normalize_category_match_text(
                part
            )
        )

        if (
            normalized
            and normalized not in result
        ):
            result.append(normalized)

    return result


# ============================================================
# SCORE
# ============================================================


def calculate_category_score(
    source_name: str,
    target_name: str,
) -> tuple[float, str]:

    source = (
        normalize_category_match_text(
            source_name
        )
    )

    target = (
        normalize_category_match_text(
            target_name
        )
    )

    if not source or not target:
        return 0.0, "NONE"

    # --------------------------------------------------------
    # 1. 완전 일치
    # --------------------------------------------------------

    if source == target:
        return 100.0, "EXACT"

    # --------------------------------------------------------
    # 2. '/' 등으로 묶인 FEEDIT 명칭 내부 alias
    #
    # 블루종 -> 블루종/MA-1
    # 민소매 -> 민소매/슬리브리스
    # --------------------------------------------------------

    labels = split_category_labels(
        target_name
    )

    for label in labels:

        if source == label:
            return 98.0, "LABEL"

    # --------------------------------------------------------
    # 3. FUZZY
    # --------------------------------------------------------

    ratio = fuzz.ratio(
        source,
        target,
    )

    weighted = fuzz.WRatio(
        source,
        target,
    )

    partial = fuzz.partial_ratio(
        source,
        target,
    )

    # partial은 짧은 단어에서 과대평가될 수 있으므로
    # 그대로 100% 사용하지 않는다.
    partial_adjusted = (
        partial * 0.92
    )

    score = max(
        ratio,
        weighted,
        partial_adjusted,
    )

    return float(score), "SIMILARITY"


# ============================================================
# MATCHER
# ============================================================


class CategoryMatcher:
    """
    모든 플랫폼에서 공통 사용.

    source category name
        ↓
    FEEDIT Category
    """

    AUTO_MATCH_THRESHOLD = 90.0

    # 1위와 2위 점수 차이가 너무 작으면
    # 잘못된 자동 매핑 위험이 있으므로 UNMAPPED.
    MIN_SCORE_MARGIN = 6.0

    def __init__(self):

        self.categories = list(
            Category.objects
            .filter(
                category_type=(
                    Category
                    .CategoryType
                    .PRODUCT
                ),
                status=(
                    Category
                    .Status
                    .ACTIVE
                ),
            )
            .only(
                "id",
                "code",
                "name",
            )
        )

    # ========================================================
    # MATCH
    # ========================================================

    def match(
        self,
        source_name: str | None,
    ) -> CategoryMatchResult:

        if not source_name:

            return CategoryMatchResult(
                category=None,
                matched=False,
                method="NO_NAME",
                score=0.0,
                source_name=source_name,
            )

        candidates = []

        for category in self.categories:

            score, method = (
                calculate_category_score(
                    source_name,
                    category.name,
                )
            )

            candidates.append(
                (
                    score,
                    method,
                    category,
                )
            )

        if not candidates:

            return CategoryMatchResult(
                category=None,
                matched=False,
                method="NO_CATEGORY",
                score=0.0,
                source_name=source_name,
            )

        candidates.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        best_score = candidates[0][0]
        best_method = candidates[0][1]
        best_category = candidates[0][2]

        second_score = (
            candidates[1][0]
            if len(candidates) > 1
            else 0.0
        )

        # ----------------------------------------------------
        # EXACT / LABEL은 바로 확정
        # ----------------------------------------------------

        if best_method in (
            "EXACT",
            "LABEL",
        ):

            return CategoryMatchResult(
                category=best_category,
                matched=True,
                method=best_method,
                score=best_score,
                source_name=source_name,
                target_name=(
                    best_category.name
                ),
                second_score=second_score,
            )

        # ----------------------------------------------------
        # SIMILARITY threshold
        # ----------------------------------------------------

        if (
            best_score
            < self.AUTO_MATCH_THRESHOLD
        ):

            return CategoryMatchResult(
                category=None,
                matched=False,
                method="LOW_SCORE",
                score=best_score,
                source_name=source_name,
                target_name=(
                    best_category.name
                ),
                second_score=second_score,
            )

        # ----------------------------------------------------
        # 후보간 점수 차이가 너무 작으면
        # 애매한 것으로 판단
        # ----------------------------------------------------

        margin = (
            best_score
            - second_score
        )

        if (
            margin
            < self.MIN_SCORE_MARGIN
        ):

            return CategoryMatchResult(
                category=None,
                matched=False,
                method="AMBIGUOUS",
                score=best_score,
                source_name=source_name,
                target_name=(
                    best_category.name
                ),
                second_score=second_score,
            )

        # ----------------------------------------------------
        # AUTO MATCH
        # ----------------------------------------------------

        return CategoryMatchResult(
            category=best_category,
            matched=True,
            method="SIMILARITY",
            score=best_score,
            source_name=source_name,
            target_name=(
                best_category.name
            ),
            second_score=second_score,
        )