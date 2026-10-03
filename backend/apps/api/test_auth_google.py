"""일반 가입(이메일 인증)·로그인과 Google·카카오 로그인 API 테스트.

Google·카카오 토큰 서버는 부르지 않는다 — exchange_code 를 가짜로 바꿔 끼운다.
메일은 Django 테스트용 locmem 백엔드(mail.outbox)로 받는다.
실행:  python manage.py test apps.api.test_auth_google
"""

import re
import time
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase

from apps.api import google_auth, kakao_auth
from apps.core.models import AppUser

IDENTITY = {"sub": "1234567890", "email": "me@gmail.com", "name": "구글회원", "picture": ""}
KAKAO_IDENTITY = {"sub": "987654", "email": "", "name": "카카오회원", "picture": ""}


class AuthApiTests(TestCase):
    def setUp(self):
        cache.clear()   # 인증번호 재발송 간격(주소 단위)이 테스트 사이에 남지 않게
        # 마이그레이션이 미리 넣어 두는 계정이 있어, 사용자 수는 시작 값과의 차이로 본다.
        self.base = User.objects.count()
        # CSRF 까지 실제와 같게 검사한다.
        self.c = Client(enforce_csrf_checks=True)
        self.csrf = self.c.get("/api/auth/me").json()["data"]["csrf_token"]

    def post(self, path, body):
        return self.c.post(path, body, content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)

    def verify_email(self, email):
        r = self.post("/api/auth/email-code", {"email": email})
        self.assertEqual(r.status_code, 200, r.content)
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        r = self.post("/api/auth/email-verify", {"email": email, "code": code})
        self.assertEqual(r.status_code, 200, r.content)

    # ── 일반 가입·로그인 ──
    def test_signup_hashes_password_and_login_keeps_session(self):
        self.verify_email("feedit01@example.com")
        r = self.post("/api/auth/signup", {"username": "feedit01", "nickname": "피딧", "password": "Secret!234",
                                           "email": "feedit01@example.com", "gender": "FEMALE"})
        self.assertEqual(r.status_code, 201, r.content)
        user = User.objects.get(username="feedit01")
        self.assertNotEqual(user.password, "Secret!234")
        self.assertTrue(user.check_password("Secret!234"))
        self.assertTrue(AppUser.objects.filter(user=user).exists())
        self.assertEqual(user.feedit_profile.gender, "FEMALE")

        self.csrf = r.json()["data"]["csrf_token"]
        self.post("/api/auth/logout", {})
        self.assertFalse(self.c.get("/api/auth/me").json()["data"]["authenticated"])
        self.csrf = self.c.get("/api/auth/me").json()["data"]["csrf_token"]
        self.assertEqual(self.post("/api/auth/login", {"username": "feedit01", "password": "wrong"}).status_code, 401)
        r = self.post("/api/auth/login", {"username": "feedit01", "password": "Secret!234"})
        self.assertEqual(r.status_code, 200, r.content)
        me = self.c.get("/api/auth/me").json()["data"]
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["user"]["nickname"], "피딧")
        self.assertEqual(me["user"]["gender"], "FEMALE")
        changed = self.post("/api/auth/profile", {"nickname": "피딧", "gender": "MALE"})
        self.assertEqual(changed.status_code, 200, changed.content)
        user.feedit_profile.refresh_from_db()
        self.assertEqual(user.feedit_profile.gender, "MALE")
        self.assertEqual(changed.json()["data"]["user"]["gender"], "MALE")
        invalid = self.post("/api/auth/profile", {"nickname": "피딧", "gender": "UNKNOWN"})
        self.assertEqual(invalid.status_code, 400)
        user.feedit_profile.refresh_from_db()
        self.assertEqual(user.feedit_profile.gender, "MALE")

    def test_signup_requires_verified_email(self):
        body = {"username": "feedit02", "nickname": "피딧", "password": "Secret!234", "email": "a@example.com"}
        self.assertEqual(self.post("/api/auth/signup", body).status_code, 400)
        # 다른 주소를 인증해 두고 이 주소로 가입할 수는 없다
        self.verify_email("b@example.com")
        self.assertEqual(self.post("/api/auth/signup", body).status_code, 400)
        self.assertEqual(User.objects.count(), self.base + 0)

    def test_email_code_wrong_code_and_resend_gap(self):
        self.assertEqual(self.post("/api/auth/email-code", {"email": "c@example.com"}).status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("000000", mail.outbox[0].subject)
        r = self.post("/api/auth/email-verify", {"email": "c@example.com", "code": "000000"})
        code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)
        if code != "000000":
            self.assertEqual(r.status_code, 400)
        # 1분 안에 다시 보내면 막는다
        self.assertEqual(self.post("/api/auth/email-code", {"email": "c@example.com"}).status_code, 429)

    def test_email_code_rejects_registered_email(self):
        User.objects.create_user(username="old", password="x", email="used@example.com")
        self.assertEqual(self.post("/api/auth/email-code", {"email": "USED@example.com"}).status_code, 409)
        self.assertEqual(len(mail.outbox), 0)

    def test_post_without_csrf_is_rejected(self):
        r = self.c.post("/api/auth/login", {"username": "a", "password": "b"}, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    # ── Google ──
    def test_google_not_configured(self):
        with mock.patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": ""}):
            self.assertEqual(self.post("/api/auth/google", {"code": "x"}).status_code, 503)

    @mock.patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "sec"})
    def test_google_first_visit_then_signup_then_login(self):
        self.assertEqual(self.c.get("/api/auth/me").json()["data"]["google_client_id"], "cid")
        with mock.patch.object(google_auth, "exchange_code", return_value=dict(IDENTITY)):
            r = self.post("/api/auth/google", {"code": "c1"})
        data = r.json()["data"]
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(data["authenticated"])
        self.assertTrue(data["needs_signup"])
        self.assertEqual(data["google"]["email"], "me@gmail.com")
        self.assertEqual(User.objects.count(), self.base + 0, "가입 폼을 끝내기 전에는 계정을 만들지 않는다")

        r = self.post("/api/auth/google-signup", {"nickname": "구글회원", "height": 170, "weight": 60})
        self.assertEqual(r.status_code, 201, r.content)
        user = User.objects.get(email="me@gmail.com")
        self.assertFalse(user.has_usable_password(), "Google 계정은 비밀번호 로그인이 막혀 있어야 한다")
        self.assertEqual(user.feedit_profile.profile_metadata["google_sub"], "1234567890")
        self.assertEqual(user.feedit_profile.body_type, "표준")
        self.assertTrue(self.c.get("/api/auth/me").json()["data"]["authenticated"])

        # 두 번째 방문 — 가입 폼 없이 바로 로그인
        self.csrf = r.json()["data"]["csrf_token"]
        self.post("/api/auth/logout", {})
        self.csrf = self.c.get("/api/auth/me").json()["data"]["csrf_token"]
        with mock.patch.object(google_auth, "exchange_code", return_value=dict(IDENTITY)):
            r = self.post("/api/auth/google", {"code": "c2"})
        self.assertTrue(r.json()["data"]["authenticated"], r.content)
        self.assertEqual(User.objects.count(), self.base + 1)

    @mock.patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "sec"})
    def test_google_signup_requires_google_step(self):
        r = self.post("/api/auth/google-signup", {"nickname": "몰래가입"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(User.objects.count(), self.base + 0)

    @mock.patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "sec"})
    def test_same_email_password_account_is_not_hijacked(self):
        # 이메일 인증을 마친 아이디 계정이 있어도 Google 로그인과 연결되지 않는다.
        self.verify_email("me@gmail.com")
        self.post("/api/auth/signup", {"username": "attacker1", "nickname": "공격자", "password": "Secret!234", "email": "me@gmail.com"})
        self.c.logout()
        self.csrf = self.c.get("/api/auth/me").json()["data"]["csrf_token"]
        with mock.patch.object(google_auth, "exchange_code", return_value=dict(IDENTITY)):
            r = self.post("/api/auth/google", {"code": "c"})
        self.assertTrue(r.json()["data"]["needs_signup"])

    # ── 카카오 ──
    def test_kakao_not_configured(self):
        with mock.patch.dict("os.environ", {"KAKAO_REST_API_KEY": ""}):
            self.assertEqual(self.post("/api/auth/kakao-start", {"redirect_uri": "http://localhost:5173/"}).status_code, 503)

    @mock.patch.dict("os.environ", {"KAKAO_REST_API_KEY": "rest", "KAKAO_REDIRECT_URIS": ""})
    def test_kakao_state_then_signup_then_login(self):
        self.assertTrue(self.c.get("/api/auth/me").json()["data"]["kakao_enabled"])
        r = self.post("/api/auth/kakao-start", {"redirect_uri": "http://localhost:5173/"})
        url = r.json()["data"]["url"]
        state = re.search(r"state=([^&]+)", url).group(1)
        self.assertIn("client_id=rest", url)

        # state 가 다르면 코드를 바꾸지 않는다 (그리고 한 번 쓴 state 는 버린다)
        with mock.patch.object(kakao_auth, "exchange_code", return_value=dict(KAKAO_IDENTITY)) as ex:
            self.assertEqual(self.post("/api/auth/kakao", {"code": "c", "state": "other"}).status_code, 401)
            self.assertEqual(self.post("/api/auth/kakao", {"code": "c", "state": state}).status_code, 401)
            ex.assert_not_called()

        state = re.search(r"state=([^&]+)", self.post(
            "/api/auth/kakao-start", {"redirect_uri": "http://localhost:5173/"}).json()["data"]["url"]).group(1)
        with mock.patch.object(kakao_auth, "exchange_code", return_value=dict(KAKAO_IDENTITY)) as ex:
            r = self.post("/api/auth/kakao", {"code": "c1", "state": state})
            ex.assert_called_once_with("c1", "http://localhost:5173/")
        data = r.json()["data"]
        self.assertTrue(data["needs_signup"], r.content)
        self.assertEqual(data["kakao"]["name"], "카카오회원")

        r = self.post("/api/auth/kakao-signup", {"nickname": "카카오회원"})
        self.assertEqual(r.status_code, 201, r.content)
        user = User.objects.get(username="kakao_987654")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.feedit_profile.profile_metadata["kakao_sub"], "987654")

        self.csrf = r.json()["data"]["csrf_token"]
        self.post("/api/auth/logout", {})
        self.csrf = self.c.get("/api/auth/me").json()["data"]["csrf_token"]
        state = re.search(r"state=([^&]+)", self.post(
            "/api/auth/kakao-start", {"redirect_uri": "http://localhost:5173/"}).json()["data"]["url"]).group(1)
        with mock.patch.object(kakao_auth, "exchange_code", return_value=dict(KAKAO_IDENTITY)):
            r = self.post("/api/auth/kakao", {"code": "c2", "state": state})
        self.assertTrue(r.json()["data"]["authenticated"], r.content)
        self.assertEqual(User.objects.count(), self.base + 1)

    @mock.patch.dict("os.environ", {"KAKAO_REST_API_KEY": "rest", "KAKAO_REDIRECT_URIS": "https://feedit.app/"})
    def test_kakao_redirect_allowlist(self):
        self.assertEqual(self.post("/api/auth/kakao-start", {"redirect_uri": "https://evil.com/"}).status_code, 400)
        self.assertEqual(self.post("/api/auth/kakao-start", {"redirect_uri": "https://feedit.app/"}).status_code, 200)


class KakaoUserTests(TestCase):
    def test_email_only_when_verified(self):
        base = {"id": 5, "kakao_account": {"profile": {"nickname": "닉"}, "email": "k@kakao.com",
                                           "is_email_valid": True, "is_email_verified": True}}
        self.assertEqual(kakao_auth.parse_user(base)["email"], "k@kakao.com")
        base["kakao_account"]["is_email_verified"] = False
        self.assertEqual(kakao_auth.parse_user(base)["email"], "")
        self.assertEqual(kakao_auth.parse_user({"id": 6})["name"], "")


class GoogleClaimTests(TestCase):
    @mock.patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "cid"})
    def test_claims(self):
        good = {"aud": "cid", "iss": "https://accounts.google.com", "exp": time.time() + 60,
                "sub": "1", "email": "a@gmail.com", "email_verified": True}
        self.assertEqual(google_auth.verify_claims(good)["sub"], "1")
        for bad in ({"aud": "other"}, {"iss": "evil.com"}, {"exp": time.time() - 1}, {"email_verified": False}):
            with self.assertRaises(google_auth.GoogleAuthError):
                google_auth.verify_claims({**good, **bad})
