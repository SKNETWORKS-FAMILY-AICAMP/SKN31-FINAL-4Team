"""링크 질문이 답을 쓰는 바퀴까지 가는가 (2026-09-11 실측 회귀).

    ! 18574ms stopped=time_budget 바퀴=3(5563+6871ms) 웹검색=2 호출=5 블록=1
      도구=search_terms,get_metric,get_metric,get_metric,get_salmal_index

링크 확인(5.6초) + 지표 조회(6.9초)로 루프 몫을 다 쓰고, 답을 쓰는 세 번째
바퀴가 시작도 못 했다. compose_report 도 못 불러 화면은 폴백으로 그려졌다.
"""
import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from app import orchestrator


class LinkBudgetTests(unittest.TestCase):
    def test_a_link_question_gets_the_extra_round(self):
        plain = orchestrator.budget_for("삼바 지금 사도 될까?")
        link = orchestrator.budget_for("https://www.musinsa.com/products/6886664 이거 사도 될까?")
        self.assertEqual(link - plain, orchestrator.LINK_EXTRA)

    def test_bare_www_counts_as_a_link(self):
        self.assertGreater(orchestrator.budget_for("www.musinsa.com/products/1 어때?"),
                           orchestrator.TIME_BUDGET)

    def test_ordinary_questions_are_not_slowed_down(self):
        self.assertEqual(orchestrator.budget_for("요즘 뭐가 핫해?"), orchestrator.TIME_BUDGET)

    def test_the_measured_run_now_reaches_the_writing_round(self):
        """실측 그대로 계산해 본다 — 예산 25초, 조회에 12.43초를 쓴 시점.

        예전: 루프 몫(25-8=17초)에서 12.43초를 쓰면 4.57초가 남아 WRITE_MIN(6.5)에
        못 미쳐 답 쓰는 바퀴가 시작되지 못했다.
        지금: 조회가 끝났으면 뒷몫에서 빌려 deadline-검증몫 까지 쓴다.
        """
        budget, used = 25.0, 12.434
        loop_end = budget - orchestrator.reserve(budget, orchestrator.TAIL_RESERVE)
        self.assertLess(loop_end - used, orchestrator.WRITE_MIN)          # 예전이라면 중단
        borrowed = budget - orchestrator.VERIFY_RESERVE - used
        self.assertGreaterEqual(borrowed, orchestrator.WRITE_MIN)         # 지금은 시작한다

    def test_link_question_with_the_default_budget_also_fits(self):
        budget = orchestrator.TIME_BUDGET + orchestrator.LINK_EXTRA
        borrowed = budget - orchestrator.VERIFY_RESERVE - 12.434
        self.assertGreaterEqual(borrowed, orchestrator.WRITE_MIN)


class LinkRoundTests(unittest.TestCase):
    """실측 2번째 (2026-09-11):

        ! 33058ms/33000ms stopped=max_rounds 바퀴=4(5328+12387+4624+3006ms)
          도구=…,get_salmal_index,declare_missing,declare_missing,compose_report

    예산은 늘어나 compose_report 까지 갔는데, **답을 쓰는 다섯 번째 바퀴가
    없었다.** 이번엔 시간이 아니라 바퀴가 모자랐다.
    """

    def test_a_link_question_gets_one_more_round(self):
        self.assertEqual(
            orchestrator.rounds_for("https://www.musinsa.com/products/6503291 이거?"),
            orchestrator.MAX_ROUNDS + orchestrator.LINK_EXTRA_ROUNDS)

    def test_ordinary_questions_keep_the_same_rounds(self):
        self.assertEqual(orchestrator.rounds_for("삼바 어때?"), orchestrator.MAX_ROUNDS)

    def test_the_measured_run_now_has_a_round_left_to_write(self):
        used_rounds = 4   # 링크확인 · 지표 · 결측 · compose_report
        self.assertGreater(
            orchestrator.rounds_for("https://www.musinsa.com/products/1 이거?"),
            used_rounds)


if __name__ == "__main__":
    unittest.main()
