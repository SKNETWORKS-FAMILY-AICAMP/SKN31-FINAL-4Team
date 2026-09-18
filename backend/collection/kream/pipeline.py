from __future__ import annotations

from collection.common.pipeline import BasePlatformPipeline

from collection.kream.client import KreamClient
from collection.kream.collector import KreamCollector
from collection.kream.discovery import KreamDiscoveryCollector
from datetime import datetime

class KreamPipeline(BasePlatformPipeline):
    SOURCE = "KREAM"

    MODE_PRODUCT = "PRODUCT"
    MODE_DISCOVERY = "DISCOVERY"

    def collect(
        self,
        *,
        target_type: str | None = None,
        target_url: str | None,
        params: dict,
    ) -> dict:

        params = params or {}

        mode = (
            params.get("mode")
            or self.MODE_PRODUCT
        ).upper()

        if mode == self.MODE_PRODUCT:
            return self._collect_product(
                target_url=target_url,
                params=params,
            )

        if mode == self.MODE_DISCOVERY:
            return self._collect_discovery(
                target_url=target_url,
                params=params,
            )

        raise ValueError(
            f"지원하지 않는 KREAM mode: {mode}"
        )

    def _collect_product(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> dict:

        if not target_url:
            raise ValueError(
                "KREAM PRODUCT target_url이 없습니다."
            )

        with KreamCollector() as collector:
            data = collector.collect_product(
                target_url
            )

        return {
            "entity_type": "PRODUCT",
            "source_entity_id": data["source_product_id"],
            "source_url": data["source_url"],
            "collected_at": data["collected_at"],
            "http_status": 200,
            "content_type": "application/json",
            "payload": data,
            "discovered_count": 1,
            "success_count": 1,
            "failure_count": 0,
        }

    def _collect_discovery(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> dict:

        tab_id = int(params["tab_id"])
        limit = int(params.get("limit", 100))
        sort = params.get("sort") or "popular_score"
        include_detail = bool(
            params.get("include_detail", False)
        )

        with KreamClient() as client:
            discovery = KreamDiscoveryCollector(client)

            products = discovery.collect_products(
                tab_id=tab_id,
                limit=limit,
                sort=sort,
            )

        details = []
        failures = []

        if include_detail:
            with KreamCollector() as collector:
                for product in products:
                    product_id = product["product_id"]

                    try:
                        detail = collector.collect_product(
                            product_id
                        )

                        details.append(
                            {
                                "feed_rank": product["feed_rank"],
                                "feed": product,
                                "detail": detail,
                            }
                        )

                    except Exception as exc:
                        failures.append(
                            {
                                "product_id": product_id,
                                "error_type": type(exc).__name__,
                                "error_message": str(exc),
                            }
                        )

        payload = {
            "schema_version": "1.0",
            "source": "KREAM",
            "entity_type": "DISCOVERY",
            "discovery": {
                "tab_id": tab_id,
                "sort": sort,
                "limit": limit,
                "include_detail": include_detail,
            },
            "products": products,
            "details": details,
            "failures": failures,
        }

        return {
            "entity_type": "DISCOVERY",
            "source_entity_id": f"shop:{tab_id}:{sort}",
            "source_url": (
                target_url
                or f"https://kream.co.kr/categories/{tab_id}"
            ),
            "collected_at": datetime.now().astimezone().isoformat(),
            "http_status": 200,
            "content_type": "application/json",
            "payload": payload,
            "discovered_count": len(products),
            "success_count": (
                len(details)
                if include_detail
                else len(products)
            ),
            "failure_count": len(failures),
        }
