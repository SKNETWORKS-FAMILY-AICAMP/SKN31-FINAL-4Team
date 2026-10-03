"""회원가입 이메일 인증 — 6자리 인증번호를 메일로 보내고 확인한다.

인증번호와 '확인됨' 표시는 모두 서버 세션에만 둔다(Google 가입 대기와 같은 방식).
번호는 평문이 아니라 SECRET_KEY 로 서명한 해시로 보관한다.

── 환경변수 (서버 .env) ─────────────────────────────────────
  EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS,
  DEFAULT_FROM_EMAIL — config/settings.py 참고.
  EMAIL_HOST 가 비어 있으면 DEBUG 에서는 콘솔(runserver 로그)에 메일을 찍고,
  운영에서는 '발송이 설정되지 않았다'고 안내한다.
"""

from __future__ import annotations

import secrets
import time

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils.crypto import constant_time_compare, salted_hmac

CODE_KEY = "email_code"
VERIFIED_KEY = "email_verified"
CODE_TTL = 10 * 60          # 인증번호 유효 시간
VERIFIED_TTL = 30 * 60      # 확인 뒤 가입을 마쳐야 하는 시간
RESEND_GAP = 60             # 같은 주소로 다시 보내기까지 기다리는 시간
MAX_TRIES = 5               # 번호 하나로 틀릴 수 있는 횟수


class EmailVerifyError(Exception):
    def __init__(self, reason, status=400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def is_configured():
    # 콘솔 백엔드는 EMAIL_HOST 가 없을 때의 기본값이다 — 운영에서는 '설정 안 됨'으로 본다.
    # (테스트는 Django 가 locmem 백엔드로 바꿔 끼우므로 설정된 것으로 본다)
    console = settings.MAILERS["default"]["BACKEND"].endswith("console.EmailBackend")
    return settings.DEBUG or not console


def _hash(email, code):
    return salted_hmac("feedit.email-code", f"{email}:{code}").hexdigest()


def send_code(request, email):
    if not is_configured():
        raise EmailVerifyError("이메일 발송이 아직 설정되지 않았습니다. 관리자에게 문의해 주세요.", status=503)
    # 세션을 새로 열어 가며 같은 주소로 메일을 퍼붓지 못하게 주소 단위로도 막는다.
    if not cache.add(f"email-code-gap:{email}", 1, RESEND_GAP):
        raise EmailVerifyError("인증번호를 방금 보냈습니다. 1분 뒤에 다시 요청해 주세요.", status=429)
    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        send_mail(
            "[FEEDiT] 이메일 인증번호",
            f"FEEDiT 회원가입 인증번호는 {code} 입니다.\n"
            f"{CODE_TTL // 60}분 안에 입력해 주세요.\n\n"
            "본인이 요청하지 않았다면 이 메일은 무시하셔도 됩니다.",
            None,   # DEFAULT_FROM_EMAIL
            [email],
        )
    except Exception:
        cache.delete(f"email-code-gap:{email}")
        raise EmailVerifyError("인증 메일을 보내지 못했습니다. 주소를 확인하고 다시 시도해 주세요.", status=502)
    request.session[CODE_KEY] = {
        "email": email,
        "hash": _hash(email, code),
        "expires_at": time.time() + CODE_TTL,
        "tries": 0,
    }
    request.session.pop(VERIFIED_KEY, None)


def check_code(request, email, code):
    pending = request.session.get(CODE_KEY)
    if not isinstance(pending, dict) or pending.get("email") != email:
        raise EmailVerifyError("먼저 이 주소로 인증번호를 받아 주세요.")
    if float(pending.get("expires_at") or 0) < time.time():
        request.session.pop(CODE_KEY, None)
        raise EmailVerifyError("인증번호가 만료됐습니다. 다시 받아 주세요.")
    if int(pending.get("tries") or 0) >= MAX_TRIES:
        request.session.pop(CODE_KEY, None)
        raise EmailVerifyError("인증번호를 여러 번 틀렸습니다. 새 번호를 받아 주세요.", status=429)
    if not constant_time_compare(pending.get("hash") or "", _hash(email, code)):
        pending["tries"] = int(pending.get("tries") or 0) + 1
        request.session[CODE_KEY] = pending
        raise EmailVerifyError("인증번호가 맞지 않습니다.")
    request.session.pop(CODE_KEY, None)
    request.session[VERIFIED_KEY] = {"email": email, "expires_at": time.time() + VERIFIED_TTL}


def verified_email(request):
    """확인을 마친 이메일(아직 유효하면). 없으면 빈 문자열."""
    done = request.session.get(VERIFIED_KEY)
    if not isinstance(done, dict) or float(done.get("expires_at") or 0) < time.time():
        return ""
    return str(done.get("email") or "")


def clear(request):
    request.session.pop(CODE_KEY, None)
    request.session.pop(VERIFIED_KEY, None)
