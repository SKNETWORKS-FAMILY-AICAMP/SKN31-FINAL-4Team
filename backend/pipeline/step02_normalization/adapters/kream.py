from __future__ import annotations

from typing import Any


class KreamNormalizationAdapter:

    source_code = "kream"

    def build(
        self,
        product_source,
    ) -> dict[str, Any]:

        return {
            "product_source_id": product_source.id,
            "source_code": self.source_code,
            "source_name": str(
                product_source.source_name
                or ""
            ).strip(),
            "source_tags": [],
            "source_options": {},
            "source_attributes": {},
        }