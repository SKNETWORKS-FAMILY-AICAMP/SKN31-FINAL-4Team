from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from collection.common.pipeline import BasePlatformPipeline
from collection.common.schemas import CollectionResult

from .constants import COMPONENT_LIST_API_URL
from .store_profile_collector import AblyStoreProfileCollector


class AblyStoreProfilePipeline(BasePlatformPipeline):
    SOURCE_CODE = "ABLY"

    def __init__(self, collector_factory=AblyStoreProfileCollector):
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

        collected_at = datetime.now(timezone.utc)
        run_id = uuid4().hex
        payload = {
            "schema_version": "1.0",
            "source": self.SOURCE_CODE,
            "entity_type": "STORE_PROFILE",
            "collected_at": collected_at.isoformat(),
            "run_id": run_id,
            "collection_scope": {
                "screen_name": "COMPONENT_LIST",
                "previous_screen_name": "BRAND_DEPARTMENT",
                "market_type_sno": 6,
                "exclude_category_snos": [535, 467],
            },
            **collected,
        }
        return CollectionResult(
            source_code=self.SOURCE_CODE, entity_type="STORE_PROFILE",
            source_entity_id=f"ably-brand-department-ranking-{run_id}",
            source_url=target_url or COMPONENT_LIST_API_URL,
            collected_at=collected_at, payload=payload,
            http_status=200 if collected["request_count"] else None,
            discovered_count=collected["products_count"],
            success_count=collected["products_count"],
            failure_count=collected["failure_count"],
            metadata={"brand_count": collected.get("brand_count", 0)},
        )
