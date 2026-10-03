# -*- coding: utf-8 -*-
"""
네이버 검색광고 API (키워드 도구) - 월간 절대 검색량 수집

네이버 검색광고 플랫폼의 RelKwdStat(연관 키워드 통계) API를 사용하여
키워드별 월간 PC/모바일 절대 검색량, 클릭수, 경쟁정도 등을 조회합니다.

API 문서: https://naver.github.io/searchad-apidoc/#/tags/RelKwdStat
인증 방식: HMAC-SHA256 서명
"""

import time
import hmac
import hashlib
import base64
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

import requests

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))   # ★ insert(0) 금지 — Django 모듈을 가린다
from sv_config.settings import NaverSearchAdConfig

logger = logging.getLogger(__name__)


class NaverSearchAdCollector:
    """네이버 검색광고 API를 통한 키워드 월간 검색량 수집기"""

    def __init__(self):
        self.config = NaverSearchAdConfig
        if not self.config.is_configured():
            logger.warning("⚠️ 네이버 검색광고 API 키가 설정되지 않았습니다.")

    def _generate_signature(self, timestamp: str, method: str, uri: str) -> str:
        """
        HMAC-SHA256 서명을 생성합니다.
        네이버 검색광고 API는 모든 요청에 서명이 필요합니다.
        """
        secret_key = self.config.SECRET_KEY
        message = f"{timestamp}.{method}.{uri}"
        sign = hmac.new(
            secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).digest()
        return base64.b64encode(sign).decode("utf-8")

    def _build_headers(self, method: str, uri: str) -> dict:
        """API 요청 헤더를 구성합니다."""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, uri)

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": timestamp,
            "X-API-KEY": self.config.API_KEY,
            "X-Signature": signature,
        }
        if self.config.CUSTOMER_ID:
            headers["X-Customer"] = self.config.CUSTOMER_ID
        return headers

    def get_keyword_stats(
        self,
        keywords: List[str],
        show_detail: int = 1
    ) -> List[Dict]:
        """
        키워드 목록의 월간 검색 통계를 조회합니다.

        Args:
            keywords: 조회할 키워드 목록
            show_detail: 1이면 월별 상세 데이터 포함

        Returns:
            키워드별 검색 통계 리스트
            [
                {
                    "relKeyword": "민소매",
                    "monthlyPcQcCnt": 12000,
                    "monthlyMobileQcCnt": 45000,
                    "monthlyAvePcClkCnt": 800,
                    "monthlyAveMobileClkCnt": 3200,
                    "monthlyAvePcCtr": 2.5,
                    "monthlyAveMobileCtr": 3.1,
                    "plAvgDepth": 15,
                    "compIdx": "높음"
                }, ...
            ]
        """
        if not self.config.is_configured():
            logger.error("❌ 네이버 검색광고 API가 설정되지 않았습니다.")
            return []

        uri = "/keywordstool"
        method = "GET"
        url = f"{self.config.BASE_URL}{uri}"

        all_results = []

        # API는 한 번에 최대 5개 키워드까지 조회 가능
        batch_size = 5
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            # 네이버 API는 띄어쓰기가 포함된 키워드를 거부하므로 공백 제거
            keyword_str = ",".join([k.replace(" ", "") for k in batch])

            headers = self._build_headers(method, uri)
            params = {
                "hintKeywords": keyword_str,
                "showDetail": show_detail,
            }

            try:
                logger.info(f"📡 네이버 검색광고 API 호출: {batch}")
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()

                data = response.json()
                keyword_list = data.get("keywordList", [])
                all_results.extend(keyword_list)

                logger.info(f"  ✅ {len(keyword_list)}개 키워드 결과 수신")

            except requests.exceptions.HTTPError as e:
                logger.error(f"  ❌ HTTP 오류: {e}")
                logger.error(f"  응답: {response.text}")
            except requests.exceptions.RequestException as e:
                logger.error(f"  ❌ 요청 오류: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"  ❌ JSON 파싱 오류: {e}")

            # Rate limit 대응: 요청 간 대기
            if i + batch_size < len(keywords):
                time.sleep(1)

        return all_results

    def collect(self, keywords: List[str]) -> Dict:
        """
        키워드 검색량 데이터를 수집하고 표준 형식으로 반환합니다.

        Returns:
            {
                "source": "naver_searchad",
                "collected_at": "2026-09-14T09:00:00",
                "keywords_count": 25,
                "data": [ ... ]
            }
        """
        logger.info(f"🚀 네이버 검색광고 API 수집 시작 (키워드 {len(keywords)}개)")
        results = self.get_keyword_stats(keywords)

        return {
            "source": "naver_searchad",
            "collected_at": datetime.now().isoformat(),
            "keywords_count": len(keywords),
            "results_count": len(results),
            "data": results,
        }


if __name__ == "__main__":
    # 단독 실행 테스트
    logging.basicConfig(level=logging.INFO)
    collector = NaverSearchAdCollector()

    test_keywords = ["민소매", "오버핏", "와이드팬츠"]
    result = collector.collect(test_keywords)

    print(json.dumps(result, ensure_ascii=False, indent=2))
