"""금주의 리포트 집계(activity.py) 단위 테스트 — DB 없이 돈다.

돌리는 법:  cd backend && python -m unittest apps.api.test_activity
"""
import unittest
from datetime import datetime, timedelta

from apps.api.activity import KST, build_weekly_report, week_bounds

NOW = datetime(2026, 9, 17, 15, 0, tzinfo=KST)   # 목요일


def ev(kind, days_ago, style=None, hour=15, **meta):
    at = NOW.replace(hour=hour) - timedelta(days=days_ago)
    return {"type": kind, "at": at, "meta": meta, "style": style}


class WeeklyReportTest(unittest.TestCase):
    def test_week_bounds_monday_kst(self):
        start, end, prev = week_bounds(NOW)
        self.assertEqual(start.date().isoformat(), "2026-09-14")
        self.assertEqual(end.date().isoformat(), "2026-09-21")
        self.assertEqual(prev.date().isoformat(), "2026-09-07")

    def test_search_keywords_delta_and_top(self):
        events = [ev("SEARCH", 0, q="발레코어"), ev("SEARCH", 1, q="발레코어"), ev("SEARCH", 2, q="고프코어"),
                  ev("SEARCH", 7, q="아메카지")]
        events[0]["meta"]["facet"] = "스타일"
        s = build_weekly_report(events, [], NOW)["search"]
        self.assertEqual((s["keywords"], s["count"], s["prev_keywords"], s["delta"]), (2, 3, 1, 1))
        self.assertEqual(s["top"], {"label": "발레코어", "count": 2, "facet": "스타일"})

    def test_vote_toggle_counts_latest_only(self):
        events = [ev("VOTE", 1, card_key="a", choice="BUY"), ev("VOTE", 0, card_key="a", choice=None),
                  ev("VOTE", 0, card_key="b", choice="PASS"), ev("VOTE", 8, card_key="c", choice="BUY")]
        v = build_weekly_report(events, [], NOW)["vote"]
        self.assertEqual((v["count"], v["prev"], v["total"]), (1, 1, 2))

    def test_saved_new_and_total(self):
        events = [ev("SAVE", 20, item_id="x", liked=True), ev("SAVE", 1, item_id="y", liked=True),
                  ev("SAVE", 0, item_id="z", liked=True), ev("SAVE", 0, hour=16, item_id="z", liked=False)]
        self.assertEqual(build_weekly_report(events, [], NOW)["saved"], {"new": 1, "total": 2})

    def test_chat_minutes(self):
        t = NOW - timedelta(days=1)
        sessions = [{"started_at": t, "updated_at": t + timedelta(minutes=12)},
                    {"started_at": t, "updated_at": t}]          # 한 번만 물어본 대화 → 1분
        c = build_weekly_report([], sessions, NOW)["chat"]
        self.assertEqual((c["minutes"], c["sessions"], c["avg_minutes"]), (13, 2, 6))

    def test_chat_minutes_from_turns_not_session_span(self):
        """월요일에 묻고 일요일에 한 번 더 물어도 6일이 아니다 — 질문·응답·읽기 시간만 센다."""
        mon = datetime(2026, 9, 14, 10, 0, tzinfo=KST)
        chat = lambda at, ms, conv="c1": {"type": "CHAT", "at": at, "meta": {"conversation_id": conv, "answer_ms": ms}, "style": None}
        events = [chat(mon, 20_000),
                  chat(mon + timedelta(minutes=3), 40_000),          # 앞 답 끝나고 2분 40초 뒤 → 이어서 셈
                  chat(mon + timedelta(days=3), 30_000)]             # 3일 뒤 → 공백은 안 셈
        sessions = [{"started_at": mon, "updated_at": mon + timedelta(days=3)}]
        c = build_weekly_report(events, sessions, NOW)["chat"]
        # 첫 묶음 10:00:00 ~ 10:03:40 = 220초, 둘째 30초 → 250초 ≈ 4분
        self.assertEqual((c["minutes"], c["sessions"]), (4, 1))

    def test_chat_minutes_overlap_and_idle(self):
        t = datetime(2026, 9, 15, 20, 0, tzinfo=KST)
        chat = lambda at, ms, conv: {"type": "CHAT", "at": at, "meta": {"conversation_id": conv, "answer_ms": ms}, "style": None}
        events = [chat(t, 60_000, "a"), chat(t + timedelta(seconds=10), 60_000, "b"),   # 두 방 동시 → 겹침은 한 번
                  chat(t + timedelta(minutes=30), 0, "a")]                            # 30분 뒤 · 응답 기록 없음
        c = build_weekly_report(events, [], NOW)["chat"]
        self.assertEqual((c["minutes"], c["sessions"], c["avg_minutes"]), (1, 2, 1))

    def test_chat_legacy_session_capped(self):
        t = NOW - timedelta(days=2)
        c = build_weekly_report([], [{"started_at": t, "updated_at": t + timedelta(days=1)}], NOW)["chat"]
        self.assertEqual(c["minutes"], 30)

    def test_activity_days_and_hours(self):
        events = [ev("SEARCH", 0, q="a", hour=21), ev("CHAT", 3, hour=9)]   # 목 21시 · 월 9시
        a = build_weekly_report(events, [], NOW)["activity"]
        self.assertEqual(a["days"], [1, 0, 0, 1, 0, 0, 0])
        self.assertEqual((a["hours"][21], a["hours"][9]), (1, 1))

    def test_activity_drops_quick_undo(self):
        """★ 30초 안에 취소한 찜 · 투표는 활동량에서 뺀다.

        잘못 눌러 곧바로 취소한 것까지 세면 막대가 실제 관심보다 부풀어 보인다.
        대신 한참 뒤에 취소한 것은 진짜 활동이므로 그대로 센다.
        """
        def at(hour, minute, second=0, days_ago=0):
            return NOW.replace(hour=hour, minute=minute, second=second) - timedelta(days=days_ago)

        events = [
            # ① 찜 → 10초 뒤 취소 = 없던 일 (2건 모두 빠진다)
            {"type": "SAVE", "at": at(10, 0, 0), "meta": {"item_id": "a", "liked": True}, "style": None},
            {"type": "SAVE", "at": at(10, 0, 10), "meta": {"item_id": "a", "liked": False}, "style": None},
            # ② 찜 → 5분 뒤 취소 = 실제 활동 (2건 다 센다)
            {"type": "SAVE", "at": at(11, 0, 0), "meta": {"item_id": "b", "liked": True}, "style": None},
            {"type": "SAVE", "at": at(11, 5, 0), "meta": {"item_id": "b", "liked": False}, "style": None},
            # ③ 투표 → 10초 뒤 취소 = 없던 일
            {"type": "VOTE", "at": at(12, 0, 0), "meta": {"card_key": "c", "choice": "BUY"}, "style": None},
            {"type": "VOTE", "at": at(12, 0, 10), "meta": {"card_key": "c", "choice": None}, "style": None},
            # ④ 취소하지 않은 찜 = 그대로 센다
            {"type": "SAVE", "at": at(13, 0, 0), "meta": {"item_id": "d", "liked": True}, "style": None},
        ]
        a = build_weekly_report(events, [], NOW)["activity"]
        self.assertEqual(sum(a["days"]), 3)          # ② 2건 + ④ 1건
        self.assertEqual(a["hours"][10], 0)          # ① 빠짐
        self.assertEqual(a["hours"][11], 2)          # ② 남음
        self.assertEqual(a["hours"][12], 0)          # ③ 빠짐
        self.assertEqual(a["hours"][13], 1)          # ④ 남음

    def test_taste_share_vs_last_week(self):
        """검색한 키워드 중 스타일만 센다 — 투표 · 찜 · 스타일 아닌 검색은 빠진다."""
        events = [ev("SEARCH", 0, style="발레코어", q="발레코어"), ev("SEARCH", 1, style="발레코어", q="발레코어"),
                  ev("SEARCH", 2, style="고프코어", q="고프코어"), ev("SEARCH", 2, q="아디다스"),
                  ev("SAVE", 1, style="클래식", item_id="1", liked=True),
                  ev("VOTE", 2, style="클래식", card_key="k", choice="BUY"),
                  ev("SEARCH", 8, style="발레코어", q="발레코어")]
        t = build_weekly_report(events, [], NOW)["taste"]
        self.assertEqual(t["items"], [{"label": "발레코어", "share": 67, "delta": -33},
                                      {"label": "고프코어", "share": 33, "delta": 33}])
        self.assertEqual(t["new_style"], "고프코어")

    def test_taste_no_last_week_means_no_delta(self):
        t = build_weekly_report([ev("SEARCH", 0, style="클래식", q="클래식")], [], NOW)["taste"]
        self.assertIsNone(t["items"][0]["delta"])
        self.assertIsNone(t["new_style"])


if __name__ == "__main__":
    unittest.main()
