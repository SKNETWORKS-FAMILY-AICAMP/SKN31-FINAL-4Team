from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
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


logger = logging.getLogger(__name__)


# 한 번의 dispatcher 실행에서 너무 많은 타깃을
# 동시에 queue에 넣지 않도록 제한.
DISPATCH_BATCH_SIZE = 100


# ============================================================
# LIVE TARGET EXECUTOR
# ============================================================


@shared_task(
    bind=True,
    name="core.run_live_target",
)
def run_live_target(
    self,
    target_id: int,
):
    """
    CrawlTarget 하나를 실제로 실행한다.

    흐름:
        CrawlTarget
        -> CrawlRun 생성
        -> 플랫폼 Pipeline 실행
        -> S3 RAW 저장
        -> RawDocument 생성
        -> 플랫폼별 후처리
        -> CrawlRun 성공/실패 처리
        -> CrawlTarget last_crawled_at 갱신
    """

    target = (
        CrawlTarget.objects
        .select_related("source")
        .get(id=target_id)
    )

    # ========================================================
    # 0. CRAWL RUN
    # ========================================================

    crawl_run = create_crawl_run(
        target=target,
        celery_task_id=self.request.id,
    )

    try:
        # ====================================================
        # 1. PLATFORM PIPELINE
        # ====================================================

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

        # ====================================================
        # 2. RAW DOCUMENT
        #
        # 실제 RAW 데이터는 S3에 저장한다.
        # RDS에는 S3 위치와 메타데이터만 기록한다.
        # ====================================================

        create_raw_document(
            crawl_run=crawl_run,
            document_type=result["entity_type"],
            external_id=result["source_entity_id"],
            source_url=result.get("source_url"),
            s3_bucket=result["s3"]["bucket"],
            s3_key=result["s3"]["key"],
            content_hash=result.get(
                "content_hash"
            ),
            http_status=result.get(
                "http_status"
            ),
            content_type=result.get(
                "content_type"
            ),
            collected_at=result.get(
                "collected_at"
            ),
        )

        # ====================================================
        # 3. SOURCE-SPECIFIC POST PROCESS
        #
        # 현재:
        # YOUTUBE CREATOR
        #   -> ContentProfile upsert
        #
        # 이후:
        # VIDEO / PRODUCT / STORE 등 확장 가능
        # ====================================================

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

        # ====================================================
        # 4. RUN SUCCESS
        # ====================================================

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

        # ====================================================
        # 5. RESULT
        # ====================================================

        return {
            "target_id": target.id,
            "target_name": target.name,
            "target_type": target.target_type,
            "source": target.source.code,
            "crawl_run_id": crawl_run.id,
            "entity_type": result[
                "entity_type"
            ],
            "source_entity_id": result[
                "source_entity_id"
            ],
            "s3_bucket": result["s3"][
                "bucket"
            ],
            "s3_key": result["s3"]["key"],
            "verified": result["s3"].get(
                "verified",
                False,
            ),
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
        # ====================================================
        # RUN FAILED
        # ====================================================

        mark_crawl_run_failed(
            crawl_run,
            error=exc,
            error_code=exc.__class__.__name__,
        )

        raise


# ============================================================
# CELERY ENQUEUE
# ============================================================


def _enqueue_live_target(
    target_id: int,
):
    """
    DB transaction commit 이후 호출된다.

    Celery Broker 등록에 실패하면 next_crawl_at을
    현재 시각으로 되돌려 다음 dispatcher 실행에서
    다시 잡힐 수 있게 한다.
    """

    try:
        run_live_target.delay(
            target_id
        )

    except Exception:
        logger.exception(
            "Failed to enqueue CrawlTarget. "
            "target_id=%s",
            target_id,
        )

        # 이미 next_crawl_at이 미래로 갱신된 상태이므로,
        # Broker 등록 실패 시 다시 실행 대상이 되게 복구.
        CrawlTarget.objects.filter(
            id=target_id,
            is_active=True,
        ).update(
            next_crawl_at=timezone.now()
        )


# ============================================================
# LIVE TARGET DISPATCHER
# ============================================================


@shared_task(
    name="core.dispatch_due_targets",
)
def dispatch_due_targets():
    """
    실행 시간이 도래한 LIVE CrawlTarget을 조회하여
    Celery queue에 등록한다.

    실행 조건:
        - is_active=True
        - collection_mode=LIVE
        - next_crawl_at IS NULL
          또는
        - next_crawl_at <= 현재 시각

    동시성 처리:
        select_for_update(skip_locked=True)

    Queue 등록:
        transaction.on_commit()

    즉 여러 dispatcher가 동시에 실행되더라도
    같은 CrawlTarget을 중복 dispatch하는 것을
    최대한 방지한다.
    """

    now = timezone.now()

    dispatched = 0
    target_ids = []

    # ========================================================
    # 1. DUE TARGET LOCK
    # ========================================================

    with transaction.atomic():
        targets = list(
            CrawlTarget.objects
            .select_for_update(
                skip_locked=True
            )
            .select_related("source")
            .filter(
                is_active=True,
                collection_mode=(
                    CrawlTarget.CollectionMode.LIVE
                ),
            )
            .filter(
                Q(
                    next_crawl_at__isnull=True
                )
                | Q(
                    next_crawl_at__lte=now
                )
            )
            .order_by(
                "priority",
                "id",
            )[
                :DISPATCH_BATCH_SIZE
            ]
        )

        # ====================================================
        # 2. SCHEDULE NEXT RUN
        # ====================================================

        for target in targets:
            interval = (
                target.interval_minutes
                or (
                    target
                    .source
                    .crawl_interval_minutes
                )
                or 1440
            )

            next_crawl_at = (
                now
                + timedelta(
                    minutes=interval
                )
            )

            target.next_crawl_at = (
                next_crawl_at
            )

            target.save(
                update_fields=[
                    "next_crawl_at",
                ]
            )

            # ================================================
            # 3. QUEUE AFTER DB COMMIT
            #
            # DB transaction이 성공적으로 commit된 다음에만
            # Celery Broker에 task를 등록한다.
            #
            # lambda closure 문제를 피하기 위해
            # target_id를 default argument로 고정.
            # ================================================

            transaction.on_commit(
                lambda target_id=target.id: (
                    _enqueue_live_target(
                        target_id
                    )
                )
            )

            target_ids.append(
                target.id
            )

            dispatched += 1
    return {
        "dispatched": dispatched,
        "target_ids": target_ids,
    }