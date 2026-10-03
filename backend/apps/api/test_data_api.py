"""데이터 API 규칙(data_api.py) 단위 테스트 — DB 없이 돈다.

돌리는 법:  cd backend && python -m unittest apps.api.test_data_api
"""
import os
import unittest
from unittest import mock

from apps.api import data_api as D

TODAY = "2026-10-03"


class KeyTest(unittest.TestCase):
    def test_new_key_round_trip_and_only_hash_is_stored(self):
        raw, row = D.new_key(42)
        self.assertTrue(raw.startswith("fdk_42_"))
        self.assertEqual(D.parse_key(raw), (42, row["id"]))
        self.assertNotIn(raw, str(row))                      # 원문은 행 어디에도 없다
        self.assertEqual(row["hash"], D.digest(raw))
        meta = {"data_api_keys": [dict(row, name="a")]}
        self.assertIs(D.match(meta, row["id"], raw), meta["data_api_keys"][0])
        self.assertIsNone(D.match(meta, row["id"], raw + "x"))
        self.assertIsNone(D.match(meta, "deadbeef", raw))

    def test_revoked_keys_do_not_match(self):
        raw, row = D.new_key(1)
        meta = {"data_api_keys": [dict(row, revoked_at="2026-10-03T00:00:00")]}
        self.assertIsNone(D.match(meta, row["id"], raw))
        self.assertEqual(D.active_keys(meta), [])

    def test_parse_rejects_garbage(self):
        for bad in (None, "", "fdk_", "fdk_x_ab12cd34_" + "a" * 30, "fdk_1_XYZ12345_" + "a" * 30,
                    "fdk_1_ab12cd34_short", "sk_1_ab12cd34_" + "a" * 30, "fdk_1_ab12cd34_" + "a" * 30 + " x"):
            self.assertIsNone(D.parse_key(bad), bad)

    def test_header_forms(self):
        self.assertEqual(D.key_from_headers({"HTTP_AUTHORIZATION": "Bearer fdk_1"}), "fdk_1")
        self.assertEqual(D.key_from_headers({"HTTP_AUTHORIZATION": "bearer  fdk_2 "}), "fdk_2")
        self.assertEqual(D.key_from_headers({"HTTP_X_API_KEY": "fdk_3"}), "fdk_3")
        self.assertEqual(D.key_from_headers({"HTTP_AUTHORIZATION": "Basic abc"}), "")

    def test_public_view_hides_hash(self):
        raw, row = D.new_key(5)
        pub = D.public_key(dict(row, name="대시보드", created_at="t"))
        self.assertNotIn("hash", pub)
        self.assertEqual(pub["hint"], "fdk_…" + raw[-4:])

    def test_clean_name(self):
        self.assertEqual(D.clean_name("  마케팅   대시보드 "), "마케팅 대시보드")
        self.assertEqual(D.clean_name(""), "이름 없는 키")
        self.assertEqual(len(D.clean_name("가" * 99)), D.NAME_MAX)


class LimitTest(unittest.TestCase):
    def test_daily_limit(self):
        meta = {}
        for _ in range(3):
            ok, row = D.consume(meta, TODAY, limit=3)
            self.assertTrue(ok)
            meta["data_api_usage"] = row
        self.assertFalse(D.consume(meta, TODAY, limit=3)[0])
        self.assertTrue(D.consume(meta, "2026-10-04", limit=3)[0])     # 날이 바뀌면 다시

    def test_env_limits_are_clamped(self):
        with mock.patch.dict(os.environ, {"FEEDIT_DATA_API_PER_DAY": "50", "FEEDIT_DATA_API_PER_MIN": "-3"}):
            self.assertEqual(D.per_day(), 50)
            self.assertEqual(D.per_min(), 1)
        with mock.patch.dict(os.environ, {"FEEDIT_DATA_API_PER_DAY": "abc"}):
            self.assertEqual(D.per_day(), 10000)


class CatalogueTest(unittest.TestCase):
    def test_every_metric_points_at_a_real_view(self):
        # views.py 를 불러오면 Django 설정이 필요하다 — 이름만 소스에서 확인한다
        from pathlib import Path
        src = (Path(__file__).with_name("views.py")).read_text(encoding="utf-8")
        for name, (view, about, params) in D.METRICS.items():
            self.assertIn(f"\ndef {view}(request", src, name)
            self.assertTrue(about and params)
        self.assertNotIn("products", D.METRICS)         # 상품 통째 받기는 내주지 않는다
        self.assertNotIn("dictionary", D.METRICS)


if __name__ == "__main__":
    unittest.main()
