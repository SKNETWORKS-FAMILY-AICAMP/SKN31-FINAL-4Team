from __future__ import annotations

from .client import KreamClient
from .constants import PRODUCT_HEADER_API_URL, PRODUCT_SCREEN_API_URL
from .exceptions import KreamCollectError


class KreamProductCollector:
    """KREAM 상품 상세 화면을 구성하는 공개 웹 API 응답 수집기."""

    def __init__(self, client: KreamClient):
        self.client = client

    def collect_screen(self, product_id: int) -> dict:
        if not isinstance(product_id, int) or product_id <= 0:
            raise KreamCollectError(f"잘못된 KREAM product_id: {product_id!r}")

        return self.client.get_json(
            PRODUCT_SCREEN_API_URL.format(product_id=product_id),
            product_id=product_id,
        )

    def collect_header(self, product_id: int) -> dict:
        if not isinstance(product_id, int) or product_id <= 0:
            raise KreamCollectError(f"잘못된 KREAM product_id: {product_id!r}")

        return self.client.get_json(
            PRODUCT_HEADER_API_URL.format(product_id=product_id),
            product_id=product_id,
        )
