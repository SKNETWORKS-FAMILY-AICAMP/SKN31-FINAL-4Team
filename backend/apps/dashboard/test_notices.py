"""알림 보내기 · 실시간 공지 · 성별 요청 알림 (2026-10-02).

돌리는 법:  cd backend && python manage.py test apps.dashboard.test_notices
"""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from apps.api import notification_service as service
from apps.core.models import Announcement, AppUser, Notification, NotificationSetting


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.staff = User.objects.create_user(username="ops", password="pw-ops-12345", is_staff=True)
        self.u1 = AppUser.objects.create(user=User.objects.create_user(username="a", password="pw-a-12345"),
                                         nickname="진", gender="MALE")
        self.u2 = AppUser.objects.create(user=User.objects.create_user(username="b", password="pw-b-12345"),
                                         nickname="민지", gender=None)
        self.u3 = AppUser.objects.create(user=User.objects.create_user(username="c", password="pw-c-12345"),
                                         nickname="끈사람", gender="")
        NotificationSetting.objects.create(user=self.u3, enabled=False)
        gone = User.objects.create_user(username="d", password="x", is_active=False)
        self.gone = AppUser.objects.create(user=gone, nickname="탈퇴")
        self.ops = Client()
        self.ops.force_login(self.staff)


class SendNoticeTests(_Base):
    URL = "/admin-dashboard/service/notices/send/"

    def test_화면이_뜨고_대상_수를_보여준다(self):
        html = self.ops.get("/admin-dashboard/service/notices/").content.decode()
        self.assertIn("알림 보내기", html)
        self.assertIn("실시간 공지", html)
        self.assertIn("성별 미입력", html)

    def test_고른_회원에게만_보내고_못_찾은_이름을_알린다(self):
        res = self.ops.post(self.URL, {"title": " 점검  안내 ", "body": "02:00~02:30\r\n챗봇 잠시 멈춤",
                                       "link": "trend", "target": "pick", "recipients": "진, 없는사람"},
                            follow=True)
        rows = list(Notification.objects.filter(kind="ADMIN_NOTICE"))
        self.assertEqual([r.user_id for r in rows], [self.u1.id])
        self.assertEqual((rows[0].title, rows[0].body, rows[0].link),
                         ("점검 안내", "02:00~02:30\n챗봇 잠시 멈춤", "trend"))
        html = res.content.decode()
        self.assertIn("1명에게 보냈습니다", html)
        self.assertIn("없는사람", html)

    def test_전체는_확인_칸이_있어야_하고_끈_사람과_탈퇴자는_빠진다(self):
        self.ops.post(self.URL, {"title": "t", "target": "all"})
        self.assertFalse(Notification.objects.filter(kind="ADMIN_NOTICE").exists())
        self.ops.post(self.URL, {"title": "t", "target": "all", "confirm_all": "1"})
        got = set(Notification.objects.filter(kind="ADMIN_NOTICE").values_list("user_id", flat=True))
        self.assertEqual(got, {self.u1.id, self.u2.id})        # u3 는 알림 전체 끔, gone 은 비활성

    def test_성별_미입력_대상(self):
        self.ops.post(self.URL, {"title": "성별을 알려 주세요", "target": "no_gender"})
        got = set(Notification.objects.filter(kind="ADMIN_NOTICE").values_list("user_id", flat=True))
        self.assertEqual(got, {self.u2.id})                     # u3 도 미입력이지만 알림을 껐다

    def test_없는_화면으로는_보내지_않는다(self):
        self.ops.post(self.URL, {"title": "t", "target": "pick", "recipients": "진", "link": "admin"})
        self.assertFalse(Notification.objects.filter(kind="ADMIN_NOTICE").exists())

    def test_운영자가_아니면_못_쓴다(self):
        c = Client()
        c.force_login(self.u1.user)
        c.post(self.URL, {"title": "t", "target": "pick", "recipients": "진"})
        self.assertFalse(Notification.objects.filter(kind="ADMIN_NOTICE").exists())


class TickerTests(_Base):
    def test_올리면_공개_API에_뜨고_내리면_사라진다(self):
        self.ops.post("/admin-dashboard/service/notices/ticker/",
                      {"message": "  가을 리포트\n오픈  ", "link": "trend", "hours": "24"})
        a = Announcement.objects.get()
        self.assertEqual(a.message, "가을 리포트 오픈")
        self.assertIsNotNone(a.ends_at)
        anon = Client()
        got = anon.get("/api/auth/announcements").json()["data"]["items"]
        self.assertEqual([x["message"] for x in got], ["가을 리포트 오픈"])
        self.ops.post(f"/admin-dashboard/service/notices/ticker/{a.id}/end/")
        got = anon.get("/api/auth/announcements").json()["data"]["items"]
        self.assertEqual(got, [])

    def test_게시_시간이_지난_공지는_보이지_않는다(self):
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        Announcement.objects.create(message="지난 것", starts_at=now - timedelta(days=2),
                                    ends_at=now - timedelta(days=1))
        Announcement.objects.create(message="내릴 때까지", starts_at=now - timedelta(minutes=1))
        got = service.live_announcements(use_cache=False)
        self.assertEqual([x["message"] for x in got], ["내릴 때까지"])


class GenderPromptTests(_Base):
    def _login(self, profile):
        c = Client()
        c.force_login(profile.user)
        return c

    def test_성별이_비면_알림이_한_번_생기고_고르면_사라진다(self):
        c = self._login(self.u2)
        items = c.get("/api/auth/notifications").json()["data"]["items"]
        self.assertEqual([i["kind"] for i in items], ["PROFILE_GENDER"])
        self.assertEqual(items[0]["payload"], {"action": "gender"})
        cache.clear()
        c.get("/api/auth/notifications")
        self.assertEqual(Notification.objects.filter(user=self.u2, kind="PROFILE_GENDER").count(), 1)

        me = c.get("/api/auth/me").json()
        res = c.post("/api/auth/gender", data=json.dumps({"gender": "FEMALE"}),
                     content_type="application/json", HTTP_X_CSRFTOKEN=me["data"].get("csrf_token", ""))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["data"]["user"]["gender"], "FEMALE")
        self.u2.refresh_from_db()
        self.assertEqual(self.u2.gender, "FEMALE")
        cache.clear()
        data = c.get("/api/auth/notifications").json()["data"]
        self.assertEqual(data["items"], [])
        self.assertEqual(data["unread"], 0)

    def test_성별이_있으면_묻지_않는다(self):
        c = self._login(self.u1)
        c.get("/api/auth/notifications")
        self.assertFalse(Notification.objects.filter(user=self.u1, kind="PROFILE_GENDER").exists())

    def test_잘못된_값과_비로그인은_막는다(self):
        c = self._login(self.u2)
        res = c.post("/api/auth/gender", data=json.dumps({"gender": "X"}), content_type="application/json")
        self.assertEqual(res.status_code, 400)
        res = c.post("/api/auth/gender", data=json.dumps({}), content_type="application/json")
        self.assertEqual(res.status_code, 400)
        res = Client().post("/api/auth/gender", data=json.dumps({"gender": "MALE"}),
                            content_type="application/json")
        self.assertEqual(res.status_code, 401)
