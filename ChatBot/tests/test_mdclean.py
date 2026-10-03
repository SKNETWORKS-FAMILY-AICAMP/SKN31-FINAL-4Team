"""모델 내부 인용 표식이 사용자 문장으로 새지 않는지 본다."""
import unittest

from app import mdclean


class CitationCleanupTests(unittest.TestCase):
    def test_private_use_web_citation_marker_is_removed_from_html(self):
        raw = "고프코어를 확인했습니다. \ue200cite\ue202turn0search0\ue201"
        html = mdclean.to_html(raw)
        self.assertIn("고프코어를 확인했습니다.", html)
        self.assertNotIn("cite", html)
        self.assertNotIn("turn0search0", html)

    def test_visible_fallback_citation_marker_is_removed(self):
        raw = "자료가 적습니다. ▤cite▤turn0search0▤"
        converted = mdclean.convert(raw)
        self.assertEqual(converted["text"], "자료가 적습니다.")

    def test_normal_use_of_cite_word_is_not_removed(self):
        raw = "문서에서 cite라는 단어를 설명합니다."
        self.assertIn("cite라는", mdclean.convert(raw)["text"])


if __name__ == "__main__":
    unittest.main()
