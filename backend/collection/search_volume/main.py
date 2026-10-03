# -*- coding: utf-8 -*-
"""
패션 트렌드 키워드 검색량 수집 파이프라인

처리 순서:
1. CSV 사전에서 키워드 로드
2. [Collect] 네이버 검색광고 + 데이터랩 + Google Trends API 호출
3. [Save Raw] 원본 raw 데이터 → output/raw/ 에 CSV/JSON 저장
4. [Process] 정규화 전처리 (상대값 → 절대검색량 치환)
5. [Save Processed] 전처리 결과 → output/processed/ 에 CSV 저장

산출물:
  output/raw/         원본 API 응답 그대로
  output/processed/   절대검색량으로 치환된 최종 데이터
"""

import io
import os
import sys
import json
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent
sys.path.append(str(PROJECT_ROOT))   # ★ insert(0) 금지 — Django 모듈을 가린다

from sv_config.settings import (
    load_keywords_from_csv, get_keyword_names, check_all_configs,
    NaverSearchAdConfig, NaverDatalabConfig,
    GoogleTrendsConfig, GoogleKeywordConfig,
)
from collectors.naver_searchad import NaverSearchAdCollector
from collectors.naver_datalab import NaverDatalabCollector
from collectors.google_trends import GoogleTrendsCollector
from collectors.google_keyword import GoogleKeywordCollector

logger = logging.getLogger(__name__)

# 출력 디렉토리
NOW_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
RAW_DIR = PROJECT_ROOT / "output" / "raw" / NOW_STR
PROCESSED_DIR = PROJECT_ROOT / "output" / "processed" / NOW_STR


def setup_logging(verbose: bool = False):
    """로깅 설정"""
    level = logging.DEBUG if verbose else logging.INFO
    stream_handler = logging.StreamHandler(
        io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    )
    file_handler = logging.FileHandler(
        PROJECT_ROOT / "pipeline.log", encoding="utf-8",
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[stream_handler, file_handler],
    )


# ============================================================
# STEP 1: 수집 (Collect)
# ============================================================

def collect_naver_searchad(keywords: list) -> pd.DataFrame:
    """네이버 검색광고 API → 월간 절대 검색량 수집"""
    if not NaverSearchAdConfig.is_configured():
        logger.warning("[SKIP] 네이버 검색광고 API 미설정")
        return pd.DataFrame()

    collector = NaverSearchAdCollector()
    result = collector.collect(keywords)
    data = result.get("data", [])

    if not data:
        logger.warning("[WARN] 네이버 검색광고 응답 데이터 없음")
        return pd.DataFrame()

    rows = []
    for item in data:
        kw = item.get("relKeyword", "")
        pc = item.get("monthlyPcQcCnt", 0)
        mobile = item.get("monthlyMobileQcCnt", 0)

        # "< 10" 같은 문자열 처리
        if isinstance(pc, str):
            pc = 5 if "< 10" in pc else 0
        if isinstance(mobile, str):
            mobile = 5 if "< 10" in mobile else 0

        pc = pc or 0
        mobile = mobile or 0

        rows.append({
            "keyword": kw,
            "platform": "naver",
            "data_type": "monthly_absolute",
            "pc_search_volume": pc,
            "mobile_search_volume": mobile,
            "total_search_volume": pc + mobile,
            "competition": item.get("compIdx", ""),
            "monthly_avg_pc_click": item.get("monthlyAvePcClkCnt", 0),
            "monthly_avg_mobile_click": item.get("monthlyAveMobileClkCnt", 0),
        })

    df = pd.DataFrame(rows)
    
    # 네이버 API는 띄어쓰기를 무시하고 결과를 주거나 연관검색어를 주므로, 공백을 제거한 기준으로 원본 키워드와 매핑합니다.
    df["keyword_no_space"] = df["keyword"].astype(str).str.replace(" ", "")
    valid_keywords_no_space = [k.replace(" ", "") for k in keywords]
    
    # 사전에 있는 단어만 남김 (공백 제거 기준)
    df = df[df["keyword_no_space"].isin(valid_keywords_no_space)].copy()
    
    # 원본 키워드 복원 (공백 있는 원래 형태로 되돌리기)
    mapping = {k.replace(" ", ""): k for k in keywords}
    df["keyword"] = df["keyword_no_space"].map(mapping)
    df = df.drop(columns=["keyword_no_space"])
    
    # 여러 번 조회된 중복 키워드 제거
    df = df.drop_duplicates(subset=["keyword"], keep="first")
    
    logger.info(f"[OK] 네이버 검색광고: {len(df)}개 키워드 수집 (중복 제거 및 필터링 후)")
    return df


def collect_naver_datalab(keywords: list) -> pd.DataFrame:
    """네이버 데이터랩 API → 트렌드 상대값 수집"""
    if not NaverDatalabConfig.is_configured():
        logger.warning("[SKIP] 네이버 데이터랩 API 미설정")
        return pd.DataFrame()

    collector = NaverDatalabCollector()
    result = collector.collect(keywords, time_unit="month")
    data = result.get("data", [])

    if not data:
        logger.warning("[WARN] 네이버 데이터랩 응답 데이터 없음")
        return pd.DataFrame()

    rows = []
    for group in data:
        kw = group.get("title", "")
        for point in group.get("data", []):
            rows.append({
                "keyword": kw,
                "platform": "naver",
                "data_type": "trend_relative",
                "period": point.get("period", ""),
                "ratio": point.get("ratio", 0),
            })

    df = pd.DataFrame(rows)
    logger.info(f"[OK] 네이버 데이터랩: {len(df)}건 수집")
    return df


TRENDS_CACHE = PROJECT_ROOT / "cache" / "raw_google_trends_backup.csv"


def collect_google_trends(keywords: list, dictionary_terms: list = None) -> pd.DataFrame:
    """Google Trends → 주간 상대지수(G1) 수집. 지역별(G5)·급상승(G6)은 옆에 따로 떨군다.

    ★ 2026-09-21 — 예전 이 함수는 수집기를 아예 부르지 않고 개발용 캐시 CSV 한 장을
      읽고 있었다. 그것도 윈도우 절대경로(c:/Users/Playdata/...)라 맥·EC2 에서는
      무조건 실패했고, 설령 읽히더라도 2026-09-14 에 멈춘 값을 계속 보게 된다.
      → 수집기를 실제로 부른다. 캐시는 레포 안 상대경로로 내려 둔 '비상용'이다.

      FEEDIT_TRENDS_CACHE_ONLY=1 → API 를 건드리지 않고 캐시만 읽는다(오프라인 검증용).
    """
    cache_only = (os.getenv("FEEDIT_TRENDS_CACHE_ONLY") or "").strip() == "1"

    if not cache_only:
        try:
            collector = GoogleTrendsCollector()
            result = collector.collect(keywords, dictionary_terms=dictionary_terms)

            # G5 지역별 · G6 급상승은 스키마가 달라 본 DataFrame 에 못 섞는다 — 옆에 떨군다.
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            region = result.get("interest_by_region") or []
            if region:
                path = RAW_DIR / "raw_google_region.csv"
                pd.DataFrame(region).to_csv(path, index=False, encoding="utf-8-sig")
                logger.info(f"[RAW] {path.name} ({len(region)}행)")
            hits = result.get("trending_hits") or []
            if result.get("trending"):
                path = RAW_DIR / "raw_google_trending.json"
                path.write_text(json.dumps(
                    {"trending": result["trending"], "hits": hits},
                    ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info(f"[RAW] {path.name} (급상승 {len(result['trending'])}건 · 사전 적중 {len(hits)}건)")

            rows = result.get("interest_over_time") or []
            if rows:
                df = pd.DataFrame(rows).rename(columns={"date": "period", "value": "ratio"})
                df["platform"] = "google"
                df["data_type"] = "trend_relative"
                logger.info(f"[OK] Google Trends: {len(df)}건 수집")
                return df[["period", "keyword", "ratio", "platform", "data_type"]]
            logger.warning("[WARN] Google Trends 응답이 비었습니다 — 캐시로 내려갑니다.")
        except Exception as e:
            logger.error(f"[ERR] Google Trends 수집 실패: {e} — 캐시로 내려갑니다.")

    try:
        df = pd.read_csv(TRENDS_CACHE, encoding="utf-8-sig")
        logger.warning(f"[CACHE] Google Trends 캐시 사용: {len(df)}건 "
                       f"({TRENDS_CACHE.name}) — 최신 값이 아닙니다.")
        return df
    except Exception as e:
        logger.error(f"[ERR] Google Trends 캐시도 없음: {e}")
        return pd.DataFrame()


def collect_google_keyword(keywords: list) -> pd.DataFrame:
    """Google Ads Keyword Planner → 월간 검색량(절대값) 수집"""
    try:
        collector = GoogleKeywordCollector()
        if not collector.config.is_configured():
            logger.warning("[WARN] Google Keyword API 설정 안됨")
            return pd.DataFrame()
            
        result = collector.collect(keywords)
        data = result.get("data", [])
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        
        # 구글 키워드도 띄어쓰기 무시하고 원본 사전(542개)에 있는 단어만 남깁니다.
        df["keyword_no_space"] = df["keyword"].astype(str).str.replace(" ", "")
        valid_keywords_no_space = [k.replace(" ", "") for k in keywords]
        df = df[df["keyword_no_space"].isin(valid_keywords_no_space)].copy()
        
        # 원본 키워드 복원
        mapping = {k.replace(" ", ""): k for k in keywords}
        df["keyword"] = df["keyword_no_space"].map(mapping)
        df = df.drop(columns=["keyword_no_space"])
        df = df.drop_duplicates(subset=["keyword"], keep="first")   # 중복 응답 제거

        if "avg_monthly_searches" in df.columns:
            df.rename(columns={"avg_monthly_searches": "total_search_volume"}, inplace=True)
            df["platform"] = "google"
            df["data_type"] = "monthly_absolute"
            logger.info(f"[OK] Google Keyword Planner: {len(df)}건 수집 (필터링 후)")
            return df
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"[ERR] Google Keyword 수집 실패: {e}")
        return pd.DataFrame()


# ============================================================
# STEP 2: 원본(Raw) 저장
# ============================================================

def save_raw_data(
    naver_ad_df: pd.DataFrame,
    naver_datalab_df: pd.DataFrame,
    google_trends_df: pd.DataFrame,
    google_ad_df: pd.DataFrame,
):
    """원본 데이터를 그대로 CSV로 저장"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    saved = []
    if not naver_ad_df.empty:
        path = RAW_DIR / "raw_naver_searchad.csv"
        naver_ad_df.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(str(path))
        logger.info(f"[RAW] {path.name} ({len(naver_ad_df)}행)")

    if not naver_datalab_df.empty:
        path = RAW_DIR / "raw_naver_datalab.csv"
        naver_datalab_df.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(str(path))
        logger.info(f"[RAW] {path.name} ({len(naver_datalab_df)}행)")

    if not google_trends_df.empty:
        path = RAW_DIR / "raw_google_trends.csv"
        google_trends_df.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(str(path))
        logger.info(f"[RAW] {path.name} ({len(google_trends_df)}행)")

    if not google_ad_df.empty:
        path = RAW_DIR / "raw_google_keyword.csv"
        google_ad_df.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(str(path))
        logger.info(f"[RAW] {path.name} ({len(google_ad_df)}행)")

    return saved


# ============================================================
# STEP 3: 전처리 - 상대값 → 절대검색량 치환
# ============================================================

def normalize_to_absolute(
    naver_ad_df: pd.DataFrame,
    naver_datalab_df: pd.DataFrame,
    google_trends_df: pd.DataFrame,
    csv_records: list,
) -> tuple:
    """
    핵심 정규화 로직: 상대값(ratio) → 절대검색량 치환

    공식:
        B의 추정 절대검색량 = (B의 ratio / A의 ratio) × A의 월간 절대검색량

    여기서 A = 기준 키워드 (검색광고 API에서 절대 검색량을 아는 키워드)

    Returns:
        (naver_absolute_df, google_absolute_df)
    """

    # ── 1. 기준 검색량 맵 구축 (네이버 검색광고 결과) ──
    ref_volume_map = {}  # {keyword: total_search_volume}
    if not naver_ad_df.empty:
        for _, row in naver_ad_df.iterrows():
            kw = row["keyword"]
            vol = row["total_search_volume"]
            if vol and vol > 0:
                ref_volume_map[kw] = vol

    logger.info(f"[NORM] 기준 절대검색량 키워드: {len(ref_volume_map)}개")

    # ── 2. 네이버 데이터랩 정규화 ──
    naver_abs_rows = []
    if not naver_datalab_df.empty and ref_volume_map:
        # 키워드별 평균 ratio 계산
        kw_avg_ratio = naver_datalab_df.groupby("keyword")["ratio"].mean().to_dict()

        # 가장 좋은 기준 키워드 선택 (ratio 높고 절대검색량 큰 것)
        best_ref = None
        best_score = 0
        for kw, avg_r in kw_avg_ratio.items():
            if kw in ref_volume_map and avg_r > 0:
                score = avg_r * ref_volume_map[kw]
                if score > best_score:
                    best_score = score
                    best_ref = (kw, avg_r, ref_volume_map[kw])

        if best_ref:
            ref_kw, ref_ratio, ref_vol = best_ref
            logger.info(f"[NORM] 네이버 기준 키워드: '{ref_kw}' (ratio={ref_ratio:.1f}, vol={ref_vol})")

            for _, row in naver_datalab_df.iterrows():
                ratio = row["ratio"]
                estimated = int((ratio / ref_ratio) * ref_vol) if ref_ratio > 0 and ratio > 0 else 0

                naver_abs_rows.append({
                    "keyword": row["keyword"],
                    "platform": "naver",
                    "period": row["period"],
                    "ratio": ratio,
                    "estimated_absolute_volume": estimated,
                    "reference_keyword": ref_kw,
                    "reference_volume": ref_vol,
                })
        else:
            logger.warning("[NORM] 네이버 기준 키워드를 찾을 수 없음 (데이터랩+검색광고 교집합 없음)")
            # ratio만이라도 저장
            for _, row in naver_datalab_df.iterrows():
                naver_abs_rows.append({
                    "keyword": row["keyword"],
                    "platform": "naver",
                    "period": row["period"],
                    "ratio": row["ratio"],
                    "estimated_absolute_volume": None,
                    "reference_keyword": None,
                    "reference_volume": None,
                })

    naver_abs_df = pd.DataFrame(naver_abs_rows) if naver_abs_rows else pd.DataFrame()

    # ── 3. Google Trends 정규화 ──
    google_abs_rows = []
    if not google_trends_df.empty:
        # Google은 네이버 검색광고 기준으로 교차 참조
        # (Google Keyword Planner가 없으므로 네이버 기준 사용)
        kw_avg_ratio_g = google_trends_df.groupby("keyword")["ratio"].mean().to_dict()

        best_ref_g = None
        best_score_g = 0
        for kw, avg_r in kw_avg_ratio_g.items():
            if kw in ref_volume_map and avg_r > 0:
                score = avg_r * ref_volume_map[kw]
                if score > best_score_g:
                    best_score_g = score
                    best_ref_g = (kw, avg_r, ref_volume_map[kw])

        if best_ref_g:
            ref_kw_g, ref_ratio_g, ref_vol_g = best_ref_g
            logger.info(f"[NORM] Google 기준 키워드: '{ref_kw_g}' (ratio={ref_ratio_g:.1f}, vol={ref_vol_g})")

            for _, row in google_trends_df.iterrows():
                ratio = row["ratio"]
                estimated = int((ratio / ref_ratio_g) * ref_vol_g) if ref_ratio_g > 0 and ratio > 0 else 0

                google_abs_rows.append({
                    "keyword": row["keyword"],
                    "platform": "google",
                    "period": row["period"],
                    "ratio": ratio,
                    "estimated_absolute_volume": estimated,
                    "reference_keyword": ref_kw_g,
                    "reference_volume": ref_vol_g,
                })
        else:
            logger.warning("[NORM] Google 기준 키워드를 찾을 수 없음")
            for _, row in google_trends_df.iterrows():
                google_abs_rows.append({
                    "keyword": row["keyword"],
                    "platform": "google",
                    "period": row["period"],
                    "ratio": row["ratio"],
                    "estimated_absolute_volume": None,
                    "reference_keyword": None,
                    "reference_volume": None,
                })

    google_abs_df = pd.DataFrame(google_abs_rows) if google_abs_rows else pd.DataFrame()

    return naver_abs_df, google_abs_df


# ============================================================
# STEP 4: 전처리 후 결과 저장
# ============================================================

def save_processed_data(
    naver_ad_df: pd.DataFrame,
    naver_abs_df: pd.DataFrame,
    google_abs_df: pd.DataFrame,
    google_ad_df: pd.DataFrame,
    csv_records: list,
):
    """전처리된 절대검색량 데이터를 CSV로 저장"""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    saved = []

    # 1. 네이버 월간 절대검색량 (검색광고 원본 = 이미 절대값)
    if not naver_ad_df.empty:
        # CSV 사전 정보를 조인
        dict_df = pd.DataFrame(csv_records)
        merged = naver_ad_df.merge(
            dict_df[["term_id", "canonical_name", "search_keyword", "term_type",
                     "english_name", "term_code", "keyword_rank"]],
            left_on="keyword", right_on="search_keyword",
            how="left",
        )
        merged.rename(columns={"keyword": "matched_keyword"}, inplace=True)
        merged.drop(columns=["search_keyword"], inplace=True, errors="ignore")
        merged.rename(columns={"canonical_name": "keyword"}, inplace=True)

        path = PROCESSED_DIR / "processed_naver_monthly_absolute.csv"
        merged.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(str(path))
        logger.info(f"[PROCESSED] {path.name} ({len(merged)}행)")

    # 2. 네이버 데이터랩 → 절대검색량 치환 결과
    if not naver_abs_df.empty:
        path = PROCESSED_DIR / "processed_naver_trend_absolute.csv"
        naver_abs_df.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(str(path))
        logger.info(f"[PROCESSED] {path.name} ({len(naver_abs_df)}행)")

    # 3. Google Trends → 절대검색량 치환 결과
    if not google_abs_df.empty:
        path = PROCESSED_DIR / "processed_google_trend_absolute.csv"
        google_abs_df.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(str(path))
        logger.info(f"[PROCESSED] {path.name} ({len(google_abs_df)}행)")

    # 4. 통합 요약 (키워드별 최종 절대검색량 요약)
    summary_rows = []

    # 네이버 검색광고 (월간 절대)
    if not naver_ad_df.empty:
        for _, row in naver_ad_df.iterrows():
            summary_rows.append({
                "keyword": row["keyword"],
                "platform": "naver",
                "source": "searchad_monthly",
                "absolute_volume": row["total_search_volume"],
                "pc_volume": row["pc_search_volume"],
                "mobile_volume": row["mobile_search_volume"],
                "data_type": "monthly_absolute",
            })

    # 네이버 데이터랩 (치환 절대)
    if not naver_abs_df.empty:
        # 키워드별 최근 기간 평균
        latest = naver_abs_df.groupby("keyword").agg({
            "estimated_absolute_volume": "mean",
            "ratio": "mean",
        }).reset_index()
        for _, row in latest.iterrows():
            est = row["estimated_absolute_volume"]
            summary_rows.append({
                "keyword": row["keyword"],
                "platform": "naver",
                "source": "datalab_estimated",
                "absolute_volume": int(est) if pd.notna(est) else None,
                "pc_volume": None,
                "mobile_volume": None,
                "data_type": "estimated_from_ratio",
            })

    # (수정) 구글 트렌드 추정치는 구글 키워드 플래너 진짜 데이터가 있으므로 최종 요약본에서 제외합니다.

    # Google Keyword Planner (실제 절대 검색량)
    if not google_ad_df.empty:
        for _, row in google_ad_df.iterrows():
            summary_rows.append({
                "keyword": row["keyword"],
                "platform": "google",
                "source": "searchad_monthly",
                "absolute_volume": row.get("total_search_volume"),
                "pc_volume": None,
                "mobile_volume": None,
                "data_type": "monthly_absolute",
            })

    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        # CSV 사전 조인
        dict_df = pd.DataFrame(csv_records)
        summary_merged = summary_df.merge(
            dict_df[["term_id", "canonical_name", "search_keyword", "term_type",
                     "english_name", "term_code", "keyword_rank", "is_primary"]],
            left_on="keyword", right_on="search_keyword",
            how="left",
        )
        # keyword 컬럼은 실제 검색한 키워드 -> matched_keyword 로 보존
        summary_merged.rename(columns={"keyword": "matched_keyword"}, inplace=True)
        summary_merged.drop(columns=["search_keyword"], inplace=True, errors="ignore")
        summary_merged.rename(columns={"canonical_name": "keyword"}, inplace=True)

        # 컬럼 순서 정리
        cols = ["term_id", "keyword", "english_name", "term_type", "term_code",
                "matched_keyword", "keyword_rank", "is_primary",
                "platform", "data_type", "absolute_volume",
                "pc_volume", "mobile_volume", "source"]
        final_cols = [c for c in cols if c in summary_merged.columns]
        summary_merged = summary_merged[final_cols]

        path = PROCESSED_DIR / "final_summary_absolute.csv"
        summary_merged.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(str(path))
        logger.info(f"[PROCESSED] {path.name} ({len(summary_merged)}행)")

        # ── 5. term 단위 합산 집계 ──
        saved += aggregate_by_term(summary_merged, csv_records, google_ad_df)

    return saved


# ============================================================
# STEP 5: term 단위 합산 집계
# ============================================================

def aggregate_by_term(summary_df: pd.DataFrame, csv_records: list,
                      google_ad_df: pd.DataFrame = None) -> list:
    """
    다중 키워드를 term(canonical_name) 단위로 SUM 집계합니다.

    산출물:
      term_volume_long.csv   term x platform 롱포맷
      term_volume_wide.csv   term 한 줄 = naver/google/total (메인 산출물)
      term_monthly_trend.csv term x 연월 (구글 12개월 시계열, 시즌성 분석용)
    """
    saved = []
    df = summary_df[summary_df["source"] == "searchad_monthly"].copy()
    if df.empty:
        logger.warning("[AGG] 집계할 절대검색량 데이터 없음")
        return saved

    df["absolute_volume"] = pd.to_numeric(df["absolute_volume"], errors="coerce").fillna(0)

    dict_df = pd.DataFrame(csv_records)
    # term별 요청 키워드 수
    planned = (dict_df.groupby("canonical_name")["search_keyword"]
               .nunique().rename("keywords_requested").reset_index())

    # ── 롱포맷: term x platform ──
    long = (df.groupby(["term_id", "keyword", "english_name", "term_type", "term_code", "platform"])
              .agg(total_volume=("absolute_volume", "sum"),
                   keywords_matched=("matched_keyword", "nunique"),
                   pc_volume=("pc_volume", "sum"),
                   mobile_volume=("mobile_volume", "sum"))
              .reset_index())

    # term별 최다 검색 키워드
    top = (df.sort_values("absolute_volume", ascending=False)
             .groupby(["term_id", "platform"])
             .agg(top_keyword=("matched_keyword", "first"),
                  top_keyword_volume=("absolute_volume", "first"))
             .reset_index())
    long = long.merge(top, on=["term_id", "platform"], how="left")
    long = long.merge(planned, left_on="keyword", right_on="canonical_name", how="left")
    long.drop(columns=["canonical_name"], inplace=True, errors="ignore")
    long["coverage"] = (long["keywords_matched"] / long["keywords_requested"]).round(3)
    long = long.sort_values(["platform", "total_volume"], ascending=[True, False])

    p = PROCESSED_DIR / "term_volume_long.csv"
    long.to_csv(p, index=False, encoding="utf-8-sig")
    saved.append(str(p)); logger.info(f"[AGG] {p.name} ({len(long)}행)")

    # ── 와이드: term 한 줄 ──
    wide = long.pivot_table(index=["term_id", "keyword", "english_name", "term_type", "term_code"],
                            columns="platform", values="total_volume",
                            aggfunc="sum", fill_value=0).reset_index()
    wide.columns.name = None
    for c in ["naver", "google"]:
        if c not in wide.columns:
            wide[c] = 0
    wide.rename(columns={"naver": "naver_volume", "google": "google_volume"}, inplace=True)
    wide["total_volume"] = wide["naver_volume"] + wide["google_volume"]

    # 플랫폼 편향 지표 (1에 가까울수록 네이버 편중)
    wide["naver_share"] = (wide["naver_volume"] /
                           wide["total_volume"].replace(0, pd.NA)).round(3)
    wide = wide.merge(planned, left_on="keyword", right_on="canonical_name", how="left")
    wide.drop(columns=["canonical_name"], inplace=True, errors="ignore")
    wide = wide.sort_values("total_volume", ascending=False)
    wide["rank_overall"] = range(1, len(wide) + 1)
    wide["rank_in_type"] = wide.groupby("term_type")["total_volume"].rank(
        ascending=False, method="min").astype(int)

    p = PROCESSED_DIR / "term_volume_wide.csv"
    wide.to_csv(p, index=False, encoding="utf-8-sig")
    saved.append(str(p)); logger.info(f"[AGG] {p.name} ({len(wide)}행)")

    # ── 월별 시계열 (구글 keyword planner 12개월) ──
    if google_ad_df is not None and not google_ad_df.empty \
            and "monthly_search_volumes" in google_ad_df.columns:
        import ast
        MONTHS = {"JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
                  "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10,
                  "NOVEMBER": 11, "DECEMBER": 12}
        kw2term = dict(zip(dict_df["search_keyword"], dict_df["canonical_name"]))
        rows = []
        for _, r in google_ad_df.iterrows():
            term = kw2term.get(r["keyword"])
            if not term:
                continue
            try:
                series = r["monthly_search_volumes"]
                if isinstance(series, str):
                    series = ast.literal_eval(series)
            except Exception:
                continue
            for pt in series or []:
                m = MONTHS.get(str(pt.get("month", "")).upper())
                if not m:
                    continue
                rows.append({"keyword": term, "matched_keyword": r["keyword"],
                             "year_month": f"{pt.get('year')}-{m:02d}",
                             "volume": pt.get("monthly_searches", 0) or 0})
        if rows:
            mon = pd.DataFrame(rows)
            mon = (mon.groupby(["keyword", "year_month"])["volume"].sum().reset_index()
                      .sort_values(["keyword", "year_month"]))
            mon = mon.merge(dict_df[["canonical_name", "term_type"]].drop_duplicates(),
                            left_on="keyword", right_on="canonical_name", how="left")
            mon.drop(columns=["canonical_name"], inplace=True, errors="ignore")
            p = PROCESSED_DIR / "term_monthly_trend.csv"
            mon.to_csv(p, index=False, encoding="utf-8-sig")
            saved.append(str(p)); logger.info(f"[AGG] {p.name} ({len(mon)}행)")

    # ── 콘솔 요약 ──
    logger.info("\n" + "=" * 60)
    logger.info("  TERM 집계 요약")
    logger.info("=" * 60)
    logger.info(f"  term 수: {len(wide)} / 검색 키워드 수: {df['matched_keyword'].nunique()}")
    logger.info(f"  네이버 총합: {int(wide['naver_volume'].sum()):,}")
    logger.info(f"  구글 총합:   {int(wide['google_volume'].sum()):,}")
    logger.info("  -- TOP 15 (total) --")
    for _, r in wide.head(15).iterrows():
        logger.info(f"    {r['rank_overall']:>3}. [{r['term_type']:<8}] {r['keyword']:<12} "
                    f"total={int(r['total_volume']):>9,}  "
                    f"(N {int(r['naver_volume']):>8,} / G {int(r['google_volume']):>8,})")
    logger.info("  -- term_type 별 --")
    by_type = wide.groupby("term_type").agg(terms=("keyword", "count"),
                                            total=("total_volume", "sum")).sort_values("total", ascending=False)
    for t, r in by_type.iterrows():
        logger.info(f"    {t:<10} terms={int(r['terms']):>4}  total={int(r['total']):>12,}")
    zero = wide[wide["total_volume"] == 0]
    logger.info(f"  검색량 0인 term: {len(zero)}개")
    if len(zero):
        logger.info(f"    {', '.join(zero['keyword'].head(20).tolist())}")
    logger.info("=" * 60)

    return saved


# ============================================================
# 메인 파이프라인
# ============================================================

def run_pipeline(
    csv_records: list,
    source_filter: str = "all",
    dry_run: bool = False,
):
    """전체 파이프라인 실행"""
    start_time = datetime.now()
    keywords = get_keyword_names(csv_records)

    logger.info("=" * 60)
    logger.info(f"Pipeline Start")
    logger.info(f"  Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Keywords: {len(keywords)}")
    logger.info(f"  Source: {source_filter}")
    logger.info(f"  Raw output: {RAW_DIR}")
    logger.info(f"  Processed output: {PROCESSED_DIR}")
    logger.info("=" * 60)

    if dry_run:
        logger.info("[DRY-RUN] API 호출 없이 구조 검증만 수행합니다.")
        logger.info(f"  Keywords ({len(keywords)}): {keywords[:10]}...")
        check_all_configs()
        return

    # ── STEP 1: 수집 ──
    logger.info("\n>>> STEP 1: Collect (API 수집)")

    naver_ad_df = pd.DataFrame()
    naver_datalab_df = pd.DataFrame()
    google_trends_df = pd.DataFrame()
    google_ad_df = pd.DataFrame()

    if source_filter in ["all", "naver", "naver_ad"]:
        naver_ad_df = collect_naver_searchad(keywords)

    # (수정) 불필요한 401 에러를 피하기 위해 네이버 데이터랩 수집 스킵
    # if source_filter in ["all", "naver", "naver_datalab"]:
    #     naver_datalab_df = collect_naver_datalab(keywords)

    if source_filter in ["all", "google"]:
        google_trends_df = collect_google_trends(
            keywords,
            dictionary_terms=[r["canonical_name"] for r in csv_records],
        )
        google_ad_df = collect_google_keyword(keywords)

    # ── 원본 파일 저장 ──
    logger.info("\n>>> STEP 2: Save Raw Data")
    raw_files = save_raw_data(
        naver_ad_df, naver_datalab_df, google_trends_df, google_ad_df
    )
    # ── STEP 3: 전처리 (절대검색량 치환) ──
    logger.info("\n>>> STEP 3: Normalize (ratio -> absolute volume)")
    naver_abs_df, google_abs_df = normalize_to_absolute(
        naver_ad_df, naver_datalab_df, google_trends_df, csv_records
    )

    # ── 4. 가공 파일 저장 ──
    logger.info("\n>>> STEP 4: Save Processed Data")
    processed_files = save_processed_data(
        naver_ad_df, naver_abs_df, google_abs_df, google_ad_df, csv_records
    )

    # ── 완료 ──
    duration = datetime.now() - start_time
    logger.info("\n" + "=" * 60)
    logger.info(f"Pipeline Complete ({duration})")
    logger.info(f"  Raw files: {len(raw_files)}")
    for f in raw_files:
        logger.info(f"    - {Path(f).name}")
    logger.info(f"  Processed files: {len(processed_files)}")
    for f in processed_files:
        logger.info(f"    - {Path(f).name}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Fashion Keyword Search Volume Pipeline"
    )
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 구조 검증")
    parser.add_argument("--source", choices=["all", "naver", "google"], default="all")
    parser.add_argument("--csv", type=str, default=None, help="CSV 사전 파일 경로")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    setup_logging(verbose=args.verbose)
    check_all_configs()

    # CSV에서 키워드 로드
    try:
        csv_records = load_keywords_from_csv(args.csv)
        if not csv_records:
            logger.error("[ERR] CSV에서 키워드를 찾을 수 없습니다.")
            sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"[ERR] {e}")
        sys.exit(1)

    run_pipeline(csv_records, source_filter=args.source, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
