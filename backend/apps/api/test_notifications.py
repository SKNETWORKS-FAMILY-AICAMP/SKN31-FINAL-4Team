"""알림 규칙(notifications.py) 단위 테스트 — DB 없이 돈다.

돌리는 법:  cd backend && python -m unittest apps.api.test_notifications
"""
import unittest
from datetime import date, datetime, timezone as dt_timezone

from apps.api.notifications import (
    KST,
    PRICE_DROP_MIN_RATE,
    badge_text,
    drop_rate,
    has_final,
    kst_day,
    price_digest,
    price_drops,
    term_added_text,
    vote_milestone,
    vote_result_text,
    weekly_report_text,
)


def item(name, base, current):
    return {"item_id": name, "name": name, "base": base, "current": current}


class PriceDropTest(unittest.TestCase):
    def test_drop_rate(self):
        self.assertAlmostEqual(drop_rate(100000, 85000), 0.15)
        self.assertIsNone(drop_rate(100000, 100000))   # 그대로면 하락이 아니다
        self.assertIsNone(drop_rate(100000, 120000))   # 올랐다
        self.assertIsNone(drop_rate(None, 1000))
        self.assertIsNone(drop_rate(0, 1000))

    def test_small_drop_is_ignored(self):
        """1~2% 는 판매처의 일상적인 등락이라 알리지 않는다."""
        self.assertEqual(price_drops([item("A", 100000, 99000)]), [])
        self.assertEqual(len(price_drops([item("A", 100000, 100000 * (1 - PRICE_DROP_MIN_RATE))])), 1)

    def test_sorted_by_rate(self):
        drops = price_drops([item("A", 100, 90), item("B", 100, 50), item("C", 100, 80)])
        self.assertEqual([d["name"] for d in drops], ["B", "C", "A"])
        self.assertEqual([d["percent"] for d in drops], [50, 20, 10])

    def test_digest_one(self):
        title, body = price_digest(price_drops([item("발레 플랫", 100000, 85000)]))
        self.assertEqual(title, "찜한 발레 플랫이 15% 내려갔어요.")
        self.assertEqual(body, "")

    def test_digest_many_is_one_line(self):
        """상품마다 한 건씩 보내지 않는다 — 하루치를 한 줄로 묶는다."""
        drops = price_drops([item("A", 100, 80), item("B", 100, 70), item("C", 100, 60)])
        title, body = price_digest(drops)
        self.assertEqual(title, "찜한 상품 3개가 내려갔어요.")
        self.assertEqual(body, "C 40% · B 30% · A 20%")

    def test_digest_caps_at_five(self):
        drops = price_drops([item(f"P{i}", 100, 50) for i in range(8)])
        _title, body = price_digest(drops)
        self.assertTrue(body.endswith("외 3개"))

    def test_digest_empty(self):
        self.assertEqual(price_digest([]), (None, None))


class VoteResultTest(unittest.TestCase):
    def test_milestone(self):
        self.assertIsNone(vote_milestone(9))
        self.assertEqual(vote_milestone(10), 10)
        self.assertEqual(vote_milestone(31), 10)

    def test_text_counts_are_not_conclusions(self):
        title, body = vote_result_text(10, 7, "스퀘어 토 로퍼")
        self.assertEqual(title, "10명 중 7명이 '살!'이라고 했어요.")
        self.assertEqual(body, "스퀘어 토 로퍼")

    def test_no_votes(self):
        self.assertEqual(vote_result_text(0, 0), (None, None))


class OtherTextTest(unittest.TestCase):
    def test_badge(self):
        self.assertEqual(badge_text("살말 백전 100")[0], "뱃지 '살말 백전 100'을 달성했어요.")

    def test_term_added_shows_canonical_when_different(self):
        title, body = term_added_text("블로 코어", "블록코어")
        self.assertEqual(title, "요청한 '블로 코어'가 사전에 올라갔어요.")
        self.assertEqual(body, "사전에는 '블록코어'로 올라갔어요.")

    def test_term_added_same_name(self):
        self.assertEqual(term_added_text("고프코어", "고프코어")[1], "")

    def test_weekly(self):
        title, _body = weekly_report_text(date(2026, 9, 14))
        # 2026-09-21 — 일요일 18:00 에 금주의 리포트가 갱신된다는 문구로 바뀌었다(0479ac4)
        self.assertEqual(title, "일요일이 왔어요.")


class JosaTest(unittest.TestCase):
    """조사 — 상품명·용어는 우리가 고른 말이 아니다."""

    def test_hangul(self):
        self.assertTrue(has_final("플랫"))
        self.assertFalse(has_final("로퍼"))

    def test_digit_reading(self):
        self.assertTrue(has_final("살말 백전 100"))    # 백 → 받침 있음
        self.assertFalse(has_final("개근상 2"))        # 이 → 받침 없음

    def test_price_digest_picks_josa(self):
        title, _ = price_digest(price_drops([item("로퍼", 100000, 80000)]))
        self.assertEqual(title, "찜한 로퍼가 20% 내려갔어요.")

    def test_badge_josa(self):
        self.assertEqual(badge_text("스타일 입문자")[0], "뱃지 '스타일 입문자'를 달성했어요.")


class DayTest(unittest.TestCase):
    def test_kst_day_groups_by_korean_date(self):
        """배치가 UTC 로 돌아도 '하루 한 번'은 한국 날짜로 묶인다."""
        at = datetime(2026, 9, 19, 16, 0, tzinfo=dt_timezone.utc)   # KST 9/20 01:00
        self.assertEqual(kst_day(at), date(2026, 9, 20))
        self.assertEqual(kst_day(datetime(2026, 9, 19, 1, 0, tzinfo=KST)), date(2026, 9, 19))



class JobReviewTextTest(unittest.TestCase):
    """직업 인증 결과 알림 문구 (2026-09-19)."""

    def test_approved(self):
        from apps.api.notifications import job_review_text
        title, body = job_review_text("Stylist", True)
        self.assertEqual(title, "Stylist 인증이 승인됐어요.")
        self.assertIn("배지", body)

    def test_rejected_with_reason(self):
        from apps.api.notifications import job_review_text
        title, body = job_review_text("MD", False, "서류가 흐려요")
        self.assertEqual(title, "MD 인증이 반려됐어요.")
        self.assertTrue(body.startswith("사유: 서류가 흐려요\n"))

    def test_setting_field(self):
        from apps.api.notifications import JOB_REVIEW, SETTING_FIELD
        self.assertEqual(SETTING_FIELD[JOB_REVIEW], "job_review")


class VoteCommentTextTest(unittest.TestCase):
    """살말 새 댓글 알림 문구 (2026-09-19)."""

    def test_side_and_quote(self):
        from apps.api.notifications import vote_comment_text
        title, body = vote_comment_text("민지", "보머 재킷", "실물이 더 예뻐요", "BUY")
        self.assertEqual(title, "민지님이 '살!' 쪽에서 댓글을 남겼어요.")
        self.assertEqual(body, "'보머 재킷'\n“실물이 더 예뻐요”")   # 2026-09-20 줄을 나눠 적는다

    def test_long_comment_is_cut(self):
        from apps.api.notifications import vote_comment_text
        _, body = vote_comment_text("A", "", "가" * 100, "NEUTRAL")
        self.assertTrue(body.endswith("…”"))
        self.assertLessEqual(len(body), 64)

if __name__ == "__main__":
    unittest.main()


class AdminNoticeRuleTest(unittest.TestCase):
    """관리자가 보내는 알림 · 상단 띠 공지 문구 다듬기 (2026-10-02)."""

    def test_clean_notice_keeps_line_breaks_and_trims(self):
        from apps.api.notifications import clean_notice
        self.assertEqual(clean_notice(" 점검  안내 ", "첫 줄\r\n\n\n\n둘째   줄", "trend"),
                         ("점검 안내", "첫 줄\n\n둘째 줄", "trend"))

    def test_clean_notice_rejects_empty_long_and_unknown_link(self):
        from apps.api.notifications import NOTICE_TITLE_MAX, clean_notice
        for args in (("",), ("가" * (NOTICE_TITLE_MAX + 1),), ("t", "", "admin")):
            with self.assertRaises(ValueError):
                clean_notice(*args)

    def test_ticker_is_one_line(self):
        from apps.api.notifications import clean_ticker
        self.assertEqual(clean_ticker("가을\n리포트  오픈", "home"), ("가을 리포트 오픈", "home"))

    def test_parse_recipients_numbers_are_ids_rest_are_nicknames(self):
        from apps.api.notifications import parse_recipients
        self.assertEqual(parse_recipients("12, 진, @민지\n34;12"), ([12, 34], ["진", "민지"]))
