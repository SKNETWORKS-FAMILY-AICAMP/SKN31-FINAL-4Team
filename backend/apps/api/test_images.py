"""상품 사진 주소 보정 — 세 곳이 같은 답을 내야 한다.

같은 규칙이 Django(apps/api/images.py) · Vercel 함수(frontend/api/_lib/image.js) ·
챗봇(ChatBot/app/fit.py) 에 있다. 아래 표는 그 셋의 공통 계약이다 — 한 곳을
고치면 이 표로 나머지를 맞춘다.
"""
import unittest

from apps.api.images import absolute_image_url

MUSINSA = "https://image.msscdn.net"


class AbsoluteImageUrlTests(unittest.TestCase):
    def test_musinsa_relative_paths(self):
        # 실측 27,424건의 모양
        self.assertEqual(
            absolute_image_url("thumbnails/images/goods_img/20260806/1/x_big.jpg", "MUSINSA"),
            MUSINSA + "/thumbnails/images/goods_img/20260806/1/x_big.jpg")
        # 소스 코드가 비어 와도 goods_img 는 무신사 경로다
        self.assertTrue(absolute_image_url("images/goods_img/a/b.jpg", "")
                        .startswith(MUSINSA + "/"))
        # 앞의 슬래시는 먹는다
        self.assertTrue(absolute_image_url("/goods_img/a/b.jpg", "")
                        .startswith(MUSINSA + "/"))

    def test_absolute_urls_pass_through(self):
        for url in ("https://image.msscdn.net/a.jpg",
                    "https://cf.product-image.s3.zigzag.kr/a.jpg",
                    "https://d3ha2047wt6x28.cloudfront.net/c.jpg",
                    "https://kream-phinf.pstatic.net/b.jpg"):
            self.assertEqual(absolute_image_url(url), url)

    def test_scheme_relative_becomes_https(self):
        self.assertEqual(absolute_image_url("//kream-phinf.pstatic.net/b.jpg"),
                         "https://kream-phinf.pstatic.net/b.jpg")

    def test_unknown_shape_is_not_guessed(self):
        # ★ 모르는 모양에 아무 호스트도 붙이지 않는다 — 엉뚱한 사진이 카드에 걸린다.
        self.assertIsNone(absolute_image_url("uploads/2026/unknown.jpg"))
        self.assertIsNone(absolute_image_url("data/x.png", "ZIGZAG"))

    def test_empty_stays_empty(self):
        for value in (None, "", "   "):
            self.assertIsNone(absolute_image_url(value))


if __name__ == "__main__":
    unittest.main()
