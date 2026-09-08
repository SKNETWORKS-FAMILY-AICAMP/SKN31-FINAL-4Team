
from __future__ import annotations

import json
import boto3

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest,Http404, JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.core.paginator import Paginator
from .services.dashboard_service import get_dashboard_context
from apps.core.models import CrawlTarget, Source,CrawlRun,RawDocument, BrandSource, Brand, Category, Style

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
    """
    Collection Run 목록

    - 최근 수집 실행 이력
    - 성공 / 실패 / 실행중 통계
    - Source / Status / Run Type 필터
    - 검색
    - 각 Run에서 생성된 RawDocument 연결
    """

    # =========================================================
    # QUERY PARAMS
    # =========================================================

    search_query = request.GET.get("q", "").strip()
    selected_source = request.GET.get("source", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_run_type = request.GET.get("run_type", "").strip()

    # =========================================================
    # BASE QUERYSET
    # =========================================================

    runs_qs = (
        CrawlRun.objects
        .select_related(
            "source",
            "crawl_target",
        )
        .order_by("-created_at")
    )

    # =========================================================
    # SEARCH
    # =========================================================

    if search_query:

        runs_qs = runs_qs.filter(

            Q(target__icontains=search_query)

            | Q(source__code__icontains=search_query)

            | Q(source__name__icontains=search_query)

            | Q(error_code__icontains=search_query)

            | Q(error_message__icontains=search_query)

            | Q(celery_task_id__icontains=search_query)

            | Q(crawl_target__name__icontains=search_query)

        )

    # =========================================================
    # SOURCE FILTER
    # =========================================================

    if selected_source:
        runs_qs = runs_qs.filter(
            source_id=selected_source
        )

    # =========================================================
    # STATUS FILTER
    # =========================================================

    if selected_status:
        runs_qs = runs_qs.filter(
            status=selected_status
        )

    # =========================================================
    # RUN TYPE FILTER
    # =========================================================

    if selected_run_type:
        runs_qs = runs_qs.filter(
            run_type=selected_run_type
        )

    # =========================================================
    # SUMMARY
    # 현재 필터 조건 기준
    # =========================================================

    summary = {
        "total": runs_qs.count(),

        "running": runs_qs.filter(
            status="RUNNING"
        ).count(),

        "success": runs_qs.filter(
            status="SUCCESS"
        ).count(),

        "failed": runs_qs.filter(
            status="FAILED"
        ).count(),
    }

    # =========================================================
    # PAGINATION
    # =========================================================

    paginator = Paginator(
        runs_qs,
        30,
    )

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(
        page_number
    )

    runs = list(page_obj.object_list)

    # =========================================================
    # RAW DOCUMENT 연결
    #
    # RawDocument.crawl_run FK를 기준으로
    # 현재 페이지의 Run에 해당하는 문서만 가져옴
    # =========================================================

    run_ids = [
        run.id
        for run in runs
    ]

    raw_documents_by_run = {}

    if run_ids:

        raw_documents = (
            RawDocument.objects
            .filter(
                crawl_run_id__in=run_ids
            )
            .order_by(
                "-collected_at"
            )
        )

        for document in raw_documents:

            raw_documents_by_run.setdefault(
                document.crawl_run_id,
                []
            ).append(
                document
            )

    # =========================================================
    # Run 객체에 RawDocument 정보 임시 부착
    #
    # DB 저장하는 것 아님.
    # template에서 사용하기 위한 attribute.
    # =========================================================

    for run in runs:

        documents = raw_documents_by_run.get(
            run.id,
            [],
        )

        run.raw_documents = documents

        run.raw_document_count = len(
            documents
        )

        # 상세화면에 너무 많이 뿌리지 않도록
        # 최근 5개만 preview
        run.raw_document_preview = documents[:5]

    # =========================================================
    # FILTER OPTIONS
    # =========================================================

    sources = (
        Source.objects
        .all()
        .order_by("code")
    )

    status_choices = (
        CrawlRun._meta
        .get_field("status")
        .choices
    )

    run_type_choices = (
        CrawlRun._meta
        .get_field("run_type")
        .choices
    )

    # =========================================================
    # CONTEXT
    # =========================================================

    context = {

        "page_title": "Collection Runs",

        "page_description":
            "크롤링 및 수집 실행 이력을 확인합니다.",

        "runs": runs,

        "page_obj": page_obj,

        "summary": summary,

        "sources": sources,

        "status_choices": status_choices,

        "run_type_choices": run_type_choices,

        "search_query": search_query,

        "selected_source": selected_source,

        "selected_status": selected_status,

        "selected_run_type": selected_run_type,
    }

    return render(
        request,
        "dashboard/collection/runs.html",
        context,
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
    rows = list(queryset[:500])
    for item in rows:
        item.ui_target_gender = ", ".join(
            str(v) for v in (item.target_gender or [])
        )
        item.ui_target_age = ", ".join(
            str(v) for v in (item.target_age or [])
        )
        item.ui_style_ids = ",".join(
            str(v) for v in item.styles.values_list("term_id", flat=True)
        )
        item.ui_style_names = ", ".join(
            str(v) for v in item.styles.all()
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

    brands = (
        Brand.objects
        .filter(status=Brand.Status.ACTIVE)
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


# ============================================================
# EXISTING BRAND MAPPING / REMAPPING
# ============================================================


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


# ============================================================
# CREATE / PROMOTE FEEDIT BRAND
# ============================================================


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


# ============================================================
# UNMAP
# ============================================================


@transaction.atomic
def unmap_brand_source(
    request: HttpRequest,
    source_id: int,
):
    if request.method != "POST":
        return redirect("dashboard:brand_sources")

    brand_source = get_object_or_404(
        BrandSource.objects.select_related("brand"),
        pk=source_id,
    )

    old_brand = brand_source.brand

    brand_source.brand = None
    brand_source.mapping_status = BrandSource.MappingStatus.UNMAPPED
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


# ============================================================
# EXCLUDE
# ============================================================


@transaction.atomic
def exclude_brand_source(
    request: HttpRequest,
    source_id: int,
):
    if request.method != "POST":
        return redirect("dashboard:brand_sources")

    brand_source = get_object_or_404(
        BrandSource.objects.select_related("brand"),
        pk=source_id,
    )

    old_brand = brand_source.brand

    brand_source.brand = None
    brand_source.mapping_status = BrandSource.MappingStatus.EXCLUDED
    brand_source.mapping_method = BrandSource.MappingMethod.MANUAL
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


def raw_document_json(request, pk):

    document = get_object_or_404(
        RawDocument,
        pk=pk,
    )

    if not document.s3_key:

        raise Http404(
            "S3 object key가 없습니다."
        )

    bucket = (
        document.s3_bucket
        or settings.AWS_STORAGE_BUCKET_NAME
    )

    s3 = boto3.client(
        "s3",
        region_name=getattr(
            settings,
            "AWS_REGION",
            "ap-northeast-2",
        ),
    )

    try:

        response = s3.get_object(
            Bucket=bucket,
            Key=document.s3_key,
        )

        body = (
            response["Body"]
            .read()
            .decode("utf-8")
        )

        data = json.loads(
            body
        )

    except Exception as exc:

        raise Http404(
            f"S3 Raw JSON 조회 실패: {exc}"
        )

    return JsonResponse(
        data,
        safe=not isinstance(
            data,
            list,
        ),
        json_dumps_params={
            "ensure_ascii": False,
            "indent": 2,
        },
    )