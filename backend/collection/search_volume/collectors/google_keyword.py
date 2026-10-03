# -*- coding: utf-8 -*-
"""
Google Keyword Planner API - 구글 월간 검색량 수집

Google Ads API의 KeywordPlannerService를 통해
키워드별 월간 검색량, 경쟁도, CPC 등을 조회합니다.

⚠️ 사전 준비:
1. Google Ads 계정 생성
2. API 개발자 토큰 발급 (승인까지 며칠 소요)
3. OAuth2 인증 설정

API 문서: https://developers.google.com/google-ads/api/docs/keyword-planning/overview
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))   # ★ insert(0) 금지 — Django 모듈을 가린다
from sv_config.settings import GoogleKeywordConfig

logger = logging.getLogger(__name__)


class GoogleKeywordCollector:
    """Google Keyword Planner API를 통한 월간 검색량 수집기"""

    def __init__(self):
        self.config = GoogleKeywordConfig
        self._client = None
        if not self.config.is_configured():
            logger.warning(
                "⚠️ Google Ads API가 설정되지 않았습니다. "
                "Google Keyword Planner 기능은 비활성화됩니다."
            )

    def _get_client(self):
        """Google Ads API 클라이언트를 반환합니다. (lazy 초기화)"""
        if self._client is None:
            try:
                from google.ads.googleads.client import GoogleAdsClient

                credentials = {
                    "developer_token": self.config.DEVELOPER_TOKEN,
                    "client_id": self.config.CLIENT_ID,
                    "client_secret": self.config.CLIENT_SECRET,
                    "refresh_token": self.config.REFRESH_TOKEN,
                    "login_customer_id": self.config.LOGIN_CUSTOMER_ID,
                    "use_proto_plus": True,
                }
                self._client = GoogleAdsClient.load_from_dict(credentials)
                logger.info("✅ Google Ads API 클라이언트 초기화 성공")
            except ImportError:
                logger.error("❌ google-ads 패키지가 설치되지 않았습니다. pip install google-ads")
                raise
            except Exception as e:
                logger.error(f"❌ Google Ads API 클라이언트 초기화 실패: {e}")
                raise
        return self._client

    def get_keyword_metrics(
        self,
        keywords: List[str],
        language_id: str = "1012",  # 한국어
        location_id: str = "2410",  # 대한민국
    ) -> List[Dict]:
        """
        키워드의 월간 검색량 메트릭을 조회합니다.

        Args:
            keywords: 키워드 목록
            language_id: 언어 코드 (1012 = 한국어)
            location_id: 지역 코드 (2410 = 대한민국)

        Returns:
            [
                {
                    "keyword": "민소매",
                    "avg_monthly_searches": 22000,
                    "competition": "MEDIUM",
                    "competition_index": 45,
                    "low_top_of_page_bid": 500,
                    "high_top_of_page_bid": 1200,
                    "monthly_search_volumes": [
                        {"year": 2026, "month": 1, "monthly_searches": 15000},
                        ...
                    ]
                }, ...
            ]
        """
        if not self.config.is_configured():
            logger.error("❌ Google Ads API가 설정되지 않았습니다.")
            return []

        try:
            client = self._get_client()
            keyword_plan_idea_service = client.get_service("KeywordPlanIdeaService")

            # 리소스 이름 구성
            customer_id = self.config.CUSTOMER_ID.replace("-", "")
            language_rn = client.get_service("GoogleAdsService").language_constant_path(language_id)
            location_rn = client.get_service("GoogleAdsService").geo_target_constant_path(location_id)

            # 요청 구성
            request = client.get_type("GenerateKeywordIdeasRequest")
            request.customer_id = customer_id
            request.language = language_rn
            request.geo_target_constants.append(location_rn)
            request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
            request.keyword_seed.keywords.extend(keywords)

            # API 호출
            logger.info(f"📡 Google Keyword Planner API 호출: {len(keywords)}개 키워드")
            response = keyword_plan_idea_service.generate_keyword_ideas(request=request)

            results = []
            for idea in response:
                metrics = idea.keyword_idea_metrics

                # 월별 검색량 파싱
                monthly_volumes = []
                if metrics.monthly_search_volumes:
                    for mv in metrics.monthly_search_volumes:
                        monthly_volumes.append({
                            "year": mv.year,
                            "month": mv.month.name,
                            "monthly_searches": mv.monthly_searches,
                        })

                results.append({
                    "keyword": idea.text,
                    "avg_monthly_searches": metrics.avg_monthly_searches,
                    "competition": metrics.competition.name if metrics.competition else None,
                    "competition_index": metrics.competition_index,
                    "low_top_of_page_bid": metrics.low_top_of_page_bid_micros / 1_000_000 if metrics.low_top_of_page_bid_micros else None,
                    "high_top_of_page_bid": metrics.high_top_of_page_bid_micros / 1_000_000 if metrics.high_top_of_page_bid_micros else None,
                    "monthly_search_volumes": monthly_volumes,
                })

            logger.info(f"  ✅ {len(results)}개 키워드 결과 수신")
            return results

        except Exception as e:
            logger.error(f"  ❌ Google Keyword Planner 오류: {e}")
            return []

    def collect(self, keywords: List[str]) -> Dict:
        """
        키워드 검색량 데이터를 수집하고 표준 형식으로 반환합니다.

        Returns:
            {
                "source": "google_keyword",
                "collected_at": "2026-09-14T09:00:00",
                "keywords_count": 25,
                "data": [ ... ]
            }
        """
        logger.info(f"🚀 Google Keyword Planner 수집 시작 (키워드 {len(keywords)}개)")

        # Google Ads API는 한 번에 많은 키워드를 처리할 수 있음
        # 하지만 안전하게 20개씩 배치 처리
        all_results = []
        batch_size = 20

        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            results = self.get_keyword_metrics(batch)
            all_results.extend(results)

        return {
            "source": "google_keyword",
            "collected_at": datetime.now().isoformat(),
            "keywords_count": len(keywords),
            "results_count": len(all_results),
            "data": all_results,
        }


if __name__ == "__main__":
    # 단독 실행 테스트
    logging.basicConfig(level=logging.INFO)
    collector = GoogleKeywordCollector()

    test_keywords = ["민소매", "오버핏", "와이드팬츠"]
    result = collector.collect(test_keywords)

    print(json.dumps(result, ensure_ascii=False, indent=2))
