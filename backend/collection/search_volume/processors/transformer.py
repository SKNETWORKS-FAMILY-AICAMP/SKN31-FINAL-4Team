# -*- coding: utf-8 -*-
"""
데이터 변환/통합 모듈

각 API 소스에서 수집한 데이터를 통합 스키마로 변환합니다.
RDS에 적재할 수 있는 표준 형식의 pandas DataFrame으로 가공합니다.
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class DataTransformer:
    """다양한 소스의 검색량 데이터를 통합 스키마로 변환하는 클래스"""

    @staticmethod
    def transform_naver_searchad(raw_data: Dict) -> pd.DataFrame:
        """
        네이버 검색광고 API 결과를 keyword_monthly_volume 테이블 형식으로 변환합니다.

        Returns:
            DataFrame columns:
                keyword, platform, year_month, pc_search_volume,
                mobile_search_volume, total_search_volume,
                competition_level, collected_at
        """
        data_list = raw_data.get("data", [])
        if not data_list:
            logger.warning("⚠️ 네이버 검색광고 변환 대상 데이터 없음")
            return pd.DataFrame()

        now = datetime.now()
        # 검색광고 데이터는 직전 월 기준
        year_month = f"{now.year}-{now.month:02d}"

        records = []
        for item in data_list:
            keyword = item.get("relKeyword", "")
            pc = item.get("monthlyPcQcCnt", 0)
            mobile = item.get("monthlyMobileQcCnt", 0)

            # "< 10" 같은 문자열 처리
            if isinstance(pc, str):
                pc = 5 if "< 10" in pc else 0
            if isinstance(mobile, str):
                mobile = 5 if "< 10" in mobile else 0

            pc = pc or 0
            mobile = mobile or 0

            # 경쟁정도 매핑
            comp_idx = item.get("compIdx", "")
            competition_map = {"높음": "HIGH", "중간": "MEDIUM", "낮음": "LOW"}
            competition = competition_map.get(comp_idx, comp_idx)

            records.append({
                "keyword": keyword,
                "platform": "naver",
                "year_month": year_month,
                "pc_search_volume": pc,
                "mobile_search_volume": mobile,
                "total_search_volume": pc + mobile,
                "competition_level": competition,
                "collected_at": now,
            })

        df = pd.DataFrame(records)
        logger.info(f"✅ 네이버 검색광고 변환 완료: {len(df)}행")
        return df

    @staticmethod
    def transform_google_keyword(raw_data: Dict) -> pd.DataFrame:
        """
        Google Keyword Planner 결과를 keyword_monthly_volume 테이블 형식으로 변환합니다.
        """
        data_list = raw_data.get("data", [])
        if not data_list:
            logger.warning("⚠️ Google Keyword Planner 변환 대상 데이터 없음")
            return pd.DataFrame()

        now = datetime.now()
        year_month = f"{now.year}-{now.month:02d}"

        records = []
        for item in data_list:
            keyword = item.get("keyword", "")
            avg_searches = item.get("avg_monthly_searches", 0) or 0
            competition = item.get("competition", "UNKNOWN")

            records.append({
                "keyword": keyword,
                "platform": "google",
                "year_month": year_month,
                "pc_search_volume": None,  # Google은 PC/모바일 구분 없음
                "mobile_search_volume": None,
                "total_search_volume": avg_searches,
                "competition_level": competition,
                "collected_at": now,
            })

        df = pd.DataFrame(records)
        logger.info(f"✅ Google Keyword Planner 변환 완료: {len(df)}행")
        return df

    @staticmethod
    def transform_trend_data(normalized_data: List[Dict]) -> pd.DataFrame:
        """
        정규화된 트렌드 데이터를 keyword_trend 테이블 형식으로 변환합니다.

        Args:
            normalized_data: normalizer.py에서 정규화된 데이터 리스트

        Returns:
            DataFrame columns:
                keyword, platform, period, ratio,
                estimated_volume, collected_at
        """
        if not normalized_data:
            logger.warning("⚠️ 트렌드 변환 대상 데이터 없음")
            return pd.DataFrame()

        now = datetime.now()

        records = []
        for item in normalized_data:
            records.append({
                "keyword": item.get("keyword", ""),
                "platform": item.get("platform", ""),
                "period": item.get("period", ""),
                "ratio": item.get("ratio", 0),
                "estimated_volume": item.get("estimated_volume"),
                "collected_at": now,
            })

        df = pd.DataFrame(records)

        # period 컬럼을 datetime으로 변환
        if not df.empty:
            df["period"] = pd.to_datetime(df["period"], errors="coerce")

        logger.info(f"✅ 트렌드 데이터 변환 완료: {len(df)}행")
        return df

    @staticmethod
    def merge_monthly_volumes(*dfs: pd.DataFrame) -> pd.DataFrame:
        """
        여러 소스의 월간 검색량 DataFrame을 하나로 병합합니다.
        중복 키(keyword + platform + year_month) 시 최신 데이터를 우선합니다.
        """
        valid_dfs = [df for df in dfs if not df.empty]
        if not valid_dfs:
            return pd.DataFrame()

        merged = pd.concat(valid_dfs, ignore_index=True)

        # 중복 제거: 동일 keyword+platform+year_month에서 최신 collected_at 우선
        if not merged.empty:
            merged = merged.sort_values("collected_at", ascending=False)
            merged = merged.drop_duplicates(
                subset=["keyword", "platform", "year_month"],
                keep="first"
            )

        logger.info(f"✅ 월간 검색량 병합 완료: {len(merged)}행")
        return merged

    @staticmethod
    def merge_trend_data(*dfs: pd.DataFrame) -> pd.DataFrame:
        """
        여러 소스의 트렌드 DataFrame을 하나로 병합합니다.
        """
        valid_dfs = [df for df in dfs if not df.empty]
        if not valid_dfs:
            return pd.DataFrame()

        merged = pd.concat(valid_dfs, ignore_index=True)

        if not merged.empty:
            merged = merged.sort_values("collected_at", ascending=False)
            merged = merged.drop_duplicates(
                subset=["keyword", "platform", "period"],
                keep="first"
            )

        logger.info(f"✅ 트렌드 데이터 병합 완료: {len(merged)}행")
        return merged


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 테스트
    transformer = DataTransformer()

    mock_searchad = {
        "data": [
            {"relKeyword": "민소매", "monthlyPcQcCnt": 12000, "monthlyMobileQcCnt": 45000, "compIdx": "높음"},
            {"relKeyword": "오버핏", "monthlyPcQcCnt": 8000, "monthlyMobileQcCnt": 35000, "compIdx": "중간"},
        ]
    }

    df = transformer.transform_naver_searchad(mock_searchad)
    print(df.to_string(index=False))
