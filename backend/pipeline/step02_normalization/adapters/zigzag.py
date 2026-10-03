from __future__ import annotations

from typing import Any

from .base import BaseNormalizationAdapter


class ZigzagNormalizationAdapter(BaseNormalizationAdapter):
    """Zigzag STEP02 입력을 FEEDIT 공통 source evidence 형태로 변환한다.

    Zigzag의 수집 attributes에는 검색/필터에서 관찰된 style tag 등이 들어간다.
    이 값은 상품명과 별개의 positive evidence이므로 source_tags로 전달한다.
    실제 DictionaryTerm 매칭 여부는 Pipeline의 SemanticAttributeExtractor가 결정한다.
    """

    source_code = "zigzag"

    def build(self, product_source) -> dict[str, Any]:
        payload = (
            product_source.attributes
            if isinstance(product_source.attributes, dict)
            else {}
        )

        source_tags: list[str] = []

        # tags 예: {"style": [{"name": "글램"}, ...]}
        self._collect_tag_values(payload.get("tags"), source_tags)

        # observed_tags 예: [{"tag": "글램", "group": "style", ...}]
        self._collect_tag_values(payload.get("observed_tags"), source_tags)

        # 일부 ingestion 버전에서 filter/tag 계열이 별도 키로 저장될 수 있다.
        for key in (
            "filter_tags",
            "filters",
            "style_tags",
            "trend_tags",
        ):
            self._collect_tag_values(payload.get(key), source_tags)

        source_attributes = self._normalize_source_attributes(
            payload.get("attributes")
        )

        return {
            "product_source_id": product_source.id,
            "source_code": self.source_code,
            "source_name": str(product_source.source_name or "").strip(),
            "source_tags": source_tags,
            "source_options": {},
            "source_attributes": source_attributes,
        }

    @classmethod
    def _collect_tag_values(
        cls,
        value: Any,
        result: list[str],
    ) -> None:
        """중첩된 Zigzag tag/filter payload에서 실제 label만 수집한다."""
        if value in (None, ""):
            return

        if isinstance(value, str):
            cls._append(result, value)
            return

        if isinstance(value, (list, tuple, set)):
            for item in value:
                cls._collect_tag_values(item, result)
            return

        if not isinstance(value, dict):
            return

        # 객체 자체가 tag row인 경우 label 필드만 사용한다.
        for label_key in ("tag", "name", "label", "value"):
            label = value.get(label_key)
            if isinstance(label, str) and label.strip():
                cls._append(result, label)
                return

        # {"style": [...], "trend": [...]} 같은 group mapping.
        for nested in value.values():
            cls._collect_tag_values(nested, result)

    @classmethod
    def _normalize_source_attributes(
        cls,
        value: Any,
    ) -> dict[str, list[str]]:
        if not isinstance(value, dict):
            return {}

        result: dict[str, list[str]] = {}
        for raw_key, raw_values in value.items():
            key = str(raw_key or "").strip()
            if not key:
                continue

            values: list[str] = []
            cls._collect_tag_values(raw_values, values)
            if values:
                result[key] = values

        return result

    @staticmethod
    def _append(result: list[str], value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
