"""'입혀 줘' 가 "태그된 상품이 없다" 로 끝나던 자리 (2026-10-01 실측).

    사용자  이번에 지인 결혼식이 있는데 하객룩 추천해줘 → 그럼 예시로 입혀봐줄 수 있을까?
    챗봇    지금은 '결혼식 하객' 태그가 붙은 사진 상품을 찾지 못해서 …
    사용자  그러면 긱시크룩으로 한번 입혀봐줄래?
    챗봇    긱시크룩 태그 상품은 현재 사진이 있는 상의·하의·신발 조합을 찾지 못했어요.
    사용자  그러면 지금 입혀볼 수 있는 태깅되어있는 스타일이 뭐가 있어?
    챗봇    입혀보기용으로 태깅된 스타일 목록이 확인되지 않았어요. (스타일 축 반환 없음)

  상품이 없던 게 아니다. 운영 /api/products 실측:
      style=긱시크룩 → 0건      style=긱시크 → 상의·하의·신발 모두 있음
      style=클래식 + 블라우스·슬랙스·로퍼 → 세 칸 모두 있음
  ① 모델이 사용자의 말("긱시크룩", "결혼식 하객")을 그대로 상품 태그 이름으로 썼다.
     하객은 스타일이 아니라 착용 상황(TPO)이다.
  ② "입혀볼 수 있는 스타일" 을 답할 도구가 없어 트렌드 순위(rank_terms)를 뒤졌다.
     순위는 그날 언급된 용어만 있어 스타일 축이 비어 있었다.
  ③ 지그재그 사진 호스트(cf.product-image.s.zigzag.kr)가 허용 목록에 없어 코디에서 빠졌다.

돌리는 법:  PYTHONPATH=ChatBot python -m unittest ChatBot/tests/test_fit_style_names.py
"""
import sys
import unittest
from unittest.mock import Mock, patch

sys.modules.setdefault("requests", Mock())
sys.modules.setdefault("psycopg", Mock())
sys.modules.setdefault("psycopg.rows", Mock(dict_row=None))

from app import adapters, agent_path, fit, tools, vton
from app.lexicon_gate import LexiconGate

# 운영 /api/facets 의 스타일 칸 (2026-10-01) — 핵심 스타일과 태그가 달린 판매 중 상품 수
FACET_STYLES = [{"label": "클래식", "count": 1069, "core": True},
                {"label": "페미닌", "count": 956, "core": True},
                {"label": "고프코어", "count": 240, "core": True},
                {"label": "바이크코어", "count": 0, "core": True}]


class Store:
    """저장소 대신 저장소에 들어 있는 사전(vendor lexicon)을 그대로 쓴다."""

    def metric_canonicals(self):
        return set()


def gate():
    return LexiconGate(Store())


class Market:
    """운영 /api/products 를 흉내 낸다 — (스타일, 아이템) 이 정확히 맞아야 걸린다."""

    def __init__(self, rows=None, styles=None):
        self.rows = rows or {}
        self.asked = []
        self._styles = FACET_STYLES if styles is None else styles

    def products(self, sel, limit=3):
        self.asked.append(dict(sel))
        return self.rows.get((sel.get("style"), sel.get("kind")), [])

    def styles(self):
        return [{"style": r["label"], "products": r["count"]}
                for r in self._styles if r["count"]]


def img(name):
    return {"name": name, "image": f"https://image.msscdn.net/{name}.jpg", "source": "MUSINSA"}


class ResolveStyleTests(unittest.TestCase):
    def test_look_suffix_resolves_to_the_tag_name(self):
        self.assertEqual(fit.resolve_styles(["긱시크룩"], gate()), (["긱시크"], []))
        self.assertEqual(fit.resolve_styles(["고프코어 룩", "꾸안꾸"], gate())[0],
                         ["고프코어", "놈코어"])

    def test_tpo_is_not_a_style(self):
        styles, skipped = fit.resolve_styles(["결혼식 하객"], gate())
        self.assertEqual(styles, [])
        self.assertEqual(skipped[0]["facet"], "tpo")
        self.assertIn("TPO", skipped[0]["reason"])

    def test_mixed_names_keep_the_style_and_say_what_was_dropped(self):
        styles, skipped = fit.resolve_styles(["결혼식 하객", "미니멀룩"], gate())
        self.assertEqual(styles, ["미니멀"])
        self.assertEqual([s["name"] for s in skipped], ["결혼식 하객"])

    def test_names_are_kept_when_the_dictionary_cannot_be_read(self):
        broken = Mock()
        broken.parse.side_effect = RuntimeError("down")
        self.assertEqual(fit.resolve_styles(["블록코어"], broken), (["블록코어"], []))


class ProposeFitTests(unittest.TestCase):
    def box(self, market, ctx=None):
        return tools.Toolbox(Mock(), gate(), ctx=ctx or {}, market=market)

    def test_geek_chic_look_finds_a_full_outfit(self):
        market = Market({("긱시크", "티셔츠"): [img("홀터 레이어드 긴팔")],
                         ("긱시크", "팬츠"): [img("록 링크 팬츠")],
                         ("긱시크", "스니커즈"): [img("샥스 칼리스트라")]})
        got = self.box(market).t_propose_fit(styles=["긱시크룩"], slots=[], kinds=[],
                                             options=[], why="")
        self.assertTrue(got.get("proposed"), got)
        self.assertEqual([i["slot"] for i in got["items"]], ["상의", "하의", "신발"])
        self.assertEqual(got["styles"], ["긱시크"])
        # 사용자 말 그대로("긱시크룩")로는 한 번도 찾지 않는다
        self.assertNotIn("긱시크룩", {a.get("style") for a in market.asked})

    def test_wedding_guest_returns_choices_instead_of_a_dead_end(self):
        market = Market()
        got = self.box(market, {"recent_styles": ["고프코어"]}).t_propose_fit(
            styles=["결혼식 하객"], slots=[], kinds=["블라우스", "슬랙스", "로퍼"],
            options=[], why="")
        self.assertIn("unavailable", got)
        self.assertEqual(got["skipped"][0]["facet"], "tpo")
        # 고를 수 있는 스타일과 다음 행동이 함께 간다. 0건 스타일은 빠진다.
        self.assertEqual([r["style"] for r in got["available_styles"]],
                         ["클래식", "페미닌", "고프코어"])
        self.assertIn("한 번 더", got["next"])
        # 즐겨입는 스타일(고프코어)로 몰래 바꿔 찾지 않았다 — 하객룩에 고프코어는 엉뚱하다
        self.assertEqual(market.asked, [])

    def test_second_call_with_a_listed_style_becomes_the_proposal(self):
        market = Market({("클래식", "블라우스"): [img("베이직 셔츠")],
                         ("클래식", "슬랙스"): [img("부츠컷 슬랙스")],
                         ("클래식", "로퍼"): [img("플랫폼 로퍼")]})
        box = self.box(market)
        box.run("propose_fit", {"styles": ["결혼식 하객"], "slots": [],
                                "kinds": ["블라우스", "슬랙스", "로퍼"], "options": [], "why": ""})
        box.run("propose_fit", {"styles": ["클래식"], "slots": [],
                                "kinds": ["블라우스", "슬랙스", "로퍼"], "options": [],
                                "why": "하객룩은 단정한 클래식이 맞다"})
        proposal = agent_path._fit(box.trace, "propose_fit")
        self.assertEqual([i["name"] for i in proposal["items"]],
                         ["베이직 셔츠", "부츠컷 슬랙스", "플랫폼 로퍼"])

    def test_empty_shelf_also_brings_the_choices(self):
        got = self.box(Market()).t_propose_fit(styles=["긱시크"], slots=[], kinds=[],
                                               options=[], why="")
        self.assertIn("unavailable", got)
        self.assertTrue(got["available_styles"])

    def test_market_without_style_list_still_answers(self):
        class Old(Market):
            styles = None
        got = self.box(Old()).t_propose_fit(styles=["결혼식 하객"], slots=[], kinds=[],
                                            options=[], why="")
        self.assertIn("unavailable", got)
        self.assertNotIn("available_styles", got)


class FitStylesToolTests(unittest.TestCase):
    def test_lists_tagged_styles_with_counts(self):
        box = tools.Toolbox(Mock(), Mock(), market=Market())
        got = box.t_fit_styles()
        self.assertEqual(got["styles"][0], {"style": "클래식", "products": 1069})
        self.assertNotIn("바이크코어", [r["style"] for r in got["styles"]])

    def test_unavailable_when_the_list_cannot_be_read(self):
        box = tools.Toolbox(Mock(), Mock(), market=Market(styles=[]))
        self.assertIn("unavailable", box.t_fit_styles())

    def test_offered_in_both_modes(self):
        for mode in ("general", "salmal"):
            names = [s.get("name") for s in tools.specs_for({"mode": mode})]
            self.assertIn("fit_styles", names, mode)

    def test_progress_line(self):
        self.assertEqual(tools.progress_say("fit_styles", {}), "입혀볼 수 있는 스타일 보는 중")


class MarketStylesAdapterTests(unittest.TestCase):
    def setUp(self):
        adapters.MarketHTTPAdapter._styles_cache.clear()

    def test_reads_the_facets_style_column(self):
        m = adapters.MarketHTTPAdapter(base="http://api.test")
        with patch.object(m, "_get", return_value={"style": FACET_STYLES}) as get:
            rows = m.styles()
            again = m.styles()
        self.assertEqual(rows[0], {"style": "클래식", "products": 1069})
        self.assertEqual(again, rows)
        get.assert_called_once_with("facets", {"limit": 1})     # 10분 동안 다시 묻지 않는다

    def test_style_list_does_not_wait_the_full_default_timeout(self):
        # 운영 facets 는 캐시 없이 3~5초 — 기본 8초를 다 기다리면 코디 한 바퀴가 밀린다
        m = adapters.MarketHTTPAdapter(base="http://api.slow")
        seen = []
        with patch.object(m, "_get", side_effect=lambda *a: seen.append(m.timeout) or {"style": []}):
            m.styles()
        self.assertEqual(seen, [adapters.FACETS_TIMEOUT])
        self.assertEqual(m.timeout, 8.0)                         # 끝나면 되돌린다

    def test_failure_is_an_empty_list(self):
        m = adapters.MarketHTTPAdapter(base="http://api.down")
        with patch.object(m, "_get", return_value={"unavailable": "x"}):
            self.assertEqual(m.styles(), [])


class ZigzagHostTests(unittest.TestCase):
    def test_both_zigzag_hosts_are_allowed(self):
        for url in ("https://cf.product-image.s.zigzag.kr/original/d/2026/9/15/a.jpeg",
                    "https://cf.product-image.s3.zigzag.kr/a.jpg"):
            self.assertTrue(vton.image_host_allowed(url), url)


if __name__ == "__main__":
    unittest.main()
