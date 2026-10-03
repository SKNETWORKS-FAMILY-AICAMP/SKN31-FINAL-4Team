"""Google 로그인 — OAuth 2.0 인가 코드 교환과 ID 토큰 확인.

── 흐름 ─────────────────────────────────────────────────────
  브라우저(Google 팝업) ─code─▶ 버셀 함수 ─▶ Django ─code+secret─▶ Google 토큰 서버
                                                   ◀── id_token ──┘

프론트는 Google Identity Services 의 `initCodeClient`(ux_mode=popup)로
**인가 코드**만 받는다. 코드를 토큰으로 바꾸는 일은 client_secret 을 아는
이 서버만 한다. 그래서 브라우저에는 비밀 값이 절대 내려가지 않는다.

── 왜 서명 검증 라이브러리를 쓰지 않나 ─────────────────────
id_token 을 브라우저에서 받은 것이 아니라, 이 서버가 TLS 로 Google 토큰
서버에 **직접** 요청해서 받았다. OpenID Connect Core §3.1.3.7 은 이 경우
TLS 서버 인증으로 서명 검증을 대신할 수 있다고 정한다. 대신 aud·iss·exp·
email_verified 는 반드시 확인한다. 덕분에 google-auth 같은 새 패키지 없이
표준 라이브러리만으로 돈다(requirements-api.txt 를 늘리지 않는다).

── 환경변수 (서버 .env) ─────────────────────────────────────
  GOOGLE_CLIENT_ID       Google Cloud 콘솔 → OAuth 클라이언트 ID(웹 애플리케이션)
  GOOGLE_CLIENT_SECRET   같은 클라이언트의 보안 비밀
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
# 팝업(ux_mode=popup) 방식의 코드는 redirect_uri 로 'postmessage' 를 쓴다.
POPUP_REDIRECT_URI = "postmessage"


class GoogleAuthError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 사유와 HTTP 상태를 담는다."""

    def __init__(self, reason, status=400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def client_id():
    return (os.getenv("GOOGLE_CLIENT_ID") or "").strip()


def client_secret():
    return (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()


def is_configured():
    return bool(client_id() and client_secret())


def _decode_jwt_payload(token):
    """JWT 가운데 조각(payload)만 base64url 로 푼다."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (IndexError, ValueError, UnicodeError):
        raise GoogleAuthError("Google 토큰 형식이 올바르지 않습니다.", status=502)


def exchange_code(code):
    """인가 코드를 Google 토큰 서버에서 id_token 으로 바꾼다."""
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id(),
        "client_secret": client_secret(),
        "redirect_uri": POPUP_REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 400 invalid_grant 는 대개 코드 재사용·만료, 또는 클라이언트 ID/비밀 불일치다.
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except (ValueError, UnicodeError):
            detail = ""
        if detail == "invalid_client":
            raise GoogleAuthError("서버의 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 값을 확인해 주세요.", status=503)
        raise GoogleAuthError("Google 인증이 만료됐거나 이미 사용됐습니다. 다시 시도해 주세요.", status=401)
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise GoogleAuthError("Google 인증 서버에 연결하지 못했습니다.", status=502)

    id_token = data.get("id_token")
    if not id_token:
        raise GoogleAuthError("Google 이 신원 정보를 돌려주지 않았습니다. scope 에 openid 가 있는지 확인해 주세요.", status=502)
    return verify_claims(_decode_jwt_payload(id_token))


def verify_claims(claims, now=None):
    """id_token 의 필수 항목을 확인하고, 서비스에 필요한 값만 추려 돌려준다."""
    now = time.time() if now is None else now
    if claims.get("aud") != client_id():
        raise GoogleAuthError("이 서비스용으로 발급된 Google 토큰이 아닙니다.", status=401)
    if claims.get("iss") not in VALID_ISSUERS:
        raise GoogleAuthError("Google 이 발급한 토큰이 아닙니다.", status=401)
    try:
        if float(claims.get("exp", 0)) < now:
            raise GoogleAuthError("Google 토큰이 만료됐습니다. 다시 시도해 주세요.", status=401)
    except (TypeError, ValueError):
        raise GoogleAuthError("Google 토큰의 만료 시각을 읽지 못했습니다.", status=401)
    sub = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").strip()
    verified = claims.get("email_verified") in (True, "true")
    if not sub or not email or not verified:
        raise GoogleAuthError("이메일이 확인된 Google 계정만 사용할 수 있습니다.", status=401)
    return {
        "sub": sub,
        "email": email,
        "name": str(claims.get("name") or "").strip(),
        "picture": str(claims.get("picture") or "").strip(),
    }
