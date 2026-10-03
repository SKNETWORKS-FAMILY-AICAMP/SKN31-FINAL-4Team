"""알파 테스트 계정 — 해커톤 시연 기간(15일) 한정.

처음 들어온 사람이 회원가입 없이 바로 서비스를 쓰게 한다. 접속자마다
다른 계정을 하나씩 발급하고 Django 세션으로 로그인시킨다.

이 파일은 **기간이 끝나면 통째로 지우는 것을 전제로** 따로 두었다.
기존 auth_views.py 는 건드리지 않고, 계정 생성은 그쪽 _create_account 를
그대로 재사용한다 (auth_user + app_user 한 트랜잭션 + 로그인).

끄는 법
  FEEDIT_ALPHA_MODE=0            — 발급 중단 (이미 받은 계정은 그대로 남는다)
  FEEDIT_ALPHA_UNTIL=2026-10-05  — 이 날짜까지만 발급 (KST 기준, 포함)
  FEEDIT_ALPHA_CHAT_QUOTA=20     — 계정당 챗봇 누적 허용 횟수

한계 (문서에도 적어 둘 것)
  챗봇은 Django 가 아니라 별도 서버(ChatBot/server.py)라 세션을 모른다.
  그래서 횟수 차감은 프론트가 전송 직전에 여기로 요청하는 구조다. 개발자도구를
  아는 사람은 우회할 수 있다. 시연 기간의 안내·집계 용도이고, 원가를 강제로
  막는 장치는 챗봇 서버 쪽 IP 한도(그대로 살아 있다)다.
"""

from __future__ import annotations

import os
import secrets
from datetime import date, datetime

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .auth_views import _auth_payload, _create_account, _error, _json, _profile
from . import plan_policy


ALPHA_PLAN = "TEST"
DEFAULT_QUOTA = 20
# 발급 실패를 사용자에게 보여 주지 않기 위해 아이디 충돌은 몇 번 다시 시도한다.
USERNAME_TRIES = 5


def _flag(name: str, default: str = "1") -> bool:
    return str(os.getenv(name, default)).strip().lower() not in {"0", "false", "off", "no"}


def chat_quota() -> int:
    try:
        value = int(os.getenv("FEEDIT_ALPHA_CHAT_QUOTA", str(DEFAULT_QUOTA)))
    except (TypeError, ValueError):
        return DEFAULT_QUOTA
    return value if value > 0 else DEFAULT_QUOTA


def _until() -> date | None:
    raw = (os.getenv("FEEDIT_ALPHA_UNTIL") or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        # 형식이 틀렸다고 발급을 멈추면 시연이 조용히 죽는다. 기한 없음으로 본다.
        return None


def alpha_enabled() -> bool:
    """지금 새 알파 계정을 발급해도 되는가."""
    if not _flag("FEEDIT_ALPHA_MODE"):
        return False
    # 베타가 끝나 요금제가 걸리면(plan_policy.enforced) 알파 계정도 끝이다 (2026-10-03).
    # 베타 동안에는 이 줄이 아무것도 바꾸지 않는다.
    if plan_policy.enforced():
        return False
    until = _until()
    if until is None:
        return True
    from django.utils import timezone
    return timezone.localdate() <= until


def is_alpha(profile) -> bool:
    meta = (profile.profile_metadata or {}) if profile else {}
    return bool(meta.get("alpha"))


def quota_state(profile) -> dict:
    """프론트가 배너에 그릴 값. 알파 계정이 아니면 제한 없음으로 답한다."""
    limit = chat_quota()
    # 베타가 끝나면 알파 계정은 프리 요금제로 본다 — 챗봇 횟수는 요금제의 하루 한도가 맡고,
    # '알파테스트 계정 · 모든 기능 이용 가능' 배너도 더 띄우지 않는다 (2026-10-03).
    if not is_alpha(profile) or plan_policy.enforced():
        return {"alpha": False, "limit": None, "used": 0, "remaining": None}
    used = int((profile.profile_metadata or {}).get("alpha_chat_used") or 0)
    return {
        "alpha": True,
        "limit": limit,
        "used": min(used, limit),
        "remaining": max(limit - used, 0),
    }


def _new_username() -> str:
    return "alpha" + secrets.token_hex(5)


@require_POST
def alpha_account(request):
    """방문자가 고른 닉네임·스타일로 알파 계정을 만들고 바로 로그인시킨다.

    body: {"nickname": "...", "styles": ["스트릿웨어", ...]}
      nickname 은 정식 가입과 같은 규칙(2~12자)을 쓴다.
      styles 는 표준 스타일명이고, 개수 제한·존재 검증은 auth_views._save_styles 가 한다.

    이미 로그인한 사람(알파든 정식 회원이든)에게는 아무것도 만들지 않고
    현재 계정을 그대로 돌려준다 — 새로고침마다 계정이 늘어나면 안 된다.
    """
    if request.user.is_authenticated:
        profile = _profile(request.user, create=True)
        payload = _auth_payload(request, request.user, profile)
        payload["data"]["alpha"] = quota_state(profile)
        payload["data"]["issued"] = False
        return JsonResponse(payload)

    if not alpha_enabled():
        return _error("알파 테스트 기간이 끝났습니다. 로그인하거나 회원가입해 주세요.", status=403)

    data = _json(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    nickname = str(data.get("nickname") or "").strip()
    if not 2 <= len(nickname) <= 12:
        return _error("닉네임은 2~12자로 입력해 주세요.")
    styles = data.get("styles")
    if styles is not None and not isinstance(styles, list):
        return _error("스타일 형식이 올바르지 않습니다.")

    for _ in range(USERNAME_TRIES):
        username = _new_username()
        # _create_account 는 스스로 트랜잭션을 열고, 커밋된 뒤에 로그인시킨다.
        # 여기서 또 감싸면 세션 행이 아직 커밋 안 된 사용자를 가리키게 되므로 감싸지 않는다.
        try:
            user, profile = _create_account(
                request,
                username=username,
                nickname=nickname,
                password=None,
                email="",
                data={"styles": styles},
                body=(None, None, None),
                extra_meta={
                    "plan": ALPHA_PLAN,
                    "alpha": True,
                    "alpha_chat_used": 0,
                    "alpha_issued_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        except IntegrityError:      # 아이디가 겹쳤다 — 다시 뽑는다
            continue
        except ValueError as exc:   # 사전에 없는 스타일 · 개수 초과
            return _error(str(exc))
        payload = _auth_payload(request, user, profile)
        payload["data"]["alpha"] = quota_state(profile)
        payload["data"]["issued"] = True
        return JsonResponse(payload, status=201)

    return _error("알파 계정을 만들지 못했습니다. 잠시 뒤 다시 시도해 주세요.", status=500)


@require_GET
def alpha_quota(request):
    """남은 챗봇 횟수 조회. 차감하지 않는다."""
    if not request.user.is_authenticated:
        return JsonResponse({"status": "ok", "data": {"alpha": False, "limit": None,
                                                      "used": 0, "remaining": None}})
    return JsonResponse({"status": "ok", "data": quota_state(_profile(request.user, create=True))})


@require_POST
def alpha_chat_use(request):
    """챗봇 한 번 쓰기 직전에 부른다. 남아 있으면 1 차감하고 ok.

    남은 횟수가 0이면 429 로 막는다. 알파 계정이 아니면 차감하지 않고 통과시킨다
    (정식 회원과 관리자는 이 제한의 대상이 아니다).
    """
    if not request.user.is_authenticated:
        return _error("로그인이 필요합니다.", status=401)
    profile = _profile(request.user, create=True)
    # 베타 이후에는 요금제의 하루 한도(plan_views.plan_chat_use)가 센다 — 여기서 또 막지 않는다
    if not is_alpha(profile) or plan_policy.enforced():
        return JsonResponse({"status": "ok", "data": quota_state(profile)})

    limit = chat_quota()
    # 같은 사람이 여러 탭에서 동시에 보낼 수 있다 — 행을 잠그고 센다.
    with transaction.atomic():
        locked = type(profile).objects.select_for_update().get(pk=profile.pk)
        meta = dict(locked.profile_metadata or {})
        used = int(meta.get("alpha_chat_used") or 0)
        if used >= limit:
            return JsonResponse({
                "status": "error",
                "reason": f"알파테스트 계정의 챗봇 이용 횟수({limit}회)를 모두 사용하셨습니다.\n"
                          "챗봇 외의 기능은 그대로 이용하실 수 있습니다.",
                "data": {"alpha": True, "limit": limit, "used": limit, "remaining": 0},
            }, status=429)
        meta["alpha_chat_used"] = used + 1
        locked.profile_metadata = meta
        locked.save(update_fields=["profile_metadata"])

    profile.profile_metadata = meta
    return JsonResponse({"status": "ok", "data": quota_state(profile)})
