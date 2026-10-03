"""탈퇴 — 다른 사람의 신고 기록에 남은 내 글 사본까지 지운다 (PRIVACY-001, 2026-09-27)."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.core.models import AppUser, VoteCard, VoteComment, VoteReport


class WithdrawScrubsReportSnapshotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.author_user = User.objects.create_user(username="author", password="pw-author-123")
        self.author = AppUser.objects.create(user=self.author_user, nickname="글쓴이")
        self.reporter = AppUser.objects.create(user=User.objects.create_user(username="rep", password="x"),
                                               nickname="신고자")
        card = VoteCard.objects.create(user=self.author, title="내 자켓", seed_key="user:1")
        comment = VoteComment.objects.create(card=card, user=self.author, content="내 댓글 원문")
        self.comment_report = VoteReport.objects.create(
            reporter=self.reporter, target_type="COMMENT", target_id=comment.id, card=card, comment=comment,
            reason="욕설", target_snapshot={"card_id": card.id, "card_title": card.title,
                                           "comment_id": comment.id, "comment_author_id": self.author.id,
                                           "comment_content": comment.content})
        self.card_report = VoteReport.objects.create(
            reporter=self.reporter, target_type="CARD", target_id=card.id, card=card, reason="광고",
            target_snapshot={"card_id": card.id, "title": card.title, "author_id": self.author.id})
        other = VoteCard.objects.create(user=self.reporter, title="남의 카드", seed_key="user:2")
        self.other_report = VoteReport.objects.create(
            reporter=self.author, target_type="CARD", target_id=other.id, card=other,
            target_snapshot={"card_id": other.id, "title": other.title, "author_id": self.reporter.id})

    def _withdraw(self):
        c = Client()
        c.force_login(self.author_user)
        res = c.post("/api/auth/withdraw", content_type="application/json", data="{}")
        self.assertEqual(res.status_code, 200, res.content)

    def test_내_글_사본은_지워지고_신고_행은_남는다(self):
        self._withdraw()
        for r in (self.comment_report, self.card_report):
            r.refresh_from_db()
            self.assertEqual(r.target_snapshot, {"withdrawn": True})
            self.assertEqual(r.reason in ("욕설", "광고"), True)   # 신고자의 기록은 그대로

    def test_남의_글_사본은_건드리지_않는다(self):
        self._withdraw()
        self.other_report.refresh_from_db()
        self.assertEqual(self.other_report.target_snapshot["title"], "남의 카드")
        self.assertIsNone(self.other_report.reporter_id)          # 내가 한 신고는 신고자만 비운다

    def test_계정과_딸린_기록은_지워진다(self):
        self._withdraw()
        self.assertFalse(AppUser.objects.filter(id=self.author.id).exists())
        self.assertFalse(VoteComment.objects.filter(user_id=self.author.id).exists())
