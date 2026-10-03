from __future__ import annotations

from typing import Any


class MusinsaNormalizationAdapter:

    source_code = "musinsa"

    def build(
        self,
        product_source,
    ) -> dict[str, Any]:

        payload = (
            product_source.attributes
            if isinstance(
                product_source.attributes,
                dict,
            )
            else {}
        )

        source_tags = self._normalize_tags(
            payload.get("tags")
        )

        source_options = self._normalize_options(
            payload.get("options")
        )

        source_attributes = (
            payload.get("attributes")
            if isinstance(
                payload.get("attributes"),
                dict,
            )
            else {}
        )

        detail_text = str(
            payload.get("detail_text")
            or ""
        ).strip()

        return {
            "product_source_id": product_source.id,
            "source_code": self.source_code,

            "source_name": str(
                product_source.source_name
                or ""
            ).strip(),

            # 무신사 원본 정보
            "source_tags": source_tags,
            "source_options": source_options,
            "source_attributes": source_attributes,

            # 아직 Step02 attribute 분석에는 사용하지 않는다.
            # 추후 detail extractor 입력으로 사용 가능.
            "detail_text": detail_text,
        }

    @staticmethod
    def _normalize_tags(
        value: Any,
    ) -> list[str]:

        if not isinstance(value, list):
            return []

        result: list[str] = []

        for item in value:
            if isinstance(item, dict):
                raw = (
                    item.get("tag")
                    or item.get("name")
                    or item.get("label")
                    or item.get("value")
                )
            else:
                raw = item

            text = str(raw or "").strip()

            if text and text not in result:
                result.append(text)

        return result

    @staticmethod
    def _normalize_options(
        value: Any,
    ) -> dict[str, list[str]]:

        if not isinstance(value, dict):
            return {}

        result: dict[str, list[str]] = {}

        for raw_key, raw_values in value.items():

            key = str(
                raw_key or ""
            ).strip()

            if not key:
                continue

            if isinstance(
                raw_values,
                (list, tuple, set),
            ):
                values = [
                    str(item).strip()
                    for item in raw_values
                    if str(item or "").strip()
                ]

            elif raw_values not in (
                None,
                "",
            ):
                values = [
                    str(raw_values).strip()
                ]

            else:
                values = []

            values = list(
                dict.fromkeys(values)
            )

            if values:
                result[key] = values

        return result