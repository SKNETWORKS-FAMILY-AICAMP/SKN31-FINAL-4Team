from django.urls import path
from . import dictionary_views, notice_views, operations_views, service_views, views


app_name = "dashboard"


urlpatterns = [
    path("login/", views.dashboard_login, name="login"),
    path("logout/", views.dashboard_logout, name="logout"),
    path("otp/setup/", views.dashboard_otp_setup, name="otp_setup"),
    path("otp/verify/", views.dashboard_otp_verify, name="otp_verify"),
    path("session/ping/", views.dashboard_session_ping, name="session_ping"),

    path("", views.dashboard, name="dashboard"),

    path("collection/targets/", views.collection_targets, name="collection_targets"),
    path("collection/targets/create/", views.collection_targets_create, name="collection_targets_create"),
    path("collection/targets/update/<int:target_id>/", views.collection_targets_update, name="collection_targets_update"),
    path("collection/targets/delete/", views.collection_targets_delete, name="collection_targets_delete"),
    path("collection/runs/", views.collection_runs, name="collection_runs"),
    path("collection/raw-documents/", views.raw_documents, name="raw_documents"),
    path("collection/raw-documents/<int:pk>/preview/", views.raw_document_preview, name="raw_document_preview"),

    path(
        "collection/raw-documents/<int:pk>/json/",
        views.raw_document_json,
        name="raw_document_json",
    ),
    path("collection/raw-documents/<int:pk>/download/", views.raw_document_download, name="raw_document_download"),

    path("normalization/products/", views.normalized_products, name="normalized_products"),
    path("normalization/failures/", views.normalization_failures, name="normalization_failures"),
    path("normalization/quality/", views.data_quality, name="data_quality"),
    path("normalization/pipeline/", operations_views.pipeline_overview, name="pipeline_overview"),

    # 서비스 운영 — 홈페이지 피드백 · 살!말? 신고 처리 (2026-09-27)
    path("service/feedback/", service_views.feedback_list, name="feedback_list"),
    path("service/feedback/<int:pk>/", service_views.feedback_update, name="feedback_update"),
    path("service/reports/", service_views.report_list, name="report_list"),
    path("service/reports/<int:pk>/", service_views.report_update, name="report_update"),
    path("service/users/", operations_views.service_users, name="service_users"),
    path("service/events/", operations_views.service_events, name="service_events"),
    path("service/votes/", operations_views.service_votes, name="service_votes"),
    path("service/comments/", operations_views.service_comments, name="service_comments"),
    # 알림 보내기 · 실시간 공지 (2026-10-02)
    path("service/notices/", notice_views.notices, name="service_notices"),
    path("service/notices/send/", notice_views.notice_send, name="notice_send"),
    path("service/notices/ticker/", notice_views.ticker_create, name="ticker_create"),
    path("service/notices/ticker/<int:pk>/end/", notice_views.ticker_end, name="ticker_end"),

    path("database/", operations_views.database_overview, name="database_overview"),
    path("database/query/", operations_views.database_query, name="database_query"),

    path("dictionary/", dictionary_views.dictionary_overview, name="dictionary_overview"),
    path("dictionary/terms/", dictionary_views.dictionary_terms, name="dictionary_terms"),
    path("dictionary/terms/<int:pk>/", dictionary_views.dictionary_term_detail, name="dictionary_term_detail"),
    path("dictionary/candidates/", dictionary_views.dictionary_candidates, name="dictionary_candidates"),
    path("dictionary/candidates/<int:pk>/", dictionary_views.dictionary_candidate_detail, name="dictionary_candidate_detail"),
    path("dictionary/candidates/<int:pk>/review/", dictionary_views.dictionary_candidate_review, name="dictionary_candidate_review"),
    path("dictionary/quality/", dictionary_views.dictionary_quality, name="dictionary_quality"),
    path(
        "dictionary/brands/",
        dictionary_views.brand_sources,
        name="brand_sources",
    ),
    path("dictionary/brands/search/", dictionary_views.brand_search, name="brand_search"),

    path(
        "dictionary/brands/<int:source_id>/map/",
        views.map_brand_source,
        name="map_brand_source",
    ),

    path(
        "dictionary/brands/<int:source_id>/create/",
        views.create_brand_from_source,
        name="create_brand_from_source",
    ),

    path(
        "dictionary/brands/<int:source_id>/unmap/",
        views.unmap_brand_source,
        name="unmap_brand_source",
    ),

    path(
        "dictionary/brands/<int:source_id>/exclude/",
        views.exclude_brand_source,
        name="exclude_brand_source",
    ),
    path("trend/metrics/", views.trend_metrics, name="trend_metrics"),
    path("trend/metrics/rebuild/", views.rebuild_metrics, name="rebuild_metrics"),

    path("data/products/", views.products, name="products"),
    path("data/brands/", views.brands, name="brands"),
    path("data/categories/", views.categories, name="categories"),

    path("jobs/", views.jobs, name="jobs"),
    path("system/", views.system_status, name="system_status"),

    # ---------- 수집 ----------
    path("collection/platform-status/", views.platform_status, name="platform_status"),
    path("collection/run/", views.run_crawl, name="run_crawl"),
    path("collection/rules/", views.crawl_rules, name="crawl_rules"),
    path("collection/robots/", views.robots_check, name="robots_check"),

    # ---------- 정규화 데이터 ----------
    path("normalized/musinsa/", views.normalized_musinsa, name="normalized_musinsa"),
    path("normalized/zigzag/", views.normalized_zigzag, name="normalized_zigzag"),
    path("normalized/ably/", views.normalized_ably, name="normalized_ably"),
    path("normalized/kream/", views.normalized_kream, name="normalized_kream"),
    path("normalized/musinsa-used/", views.normalized_musinsa_used, name="normalized_musinsa_used"),
    path("normalized/youtube/", views.normalized_youtube, name="normalized_youtube"),
    path("normalized/naver/", views.normalized_naver, name="normalized_naver"),

    # ---------- 분석 텍스트 ----------
    path("text/youtube/", views.text_youtube, name="text_youtube"),
    path("text/musinsa/", views.text_musinsa, name="text_musinsa"),
    path("text/zigzag/", views.text_zigzag, name="text_zigzag"),
    path("text/ably/", views.text_ably, name="text_ably"),
    path("text/naver/", views.text_naver, name="text_naver"),

    # ---------- 데이터 분석 ----------
    path("analytics/term-metrics/", views.term_metrics, name="term_metrics"),
    path("analytics/product-metrics/", views.product_metrics, name="product_metrics"),
    path("analytics/product-snapshot/", views.product_snapshot, name="product_snapshot"),

    # ---------- 시스템 ----------
    path("system/api/", views.system_api, name="system_api"),
    path("system/aws/", views.system_aws, name="system_aws"),
    path("system/celery/", views.system_celery, name="system_celery"),
]
