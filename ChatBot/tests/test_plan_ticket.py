"""요금제 확인증 — Django 가 서명하고 챗봇이 검사한다 (2026-10-03).

베타 동안(PUBLIC_BETA)은 확인증을 보지 않고 예전처럼 BUSINESS 로 연다.
베타가 끝나면 요청이 적은 plan 은 믿지 않는다 — 확인증이 없거나 틀리면 FREE.

서명 코드(backend/apps/api/plan_policy.py)를 파일 경로로 직접 불러와 **같은 모양인지** 맞춰 본다.
챗봇 이미지에는 backend 폴더가 없으므로, 그 파일이 없으면 그 시험만 건너뛴다.
"""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from app import plans

SIGNER = Path(__file__).resolve().parents[2] / "backend" / "apps" / "api" / "plan_policy.py"


def load_signer():
    spec = importlib.util.spec_from_file_location("feedit_plan_policy", SIGNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VerifyTests(unittest.TestCase):
    @unittest.skipUnless(SIGNER.exists(), "backend/ 가 없는 배포 이미지")
    def test_django_signed_ticket_is_accepted(self):
        sign = load_signer().sign_ticket
        t = sign(42, "PRO", now=1_000, secret="s3cret")
        self.assertEqual(plans.verify_ticket(t, now=1_100, secret="s3cret"), {"user": "42", "plan": "PRO"})
        # 운영 계정은 챗봇이 아는 가장 넓은 BUSINESS 로 온다
        t = sign(1, "ADMIN", now=1_000, secret="s3cret")
        self.assertEqual(plans.verify_ticket(t, now=1_000, secret="s3cret")["plan"], "BUSINESS")

    @unittest.skipUnless(SIGNER.exists(), "backend/ 가 없는 배포 이미지")
    def test_rejects_wrong_key_expired_and_tampered(self):
        sign = load_signer().sign_ticket
        t = sign(42, "PRO", now=1_000, ttl=600, secret="s3cret")
        self.assertIsNone(plans.verify_ticket(t, now=1_100, secret="other"))
        self.assertIsNone(plans.verify_ticket(t, now=1_601, secret="s3cret"))
        head, body, sig = t.split(".")
        import base64
        forged = json.dumps({"u": "42", "p": "BUSINESS", "e": 9_999_999}, separators=(",", ":"))
        forged = base64.urlsafe_b64encode(forged.encode()).decode().rstrip("=")
        self.assertIsNone(plans.verify_ticket(f"{head}.{forged}.{sig}", now=1_100, secret="s3cret"))

    def test_garbage_is_none(self):
        for bad in (None, "", "v1", "v1.a.b", "v2.a.b", "v1.!!.??", 123, "x" * 700):
            self.assertIsNone(plans.verify_ticket(bad, now=0, secret="s3cret"), bad)
        self.assertIsNone(plans.verify_ticket("v1.a.b", now=0, secret=""))   # 키가 없으면 아무것도 믿지 않는다


class ChatPlanTests(unittest.TestCase):
    """server.py 의 /v1/chat 이 요금제를 고르는 두 줄을 그대로 따라 한다."""

    def pick(self, req):
        ticket = None if plans.PUBLIC_BETA else plans.verify_ticket(req.get("plan_ticket"))
        return plans.effective(ticket["plan"] if ticket else None), ticket

    def test_beta_ignores_tickets_and_opens_everything(self):
        with patch.object(plans, "PUBLIC_BETA", True):
            self.assertEqual(self.pick({"plan": "FREE"})[0], "BUSINESS")
            self.assertEqual(self.pick({"plan_ticket": "garbage"})[0], "BUSINESS")

    @unittest.skipUnless(SIGNER.exists(), "backend/ 가 없는 배포 이미지")
    def test_after_beta_only_the_ticket_counts(self):
        sign = load_signer().sign_ticket
        with patch.object(plans, "PUBLIC_BETA", False), \
                patch.dict("os.environ", {"FEEDIT_PLAN_SECRET": "k"}):
            self.assertEqual(self.pick({"plan": "BUSINESS"})[0], "FREE")       # 스스로 적은 plan 은 무시
            plan, ticket = self.pick({"plan_ticket": sign(5, "PRO", secret="k")})
            self.assertEqual((plan, ticket["user"]), ("PRO", "5"))

    def test_free_daily_limit_counts_per_key(self):
        server._daily.clear()
        limit = plans.QUOTA[plans.FREE]["turns"]
        for _ in range(limit):
            self.assertTrue(server.daily_ok("user:1", plans.FREE))
        self.assertFalse(server.daily_ok("user:1", plans.FREE))
        self.assertTrue(server.daily_ok("user:2", plans.FREE))    # 다른 계정은 따로 센다
        self.assertTrue(server.daily_ok("user:1", plans.PRO))     # 유료는 막지 않는다
        server._daily.clear()

    def test_django_and_chatbot_agree_on_the_free_limit(self):
        if not SIGNER.exists():
            self.skipTest("backend/ 가 없는 배포 이미지")
        self.assertEqual(load_signer().FREE_CHAT_DAILY, plans.QUOTA[plans.FREE]["turns"])


class ChatEndpointTests(unittest.TestCase):
    """실제 /v1/chat 처리 코드를 띄워 본다 — 엔진만 가짜로 바꾼다(지표 DB · 모델을 부르지 않게)."""

    @classmethod
    def setUpClass(cls):
        import threading

        class Fake:
            seen = []

            def ask(self, question, mode="general", plan="FREE", **_kw):
                Fake.seen.append(plan)
                return {"ok": True, "kind": "meta", "message": "ok"}

        cls.Fake = Fake
        cls.patch_engine = patch.object(server, "engine", lambda: Fake())
        cls.patch_token = patch.object(server, "CHAT_TOKEN", "")
        cls.patch_engine.start()
        cls.patch_token.start()
        cls.srv = server._Server(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.patch_engine.stop()
        cls.patch_token.stop()

    def setUp(self):
        server._daily.clear()
        server._hits.clear()
        self.Fake.seen.clear()

    def post(self, body):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        raw = json.dumps(body).encode()
        c.request("POST", "/v1/chat", raw, {"Content-Type": "application/json",
                                             "Content-Length": str(len(raw))})
        r = c.getresponse()
        out = (r.status, r.read().decode("utf-8", "replace"))
        c.close()
        return out

    def test_beta_is_business_like_before(self):
        with patch.object(plans, "PUBLIC_BETA", True):
            status, _ = self.post({"question": "안녕", "plan": "FREE"})
        self.assertEqual(status, 200)
        self.assertEqual(self.Fake.seen, ["BUSINESS"])

    @unittest.skipUnless(SIGNER.exists(), "backend/ 가 없는 배포 이미지")
    def test_after_beta_ticket_decides_the_plan_and_free_limit_is_per_user(self):
        sign = load_signer().sign_ticket
        with patch.object(plans, "PUBLIC_BETA", False), \
                patch.dict("os.environ", {"FEEDIT_PLAN_SECRET": "k"}):
            self.assertEqual(self.post({"question": "q", "plan": "PRO",
                                        "plan_ticket": sign(9, "PRO", secret="k")})[0], 200)
            self.assertEqual(self.post({"question": "q", "plan": "BUSINESS"})[0], 200)   # 확인증 없음
            self.assertEqual(self.Fake.seen, ["PRO", "FREE"])
            free = sign(10, "FREE", secret="k")
            limit = plans.QUOTA[plans.FREE]["turns"]
            # 분당 횟수 제한(RATE_PER_MIN)은 따로 있다 — 하루 한도만 보려고 잠시 넉넉히 연다
            with patch.object(server, "RATE_PER_MIN", 10_000):
                codes = [self.post({"question": "q", "plan_ticket": free})[0] for _ in range(limit)]
                status, text = self.post({"question": "q", "plan_ticket": free})
                other = self.post({"question": "q", "plan_ticket": sign(11, "FREE", secret="k")})[0]
            self.assertEqual(codes, [200] * limit)
            self.assertEqual(status, 429)
            self.assertEqual(json.loads(text)["reason"], "DAILY_LIMIT")
            self.assertEqual(other, 200)          # 같은 IP 의 다른 계정은 막히지 않는다


if __name__ == "__main__":
    unittest.main()
