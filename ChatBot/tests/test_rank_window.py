"""'요즘 뜨는 스타일' 순위가 하루치만 보던 자리 (2026-10-01).

  지표 행은 언급이 있는 날에만 생긴다. 예전 순위는 전체 최신일 **하루**의 행만 봐서
  그날 언급되지 않은 용어는 통째로 빠졌다. 스타일은 하루 언급이 1~3건이라 10/1 에는
  스타일 축이 0개였다(트렌드 API 실측: 클래식 마지막 행 9/30 · 미니멀 9/29 · 고프코어 9/27).
  이제 최근 7일 안에서 용어마다 **마지막 값**으로 줄을 세운다 — 그 값은 트렌드 분석 화면이
  그 용어의 온도로 보여 주는 값과 같다.

  RDS 쿼리(rds_store.top_terms)는 같은 표를 만든 로컬 PostgreSQL 16 에서 같은 결과를
  확인했다(DEVELOPLOG 2026-10-01). 여기서는 SQLite 저장소로 같은 규칙을 지킨다.

돌리는 법:  PYTHONPATH=ChatBot python -m unittest ChatBot/tests/test_rank_window.py
"""
import sqlite3
import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from app import agent_blocks, tools
from app.store import ReadOnlyStore

ROWS = [
    # version, observed_on, source, canonical, facet, raw_count, temp, pct
    ("v1", "2026-10-01", "__all__", "재킷", "item", 5, 70.0, 70),
    ("v1", "2026-09-30", "__all__", "재킷", "item", 9, 80.0, 80),     # 마지막 값이 아니다
    ("v1", "2026-09-30", "__all__", "클래식", "style", 3, 66.4, 60),
    ("v1", "2026-09-28", "__all__", "클래식", "style", 1, 50.0, 40),
    ("v1", "2026-10-01", "musinsa", "클래식", "style", 1, 99.0, 99),  # 출처별 행은 안 본다
    ("v1", "2026-09-29", "__all__", "미니멀", "style", 2, 72.6, 70),
    ("v1", "2026-09-20", "__all__", "긱시크", "style", 1, 88.0, 88),  # 7일 밖
    ("v2", "2026-10-01", "__all__", "고프코어", "style", 9, 99.0, 99),  # 다른 버전
]


def store():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE metric_term_daily(metric_version, observed_on, source_code, "
               "canonical, facet, raw_count, temp, pct_rank)")
    db.executemany("INSERT INTO metric_term_daily VALUES (?,?,?,?,?,?,?,?)", ROWS)
    s = ReadOnlyStore.__new__(ReadOnlyStore)
    s.version = "v1"
    s.conn = lambda: db
    return s


class StoreWindowTests(unittest.TestCase):
    def test_style_rank_is_not_empty_on_a_day_without_style_mentions(self):
        rows = store().top_terms(facet="style")
        self.assertEqual([(r["canonical"], r["metric_date"]) for r in rows],
                         [("미니멀", "2026-09-29"), ("클래식", "2026-09-30")])

    def test_each_term_uses_its_latest_value(self):
        rows = {r["canonical"]: r for r in store().top_terms(facets=["style", "item"])}
        self.assertEqual(rows["재킷"]["temp"], 70.0)          # 9/30 의 80 이 아니다
        self.assertEqual(rows["클래식"]["temp"], 66.4)        # 출처별 99 가 아니다
        self.assertNotIn("긱시크", rows)                        # 9/20 은 7일 밖
        self.assertNotIn("고프코어", rows)                      # 다른 버전

    def test_one_day_window_is_the_old_rule(self):
        self.assertEqual([r["canonical"] for r in store().top_terms(facet="style", window_days=1)], [])


class RankToolTests(unittest.TestCase):
    def rank(self):
        return tools.Toolbox(store(), Mock()).t_rank_terms(facet="style", limit=10)

    def test_tool_says_the_window_and_each_date(self):
        res = self.rank()
        self.assertEqual(res["as_of"], "2026-10-01")
        self.assertEqual(res["window_days"], 7)
        self.assertIn("최근 7일", res["window_note"])
        self.assertEqual([(i["term"], i["temp"], i["date"]) for i in res["items"]],
                         [("미니멀", 73, "2026-09-29"), ("클래식", 66, "2026-09-30")])

    def test_card_shows_the_window_and_older_dates(self):
        block = agent_blocks._rank_block(self.rank(), "2026-10-01")
        # 10개를 물었는데 2개뿐이라 그 사실도 함께 적힌다
        self.assertEqual(block["meta"], "트렌드 온도순 · 최근 7일 · 2026-10-01 기준 · 찾은 것 2개가 전부입니다")
        self.assertEqual([r["small"] for r in block["rows"]], ["스타일 · 9/29", "스타일 · 9/30"])


if __name__ == "__main__":
    unittest.main()
