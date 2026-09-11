from __future__ import annotations

import re

from apps.core.models import (
    DictionaryTerm,
    TermAlias,
    Brand,
    Category,
)


class DictionaryGuard:
    """
    Known Entity Guard v4

    포함:
    - DictionaryTerm
    - TermAlias
    - Brand
    - Category

    Category/Brand는 프로젝트 모델 필드가 바뀔 수 있으므로
    _meta를 보고 존재하는 텍스트 필드만 동적으로 사용한다.
    """

    TEXT_FIELD_CANDIDATES = (
        "name",
        "normalized_name",
        "canonical_name",
        "english_name",
        "brand_code",
        "code",
        "category_code",
        "slug",
    )

    def __init__(self):
        self.term_lookup: set[str] = set()
        self.brand_lookup: set[str] = set()
        self.category_lookup: set[str] = set()
        self.reload()

    @staticmethod
    def normalize(value: str | None) -> str:
        if value is None:
            return ""

        text = str(value).lower().strip()
        if not text:
            return ""

        text = text.replace("_", " ").replace("-", " ")
        text = re.sub(r"[^\w가-힣\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def _model_text_fields(cls, model):
        available = {
            field.name
            for field in model._meta.fields
        }

        return [
            field
            for field in cls.TEXT_FIELD_CANDIDATES
            if field in available
        ]

    @classmethod
    def _load_model_texts(cls, model) -> set[str]:
        fields = cls._model_text_fields(model)

        if not fields:
            return set()

        result = set()

        for row in model.objects.all().values(*fields).iterator(
            chunk_size=1000
        ):
            for value in row.values():
                normalized = cls.normalize(value)
                if normalized:
                    result.add(normalized)

        return result

    def reload(self) -> None:
        term_values = (
            DictionaryTerm.objects
            .filter(status="ACTIVE")
            .exclude(normalized_name__isnull=True)
            .values_list("normalized_name", flat=True)
        )

        alias_values = (
            TermAlias.objects
            .filter(term__status="ACTIVE")
            .exclude(normalized_alias__isnull=True)
            .values_list("normalized_alias", flat=True)
        )

        self.term_lookup = {
            self.normalize(value)
            for value in list(term_values) + list(alias_values)
            if value
        }

        self.brand_lookup = self._load_model_texts(Brand)
        self.category_lookup = self._load_model_texts(Category)

    def role_of(self, value: str | None) -> str | None:
        normalized = self.normalize(value)

        if not normalized:
            return None

        if normalized in self.term_lookup:
            return "KNOWN_TERM"

        if normalized in self.brand_lookup:
            return "BRAND"

        if normalized in self.category_lookup:
            return "CATEGORY"

        return None

    def is_dictionary_known(self, value: str | None) -> bool:
        return self.role_of(value) == "KNOWN_TERM"

    def is_brand(self, value: str | None) -> bool:
        return self.role_of(value) == "BRAND"

    def is_category(self, value: str | None) -> bool:
        return self.role_of(value) == "CATEGORY"

    def is_known(self, value: str | None) -> bool:
        return self.role_of(value) is not None

    def stats(self) -> dict:
        return {
            "dictionary": len(self.term_lookup),
            "brand": len(self.brand_lookup),
            "category": len(self.category_lookup),
        }
