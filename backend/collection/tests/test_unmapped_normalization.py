from __future__ import annotations

from unittest import TestCase

from collection.ably.normalization import normalize_ably_preview
from collection.musinsa_used.normalization import normalize_musinsa_used_preview


class UnmappedNormalizationTests(TestCase):
    def assert_unmapped_boundary(self, preview: dict) -> None:
        targets = preview["targets"]
        brand = targets["brand_source"]
        category = targets["category_source"]
        product = targets["product_source"]

        self.assertEqual(brand["mapping_status"], "UNMAPPED")
        self.assertIsNone(brand["brand_id"])
        self.assertIsNone(category["category_id"])
        self.assertEqual(product["mapping_status"], "UNMAPPED")
        self.assertIsNone(product["product_id"])
        self.assertNotIn("normalized_name", product)
        self.assertNotIn("normalized_name_candidate", product.get("_derived", {}))

    def test_ably_preview_stops_before_feedit_mapping(self):
        preview = normalize_ably_preview(
            {
                "source_product_id": "ably-1",
                "name": "  원본   상품명  ",
                "brand": {"source_brand_id": "brand-1", "name": "브랜드"},
                "category": {"source_category_id": "cat-1", "name": "상의"},
            }
        )

        self.assert_unmapped_boundary(preview)
        self.assertEqual(
            preview["targets"]["product_source"]["source_name"],
            "원본 상품명",
        )

    def test_musinsa_used_preview_stops_before_feedit_mapping(self):
        preview = normalize_musinsa_used_preview(
            {
                "brand": {"brand_code": "brand-1", "name_ko": "브랜드"},
                "product": {
                    "goods_no": "used-1",
                    "name": "  중고   상품명  ",
                    "category": {
                        "depth1_code": "1",
                        "depth1_name": "상의",
                    },
                },
            }
        )

        self.assert_unmapped_boundary(preview)
        self.assertEqual(
            preview["targets"]["product_source"]["source_name"],
            "중고 상품명",
        )

