# -*- coding: utf-8 -*-
"""
Google Trends 수집기 (pytrends)

── 무엇이 바뀌었나 (★ 2026-09-21) ─────────────────────────────
① build_payload 를 배치당 **한 번만** 부른다.
   이전에는 get_interest_over_time() 과 get_related_queries() 가 각각
   build_payload 를 새로 불렀다. 같은 키워드·같은 기간인데 두 번 세운 셈이다.
   pytrends 는 429(rate limit)가 유일한 실질 제약이라 이 한 번이 크다.
   → 페이로드 하나로 시계열 · 관련검색어 · 지역별을 **모두** 꺼낸다.
     지역별(G5)을 새로 추가하면서도 전체 호출 수는 오히려 줄어든다.

② interest_by_region(G5) 추가 — ★ 반드시 **키워드 1개짜리 페이로드**로 받는다.
   2026-09-21 스모크 테스트에서 확인: 키워드를 여러 개 넣고 지역을 받으면
   값이 '지역별 용어 점유율'로 온다. 지역마다 합이 정확히 100 이고,
   고프코어가 강원도에서도 100, 경상남도에서도 100 이었다 —
   용어별 정규화라면 100 은 한 지역에만 나와야 하므로 점유율이 맞다.
   그 값을 term × region 으로 적재하면 같은 배치에 누가 묶였느냐에 따라
   숫자가 통째로 바뀌는, 의미 없는 지표가 된다.
   → 용어 하나씩 따로 build_payload 해서 받는다. 그래야 "이 용어는 어느
     시·도에서 상대적으로 강한가"(지역 간 0~100 정규화)가 나온다.
   대신 페이로드가 용어 수만큼 필요해 비싸다 → REGION_LIMIT 개까지만.
   KR 은 16개 시·도가 온다(세종 없음). 검색량이 적은 용어는 대부분 0 이다.

③ trending_searches(G6) 추가 — 단, **알림 전용**이다.
   사전으로 거르면 '이미 아는 용어'만 남으므로 신규 발굴에는 못 쓴다.
   대신 우리 사전 용어가 전국 트렌딩에 진입한 날은 그 자체로 사건이다.
   한 달에 한두 번 걸리는 정도라 화면 자리를 주면 빈칸이 된다.
   그리고 구글이 이 엔드포인트를 자주 바꿔 pytrends 쪽이 잘 깨진다 —
   실패해도 본 파이프라인이 죽지 않도록 전부 삼킨다.

④ 429 백오프. 실패하면 REQUEST_DELAY 를 배로 늘려 최대 3회 재시도한다.
"""

import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))   # ★ insert(0) 금지 — Django 모듈을 가린다
from sv_config.settings import GoogleTrendsConfig

logger = logging.getLogger(__name__)

MAX_RETRY = 3
# 429 를 이만큼 연속으로 맞으면 그날 수집을 접는다 (계속 두드리면 차단이 길어진다)
RATE_LIMIT_GIVEUP = 3


class GoogleTrendsCollector:
    """Google Trends 데이터 수집기 (pytrends 기반)"""

    def __init__(self):
        self.config = GoogleTrendsConfig
        self._pytrends = None
        self._payload_key = None      # 지금 세워져 있는 페이로드의 (키워드, 기간, 지역)
        # ★ 2026-09-23 — 429 를 연속 몇 번 맞았는지 센다.
        #   구글은 같은 IP 가 두드릴수록 차단을 길게 잡는다. 끝까지 재시도하면
        #   그날 수집을 통째로 날리므로, 연속으로 맞으면 조기에 손을 뗀다.
        self.rate_limited = 0
        self.aborted = False

    # ──────────────────────────────────────────────────────────
    #  연결 · 페이로드
    # ──────────────────────────────────────────────────────────

    def _get_pytrends(self):
        """pytrends 연결 객체를 반환합니다. (lazy 초기화)"""
        if self._pytrends is None:
            try:
                from pytrends.request import TrendReq
                self._pytrends = TrendReq(
                    hl=self.config.LANGUAGE,
                    tz=self.config.TIMEZONE,
                )
                logger.info("✅ Google Trends 연결 성공")
            except ImportError:
                logger.error("❌ pytrends 패키지가 설치되지 않았습니다. pip install pytrends")
                raise
            except Exception as e:
                logger.error(f"❌ Google Trends 연결 실패: {e}")
                raise
        return self._pytrends

    def build(self, keywords: List[str], timeframe: str = "today 12-m",
              geo: str = None) -> bool:
        """페이로드를 세운다. 같은 조건이면 다시 세우지 않는다.

        여기서 True 가 나오면 interest_over_time · related_queries ·
        interest_by_region 을 추가 build 없이 이어서 부를 수 있다.
        """
        if geo is None:
            geo = self.config.GEO
        key = (tuple(keywords[:5]), timeframe, geo)
        if key == self._payload_key:
            return True                      # 이미 같은 페이로드가 서 있다

        pytrends = self._get_pytrends()
        delay = self.config.REQUEST_DELAY
        for attempt in range(1, MAX_RETRY + 1):
            try:
                pytrends.build_payload(kw_list=list(keywords[:5]),
                                       timeframe=timeframe, geo=geo)
                self._payload_key = key
                return True
            except Exception as e:
                self._payload_key = None
                if attempt == MAX_RETRY:
                    logger.error(f"❌ 페이로드 생성 실패({attempt}/{MAX_RETRY}): {e}")
                    return False
                logger.warning(f"  ⏳ 페이로드 재시도 {attempt}/{MAX_RETRY} — {delay}초 후 ({e})")
                time.sleep(delay)
                delay *= 2               # 429 백오프
        return False

    # ──────────────────────────────────────────────────────────
    #  개별 조회 — 모두 '이미 세워진 페이로드' 위에서 돈다
    # ──────────────────────────────────────────────────────────

    def _retry(self, call, label, empty):
        """429 를 맞으면 기다렸다 다시 묻는다.

        ★ 2026-09-23 — 백오프가 build() 에만 있었다. 그래서 페이로드는 서고
          정작 데이터 조회에서 429 가 나면 그냥 빈손으로 넘어갔다.
          (실측: "관심도 조회 실패: ... code 429" 바로 뒤 "관심도 데이터 없음")
          조회 쪽에도 같은 백오프를 건다.
        """
        delay = self.config.REQUEST_DELAY
        for attempt in range(1, MAX_RETRY + 1):
            try:
                out = call()
                self.rate_limited = 0          # 한 번 성공하면 연속 카운터를 푼다
                return out
            except Exception as e:
                if "429" not in str(e):
                    logger.error(f"❌ {label} 실패: {e}")
                    return empty
                if attempt == MAX_RETRY:
                    self.rate_limited += 1
                    logger.error(f"❌ {label} — 429 가 {MAX_RETRY}회 이어졌습니다 "
                                 f"(연속 {self.rate_limited}번째)")
                    if self.rate_limited >= RATE_LIMIT_GIVEUP:
                        self.aborted = True
                        logger.error(
                            "⛔ 구글이 계속 429 를 돌려줍니다 — 이 실행을 멈춥니다. "
                            "더 두드리면 차단만 길어집니다. "
                            "FEEDIT_TRENDS_DELAY 를 올리거나 몇 시간 뒤에 다시 도세요.")
                    return empty
                logger.warning(f"  ⏳ {label} 429 — {delay}초 쉬고 재시도 ({attempt}/{MAX_RETRY})")
                time.sleep(delay)
                delay *= 2
        return empty

    def interest_over_time(self) -> pd.DataFrame:
        """관심도 시계열 (0~100). build() 가 먼저 성공해 있어야 한다."""
        def _call():
            df = self._get_pytrends().interest_over_time()
            if not df.empty and "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])
            return df
        return self._retry(_call, "관심도 조회", pd.DataFrame())

    def related_queries(self) -> Dict:
        """관련 검색어 {키워드: {top: DF, rising: DF}}"""
        return self._retry(lambda: self._get_pytrends().related_queries() or {},
                           "관련 검색어 조회", {})

    def interest_by_region(self) -> pd.DataFrame:
        """시·도별 관심도 (G5).

        resolution='REGION' + geo='KR' → 17개 시·도.
        값은 '그 지역 검색량 대비 비율'이라 인구 보정이 이미 들어가 있다.
        """
        def _call():
            df = self._get_pytrends().interest_by_region(
                resolution=self.config.REGION_RESOLUTION,
                inc_low_vol=True,
                inc_geo_code=False,
            )
            return df if df is not None else pd.DataFrame()
        return self._retry(_call, "지역별 관심도 조회", pd.DataFrame())

    # ── 하위 호환 — 예전 이름으로 부르던 코드가 있어 남겨 둔다 ──
    def get_interest_over_time(self, keywords: List[str],
                               timeframe: str = "today 12-m",
                               geo: str = None) -> pd.DataFrame:
        return self.interest_over_time() if self.build(keywords, timeframe, geo) else pd.DataFrame()

    def get_related_queries(self, keywords: List[str],
                            timeframe: str = "today 12-m",
                            geo: str = None) -> Dict:
        return self.related_queries() if self.build(keywords, timeframe, geo) else {}

    def collect_region(self, keywords: List[str], timeframe: str = "today 12-m",
                       limit: int = None) -> List[Dict]:
        """시·도별 관심도 — 용어 **하나씩** 따로 받는다 (G5).

        여러 개를 한 페이로드에 넣으면 '지역 내 점유율'이 와서 못 쓴다.
        (독스트링 ② 참고 — 스모크 테스트로 확인된 사실이다.)
        """
        if not self.config.WITH_REGION:
            return []
        limit = self.config.REGION_LIMIT if limit is None else limit
        targets = keywords[:limit]
        logger.info(f"🗺️  지역별 관심도 수집 (상위 {len(targets)}개 용어, 용어당 페이로드 1회)")

        rows: List[Dict] = []
        for n, kw in enumerate(targets, start=1):
            if self.aborted:
                logger.error(f"⛔ 429 로 중단 — 남은 용어 {len(targets) - n + 1}개를 건너뜁니다.")
                break
            if not self.build([kw], timeframe=timeframe):
                logger.warning(f"  ⚠️ [{n}/{len(targets)}] {kw} — 페이로드 실패, 건너뜀")
                continue
            rdf = self.interest_by_region()
            if rdf.empty or kw not in rdf.columns:
                logger.warning(f"  ⚠️ [{n}/{len(targets)}] {kw} — 지역 데이터 없음 (검색량 부족)")
            else:
                kept = 0
                for region, row in rdf.iterrows():
                    value = row.get(kw)
                    if pd.isna(value):
                        continue
                    rows.append({"keyword": kw, "region": str(region),
                                 "value": int(value)})
                    kept += 1
                logger.info(f"  ✅ [{n}/{len(targets)}] {kw} — {kept}개 시·도")
            if n < len(targets):
                time.sleep(self.config.REQUEST_DELAY)
        return rows

    # ──────────────────────────────────────────────────────────
    #  G6 — 실시간 급상승 (알림 전용)
    # ──────────────────────────────────────────────────────────

    def trending_searches(self, pn: str = "south_korea") -> List[str]:
        """전국 급상승 검색어.

        ★ 이 값을 '신규 키워드 발굴'에 쓰면 안 된다. 사전으로 거르는 순간
          이미 아는 용어만 남아 발굴 가치가 0 이 된다.
          쓰임은 하나다 — 우리 사전 용어가 전국구로 터진 날을 잡아 **알림**을 쏜다.

        구글이 이 엔드포인트를 자주 바꿔 pytrends 가 404/429 로 깨진다.
        깨져도 본 수집이 죽으면 안 되므로 조용히 빈 리스트를 돌려준다.
        """
        if not self.config.WITH_TRENDING:
            return []
        try:
            df = self._get_pytrends().trending_searches(pn=pn)
            if df is None or df.empty:
                return []
            return [str(v).strip() for v in df[0].tolist() if str(v).strip()]
        except Exception as e:
            logger.warning(f"⚠️ 실시간 급상승 조회 실패 — 건너뜁니다 ({e})")
            return []

    @staticmethod
    def match_dictionary(trending: List[str], dictionary_terms: List[str]) -> List[Dict]:
        """급상승 목록에서 우리 사전에 있는 것만 골라낸다 (알림용).

        부분일치까지 본다 — 트렌딩은 "올드머니 룩" 처럼 꾸며 붙어 오는 일이 많다.
        """
        hits = []
        for rank, phrase in enumerate(trending, start=1):
            for term in dictionary_terms:
                if term and term in phrase:
                    hits.append({"term": term, "phrase": phrase, "rank": rank})
                    break
        return hits

    # ──────────────────────────────────────────────────────────
    #  배치 수집
    # ──────────────────────────────────────────────────────────

    def collect(
        self,
        keywords: List[str],
        timeframe: str = "today 12-m",
        dictionary_terms: Optional[List[str]] = None,
        region_keywords: Optional[List[str]] = None,
    ) -> Dict:
        """키워드 목록을 5개씩 묶어 수집한다.

        배치 하나에 build_payload 1회 + 조회 2~3회.
        """
        logger.info(f"🚀 Google Trends 수집 시작 (키워드 {len(keywords)}개)")

        all_interest_data: List[Dict] = []
        all_related: Dict = {}
        all_region: List[Dict] = []
        batch_size = 5
        total_batches = (len(keywords) + batch_size - 1) // batch_size

        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            n = i // batch_size + 1
            if self.aborted:
                logger.error(f"⛔ 429 로 중단 — 남은 배치 {total_batches - n + 1}개를 건너뜁니다.")
                break
            logger.info(f"📡 [{n}/{total_batches}] Google Trends 조회: {batch}")

            # ★ 페이로드는 여기서 딱 한 번
            if not self.build(batch, timeframe=timeframe):
                logger.error(f"  ❌ 배치 건너뜀 — 페이로드 실패: {batch}")
                continue

            # 1) 관심도 시계열 (G1)
            df = self.interest_over_time()
            if not df.empty:
                for col in df.columns:
                    for date_idx, value in df[col].items():
                        all_interest_data.append({
                            "date": date_idx.strftime("%Y-%m-%d"),
                            "keyword": col,
                            "value": int(value),
                        })
                logger.info(f"  ✅ 관심도 {len(df)}행")
            else:
                logger.warning("  ⚠️ 관심도 데이터 없음")

            # 2) 관련 검색어 (G2 rising · G3 top)
            time.sleep(self.config.REQUEST_DELAY)
            for kw, data in (self.related_queries() or {}).items():
                info = {}
                top, rising = (data or {}).get("top"), (data or {}).get("rising")
                if top is not None and not top.empty:
                    info["top"] = top.to_dict("records")
                if rising is not None and not rising.empty:
                    info["rising"] = rising.to_dict("records")
                if info:
                    all_related[kw] = info
            logger.info("  ✅ 관련 검색어")

            if i + batch_size < len(keywords):
                logger.info(f"  ⏳ Rate limit 대기 ({self.config.REQUEST_DELAY}초)...")
                time.sleep(self.config.REQUEST_DELAY)

        # 3) 시·도별 관심도 (G5) — 본 배치가 끝난 뒤 용어 단건으로
        all_region = self.collect_region(region_keywords or keywords,
                                         timeframe=timeframe)

        # 4) 실시간 급상승 (G6) — 하루 1회, 전체에서 한 번만
        trending = self.trending_searches()
        trending_hits = (self.match_dictionary(trending, dictionary_terms)
                         if (trending and dictionary_terms) else [])
        if trending:
            logger.info(f"  ✅ 실시간 급상승 {len(trending)}건 · 사전 적중 {len(trending_hits)}건")

        return {
            "source": "google_trends",
            "collected_at": datetime.now().isoformat(),
            "geo": self.config.GEO,
            "timeframe": timeframe,
            "keywords_count": len(keywords),
            "interest_data_count": len(all_interest_data),
            "interest_over_time": all_interest_data,
            "related_queries": all_related,
            "interest_by_region": all_region,      # ★ 신규 (G5)
            "trending": trending,                  # ★ 신규 (G6) 원본
            "trending_hits": trending_hits,        # ★ 신규 (G6) 사전 적중 — 알림용
            # ★ 429 로 중간에 접었는지. 크론이 "0건 수집" 으로 조용히 끝나면
            #   화면에 아무 티도 안 나므로, 부른 쪽이 알 수 있게 실어 보낸다.
            "rate_limited": self.aborted,
        }


if __name__ == "__main__":
    # 단독 스모크 테스트:  python collectors/google_trends.py
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    collector = GoogleTrendsCollector()

    test_keywords = ["스트릿웨어", "고프코어", "발레코어"]
    result = collector.collect(test_keywords, timeframe="today 3-m",
                               dictionary_terms=test_keywords)

    print("\n── 스모크 테스트 결과 ─────────────────────────")
    print(f"  G1 관심도 시계열   : {result['interest_data_count']}건")
    print(f"  G2/G3 관련 검색어  : {len(result['related_queries'])}개 키워드")
    print(f"  G5 지역별          : {len(result['interest_by_region'])}건")
    print(f"  G6 실시간 급상승   : {len(result['trending'])}건 "
          f"(사전 적중 {len(result['trending_hits'])}건)")
    print("───────────────────────────────────────────────")
    if result["interest_by_region"]:
        print("\n[G5 샘플]")
        print(json.dumps(result["interest_by_region"][:10], ensure_ascii=False, indent=2))
    if result["trending"]:
        print("\n[G6 원본 상위 10]")
        print(json.dumps(result["trending"][:10], ensure_ascii=False, indent=2))
    else:
        print("\n[G6] 값이 안 옵니다 — 구글이 엔드포인트를 바꿨을 수 있습니다.")
        print("     FEEDIT_TRENDS_TRENDING=0 으로 꺼두고 가도 나머지는 정상 동작합니다.")
