from __future__ import annotations

import os

from celery import Celery


os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

app = Celery("feedit")

app.config_from_object(
    "django.conf:settings",
    namespace="CELERY",
)

app.autodiscover_tasks()

# Existing service queues are preserved. The four current commerce collectors
# enter through core.run_live_target -> collection.common.runner.run_target.
app.conf.task_default_queue = "default"
app.conf.task_routes = {
    "core.run_live_target": {"queue": "crawl_live"},
    "core.dispatch_due_targets": {"queue": "crawl_live"},
    "core.collect_search_daily": {"queue": "analysis"},
    "core.collect_search_weekly": {"queue": "analysis"},
    "core.collect_search_volume_monthly": {"queue": "analysis"},
    "core.rebuild_metrics": {"queue": "analysis"},
}

# Do not redefine beat_schedule here. settings.CELERY_BEAT_SCHEDULE is the
# single source of truth, so config_from_object cannot be silently overwritten.
if os.getenv("CELERY_CRAWL_DISPATCH", "1") == "0":
    schedule = dict(app.conf.beat_schedule or {})
    schedule.pop("dispatch-due-crawl-targets", None)
    app.conf.beat_schedule = schedule


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
