from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin-dashboard/", include("apps.dashboard.urls")),
    path("api/", include("apps.api.urls")),
]