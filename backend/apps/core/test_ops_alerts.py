"""운영 알림 — 수집 실패 · 장기 미갱신 (COLLECT-001 · OPERATIONS-002, 2026-09-27)."""

import os
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import AppUser, CrawlRun, CrawlTarget, Notification, Source
from apps.core.services import ops_alerts
from apps.core.services.crawl import mark_crawl_run_failed

SMTP = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
CONSOLE = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}


class _Base(TestCase):
    def setUp(self):
        User = get_user_model()
        ops = User.objects.create_user(username="ops", password="x", is_staff=True, email="ops@feedit.test")
        self.ops = AppUser.objects.create(user=ops, nickname="ADMIN")
        normal = User.objects.create_user(username="n", password="x", email="n@feedit.test")
        self.normal = AppUser.objects.create(user=normal, nickname="회원")
        self.source = Source.objects.create(code="musinsa_t", name="무신사T", source_type="COMMERCE")
        self.target = CrawlTarget.objects.create(source=self.source, name="남성 상의 DAILY",
                                                 target_type="RANKING", interval_minutes=60)

    def _run(self, **kw):
        return CrawlRun.objects.create(source=self.source, crawl_target=self.target, run_type="LIVE",
                                       started_at=timezone.now(), **kw)


@override_settings(MAILERS=SMTP)
class CrawlFailedTests(_Base):
    def test_실패하면_운영_계정에만_알리고_메일도_보낸다(self):
        run = self._run()
        mark_crawl_run_failed(run, error="HTTP 403 blocked", error_code="HTTPError")
        rows = Notification.objects.filter(kind="OPS_ALERT")
        self.assertEqual([n.user_id for n in rows], [self.ops.id])
        n = rows.first()
        self.assertIn("수집 실패", n.title)
        self.assertIn("남성 상의 DAILY", n.body)
        self.assertIn("HTTPError", n.body)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ops@feedit.test"])
        self.assertIn("[FEEDiT 운영]", mail.outbox[0].subject)

    def test_같은_날_같은_소스는_한_번만(self):
        mark_crawl_run_failed(self._run(), error="a", error_code="E")
        mark_crawl_run_failed(self._run(), error="b", error_code="E")
        self.assertEqual(Notification.objects.filter(kind="OPS_ALERT").count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_다른_소스는_따로_알린다(self):
        mark_crawl_run_failed(self._run(), error="a")
        other = Source.objects.create(code="zigzag_t", name="지그재그T", source_type="COMMERCE")
        mark_crawl_run_failed(CrawlRun.objects.create(source=other, run_type="LIVE"), error="b")
        self.assertEqual(Notification.objects.filter(kind="OPS_ALERT").count(), 2)

    def test_OPS_ALERT_EMAILS_가_있으면_그쪽으로(self):
        with mock.patch.dict(os.environ, {"OPS_ALERT_EMAILS": "a@x.test, b@x.test"}):
            mark_crawl_run_failed(self._run(), error="a")
        self.assertEqual(mail.outbox[0].to, ["a@x.test", "b@x.test"])

    def test_알림이_실패해도_수집_실패_기록은_남는다(self):
        run = self._run()
        with mock.patch("apps.core.services.ops_alerts._staff_profiles", side_effect=RuntimeError("db down")):
            mark_crawl_run_failed(run, error="a")      # 예외가 새지 않아야 한다
        run.refresh_from_db()
        self.assertEqual(run.status, "FAILED")

    def test_슈퍼유저_ADMIN_도_받는다(self):
        """앱의 ADMIN 판정은 is_staff 또는 is_superuser 다 — 슈퍼유저만 켠 계정도 받아야 한다."""
        User = get_user_model()
        su = User.objects.create_user(username="root", password="x", email="root@feedit.test")
        User.objects.filter(pk=su.pk).update(is_superuser=True)
        admin = AppUser.objects.create(user=su, nickname="FEEDITADMIN")
        mark_crawl_run_failed(self._run(), error="a")
        self.assertTrue(Notification.objects.filter(user=admin, kind="OPS_ALERT").exists())
        self.assertIn("root@feedit.test", mail.outbox[0].to)

    def test_운영_계정이_알림을_꺼도_끌_수_없다(self):
        from apps.core.models import NotificationSetting
        NotificationSetting.objects.create(user=self.ops, enabled=False)
        mark_crawl_run_failed(self._run(), error="a")
        self.assertEqual(Notification.objects.filter(user=self.ops, kind="OPS_ALERT").count(), 1)


@override_settings(MAILERS=CONSOLE)
class NoMailTests(_Base):
    def test_메일이_설정되지_않았으면_서비스_알림만(self):
        mark_crawl_run_failed(self._run(), error="a")
        self.assertEqual(Notification.objects.filter(kind="OPS_ALERT").count(), 1)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(MAILERS=SMTP)
class FreshnessAlertTests(_Base):
    def test_지연이_있으면_하루_한_번_알린다(self):
        run = self._run(status="SUCCESS")
        CrawlRun.objects.filter(id=run.id).update(started_at=timezone.now() - timedelta(hours=6),
                                                    finished_at=timezone.now() - timedelta(hours=5))
        first = ops_alerts.check_freshness_and_alert()
        again = ops_alerts.check_freshness_and_alert()
        self.assertEqual((first["stale"], first["notified"], first["mailed"]), (1, 1, 1))
        self.assertEqual((again["notified"], again["mailed"]), (0, 0))
        n = Notification.objects.get(kind="OPS_ALERT")
        self.assertIn("장기 미갱신", n.title)
        self.assertIn("무신사T", n.body)

    def test_모두_정상이면_아무것도_보내지_않는다(self):
        self._run(status="SUCCESS", finished_at=timezone.now() + timedelta(seconds=1))
        got = ops_alerts.check_freshness_and_alert()
        self.assertEqual(got, {"stale": 0, "notified": 0, "mailed": 0})
        self.assertFalse(Notification.objects.exists())

    def test_셀러리_작업으로도_돈다(self):
        from apps.core.tasks import check_data_freshness
        run = self._run(status="SUCCESS")
        CrawlRun.objects.filter(id=run.id).update(started_at=timezone.now() - timedelta(hours=6),
                                                    finished_at=timezone.now() - timedelta(hours=5))
        self.assertEqual(check_data_freshness()["stale"], 1)

    def test_비트_스케줄에_두_곳_모두_있다(self):
        from django.conf import settings
        from config.celery import app
        self.assertIn("check-data-freshness", settings.CELERY_BEAT_SCHEDULE)
        self.assertIn("check-data-freshness", app.conf.beat_schedule)
