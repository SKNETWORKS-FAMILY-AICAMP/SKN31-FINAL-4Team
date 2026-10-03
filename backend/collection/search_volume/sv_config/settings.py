# -*- coding: utf-8 -*-
"""
설정 관리 모듈
.env 파일에서 환경변수를 로드하고 각 API별 설정을 관리합니다.
"""

import os
import csv
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 디렉토리
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = Path(__file__).parent

# .env 탐색 — FEEDiT 레포 루트의 .env 가 단일 원본이다.
#  ★ 2026-09-21 — 이 패키지가 feedit/backend/collection/search_volume 으로 들어오면서
#    키는 레포 루트 .env 한 곳에서만 관리한다(Django 도 거기만 읽는다).
#    옛 위치(config/.env)도 뒤에 남겨 둬 이 폴더만 떼어내 단독 실행하는 것도 된다.
#    override=False 라 먼저 읽힌 쪽이 이긴다 — 루트가 우선.
FEEDIT_ROOT = PROJECT_ROOT.parent.parent.parent      # …/backend/collection/search_volume → …/feedit
for env_candidate in (FEEDIT_ROOT / ".env", PROJECT_ROOT / ".env", CONFIG_DIR / ".env"):
    if env_candidate.exists():
        load_dotenv(env_candidate, override=False)


def _env(*names: str, default: str = "") -> str:
    """여러 이름 중 먼저 값이 있는 것을 쓴다.

    대문자(NAVER_AD_API_KEY)가 FEEDiT 표준이고, 소문자(naver_lisence_ad)는
    팀원이 처음 만든 이름이다. 둘 다 받아 둬야 옮기는 도중에 안 깨진다.
    """
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return default


# ===== 네이버 검색광고 API 설정 =====
class NaverSearchAdConfig:
    """네이버 검색광고 (키워드 도구) API 설정"""
    API_KEY = _env("NAVER_AD_API_KEY", "naver_lisence_ad")
    SECRET_KEY = _env("NAVER_AD_SECRET_KEY", "naver_secret_ad")
    CUSTOMER_ID = _env("NAVER_AD_CUSTOMER_ID", "naver_customer_id")
    BASE_URL = "https://api.searchad.naver.com"

    @classmethod
    def is_configured(cls) -> bool:
        return all([cls.API_KEY, cls.SECRET_KEY])


# ===== 네이버 데이터랩 API 설정 =====
class NaverDatalabConfig:
    """네이버 데이터랩 통합 검색어 트렌드 API 설정"""
    CLIENT_ID = _env("NAVER_DATALAB_CLIENT_ID", "naver_lisence_datalap")
    CLIENT_SECRET = _env("NAVER_DATALAB_CLIENT_SECRET", "naver_secret_datalap")
    BASE_URL = "https://openapi.naver.com/v1/datalab/search"
    DAILY_LIMIT = 1000

    @classmethod
    def is_configured(cls) -> bool:
        return all([cls.CLIENT_ID, cls.CLIENT_SECRET])


# ===== Google Trends 설정 (API 키 불필요) =====
class GoogleTrendsConfig:
    """Google Trends (pytrends) 설정"""
    GEO = "KR"
    LANGUAGE = "ko"
    TIMEZONE = 540
    REQUEST_DELAY = int(_env("FEEDIT_TRENDS_DELAY", default="5") or 5)
    # G5 지역별 · G6 실시간 급상승 스위치 — 429 가 나면 여기부터 끈다.
    WITH_REGION = _env("FEEDIT_TRENDS_REGION", default="1") != "0"
    WITH_TRENDING = _env("FEEDIT_TRENDS_TRENDING", default="1") != "0"
    REGION_RESOLUTION = "REGION"      # KR → 실제로는 16개가 온다 (세종 없음)
    # 지역은 키워드 1개짜리 페이로드로 따로 받아야 해서 비싸다 → 상위 N개만.
    REGION_LIMIT = int(_env("FEEDIT_TRENDS_REGION_LIMIT", default="50") or 50)

    @classmethod
    def is_configured(cls) -> bool:
        return True


# ===== Google Keyword Planner API 설정 =====
class GoogleKeywordConfig:
    """Google Ads Keyword Planner API 설정"""
    # ★ GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 는 구글 "로그인"용이다(.env 194~195행).
    #   여기서 그 이름을 읽으면 로그인 자격증명으로 광고 API 를 부르게 된다 — 반드시 GOOGLE_ADS_ 접두어.
    DEVELOPER_TOKEN = _env("GOOGLE_ADS_DEVELOPER_TOKEN", "google_developer_token")
    CLIENT_ID = _env("GOOGLE_ADS_CLIENT_ID", "google_client_id")
    CLIENT_SECRET = _env("GOOGLE_ADS_CLIENT_SECRET", "google_client_secret")
    REFRESH_TOKEN = _env("GOOGLE_ADS_REFRESH_TOKEN", "google_refresh_token")
    CUSTOMER_ID = _env("GOOGLE_ADS_CUSTOMER_ID", "google_customer_id")
    LOGIN_CUSTOMER_ID = _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "google_login_customer_id")

    @classmethod
    def is_configured(cls) -> bool:
        return all([cls.DEVELOPER_TOKEN, cls.CLIENT_ID, cls.CLIENT_SECRET, cls.REFRESH_TOKEN, cls.CUSTOMER_ID])


# ===== AWS 설정 =====
class S3Config:
    ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
    SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    REGION = os.getenv("AWS_REGION", "ap-northeast-2")
    BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")

    @classmethod
    def is_configured(cls) -> bool:
        return all([cls.ACCESS_KEY_ID, cls.SECRET_ACCESS_KEY, cls.BUCKET_NAME])


class RDSConfig:
    # FEEDiT 는 SSM 굴을 통해 RDS 로 나간다 — 루트 .env 의 DB_* 가 그 굴의 입구다.
    HOST = _env("DB_HOST", "RDS_HOST")
    PORT = int(_env("DB_PORT", "RDS_PORT", default="5432") or 5432)
    DBNAME = _env("DB_NAME", "RDS_DBNAME")
    USER = _env("DB_USER", "RDS_USER")
    PASSWORD = _env("DB_PASSWORD", "RDS_PASSWORD")

    @classmethod
    def get_connection_string(cls) -> str:
        return f"postgresql://{cls.USER}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.DBNAME}"

    @classmethod
    def is_configured(cls) -> bool:
        return all([cls.HOST, cls.DBNAME, cls.USER, cls.PASSWORD])


def load_keywords_from_csv(filepath: str = None) -> list:
    """
    CSV 사전 파일에서 키워드(canonical_name)를 읽어옵니다.
    keywords/ 폴더에서 가장 최신 CSV를 자동 탐색합니다.

    Returns:
        [{"id": 157, "term_type": "ITEM", "canonical_name": "코트",
          "english_name": "Coat", "normalized_name": "코트"}, ...]
    """
    keywords_dir = PROJECT_ROOT / "keywords"

    if filepath:
        csv_path = Path(filepath)
    else:
        # keywords/ 폴더에서 .csv 파일 자동 탐색 (최신 파일)
        csv_files = sorted(keywords_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not csv_files:
            raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {keywords_dir}")
        csv_path = csv_files[0]

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {csv_path}")

    records = []
    seen_keywords = set()
    term_count = 0

    # BOM 대응: utf-8-sig
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status", "").strip() != "ACTIVE":
                continue

            canonical = row.get("canonical_name", "").strip()
            raw_kw = (row.get("search_keyword") or canonical).strip()

            # 다중 키워드 지원: "골프웨어|골프룩|골프복" -> 3개 레코드로 전개
            keywords = [k.strip() for k in raw_kw.split("|") if k.strip()]
            if not keywords:
                keywords = [canonical]

            term_count += 1
            for rank, kw in enumerate(keywords, start=1):
                if kw in seen_keywords:      # 키워드 중복 호출 방지
                    continue
                seen_keywords.add(kw)
                records.append({
                    "id": int(row.get("id", 0) or 0),
                    "term_id": int(row.get("id", 0) or 0),
                    "term_type": row.get("term_type", "").strip(),
                    "canonical_name": canonical,
                    "english_name": row.get("english_name", "").strip(),
                    "normalized_name": row.get("normalized_name", "").strip(),
                    "term_code": row.get("term_code", "").strip(),
                    "search_keyword": kw,
                    "keyword_rank": rank,
                    "is_primary": rank == 1,
                })

    print(f"[INFO] CSV 로드 완료: {csv_path.name} "
          f"(term {term_count}개 -> 검색 키워드 {len(records)}개)")
    return records


def get_keyword_names(records: list) -> list:
    """CSV 레코드에서 검색용 키워드명(search_keyword) 리스트를 추출합니다."""
    return [r.get("search_keyword", r["canonical_name"]) for r in records]


def check_all_configs():
    """모든 설정의 상태를 확인하고 출력합니다."""
    configs = {
        "Naver SearchAd API": NaverSearchAdConfig.is_configured(),
        "Naver Datalab API": NaverDatalabConfig.is_configured(),
        "Google Trends": GoogleTrendsConfig.is_configured(),
        "Google Keyword Planner": GoogleKeywordConfig.is_configured(),
        "AWS S3": S3Config.is_configured(),
        "AWS RDS": RDSConfig.is_configured(),
    }

    print("\n" + "=" * 50)
    print("  Setting Status Check")
    print("=" * 50)
    for name, status in configs.items():
        icon = "[OK]" if status else "[--]"
        print(f"  {icon} {name}")
    print("=" * 50 + "\n")

    return configs
