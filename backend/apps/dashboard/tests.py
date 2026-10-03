"""운영 대시보드 접근 제어 — 보고된 권한 상승 경로를 그대로 재현한다.

일반 회원이 앱 로그인으로 받은 세션을 /admin-dashboard/ 에 내밀면
들어가지던 문제(2026-09-21)를 막았는지 확인한다.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase


class DashboardAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.normal = User.objects.create_user(
            username="normal", password="pw-normal-12345", is_staff=False
        )
        self.staff = User.objects.create_user(
            username="ops", password="pw-ops-12345", is_staff=True
        )

    def test_익명은_로그인_화면으로(self):
        res = Client().get("/admin-dashboard/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/admin-dashboard/login/", res["Location"])

    def test_일반_회원_세션으로는_못_들어온다(self):
        """★ 이게 핵심. force_login 은 앱 로그인이 만드는 세션과 같다."""
        c = Client()
        c.force_login(self.normal)
        self.assertEqual(c.get("/admin-dashboard/").status_code, 403)

    def test_일반_회원은_하위_화면도_못_연다(self):
        c = Client()
        c.force_login(self.normal)
        for path in (
            "/admin-dashboard/collection/targets/",
            "/admin-dashboard/collection/raw-documents/",
            "/admin-dashboard/normalization/products/",
        ):
            with self.subTest(path=path):
                self.assertEqual(c.get(path).status_code, 403)

    def test_운영_계정은_들어온다(self):
        c = Client()
        c.force_login(self.staff)
        self.assertNotIn(c.get("/admin-dashboard/").status_code, (403, 302))

    def test_로그인_화면은_일반_회원도_열린다(self):
        """막아 버리면 운영 계정으로 갈아탈 길이 없어진다(무한 반복)."""
        c = Client()
        c.force_login(self.normal)
        res = c.get("/admin-dashboard/login/")
        self.assertEqual(res.status_code, 200)

    def test_일반_회원_비밀번호로는_로그인_안_된다(self):
        res = Client().post(
            "/admin-dashboard/login/",
            {"username": "normal", "password": "pw-normal-12345"},
        )
        self.assertEqual(res.status_code, 200)   # 폼이 그대로 다시 뜬다
        self.assertFalse(res.wsgi_request.user.is_authenticated)

    def test_next_로_외부_사이트에_못_보낸다(self):
        """//evil.example 은 '/' 로 시작하지만 바깥이다."""
        res = Client().post(
            "/admin-dashboard/login/?next=//evil.example/x",
            {"username": "ops", "password": "pw-ops-12345"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertNotIn("evil.example", res["Location"])
