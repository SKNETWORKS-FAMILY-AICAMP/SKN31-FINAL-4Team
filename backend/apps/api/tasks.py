"""알림 배치 — Celery.

  app.notify_daily    매일 10:00 KST   찜한 상품 가격 하락 · 용어 사전 등재
  app.notify_weekly   일요일 18:00 KST 주간 트렌드 리포트

시각은 config/celery.py 의 beat 스케줄에 있다 (app.conf.timezone = Asia/Seoul).

★ 워커·beat 없이 손으로 돌리려면:
    python manage.py notify_batch --daily
    python manage.py notify_batch --weekly
"""
from __future__ import annotations

import logging

from celery import shared_task

from . import notification_service

logger = logging.getLogger(__name__)


@shared_task(name="app.notify_daily")
def notify_daily():
    made = notification_service.run_daily()
    logger.info("알림 일 배치 — 가격 하락 %s건 · 용어 등재 %s건",
                made["price_drop"], made["term_added"])
    return made


@shared_task(name="app.notify_weekly")
def notify_weekly():
    made = notification_service.run_weekly()
    logger.info("알림 주 배치 — 주간 리포트 %s건", made["weekly_report"])
    return made
