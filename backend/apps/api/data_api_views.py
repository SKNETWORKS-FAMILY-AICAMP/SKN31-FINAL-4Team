"""데이터 API 연동 — 키 관리 · 지표 내주기 (2026-10-03). 규칙은 data_api.py.

  ① 키 관리 — 로그인 세션 (화면의 계정 메뉴 '데이터 API')
     GET    /api/auth/data-keys                 내 키 목록 · 쓸 수 있는 지표 · 한도 · 오늘 사용량
     POST   /api/auth/data-keys  {name}         새 키 (원문은 이 응답에서 한 번만 보인다)
     DELETE /api/auth/data-keys  {key_id}       키 폐기

  ② 지표 — API 키 (밖의 시스템이 부른다. 세션 · CSRF 를 쓰지 않는다)
     GET /api/data                  지표 목록
     GET /api/data/<지표>?…          views.py 의 같은 함수를 그대로 부른다 — 화면과 같은 숫자
     Authorization: Bearer fdk_…    (또는 X-API-Key)

★ 베타 동안(plan_policy.enforced() 가 False)
  · 키를 만들 수 없다(409) — 목록 조회와 폐기는 된다.
  · 지표 주소는 403 BETA 로 답하고 DB 를 보지 않는다.
★ 매 요청마다 지금 요금제를 다시 본다. 비즈니스에서 내려간 계정의 키는 지워지지 않고 멈춘다(403 PLAN).
★ 응답은 엣지에 캐시하지 않는다(no-store). 키마다 허락이 다르기 때문이다.
"""
from __future__ import annotations

import json
import time

from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.models import AppUser

from . import data_api
from . import plan_policy as policy
from . import views

HISTORY_KEEP = 20     # 폐기한 키까지 합쳐 남겨 두는 행 수


def _ok(data, status=200):
    return JsonResponse({"status": "ok", "data": data}, status=status)


def _error(reason, status=400, code="", **extra):
    resp = JsonResponse({"status": "error", "reason": reason, "code": code or None, "data": None, **extra},
                        status=status)
    resp["Cache-Control"] = "no-store"
    return resp


def _is_admin(user):
    return bool(user and (user.is_superuser or user.is_staff))


def _today():
    return timezone.localdate().isoformat()


def _allowed(meta, user) -> tuple[bool, str]:
    plan = policy.stored_plan(meta, _is_admin(user))
    return policy.enforced() and bool(policy.features_of(plan)["data_api"]), plan


def _limits():
    return {"per_day": data_api.per_day(), "per_minute": data_api.per_min()}


# ── ① 키 관리 ─────────────────────────────────────────────────

def _keys_payload(user, meta):
    allowed, plan = _allowed(meta, user)
    return {
        "enforced": policy.enforced(), "allowed": allowed, "plan": plan,
        "keys": [data_api.public_key(r) for r in data_api.active_keys(meta)],
        "max_keys": data_api.MAX_KEYS,
        "metrics": data_api.catalogue(),
        "limits": _limits(),
        "used_today": data_api.used_today(meta, _today()),
    }


@require_http_methods(["GET", "POST", "DELETE"])
def data_keys(request):
    if not request.user.is_authenticated:
        return _error("로그인이 필요합니다.", 401)
    profile, _ = AppUser.objects.get_or_create(
        user=request.user, defaults={"nickname": request.user.first_name or request.user.username[:12]})

    if request.method == "GET":
        return _ok(_keys_payload(request.user, profile.profile_metadata or {}))

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = None
    if not isinstance(body, dict):
        return _error("요청 형식이 올바른 JSON이 아닙니다.")

    with transaction.atomic():
        p = AppUser.objects.select_for_update().get(pk=profile.pk)
        meta = dict(p.profile_metadata or {})
        rows = [dict(r) for r in (meta.get("data_api_keys") or []) if isinstance(r, dict)]
        now = timezone.now().isoformat()

        if request.method == "DELETE":
            # 폐기는 베타 · 요금제와 상관없이 언제나 된다 — 새어 나간 키를 막는 길이라서.
            key_id = str(body.get("key_id") or "")
            hit = next((r for r in rows if r.get("id") == key_id and not r.get("revoked_at")), None)
            if hit is None:
                return _error("그 키를 찾지 못했습니다.", 404)
            hit["revoked_at"] = now
            meta["data_api_keys"] = rows
            p.profile_metadata = meta
            p.save(update_fields=["profile_metadata", "updated_at"])
            return _ok(_keys_payload(request.user, meta))

        if not policy.enforced():
            return _error("지금은 베타 기간이라 데이터 API 를 열지 않았습니다.\n정식 서비스가 시작되면 키를 만들 수 있어요.",
                          409, code="BETA")
        allowed, plan = _allowed(meta, request.user)
        if not allowed:
            return _error(f"데이터 API 는 비즈니스 요금제에서 쓸 수 있어요. 지금 요금제: {policy.LABEL.get(plan, plan)}",
                          403, code="PLAN")
        if len(data_api.active_keys(meta)) >= data_api.MAX_KEYS:
            return _error(f"키는 {data_api.MAX_KEYS}개까지 만들 수 있어요. 쓰지 않는 키를 폐기한 뒤 다시 만들어 주세요.", 409)
        raw, row = data_api.new_key(p.id)
        row.update(name=data_api.clean_name(body.get("name")), created_at=now, last_used_at=None, revoked_at=None)
        # 폐기한 키는 기록으로만 남긴다 — 오래된 것부터 지운다(살아 있는 키는 지우지 않는다)
        rows.append(row)
        while len(rows) > HISTORY_KEEP:
            old = next((r for r in rows if r.get("revoked_at")), None)
            if old is None:
                break
            rows.remove(old)
        meta["data_api_keys"] = rows
        p.profile_metadata = meta
        p.save(update_fields=["profile_metadata", "updated_at"])
    data = _keys_payload(request.user, meta)
    data["key"] = raw          # ★ 원문은 여기서 한 번만 나간다
    data["created"] = data_api.public_key(row)
    return _ok(data, status=201)


# ── ② 지표 ────────────────────────────────────────────────────

def _minute_ok(profile_id: int, key_id: str) -> bool:
    """키당 분당 횟수. 프로세스 메모리 캐시라 워커마다 따로 센다(대략적인 상한)."""
    bucket = f"dapi:{profile_id}:{key_id}:{int(time.time() // 60)}"
    if cache.add(bucket, 1, timeout=90):
        return True
    try:
        return cache.incr(bucket) <= data_api.per_min()
    except ValueError:            # 그 사이에 만료됐다
        cache.add(bucket, 1, timeout=90)
        return True


def _serve(request, metric):
    if not policy.enforced():
        return _error("데이터 API 는 정식 서비스가 시작되면 열립니다.", 403, code="BETA")
    raw = data_api.key_from_headers(request.META)
    parsed = data_api.parse_key(raw)
    if parsed is None:
        return _error("API 키가 없거나 형식이 맞지 않습니다. Authorization: Bearer fdk_… 머리글로 보내 주세요.",
                      401, code="NO_KEY")
    profile_id, key_id = parsed
    # 없는 지표는 횟수를 쓰기 전에 돌려보낸다
    if metric is not None and metric not in data_api.METRICS:
        return _error(f"없는 지표입니다: {metric}. GET /api/data 로 목록을 보세요.", 404, code="NO_METRIC")
    if not _minute_ok(profile_id, key_id):
        resp = _error(f"요청이 너무 잦습니다. 키 하나당 분당 {data_api.per_min()}회까지입니다.", 429, code="RATE_LIMITED")
        resp["Retry-After"] = "60"
        return resp

    today = _today()
    with transaction.atomic():
        p = AppUser.objects.select_for_update().filter(pk=profile_id).first()
        meta = dict((p.profile_metadata if p else None) or {})
        row = data_api.match(meta, key_id, raw) if p else None
        if row is None or not p.user.is_active:
            return _error("API 키가 맞지 않거나 폐기됐습니다.", 401, code="INVALID_KEY")
        allowed, plan = _allowed(meta, p.user)
        if not allowed:
            return _error(f"데이터 API 는 비즈니스 요금제에서 쓸 수 있어요. 지금 요금제: {policy.LABEL.get(plan, plan)}",
                          403, code="PLAN")
        ok, usage = data_api.consume(meta, today)
        if not ok:
            return _error(f"오늘 요청 한도({data_api.per_day()}회)를 다 썼습니다. 내일 0시(한국시간)에 다시 열립니다.",
                          429, code="DAILY_LIMIT")
        meta["data_api_usage"] = usage
        row["last_used_at"] = timezone.now().isoformat()
        p.profile_metadata = meta
        p.save(update_fields=["profile_metadata", "updated_at"])

    # 지표 계산은 행 잠금을 푼 뒤에 한다 — 무거운 조회 동안 그 회원의 다른 동작을 막지 않게.
    if metric is None:
        resp = _ok({"metrics": data_api.catalogue(), "plan": plan, "limits": _limits()})
    else:
        resp = getattr(views, data_api.METRICS[metric][0])(request)
    resp["Cache-Control"] = "no-store"
    resp["X-RateLimit-Limit"] = str(data_api.per_day())
    resp["X-RateLimit-Remaining"] = str(max(data_api.per_day() - usage["count"], 0))
    return resp


@require_GET
def data_index(request):
    return _serve(request, None)


@require_GET
def data_metric(request, metric):
    return _serve(request, metric)
