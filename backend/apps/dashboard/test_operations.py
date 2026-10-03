from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.core.models import AppUser, UserEvent, VoteCard, VoteComment
from apps.dashboard.operations_views import validate_readonly_sql


class OperationsDashboardTests(TestCase):
    def setUp(self):
        cache.clear()
        auth_user = get_user_model().objects.create_user(
            username="ops-admin", password="x", is_staff=True,
            email="private-admin@example.test",
        )
        self.client.force_login(auth_user)
        self.profile = AppUser.objects.create(user=auth_user, nickname="운영 테스트")

    def test_개인정보_없는_사용자_현황을_표시한다(self):
        UserEvent.objects.create(user=self.profile, event_type=UserEvent.EventType.VIEW)

        response = self.client.get("/admin-dashboard/service/users/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "운영 테스트")
        self.assertContains(response, "USER-")
        self.assertNotContains(response, "private-admin@example.test")

    def test_사용자_목록은_n_plus_one_없이_조회한다(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/admin-dashboard/service/users/")

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 8)

    def test_살말_게시글과_댓글을_조회한다(self):
        card = VoteCard.objects.create(user=self.profile, title="이 재킷 살까요?")
        VoteComment.objects.create(
            card=card, user=self.profile, choice="BUY", content="활용도가 좋아 보여요"
        )

        cards = self.client.get("/admin-dashboard/service/votes/")
        comments = self.client.get("/admin-dashboard/service/comments/")

        self.assertContains(cards, "이 재킷 살까요?")
        self.assertContains(comments, "활용도가 좋아 보여요")

    def test_파이프라인과_erd를_조회한다(self):
        pipeline = self.client.get("/admin-dashboard/normalization/pipeline/")
        database = self.client.get("/admin-dashboard/database/")

        self.assertEqual(pipeline.status_code, 200)
        self.assertContains(pipeline, "데이터가 흐르는 상태")
        self.assertEqual(database.status_code, 200)
        self.assertContains(database, "text_document")
        self.assertContains(database, "외래키 관계")

    def test_sql_검증은_읽기만_허용하고_민감_테이블을_막는다(self):
        self.assertEqual(validate_readonly_sql("SELECT 1"), "")
        self.assertEqual(validate_readonly_sql("WITH n AS (SELECT 1) SELECT * FROM n"), "")
        self.assertIn("SELECT", validate_readonly_sql("DELETE FROM app.vote_card"))
        self.assertIn("개인정보", validate_readonly_sql("SELECT * FROM app.app_user"))
        self.assertIn("하나", validate_readonly_sql("SELECT 1; SELECT 2"))
        self.assertIn("함수", validate_readonly_sql("SELECT pg_terminate_backend(123)"))

    @override_settings(DEBUG=True)
    def test_sql_콘솔은_결과를_출력한다(self):
        response = self.client.post("/admin-dashboard/database/query/", {"sql": "SELECT 42 AS answer"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "answer")
        self.assertContains(response, "42")
