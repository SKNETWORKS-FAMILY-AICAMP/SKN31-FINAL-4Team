from __future__ import annotations

import boto3
import json
import logging
import os
import time
import traceback
from django.views.decorators.http import require_POST
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
    Prefetch,
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
    ConsoleLogHandler,
    ROBOTS_S3_PREFIX,
    console_line,
    group_count,
    ordered_sources,
    s3_bucket,
    s3_client,
    source_label,
    search_product_categories,
    get_category_source_queryset,
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


@login_required(login_url="/admin-dashboard/login/")
def raw_documents(request):
    sources = ordered_sources()
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
        doc.platform_label = source_label(doc.source)

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


@login_required(login_url="/admin-dashboard/login/")
def platform_status(request):
    """플랫폼별 수집 현황.

    소스마다 개별 count()를 돌리면 쿼리가 소스 수에 비례해 늘어난다.
    테이블별로 한 번씩 group by 집계해서 파이썬에서 합친다.
    """

    sources = ordered_sources()

    target_stats = group_count(
        CrawlTarget.objects.all(),
        active=Q(is_active=True),
    )
    run_stats = group_count(
        CrawlRun.objects.all(),
        success=Q(status="SUCCESS"),
        failed=Q(status="FAILED"),
    )
    doc_stats = group_count(RawDocument.objects.all())

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
            console_line(
                "INFO",
                f"선택한 대상 {len(targets)}건 · "
                + ("큐 등록" if mode == "queue" else "즉시 실행"),
            ),
        ]

        ok_count = 0
        fail_count = 0
        batch_started = time.monotonic()

        for index, target in enumerate(targets, start=1):
            console.append(console_line(
                "INFO",
                f"[{index}/{len(targets)}] #{target.id} "
                f"[{target.source.code}] {target.name}",
            ))

            handler = ConsoleLogHandler()
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
                    console.append(console_line(
                        "INFO", f"    큐 등록 완료 · task_id={async_result.id}",
                    ))
                    ok_count += 1
                else:
                    result = run_live_target.apply(args=[target.id])
                    payload = result.result

                    if result.failed():
                        console.append(console_line(
                            "ERROR", f"    실패: {payload}",
                        ))
                        fail_count += 1
                    else:
                        console.append(console_line(
                            "INFO", f"    결과: {payload}",
                        ))
                        ok_count += 1

            except Exception as exc:  # noqa: BLE001
                console.append(console_line(
                    "ERROR", f"    {type(exc).__name__}: {exc}",
                ))
                fail_count += 1

            finally:
                root_logger.removeHandler(handler)
                root_logger.setLevel(previous_level)

            console.extend(handler.records)
            console.append(console_line(
                "INFO", f"    소요 {time.monotonic() - started:.2f}초",
            ))

        elapsed = time.monotonic() - batch_started
        console.append(console_line(
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
            console_line(
                "INFO",
                f"수집 대상 #{target.id} [{target.source.code}] {target.name}",
            ),
            console_line(
                "INFO",
                "실행 방식: " + ("큐 등록" if mode == "queue" else "즉시 실행"),
            ),
        ]

        handler = ConsoleLogHandler()
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
                console.append(console_line(
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
                    console.append(console_line(
                        "ERROR", f"실행 실패: {payload}",
                    ))
                    messages.error(
                        request,
                        f"'{target.name}' 실행 중 오류가 발생했습니다.",
                    )
                else:
                    console.append(console_line(
                        "INFO", f"실행 결과: {payload}",
                    ))
                    messages.success(
                        request,
                        f"'{target.name}' 실행이 완료되었습니다.",
                    )

        except Exception as exc:  # noqa: BLE001
            console.append(console_line("ERROR", f"{type(exc).__name__}: {exc}"))
            messages.error(request, f"실행에 실패했습니다: {exc}")

        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(previous_level)

        console.extend(handler.records)
        console.append(console_line(
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
        "sources": ordered_sources(),
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
        "sources": ordered_sources(),
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

    bucket = s3_bucket()

    # ---------- 업로드 / 삭제 ----------
    if request.method == "POST":
        action = request.POST.get("action", "upload")

        if not bucket:
            messages.error(request, "S3 버킷이 설정되어 있지 않습니다.")
            return redirect("dashboard:robots_check")

        try:
            client = s3_client()

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
            client = s3_client()
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
            client = s3_client()
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


@login_required(login_url="/admin-dashboard/login/")
def category_mapping(request):
    source_id = request.GET.get("source", "").strip()
    mapping_status = request.GET.get("status", "unmapped").strip()
    search = request.GET.get("q", "").strip()

    qs = get_category_source_queryset(
        source_id=source_id or None,
        mapping_status=mapping_status or None,
        search=search or None,
    )

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    sources = Source.objects.order_by("name")

    return render(
        request,
        "dashboard/collection/category_mapping.html",
        {
            "page_title": "카테고리 매핑",

            "category_sources": page_obj.object_list,
            "page_obj": page_obj,

            "sources": sources,
            "selected_source": source_id,
            "selected_status": mapping_status,
            "search_query": search,
        },
    )

@login_required(login_url="/admin-dashboard/login/")
def category_mapping_search(request):
    query = request.GET.get("q", "").strip()

    categories = search_product_categories(query)

    results = []

    for category in categories:
        if category.parent:
            label = (
                f"[PRODUCT] "
                f"{category.parent.name} > {category.name}"
            )
        else:
            label = f"[PRODUCT] {category.name}"

        results.append({
            "id": category.id,
            "code": category.code,
            "name": category.name,
            "label": label,
        })

    return JsonResponse({
        "results": results,
    })



@login_required(login_url="/admin-dashboard/login/")
@require_POST
def category_mapping_save(request, source_id):
    category_source = get_object_or_404(
        CategorySource,
        pk=source_id,
    )

    category_id = request.POST.get("category_id", "").strip()

    if category_id:
        category = get_object_or_404(
            Category,
            pk=category_id,
            category_type="PRODUCT",  # ← PRODUCT만 허용
        )

        category_source.category = category

    else:
        category_source.category = None

    category_source.save(
        update_fields=["category"],
    )

    return JsonResponse({
        "ok": True,
        "mapped_id": category_source.category_id,
        "mapped_label": (
            category_source.category.name
            if category_source.category_id
            else None
        ),
    })


# ============================================================
# BRAND MAPPING
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
