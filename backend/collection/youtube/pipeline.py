from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings

from collection.common.pipeline import BasePlatformPipeline

from .collector import YoutubeCollector
from .constants import DEFAULT_VIDEO_LIMIT


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

    # ============================================================
    # CREATOR (+ VIDEOS)
    # ============================================================

    def _collect_creator(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> dict:
        """
        채널 정보를 수집하고,
        params.collect_videos가 True이면 최근 영상도 함께 수집한다.

        한 번의 실행 = S3 파일 1개 + RawDocument 1행이므로
        채널과 영상을 하나의 payload에 담는다.
        """

        channel_id = params.get("channel_id")

        if not channel_id:
            raise ValueError(
                "YOUTUBE CREATOR target에는 params.channel_id가 필요합니다."
            )

        seed = params.get("seed") or {}

        collect_videos = bool(
            params.get("collect_videos", False)
        )

        video_limit = self._to_int(
            params.get("video_limit"),
            default=DEFAULT_VIDEO_LIMIT,
        )

        videos: list[dict] = []
        video_errors: list[dict] = []
        video_summary: dict = {}
        playlist_id = None

        with YoutubeCollector(
            api_key=settings.YOUTUBE_API_KEY
        ) as collector:

            profile = collector.collect_profile(
                channel_id,
                seed=seed,
            )

            if collect_videos:

                playlist_id = (
                    (
                        profile.get("content_details")
                        or {}
                    ).get("uploads_playlist_id")
                )

                video_result = collector.collect_videos(
                    channel_id,
                    playlist_id=playlist_id,
                    limit=video_limit,
                )

                playlist_id = video_result["playlist_id"]
                videos = video_result["videos"]
                video_errors = video_result["errors"]
                video_summary = video_result["summary"]

        collected_at = datetime.now(
            timezone.utc
        ).isoformat()

        payload = {
            "creator": profile,

            "videos": videos,

            "meta": {
                "source": "YOUTUBE",
                "source_url": target_url,
                "collected_at": collected_at,
                "collect_videos": collect_videos,
                "video_limit": (
                    video_limit
                    if collect_videos
                    else None
                ),
                "uploads_playlist_id": playlist_id,
                "video_summary": video_summary,
                "video_errors": video_errors,
            },
        }

        # 채널 1건 + 영상 N건
        discovered_count = 1 + int(
            video_summary.get("discovered_count", 0) or 0
        )

        success_count = 1 + len(videos)

        failure_count = int(
            video_summary.get("failure_count", 0) or 0
        )

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
            "discovered_count": discovered_count,
            "success_count": success_count,
            "failure_count": failure_count,

            # DB upsert용 작은 데이터
            "platform_data": {
                "profile": profile,
                "videos": videos,
                "collected_at": collected_at,
            },
        }

    # ============================================================
    # HELPER
    # ============================================================

    @staticmethod
    def _to_int(
        value,
        *,
        default: int,
    ) -> int:
        try:
            parsed = int(value)

        except (TypeError, ValueError):
            return default

        if parsed <= 0:
            return default

        return parsed
