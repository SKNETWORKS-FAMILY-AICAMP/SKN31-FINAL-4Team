from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from .client import KreamClient
from .constants import PRODUCT_PAGE_URL
from .exceptions import KreamCollectError
from .parser import KreamParser
from .product import KreamProductCollector


class KreamCollector:
    PRODUCT_PATTERN = re.compile(r"/products/(\d+)")

    def __init__(self, *, timeout: int | float | None = None, session=None):
        self.client = KreamClient(timeout=timeout, session=session)
        self.products = KreamProductCollector(self.client)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def collect_product(self, product: str | int) -> dict:
        product_id = self.extract_product_id(product)

        screen = self.products.collect_screen(product_id)
        header = self.products.collect_header(product_id)

        parsed = KreamParser.parse_product(
            product_id=product_id,
            screen=screen,
            header=header,
        )

        return {
            "schema_version": "1.1",
            "source": "KREAM",
            "entity_type": "PRODUCT",
            "source_product_id": str(product_id),
            "source_url": PRODUCT_PAGE_URL.format(product_id=product_id),
            "collected_at": datetime.now().astimezone().isoformat(),
            **parsed,
        }

    @classmethod
    def extract_product_id(cls, value: str | int) -> int:
        if isinstance(value, int):
            return value

        text = str(value).strip()

        if text.isdigit():
            return int(text)

        match = cls.PRODUCT_PATTERN.search(urlparse(text).path)

        if not match:
            raise KreamCollectError(
                f"KREAM 상품 ID를 찾을 수 없습니다: {value}"
            )

        return int(match.group(1))
