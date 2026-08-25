"""Import standalone YouTube collector output into Django models."""

from __future__ import annotations

import json
import re
from datetime import timedelta, timezone as datetime_timezone
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.crawler.models import YoutubeContent, YoutubeContentMetric, YoutubeCreator


def load_json_list(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array and reject malformed collector output."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CommandError(f"Collector output was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CommandError(f"Invalid JSON in collector output: {path}") from exc

    if not isinstance(data, list):
        raise CommandError(f"Expected a JSON array in: {path}")
    return [row for row in data if isinstance(row, dict)]


def parse_collector_datetime(value: object):
    if not value:
        return None
    parsed = parse_datetime(str(value).replace("Z", "+00:00"))
    if parsed is not None and timezone.is_naive(parsed):
        return timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed


def parse_iso8601_duration_seconds(value: object) -> int | None:
    """Convert YouTube durations such as PT1H2M3S to seconds."""
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        str(value or ""),
    )
    if match is None:
        return None
    parts = {name: int(raw or 0) for name, raw in match.groupdict().items()}
    return (
        parts["days"] * 86_400
        + parts["hours"] * 3_600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


class Command(BaseCommand):
    help = "Import creator and video JSON emitted by the YouTube collector."

    def add_arguments(self, parser) -> None:
        default_dir = Path(__file__).resolve().parents[4] / "collection" / "youtube" / "data" / "youtube"
        parser.add_argument(
            "--input-dir",
            type=Path,
            default=default_dir,
            help="Directory containing creators_current.json and videos_current.json.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Only import videos published in the most recent N days.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate collector output without changing the database.",
        )

    def handle(self, *args, **options) -> None:
        input_dir: Path = options["input_dir"]
        days: int = options["days"]
        dry_run: bool = options["dry_run"]
        if days < 1:
            raise CommandError("--days must be at least 1.")

        creators = load_json_list(input_dir / "creators_current.json")
        videos = load_json_list(input_dir / "videos_current.json")
        channels = load_json_list(input_dir / "channels_current.json")
        channels_by_id = {str(row.get("channel_id", "")): row for row in channels}
        threshold = timezone.now() - timedelta(days=days)

        valid_videos = []
        for video in videos:
            published_at = parse_collector_datetime(video.get("published_at"))
            if video.get("video_id") and video.get("channel_id") and published_at and published_at >= threshold:
                video["_published_at"] = published_at
                valid_videos.append(video)

        self.stdout.write(
            f"Prepared creators={len(creators)}, videos={len(valid_videos)} "
            f"(published in the last {days} days)."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: database was not changed."))
            return

        observed_at = timezone.now()
        creator_by_channel_id: dict[str, YoutubeCreator] = {}
        creators_created = 0
        contents_created = 0
        contents_skipped = 0
        metric_rows: list[YoutubeContentMetric] = []

        with transaction.atomic():
            for row in creators:
                channel_id = str(row.get("channel_id", "")).strip()
                if not channel_id:
                    continue
                channel = channels_by_id.get(channel_id, {})
                creator, created = YoutubeCreator.objects.update_or_create(
                    channel_id=channel_id,
                    defaults={
                        "channel_name": str(row.get("channel_title") or row.get("creator_name") or channel_id),
                        "channel_url": f"https://www.youtube.com/channel/{channel_id}",
                        "profile_image_url": channel.get("channel_thumbnail_high") or None,
                        "description": channel.get("channel_description") or None,
                        "uploads_playlist_id": row.get("uploads_playlist_id") or None,
                        "last_seen_at": observed_at,
                        "last_checked_at": observed_at,
                    },
                )
                creator_by_channel_id[channel_id] = creator
                creators_created += int(created)

            for row in valid_videos:
                channel_id = str(row["channel_id"])
                creator = creator_by_channel_id.get(channel_id)
                if creator is None:
                    continue
                content, created = YoutubeContent.objects.get_or_create(
                    video_id=str(row["video_id"]),
                    defaults={
                        "creator": creator,
                        "title": str(row.get("title") or ""),
                        "description": row.get("description") or None,
                        "content_url": str(row.get("video_url") or ""),
                        "thumbnail_url": row.get("thumbnail_high") or row.get("thumbnail_medium") or None,
                        "duration_seconds": parse_iso8601_duration_seconds(row.get("duration_iso8601")),
                        "published_at": row["_published_at"],
                        "last_seen_at": observed_at,
                    },
                )
                if created:
                    content.first_seen_at = observed_at
                    content.save(update_fields=["first_seen_at"])
                    contents_created += 1
                else:
                    contents_skipped += 1
                    continue

                metric_rows.append(
                    YoutubeContentMetric(
                        content=content,
                        observed_at=observed_at,
                        view_count=row.get("view_count"),
                        like_count=row.get("like_count"),
                        comment_count=row.get("comment_count"),
                    )
                )

            # A metric is created only with a newly inserted content. Existing
            # video IDs are skipped, so repeated imports cannot add duplicates.
            if metric_rows:
                YoutubeContentMetric.objects.bulk_create(metric_rows, batch_size=500)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported creators={len(creator_by_channel_id)} (new={creators_created}), "
                f"videos={len(valid_videos)} "
                f"(new={contents_created}, skipped={contents_skipped})."
            )
        )
