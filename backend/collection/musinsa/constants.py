# 무신사 고정값

MUSINSA_BASE_URL = "https://www.musinsa.com"
PRODUCT_BASE_URL = "https://www.musinsa.com/products/{goods_no}"
IMAGE_BASE_URL = "https://image.msscdn.net"

PARSER_VERSION = "musinsa-product-v0.3"
REQUEST_TIMEOUT = 20
LIKE_BATCH_SIZE = 30

TAG_API_URL = "https://goods-detail.musinsa.com/" "api2/goods/{goods_no}/tags"

STAT_API_URL = "https://goods-detail.musinsa.com/" "api2/goods/{goods_no}/stat"

LIKE_API_URL = "https://like.musinsa.com/" "like/api/v2/liketypes/goods/counts"

RANKING_API_URL = "https://client.musinsa.com/" "api/home/web/v5/pans/ranking"

ARCHIVE_CATEGORIES_API_URL = (
    "https://api.musinsa.com/" "api2/dp/v1/ranking-archive/categories"
)

ARCHIVE_GOODS_API_URL = "https://api.musinsa.com/" "api2/dp/v1/ranking-archive/goods"
# ============================================================
# GENDER
# ============================================================

MUSINSA_GENDERS = {
    "M": "남성",
    "F": "여성",
    "A": "전체",
}


# ============================================================
# CATEGORY
# ============================================================

MUSINSA_CATEGORIES = {
    "001": "상의",
    "002": "아우터",
    "003": "바지",
    "100": "원피스/스커트",
}


# ============================================================
# SUB CATEGORY - 001 상의
# ============================================================

MUSINSA_SUBCATEGORIES_001 = {
    "001001": "반소매 티셔츠",
    "001002": "셔츠/블라우스",
    "001003": "피케/카라 티셔츠",
    "001004": "후드 티셔츠",
    "001005": "맨투맨/스웨트",
    "001006": "니트/스웨터",
    "001008": "기타 상의",
    "001010": "긴소매 티셔츠",
    "001011": "민소매 티셔츠",
}


# ============================================================
# SUB CATEGORY - 002 아우터
# ============================================================

MUSINSA_SUBCATEGORIES_002 = {
    "002001": "블루종/MA-1",
    "002002": "레더/라이더스 재킷",
    "002018": "트레이닝 재킷",
    "002020": "카디건",
    "002022": "후드 집업",
    # TODO:
    # 아래 항목은 실제 6자리 코드 확인 후 추가
    #
    # 무스탕/퍼
    # 트러커 재킷
    # 슈트/블레이저 재킷
    # 아노락 재킷
    # 플리스/뽀글이
    # 스타디움 재킷
    # 환절기 코트
    # 겨울 싱글 코트
    # 겨울 더블 코트
    # 겨울 기타 코트
    # 롱패딩/롱헤비 아우터
    # 숏패딩/숏헤비 아우터
    # 패딩 베스트
    # 베스트
    # 사파리/헌팅 재킷
    # 나일론/코치 재킷
    # 기타 아우터
}


# ============================================================
# SUB CATEGORY - 003 바지
# ============================================================

MUSINSA_SUBCATEGORIES_003 = {
    "003002": "데님 팬츠",
    "003004": "트레이닝/조거 팬츠",
    "003005": "레깅스",
    "003006": "기타 바지",
    "003007": "코튼 팬츠",
    "003008": "슈트 팬츠/슬랙스",
    "003009": "숏 팬츠",
    "003010": "점프 슈트/오버올",
}


# ============================================================
# SUB CATEGORY - 100 원피스/스커트
# ============================================================

MUSINSA_SUBCATEGORIES_100 = {
    "100001": "미니원피스",
    "100002": "미디원피스",
    "100003": "맥시원피스",
    "100004": "미니스커트",
    "100005": "미디스커트",
    "100006": "롱스커트",
}


# ============================================================
# CATEGORY MAPPING
# ============================================================

MUSINSA_SUBCATEGORIES = {
    "001": MUSINSA_SUBCATEGORIES_001,
    "002": MUSINSA_SUBCATEGORIES_002,
    "003": MUSINSA_SUBCATEGORIES_003,
    "100": MUSINSA_SUBCATEGORIES_100,
}

