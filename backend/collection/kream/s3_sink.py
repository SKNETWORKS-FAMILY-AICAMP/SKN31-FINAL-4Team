from __future__ import annotations

from datetime import datetime

from collection.common.s3 import (
    S3Storage,
)


class KreamS3Sink:
    def __init__(self, *, bucket: str, region_name: str | None = None):
        self.storage = S3Storage(
            bucket=bucket,
            region_name=region_name,
        )

    def save_product(self, collected: dict) -> dict:
        product_id = str(collected["source_product_id"])

        collected_at = collected.get("collected_at")
        dt = (
            datetime.fromisoformat(collected_at)
            if collected_at
            else datetime.now().astimezone()
        )

        key = (
            "raw/kream/product/"
            f"{dt:%Y/%m/%d}/"
            f"{product_id}/"
            "product.json"
        )

        result = self.storage.upload_json(
            key=key,
            data=collected,
        )

        return {
            "bucket": self.storage.bucket,
            "key": key,
            "uri": result.uri,
            "verified": self.storage.exists(key),
        }
