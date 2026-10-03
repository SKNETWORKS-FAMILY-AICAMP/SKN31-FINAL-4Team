"""데이터 품질 화면 (DATA_QUALITY-001·002·003, 2026-09-27)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.core.models import (
    Brand, CrawlRun, Product, ProductSource, ProductSourceSnapshot, RawDocument, Source,
)
from apps.dashboard.services.data_quality import (
    data_quality_context, duplicate_brands, duplicate_products, duplicate_raw_documents,
    missing_by_source, normalization_by_source,
)


def _source(code):
    return Source.objects.create(code=code, name=code, source_type="COMMERCE")


def _raw(source, run, key, hash_=None, status="SUCCESS"):
    return RawDocument.objects.create(source=source, crawl_run=run, document_type="RANKING",
                                      s3_bucket="b", s3_key=key, content_hash=hash_,
                                      collected_at=timezone.now(), normalization_status=status)


class MissingTests(TestCase):
    def setUp(self):
        self.s = _source("dq_a")
        self.brand = Brand.objects.create(brand_code="B1", name="브랜드")
        full = ProductSource.objects.create(
            source=self.s, source_product_id="1", source_brand_id=None,
            thumbnail_url="https://img/1.jpg", product_url="https://p/1")
        ProductSourceSnapshot.objects.create(product_source=full, observed_at=timezone.now())
        ProductSource.objects.create(source=self.s, source_product_id="2", thumbnail_url="")

    def _cell(self, key):
        row = missing_by_source()[0]
        return next(c for c in row["cells"] if c["key"] == key)

    def test_플랫폼별로_센다(self):
        rows = missing_by_source()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total"], 2)

    def test_빈_문자열도_누락이다(self):
        self.assertEqual(self._cell("thumbnail")["count"], 1)
        self.assertEqual(self._cell("thumbnail")["pct"], 50.0)

    def test_가격은_스냅숏이_없는_상품을_센다(self):
        self.assertEqual(self._cell("price")["count"], 1)

    def test_기준_이상은_경고로_표시(self):
        self.assertTrue(self._cell("brand")["warn"])      # 2개 다 비었다 → 100%

    def test_상품이_없는_플랫폼은_빼고_보인다(self):
        _source("dq_empty")
        self.assertEqual([r["source"].code for r in missing_by_source()], ["dq_a"])


class DuplicateTests(TestCase):
    def test_같은_브랜드_같은_정규화_이름만_중복이다(self):
        b1 = Brand.objects.create(brand_code="B1", name="나이키")
        b2 = Brand.objects.create(brand_code="B2", name="아디다스")
        for _ in range(3):
            Product.objects.create(brand=b1, canonical_name="에어 포스", normalized_name="에어포스")
        Product.objects.create(brand=b2, canonical_name="에어 포스", normalized_name="에어포스")   # 다른 브랜드
        Product.objects.create(brand=b1, canonical_name="덩크", normalized_name="덩크")
        got = duplicate_products()
        self.assertEqual(got["groups"], 1)
        self.assertEqual(got["extra_rows"], 2)
        self.assertEqual(got["top"][0]["brand"], "나이키")
        self.assertEqual(len(got["top"][0]["ids"]), 3)

    def test_빈_이름은_중복으로_세지_않는다(self):
        Product.objects.create(canonical_name="a", normalized_name="")
        Product.objects.create(canonical_name="b", normalized_name="")
        self.assertEqual(duplicate_products()["groups"], 0)

    def test_브랜드는_대소문자와_앞뒤_공백을_무시한다(self):
        Brand.objects.create(brand_code="N1", name="Nike")
        Brand.objects.create(brand_code="N2", name=" nike ")
        Brand.objects.create(brand_code="N3", name="Nikes")
        got = duplicate_brands()
        self.assertEqual(got["groups"], 1)
        self.assertEqual(got["top"][0]["n"], 2)

    def test_같은_원본을_두_번_받은_문서(self):
        s, other = _source("dq_r"), _source("dq_r2")
        run = CrawlRun.objects.create(source=s, run_type="LIVE")
        run2 = CrawlRun.objects.create(source=other, run_type="LIVE")
        _raw(s, run, "k1", "h1"); _raw(s, run, "k2", "h1"); _raw(s, run, "k3", "h1")
        _raw(s, run, "k4", "h2")
        _raw(other, run2, "k5", "h1")        # 다른 플랫폼의 같은 해시는 중복이 아니다
        _raw(s, run, "k6", None); _raw(s, run, "k7", None)   # 해시가 없으면 셀 수 없다
        rows = duplicate_raw_documents()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["hashes"], rows[0]["extra"]), (1, 2))


class NormalizationTests(TestCase):
    def test_플랫폼별_정규화_상태(self):
        s = _source("dq_n")
        run = CrawlRun.objects.create(source=s, run_type="LIVE")
        _raw(s, run, "a", status="SUCCESS"); _raw(s, run, "b", status="FAILED")
        _raw(s, run, "c", status="PENDING"); _raw(s, run, "d", status="PROCESSING")
        row = normalization_by_source()[0]
        self.assertEqual((row["total"], row["success"], row["failed"], row["pending"]), (4, 1, 1, 2))
        self.assertEqual(row["fail_pct"], 25.0)
        self.assertTrue(row["warn"])


class ScreenTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(username="ops", password="pw-ops-12345", is_staff=True)
        self.normal = User.objects.create_user(username="n", password="pw-n-12345", is_staff=False)

    def test_운영_계정은_열린다(self):
        c = Client(); c.force_login(self.staff)
        s = _source("dq_s")
        ProductSource.objects.create(source=s, source_product_id="1")
        res = c.get("/admin-dashboard/normalization/quality/")
        self.assertEqual(res.status_code, 200)
        html = res.content.decode()
        for text in ("누락 — 플랫폼별 빈 칸", "중복 — 통합 상품", "정규화 상태 — 플랫폼별", "가격 관측"):
            self.assertIn(text, html)

    def test_빈_DB에서도_열린다(self):
        c = Client(); c.force_login(self.staff)
        res = c.get("/admin-dashboard/normalization/quality/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("플랫폼 상품이 아직 적재되지 않았습니다", res.content.decode())
        self.assertEqual(data_quality_context()["summary"]["product_sources"], 0)

    def test_일반_회원은_못_연다(self):
        c = Client(); c.force_login(self.normal)
        self.assertEqual(c.get("/admin-dashboard/normalization/quality/").status_code, 403)
