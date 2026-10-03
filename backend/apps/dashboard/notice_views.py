"""서비스 운영 — 알림 보내기 · 실시간 공지 (2026-10-02).

두 가지를 한 화면에서 다룬다.

  ① 알림 보내기  받는 사람의 알림함(종 모양)에 한 건씩 들어간다. 사용자 앱의 알림과 같은
                 양식(제목 한 줄 · 본문 · 눌렀을 때 갈 화면)이고, 종류는 '운영 공지' 다.
                 대상은 전체 · 성별 미입력 회원 · 직접 고른 회원(번호 · 닉네임).
  ② 실시간 공지  홈페이지 상단 가운데에 흘러가는 한 줄. 로그인하지 않은 방문자도 본다.
                 화면이 30초마다 받아 가므로 올리면 1분 안에 모두에게 뜬다.

접근은 대시보드 미들웨어가 운영 계정(is_staff)으로 막는다.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.api import notification_service as service
from apps.api import notifications as rules
from apps.core.models import Announcement, AppUser

LOGIN_URL = "/admin-dashboard/login/"
TARGETS = (("all", "전체 회원"), ("no_gender", "성별 미입력 회원"), ("pick", "직접 고르기"))


def _who(request):
    user = request.user
    return (getattr(user, "get_username", lambda: "")() or "")[:150]


@login_required(login_url=LOGIN_URL)
def notices(request):
    now = timezone.now()
    active_users = AppUser.objects.filter(user__is_active=True)
    tickers = list(Announcement.objects.order_by("-created_at", "-id")[:12])
    for a in tickers:
        a.live = a.active and a.starts_at <= now and (a.ends_at is None or a.ends_at > now)
    return render(request, "dashboard/service/notices.html", {
        "tickers": tickers,
        "history": service.admin_notice_history(),
        "links": list(rules.NOTICE_LINKS.items()),
        "targets": TARGETS,
        "count_all": active_users.count(),
        "count_no_gender": active_users.filter(Q(gender__isnull=True) | Q(gender="")).count(),
        "title_max": rules.NOTICE_TITLE_MAX,
        "body_max": rules.NOTICE_BODY_MAX,
        "ticker_max": rules.TICKER_MAX,
        "form": request.session.pop("notice_form", {}),
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def notice_send(request):
    data = {k: request.POST.get(k, "") for k in ("title", "body", "link", "target", "recipients")}
    back = redirect("dashboard:service_notices")
    target = data["target"]
    try:
        title, body, link = rules.clean_notice(data["title"], data["body"], data["link"])
        if target == "all" and request.POST.get("confirm_all") != "1":
            raise ValueError("전체 회원에게 보내려면 확인 칸을 체크해 주세요.")
        ids, names = rules.parse_recipients(data["recipients"])
        if target == "pick" and not (ids or names):
            raise ValueError("받을 회원의 번호나 닉네임을 적어 주세요.")
        profiles, missing = service.notice_targets(target, ids, names)
    except ValueError as exc:
        messages.error(request, str(exc))
        request.session["notice_form"] = data          # 쓴 글을 잃지 않게 다시 채운다
        return back
    if not profiles.exists():
        messages.error(request, "보낼 회원이 없습니다." + (f" 찾지 못함: {', '.join(missing)}" if missing else ""))
        request.session["notice_form"] = data
        return back
    got = service.send_admin_notice(profiles, title, body, link, by=_who(request))
    note = f"알림을 {got['sent']:,}명에게 보냈습니다."
    if got["skipped"]:
        note += f" (알림을 모두 끈 {got['skipped']:,}명 제외)"
    messages.success(request, note)
    if missing:
        messages.warning(request, "찾지 못한 회원: " + ", ".join(missing[:20]))
    return back


@login_required(login_url=LOGIN_URL)
@require_POST
def ticker_create(request):
    back = redirect("dashboard:service_notices")
    try:
        message, link = rules.clean_ticker(request.POST.get("message"), request.POST.get("link"))
        hours_raw = (request.POST.get("hours") or "").strip()
        hours = int(hours_raw) if hours_raw else 0
        if hours < 0 or hours > 24 * 30:
            raise ValueError("게시 시간은 0(내릴 때까지)~720시간 사이로 적어 주세요.")
    except ValueError as exc:
        messages.error(request, str(exc) if "invalid literal" not in str(exc) else "게시 시간은 숫자로 적어 주세요.")
        request.session["notice_form"] = {"message": request.POST.get("message", ""),
                                          "ticker_link": request.POST.get("link", ""),
                                          "hours": request.POST.get("hours", "")}
        return back
    now = timezone.now()
    Announcement.objects.create(message=message, link=link, starts_at=now,
                                ends_at=(now + timedelta(hours=hours)) if hours else None,
                                created_by=_who(request))
    service.forget_live_announcements()
    messages.success(request, "실시간 공지를 올렸습니다. 1분 안에 모든 화면에 뜹니다.")
    return back


@login_required(login_url=LOGIN_URL)
@require_POST
def ticker_end(request, pk):
    n = Announcement.objects.filter(pk=pk, active=True).update(active=False)
    service.forget_live_announcements()
    if n:
        messages.success(request, f"공지 #{pk} 를 내렸습니다.")
    else:
        messages.error(request, "이미 내렸거나 없는 공지입니다.")
    return redirect("dashboard:service_notices")
