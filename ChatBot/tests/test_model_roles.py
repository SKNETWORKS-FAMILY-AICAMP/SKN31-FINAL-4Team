"""Terra · Sol · Luna 역할 배치 (2026-09-18).

설계
  · Terra(MID)  판단 — 오케스트레이터(도구 선택·살말 판단) · 사진 · 사전 밖 지식 설명
  · Luna(SMALL) 닫힌 출력 — 의도 분류 · 앞 턴 이어받기 · 다듬기 · 발췌·추출 · 검증 · 마무리
  · Sol(LARGE)  막혔을 때만 — Terra/Luna 호출이 실패했거나 결과가 깨졌을 때 한 번 더
"""
import sys
import unittest
from unittest.mock import Mock, patch

sys.modules.setdefault("requests", Mock())

from app import llm, nlu, orchestrator, polish, verify

MID, SMALL, LARGE = llm.MODEL_MID, llm.MODEL_SMALL, llm.MODEL_LARGE


class Store:
    def metric_facet(self, _t): return "style"
    def latest_day(self): return "2026-09-10"


class Gate:
    def facet_of(self, _t): return "style"


def msg(text):
    return {"_raw": {"output": [{"type": "message"}]}, "text": text}


class RoleTable(unittest.TestCase):
    def test_design(self):
        judge = ["orchestrator", "interpreter", "advisor", "general", "vision"]
        closed = ["classify", "context", "polish", "extract", "quote", "verify", "ask", "finish"]
        self.assertEqual({llm.role(r)["model"] for r in judge}, {MID})
        self.assertEqual({llm.role(r)["model"] for r in closed}, {SMALL})
        self.assertNotIn(LARGE, {m for m, _ in llm.ROLES.values()}, "Sol 은 평소 역할에 없다")

    def test_escalate_keeps_effort_swaps_model(self):
        self.assertEqual(llm.escalate("orchestrator"),
                         {"model": LARGE, "effort": llm.role("orchestrator")["effort"]})

    def test_can_escalate(self):
        with patch.object(llm, "DISABLED", False):
            for err, want in [("NET_ReadTimeout", True), ("HTTP_500", True), ("HTTP_429", True),
                              ("NO_KEY", False), ("DISABLED", False), ("HTTP_401", False), (None, False)]:
                with patch.object(llm, "LAST_ERROR", err):
                    self.assertEqual(llm.can_escalate(), want, err)
            with patch.object(llm, "LAST_ERROR", None):
                self.assertTrue(llm.can_escalate(bad_output=True))
            with patch.object(llm, "ESCALATE", False), patch.object(llm, "LAST_ERROR", "HTTP_500"):
                self.assertFalse(llm.can_escalate())


class CallSitesUseRoles(unittest.TestCase):
    def test_nlu_uses_luna(self):
        with patch.object(nlu.llm, "available", return_value=True), \
             patch.object(nlu, "classify_rule", return_value=("trend.direction", False)), \
             patch.object(nlu.llm, "respond", return_value=None) as r:
            nlu.classify("음… 이거 괜찮을까 모르겠네", "general")
        self.assertEqual(r.call_args.kwargs["model"], SMALL)

    def test_polish_uses_luna(self):
        with patch.object(polish.llm, "available", return_value=True), \
             patch.object(polish.llm, "respond", return_value=None) as r:
            polish.polish("고프코어는 지금 올라가는 중입니다.")
        self.assertEqual(r.call_args.kwargs["model"], SMALL)


class SolFallback(unittest.TestCase):
    @patch("app.orchestrator.llm.respond")
    def test_orchestrator_retries_with_sol_when_terra_fails(self, respond):
        def fake(*a, **kw):
            if kw.get("model") == MID:
                llm.LAST_ERROR = "NET_ReadTimeout"
                return None
            return msg("Sol 이 이어서 답했어요.")
        respond.side_effect = fake
        with patch.object(llm, "DISABLED", False):
            out = orchestrator.run("안녕", store=Store(), gate=Gate())
        self.assertEqual(out.answer, "Sol 이 이어서 답했어요.")
        self.assertEqual([c.kwargs["model"] for c in respond.call_args_list], [MID, LARGE])
        self.assertEqual(out.escalated, ["orchestrator:NET_ReadTimeout"])

    @patch("app.orchestrator.llm.respond")
    def test_no_sol_when_terra_answers(self, respond):
        respond.return_value = msg("반가워요.")
        out = orchestrator.run("안녕", store=Store(), gate=Gate())
        self.assertEqual(out.escalated, [])
        self.assertEqual({c.kwargs["model"] for c in respond.call_args_list}, {MID})

    @patch("app.orchestrator.llm.respond")
    def test_no_sol_without_key(self, respond):
        def fake(*a, **kw):
            llm.LAST_ERROR = "NO_KEY"
            return None
        respond.side_effect = fake
        with patch.object(llm, "DISABLED", False):
            out = orchestrator.run("안녕", store=Store(), gate=Gate())
        self.assertNotIn(LARGE, [c.kwargs["model"] for c in respond.call_args_list])
        self.assertEqual(out.escalated, [])

    def test_verify_fix_escalates_on_garbled_luna(self):
        rep = verify.Report(); rep.suspect_numbers = ["87"]
        calls = []
        def fake(*a, **kw):
            calls.append(kw["model"])
            if kw["model"] == SMALL:
                llm.LAST_ERROR = None
                return {"ok": False, "answer": "감성 지표는 아직 측정 자료가 없습니다.keletal", "removed": []}
            return {"ok": False, "answer": "감성 지표는 아직 측정 자료가 없습니다.", "removed": ["87"]}
        with patch.object(verify.llm, "respond", side_effect=fake), patch.object(llm, "DISABLED", False):
            got = verify.fix("감성 지표는 87점입니다.", None, rep, deadline=None)
        self.assertEqual(got, "감성 지표는 아직 측정 자료가 없습니다.")
        self.assertEqual(calls, [SMALL, LARGE])
        self.assertTrue(rep.escalated.startswith("verify:fix_garbled"))


if __name__ == "__main__":
    unittest.main()


class LastRoundWrites(unittest.TestCase):
    """바퀴가 바닥나도 답 없이 끝나지 않는다 (2026-09-18)."""

    @patch("app.orchestrator.llm.respond")
    def test_last_round_has_no_data_tools_and_answers(self, respond):
        import json
        seen_tools = []

        def fake(*a, **kw):
            names = [t.get("name") for t in (kw.get("tools") or [])]
            seen_tools.append(names)
            if "get_metric" in names:            # 데이터 도구가 있으면 계속 더 부르려 한다
                n = len(seen_tools)
                return {"_raw": {"output": [{"type": "function_call", "call_id": f"c{n}",
                        "name": "get_metric", "arguments": json.dumps({"term": f"용어{n}"})}]},
                        "text": ""}
            return msg("지금까지 본 것으로 답합니다.")
        respond.side_effect = fake

        class S(Store):
            def term_latest(self, _k): return None
            def obs_count(self, *a): return 0
            def term_sources(self, _k): return []

        out = orchestrator.run("고프코어 요즘 어때?", store=S(), gate=Gate())
        self.assertEqual(out.answer, "지금까지 본 것으로 답합니다.")
        self.assertEqual(len(seen_tools), orchestrator.MAX_ROUNDS)
        self.assertNotIn("get_metric", seen_tools[-1])
        self.assertEqual(out.stopped, "done")
