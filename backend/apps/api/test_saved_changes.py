"""찜 상품 변동 알림 — 급락 · 6개월 최저가 · 급등 · 품절 (FAVORITE-002, 2026-09-27)."""
import unittest
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.api import notification_service as svc
from apps.api.notifications import (
    PRICE_RISE_MIN_RATE, price_drops, price_rises, saved_change_digest,
)
from apps.core.models import (
    AppUser, Notification, ProductSource, ProductSourceSnapshot, Source, UserSavedItem,
)


def item(name, base, current):
    return {"item_id": name, "name": name, "base": base, "current": current}


class RuleTests(unittest.TestCase):
    def test_급등은_10퍼센트부터(self):
        self.assertEqual(price_rises([item("A", 100, 109)]), [])
        self.assertEqual(price_rises([item("A", 100, 100 * (1 + PRICE_RISE_MIN_RATE))])[0]["percent"], 10)

    def test_내린_것만_있으면_예전_문구(self):
        title, _ = saved_change_digest(price_drops([item("로퍼", 100000, 80000)]))
        self.assertEqual(title, "찜한 로퍼가 20% 내려갔어요.")

    def test_품절_한_건(self):
        title, _ = saved_change_digest([], [], [{"item_id": "x", "name": "자켓"}])
        self.assertEqual(title, "찜한 자켓이 품절됐어요.")

    def test_급등_한_건(self):
        title, _ = saved_change_digest([], price_rises([item("셔츠", 100, 125)]))
        self.assertEqual(title, "찜한 셔츠가 25% 올랐어요.")

    def test_최저가_한_건(self):
        drops = price_drops([item("로퍼", 100, 80)])
        title, _ = saved_change_digest(drops, lows={"로퍼"})
        self.assertEqual(title, "찜한 로퍼가 6개월 최저가예요 (20% 내림).")

    def test_여러_변동은_한_건으로_묶는다(self):
        title, body = saved_change_digest(price_drops([item("A", 100, 80)]),
                                          price_rises([item("B", 100, 130)]),
                                          [{"item_id": "C", "name": "C"}], lows={"A"})
        self.assertEqual(title, "찜한 상품 3개에 변동이 있어요.")
        self.assertEqual(body.split("\n"), ["A 20% ↓ · 6개월 최저가", "B 30% ↑", "C 품절"])

    def test_아무_변동이_없으면_없다(self):
        self.assertEqual(saved_change_digest([], [], []), (None, None))


class ServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.me = AppUser.objects.create(user=User.objects.create_user(username="me", password="x"), nickname="나")
        self.src = Source.objects.create(code="ably_t", name="에이블리T", source_type="COMMERCE")
        self.now = timezone.now()

    def _saved(self, name, saved_price, snaps):
        """snaps: [(며칠 전, 가격, 재고 상태)] — 오래된 것부터."""
        ps = ProductSource.objects.create(source=self.src, source_product_id=name, source_name=name)
        for days, price, stock in snaps:
            ProductSourceSnapshot.objects.create(product_source=ps, observed_at=self.now - timedelta(days=days),
                                                 sale_price=Decimal(price), stock_status=stock)
        return UserSavedItem.objects.create(user=self.me, saved_price=Decimal(saved_price), saved_price_source=ps)

    def _run(self):
        return svc.price_drop_digest(self.me, now=self.now)

    def test_급등을_알리고_기준가를_옮긴다(self):
        it = self._saved("셔츠", 100000, [(1, 100000, "AVAILABLE"), (0, 130000, "AVAILABLE")])
        row = self._run()
        self.assertEqual(row.title, "찜한 셔츠가 30% 올랐어요.")
        it.refresh_from_db()
        self.assertEqual(it.notified_price, Decimal("130000"))
        self.assertEqual(row.payload["items"][0]["change"], "rise")

    def test_새로_품절되면_알린다(self):
        self._saved("자켓", 50000, [(1, 50000, "AVAILABLE"), (0, 50000, "SOLD_OUT")])
        self.assertEqual(self._run().title, "찜한 자켓이 품절됐어요.")

    def test_어제도_품절이었으면_다시_알리지_않는다(self):
        self._saved("자켓", 50000, [(2, 50000, "AVAILABLE"), (1, 50000, "SOLD_OUT"), (0, 50000, "SOLD_OUT")])
        self.assertIsNone(self._run())

    def test_6개월_최저가를_표시한다(self):
        self._saved("로퍼", 100000, [(100, 90000, "AVAILABLE"), (10, 95000, "AVAILABLE"), (0, 80000, "AVAILABLE")])
        self.assertEqual(self._run().title, "찜한 로퍼가 6개월 최저가예요 (20% 내림).")

    def test_6개월보다_오래된_최저가는_보지_않는다(self):
        self._saved("로퍼", 100000, [(300, 70000, "AVAILABLE"), (10, 95000, "AVAILABLE"), (0, 80000, "AVAILABLE")])
        self.assertEqual(self._run().title, "찜한 로퍼가 6개월 최저가예요 (20% 내림).")

    def test_최저가가_아니면_예전처럼_하락만(self):
        self._saved("로퍼", 100000, [(10, 70000, "AVAILABLE"), (0, 80000, "AVAILABLE")])
        self.assertEqual(self._run().title, "찜한 로퍼가 20% 내려갔어요.")

    def test_잠잠하면_보내지_않는다(self):
        self._saved("티", 30000, [(1, 30000, "AVAILABLE"), (0, 31000, "AVAILABLE")])
        self.assertIsNone(self._run())
        self.assertFalse(Notification.objects.exists())

    def test_하루에_한_번(self):
        self._saved("셔츠", 100000, [(1, 100000, "AVAILABLE"), (0, 130000, "AVAILABLE")])
        self.assertIsNotNone(self._run())
        self.assertIsNone(self._run())
