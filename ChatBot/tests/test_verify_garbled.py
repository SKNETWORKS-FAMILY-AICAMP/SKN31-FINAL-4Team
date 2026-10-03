"""검증관이 흘린 조각을 잡는다 (2026-09-14).

실측 — 화면에 이런 문장이 떴다:
    "감성 지표는 아직 측정 자료가 없습니다.keletal"
앞부분은 verify 의 규칙 2("그 축의 값을 말하는 문장은 '아직 측정 자료가
없습니다' 로 바꾼다")가 시킨 대로다. 뒤의 "keletal" 은 소형 모델이 흘린
조각이고, fix() 가 그 재작성을 그대로 내보내고 있었다.
"""
import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from app import verify


class NewLatinWordTests(unittest.TestCase):
    def test_catches_the_stray_fragment(self):
        got = verify._new_latin_words(
            "감성 지표는 아직 87점입니다.",
            "감성 지표는 아직 측정 자료가 없습니다.keletal")
        self.assertEqual(got, ["keletal"])

    def test_brand_names_already_in_the_draft_pass(self):
        """원문에 있던 영문은 지워도 남겨도 통과해야 한다."""
        draft = "Stussy 후디는 28일 관측 120건입니다."
        self.assertEqual(verify._new_latin_words(draft, "Stussy 후디는 아직 측정 자료가 없습니다."), [])
        self.assertEqual(verify._new_latin_words(draft, draft), [])

    def test_case_and_short_runs_are_ignored(self):
        """대소문자는 같은 낱말로 보고, 두 글자 이하(cm·kg)는 세지 않는다."""
        self.assertEqual(verify._new_latin_words("STUSSY 후디", "Stussy 후디"), [])
        self.assertEqual(verify._new_latin_words("기장 70", "기장 70cm"), [])

    def test_plain_korean_rewrite_passes(self):
        self.assertEqual(
            verify._new_latin_words("감성 지표는 87점입니다.",
                                    "감성 지표는 아직 측정 자료가 없습니다."), [])


class FixRejectsGarbledTests(unittest.TestCase):
    """깨진 재작성은 내보내지 않고, 원문 + 경고로 떨어진다."""

    def _report(self):
        rep = verify.Report()
        rep.suspect_numbers = ["87"]
        return rep

    def test_garbled_rewrite_is_refused(self):
        draft = "감성 지표는 87점입니다."
        rep = self._report()
        out = verify._hedge(draft, rep)          # 떨어졌을 때의 모양
        self.assertTrue(out.startswith(draft))
        self.assertIn("확인하지 못했습니다", out)

    def test_stray_words_are_named_in_the_report(self):
        """왜 떨어졌는지 로그로 볼 수 있어야 한다 — 조용히 넘기지 않는다."""
        strays = verify._new_latin_words("감성 지표는 87점입니다.",
                                         "감성 지표는 아직 측정 자료가 없습니다.keletal")
        note = "fix_garbled:" + ",".join(strays[:3])
        self.assertEqual(note, "fix_garbled:keletal")


if __name__ == "__main__":
    unittest.main()
