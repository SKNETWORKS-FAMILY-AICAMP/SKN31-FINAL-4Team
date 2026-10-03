from __future__ import annotations

import hashlib
import json
import os
from datetime import timedelta

from django.utils import timezone

from apps.core.models import ContentItem, CrawlRun, RawDocument, Source
from apps.core.services.content import upsert_youtube_comments
from collection.common.storage import S3RawStorage

from .pipeline import YoutubePipeline


def _hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def collect_daily_youtube_comments(*, video_limit: int | None = None, comment_limit: int | None = None, lookback_days: int | None = None) -> dict:
    video_limit = video_limit or int(os.getenv("FEEDIT_YOUTUBE_DAILY_VIDEO_LIMIT", "100"))
    comment_limit = comment_limit or int(os.getenv("FEEDIT_YOUTUBE_COMMENT_LIMIT", "100"))
    lookback_days = lookback_days or int(os.getenv("FEEDIT_YOUTUBE_COMMENT_LOOKBACK_DAYS", "180"))
    source = Source.objects.get(code__iexact="YOUTUBE")
    run = CrawlRun.objects.create(
        source=source,
        run_type=CrawlRun.RunType.LIVE,
        target="daily-youtube-comments",
        params={"video_limit": video_limit, "comment_limit": comment_limit, "lookback_days": lookback_days},
        status=CrawlRun.Status.RUNNING,
        started_at=timezone.now(),
    )
    storage = S3RawStorage(
        bucket=os.environ["AWS_STORAGE_BUCKET_NAME"],
        region_name=os.getenv("AWS_REGION", "ap-northeast-2"),
    )
    pipeline = YoutubePipeline()
    since = timezone.now() - timedelta(days=lookback_days)
    items = list(ContentItem.objects.filter(source=source, published_at__gte=since).order_by("-published_at", "-id")[:video_limit])
    discovered = created = updated = failed = disabled = 0
    errors = []
    try:
        for item in items:
            try:
                result = pipeline.run(
                    target_type="VIDEO",
                    target_url=item.content_url,
                    params={"video_id": item.external_content_id, "comment_limit": comment_limit, "comment_order": "time"},
                )
                stored = storage.save(
                    source_code=result.source_code,
                    entity_type=result.entity_type,
                    source_entity_id=result.source_entity_id,
                    collected_at=result.collected_at,
                    payload=result.payload,
                )
                RawDocument.objects.create(
                    source=source, crawl_run=run, document_type=result.entity_type,
                    external_id=result.source_entity_id, source_url=result.source_url,
                    s3_bucket=stored.bucket, s3_key=stored.key, content_hash=_hash(result.payload),
                    http_status=result.http_status, content_type="application/json", collected_at=result.collected_at,
                )
                platform_data = (result.metadata or {}).get("platform_data") or {}
                ingested = upsert_youtube_comments(
                    source=source, content_item=item, comments=platform_data.get("comments") or [],
                )
                discovered += result.discovered_count
                created += int(ingested.get("created") or 0)
                updated += int(ingested.get("updated") or 0)
                failed += int(ingested.get("failed") or 0)
                disabled += int(bool(platform_data.get("disabled")))
            except Exception as exc:
                failed += 1
                errors.append({"video_id": item.external_content_id, "error_type": type(exc).__name__, "error_message": str(exc)[:300]})

        run.status = CrawlRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.discovered_count = discovered
        run.success_count = created + updated
        run.failure_count = failed
        run.save(update_fields=["status", "finished_at", "discovered_count", "success_count", "failure_count"])
    except Exception as exc:
        run.status = CrawlRun.Status.FAILED
        run.finished_at = timezone.now()
        run.failure_count = failed + 1
        run.error_code = type(exc).__name__
        run.error_message = str(exc)[:5000]
        run.save(update_fields=["status", "finished_at", "failure_count", "error_code", "error_message"])
        raise

    return {
        "crawl_run_id": run.id, "videos": len(items), "comments_discovered": discovered,
        "created": created, "updated": updated, "failed": failed,
        "comments_disabled_videos": disabled, "errors": errors[:20],
    }
