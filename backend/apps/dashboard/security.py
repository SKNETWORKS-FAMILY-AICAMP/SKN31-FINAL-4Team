"""관리자 대시보드의 저비용 2단계 인증 도구."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import DashboardOTPDevice


PASSWORD_SESSION_KEY = "dashboard_password_verified_user_id"
OTP_SESSION_KEY = "dashboard_otp_verified_user_id"
NEXT_SESSION_KEY = "dashboard_login_next"
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6
RECOVERY_CODE_COUNT = 10


def otp_required() -> bool:
    return bool(getattr(settings, "DASHBOARD_OTP_REQUIRED", False))


def dashboard_operator_allowed(user) -> bool:
    """활성 운영 계정이며, 설정된 경우 팀 이메일 허용 목록에도 속하는지 확인한다."""

    if not (
        user
        and user.is_authenticated
        and user.is_active
        and (user.is_staff or user.is_superuser)
    ):
        return False

    allowed = {
        str(email).strip().casefold()
        for email in getattr(settings, "DASHBOARD_ALLOWED_EMAILS", ())
        if str(email).strip()
    }
    if not allowed:
        return True
    return str(getattr(user, "email", "")).strip().casefold() in allowed


def _session_matches(request, key: str) -> bool:
    user = getattr(request, "user", None)
    return bool(
        user
        and user.is_authenticated
        and str(request.session.get(key, "")) == str(user.pk)
    )


def password_verified(request) -> bool:
    return _session_matches(request, PASSWORD_SESSION_KEY)


def otp_verified(request) -> bool:
    return _session_matches(request, OTP_SESSION_KEY)


def dashboard_session_age() -> int:
    """관리자 유휴 세션 수명(초)을 안전한 양수로 반환한다."""

    return max(60, int(getattr(settings, "DASHBOARD_SESSION_AGE", 3600)))


def touch_dashboard_session(request) -> int:
    """현재 관리자 활동을 기준으로 세션 만료 시각을 다시 잡는다."""

    age = dashboard_session_age()
    request.session.set_expiry(age)
    return age


def mark_password_verified(request) -> None:
    request.session[PASSWORD_SESSION_KEY] = str(request.user.pk)
    request.session.pop(OTP_SESSION_KEY, None)
    touch_dashboard_session(request)


def mark_otp_verified(request) -> None:
    request.session[OTP_SESSION_KEY] = str(request.user.pk)
    touch_dashboard_session(request)


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def provisioning_uri(user, secret: str) -> str:
    issuer = getattr(settings, "DASHBOARD_OTP_ISSUER", "FEEDiT Admin")
    label = quote(f"{issuer}:{user.get_username()}", safe="")
    query = urlencode({"secret": secret, "issuer": issuer, "digits": TOTP_DIGITS, "period": TOTP_STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"


def provisioning_qr_svg(user, secret: str) -> str:
    """OTP URI를 외부 서비스에 보내지 않고 스캔 가능한 SVG로 만든다."""

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
        image_factory=qrcode.image.svg.SvgPathFillImage,
    )
    qr.add_data(provisioning_uri(user, secret))
    qr.make(fit=True)
    image = qr.make_image(attrib={
        "class": "otp-qr",
        "role": "img",
        "aria-label": "FEEDiT 관리자 OTP 등록 QR 코드",
    })
    return image.to_string(encoding="unicode")


def _totp(secret: str, counter: int) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def matching_counter(secret: str, token: str, *, now: float | None = None, last_used: int | None = None) -> int | None:
    normalized = "".join(ch for ch in str(token) if ch.isdigit())
    if len(normalized) != TOTP_DIGITS:
        return None
    current = int((time.time() if now is None else now) // TOTP_STEP_SECONDS)
    for offset in (-1, 0, 1):
        counter = current + offset
        if last_used is not None and counter <= last_used:
            continue
        if constant_time_compare(_totp(secret, counter), normalized):
            return counter
    return None


def _recovery_digest(code: str) -> str:
    normalized = "".join(ch for ch in code.upper() if ch.isalnum())
    return salted_hmac(
        "dashboard-recovery-code",
        normalized,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def generate_recovery_codes() -> list[str]:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(alphabet) for _ in range(12))
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
    return codes


def get_or_create_device(user) -> DashboardOTPDevice:
    device, _ = DashboardOTPDevice.objects.get_or_create(
        user=user,
        defaults={"secret": generate_secret()},
    )
    return device


def confirm_device(user, token: str) -> list[str] | None:
    with transaction.atomic():
        device = DashboardOTPDevice.objects.select_for_update().get(user=user)
        counter = matching_counter(
            device.secret,
            token,
            last_used=device.last_used_counter,
        )
        if counter is None:
            return None
        codes = generate_recovery_codes()
        device.confirmed = True
        device.last_used_counter = counter
        device.recovery_code_hashes = [_recovery_digest(code) for code in codes]
        device.save(update_fields=[
            "confirmed", "last_used_counter", "recovery_code_hashes", "updated_at",
        ])
        return codes


def verify_device(user, token: str) -> tuple[bool, bool]:
    """(성공, 복구 코드 사용 여부)를 반환한다."""

    with transaction.atomic():
        device = DashboardOTPDevice.objects.select_for_update().get(
            user=user,
            confirmed=True,
        )
        counter = matching_counter(
            device.secret,
            token,
            last_used=device.last_used_counter,
        )
        if counter is not None:
            device.last_used_counter = counter
            device.save(update_fields=["last_used_counter", "updated_at"])
            return True, False

        candidate = _recovery_digest(token)
        remaining = list(device.recovery_code_hashes or [])
        for index, stored in enumerate(remaining):
            if constant_time_compare(stored, candidate):
                remaining.pop(index)
                device.recovery_code_hashes = remaining
                device.save(update_fields=["recovery_code_hashes", "updated_at"])
                return True, True
        return False, False


def _attempt_key(kind: str, identity: str) -> str:
    digest = hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()
    return f"dashboard-auth:{kind}:{digest}"


def register_failed_attempt(kind: str, identity: str, *, limit: int = 5, window: int = 300) -> bool:
    """실패를 기록하고 제한에 도달했으면 True를 반환한다."""

    key = _attempt_key(kind, identity)
    if cache.add(key, 1, timeout=window):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window)
            count = 1
    return count >= limit


def attempts_blocked(kind: str, identity: str, *, limit: int = 5) -> bool:
    return int(cache.get(_attempt_key(kind, identity), 0) or 0) >= limit


def clear_attempts(kind: str, identity: str) -> None:
    cache.delete(_attempt_key(kind, identity))
