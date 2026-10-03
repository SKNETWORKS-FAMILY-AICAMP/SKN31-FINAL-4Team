"""요금제 API(plan_views.py) — 신청 · 관리자 승인 · 해지 · 챗봇 하루 횟수.

베타(FEEDIT_PUBLIC_BETA) 켜짐/꺼짐 두 경우를 모두 본다.
  · 켜짐 — 지금 운영 상태. 신청을 받지 않고, 로그인 응답의 billing 은 전부 열려 있어야 한다.
  · 꺼짐 — 베타 이후. 표대로 막고, 신청 → 승인으로 요금제가 바뀐다.

실행:  python manage.py test apps.api.test_plan_views
"""
import os
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase

from apps.api import plan_policy
from apps.core.models import AppUser, Notification


def beta(on):
    return mock.patch.dict(os.environ, {"FEEDIT_PUBLIC_BETA": "1" if on else "0",
                                        "FEEDIT_PLAN_SECRET": "test-secret"})


class PlanApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("member01", "member01@example.com", "Secret!234")
        self.profile = AppUser.objects.create(user=self.user, nickname="회원")
        self.admin = User.objects.create_user("boss01", "boss@example.com", "Secret!234", is_staff=True)
        AppUser.objects.create(user=self.admin, nickname="운영")
        self.c = self.login("member01")

    def login(self, username):
        c = Client(enforce_csrf_checks=True)
        csrf = c.get("/api/auth/me").json()["data"]["csrf_token"]
        r = c.post("/api/auth/login", {"username": username, "password": "Secret!234"},
                   content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(r.status_code, 200, r.content)
        c.csrf = r.json()["data"]["csrf_token"]
        return c

    def post(self, c, path, body):
        return c.post(path, body, content_type="application/json", HTTP_X_CSRFTOKEN=c.csrf)

    def delete(self, c, path):
        return c.delete(path, {}, content_type="application/json", HTTP_X_CSRFTOKEN=c.csrf)

    def meta(self):
        self.profile.refresh_from_db()
        return self.profile.profile_metadata or {}

    # ── 베타 (지금) ──
    def test_beta_changes_nothing(self):
        with beta(True):
            me = self.c.get("/api/auth/me").json()["data"]["user"]
            self.assertEqual(me["plan"], "FREE")            # 예전 칸은 그대로
            self.assertFalse(me["billing"]["enforced"])
            self.assertTrue(me["billing"]["features"]["report_export"])
            self.assertEqual(me["billing"]["features"]["trend_edit"], list(plan_policy.EDIT_TABS))
            r = self.post(self.c, "/api/auth/plan-request", {"plan": "PRO"})
            self.assertEqual(r.status_code, 409, r.content)
            self.assertNotIn("plan_request", self.meta())
            # 챗봇 횟수도 세지 않는다
            r = self.post(self.c, "/api/auth/plan-chat-use", {})
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.json()["data"]["enforced"])
            self.assertNotIn("plan_chat", self.meta())
            anon = Client().get("/api/auth/me").json()["data"]
            self.assertFalse(anon["billing"]["enforced"])

    # ── 베타 이후 ──
    def test_request_approve_and_cancel(self):
        with beta(False):
            r = self.post(self.c, "/api/auth/plan-request", {"plan": "PRO", "note": "실무용"})
            self.assertEqual(r.status_code, 201, r.content)
            self.assertEqual(r.json()["data"]["request"]["status"], "PENDING")
            self.assertEqual(r.json()["data"]["plan"], "FREE")       # 승인 전에는 그대로 프리

            # 일반 회원은 심사할 수 없다
            self.assertEqual(self.c.get("/api/auth/plan-requests").status_code, 403)
            self.assertEqual(self.post(self.c, "/api/auth/plan-review",
                                       {"user_id": self.profile.id, "approve": True}).status_code, 403)

            boss = self.login("boss01")
            items = boss.get("/api/auth/plan-requests").json()["data"]["items"]
            self.assertEqual([(i["user_id"], i["plan"], i["note"]) for i in items],
                             [(self.profile.id, "PRO", "실무용")])
            r = self.post(boss, "/api/auth/plan-review", {"user_id": self.profile.id, "approve": True})
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(self.meta()["plan"], "PRO")
            self.assertTrue(Notification.objects.filter(user=self.profile, kind="PLAN_REVIEW").exists())

            me = self.c.get("/api/auth/me").json()["data"]["user"]["billing"]
            self.assertEqual((me["plan"], me["features"]["report_export"]), ("PRO", True))

            # 해지 — 승인 없이 바로 프리
            r = self.post(self.c, "/api/auth/plan-request", {"plan": "FREE"})
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(self.meta()["plan"], "FREE")
            self.assertEqual([h["kind"] for h in self.meta()["plan_history"]], ["APPROVED", "CANCELLED"])

    def test_reject_with_reason_and_pending_cancel(self):
        with beta(False):
            self.post(self.c, "/api/auth/plan-request", {"plan": "BUSINESS", "company": "피딧"})
            boss = self.login("boss01")
            r = self.post(boss, "/api/auth/plan-review",
                          {"user_id": self.profile.id, "approve": False, "reason": "연락처 확인 불가"})
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(self.meta().get("plan"), None)
            self.assertEqual(self.meta()["plan_request"]["reason"], "연락처 확인 불가")
            # 두 번 심사할 수 없다
            self.assertEqual(self.post(boss, "/api/auth/plan-review",
                                       {"user_id": self.profile.id, "approve": True}).status_code, 409)
            # 다시 신청하고 직접 취소
            self.post(self.c, "/api/auth/plan-request", {"plan": "PRO"})
            r = self.delete(self.c, "/api/auth/plan-request")
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(self.meta()["plan_request"]["status"], "CANCELLED")
            self.assertEqual(boss.get("/api/auth/plan-requests").json()["data"]["items"], [])

    def test_business_needs_company_and_admin_cannot_request(self):
        with beta(False):
            self.assertEqual(self.post(self.c, "/api/auth/plan-request", {"plan": "BUSINESS"}).status_code, 400)
            self.assertEqual(self.post(self.c, "/api/auth/plan-request", {"plan": "FREE"}).status_code, 409)
            boss = self.login("boss01")
            self.assertEqual(self.post(boss, "/api/auth/plan-request", {"plan": "PRO"}).status_code, 409)

    def test_admin_revoke(self):
        with beta(False):
            meta = dict(self.profile.profile_metadata or {}, plan="BUSINESS")
            AppUser.objects.filter(pk=self.profile.pk).update(profile_metadata=meta)
            boss = self.login("boss01")
            r = self.post(boss, "/api/auth/plan-review", {"user_id": self.profile.id, "op": "revoke"})
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(self.meta()["plan"], "FREE")

    def test_free_chat_daily_limit_and_ticket(self):
        with beta(False):
            for i in range(plan_policy.FREE_CHAT_DAILY):
                r = self.post(self.c, "/api/auth/plan-chat-use", {})
                self.assertEqual(r.status_code, 200, (i, r.content))
            data = r.json()["data"]
            self.assertEqual(data["chat"]["remaining"], 0)
            self.assertTrue(data["ticket"].startswith("v1."))
            r = self.post(self.c, "/api/auth/plan-chat-use", {})
            self.assertEqual(r.status_code, 429)
            self.assertEqual(r.json()["data"]["chat"]["remaining"], 0)
            # 운영 계정은 세기만 하고 막지 않는다
            boss = self.login("boss01")
            for _ in range(plan_policy.FREE_CHAT_DAILY + 1):
                self.assertEqual(self.post(boss, "/api/auth/plan-chat-use", {}).status_code, 200)

    def test_alpha_account_becomes_free_after_beta(self):
        meta = dict(self.profile.profile_metadata or {}, plan="TEST", alpha=True, alpha_chat_used=20)
        AppUser.objects.filter(pk=self.profile.pk).update(profile_metadata=meta)
        with beta(True):
            self.assertTrue(self.c.get("/api/auth/alpha-quota").json()["data"]["alpha"])
        with beta(False):
            self.assertFalse(self.c.get("/api/auth/alpha-quota").json()["data"]["alpha"])
            billing = self.c.get("/api/auth/me").json()["data"]["user"]["billing"]
            self.assertEqual(billing["plan"], "FREE")
            r = Client().post("/api/auth/alpha", {"nickname": "새손님"}, content_type="application/json")
            self.assertEqual(r.status_code, 403, r.content)       # 알파 발급도 끝난다
