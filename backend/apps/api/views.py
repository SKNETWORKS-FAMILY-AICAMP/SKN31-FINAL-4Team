from django.shortcuts import render

# Create your views here.
from rest_framework import generics

from apps.core.models.collection import CrawlRun, CrawlTarget

from .serializers import (
    CrawlRunSerializer,
    CrawlTargetSerializer,
)


class CrawlTargetListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CrawlTargetSerializer

    def get_queryset(self):
        return (
            CrawlTarget.objects
            .select_related("source")
            .order_by("-created_at")
        )


class CrawlTargetDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CrawlTarget.objects.select_related("source")
    serializer_class = CrawlTargetSerializer


class CrawlRunListAPIView(generics.ListAPIView):
    serializer_class = CrawlRunSerializer

    def get_queryset(self):
        return (
            CrawlRun.objects
            .select_related("source", "crawl_target")
            .order_by("-started_at", "-id")
        )


class CrawlRunDetailAPIView(generics.RetrieveAPIView):
    serializer_class = CrawlRunSerializer

    def get_queryset(self):
        return (
            CrawlRun.objects
            .select_related("source", "crawl_target")
        )