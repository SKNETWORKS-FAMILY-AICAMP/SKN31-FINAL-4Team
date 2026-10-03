"""할인률 상품명 입력 경로는 다른 축을 재집계하지 않는다."""

import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.api.views import discount_facets


class DiscountFacetSearchTest(SimpleTestCase):
    def test_items_only_skips_other_facet_aggregates(self):
        request = RequestFactory().get(
            "/api/discount/facets", {"q": "후드", "items_only": "1", "limit": "20"}
        )
        row = {"id": 17, "label": "후드", "brand": "", "source": "무신사", "thumb": None}
        with patch("apps.api.views._discount_product_rows", return_value=[row]) as items, \
             patch("apps.api.views._core_style_rows", side_effect=AssertionError("style aggregate")), \
             patch("apps.api.views._count_rows", side_effect=AssertionError("other aggregate")):
            response = discount_facets(request)

        body = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["items_only"])
        self.assertEqual(body["data"], {"item": [row]})
        self.assertFalse(body["item_has_more"])
        self.assertEqual(items.call_args.args[1:], ("후드", 21, 0))

    def test_item_page_returns_only_requested_thumbnails(self):
        request = RequestFactory().get("/api/discount/facets", {
            "q": "원피스", "items_only": "1", "item_limit": "24", "item_offset": "24",
        })
        rows = [{"id": i, "label": f"원피스 {i}", "thumb": f"https://img.example/{i}.jpg"}
                for i in range(25)]
        with patch("apps.api.views._discount_product_rows", return_value=rows) as items, \
             patch("apps.api.views._core_style_rows", side_effect=AssertionError("style aggregate")), \
             patch("apps.api.views._count_rows", side_effect=AssertionError("other aggregate")):
            response = discount_facets(request)

        body = json.loads(response.content)
        self.assertEqual(len(body["data"]["item"]), 24)
        self.assertTrue(body["item_has_more"])
        self.assertEqual(body["item_offset"], 24)
        self.assertEqual(items.call_args.args[1:], ("원피스", 25, 24))
