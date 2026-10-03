from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import CrawlRun, CrawlTarget


logger = logging.getLogger(__name__)

DISPATCH_BATCH_SIZE = 2

LIVE_MAX_RETRIES = 2
LIVE_RETRY_COUNTDOWN = (300, 900)


def live_retry_countdown(retries: int) -> int:
    return LIVE_RETRY_COUNTDOWN[
        min(retries, len(LIVE_RETRY_COUNTDOWN) - 1)
    ]


@shared_task(
    name="core.celery_smoke_test",
)
def celery_smoke_test(
    message: str = "FEEDIT DATA CRAWLER",
) -> dict[str, Any]:
    return {
        "ok": True,
        "message": message,
    }


@shared_task(
    bind=True,
    name="core.run_live_target",
    max_retries=LIVE_MAX_RETRIES,
)
def run_live_target(
    self,
    target_id: int,
) -> dict[str, Any]:
    """
    CrawlTarget 하나를 실행한다.

    실제 수집/RAW 저장/RawDocument 생성/STEP01/STEP02는
    collection.common.runner.run_target()이 담당한다.

    Celery task의 책임:
    - DB connection 정리
    - runner 호출
    - 실패 재시도
    - 최종 실패 로그
    """
    close_old_connections()

    logger.info(
        "Celery crawl start. target_id=%s task_id=%s",
        target_id,
        self.request.id,
    )

    try:
        # The API imports this task module during Django admin startup. Load the
        # collector only when a crawl runs; the API image has no crawl deps.
        from collection.common.runner import run_target

        result = run_target(
            target_id=target_id,
        )

        logger.info(
            "Celery crawl success. target_id=%s task_id=%s",
            target_id,
            self.request.id,
        )

        return result

    except Exception as exc:
        retries = self.request.retries or 0
        will_retry = retries < LIVE_MAX_RETRIES

        logger.exception(
            "CrawlTarget failed. target_id=%s retry=%s/%s",
            target_id,
            retries,
            LIVE_MAX_RETRIES,
        )

        if will_retry:
            raise self.retry(
                exc=exc,
                countdown=live_retry_countdown(retries),
            )

        raise

    finally:
        close_old_connections()


def _enqueue_live_target(
    target_id: int,
) -> None:
    """
    transaction commit 이후 Celery broker에 등록한다.

    broker 등록에 실패하면 next_crawl_at을 현재 시각으로 복구하여
    다음 dispatcher에서 다시 잡힐 수 있게 한다.
    """
    try:
        run_live_target.delay(target_id)

    except Exception:
        logger.exception(
            "Failed to enqueue CrawlTarget. target_id=%s",
            target_id,
        )

        CrawlTarget.objects.filter(
            id=target_id,
            is_active=True,
        ).update(
            next_crawl_at=timezone.now(),
        )


@shared_task(
    name="core.dispatch_due_targets",
)
def dispatch_due_targets(
    batch_size: int = DISPATCH_BATCH_SIZE,
) -> dict[str, Any]:
    """
    실행 시각이 도래한 LIVE CrawlTarget을 Celery queue에 등록한다.

    조건:
    - is_active=True
    - collection_mode=LIVE
    - next_crawl_at IS NULL 또는 next_crawl_at <= now

    중복 dispatch 방지:
    - select_for_update(skip_locked=True)
    - RUNNING CrawlRun 확인
    - transaction.on_commit 이후 broker enqueue
    """
    close_old_connections()

    now = timezone.now()
    dispatched = 0
    target_ids: list[int] = []
    skipped_running: list[int] = []

    try:
        with transaction.atomic():
            targets = list(
                CrawlTarget.objects
                .select_for_update(skip_locked=True)
                .select_related("source")
                .filter(
                    is_active=True,
                    collection_mode=CrawlTarget.CollectionMode.LIVE,
                )
                .filter(
                    Q(next_crawl_at__isnull=True)
                    | Q(next_crawl_at__lte=now)
                )
                .order_by(
                    "priority",
                    "id",
                )[:batch_size]
            )

            for target in targets:
                is_running = (
                    CrawlRun.objects
                    .filter(
                        crawl_target=target,
                        status="RUNNING",
                    )
                    .exists()
                )

                if is_running:
                    skipped_running.append(target.id)
                    continue

                interval = (
                    target.interval_minutes
                    or target.source.crawl_interval_minutes
                    or 1440
                )

                target.next_crawl_at = (
                    now
                    + timedelta(minutes=interval)
                )
                target.save(
                    update_fields=["next_crawl_at"],
                )

                transaction.on_commit(
                    lambda target_id=target.id: (
                        _enqueue_live_target(target_id)
                    )
                )

                target_ids.append(target.id)
                dispatched += 1

        result = {
            "checked_at": now.isoformat(),
            "dispatched": dispatched,
            "target_ids": target_ids,
            "skipped_running": skipped_running,
        }

        logger.info(
            "Dispatcher finished. dispatched=%s skipped_running=%s",
            dispatched,
            len(skipped_running),
        )

        return result

    finally:
        close_old_connections()


@shared_task(
    name="core.collect_search_daily",
    soft_time_limit=60 * 110,
    time_limit=60 * 120,
)
def collect_search_daily():
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()

    call_command(
        "collect_search_signals",
        mode="daily",
        stdout=out,
    )

    return out.getvalue()[-2000:]


@shared_task(
    name="core.collect_search_weekly",
    soft_time_limit=60 * 110,
    time_limit=60 * 120,
)
def collect_search_weekly():
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()

    call_command(
        "collect_search_signals",
        mode="weekly",
        stdout=out,
    )

    return out.getvalue()[-2000:]


@shared_task(
    name="core.check_data_freshness",
)
def check_data_freshness():
    from apps.core.services.ops_alerts import (
        check_freshness_and_alert,
    )

    result = check_freshness_and_alert()

    logger.info(
        "Data freshness check: %s",
        result,
    )

    return result


@shared_task(
    name="core.rebuild_metrics",
    soft_time_limit=60 * 50,
    time_limit=60 * 60,
)
def rebuild_metrics(
    days: int = 35,
):
    from datetime import date, timedelta

    from analysis.text_signals.metrics import (
        rebuild_text_metrics,
    )

    days = max(
        1,
        min(int(days), 400),
    )

    until = date.today()

    result = rebuild_text_metrics(
        since=until - timedelta(days=days),
        until=until,
    )

    logger.info(
        "Metrics rebuild. days=%s result=%s",
        days,
        result,
    )

    return {
        "days": days,
        **(result or {}),
    }


@shared_task(
    name="core.collect_search_volume_monthly",
    soft_time_limit=60 * 110,
    time_limit=60 * 120,
)
def collect_search_volume_monthly():
    """네이버 검색광고 + Google Keyword Planner 월간 절대 검색량 적재."""
    from io import StringIO
    from django.core.management import call_command

    out = StringIO()
    call_command("collect_search_volume", source="all", stdout=out)
    return out.getvalue()[-4000:]
