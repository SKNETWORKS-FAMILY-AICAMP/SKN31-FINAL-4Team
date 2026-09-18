from __future__ import annotations

import boto3
import json
import logging
import os
import time
import traceback
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    BooleanField,
    Case,
    Count,
    Max,
    Min,
    Q,
    Value,
    When,
)
from django.db.models.functions import TruncDate
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    Brand,
    BrandSource,
    Category,
    CategorySource,
    ContentItem,
    ContentProfile,
    ContentSnapshot,
    CrawlRun,
    CrawlTarget,
    DictionaryTerm,
    Product,
    ProductSource,
    ProductSourceSnapshot,
    RawDocument,
    ResaleSnapshot,
    Source,
    Style,
    TermAlias,
    TermAssocDaily,
    TermCandidate,
    TermMetricDaily,
    TextDocument,
)

from .helpers import (
    attach_latest_content_snapshot,
    attach_latest_product_snapshot,
    find_source,
    ordered_sources,
    qs_without,
    qs_without_page,
    source_label,
)


def _normalization_summary():
    """RawDocument 정규화 상태 요약.

    상태별로 따로 count()를 돌리면 같은 테이블을 다섯 번 훑는다.
    filter 조건부 집계로 한 번에 처리한다.
    """

    agg = RawDocument.objects.aggregate(
        total=Count("id"),
        success=Count("id", filter=Q(normalization_status="SUCCESS")),
        failed=Count("id", filter=Q(normalization_status="FAILED")),
        pending=Count("id", filter=Q(normalization_status="PENDING")),
        processing=Count("id", filter=Q(normalization_status="PROCESSING")),
    )

    return {
        **agg,
        "product_source": ProductSource.objects.count(),
        "product": Product.objects.count(),
        "content_item": ContentItem.objects.count(),
    }


@login_required(login_url="/admin-dashboard/login/")
def normalized_products(request):
    """정규화 성공 — 정규화를 통과해 적재된 결과물."""

    selected_source = request.GET.get("source", "").strip()
    selected_mapping = request.GET.get("mapping", "").strip()
    q = request.GET.get("q", "").strip()

    queryset = (
        ProductSource.objects
        .select_related(
            "source",
            "source_brand",
            "source_brand__brand",
            "source_category",
        )
        .order_by("-last_seen_at", "-id")
    )

    if selected_source:
        queryset = queryset.filter(
            source_id=selected_source
        )

    if selected_mapping:
        queryset = queryset.filter(
            mapping_status=selected_mapping
        )

    if q:
        queryset = queryset.filter(
            Q(source_name__icontains=q)
            | Q(normalized_name__icontains=q)
            | Q(source_product_id__icontains=q)
            | Q(style_no__icontains=q)
            | Q(source_brand__name__icontains=q)
        )

    paginator = Paginator(queryset, 30)
    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    # 플랫폼별 정규화 결과 수
    by_source = (
        ProductSource.objects
        .values("source__code")
        .annotate(n=Count("id"))
        .order_by("-n")
    )


    context = {
        "page_title": "정규화 성공",
        "page_description": (
            "정규화를 통과해 적재된 플랫폼 상품을 조회합니다."
        ),
        "summary": _normalization_summary(),
        "by_source": by_source,
        "sources": ordered_sources(),
        "mapping_choices": (
            ProductSource.MappingStatus.choices
        ),
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "filtered_count": paginator.count,
        "selected_source": selected_source,
        "selected_mapping": selected_mapping,
        "search_query": q,
    }

    return render(
        request,
        "dashboard/normalization/products.html",
        context,
    )

@login_required(login_url="/admin-dashboard/login/")
def normalization_failures(request):
    """정규화 실패 — 실패한 RawDocument와 오류 내용."""

    selected_source = request.GET.get("source", "").strip()
    selected_type = request.GET.get("document_type", "").strip()
    q = request.GET.get("q", "").strip()

    queryset = (
        RawDocument.objects
        .select_related("source", "crawl_run")
        .filter(normalization_status="FAILED")
        .order_by("-collected_at", "-id")
    )

    if selected_source:
        queryset = queryset.filter(
            source_id=selected_source
        )

    if selected_type:
        queryset = queryset.filter(
            document_type=selected_type
        )

    if q:
        queryset = queryset.filter(
            Q(external_id__icontains=q)
            | Q(s3_key__icontains=q)
            | Q(normalization_error__icontains=q)
            | Q(source_url__icontains=q)
        )

    paginator = Paginator(queryset, 30)
    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    rows = list(page_obj.object_list)

    for row in rows:
        row.platform_label = source_label(row.source)

    # 실패 사유 상위 (앞 80자로 묶음)
    reasons = {}
    for text in (
        RawDocument.objects
        .filter(normalization_status="FAILED")
        .values_list("normalization_error", flat=True)[:2000]
    ):
        key = (str(text or "").strip() or "(사유 없음)")[:80]
        reasons[key] = reasons.get(key, 0) + 1

    top_reasons = sorted(
        reasons.items(),
        key=lambda x: -x[1],
    )[:6]

    document_types = (
        RawDocument.objects
        .filter(normalization_status="FAILED")
        .values_list("document_type", flat=True)
        .distinct()
        .order_by("document_type")
    )

    context = {
        "page_title": "정규화 실패",
        "page_description": (
            "정규화에 실패한 원본 문서와 오류 내용을 검토합니다."
        ),
        "summary": _normalization_summary(),
        "top_reasons": top_reasons,
        "sources": ordered_sources(),
        "document_types": document_types,
        "page_obj": page_obj,
        "rows": rows,
        "filtered_count": paginator.count,
        "selected_source": selected_source,
        "selected_type": selected_type,
        "search_query": q,
    }

    return render(
        request,
        "dashboard/normalization/failures.html",
        context,
    )


def _platform_commerce_page(request, source, title, description, reset_url):
    """플랫폼 상품(ProductSource) 기반 정규화 페이지."""

    selected_mapping = request.GET.get("mapping", "").strip()
    selected_brand = request.GET.get("brand", "").strip()
    selected_order = request.GET.get("order", "recent").strip()
    q = request.GET.get("q", "").strip()

    base = ProductSource.objects.filter(source=source)

    queryset = (
        base
        .select_related(
            "source",
            "source_brand",
            "source_brand__brand",
            "source_category",
        )
    )

    if selected_order == "id_asc":
        queryset = queryset.order_by("id")
    elif selected_order == "id_desc":
        queryset = queryset.order_by("-id")
    else:
        queryset = queryset.order_by("-last_seen_at", "-id")

    if selected_mapping:
        queryset = queryset.filter(mapping_status=selected_mapping)

    if selected_brand == "1":
        queryset = queryset.filter(source_brand__brand__isnull=False)
    elif selected_brand == "0":
        queryset = queryset.filter(
            Q(source_brand__isnull=True)
            | Q(source_brand__brand__isnull=True)
        )

    if q:
        queryset = queryset.filter(
            Q(source_name__icontains=q)
            | Q(normalized_name__icontains=q)
            | Q(source_product_id__icontains=q)
            | Q(style_no__icontains=q)
            | Q(source_brand__name__icontains=q)
        )

    paginator = Paginator(queryset, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = list(page_obj.object_list)
    attach_latest_product_snapshot(rows)

    docs = RawDocument.objects.filter(source=source)
    total_rows = base.count()

    cards = [
        {
            "label": "원본 문서",
            "value": docs.count(),
            "caption": "RawDocument",
            "tone": "",
        },
        {
            "label": "정규화 성공",
            "value": docs.filter(normalization_status="SUCCESS").count(),
            "caption": "SUCCESS",
            "tone": "ok",
        },
        {
            "label": "정규화 실패",
            "value": docs.filter(normalization_status="FAILED").count(),
            "caption": "FAILED",
            "tone": "bad",
        },
        {
            "label": "플랫폼 상품",
            "value": total_rows,
            "caption": "ProductSource",
            "tone": "",
        },
        {
            "label": "브랜드 연결",
            "value": base.filter(source_brand__brand__isnull=False).count(),
            "caption": "표준 브랜드 매핑됨",
            "tone": "",
        },
        {
            "label": "표준 상품 연결",
            "value": base.filter(product__isnull=False).count(),
            "caption": "Product 승격",
            "tone": "",
        },
    ]

    context = {
        "page_title": title,
        "page_description": description,
        "mode": "commerce",
        "cards": cards,
        "rows": rows,
        "page_obj": page_obj,
        "filtered_count": paginator.count,
        "total_rows": total_rows,
        "blank_reason": (
            "Source는 등록돼 있지만 이 플랫폼의 상품이 아직 한 건도 "
            "적재되지 않았습니다. 수집과 정규화를 먼저 실행해야 합니다."
        ),
        "mapping_choices": ProductSource.MappingStatus.choices,
        "selected_mapping": selected_mapping,
        "selected_brand": selected_brand,
        "selected_order": selected_order,
        "search_query": q,
        "reset_url": reset_url,
        "qs": qs_without_page(request),
        "qs_sort": qs_without(request, "order"),
    }

    return render(
        request,
        "dashboard/normalization/platform.html",
        context,
    )


def _platform_content_page(request, source, title, description, reset_url):
    """콘텐츠(ContentItem) 기반 정규화 페이지."""

    selected_content_type = request.GET.get("content_type", "").strip()
    selected_order = request.GET.get("order", "recent").strip()
    q = request.GET.get("q", "").strip()

    base = ContentItem.objects.filter(source=source)

    queryset = (
        base
        .select_related("source", "profile")
    )

    if selected_order == "id_asc":
        queryset = queryset.order_by("id")
    elif selected_order == "id_desc":
        queryset = queryset.order_by("-id")
    elif selected_order in ("views_desc", "views_asc"):
        queryset = queryset.annotate(
            v=Max("snapshots__view_count")
        ).order_by(
            "v" if selected_order == "views_asc" else "-v",
            "-id",
        )
    else:
        queryset = queryset.order_by("-published_at", "-id")

    if selected_content_type:
        queryset = queryset.filter(content_type=selected_content_type)

    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(external_content_id__icontains=q)
            | Q(profile__name__icontains=q)
        )

    paginator = Paginator(queryset, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = list(page_obj.object_list)
    attach_latest_content_snapshot(rows)

    docs = RawDocument.objects.filter(source=source)
    total_rows = base.count()

    cards = [
        {
            "label": "원본 문서",
            "value": docs.count(),
            "caption": "RawDocument",
            "tone": "",
        },
        {
            "label": "정규화 성공",
            "value": docs.filter(normalization_status="SUCCESS").count(),
            "caption": "SUCCESS",
            "tone": "ok",
        },
        {
            "label": "콘텐츠",
            "value": total_rows,
            "caption": "ContentItem",
            "tone": "",
        },
        {
            "label": "채널/프로필",
            "value": ContentProfile.objects.filter(source=source).count(),
            "caption": "ContentProfile",
            "tone": "",
        },
        {
            "label": "스냅샷",
            "value": ContentSnapshot.objects.filter(
                content_item__source=source
            ).count(),
            "caption": "ContentSnapshot",
            "tone": "",
        },
        {
            "label": "분석 문서",
            "value": TextDocument.objects.filter(source=source).count(),
            "caption": "TextDocument",
            "tone": "",
        },
    ]

    content_types = (
        base
        .exclude(content_type="")
        .values_list("content_type", flat=True)
        .distinct()
        .order_by("content_type")
    )

    context = {
        "page_title": title,
        "page_description": description,
        "mode": "content",
        "cards": cards,
        "rows": rows,
        "page_obj": page_obj,
        "filtered_count": paginator.count,
        "total_rows": total_rows,
        "blank_reason": (
            "Source는 등록돼 있지만 이 플랫폼의 콘텐츠가 아직 "
            "적재되지 않았습니다."
        ),
        "content_types": content_types,
        "selected_content_type": selected_content_type,
        "selected_order": selected_order,
        "search_query": q,
        "reset_url": reset_url,
        "qs": qs_without_page(request),
        "qs_sort": qs_without(request, "order"),
    }

    return render(
        request,
        "dashboard/normalization/platform.html",
        context,
    )


def _platform_page(request, codes, title, description, url_name, mode="commerce"):
    """플랫폼별 정규화 페이지 공통 진입점."""

    source = find_source(*codes)
    reset_url = reverse("dashboard:" + url_name)

    if source is None:
        return render(
            request,
            "dashboard/normalization/platform.html",
            {
                "page_title": title,
                "page_description": description,
                "mode": "none",
                "blank_reason": (
                    "이 플랫폼의 Source가 아직 등록되지 않았습니다. "
                    "수집 대상을 등록하고 크롤링을 실행하면 여기에 "
                    "정규화 결과가 표시됩니다."
                ),
            },
        )

    if mode == "auto":
        has_content = ContentItem.objects.filter(source=source).exists()
        has_product = ProductSource.objects.filter(source=source).exists()
        mode = "content" if (has_content and not has_product) else "commerce"

    if mode == "content":
        return _platform_content_page(
            request, source, title, description, reset_url
        )

    return _platform_commerce_page(
        request, source, title, description, reset_url
    )


@login_required(login_url="/admin-dashboard/login/")
def normalized_musinsa(request):
    return _platform_page(
        request,
        ["musinsa"],
        "무신사",
        "무신사에서 수집·정규화된 상품을 조회합니다.",
        "normalized_musinsa",
    )


@login_required(login_url="/admin-dashboard/login/")
def normalized_zigzag(request):
    return _platform_page(
        request,
        ["zigzag"],
        "지그재그",
        "지그재그에서 수집·정규화된 상품을 조회합니다.",
        "normalized_zigzag",
    )


@login_required(login_url="/admin-dashboard/login/")
def normalized_ably(request):
    return _platform_page(
        request,
        ["ably"],
        "에이블리",
        "에이블리에서 수집·정규화된 상품을 조회합니다.",
        "normalized_ably",
    )


@login_required(login_url="/admin-dashboard/login/")
def normalized_kream(request):
    return _platform_page(
        request,
        ["kream"],
        "크림",
        "크림에서 수집·정규화된 리셀 상품을 조회합니다.",
        "normalized_kream",
    )


@login_required(login_url="/admin-dashboard/login/")
def normalized_musinsa_used(request):
    return _platform_page(
        request,
        ["musinsa_used", "musinsa-used"],
        "무신사 USED",
        "무신사 USED에서 수집·정규화된 중고 상품을 조회합니다.",
        "normalized_musinsa_used",
    )


@login_required(login_url="/admin-dashboard/login/")
def normalized_youtube(request):
    return _platform_page(
        request,
        ["YOUTUBE", "youtube"],
        "유튜브",
        "유튜브에서 수집·정규화된 콘텐츠를 조회합니다.",
        "normalized_youtube",
        mode="content",
    )


@login_required(login_url="/admin-dashboard/login/")
def normalized_naver(request):
    return _platform_page(
        request,
        ["naver"],
        "네이버",
        "네이버에서 수집·정규화된 데이터를 조회합니다.",
        "normalized_naver",
        mode="auto",
    )
