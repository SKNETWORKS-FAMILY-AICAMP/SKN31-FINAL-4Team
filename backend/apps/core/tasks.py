from __future__ import annotations

from celery import shared_task
from django.conf import settings
from datetime import timedelta
from django.db.models import Q
from django.utils import timezone

from apps.core.models import CrawlTarget
from apps.core.services import (
    create_crawl_run,
    create_raw_document,
    mark_crawl_run_failed,
    mark_crawl_run_success,
    mark_target_crawled,
)
from apps.core.services.registry import get_pipeline_class


@shared_task(
    bind=True,
    name="core.run_live_target",
)
def run_live_target(
    self,
    target_id: int,
):
    target = (
        CrawlTarget.objects
        .select_related("source")
        .get(id=target_id)
    )

    crawl_run = create_crawl_run(
        target=target,
        celery_task_id=self.request.id,
    )

    try:
        # ==============================================
        # PLATFORM PIPELINE
        # ==============================================

        pipeline_class = (
            get_pipeline_class(
                target.source.code
            )
        )

        pipeline = pipeline_class(
            bucket=(
                settings.AWS_STORAGE_BUCKET_NAME
            ),
            region_name=(
                settings.AWS_REGION
            ),
        )

        # ==============================================
        # 핵심
        #
        # PRODUCT / RANKING을 여기서 Pipeline으로 전달
        # ==============================================

        result = pipeline.run_target(
            target_type=target.target_type,
            target_url=target.target_url,
            params=target.params,
        )

        # ==============================================
        # RAW DOCUMENT
        # ==============================================

        create_raw_document(
            crawl_run=crawl_run,

            document_type=(
                result["entity_type"]
            ),

            external_id=(
                result[
                    "source_entity_id"
                ]
            ),

            source_url=(
                result.get(
                    "source_url"
                )
            ),

            s3_bucket=(
                result["s3"]["bucket"]
            ),

            s3_key=(
                result["s3"]["key"]
            ),

            content_hash=(
                result.get(
                    "content_hash"
                )
            ),

            http_status=(
                result.get(
                    "http_status"
                )
            ),

            content_type=(
                result.get(
                    "content_type"
                )
            ),

            collected_at=(
                result.get(
                    "collected_at"
                )
            ),
        )

        # ==============================================
        # RUN SUCCESS
        # ==============================================

        mark_crawl_run_success(
            crawl_run,

            discovered_count=(
                result.get(
                    "discovered_count",
                    0,
                )
            ),

            success_count=(
                result.get(
                    "success_count",
                    0,
                )
            ),

            failure_count=(
                result.get(
                    "failure_count",
                    0,
                )
            ),
        )

        mark_target_crawled(
            target
        )

        return {
            "target_id": target.id,

            "target_type": (
                target.target_type
            ),

            "source": (
                target.source.code
            ),

            "crawl_run_id": (
                crawl_run.id
            ),

            "entity_type": (
                result[
                    "entity_type"
                ]
            ),

            "source_entity_id": (
                result[
                    "source_entity_id"
                ]
            ),

            "s3_bucket": (
                result["s3"]["bucket"]
            ),

            "s3_key": (
                result["s3"]["key"]
            ),

            "verified": (
                result[
                    "s3"
                ][
                    "verified"
                ]
            ),

            "discovered_count": (
                result.get(
                    "discovered_count",
                    0,
                )
            ),

            "success_count": (
                result.get(
                    "success_count",
                    0,
                )
            ),

            "failure_count": (
                result.get(
                    "failure_count",
                    0,
                )
            ),
        }

    except Exception as exc:

        mark_crawl_run_failed(
            crawl_run,
            error=exc,
            error_code=(
                exc.__class__.__name__
            ),
        )

        raise

@shared_task(
    name="core.dispatch_due_targets",
)
def dispatch_due_targets():
    now = timezone.now()

    targets = (
        CrawlTarget.objects
        .select_related("source")
        .filter(
            is_active=True,
            collection_mode="LIVE",
        )
        .filter(
            Q(next_crawl_at__isnull=True)
            | Q(next_crawl_at__lte=now)
        )
    )

    dispatched = 0

    for target in targets:
        interval = (
            target.interval_minutes
            or target.source.crawl_interval_minutes
            or 1440
        )

        target.next_crawl_at = (
            now
            + timedelta(
                minutes=interval
            )
        )

        target.save(
            update_fields=[
                "next_crawl_at",
            ]
        )

        run_live_target.delay(
            target.id
        )

        dispatched += 1

    return {
        "dispatched": dispatched,
    }