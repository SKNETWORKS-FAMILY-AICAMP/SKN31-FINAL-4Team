from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("admin/", admin.site.urls),
    path("dashboard/", include("apps.dashboard.urls")),
]