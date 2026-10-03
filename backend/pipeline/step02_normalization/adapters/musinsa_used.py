from __future__ import annotations

from typing import Any


class MusinsaUsedNormalizationAdapter:

    source_code = "musinsa_used"

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

        source_options = self._normalize_mapping(
            payload.get("options")
        )

        # USED 필터 수집으로 확인된 positive evidence
        source_attributes = self._normalize_mapping(
            payload.get("attributes")
        )

        source_genders = self._normalize_list(
            product_source.source_genders
        )

        gender_scope = str(
            product_source.gender_scope
            or ""
        ).strip().upper()

        if (
            gender_scope
            and gender_scope not in source_genders
        ):
            source_genders.append(
                gender_scope
            )

        return {
            "product_source_id": product_source.id,
            "source_code": self.source_code,

            "source_name": str(
                product_source.source_name
                or ""
            ).strip(),

            "style_no": str(
                product_source.style_no
                or ""
            ).strip(),

            "source_genders": source_genders,

            "source_tags": source_tags,
            "source_options": source_options,

            # 핵심:
            # USED filter observation 결과
            "source_attributes": source_attributes,
        }

    @classmethod
    def _normalize_tags(
        cls,
        value: Any,
    ) -> list[str]:

        return cls._normalize_list(
            value
        )

    @staticmethod
    def _normalize_list(
        value: Any,
    ) -> list[str]:

        if not isinstance(
            value,
            (list, tuple, set),
        ):
            return []

        result: list[str] = []

        for item in value:

            text = str(
                item or ""
            ).strip()

            if (
                text
                and text not in result
            ):
                result.append(text)

        return result

    @classmethod
    def _normalize_mapping(
        cls,
        value: Any,
    ) -> dict[str, list[str]]:

        if not isinstance(
            value,
            dict,
        ):
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
                values = cls._normalize_list(
                    raw_values
                )

            elif raw_values not in (
                None,
                "",
            ):
                values = [
                    str(raw_values).strip()
                ]

            else:
                values = []

            if values:
                result[key] = values

        return result