from __future__ import annotations

from .client import KreamClient
from .constants import PRODUCT_HEADER_API_URL, PRODUCT_SCREEN_API_URL


class KreamProductCollector:
    def __init__(self, client: KreamClient):
        self.client = client

    def collect_screen(self, product_id: int) -> dict:
        return self.client.get_json(
            PRODUCT_SCREEN_API_URL.format(product_id=product_id),
            product_id=product_id,
        )

    def collect_header(self, product_id: int) -> dict:
        return self.client.get_json(
            PRODUCT_HEADER_API_URL.format(product_id=product_id),
            product_id=product_id,
        )
