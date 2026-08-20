from celery import shared_task

from apps.crawler.models import (
    CrawlJob,
    CrawlTarget,
)
from apps.pipeline.zigzag_pipeline import (
    ZigzagPipeline,
)

# ============================================================
# RUN ONE TARGET
# ============================================================


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_zigzag_target(
    self,
    crawl_target_id: int,
    trigger_type: str = CrawlJob.TriggerType.SCHEDULED,
):
    """
    지그재그 카테고리 CrawlTarget 1개 실행.

    target_value 컨벤션:
        "{category_id}:{sort}"

    예:
        "474:200"

    sort가 없으면 기본값:
        "200"
    """

    try:
        crawl_target = CrawlTarget.objects.select_related("source").get(
            pk=crawl_target_id,
            source__code="ZIGZAG",
            target_type=CrawlTarget.TargetType.CATEGORY,
            is_active=True,
        )

    except CrawlTarget.DoesNotExist:
        return None

    # --------------------------------------------------------
    # Parse target
    # --------------------------------------------------------

    target_value = (crawl_target.target_value or "").strip()

    category_id, separator, sort = target_value.partition(":")

    category_id = category_id.strip()

    if not category_id:
        raise ValueError(
            "ZIGZAG CrawlTarget의 "
            "category_id가 비어 있습니다. "
            f"target_id={crawl_target_id}"
        )

    sort = sort.strip() if separator else ""

    sort = sort or "200"

    # --------------------------------------------------------
    # Pipeline
    # --------------------------------------------------------

    pipeline = ZigzagPipeline()

    try:
        crawl_job = pipeline.run(
            crawl_target=crawl_target,
            category_id=category_id,
            sort=sort,
            trigger_type=trigger_type,
        )

    except Exception as exc:
        raise self.retry(
            exc=exc,
        )

    return crawl_job.pk if crawl_job else None


# ============================================================
# RUN ALL TARGETS
# ============================================================


@shared_task
def run_all_zigzag_targets(
    trigger_type: str = CrawlJob.TriggerType.SCHEDULED,
):
    """
    활성화된 모든 ZIGZAG CATEGORY Target을
    개별 Celery Task로 dispatch.

    Celery Beat:
        기본 SCHEDULED

    웹 화면 수동 실행:
        MANUAL 전달
    """

    target_ids = list(
        CrawlTarget.objects.filter(
            source__code="ZIGZAG",
            target_type=CrawlTarget.TargetType.CATEGORY,
            is_active=True,
        ).values_list(
            "id",
            flat=True,
        )
    )

    task_ids = []

    for target_id in target_ids:
        task = run_zigzag_target.delay(
            target_id,
            trigger_type,
        )

        task_ids.append(str(task.id))

    return {
        "target_count": len(target_ids),
        "task_ids": task_ids,
    }
