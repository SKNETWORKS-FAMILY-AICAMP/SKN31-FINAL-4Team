from __future__ import annotations

from datetime import datetime, timezone

from collection.common.pipeline import BasePlatformPipeline

from .collector import AblyCollector


class AblyPipeline(BasePlatformPipeline):
    """ABLY API 결과를 공통 S3 Raw 저장 흐름에 연결한다."""

    SOURCE = "ABLY"

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:
        target_type = (target_type or "").upper().strip()
        if target_type != "RANKING":
            raise ValueError(
                f"ABLY에서 지원하지 않는 target_type입니다: {target_type}"
            )
        if not target_url:
            raise ValueError("ABLY RANKING target_url이 없습니다.")

        with AblyCollector() as collector:
            collected = collector.collect_ranking(target_url, params=params)

        ranking = collected["ranking"]
        collected_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "schema_version": "1.0",
            "source": self.SOURCE,
            "entity_type": "RANKING",
            "collected_at": collected_at,
            "ranking": ranking,
            "products": collected.get("products") or [],
            "errors": collected.get("errors") or [],
        }

        return {
            "entity_type": "RANKING",
            "source_entity_id": self._build_ranking_id(ranking),
            "source_url": target_url,
            "collected_at": collected_at,
            "http_status": 200 if ranking["raw_page_count"] else None,
            "content_type": "application/json",
            "payload": payload,
            "discovered_count": ranking["discovered_count"],
            "success_count": ranking["success_count"],
            "failure_count": ranking["failure_count"],
            # 최신 요청에 따라 normalize/DB post-process는 연결하지 않는다.
            "platform_data": None,
        }

    @staticmethod
    def _build_ranking_id(ranking: dict) -> str:
        age_tags = ranking.get("age_tags") or ["all"]
        values = [
            ranking.get("filter") or "best",
            ranking.get("market_type_sno") or "all",
            ranking.get("category_sno") or "all",
            ranking.get("period") or "daily",
            "-".join(str(value) for value in age_tags),
        ]
        return "ably-ranking:" + ":".join(str(value) for value in values)
