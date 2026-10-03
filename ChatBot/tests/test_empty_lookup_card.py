"""조회했는데 지표가 하나도 없던 질문에서도 리포트 카드는 떠야 한다.

실측(2026-09-11): 링크 질문에서 찾아본 용어가 전부 무측정이라 카탈로그가 비었고,
화면에는 문장만 남고 카드가 통째로 사라졌다. 무엇을 보고 그렇게 말했는지
확인할 자리가 없어진다.
"""
import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from app import agent_blocks


class _Trace:
    def __init__(self, calls, missing=None):
        self.calls = calls
        self.missing = missing or []


def _texts(canvas):
    out = []
    for module in canvas.get("modules") or []:
        block = module.get("block") or (module.get("content") or {}).get("block") or {}
        if block.get("text"):
            out.append(block["text"])
    return out


class EmptyLookupTests(unittest.TestCase):
    def test_terms_without_metrics_still_make_a_card(self):
        trace = _Trace([
            {"tool": "get_metric", "args": {"term": "폴로셔츠", "axes": ["온도"]},
             "result": {"term": "폴로셔츠", "has_metric": False,
                        "reason": "표본이 적어 판단에 사용할 수 없습니다."}},
        ])
        blocks = agent_blocks.build(trace, store=Mock(), gate=Mock())
        self.assertEqual(len(blocks), 1)
        self.assertIn("폴로셔츠 — 표본이 적어 판단에 사용할 수 없습니다.",
                      _texts(blocks[0]))

    def test_same_thing_is_not_said_twice(self):
        trace = _Trace(
            [{"tool": "get_metric", "args": {"term": "폴로셔츠", "axes": ["온도"]},
              "result": {"term": "폴로셔츠", "has_metric": False, "reason": "없습니다."}}],
            missing=[{"term": "폴로셔츠", "axis": "온도", "reason": "측정 자료 없음"}])
        blocks = agent_blocks.build(trace, store=Mock(), gate=Mock())
        texts = _texts(blocks[0])
        self.assertEqual(len([t for t in texts if t.startswith("폴로셔츠")]), 1)

    def test_nothing_looked_up_still_means_no_card(self):
        self.assertEqual(agent_blocks.build(_Trace([]), store=Mock(), gate=Mock()), [])


if __name__ == "__main__":
    unittest.main()
