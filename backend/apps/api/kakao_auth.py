"""카카오 로그인 — OAuth 2.0 인가 코드 교환과 사용자 정보 조회.

── 흐름 ─────────────────────────────────────────────────────
  브라우저 ─(카카오 로그인 페이지로 이동)─▶ 카카오 ─code+state─▶ 브라우저(redirect_uri)
  브라우저 ─code─▶ 버셀 함수 ─▶ Django ─code(+secret)─▶ 카카오 토큰 서버
                                        ◀── access_token ──┘
                                  Django ─access_token─▶ 카카오 사용자 정보 API

카카오 JS SDK v2 는 팝업 로그인을 없앴다. 그래서 SDK 없이 페이지 이동(redirect)
방식으로 간다. 코드를 토큰으로 바꾸는 일은 이 서버만 한다 — 브라우저에는 비밀 값이
내려가지 않는다. Google(google_auth.py)과 같게 표준 라이브러리만 쓴다.

── 환경변수 (서버 .env) ─────────────────────────────────────
  KAKAO_REST_API_KEY    카카오 디벨로퍼스 → 내 애플리케이션 → 앱 키 → REST API 키
  KAKAO_CLIENT_SECRET   (선택) 보안 → Client Secret 을 '사용함'으로 켰을 때만
  KAKAO_REDIRECT_URIS   (선택) 허용할 redirect_uri 목록(쉼표 구분). 비우면 http(s) 주소면 받는다.
                        어느 쪽이든 카카오 콘솔의 Redirect URI 에 같은 주소가 등록돼 있어야 한다.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
USER_URL = "https://kapi.kakao.com/v2/user/me"


class KakaoAuthError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 사유와 HTTP 상태를 담는다."""

    def __init__(self, reason, status=400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def client_id():
    return (os.getenv("KAKAO_REST_API_KEY") or "").strip()


def client_secret():
    return (os.getenv("KAKAO_CLIENT_SECRET") or "").strip()


def is_configured():
    return bool(client_id())


def redirect_allowed(uri):
    parsed = urllib.parse.urlsplit(uri or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc or len(uri) > 300:
        return False
    allowed = [u.strip() for u in (os.getenv("KAKAO_REDIRECT_URIS") or "").split(",") if u.strip()]
    return not allowed or uri in allowed


def authorize_url(redirect_uri, state):
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    })


def _read_error(exc):
    try:
        return json.loads(exc.read().decode("utf-8"))
    except (ValueError, UnicodeError):
        return {}


def exchange_code(code, redirect_uri):
    """인가 코드를 액세스 토큰으로 바꾸고, 그 토큰으로 사용자 정보를 읽는다."""
    fields = {
        "grant_type": "authorization_code",
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret():
        fields["client_secret"] = client_secret()
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            token = json.loads(resp.read().decode("utf-8")).get("access_token")
    except urllib.error.HTTPError as exc:
        # invalid_client — REST API 키나 Client Secret 이 틀렸다.
        # 그 밖(KOE320 등)은 대개 코드 재사용·만료, redirect_uri 불일치다.
        if _read_error(exc).get("error") == "invalid_client":
            raise KakaoAuthError("서버의 KAKAO_REST_API_KEY / KAKAO_CLIENT_SECRET 값을 확인해 주세요.", status=503)
        raise KakaoAuthError("카카오 인증이 만료됐거나 이미 사용됐습니다. 다시 시도해 주세요.", status=401)
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise KakaoAuthError("카카오 인증 서버에 연결하지 못했습니다.", status=502)
    if not token:
        raise KakaoAuthError("카카오가 토큰을 돌려주지 않았습니다.", status=502)
    return fetch_user(token)


def fetch_user(access_token):
    req = urllib.request.Request(
        USER_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError:
        raise KakaoAuthError("카카오 사용자 정보를 읽지 못했습니다. 다시 시도해 주세요.", status=401)
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise KakaoAuthError("카카오 사용자 정보 서버에 연결하지 못했습니다.", status=502)
    return parse_user(data)


def parse_user(data):
    """카카오 응답에서 서비스에 필요한 값만 추린다.

    이메일은 동의 항목을 켜고(비즈 앱 필요), 사용자가 동의했고, 카카오가 확인한
    주소일 때만 쓴다. 없으면 빈 값 — 카카오 가입은 이메일 없이도 된다.
    """
    sub = str((data or {}).get("id") or "")
    if not sub:
        raise KakaoAuthError("카카오 회원 번호를 받지 못했습니다.", status=502)
    account = data.get("kakao_account") or {}
    profile = account.get("profile") or {}
    email = str(account.get("email") or "").strip()
    if not (account.get("is_email_valid") and account.get("is_email_verified")):
        email = ""
    return {
        "sub": sub,
        "email": email,
        "name": str(profile.get("nickname") or "").strip(),
        "picture": str(profile.get("profile_image_url") or "").strip(),
    }
