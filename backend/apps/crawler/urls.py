from django.urls import path

from . import views

app_name = "crawler"


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "monitoring/",
        views.monitoring,
        name="monitoring",
    ),
    path(
        "musinsa/",
        views.musinsa,
        name="musinsa",
    ),
    path(
        "musinsa/run-all/",
        views.run_all_targets,
        name="run_all_targets",
    ),
    path(
        "targets/<int:target_id>/run/",
        views.run_target,
        name="run_target",
    ),
    path(
        "musinsa/toggle-active/",
        views.toggle_active,
        name="toggle_active",
    ),
    path(
        "musinsa/update-cycle/",
        views.update_cycle,
        name="update_cycle",
    ),
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
    path(
        "jobs/<int:job_id>/",
        views.job,
        name="job",
    ),
]
