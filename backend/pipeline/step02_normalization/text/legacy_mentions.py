from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.core.models import DictionaryTerm, TextDocument

from .mention_extractor import (
    TextMention,
    TextMentionExtractionResult,
)


@dataclass
class LegacyMentionMergeResult:
    mentions: list[TextMention]

    new_count: int
    legacy_input_count: int
    legacy_resolved_count: int
    legacy_unresolved_count: int

    matched_with_new_count: int
    legacy_only_count: int

    unresolved_legacy: list[dict[str, Any]] = field(
        default_factory=list
    )


class LegacyMentionResolver:
    """
    기존 TextDocument.analysis_metadata["mentions"]를
    현재 DictionaryTerm으로 다시 검증한다.

    중요:
    - 기존 AI 결과를 그대로 신뢰하지 않는다.
    - 현재 DictionaryTerm으로 resolve 가능한 것만 사용한다.
    - candidates는 정식 mention으로 승격하지 않는다.
    - 기존 analysis_metadata 자체는 수정하지 않는다.
    """

    SLOT_TERM_TYPE_MAP = {
        "brand": "BRAND",
        "item": "ITEM",
        "style": "STYLE",
        "detail": "DETAIL",
        "material": "MATERIAL",
        "color": "COLOR",
        "tpo": "TPO",
    }

    def __init__(self) -> None:
        self._term_cache: dict[
            tuple[str, str | None],
            DictionaryTerm | None,
        ] = {}

    def get_legacy_rows(
        self,
        document: TextDocument,
    ) -> list[dict[str, Any]]:
        metadata = (
            document.analysis_metadata
            if isinstance(document.analysis_metadata, dict)
            else {}
        )

        rows = metadata.get("mentions")

        if not isinstance(rows, list):
            return []

        return [
            row
            for row in rows
            if isinstance(row, dict)
        ]

    def resolve_document(
        self,
        document: TextDocument,
    ) -> tuple[
        list[TextMention],
        list[dict[str, Any]],
    ]:
        body = str(document.body or "")

        resolved: list[TextMention] = []
        unresolved: list[dict[str, Any]] = []

        for row in self.get_legacy_rows(document):
            mention = self.resolve_one(
                row=row,
                body=body,
            )

            if mention is None:
                unresolved.append(dict(row))
                continue

            resolved.append(mention)

        return resolved, unresolved

    def resolve_one(
        self,
        *,
        row: dict[str, Any],
        body: str,
    ) -> TextMention | None:
        raw_term = str(
            row.get("term") or ""
        ).strip()

        if not raw_term:
            return None

        slot = str(
            row.get("slot") or ""
        ).strip().lower()

        expected_term_type = (
            self.SLOT_TERM_TYPE_MAP.get(slot)
        )

        term = self._resolve_term(
            raw_term,
            expected_term_type=expected_term_type,
        )

        if term is None:
            return None

        start_char = self._find_start(
            body=body,
            raw_term=raw_term,
        )

        end_char = (
            start_char + len(raw_term)
            if start_char is not None
            else None
        )

        return TextMention(
            term_id=term.id,
            term_code=getattr(
                term,
                "code",
                None,
            ),
            term_type=getattr(
                term,
                "term_type",
                None,
            ),
            canonical_name=term.canonical_name,
            surface=raw_term,
            match_type="LEGACY_AI",
            segment_index=-1,
            segment_text=str(
                row.get("span") or body
            ),
            start_char=start_char,
            end_char=end_char,
            confidence=1.0,
            context_type="TEXT",
            product_name=None,
            product_name_confidence=None,
        )

    def _resolve_term(
        self,
        raw_term: str,
        *,
        expected_term_type: str | None,
    ) -> DictionaryTerm | None:
        normalized = (
            str(raw_term or "")
            .strip()
            .casefold()
        )

        if not normalized:
            return None

        cache_key = (
            normalized,
            expected_term_type,
        )

        if cache_key in self._term_cache:
            return self._term_cache[cache_key]

        # 1. canonical exact
        qs = (
            DictionaryTerm.objects
            .filter(
                canonical_name__iexact=raw_term,
                status="ACTIVE",
            )
            .order_by("id")
        )

        if expected_term_type:
            typed = (
                qs
                .filter(
                    term_type=expected_term_type,
                )
                .first()
            )

            if typed is not None:
                self._term_cache[cache_key] = typed
                return typed

        exact = qs.first()

        if exact is not None:
            self._term_cache[cache_key] = exact
            return exact

        # 2. alias exact
        alias_qs = (
            DictionaryTerm.objects
            .filter(
                aliases__alias__iexact=raw_term,
                status="ACTIVE",
            )
            .distinct()
            .order_by("id")
        )

        if expected_term_type:
            typed_alias = (
                alias_qs
                .filter(
                    term_type=expected_term_type,
                )
                .first()
            )

            if typed_alias is not None:
                self._term_cache[cache_key] = typed_alias
                return typed_alias

        alias_term = alias_qs.first()

        self._term_cache[cache_key] = alias_term

        return alias_term

    @staticmethod
    def _find_start(
        *,
        body: str,
        raw_term: str,
    ) -> int | None:
        position = body.find(raw_term)

        if position < 0:
            return None

        return position


class MentionMerger:
    """
    NEW STEP02 mention + 검증된 LEGACY AI mention 병합.

    NEW를 primary로 사용한다.

    같은 term_id가 NEW에 이미 존재하면
    LEGACY row를 새로 만들지 않는다.

    Writer가 document.analysis_metadata를 사용해
    해당 NEW mention에 기존 AI evidence를 다시 붙인다.

    NEW에 없는 LEGACY term만 별도 mention으로 추가한다.
    """

    def __init__(
        self,
        *,
        resolver: LegacyMentionResolver | None = None,
    ) -> None:
        self.resolver = (
            resolver
            or LegacyMentionResolver()
        )

    def merge(
        self,
        *,
        document: TextDocument,
        result: TextMentionExtractionResult,
    ) -> LegacyMentionMergeResult:
        new_mentions = list(
            result.mentions or []
        )

        (
            legacy_mentions,
            unresolved,
        ) = self.resolver.resolve_document(
            document
        )

        new_term_ids = {
            mention.term_id
            for mention in new_mentions
            if mention.term_id is not None
        }

        merged_mentions = list(new_mentions)

        matched_with_new_count = 0
        legacy_only_count = 0

        added_legacy_term_ids: set[int] = set()

        for legacy in legacy_mentions:
            term_id = legacy.term_id

            if term_id is None:
                continue

            if term_id in new_term_ids:
                matched_with_new_count += 1
                continue

            if term_id in added_legacy_term_ids:
                continue

            merged_mentions.append(legacy)

            added_legacy_term_ids.add(term_id)
            legacy_only_count += 1

        return LegacyMentionMergeResult(
            mentions=merged_mentions,
            new_count=len(new_mentions),
            legacy_input_count=(
                len(legacy_mentions)
                + len(unresolved)
            ),
            legacy_resolved_count=len(
                legacy_mentions
            ),
            legacy_unresolved_count=len(
                unresolved
            ),
            matched_with_new_count=(
                matched_with_new_count
            ),
            legacy_only_count=legacy_only_count,
            unresolved_legacy=unresolved,
        )