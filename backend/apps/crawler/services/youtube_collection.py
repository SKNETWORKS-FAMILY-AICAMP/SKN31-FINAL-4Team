"""Collect a creator's YouTube uploads directly from the Django UI."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from apps.crawler.services.youtube import YoutubeService


class YouTubeCollectionError(RuntimeError):
    """Raised when YouTube data cannot be collected safely."""


@dataclass(frozen=True)
class CollectionResult:
    checked: int
    added: int
    skipped: int
    filtered_out: int


class YoutubeCollectionService:
    """Fetch uploads for one creator and save only new video IDs."""

    def __init__(self) -> None:
        api_key = settings.YOUTUBE_API_KEY.strip()
        if not api_key:
            raise YouTubeCollectionError("YOUTUBE_API_KEY가 설정되지 않았습니다.")
        self.youtube = build("youtube", "v3", developerKey=api_key)
        self.persistence = YoutubeService()

    def collect_history(self, creator, days: int = 365) -> CollectionResult:
        """Collect all uploads published during the requested history window."""
        cutoff = timezone.now() - timedelta(days=days)
        video_ids = self._upload_ids_since(creator, cutoff=cutoff)
        return self._save(creator, video_ids)

    def collect_updates(self, creator) -> CollectionResult:
        """Collect uploads published since the creator was last checked."""
        if creator.last_checked_at:
            video_ids = self._upload_ids_since(creator, cutoff=creator.last_checked_at)
        else:
            # The first check stores only the newest upload as its baseline.
            video_ids = self._upload_ids_since(creator, cutoff=None, maximum=1)
        return self._save(creator, video_ids)

    def _upload_ids_since(self, creator, cutoff, maximum: int | None = None) -> list[str]:
        playlist_id = (creator.uploads_playlist_id or "").strip()
        if not playlist_id:
            raise YouTubeCollectionError(f"{creator.channel_name}의 업로드 재생목록 정보가 없습니다.")

        video_ids: list[str] = []
        page_token: str | None = None
        try:
            while True:
                response = (
                    self.youtube.playlistItems()
                    .list(
                        part="contentDetails",
                        playlistId=playlist_id,
                        maxResults=50,
                        pageToken=page_token,
                    )
                    .execute()
                )
                for item in response.get("items", []):
                    details = item.get("contentDetails", {})
                    published_at = parse_datetime(details.get("videoPublishedAt", ""))
                    if published_at is None:
                        continue
                    if timezone.is_naive(published_at):
                        published_at = timezone.make_aware(published_at)
                    if cutoff is not None and published_at <= cutoff:
                        return video_ids
                    video_id = details.get("videoId")
                    if video_id:
                        video_ids.append(str(video_id))
                        if maximum is not None and len(video_ids) >= maximum:
                            return video_ids

                page_token = response.get("nextPageToken")
                if not page_token:
                    return video_ids
        except HttpError as exc:
            raise YouTubeCollectionError("YouTube 업로드 목록을 조회하지 못했습니다.") from exc

    def _save(self, creator, video_ids: Iterable[str]) -> CollectionResult:
        unique_video_ids = list(dict.fromkeys(video_ids))
        added = 0
        skipped = 0
        filtered_out = 0
        newest_video_id = unique_video_ids[0] if unique_video_ids else creator.last_video_id
        fashion_filter = _fashion_filter_enabled(creator)

        try:
            for video_id_group in _chunks(unique_video_ids, 50):
                response = (
                    self.youtube.videos()
                    .list(
                        part="snippet,contentDetails,statistics",
                        id=",".join(video_id_group),
                        maxResults=50,
                    )
                    .execute()
                )
                for item in response.get("items", []):
                    video_data = _to_video_data(item)
                    if fashion_filter and not _is_fashion_relevant(video_data):
                        filtered_out += 1
                        continue

                    result = self.persistence.save_video(creator, video_data)
                    if result["created"]:
                        added += 1
                    else:
                        skipped += 1
        except HttpError as exc:
            raise YouTubeCollectionError("YouTube 영상 정보를 조회하지 못했습니다.") from exc

        creator.last_checked_at = timezone.now()
        creator.last_video_id = newest_video_id or ""
        creator.save(update_fields=["last_checked_at", "last_video_id", "updated_at"])
        return CollectionResult(
            checked=len(unique_video_ids),
            added=added,
            skipped=skipped,
            filtered_out=filtered_out,
        )


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _to_video_data(item: dict[str, Any]) -> dict[str, Any]:
    snippet = item.get("snippet", {})
    thumbnails = snippet.get("thumbnails", {})
    statistics = item.get("statistics", {})
    video_id = str(item["id"])
    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "description": snippet.get("description") or None,
        "content_url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail_url": _thumbnail_url(thumbnails),
        "duration_seconds": _duration_seconds(item.get("contentDetails", {}).get("duration", "")),
        "published_at": parse_datetime(snippet.get("publishedAt", "")),
        "view_count": _optional_int(statistics.get("viewCount")),
        "like_count": _optional_int(statistics.get("likeCount")),
        "comment_count": _optional_int(statistics.get("commentCount")),
    }


def _thumbnail_url(thumbnails: dict[str, Any]) -> str | None:
    for quality in ("maxres", "standard", "high", "medium", "default"):
        url = thumbnails.get(quality, {}).get("url")
        if url:
            return str(url)
    return None


def _duration_seconds(value: str) -> int | None:
    matched = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not matched:
        return None
    hours, minutes, seconds = (int(part or 0) for part in matched.groups())
    return hours * 3600 + minutes * 60 + seconds


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _fashion_filter_enabled(creator) -> bool:
    """Read the creator's current filter preference from creator_channels.json."""
    config_path = (
        Path(settings.BASE_DIR)
        / "collection"
        / "youtube"
        / "yt_crawler"
        / "creator_channels.json"
    )
    try:
        records = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True

    creator_name = _normalized_name(creator.channel_name)
    for record in records:
        if not isinstance(record, dict):
            continue
        channel_id = str(record.get("channel_id") or "").strip()
        if channel_id and channel_id == creator.channel_id:
            return bool(record.get("fashion_filter", True))

        configured_name = _normalized_name(str(record.get("name") or ""))
        if configured_name and (
            configured_name in creator_name or creator_name in configured_name
        ):
            return bool(record.get("fashion_filter", True))
    return True


def _normalized_name(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", value.lower())


def _is_fashion_relevant(video_data: dict[str, Any]) -> bool:
    """Reuse the standalone collector's established keyword filter."""
    from collection.youtube.yt_crawler.collector import is_fashion_relevant

    return is_fashion_relevant(video_data)
