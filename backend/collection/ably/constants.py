ABLY_API_BASE_URL = "https://api.a-bly.com"
ABLY_MOBILE_BASE_URL = "https://mobile.a-bly.com"

RANKING_PAGE_URL = f"{ABLY_MOBILE_BASE_URL}/ranking"
ANONYMOUS_TOKEN_API_URL = f"{ABLY_API_BASE_URL}/api/v2/anonymous/token/"
RANKING_GOODS_API_URL = f"{ABLY_API_BASE_URL}/api/v2/goods/"
RANKING_FILTERS_API_URL = (
    f"{ABLY_API_BASE_URL}/api/v2/goods/ranking-filters/"
)
PRODUCT_URL_TEMPLATE = f"{ABLY_MOBILE_BASE_URL}/goods/{{goods_sno}}"

REQUEST_TIMEOUT = 20
DEFAULT_MAX_RANK = 100
DEFAULT_MAX_REQUESTS = 50

ANONYMOUS_TOKEN_ENV = "ABLY_ANONYMOUS_TOKEN"
DEVICE_ID_ENV = "ABLY_DEVICE_ID"

# 일반 JSON 요청 헤더만 기본값으로 둔다. 실제 호출 검증 결과 상품 API에는
# x-anonymous-token과 x-device-id가 필요하며 client가 실행 시점에만 추가한다.
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
}
