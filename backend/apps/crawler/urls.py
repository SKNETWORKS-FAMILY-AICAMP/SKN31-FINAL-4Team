from django.urls import path
from . import views

app_name = "crawler"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("monitoring/", views.monitoring, name="monitoring"),
    path("musinsa/", views.musinsa, name="musinsa"),
    path("youtube/", views.youtube, name="youtube"),
]
