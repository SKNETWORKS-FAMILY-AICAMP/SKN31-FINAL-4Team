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

from django.db.models import Count, Prefetch, Q


def _sync_brand_source_count(brand):
    """Brand.source_count를 실제 연결된 플랫폼 수 기준으로 동기화."""
    if brand is None:
        return

    count = (
        BrandSource.objects
        .filter(brand=brand)
        .values("source_id")
        .distinct()
        .count()
    )

    if brand.source_count != count:
        brand.source_count = count
        brand.save(
            update_fields=[
                "source_count",
                "updated_at",
            ]
        )


def _parse_list_input(value):
    """쉼표 입력 -> JSONField용 list[str]"""
    if value is None:
        return None

    if isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_values = str(value).split(",")

    result = []
    seen = set()

    for item in raw_values:
        item = str(item).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)

    return result or None


def _brand_categories():
    return (
        Category.objects
        .filter(
            category_type=Category.CategoryType.BRAND,
            status=Category.Status.ACTIVE,
        )
        .order_by("sort_order", "name")
    )


@login_required(login_url="/admin-dashboard/login/")
def brand_sources(
    request: HttpRequest,
):
    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------
    status = request.GET.get("status", "unmapped")
    source_id = request.GET.get("source", "")
    q = request.GET.get("q", "").strip()

    queryset = (
        BrandSource.objects
        .select_related("source", "brand")
        .prefetch_related("styles")
        .all()
    )

    if status == "unmapped":
        queryset = queryset.filter(
            brand__isnull=True,
            mapping_status=BrandSource.MappingStatus.UNMAPPED,
        )
    elif status == "mapped":
        queryset = queryset.filter(brand__isnull=False)
    elif status == "excluded":
        queryset = queryset.filter(
            mapping_status=BrandSource.MappingStatus.EXCLUDED
        )

    if source_id:
        queryset = queryset.filter(source_id=source_id)

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(source_brand_id__icontains=q)
            | Q(brand__name__icontains=q)
            | Q(brand__english_name__icontains=q)
            | Q(brand__brand_code__icontains=q)
        )

    queryset = queryset.order_by(
        "-detected_count",
        "-last_seen_at",
    )

    # UI용 안전한 문자열 속성 준비
    #
    # styles 는 prefetch_related 로 이미 가져와 두었다.
    # .values_list() 는 그 캐시를 쓰지 않고 행마다 DB에 다시 물어보므로
    # 500행이면 조회가 500번 더 나간다. RDS가 SSM 터널 뒤에 있어
    # 이것만으로 화면이 수십 초 느려졌다. (2026-09-09 수정)
    rows = list(queryset[:500])
    for item in rows:
        item.ui_target_gender = ", ".join(
            str(v) for v in (item.target_gender or [])
        )
        item.ui_target_age = ", ".join(
            str(v) for v in (item.target_age or [])
        )

        prefetched_styles = list(item.styles.all())

        item.ui_style_ids = ",".join(
            str(style.term_id) for style in prefetched_styles
        )
        item.ui_style_names = ", ".join(
            str(style) for style in prefetched_styles
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------
    all_sources = BrandSource.objects.all()

    summary = {
        "total": all_sources.count(),
        "unmapped": all_sources.filter(
            brand__isnull=True,
            mapping_status=BrandSource.MappingStatus.UNMAPPED,
        ).count(),
        "review": all_sources.filter(
            brand__isnull=True,
            mapping_status=BrandSource.MappingStatus.UNMAPPED,
            detected_count__gte=5,
        ).count(),
        "priority": all_sources.filter(
            brand__isnull=True,
            mapping_status=BrandSource.MappingStatus.UNMAPPED,
            detected_count__gte=20,
        ).count(),
        "mapped": all_sources.filter(
            brand__isnull=False,
        ).count(),
        "excluded": all_sources.filter(
            mapping_status=BrandSource.MappingStatus.EXCLUDED,
        ).count(),
    }

    # 2,949개를 통째로 가져오면 description 등까지 실려 와 1초 이상 걸린다.
    # 선택 목록에 필요한 컬럼만 가져온다. (2026-09-09)
    brands = (
        Brand.objects
        .filter(status=Brand.Status.ACTIVE)
        .only("id", "name", "english_name")
        .order_by("name")
    )

    sources = Source.objects.order_by("name")

    context = {
        "brand_sources": rows,
        "brands": brands,
        "brand_categories": _brand_categories(),
        "styles": (
            Style.objects
            .select_related("term")
            .all()
            .order_by("term__canonical_name")
        ),
        "sources": sources,
        "summary": summary,
        "selected_status": status,
        "selected_source": str(source_id) if source_id else "",
        "search_query": q,
    }

    return render(
        request,
        "dashboard/dictionary/brand_sources.html",
        context,
    )


@login_required(login_url="/admin-dashboard/login/")
@transaction.atomic
def map_brand_source(
    request: HttpRequest,
    source_id: int,
):
    if request.method != "POST":
        return redirect("dashboard:brand_sources")

    brand_source = get_object_or_404(
        BrandSource.objects.select_related("brand"),
        pk=source_id,
    )

    brand_id = request.POST.get("brand_id")

    if not brand_id:
        messages.error(
            request,
            "매핑할 FEEDIT 브랜드를 선택해주세요.",
        )
        return redirect("dashboard:brand_sources")

    brand = get_object_or_404(
        Brand,
        pk=brand_id,
        status=Brand.Status.ACTIVE,
    )

    old_brand = brand_source.brand

    brand_source.brand = brand
    brand_source.mapping_status = BrandSource.MappingStatus.MANUAL_MAPPED
    brand_source.mapping_method = BrandSource.MappingMethod.MANUAL
    brand_source.mapping_confidence = 1
    brand_source.save(
        update_fields=[
            "brand",
            "mapping_status",
            "mapping_method",
            "mapping_confidence",
            "updated_at",
        ]
    )

    _sync_brand_source_count(old_brand)
    _sync_brand_source_count(brand)

    messages.success(
        request,
        f"{brand_source.name or brand_source.source_brand_id} → {brand.name} 매핑 완료",
    )

    return redirect("dashboard:brand_sources")


@login_required(login_url="/admin-dashboard/login/")
@transaction.atomic
def create_brand_from_source(
    request: HttpRequest,
    source_id: int,
):
    if request.method != "POST":
        return redirect("dashboard:brand_sources")

    brand_source = get_object_or_404(
        BrandSource.objects.prefetch_related("styles"),
        pk=source_id,
    )

    # --------------------------------------------------------
    # INPUT (비어 있으면 BrandSource 값 승계)
    # --------------------------------------------------------
    brand_code = request.POST.get("brand_code", "").strip()
    name = request.POST.get("name", "").strip() or (brand_source.name or "")
    english_name = (
        request.POST.get("english_name", "").strip()
        or brand_source.english_name
        or ""
    )
    image_url = (
        request.POST.get("image_url", "").strip()
        or brand_source.image_url
        or ""
    )
    country_code = (
        request.POST.get("country_code", "").strip().upper()
        or (brand_source.country_code or "").upper()
    )
    description = (
        request.POST.get("description", "").strip()
        or brand_source.description
        or ""
    )
    website_url = (
        request.POST.get("website_url", "").strip()
        or brand_source.website_url
        or ""
    )

    target_gender = _parse_list_input(
        request.POST.get("target_gender", "")
    )
    if target_gender is None:
        target_gender = brand_source.target_gender

    target_age = _parse_list_input(
        request.POST.get("target_age", "")
    )
    if target_age is None:
        target_age = brand_source.target_age

    category_id = request.POST.get("category_id", "").strip()
    status = request.POST.get("status", "").strip()
    is_verified = request.POST.get("is_verified") == "on"

    # --------------------------------------------------------
    # BRAND CODE
    # --------------------------------------------------------
    if brand_code:
        brand_code = (
            brand_code
            .upper()
            .replace(" ", "_")
            .replace("-", "_")
        )

        while "__" in brand_code:
            brand_code = brand_code.replace("__", "_")

        if not brand_code.startswith("BRAND_"):
            brand_code = f"BRAND_{brand_code}"

    if not brand_code:
        messages.error(request, "브랜드 코드는 필수입니다.")
        return redirect("dashboard:brand_sources")

    if not name:
        messages.error(request, "표준 브랜드명은 필수입니다.")
        return redirect("dashboard:brand_sources")

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------
    category = None

    if category_id:
        category = (
            _brand_categories()
            .filter(pk=category_id)
            .first()
        )

        if category is None:
            messages.error(
                request,
                "유효하지 않은 브랜드 카테고리입니다.",
            )
            return redirect("dashboard:brand_sources")

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------
    valid_statuses = {
        value for value, _ in Brand.Status.choices
    }

    if status not in valid_statuses:
        status = Brand.Status.ACTIVE

    # --------------------------------------------------------
    # DUPLICATE CHECK
    # --------------------------------------------------------
    duplicate_query = (
        Q(brand_code__iexact=brand_code)
        | Q(name__iexact=name)
    )

    if english_name:
        duplicate_query |= Q(
            english_name__iexact=english_name
        )

    existing = Brand.objects.filter(duplicate_query).first()

    if existing:
        messages.warning(
            request,
            (
                "비슷한 FEEDIT 브랜드가 이미 존재합니다: "
                f"{existing.name} ({existing.brand_code}). "
                "신규 생성 대신 기존 브랜드 매핑을 사용해주세요."
            ),
        )
        return redirect("dashboard:brand_sources")

    # --------------------------------------------------------
    # CREATE BRAND
    # --------------------------------------------------------
    brand = Brand.objects.create(
        brand_code=brand_code,
        name=name,
        english_name=english_name or None,
        image_url=image_url or None,
        category=category,
        country_code=country_code or None,
        description=description or None,
        target_gender=target_gender,
        target_age=target_age,
        website_url=website_url or None,
        is_verified=is_verified,
        source_count=0,
        status=status,
    )

    # 선택한 스타일이 있으면 우선, 없으면 Source 스타일 승계
    style_ids = request.POST.getlist("style_ids")

    if style_ids:
        selected_styles = Style.objects.filter(term_id__in=style_ids)
        brand.styles.set(selected_styles)
    else:
        brand.styles.set(brand_source.styles.all())

    # --------------------------------------------------------
    # SOURCE -> BRAND
    # --------------------------------------------------------
    old_brand = brand_source.brand

    brand_source.brand = brand
    brand_source.mapping_status = BrandSource.MappingStatus.MANUAL_MAPPED
    brand_source.mapping_method = BrandSource.MappingMethod.MANUAL
    brand_source.mapping_confidence = 1
    brand_source.save(
        update_fields=[
            "brand",
            "mapping_status",
            "mapping_method",
            "mapping_confidence",
            "updated_at",
        ]
    )

    _sync_brand_source_count(old_brand)
    _sync_brand_source_count(brand)

    category_name = category.name if category else "미지정"

    messages.success(
        request,
        (
            f"{brand.name} ({brand.brand_code}) FEEDIT 브랜드 승격 완료 / "
            f"카테고리: {category_name} / {brand_source.source} 매핑 완료"
        ),
    )

    return redirect("dashboard:brand_sources")


@login_required(login_url="/admin-dashboard/login/")
@transaction.atomic
def unmap_brand_source(
    request: HttpRequest,
    source_id: int,
):
    """매핑을 끊고 미매핑 상태로 되돌린다."""

    if request.method != "POST":
        return redirect("dashboard:brand_sources")

    brand_source = get_object_or_404(
        BrandSource.objects.select_related("brand"),
        pk=source_id,
    )

    old_brand = brand_source.brand

    brand_source.brand = None
    brand_source.mapping_status = (
        BrandSource.MappingStatus.UNMAPPED
    )
    brand_source.mapping_method = None
    brand_source.mapping_confidence = None
    brand_source.save(
        update_fields=[
            "brand",
            "mapping_status",
            "mapping_method",
            "mapping_confidence",
            "updated_at",
        ]
    )

    _sync_brand_source_count(old_brand)

    messages.success(
        request,
        f"{brand_source.name or brand_source.source_brand_id} 매핑 해제 완료",
    )

    return redirect("dashboard:brand_sources")


@login_required(login_url="/admin-dashboard/login/")
@transaction.atomic
def exclude_brand_source(
    request: HttpRequest,
    source_id: int,
):
    """분석 대상에서 제외 처리한다."""

    if request.method != "POST":
        return redirect("dashboard:brand_sources")

    brand_source = get_object_or_404(
        BrandSource.objects.select_related("brand"),
        pk=source_id,
    )

    old_brand = brand_source.brand

    brand_source.brand = None
    brand_source.mapping_status = (
        BrandSource.MappingStatus.EXCLUDED
    )
    brand_source.mapping_method = (
        BrandSource.MappingMethod.MANUAL
    )
    brand_source.mapping_confidence = None
    brand_source.save(
        update_fields=[
            "brand",
            "mapping_status",
            "mapping_method",
            "mapping_confidence",
            "updated_at",
        ]
    )

    _sync_brand_source_count(old_brand)

    messages.success(
        request,
        f"{brand_source.name or brand_source.source_brand_id} 제외 처리 완료",
    )

    return redirect("dashboard:brand_sources")


@login_required(login_url="/admin-dashboard/login/")
def brand_connections(request):
    q = request.GET.get("q", "").strip()
    source_code = request.GET.get("source", "").strip()
    connection = request.GET.get("connection", "connected").strip()

    source_qs = (
        BrandSource.objects
        .select_related("source")
        .order_by(
            "source__code",
            "name",
        )
    )

    if source_code:
        source_qs = source_qs.filter(
            source__code__iexact=source_code
        )

    brands = (
        Brand.objects
        .prefetch_related(
            Prefetch(
                "brand_sources",
                queryset=source_qs,
                to_attr="linked_sources",
            )
        )
        .annotate(
            linked_source_count=Count(
                "brand_sources",
                distinct=True,
            )
        )
        .order_by("name")
    )

    if q:
        brands = brands.filter(
            Q(name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(brand_code__icontains=q)
            | Q(
                brand_sources__name__icontains=q
            )
            | Q(
                brand_sources__source_brand_id__icontains=q
            )
        ).distinct()

    if connection == "connected":
        brands = brands.filter(
            linked_source_count__gt=0
        )

    elif connection == "multi":
        brands = brands.filter(
            linked_source_count__gt=2
        )

    elif connection == "single":
        brands = brands.filter(
            linked_source_count__gt=1
        )

    elif connection == "none":
        brands = brands.filter(
            linked_source_count__gt=0
        )

    summary = {
        "total": Brand.objects.count(),

        "connected": (
            Brand.objects
            .filter(
                brand_sources__isnull=False
            )
            .distinct()
            .count()
        ),

        "multi": (
            Brand.objects
            .annotate(
                c=Count(
                    "brand_sources",
                    distinct=True,
                )
            )
            .filter(c__gte=2)
            .count()
        ),

        "single": (
            Brand.objects
            .annotate(
                c=Count(
                    "brand_sources",
                    distinct=True,
                )
            )
            .filter(c=1)
            .count()
        ),
    }

    sources = (
        Source.objects
        .filter(
            brand_sources__isnull=False
        )
        .distinct()
        .order_by("name")
    )

    context = {
        "brands": brands,
        "summary": summary,
        "sources": sources,

        "search_query": q,
        "selected_source": source_code,
        "selected_connection": connection,
    }

    return render(
        request,
        "dashboard/dictionary/brand_connections.html",
        context,
    )