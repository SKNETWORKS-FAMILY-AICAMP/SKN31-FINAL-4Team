from django.db import transaction
from django.utils import timezone

from crawler.models import (
    YoutubeContent,
    YoutubeContentMetric,
)


class YoutubeService:
    """
    YouTube 파싱 결과를 DB에 저장하는 Service.
    """

    @transaction.atomic
    def save_video(
        self,
        creator,
        video_data,
        crawl_job=None,
        observed_at=None,
    ):
        observed_at = observed_at or timezone.now()

        video_id = video_data["video_id"]

        # ====================================================
        # YoutubeContent
        # ====================================================

        content, created = YoutubeContent.objects.update_or_create(
            video_id=video_id,
            defaults={
                "creator": creator,
                "title": video_data.get("title", ""),
                "description": video_data.get("description"),
                "content_url": video_data.get("content_url", ""),
                "thumbnail_url": video_data.get("thumbnail_url"),
                "duration_seconds": video_data.get("duration_seconds"),
                "published_at": video_data.get("published_at"),
                "last_seen_at": observed_at,
            },
        )

        if created and not content.first_seen_at:
            content.first_seen_at = observed_at
            content.save(
                update_fields=[
                    "first_seen_at",
                ]
            )

        # ====================================================
        # YoutubeContentMetric
        # ====================================================

        metric, metric_created = YoutubeContentMetric.objects.get_or_create(
            content=content,
            observed_at=observed_at,
            defaults={
                "crawl_job": crawl_job,
                "view_count": video_data.get("view_count"),
                "like_count": video_data.get("like_count"),
                "comment_count": video_data.get("comment_count"),
            },
        )

        return {
            "content": content,
            "created": created,
            "metric": metric,
            "metric_created": metric_created,
        }
