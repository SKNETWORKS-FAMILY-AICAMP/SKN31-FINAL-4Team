"""무신사 유즈드 RAW 의 relations 가 ProductSourceRelation 으로 적재된다 (2026-10-04).

[파이프라인 연동] 뒤로 relations 는 개수만 세고 버려지고 있었다.
유즈드 매물 → 무신사 원상품(RESALE_OF) 연결을 다시 남긴다.
"""
from unittest import mock

from django.test import TestCase

from apps.core.models import (
    CrawlRun, CrawlTarget, ProductSource, ProductSourceRelation, RawDocument, Source,
)
from pipeline.step01_ingestion import musinsa_used
from pipeline.step01_ingestion.musinsa_used import (
    MusinsaUsedIngestion, persist_product_source_relations,
)


def _relation(used_no, original_no, **extra):
    return {
        "from_source": "musinsa_used_rt",
        "from_source_product_id": used_no,
        "to_source": "musinsa_rt",
        "to_source_product_id": original_no,
        "relation_type": "RESALE_OF",
        "evidence_source": "MUSINSA_RELATED_GOODS",
        **extra,
    }


class PersistRelationTests(TestCase):
    def setUp(self):
        self.used = Source.objects.create(code="musinsa_used_rt", name="무신사 유즈드", source_type="COMMERCE")
        self.musinsa = Source.objects.create(code="musinsa_rt", name="무신사", source_type="COMMERCE")
        self.u1 = ProductSource.objects.create(source=self.used, source_product_id="U1", market_type="RESALE")
        self.m1 = ProductSource.objects.create(source=self.musinsa, source_product_id="M1", market_type="RETAIL")

    def test_유즈드_매물과_원상품을_잇는다(self):
        result = persist_product_source_relations([_relation("U1", "M1")])

        self.assertEqual(result["created"], 1)
        rel = ProductSourceRelation.objects.get()
        self.assertEqual((rel.from_product_source, rel.to_product_source), (self.u1, self.m1))
        self.assertEqual(rel.relation_type, "RESALE_OF")
        self.assertEqual(rel.evidence_source, "MUSINSA_RELATED_GOODS")

    def test_같은_RAW_를_다시_돌려도_한_번만_남는다(self):
        persist_product_source_relations([_relation("U1", "M1")])
        result = persist_product_source_relations([_relation("U1", "M1"), _relation("U1", "M1")])

        self.assertEqual((result["created"], result["existing"]), (0, 1))
        self.assertEqual(ProductSourceRelation.objects.count(), 1)

    def test_원상품이_아직_없으면_건너뛴다(self):
        result = persist_product_source_relations([_relation("U1", "M-없음")])

        self.assertEqual((result["created"], result["skipped"]), (0, 1))
        self.assertEqual(result["skipped_relations"][0]["skip_reason"], "PRODUCT_SOURCE_NOT_FOUND")
        self.assertFalse(ProductSourceRelation.objects.exists())

    def test_모르는_관계유형과_빈_키는_건너뛴다(self):
        result = persist_product_source_relations([
            _relation("U1", "M1", relation_type="SIMILAR"),
            _relation("", "M1"),
        ])

        self.assertEqual((result["created"], result["skipped"]), (0, 2))

    def test_소스_코드_표기가_달라도_찾는다(self):
        result = persist_product_source_relations([
            _relation("U1", "M1", from_source="MUSINSA-USED-RT", to_source="Musinsa_RT"),
        ])

        self.assertEqual(result["created"], 1)


class IngestionRunTests(TestCase):
    """run() 이 상품을 먼저 적재한 뒤 relations 를 저장하고 통계에 남긴다."""

    def setUp(self):
        # run() 은 source.code 가 정확히 'musinsa_used' 인 RAW 만 받는다.
        self.used, _ = Source.objects.get_or_create(
            code="musinsa_used", defaults={"name": "무신사 유즈드", "source_type": "COMMERCE"},
        )
        self.musinsa = Source.objects.create(code="musinsa_rt", name="무신사", source_type="COMMERCE")
        self.m1 = ProductSource.objects.create(source=self.musinsa, source_product_id="M1", market_type="RETAIL")
        target = CrawlTarget.objects.create(source=self.used, name="유즈드 필터", target_type="RANKING")
        run = CrawlRun.objects.create(source=self.used, crawl_target=target, run_type="LIVE")
        self.raw = RawDocument.objects.create(
            source=self.used, crawl_run=run, document_type="RANKING", s3_key="test/used.json",
        )

    def test_적재된_유즈드_상품과_원상품이_연결된다(self):
        payload = {
            "products": [{
                "product": {"goods_no": "U1", "name": "테스트 셔츠"},
                "snapshot": {"sale_price": 30000},
                "ranking_context": {"observation_type": "FILTER", "filter_type": "COLOR", "filter_name": "블랙"},
            }],
            "related_products": {"musinsa_used": [], "musinsa": []},
            "relations": [{
                "from_source": "musinsa_used", "from_source_product_id": "U1",
                "to_source": "musinsa_rt", "to_source_product_id": "M1",
                "relation_type": "RESALE_OF", "evidence_source": "MUSINSA_RELATED_GOODS",
            }],
        }
        with mock.patch.object(musinsa_used, "get_s3_client", return_value=None), \
                mock.patch.object(musinsa_used, "load_raw_json", return_value=payload), \
                mock.patch.object(musinsa_used, "extract_payload", side_effect=lambda raw: raw):
            stats = MusinsaUsedIngestion().run(raw_document_id=self.raw.id)

        self.assertEqual(stats["failed"], 0, stats["errors"])
        self.assertEqual(stats["relation_created"], 1)
        rel = ProductSourceRelation.objects.get()
        self.assertEqual(rel.from_product_source.source_product_id, "U1")
        self.assertEqual(rel.to_product_source, self.m1)
