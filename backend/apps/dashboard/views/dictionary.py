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
