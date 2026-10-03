from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.core.models import DictionaryTerm, TermAlias
from pipeline.step02_normalization.semantic_tokenizer.tokenizer import (
    get_feedit_tokenizer,
    normalize_match_text,
)

@dataclass(frozen=True)
class SearchTerm:
    term_id: int
    query: str
    normalized_query: str


class SearchTermResolver:
    """검색 신호와 FEEDIT DictionaryTerm 사이의 단일 진입점."""

    def __init__(self) -> None:
        self.tokenizer = get_feedit_tokenizer()
        self._exact: dict[str, int] = {}
        self._load_exact_index()

    def _load_exact_index(self) -> None:
        terms = DictionaryTerm.objects.filter(status="ACTIVE").only(
            "id", "canonical_name", "normalized_name"
        )
        for term in terms.iterator():
            for value in (term.canonical_name, term.normalized_name):
                key = normalize_match_text(value)
                if key:
                    self._exact.setdefault(key, term.id)
                    self._exact.setdefault(key.replace(" ", ""), term.id)

        aliases = TermAlias.objects.filter(term__status="ACTIVE").only(
            "term_id", "alias", "normalized_alias"
        )
        for alias in aliases.iterator():
            for value in (alias.alias, alias.normalized_alias):
                key = normalize_match_text(value)
                if key:
                    self._exact.setdefault(key, alias.term_id)
                    self._exact.setdefault(key.replace(" ", ""), alias.term_id)

    def active_search_terms(self, limit: int | None = None) -> list[SearchTerm]:
        qs = (
            DictionaryTerm.objects
            .filter(status="ACTIVE")
            .exclude(canonical_name__isnull=True)
            .exclude(canonical_name="")
            .only("id", "canonical_name")
            .order_by("id")
        )
        if limit:
            qs = qs[:limit]

        rows: list[SearchTerm] = []
        for term in qs:
            query = str(term.canonical_name).strip()
            if not query:
                continue
            # Tokenizer를 실제로 통과시켜 현재 사전 snapshot이 읽히는지 검증한다.
            self.tokenizer.tokenize(query)
            rows.append(SearchTerm(
                term_id=term.id,
                query=query,
                normalized_query=normalize_match_text(query),
            ))
        return rows

    def resolve(self, text: str | None) -> int | None:
        """API가 돌려준 문자열을 기존 DictionaryTerm 하나에만 보수적으로 연결한다."""
        key = normalize_match_text(text)
        if not key:
            return None

        direct = self._exact.get(key) or self._exact.get(key.replace(" ", ""))
        if direct:
            return direct

        result = self.tokenizer.tokenize(text)
        term_ids = self._collect_known_term_ids(result)
        if len(term_ids) == 1:
            return next(iter(term_ids))
        return None

    def _collect_known_term_ids(self, value: Any) -> set[int]:
        found: set[int] = set()
        if isinstance(value, dict):
            term_id = value.get("term_id")
            kind = str(value.get("kind") or "").upper()
            if term_id and kind not in {"UNKNOWN", "EXCLUDED"}:
                try:
                    found.add(int(term_id))
                except (TypeError, ValueError):
                    pass
            for child in value.values():
                found.update(self._collect_known_term_ids(child))
        elif isinstance(value, list):
            for child in value:
                found.update(self._collect_known_term_ids(child))
        return found
