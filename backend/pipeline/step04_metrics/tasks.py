from __future__ import annotations

from datetime import date
from celery import shared_task
from .config import METRIC_VERSION
from .runner import run_daily_metrics


@shared_task(name="pipeline.step04_metrics.run_daily_metrics")
def run_daily_metrics_task(metric_date: str, metric_version: str = METRIC_VERSION):
    return run_daily_metrics(date.fromisoformat(metric_date), metric_version=metric_version)
