# -*- coding: utf-8 -*-
"""
네이버 데이터랩 통합 검색어 트렌드 API - 검색 트렌드 상대값 수집

네이버 데이터랩 API를 통해 키워드의 일별/주별/월별 검색 추이를
상대값(ratio 0~100)으로 수집합니다.

API 문서: https://developers.naver.com/docs/serviceapi/datalab/search/search.md
인증 방식: X-Naver-Client-Id / X-Naver-Client-Secret 헤더
호출 한도: 1,000회/일
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))   # ★ insert(0) 금지 — Django 모듈을 가린다
from sv_config.settings import NaverDatalabConfig

logger = logging.getLogger(__name__)

# ── 세그먼트 수집 (D2 성별 · D3 연령) ────────────────────────────
#  ★ 2026-09-21
#  데이터랩은 요청 하나에 키워드 5개 + 세그먼트 값 **하나**다.
#  ages 에 배열을 넣으면 그 구간들을 **합친 한 줄**이 오지, 구간별로 쪼개 오지 않는다.
#  그래서 연령대별로 보려면 구간마다 요청을 따로 쏴야 한다.
#
#  543개 용어 기준 컷 하나당 ceil(543/5) = 109회.
#    D1 전체        109
#    D2 성별(m,f)   218
#    D3 연령 11구간 1,199   ← 이것만으로 하루 한도(1,000) 초과
#    D3 연령 5버킷    545
#  D1+D2+D3(5버킷) = 872/1,000. 돌긴 하지만 재시도 한 번이면 그날 끝난다.
#
#  결론: **세그먼트는 매일 받을 값이 아니다.**
#  "이 스타일은 20대 여성이 주도한다"는 캐릭터 규정이지 일간 변동값이 아니다.
#  D1 은 매일, D2·D3 는 주 1회(요일 분산). 7일 간격이면 노이즈도 덜하다.
AGE_BUCKETS = {
    "10s":   ["2"],                  # 13~18
    "20s":   ["3", "4"],             # 19~29
    "30s":   ["5", "6"],             # 30~39
    "40s":   ["7", "8"],             # 40~49
    "50s+":  ["9", "10", "11"],      # 50~
}
GENDERS = {"m": "남성", "f": "여성"}


def estimate_calls(keyword_count: int, *, with_gender: bool = False,
                   age_buckets: int = 0) -> int:
    """이 조합이 하루 한도(1,000) 안에 드는지 미리 센다."""
    per_cut = -(-keyword_count // 5)          # ceil
    cuts = 1 + (2 if with_gender else 0) + age_buckets
    return per_cut * cuts


class NaverDatalabCollector:
    """네이버 데이터랩 API를 통한 검색 트렌드 수집기"""

    def __init__(self):
        self.config = NaverDatalabConfig
        self.calls_used = 0          # ★ 하루 1,000회 한도를 실제로 얼마나 썼는지
        if not self.config.is_configured():
            logger.warning("⚠️ 네이버 데이터랩 API 키가 설정되지 않았습니다.")
        # ★ 2026-09-21 — 원래 여기 "Client ID 가 20자 미만이면 NCP 키로 간주" 라는
        #   길이 추정이 있었는데 **방향이 거꾸로였다.**
        #   developers.naver.com 에서 발급하는 오픈 API Client ID 가 10자 안팎이고,
        #   NCP(API Gateway) 키가 더 길다. 우리 키는 10자라 그 조건에 걸려
        #   ntruss.com 게이트웨이로 나가고 있었다 → 무조건 401.
        #   추정을 버리고 명시 스위치로 바꾼다. 기본은 developers.naver.com.
        use_ncp = (os.getenv("NAVER_DATALAB_USE_NCP") or "").strip() == "1"
        if use_ncp:
            self.api_url = "https://naveropenapi.apigw.ntruss.com/datalab/v1/search"
            self.headers = {
                "X-NCP-APIGW-API-KEY-ID": self.config.CLIENT_ID,
                "X-NCP-APIGW-API-KEY": self.config.CLIENT_SECRET,
                "Content-Type": "application/json",
            }
        else:
            self.api_url = "https://openapi.naver.com/v1/datalab/search"
            self.headers = {
                "X-Naver-Client-Id": self.config.CLIENT_ID,
                "X-Naver-Client-Secret": self.config.CLIENT_SECRET,
                "Content-Type": "application/json",
            }
        logger.debug("데이터랩 엔드포인트: %s", self.api_url)

    # ── 세그먼트 일괄 수집 (D2 + D3) ─────────────────────────
    def collect_segments(
        self,
        keywords: List[str],
        start_date: str = None,
        end_date: str = None,
        time_unit: str = "week",
        with_gender: bool = True,
        buckets: Dict[str, List[str]] = None,
        budget: int = None,
    ) -> List[Dict]:
        """성별·연령 컷을 한 번에 돌린다. 한도를 넘길 것 같으면 **시작 전에** 멈춘다.

        반환: collect() 결과의 리스트 (각각 segment 라벨이 붙어 있다)
        """
        buckets = AGE_BUCKETS if buckets is None else buckets
        budget = budget or self.config.DAILY_LIMIT
        need = estimate_calls(len(keywords), with_gender=with_gender,
                              age_buckets=len(buckets)) - -(-len(keywords) // 5)
        if need > budget:
            raise RuntimeError(
                f"데이터랩 호출 {need}회가 필요한데 예산은 {budget}회입니다. "
                f"용어 수를 줄이거나(상위 N개만) 컷을 요일에 나눠 도세요."
            )
        logger.info(f"🧮 세그먼트 수집 예상 호출 {need}회 / 예산 {budget}회")

        out = []
        if with_gender:
            for code, label in GENDERS.items():
                logger.info(f"  ▶ 성별 컷: {label}")
                out.append(self.collect(keywords, start_date, end_date, time_unit,
                                        gender=code, segment=f"gender:{code}"))
        for name, codes in buckets.items():
            logger.info(f"  ▶ 연령 컷: {name}")
            out.append(self.collect(keywords, start_date, end_date, time_unit,
                                    ages=codes, segment=f"age:{name}"))
        return out

    def _build_headers(self) -> dict:
        """API 요청 헤더를 구성합니다."""
        return self.headers

    def get_search_trend(
        self,
        keyword_groups: List[Dict],
        start_date: str = None,
        end_date: str = None,
        time_unit: str = "date",
        device: str = None,
        gender: str = None,
        ages: List[str] = None,
    ) -> Dict:
        """
        키워드 그룹의 검색 트렌드를 조회합니다.

        Args:
            keyword_groups: 키워드 그룹 리스트 (최대 5개)
                [{"groupName": "민소매", "keywords": ["민소매", "민소매티"]}]
            start_date: 시작 날짜 (yyyy-mm-dd). 기본값: 1년 전
            end_date: 종료 날짜 (yyyy-mm-dd). 기본값: 어제
            time_unit: 구간 단위 - "date"(일간), "week"(주간), "month"(월간)
            device: "pc" | "mo" | None(전체)
            gender: "m" | "f" | None(전체)
            ages: 연령대 리스트 ["1","2",...] | None(전체)

        Returns:
            API 응답 JSON
        """
        if not self.config.is_configured():
            logger.error("❌ 네이버 데이터랩 API가 설정되지 않았습니다.")
            return {}

        # 기본 날짜 설정: 최근 1년
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "keywordGroups": keyword_groups[:5],  # 최대 5개
        }

        # 선택적 파라미터 추가
        if device:
            body["device"] = device
        if gender:
            body["gender"] = gender
        if ages:
            body["ages"] = ages

        headers = self._build_headers()

        try:
            logger.info(f"📡 네이버 데이터랩 API 호출: {[g['groupName'] for g in keyword_groups[:5]]}")
            self.calls_used += 1
            if self.calls_used > self.config.DAILY_LIMIT:
                # 한도를 넘겨 400 을 받고 나서 알아채면 그날 수집이 통째로 어그러진다.
                raise RuntimeError(
                    f"데이터랩 일일 한도({self.config.DAILY_LIMIT}회)를 넘겼습니다 "
                    f"— {self.calls_used}회째. 세그먼트 컷을 요일에 나눠 도세요."
                )
            response = requests.post(
                self.api_url,
                headers=headers,
                data=json.dumps(body),
                timeout=30,
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"  ✅ {len(data.get('results', []))}개 그룹 결과 수신")
            return data

        except requests.exceptions.HTTPError as e:
            logger.error(f"  ❌ HTTP 오류: {e}")
            logger.error(f"  응답: {response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"  ❌ 요청 오류: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"  ❌ JSON 파싱 오류: {e}")

        return {}

    def collect(
        self,
        keywords: List[str],
        start_date: str = None,
        end_date: str = None,
        time_unit: str = "date",
        device: str = None,
        gender: str = None,
        ages: List[str] = None,
        segment: str = "all",
    ) -> Dict:
        """
        키워드 목록의 검색 트렌드를 수집합니다.
        키워드가 5개를 초과할 경우 배치로 나누어 호출합니다.

        Args:
            keywords: 키워드 목록
            start_date: 시작 날짜
            end_date: 종료 날짜
            time_unit: 구간 단위

        Returns:
            {
                "source": "naver_datalab",
                "collected_at": "2026-09-14T09:00:00",
                "start_date": "2025-09-14",
                "end_date": "2026-09-13",
                "time_unit": "date",
                "keywords_count": 25,
                "data": [ ... ]
            }
        """
        logger.info(f"🚀 네이버 데이터랩 API 수집 시작 (키워드 {len(keywords)}개)")

        all_results = []
        batch_size = 5  # 한 번에 최대 5개 키워드 그룹

        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]

            # 각 키워드를 개별 그룹으로 구성
            keyword_groups = [
                {"groupName": kw, "keywords": [kw]}
                for kw in batch
            ]

            result = self.get_search_trend(
                keyword_groups=keyword_groups,
                start_date=start_date,
                end_date=end_date,
                time_unit=time_unit,
                device=device,
                gender=gender,
                ages=ages,
            )

            if result and "results" in result:
                all_results.extend(result["results"])

            # Rate limit 대응
            if i + batch_size < len(keywords):
                time.sleep(1)

        return {
            "source": "naver_datalab",
            "collected_at": datetime.now().isoformat(),
            "start_date": start_date or (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
            "end_date": end_date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "time_unit": time_unit,
            "keywords_count": len(keywords),
            "results_count": len(all_results),
            "segment": segment,          # ★ all | gender:m | age:20 …
            "device": device,
            "gender": gender,
            "ages": ages,
            "calls_used": self.calls_used,
            "data": all_results,
        }


if __name__ == "__main__":
    # 단독 실행 테스트
    logging.basicConfig(level=logging.INFO)
    collector = NaverDatalabCollector()

    test_keywords = ["민소매", "오버핏", "와이드팬츠"]
    result = collector.collect(test_keywords, time_unit="month")

    print(json.dumps(result, ensure_ascii=False, indent=2))
