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


from ..services.dashboard_service import get_dashboard_context

@login_required(login_url="/admin-dashboard/login/")
def dashboard(request):
    return render(
        request,
        "dashboard/dashboard.html",
        get_dashboard_context(),
    )


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
