from django.urls import path
from . import views


app_name = "dashboard"


urlpatterns = [
    path("", views.home, name="home"),

    # 운영
    path("collection/", views.collection, name="collection"),

    # 데이터
    path("data/", views.data, name="data"),
    path("content/", views.content, name="content"),

    # 분석
    path("analysis/", views.analysis, name="analysis"),

    # 품질
    path("quality/", views.quality, name="quality"),

    # 운영 도구
    path("tools/import/", views.import_data, name="import"),
    path("tools/export/", views.export_data, name="export"),
    path("tools/probe/", views.probe, name="probe"),

    # 설정
    path("settings/api/", views.api_settings, name="api_settings"),
    path(
        "settings/collection/",
        views.collection_settings,
        name="collection_settings",
    ),
]