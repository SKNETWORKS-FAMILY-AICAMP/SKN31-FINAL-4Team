from __future__ import annotations

from .base import BaseNormalizationAdapter


class ZigzagNormalizationAdapter(BaseNormalizationAdapter):
    """
    Zigzag STEP02 입력 정책.

    source_name만 분석 입력으로 사용한다.
    기존 ProductSource.attributes/tags/observed_tags/source_name_meta는 사용하지 않는다.
    """

    source_code = "zigzag"

    def build(self, product_source) -> dict:
        return {
            "product_source_id": product_source.id,
            "source_code": self.source_code,
            "source_name": str(product_source.source_name or "").strip(),
        }
