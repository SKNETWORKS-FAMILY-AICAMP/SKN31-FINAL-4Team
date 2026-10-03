"""수명주기 발주 판별 (METRIC-002, 2026-09-27) — DB 없이 돈다."""
import unittest

from apps.api.views import ORDER_TIMING, _lifecycle_stage, _order_timing


class OrderTimingTest(unittest.TestCase):
    def test_네_단계를_모두_판별한다(self):
        self.assertEqual({k: _order_timing(k)["code"] for k in ("태동", "확산", "정점", "쇠퇴")},
                         {"태동": "GOOD", "확산": "GOOD", "정점": "CAUTION", "쇠퇴": "AVOID"})

    def test_쇠퇴는_비추천(self):
        self.assertEqual(_order_timing("쇠퇴")["label"], "발주 비추천")

    def test_판정_보류면_판별하지_않는다(self):
        self.assertIsNone(_order_timing(None))

    def test_문구에_지어낸_숫자가_없다(self):
        """리드타임 · 잔여 주 수 같은 값은 우리 데이터에 없다 — 문구에 숫자를 넣지 않는다."""
        for _code, label, reason in ORDER_TIMING.values():
            self.assertFalse(any(ch.isdigit() for ch in label + reason), reason)

    def test_관측이_모자라면_단계도_판별도_없다(self):
        pts = [{"date": f"2026-09-{i + 1:02d}", "level": 50, "ma28": 50, "momentum": 60} for i in range(10)]
        stage, _p, _d = _lifecycle_stage(pts)
        self.assertIsNone(_order_timing(stage))
