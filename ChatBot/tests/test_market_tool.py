"""get_market — 가격·할인·리셀·수명주기 도구 (2026-09-20).

트렌드 분석 화면과 같은 Django API(/api/discount · resale · lifecycle)를 읽는다.
여기서는 HTTP 대신 가짜 응답으로, 조건 전달 · 결과 추리기 · 빈 조건 처리만 본다.
"""
import unittest
from unittest.mock import patch

from app import tools
from app.adapters import MarketHTTPAdapter


class _Box(tools.Toolbox):
    def __init__(self, market):
        self.store = None; self.gate = None; self.ctx = {}
        self.salmal = None; self.taste = None; self.websearch = None
        self.product = None; self.market = market
        self.trace = tools.TraceLog()


RESALE = {"status": "ok", "data": {
    "label": "나이키", "as_of": "2026-09-19T10:00:00+09:00", "days": 30, "listings": 577,
    "keep_pct": 80.0, "used_price": 33000, "regular_price": None, "volume_4w": 717,
    "sizes": [{"label": "270", "count": 40, "share_pct": 7.0, "ratio": .8, "price": 33000}],
    "platforms": [{"label": "크림", "count": 100, "share_pct": 17.3, "ratio": None, "price": 120000}],
    "series": [{"date": "2026-09-01", "ratio": .8}] * 30}}


class MarketToolTests(unittest.TestCase):
    def test_spec_registered(self):
        self.assertIn("get_market", tools.NAMES)

    def test_needs_some_condition(self):
        out = _Box(MarketHTTPAdapter()).t_get_market("resale")
        self.assertIn("unavailable", out)

    def test_resale_passes_selection_and_drops_series(self):
        seen = {}
        def fake_get(self, path, params):
            seen["path"], seen["params"] = path, params
            return RESALE["data"]
        with patch.object(MarketHTTPAdapter, "_get", fake_get):
            out = _Box(MarketHTTPAdapter()).t_get_market("resale", brand="나이키", days=30)
        self.assertEqual(seen["path"], "resale")
        self.assertEqual(seen["params"]["brand"], "나이키")
        self.assertNotIn("series", out)
        self.assertEqual(out["listings"], 577)
        self.assertEqual(out["platforms"][0]["label"], "크림")
        self.assertIn("note", out)          # 정가 없음 안내
        self.assertEqual(out["query"], {"brand": "나이키"})

    def test_unavailable_passthrough(self):
        with patch.object(MarketHTTPAdapter, "_get",
                          lambda self, p, q: {"unavailable": "살!말? 데이터가 없습니다."}):
            out = _Box(MarketHTTPAdapter()).t_get_market("discount", style="고프코어")
        self.assertIn("시장 데이터", out["unavailable"])


if __name__ == "__main__":
    unittest.main()
