"""운영 화면 '지표 다시 계산' (ADMIN-001, 2026-09-27)."""
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from apps.core.models import (
    DictionaryTerm,
    Source,
    TermAssocDaily,
    TermMetricDaily,
)


class RebuildMetricsTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.staff = User.objects.create_user(username="ops", password="x", is_staff=True)
        self.normal = User.objects.create_user(username="n", password="x")
        self.c = Client()
        self.c.force_login(self.staff)

    def test_버튼이_보인다(self):
        html = self.c.get("/admin-dashboard/trend/metrics/").content.decode()
        self.assertIn("지표 다시 계산", html)
        self.assertIn('value="365"', html)

    def test_누르면_셀러리에_맡긴다(self):
        with mock.patch("apps.core.tasks.rebuild_metrics.delay") as delay:
            delay.return_value.id = "abcdef123456"
            res = self.c.post("/admin-dashboard/trend/metrics/rebuild/", {"days": "90"}, follow=True)
        delay.assert_called_once_with(90)
        self.assertIn("최근 90일 지표 다시 계산을 요청했습니다", res.content.decode())

    def test_연타는_한_번만(self):
        with mock.patch("apps.core.tasks.rebuild_metrics.delay") as delay:
            delay.return_value.id = "x"
            self.c.post("/admin-dashboard/trend/metrics/rebuild/", {"days": "35"})
            res = self.c.post("/admin-dashboard/trend/metrics/rebuild/", {"days": "35"}, follow=True)
        self.assertEqual(delay.call_count, 1)
        self.assertIn("아직 돌고 있습니다", res.content.decode())

    def test_정해진_기간만(self):
        with mock.patch("apps.core.tasks.rebuild_metrics.delay") as delay:
            res = self.c.post("/admin-dashboard/trend/metrics/rebuild/", {"days": "9999"}, follow=True)
        delay.assert_not_called()
        self.assertIn("기간이 올바르지 않습니다", res.content.decode())

    def test_브로커가_죽어도_화면은_산다(self):
        with mock.patch("apps.core.tasks.rebuild_metrics.delay", side_effect=ConnectionError("redis")):
            res = self.c.post("/admin-dashboard/trend/metrics/rebuild/", {"days": "35"}, follow=True)
        self.assertIn("작업을 보내지 못했습니다", res.content.decode())
        self.assertTrue(cache.add("dashboard:rebuild-metrics", 1, 5), "실패하면 잠금을 풀어야 다시 누를 수 있다")

    def test_GET_은_아무것도_안_한다(self):
        with mock.patch("apps.core.tasks.rebuild_metrics.delay") as delay:
            self.c.get("/admin-dashboard/trend/metrics/rebuild/")
        delay.assert_not_called()

    def test_일반_회원은_못_누른다(self):
        c = Client(); c.force_login(self.normal)
        with mock.patch("apps.core.tasks.rebuild_metrics.delay") as delay:
            c.post("/admin-dashboard/trend/metrics/rebuild/", {"days": "35"})
        delay.assert_not_called()

    def test_작업은_기간을_넘겨_계산한다(self):
        from apps.core.tasks import rebuild_metrics
        with mock.patch("analysis.text_signals.metrics.rebuild_text_metrics", return_value={"rows": 3}) as fn:
            got = rebuild_metrics(90)
        kwargs = fn.call_args.kwargs
        self.assertEqual((kwargs["until"] - kwargs["since"]).days, 90)
        self.assertEqual(got["days"], 90)


class TrendMetricsSchemaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="metrics-ops",
            password="x",
            is_staff=True,
        )
        self.client.force_login(self.staff)
        self.source_term = DictionaryTerm.objects.create(
            term_code="STYLE_DENIM",
            term_type=DictionaryTerm.TermType.STYLE,
            canonical_name="데님",
        )
        self.target_term = DictionaryTerm.objects.create(
            term_code="ITEM_JEANS",
            term_type=DictionaryTerm.TermType.ITEM,
            canonical_name="청바지",
        )
        TermMetricDaily.objects.create(
            term=self.source_term,
            metric_date=date(2026, 9, 28),
            mention_count=131,
            document_count=42,
            content_count=37,
            momentum=Decimal("0.2810"),
            trend_temperature=Decimal("64.2500"),
        )
        source = Source.objects.create(
            code="TEST_CONTENT",
            name="테스트 콘텐츠",
            source_type=Source.SourceType.CONTENT,
        )
        TermMetricDaily.objects.create(
            term=self.source_term,
            source=source,
            metric_date=date(2026, 9, 28),
            mention_count=999,
            document_count=999,
            content_count=999,
            momentum=Decimal("0.9990"),
            trend_temperature=Decimal("99.0000"),
        )
        TermAssocDaily.objects.create(
            source_term=self.source_term,
            target_term=self.target_term,
            metric_date=date(2026, 9, 28),
            cooccurrence_count=23,
            pmi=Decimal("2.125000"),
            lift=Decimal("4.500000"),
        )

    def test_트렌드_지표는_현재_스키마로_표시된다(self):
        response = self.client.get("/admin-dashboard/trend/metrics/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "트렌드 온도 상위")
        self.assertContains(response, "64.25")
        self.assertContains(response, "2.125")
        self.assertContains(response, "4.500")
        self.assertEqual(len(response.context["top_trend"]), 1)

    def test_용어별_지표는_현재_스키마로_표시된다(self):
        response = self.client.get("/admin-dashboard/analytics/term-metrics/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "콘텐츠 수")
        self.assertContains(response, "모멘텀")
        self.assertContains(response, "트렌드 온도")
        self.assertContains(response, "37")
        self.assertContains(response, "0.28")
        self.assertContains(response, "64.25")
        denim = next(
            row for row in response.context["rows"]
            if row.id == self.source_term.id
        )
        self.assertEqual(denim.content_count, 37)
