"""서비스 운영 — 홈페이지 피드백 · 살!말? 신고 처리 (ADMIN-001 버그 신고 처리, 2026-09-27).

사용자가 남긴 글은 이미 표에 쌓이고 있었다(app.site_feedback · app.vote_report).
처리 상태 칸도 있었지만 운영 대시보드에 화면이 없어 기본 /admin/ 에서만 바꿀 수 있었다.

- 피드백: 확인 전 → 반영·처리 / 반려. **반려하면 그 글은 경험치에서 빠진다**
  (apps/api/xp_service.py 가 반려를 뺀다). 바꾼 즉시 작성자의 경험치 사본도 다시 계산한다.
- 신고: 검토 대기 → 검토 완료 / 기각. 댓글 신고는 '댓글 숨기기'로 앱의 ADMIN 삭제와
  같은 처리(is_deleted)를 할 수 있다. 카드 삭제는 지금처럼 앱에서 ADMIN 계정으로 한다.

접근은 대시보드 미들웨어가 운영 계정(is_staff)으로 막는다.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import SiteFeedback, VoteComment, VoteReport

logger = logging.getLogger(__name__)

LOGIN_URL = "/admin-dashboard/login/"
PAGE_SIZE = 30


def _back(request, name):
    """처리 후 보던 목록(필터 · 쪽)으로 돌아간다. 다른 호스트로는 보내지 않는다."""
    qs = request.POST.get("qs", "")
    url = reverse(name)
    return redirect(url + ("?" + qs if qs and "\n" not in qs and "//" not in qs else ""))


def _nickname(profile):
    if profile is None:
        return "(탈퇴한 사용자)"
    return getattr(profile, "nickname", "") or f"회원 #{profile.id}"


# ── 홈페이지 피드백 ─────────────────────────────────────────────


@login_required(login_url=LOGIN_URL)
def feedback_list(request):
    status = request.GET.get("status", SiteFeedback.Status.OPEN)
    kind = request.GET.get("kind", "")
    q = request.GET.get("q", "").strip()

    qs = SiteFeedback.objects.select_related("user").order_by("-created_at", "-id")
    if status in SiteFeedback.Status.values:
        qs = qs.filter(status=status)
    elif status != "ALL":
        status = SiteFeedback.Status.OPEN
        qs = qs.filter(status=status)
    if kind in SiteFeedback.Kind.values:
        qs = qs.filter(kind=kind)
    if q:
        qs = qs.filter(Q(content__icontains=q) | Q(page__icontains=q) | Q(user__nickname__icontains=q))

    counts = dict(SiteFeedback.objects.values_list("status").annotate(n=Count("id")))
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    for fb in page:
        fb.nickname = _nickname(fb.user)

    params = request.GET.copy(); params.pop("page", None)
    return render(request, "dashboard/service/feedback.html", {
        "page_title": "홈페이지 피드백",
        "page_obj": page,
        "rows": page.object_list,
        "status": status,
        "kind": kind,
        "search_query": q,
        "statuses": SiteFeedback.Status.choices,
        "kinds": SiteFeedback.Kind.choices,
        "counts": {k: counts.get(k, 0) for k in SiteFeedback.Status.values},
        "qs": params.urlencode(),
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def feedback_update(request, pk):
    fb = SiteFeedback.objects.select_related("user").filter(pk=pk).first()
    if fb is None:
        messages.error(request, "피드백을 찾지 못했습니다.")
        return _back(request, "dashboard:feedback_list")
    status = request.POST.get("status", "")
    if status not in SiteFeedback.Status.values:
        messages.error(request, "처리 상태가 올바르지 않습니다.")
        return _back(request, "dashboard:feedback_list")
    note = (request.POST.get("admin_note") or "").strip()[:300]

    was = fb.status
    fb.status = status
    fb.admin_note = note
    fb.save(update_fields=["status", "admin_note", "updated_at"])

    # 반려로 바뀌거나 반려가 풀리면 경험치가 달라진다 — 작성자의 사본을 바로 맞춘다
    if SiteFeedback.Status.REJECTED in (was, status) and was != status:
        try:
            from apps.api.xp_service import xp_state
            xp_state(fb.user, save=True)
        except Exception:
            # 경험치 사본은 다음 접속 때도 다시 계산된다 — 처리 자체를 되돌리지 않는다
            logger.exception("피드백 처리 후 경험치 재계산 실패 feedback=%s", fb.id)

    messages.success(request, f"피드백 #{fb.id} → {fb.get_status_display()}")
    return _back(request, "dashboard:feedback_list")


# ── 살!말? 신고 ─────────────────────────────────────────────────


@login_required(login_url=LOGIN_URL)
def report_list(request):
    status = request.GET.get("status", VoteReport.Status.PENDING)
    target = request.GET.get("target", "")

    qs = VoteReport.objects.select_related("reporter", "card", "comment").order_by("-created_at", "-id")
    if status in VoteReport.Status.values:
        qs = qs.filter(status=status)
    elif status != "ALL":
        status = VoteReport.Status.PENDING
        qs = qs.filter(status=status)
    if target in VoteReport.TargetType.values:
        qs = qs.filter(target_type=target)

    counts = dict(VoteReport.objects.values_list("status").annotate(n=Count("id")))
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))

    # 같은 대상을 몇 명이 신고했는지 — 한 쪽에 보이는 것만 한 번에 센다
    keys = {(r.target_type, r.target_id) for r in page}
    same = {}
    if keys:
        cond = Q()
        for tt, tid in keys:
            cond |= Q(target_type=tt, target_id=tid)
        same = {(r["target_type"], r["target_id"]): r["n"]
                for r in VoteReport.objects.filter(cond).values("target_type", "target_id").annotate(n=Count("id"))}
    for r in page:
        r.nickname = _nickname(r.reporter)
        r.same_count = same.get((r.target_type, r.target_id), 1)
        snap = r.target_snapshot or {}
        r.target_title = snap.get("title") or snap.get("card_title") or (r.card.title if r.card else "")
        r.target_text = snap.get("comment_content", "")
        r.author_withdrawn = bool(snap.get("withdrawn"))   # 글쓴이가 탈퇴해 사본을 지웠다
        r.comment_hidden = bool(r.comment and r.comment.is_deleted)

    params = request.GET.copy(); params.pop("page", None)
    return render(request, "dashboard/service/reports.html", {
        "page_title": "살!말? 신고",
        "page_obj": page,
        "rows": page.object_list,
        "status": status,
        "target": target,
        "statuses": VoteReport.Status.choices,
        "targets": VoteReport.TargetType.choices,
        "counts": {k: counts.get(k, 0) for k in VoteReport.Status.values},
        "qs": params.urlencode(),
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def report_update(request, pk):
    report = VoteReport.objects.select_related("comment").filter(pk=pk).first()
    if report is None:
        messages.error(request, "신고를 찾지 못했습니다.")
        return _back(request, "dashboard:report_list")
    status = request.POST.get("status", "")
    if status not in VoteReport.Status.values:
        messages.error(request, "처리 상태가 올바르지 않습니다.")
        return _back(request, "dashboard:report_list")
    hide = request.POST.get("hide_comment") == "1"

    with transaction.atomic():
        # 같은 대상에 들어온 신고는 한 번에 같은 결론을 낸다 — 같은 댓글을 여러 번 검토하지 않게
        same = VoteReport.objects.filter(target_type=report.target_type, target_id=report.target_id)
        n = same.exclude(status=status).update(status=status)
        hidden = False
        if hide and report.target_type == VoteReport.TargetType.COMMENT and report.comment_id:
            hidden = bool(VoteComment.objects.filter(id=report.comment_id, is_deleted=False)
                          .update(is_deleted=True, updated_at=timezone.now()))

    msg = f"신고 #{report.id} → {VoteReport.Status(status).label}"
    if n > 1:
        msg += f" (같은 대상 신고 {n}건 함께)"
    if hidden:
        msg += " · 댓글을 숨겼습니다"
    messages.success(request, msg)
    return _back(request, "dashboard:report_list")
