"""운영 대시보드(/admin-dashboard/)는 운영 계정만 들어온다.

── 왜 미들웨어인가 ──────────────────────────────────────────
뷰마다 붙은 `@login_required` 는 "로그인했는가"만 본다. 그런데 이 Django 는
앱 로그인(`apps/api/auth_views.py` 의 `django_login`)과 **세션을 공유**한다.
즉 누구나 FEEDiT 에 회원가입하면 유효한 sessionid 를 받고, 그 쿠키를
`/admin-dashboard/` 에 그대로 내밀면 `@login_required` 를 통과해 버렸다.
권한 검사는 로그인 폼 안에만 있었으므로, 폼을 거치지 않으면 검사도 없었다.

뷰 43개에 데코레이터를 하나씩 더 붙이는 대신 길목을 막는다. 새 뷰를 추가해도
자동으로 적용되고, 빠뜨릴 자리가 생기지 않는다.
(뷰의 `@login_required` 는 그대로 둔다 — 겹쳐서 손해 볼 것이 없다.)

── 어디에 놓나 ──────────────────────────────────────────────
`AuthenticationMiddleware` 뒤. 그래야 `request.user` 가 채워져 있다.
"""

from __future__ import annotations

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from .models import DashboardOTPDevice
from .security import (
    dashboard_operator_allowed,
    otp_required,
    otp_verified,
    password_verified,
)

PREFIX = "/admin-dashboard/"
LOGIN_URL = "/admin-dashboard/login/"
# 로그인·로그아웃은 막으면 안 된다. 막으면 운영자가 들어올 길이 없어진다.
OTP_SETUP_URL = "/admin-dashboard/otp/setup/"
OTP_VERIFY_URL = "/admin-dashboard/otp/verify/"
EXEMPT = frozenset({
    LOGIN_URL,
    "/admin-dashboard/logout/",
    OTP_SETUP_URL,
    OTP_VERIFY_URL,
})

DENIED_HTML = (
    "<!doctype html><meta charset='utf-8'>"
    "<title>403 — 권한 없음</title>"
    "<div style=\"font:15px/1.7 system-ui,sans-serif;max-width:34em;margin:18vh auto;padding:0 24px\">"
    "<h1 style='font-size:19px;margin:0 0 10px'>운영 계정만 들어올 수 있습니다.</h1>"
    "<p style='color:#555;margin:0'>이 화면은 FEEDiT 운영자용입니다. "
    "일반 계정으로는 열 수 없습니다.</p></div>"
)


class DashboardStaffMiddleware:
    """`/admin-dashboard/` 앞에 서서 is_staff 를 확인한다."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(PREFIX) and path not in EXEMPT:
            user = getattr(request, "user", None)

            # 로그인조차 안 했으면 로그인 화면으로 (원래 가려던 곳을 기억해 둔다).
            if user is None or not user.is_authenticated:
                return redirect_to_login(request.get_full_path(), LOGIN_URL)

            # 로그인은 했는데 운영 계정이 아니면 여기서 끝.
            #   ★ 로그인 화면으로 되돌리지 않는다. 이미 로그인한 사람을
            #     로그인 화면으로 보내면 무한 반복이 된다.
            if not dashboard_operator_allowed(user):
                return HttpResponseForbidden(DENIED_HTML)

            if otp_required():
                # 일반 앱 세션만 가진 운영 계정도 비밀번호를 다시 확인해야 한다.
                if not password_verified(request):
                    return redirect_to_login(request.get_full_path(), LOGIN_URL)

                if not otp_verified(request):
                    has_device = DashboardOTPDevice.objects.filter(
                        user=user,
                        confirmed=True,
                    ).exists()
                    return redirect(OTP_VERIFY_URL if has_device else OTP_SETUP_URL)

        return self.get_response(request)
