from django.urls import path

from . import views

app_name = "crawler"


urlpatterns = [
    # ============================================================
    # DASHBOARD
    # ============================================================
    path(
        "",
        views.dashboard,
        name="dashboard",
    ),
    path(
        "monitoring/",
        views.monitoring,
        name="monitoring",
    ),
    # ============================================================
    # MUSINSA
    # ============================================================
    path(
        "musinsa/",
        views.musinsa,
        name="musinsa",
    ),
    # MUSINSA 전체 Target 실행
    path(
        "musinsa/run-all/",
        views.run_all_targets,
        name="run_all_targets",
    ),
    # MUSINSA 개별 Target 실행
    path(
        "musinsa/targets/<int:target_id>/run/",
        views.run_target,
        name="run_target",
    ),
    # ============================================================
    # ZIGZAG
    # ============================================================
    path(
        "zigzag/",
        views.zigzag,
        name="zigzag",
    ),
    path(
        "zigzag/run-all/",
        views.zigzag_run_all_targets,
        name="zigzag_run_all_targets",
    ),
    path(
        "zigzag/targets/<int:target_id>/run/",
        views.zigzag_run_target,
        name="zigzag_run_target",
    ),
    # ============================================================
    # YOUTUBE
    # ============================================================
    path(
        "youtube/",
        views.youtube,
        name="youtube",
    ),
    path(
        "youtube/<int:creator_id>/run/",
        views.run_youtube_pipeline,
        name="run_youtube_pipeline",
    ),
    # ============================================================
    # BACKFILL
    # ============================================================
    path(
        "backfill/",
        views.backfill,
        name="backfill",
    ),
    path(
        "backfill/create/",
        views.backfill_create,
        name="backfill_create",
    ),
    path(
        "backfill/<int:batch_id>/run/",
        views.backfill_run,
        name="backfill_run",
    ),
    # ============================================================
    # JOB
    # ============================================================
    path(
        "jobs/<int:job_id>/",
        views.job,
        name="job",
    ),
]
