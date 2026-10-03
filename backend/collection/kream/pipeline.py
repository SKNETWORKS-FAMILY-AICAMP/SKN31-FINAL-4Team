from __future__ import annotations

from datetime import datetime
from typing import Any

from collection.common.pipeline import BasePlatformPipeline
from collection.common.schemas import CollectionResult

from collection.kream.client import KreamClient
from collection.kream.collector import KreamCollector
from collection.kream.discovery import KreamDiscoveryCollector


class KreamPipeline(BasePlatformPipeline):
    SOURCE_CODE = "KREAM"
    SOURCE = "KREAM"

    MODE_PRODUCT = "PRODUCT"
    MODE_DISCOVERY = "DISCOVERY"

    def collect(
        self,
        *,
        target_type: str | None = None,
        target_url: str | None,
        params: dict,
    ) -> CollectionResult:

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
    ) -> CollectionResult:

        if not target_url:
            raise ValueError(
                "KREAM PRODUCT target_url이 없습니다."
            )

        with KreamCollector() as collector:
            data = collector.collect_product(
                target_url
            )

        collected_at = self._as_datetime(
            data["collected_at"]
        )

        return CollectionResult(
            source_code=self.SOURCE_CODE,
            entity_type="PRODUCT",
            source_entity_id=str(
                data["source_product_id"]
            ),
            source_url=data.get("source_url"),
            collected_at=collected_at,
            http_status=200,
            payload=data,
            discovered_count=1,
            success_count=1,
            failure_count=0,
            metadata={
                "mode": self.MODE_PRODUCT,
            },
        )

    def _collect_discovery(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> CollectionResult:

        tab_id = int(params["tab_id"])

        category_id = params.get(
            "category_id"
        )

        if category_id is None:
            category_id = "all"

        limit = int(
            params.get(
                "limit",
                100,
            )
        )

        detail_limit = int(
            params.get(
                "detail_limit",
                limit,
            )
        )

        sort = (
            params.get("sort")
            or "popular_score"
        )

        include_detail = bool(
            params.get(
                "include_detail",
                False,
            )
        )

        collected_at = (
            datetime.now().astimezone()
        )

        with KreamClient() as client:
            discovery = KreamDiscoveryCollector(
                client
            )

            products = discovery.collect_products(
                tab_id=tab_id,
                category_id=category_id,
                limit=limit,
                sort=sort,
            )

        details: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        if include_detail:
            with KreamCollector() as collector:
                for product in products[:detail_limit]:

                    product_id = product[
                        "product_id"
                    ]

                    try:
                        detail = (
                            collector.collect_product(
                                product_id
                            )
                        )

                        details.append(
                            {
                                "feed_rank": product[
                                    "feed_rank"
                                ],
                                "feed": product,
                                "detail": detail,
                            }
                        )

                    except Exception as exc:
                        failures.append(
                            {
                                "product_id": product_id,
                                "error_type": (
                                    type(exc).__name__
                                ),
                                "error_message": str(exc),
                            }
                        )

        payload = {
            "schema_version": "1.0",
            "source": "KREAM",
            "entity_type": "DISCOVERY",
            "collected_at": (
                collected_at.isoformat()
            ),
            "discovery": {
                "tab_id": tab_id,
                "category_id": category_id,
                "sort": sort,
                "limit": limit,
                "include_detail": include_detail,
            },
            "products": products,
            "details": details,
            "failures": failures,
        }

        if include_detail:
            success_count = len(details)
        else:
            success_count = len(products)

        return CollectionResult(
            source_code=self.SOURCE_CODE,
            entity_type="DISCOVERY",
            source_entity_id=(
                f"shop:{tab_id}:"
                f"{category_id}:{sort}"
            ),
            source_url=(
                target_url
                or (
                    "https://kream.co.kr/"
                    f"categories/{tab_id}/"
                    f"{category_id}"
                )
            ),
            collected_at=collected_at,
            http_status=200,
            payload=payload,
            discovered_count=len(products),
            success_count=success_count,
            failure_count=len(failures),
            metadata={
                "mode": self.MODE_DISCOVERY,
                "tab_id": tab_id,
                "category_id": category_id,
                "sort": sort,
                "include_detail": include_detail,
                "detail_limit": detail_limit,
            },
        )

    @staticmethod
    def _as_datetime(
        value: datetime | str,
    ) -> datetime:

        if isinstance(
            value,
            datetime,
        ):
            return value

        if isinstance(
            value,
            str,
        ):
            return datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )

        raise TypeError(
            "KREAM collected_at은 "
            "datetime 또는 ISO datetime 문자열이어야 합니다. "
            f"현재 타입: {type(value).__name__}"
        )