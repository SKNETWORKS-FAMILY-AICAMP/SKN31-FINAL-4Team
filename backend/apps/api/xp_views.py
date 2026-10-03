"""경험치 · 홈페이지 피드백 API (2026-09-25).

  GET  /api/auth/xp                      내 경험치 (누적 · 오늘 · 이번 주)
  POST /api/auth/xp  {"type": "VISIT"}   오늘 접속 (자정을 넘겨 탭을 계속 켜 둔 경우)
  POST /api/auth/xp  {"type": "DWELL", "seconds": 60}
                                         트렌드 분석 화면을 본 시간

  GET  /api/auth/site-feedback           내가 남긴 홈페이지 피드백 (최근 순)
  POST /api/auth/site-feedback  {"kind": "REQUEST"|"BUG", "content": "...", "page": "trend"}

계산 규칙은 xp.py, 어느 기록을 세는지는 xp_service.py 에 있다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.models import AppUser, SiteFeedback

from .activity import KST
from .xp import kst_day, week_start
from .xp_service import add_dwell, is_operator, mark_visit, xp_state

FEEDBACK_MIN, FEEDBACK_MAX = 10, 1000
FEEDBACK_DAILY_LIMIT = 5          # 하루에 남길 수 있는 글 수 — 도배 방지
FEEDBACK_LIST_LIMIT = 10


def _error(reason, status=400):
    return JsonResponse({"status": "error", "reason": reason, "data": None}, status=status)


def _body(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _profile(request):
    if not request.user.is_authenticated:
        return None
    profile, _ = AppUser.objects.get_or_create(
        user=request.user, defaults={"nickname": request.user.first_name or request.user.username[:12]},
    )
    return profile


def _clean(value, limit):
    # 줄바꿈은 살린다 — 재현 순서를 여러 줄로 적는 글이 많다.
    text = str(value or "").replace("\r\n", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:limit]


@require_http_methods(["GET", "POST"])
def xp(request):
    profile = _profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    if request.method == "GET":
        return JsonResponse({"status": "ok", "data": {"xp": xp_state(profile)}})

    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    kind = str(data.get("type") or "").strip().upper()
    now = timezone.now()
    if kind == "VISIT":
        mark_visit(profile, now)
        return JsonResponse({"status": "ok", "data": {"recorded": "VISIT", "xp": xp_state(profile, now)}})
    if kind == "DWELL":
        mark_visit(profile, now)
        added = 0 if is_operator(request.user) else add_dwell(profile, data.get("seconds"), now)
        return JsonResponse({"status": "ok", "data": {"recorded": "DWELL", "added_seconds": added,
                                                      "xp": xp_state(profile, now)}})
    return _error("type 은 VISIT 또는 DWELL 이어야 합니다.")


def _feedback_public(row):
    return {
        "id": row.id,
        "kind": row.kind,
        "kind_label": row.get_kind_display(),
        "content": row.content,
        "status": row.status,
        "status_label": row.get_status_display(),
        "created_at": timezone.localtime(row.created_at).strftime("%Y.%m.%d %H:%M"),
    }


@require_http_methods(["GET", "POST"])
def site_feedback(request):
    profile = _profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    mine = SiteFeedback.objects.filter(user=profile)
    if request.method == "GET":
        rows = [_feedback_public(r) for r in mine.order_by("-created_at")[:FEEDBACK_LIST_LIMIT]]
        return JsonResponse({"status": "ok", "data": {"items": rows}})

    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    kind = str(data.get("kind") or "").strip().upper()
    if kind not in SiteFeedback.Kind.values:
        return _error("유형은 불편사항·추가요청(REQUEST) 또는 수정사항·버그리포트(BUG) 중 하나여야 합니다.")
    content = _clean(data.get("content"), FEEDBACK_MAX)
    if len(content) < FEEDBACK_MIN:
        return _error(f"내용을 {FEEDBACK_MIN}자 이상 적어 주세요.")
    page = _clean(data.get("page"), 120).replace("\n", " ")

    now = timezone.now()
    today = kst_day(now)
    day_from = datetime.combine(today, time.min, tzinfo=KST)
    if mine.filter(created_at__gte=day_from).count() >= FEEDBACK_DAILY_LIMIT:
        return _error(f"피드백은 하루 {FEEDBACK_DAILY_LIMIT}건까지 남길 수 있어요. 내일 다시 남겨 주세요.", status=429)
    if mine.filter(content=content, created_at__gte=now - timedelta(days=1)).exists():
        return _error("같은 내용을 이미 남기셨어요.", status=409)

    week_from = datetime.combine(week_start(today), time.min, tzinfo=KST)
    already = (mine.filter(created_at__gte=week_from)
               .exclude(status=SiteFeedback.Status.REJECTED).exists())
    row = SiteFeedback.objects.create(user=profile, kind=kind, content=content, page=page)
    state = xp_state(profile, now)
    # 이번 주 첫 피드백이면 +25. 운영 계정(고정)과 시작일 전에는 받지 않는다.
    got = (not state.get("fixed")) and any(
        item["key"] == "site_feedback" and item["xp"] > 0
        for item in state["week"]["weekly"]["items"])
    return JsonResponse({
        "status": "ok",
        "data": {"item": _feedback_public(row), "rewarded": bool(got and not already), "xp": state},
    }, status=201)
