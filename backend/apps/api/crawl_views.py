"""관리자용 수집 대상 / 수집 이력 API (DRF).

★ 2026-09-23 보안 — 운영 계정(is_staff 또는 is_superuser)만 쓸 수 있다.
  예전에는 permission_classes 가 없어서 DRF 기본값(AllowAny)이 적용됐다.
  `/api/` 공유 토큰만 있으면 로그인 없이 수집 대상을 만들고·고치고·지울 수
  있었고, 그 토큰은 백엔드 구간이 http 인 동안 평문으로 오간다.
  settings.REST_FRAMEWORK 의 기본 권한도 IsOperator 로 올려 두었지만,
  뷰에서도 명시한다 — 설정이 바뀌어도 여기는 열리지 않게.
"""
from rest_framework import generics
from .permissions import IsOperator

from apps.core.models.collection import CrawlRun, CrawlTarget

from .serializers import (
    CrawlRunSerializer,
    CrawlTargetSerializer,
)


class CrawlTargetListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsOperator]
    serializer_class = CrawlTargetSerializer

    def get_queryset(self):
        return (
            CrawlTarget.objects
            .select_related("source")
            .order_by("-created_at")
        )


class CrawlTargetDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOperator]
    queryset = CrawlTarget.objects.select_related("source")
    serializer_class = CrawlTargetSerializer


class CrawlRunListAPIView(generics.ListAPIView):
    permission_classes = [IsOperator]
    serializer_class = CrawlRunSerializer

    def get_queryset(self):
        return (
            CrawlRun.objects
            .select_related("source", "crawl_target")
            .order_by("-started_at", "-id")
        )


class CrawlRunDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [IsOperator]
    serializer_class = CrawlRunSerializer

    def get_queryset(self):
        return (
            CrawlRun.objects
            .select_related("source", "crawl_target")
        )