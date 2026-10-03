"""챗봇이 되물은 것을 다음 턴이 안다 (2026-10-01 실측).

    챗봇: 더비슈즈의 출처별 반응이나, 실제 언급 근거를 더 볼까요?
    사용자: 응 두개 다 알려줘
    챗봇: (아이템 순위와 소재 순위를 다시 보여 줌)

기억(history)에 사용자 질문만 있어서 '두 개' 가 무엇인지 모델이 알 수 없었다.
같은 대화의 "‘더비슈즈는 왜 93점이야?’ 대신 더비슈즈 기준으로 봤어요" 도 여기서 본다 —
원문에서 찾았는데도 '대신 봤다' 표시가 붙었다.

돌리는 법:  PYTHONPATH=ChatBot python -m unittest ChatBot/tests/test_followup_memory.py
"""
import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from app import history, orchestrator
from app.lexicon_gate import LexiconGate
from app.tools import Toolbox

ASKED = "더비슈즈의 출처별 반응이나, 실제 언급 근거를 더 볼까요?"


class Store:
    version = "feedit-unified-text-v1"

    def lexicon_entries(self):
        return [{"canonical": c, "facet": "item", "aliases": []} for c in ("더비슈즈", "재킷")]

    def metric_canonicals(self):
        return {"더비슈즈", "재킷"}

    def metric_terms_in(self, text, limit=3):
        return []


class MemoryTests(unittest.TestCase):
    def test_client_history_keeps_what_the_bot_asked(self):
        got = history.sanitize([{"q": "더비슈즈는 왜 93점이야?", "intent": "agent",
                                 "terms": [{"canonical": "더비슈즈"}],
                                 "next": f"<p>{ASKED}</p>"}])
        self.assertEqual(got[0]["next"], ASKED)

    def test_outside_value_is_clipped_to_one_line(self):
        got = history.sanitize([{"q": "x", "next": "줄\n바꿈 " + "가" * 500}])
        self.assertNotIn("\n", got[0]["next"])
        self.assertLessEqual(len(got[0]["next"]), history.NEXT_MAX)

    def test_server_memory_keeps_it_too(self):
        turn = history.make_turn("더비슈즈는 왜 93점이야?", "agent", "general", [],
                                 follow=f"<p>{ASKED}</p>")
        self.assertEqual(turn["next"], ASKED)
        self.assertNotIn("next", history.make_turn("안녕", "agent", "general", []))

    def test_model_sees_the_question_it_asked(self):
        past = history.sanitize([{"q": "더비슈즈는 왜 93점이야?", "next": ASKED}])
        block = orchestrator._ctx_block("응 두개 다 알려줘", {}, past)
        self.assertIn(f"[직전 답변이 물은 것] {ASKED}", block)

    def test_only_the_last_turn_counts(self):
        past = history.sanitize([{"q": "a", "next": "옛 질문을 볼까요?"}, {"q": "b"}])
        self.assertNotIn("[직전 답변이 물은 것]", orchestrator._ctx_block("응", {}, past))


class SubstitutedTests(unittest.TestCase):
    def setUp(self):
        self.box = Toolbox(Store(), LexiconGate(Store()))

    def test_found_in_the_question_itself_is_not_a_substitute(self):
        out = self.box.t_search_terms("더비슈즈는 왜 93점이야?", ["더비슈즈"])
        self.assertEqual([h["term"] for h in out["found"]], ["더비슈즈"])
        self.assertNotIn("substituted", out)

    def test_found_only_through_alts_is_a_substitute(self):
        out = self.box.t_search_terms("https://example.com/goods/123", ["더비슈즈"])
        self.assertTrue(out.get("substituted"))


if __name__ == "__main__":
    unittest.main()
