"""데이터 API (data_api_views.py) — 키 관리 · 지표 내주기 · 한도 · 베타 잠금.

실행:  python manage.py test apps.api.test_data_api_views
"""
import os
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase

from apps.core.models import AppUser


def env(beta, **extra):
    values = {"FEEDIT_PUBLIC_BETA": "1" if beta else "0"}
    values.update({k: str(v) for k, v in extra.items()})
    return mock.patch.dict(os.environ, values)


class DataApiTests(TestCase):
    def setUp(self):
        cache.clear()          # 분당 횟수 칸이 시험 사이에 남지 않게
        self.biz_user = User.objects.create_user("biz01", "biz@example.com", "Secret!234")
        self.biz = AppUser.objects.create(user=self.biz_user, nickname="팀장", profile_metadata={"plan": "BUSINESS"})
        self.free_user = User.objects.create_user("free01", "free@example.com", "Secret!234")
        self.free = AppUser.objects.create(user=self.free_user, nickname="회원")
        self.admin_user = User.objects.create_user("boss01", "boss@example.com", "Secret!234", is_staff=True)
        AppUser.objects.create(user=self.admin_user, nickname="운영")
        self.out = Client()                 # 밖의 시스템 — 세션 없음

    def login(self, username):
        c = Client(enforce_csrf_checks=True)
        csrf = c.get("/api/auth/me").json()["data"]["csrf_token"]
        r = c.post("/api/auth/login", {"username": username, "password": "Secret!234"},
                   content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(r.status_code, 200, r.content)
        c.csrf = r.json()["data"]["csrf_token"]
        return c

    def send(self, c, method, body):
        return getattr(c, method)("/api/auth/data-keys", body, content_type="application/json",
                                  HTTP_X_CSRFTOKEN=c.csrf)

    def make_key(self, c, name="대시보드"):
        r = self.send(c, "post", {"name": name})
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["data"]["key"]

    def call(self, path, key=None, header="auth"):
        extra = {}
        if key and header == "auth":
            extra["HTTP_AUTHORIZATION"] = f"Bearer {key}"
        elif key:
            extra["HTTP_X_API_KEY"] = key
        return self.out.get(path, **extra)

    def meta(self, profile):
        profile.refresh_from_db()
        return profile.profile_metadata or {}

    # ── 베타 (지금) ──
    def test_beta_keeps_everything_closed(self):
        c = self.login("biz01")
        with env(beta=True):
            d = c.get("/api/auth/data-keys").json()["data"]
            self.assertEqual((d["enforced"], d["allowed"], d["keys"]), (False, False, []))
            r = self.send(c, "post", {"name": "x"})
            self.assertEqual((r.status_code, r.json()["code"]), (409, "BETA"))
            r = self.call("/api/data/trend?term=x", key="fdk_1_ab12cd34_" + "a" * 30)
            self.assertEqual((r.status_code, r.json()["code"]), (403, "BETA"))
            self.assertEqual(r["Cache-Control"], "no-store")
        self.assertNotIn("data_api_keys", self.meta(self.biz))

    # ── 베타 이후 ──
    def test_business_key_flow(self):
        c = self.login("biz01")
        with env(beta=False):
            key = self.make_key(c)
            self.assertTrue(key.startswith(f"fdk_{self.biz.id}_"))
            listed = c.get("/api/auth/data-keys").json()["data"]
            self.assertEqual(len(listed["keys"]), 1)
            self.assertNotIn(key, str(listed))                  # 원문은 다시 나오지 않는다
            self.assertTrue(listed["allowed"])

            r = self.call("/api/data", key)
            self.assertEqual(r.status_code, 200, r.content)
            self.assertIn("trend", [m["metric"] for m in r.json()["data"]["metrics"]])

            r = self.call("/api/data/trend?term=발레코어", key)
            self.assertEqual(r.status_code, 200, r.content)    # 화면과 같은 views.trend 의 답
            self.assertIn(r.json()["status"], ("ok", "empty"))
            self.assertEqual(r["Cache-Control"], "no-store")
            self.assertEqual(r["X-RateLimit-Remaining"], str(10000 - 2))

            self.assertEqual(self.call("/api/data/terms", key, header="x-api-key").status_code, 200)
            meta = self.meta(self.biz)
            self.assertEqual(meta["data_api_usage"]["count"], 3)
            self.assertTrue(meta["data_api_keys"][0]["last_used_at"])

    def test_free_plan_and_downgrade(self):
        with env(beta=False):
            r = self.send(self.login("free01"), "post", {"name": "x"})
            self.assertEqual((r.status_code, r.json()["code"]), (403, "PLAN"))

            c = self.login("biz01")
            key = self.make_key(c)
            AppUser.objects.filter(pk=self.biz.pk).update(
                profile_metadata={**self.meta(self.biz), "plan": "FREE"})
            r = self.call("/api/data/trend?term=x", key)
            self.assertEqual((r.status_code, r.json()["code"]), (403, "PLAN"))
            # 내려간 뒤에도 폐기는 된다
            key_id = c.get("/api/auth/data-keys").json()["data"]["keys"][0]["id"]
            r = self.send(c, "delete", {"key_id": key_id})
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.json()["data"]["keys"], [])
            AppUser.objects.filter(pk=self.biz.pk).update(
                profile_metadata={**self.meta(self.biz), "plan": "BUSINESS"})
            r = self.call("/api/data/trend?term=x", key)
            self.assertEqual((r.status_code, r.json()["code"]), (401, "INVALID_KEY"))   # 폐기한 키

    def test_bad_keys_and_unknown_metric(self):
        c = self.login("biz01")
        with env(beta=False):
            key = self.make_key(c)
            self.assertEqual(self.call("/api/data/trend").json()["code"], "NO_KEY")
            self.assertEqual(self.call("/api/data/trend", "nope").status_code, 401)
            forged = key[:-4] + ("AAAA" if not key.endswith("AAAA") else "BBBB")
            self.assertEqual(self.call("/api/data/trend", forged).json()["code"], "INVALID_KEY")
            other = f"fdk_{self.free.id}_" + key.split("_", 2)[2]          # 남의 계정 번호로 바꿔 끼움
            self.assertEqual(self.call("/api/data/trend", other).status_code, 401)
            r = self.call("/api/data/products", key)
            self.assertEqual((r.status_code, r.json()["code"]), (404, "NO_METRIC"))
            self.assertNotIn("data_api_usage", self.meta(self.biz))       # 없는 지표는 횟수를 쓰지 않는다

    def test_limits(self):
        c = self.login("biz01")
        with env(beta=False, FEEDIT_DATA_API_PER_DAY=2):
            key = self.make_key(c)
            self.assertEqual(self.call("/api/data", key).status_code, 200)
            self.assertEqual(self.call("/api/data", key).status_code, 200)
            r = self.call("/api/data", key)
            self.assertEqual((r.status_code, r.json()["code"]), (429, "DAILY_LIMIT"))
        cache.clear()
        AppUser.objects.filter(pk=self.biz.pk).update(
            profile_metadata={**self.meta(self.biz), "data_api_usage": {}})
        with env(beta=False, FEEDIT_DATA_API_PER_MIN=1):
            self.assertEqual(self.call("/api/data", key).status_code, 200)
            r = self.call("/api/data", key)
            self.assertEqual((r.status_code, r.json()["code"]), (429, "RATE_LIMITED"))
            self.assertEqual(r["Retry-After"], "60")

    def test_admin_and_key_cap(self):
        c = self.login("boss01")
        with env(beta=False):
            keys = [self.make_key(c, f"키{i}") for i in range(5)]
            r = self.send(c, "post", {"name": "6번째"})
            self.assertEqual(r.status_code, 409, r.content)
            self.assertEqual(self.call("/api/data", keys[0]).status_code, 200)

    def test_login_required_for_key_management(self):
        self.assertEqual(Client().get("/api/auth/data-keys").status_code, 401)
