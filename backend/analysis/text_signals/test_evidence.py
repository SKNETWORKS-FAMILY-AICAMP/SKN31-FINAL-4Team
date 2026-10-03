from __future__ import annotations

import unittest

from .evidence import resolve_evidence


class EvidenceResolverTests(unittest.TestCase):
    def test_keeps_complete_exact_quote(self):
        text = "미쏘 코듀로이 패딩이 정말 따뜻하고 예뻐요"
        quote = "코듀로이 패딩이 정말 따뜻하고 예뻐요"
        start = text.index(quote)
        result = resolve_evidence(
            text,
            quote=quote,
            surface="코듀로이",
            start=start,
            end=start + len(quote),
        )
        self.assertEqual(result.status, "EXACT")
        self.assertEqual(text[result.start:result.end], quote)

    def test_expands_keyword_to_same_sentence(self):
        text = "다른 패딩은 그냥 봤어요. 이 패딩은 가볍고 정말 따뜻해서 추천해요!"
        second = text.rindex("패딩")
        result = resolve_evidence(
            text,
            quote="패딩",
            surface="패딩",
            start=second,
            end=second + 2,
        )
        self.assertEqual(result.status, "EXPANDED")
        self.assertIn("가볍고 정말 따뜻해서 추천해요", result.quote)
        self.assertNotIn("다른 패딩", result.quote)
        self.assertEqual(text[result.start:result.end], result.quote)

    def test_rejects_hallucinated_surface(self):
        result = resolve_evidence(
            "재질이 정말 부드러워요",
            quote="울 소재가 부드러워요",
            surface="울",
            start=0,
            end=11,
        )
        self.assertEqual(result.status, "INVALID")
        self.assertFalse(result.valid)

    def test_uses_surface_when_quote_was_rewritten(self):
        text = "브라운 색이 생각보다 칙칙해서 반품했어요"
        result = resolve_evidence(
            text,
            quote="브라운이 별로였다",
            surface="브라운",
            start=0,
            end=9,
        )
        self.assertEqual(result.status, "EXPANDED")
        self.assertIn("칙칙해서 반품", result.quote)
        self.assertEqual(text[result.start:result.end], result.quote)


if __name__ == "__main__":
    unittest.main()
