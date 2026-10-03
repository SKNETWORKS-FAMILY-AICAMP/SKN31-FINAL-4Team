from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.core.models import (
    DictionaryTerm,
    TextDocument,
    TextTermMention,
)


@dataclass
class TextMentionWriteResult:
    document_id: int

    deleted: int
    created: int
    skipped: int

    mention_count: int
    unique_term_count: int

    legacy_enriched: int = 0
    legacy_only: int = 0


class TextMentionWriter:
    """
    TextMention extraction 결과를 TextTermMention으로 저장한다.

    Policy
    ------
    - document 단위 replace 방식
    - DictionaryTerm이 실제 존재하는 mention만 저장
    - NEW STEP02 결과가 primary
    - 기존 TextDocument.analysis_metadata는 수정하지 않음
    - 기존 AI intent / sentiment / polarity / attributed는
      가능한 경우 TextTermMention에 다시 결합
    """

    BATCH_SIZE = 1000

    def write(
        self,
        *,
        document: TextDocument,
        result: Any,
    ) -> TextMentionWriteResult:
        if document.pk is None:
            raise ValueError(
                "저장되지 않은 TextDocument는 처리할 수 없습니다."
            )

        mentions = list(
            result.mentions or []
        )

        term_ids = {
            mention.term_id
            for mention in mentions
            if mention.term_id is not None
        }

        valid_term_ids = set(
            DictionaryTerm.objects
            .filter(id__in=term_ids)
            .values_list(
                "id",
                flat=True,
            )
        )

        document_metadata = self._get_document_metadata(
            document
        )

        legacy_index = self._build_legacy_index(
            document_metadata
        )

        document_intent = self._clean_string(
            document_metadata.get("intent")
        )

        document_sentiment = self._to_float(
            document_metadata.get("sentiment")
        )

        rows: list[TextTermMention] = []

        skipped = 0
        legacy_enriched = 0
        legacy_only = 0

        for mention in mentions:
            if (
                mention.term_id is None
                or mention.term_id
                not in valid_term_ids
            ):
                skipped += 1
                continue

            legacy_rows = legacy_index.get(
                mention.term_id,
                [],
            )

            primary_legacy = (
                legacy_rows[0]
                if legacy_rows
                else None
            )

            has_legacy = bool(
                primary_legacy
            )

            is_legacy_only = (
                mention.match_type
                == "LEGACY_AI"
            )

            if has_legacy:
                legacy_enriched += 1

            if is_legacy_only:
                legacy_only += 1

            metadata = self._build_metadata(
                mention=mention,
                legacy_rows=legacy_rows,
            )

            rows.append(
                TextTermMention(
                    document=document,
                    term_id=mention.term_id,
                    mention_text=mention.surface,
                    mention_role="CONTEXT",
                    sentiment_score=(
                        document_sentiment
                        if has_legacy
                        else None
                    ),
                    intent_code=(
                        document_intent
                        if has_legacy
                        else None
                    ),
                    confidence=mention.confidence,
                    start_seconds=None,
                    end_seconds=None,
                    analysis_metadata=metadata,
                )
            )

        with transaction.atomic():
            old_qs = (
                TextTermMention.objects
                .filter(document=document)
            )

            deleted = old_qs.count()

            old_qs.delete()

            if rows:
                TextTermMention.objects.bulk_create(
                    rows,
                    batch_size=self.BATCH_SIZE,
                )

        return TextMentionWriteResult(
            document_id=document.id,
            deleted=deleted,
            created=len(rows),
            skipped=skipped,
            mention_count=len(mentions),
            unique_term_count=len(
                {
                    row.term_id
                    for row in rows
                }
            ),
            legacy_enriched=legacy_enriched,
            legacy_only=legacy_only,
        )

    # ========================================================
    # Legacy AI
    # ========================================================

    def _build_legacy_index(
        self,
        document_metadata: dict[str, Any],
    ) -> dict[int, list[dict[str, Any]]]:
        """
        OLD AI mentions를 현재 DictionaryTerm ID 기준으로 index한다.

        canonical exact -> alias exact 순서.

        resolve되지 않는 OLD mention은 무시한다.
        원본은 TextDocument.analysis_metadata에 그대로 남는다.
        """

        raw_mentions = document_metadata.get(
            "mentions"
        )

        if not isinstance(raw_mentions, list):
            return {}

        prepared: list[
            tuple[dict[str, Any], str, str | None]
        ] = []

        names: set[str] = set()

        for row in raw_mentions:
            if not isinstance(row, dict):
                continue

            raw_term = self._clean_string(
                row.get("term")
            )

            if not raw_term:
                continue

            slot = self._clean_string(
                row.get("slot")
            )

            expected_type = (
                self._slot_to_term_type(slot)
            )

            prepared.append(
                (
                    row,
                    raw_term,
                    expected_type,
                )
            )

            names.add(raw_term)

        if not prepared:
            return {}

        # canonical_name 조회
        canonical_terms = list(
            DictionaryTerm.objects
            .filter(
                canonical_name__in=names,
                status="ACTIVE",
            )
        )

        canonical_lookup: dict[
            str,
            list[DictionaryTerm],
        ] = {}

        for term in canonical_terms:
            key = (
                str(term.canonical_name)
                .strip()
                .casefold()
            )

            canonical_lookup.setdefault(
                key,
                [],
            ).append(term)

        # alias 조회
        alias_terms = list(
            DictionaryTerm.objects
            .filter(
                aliases__alias__in=names,
                status="ACTIVE",
            )
            .prefetch_related("aliases")
            .distinct()
        )

        alias_lookup: dict[
            str,
            list[DictionaryTerm],
        ] = {}

        name_keys = {
            name.casefold()
            for name in names
        }

        for term in alias_terms:
            for alias in term.aliases.all():
                alias_value = self._clean_string(
                    getattr(
                        alias,
                        "alias",
                        None,
                    )
                )

                if not alias_value:
                    continue

                key = alias_value.casefold()

                if key not in name_keys:
                    continue

                alias_lookup.setdefault(
                    key,
                    [],
                ).append(term)

        index: dict[
            int,
            list[dict[str, Any]],
        ] = {}

        for (
            row,
            raw_term,
            expected_type,
        ) in prepared:
            key = raw_term.casefold()

            candidates = (
                canonical_lookup.get(
                    key,
                    [],
                )
                or alias_lookup.get(
                    key,
                    [],
                )
            )

            term = self._select_term(
                candidates,
                expected_type=expected_type,
            )

            if term is None:
                continue

            index.setdefault(
                term.id,
                [],
            ).append(
                dict(row)
            )

        return index

    @staticmethod
    def _select_term(
        candidates: list[DictionaryTerm],
        *,
        expected_type: str | None,
    ) -> DictionaryTerm | None:
        if not candidates:
            return None

        if expected_type:
            for term in candidates:
                if (
                    str(
                        getattr(
                            term,
                            "term_type",
                            "",
                        )
                    ).upper()
                    == expected_type
                ):
                    return term

        return candidates[0]

    @staticmethod
    def _slot_to_term_type(
        slot: str | None,
    ) -> str | None:
        mapping = {
            "brand": "BRAND",
            "item": "ITEM",
            "style": "STYLE",
            "detail": "DETAIL",
            "material": "MATERIAL",
            "color": "COLOR",
            "tpo": "TPO",
        }

        return mapping.get(
            str(slot or "")
            .strip()
            .lower()
        )

    # ========================================================
    # Metadata
    # ========================================================

    def _build_metadata(
        self,
        *,
        mention: Any,
        legacy_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evidence_sources = [
            "LEGACY_AI"
            if mention.match_type == "LEGACY_AI"
            else "DICTIONARY"
        ]

        if (
            legacy_rows
            and "LEGACY_AI"
            not in evidence_sources
        ):
            evidence_sources.append(
                "LEGACY_AI"
            )

        metadata: dict[str, Any] = {
            "pipeline": "TEXT_STEP02",
            "evidence_sources": (
                evidence_sources
            ),
            "segment_index": (
                mention.segment_index
            ),
            "segment_text": (
                mention.segment_text
            ),
            "start_char": (
                mention.start_char
            ),
            "end_char": (
                mention.end_char
            ),
            "canonical_name": (
                mention.canonical_name
            ),
            "term_code": (
                mention.term_code
            ),
            "term_type": (
                mention.term_type
            ),
            "match_type": (
                mention.match_type
            ),
            "context_type": (
                mention.context_type
            ),
            "product_name": (
                mention.product_name
            ),
            "product_name_confidence": (
                mention.product_name_confidence
            ),
            "brand_id": (
                mention.brand_id
            ),
            "brand_code": (
                mention.brand_code
            ),
        }

        if legacy_rows:
            metadata["legacy"] = {
                "mentions": [
                    {
                        "slot": row.get(
                            "slot"
                        ),
                        "span": row.get(
                            "span"
                        ),
                        "term": row.get(
                            "term"
                        ),
                        "polarity": row.get(
                            "polarity"
                        ),
                        "attributed": row.get(
                            "attributed"
                        ),
                    }
                    for row in legacy_rows
                ]
            }

        return metadata

    # ========================================================
    # Helpers
    # ========================================================

    @staticmethod
    def _get_document_metadata(
        document: TextDocument,
    ) -> dict[str, Any]:
        value = document.analysis_metadata

        if isinstance(value, dict):
            return value

        return {}

    @staticmethod
    def _clean_string(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        value = str(value).strip()

        return value or None

    @staticmethod
    def _to_float(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None