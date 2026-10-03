"""코디 인계 — 도구 목록 관문 · 연출 검수 · 상품 고르기 · 사진 주소.

설계서 '코디 인계(Fit Handoff)' 장의 확정 사항을 코드로 묶어 둔다.
"""
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.modules.setdefault("requests", Mock())
sys.modules.setdefault("psycopg", Mock())
sys.modules.setdefault("psycopg.rows", Mock(dict_row=None))

from app import adapters, agent_path, fit, tools, vton


class ToolGateTests(unittest.TestCase):
    """VTON 은 살!말? 의 고유 기능이다 — 프롬프트가 아니라 도구 목록이 지킨다."""

    def names(self, ctx):
        return [s.get("name") for s in tools.specs_for(ctx)]

    def test_general_mode_has_no_build_fit(self):
        got = self.names({"mode": "general"})
        self.assertIn("propose_fit", got)        # 제안까지는 한다
        self.assertNotIn("build_fit", got)       # 입히지는 못한다

    def test_salmal_needs_approved_proposal(self):
        # 승인을 거치지 않은 살말 턴에는 확정할 코디가 없다.
        self.assertNotIn("build_fit", self.names({"mode": "salmal"}))
        self.assertIn("build_fit", self.names(
            {"mode": "salmal", "fit_proposal": {"items": [{"slot": "상의"}]}}))


class PruneOptionTests(unittest.TestCase):
    """아이템과 맞지 않는 연출은 뗀다. 다만 조용히 버리지 않는다."""

    def test_pullover_drops_top_open_with_reason(self):
        items = [{"slot": "상의", "name": "빈티지 스웨트셔츠"}]
        seen = [{"slot": "상의", "closure": "없음", "openable": "no", "layer": "보통"}]
        on, dropped = fit.prune_options({"top_open": True}, items, seen)
        self.assertFalse(on.get("top_open"))
        self.assertTrue(any("여밈이 없어" in d for d in dropped))

    def test_unknown_keeps_option_and_says_so(self):
        # ★ 모르면 빼지도 넣지도 않는다. 확인하지 못한 것을 근거로 지시를 지우면
        #   사용자가 켠 연출이 이유 없이 사라진다.
        items = [{"slot": "상의", "name": "트랙탑"}]
        seen = [{"slot": "상의", "closure": "모르겠음", "openable": "unknown",
                 "layer": "모르겠음"}]
        on, dropped = fit.prune_options({"top_open": True}, items, seen)
        self.assertTrue(on.get("top_open"))
        self.assertTrue(any("확인하지 못했" in d for d in dropped))

    def test_layered_needs_two_outers(self):
        items = [{"slot": "아우터", "name": "코치 재킷"}]
        on, dropped = fit.prune_options({"outer_layered": True}, items, [])
        self.assertFalse(on.get("outer_layered"))
        self.assertTrue(any("아우터가 한 벌" in d for d in dropped))

    def test_conflict_drops_both(self):
        items = [{"slot": "아우터", "name": "트랙 재킷"}]
        seen = [{"slot": "아우터", "closure": "지퍼", "openable": "yes", "layer": "얇음"}]
        on, dropped = fit.prune_options({"outer_open": True, "outer_closed": True},
                                        items, seen)
        self.assertFalse(on.get("outer_open"))
        self.assertFalse(on.get("outer_closed"))
        self.assertTrue(any("둘 다" in d for d in dropped))

    def test_layer_order_puts_thin_first(self):
        items = [{"slot": "아우터", "name": "패딩"}, {"slot": "아우터", "name": "트랙 재킷"}]
        seen = [{"slot": "아우터", "layer": "두꺼움"}, {"slot": "아우터", "layer": "얇음"}]
        ordered = fit.layer_order(items, seen)
        self.assertEqual(ordered[0]["name"], "트랙 재킷")


class ProposeTests(unittest.TestCase):
    """사진 없는 상품은 코디에 담지 않는다 — 입힐 수 없는 것을 승인 카드에 올리면
    사용자는 눌러 보고 나서야 안다."""

    class FakeMarket:
        def __init__(self, rows):
            self.rows, self.asked = rows, []

        def products(self, sel, limit=3):
            self.asked.append(sel)
            return self.rows.get(sel.get("kind"), [])

    def test_skips_items_without_photo(self):
        market = self.FakeMarket({
            "티셔츠": [{"name": "사진 없는 상의", "image": ""},
                       {"name": "트랙탑", "image": "https://image.msscdn.net/a.jpg"}],
            "팬츠": [{"name": "배럴레그 팬츠", "image": "https://image.msscdn.net/b.jpg"}],
            "스니커즈": [],
        })
        got = fit.propose(market, ["블록코어"], ["상의", "하의", "신발"])
        names = [i["name"] for i in got["items"]]
        self.assertEqual(names, ["트랙탑", "배럴레그 팬츠"])
        # 못 채운 칸은 숨기지 않는다
        self.assertEqual(got["missing_slots"], ["신발"])
        # 어느 태그로 골랐는지 남는다 — "왜 이걸 골랐나" 를 말할 수 있어야 한다
        self.assertEqual(got["items"][0]["style"], "블록코어")

    def test_no_style_is_not_guessed(self):
        got = fit.propose(self.FakeMarket({}), [], None)
        self.assertIn("unavailable", got)

    def test_gender_is_sent_to_product_search(self):
        market = self.FakeMarket({"티셔츠": [{"name": "공용 상의",
                                             "image": "https://image.msscdn.net/a.jpg"}]})
        got = fit.propose(market, ["블록코어"], ["상의"], gender="FEMALE")
        self.assertEqual(got["items"][0]["name"], "공용 상의")
        self.assertEqual(market.asked[0]["gender"], "FEMALE")
        self.assertEqual(got["gender"], "FEMALE")
        market.asked.clear()
        fit.propose(market, ["블록코어"], ["상의"], gender="INVALID")
        self.assertNotIn("gender", market.asked[0])

    def test_same_slot_twice_is_kept(self):
        # '아우터' 둘이 레이어드의 조건이다 — 중복을 막으면 레이어드를 만들 수 없다.
        self.assertEqual(fit._normalize_slots(["아우터", "아우터"]), ["아우터", "아우터"])
        self.assertEqual(fit._normalize_slots(["없는칸"]), fit.DEFAULT_SLOTS)

    def test_approved_item_keeps_shop_provenance(self):
        proposal = fit.clean_proposal({"gender": "FEMALE", "items": [{
            "slot": "상의", "image": "https://image.msscdn.net/a.jpg",
            "name": "트랙 재킷", "brand": "아디다스", "source": "MUSINSA",
            "source_label": "무신사", "url": "https://www.musinsa.com/products/123",
        }]})
        self.assertEqual(proposal["items"][0]["source_label"], "무신사")
        self.assertEqual(proposal["items"][0]["url"], "https://www.musinsa.com/products/123")
        self.assertEqual(proposal["gender"], "FEMALE")
        self.assertEqual(adapters._sel({"style": "블록코어", "gender": "FEMALE"})["gender"],
                         "FEMALE")
        trace = Mock(calls=[{"tool": "propose_fit", "result": {
            **proposal, "gender": "FEMALE"}}])
        card = agent_path._fit(trace, "propose_fit")
        self.assertEqual(card["items"][0]["url"], proposal["items"][0]["url"])
        self.assertEqual(card["gender"], "FEMALE")


class RememberedStyleTests(unittest.TestCase):
    """"위 스타일대로 입혀 줘" 에 되묻지 않는다 — 대화가 기억한다."""

    def styles(self, history, ctx=None):
        from app import orchestrator
        return orchestrator._recent_styles(history, ctx or {})

    def test_looked_up_styles_come_first_newest_first(self):
        history = [
            {"q": "발레코어 어때?", "terms": [{"canonical": "발레코어", "facet": "style"}]},
            {"q": "가을 스타일 추천해줘",
             "terms": [{"canonical": "빈티지", "facet": "style"},
                       {"canonical": "카디건", "facet": "item"}]},   # 스타일만 본다
        ]
        self.assertEqual(self.styles(history), ["빈티지", "발레코어"])

    def test_falls_back_to_taste_and_never_empties_on_purpose(self):
        ctx = {"taste_context": {"favorite_styles": ["고프코어", "블록코어"]}}
        # 조회한 스타일이 없으면 즐겨입는 스타일로 떨어진다
        self.assertEqual(self.styles([], ctx), ["고프코어", "블록코어"])
        # 둘 다 없으면 빈 목록 — 도구는 되묻지 않고 못 고른다고 말한다
        self.assertEqual(self.styles([], {}), [])

    def test_propose_fit_uses_remembered_styles_without_args(self):
        market = ProposeTests.FakeMarket({
            "티셔츠": [{"name": "트랙탑", "image": "https://image.msscdn.net/a.jpg"}],
            "팬츠": [], "스니커즈": [],
        })
        box = tools.Toolbox(Mock(), Mock(), ctx={"recent_styles": ["블록코어"]},
                            market=market)
        got = box.t_propose_fit(styles=[], slots=["상의"], kinds=[], options=[], why="")
        self.assertEqual(got["items"][0]["style"], "블록코어")
        self.assertEqual(got["styles_from"], "대화")     # 무엇을 기준으로 골랐나

    def test_profile_gender_is_the_default_and_wearer_overrides_it(self):
        # 2026-10-02 — "여자친구랑 데이트할 때 뭐 입지?" 는 본인(남자)이 입을 옷이다.
        #   질문 글자가 아니라 회원정보 성별이 기본이고, 다른 사람의 옷이라고 분명히
        #   말했을 때만 모델이 wearer 로 바꾼다.
        rows = {"티셔츠": [{"name": "셔츠", "image": "https://image.msscdn.net/a.jpg"}]}
        market = ProposeTests.FakeMarket(rows)
        box = tools.Toolbox(Mock(), Mock(), ctx={"recent_styles": ["클래식"], "gender": "MALE"},
                            market=market)
        got = box.t_propose_fit(styles=[], slots=["상의"], kinds=[], options=[], why="",
                                wearer="self")
        self.assertEqual(market.asked[0]["gender"], "MALE")
        self.assertEqual(got["gender"], "MALE")
        market.asked.clear()
        got = box.t_propose_fit(styles=[], slots=["상의"], kinds=[], options=[], why="",
                                wearer="FEMALE")                     # 여자친구 선물
        self.assertEqual(market.asked[0]["gender"], "FEMALE")
        self.assertEqual(got["gender"], "FEMALE")
        # 회원정보에 성별이 없으면 거르지 않는다(추측하지 않는다)
        market = ProposeTests.FakeMarket(rows)
        box = tools.Toolbox(Mock(), Mock(), ctx={"recent_styles": ["클래식"]}, market=market)
        box.t_propose_fit(styles=[], slots=["상의"], kinds=[], options=[], why="", wearer="self")
        self.assertNotIn("gender", market.asked[0])

    def test_propose_fit_spec_requires_wearer(self):
        spec = [s for s in tools.SPECS if s.get("name") == "propose_fit"][0]
        self.assertIn("wearer", spec["parameters"]["required"])
        self.assertEqual(spec["parameters"]["properties"]["wearer"]["enum"],
                         ["self", "FEMALE", "MALE"])

    def test_asked_item_words_are_used_before_the_default_table(self):
        market = ProposeTests.FakeMarket({
            "트랙 재킷": [{"name": "아디다스 트랙 재킷",
                           "image": "https://image.msscdn.net/t.jpg"}],
            "재킷": [{"name": "아무 재킷", "image": "https://image.msscdn.net/x.jpg"}],
        })
        got = fit.propose(market, ["블록코어"], ["아우터"], ["트랙 재킷"])
        self.assertEqual(got["items"][0]["name"], "아디다스 트랙 재킷")
        self.assertEqual(got["items"][0]["kind"], "트랙 재킷")


class RelativeImageTests(unittest.TestCase):
    """DB 실측 — thumbnail_url 27,424건이 호스트 없는 무신사 상대 경로다."""

    def test_musinsa_relative_path_becomes_absolute(self):
        got = fit.absolute_image("thumbnails/images/goods_img/20260806/7011611/x_big.jpg",
                                 "MUSINSA")
        self.assertEqual(got, "https://image.msscdn.net/thumbnails/images/"
                              "goods_img/20260806/7011611/x_big.jpg")

    def test_source_is_inferred_from_the_path_shape(self):
        # 소스 코드가 비어 와도 goods_img 는 무신사 경로다.
        self.assertTrue(fit.absolute_image("images/goods_img/a/b.jpg", "")
                        .startswith("https://image.msscdn.net/"))

    def test_unknown_shape_is_not_guessed(self):
        # ★ 모르는 모양에 아무 호스트나 붙이지 않는다 — 엉뚱한 사진을 입히게 된다.
        self.assertEqual(fit.absolute_image("uploads/2026/unknown.jpg", ""), "")
        self.assertEqual(fit.absolute_image("", "MUSINSA"), "")

    def test_absolute_urls_pass_through(self):
        for url in ("https://cf.product-image.s3.zigzag.kr/a.jpg",
                    "https://kream-phinf.pstatic.net/b.jpg",
                    "https://d3ha2047wt6x28.cloudfront.net/c.jpg"):
            self.assertEqual(fit.absolute_image(url, ""), url)
            # 실측 호스트 넷은 그대로 받을 수 있어야 한다
            self.assertTrue(vton.image_host_allowed(url), url)

    def test_relative_path_products_are_offered(self):
        market = ProposeTests.FakeMarket({
            "티셔츠": [{"name": "트랙탑", "source": "MUSINSA",
                        "image": "thumbnails/images/goods_img/20260806/1/x.jpg"}],
            "팬츠": [], "스니커즈": [],
        })
        got = fit.propose(market, ["블록코어"], ["상의", "하의", "신발"])
        self.assertTrue(got["items"][0]["image"].startswith("https://image.msscdn.net/"))


class ImageHostTests(unittest.TestCase):
    """상품 사진은 서버가 받는다. 다만 아무 주소나 대신 받아 주지 않는다."""

    def test_unknown_host_is_refused_with_host_in_message(self):
        with self.assertRaises(ValueError) as caught:
            vton.fetch_as_data_url("https://evil.example.com/a.jpg")
        self.assertIn("evil.example.com", str(caught.exception))

    def test_items_accept_image_url(self):
        with patch("app.vton.fetch_as_data_url",
                   return_value="data:image/png;base64,eA==") as fetch:
            rows = vton._items([{"image_url": "https://image.msscdn.net/a.jpg",
                                 "category": "상의"}], None, None)
        fetch.assert_called_once()
        self.assertEqual(rows[0]["category"], "상의")
        self.assertTrue(rows[0]["image"].startswith("data:image/png"))


if __name__ == "__main__":
    unittest.main()
