from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path(
        "",
        RedirectView.as_view(
            url="/admin-dashboard/",
            permanent=False,
        ),
        name="root_redirect",
    ),

    path("admin/", admin.site.urls),
    path("admin-dashboard/", include("apps.dashboard.urls")),
    path("api/", include("apps.api.urls")),
]