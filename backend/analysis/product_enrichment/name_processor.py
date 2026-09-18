from __future__ import annotations

from typing import Any

from analysis.source_ingestion.common import normalize_product_name
from analysis.source_ingestion.product_name_preprocessor import (
    ProductNamePreprocessor,
)


class ProductNameProcessor:
    def __init__(self):
        self.preprocessor = ProductNamePreprocessor()

    def process(
        self,
        *,
        source_name: str | None,
        source_code: str,
        existing_tags: list | tuple | None = None,
    ) -> dict[str, Any]:

        tags = (
            list(existing_tags)
            if isinstance(existing_tags, (list, tuple))
            else []
        )

        parsed = self.preprocessor.parse(
            source_name or "",
            existing_tags=tags,
            source_code=(source_code or "").upper(),
        )

        clean_name = parsed.get("source_name") or ""

        return {
            "raw_name": source_name or "",
            "clean_name": clean_name,
            "normalized_name": normalize_product_name(clean_name) or "",
            "tags": parsed.get("tags") or [],
            "source_name_meta": parsed.get("source_name_meta") or {},
        }
