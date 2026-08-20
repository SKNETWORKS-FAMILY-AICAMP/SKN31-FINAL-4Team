"""
MUSINSA Historical Backfill URL Builder.
무신사 과거 랭킹 데이터 수집용. 다.~~~
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import MUSINSA_CATEGORIES, MUSINSA_GENDERS

ARCHIVE_BASE_URL = "https://www.musinsa.com/ranking/archive"


@dataclass(frozen=True)
class BackfillRequest:
    year_month: str
    gender_code: str
    category_code: str
    request_url: str


def build_archive_url(
    *,
    year_month: str,
    category_code: str,
    gender_code: str,
) -> str:
    """
    과거 랭킹 URL 하나 생성.

    예:
    year_month="202401"
    category_code="001"
    gender_code="F"
    """

    return (
        f"{ARCHIVE_BASE_URL}"
        f"?date={year_month}"
        f"&categoryCode={category_code}"
        f"&gf={gender_code}"
    )


def iter_months(
    *,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
):
    """
    시작 월부터 종료 월까지 YYYYMM 문자열을 생성합니다.

    예:
    2024-01 ~ 2024-03
    -> 202401, 202402, 202403
    """

    if start_month < 1 or start_month > 12:
        raise ValueError(f"잘못된 start_month: {start_month}")

    if end_month < 1 or end_month > 12:
        raise ValueError(f"잘못된 end_month: {end_month}")

    if (start_year, start_month) > (
        end_year,
        end_month,
    ):
        raise ValueError("시작 월은 종료 월보다 늦을 수 없습니다.")

    year = start_year
    month = start_month

    while year < end_year or (year == end_year and month <= end_month):
        yield f"{year}{month:02d}"

        month += 1

        if month == 13:
            year += 1
            month = 1


def generate_backfill_requests(
    *,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    gender_codes: list[str],
    category_codes: list[str],
) -> list[BackfillRequest]:
    """
    월 × 성별 × 카테고리 조합 전체를
    BackfillRequest 목록으로 생성합니다.
    """

    if not gender_codes:
        raise ValueError("gender_codes가 비어 있습니다.")

    if not category_codes:
        raise ValueError("category_codes가 비어 있습니다.")

    for gender_code in gender_codes:
        if gender_code not in MUSINSA_GENDERS:
            raise ValueError(f"지원하지 않는 gender code: " f"{gender_code}")

    for category_code in category_codes:
        if category_code not in MUSINSA_CATEGORIES:
            raise ValueError(f"등록되지 않은 category code: " f"{category_code}")

    result = []

    for year_month in iter_months(
        start_year=start_year,
        start_month=start_month,
        end_year=end_year,
        end_month=end_month,
    ):
        for gender_code in gender_codes:
            for category_code in category_codes:

                request_url = build_archive_url(
                    year_month=year_month,
                    category_code=category_code,
                    gender_code=gender_code,
                )

                result.append(
                    BackfillRequest(
                        year_month=year_month,
                        gender_code=gender_code,
                        category_code=category_code,
                        request_url=request_url,
                    )
                )

    return result
