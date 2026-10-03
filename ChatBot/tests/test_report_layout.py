"""리포트 캔버스의 시각 문법 — 같은 종류는 같은 모양, 빈 칸은 남기지 않는다."""
import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from app import orchestrator, report_skill


def _content(cid, kind, block):
    return {"id": cid, "kind": kind, "term": None, "block": block}


class Trace:
    def __init__(self, calls=None):
        self.calls = calls or []
        self.missing = []


def _spec(modules, **kw):
    return Trace([{"tool": "compose_report", "args": {}, "result": {
        "ok": True, "spec": {"title": "테스트", "accent": "coral", "surface": "paper",
                             "density": "balanced", "modules": modules, **kw}}}])


class NoteLooksTheSameTests(unittest.TestCase):
    def test_every_note_gets_one_treatment(self):
        """실측(2026-09-11): 같은 화면에서 안내문이 베이지 지면·흰 카드·점선으로
        세 가지 모양이었다. 셋 다 '없는 자료' 라는 같은 말이다."""
        catalog = [
            _content("missing:a", "missing", {"type": "note", "text": "A 없음"}),
            _content("salmal:b", "salmal", {"type": "note", "text": "빠진 신호"}),
            _content("missing:c", "missing", {"type": "note", "text": "C 없음"}),
        ]
        trace = _spec([{"kind": "missing", "presentation": "editorial", "span": 6},
                       {"kind": "salmal", "presentation": "card", "span": 6}])
        canvas = report_skill.build(catalog, trace)
        notes = [m for m in canvas["modules"] if m["block"]["type"] == "note"]
        self.assertEqual(len(notes), 3)
        self.assertEqual({m["presentation"] for m in notes}, {"compact"})
        self.assertEqual({m["emphasis"] for m in notes}, {"normal"})
        self.assertEqual({m["span"] for m in notes}, {12})


class NoEmptyColumnsTests(unittest.TestCase):
    def test_a_lone_half_width_module_fills_its_row(self):
        """실측: 방향 지표가 6열로 놓여 오른쪽 절반이 통째로 비었다."""
        catalog = [_content("direction:t", "direction",
                            {"type": "kpis", "items": [{"k": "방향", "v": "완만한 상승"},
                                                       {"k": "7일/4주", "v": "1.43"},
                                                       {"k": "7일 평균", "v": "14.86"},
                                                       {"k": "4주 평균", "v": "10.39"}]})]
        canvas = report_skill.build(
            catalog, _spec([{"kind": "direction", "presentation": "card", "span": 6}]))
        module = canvas["modules"][0]
        self.assertEqual(module["span"], 12)
        # 폭을 다 쓰면 네 칸이 한 줄에 선다 — 2×2 로 접히지 않는다.
        self.assertEqual(module["columns"], 4)

    def test_rows_that_already_add_up_are_left_alone(self):
        modules = [{"span": 6}, {"span": 6}, {"span": 4}, {"span": 4}, {"span": 4}]
        report_skill._pack_rows(modules)
        self.assertEqual([m["span"] for m in modules], [6, 6, 4, 4, 4])

    def test_the_last_module_of_a_short_row_stretches(self):
        modules = [{"span": 12}, {"span": 4}, {"span": 4}]
        report_skill._pack_rows(modules)
        self.assertEqual([m["span"] for m in modules], [12, 4, 8])


class CutOffAnswerTests(unittest.TestCase):
    """예산이 끊겨 요약 문장을 못 써도, 조회한 것은 말해 준다."""

    def _result(self, calls):
        out = orchestrator.Result()
        out.trace = Trace(calls)
        out.stopped = "time_budget"
        return out

    def test_recap_is_written_from_tool_results(self):
        text = orchestrator._stop_say(self._result([
            {"tool": "get_metric", "args": {"term": "아디다스"},
             "result": {"term": "아디다스", "has_metric": True,
                        "온도": {"temp": 58, "band": "따뜻함"}}},
            {"tool": "get_metric", "args": {"term": "폴로셔츠"},
             "result": {"term": "폴로셔츠", "has_metric": False}},
            {"tool": "get_salmal_index", "args": {},
             "result": {"score": 44, "recommendation": "보류", "confidence": "낮음",
                        "missing": ["taste", "price"]}},
        ]))
        self.assertIn("살말 지수 44점 · 보류", text)
        self.assertIn("아디다스 58점 (따뜻함)", text)
        self.assertIn("폴로셔츠", text)
        self.assertIn("취향 · 가격", text)

    def test_nothing_looked_up_keeps_the_short_line(self):
        text = orchestrator._stop_say(self._result([]))
        self.assertEqual(text, orchestrator.STOP_SAY["time_budget"])

    def test_recap_never_invents_a_number(self):
        text = orchestrator._stop_say(self._result([
            {"tool": "get_metric", "args": {"term": "셔츠"},
             "result": {"term": "셔츠", "has_metric": False}}]))
        self.assertIn("측정 자료가 없던 것: 셔츠", text)
        self.assertNotIn("점", text.split("어느 쪽")[0].replace("셔츠", ""))


if __name__ == "__main__":
    unittest.main()
