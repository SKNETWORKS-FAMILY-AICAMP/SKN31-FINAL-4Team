"""Evidence lookup keeps working after the 0068 schema cleanup."""

import unittest
from unittest.mock import Mock

from app.rds_store import RDSStore


class EvidenceQueryTests(unittest.TestCase):
    def test_uses_current_mention_columns_and_keeps_the_source(self):
        store = RDSStore()
        store.q = Mock(return_value=[{
            "source_code": "youtube", "doc_kind": "COMMENT",
            "body": "이 셔츠는 소재가 가볍고 여름에도 입기 좋습니다.",
            "surface": "셔츠", "sentiment": 0.8,
            "at": None, "url": "https://example.com/review",
        }])

        rows = store.term_evidence("item:셔츠")

        query = store.q.call_args.args[0]
        self.assertNotIn("evidence_status", query)
        self.assertIn("tm.mention_text IS NOT NULL", query)
        self.assertEqual(rows[0]["source_code"], "youtube")
        self.assertIn("셔츠", rows[0]["body"])
        self.assertEqual(rows[0]["url"], "https://example.com/review")


if __name__ == "__main__":
    unittest.main()
