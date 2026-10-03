"""'핫한 아이템 순위는?' 답이 꼬였던 자리 (2026-10-01 실측).

    더비슈즈가 가장 뜨겁고, … 상위 개는 모두 과열 구간입니다.
    플리스재킷도 따뜻함 구간에 있어, 최근 본 플리스와 함께 볼 만해요.
    [다음] 플리스재킷과 트랙탑 중 어느 쪽을 더 자세히 볼까요?

  ① "상위 개는" — 모델이 순위 항목을 세어 쓴 "4" 가 도구 결과에 없어 검증이 숫자만 지웠다.
  ② 트랙탑 · 플리스 — 이번 순위에 없는 지난 주제를 [최근 본 용어] 에서 끌어왔다.
  ③ 카드의 'item' · 87점 — 축 이름이 영어로, 온도는 화면(88°)과 달리 잘려 나왔다.

돌리는 법:  PYTHONPATH=ChatBot python -m unittest ChatBot/tests/test_rank_followup.py
"""
import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from app import agent_blocks, agent_path, verify
from app.lexicon_gate import LexiconGate
from app.tools import Toolbox

# 운영 순위 그대로 (2026-09-29 아이템 축) — 원값은 소수, 화면은 반올림해 보여 준다
TOP = [("더비슈즈", 92.9), ("재킷", 87.6), ("가디건", 85.1), ("셔츠", 84.6),
       ("플리스재킷", 83.7), ("첼시부츠", 83.6), ("구두", 83.4), ("슬랙스", 80.6)]


class Store:
    version = "feedit-unified-text-v1"

    def latest_day(self):
        return "2026-09-29"

    def top_terms(self, facet=None, limit=10, facets=None):
        return [{"canonical": t, "facet": "item", "temp": v, "raw_count": 10}
                for t, v in TOP[:limit]]

    # LexiconGate 가 운영(RDS)과 같은 길로 사전을 만들게 한다
    def lexicon_entries(self):
        rows = [(t, "item") for t, _ in TOP] + [("트랙탑", "item"), ("플리스", "material"),
                                                ("새틴", "material"), ("니트", "material")]
        return [{"canonical": c, "facet": f, "aliases": []} for c, f in rows]

    def metric_canonicals(self):
        return {c["canonical"] for c in self.lexicon_entries()}


class Trace:
    def __init__(self, calls):
        self.calls = calls
        self.missing = []


def ranking_trace():
    box = Toolbox(Store(), Mock())
    box.run("rank_terms", {"facet": "item", "limit": 8})
    return box.trace


class RankItemsTests(unittest.TestCase):
    def test_temperatures_are_rounded_like_the_page(self):
        items = ranking_trace().calls[0]["result"]["items"]
        self.assertEqual([i["temp"] for i in items], [93, 88, 85, 85, 84, 84, 83, 81])
        self.assertEqual([i["rank"] for i in items], list(range(1, 9)))
        self.assertEqual({i["facet_name"] for i in items}, {"아이템"})

    def test_band_counts_and_streak_come_from_the_tool(self):
        res = ranking_trace().calls[0]["result"]
        # 화면 구간: 반올림한 값이 85 이상이면 과열 — 셔츠 84.6 → 85 → 과열
        self.assertEqual([i["band"] for i in res["items"][:5]],
                         ["과열", "과열", "과열", "과열", "따뜻함"])
        self.assertEqual(res["top_streak"], {"band": "과열", "count": 4})
        self.assertEqual(res["band_counts"], {"과열": 4, "따뜻함": 4})

    def test_top_n_count_is_a_verified_number(self):
        trace = ranking_trace()
        rep = verify.check("상위 4개는 모두 과열 구간입니다. 더비슈즈가 93점으로 1위예요.", trace)
        self.assertEqual(rep.suspect_numbers, [])

    def test_ranking_card_speaks_korean_and_page_numbers(self):
        block = agent_blocks._rank_block(ranking_trace().calls[0]["result"], "2026-09-29")
        self.assertEqual(block["rows"][1]["small"], "아이템")
        self.assertEqual(block["rows"][1]["v"], "88점")


class VerifyFixTests(unittest.TestCase):
    def test_fix_that_leaves_a_bare_unit_is_rejected(self):
        before = "더비슈즈가 가장 뜨거워요.\n상위 4개는 모두 과열 구간입니다."
        broken = "더비슈즈가 가장 뜨거워요.\n상위 개는 모두 과열 구간입니다."
        fixed, why = verify._read_fix(before, {"ok": False, "answer": broken})
        self.assertIsNone(fixed)
        self.assertEqual(why, "fix_garbled:dangling_unit")

    def test_dropping_the_whole_sentence_is_accepted(self):
        before = "더비슈즈가 가장 뜨거워요.\n상위 4개는 모두 과열 구간입니다."
        dropped = "더비슈즈가 가장 뜨거워요."
        self.assertEqual(verify._read_fix(before, {"ok": False, "answer": dropped}), (dropped, ""))


class FollowupGroundingTests(unittest.TestCase):
    def setUp(self):
        self.gate = LexiconGate(Store())
        self.trace = ranking_trace()
        self.q = "그럼 핫한 아이템 순위는?"

    def follow(self, text, question=None):
        return agent_path._grounded_followup(text, question or self.q, self.trace, self.gate)

    def test_old_topic_in_followup_is_dropped(self):
        self.assertEqual(self.follow("플리스재킷과 트랙탑 중 어느 쪽을 더 자세히 볼까요?"), "")

    def test_followup_about_this_ranking_is_kept(self):
        for text in ("더비슈즈와 재킷 중 어느 쪽을 더 자세히 볼까요?",
                     "플리스재킷을 더 자세히 볼까요?",        # '플리스' 로 잘못 잘리지 않는다
                     "소재 축 순위도 볼까요?"):                # 용어가 없으면 건드리지 않는다
            with self.subTest(text=text):
                self.assertEqual(self.follow(text), text)

    def test_term_the_user_named_is_allowed(self):
        self.assertEqual(self.follow("트랙탑도 같이 볼까요?", "트랙탑이랑 아이템 순위 보여줘"),
                         "트랙탑도 같이 볼까요?")


if __name__ == "__main__":
    unittest.main()
