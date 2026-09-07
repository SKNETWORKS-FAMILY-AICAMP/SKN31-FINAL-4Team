KREAM_BASE_URL = "https://kream.co.kr"
KREAM_API_BASE_URL = "https://api.kream.co.kr"

PRODUCT_PAGE_URL = (
    KREAM_BASE_URL
    + "/products/{product_id}"
)

PRODUCT_SCREEN_API_URL = (
    KREAM_API_BASE_URL
    + "/api/screens/products/{product_id}"
)

PRODUCT_HEADER_API_URL = (
    KREAM_API_BASE_URL
    + "/api/p/products/header/{product_id}"
)

REQUEST_TIMEOUT = 20


KREAM_API_VERSION = "64"
KREAM_WEB_BUILD_VERSION = "26.12.1"

KREAM_WEB_REQUEST_SECRET = (
    "kream-djscjsghdkd"
)


DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": (
        "ko-KR,ko;q=0.9,"
        "en-US;q=0.8,en;q=0.7"
    ),
    "Origin": KREAM_BASE_URL,
}