"""요금제 — 신청 · 관리자 승인 · 챗봇 하루 횟수 (2026-10-03).

규칙과 숫자는 plan_policy.py 에 있다. 여기서는 그것을 DB(app_user.profile_metadata)에 붙인다.
모양은 직업 인증(job_views.py)과 같다 — 신청은 본인, 승인 · 반려는 운영 계정만.

★ 베타 동안(FEEDIT_PUBLIC_BETA 가 켜져 있으면)
  · 신청을 받지 않는다(409). 지금은 모든 기능이 무료라 신청할 이유가 없다.
  · 관리자 목록 · 내 상태 조회는 그대로 된다 — 아무것도 바꾸지 않는 길이라서.
  · 챗봇 횟수는 세지 않는다. 화면도 베타 동안에는 이 주소를 부르지 않는다
    (베타의 챗봇 제한은 지금처럼 알파 계정 20회 — alpha_views.py).

  GET    /api/auth/plan                                    내 요금제 · 오늘 챗봇 사용량
  POST   /api/auth/plan-request  {plan, note?, company?, contact?}
                                   plan=PRO|BUSINESS  신청 (진행 중인 신청은 새 것으로 바뀐다)
                                   plan=FREE          해지 — 승인 없이 바로 프리로
  DELETE /api/auth/plan-request                            진행 중 신청 취소
  GET    /api/auth/plan-requests?status=PENDING|ALL        (관리자) 신청 목록
  POST   /api/auth/plan-review   {user_id, approve: bool, reason?}   (관리자) 승인 · 반려
                                 {user_id, op: "revoke", reason?}    (관리자) 프리로 되돌리기
  POST   /api/auth/plan-chat-use                           챗봇 한 번 쓰기 직전 — 횟수 차감 + 확인증

★ 결제는 붙어 있지 않다. 승인은 "운영자가 확인했다" 는 뜻이다.
"""
from __future__ import annotations

import json

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.models import AppUser

from . import plan_policy as policy

BETA_REASON = ("지금은 베타 기간이라 모든 기능을 무료로 쓰실 수 있어요.\n"
               "요금제 신청은 정식 서비스가 시작되면 열립니다.")


def _ok(data, status=200):
    return JsonResponse({"status": "ok", "data": data}, status=status)


def _error(reason, status=400, data=None):
    return JsonResponse({"status": "error", "reason": reason, "data": data}, status=status)


def _body(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))


def _me(request):
    if not request.user.is_authenticated:
        return None
    profile, _ = AppUser.objects.get_or_create(
        user=request.user,
        defaults={"nickname": request.user.first_name or request.user.username[:12]},
    )
    return profile


def _today():
    return timezone.localdate().isoformat()


def _now():
    return timezone.now().isoformat()


def billing_state(user, profile):
    """auth_views._user_payload 가 user.billing 으로 싣는 값."""
    return policy.state(getattr(profile, "profile_metadata", None) or {},
                        is_admin=_is_admin(user), signed_in=True, today=_today())


@require_GET
def plan(request):
    profile = _me(request)
    if profile is None:
        return _ok(policy.guest_state())
    return _ok(billing_state(request.user, profile))


@require_http_methods(["POST", "DELETE"])
def plan_request(request):
    profile = _me(request)
    if profile is None:
        return _error("로그인이 필요합니다.", 401)
    if _is_admin(request.user):
        return _error("운영 계정은 요금제와 상관없이 모든 기능을 씁니다.", 409)

    if request.method == "DELETE":
        with transaction.atomic():
            p = AppUser.objects.select_for_update().get(pk=profile.pk)
            meta = dict(p.profile_metadata or {})
            req = policy.pending_of(meta)
            if req:
                req.update(status="CANCELLED", decided_at=_now())
                meta["plan_request"] = req
                p.profile_metadata = meta
                p.save(update_fields=["profile_metadata", "updated_at"])
        return _ok(billing_state(request.user, p))

    if not policy.enforced():
        return _error(BETA_REASON, 409)
    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    try:
        parsed = policy.parse_request(data)
    except ValueError as exc:
        return _error(str(exc))

    with transaction.atomic():
        p = AppUser.objects.select_for_update().get(pk=profile.pk)
        meta = dict(p.profile_metadata or {})
        current = policy.stored_plan(meta)
        pending = policy.pending_of(meta)
        now = _now()

        if parsed["plan"] == policy.FREE:
            # 해지 — 결제가 없으니 승인할 것도 없다. 바로 프리로, 진행 중인 신청은 취소.
            if current == policy.FREE and not pending:
                return _error("이미 프리 요금제를 쓰고 계세요.", 409)
            if pending:
                pending.update(status="CANCELLED", decided_at=now)
                meta["plan_request"] = pending
            if current != policy.FREE:
                meta["plan"] = policy.FREE
                meta["plan_since"] = now
                policy.add_history(meta, "CANCELLED", policy.FREE, current, now, request.user.username)
            status = 200
        else:
            if current == parsed["plan"]:
                return _error(f"이미 {policy.LABEL[current]} 요금제를 쓰고 계세요.", 409)
            # 진행 중인 신청이 있으면 새 신청으로 바꾼다 (직업 인증과 같은 규칙)
            meta["plan_request"] = policy.new_request(parsed, current, now)
            status = 201
        p.profile_metadata = meta
        p.save(update_fields=["profile_metadata", "updated_at"])
    return _ok(billing_state(request.user, p), status=status)


@require_GET
def plan_requests(request):
    if not _is_admin(request.user):
        return _error("운영 계정만 볼 수 있습니다.", 403)
    want = (request.GET.get("status") or "PENDING").upper()
    rows = []
    for p in AppUser.objects.filter(profile_metadata__has_key="plan_request").select_related("user"):
        meta = p.profile_metadata or {}
        req = meta.get("plan_request")
        if not isinstance(req, dict) or req.get("status") == "CANCELLED":
            continue
        if want != "ALL" and req.get("status") != want:
            continue
        rows.append({
            "user_id": p.id, "nickname": p.nickname or p.user.username, "username": p.user.username,
            "email": p.user.email or "",
            "current_plan": policy.stored_plan(meta),
            "plan": req.get("plan"), "from_plan": req.get("from_plan") or policy.FREE,
            "note": req.get("note") or "", "company": req.get("company") or "",
            "contact": req.get("contact") or "",
            "status": req.get("status"), "requested_at": req.get("requested_at"),
            "decided_at": req.get("decided_at"), "reason": req.get("reason") or "",
        })
    # 대기 중이 먼저, 그 안에서는 먼저 신청한 사람이 위로
    rows.sort(key=lambda r: (r["status"] != "PENDING", r["requested_at"] or ""))
    return _ok({"items": rows, "pending": sum(1 for r in rows if r["status"] == "PENDING"),
                "enforced": policy.enforced()})


@require_POST
def plan_review(request):
    if not _is_admin(request.user):
        return _error("운영 계정만 심사할 수 있습니다.", 403)
    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return _error("user_id 가 올바르지 않습니다.")
    reason = " ".join(str(data.get("reason") or "").split())[:policy.REASON_MAX]
    revoke = str(data.get("op") or "").lower() == "revoke"
    approve = bool(data.get("approve"))
    now = _now()

    with transaction.atomic():
        p = AppUser.objects.select_for_update().filter(id=user_id).first()
        if p is None:
            return _error("사용자를 찾지 못했습니다.", 404)
        if _is_admin(p.user):
            return _error("운영 계정의 요금제는 바꿀 수 없습니다.", 409)
        meta = dict(p.profile_metadata or {})
        current = policy.stored_plan(meta)

        if revoke:
            if current == policy.FREE:
                return _error("이미 프리 요금제입니다.", 409)
            meta["plan"] = policy.FREE
            meta["plan_since"] = now
            policy.add_history(meta, "REVOKED", policy.FREE, current, now, request.user.username)
            p.profile_metadata = meta
            p.save(update_fields=["profile_metadata", "updated_at"])
            result = {"user_id": user_id, "status": "REVOKED", "plan": policy.FREE}
            req = None
        else:
            req = policy.pending_of(meta)
            if not req:
                return _error("심사 대기 중인 신청이 아닙니다.", 409)
            req.update(status="APPROVED" if approve else "REJECTED",
                       decided_at=now, decided_by=request.user.username, reason=reason)
            if approve:
                meta["plan"] = req.get("plan")
                meta["plan_since"] = now
                policy.add_history(meta, "APPROVED", req.get("plan"), current, now, request.user.username)
            meta["plan_request"] = req
            p.profile_metadata = meta
            p.save(update_fields=["profile_metadata", "updated_at"])
            result = {"user_id": user_id, "status": req["status"], "plan": policy.stored_plan(meta)}

    # 신청자에게 결과 알림. 실패해도 심사는 끝났다.
    from . import notification_service
    if revoke:
        notification_service.notify_plan_review(p, current, "REVOKED", reason, now)
    else:
        notification_service.notify_plan_review(p, req.get("plan"), req["status"], reason,
                                                req.get("requested_at") or now)
    return _ok(result)


@require_POST
def plan_chat_use(request):
    """챗봇 한 번 쓰기 직전에 부른다.

    · 베타 — 세지 않고 통과(enforced=false). 화면은 베타 동안 이 주소를 부르지 않는다.
    · 베타 이후 — 오늘 횟수를 세고, 프리 한도를 넘으면 429.
      통과하면 챗봇 서버에 넘길 확인증(ticket)을 준다. 챗봇은 이것으로 요금제를 안다.
    """
    if not policy.enforced():
        return _ok({"enforced": False, "plan": None, "ticket": None, "chat": None})
    profile = _me(request)
    if profile is None:
        return _error("로그인이 필요합니다.", 401)
    is_admin = _is_admin(request.user)
    today = _today()
    with transaction.atomic():
        p = AppUser.objects.select_for_update().get(pk=profile.pk)
        meta = dict(p.profile_metadata or {})
        current = policy.stored_plan(meta, is_admin)
        ok, row = policy.chat_consume(meta, current, today)
        if not ok:
            usage = policy.chat_usage(meta, current, today)
            return _error(
                f"오늘 프리 요금제의 AI 챗 이용 횟수({usage['limit']}회)를 모두 쓰셨어요.\n"
                "내일 다시 이용하시거나, 요금제 화면에서 프로를 신청해 주세요.",
                429, data={"enforced": True, "plan": current, "chat": usage, "ticket": None})
        meta["plan_chat"] = row
        p.profile_metadata = meta
        p.save(update_fields=["profile_metadata", "updated_at"])
    return _ok({
        "enforced": True,
        "plan": current,
        "chat": policy.chat_usage(meta, current, today),
        "ticket": policy.sign_ticket(p.id, current),
    })
