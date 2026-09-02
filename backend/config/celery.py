from __future__ import annotations

import os

from celery import Celery


os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)


app = Celery(
    "feedit"
)


app.config_from_object(
    "django.conf:settings",
    namespace="CELERY",
)


app.autodiscover_tasks()


# ============================================================
# QUEUE / ROUTING
# ============================================================

app.conf.task_default_queue = (
    "default"
)

app.conf.task_routes = {
    "core.run_live_target": {
        "queue": "crawl_live",
    },
    "core.dispatch_due_targets": {
        "queue": "crawl_live",
    },
}


app.conf.beat_schedule = {
    "dispatch-due-crawl-targets": {
        "task": "core.dispatch_due_targets",
        "schedule": 60.0,
    },
}

# ============================================================
# SERIALIZER
# ============================================================

app.conf.task_serializer = (
    "json"
)

app.conf.result_serializer = (
    "json"
)

app.conf.accept_content = [
    "json",
]


# ============================================================
# TIMEZONE
# ============================================================

app.conf.timezone = (
    "Asia/Seoul"
)

app.conf.enable_utc = True


# ============================================================
# DEBUG
# ============================================================

@app.task(bind=True)
def debug_task(self):
    print(
        f"Request: {self.request!r}"
    )