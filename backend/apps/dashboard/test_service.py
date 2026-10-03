"""서비스 운영 화면 — 홈페이지 피드백 · 살!말? 신고 처리 (ADMIN-001, 2026-09-27)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.core.models import AppUser, SiteFeedback, VoteCard, VoteComment, VoteReport


class _Base(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(username="ops", password="pw-ops-12345", is_staff=True)
        self.normal = User.objects.create_user(username="n", password="pw-n-12345", is_staff=False)
        self.author = AppUser.objects.create(user=User.objects.create_user(username="a", password="x"),
                                             nickname="글쓴이")
        self.reporter = AppUser.objects.create(user=User.objects.create_user(username="r", password="x"),
                                               nickname="신고자")
        self.reporter2 = AppUser.objects.create(user=User.objects.create_user(username="r2", password="x"),
                                                nickname="신고자2")
        self.c = Client()
        self.c.force_login(self.staff)


class FeedbackScreenTests(_Base):
    def test_기본은_확인_전만_보인다(self):
        SiteFeedback.objects.create(user=self.author, kind="BUG", content="검색이 안 돼요", page="trend")
        SiteFeedback.objects.create(user=self.author, kind="REQUEST", content="이미 처리한 글", status="DONE")
        html = self.c.get("/admin-dashboard/service/feedback/").content.decode()
        self.assertIn("검색이 안 돼요", html)
        self.assertNotIn("이미 처리한 글", html)
        self.assertIn("글쓴이", html)
        self.assertIn("남긴 화면: trend", html)

    def test_전체와_유형_필터(self):
        SiteFeedback.objects.create(user=self.author, kind="BUG", content="버그 글")
        SiteFeedback.objects.create(user=self.author, kind="REQUEST", content="요청 글", status="DONE")
        html = self.c.get("/admin-dashboard/service/feedback/?status=ALL&kind=REQUEST").content.decode()
        self.assertIn("요청 글", html)
        self.assertNotIn("버그 글", html)

    def test_처리_상태와_메모를_저장한다(self):
        fb = SiteFeedback.objects.create(user=self.author, kind="BUG", content="x")
        res = self.c.post(f"/admin-dashboard/service/feedback/{fb.id}/",
                          {"status": "DONE", "admin_note": "  9/28 배포에 반영  ", "qs": "status=OPEN"})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res["Location"].endswith("/admin-dashboard/service/feedback/?status=OPEN"))
        fb.refresh_from_db()
        self.assertEqual((fb.status, fb.admin_note), ("DONE", "9/28 배포에 반영"))

    def test_반려하면_작성자_경험치를_다시_계산한다(self):
        fb = SiteFeedback.objects.create(user=self.author, kind="REQUEST", content="스팸")
        with mock.patch("apps.api.xp_service.xp_state") as xp:
            self.c.post(f"/admin-dashboard/service/feedback/{fb.id}/", {"status": "REJECTED"})
        xp.assert_called_once()
        self.assertEqual(xp.call_args.args[0].id, self.author.id)

    def test_반려와_상관없는_변경은_경험치를_건드리지_않는다(self):
        fb = SiteFeedback.objects.create(user=self.author, kind="REQUEST", content="x")
        with mock.patch("apps.api.xp_service.xp_state") as xp:
            self.c.post(f"/admin-dashboard/service/feedback/{fb.id}/", {"status": "DONE"})
        xp.assert_not_called()

    def test_이상한_상태값은_거절(self):
        fb = SiteFeedback.objects.create(user=self.author, kind="BUG", content="x")
        self.c.post(f"/admin-dashboard/service/feedback/{fb.id}/", {"status": "HACK"})
        fb.refresh_from_db()
        self.assertEqual(fb.status, "OPEN")

    def test_GET_으로는_바꿀_수_없다(self):
        fb = SiteFeedback.objects.create(user=self.author, kind="BUG", content="x")
        self.assertEqual(self.c.get(f"/admin-dashboard/service/feedback/{fb.id}/?status=DONE").status_code, 405)

    def test_다른_호스트로_돌려보내지_않는다(self):
        fb = SiteFeedback.objects.create(user=self.author, kind="BUG", content="x")
        res = self.c.post(f"/admin-dashboard/service/feedback/{fb.id}/", {"status": "DONE", "qs": "//evil.test"})
        self.assertEqual(res["Location"], "/admin-dashboard/service/feedback/")


class ReportScreenTests(_Base):
    def setUp(self):
        super().setUp()
        self.card = VoteCard.objects.create(user=self.author, title="이 자켓 살까?", seed_key="user:1")
        self.comment = VoteComment.objects.create(card=self.card, user=self.author, content="나쁜 댓글")

    def _report(self, reporter, target="COMMENT"):
        if target == "COMMENT":
            return VoteReport.objects.create(
                reporter=reporter, target_type="COMMENT", target_id=self.comment.id, card=self.card,
                comment=self.comment, reason="욕설",
                target_snapshot={"card_title": self.card.title, "comment_content": self.comment.content})
        return VoteReport.objects.create(reporter=reporter, target_type="CARD", target_id=self.card.id,
                                         card=self.card, reason="광고", target_snapshot={"title": self.card.title})

    def test_신고_목록에_대상과_사유가_보인다(self):
        self._report(self.reporter); self._report(self.reporter2)
        html = self.c.get("/admin-dashboard/service/reports/").content.decode()
        self.assertIn("나쁜 댓글", html)
        self.assertIn("사유: 욕설", html)
        self.assertIn("같은 대상 신고 2건", html)
        self.assertIn("검토 완료와 함께 댓글 숨기기", html)

    def test_같은_대상_신고는_한_번에_처리된다(self):
        r1 = self._report(self.reporter); r2 = self._report(self.reporter2)
        card_report = self._report(self.reporter, target="CARD")
        self.c.post(f"/admin-dashboard/service/reports/{r1.id}/", {"status": "DISMISSED"})
        r2.refresh_from_db(); card_report.refresh_from_db()
        self.assertEqual(r2.status, "DISMISSED")
        self.assertEqual(card_report.status, "PENDING")   # 다른 대상은 그대로

    def test_댓글_숨기기는_앱_삭제와_같다(self):
        r = self._report(self.reporter)
        self.c.post(f"/admin-dashboard/service/reports/{r.id}/", {"status": "REVIEWED", "hide_comment": "1"})
        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_deleted)
        html = self.c.get("/admin-dashboard/service/reports/?status=ALL").content.decode()
        self.assertIn("숨긴 댓글", html)

    def test_숨기기를_고르지_않으면_댓글은_그대로(self):
        r = self._report(self.reporter)
        self.c.post(f"/admin-dashboard/service/reports/{r.id}/", {"status": "REVIEWED"})
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.is_deleted)

    def test_카드_신고로는_댓글을_숨기지_않는다(self):
        r = self._report(self.reporter, target="CARD")
        self.c.post(f"/admin-dashboard/service/reports/{r.id}/", {"status": "REVIEWED", "hide_comment": "1"})
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.is_deleted)

    def test_탈퇴한_신고자도_목록이_깨지지_않는다(self):
        VoteReport.objects.create(reporter=None, target_type="CARD", target_id=self.card.id, card=self.card)
        html = self.c.get("/admin-dashboard/service/reports/").content.decode()
        self.assertIn("(탈퇴한 사용자)", html)


class AccessTests(_Base):
    def test_일반_회원은_못_연다(self):
        c = Client(); c.force_login(self.normal)
        for path in ("/admin-dashboard/service/feedback/", "/admin-dashboard/service/reports/"):
            with self.subTest(path=path):
                self.assertEqual(c.get(path).status_code, 403)

    def test_일반_회원은_처리도_못_한다(self):
        fb = SiteFeedback.objects.create(user=self.author, kind="BUG", content="x")
        c = Client(); c.force_login(self.normal)
        c.post(f"/admin-dashboard/service/feedback/{fb.id}/", {"status": "REJECTED"})
        fb.refresh_from_db()
        self.assertEqual(fb.status, "OPEN")
