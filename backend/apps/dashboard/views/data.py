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
from django.db.models import Q, Count, F, Prefetch
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


@login_required(login_url="/admin-dashboard/login/")
def products(request):
    """FEEDIT 표준 상품."""

    q = request.GET.get("q", "").strip()

    queryset = (
        Product.objects
        .select_related("brand", "category")
        .defer("item_term")
        .annotate(source_n=Count("sources"))
        .order_by("-source_n", "canonical_name")
    )

    if q:
        queryset = queryset.filter(
            Q(canonical_name__icontains=q)
            | Q(normalized_name__icontains=q)
            | Q(brand__name__icontains=q)
        )

    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_title": "상품",
        "page_description": (
            "여러 플랫폼 상품을 하나로 묶은 표준 상품입니다."
        ),
        "summary": {
            "total": Product.objects.count(),
            "product_source": ProductSource.objects.count(),
            "mapped": ProductSource.objects.filter(
                product__isnull=False
            ).count(),
            "unmapped": ProductSource.objects.filter(
                product__isnull=True
            ).count(),
        },
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "filtered_count": paginator.count,
        "search_query": q,
    }

    return render(
        request,
        "dashboard/data/products.html",
        context,
    )



@login_required(login_url="/admin-dashboard/login/")
def brands(request):
    """FEEDIT 표준 브랜드."""

    selected_status = request.GET.get("status", "").strip()
    selected_verified = request.GET.get("verified", "").strip()
    q = request.GET.get("q", "").strip()

    linked_sources_qs = (
        BrandSource.objects
        .select_related("source")
        .order_by(
            "source__code",
            "name",
        )
    )

    queryset = (
        Brand.objects
        .select_related("category")
        .prefetch_related(
            Prefetch(
                "brand_sources",
                queryset=linked_sources_qs,
                to_attr="linked_sources",
            )
        )
        .order_by(
            "-source_count",
            "name",
        )
    )

    if selected_status:
        queryset = queryset.filter(
            status=selected_status
        )

    if selected_verified == "1":
        queryset = queryset.filter(
            is_verified=True
        )

    elif selected_verified == "0":
        queryset = queryset.filter(
            is_verified=False
        )

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(brand_code__icontains=q)
            | Q(
                brand_sources__name__icontains=q
            )
            | Q(
                brand_sources__source_brand_id__icontains=q
            )
            | Q(
                brand_sources__source__code__icontains=q
            )
        ).distinct()

    paginator = Paginator(
        queryset,
        40,
    )

    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    brand_agg = Brand.objects.aggregate(
        total=Count("id"),
        active=Count(
            "id",
            filter=Q(status="ACTIVE"),
        ),
        verified=Count(
            "id",
            filter=Q(is_verified=True),
        ),
        linked=Count(
            "id",
            filter=Q(source_count__gt=0),
        ),
    )

    context = {
        "page_title": "브랜드",
        "page_description":
            "FEEDIT 표준 브랜드와 연결된 플랫폼 브랜드를 조회합니다.",

        "summary": {
            **brand_agg,
            "brand_source":
                BrandSource.objects.count(),
        },

        "status_choices":
            Brand.Status.choices,

        "page_obj":
            page_obj,

        "rows":
            page_obj.object_list,

        "filtered_count":
            paginator.count,

        "selected_status":
            selected_status,

        "selected_verified":
            selected_verified,

        "search_query":
            q,
    }

    return render(
        request,
        "dashboard/data/brands.html",
        context,
    )


@login_required(login_url="/admin-dashboard/login/")
def categories(request):
    """FEEDIT 표준 카테고리."""

    selected_type = request.GET.get("category_type", "").strip()
    selected_level = request.GET.get("level", "").strip()
    q = request.GET.get("q", "").strip()

    queryset = (
        Category.objects
        .select_related("parent")
        .order_by("category_type", "level", "sort_order", "code")
    )

    if selected_type:
        queryset = queryset.filter(category_type=selected_type)

    if selected_level:
        queryset = queryset.filter(level=selected_level)

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(code__icontains=q)
        )

    paginator = Paginator(queryset, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    all_categories = Category.objects.all()
    category_agg = all_categories.aggregate(
        total=Count("id"),
        product=Count("id", filter=Q(category_type="PRODUCT")),
        brand=Count("id", filter=Q(category_type="BRAND")),
    )

    context = {
        "page_title": "카테고리",
        "page_description": "FEEDIT 표준 카테고리 체계를 조회합니다.",
        "summary": {
            **category_agg,
            "category_source": CategorySource.objects.count(),
        },
        "type_choices": Category.CategoryType.choices,
        "levels": (
            all_categories
            .values_list("level", flat=True)
            .distinct()
            .order_by("level")
        ),
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "filtered_count": paginator.count,
        "selected_type": selected_type,
        "selected_level": selected_level,
        "search_query": q,
    }

    return render(
        request,
        "dashboard/data/categories.html",
        context,
    )
