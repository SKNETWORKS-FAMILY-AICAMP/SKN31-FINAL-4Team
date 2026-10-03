"""리세일 상품 검색은 표준상품 FK를 기준으로 묶고 실제 값이 있는 플랫폼만 보여 준다."""

import json
from datetime import timedelta
from decimal import Decimal

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.api.views import resale, resale_products
from apps.core.models import Brand, Category, Product, ProductSource, ProductSourceSnapshot, ResaleSnapshot, Source


class ResaleProductSearchTest(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.musinsa = Source.objects.create(
            code="musinsa_test", name="무신사", source_type="COMMERCE"
        )
        self.used = Source.objects.create(
            code="musinsa_used_test", name="무신사 USED", source_type="COMMERCE"
        )
        self.kream = Source.objects.create(
            code="kream_test", name="크림", source_type="COMMERCE"
        )
        self.brand = Brand.objects.create(brand_code="BRAND_TEST", name="테스트브랜드")
        self.category = Category.objects.create(code="CATEGORY_TEST", name="쇼츠")
        self.product = Product.objects.create(
            product_code="FDT-P-TEST-1",
            canonical_name="테스트 에어포스 블랙",
            normalized_name="테스트 에어포스 블랙",
            brand=self.brand,
            category=self.category,
        )
        # mapping_status가 아직 UNMAPPED여도 product FK가 실제 연결 기준이다.
        self.retail = ProductSource.objects.create(
            product=self.product,
            source=self.musinsa,
            source_product_id="retail-1",
            source_name="테스트 에어포스 블랙",
            style_no="TEST-001",
            market_type="RETAIL",
            mapping_status="UNMAPPED",
            thumbnail_url="https://img.example/fallback.jpg",
        )
        ProductSourceSnapshot.objects.create(
            product_source=self.retail,
            observed_at=self.now,
            list_price=Decimal("100000"),
            sale_price=Decimal("90000"),
        )
        self.used_listing = ProductSource.objects.create(
            product=self.product,
            source=self.used,
            source_product_id="used-1",
            source_name="테스트 에어포스 블랙 270",
            style_no="TEST-001",
            market_type="RESALE",
            mapping_status="UNMAPPED",
        )
        ResaleSnapshot.objects.create(
            product_source=self.used_listing,
            observed_at=self.now,
            listing_count=1,
            available_count=1,
            min_price=Decimal("60000"),
            median_price=Decimal("60000"),
            market_metrics={"regular_price": 100000, "condition_grade": "A"},
        )
        # 같은 표준상품이어도 값이 전혀 없는 플랫폼 카드는 숨겨야 한다.
        ProductSource.objects.create(
            product=self.product,
            source=self.kream,
            source_product_id="kream-no-snapshot",
            source_name="테스트 에어포스 블랙",
            style_no="TEST-001",
            market_type="RESALE",
            mapping_status="UNMAPPED",
        )

    def test_product_search_returns_canonical_product_and_connected_platforms(self):
        response = resale_products(RequestFactory().get(
            "/api/resale/products", {"q": "TEST-001"}
        ))
        body = json.loads(response.content)

        self.assertEqual(body["status"], "ok")
        item = body["data"]["items"][0]
        self.assertEqual(item["type"], "product")
        self.assertEqual(item["id"], self.product.id)
        self.assertEqual(item["code"], "FDT-P-TEST-1")
        self.assertEqual(item["model_code"], "TEST-001")
        self.assertEqual(
            {row["name"] for row in item["platforms"]},
            {"무신사", "무신사 USED", "크림"},
        )

    def test_category_selection_lists_matching_products_without_name_query(self):
        response = resale_products(RequestFactory().get(
            "/api/resale/products", {"kind": "쇼츠"}
        ))
        body = json.loads(response.content)

        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["items"][0]["id"], self.product.id)
        self.assertEqual(body["data"]["selection"]["kind"], ["쇼츠"])

    def test_short_canonical_name_keeps_original_and_uses_descriptive_source_name(self):
        product = Product.objects.create(
            product_code="FDT-P-SHORT", canonical_name="블랙", normalized_name="블랙"
        )
        source = ProductSource.objects.create(
            product=product,
            source=self.kream,
            source_product_id="short-1",
            source_name="나이키 P-6000 블랙",
            style_no="CD6404-002",
            market_type="RESALE",
        )
        ResaleSnapshot.objects.create(
            product_source=source, observed_at=self.now, median_price=Decimal("70000")
        )

        body = json.loads(resale_products(RequestFactory().get(
            "/api/resale/products", {"q": "CD6404-002"}
        )).content)
        item = body["data"]["items"][0]
        self.assertEqual(item["canonical_name"], "블랙")
        self.assertEqual(item["name"], "나이키 P-6000 블랙")
        self.assertEqual(item["model_code"], "CD6404-002")

    def test_exact_product_uses_product_fk_even_when_mapping_status_is_unmapped(self):
        # 관측일을 세 날짜로 만들어 응답의 기간·신뢰도 계산도 실제 경로로 지난다.
        for days in (1, 2):
            ResaleSnapshot.objects.create(
                product_source=self.used_listing,
                observed_at=self.now - timedelta(days=days),
                median_price=Decimal("60000"),
                market_metrics={"regular_price": 100000, "condition_grade": "A"},
            )

        response = resale(RequestFactory().get(
            "/api/resale", {"product_id": str(self.product.id), "days": "90"}
        ))
        body = json.loads(response.content)

        self.assertEqual(body["status"], "ok")
        data = body["data"]
        self.assertEqual(data["analysis_scope"], "product")
        self.assertEqual(data["product"]["id"], self.product.id)
        self.assertTrue(data["product"]["mapped"])
        self.assertEqual(data["regular_price"], 90000.0)
        self.assertEqual(data["used_price"], 60000.0)
        self.assertEqual(data["keep_pct"], 66.7)
        self.assertEqual(
            {row["name"] for row in data["platform_cards"]},
            {"무신사", "무신사 USED"},
        )
        self.assertNotIn("크림", data["mapping"]["platforms"])

    def test_unmapped_source_stays_platform_only(self):
        solo = ProductSource.objects.create(
            source=self.used,
            source_product_id="solo-1",
            source_name="단독 빈티지 재킷",
            market_type="RESALE",
        )
        ResaleSnapshot.objects.create(
            product_source=solo,
            observed_at=self.now,
            median_price=Decimal("45000"),
        )

        search = json.loads(resale_products(RequestFactory().get(
            "/api/resale/products", {"q": "단독 빈티지"}
        )).content)
        self.assertEqual(search["data"]["items"][0]["type"], "platform_only")

        detail = json.loads(resale(RequestFactory().get(
            "/api/resale", {"source_id": str(solo.id)}
        )).content)
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail["data"]["analysis_scope"], "platform_only")
        self.assertFalse(detail["data"]["product"]["mapped"])
        self.assertEqual([row["name"] for row in detail["data"]["platform_cards"]], ["무신사 USED"])

    def test_product_image_skips_invalid_url_and_uses_next_connected_source(self):
        self.used_listing.thumbnail_url = "uploads/not-public/used.jpg"
        self.used_listing.save(update_fields=["thumbnail_url"])

        body = json.loads(resale_products(RequestFactory().get(
            "/api/resale/products", {"q": "TEST-001"}
        )).content)

        self.assertEqual(body["data"]["items"][0]["image"], "https://img.example/fallback.jpg")

    def test_brand_analysis_returns_real_resale_recommendation_pool(self):
        response = resale(RequestFactory().get(
            "/api/resale", {"brand": "테스트브랜드", "days": "90"}
        ))
        body = json.loads(response.content)

        self.assertEqual(body["status"], "ok")
        data = body["data"]
        self.assertEqual(data["analysis_scope"], "brand")
        self.assertLessEqual(len(data["recommendations"]), 15)
        self.assertEqual(data["recommendations"][0]["platform"], "무신사 USED")
        # USED 자체 이미지가 없어도 같은 표준상품의 정상 이미지를 쓴다.
        self.assertEqual(data["recommendations"][0]["image"], "https://img.example/fallback.jpg")
        self.assertTrue(data["md_signals"])
        self.assertIsNotNone(data["volume_4w"])

    def test_used_recommendation_sums_current_listings_for_the_same_product(self):
        second_listing = ProductSource.objects.create(
            product=self.product,
            source=self.used,
            source_product_id="used-2",
            source_name="테스트 에어포스 블랙 275",
            style_no="TEST-001",
            market_type="RESALE",
            mapping_status="UNMAPPED",
        )
        ResaleSnapshot.objects.create(
            product_source=second_listing,
            observed_at=self.now,
            listing_count=1,
            available_count=1,
            median_price=Decimal("62000"),
            market_metrics={"regular_price": 100000, "is_sold_out": False},
        )

        data = json.loads(resale(RequestFactory().get(
            "/api/resale", {"brand": "테스트브랜드", "days": "90"}
        )).content)["data"]
        recommendation = next(row for row in data["recommendations"]
                              if row["product_id"] == self.product.id)

        self.assertEqual(recommendation["platform"], "무신사 USED")
        self.assertEqual(recommendation["listing_count"], 2)
        self.assertEqual(recommendation["price"], 61000.0)

    def test_kream_observed_ask_quantities_are_used_as_partial_listing_count(self):
        kream_source = ProductSource.objects.get(source_product_id="kream-no-snapshot")
        ResaleSnapshot.objects.create(
            product_source=kream_source,
            observed_at=self.now,
            lowest_ask=Decimal("61000"),
            market_metrics={
                "coverage": {"asks_complete": False, "listings_complete": False},
                "sample_asks": [
                    {"size": "M", "price": 61000, "quantity": 2},
                    {"size": "L", "price": 62000, "quantity": 4},
                ],
                "sample_listings": [],
                "sample_statistics": {"listing_sample_count": 0},
            },
        )

        detail = json.loads(resale(RequestFactory().get(
            "/api/resale", {"product_id": str(self.product.id), "days": "90"}
        )).content)["data"]
        kream_card = next(row for row in detail["platform_cards"] if row["name"] == "크림")
        self.assertEqual(kream_card["listing_count"], 6)
        self.assertTrue(kream_card["listing_count_partial"])
        self.assertEqual(detail["current_listing_count"], 7)
        self.assertTrue(detail["current_listing_count_partial"])

        brand = json.loads(resale(RequestFactory().get(
            "/api/resale", {"brand": "테스트브랜드", "days": "90"}
        )).content)["data"]
        recommendation = next(row for row in brand["recommendations"]
                              if row["product_id"] == self.product.id)
        self.assertEqual(recommendation["platform"], "크림")
        self.assertEqual(recommendation["listing_count"], 6)
        self.assertTrue(recommendation["listing_count_partial"])

    def test_condition_grades_follow_quality_order_not_row_count(self):
        for days, grade in enumerate(("B", "S", "A+"), start=1):
            ResaleSnapshot.objects.create(
                product_source=self.used_listing,
                observed_at=self.now - timedelta(days=days),
                median_price=Decimal("55000"),
                market_metrics={"regular_price": 100000, "condition_grade": grade},
            )

        body = json.loads(resale(RequestFactory().get(
            "/api/resale", {"product_id": str(self.product.id), "days": "90"}
        )).content)

        self.assertEqual(
            [row["label"] for row in body["data"]["grades"]],
            ["S", "A+", "A", "B"],
        )
