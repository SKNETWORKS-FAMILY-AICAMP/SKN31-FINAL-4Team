# -*- coding: utf-8 -*-
"""
정규화 전처리 모듈

핵심 로직: 상대값 → 절대값 치환

네이버 데이터랩과 Google Trends는 상대적 비율(0~100)만 제공합니다.
네이버 검색광고 API에서 얻은 월간 절대 검색량을 기준으로
상대값을 절대값으로 치환하는 정규화 공식을 적용합니다.

공식:
    B의 추정 절대 검색량 = (B의 ratio / A의 ratio) × A의 월간 절대 검색량

여기서:
    A = 기준 키워드 (검색광고 API에서 월간 절대 검색량을 아는 키워드)
    B = 추정하려는 키워드
"""

import logging
from typing import List, Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class SearchVolumeNormalizer:
    """검색량 상대값 → 절대값 정규화 처리기"""

    def __init__(self):
        self._reference_volumes = {}  # {키워드: 월간_절대_검색량}

    def set_reference_volumes(self, searchad_data: List[Dict]):
        """
        네이버 검색광고 API 결과에서 기준 절대 검색량을 설정합니다.

        Args:
            searchad_data: 검색광고 API 결과 리스트
                [{"relKeyword": "민소매", "monthlyPcQcCnt": 12000, "monthlyMobileQcCnt": 45000}, ...]
        """
        for item in searchad_data:
            keyword = item.get("relKeyword", "")
            pc = item.get("monthlyPcQcCnt", 0)
            mobile = item.get("monthlyMobileQcCnt", 0)

            # "< 10" 같은 문자열 처리
            if isinstance(pc, str):
                pc = 5 if "< 10" in pc else 0
            if isinstance(mobile, str):
                mobile = 5 if "< 10" in mobile else 0

            total = (pc or 0) + (mobile or 0)
            if total > 0:
                self._reference_volumes[keyword] = {
                    "pc": pc or 0,
                    "mobile": mobile or 0,
                    "total": total,
                }

        logger.info(f"✅ 기준 검색량 설정: {len(self._reference_volumes)}개 키워드")

    def _find_reference_keyword(self, datalab_results: List[Dict]) -> Optional[Tuple[str, float, int]]:
        """
        데이터랩 결과에서 기준 키워드를 찾습니다.
        기준 키워드 = 검색광고 API에서 절대 검색량을 알고 있으면서
                      데이터랩에서도 충분한 ratio 값을 가진 키워드

        Returns:
            (키워드명, 데이터랩 평균 ratio, 월간 절대 검색량) 또는 None
        """
        best_ref = None
        best_score = 0

        for result in datalab_results:
            keyword = result.get("title", "")
            if keyword not in self._reference_volumes:
                continue

            # 해당 키워드의 데이터랩 ratio 평균 계산
            data_points = result.get("data", [])
            if not data_points:
                continue

            ratios = [d["ratio"] for d in data_points if d.get("ratio", 0) > 0]
            if not ratios:
                continue

            avg_ratio = sum(ratios) / len(ratios)
            total_volume = self._reference_volumes[keyword]["total"]

            # 점수: ratio * 절대 검색량 (둘 다 높을수록 좋은 기준 키워드)
            score = avg_ratio * total_volume
            if score > best_score:
                best_score = score
                best_ref = (keyword, avg_ratio, total_volume)

        return best_ref

    def normalize_naver_datalab(self, datalab_data: Dict) -> List[Dict]:
        """
        네이버 데이터랩 상대값을 절대값으로 치환합니다.

        Args:
            datalab_data: 네이버 데이터랩 수집 결과
                {"data": [{"title": "민소매", "data": [{"period": "2026-01-01", "ratio": 85}, ...]}]}

        Returns:
            [
                {
                    "keyword": "민소매",
                    "platform": "naver",
                    "period": "2026-01-01",
                    "ratio": 85.0,
                    "estimated_volume": 42500,
                    "reference_keyword": "민소매",
                    "normalization_method": "searchad_ratio"
                }, ...
            ]
        """
        results_data = datalab_data.get("data", [])
        if not results_data:
            logger.warning("⚠️ 데이터랩 데이터가 비어있습니다.")
            return []

        # 기준 키워드 찾기
        ref = self._find_reference_keyword(results_data)

        normalized = []
        for result in results_data:
            keyword = result.get("title", "")
            data_points = result.get("data", [])

            for point in data_points:
                period = point.get("period", "")
                ratio = point.get("ratio", 0)

                estimated_volume = None
                ref_keyword = None
                method = "none"

                if ref and ratio > 0:
                    ref_keyword, ref_ratio, ref_volume = ref
                    if ref_ratio > 0:
                        # 핵심 치환 공식
                        estimated_volume = int((ratio / ref_ratio) * ref_volume)
                        method = "searchad_ratio"

                normalized.append({
                    "keyword": keyword,
                    "platform": "naver",
                    "period": period,
                    "ratio": ratio,
                    "estimated_volume": estimated_volume,
                    "reference_keyword": ref_keyword,
                    "normalization_method": method,
                })

        logger.info(f"✅ 네이버 데이터랩 정규화 완료: {len(normalized)}건")
        return normalized

    def normalize_google_trends(
        self,
        trends_data: Dict,
        google_keyword_data: Dict = None
    ) -> List[Dict]:
        """
        Google Trends 상대값을 절대값으로 치환합니다.

        Google Keyword Planner 데이터가 있으면 이를 기준으로,
        없으면 네이버 검색광고 데이터를 교차 참조로 사용합니다.

        Args:
            trends_data: Google Trends 수집 결과
            google_keyword_data: Google Keyword Planner 수집 결과 (선택)

        Returns:
            정규화된 데이터 리스트
        """
        interest_data = trends_data.get("interest_over_time", [])
        if not interest_data:
            logger.warning("⚠️ Google Trends 관심도 데이터가 비어있습니다.")
            return []

        # Google Keyword Planner 기준값 설정
        google_ref_volumes = {}
        if google_keyword_data and google_keyword_data.get("data"):
            for item in google_keyword_data["data"]:
                kw = item.get("keyword", "")
                avg_searches = item.get("avg_monthly_searches", 0)
                if avg_searches and avg_searches > 0:
                    google_ref_volumes[kw] = avg_searches

        # 키워드별 평균 ratio 계산
        keyword_ratios = {}
        for point in interest_data:
            kw = point["keyword"]
            val = point["value"]
            if kw not in keyword_ratios:
                keyword_ratios[kw] = []
            keyword_ratios[kw].append(val)

        keyword_avg_ratios = {
            kw: sum(vals) / len(vals) if vals else 0
            for kw, vals in keyword_ratios.items()
        }

        # 기준 키워드 찾기 (Google Keyword Planner 데이터 기반)
        ref_keyword = None
        ref_ratio = 0
        ref_volume = 0

        for kw, avg_ratio in keyword_avg_ratios.items():
            if kw in google_ref_volumes and avg_ratio > 0:
                vol = google_ref_volumes[kw]
                score = avg_ratio * vol
                if score > ref_ratio * ref_volume:
                    ref_keyword = kw
                    ref_ratio = avg_ratio
                    ref_volume = vol

        normalized = []
        for point in interest_data:
            keyword = point["keyword"]
            date = point["date"]
            value = point["value"]

            estimated_volume = None
            method = "none"

            if ref_keyword and ref_ratio > 0 and value > 0:
                estimated_volume = int((value / ref_ratio) * ref_volume)
                method = "google_keyword_ratio"

            normalized.append({
                "keyword": keyword,
                "platform": "google",
                "period": date,
                "ratio": value,
                "estimated_volume": estimated_volume,
                "reference_keyword": ref_keyword,
                "normalization_method": method,
            })

        logger.info(f"✅ Google Trends 정규화 완료: {len(normalized)}건")
        return normalized


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 테스트: 가상 데이터로 정규화 테스트
    normalizer = SearchVolumeNormalizer()

    # 1. 기준 검색량 설정 (검색광고 API 데이터 가정)
    mock_searchad = [
        {"relKeyword": "민소매", "monthlyPcQcCnt": 12000, "monthlyMobileQcCnt": 45000},
        {"relKeyword": "오버핏", "monthlyPcQcCnt": 8000, "monthlyMobileQcCnt": 35000},
    ]
    normalizer.set_reference_volumes(mock_searchad)

    # 2. 데이터랩 데이터 정규화 (가상 데이터)
    mock_datalab = {
        "data": [
            {
                "title": "민소매",
                "data": [
                    {"period": "2026-01-01", "ratio": 100},
                    {"period": "2026-02-01", "ratio": 85},
                ]
            },
            {
                "title": "와이드팬츠",
                "data": [
                    {"period": "2026-01-01", "ratio": 60},
                    {"period": "2026-02-01", "ratio": 72},
                ]
            },
        ]
    }

    result = normalizer.normalize_naver_datalab(mock_datalab)
    for r in result:
        print(f"  {r['keyword']} | {r['period']} | ratio={r['ratio']} → 추정 {r['estimated_volume']}회")
