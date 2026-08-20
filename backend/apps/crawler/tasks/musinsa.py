from celery import shared_task

from apps.crawler.models import (
    CrawlJob,
    CrawlTarget,
)

from apps.pipeline.musinsa_pipeline import (
    MusinsaPipeline,
)


@shared_task(
    bind=True,
    name="crawler.musinsa.run_target",
)
def run_musinsa_target(
    self,
    target_id: int,
    limit: int | None = None,
):
    """
    무신사 CrawlTarget 1개를 비동기로 실행한다.

    흐름:
        Celery Task
            ↓
        CrawlTarget 조회
            ↓
        MusinsaPipeline.run_target()
            ↓
        Collector
            ↓
        Parser
            ↓
        Service
            ↓
        DB 저장

    CrawlJob의 생성/성공/실패 처리는
    MusinsaPipeline이 담당한다.
    """

    target = CrawlTarget.objects.select_related("source").get(id=target_id)

    if target.source.code != "MUSINSA":
        raise ValueError("MUSINSA CrawlTarget만 실행할 수 있습니다.")

    job = MusinsaPipeline.run_target(
        crawl_target=target,
        trigger_type=CrawlJob.TriggerType.MANUAL,
        celery_task_id=self.request.id,
        limit=limit,
    )

    return {
        "job_id": job.id,
        "target_id": target.id,
        "status": job.status,
        "items_found": job.items_found,
        "items_created": job.items_created,
        "items_updated": job.items_updated,
    }


@shared_task(
    bind=True,
    name="crawler.musinsa.run_all_targets",
)
def run_all_musinsa_targets(
    self,
    limit: int | None = None,
):
    """
    활성화된 MUSINSA CrawlTarget 전체 실행.

    각 Target은 별도의 Celery Task로 분리해서 실행한다.
    """

    targets = (
        CrawlTarget.objects.select_related("source")
        .filter(
            source__code="MUSINSA",
            is_active=True,
        )
        .order_by("id")
    )

    task_ids = []

    for target in targets:
        result = run_musinsa_target.delay(
            target.id,
            limit,
        )

        task_ids.append(
            {
                "target_id": target.id,
                "task_id": result.id,
            }
        )

    return {
        "count": len(task_ids),
        "tasks": task_ids,
    }
