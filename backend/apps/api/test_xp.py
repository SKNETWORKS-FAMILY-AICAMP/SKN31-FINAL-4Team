"""경험치 계산(xp.py) 단위 테스트 — DB 없이 돈다.

돌리는 법:  cd backend && python -m unittest apps.api.test_xp
"""
import unittest
from datetime import date, datetime, timedelta

from apps.api.xp import (
    DAILY_CAP,
    WEEK_CAP,
    compute_xp,
    first_on_times,
    step_xp,
)
from apps.api.activity import KST

START = date(2026, 9, 21)                               # 월요일
NOW = datetime(2026, 9, 24, 18, 0, tzinfo=KST)          # 목요일


def at(day, hour=12, minute=0, second=0):
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=KST)


def week_item(state, key):
    return next(i for i in state["week"]["weekly"]["items"] if i["key"] == key)


def today_item(state, key):
    return next(i for i in state["today"]["items"] if i["key"] == key)


class StepTest(unittest.TestCase):
    def test_first_and_third(self):
        self.assertEqual([step_xp(n) for n in range(6)], [0, 1, 1, 4, 4, 4])


class DailyTest(unittest.TestCase):
    def test_zero_without_records(self):
        s = compute_xp(now=NOW, start=START)
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["today"]["earned"], 0)
        self.assertEqual(s["week"]["earned"], 0)
        self.assertFalse(s["fixed"])

    def test_full_day_is_fifteen(self):
        d = NOW.date()
        three = [at(d, 10), at(d, 11), at(d, 12), at(d, 13)]   # 4번 해도 하루 4가 끝
        s = compute_xp(now=NOW, start=START, visits={d}, chats=three, votes=three, saves=three)
        self.assertEqual(s["today"]["earned"], DAILY_CAP)
        self.assertEqual(s["total"], 15)
        self.assertEqual(today_item(s, "chat")["xp"], 4)
        self.assertEqual(today_item(s, "chat")["count"], 4)

    def test_two_questions_is_one(self):
        d = NOW.date()
        s = compute_xp(now=NOW, start=START, chats=[at(d, 9), at(d, 10)])
        self.assertEqual(s["total"], 1)

    def test_kst_midnight_splits_days(self):
        # 한국 시간 23:59 와 00:01 은 다른 날이다
        d = NOW.date()
        late = at(d - timedelta(days=1), 23, 59)
        early = at(d, 0, 1)
        s = compute_xp(now=NOW, start=START, chats=[late, late, early])
        self.assertEqual(s["total"], 1 + 1)                  # 어제 1(2번) + 오늘 1(1번)
        self.assertEqual(today_item(s, "chat")["count"], 1)

    def test_before_start_is_ignored(self):
        before = START - timedelta(days=1)
        s = compute_xp(now=NOW, start=START, visits={before},
                       chats=[at(before)] * 3, dwell={before: 3600},
                       site_feedbacks=[at(before)])
        self.assertEqual(s["total"], 0)


class ToggleTest(unittest.TestCase):
    def rows(self, *items):
        return [{"type": "SAVE", "at": t, "meta": {"item_id": k, "liked": on}} for t, k, on in items]

    def test_first_on_only_once_per_item(self):
        d = NOW.date()
        rows = self.rows((at(d, 9), "a", True), (at(d, 10), "a", False),
                         (at(d, 11), "a", True), (at(d, 12), "b", True))
        times = first_on_times(rows, "SAVE", "item_id", lambda m: bool(m.get("liked")))
        self.assertEqual(times, [at(d, 9), at(d, 12)])

    def test_quick_undo_does_not_count(self):
        d = NOW.date()
        rows = self.rows((at(d, 9, 0, 0), "a", True), (at(d, 9, 0, 10), "a", False))
        self.assertEqual(first_on_times(rows, "SAVE", "item_id", lambda m: bool(m.get("liked"))), [])

    def test_liked_before_start_never_counts_again(self):
        # 시작 전에 찜한 상품을 껐다 다시 켜도 새 찜이 아니다 → 첫 켬이 시작 전이라 0
        old = at(START - timedelta(days=3))
        d = NOW.date()
        rows = self.rows((old, "a", True), (at(d, 9), "a", False), (at(d, 10), "a", True))
        times = first_on_times(rows, "SAVE", "item_id", lambda m: bool(m.get("liked")))
        s = compute_xp(now=NOW, start=START, saves=times)
        self.assertEqual(s["total"], 0)


class WeeklyTest(unittest.TestCase):
    def test_all_attendance_needs_every_day(self):
        sun = date(2026, 9, 27)
        end = at(sun, 20)
        six = {START + timedelta(days=i) for i in range(6)}
        s = compute_xp(now=end, start=START, visits=six)
        self.assertEqual(week_item(s, "attend")["xp"], 0)
        self.assertEqual(week_item(s, "attend")["count"], 6)
        s = compute_xp(now=end, start=START, visits=six | {sun})
        self.assertEqual(week_item(s, "attend")["xp"], 5)
        self.assertEqual(s["total"], 7 * 3 + 5)

    def test_first_week_counts_from_start_day(self):
        start = date(2026, 9, 25)                          # 금요일에 시작
        sun = date(2026, 9, 27)
        visits = {start, start + timedelta(days=1), sun}
        s = compute_xp(now=at(sun, 21), start=start, visits=visits)
        self.assertEqual(week_item(s, "attend")["goal"], 3)
        self.assertEqual(week_item(s, "attend")["xp"], 5)

    def test_hits_five_each_capped(self):
        d = NOW.date()
        s = compute_xp(now=NOW, start=START, hits=[at(d, h) for h in range(8, 15)])
        self.assertEqual(week_item(s, "hit")["xp"], 25)
        self.assertEqual(week_item(s, "hit")["count"], 7)
        s = compute_xp(now=NOW, start=START, hits=[at(d, 9), at(d, 10)])
        self.assertEqual(s["total"], 10)

    def test_feedbacks_once_a_week(self):
        d = NOW.date()
        s = compute_xp(now=NOW, start=START, vote_feedbacks=[at(d), at(d, 13)], site_feedbacks=[at(d)])
        self.assertEqual(week_item(s, "vote_feedback")["xp"], 25)
        self.assertEqual(week_item(s, "site_feedback")["xp"], 25)
        self.assertEqual(s["total"], 50)

    def test_dwell_two_minutes_each(self):
        d = NOW.date()
        s = compute_xp(now=NOW, start=START, dwell={d: 7 * 60 + 59})     # 7분 59초 → 7분 → 3
        self.assertEqual(week_item(s, "dwell")["xp"], 3)
        self.assertEqual(week_item(s, "dwell")["minutes"], 7)
        s = compute_xp(now=NOW, start=START, dwell={d: 30 * 60, d - timedelta(days=1): 40 * 60})
        self.assertEqual(week_item(s, "dwell")["xp"], 25)                # 70분 → 35 → 25 에서 멈춤

    def test_last_week_counts_in_total_not_in_this_week(self):
        last = START - timedelta(days=3)
        s = compute_xp(now=NOW, start=START - timedelta(days=7), site_feedbacks=[at(last)],
                       visits={last})
        self.assertEqual(s["total"], 25 + 3)
        self.assertEqual(s["week"]["earned"], 0)
        self.assertEqual(week_item(s, "site_feedback")["xp"], 0)

    def test_perfect_week_is_210(self):
        sun = date(2026, 9, 27)
        days = [START + timedelta(days=i) for i in range(7)]
        act = [at(d, h) for d in days for h in (9, 10, 11)]
        s = compute_xp(now=at(sun, 23), start=START, visits=set(days), chats=act, votes=act, saves=act,
                       hits=[at(sun, h) for h in range(1, 7)], vote_feedbacks=[at(sun)],
                       dwell={d: 3600 for d in days}, site_feedbacks=[at(sun)])
        self.assertEqual(s["week"]["daily"]["earned"], 105)
        self.assertEqual(s["week"]["weekly"]["earned"], 105)
        self.assertEqual(s["week"]["earned"], WEEK_CAP)
        self.assertEqual(s["total"], 210)


if __name__ == "__main__":
    unittest.main()
