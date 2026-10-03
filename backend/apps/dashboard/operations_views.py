"""운영 대시보드의 파이프라인·서비스·데이터베이스 읽기 화면.

모든 URL은 dashboard middleware의 staff 검사를 거친다. 개인정보 원문과 인증
정보는 이 모듈에서 조회하지 않으며, SQL 콘솔도 읽기 전용 트랜잭션과 제한된
테이블 집합만 허용한다.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict

import sqlparse
from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count, DateTimeField, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render

from apps.core.models import (
    AppUser,
    ContentItem,
    CrawlRun,
    Product,
    ProductSource,
    RawDocument,
    TermAssocDaily,
    TermMetricDaily,
    TermSearchMetricMonthly,
    TextDocument,
    TextTermMention,
    UserEvent,
    UserSavedItem,
    VoteBallot,
    VoteCard,
    VoteComment,
    VoteReport,
)
from apps.api.images import absolute_image_url
from apps.api.salmal_storage import vote_image_url

LOGIN_URL = "/admin-dashboard/login/"
PAGE_SIZE = 30


def _nickname(profile):
    return (profile.nickname or f"회원 #{profile.pk}") if profile else "(탈퇴한 사용자)"


@login_required(login_url=LOGIN_URL)
def pipeline_overview(request):
    """비싼 전체 count를 요청마다 반복하지 않는 파이프라인 개요."""

    cache_key = "dashboard:pipeline-overview:v2"
    payload = cache.get(cache_key)
    if payload is None:
        raw_total = RawDocument.objects.count()
        product_sources = ProductSource.objects.count()
        content_items = ContentItem.objects.count()
        normalized_total = product_sources + content_items
        text_total = TextDocument.objects.count()
        text_done = TextDocument.objects.filter(
            analysis_status=TextDocument.AnalysisStatus.DONE
        ).count()
        mentions = TextTermMention.objects.count()
        metric_total = TermMetricDaily.objects.count() + TermAssocDaily.objects.count()
        search_total = TermSearchMetricMonthly.objects.count()
        failed_runs = CrawlRun.objects.filter(status=CrawlRun.Status.FAILED).count()
        running_runs = CrawlRun.objects.filter(status=CrawlRun.Status.RUNNING).count()

        stages = [
            {"label": "원본 수집", "value": raw_total, "caption": "RawDocument", "url": "dashboard:raw_documents"},
            {"label": "정규화", "value": normalized_total, "caption": f"상품 {product_sources:,} · 콘텐츠 {content_items:,}", "url": "dashboard:normalized_products"},
            {"label": "텍스트 분석", "value": text_total, "caption": f"완료 {text_done:,}", "url": "dashboard:text_youtube"},
            {"label": "검증 키워드", "value": mentions, "caption": "TextTermMention", "url": "dashboard:term_metrics"},
            {"label": "트렌드 지표", "value": metric_total, "caption": f"검색 지표 {search_total:,}", "url": "dashboard:trend_metrics"},
        ]
        payload = {
            "stages": stages,
            "raw_total": raw_total,
            "normalized_total": normalized_total,
            "text_total": text_total,
            "text_done": text_done,
            "mentions": mentions,
            "metric_total": metric_total,
            "failed_runs": failed_runs,
            "running_runs": running_runs,
            "health": "attention" if failed_runs else ("running" if running_runs else "stable"),
        }
        cache.set(cache_key, payload, 60)

    return render(request, "dashboard/operations/pipeline.html", payload)


@login_required(login_url=LOGIN_URL)
def service_users(request):
    q = request.GET.get("q", "").strip()

    def related_count(model, user_field="user"):
        return Subquery(
            model.objects.filter(**{user_field: OuterRef("pk")})
            .values(user_field)
            .annotate(n=Count("pk"))
            .values("n")[:1],
            output_field=IntegerField(),
        )

    last_event = Subquery(
        UserEvent.objects.filter(user=OuterRef("pk"))
        .order_by("-created_at")
        .values("created_at")[:1],
        output_field=DateTimeField(),
    )
    rows = (
        AppUser.objects.annotate(
            event_count=Coalesce(related_count(UserEvent), Value(0)),
            vote_count=Coalesce(related_count(VoteBallot), Value(0)),
            card_count=Coalesce(related_count(VoteCard), Value(0)),
            saved_count=Coalesce(related_count(UserSavedItem), Value(0)),
            last_activity=last_event,
        )
        .only("id", "nickname", "created_at")
        .order_by("-created_at", "-id")
    )
    if q:
        condition = Q(nickname__icontains=q)
        if q.isdigit():
            condition |= Q(id=int(q))
        rows = rows.filter(condition)
    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy(); params.pop("page", None)
    return render(request, "dashboard/service/users.html", {
        "rows": page.object_list, "page_obj": page, "search_query": q,
        "qs": params.urlencode(),
    })


@login_required(login_url=LOGIN_URL)
def service_events(request):
    event_type = request.GET.get("type", "")
    rows = UserEvent.objects.select_related("user", "content_item", "product", "term")
    if event_type in UserEvent.EventType.values:
        rows = rows.filter(event_type=event_type)
    else:
        event_type = ""
    rows = rows.order_by("-created_at", "-id")
    page = Paginator(rows, 50).get_page(request.GET.get("page"))
    for row in page.object_list:
        row.nickname_public = _nickname(row.user)
        row.target_public = (
            (row.term.canonical_name if row.term_id else "")
            or (row.product.canonical_name if row.product_id else "")
            or (row.content_item.title if row.content_item_id else "")
            or "—"
        )
    params = request.GET.copy(); params.pop("page", None)
    return render(request, "dashboard/service/events.html", {
        "rows": page.object_list, "page_obj": page, "selected_type": event_type,
        "event_types": UserEvent.EventType.choices, "qs": params.urlencode(),
    })


@login_required(login_url=LOGIN_URL)
def service_votes(request):
    status = request.GET.get("status", "")
    rows = VoteCard.objects.select_related(
        "user", "product_source", "product_source__source", "product"
    ).annotate(
        ballot_count=Count("ballots", distinct=True),
        comment_count=Count("comments", filter=Q(comments__is_deleted=False), distinct=True),
        report_count=Count("reports", distinct=True),
    )
    if status in VoteCard.Status.values:
        rows = rows.filter(status=status)
    else:
        status = ""
    page = Paginator(rows.order_by("-created_at", "-id"), 24).get_page(request.GET.get("page"))
    for row in page.object_list:
        row.nickname_public = _nickname(row.user)
        row.display_image = vote_image_url(row.image_url) or (
            absolute_image_url(
                row.product_source.thumbnail_url,
                row.product_source.source.code,
            )
            if row.product_source_id else ""
        )
    params = request.GET.copy(); params.pop("page", None)
    return render(request, "dashboard/service/votes.html", {
        "rows": page.object_list, "page_obj": page, "selected_status": status,
        "statuses": VoteCard.Status.choices, "qs": params.urlencode(),
    })


@login_required(login_url=LOGIN_URL)
def service_comments(request):
    visibility = request.GET.get("visibility", "visible")
    rows = VoteComment.objects.select_related("user", "card").annotate(
        report_count=Count("reports", distinct=True)
    )
    if visibility == "hidden":
        rows = rows.filter(is_deleted=True)
    elif visibility == "all":
        pass
    else:
        visibility = "visible"
        rows = rows.filter(is_deleted=False)
    page = Paginator(rows.order_by("-created_at", "-id"), PAGE_SIZE).get_page(request.GET.get("page"))
    for row in page.object_list:
        row.nickname_public = _nickname(row.user)
    params = request.GET.copy(); params.pop("page", None)
    return render(request, "dashboard/service/comments.html", {
        "rows": page.object_list, "page_obj": page,
        "visibility": visibility, "qs": params.urlencode(),
    })


def _split_db_table(db_table):
    clean = (db_table or "").replace('"', "")
    if "." in clean:
        return clean.split(".", 1)
    return "public", clean


def _model_schema():
    grouped = defaultdict(list)
    edges = []
    model_names = {}
    for model in apps.get_models():
        if not model._meta.managed or model._meta.proxy:
            continue
        schema, table = _split_db_table(model._meta.db_table)
        key = f"{schema}.{table}"
        model_names[model] = key
        grouped[schema].append({
            "name": model._meta.verbose_name,
            "model": model.__name__,
            "table": table,
            "key": key,
            "fields": [f.name for f in model._meta.fields[:8]],
            "field_count": len(model._meta.fields),
        })
    for model, source in model_names.items():
        for field in model._meta.fields:
            target_model = getattr(getattr(field, "remote_field", None), "model", None)
            if target_model in model_names:
                edges.append({"source": source, "target": model_names[target_model], "field": field.name})
    return [
        {"name": schema, "tables": sorted(tables, key=lambda item: item["table"])}
        for schema, tables in sorted(grouped.items())
    ], edges


def _table_stats():
    if connection.vendor != "postgresql":
        return [
            {"schema": _split_db_table(model._meta.db_table)[0],
             "table": _split_db_table(model._meta.db_table)[1],
             "rows": None, "size": None}
            for model in apps.get_models()
            if model._meta.managed and not model._meta.proxy
        ]
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT s.schemaname, s.relname, s.n_live_tup,
                   pg_size_pretty(pg_total_relation_size(quote_ident(s.schemaname)||'.'||quote_ident(s.relname)))
            FROM pg_stat_user_tables s
            ORDER BY pg_total_relation_size(quote_ident(s.schemaname)||'.'||quote_ident(s.relname)) DESC
        """)
        return [
            {"schema": schema, "table": table, "rows": rows, "size": size}
            for schema, table, rows, size in cursor.fetchall()
        ]


_SQL_SENSITIVE = re.compile(
    r"\b(auth_user|django_session|app_user|chat_message|notification|password|email|profile_metadata|session|token)\b",
    re.IGNORECASE,
)
_SQL_DANGEROUS = re.compile(
    r"\b(pg_read_file|pg_ls_dir|pg_stat_file|pg_sleep|pg_terminate_backend|pg_cancel_backend|"
    r"dblink|lo_import|lo_export|set_config|nextval|setval|pg_notify|copy|call|do)\b",
    re.IGNORECASE,
)
_SQL_PG_FUNCTION = re.compile(r"\bpg_[a-z0-9_]+\s*\(", re.IGNORECASE)


def validate_readonly_sql(sql):
    statements = [item for item in sqlparse.parse(sql) if str(item).strip()]
    if len(statements) != 1:
        return "한 번에 하나의 쿼리만 실행할 수 있습니다."
    statement = statements[0]
    kind = statement.get_type().upper()
    if kind != "SELECT" and not str(statement).lstrip().upper().startswith("EXPLAIN"):
        return "SELECT, WITH … SELECT, EXPLAIN만 허용합니다."
    normalized = sqlparse.format(str(statement), strip_comments=True)
    if _SQL_SENSITIVE.search(normalized):
        return "개인정보·인증·대화 원문 테이블은 이 화면에서 조회할 수 없습니다."
    if _SQL_DANGEROUS.search(normalized) or _SQL_PG_FUNCTION.search(normalized):
        return "서버 파일·지연·외부 연결 함수는 사용할 수 없습니다."
    return ""


@login_required(login_url=LOGIN_URL)
def database_overview(request):
    schemas, edges = _model_schema()
    return render(request, "dashboard/database/overview.html", {
        "schemas": schemas,
        "edges": edges,
        "table_stats": _table_stats(),
        "table_count": sum(len(group["tables"]) for group in schemas),
        "relation_count": len(edges),
    })


@login_required(login_url=LOGIN_URL)
def database_query(request):
    enabled = settings.DEBUG or os.getenv("DASHBOARD_SQL_ENABLED") == "1"
    sql = (request.POST.get("sql") or request.GET.get("sql") or "").strip()
    error = ""
    columns = []
    rows = []
    truncated = False
    elapsed_ms = None
    if request.method == "POST":
        if not enabled:
            error = "운영 환경에서는 DASHBOARD_SQL_ENABLED=1과 읽기 전용 DB 계정 설정이 필요합니다."
        elif not sql:
            error = "조회할 SELECT 문을 입력하세요."
        else:
            error = validate_readonly_sql(sql)
        if not error:
            import time
            started = time.monotonic()
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        if connection.vendor == "postgresql":
                            cursor.execute("SET TRANSACTION READ ONLY")
                            cursor.execute("SET LOCAL statement_timeout = 3000")
                        cursor.execute(sql)
                        columns = [col[0] for col in (cursor.description or [])]
                        fetched = cursor.fetchmany(201) if cursor.description else []
                        truncated = len(fetched) > 200
                        rows = fetched[:200]
                        transaction.set_rollback(True)
                elapsed_ms = (time.monotonic() - started) * 1000
            except Exception as exc:  # noqa: BLE001
                error = str(exc)[:500]
    return render(request, "dashboard/database/query.html", {
        "enabled": enabled, "sql": sql, "error": error, "columns": columns,
        "rows": rows, "truncated": truncated, "elapsed_ms": elapsed_ms,
    })
