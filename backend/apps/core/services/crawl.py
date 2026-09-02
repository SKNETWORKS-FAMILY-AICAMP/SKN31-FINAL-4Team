from __future__ import annotations

from django.utils import timezone

from apps.core.models import (
    CrawlRun,
    CrawlTarget,
    RawDocument,
)


def create_crawl_run(
    *,
    target: CrawlTarget,
    celery_task_id: str | None = None,
) -> CrawlRun:
    return CrawlRun.objects.create(
        source=target.source,
        crawl_target=target,
        run_type=target.collection_mode,
        target=target.target_url,
        params=target.params,
        status=CrawlRun.Status.RUNNING,
        celery_task_id=celery_task_id,
        started_at=timezone.now(),
    )


def mark_crawl_run_success(
    crawl_run: CrawlRun,
    *,
    discovered_count: int = 0,
    success_count: int = 0,
    failure_count: int = 0,
) -> None:
    crawl_run.status = (
        CrawlRun.Status.SUCCESS
        if failure_count == 0
        else CrawlRun.Status.PARTIAL_SUCCESS
    )

    crawl_run.discovered_count = discovered_count
    crawl_run.success_count = success_count
    crawl_run.failure_count = failure_count
    crawl_run.finished_at = timezone.now()

    crawl_run.save(
        update_fields=[
            "status",
            "discovered_count",
            "success_count",
            "failure_count",
            "finished_at",
        ]
    )


def mark_crawl_run_failed(
    crawl_run: CrawlRun,
    *,
    error: Exception | str,
    error_code: str | None = None,
) -> None:
    crawl_run.status = CrawlRun.Status.FAILED
    crawl_run.error_code = error_code
    crawl_run.error_message = str(error)[:10000]
    crawl_run.finished_at = timezone.now()

    crawl_run.save(
        update_fields=[
            "status",
            "error_code",
            "error_message",
            "finished_at",
        ]
    )


def create_raw_document(
    *,
    crawl_run: CrawlRun,
    document_type: str,
    external_id: str | None,
    source_url: str | None,
    s3_bucket: str,
    s3_key: str,
    content_hash: str | None = None,
    http_status: int | None = None,
    content_type: str | None = "application/json",
    collected_at=None,
) -> RawDocument:
    return RawDocument.objects.create(
        source=crawl_run.source,
        crawl_run=crawl_run,
        document_type=document_type,
        external_id=external_id,
        source_url=source_url,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        content_hash=content_hash,
        http_status=http_status,
        content_type=content_type,
        collected_at=collected_at or timezone.now(),
    )


def mark_target_crawled(
    target: CrawlTarget,
) -> None:
    target.last_crawled_at = timezone.now()

    target.save(
        update_fields=[
            "last_crawled_at",
        ]
    )