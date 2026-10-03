"""알림 API — 목록 · 읽음 · 알림 설정 · 용어 등재 요청.

모두 로그인 세션이 있어야 한다. 브라우저는 /api/auth/<action> 으로 부르고
버셀 함수(frontend/api/auth/[action].js)가 쿠키·CSRF 를 중계한다.

알림을 만드는 쪽은 notification_service.py 다. 여기서는 만들어진 것을 보여 주고,
사용자가 끄고 켜는 것만 한다.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.models import Notification, NotificationSetting, TermRequest

from . import notifications as rules
from . import notification_service as service
from . import plan_policy
from .activity_views import _body, _error, _login_profile, _text

LIST_LIMIT = 30
TERM_MAX = 40
NOTE_MAX = 200


def _ok(data):
    return JsonResponse({"status": "ok", "data": data})


def _row(noti):
    return {
        "id": noti.id,
        "kind": noti.kind,
        "title": noti.title,
        "body": noti.body,
        "link": noti.link,
        "payload": noti.payload or {},
        "read": noti.read_at is not None,
        "created_at": noti.created_at,
    }


def _setting_payload(profile):
    row = service.setting_of(profile)
    if row is None:
        return {"enabled": True, "kinds": {kind: True for kind in rules.SETTING_FIELD}}
    return {
        "enabled": bool(row.enabled),
        "kinds": {kind: bool(getattr(row, field)) for kind, field in rules.SETTING_FIELD.items()},
    }


# ── 목록 · 읽음 ────────────────────────────────────────────

def _mine(profile):
    """지운 알림은 목록에도 숫자에도 들어가지 않는다 (행은 남는다 — 모델 주석 참고)."""
    return Notification.objects.filter(user=profile, deleted_at__isnull=True)


def _unread(profile):
    return _mine(profile).filter(read_at__isnull=True).count()


@require_http_methods(["GET", "POST"])
def notifications(request):
    """GET  /api/auth/notifications  — 최근 30건 + 안 읽은 수

    POST /api/auth/notifications
      {"op": "read", "id": 12}   {"op": "read_all"}
      {"op": "delete", "id": 12} {"op": "delete_all"}
    """
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)

    if request.method == "GET":
        # ★ 운영 계정은 직업 인증 심사 대기 건수를 알림으로 받는다
        if request.user.is_superuser or request.user.is_staff:
            service.notify_admin_job_pending(profile)
            # 요금제 신청 대기 (2026-10-03) — 베타 동안은 신청이 없으니 묻지도 않는다
            if plan_policy.enforced():
                service.notify_admin_plan_pending(profile)
        # 성별이 비어 있으면 한 번 묻는다 (2026-10-02) — 가입에서 성별을 받기 전의 회원
        service.ensure_gender_prompt(profile)
        rows = list(_mine(profile).order_by("-created_at", "-id")[:LIST_LIMIT])
        return _ok({"items": [_row(r) for r in rows], "unread": _unread(profile),
                    "setting": _setting_payload(profile)})

    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    op = _text(data.get("op"), 20).lower()
    now = timezone.now()
    if op == "read_all":
        n = _mine(profile).filter(read_at__isnull=True).update(read_at=now)
        return _ok({"read": n, "unread": 0})
    if op == "delete_all":
        n = _mine(profile).update(deleted_at=now, read_at=now)
        return _ok({"deleted": n, "unread": 0})
    if op in ("read", "delete"):
        try:
            noti_id = int(data.get("id"))
        except (TypeError, ValueError):
            return _error("id 가 올바르지 않습니다.")
        rows = _mine(profile).filter(id=noti_id)
        if op == "read":
            n = rows.filter(read_at__isnull=True).update(read_at=now)
            return _ok({"read": n, "unread": _unread(profile)})
        # 지울 때 읽음도 같이 찍는다 — 안 읽은 채로 지우면 숫자만 남는다.
        n = rows.update(deleted_at=now, read_at=now)
        return _ok({"deleted": n, "unread": _unread(profile)})
    return _error("op 는 read · read_all · delete · delete_all 중 하나여야 합니다.")


# ── 상단 띠 공지 (2026-10-02) ──────────────────────────────

@require_GET
def announcements(request):
    """GET /api/auth/announcements — 지금 걸린 실시간 공지. 로그인 없이도 본다.

    화면(ticker.js)이 30초마다 부른다. 값은 15초 캐시(service.live_announcements).
    """
    return _ok({"items": service.live_announcements()})


# ── 알림 설정 ──────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def notification_settings(request):
    """GET  /api/auth/notification-settings
    POST /api/auth/notification-settings  {"enabled": true, "kinds": {"PRICE_DROP": false}}

    보내지 않은 종류는 그대로 둔다 — 화면이 한 칸만 껐을 때 나머지를 되돌리지 않는다.
    """
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    if request.method == "GET":
        return _ok(_setting_payload(profile))

    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    kinds = data.get("kinds")
    if kinds is not None and not isinstance(kinds, dict):
        return _error("kinds 는 {종류: true/false} 여야 합니다.")
    unknown = [k for k in (kinds or {}) if k not in rules.SETTING_FIELD]
    if unknown:
        return _error("모르는 알림 종류입니다: " + ", ".join(unknown))

    row, _created = NotificationSetting.objects.get_or_create(user=profile)
    changed = []
    if "enabled" in data:
        row.enabled = bool(data.get("enabled"))
        changed.append("enabled")
    for kind, value in (kinds or {}).items():
        field = rules.SETTING_FIELD[kind]
        setattr(row, field, bool(value))
        changed.append(field)
    if changed:
        row.save(update_fields=changed + ["updated_at"])
    return _ok(_setting_payload(profile))


# ── 용어 사전 등재 요청 ────────────────────────────────────

@require_http_methods(["GET", "POST"])
def term_request(request):
    """GET  /api/auth/term-request         — 내가 낸 요청 목록
    POST /api/auth/term-request  {"term": "블로코어", "note": ""}

    이미 사전에 있는 말이면 요청을 만들지 않고 그 사실을 그대로 알려 준다 —
    영원히 오지 않을 알림을 기다리게 두지 않는다.
    """
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)

    if request.method == "GET":
        rows = (TermRequest.objects.filter(user=profile)
                .select_related("term").order_by("-created_at")[:50])
        return _ok({"items": [{"id": r.id, "term": r.raw_term, "status": r.status,
                               "canonical_name": r.term.canonical_name if r.term_id else "",
                               "created_at": r.created_at} for r in rows]})

    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    raw = _text(data.get("term"), TERM_MAX)
    if not raw:
        return _error("등재를 요청할 용어를 적어 주세요.")
    normalized = service.norm_term(raw)
    if not normalized:
        return _error("등재를 요청할 용어를 적어 주세요.")

    exists = service.find_active_term(raw, normalized)
    if exists is not None:
        return _ok({"already": True, "canonical_name": exists.canonical_name,
                    "term_type": exists.term_type})

    row, created = TermRequest.objects.get_or_create(
        user=profile, normalized_term=normalized,
        defaults={"raw_term": raw, "note": _text(data.get("note"), NOTE_MAX)},
    )
    return _ok({"already": False, "created": created, "id": row.id,
                "term": row.raw_term, "status": row.status})
