from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings

from collection.common.pipeline import BasePlatformPipeline
from collection.common.schemas import CollectionResult

from .collector import YoutubeCollector
from .constants import DEFAULT_COMMENT_LIMIT, DEFAULT_VIDEO_LIMIT, WATCH_URL


class YoutubePipeline(BasePlatformPipeline):
    SOURCE_CODE = "YOUTUBE"

    def collect(self, *, target_type: str, target_url: str | None, params: dict) -> CollectionResult:
        target_type = (target_type or "").upper().strip()
        params = params or {}
        if target_type == "CREATOR":
            return self._collect_creator(target_url=target_url, params=params)
        if target_type == "VIDEO":
            return self._collect_video_comments(target_url=target_url, params=params)
        raise ValueError(f"YOUTUBE에서 지원하지 않는 target_type: {target_type}")

    def _collect_creator(self, *, target_url: str | None, params: dict) -> CollectionResult:
        channel_id = str(params.get("channel_id") or "").strip()
        if not channel_id:
            raise ValueError("YOUTUBE CREATOR target에는 params.channel_id가 필요합니다.")

        seed = params.get("seed") or {}
        collect_videos = bool(params.get("collect_videos", False))
        video_limit = self._to_int(params.get("video_limit"), default=DEFAULT_VIDEO_LIMIT)
        videos = []
        video_errors = []
        video_summary = {}
        playlist_id = None

        with YoutubeCollector(api_key=settings.YOUTUBE_API_KEY) as collector:
            profile = collector.collect_profile(channel_id, seed=seed)
            if collect_videos:
                playlist_id = (profile.get("content_details") or {}).get("uploads_playlist_id")
                video_result = collector.collect_videos(
                    channel_id,
                    playlist_id=playlist_id,
                    limit=video_limit,
                )
                playlist_id = video_result["playlist_id"]
                videos = video_result["videos"]
                video_errors = video_result["errors"]
                video_summary = video_result["summary"]

        collected_at = datetime.now(timezone.utc)
        payload = {
            "creator": profile,
            "videos": videos,
            "meta": {
                "source": "YOUTUBE",
                "source_url": target_url,
                "collected_at": collected_at.isoformat(),
                "collect_videos": collect_videos,
                "video_limit": video_limit if collect_videos else None,
                "uploads_playlist_id": playlist_id,
                "video_summary": video_summary,
                "video_errors": video_errors,
            },
        }
        discovered_count = 1 + int(video_summary.get("discovered_count", 0) or 0)
        failure_count = int(video_summary.get("failure_count", 0) or 0)
        return CollectionResult(
            source_code=self.SOURCE_CODE,
            entity_type="CREATOR",
            source_entity_id=channel_id,
            source_url=target_url or profile.get("channel_url"),
            collected_at=collected_at,
            http_status=200,
            payload=payload,
            discovered_count=discovered_count,
            success_count=1 + len(videos),
            failure_count=failure_count,
            metadata={
                "platform_data": {
                    "profile": profile,
                    "videos": videos,
                    "collected_at": collected_at.isoformat(),
                }
            },
        )

    def _collect_video_comments(self, *, target_url: str | None, params: dict) -> CollectionResult:
        video_id = str(params.get("video_id") or "").strip()
        if not video_id:
            raise ValueError("YOUTUBE VIDEO target에는 params.video_id가 필요합니다.")
        comment_limit = self._to_int(params.get("comment_limit"), default=DEFAULT_COMMENT_LIMIT)
        comment_order = str(params.get("comment_order") or "relevance").lower()
        if comment_order not in {"time", "relevance"}:
            comment_order = "relevance"

        with YoutubeCollector(api_key=settings.YOUTUBE_API_KEY) as collector:
            data = collector.collect_comments(video_id, limit=comment_limit, order=comment_order)

        collected_at = datetime.now(timezone.utc)
        comments = data.get("comments") or []
        error = data.get("error")
        disabled = bool(data.get("disabled"))
        source_url = target_url or WATCH_URL.format(video_id=video_id)
        payload = {
            "video": {"video_id": video_id},
            "comments": comments,
            "meta": {
                "source": "YOUTUBE",
                "source_url": source_url,
                "collected_at": collected_at.isoformat(),
                "comment_limit": comment_limit,
                "comment_order": comment_order,
                "comments_disabled": disabled,
                "error": error,
                "summary": data.get("summary") or {},
            },
        }
        return CollectionResult(
            source_code=self.SOURCE_CODE,
            entity_type="COMMENT",
            source_entity_id=video_id,
            source_url=source_url,
            collected_at=collected_at,
            http_status=200 if not error else None,
            payload=payload,
            discovered_count=len(comments),
            success_count=len(comments),
            failure_count=1 if error else 0,
            metadata={
                "platform_data": {
                    "video_id": video_id,
                    "comments": comments,
                    "disabled": disabled,
                    "error": error,
                }
            },
        )

    @staticmethod
    def _to_int(value, *, default: int) -> int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default
