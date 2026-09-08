from django.urls import path
from . import views


app_name = "dashboard"


urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    # =========================================================
    # COLLECTION
    # =========================================================
    path(
        "collection/targets/",
        views.collection_targets,
        name="collection_targets",
    ),

    path(
        "collection/runs/",
        views.collection_runs,
        name="collection_runs",
    ),

    path(
        "collection/raw-documents/",
        views.raw_documents,
        name="raw_documents",
    ),

    path(
        "collection/raw-documents/<int:pk>/json/",
        views.raw_document_json,
        name="raw_document_json",
    ),

    # =========================================================
    # NORMALIZATION
    # =========================================================
    path(
        "normalization/products/",
        views.normalized_products,
        name="normalized_products",
    ),

    path(
        "normalization/failures/",
        views.normalization_failures,
        name="normalization_failures",
    ),

    # =========================================================
    # DICTIONARY
    # =========================================================
    path(
        "dictionary/terms/",
        views.dictionary_terms,
        name="dictionary_terms",
    ),

    path(
        "dictionary/candidates/",
        views.dictionary_candidates,
        name="dictionary_candidates",
    ),

    path(
        "dictionary/candidates/<int:pk>/",
        views.dictionary_candidate_detail,
        name="dictionary_candidate_detail",
    ),

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

    # =========================================================
    # TREND
    # =========================================================
    path(
        "trend/metrics/",
        views.trend_metrics,
        name="trend_metrics",
    ),

    # =========================================================
    # DATA
    # =========================================================
    path(
        "data/products/",
        views.products,
        name="products",
    ),

    path(
        "data/brands/",
        views.brands,
        name="brands",
    ),

    path(
        "data/categories/",
        views.categories,
        name="categories",
    ),

    # =========================================================
    # SYSTEM
    # =========================================================
    path(
        "jobs/",
        views.jobs,
        name="jobs",
    ),

    path(
        "system/",
        views.system_status,
        name="system_status",
    ),
]