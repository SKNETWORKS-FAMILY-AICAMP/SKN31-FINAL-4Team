"""FEEDIT 관리자 대시보드 뷰.

# ============================================================
# 병합 이력 (2026-09-09)
#
# 메인 레포 views.py 와 대시보드 작업본을 함수 단위로 병합했다.
#
# [메인 구현을 채택한 것]
#   _sync_brand_source_count   작업본에는 정의가 없고 호출만 있어
#                              unmap/exclude 실행 시 NameError 상태였음
#   _parse_list_input          작업본에 없었음
#   _brand_categories          작업본에 없었음
#   brand_sources              메인이 상위 집합
#                              (brand_categories, styles 추가 제공)
#   map_brand_source           메인을 정본으로
#   create_brand_from_source   메인은 카테고리·스타일·타깃·중복검사까지 처리.
#                              작업본은 3개 필드만 저장하는 축소판이었음
#   raw_document_json          작업본에 없었음.
#                              단 settings import 누락으로 호출 시 NameError가
#                              나던 버그는 수정함
#
# [작업본 구현을 채택한 것]
#   그 외 전부. 메인 쪽은 대부분 _simple_page 자리표시자이거나
#   하드코딩된 예시 데이터였다.
#
# [메인에서 사라진 것]
#   _simple_page   이를 쓰던 뷰가 모두 실제 구현으로 대체되어 불필요해짐.
#                  대상: raw_documents, normalized_products,
#                        normalization_failures, dictionary_terms,
#                        trend_metrics, products, brands, categories, jobs
#   dictionary_candidates / dictionary_candidate_detail / system_status
#                  하드코딩된 예시 데이터 -> 실제 DB 조회로 교체
# ============================================================
"""

from __future__ import annotations
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
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
from django.http import HttpRequest
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse, HttpResponse
import boto3
import json
import logging
import os
import time
import traceback
from datetime import datetime, timezone as dt_timezone
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from .services.dashboard_service import get_dashboard_context
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
def dashboard(request):
    return render(
        request,
        "dashboard/dashboard.html",
        get_dashboard_context(),
    )


@login_required(login_url="/admin-dashboard/login/")
def collection_targets_create(request):
    if request.method == "POST":
        source_id = request.POST.get("source")
        name = request.POST.get("name")
        target_url = request.POST.get("target_url")
        target_type = request.POST.get("target_type") or "CREATOR"
        collection_mode = request.POST.get("collection_mode") or "LIVE"
        
        try:
            source = Source.objects.get(id=source_id)
            CrawlTarget.objects.create(
                source=source,
                name=name,
                target_url=target_url,
                target_type=target_type,
                collection_mode=collection_mode,
                interval_minutes=1440,
                priority=5,
                is_active=True
            )
            messages.success(request, "URL 타겟이 성공적으로 등록되었습니다.")
        except Exception as e:
            messages.error(request, f"URL 타겟 등록 중 오류가 발생했습니다: {e}")
            
    return_url = request.POST.get("return_url") or "dashboard:collection_targets"
    return redirect(return_url)


@login_required(login_url="/admin-dashboard/login/")
def collection_targets_update(request, target_id):
    if request.method == "POST":
        target = get_object_or_404(CrawlTarget, id=target_id)
        
        source_id = request.POST.get("source")
        if source_id:
            target.source = get_object_or_404(Source, id=source_id)
            
        target.name = request.POST.get("name", target.name)
        target.target_url = request.POST.get("target_url", target.target_url)
        target.target_type = request.POST.get("target_type", target.target_type)
        target.collection_mode = request.POST.get("collection_mode", target.collection_mode)
        
        interval_minutes = request.POST.get("interval_minutes")
        if interval_minutes and interval_minutes.isdigit():
            target.interval_minutes = int(interval_minutes)
            
        target.is_active = request.POST.get("is_active") == "on"
        
        try:
            target.save()
            messages.success(request, "URL 타겟이 성공적으로 수정되었습니다.")
        except Exception as e:
            messages.error(request, f"URL 타겟 수정 중 오류가 발생했습니다: {e}")
            
    return_url = request.POST.get("return_url") or "dashboard:collection_targets"
    return redirect(return_url)


@login_required(login_url="/admin-dashboard/login/")
def collection_targets_delete(request):
    if request.method == "POST":
        target_ids = request.POST.getlist("target_ids")
        if target_ids:
            try:
                CrawlTarget.objects.filter(id__in=target_ids).delete()
                messages.success(request, f"{len(target_ids)}개의 항목이 성공적으로 삭제되었습니다.")
            except Exception as e:
                messages.error(request, f"항목 삭제 중 오류가 발생했습니다: {e}")
        else:
            messages.warning(request, "삭제할 항목을 선택해주세요.")
            
    return_url = request.POST.get("return_url") or "dashboard:collection_targets"
    return redirect(return_url)



@login_required(login_url="/admin-dashboard/login/")
def collection_targets(request):
    targets = (
        CrawlTarget.objects
        .select_related("source")
        .order_by("id")
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

    paginator = Paginator(targets, 20)

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


@login_required(login_url="/admin-dashboard/login/")
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

        run.attached_raw_documents = documents
        
        run.attached_raw_document_count = len(
            documents
        )

        # 상세화면에 너무 많이 뿌리지 않도록
        # 최근 5개만 preview
        run.attached_raw_document_preview = documents[:5]

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


# 필터 버튼 노출 순서와 한글 라벨
SOURCE_ORDER = [
    "musinsa",
    "zigzag",
    "ably",
    "musinsa_used",
    "kream",
    "YOUTUBE",
    "naver",
]

SOURCE_LABELS = {
    "musinsa": "무신사",
    "musinsa_used": "무신사 USED",
    "zigzag": "지그재그",
    "ably": "에이블리",
    "kream": "크림",
    "YOUTUBE": "유튜브",
    "youtube": "유튜브",
    "naver": "네이버",
}


def _source_label(source):
    """Source에 대한 한글 라벨."""
    if source is None:
        return "-"
    return SOURCE_LABELS.get(
        source.code,
        source.name or source.code,
    )


def _group_count(queryset, key="source_id", **filters):
    """소스별 건수를 한 번의 쿼리로 집계한다."""
    annotations = {"n": Count("id")}
    for name, condition in filters.items():
        annotations[name] = Count("id", filter=condition)

    result = {}
    for row in queryset.values(key).annotate(**annotations):
        result[row[key]] = row
    return result


def _ordered_sources():
    """SOURCE_ORDER 순서대로 정렬된 Source 목록."""
    by_code = {s.code: s for s in Source.objects.all()}

    ordered = []
    for code in SOURCE_ORDER:
        source = by_code.pop(code, None)
        if source is not None:
            source.label = _source_label(source)
            ordered.append(source)

    # 목록에 없는 소스는 뒤에 코드순으로 붙인다.
    for code in sorted(by_code):
        source = by_code[code]
        source.label = _source_label(source)
        ordered.append(source)

    return ordered


@login_required(login_url="/admin-dashboard/login/")
def raw_documents(request):
    sources = _ordered_sources()
    selected_source = request.GET.get("source", "")

    docs_qs = (
        RawDocument.objects
        .select_related("source", "crawl_run")
        .order_by("-id")
    )

    if selected_source:
        docs_qs = docs_qs.filter(source_id=selected_source)

    paginator = Paginator(docs_qs, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    documents = list(page_obj.object_list)

    for doc in documents:
        doc.platform_label = _source_label(doc.source)

    context = {
        "page_title": "Raw Documents",
        "page_description": "S3에 저장된 원본 수집 데이터를 추적합니다.",
        "sources": sources,
        "selected_source": selected_source,
        "page_obj": page_obj,
        "documents": documents,
    }
    return render(request, "dashboard/collection/raw_documents.html", context)


@login_required(login_url="/admin-dashboard/login/")
def raw_document_preview(request, pk):
    doc = get_object_or_404(RawDocument, pk=pk)
    if not doc.s3_key:
        return JsonResponse({"error": "S3 키가 없습니다."}, status=400)
        
    try:
        s3 = boto3.client("s3")
        # 메모리 최적화를 위해 처음 5KB만 가져오기 (Range HTTP Header 사용)
        response = s3.get_object(
            Bucket=doc.s3_bucket,
            Key=doc.s3_key,
            Range="bytes=0-5120"
        )
        content = response["Body"].read().decode("utf-8", errors="replace")
        
        # JSON 파싱 시도 (잘린 경우를 대비해 그냥 텍스트로 보낼 수도 있음)
        # 하지만 예쁘게 보이기 위해 텍스트 그대로 보냄
        return JsonResponse({"content": content + "\n\n... (데이터 생략됨) ..."})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required(login_url="/admin-dashboard/login/")
def raw_document_download(request, pk):
    doc = get_object_or_404(RawDocument, pk=pk)
    if not doc.s3_key:
        return HttpResponse("S3 키가 없습니다.", status=400)
        
    try:
        s3 = boto3.client("s3")
        response = s3.get_object(
            Bucket=doc.s3_bucket,
            Key=doc.s3_key
        )
        
        filename = doc.s3_key.split("/")[-1]
        
        http_response = HttpResponse(
            response["Body"].read(),
            content_type=response.get("ContentType", "application/json")
        )
        http_response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return http_response
    except Exception as e:
        return HttpResponse(f"다운로드 실패: {e}", status=500)


@login_required(login_url="/admin-dashboard/login/")
def raw_document_json(request, pk):
    """RawDocument의 S3 원본 JSON을 그대로 응답한다."""

    document = get_object_or_404(
        RawDocument,
        pk=pk,
    )

    if not document.s3_key:
        raise Http404("S3 object key가 없습니다.")

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

        data = json.loads(body)

    except Exception as exc:  # noqa: BLE001
        raise Http404(f"S3 Raw JSON 조회 실패: {exc}")

    return JsonResponse(
        data,
        safe=not isinstance(data, list),
        json_dumps_params={
            "ensure_ascii": False,
            "indent": 2,
        },
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
        "sources": _ordered_sources(),
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
        row.platform_label = _source_label(row.source)

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
        "sources": _ordered_sources(),
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


@login_required(login_url="/admin-dashboard/login/")
def dictionary_terms(request):
    """표준 패션 용어 사전."""

    selected_type = request.GET.get("term_type", "").strip()
    selected_status = request.GET.get("status", "").strip()
    q = request.GET.get("q", "").strip()

    # embedding 은 1536차원 벡터라 행당 수 KB다. 값은 화면에서 쓰지 않고
    # "있음/없음" 만 필요하므로, 필드는 빼고 존재 여부만 DB에서 계산해 온다.
    #
    # defer 만 하고 템플릿에서 row.embedding 을 읽으면 행마다 재조회가 나가
    # 오히려 느려진다(40행 -> 쿼리 40회). (2026-09-09)
    queryset = (
        DictionaryTerm.objects
        .defer("embedding", "embedding_updated_at")
        .annotate(
            has_embedding=Case(
                When(embedding__isnull=False, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        .select_related("brand")
        .prefetch_related("aliases")
        .order_by("term_type", "canonical_name")
    )

    if selected_type:
        queryset = queryset.filter(term_type=selected_type)

    if selected_status:
        queryset = queryset.filter(status=selected_status)

    if q:
        queryset = queryset.filter(
            Q(canonical_name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(term_code__icontains=q)
            | Q(aliases__alias__icontains=q)
        ).distinct()

    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    all_terms = DictionaryTerm.objects.all()

    by_type = (
        all_terms
        .values("term_type")
        .annotate(n=Count("id"))
        .order_by("-n")
    )

    context = {
        "page_title": "사전 용어",
        "page_description": "FEEDIT 표준 패션 용어를 조회합니다.",
        "summary": {
            "total": all_terms.count(),
            "active": all_terms.filter(status="ACTIVE").count(),
            "alias": TermAlias.objects.count(),
            "embedded": all_terms.filter(
                embedding__isnull=False
            ).count(),
        },
        "by_type": by_type,
        "type_choices": DictionaryTerm.TermType.choices,
        "status_choices": DictionaryTerm.Status.choices,
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "filtered_count": paginator.count,
        "selected_type": selected_type,
        "selected_status": selected_status,
        "search_query": q,
    }

    return render(
        request,
        "dashboard/dictionary/terms.html",
        context,
    )


@login_required(login_url="/admin-dashboard/login/")
def dictionary_candidates(request):
    """신규 용어 후보 검토 목록."""

    selected_type = request.GET.get("suggested_type", "").strip()
    selected_decision = request.GET.get("decision", "").strip()
    selected_status = request.GET.get("status", "").strip()
    q = request.GET.get("q", "").strip()

    queryset = (
        TermCandidate.objects
        .select_related("nearest_term")
        .order_by("-detected_count", "-last_seen_at")
    )

    if selected_type:
        queryset = queryset.filter(suggested_type=selected_type)

    if selected_decision:
        queryset = queryset.filter(decision=selected_decision)

    if selected_status:
        queryset = queryset.filter(status=selected_status)

    if q:
        queryset = queryset.filter(
            Q(raw_term__icontains=q)
            | Q(note__icontains=q)
            | Q(decision_reason__icontains=q)
        )

    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    all_candidates = TermCandidate.objects.all()

    context = {
        "page_title": "용어 후보",
        "page_description": (
            "수집 데이터에서 발견된 신규 용어 후보를 검토합니다."
        ),
        "summary": {
            "total": all_candidates.count(),
            "pending": all_candidates.filter(
                status="PENDING"
            ).count(),
            "new_term": all_candidates.filter(
                decision="NEW_TERM"
            ).count(),
            "alias": all_candidates.filter(
                decision="ALIAS"
            ).count(),
            "reject": all_candidates.filter(
                decision="REJECT"
            ).count(),
        },
        "type_choices": DictionaryTerm.TermType.choices,
        "decision_choices": TermCandidate.Decision.choices,
        "status_choices": TermCandidate.Status.choices,
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "filtered_count": paginator.count,
        "selected_type": selected_type,
        "selected_decision": selected_decision,
        "selected_status": selected_status,
        "search_query": q,
    }

    return render(
        request,
        "dashboard/dictionary/candidates.html",
        context,
    )


@login_required(login_url="/admin-dashboard/login/")
def dictionary_candidate_detail(request, pk):
    """용어 후보 상세 + 관측 문맥."""

    candidate = get_object_or_404(
        TermCandidate.objects.select_related("nearest_term"),
        pk=pk,
    )

    observations = (
        candidate.observations
        .select_related("source")
        .order_by("-detected_at")[:50]
    )

    context = {
        "page_title": candidate.raw_term,
        "page_description": "용어 후보 상세",
        "candidate": candidate,
        "observations": observations,
        "observation_count": candidate.observations.count(),
    }

    return render(
        request,
        "dashboard/dictionary/candidate_detail.html",
        context,
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

    queryset = (
        Brand.objects
        .select_related("category")
        .order_by("-source_count", "name")
    )

    if selected_status:
        queryset = queryset.filter(status=selected_status)

    if selected_verified == "1":
        queryset = queryset.filter(is_verified=True)
    elif selected_verified == "0":
        queryset = queryset.filter(is_verified=False)

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(brand_code__icontains=q)
            | Q(country_code__icontains=q)
        )

    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    brand_agg = Brand.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status="ACTIVE")),
        verified=Count("id", filter=Q(is_verified=True)),
        linked=Count("id", filter=Q(source_count__gt=0)),
    )

    context = {
        "page_title": "브랜드",
        "page_description": "FEEDIT 표준 브랜드를 조회합니다.",
        "summary": {
            **brand_agg,
            "brand_source": BrandSource.objects.count(),
        },
        "status_choices": Brand.Status.choices,
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "filtered_count": paginator.count,
        "selected_status": selected_status,
        "selected_verified": selected_verified,
        "search_query": q,
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


@login_required(login_url="/admin-dashboard/login/")
def jobs(request):
    """작업 현황 — 실행 상태와 대기 중인 작업을 모아 본다."""

    now = timezone.now()
    today = timezone.localtime(now).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    runs = CrawlRun.objects.all()

    by_status = list(
        runs.values("status").annotate(n=Count("id")).order_by("-n")
    )

    run_stats = _group_count(
        runs,
        success=Q(status="SUCCESS"),
        failed=Q(status="FAILED"),
        running=Q(status="RUNNING"),
    )

    last_runs = {}
    for run in (
        CrawlRun.objects
        .order_by("source_id", "-started_at")
        .only("id", "source_id", "started_at")
    ):
        last_runs.setdefault(run.source_id, run)

    by_source = []
    for source in _ordered_sources():
        stat = run_stats.get(source.id)
        if not stat:
            continue
        by_source.append({
            "label": source.label,
            "code": source.code,
            "total": stat.get("n", 0),
            "success": stat.get("success", 0),
            "failed": stat.get("failed", 0),
            "running": stat.get("running", 0),
            "last": last_runs.get(source.id),
        })

    # 실행 대기 중인 타겟
    due_queryset = (
        CrawlTarget.objects
        .select_related("source")
        .filter(is_active=True, collection_mode="LIVE")
        .filter(Q(next_crawl_at__isnull=True) | Q(next_crawl_at__lte=now))
        .order_by("-priority", "next_crawl_at")
    )
    due_count = due_queryset.count()
    due_targets = due_queryset[:20]

    # 실패 사유 상위
    reasons = {}
    for code, message in (
        runs.filter(status="FAILED")
        .values_list("error_code", "error_message")[:2000]
    ):
        key = (code or "UNKNOWN", (str(message or "").strip() or "(메시지 없음)")[:110])
        reasons[key] = reasons.get(key, 0) + 1

    top_reasons = [
        {"code": k[0], "message": k[1], "count": v}
        for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:8]
    ]

    running = (
        runs.select_related("source", "crawl_target")
        .filter(status="RUNNING")
        .order_by("-started_at")[:20]
    )

    context = {
        "page_title": "작업 현황",
        "page_description": "수집 작업의 상태별 분포와 대기 중인 작업을 확인합니다.",
        "summary": {
            "total": runs.count(),
            "today": runs.filter(started_at__gte=today).count(),
            "running": runs.filter(status="RUNNING").count(),
            "failed": runs.filter(status="FAILED").count(),
            "due": due_count,
        },
        "by_status": by_status,
        "by_source": by_source,
        "due_targets": due_targets,
        "top_reasons": top_reasons,
        "running_runs": running,
    }

    return render(request, "dashboard/jobs/index.html", context)


@login_required(login_url="/admin-dashboard/login/")
def system_status(request):
    """시스템 상태 — 실제로 접속을 시도해 확인한다."""

    services = []

    # ---------- PostgreSQL ----------
    started = time.monotonic()
    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        elapsed = (time.monotonic() - started) * 1000
        db = settings.DATABASES.get("default", {})
        services.append({
            "name": "PostgreSQL / RDS",
            "status": "healthy",
            "detail": f"연결됨 · {elapsed:.0f}ms",
            "meta": f"{db.get('NAME', '')} @ {_mask(db.get('HOST', ''), keep=10)}",
        })
    except Exception as exc:  # noqa: BLE001
        services.append({
            "name": "PostgreSQL / RDS",
            "status": "danger",
            "detail": "연결 실패",
            "meta": str(exc)[:200],
        })

    # ---------- Redis ----------
    started = time.monotonic()
    try:
        import redis

        client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL, socket_connect_timeout=1.5
        )
        client.ping()
        elapsed = (time.monotonic() - started) * 1000
        services.append({
            "name": "Redis",
            "status": "healthy",
            "detail": f"응답함 · {elapsed:.0f}ms",
            "meta": _mask(settings.CELERY_BROKER_URL, keep=14),
        })
    except Exception as exc:  # noqa: BLE001
        services.append({
            "name": "Redis",
            "status": "danger",
            "detail": "응답 없음",
            "meta": str(exc)[:200],
        })

    # ---------- S3 ----------
    bucket = _s3_bucket()
    if not bucket:
        services.append({
            "name": "S3",
            "status": "warning",
            "detail": "버킷 미설정",
            "meta": "AWS_STORAGE_BUCKET_NAME 없음",
        })
    else:
        started = time.monotonic()
        try:
            _s3_client().head_bucket(Bucket=bucket)
            elapsed = (time.monotonic() - started) * 1000
            services.append({
                "name": "S3",
                "status": "healthy",
                "detail": f"접근 가능 · {elapsed:.0f}ms",
                "meta": f"{bucket} ({getattr(settings, 'AWS_REGION', '')})",
            })
        except Exception as exc:  # noqa: BLE001
            services.append({
                "name": "S3",
                "status": "danger",
                "detail": "접근 실패",
                "meta": str(exc)[:200],
            })

    # ---------- Celery ----------
    # 워커가 없으면 응답을 타임아웃까지 기다린다. 기본은 건너뛰고
    # ?workers=1 로 요청했을 때만 확인한다. (2026-09-09)
    check_workers = request.GET.get("workers") == "1"

    if not check_workers:
        services.append({
            "name": "Celery Worker",
            "status": "idle",
            "detail": "미확인",
            "meta": "워커 동작 확인 버튼으로 조회합니다.",
        })
    else:
        try:
            _, stats, _ = _inspect_workers()

            if stats:
                services.append({
                    "name": "Celery Worker",
                    "status": "healthy",
                    "detail": f"워커 {len(stats)}대 응답",
                    "meta": ", ".join(sorted(stats)[:3]),
                })
            else:
                services.append({
                    "name": "Celery Worker",
                    "status": "danger",
                    "detail": "응답하는 워커 없음",
                    "meta": "worker/beat 컨테이너가 없어 자동 수집이 동작하지 않습니다.",
                })
        except Exception as exc:  # noqa: BLE001
            services.append({
                "name": "Celery Worker",
                "status": "danger",
                "detail": "확인 실패",
                "meta": str(exc)[:200],
            })

    healthy = sum(1 for s_ in services if s_["status"] == "healthy")

    context = {
        "page_title": "시스템 상태",
        "page_description": "인프라 구성 요소에 직접 접속해 상태를 확인합니다.",
        "services": services,
        "summary": {
            "total": len(services),
            "healthy": healthy,
            "down": sum(1 for s_ in services if s_["status"] == "danger"),
        },
        "counts": {
            "raw_documents": RawDocument.objects.count(),
            "product_sources": ProductSource.objects.count(),
            "content_items": ContentItem.objects.count(),
            "text_documents": TextDocument.objects.count(),
            "crawl_targets": CrawlTarget.objects.count(),
            "dictionary_terms": DictionaryTerm.objects.count(),
        },
        "checked_at": timezone.now(),
        "checked_workers": check_workers,
    }
    return render(request, "dashboard/system/status.html", context)

# ============================================================
# EXISTING BRAND MAPPING
# ============================================================


# ============================================================
# CREATE NEW FEEDIT BRAND
# ============================================================


# ============================================================
# 수집 (COLLECTION)
# ============================================================


@login_required(login_url="/admin-dashboard/login/")
def platform_status(request):
    """플랫폼별 수집 현황.

    소스마다 개별 count()를 돌리면 쿼리가 소스 수에 비례해 늘어난다.
    테이블별로 한 번씩 group by 집계해서 파이썬에서 합친다.
    """

    sources = _ordered_sources()

    target_stats = _group_count(
        CrawlTarget.objects.all(),
        active=Q(is_active=True),
    )
    run_stats = _group_count(
        CrawlRun.objects.all(),
        success=Q(status="SUCCESS"),
        failed=Q(status="FAILED"),
    )
    doc_stats = _group_count(RawDocument.objects.all())

    # 소스별 최근 실행 1건씩 — 한 번의 쿼리로 가져와 앞선 것만 남긴다.
    last_runs = {}
    for run in (
        CrawlRun.objects
        .order_by("source_id", "-started_at")
        .only("id", "source_id", "started_at", "status")
    ):
        last_runs.setdefault(run.source_id, run)

    rows = []
    for source in sources:
        targets = target_stats.get(source.id, {})
        runs = run_stats.get(source.id, {})

        rows.append({
            "source": source,
            "label": source.label,
            "code": source.code,
            "source_type": (
                source.get_source_type_display()
                if hasattr(source, "get_source_type_display")
                else source.source_type
            ),
            "status": source.status,
            "target_count": targets.get("n", 0),
            "active_target_count": targets.get("active", 0),
            "run_count": runs.get("n", 0),
            "success_count": runs.get("success", 0),
            "failed_count": runs.get("failed", 0),
            "doc_count": doc_stats.get(source.id, {}).get("n", 0),
            "last_run": last_runs.get(source.id),
        })

    context = {
        "page_title": "Platform Status",
        "page_description": "플랫폼별 수집 현황",
        "rows": rows,
        "total_targets": sum(r["target_count"] for r in rows),
        "total_runs": sum(r["run_count"] for r in rows),
        "total_docs": sum(r["doc_count"] for r in rows),
    }
    return render(request, "dashboard/collection/platform_status.html", context)




# ============================================================
# 정규화 데이터 (NORMALIZED) — 플랫폼별
# ============================================================


def _qs_without_page(request):
    """페이지네이션 링크에 붙일 쿼리스트링(page 제외)."""
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return (encoded + "&") if encoded else ""


def _qs_without(request, *keys):
    """지정한 키를 뺀 쿼리스트링(page 항상 제외)."""
    params = request.GET.copy()
    params.pop("page", None)
    for key in keys:
        params.pop(key, None)
    encoded = params.urlencode()
    return (encoded + "&") if encoded else ""


def _find_source(*codes):
    """후보 코드 중 실제 존재하는 Source를 찾는다."""
    for code in codes:
        source = Source.objects.filter(code=code).first()
        if source is not None:
            return source
    return None


class _AttrSnapshot:
    """스냅샷 테이블이 비어 있을 때 attributes에서 복원한 대체 지표.

    ProductSourceSnapshot을 적재하는 코드가 아직 없어서, 정규화 때
    attributes에 담아둔 값이라도 보여준다. 실제 스냅샷이 생기면
    그쪽이 우선한다.
    """

    from_attributes = True

    _KEYS = {
        "list_price": ("regular_price", "original_price", "list_price"),
        "sale_price": ("sale_price", "final_sale_price", "price"),
        "discount_rate": ("discount_rate", "discount"),
        "rating": ("rating", "review_score"),
        "review_count": ("review_count", "review_cnt"),
        "like_count": ("like_count", "likes"),
        "rank_position": ("rank_position", "rank"),
        "stock_status": ("stock_status",),
    }

    def __init__(self, attributes):
        pools = [attributes or {}]
        nested = (attributes or {}).get("source_attributes")
        if isinstance(nested, dict):
            pools.append(nested)

        for field, candidates in self._KEYS.items():
            value = None
            for pool in pools:
                for key in candidates:
                    if pool.get(key) not in (None, "", []):
                        value = pool.get(key)
                        break
                if value is not None:
                    break
            setattr(self, field, value)

    def __bool__(self):
        return any(
            getattr(self, field) is not None
            for field in self._KEYS
        )

    # 템플릿에서 참조하지만 대체본에 없는 필드
    observed_at = None
    ranking_scope = None


def _attach_latest_product_snapshot(rows):
    """행 목록에 최신 ProductSourceSnapshot을 붙인다."""
    if not rows:
        return

    latest = {}
    for snap in (
        ProductSourceSnapshot.objects
        .filter(product_source_id__in=[r.id for r in rows])
        .order_by("product_source_id", "-observed_at")
    ):
        latest.setdefault(snap.product_source_id, snap)

    for row in rows:
        snapshot = latest.get(row.id)
        if snapshot is None:
            fallback = _AttrSnapshot(row.attributes)
            snapshot = fallback if fallback else None
        row.latest_snapshot = snapshot


def _attach_latest_content_snapshot(rows):
    """행 목록에 최신 ContentSnapshot을 붙인다."""
    if not rows:
        return

    latest = {}
    for snap in (
        ContentSnapshot.objects
        .filter(content_item_id__in=[r.id for r in rows])
        .order_by("content_item_id", "-observed_at")
    ):
        latest.setdefault(snap.content_item_id, snap)

    for row in rows:
        row.latest_snapshot = latest.get(row.id)


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
    _attach_latest_product_snapshot(rows)

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
        "qs": _qs_without_page(request),
        "qs_sort": _qs_without(request, "order"),
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
    _attach_latest_content_snapshot(rows)

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
        "qs": _qs_without_page(request),
        "qs_sort": _qs_without(request, "order"),
    }

    return render(
        request,
        "dashboard/normalization/platform.html",
        context,
    )


def _platform_page(request, codes, title, description, url_name, mode="commerce"):
    """플랫폼별 정규화 페이지 공통 진입점."""

    source = _find_source(*codes)
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


# ============================================================
# 데이터 분석 (ANALYTICS)
# ============================================================


def _analytics_summary():
    """분석 관련 테이블 요약."""

    metrics = TermMetricDaily.objects.all()

    return {
        "metric_rows": metrics.count(),
        "assoc_rows": TermAssocDaily.objects.count(),
        "terms": DictionaryTerm.objects.count(),
        "aliases": TermAlias.objects.count(),
        "documents": TextDocument.objects.count(),
        "content_items": ContentItem.objects.count(),
        "measured_terms": (
            metrics.values("term_id").distinct().count()
        ),
        "dates": (
            metrics.values("metric_date").distinct().count()
        ),
    }


@login_required(login_url="/admin-dashboard/login/")
def trend_metrics(request):
    """트렌드 지표 — 일자별 용어 지표 상위 집계."""

    summary = _analytics_summary()

    latest_date = (
        TermMetricDaily.objects
        .order_by("-metric_date")
        .values_list("metric_date", flat=True)
        .first()
    )

    top_trend = []
    top_mention = []
    by_type = []
    top_assoc = []

    if latest_date is not None:
        day = TermMetricDaily.objects.filter(metric_date=latest_date)

        top_trend = list(
            day.select_related("term")
            .exclude(trend_score__isnull=True)
            .order_by("-trend_score")[:12]
        )
        top_mention = list(
            day.select_related("term")
            .order_by("-mention_count")[:12]
        )

        max_trend = max(
            [float(r.trend_score or 0) for r in top_trend] or [0]
        )
        for row in top_trend:
            row.pct = (
                round(float(row.trend_score or 0) / max_trend * 100, 1)
                if max_trend else 0
            )

        max_mention = max(
            [r.mention_count or 0 for r in top_mention] or [0]
        )
        for row in top_mention:
            row.pct = (
                round((row.mention_count or 0) / max_mention * 100, 1)
                if max_mention else 0
            )

        by_type = list(
            day.values("term__term_type")
            .annotate(n=Count("id"))
            .order_by("-n")
        )

        top_assoc = list(
            TermAssocDaily.objects
            .filter(metric_date=latest_date)
            .select_related("source_term", "target_term")
            .order_by("-cooccurrence_count")[:15]
        )

    context = {
        "page_title": "트렌드 지표",
        "page_description": (
            "사전 용어의 일자별 언급량과 트렌드 점수를 확인합니다."
        ),
        "summary": summary,
        "latest_date": latest_date,
        "top_trend": top_trend,
        "top_mention": top_mention,
        "by_type": by_type,
        "top_assoc": top_assoc,
    }

    return render(
        request,
        "dashboard/analytics/trend_metrics.html",
        context,
    )


@login_required(login_url="/admin-dashboard/login/")
def term_metrics(request):
    """용어별 지표 — 사전 용어에 최신 지표를 붙여 조회."""

    selected_type = request.GET.get("term_type", "").strip()
    selected_date = request.GET.get("metric_date", "").strip()
    q = request.GET.get("q", "").strip()

    # embedding 은 1536차원 벡터라 행당 수 KB다. 화면에서 쓰지 않으므로 제외한다.
    # (2026-09-09) 이것만으로 이 페이지 조회가 1.5초 -> 0.1초 수준이 된다.
    queryset = DictionaryTerm.objects.defer(
        "embedding", "embedding_updated_at"
    ).order_by("term_type", "canonical_name")

    if selected_type:
        queryset = queryset.filter(term_type=selected_type)

    if q:
        queryset = queryset.filter(
            Q(canonical_name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(term_code__icontains=q)
        )

    if selected_date:
        queryset = queryset.filter(
            daily_metrics__metric_date=selected_date
        ).distinct()

    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = list(page_obj.object_list)

    # 각 용어의 최신(또는 선택된 일자) 지표를 붙인다.
    metric_map = {}
    if rows:
        metric_qs = TermMetricDaily.objects.filter(
            term_id__in=[r.id for r in rows]
        )
        if selected_date:
            metric_qs = metric_qs.filter(metric_date=selected_date)
        for metric in metric_qs.order_by("term_id", "-metric_date"):
            metric_map.setdefault(metric.term_id, metric)

    for row in rows:
        metric = metric_map.get(row.id)
        row.term_text = row.canonical_name
        row.metric_date = metric.metric_date if metric else None
        row.mention_count = metric.mention_count if metric else None
        row.document_count = metric.document_count if metric else None
        row.source_count = metric.source_count if metric else None
        row.growth_rate = metric.growth_rate if metric else None
        row.trend_score = metric.trend_score if metric else None

    dates = (
        TermMetricDaily.objects
        .values_list("metric_date", flat=True)
        .distinct()
        .order_by("-metric_date")[:30]
    )

    context = {
        "page_title": "용어별 지표",
        "page_description": (
            "사전 용어별 언급량·문서수·트렌드 점수를 조회합니다."
        ),
        "summary": _analytics_summary(),
        "term_types": [c[0] for c in DictionaryTerm.TermType.choices],
        "dates": dates,
        "rows": rows,
        "page_obj": page_obj,
        "filtered_count": paginator.count,
        "selected_type": selected_type,
        "selected_date": selected_date,
        "search_query": q,
        "qs": _qs_without_page(request),
    }

    return render(
        request,
        "dashboard/analytics/term_metrics.html",
        context,
    )


PRODUCT_METRIC_ORDER_CHOICES = [
    ("recent", "최근 확인순"),
    ("rank", "랭킹순"),
    ("discount", "할인율 높은순"),
    ("review", "리뷰 많은순"),
    ("price_desc", "판매가 높은순"),
    ("price_asc", "판매가 낮은순"),
]


@login_required(login_url="/admin-dashboard/login/")
def product_metrics(request):
    """상품별 지표 — 플랫폼 상품에 최신 스냅샷 지표를 붙여 조회."""

    selected_source = request.GET.get("source", "").strip()
    selected_order = request.GET.get("order", "recent").strip()
    q = request.GET.get("q", "").strip()

    queryset = (
        ProductSource.objects
        .select_related("source", "source_brand")
        .all()
    )

    if selected_source:
        queryset = queryset.filter(source_id=selected_source)

    if q:
        queryset = queryset.filter(
            Q(source_name__icontains=q)
            | Q(normalized_name__icontains=q)
            | Q(source_product_id__icontains=q)
            | Q(source_brand__name__icontains=q)
        )

    if selected_order == "rank":
        queryset = queryset.annotate(
            v=Min("snapshots__rank_position")
        ).exclude(v__isnull=True).order_by("v")
    elif selected_order == "discount":
        queryset = queryset.annotate(
            v=Max("snapshots__discount_rate")
        ).exclude(v__isnull=True).order_by("-v")
    elif selected_order == "review":
        queryset = queryset.annotate(
            v=Max("snapshots__review_count")
        ).exclude(v__isnull=True).order_by("-v")
    elif selected_order == "price_desc":
        queryset = queryset.annotate(
            v=Max("snapshots__sale_price")
        ).exclude(v__isnull=True).order_by("-v")
    elif selected_order == "price_asc":
        queryset = queryset.annotate(
            v=Min("snapshots__sale_price")
        ).exclude(v__isnull=True).order_by("v")
    else:
        queryset = queryset.order_by("-last_seen_at", "-id")

    paginator = Paginator(queryset, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = list(page_obj.object_list)
    _attach_latest_product_snapshot(rows)

    snapshots = ProductSourceSnapshot.objects.all()

    context = {
        "page_title": "상품별 지표",
        "page_description": (
            "플랫폼 상품의 최신 가격·할인·평점·순위를 조회합니다."
        ),
        "summary": {
            "product_source": ProductSource.objects.count(),
            "snapshot_rows": snapshots.count(),
            "resale_rows": ResaleSnapshot.objects.count(),
            "with_snapshot": (
                snapshots.values("product_source_id").distinct().count()
            ),
            "latest_observed": (
                snapshots.order_by("-observed_at")
                .values_list("observed_at", flat=True)
                .first()
            ),
        },
        "sources": _ordered_sources(),
        "order_choices": PRODUCT_METRIC_ORDER_CHOICES,
        "rows": rows,
        "page_obj": page_obj,
        "filtered_count": paginator.count,
        "selected_source": selected_source,
        "selected_order": selected_order,
        "search_query": q,
        "qs": _qs_without_page(request),
    }

    return render(
        request,
        "dashboard/analytics/product_metrics.html",
        context,
    )


@login_required(login_url="/admin-dashboard/login/")
def product_snapshot(request):
    """상품 스냅샷 — 관측 시점별 원본 지표 행."""

    selected_source = request.GET.get("source", "").strip()
    q = request.GET.get("q", "").strip()

    queryset = (
        ProductSourceSnapshot.objects
        .select_related(
            "product_source",
            "product_source__source",
        )
        .order_by("-observed_at", "-id")
    )

    if selected_source:
        queryset = queryset.filter(
            product_source__source_id=selected_source
        )

    if q:
        queryset = queryset.filter(
            Q(product_source__source_name__icontains=q)
            | Q(product_source__source_product_id__icontains=q)
        )

    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    snapshots = ProductSourceSnapshot.objects.all()

    daily_counts = list(
        snapshots
        .annotate(day=TruncDate("observed_at"))
        .values("day")
        .annotate(n=Count("id"))
        .order_by("-day")[:14]
    )

    context = {
        "page_title": "상품 스냅샷",
        "page_description": (
            "관측 시점별로 쌓인 상품 지표 원본을 조회합니다."
        ),
        "summary": {
            "snapshot_rows": snapshots.count(),
            "resale_rows": ResaleSnapshot.objects.count(),
            "content_rows": ContentSnapshot.objects.count(),
            "observed_days": (
                snapshots
                .annotate(day=TruncDate("observed_at"))
                .values("day")
                .distinct()
                .count()
            ),
            "latest_observed": (
                snapshots.order_by("-observed_at")
                .values_list("observed_at", flat=True)
                .first()
            ),
        },
        "daily_counts": daily_counts,
        "sources": _ordered_sources(),
        "rows": page_obj.object_list,
        "page_obj": page_obj,
        "filtered_count": paginator.count,
        "selected_source": selected_source,
        "search_query": q,
        "qs": _qs_without_page(request),
    }

    return render(
        request,
        "dashboard/analytics/product_snapshot.html",
        context,
    )



# ============================================================
# 시스템 (SYSTEM)
# ============================================================




# ============================================================
# 브랜드 매핑 해제 / 제외
# ============================================================


# ============================================================
# 브랜드 매핑 (메인 레포 구현 채택)
# ============================================================


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


# ============================================================
# 인증 (LOGIN / LOGOUT)
# ============================================================


def dashboard_login(request):
    """관리자 대시보드 로그인."""

    if request.user.is_authenticated:
        return redirect("dashboard:dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:
            messages.error(
                request,
                "아이디 또는 비밀번호가 올바르지 않습니다.",
            )

        elif not (user.is_staff or user.is_superuser):
            messages.error(
                request,
                "관리자 권한이 없는 계정입니다.",
            )

        else:
            login(request, user)

            next_url = (
                request.GET.get("next")
                or request.POST.get("next")
            )

            if next_url and next_url.startswith("/"):
                return redirect(next_url)

            return redirect("dashboard:dashboard")

    return render(
        request,
        "dashboard/login.html",
        {"next": request.GET.get("next", "")},
    )


def dashboard_logout(request):
    """로그아웃 후 로그인 화면으로."""

    logout(request)
    return redirect("dashboard:login")


# ============================================================
# 수집 실행 / 규칙 / robots.txt
# ============================================================

ROBOTS_S3_PREFIX = "config/robots/"


def _s3_client():
    return boto3.client("s3", region_name=getattr(settings, "AWS_REGION", None))


def _s3_bucket():
    return getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)


class _ConsoleLogHandler(logging.Handler):
    """실행 중 발생한 로그를 콘솔 출력용으로 모은다."""

    MAX_RECORDS = 400

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        if len(self.records) >= self.MAX_RECORDS:
            return
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            message = str(record.msg)

        if record.exc_info:
            message += "\n" + "".join(
                traceback.format_exception(*record.exc_info)
            ).rstrip()

        self.records.append({
            "time": timezone.localtime(
                datetime.fromtimestamp(record.created, tz=dt_timezone.utc)
            ).strftime("%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        })


def _console_line(level, message):
    return {
        "time": timezone.localtime().strftime("%H:%M:%S"),
        "level": level,
        "logger": "dashboard",
        "message": message,
    }


@login_required(login_url="/admin-dashboard/login/")
def run_crawl(request):
    """수동 크롤링 실행."""

    if request.method == "POST":
        target_ids = [
            value for value in request.POST.getlist("target") if value.strip()
        ]
        mode = (request.POST.get("mode") or "sync").strip()

        targets = list(
            CrawlTarget.objects
            .select_related("source")
            .filter(id__in=target_ids)
            .order_by("source__code", "name")
        )

        if not targets:
            messages.error(request, "실행할 수집 대상을 하나 이상 선택해주세요.")
            return redirect("dashboard:run_crawl")

        from apps.core.tasks import run_live_target

        console = [
            _console_line(
                "INFO",
                f"선택한 대상 {len(targets)}건 · "
                + ("큐 등록" if mode == "queue" else "즉시 실행"),
            ),
        ]

        ok_count = 0
        fail_count = 0
        batch_started = time.monotonic()

        for index, target in enumerate(targets, start=1):
            console.append(_console_line(
                "INFO",
                f"[{index}/{len(targets)}] #{target.id} "
                f"[{target.source.code}] {target.name}",
            ))

            handler = _ConsoleLogHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            previous_level = root_logger.level
            if previous_level > logging.INFO or previous_level == logging.NOTSET:
                root_logger.setLevel(logging.INFO)

            started = time.monotonic()

            try:
                if mode == "queue":
                    async_result = run_live_target.delay(target.id)
                    console.append(_console_line(
                        "INFO", f"    큐 등록 완료 · task_id={async_result.id}",
                    ))
                    ok_count += 1
                else:
                    result = run_live_target.apply(args=[target.id])
                    payload = result.result

                    if result.failed():
                        console.append(_console_line(
                            "ERROR", f"    실패: {payload}",
                        ))
                        fail_count += 1
                    else:
                        console.append(_console_line(
                            "INFO", f"    결과: {payload}",
                        ))
                        ok_count += 1

            except Exception as exc:  # noqa: BLE001
                console.append(_console_line(
                    "ERROR", f"    {type(exc).__name__}: {exc}",
                ))
                fail_count += 1

            finally:
                root_logger.removeHandler(handler)
                root_logger.setLevel(previous_level)

            console.extend(handler.records)
            console.append(_console_line(
                "INFO", f"    소요 {time.monotonic() - started:.2f}초",
            ))

        elapsed = time.monotonic() - batch_started
        console.append(_console_line(
            "INFO",
            f"전체 완료 — 성공 {ok_count}건 · 실패 {fail_count}건 · "
            f"총 {elapsed:.2f}초",
        ))

        if fail_count and ok_count:
            messages.warning(
                request,
                f"{len(targets)}건 중 {ok_count}건 성공, {fail_count}건 실패했습니다.",
            )
        elif fail_count:
            messages.error(request, f"{fail_count}건 모두 실패했습니다.")
        else:
            messages.success(
                request,
                f"{ok_count}건을 "
                + ("큐에 등록했습니다." if mode == "queue" else "실행했습니다."),
            )

        if len(targets) == 1:
            label = f"{targets[0].source.code} · {targets[0].name}"
        else:
            label = f"{len(targets)}개 대상"

        request.session["run_console"] = console[-800:]
        request.session["run_console_target"] = label

        return redirect("dashboard:run_crawl")

        from apps.core.tasks import run_live_target

        console = [
            _console_line(
                "INFO",
                f"수집 대상 #{target.id} [{target.source.code}] {target.name}",
            ),
            _console_line(
                "INFO",
                "실행 방식: " + ("큐 등록" if mode == "queue" else "즉시 실행"),
            ),
        ]

        handler = _ConsoleLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        previous_level = root_logger.level
        if previous_level > logging.INFO or previous_level == logging.NOTSET:
            root_logger.setLevel(logging.INFO)

        started = time.monotonic()

        try:
            if mode == "queue":
                async_result = run_live_target.delay(target.id)
                console.append(_console_line(
                    "INFO", f"큐에 등록했습니다. task_id={async_result.id}",
                ))
                messages.success(
                    request,
                    f"'{target.name}' 을(를) 큐에 등록했습니다.",
                )
            else:
                result = run_live_target.apply(args=[target.id])
                payload = result.result

                if result.failed():
                    console.append(_console_line(
                        "ERROR", f"실행 실패: {payload}",
                    ))
                    messages.error(
                        request,
                        f"'{target.name}' 실행 중 오류가 발생했습니다.",
                    )
                else:
                    console.append(_console_line(
                        "INFO", f"실행 결과: {payload}",
                    ))
                    messages.success(
                        request,
                        f"'{target.name}' 실행이 완료되었습니다.",
                    )

        except Exception as exc:  # noqa: BLE001
            console.append(_console_line("ERROR", f"{type(exc).__name__}: {exc}"))
            messages.error(request, f"실행에 실패했습니다: {exc}")

        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(previous_level)

        console.extend(handler.records)
        console.append(_console_line(
            "INFO", f"소요 시간 {time.monotonic() - started:.2f}초",
        ))

        request.session["run_console"] = console[-400:]
        request.session["run_console_target"] = f"{target.source.code} · {target.name}"

        return redirect("dashboard:run_crawl")

    targets = (
        CrawlTarget.objects
        .select_related("source")
        .order_by("source__code", "name")
    )

    selected_source = request.GET.get("source", "").strip()
    if selected_source:
        targets = targets.filter(source_id=selected_source)

    recent = (
        CrawlRun.objects
        .select_related("source", "crawl_target")
        .filter(run_type="MANUAL")
        .order_by("-started_at", "-id")[:10]
    )

    context = {
        "page_title": "수동 크롤링 실행",
        "page_description": (
            "등록된 수집 대상을 지금 바로 실행합니다."
        ),
        "targets": targets,
        "sources": _ordered_sources(),
        "selected_source": selected_source,
        "recent_runs": recent,
        "console_lines": request.session.pop("run_console", []),
        "console_target": request.session.pop("run_console_target", ""),
        "summary": {
            "target_total": CrawlTarget.objects.count(),
            "target_active": CrawlTarget.objects.filter(is_active=True).count(),
            "manual_runs": CrawlRun.objects.filter(run_type="MANUAL").count(),
            "running": CrawlRun.objects.filter(status="RUNNING").count(),
        },
    }

    return render(request, "dashboard/collection/run.html", context)


@login_required(login_url="/admin-dashboard/login/")
def crawl_rules(request):
    """크롤링 규칙 — 주기·우선순위·수집 모드를 한눈에 본다."""

    now = timezone.now()

    targets = (
        CrawlTarget.objects
        .select_related("source")
        .order_by("source__code", "-priority", "name")
    )

    selected_source = request.GET.get("source", "").strip()
    if selected_source:
        targets = targets.filter(source_id=selected_source)

    rows = list(targets)
    for row in rows:
        row.is_due = (
            row.is_active
            and row.collection_mode == "LIVE"
            and (row.next_crawl_at is None or row.next_crawl_at <= now)
        )

    # 주기별 분포
    by_interval = (
        CrawlTarget.objects
        .values("interval_minutes")
        .annotate(n=Count("id"))
        .order_by("interval_minutes")
    )

    beat_schedule = []
    try:
        from config.celery import app as celery_app

        for name, conf in (celery_app.conf.beat_schedule or {}).items():
            beat_schedule.append({
                "name": name,
                "task": conf.get("task"),
                "schedule": conf.get("schedule"),
            })
    except Exception:  # noqa: BLE001
        beat_schedule = []

    context = {
        "page_title": "크롤링 규칙",
        "page_description": (
            "수집 대상별 실행 주기와 우선순위를 확인합니다."
        ),
        "rows": rows,
        "sources": _ordered_sources(),
        "selected_source": selected_source,
        "by_interval": by_interval,
        "beat_schedule": beat_schedule,
        "now": now,
        "summary": {
            "total": CrawlTarget.objects.count(),
            "active": CrawlTarget.objects.filter(is_active=True).count(),
            "live": CrawlTarget.objects.filter(collection_mode="LIVE").count(),
            "due": sum(1 for r in rows if r.is_due),
        },
    }

    return render(request, "dashboard/collection/rules.html", context)


@login_required(login_url="/admin-dashboard/login/")
def robots_check(request):
    """robots.txt 관리 — 사이트별 파일을 올려두고 내용을 확인한다.

    새 테이블을 만들지 않기 위해 S3(config/robots/)에 보관한다.
    """

    bucket = _s3_bucket()

    # ---------- 업로드 / 삭제 ----------
    if request.method == "POST":
        action = request.POST.get("action", "upload")

        if not bucket:
            messages.error(request, "S3 버킷이 설정되어 있지 않습니다.")
            return redirect("dashboard:robots_check")

        try:
            client = _s3_client()

            if action == "delete":
                host = (request.POST.get("host") or "").strip()
                if host:
                    client.delete_object(
                        Bucket=bucket,
                        Key=f"{ROBOTS_S3_PREFIX}{host}.txt",
                    )
                    messages.success(request, f"{host} 의 robots.txt를 삭제했습니다.")

            else:
                host = (request.POST.get("host") or "").strip().lower()
                upload = request.FILES.get("robots_file")
                pasted = (request.POST.get("robots_text") or "").strip()

                host = host.replace("https://", "").replace("http://", "").strip("/")

                if not host:
                    messages.error(request, "사이트 도메인을 입력해주세요.")
                    return redirect("dashboard:robots_check")

                if upload is not None:
                    body = upload.read()
                elif pasted:
                    body = pasted.encode("utf-8")
                else:
                    messages.error(request, "파일을 올리거나 내용을 붙여넣어주세요.")
                    return redirect("dashboard:robots_check")

                if len(body) > 512 * 1024:
                    messages.error(request, "robots.txt가 너무 큽니다. (512KB 초과)")
                    return redirect("dashboard:robots_check")

                client.put_object(
                    Bucket=bucket,
                    Key=f"{ROBOTS_S3_PREFIX}{host}.txt",
                    Body=body,
                    ContentType="text/plain; charset=utf-8",
                )
                messages.success(request, f"{host} 의 robots.txt를 저장했습니다.")

        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"처리에 실패했습니다: {exc}")

        return redirect("dashboard:robots_check")

    # ---------- 목록 ----------
    entries = []
    error = None

    if not bucket:
        error = "AWS_STORAGE_BUCKET_NAME 이 설정되어 있지 않습니다."
    else:
        try:
            client = _s3_client()
            listing = client.list_objects_v2(
                Bucket=bucket,
                Prefix=ROBOTS_S3_PREFIX,
                MaxKeys=200,
            )
            for obj in listing.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".txt"):
                    continue
                entries.append({
                    "host": key[len(ROBOTS_S3_PREFIX):-4],
                    "key": key,
                    "size": obj["Size"],
                    "updated_at": obj["LastModified"],
                })
            entries.sort(key=lambda e: e["host"])
        except Exception as exc:  # noqa: BLE001
            error = f"S3 조회에 실패했습니다: {exc}"

    # ---------- 선택한 사이트 내용 ----------
    selected_host = request.GET.get("host", "").strip()
    content = None
    parsed = None

    if selected_host and bucket and not error:
        try:
            client = _s3_client()
            obj = client.get_object(
                Bucket=bucket,
                Key=f"{ROBOTS_S3_PREFIX}{selected_host}.txt",
            )
            content = obj["Body"].read().decode("utf-8", errors="replace")
            parsed = _parse_robots(content)
        except Exception as exc:  # noqa: BLE001
            error = f"파일을 읽지 못했습니다: {exc}"

    context = {
        "page_title": "robots.txt",
        "page_description": (
            "사이트별 robots.txt를 등록하고 수집 허용 범위를 확인합니다."
        ),
        "entries": entries,
        "selected_host": selected_host,
        "content": content,
        "parsed": parsed,
        "error": error,
        "bucket": bucket,
        "prefix": ROBOTS_S3_PREFIX,
    }

    return render(request, "dashboard/collection/robots.html", context)


def _parse_robots(text):
    """robots.txt를 User-agent 그룹 단위로 쪼갠다."""

    groups = []
    current = None

    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue

        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()

        if field == "user-agent":
            if current is None or current["rules"]:
                current = {"agents": [], "rules": []}
                groups.append(current)
            current["agents"].append(value)
        elif current is not None and field in (
            "allow", "disallow", "crawl-delay",
        ):
            current["rules"].append({"field": field, "value": value})
        elif field == "sitemap":
            groups.append({"agents": ["(sitemap)"], "rules": [
                {"field": "sitemap", "value": value}
            ]})
            current = None

    return groups


# ============================================================
# 시스템 (SYSTEM)
# ============================================================


def _inspect_workers(timeout=0.6):
    """Celery 워커 상태를 조회한다.

    워커가 없으면 브로커 응답을 타임아웃까지 기다리느라 수 초가 걸린다.
    그래서 기본 화면에서는 호출하지 않고, 사용자가 요청할 때만 부른다.
    (2026-09-09 — 이 호출 때문에 시스템 페이지가 6초씩 걸렸다)
    """
    from config.celery import app as celery_app

    inspector = celery_app.control.inspect(timeout=timeout)
    stats = inspector.stats() or {}
    active = (inspector.active() or {}) if stats else {}
    return celery_app, stats, active


def _mask(value, keep=4):
    """민감한 값을 마스킹한다."""
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= keep:
        return "*" * len(text)
    return text[:keep] + "*" * min(len(text) - keep, 12)


@login_required(login_url="/admin-dashboard/login/")
def system_api(request):
    """API 관리 — 외부 API 키 설정 상태와 플랫폼별 호출 결과."""

    env_keys = [
        ("YOUTUBE_API_KEY", "YouTube Data API v3"),
        ("OPENAI_API_KEY", "OpenAI (임베딩)"),
        ("AWS_ACCESS_KEY_ID", "AWS 액세스 키"),
        ("AWS_SECRET_ACCESS_KEY", "AWS 시크릿 키"),
        ("AWS_STORAGE_BUCKET_NAME", "S3 버킷"),
        ("AWS_REGION", "AWS 리전"),
        ("CELERY_BROKER_URL", "Celery 브로커"),
    ]

    env_rows = []
    for key, label in env_keys:
        value = os.getenv(key) or getattr(settings, key, "")
        env_rows.append({
            "key": key,
            "label": label,
            "is_set": bool(value),
            "masked": _mask(value),
        })

    # 플랫폼별 호출 결과 — 집계 2회 + 최근 실행 1회로 처리한다.
    run_stats = _group_count(
        CrawlRun.objects.all(),
        success=Q(status="SUCCESS"),
        failed=Q(status="FAILED"),
    )

    last_runs = {}
    for run in (
        CrawlRun.objects
        .order_by("source_id", "-started_at")
        .only("id", "source_id", "started_at")
    ):
        last_runs.setdefault(run.source_id, run)

    source_rows = []
    for source in _ordered_sources():
        stat = run_stats.get(source.id, {})
        total = stat.get("n", 0)
        success = stat.get("success", 0)

        source_rows.append({
            "source": source,
            "label": source.label,
            "total": total,
            "success": success,
            "failed": stat.get("failed", 0),
            "success_rate": round(success / total * 100, 1) if total else None,
            "last_run": last_runs.get(source.id),
        })

    context = {
        "page_title": "API 관리",
        "page_description": (
            "외부 API 설정 상태와 플랫폼별 호출 결과를 확인합니다."
        ),
        "env_rows": env_rows,
        "source_rows": source_rows,
        "summary": {
            "configured": sum(1 for r in env_rows if r["is_set"]),
            "total_keys": len(env_rows),
            "sources": len(source_rows),
        },
    }

    return render(request, "dashboard/system/api.html", context)


@login_required(login_url="/admin-dashboard/login/")
def system_aws(request):
    """AWS 관리 — S3 적재 현황과 접속 설정."""

    bucket = _s3_bucket()
    prefixes = ["raw/", "processed/", "exports/", "reports/", "images/", ROBOTS_S3_PREFIX]

    prefix_rows = []
    error = None
    top_level = []

    if not bucket:
        error = "AWS_STORAGE_BUCKET_NAME 이 설정되어 있지 않습니다."
    else:
        try:
            client = _s3_client()

            listing = client.list_objects_v2(
                Bucket=bucket, Delimiter="/", MaxKeys=100,
            )
            top_level = [
                p["Prefix"] for p in listing.get("CommonPrefixes", [])
            ]

            for prefix in prefixes:
                paginator = client.get_paginator("list_objects_v2")
                count = 0
                size = 0
                latest = None

                for page in paginator.paginate(
                    Bucket=bucket,
                    Prefix=prefix,
                    PaginationConfig={"MaxItems": 2000},
                ):
                    for obj in page.get("Contents", []):
                        count += 1
                        size += obj["Size"]
                        if latest is None or obj["LastModified"] > latest:
                            latest = obj["LastModified"]

                prefix_rows.append({
                    "prefix": prefix,
                    "count": count,
                    "size_mb": round(size / 1024 / 1024, 2),
                    "latest": latest,
                    "capped": count >= 2000,
                })

        except Exception as exc:  # noqa: BLE001
            error = f"S3 조회에 실패했습니다: {exc}"

    db = settings.DATABASES.get("default", {})

    context = {
        "page_title": "AWS 관리",
        "page_description": "S3 적재 현황과 인프라 접속 설정을 확인합니다.",
        "bucket": bucket,
        "region": getattr(settings, "AWS_REGION", ""),
        "prefix_rows": prefix_rows,
        "top_level": top_level,
        "error": error,
        "db_info": {
            "engine": db.get("ENGINE", "").split(".")[-1],
            "name": db.get("NAME", ""),
            "host": _mask(db.get("HOST", ""), keep=10),
            "port": db.get("PORT", ""),
            "user": _mask(db.get("USER", ""), keep=3),
        },
        "raw_documents": RawDocument.objects.count(),
        "latest_document": (
            RawDocument.objects.order_by("-collected_at").first()
        ),
    }

    return render(request, "dashboard/system/aws.html", context)


@login_required(login_url="/admin-dashboard/login/")
def system_celery(request):
    """Celery 로그 — 워커 상태와 작업 실행 이력."""

    workers = []
    beat_schedule = []
    celery_error = None
    broker = ""
    backend = ""

    # 워커 조회는 응답 대기가 길어 기본 화면에서는 하지 않는다. (2026-09-09)
    check_workers = request.GET.get("workers") == "1"

    try:
        from config.celery import app as celery_app

        broker = _mask(celery_app.conf.broker_url, keep=14)
        backend = _mask(celery_app.conf.result_backend, keep=14)

        for name, conf in (celery_app.conf.beat_schedule or {}).items():
            beat_schedule.append({
                "name": name,
                "task": conf.get("task"),
                "schedule": conf.get("schedule"),
            })

        stats, active = ({}, {})
        if check_workers:
            _, stats, active = _inspect_workers()

        for worker_name, info in stats.items():
            workers.append({
                "name": worker_name,
                "pool": (info.get("pool") or {}).get("max-concurrency"),
                "active": len(active.get(worker_name, [])),
                "total": sum((info.get("total") or {}).values()),
            })

    except Exception as exc:  # noqa: BLE001
        celery_error = str(exc)

    # 멈춘 채 남아 있는 실행
    stale_cutoff = timezone.now() - timedelta(hours=1)
    stale_runs = (
        CrawlRun.objects
        .select_related("source", "crawl_target")
        .filter(status="RUNNING", started_at__lt=stale_cutoff)
        .order_by("-started_at")[:20]
    )

    recent_runs = (
        CrawlRun.objects
        .select_related("source", "crawl_target")
        .exclude(celery_task_id="")
        .exclude(celery_task_id__isnull=True)
        .order_by("-started_at", "-id")[:15]
    )

    context = {
        "page_title": "Celery 작업 로그",
        "page_description": (
            "워커 상태와 비동기 작업 실행 이력을 확인합니다."
        ),
        "workers": workers,
        "beat_schedule": beat_schedule,
        "celery_error": celery_error,
        "checked_workers": check_workers,
        "broker": broker,
        "backend": backend,
        "stale_runs": stale_runs,
        "recent_runs": recent_runs,
        "summary": {
            "workers": len(workers),
            "running": CrawlRun.objects.filter(status="RUNNING").count(),
            "stale": stale_runs.count(),
            "queued_tasks": (
                CrawlRun.objects
                .exclude(celery_task_id="")
                .exclude(celery_task_id__isnull=True)
                .count()
            ),
        },
    }

    return render(request, "dashboard/system/celery.html", context)
