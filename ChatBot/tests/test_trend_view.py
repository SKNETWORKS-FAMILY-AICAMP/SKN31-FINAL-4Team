"""챗봇 지표 = 트렌드 분석 화면 지표 (2026-10-01).

★ 무엇을 보나
  챗봇이 화면과 다른 판단을 하던 문제를 고쳤다(app/trend_view.py 머리말).
  여기 기대값은 짐작이 아니라 **화면 코드가 실제로 그린 값**이다.

  fixtures_trend_api.json — 2026-10-01 09:3x KST 운영 /api/trend · /api/sentiment 응답
    (아디다스 · 트랙탑 · 팬츠 · 고프코어, 시계열은 마지막 40일만 남김. 요약에 쓰는 창은 최대 30일).
  그 JSON 을 frontend 의 dispatch.js 그대로 jsdom 에 그려서 읽은 숫자가 아래 PAGE 다.
    · 언급량·온도 탭: 다이얼 · 제목 판정 · 막대 구간 · 이번 주 온도 변화 · 화제성 레벨 · 성장 모멘텀 · 플랫폼 표
    · 긍부정 탭: 다이얼 · 판정 · 긍정/부정 비율 · 총 반응 수 · 최다 긍정/부정 신호 · 신호 6칸 · 주별 원형
  아디다스는 같은 날 운영 화면 캡처(온도 83° · +18° · 89 · 75, 긍부정 91 · 34% · 3% · 29건)와도 같다.

  화면 규칙이 바뀌면 이 표부터 다시 뽑는다 — 맞추지 않은 채 숫자만 고치지 않는다.

돌리는 법:  PYTHONPATH=ChatBot python -m unittest ChatBot/tests/test_trend_view.py
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from app import blocks, report, trend_view
from app.config import temp_band
from app.tools import Toolbox, _say_rule

FX = json.loads((Path(__file__).parent / "fixtures_trend_api.json").read_text(encoding="utf-8"))

# dispatch.js 가 같은 JSON 으로 그린 값 (jsdom, origin/main b36f52a)
PAGE = {
    "아디다스": {"temp": 83, "verdict": "뜨거움", "band": "따뜻함", "wk": 18, "level": 89, "momentum": 75,
              "plats": [("크림", 78), ("무신사", 70), ("지그재그", 64)],
              "dial": 91, "sverdict": "강한 구매 신호", "pos": 34, "neg": 3, "total": 29,
              "top_pos": ("호평", 8), "top_neg": ("비판", 1),
              "sig": {"질문": 11, "구매": 4, "경험": 4, "호평": 8, "비판": 1, "잡담": 1},
              "week": (4, 6, 0)},
    "트랙탑": {"temp": 51, "verdict": "달아오르는 중", "band": "미지근", "wk": -1, "level": 18, "momentum": 100,
             "plats": [("무신사", 100), ("YouTube", 51)],
             "dial": 50, "sverdict": "판단 보류", "pos": 13, "neg": 13, "total": 8,
             "top_pos": ("경험", 4), "top_neg": None,
             "sig": {"질문": 3, "구매": 0, "경험": 4, "호평": 0, "비판": 0, "잡담": 1},
             "week": (0, 3, 1)},
    "팬츠": {"temp": 70, "verdict": "뜨거움", "band": "따뜻함", "wk": -17, "level": 73, "momentum": 65,
            "plats": [("에이블리", 76), ("YouTube", 69), ("무신사", 62)],
            "dial": 86, "sverdict": "강한 구매 신호", "pos": 37, "neg": 6, "total": 540,
            "top_pos": ("호평", 108), "top_neg": ("비판", 23),
            "sig": {"질문": 239, "구매": 66, "경험": 80, "호평": 108, "비판": 23, "잡담": 24},
            "week": (34, 68, 9)},
    "고프코어": {"temp": 53, "verdict": "달아오르는 중", "band": "미지근", "wk": 4, "level": 22, "momentum": 100,
              "plats": [("YouTube", 48)],
              "dial": 100, "sverdict": "판단 보류", "pos": 93, "neg": 0, "total": 15,
              "top_pos": ("호평", 8), "top_neg": None,
              "sig": {"질문": 0, "구매": 1, "경험": 6, "호평": 8, "비판": 0, "잡담": 0},
              "week": (2, 1, 0)},
}


class FakeApi:
    """TrendHTTPAdapter 와 같은 모양. 무엇을 어떤 인자로 불렀는지 남긴다."""

    def __init__(self, down=False):
        self.down = down
        self.calls = []

    def trend(self, term):
        self.calls.append(("trend", term))
        if self.down:
            return {"status": "error", "reason": "트렌드 분석 데이터를 읽지 못했습니다 (ConnectionError)."}
        return FX[term]["trend"] if term in FX else {
            "status": "empty", "reason": f"‘{term}’ 을 사전에서 찾지 못했습니다."}

    def sentiment(self, term, brand=False):
        self.calls.append(("sentiment", term, brand))
        return FX[term]["sentiment"]

    def assoc(self, term):
        self.calls.append(("assoc", term))
        return {"status": "ok", "data": {"items": [{
            "term": "티셔츠", "facet": "ITEM", "facet_ko": "아이템",
            "cooccurrence": 49, "lift": 2.6, "score": 91,
            "change": "new",
        }]}}


class Gate:
    def facet_of(self, term):
        return {"트랙탑": "item", "팬츠": "item", "고프코어": "style"}.get(term)


class Store:
    """연관어·근거만 표를 읽는다. 온도·긍부정 자리를 부르면 시험이 깨지게 해 둔다."""

    def term_assoc(self, key, limit=8):
        return []

    def term_evidence(self, key, limit=3):
        return []

    def metric_facet(self, term):
        return "brand" if term == "아디다스" else None

    def __getattr__(self, name):          # term_latest · term_sentiment · obs_count …
        raise AssertionError(f"지표 표를 직접 읽으면 안 된다: store.{name}")


class PageParityTests(unittest.TestCase):
    def test_temperature_matches_the_page(self):
        for term, want in PAGE.items():
            with self.subTest(term=term):
                v = trend_view.term_view(term, Gate().facet_of(term), api=FakeApi())
                T = v["trend"]
                self.assertEqual((T["temp"], T["verdict"], T["band"]),
                                 (want["temp"], want["verdict"], want["band"]))
                self.assertEqual((T["delta_1w"], T["level"], T["momentum"]),
                                 (want["wk"], want["level"], want["momentum"]))
                self.assertEqual([(p["name"], p["temp"]) for p in v["platforms"]], want["plats"])

    def test_sentiment_matches_the_page(self):
        for term, want in PAGE.items():
            with self.subTest(term=term):
                S = trend_view.term_view(term, Gate().facet_of(term), api=FakeApi())["sentiment"]
                self.assertEqual((S["dial"], S["verdict"]), (want["dial"], want["sverdict"]))
                self.assertEqual((S["positive_pct"], S["negative_pct"], S["반응"]["합계"]),
                                 (want["pos"], want["neg"], want["total"]))
                top = S["top_positive_signal"]
                self.assertEqual((top["name"], top["count"]) if top else None, want["top_pos"])
                top = S["top_negative_signal"]
                self.assertEqual((top["name"], top["count"]) if top else None, want["top_neg"])
                self.assertEqual(S["signals"], want["sig"])
                w = S["windows"]["주별"]
                self.assertEqual((w["긍정"], w["중립"], w["부정"]), want["week"])

    def test_sentiment_is_a_28_day_total_not_one_day(self):
        """팬츠 마지막 하루는 2건이다. 챗봇이 '9월 29일 감성 표본 2건' 이라 말하던 자리."""
        last = FX["팬츠"]["sentiment"]["data"]["series"][-1]
        self.assertEqual(last["pos_n"] + last["neu_n"] + last["neg_n"], 12)
        trend_last = FX["팬츠"]["trend"]["data"]["series"][-1]
        self.assertEqual(trend_last["mention"], 2)
        S = trend_view.sentiment_summary(FX["팬츠"]["sentiment"]["data"])
        self.assertEqual(S["window_days"], 28)
        self.assertEqual(S["반응"]["합계"], 540)
        self.assertTrue(S["judged"])

    def test_brand_uses_brand_context_like_the_page(self):
        api = FakeApi()
        trend_view.term_view("아디다스", None, api=api)
        self.assertIn(("sentiment", "아디다스", True), api.calls)
        api = FakeApi()
        trend_view.term_view("팬츠", "item", api=api)
        self.assertIn(("sentiment", "팬츠", False), api.calls)

    def test_old_basis_is_disclosed_not_hidden(self):
        T = trend_view.term_view("아디다스", None, api=FakeApi())["trend"]
        self.assertEqual(T["as_of"], "2026-09-20")
        self.assertEqual(T["data_as_of"], "2026-09-29")
        self.assertEqual(T["mention_28d"], 0)
        self.assertTrue(any("2026-09-20" in n for n in T["notes"]))
        self.assertTrue(any("feedit-l2-v2" in n for n in T["notes"]))
        G = trend_view.term_view("고프코어", "style", api=FakeApi())["trend"]
        self.assertEqual(G["series_basis"], "feedit-yt-history-v1")
        self.assertTrue(any("YouTube" in n for n in G["notes"]))

    def test_temperature_bands_follow_the_page_edges(self):
        # dispatch.js: Math.round(temp) >= 85 과열 · >= 65 따뜻함 · >= 40 미지근
        self.assertEqual([temp_band(x) for x in (39.4, 39.5, 64.5, 82.95, 84.4, 84.6)],
                         ["차가움", "미지근", "따뜻함", "따뜻함", "따뜻함", "과열"])


class GetMetricTests(unittest.TestCase):
    def box(self, api=None):
        return Toolbox(Store(), Gate(), trend=api or FakeApi())

    def test_brand_has_a_metric_now(self):
        out = self.box().t_get_metric("아디다스", ["온도", "긍부정"])
        self.assertTrue(out["has_metric"])
        self.assertEqual(out["온도"]["temp"], 83)
        self.assertEqual(out["온도"]["verdict"], "뜨거움")
        self.assertEqual(out["긍부정"]["verdict"], "강한 구매 신호")
        self.assertIn("주의", out)

    def test_rank_text_uses_the_0_100_percentile(self):
        """트랙탑 백분위 18.44 → 상위 82%. 예전엔 0~1 로 읽어 '상위 1%' 였다."""
        out = self.box().t_get_metric("트랙탑", ["온도", "순위"])
        self.assertEqual(out["온도"]["rank_text"], "그날 언급된 전체 용어 중 상위 82%")
        self.assertEqual(out["순위"]["top_pct"], 82)
        self.assertNotIn("같은 축", json.dumps(out, ensure_ascii=False))

    def test_mentions_are_window_totals(self):
        out = self.box().t_get_metric("팬츠", ["온도"])
        self.assertEqual(out["mentions"]["최근28일"], out["온도"]["sample_n"])
        self.assertGreater(out["mentions"]["최근28일"], 300)
        self.assertFalse(out["thin_sample"])

    def test_unreachable_api_is_not_reported_as_missing_data(self):
        out = self.box(FakeApi(down=True)).t_get_metric("팬츠", ["온도"])
        self.assertIsNone(out["has_metric"])
        self.assertIn("읽지 못했습니다", out["unavailable"])

    def test_unknown_term_passes_the_api_reason_through(self):
        out = self.box().t_get_metric("없는말", ["온도"])
        self.assertIs(out["has_metric"], False)
        self.assertIn("사전에서 찾지 못했습니다", out["reason"])

    def test_sentiment_is_only_fetched_when_asked(self):
        api = FakeApi()
        self.box(api).t_get_metric("팬츠", ["온도"])
        self.assertEqual([c[0] for c in api.calls], ["trend"])

    def test_associations_use_the_page_api_without_losing_temperature(self):
        api = FakeApi()
        out = self.box(api).t_get_metric("팬츠", ["온도", "연관어"])
        self.assertTrue(out["has_metric"])
        self.assertEqual(out["온도"]["temp"], 70)
        self.assertEqual(out["연관어"][0]["assoc_canonical"], "티셔츠")
        self.assertEqual(out["연관어"][0]["co_count"], 49)
        self.assertIn(("assoc", "팬츠"), api.calls)

    def test_association_failure_does_not_hide_temperature(self):
        class AssocDown(FakeApi):
            def assoc(self, term):
                return {"status": "error", "reason": "연관어 서버 오류"}

        out = self.box(AssocDown()).t_get_metric("팬츠", ["온도", "연관어"])
        self.assertTrue(out["has_metric"])
        self.assertEqual(out["온도"]["temp"], 70)
        self.assertEqual(out["연관어"], {"unavailable": "연관어 서버 오류"})

    def test_evidence_failure_does_not_hide_temperature(self):
        class EvidenceDown(Store):
            def term_evidence(self, key, limit=3):
                raise RuntimeError("근거 조회 실패")

        out = Toolbox(EvidenceDown(), Gate(), trend=FakeApi()).t_get_metric(
            "팬츠", ["온도", "근거"])
        self.assertTrue(out["has_metric"])
        self.assertEqual(out["온도"]["temp"], 70)
        self.assertIn("읽지 못했습니다", out["근거"]["unavailable"])


class SayRuleTests(unittest.TestCase):
    def test_percentile_scale_is_0_to_100(self):
        self.assertEqual(_say_rule(18.44, "up", False)["allowed"], "이제 올라오기 시작했습니다")
        self.assertEqual(_say_rule(72.7, "up", False)["recommend"], "가능")

    def test_flat_or_unknown_direction_never_reads_as_rising(self):
        self.assertNotEqual(_say_rule(90, "flat", False)["recommend"], "가능")
        self.assertEqual(_say_rule(90, None, False)["recommend"], "금지")

    def test_thin_sample_blocks_judgement(self):
        self.assertEqual(_say_rule(90, "up", True, 5)["recommend"], "금지")


class CardTests(unittest.TestCase):
    def setUp(self):
        trend_view.set_source(FakeApi())

    def tearDown(self):
        trend_view.set_source(None)

    def test_card_and_sentence_say_the_same_numbers(self):
        hit = {"term_key": "item:트랙탑", "canonical": "트랙탑", "facet": "item"}
        node = report.build_term(Store(), Gate(), hit, "2026-09-29")
        rows = {r["k"]: r for r in blocks.b_metric_rank(node, "2026-09-29")["rows"]}
        self.assertEqual(rows["트렌드 온도"]["v"], "51점")
        self.assertEqual(rows["트렌드 온도"]["small"], "달아오르는 중")
        self.assertEqual(rows["순위"]["v"], "상위 82%")
        self.assertEqual(rows["언급량"]["small"], "최근 28일")
        sent = blocks.b_sentiment(node)
        self.assertEqual(sent["items"][0]["v"], "50")
        self.assertIn("판단 보류", sent["items"][0]["note"])

    def test_signal_card_keeps_db_order_and_zero_rows(self):
        hit = {"term_key": "item:트랙탑", "canonical": "트랙탑", "facet": "item"}
        node = report.build_term(Store(), Gate(), hit, "2026-09-29")
        card = blocks.b_sentiment_signal(node)
        self.assertEqual([r["k"] for r in card["rows"]], ["질문", "구매", "경험", "호평", "비판", "잡담"])
        self.assertEqual(card["rows"][1]["v"], "0건")

    def test_optional_evidence_failure_keeps_metric_card(self):
        class EvidenceDown(Store):
            def term_evidence(self, key, limit=3):
                raise RuntimeError("근거 조회 실패")

        hit = {"term_key": "item:팬츠", "canonical": "팬츠", "facet": "item"}
        node = report.build_term(EvidenceDown(), Gate(), hit, "2026-09-29",
                                 with_assoc=True, with_evidence=True)
        self.assertTrue(node["available"])
        self.assertEqual(node["temp"], 70)
        self.assertEqual(node["associations"][0]["canonical"], "티셔츠")
        self.assertEqual(node["evidence"], [])

    def test_api_errors_are_not_labeled_as_missing_measurements(self):
        class AxesDown(FakeApi):
            def assoc(self, term):
                return {"status": "error", "reason": "연관어 조회 오류"}

            def sentiment(self, term, brand=False):
                return {"status": "error", "reason": "긍부정 조회 오류"}

        hit = {"term_key": "item:팬츠", "canonical": "팬츠", "facet": "item"}
        node = report.build_term(Store(), Gate(), hit, "2026-09-29",
                                 with_assoc=True, api=AxesDown())
        self.assertTrue(node["available"])
        reasons = dict(node["coverage"]["reasons"])
        self.assertEqual(reasons["NO_ASSOC"], "연관어 조회 오류")
        self.assertEqual(reasons["NO_SENTIMENT"], "긍부정 조회 오류")


if __name__ == "__main__":
    unittest.main()
