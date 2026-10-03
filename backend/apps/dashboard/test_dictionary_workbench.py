from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Brand, BrandSource, DictionaryTerm, Source, TermAlias, TermCandidate


class DictionaryWorkbenchTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_user(
            username="dictionary-ops", password="x", is_staff=True
        )
        self.client.force_login(staff)
        self.term = DictionaryTerm.objects.create(
            term_code="ITEM_DENIM",
            term_type=DictionaryTerm.TermType.ITEM,
            canonical_name="데님",
        )
        now = timezone.now()
        self.candidate = TermCandidate.objects.create(
            raw_term="데님팬츠",
            suggested_type=DictionaryTerm.TermType.ITEM,
            detected_count=8,
            source_count=2,
            document_count=5,
            nearest_term=self.term,
            first_seen_at=now - timedelta(days=3),
            last_seen_at=now,
        )

    def test_overview_terms_candidate_and_quality_pages_load(self):
        for url, marker in [
            ("/admin-dashboard/dictionary/", "패션 언어를 운영하는 곳"),
            ("/admin-dashboard/dictionary/terms/", "표준 용어"),
            (f"/admin-dashboard/dictionary/terms/{self.term.pk}/", "검증 언급"),
            ("/admin-dashboard/dictionary/candidates/", "용어 후보 검수"),
            (f"/admin-dashboard/dictionary/candidates/{self.candidate.pk}/", "검수 판정"),
            ("/admin-dashboard/dictionary/quality/", "사전 품질 점검"),
        ]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertContains(response, marker)

    def test_candidate_can_be_merged_as_alias(self):
        response = self.client.post(
            f"/admin-dashboard/dictionary/candidates/{self.candidate.pk}/review/",
            {"action": "alias", "target_term_id": self.term.pk, "note": "같은 의미"},
        )
        self.assertEqual(response.status_code, 302)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.decision, TermCandidate.Decision.ALIAS)
        self.assertEqual(self.candidate.status, TermCandidate.Status.RESOLVED)
        self.assertTrue(TermAlias.objects.filter(term=self.term, alias="데님팬츠").exists())

    def test_new_term_review_creates_canonical_term(self):
        response = self.client.post(
            f"/admin-dashboard/dictionary/candidates/{self.candidate.pk}/review/",
            {"action": "new_term", "term_type": "STYLE"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DictionaryTerm.objects.filter(term_type="STYLE", normalized_name="데님팬츠").exists()
        )

    def test_brand_search_is_server_side_and_limited(self):
        Brand.objects.create(brand_code="BRAND_ALPHA", name="알파", status=Brand.Status.ACTIVE)
        response = self.client.get("/admin-dashboard/dictionary/brands/search/?q=알파")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["name"], "알파")

    def test_brand_list_is_paginated(self):
        source = Source.objects.create(code="TEST_DICT", name="테스트")
        for number in range(35):
            BrandSource.objects.create(
                source=source,
                source_brand_id=str(number),
                name=f"브랜드 {number}",
            )
        response = self.client.get("/admin-dashboard/dictionary/brands/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["brand_sources"]), 32)
