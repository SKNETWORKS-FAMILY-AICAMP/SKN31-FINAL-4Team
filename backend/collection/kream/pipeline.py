from __future__ import annotations

from collection.common.pipeline import (
    BasePlatformPipeline,
)
from collection.kream.collector import (
    KreamCollector,
)


class KreamPipeline(
    BasePlatformPipeline
):
    SOURCE = "KREAM"

    def collect(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> dict:

        if not target_url:
            raise ValueError(
                "KREAM target_url이 없습니다."
            )

        with KreamCollector() as collector:

            data = (
                collector.collect_product(
                    target_url
                )
            )

        return {
            "entity_type": "PRODUCT",

            "source_entity_id": (
                data[
                    "source_product_id"
                ]
            ),

            "source_url": (
                data[
                    "source_url"
                ]
            ),

            "collected_at": (
                data[
                    "collected_at"
                ]
            ),

            "http_status": 200,

            "content_type": (
                "application/json"
            ),

            # 우리가 아까 만든
            # 깔끔한 KREAM 상품 JSON
            "payload": data,

            "discovered_count": 1,
            "success_count": 1,
            "failure_count": 0,
        }