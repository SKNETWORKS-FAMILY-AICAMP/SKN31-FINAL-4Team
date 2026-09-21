from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from collection.common.pipeline import BasePlatformPipeline

from .constants import COMPONENT_LIST_API_URL
from .store_profile_collector import AblyStoreProfileCollector


class AblyStoreProfilePipeline(BasePlatformPipeline):
    SOURCE = "ABLY"

    def __init__(
        self,
        *,
        bucket: str,
        region_name: str | None = None,
        storage=None,
        collector_factory=AblyStoreProfileCollector,
    ):
        if storage is None:
            super().__init__(bucket=bucket, region_name=region_name)
        else:
            self.storage = storage
        self.collector_factory = collector_factory

    def collect(self, *, target_type: str, target_url: str | None, params: dict) -> dict:
        if (target_type or "").strip().upper() not in {"STORE", "STORE_PROFILE"}:
            raise ValueError(f"unsupported ABLY store profile target_type: {target_type}")

        collector = self.collector_factory()
        try:
            collected = collector.collect_all(category_snos=params.get("category_snos"))
        finally:
            close = getattr(collector, "close", None)
            if close:
                close()

        collected_at = datetime.now(timezone.utc).isoformat()
        run_id = uuid4().hex
        payload = {
            "schema_version": "1.0",
            "source": self.SOURCE,
            "entity_type": "STORE_PROFILE",
            "collected_at": collected_at,
            "run_id": run_id,
            "collection_scope": {
                "screen_name": "COMPONENT_LIST",
                "previous_screen_name": "BRAND_DEPARTMENT",
                "market_type_sno": 6,
                "exclude_category_snos": [535, 467],
            },
            **collected,
        }
        return {
            "entity_type": "STORE_PROFILE",
            "source_entity_id": f"ably-brand-department-ranking-{run_id}",
            "source_url": target_url or COMPONENT_LIST_API_URL,
            "collected_at": collected_at,
            "http_status": (
                200
                if collected["request_count"] and not collected["failure_count"]
                else 206 if collected["request_count"] else None
            ),
            "content_type": "application/json",
            "payload": payload,
            "discovered_count": collected["products_count"],
            "success_count": collected["products_count"],
            "failure_count": collected["failure_count"],
            "platform_data": {
                "brand_count": collected.get("brand_count", 0),
                "request_count": collected["request_count"],
            },
        }
