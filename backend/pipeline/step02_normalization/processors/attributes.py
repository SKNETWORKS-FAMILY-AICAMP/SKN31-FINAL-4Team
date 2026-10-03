from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..semantic_tokenizer.tokenizer import (
    get_feedit_tokenizer,
)

class SemanticAttributeExtractor:
    """FEEDIT Semantic Tokenizer 결과를 STEP02용 evidence로 변환한다."""

    def __init__(self):
        self.tokenizer = get_feedit_tokenizer()

    def reload_dictionary(self) -> None:
        self.tokenizer.reload_dictionary()

    def extract(self, text: str) -> dict[str, Any]:
        result = self.tokenizer.tokenize(text)
        tokens = result.get("tokens") or []

        known_evidence: list[dict[str, Any]] = []
        unknown_terms: list[dict[str, Any]] = []
        excluded_terms: list[dict[str, Any]] = []
        known_by_type: dict[str, list[str]] = defaultdict(list)
        seen_known: set[tuple] = set()
        seen_unknown: set[str] = set()

        for token in tokens:
            kind = str(token.get("kind") or "").upper()
            surface = str(token.get("surface") or "").strip()

            if kind == "KNOWN":
                canonical = (
                    token.get("canonical_name")
                    or token.get("canonical")
                    or surface
                )

                term_type = str(
                    token.get("term_type") or ""
                ).upper()

                attribute_type = str(
                    token.get("attribute_type") or ""
                ).upper() or None

                key = (
                    token.get("term_id"),
                    term_type,
                    attribute_type,
                    surface.casefold(),
                )

                if key in seen_known:
                    continue

                seen_known.add(key)

                row = {
                    "term_id": token.get("term_id"),
                    "term_code": token.get("term_code"),
                    "term_type": term_type,
                    "canonical_name": canonical,
                    "surface": surface,
                    "match_type": token.get("match_type"),
                    "attribute_type": attribute_type,
                    "component_type": token.get("component_type"),
                    "semantic_role": token.get("semantic_role"),
                    "source_field": "PRODUCT_NAME",
                }

                known_evidence.append(row)

                bucket = (
                    attribute_type
                    if term_type == "DETAIL"
                    and attribute_type
                    else term_type
                )

                if (
                    bucket
                    and canonical
                    and canonical
                    not in known_by_type[bucket]
                ):
                    known_by_type[bucket].append(
                        canonical
                    )

            elif kind == "UNKNOWN":
                if not surface:
                    continue

                key = surface.casefold()

                if key in seen_unknown:
                    continue

                seen_unknown.add(key)

                unknown_terms.append(
                    {
                        "text": surface,
                        "candidates": token.get(
                            "candidates"
                        )
                        or [],
                    }
                )

            elif kind == "EXCLUDED":
                excluded_terms.append(
                    {
                        "text": surface,
                        "reason": token.get(
                            "exclusion_reason"
                        ),
                    }
                )

        return {
            "raw_text": result.get("raw_text"),
            "cleaned_text": result.get(
                "cleaned_text"
            ),
            "tokens": tokens,
            "semantic_tokens": result.get(
                "semantic_tokens"
            )
            or [],
            "phrases": result.get("phrases") or [],
            "known_evidence": known_evidence,
            "known_by_type": dict(known_by_type),
            "unknown_terms": unknown_terms,
            "excluded_terms": excluded_terms,
        }

class ProductAttributeBuilder:
    """
    Structural + Semantic 결과를 서비스용 ProductSource.attributes로 변환한다.

    원칙
    - evidence / term_id / term_code / match_type은 attributes에 저장하지 않는다.
    - semantic evidence 원본은 pipeline의 known_evidence에 별도로 남는다.
    - 값이 없는 key는 만들지 않는다.
    - 일반 속성은 list[str], 구조형 속성(SIZE 등)은 원래 타입을 보존한다.
    """

    # Dictionary DETAIL attribute_type -> 서비스 attribute key
    ATTRIBUTE_SLOT_MAP = {
        "FIT": "fit",
        "SILHOUETTE": "silhouette",
        "NECKLINE": "neckline",
        "SLEEVE": "sleeve",
        "LENGTH": "length",
        "SHAPE": "shape",
        "DETAIL": "detail",
        "PRODUCTION_TYPE": "production_type",
    }

    # Dictionary term_type -> 서비스 attribute key
    TERM_TYPE_SLOT_MAP = {
        "ITEM": "item",
        "MATERIAL": "material",
        "COLOR": "color",
        "STYLE": "style",
        "TPO": "tpo",
        "GENDER": "gender",
        "SEASON": "season",
        "FIT": "fit",
        "SILHOUETTE": "silhouette",
        "NECKLINE": "neckline",
        "SLEEVE": "sleeve",
        "LENGTH": "length",
        "SHAPE": "shape",
        "DETAIL": "detail",
        "PRODUCTION_TYPE": "production_type",
    }

    # 현재 사전에서 DETAIL로 분류돼 있지만 서비스에서는 별도 slot으로
    # 보내야 하는 대표 term. 사전 스키마를 즉시 바꾸지 않아도 서비스 출력은 안정적이다.
    TERM_CODE_SLOT_MAP = {
        "DETAIL_SELF_MADE": "production_type",
    }

    # Structural product_meta type -> 서비스 attribute key
    META_SLOT_MAP = {
        "COLOR_COUNT": "color_count",
    }

    def build(
        self,
        *,
        structural_attributes: dict[str, Any] | None,
        semantic_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        structural = structural_attributes or {}
        semantic = semantic_result or {}

        result: dict[str, Any] = {}

        # -----------------------------------------------------
        # Structural
        # -----------------------------------------------------

        for value in structural.get("sizes") or []:
            self._append_unique(result, "size", value)

        for value in structural.get("genders") or []:
            self._append_unique(result, "gender", value)

        for value in structural.get("season_codes") or []:
            self._append_unique(result, "season", value)

        for row in structural.get("product_meta") or []:
            if not isinstance(row, dict):
                continue

            meta_type = str(row.get("type") or "").strip().upper()
            target = self.META_SLOT_MAP.get(meta_type)

            if not target:
                continue

            value = (
                row.get("value")
                if row.get("value") not in (None, "", [], {})
                else row.get("raw")
            )

            if meta_type == "COLOR_COUNT":
                value = self._to_int_if_possible(value)

            self._set_scalar(result, target, value)

        # PRODUCT_CODE는 서비스 attribute가 아니다.
        # 필요하면 ProductSource의 별도 식별 필드/normalization audit에서 관리한다.

        # -----------------------------------------------------
        # Semantic
        # -----------------------------------------------------

        for evidence in semantic.get("known_evidence") or []:
            if not isinstance(evidence, dict):
                continue

            term_type = str(
                evidence.get("term_type") or ""
            ).strip().upper()

            attribute_type = str(
                evidence.get("attribute_type") or ""
            ).strip().upper()

            term_code = str(
                evidence.get("term_code") or ""
            ).strip().upper()

            value = (
                evidence.get("canonical_name")
                or evidence.get("surface")
            )

            if value in (None, "", [], {}):
                continue

            target = self._semantic_slot(
                term_type=term_type,
                attribute_type=attribute_type,
                term_code=term_code,
            )

            if not target:
                continue

            self._append_unique(result, target, value)

        return result

    @classmethod
    def _semantic_slot(
        cls,
        *,
        term_type: str,
        attribute_type: str,
        term_code: str,
    ) -> str | None:
        # 가장 구체적인 term_code override가 최우선
        if term_code in cls.TERM_CODE_SLOT_MAP:
            return cls.TERM_CODE_SLOT_MAP[term_code]

        # DETAIL은 attribute_type이 있으면 그 의미를 우선한다.
        if term_type == "DETAIL":
            if attribute_type:
                mapped = cls.ATTRIBUTE_SLOT_MAP.get(attribute_type)
                if mapped:
                    return mapped

            return "detail"

        return cls.TERM_TYPE_SLOT_MAP.get(term_type)

    @classmethod
    def _append_unique(
        cls,
        result: dict[str, Any],
        key: str,
        value: Any,
    ) -> None:
        value = cls._clean_value(value)

        if value in (None, "", [], {}):
            return

        bucket = result.setdefault(key, [])

        if value not in bucket:
            bucket.append(value)

    @classmethod
    def _set_scalar(
        cls,
        result: dict[str, Any],
        key: str,
        value: Any,
    ) -> None:
        value = cls._clean_value(value)

        if value in (None, "", [], {}):
            return

        result[key] = value

    @classmethod
    def _clean_value(cls, value: Any) -> Any:
        # 구조형 값은 절대로 str(dict)로 만들지 않는다.
        if isinstance(value, dict):
            return {
                str(key): cls._clean_value(val)
                for key, val in value.items()
                if val not in (None, "", [], {})
            }

        if isinstance(value, list):
            cleaned = [
                cls._clean_value(item)
                for item in value
                if item not in (None, "", [], {})
            ]
            return cleaned

        if isinstance(value, tuple):
            return [
                cls._clean_value(item)
                for item in value
                if item not in (None, "", [], {})
            ]

        if isinstance(value, str):
            return value.strip()

        return value

    @staticmethod
    def _to_int_if_possible(value: Any) -> Any:
        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            return value

        text = str(value or "").strip()

        if text.isdigit():
            return int(text)

        return value
