from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from django.conf import settings

from collection.common.pipeline import BasePlatformPipeline

from .collector import YoutubeCollector


class YoutubePipeline(BasePlatformPipeline):
    SOURCE = "YOUTUBE"

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:

        target_type = (target_type or "").upper()
        params = params or {}

        if target_type == "CREATOR":
            return self._collect_creator(
                target_url=target_url,
                params=params,
            )

        raise ValueError(
            f"YOUTUBE에서 지원하지 않는 target_type: {target_type}"
        )

    def _collect_creator(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> dict:

        channel_id = params.get("channel_id")

        if not channel_id:
            raise ValueError(
                "YOUTUBE CREATOR target에는 params.channel_id가 필요합니다."
            )

        seed = params.get("seed") or {}

        with YoutubeCollector(
            api_key=settings.YOUTUBE_API_KEY
        ) as collector:

            profile = collector.collect_profile(
                channel_id,
                seed=seed,
            )

        collected_at = datetime.now(
            timezone.utc
        ).isoformat()

        payload = {
            "creator": profile,
            "meta": {
                "source": "YOUTUBE",
                "source_url": target_url,
                "collected_at": collected_at,
            },
        }

        return {
            "entity_type": "CREATOR",
            "source_entity_id": channel_id,
            "source_url": (
                target_url
                or profile.get("channel_url")
            ),
            "collected_at": collected_at,
            "http_status": 200,
            "content_type": "application/json",
            "payload": payload,
            "discovered_count": 1,
            "success_count": 1,
            "failure_count": 0,

            # DB upsert용 작은 데이터
            "platform_data": profile,
        }