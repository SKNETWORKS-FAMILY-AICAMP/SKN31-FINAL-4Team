"""요금제 규칙(plan_policy.py) 단위 테스트 — DB 없이 돈다.

돌리는 법:  cd backend && python -m unittest apps.api.test_plan_policy
"""
import os
import unittest
from unittest import mock

from apps.api import plan_policy as P

TODAY = "2026-10-03"


def env(**kw):
    """FEEDIT_PUBLIC_BETA 등 환경변수를 잠깐 바꾼다. None 이면 지운다."""
    base = {k: v for k, v in os.environ.items()
            if k not in ("FEEDIT_PUBLIC_BETA", "FEEDIT_PLAN_SECRET", "FEEDIT_CHAT_TOKEN")}
    base.update({k: v for k, v in kw.items() if v is not None})
    return mock.patch.dict(os.environ, base, clear=True)


class BetaSwitchTest(unittest.TestCase):
    def test_beta_is_on_when_the_variable_is_missing(self):
        # 지금 운영 서버의 .env 에 아무것도 더하지 않아도 베타가 유지돼야 한다
        with env():
            self.assertTrue(P.public_beta())
            self.assertFalse(P.enforced())

    def test_only_explicit_off_values_end_the_beta(self):
        for off in ("0", "false", "off", "no", " OFF "):
            with env(FEEDIT_PUBLIC_BETA=off):
                self.assertTrue(P.enforced(), off)
        for on in ("1", "true", "yes", ""):
            with env(FEEDIT_PUBLIC_BETA=on):
                self.assertFalse(P.enforced(), on)

    def test_beta_state_opens_everything_even_for_free(self):
        with env(FEEDIT_PUBLIC_BETA="1"):
            st = P.state({"plan": "FREE"}, today=TODAY)
        self.assertFalse(st["enforced"])
        self.assertEqual(st["features"]["trend_edit"], list(P.EDIT_TABS))
        self.assertTrue(st["features"]["report_export"])
        self.assertIsNone(st["features"]["chat_daily"])
        self.assertIsNone(st["chat"])          # 베타 동안은 하루 횟수를 보여 주지도 않는다

    def test_after_beta_free_gets_the_table_values(self):
        with env(FEEDIT_PUBLIC_BETA="0"):
            st = P.state({}, today=TODAY)
        self.assertTrue(st["enforced"])
        self.assertEqual(st["plan"], "FREE")
        self.assertEqual(st["features"]["trend_edit"], ["temp"])
        self.assertFalse(st["features"]["report_export"])
        self.assertFalse(st["features"]["data_api"])
        self.assertEqual(st["features"]["chat_daily"], 20)
        self.assertEqual(st["chat"], {"limit": 20, "used": 0, "remaining": 20, "day": TODAY})


class PlanTableTest(unittest.TestCase):
    def test_matches_the_pricing_table(self):
        self.assertEqual(P.features_of("PRO")["trend_edit"], list(P.EDIT_TABS))
        self.assertTrue(P.features_of("PRO")["report_export"])
        self.assertFalse(P.features_of("PRO")["data_api"])
        self.assertTrue(P.features_of("BUSINESS")["data_api"])
        for plan in P.VALID:
            self.assertTrue(P.features_of(plan)["salmal"])     # 살!말? 참여는 모두 무제한

    def test_unknown_values_fall_to_free(self):
        for raw in (None, "", "TEST", "ADMIN", "gold", "pro "):
            expect = "PRO" if raw == "pro " else "FREE"
            self.assertEqual(P.normalize(raw), expect)
        self.assertEqual(P.stored_plan({"plan": "TEST", "alpha": True}), "FREE")   # 알파 계정
        self.assertEqual(P.stored_plan({"plan": "FREE"}, is_admin=True), "ADMIN")
        self.assertEqual(P.features_of("ADMIN"), P.features_of("BUSINESS"))
        self.assertEqual(P.chat_plan("ADMIN"), "BUSINESS")

    def test_features_are_copies(self):
        P.features_of("FREE")["trend_edit"].append("assoc")
        self.assertEqual(P.FEATURES["FREE"]["trend_edit"], ["temp"])


class ChatQuotaTest(unittest.TestCase):
    def test_free_stops_at_twenty_a_day(self):
        meta = {}
        for i in range(20):
            ok, row = P.chat_consume(meta, "FREE", TODAY)
            self.assertTrue(ok, i)
            meta["plan_chat"] = row
        ok, _ = P.chat_consume(meta, "FREE", TODAY)
        self.assertFalse(ok)
        self.assertEqual(P.chat_usage(meta, "FREE", TODAY)["remaining"], 0)

    def test_new_day_resets(self):
        meta = {"plan_chat": {"day": "2026-10-02", "used": 20}}
        self.assertTrue(P.chat_consume(meta, "FREE", TODAY)[0])
        self.assertEqual(P.chat_used(meta, TODAY), 0)

    def test_paid_plans_are_not_limited_but_still_counted(self):
        meta = {"plan_chat": {"day": TODAY, "used": 500}}
        ok, row = P.chat_consume(meta, "PRO", TODAY)
        self.assertTrue(ok)
        self.assertEqual(row["used"], 501)
        self.assertIsNone(P.chat_usage(meta, "BUSINESS", TODAY)["limit"])

    def test_broken_counter_does_not_crash(self):
        self.assertEqual(P.chat_used({"plan_chat": {"day": TODAY, "used": "x"}}, TODAY), 0)
        self.assertEqual(P.chat_used({"plan_chat": "oops"}, TODAY), 0)


class RequestTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(P.parse_request({"plan": "pro", "note": "  안녕  하세요 "})["note"], "안녕 하세요")
        with self.assertRaises(ValueError):
            P.parse_request({"plan": "GOLD"})
        with self.assertRaises(ValueError):
            P.parse_request({"plan": "BUSINESS"})            # 팀 이름 없음
        biz = P.parse_request({"plan": "BUSINESS", "company": "피딧", "contact": "a@b.c"})
        self.assertEqual((biz["company"], biz["contact"]), ("피딧", "a@b.c"))
        self.assertEqual(P.parse_request({"plan": "PRO", "company": "x"})["company"], "")
        self.assertEqual(len(P.parse_request({"plan": "PRO", "note": "가" * 999})["note"]), P.NOTE_MAX)

    def test_public_request_hides_who_decided(self):
        meta = {"plan_request": P.new_request({"plan": "PRO"}, "FREE", "2026-10-03T10:00:00+09:00")}
        meta["plan_request"]["decided_by"] = "admin"
        pub = P.request_public(meta)
        self.assertEqual(pub["status"], "PENDING")
        self.assertNotIn("decided_by", pub)
        self.assertIs(P.pending_of(meta), meta["plan_request"])

    def test_history_keeps_the_latest(self):
        meta = {}
        for i in range(P.HISTORY_MAX + 5):
            P.add_history(meta, "APPROVED", "PRO", "FREE", str(i))
        self.assertEqual(len(meta["plan_history"]), P.HISTORY_MAX)
        self.assertEqual(meta["plan_history"][-1]["at"], str(P.HISTORY_MAX + 4))


class TicketTest(unittest.TestCase):
    def test_no_secret_no_ticket(self):
        with env():
            self.assertIsNone(P.sign_ticket(1, "PRO"))

    def test_shape(self):
        t = P.sign_ticket(7, "ADMIN", now=1000, secret="k")
        head, body, sig = t.split(".")
        self.assertEqual(head, "v1")
        import base64
        import json
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        self.assertEqual(data, {"u": "7", "p": "BUSINESS", "e": 1000 + P.TICKET_TTL})

    def test_falls_back_to_chat_token(self):
        with env(FEEDIT_CHAT_TOKEN="tok"):
            self.assertEqual(P.ticket_secret(), "tok")
        with env(FEEDIT_CHAT_TOKEN="tok", FEEDIT_PLAN_SECRET="sec"):
            self.assertEqual(P.ticket_secret(), "sec")


if __name__ == "__main__":
    unittest.main()
