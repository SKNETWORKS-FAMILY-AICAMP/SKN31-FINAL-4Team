"""요즘 코디 찾기 · 코디 다양화 (2026-10-02).

"데이트룩 추천해줘" 를 몇 번 물어도 같은 룩이 나왔다 — 칸마다 추천순 1위만 집었고,
요즘 실제로 입는 조합을 찾아보는 단계가 없었다.
"""
import os
import random
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.modules.setdefault("requests", Mock())
sys.modules.setdefault("psycopg", Mock())
sys.modules.setdefault("psycopg.rows", Mock(dict_row=None))

from app import fit, lookbook, orchestrator, tools  # noqa: E402


def _row(n, kind="셔츠"):
    return {"name": f"{kind} {n}", "image": f"https://image.msscdn.net/{kind}{n}.jpg",
            "url": f"https://www.musinsa.com/products/{kind}{n}", "product_source_id": f"{kind}{n}"}


class Market:
    def __init__(self, pool):
        self.pool, self.asked = pool, []

    def products(self, sel, limit=3):
        self.asked.append({**sel, "limit": limit})
        return self.pool.get(sel.get("kind"), [])[:limit]


class DiversityTests(unittest.TestCase):
    def test_same_question_does_not_always_give_the_same_item(self):
        market = Market({"티셔츠": [_row(i, "티셔츠") for i in range(10)]})
        names = {fit.propose(market, ["미니멀"], ["상의"], rng=random.Random(seed))["items"][0]["name"]
                 for seed in range(12)}
        self.assertGreater(len(names), 1)
        # 위쪽 후보에서만 고른다 — 엉뚱한 하위 상품이 섞이지 않게
        self.assertTrue(all(int(n.split()[-1]) < fit.PICK_TOP for n in names))
        self.assertEqual(market.asked[0]["limit"], fit.POOL)

    def test_seen_items_are_never_offered_again(self):
        pool = [_row(i, "티셔츠") for i in range(3)]
        market = Market({"티셔츠": pool, "셔츠": [_row(9, "셔츠")]})
        seen = [pool[0]["url"], pool[1]["product_source_id"], pool[2]["image"]]   # 어느 열쇠로 기억해도
        got = fit.propose(market, ["미니멀"], ["상의"], seen=seen, rng=random.Random(1))
        self.assertEqual(got["items"][0]["name"], "셔츠 9")      # 다 본 말은 넘어가 다음 말로
        self.assertEqual(got["excluded_seen"], 3)

    def test_everything_seen_means_unavailable_not_a_repeat(self):
        pool = [_row(0, "티셔츠")]
        market = Market({"티셔츠": pool})
        got = fit.propose(market, ["미니멀"], ["상의"], seen=[pool[0]["url"]])
        self.assertIn("unavailable", got)

    def test_same_product_is_not_used_twice_in_one_look(self):
        market = Market({"재킷": [_row(0, "재킷")]})
        got = fit.propose(market, ["미니멀"], ["아우터", "아우터"], rng=random.Random(0))
        self.assertEqual(len(got["items"]), 1)


class MemoryTests(unittest.TestCase):
    def test_clean_memory_takes_only_safe_strings(self):
        got = fit.clean_memory({"seen": ["a", 3, {"x": 1}, "", "b" * 400] + ["z"] * 100,
                                "refs": ["https://vogue.co.kr/a", "javascript:alert(1)"],
                                "occasion": "  친구   결혼식  하객 "})
        self.assertEqual(got["fit_seen"][:2], ["a", "3"])
        self.assertEqual(len(got["fit_seen"][2]), 300)
        self.assertLessEqual(len(got["fit_seen"]), 60)
        self.assertEqual(got["fit_refs"], ["https://vogue.co.kr/a"])
        self.assertEqual(got["fit_occasion"], "친구 결혼식 하객")
        self.assertEqual(fit.clean_memory("nope"), {})

    def test_proposal_keeps_occasion_and_web_ref_only(self):
        p = fit.clean_proposal({"items": [{"slot": "상의", "image": "https://image.msscdn.net/a.jpg",
                                           "name": "셔츠"}],
                                "occasion": "주말 데이트",
                                "ref": {"title": "데이트룩", "url": "https://www.vogue.co.kr/x"}})
        self.assertEqual(p["occasion"], "주말 데이트")
        self.assertEqual(p["ref"]["url"], "https://www.vogue.co.kr/x")
        bad = fit.clean_proposal({"items": [{"slot": "상의", "image": "https://image.msscdn.net/a.jpg"}],
                                  "ref": {"url": "javascript:alert(1)"}})
        self.assertNotIn("ref", bad)

    def test_context_tells_the_model_what_was_shown(self):
        block = orchestrator._ctx_block("다른 룩도", {"fit_seen": ["a", "b"], "fit_occasion": "하객",
                                                      "fit_refs": ["https://vogue.co.kr/a"]}, [])
        self.assertIn("[이 대화의 코디 상황] 하객", block)
        self.assertIn("이미 보여 준 상품] 2점", block)
        self.assertIn("https://vogue.co.kr/a", block)


class LookbookTests(unittest.TestCase):
    def setUp(self):
        lookbook._cache.clear()

    GOT = {"looks": [
        {"title": "블레이저 하객룩", "who": "보그", "url": "https://www.vogue.co.kr/2026/09/guest",
         "items": [{"slot": "아우터", "item": "블레이저"}, {"slot": "하의", "item": "‘와이드 슬랙스’"},
                   {"slot": "신발", "item": "로퍼"}]},
        {"title": "지어낸 룩", "who": "", "url": "https://made.up/look",
         "items": [{"slot": "상의", "item": "셔츠"}, {"slot": "하의", "item": "치노"}]},
        {"title": "아이템 하나", "who": "", "url": "https://www.elle.co.kr/a",
         "items": [{"slot": "상의", "item": "니트"}]},
        {"title": "인스타", "who": "", "url": "https://www.instagram.com/p/x",
         "items": [{"slot": "상의", "item": "셔츠"}, {"slot": "하의", "item": "데님"}]},
    ], "_raw_sources": [{"url": "https://www.vogue.co.kr/2026/09/guest", "title": "보그 하객룩"},
                        {"url": "https://www.elle.co.kr/a", "title": "엘르"},
                        {"url": "https://www.instagram.com/p/x", "title": "insta"}]}

    def test_only_cited_articles_with_two_or_more_items_survive(self):
        with patch("app.llm.available", return_value=True), \
             patch("app.llm.respond", return_value=self.GOT), \
             patch("app.magazine._page_exists", return_value=False):
            got = lookbook.find("친구 결혼식 하객", ["미니멀"], "MALE")
        self.assertTrue(got["found"])
        self.assertEqual([lk["title"] for lk in got["looks"]], ["블레이저 하객룩"])
        look = got["looks"][0]
        self.assertEqual(look["source"]["url"], "https://www.vogue.co.kr/2026/09/guest")
        self.assertEqual(look["items"][1], {"slot": "하의", "item": "와이드 슬랙스"})   # 따옴표를 걷는다
        self.assertTrue(got["not_feedit_data"])

    def test_search_hint_carries_gender_and_result_is_cached(self):
        with patch("app.llm.available", return_value=True), \
             patch("app.llm.respond", return_value=self.GOT) as respond, \
             patch("app.magazine._page_exists", return_value=False):
            lookbook.find("주말 데이트", [], "FEMALE")
            again = lookbook.find("주말 데이트", [], "FEMALE")
        self.assertEqual(respond.call_count, 1)
        self.assertTrue(again["cached"])
        self.assertIn("여자", respond.call_args.args[1]["search_hint"])

    def test_failure_is_said_not_invented(self):
        with patch("app.llm.available", return_value=True), \
             patch("app.llm.respond", return_value=None):
            got = lookbook.find("주말 데이트")
        self.assertFalse(got["found"])
        self.assertEqual(got["looks"], [])
        self.assertIn("실패", got["reason"])


class ToolTests(unittest.TestCase):
    LOOK = {"title": "블레이저 하객룩", "who": "보그",
            "source": {"title": "보그", "url": "https://www.vogue.co.kr/g", "domain": "www.vogue.co.kr"},
            "items": [{"slot": "상의", "item": "셔츠"}, {"slot": "하의", "item": "슬랙스"}]}

    def _box(self, ctx=None):
        market = Market({"셔츠": [_row(i) for i in range(3)], "슬랙스": [_row(i, "슬랙스") for i in range(3)]})
        gate = Mock()
        box = tools.Toolbox(Mock(), gate, ctx={"recent_styles": ["미니멀"], **(ctx or {})}, market=market)
        return box, market

    def test_find_looks_uses_profile_gender_and_marks_used_refs(self):
        box, _ = self._box({"gender": "MALE", "fit_refs": ["https://www.vogue.co.kr/g"]})
        with patch("app.lookbook.find", return_value={"looks": [self.LOOK], "found": True}) as find:
            got = box.run("find_looks", {"occasion": "하객", "styles": [], "wearer": "self"})
        self.assertEqual(find.call_args.args[2], "MALE")
        self.assertEqual(got["used_before"], ["https://www.vogue.co.kr/g"])

    def test_ref_is_attached_only_when_it_came_from_find_looks(self):
        box, _ = self._box()
        with patch("app.lookbook.find", return_value={"looks": [self.LOOK], "found": True}):
            box.run("find_looks", {"occasion": "하객", "styles": [], "wearer": "self"})
        with patch("app.fit.resolve_styles", return_value=(["미니멀"], [])):
            ok = box.t_propose_fit(styles=["미니멀"], slots=["상의", "하의"], kinds=["셔츠", "슬랙스"],
                                   options=[], why="", occasion="친구 결혼식 하객",
                                   ref_url="https://www.vogue.co.kr/g")
            bad = box.t_propose_fit(styles=["미니멀"], slots=["상의"], kinds=["셔츠"], options=[],
                                    why="", ref_url="https://made.up/x")
        self.assertEqual(ok["ref"]["url"], "https://www.vogue.co.kr/g")
        self.assertEqual(ok["occasion"], "친구 결혼식 하객")
        self.assertNotIn("ref", bad)
        self.assertIn("ref_dropped", bad)

    def test_propose_fit_passes_seen_items(self):
        box, market = self._box({"fit_seen": [_row(0)["url"], _row(1)["url"]]})
        with patch("app.fit.resolve_styles", return_value=(["미니멀"], [])):
            got = box.t_propose_fit(styles=["미니멀"], slots=["상의"], kinds=["셔츠"], options=[], why="")
        self.assertEqual(got["items"][0]["name"], "셔츠 2")

    def test_specs_have_find_looks_and_new_propose_args(self):
        names = {s.get("name") for s in tools.SPECS}
        self.assertIn("find_looks", names)
        spec = [s for s in tools.SPECS if s.get("name") == "propose_fit"][0]["parameters"]
        for k in ("occasion", "ref_url"):
            self.assertIn(k, spec["required"])
        self.assertIn("find_looks 먼저", orchestrator.INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
