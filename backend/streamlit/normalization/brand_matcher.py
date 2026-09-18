from __future__ import annotations

from difflib import SequenceMatcher
import re

import pandas as pd


def normalize_brand_text(value) -> str:
    if value is None:
        return ""

    value = str(value).strip().lower()

    # 한글/영문/숫자만 남김
    value = re.sub(r"[^0-9a-z가-힣]", "", value)

    return value


def text_similarity(a, b) -> float:
    a = normalize_brand_text(a)
    b = normalize_brand_text(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    return SequenceMatcher(None, a, b).ratio()


def find_brand_candidates(
    source_name: str | None,
    source_english_name: str | None,
    feedit_brands: pd.DataFrame,
    top_n: int = 3,
    min_score: float = 0.30,
) -> pd.DataFrame:
    """
    BrandSource의 name / english_name을
    FEEDIT Brand의 name / english_name과 교차 비교해서 후보를 만든다.
    """

    if feedit_brands is None or feedit_brands.empty:
        return pd.DataFrame()

    rows = []

    for row in feedit_brands.itertuples(index=False):
        brand_name = getattr(row, "name", None)
        brand_en = getattr(row, "english_name", None)

        scores = {
            "name_name": text_similarity(source_name, brand_name),
            "name_en": text_similarity(source_name, brand_en),
            "en_name": text_similarity(source_english_name, brand_name),
            "en_en": text_similarity(source_english_name, brand_en),
        }

        best_method = max(scores, key=scores.get)
        best_score = scores[best_method]

        if best_score < min_score:
            continue

        rows.append(
            {
                "brand_id": int(row.id),
                "brand_code": getattr(row, "brand_code", None),
                "feedit_name": brand_name,
                "feedit_english_name": brand_en,
                "score": round(best_score, 4),
                "match_method": best_method,
            }
        )

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values(
            ["score", "feedit_name"],
            ascending=[False, True],
        )
        .head(top_n)
        .reset_index(drop=True)
    )


def search_feedit_brands(
    feedit_brands: pd.DataFrame,
    keyword: str,
    limit: int = 30,
) -> pd.DataFrame:
    """
    사용자가 FEEDIT Brand를 직접 검색할 때 사용.

    검색 대상:
    - name
    - english_name
    - brand_code

    부분 문자열 검색 + 대소문자 무시.
    """

    if feedit_brands is None or feedit_brands.empty:
        return pd.DataFrame()

    keyword = str(keyword or "").strip()

    if not keyword:
        return pd.DataFrame()

    normalized_keyword = keyword.lower()

    mask = pd.Series(False, index=feedit_brands.index)

    for column in [
        "name",
        "english_name",
        "brand_code",
    ]:
        if column not in feedit_brands.columns:
            continue

        values = (
            feedit_brands[column]
            .fillna("")
            .astype(str)
            .str.lower()
        )

        mask |= values.str.contains(
            normalized_keyword,
            regex=False,
        )

    result = (
        feedit_brands.loc[mask]
        .copy()
        .head(limit)
        .reset_index(drop=True)
    )

    return result
