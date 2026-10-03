"""관리자용 수집 API(/api/crawl-targets/, /api/crawl-runs/) 권한 — 2026-09-23.

permission_classes 가 없어서 DRF 기본값(AllowAny)이 적용되던 문제를 막았는지 본다.
익명·일반 회원은 읽기도 쓰기도 못 하고, 운영 계정만 통과해야 한다.
"""

import os

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

# /api/ 공유 토큰이 설정된 환경에서도 권한 검사까지 닿도록 머리글을 붙인다.
TOKEN = {"HTTP_X_FEEDIT_TOKEN": (os.getenv("FEEDIT_API_TOKEN") or "").strip()}

PATHS = ("/api/crawl-targets/", "/api/crawl-runs/")


class CrawlApiPermissionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.normal = User.objects.create_user(username="normal", password="pw-normal-12345")
        self.staff = User.objects.create_user(username="ops", password="pw-ops-12345", is_staff=True)
        # 슈퍼유저 플래그만 켠 계정 — 대시보드와 같은 기준으로 통과해야 한다
        self.superonly = User.objects.create_user(username="root", password="pw-root-12345",
                                                  is_superuser=True, is_staff=False)

    def test_anonymous_is_rejected(self):
        c = Client()
        for path in PATHS:
            with self.subTest(path=path):
                self.assertIn(c.get(path, **TOKEN).status_code, (401, 403))
        res = c.post("/api/crawl-targets/", {}, content_type="application/json", **TOKEN)
        self.assertIn(res.status_code, (401, 403))

    def test_normal_member_is_rejected(self):
        c = Client()
        c.force_login(self.normal)
        for path in PATHS:
            with self.subTest(path=path):
                self.assertEqual(c.get(path, **TOKEN).status_code, 403)

    def test_operators_can_read(self):
        for user in (self.staff, self.superonly):
            c = Client()
            c.force_login(user)
            for path in PATHS:
                with self.subTest(user=user.username, path=path):
                    self.assertEqual(c.get(path, **TOKEN).status_code, 200)
