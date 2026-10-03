"""수집 공통 재시도 — 실패하면 다시 하고, 계속 실패하면 그때 담당자에게 알린다 (COLLECT-001, 2026-09-27)."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.core import tasks
from apps.core.models import AppUser, CrawlRun, CrawlTarget, Notification, Source


class _Pipeline:
    calls = 0
    fail_times = 99       # 이만큼 실패한 뒤에는 다른 오류로 끝난다(저장 단계까지 흉내 내지 않는다)

    def __init__(self, **kw):
        pass

    def run_target(self, **kw):
        type(self).calls += 1
        if type(self).calls <= type(self).fail_times:
            raise TimeoutError("응답 없음")
        raise RuntimeError("여기까지 오면 성공 경로 — 시험에서는 저장 단계로 가지 않는다")


@override_settings(MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}})
class LiveRetryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        AppUser.objects.create(user=User.objects.create_user(username="ops", password="x", is_staff=True),
                               nickname="ADMIN")
        src = Source.objects.create(code="zigzag_rt", name="지그재그RT", source_type="COMMERCE")
        self.target = CrawlTarget.objects.create(source=src, name="랭킹", target_type="RANKING")
        _Pipeline.calls = 0

    def _run(self):
        with mock.patch.object(tasks, "get_pipeline_class", return_value=_Pipeline):
            return tasks.run_live_target.apply(args=(self.target.id,))

    def test_계속_실패하면_두_번_더_하고_마지막에만_알린다(self):
        _Pipeline.fail_times = 99
        self._run()
        runs = list(CrawlRun.objects.filter(crawl_target=self.target).order_by("id"))
        self.assertEqual(len(runs), 1 + tasks.LIVE_MAX_RETRIES)
        self.assertTrue(all(r.status == "FAILED" for r in runs))
        self.assertIn("재시도 1/2 예정", runs[0].error_message)
        self.assertIn("재시도 2/2 예정", runs[1].error_message)
        self.assertNotIn("예정", runs[2].error_message)
        self.assertEqual(Notification.objects.filter(kind="OPS_ALERT").count(), 1)

    def test_재시도가_남은_실패는_알리지_않는다(self):
        """다음 시도가 성공하면 알릴 일이 없다 — 알림은 마지막 실패에서만."""
        from apps.core.services.crawl import mark_crawl_run_failed
        run = CrawlRun.objects.create(source=self.target.source, crawl_target=self.target, run_type="LIVE")
        mark_crawl_run_failed(run, error="일시 오류 (재시도 1/2 예정)", error_code="TimeoutError", alert=False)
        run.refresh_from_db()
        self.assertEqual(run.status, "FAILED")
        self.assertFalse(Notification.objects.filter(kind="OPS_ALERT").exists())

    def test_대기_시간은_5분_뒤_15분_뒤(self):
        self.assertEqual([tasks.live_retry_countdown(i) for i in range(3)], [300, 900, 900])
