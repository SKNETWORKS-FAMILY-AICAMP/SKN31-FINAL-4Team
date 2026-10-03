from __future__ import annotations

from django.conf import settings
from django.db import models


class DashboardOTPDevice(models.Model):
    """관리자 대시보드 전용 TOTP 장치.

    일반 사용자 로그인과 분리해 운영 계정마다 하나의 인증 앱을 연결한다.
    복구 코드는 원문을 저장하지 않고 서버 비밀키 기반 HMAC만 저장한다.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboard_otp_device",
    )
    secret = models.CharField(max_length=64)
    confirmed = models.BooleanField(default=False)
    recovery_code_hashes = models.JSONField(default=list, blank=True)
    last_used_counter = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dashboard_otp_device"

    def __str__(self):
        state = "연결됨" if self.confirmed else "연결 대기"
        return f"{self.user} · {state}"
