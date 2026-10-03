"""DRF 권한 — 운영 계정.

DRF 기본 제공 `IsAdminUser` 는 `is_staff` 하나만 본다. 그런데 이 프로젝트는
운영 계정을 `is_staff or is_superuser` 로 판정한다(운영 대시보드 미들웨어,
/api/auth/me 의 role). 슈퍼유저 플래그만 켜 둔 계정이 대시보드는 들어가는데
API 에서만 403 을 받는 어긋남이 없도록 같은 기준을 쓴다.
"""

from rest_framework.permissions import BasePermission


class IsOperator(BasePermission):
    """로그인한 운영 계정(is_staff 또는 is_superuser)만 통과."""

    message = "운영 계정만 사용할 수 있습니다."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser)
        )
