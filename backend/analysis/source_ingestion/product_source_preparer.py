from __future__ import annotations

from copy import deepcopy

from apps.core.models import ProductSource

from .product_name_preprocessor import ProductNamePreprocessor


class ProductSourcePreparer:
    """
    SOURCE INGESTION 마지막 단계.

    ProductSource.source_name:
        RAW 상품명에서 1차 노이즈를 분리한 상품명

    ProductSource.attributes["tags"]:
        기존 플랫폼 tags + 상품명에서 추출한 tags

    ProductSource.attributes["source_name_meta"]:
        원문/블록/slash/suffix/alternate name 등 추적용 JSON

    ProductSource.normalized_name:
        여기서는 절대 건드리지 않는다.
        PRODUCT ENRICHMENT 단계에서 생성한다.
    """

    def __init__(self):
        self.preprocessor = ProductNamePreprocessor()

    @staticmethod
    def _source_code(product_source: ProductSource) -> str:
        source = getattr(product_source, "source", None)
        return str(getattr(source, "code", "") or "").upper()

    @staticmethod
    def _attributes(product_source: ProductSource) -> dict:
        value = getattr(product_source, "attributes", None)
        return deepcopy(value) if isinstance(value, dict) else {}

    def prepare_one(
        self,
        product_source: ProductSource,
        *,
        raw_name: str | None = None,
        save: bool = False,
    ) -> dict:
        attributes = self._attributes(product_source)
        existing_tags = attributes.get("tags") or []

        if not isinstance(existing_tags, (list, tuple)):
            existing_tags = []

        # 신규 ingestion에서는 S3 원본명을 raw_name으로 넘기는 것을 권장.
        # 이미 source_name에 RAW가 들어간 기존 데이터는 raw_name 생략 가능.
        input_name = (
            raw_name
            if raw_name is not None
            else (product_source.source_name or "")
        )

        parsed = self.preprocessor.parse(
            input_name,
            existing_tags=existing_tags,
            source_code=self._source_code(product_source),
        )

        attributes["tags"] = parsed["tags"]
        attributes["source_name_meta"] = parsed["source_name_meta"]

        result = {
            "product_source_id": product_source.id,
            "source": self._source_code(product_source),
            "raw_name": input_name,
            "source_name": parsed["source_name"],
            "normalized_name": getattr(
                product_source,
                "normalized_name",
                None,
            ),
            "tags": parsed["tags"],
            "source_name_meta": parsed["source_name_meta"],
        }

        if save:
            product_source.source_name = parsed["source_name"]
            product_source.attributes = attributes
            product_source.save(
                update_fields=[
                    "source_name",
                    "attributes",
                ]
            )

        return result
