import unittest
from unittest.mock import patch

from app import product_link


class ProductLinkTests(unittest.TestCase):
    @patch("app.product_link.llm.respond")
    def test_returns_only_structured_confirmed_fields(self, respond):
        respond.return_value = {"found": True, "item_name": "트랙 재킷",
                                "brand": "아디다스", "price_krw": 129000,
                                "source_url": "https://shop.test/p/1", "evidence": "판매가"}
        result = product_link.inspect("https://shop.test/p/1")
        self.assertEqual(result["brand"], "아디다스")
        self.assertEqual(result["price_krw"], 129000)
        self.assertTrue(result["observed_at"])
        self.assertEqual(respond.call_args.kwargs["tools"], [{"type": "web_search"}])

    @patch("app.product_link.llm.respond")
    def test_rejects_non_http_url_without_lookup(self, respond):
        result = product_link.inspect("file:///etc/passwd")
        self.assertFalse(result["found"])
        respond.assert_not_called()


if __name__ == "__main__":
    unittest.main()
