
from __future__ import annotations
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.core.paginator import Paginator
from .services.dashboard_service import get_dashboard_context
from apps.core.models import CrawlTarget, Source, BrandSource, Brand

def dashboard(request):
    return render(
        request,
        "dashboard/dashboard.html",
        get_dashboard_context(),
    )


def _simple_page(request, template_name, title, description):
    return render(
        request,
        template_name,
        {
            "page_title": title,
            "page_description": description,
        },
    )


def collection_targets(request):
    targets = (
        CrawlTarget.objects
        .select_related("source")
        .order_by(
            "-is_active",
            "priority",
            "source__code",
            "id",
        )
    )

    # ==========================
    # FILTER
    # ==========================

    source = request.GET.get("source", "")
    target_type = request.GET.get("target_type", "")
    collection_mode = request.GET.get("collection_mode", "")
    active = request.GET.get("active", "")
    q = request.GET.get("q", "").strip()

    if source:
        targets = targets.filter(source_id=source)

    if target_type:
        targets = targets.filter(target_type=target_type)

    if collection_mode:
        targets = targets.filter(collection_mode=collection_mode)

    if active == "1":
        targets = targets.filter(is_active=True)

    elif active == "0":
        targets = targets.filter(is_active=False)

    if q:
        targets = targets.filter(
            Q(name__icontains=q)
            | Q(target_url__icontains=q)
            | Q(source__code__icontains=q)
            | Q(source__name__icontains=q)
        )

    # ==========================
    # SUMMARY
    # ==========================

    summary = {
        "total": targets.count(),
        "active": targets.filter(
            is_active=True
        ).count(),
        "inactive": targets.filter(
            is_active=False
        ).count(),
        "live": targets.filter(
            collection_mode=CrawlTarget.CollectionMode.LIVE
        ).count(),
    }

    # ==========================
    # PAGINATION
    # ==========================

    paginator = Paginator(targets, 30)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "Collection Targets",
        "page_description": (
            "크롤러 수집 대상과 실행 설정을 관리합니다."
        ),

        "page_obj": page_obj,
        "targets": page_obj.object_list,

        "summary": summary,

        "sources": Source.objects.order_by("code"),

        "target_type_choices":
            CrawlTarget.TargetType.choices,

        "collection_mode_choices":
            CrawlTarget.CollectionMode.choices,

        "selected_source": source,
        "selected_target_type": target_type,
        "selected_collection_mode": collection_mode,
        "selected_active": active,
        "search_query": q,
    }

    return render(
        request,
        "dashboard/collection/targets.html",
        context,
    )


def collection_runs(request):
    return _simple_page(
        request,
        "dashboard/collection/runs.html",
        "Collection Runs",
        "크롤링 및 수집 실행 이력을 확인합니다.",
    )


def raw_documents(request):
    return _simple_page(
        request,
        "dashboard/collection/raw_documents.html",
        "Raw Documents",
        "S3에 저장된 원본 수집 데이터를 추적합니다.",
    )


def normalized_products(request):
    return _simple_page(
        request,
        "dashboard/normalization/products.html",
        "Product Normalization",
        "상품 정규화 결과를 확인합니다.",
    )


def normalization_failures(request):
    return _simple_page(
        request,
        "dashboard/normalization/failures.html",
        "Normalization Failures",
        "정규화 실패 데이터를 검토합니다.",
    )


def dictionary_terms(request):
    return _simple_page(
        request,
        "dashboard/dictionary/terms.html",
        "Term Dictionary",
        "FEEDIT 표준 패션 용어 사전을 관리합니다.",
    )


def dictionary_candidates(request):
    context = {
        "page_title": "Dictionary Candidates",
        "page_description": "신규 패션 용어 후보를 검토하고 승격합니다.",
        "candidates": [
            {
                "id": 1,
                "term": "피치스킨",
                "term_type": "MATERIAL",
                "matched_term": "peach skin",
                "similarity": 0.89,
                "count": 34,
                "decision": "KEEP",
                "reason": "최근 상품 데이터에서 반복적으로 등장하며 기존 소재 용어와 의미적으로 구분됩니다.",
            },
            {
                "id": 2,
                "term": "발레코어",
                "term_type": "STYLE",
                "matched_term": "balletcore",
                "similarity": 0.94,
                "count": 81,
                "decision": "PROMOTE",
                "reason": "커머스와 콘텐츠 양쪽에서 반복 출현하며 독립 스타일 용어로 사용됩니다.",
            },
            {
                "id": 3,
                "term": "고프코어",
                "term_type": "STYLE",
                "matched_term": "gorpcore",
                "similarity": 0.97,
                "count": 112,
                "decision": "PROMOTE",
                "reason": "표준 스타일 사전 항목으로 관리하기 적절합니다.",
            },
        ],
    }

    return render(
        request,
        "dashboard/dictionary/candidates.html",
        context,
    )


def dictionary_candidate_detail(request, pk):
    candidate = {
        "id": pk,
        "term": "피치스킨",
        "term_type": "MATERIAL",
        "matched_term": "peach skin",
        "similarity": 0.89,
        "count": 34,
        "decision": "KEEP",
        "reason": "최근 상품 데이터에서 반복적으로 등장하며 기존 소재 용어와 의미적으로 구분됩니다.",
    }

    return render(
        request,
        "dashboard/dictionary/candidate_detail.html",
        {
            "page_title": candidate["term"],
            "page_description": "사전 후보 상세 분석",
            "candidate": candidate,
        },
    )


def trend_metrics(request):
    return _simple_page(
        request,
        "dashboard/trend/metrics.html",
        "Trend Metrics",
        "트렌드 온도 및 주요 지표를 확인합니다.",
    )


def products(request):
    return _simple_page(
        request,
        "dashboard/data/products.html",
        "Products",
        "FEEDIT 표준 상품 데이터를 조회합니다.",
    )


def brands(request):
    return _simple_page(
        request,
        "dashboard/data/brands.html",
        "Brands",
        "표준 브랜드 및 플랫폼 매핑 정보를 조회합니다.",
    )


def categories(request):
    return _simple_page(
        request,
        "dashboard/data/categories.html",
        "Categories",
        "FEEDIT 표준 카테고리 체계를 조회합니다.",
    )


def jobs(request):
    return _simple_page(
        request,
        "dashboard/jobs/index.html",
        "Jobs",
        "Celery 및 배치 작업 상태를 확인합니다.",
    )


def system_status(request):
    context = {
        "page_title": "System Status",
        "page_description": "FEEDIT 인프라 연결 상태를 확인합니다.",
        "services": [
            {"name": "PostgreSQL / RDS", "status": "healthy", "detail": "Connected"},
            {"name": "Redis", "status": "healthy", "detail": "Connected"},
            {"name": "S3", "status": "healthy", "detail": "Available"},
            {"name": "Celery Worker", "status": "warning", "detail": "1 delayed task"},
        ],
    }
    return render(request, "dashboard/system/status.html", context)

def brand_sources(
    request: HttpRequest,
):

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    status = request.GET.get(
        "status",
        "unmapped",
    )

    source_id = request.GET.get(
        "source",
    )

    q = (
        request.GET.get(
            "q",
            "",
        )
        .strip()
    )

    queryset = (
        BrandSource.objects
        .select_related(
            "source",
            "brand",
        )
        .all()
    )

    # 기본값 = 미매핑
    if status == "unmapped":
        queryset = queryset.filter(
            brand__isnull=True,
        )

    elif status == "mapped":
        queryset = queryset.filter(
            brand__isnull=False,
        )

    if source_id:
        queryset = queryset.filter(
            source_id=source_id,
        )

    if q:
        queryset = queryset.filter(
            Q(
                source_brand_name__icontains=q
            )
            | Q(
                source_brand_name_en__icontains=q
            )
            | Q(
                source_brand_id__icontains=q
            )
        )

    # 핵심:
    # 발견횟수 높은 순
    queryset = queryset.order_by(
        "-detected_count",
        "-last_seen_at",
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    all_unmapped = (
        BrandSource.objects
        .filter(
            brand__isnull=True,
        )
    )

    summary = {
        "unmapped": (
            all_unmapped.count()
        ),

        "review": (
            all_unmapped
            .filter(
                detected_count__gte=5,
            )
            .count()
        ),

        "priority": (
            all_unmapped
            .filter(
                detected_count__gte=20,
            )
            .count()
        ),

        "mapped": (
            BrandSource.objects
            .filter(
                brand__isnull=False,
            )
            .count()
        ),
    }

    # 기존 Brand 연결 모달용
    brands = (
        Brand.objects
        .order_by(
            "name",
        )
    )

    sources = (
        Source.objects
        .order_by(
            "name",
        )
    )

    context = {
        "brand_sources": queryset[:500],
        "brands": brands,
        "sources": sources,
        "summary": summary,

        "selected_status": status,
        "selected_source": source_id,
        "search_query": q,
    }

    return render(
        request,
        "dashboard/dictionary/brand_sources.html",
        context,
    )


# ============================================================
# EXISTING BRAND MAPPING
# ============================================================


@transaction.atomic
def map_brand_source(
    request: HttpRequest,
    source_id: int,
):

    if request.method != "POST":
        return redirect(
            "dashboard:brand_sources"
        )

    brand_source = get_object_or_404(
        BrandSource,
        pk=source_id,
    )

    brand_id = request.POST.get(
        "brand_id",
    )

    if not brand_id:
        messages.error(
            request,
            "매핑할 FEEDIT 브랜드를 선택해주세요.",
        )

        return redirect(
            "dashboard:brand_sources"
        )

    brand = get_object_or_404(
        Brand,
        pk=brand_id,
    )

    brand_source.brand = brand

    # MANUAL enum이 있으면 사용하고
    # 아직 없다면 기존 enum으로 fallback
    brand_source.mapping_status = getattr(
        BrandSource.MappingStatus,
        "MANUAL_MAPPED",
        BrandSource.MappingStatus.AUTO_MAPPED,
    )

    brand_source.mapping_method = getattr(
        BrandSource.MappingMethod,
        "MANUAL",
        BrandSource.MappingMethod.SOURCE_ID,
    )

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

    messages.success(
        request,
        (
            f"{brand_source.source_brand_name} "
            f"→ {brand.name} 매핑 완료"
        ),
    )

    return redirect(
        "dashboard:brand_sources"
    )


# ============================================================
# CREATE NEW FEEDIT BRAND
# ============================================================


@transaction.atomic
def create_brand_from_source(
    request: HttpRequest,
    source_id: int,
):

    if request.method != "POST":
        return redirect(
            "dashboard:brand_sources"
        )

    brand_source = get_object_or_404(
        BrandSource,
        pk=source_id,
    )

    brand_code = (
        request.POST.get(
            "brand_code",
            "",
        )
        .strip()
    )

    name = (
        request.POST.get(
            "name",
            "",
        )
        .strip()
    )

    english_name = (
        request.POST.get(
            "english_name",
            "",
        )
        .strip()
    )

    if not brand_code:
        messages.error(
            request,
            "브랜드 코드는 필수입니다.",
        )

        return redirect(
            "dashboard:brand_sources"
        )

    if not name:
        messages.error(
            request,
            "브랜드명은 필수입니다.",
        )

        return redirect(
            "dashboard:brand_sources"
        )

    # --------------------------------------------------------
    # 중복 방지
    # --------------------------------------------------------

    existing = (
        Brand.objects
        .filter(
            Q(
                brand_code__iexact=brand_code
            )
            | Q(
                name__iexact=name
            )
        )
        .first()
    )

    if existing:

        messages.warning(
            request,
            (
                f"비슷한 FEEDIT 브랜드가 이미 존재합니다: "
                f"{existing.name}. "
                f"신규 생성 대신 기존 브랜드 매핑을 사용해주세요."
            ),
        )

        return redirect(
            "dashboard:brand_sources"
        )

    # --------------------------------------------------------
    # CREATE
    # --------------------------------------------------------

    brand = Brand.objects.create(
        brand_code=brand_code,
        name=name,
        english_name=(
            english_name
            or None
        ),
    )

    # Source → Brand 연결
    brand_source.brand = brand

    brand_source.mapping_status = getattr(
        BrandSource.MappingStatus,
        "MANUAL_MAPPED",
        BrandSource.MappingStatus.AUTO_MAPPED,
    )

    brand_source.mapping_method = getattr(
        BrandSource.MappingMethod,
        "MANUAL",
        BrandSource.MappingMethod.SOURCE_ID,
    )

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

    messages.success(
        request,
        (
            f"{brand.name} FEEDIT 브랜드 생성 및 "
            f"{brand_source.source} 매핑 완료"
        ),
    )

    return redirect(
        "dashboard:brand_sources"
    )