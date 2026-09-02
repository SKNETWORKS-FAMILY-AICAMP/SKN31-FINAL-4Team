from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
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
        # ========================================================
        # 1. PLATFORM PIPELINE
        # ========================================================

        pipeline_class = get_pipeline_class(
            target.source.code
        )

        pipeline = pipeline_class(
            bucket=settings.AWS_STORAGE_BUCKET_NAME,
            region_name=settings.AWS_REGION,
        )

        result = pipeline.run_target(
            target_type=target.target_type,
            target_url=target.target_url,
            params=target.params,
        )

        # ========================================================
        # 2. RAW DOCUMENT
        #
        # S3 RAW 업로드가 성공한 뒤
        # RDS에는 S3 위치/메타데이터만 기록한다.
        # ========================================================

        create_raw_document(
            crawl_run=crawl_run,
            document_type=result["entity_type"],
            external_id=result["source_entity_id"],
            source_url=result.get("source_url"),
            s3_bucket=result["s3"]["bucket"],
            s3_key=result["s3"]["key"],
            content_hash=result.get("content_hash"),
            http_status=result.get("http_status"),
            content_type=result.get("content_type"),
            collected_at=result.get("collected_at"),
        )

        # ========================================================
        # 3. SOURCE-SPECIFIC POST PROCESS
        #
        # YOUTUBE CREATOR:
        # S3 RAW 보존 후 ContentProfile을 최신 상태로 upsert.
        #
        # VIDEO 등은 이후 여기서 별도 service로 확장한다.
        # ========================================================

        profile_id = None

        if (
            target.source.code.upper() == "YOUTUBE"
            and result["entity_type"] == "CREATOR"
        ):
            platform_data = result.get(
                "platform_data"
            )

            if platform_data:
                from apps.core.services.content import (
                    upsert_youtube_content_profile,
                )

                profile = (
                    upsert_youtube_content_profile(
                        source=target.source,
                        data=platform_data,
                    )
                )

                profile_id = profile.id

        # ========================================================
        # 4. RUN SUCCESS
        # ========================================================

        mark_crawl_run_success(
            crawl_run,
            discovered_count=result.get(
                "discovered_count",
                0,
            ),
            success_count=result.get(
                "success_count",
                0,
            ),
            failure_count=result.get(
                "failure_count",
                0,
            ),
        )

        mark_target_crawled(
            target
        )

        # ========================================================
        # 5. RESULT
        # ========================================================

        return {
            "target_id": target.id,
            "target_name": target.name,
            "target_type": target.target_type,
            "source": target.source.code,
            "crawl_run_id": crawl_run.id,
            "entity_type": result["entity_type"],
            "source_entity_id": (
                result["source_entity_id"]
            ),
            "s3_bucket": result["s3"]["bucket"],
            "s3_key": result["s3"]["key"],
            "verified": result["s3"]["verified"],
            "discovered_count": result.get(
                "discovered_count",
                0,
            ),
            "success_count": result.get(
                "success_count",
                0,
            ),
            "failure_count": result.get(
                "failure_count",
                0,
            ),
            "content_profile_id": profile_id,
        }

    except Exception as exc:
        mark_crawl_run_failed(
            crawl_run,
            error=exc,
            error_code=exc.__class__.__name__,
        )

        raise


@shared_task(
    name="core.dispatch_due_targets",
)
def dispatch_due_targets():
    """
    실행 시간이 도래한 LIVE CrawlTarget을 Celery queue에 등록한다.

    next_crawl_at이 비어 있거나 현재 시각 이전이면 실행 대상이며,
    실행을 큐에 넣으면서 다음 실행 예정 시각을 갱신한다.
    """

    now = timezone.now()

    targets = (
        CrawlTarget.objects
        .select_related("source")
        .filter(
            is_active=True,
            collection_mode=(
                CrawlTarget.CollectionMode.LIVE
            ),
        )
        .filter(
            Q(next_crawl_at__isnull=True)
            | Q(next_crawl_at__lte=now)
        )
        .order_by(
            "priority",
            "id",
        )
    )

    dispatched = 0
    target_ids = []

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

        target_ids.append(
            target.id
        )

        dispatched += 1

    return {
        "dispatched": dispatched,
        "target_ids": target_ids,
    }
