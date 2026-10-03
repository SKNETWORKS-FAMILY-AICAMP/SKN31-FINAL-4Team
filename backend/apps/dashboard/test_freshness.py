"""장기 미갱신 경고 (DATA_STATUS-003, 2026-09-27).

기대 주기의 2배가 지나도록 정상 수집이 없으면 '지연', 활성 타깃이 있는데 성공 기록이
하나도 없으면 '기록 없음', 활성 타깃이 없으면 경고하지 않는다('수집 안 함').
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.core.models import CrawlRun, CrawlTarget, Source
from apps.dashboard.services.dashboard_service import source_freshness, stale_alerts


def _source(code, **kw):
    return Source.objects.create(code=code, name=code, source_type="COMMERCE", **kw)


def _target(source, minutes=1440, active=True, mode="LIVE"):
    return CrawlTarget.objects.create(source=source, name=f"{source.code} 타깃", target_type="RANKING",
                                      collection_mode=mode, interval_minutes=minutes, is_active=active)


def _run(source, status, hours_ago, finished=True):
    at = timezone.now() - timedelta(hours=hours_ago)
    return CrawlRun.objects.create(source=source, run_type="LIVE", status=status,
                                   started_at=at, finished_at=at if finished else None)


class FreshnessTests(TestCase):
    def test_주기_2배_안이면_정상(self):
        s = _source("t_ok"); _target(s, minutes=1440)
        _run(s, "SUCCESS", hours_ago=30)
        self.assertEqual(source_freshness()[s.id]["state"], "ok")

    def test_주기_2배를_넘기면_지연(self):
        s = _source("t_late"); _target(s, minutes=1440)
        _run(s, "SUCCESS", hours_ago=50)
        f = source_freshness()[s.id]
        self.assertEqual(f["state"], "late")
        self.assertEqual(f["limit_hours"], 48.0)

    def test_실패_실행은_정상_수집으로_치지_않는다(self):
        s = _source("t_fail"); _target(s, minutes=60)
        _run(s, "SUCCESS", hours_ago=10)
        _run(s, "FAILED", hours_ago=0.1)
        self.assertEqual(source_freshness()[s.id]["state"], "late")

    def test_일부_성공도_수집으로_친다(self):
        s = _source("t_part"); _target(s, minutes=60)
        _run(s, "PARTIAL_SUCCESS", hours_ago=1)
        self.assertEqual(source_freshness()[s.id]["state"], "ok")

    def test_가장_짧은_활성_LIVE_주기를_기준으로(self):
        s = _source("t_short"); _target(s, minutes=1440); _target(s, minutes=120)
        _target(s, minutes=10, active=False)          # 꺼 둔 타깃은 빼고
        _target(s, minutes=15, mode="BACKFILL")       # 백필도 기준이 아니다
        _run(s, "SUCCESS", hours_ago=5)
        f = source_freshness()[s.id]
        self.assertEqual(f["interval_minutes"], 120)
        self.assertEqual(f["state"], "late")

    def test_끝난_시각이_없으면_시작_시각으로(self):
        s = _source("t_nofin"); _target(s, minutes=1440)
        _run(s, "SUCCESS", hours_ago=3, finished=False)
        self.assertEqual(source_freshness()[s.id]["state"], "ok")

    def test_성공_기록이_없으면_기록_없음(self):
        s = _source("t_never"); _target(s)
        _run(s, "FAILED", hours_ago=1)
        self.assertEqual(source_freshness()[s.id]["state"], "never")

    def test_활성_타깃이_없으면_경고하지_않는다(self):
        s = _source("t_idle"); _target(s, active=False)
        _run(s, "SUCCESS", hours_ago=500)
        self.assertEqual(source_freshness()[s.id]["state"], "idle")
        titles = [a["title"] for a in stale_alerts()]
        self.assertFalse(any("t_idle" in a["detail"] for a in stale_alerts()), titles)

    def test_대시보드_경고에_이름과_경과시간이_나온다(self):
        s = _source("t_alert"); _target(s, minutes=60)
        _run(s, "SUCCESS", hours_ago=5)
        alerts = stale_alerts()
        late = [a for a in alerts if a["title"].startswith("장기 미갱신")]
        self.assertEqual(len(late), 1)
        self.assertIn("t_alert", late[0]["detail"])
        self.assertIn("기준 2시간", late[0]["detail"])


class FreshnessScreenTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_user(username="ops", password="pw-ops-12345", is_staff=True)
        self.c = Client()
        self.c.force_login(staff)

    def test_플랫폼_현황에_신선도가_뜬다(self):
        s = _source("t_screen"); _target(s, minutes=60)
        _run(s, "SUCCESS", hours_ago=5)
        res = self.c.get("/admin-dashboard/collection/platform-status/")
        self.assertEqual(res.status_code, 200)
        html = res.content.decode()
        self.assertIn("마지막 정상 수집", html)
        self.assertIn("장기 미갱신", html)
        self.assertIn('class="ps-fresh late"', html)

    def test_메인_대시보드에도_경고가_뜬다(self):
        s = _source("t_main"); _target(s, minutes=60)
        _run(s, "SUCCESS", hours_ago=5)
        res = self.c.get("/admin-dashboard/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("장기 미갱신", res.content.decode())
