"""추천 웹매거진 — 도구가 인용한 기사 주소만 남기는지 확인한다."""
import unittest
from unittest.mock import patch

from app import magazine


def reply(articles, cited):
    return {"articles": articles, "_raw_sources": [{"url": u, "title": "t"} for u in cited]}


class MagazineTests(unittest.TestCase):
    def setUp(self):
        magazine._cache.clear()

    @patch("app.magazine._page_exists", return_value=False)
    @patch("app.magazine.llm.available", return_value=True)
    @patch("app.magazine.llm.respond")
    def test_keeps_only_cited_magazine_articles(self, respond, _, __):
        respond.return_value = reply([
            {"magazine": "보그", "title": "발레코어의 귀환", "url": "https://www.vogue.co.kr/2026/09/01/ballet?utm_source=openai"},
            {"magazine": "지어낸 매체", "title": "없는 기사", "url": "https://fake.example/a/1"},        # 인용 안 됨
            {"magazine": "유튜브", "title": "영상", "url": "https://www.youtube.com/watch?v=1"},          # 매거진 아님
            {"magazine": "무신사", "title": "상품", "url": "https://www.musinsa.com/products/123"},       # 상품 페이지
            {"magazine": "엘르", "title": "첫 화면", "url": "https://www.elle.co.kr/"},                   # 기사 아님
        ], ["https://www.vogue.co.kr/2026/09/01/ballet", "https://www.youtube.com/watch?v=1",
            "https://www.musinsa.com/products/123", "https://www.elle.co.kr/"])
        r = magazine.find("발레코어")
        self.assertEqual([a["title"] for a in r["articles"]], ["발레코어의 귀환"])
        self.assertEqual(r["articles"][0]["url"], "https://www.vogue.co.kr/2026/09/01/ballet")
        self.assertEqual(respond.call_args.kwargs["tools"], [{"type": "web_search"}])

    @patch("app.magazine.llm.available", return_value=True)
    @patch("app.magazine.llm.respond")
    def test_caches_success_but_not_failure(self, respond, _):
        respond.return_value = None
        self.assertFalse(magazine.find("고프코어")["found"])
        respond.return_value = reply([{"magazine": "GQ", "title": "고프코어", "url": "https://www.gqkorea.co.kr/a/1"}],
                                     ["https://www.gqkorea.co.kr/a/1"])
        self.assertTrue(magazine.find("고프코어")["found"])
        self.assertTrue(magazine.find("고프코어")["cached"])
        self.assertEqual(respond.call_count, 2)

    @patch("app.magazine.llm.available", return_value=True)
    @patch("app.magazine.llm.respond")
    def test_uncited_but_real_page_is_kept(self, respond, _):
        """인용 표시(annotation)가 비어도, 직접 열어 본 페이지가 있으면 올린다."""
        url = "https://www.wkorea.com/2023/02/10/올봄엔-우리-모두-발레리나가-될지어니/"
        respond.return_value = reply([{"magazine": "W Korea", "title": "올봄엔 우리 모두 발레리나가 될지어니", "url": url},
                                      {"magazine": "W Korea", "title": "없는 기사", "url": "https://www.wkorea.com/nope/1"}], [])
        with patch("app.magazine._page_exists", side_effect=lambda u, **k: "nope" not in u):
            r = magazine.find("발레코어")
        self.assertEqual([a["magazine"] for a in r["articles"]], ["W Korea"])

    @patch("app.magazine.llm.available", return_value=True)
    @patch("app.magazine.llm.respond")
    def test_empty_result_is_not_cached(self, respond, _):
        respond.return_value = reply([], [])
        magazine.find("발레코어"); magazine.find("발레코어")
        self.assertEqual(respond.call_count, 2)

    def test_empty_term(self):
        self.assertFalse(magazine.find("  ")["found"])


if __name__ == "__main__":
    unittest.main()
