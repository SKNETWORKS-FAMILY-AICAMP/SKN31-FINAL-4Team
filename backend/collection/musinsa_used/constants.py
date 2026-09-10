MUSINSA_BASE_URL = "https://www.musinsa.com"
PRODUCT_BASE_URL = f"{MUSINSA_BASE_URL}/products/{{goods_no}}"
IMAGE_BASE_URL = "https://image.msscdn.net"

# Endpoints verified in the supplied MUSINSA USED HAR analysis.
RANKING_API_URL = "https://client.musinsa.com/api/home/web/v5/pans/ranking"
USED_SALE_INFORMATION_API_URL = (
    "https://goods-detail.musinsa.com/api2/used/goods/{goods_no}/sale-information"
)
USED_RELATED_GOODS_API_URL = (
    "https://goods-detail.musinsa.com/api2/used/goods/{goods_no}/related-goods"
)
# Adaptive retry defaults for live MUSINSA USED transport.  Normal 2xx
# responses incur no delay; these values apply only after retryable failures.
MUSINSA_USED_MAX_RETRIES = 3
MUSINSA_USED_RETRY_INITIAL_DELAY_SEC = 1.0
MUSINSA_USED_RETRY_MULTIPLIER = 2.0
MUSINSA_USED_RETRY_MAX_DELAY_SEC = 30.0

# Live collection throughput limits. Retry timing remains separate above.
MUSINSA_USED_PRODUCT_WORKERS = 3
MUSINSA_USED_MAX_INFLIGHT_REQUESTS = 6
MUSINSA_USED_TARGET_COOLDOWN_SECONDS = 90.0

PARSER_VERSION = "musinsa-used-pdp-v1"
SOURCE_CODE = "MUSINSA_USED"
DEFAULT_RANKING_LIMIT = 300
