from django.urls import path
from . import views


app_name = "dashboard"


urlpatterns = [
    path("login/", views.dashboard_login, name="login"),
    path("logout/", views.dashboard_logout, name="logout"),

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

    path("dictionary/terms/", views.dictionary_terms, name="dictionary_terms"),
    path("dictionary/candidates/", views.dictionary_candidates, name="dictionary_candidates"),
    path("dictionary/candidates/<int:pk>/", views.dictionary_candidate_detail, name="dictionary_candidate_detail"),
        path(
        "dictionary/brands/",
        views.brand_sources,
        name="brand_sources",
    ),

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

    # ---------- 데이터 분석 ----------
    path("analytics/term-metrics/", views.term_metrics, name="term_metrics"),
    path("analytics/product-metrics/", views.product_metrics, name="product_metrics"),
    path("analytics/product-snapshot/", views.product_snapshot, name="product_snapshot"),

    # ---------- 시스템 ----------
    path("system/api/", views.system_api, name="system_api"),
    path("system/aws/", views.system_aws, name="system_aws"),
    path("system/celery/", views.system_celery, name="system_celery"),
]