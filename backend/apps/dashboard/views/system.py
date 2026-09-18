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
    group_count,
    inspect_workers,
    mask,
    ordered_sources,
    s3_bucket,
    s3_client,
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

    run_stats = group_count(
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
    for source in ordered_sources():
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
            "meta": f"{db.get('NAME', '')} @ {mask(db.get('HOST', ''), keep=10)}",
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
            "meta": mask(settings.CELERY_BROKER_URL, keep=14),
        })
    except Exception as exc:  # noqa: BLE001
        services.append({
            "name": "Redis",
            "status": "danger",
            "detail": "응답 없음",
            "meta": str(exc)[:200],
        })

    # ---------- S3 ----------
    bucket = s3_bucket()
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
            s3_client().head_bucket(Bucket=bucket)
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
            _, stats, _ = inspect_workers()

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
            "masked": mask(value),
        })

    # 플랫폼별 호출 결과 — 집계 2회 + 최근 실행 1회로 처리한다.
    run_stats = group_count(
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
    for source in ordered_sources():
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

    bucket = s3_bucket()
    prefixes = ["raw/", "processed/", "exports/", "reports/", "images/", ROBOTS_S3_PREFIX]

    prefix_rows = []
    error = None
    top_level = []

    if not bucket:
        error = "AWS_STORAGE_BUCKET_NAME 이 설정되어 있지 않습니다."
    else:
        try:
            client = s3_client()

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
            "host": mask(db.get("HOST", ""), keep=10),
            "port": db.get("PORT", ""),
            "user": mask(db.get("USER", ""), keep=3),
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

        broker = mask(celery_app.conf.broker_url, keep=14)
        backend = mask(celery_app.conf.result_backend, keep=14)

        for name, conf in (celery_app.conf.beat_schedule or {}).items():
            beat_schedule.append({
                "name": name,
                "task": conf.get("task"),
                "schedule": conf.get("schedule"),
            })

        stats, active = ({}, {})
        if check_workers:
            _, stats, active = inspect_workers()

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
