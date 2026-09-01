MUSINSA_BASE_URL = "https://www.musinsa.com"
PRODUCT_BASE_URL = f"{MUSINSA_BASE_URL}/products/{{goods_no}}"
IMAGE_BASE_URL = "https://image.msscdn.net"
GOODS_DETAIL_API_BASE = "https://goods-detail.musinsa.com/api2"
REVIEW_API_BASE = "https://goods.musinsa.com/api2/review"
LIKE_API_URL = "https://like.musinsa.com/like/api/v2/liketypes/goods/counts"

TAG_API_URL = GOODS_DETAIL_API_BASE + "/goods/{goods_no}/tags"
STAT_API_URL = GOODS_DETAIL_API_BASE + "/goods/{goods_no}/stat"
OPTIONS_API_URL = GOODS_DETAIL_API_BASE + "/goods/{goods_no}/options"
REVIEW_SUMMARY_API_URL = REVIEW_API_BASE + "/v1/goods/{goods_no}/reviews/summary"
REVIEW_LIST_API_URL = REVIEW_API_BASE + "/v1/view/list"

# 아래 3개는 기존 프로젝트에서 검증된 값을 유지해서 사용하세요.
# 새 구조에서는 ranking.py만 이 상수들을 참조합니다.
RANKING_API_URL = "https://client.musinsa.com/" "api/home/web/v5/pans/ranking"
ARCHIVE_GOODS_API_URL = "https://api.musinsa.com/" "api2/dp/v1/ranking-archive/goods"
ARCHIVE_CATEGORIES_API_URL = (
    "https://api.musinsa.com/" "api2/dp/v1/ranking-archive/categories"
)


REQUEST_TIMEOUT = 20
LIKE_BATCH_SIZE = 100
DEFAULT_REVIEW_PAGE_SIZE = 50
PARSER_VERSION = "musinsa-pdp-v2"
SCHEMA_VERSION = "1.0"
SOURCE_CODE = "MUSINSA"

MUSINSA_HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


MUSINSA_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}