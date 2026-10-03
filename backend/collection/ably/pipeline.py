from __future__ import annotations

from datetime import datetime, timezone
from collection.common.pipeline import BasePlatformPipeline
from collection.common.schemas import CollectionResult
from .collector import AblyCollector


class AblyPipeline(BasePlatformPipeline):
    """Collection only; RAW storage and STEP01/02 belong to the common runner."""
    SOURCE_CODE = "ABLY"

    def __init__(self, collector_factory=AblyCollector):
        self.collector_factory = collector_factory

    def collect(self, *, target_type, target_url, params) -> CollectionResult:
        entity = (target_type or "").strip().upper()
        if entity in {"STORE", "STORE_PROFILE"}:
            from .store_profile_pipeline import AblyStoreProfilePipeline
            return AblyStoreProfilePipeline().run(
                target_type=entity, target_url=target_url, params=params)
        if entity != "RANKING":
            raise ValueError(f"Unsupported ABLY target_type: {entity}")
        if not target_url:
            raise ValueError("ABLY RANKING target_url is required")
        with self.collector_factory() as collector:
            collected = collector.collect_ranking(target_url, params=params)
        ranking = dict(collected["ranking"])
        for key in ("ranking_mode", "parent_category_sno", "parent_category_name", "detail_category_name"):
            if key in params:
                ranking[key] = params[key]
        now = datetime.now(timezone.utc)
        payload = {
            "schema_version": "1.0", "source": self.SOURCE_CODE,
            "entity_type": entity, "collected_at": now.isoformat(),
            "ranking": ranking, "products": collected.get("products") or [],
            "errors": collected.get("errors") or [],
        }
        return CollectionResult(
            source_code=self.SOURCE_CODE, entity_type=entity,
            source_entity_id=self._build_ranking_id(ranking),
            collected_at=now, source_url=target_url, payload=payload,
            http_status=200 if ranking.get("raw_page_count") else None,
            discovered_count=ranking.get("discovered_count", len(payload["products"])),
            success_count=ranking.get("success_count", len(payload["products"])),
            failure_count=ranking.get("failure_count", len(payload["errors"])),
            metadata={"review_summary": ranking.get("review_summary") or {}},
        )

    @staticmethod
    def _build_ranking_id(ranking):
        values = [ranking.get("filter") or "best", ranking.get("market_type_sno") or "all",
                  ranking.get("category_sno") or "all", ranking.get("period") or "daily",
                  "-".join(map(str, ranking.get("age_tags") or ["all"]))]
        return "ably-ranking:" + ":".join(map(str, values))
