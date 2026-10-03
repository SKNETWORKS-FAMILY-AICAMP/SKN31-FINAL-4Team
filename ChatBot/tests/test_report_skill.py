import json
import unittest
from unittest.mock import patch

from app import agent_blocks, agent_path, blocks, orchestrator, report_skill, verify
from app.tools import Toolbox, specs_for


class Trace:
    def __init__(self, calls, missing=None):
        self.calls = calls
        self.missing = missing or []


class Store:
    def metric_facet(self, _term):
        return "style"

    def latest_day(self):
        return "2026-09-10"

    def top_terms(self, facet=None, limit=10, facets=None):
        return [{"canonical": "고프코어", "facet": "style", "temp": 82,
                 "raw_count": 120}]


class Gate:
    def facet_of(self, _term):
        return "style"


NODE = {
    "available": True, "canonical": "고프코어", "facet_name": "스타일",
    "temp": 82, "temp_band": "높음", "raw_count": 120, "pct_rank": 91,
    "sources": [], "associations": [], "evidence": [],
}


def design(modules, **overrides):
    spec = {
        "title": "고프코어 흐름", "accent": "violet", "surface": "soft",
        "density": "airy", "modules": modules,
    }
    spec.update(overrides)
    return {"tool": "compose_report", "args": spec,
            "result": {"ok": True, "skill": "generative-report-v1", "spec": spec}}


class ReportSkillTest(unittest.TestCase):
    def test_compose_report_is_exposed_as_an_orchestrator_tool(self):
        self.assertIn("compose_report", [s.get("name") for s in specs_for({})])

    def test_tool_sanitizes_design_without_accepting_html(self):
        box = Toolbox(Store(), Gate())
        out = box.t_compose_report(
            "<script>긴 제목</script>", "unknown", "paper", "balanced",
            [{"kind": "metric", "term": "고프코어", "presentation": "hero",
              "span": 99, "emphasis": "strong"},
             {"kind": "made-up", "term": None, "presentation": "card",
              "span": 6, "emphasis": "normal"}],
        )
        self.assertEqual(out["spec"]["accent"], "coral")
        self.assertEqual(out["spec"]["modules"][0]["span"], 12)
        self.assertEqual(len(out["spec"]["modules"]), 1)

    def test_canvas_follows_model_composition_not_named_variant(self):
        catalog = [
            {"id": "metric:고프코어", "kind": "metric", "term": "고프코어",
             "block": {"type": "rank", "rows": []}},
            {"id": "direction:고프코어", "kind": "direction", "term": "고프코어",
             "block": {"type": "kpis", "items": []}},
        ]
        trace = Trace([design([
            {"kind": "direction", "term": "고프코어", "presentation": "hero",
             "span": 8, "emphasis": "strong"},
            {"kind": "metric", "term": "고프코어", "presentation": "list",
             "span": 4, "emphasis": "quiet"},
        ])])
        canvas = report_skill.build(catalog, trace)
        self.assertEqual(canvas["type"], "generative_report")
        self.assertNotIn("variant", canvas)
        self.assertEqual([m["kind"] for m in canvas["modules"]], ["direction", "metric"])
        self.assertEqual([m["span"] for m in canvas["modules"]], [8, 4])

    def test_three_sentiment_kpis_get_three_columns_and_korean_labels(self):
        # 2026-10-01 — 트렌드 분석 긍부정 탭과 같은 요약(trend_view.sentiment_summary)을 그린다.
        block = blocks.b_sentiment({"sentiment": {
            "window_days": 28, "반응": {"긍정": 10, "중립": 18, "부정": 1, "합계": 29},
            "positive_pct": 34, "negative_pct": 3, "dial": 91, "dial_label": "긍정 우위 %",
            "purchase_intent_index": None, "judged": True, "verdict": "강한 구매 신호",
        }})
        catalog = [{"id": "sentiment:고프코어", "kind": "sentiment",
                    "term": "고프코어", "block": block}]
        trace = Trace([design([{"kind": "sentiment", "term": "고프코어",
                                "presentation": "card", "span": 4,
                                "emphasis": "normal"}])])
        canvas = report_skill.build(catalog, trace)
        module = canvas["modules"][0]
        self.assertEqual(module["columns"], 3)
        items = module["block"]["items"]
        self.assertEqual([i["k"] for i in items], ["긍정 우위 %", "긍정 반응 비율", "부정 반응 비율"])
        self.assertEqual(items[0]["v"], "91")
        self.assertIn("강한 구매 신호", items[0]["note"])
        self.assertEqual(items[1]["note"], "최근 28일 · 10건")

    def test_direction_kpis_keep_their_term_and_facet_label(self):
        node = dict(NODE, direction={"label": "완만한 상승", "ratio": 1.2,
                                    "ma7": 23.0, "ma28": 19.0, "tone": "up"})
        block = blocks.b_direction(node)
        self.assertEqual(block["title"], "고프코어")
        self.assertEqual(block["meta"], "스타일")

    def test_unknown_content_reference_is_not_invented(self):
        catalog = [{"id": "metric:고프코어", "kind": "metric", "term": "고프코어",
                    "block": {"type": "rank", "rows": []}}]
        trace = Trace([design([{"kind": "metric", "term": "없는상품",
                                "presentation": "hero", "span": 12,
                                "emphasis": "strong"}])])
        canvas = report_skill.build(catalog, trace)
        self.assertEqual(canvas["source"], "fallback")
        self.assertEqual(canvas["modules"][0]["id"], "metric:고프코어")
        self.assertEqual(canvas["title"], "고프코어 흐름")

    def test_generic_model_title_is_replaced_with_content_title(self):
        catalog = [{"id": "context:all:0", "kind": "context", "term": None,
                    "block": {"type": "rank", "rows": []}}]
        trace = Trace([design([{"kind": "context", "term": None,
                                "presentation": "hero", "span": 12,
                                "emphasis": "strong"}], title="FEEDiT SIGNAL")])
        canvas = report_skill.build(catalog, trace)
        self.assertEqual(canvas["title"], "오늘의 옷차림")

    def test_rank_indicator_cannot_use_mismatched_editorial_surface(self):
        catalog = [{"id": "context:all:0", "kind": "context", "term": None,
                    "block": {"type": "rank", "title": "상황에 맞는지", "rows": []}}]
        trace = Trace([design([{"kind": "context", "term": None,
                                "presentation": "editorial", "span": 5,
                                "emphasis": "normal"}])])
        canvas = report_skill.build(catalog, trace)
        self.assertEqual(canvas["modules"][0]["presentation"], "card")

    def test_unknown_season_terms_are_grouped_into_one_row(self):
        blocks = agent_blocks._season_blocks({
            "basis": "20°C 기준",
            "items": [{"term": "자켓", "verdict": "적합", "say": "잘 맞습니다."}],
            "unknown": ["캐주얼", "고프코어", "긱시크"],
        })
        rows = blocks[0]["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["k"], "판단하지 않은 항목")
        self.assertEqual(rows[1]["small"], "캐주얼 · 고프코어 · 긱시크")

    def test_missing_data_cannot_be_hidden_by_design(self):
        catalog = [
            {"id": "metric:고프코어", "kind": "metric", "term": "고프코어",
             "block": {"type": "rank", "rows": []}},
            {"id": "missing:고프코어:0", "kind": "missing", "term": "고프코어",
             "block": {"type": "note", "text": "가격 자료 없음"}},
        ]
        trace = Trace([design([{"kind": "metric", "term": "고프코어",
                                "presentation": "hero", "span": 12,
                                "emphasis": "strong"}])])
        canvas = report_skill.build(catalog, trace)
        self.assertEqual([m["kind"] for m in canvas["modules"]], ["metric", "missing"])

    def test_layout_numbers_do_not_become_verified_facts(self):
        box = Toolbox(Store(), Gate())
        box.run("compose_report", {
            "title": "보기", "accent": "coral", "surface": "paper",
            "density": "balanced", "modules": [{"kind": "metric", "term": "고프코어",
            "presentation": "hero", "span": 12, "emphasis": "strong"}]})
        self.assertNotIn("12", box.trace.numbers())

    @patch("app.orchestrator.llm.respond")
    def test_orchestrator_requests_design_after_structured_metric(self, respond):
        spec = {
            "title": "지금 뜨는 흐름", "accent": "coral", "surface": "paper",
            "density": "balanced", "modules": [{"kind": "ranking", "term": None,
            "presentation": "hero", "span": 12, "emphasis": "strong"}],
        }
        respond.side_effect = [
            {"_raw": {"output": [{"type": "function_call", "call_id": "c1",
              "name": "rank_terms", "arguments": json.dumps({"facet": None, "limit": 5})}]},
             "text": ""},
            {"_raw": {"output": [{"type": "message"}]}, "text": "고프코어가 가장 높아요."},
            {"_raw": {"output": [{"type": "function_call", "call_id": "c2",
              "name": "compose_report", "arguments": json.dumps(spec)}]}, "text": ""},
        ]
        result = orchestrator.run("요즘 뭐가 핫해?", store=Store(), gate=Gate())
        self.assertEqual(result.answer, "고프코어가 가장 높아요.")
        self.assertIn("compose_report", [c["tool"] for c in result.trace.calls])
        self.assertEqual(respond.call_count, 3)

    @patch("app.orchestrator.llm.respond")
    def test_orchestrator_allows_plain_answer_without_report_material(self, respond):
        respond.return_value = {
            "_raw": {"output": [{"type": "message"}]}, "text": "반가워요.",
        }
        result = orchestrator.run("안녕", store=Store(), gate=Gate())
        self.assertEqual(result.answer, "반가워요.")
        self.assertNotIn("compose_report", [c["tool"] for c in result.trace.calls])
        self.assertEqual(respond.call_count, 1)

    @patch("app.agent_path.agent_blocks.build", return_value=[{"type": "generative_report"}])
    @patch("app.agent_path.verify.verify")
    @patch("app.agent_path.orchestrator.run")
    def test_agent_path_builds_fallback_when_complex_report_omits_design(
            self, run, verify_answer, build):
        result = orchestrator.Result()
        result.answer = "고프코어의 여러 신호를 함께 봤습니다."
        result.stopped = "done"
        result.trace = Trace([{
            "tool": "get_metric", "args": {"term": "고프코어",
                                             "axes": ["온도", "모멘텀", "출처별"]},
            "result": {"term": "고프코어", "has_metric": True,
                       "as_of": "2026-09-09", "온도": {"temp": 21}},
        }])
        run.return_value = result
        verify_answer.return_value = (result.answer, verify.Report())

        out = agent_path.ask("고프코어 자세히 분석해줘", store=Store(), gate=Gate())

        build.assert_called_once()
        self.assertEqual(out["blocks"], [{"type": "generative_report"}])

    @patch("app.agent_path.agent_blocks.build")
    @patch("app.agent_path.verify.verify")
    @patch("app.agent_path.orchestrator.run")
    def test_agent_path_keeps_a_single_metric_as_conversation(
            self, run, verify_answer, build):
        result = orchestrator.Result()
        result.answer = "고프코어 온도는 21점으로 차가운 편입니다."
        result.stopped = "done"
        result.trace = Trace([{
            "tool": "get_metric", "args": {"term": "고프코어", "axes": ["온도"]},
            "result": {"term": "고프코어", "has_metric": True,
                       "as_of": "2026-09-09", "온도": {"temp": 21}},
        }])
        run.return_value = result
        verify_answer.return_value = (result.answer, verify.Report())

        out = agent_path.ask("고프코어 온도만 알려줘", store=Store(), gate=Gate())

        build.assert_not_called()
        self.assertEqual(out["blocks"], [])

    def test_report_safety_net_matches_information_complexity(self):
        one = Trace([{"tool": "get_metric",
                      "args": {"term": "고프코어", "axes": ["온도"]},
                      "result": {"term": "고프코어", "has_metric": True}}])
        many = Trace([{"tool": "get_metric",
                       "args": {"term": "고프코어",
                                "axes": ["온도", "모멘텀", "출처별"]},
                       "result": {"term": "고프코어", "has_metric": True}}])
        ranking = Trace([{"tool": "rank_terms", "args": {},
                          "result": {"items": [{"term": "고프코어"}]}}])
        self.assertFalse(orchestrator.report_required("온도만 알려줘", one))
        self.assertTrue(orchestrator.report_required("자세히 분석해줘", one))
        self.assertTrue(orchestrator.report_required("요즘 뭐가 핫해?", ranking))
        self.assertTrue(orchestrator.report_required("흐름을 여러 축으로 봐줘", many))

    @patch("app.orchestrator.llm.respond")
    def test_orchestrator_stops_before_model_call_when_cancelled(self, respond):
        result = orchestrator.run("멈춰 줘", store=Store(), gate=Gate(),
                                  cancel_check=lambda: True)
        self.assertEqual(result.stopped, "cancelled")
        respond.assert_not_called()

    @patch("app.agent_blocks.report.build_term", return_value=NODE)
    def test_agent_blocks_binds_only_real_metric_to_generated_canvas(self, _build):
        calls = [
            {"tool": "get_metric", "args": {"term": "고프코어", "axes": ["온도"]},
             "result": {"term": "고프코어", "has_metric": True, "as_of": "2026-09-10"}},
            design([{"kind": "metric", "term": "고프코어", "presentation": "hero",
                     "span": 12, "emphasis": "strong"}]),
        ]
        blocks = agent_blocks.build(Trace(calls), Store(), Gate())
        self.assertEqual(blocks[0]["type"], "generative_report")
        self.assertEqual(blocks[0]["source"], "model")
        self.assertEqual(blocks[0]["modules"][0]["block"]["type"], "rank")

    @patch("app.agent_blocks.report.build_term", side_effect=RuntimeError("temporary read failure"))
    def test_metric_card_survives_store_rehydrate_failure_and_missing_design(self, _build):
        calls = [
            {"tool": "search_terms", "args": {"q": "고프코어"},
             "result": {"found": [{"term": "고프코어", "facet": "style"}]}},
            {"tool": "get_metric",
             "args": {"term": "고프코어", "axes": ["온도", "출처별"]},
             "result": {"term": "고프코어", "has_metric": True,
                        "as_of": "2026-09-09",
                        "온도": {"temp": 21, "band": "차가움", "sample_n": 11},
                        "출처별": [{"source_code": "kream", "raw_count": 7}]}},
        ]
        result = agent_blocks.build(Trace(calls), Store(), Gate())
        self.assertEqual(result[0]["type"], "generative_report")
        self.assertEqual(result[0]["source"], "fallback")
        self.assertEqual([m["kind"] for m in result[0]["modules"]], ["metric", "sources"])
        self.assertEqual(result[0]["modules"][0]["block"]["rows"][0]["v"], "21점")

    def test_salmal_card_survives_a_cut_off_loop(self):
        """예산이 끊겨 compose_report 를 못 불러도 살말 카드는 남아야 한다.

        실측(2026-09-11): 이 조합에서 report_skill.build 가 spec=None 을
        그대로 읽어 AttributeError 로 터졌고, agent_path 가 예외를 삼켜
        리포트 카드가 통째로 사라졌다. 화면에는 문장만 남았다.
        """
        calls = [
            {"tool": "get_salmal_index", "args": {"term": "셔츠"},
             "result": {"term": "셔츠", "score": 61, "recommendation": "보류",
                        "confidence": "낮음", "coverage": 35, "signals": [],
                        "missing": ["taste", "price"]}},
        ]
        result = agent_blocks.build(Trace(calls), Store(), Gate())
        self.assertEqual(result[0]["type"], "generative_report")
        self.assertEqual(result[0]["source"], "fallback")
        self.assertIn("salmal", [m["kind"] for m in result[0]["modules"]])


if __name__ == "__main__":
    unittest.main()
