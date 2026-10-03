"""사진 분석 턴의 관찰값이 다음 질문까지 이어지는지 본다.

2026-09-14 실측: 살말 모드에서 스커트 사진에 답한 뒤 "소재는 뭐야?"라고
물으면 챗봇이 어떤 아이템인지 다시 물었다. 화면에 보낸 설명이 history에는
terms만 남고, Vision Agent의 item/materials 등이 버려졌기 때문이다.
"""
import sys
import unittest
from unittest.mock import Mock, patch

sys.modules.setdefault("requests", Mock())

from app import history, orchestrator
from app.engine import ChatEngine


class _Gate:
    def parse(self, text):
        if "스커트" in text:
            return {"search": [{"canonical": "스커트", "facet": "item",
                                 "term_key": "item:스커트"}]}
        return {"search": []}


OBSERVATION = {
    "item": "미디 스커트",
    "tags": ["레이스", "미디 스커트"],
    "colors": ["블랙"],
    "materials": ["광택이 있는 직물로 보임"],
    "silhouette": ["미디 길이", "A라인"],
    "details": ["밑단 레이스"],
    "styles": ["발레코어"],
    "uncertainties": ["정확한 혼용률은 사진만으로 확인 불가"],
    "summary": "은은한 광택과 밑단 레이스가 보이는 블랙 미디 스커트입니다.",
}


class VisionMemoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = ChatEngine.__new__(ChatEngine)
        self.engine.use_llm = True
        self.engine.gate = _Gate()
        self.engine.memory = history.Memory()

    @patch("app.engine.llm.available", return_value=True)
    @patch("app.engine.llm.vision_salmal", return_value=OBSERVATION)
    @patch("app.engine.salmal_index.calculate", return_value={
        "score": None, "recommendation_allowed": False,
    })
    @patch("app.engine.agent_blocks.salmal_blocks", return_value=[])
    @patch("app.engine.report_skill.build", return_value=None)
    def test_salmal_vision_keeps_item_material_and_shape(
            self, _build, _blocks, _index, _vision, _available):
        rep = self.engine._vision_ask(
            "이거 어때?", "salmal", ["data:image/png;base64,AA=="], "conv-1")

        self.assertEqual(rep["kind"], "agent")
        self.assertEqual(rep["visual_context"]["materials"],
                         ["광택이 있는 직물로 보임"])
        self.assertEqual(rep["visual_context"]["silhouette"], ["미디 길이", "A라인"])
        self.assertEqual(rep["terms"][0]["canonical"], "스커트")

        remembered = self.engine.memory.recent("conv-1")[0]
        self.assertEqual(remembered["visual"]["item"], "미디 스커트")
        self.assertEqual(remembered["visual"]["details"], ["밑단 레이스"])

    def test_browser_history_preserves_bounded_visual_observations(self):
        turns = history.sanitize([{
            "q": "이거 어때?", "intent": "vision.salmal", "mode": "salmal",
            "terms": [], "visual": OBSERVATION,
        }])

        self.assertEqual(turns[0]["visual"]["colors"], ["블랙"])
        self.assertEqual(turns[0]["visual"]["materials"],
                         ["광택이 있는 직물로 보임"])

    def test_orchestrator_receives_structured_previous_photo(self):
        turn = history.make_turn("이거 어때?", "vision.salmal", "salmal", [], OBSERVATION)
        block = orchestrator._ctx_block("소재는 뭐야?", {"mode": "salmal"}, [turn])

        self.assertIn("[최근 이미지 분석]", block)
        self.assertIn("아이템=미디 스커트", block)
        self.assertIn("소재=광택이 있는 직물로 보임", block)
        self.assertIn("실루엣=미디 길이·A라인", block)
        self.assertNotIn("최근 이미지 설명", block)


class PhotoWithDataQuestionTests(unittest.TestCase):
    """사진 + "어울리는 바지 추천해줘" 처럼 데이터가 필요한 질문 (2026-10-02).
    사진 설명으로 끝내지 않고, 본 것을 앞 턴으로 붙여 도구 루프에 넘긴다."""

    def setUp(self):
        self.engine = ChatEngine.__new__(ChatEngine)
        self.engine.use_llm = True
        self.engine.gate = _Gate()
        self.engine.memory = history.Memory()
        self.engine.store = self.engine.salmal = self.engine.taste = None

    @patch("app.engine.agent_path.enabled", return_value=True)
    @patch("app.engine.llm.available", return_value=True)
    @patch("app.engine.llm.vision", return_value=OBSERVATION)
    def test_recommend_question_goes_to_tools_with_the_photo_as_context(self, *_):
        seen = {}

        def fake_ask(q, **kw):
            seen["q"], seen["history"] = q, kw["history"]
            return {"ok": True, "kind": "agent", "intent": "agent", "headline": "<p>바지 셋</p>",
                    "terms": [], "blocks": []}

        with patch("app.engine.agent_path.ask", side_effect=fake_ask):
            rep = self.engine._vision_ask("이거랑 어울리는 바지 추천해줘", "general",
                                          ["data:image/png;base64,AA=="], "conv-2")
        self.assertEqual(seen["q"], "이거랑 어울리는 바지 추천해줘")
        self.assertEqual(seen["history"][-1]["visual"]["item"], "미디 스커트")
        self.assertIn("블랙 미디 스커트", rep["headline"])          # 본 것을 먼저 말하고
        self.assertTrue(rep["headline"].endswith("<p>바지 셋</p>"))   # 도구 답이 이어진다
        self.assertEqual(rep["visual_context"]["item"], "미디 스커트")
        self.assertEqual(self.engine.memory.recent("conv-2")[-1]["visual"]["item"], "미디 스커트")

    @patch("app.engine.agent_path.enabled", return_value=True)
    @patch("app.engine.llm.available", return_value=True)
    @patch("app.engine.llm.vision", return_value=OBSERVATION)
    def test_plain_look_question_stays_a_photo_answer(self, *_):
        with patch("app.engine.agent_path.ask") as ask:
            rep = self.engine._vision_ask("이거 뭐야?", "general",
                                          ["data:image/png;base64,AA=="], "conv-3")
        ask.assert_not_called()
        self.assertEqual(rep["intent"], "vision.image")

    @patch("app.engine.agent_path.enabled", return_value=True)
    @patch("app.engine.llm.available", return_value=True)
    @patch("app.engine.llm.vision", return_value=OBSERVATION)
    def test_tool_failure_falls_back_to_the_photo_answer(self, *_):
        with patch("app.engine.agent_path.ask", side_effect=RuntimeError("down")):
            rep = self.engine._vision_ask("요즘 이런 거 유행해?", "general",
                                          ["data:image/png;base64,AA=="], "conv-4")
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["intent"], "vision.image")


if __name__ == "__main__":
    unittest.main()
