from __future__ import annotations


# ============================================================
# BASE
# ============================================================

ZIGZAG_BASE_URL = "https://zigzag.kr"

PRODUCT_PAGE_URL = (
    ZIGZAG_BASE_URL
    + "/catalog/products/{product_id}"
)

IMAGE_BASE_URL = ZIGZAG_BASE_URL


# ============================================================
# RANKING / CATEGORY
# ============================================================

DEFAULT_RANKING_URL = (
    ZIGZAG_BASE_URL
    + "/pages/srp-clp-category?category_id=474"
)

PRODUCT_CARD_SELECTOR = "div.product-card"

PRODUCT_LINK_SELECTOR = (
    "a.product-card-link"
)

PRODUCT_LINK_PATTERN = (
    r"/catalog/products/(\d+)"
)


# ============================================================
# REQUEST
# ============================================================

REQUEST_TIMEOUT = 20

DEFAULT_HEADERS = {
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
    "Accept-Language": (
        "ko-KR,ko;q=0.9,"
        "en-US;q=0.8,en;q=0.7"
    ),
}


# ============================================================
# RENDER
# ============================================================

DEFAULT_RENDER_WAIT_MS = 3000

DEFAULT_SCROLL_WAIT_MS = 1000

DEFAULT_SCROLL_COUNT = 24

DEFAULT_RANKING_LIMIT = 100


# ============================================================
# META
# ============================================================

PARSER_VERSION = "zigzag-pdp-v2"

SCHEMA_VERSION = "1.0"

SOURCE_CODE = "ZIGZAG"