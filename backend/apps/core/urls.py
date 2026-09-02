from django.contrib import admin
from django.urls import path

from apps.core.views.normalization import (
    normalization_dashboard,
    normalize_brands,
)


urlpatterns = [
    path(
        "admin/normalization/",
        normalization_dashboard,
        name="normalization_dashboard",
    ),

    path(
        "admin/normalization/<int:run_id>/brands/",
        normalize_brands,
        name="normalize_brands",
    ),

    path(
        "admin/",
        admin.site.urls,
    ),
]