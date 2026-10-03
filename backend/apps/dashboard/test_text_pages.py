from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.core.models import (
    ContentItem,
    CrawlRun,
    DictionaryTerm,
    RawDocument,
    Source,
    TextDocument,
    TextTermMention,
)


class DashboardTextPageTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="text-ops",
            password="x",
            is_staff=True,
        )
        self.client.force_login(user)
        self.youtube = Source.objects.create(
            code="YOUTUBE",
            name="YouTube",
            source_type=Source.SourceType.CONTENT,
        )
        self.naver_search = Source.objects.create(
            code="NAVER_SEARCH",
            name="네이버 검색",
            source_type=Source.SourceType.SEARCH,
        )
        self.naver = Source.objects.create(
            code="naver",
            name="네이버",
            source_type=Source.SourceType.CONTENT,
        )
        content = ContentItem.objects.create(
            source=self.youtube,
            content_type=ContentItem.ContentType.VIDEO,
            title="데님 코디 추천",
            external_content_id="video-1",
            content_url="https://www.youtube.com/watch?v=video-1",
            thumbnail_url="https://i.ytimg.com/vi/video-1/hqdefault.jpg",
            description="출근할 때 입기 좋은 민트색 나이키 재킷입니다.",
            content_format=ContentItem.ContentFormat.RECOMMEND,
            ad_disclosure=ContentItem.AdDisclosure.NONE,
            analysis_tags={
                "item": ["재킷"],
                "style": [],
                "material": [],
                "detail": [],
                "color": ["민트"],
                "tpo": ["출근룩"],
                "brand": ["나이키"],
                "products": ["민트 러닝 재킷"],
                "candidates": [{"term": "출근꾸안꾸", "guess": "STYLE"}],
            },
        )
        document = TextDocument.objects.create(
            source=self.youtube,
            content_item=content,
            document_type=TextDocument.DocumentType.COMMENT,
            external_id="comment-1",
            body="청바지 핏이 정말 예뻐요.",
            analysis_status=TextDocument.AnalysisStatus.DONE,
        )
        term = DictionaryTerm.objects.create(
            term_code="ITEM_JEANS_TEXT_TEST",
            term_type=DictionaryTerm.TermType.ITEM,
            canonical_name="청바지",
        )
        TextTermMention.objects.create(
            document=document,
            term=term,
            mention_text="청바지",
            mention_role=TextTermMention.MentionRole.COMMENT,
            sentiment_score=Decimal("0.75000"),
            confidence=Decimal("0.98000"),
        )

    def test_유튜브_댓글과_분석_용어를_조회한다(self):
        response = self.client.get("/admin-dashboard/text/youtube/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "유튜브 댓글·자막")
        self.assertContains(response, "청바지 핏이 정말 예뻐요.")
        self.assertContains(response, "청바지")
        self.assertContains(response, "데님 코디 추천")
        self.assertContains(response, "긍정 1")

    def test_유튜브_영상의_jsonb_태그와_본문을_상세로_보인다(self):
        response = self.client.get("/admin-dashboard/normalized/youtube/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "민트")
        self.assertContains(response, "출근룩")
        self.assertContains(response, "나이키")
        self.assertContains(response, "민트 러닝 재킷")
        self.assertContains(response, "출근꾸안꾸")
        self.assertContains(response, "추천")
        self.assertContains(response, "표기 없음")
        self.assertContains(response, "analysis_tags 원본")

    def test_텍스트_목록은_행_수와_무관하게_쿼리가_제한된다(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/admin-dashboard/text/youtube/")

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 12)

    def test_원본_목록은_실제_문서가_있는_소스만_필터로_노출한다(self):
        run = CrawlRun.objects.create(
            source=self.youtube,
            run_type=CrawlRun.RunType.MANUAL,
            status=CrawlRun.Status.SUCCESS,
        )
        RawDocument.objects.create(
            source=self.youtube,
            crawl_run=run,
            document_type="COMMENT",
            s3_bucket="test-bucket",
            s3_key="raw/youtube/comment-1.json",
        )

        response = self.client.get("/admin-dashboard/collection/raw-documents/")

        self.assertEqual(response.status_code, 200)
        source_codes = [source.code for source in response.context["sources"]]
        self.assertEqual(source_codes, ["YOUTUBE"])
        self.assertNotContains(response, "네이버 검색")

    def test_등록된_소스에_텍스트가_없으면_빈_상태를_보인다(self):
        response = self.client.get("/admin-dashboard/text/naver/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "아직 적재된 텍스트가 없습니다")

    def test_검증_mention이_없어도_jsonb_전처리_후보를_보인다(self):
        document = TextDocument.objects.filter(source=self.youtube).first()
        document.term_mentions.all().delete()
        document.analysis_metadata = {
            "intent": "CRITIQUE",
            "target": "PRODUCT",
            "candidates": [
                {"term": "소매기장", "guess": "DETAIL"},
                {"surface": "소매기장", "type": "DETAIL"},
            ],
            "analysis": {
                "model": "gpt-test",
                "pipeline_version": "text-signals-v2",
            },
        }
        document.save(update_fields=["analysis_metadata"])

        response = self.client.get("/admin-dashboard/text/youtube/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "전처리 후보")
        self.assertEqual(response.context["rows"][0].candidate_keywords, [
            {"keyword": "소매기장", "kind": "DETAIL"}
        ])
        self.assertContains(response, "소매기장")
        self.assertContains(response, "CRITIQUE")
        self.assertContains(response, "text-signals-v2")
