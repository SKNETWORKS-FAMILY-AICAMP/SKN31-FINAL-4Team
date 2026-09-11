from django.urls import path

from .views import (
    CrawlRunDetailAPIView,
    CrawlRunListAPIView,
    CrawlTargetDetailAPIView,
    CrawlTargetListCreateAPIView,
)

urlpatterns = [
    # Crawl Targets
    path(
        "crawl-targets/",
        CrawlTargetListCreateAPIView.as_view(),
        name="crawl-target-list-create",
    ),
    path(
        "crawl-targets/<int:pk>/",
        CrawlTargetDetailAPIView.as_view(),
        name="crawl-target-detail",
    ),

    # Crawl Runs
    path(
        "crawl-runs/",
        CrawlRunListAPIView.as_view(),
        name="crawl-run-list",
    ),
    path(
        "crawl-runs/<int:pk>/",
        CrawlRunDetailAPIView.as_view(),
        name="crawl-run-detail",
    ),
]