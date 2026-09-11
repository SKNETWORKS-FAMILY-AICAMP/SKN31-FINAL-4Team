from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

from apps.core.models import Brand, Category


# ============================================================
# TEXT
# ============================================================

def clean_text(value) -> str | None:
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def normalize_text(value) -> str | None:
    value = clean_text(value)

    if value is None:
        return None

    value = value.lower()
    value = re.sub(r"\s+", " ", value)

    return value.strip() or None


def make_match_key(value: Any) -> str | None:
    """
    DB에 별도 normalized column을 강제하지 않고,
    비교할 때만 사용하는 공통 key.
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


# ============================================================
# BRAND
# ============================================================

def normalize_brand_name(value) -> str | None:
    return make_match_key(value)


def find_brand_exact(
    *,
    name: str | None,
    english_name: str | None = None,
) -> Brand | None:
    """
    모든 source에서 공통으로 쓰는 FEEDIT Brand exact matcher.
    """
    name_key = make_match_key(name)
    english_key = make_match_key(english_name)

    if not name_key and not english_key:
        return None

    matches = []

    brands = (
        Brand.objects
        .filter(status=Brand.Status.ACTIVE)
        .only(
            "id",
            "brand_code",
            "name",
            "english_name",
        )
    )

    for brand in brands:
        keys = {
            value
            for value in (
                make_match_key(brand.name),
                make_match_key(brand.english_name),
                make_match_key(brand.brand_code),
            )
            if value
        }

        if (
            (name_key and name_key in keys)
            or (
                english_key
                and english_key in keys
            )
        ):
            matches.append(brand)

    if len(matches) != 1:
        return None

    return matches[0]


# ============================================================
# CATEGORY
# ============================================================

def normalize_category_name(value) -> str | None:
    return normalize_text(value)


def normalize_category_path(value) -> str | None:
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

    return (
        " > ".join(parts)
        if parts
        else None
    )


def normalize_category_match_text(
    value,
) -> str | None:
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


def split_category_labels(
    value,
) -> list[str]:
    if value is None:
        return []

    raw = str(value).strip()

    if not raw:
        return []

    result = []

    full = normalize_category_match_text(raw)

    if full:
        result.append(full)

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


def calculate_category_score(
    source_name: str,
    target_name: str,
) -> tuple[float, str]:
    source = normalize_category_match_text(
        source_name
    )

    target = normalize_category_match_text(
        target_name
    )

    if not source or not target:
        return 0.0, "NONE"

    if source == target:
        return 100.0, "EXACT"

    for label in split_category_labels(
        target_name
    ):
        if source == label:
            return 98.0, "LABEL"

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

    score = max(
        ratio,
        weighted,
        partial * 0.92,
    )

    return float(score), "SIMILARITY"


@dataclass
class CategoryMatchResult:
    category: Category | None
    matched: bool
    method: str
    score: float

    source_name: str | None = None
    target_name: str | None = None
    second_score: float = 0.0


class CategoryMatcher:
    """
    모든 플랫폼에서 공통 사용.

    source category name
        ↓
    FEEDIT Category
    """

    AUTO_MATCH_THRESHOLD = 90.0
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

        if best_method in {
            "EXACT",
            "LABEL",
        }:
            return CategoryMatchResult(
                category=best_category,
                matched=True,
                method=best_method,
                score=best_score,
                source_name=source_name,
                target_name=best_category.name,
                second_score=second_score,
            )

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
                target_name=best_category.name,
                second_score=second_score,
            )

        margin = (
            best_score
            - second_score
        )

        if margin < self.MIN_SCORE_MARGIN:
            return CategoryMatchResult(
                category=None,
                matched=False,
                method="AMBIGUOUS",
                score=best_score,
                source_name=source_name,
                target_name=best_category.name,
                second_score=second_score,
            )

        return CategoryMatchResult(
            category=best_category,
            matched=True,
            method="SIMILARITY",
            score=best_score,
            source_name=source_name,
            target_name=best_category.name,
            second_score=second_score,
        )


# ============================================================
# PRODUCT
# ============================================================

def normalize_product_name(
    value,
) -> str | None:
    return normalize_text(value)
