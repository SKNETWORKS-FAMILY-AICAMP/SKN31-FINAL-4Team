"""'물어보기' 카드로 넘어가는 상품 초안 경로.

링크만 친 질문에서 상품명 칸에 주소가 그대로 들어가던 자리다(2026-09-11).
모델이 확인한 것을 도구 인자로 받아, 그것만 화면으로 넘어가는지 본다.
상품 링크는 전용 도구 한 번으로 세 필드를 함께 확인한다.
"""
import sys
import os
import unittest
from unittest.mock import Mock, patch

sys.modules.setdefault("requests", Mock())

import server
from app import agent_path, plans, tools


class _Trace:
    def __init__(self, calls):
        self.calls = calls
        self.missing = []


class ItemDraftArgTests(unittest.TestCase):
    def test_records_only_confirmed_fields(self):
        draft = tools._item_draft("벌룬 카고 미디 스커트", "허그유어스킨", "89,000원")
        self.assertEqual(draft["name"], "벌룬 카고 미디 스커트")
        self.assertEqual(draft["brand"], "허그유어스킨")
        self.assertEqual(draft["price"], 89000)

    def test_unconfirmed_fields_stay_empty(self):
        draft = tools._item_draft("카고 팬츠", None, None)
        self.assertIsNone(draft["brand"])
        self.assertIsNone(draft["price"])
        self.assertEqual(draft["recorded"], ["name"])

    def test_nothing_confirmed_is_no_draft(self):
        self.assertIsNone(tools._item_draft(None, None, None))

    def test_index_tool_takes_the_identity_in_the_same_call(self):
        spec = [s for s in tools.SPECS if s.get("name") == "get_salmal_index"][0]
        props = set(spec["parameters"]["properties"])
        self.assertEqual(props, {"term", "item_name", "brand", "price", "style_tags"})
        # 초안 전용 도구를 따로 두지 않는다 — 바퀴를 하나 더 쓴다.
        self.assertNotIn("record_item_identity", {s.get("name") for s in tools.SPECS})

    def test_product_link_tool_collects_brand_and_price_together(self):
        spec = [s for s in tools.SPECS if s.get("name") == "inspect_product_link"][0]
        self.assertEqual(set(spec["parameters"]["properties"]), {"url"})


class PublicBetaTests(unittest.TestCase):
    def test_public_beta_unlocks_the_full_chat_plan(self):
        with patch.object(plans, "PUBLIC_BETA", True):
            self.assertEqual(plans.effective(plans.FREE), plans.BUSINESS)

    def test_public_beta_keeps_the_shared_token(self):
        # 2026-09-23 — 베타는 플랜만 연다. 토큰까지 풀면 주소만 알아도 누구나
        # 챗봇(=OpenAI 비용)을 부를 수 있다.
        with patch.object(plans, "PUBLIC_BETA", True), \
             patch.dict(os.environ, {"FEEDIT_CHAT_TOKEN": "team-token"}):
            self.assertEqual(server._chat_token(), "team-token")

    def test_token_compare_is_exact(self):
        with patch.object(server, "CHAT_TOKEN", "team-token"):
            self.assertTrue(server._token_ok("team-token"))
            self.assertFalse(server._token_ok("team-toke"))
            self.assertFalse(server._token_ok(""))
            self.assertFalse(server._token_ok(None))
            self.assertFalse(server._token_ok("팀토큰"))   # ASCII 밖 글자도 500 이 아니라 거절

    def test_turning_beta_off_restores_plan_and_token_rules(self):
        with patch.object(plans, "PUBLIC_BETA", False), \
             patch.dict(os.environ, {"FEEDIT_CHAT_TOKEN": "private-token"}):
            self.assertEqual(plans.effective(plans.FREE), plans.FREE)
            self.assertEqual(server._chat_token(), "private-token")


class DraftHandoffTests(unittest.TestCase):
    def test_draft_comes_from_the_tool_not_from_the_answer(self):
        trace = _Trace([
            {"tool": "web_search", "args": {}, "result": {"answer": "허그유어스킨 스커트"}},
            {"tool": "get_salmal_index", "args": {}, "result": {
                "score": None,
                "item_draft": {"name": "벌룬 카고 미디 스커트", "brand": "허그유어스킨",
                               "price": 89000, "recorded": ["name", "brand", "price"]}}},
        ])
        draft = agent_path._item_draft(trace)
        self.assertEqual(draft["title"], "벌룬 카고 미디 스커트")
        self.assertEqual(draft["brand"], "허그유어스킨")
        self.assertEqual(draft["price"], 89000)

    def test_falls_back_to_the_name_the_bot_actually_searched(self):
        trace = _Trace([
            {"tool": "search_terms", "args": {"q": "아디다스 럭비 폴로 셔츠"}, "result": {}},
            {"tool": "get_salmal_index", "args": {}, "result": {"score": None}},
        ])
        draft = agent_path._item_draft(trace)
        self.assertEqual(draft["title"], "아디다스 럭비 폴로 셔츠")

    def test_a_link_never_becomes_the_product_name(self):
        trace = _Trace([{"tool": "search_terms",
                         "args": {"q": "https://www.musinsa.com/products/6719206"},
                         "result": {}}])
        self.assertIsNone(agent_path._item_draft(trace))

    def test_link_inspection_becomes_the_confirmed_draft(self):
        trace = _Trace([{"tool": "inspect_product_link", "args": {"url": "https://shop.test/p/1"},
                         "result": {"found": True, "item_name": "트랙 재킷",
                                    "brand": "아디다스", "price_krw": 129000}}])
        draft = agent_path._item_draft(trace)
        # 2026-09-21 — 살!말? 카드에 상품 사진을 싣는다(0479ac4). 링크가 사진을 못 주면 빈 칸이다.
        self.assertEqual(draft, {"title": "트랙 재킷", "brand": "아디다스",
                                 "price": 129000, "image": "", "source": "상품 링크에서 확인한 값"})

    def test_link_inspection_carries_the_product_image(self):
        trace = _Trace([{"tool": "inspect_product_link", "args": {"url": "https://shop.test/p/1"},
                         "result": {"found": True, "item_name": "트랙 재킷", "brand": "아디다스",
                                    "price_krw": 129000, "image_url": "https://img.test/1.jpg"}}])
        self.assertEqual(agent_path._item_draft(trace)["image"], "https://img.test/1.jpg")

    def test_no_lookup_means_no_draft(self):
        self.assertIsNone(agent_path._item_draft(_Trace([
            {"tool": "get_metric", "args": {}, "result": {"term": "카고"}}])))

    def test_community_action_carries_the_draft(self):
        acts = server.actions_for(
            {"question": "이 스커트 사도 될까?", "intent": "buy.verdict",
             "terms": [], "item_draft": {"title": "벌룬 카고 미디 스커트",
                                         "brand": "허그유어스킨", "price": 89000,
                                         "source": "챗봇이 확인한 값"}},
            mode="salmal")
        community = [a for a in acts if a.get("type") == "community"][0]
        self.assertEqual(community["draft"]["brand"], "허그유어스킨")
        self.assertEqual(community["draft"]["price"], 89000)

    def test_salmal_actions_do_not_appear_without_relevant_context(self):
        acts = server.actions_for(
            {"question": "소재는 뭐야?", "intent": "agent", "terms": []},
            mode="salmal")
        self.assertEqual(acts, [])

    def test_explicit_opinion_request_gets_a_plain_community_action(self):
        acts = server.actions_for(
            {"question": "다른 사람들 의견도 궁금해", "intent": "buy.opinion",
             "terms": []}, mode="salmal")
        community = [a for a in acts if a.get("type") == "community"][0]
        self.assertNotIn("draft", community)

    def test_photo_purchase_gets_tryon_but_not_unrelated_buttons(self):
        acts = server.actions_for(
            {"question": "이거 사도 될까?", "intent": "vision.salmal", "terms": [],
             "visual_context": {"item": "미디 스커트"}}, mode="salmal")
        self.assertEqual([a["type"] for a in acts], ["virtual_fit"])

    def test_general_actions_follow_the_answer_intent(self):
        term = {"canonical": "발레코어", "facet": "style", "available": True}
        style = server.actions_for(
            {"question": "발레코어 뜻이 뭐야?", "intent": "agent",
             "terms": [term]}, mode="general")
        trend = server.actions_for(
            {"question": "발레코어 요즘 유효해?", "intent": "metric.level",
             "terms": [term]}, mode="general")
        self.assertEqual([a["type"] for a in style], ["view"])
        self.assertEqual(style[0]["view"], "style")
        self.assertEqual([a["view"] for a in trend], ["trend"])


class TasteContextTests(unittest.TestCase):
    def test_style_profiles_survive_sanitizing(self):
        out = server.clean_taste_context({
            "favorite_styles": ["스케이터"],
            "favorite_style_profiles": [{"name": "스케이터", "keywords": ["카고", "오버핏"]}],
            "user_id": "몰래 끼워 넣은 값",
        })
        self.assertEqual(out["favorite_style_profiles"],
                         [{"name": "스케이터", "keywords": ["카고", "오버핏"]}])
        self.assertNotIn("user_id", out)


if __name__ == "__main__":
    unittest.main()
