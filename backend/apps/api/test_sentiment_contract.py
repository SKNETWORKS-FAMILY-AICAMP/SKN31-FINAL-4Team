"""Guard the ORM field used by the production sentiment endpoint."""

from datetime import datetime, timezone

from django.test import SimpleTestCase

from apps.api.views import _published_date
from apps.core.models import TextTermMention


class SentimentDocumentContractTests(SimpleTestCase):
    def test_review_published_date_can_be_selected(self):
        # /api/sentiment selects this relation for every dictionary term.
        # A model/schema mismatch used to raise FieldError before querying RDS.
        query = TextTermMention.objects.values(
            "document_id",
            "document__analysis_metadata",
            "document__source_published_at",
            "sentiment_score",
            "intent_code",
        )
        self.assertIn("source_published_at", str(query.query))

    def test_invalid_metadata_date_uses_stored_published_date(self):
        fallback = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(
            _published_date({"published_at": "2026-13-40T00:00:00"}, fallback),
            fallback.date(),
        )
