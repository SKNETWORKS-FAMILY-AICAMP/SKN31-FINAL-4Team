# backend/analysis/term_discovery/repository.py

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    DictionaryTerm,
    TermCandidate,
    TermCandidateObservation,
)

from .candidate import CandidateNormalizer


# ============================================================
# DICTIONARY
# ============================================================

class DictionaryRepository:

    def load_active_terms(self) -> list[dict]:

        terms = (
            DictionaryTerm.objects
            .filter(
                status=DictionaryTerm.Status.ACTIVE,
            )
            .prefetch_related(
                "aliases",
            )
            .order_by(
                "term_type",
                "canonical_name",
            )
        )

        result = []

        for term in terms:

            aliases = []

            for alias in term.aliases.all():

                aliases.append(
                    {
                        "alias": alias.alias,
                        "normalized_alias": (
                            alias.normalized_alias
                        ),
                    }
                )

            result.append(
                {
                    "id": term.id,
                    "term": term.canonical_name,
                    "normalized_name": (
                        term.normalized_name
                    ),
                    "term_type": term.term_type,
                    "aliases": aliases,
                }
            )

        return result


# ============================================================
# CANDIDATE REPOSITORY
# ============================================================

class TermCandidateRepository:
    """
    후보 저장 / Observation 누적 담당.

    후보는 아직 type을 모르는 상태이므로
    normalized_term 기준으로 하나만 유지한다.
    """

    def __init__(self):

        self.normalizer = (
            CandidateNormalizer()
        )

    # ========================================================
    # GET OR CREATE
    # ========================================================

    def get_candidate_by_term(
        self,
        term: str,
    ) -> TermCandidate | None:

        normalized = (
            self.normalizer
            .normalize(
                term
            )
        )

        if not normalized:
            return None

        return (
            TermCandidate.objects
            .filter(
                normalized_term=normalized,
            )
            .order_by(
                "id"
            )
            .first()
        )

    # ========================================================
    # SAVE NEW / EXISTING CANDIDATE
    # ========================================================

    @transaction.atomic
    def save_candidate(
        self,
        *,
        raw_term: str,
        raw_text: str,
        source=None,
        source_type: str,
        source_entity_id: str | None = None,
        source_field: str | None = None,
        residual_text: str | None = None,
    ) -> TermCandidate:

        now = timezone.now()

        normalized_term = (
            self.normalizer
            .normalize(
                raw_term
            )
        )

        if not normalized_term:
            raise ValueError(
                "normalized_term이 비어 있습니다."
            )

        # ----------------------------------------------------
        # CANDIDATE
        # ----------------------------------------------------

        candidate = (
            TermCandidate.objects
            .filter(
                normalized_term=normalized_term,
            )
            .order_by(
                "id"
            )
            .first()
        )

        if candidate is None:

            candidate = (
                TermCandidate.objects
                .create(
                    raw_term=raw_term,
                    normalized_term=normalized_term,
                    detected_count=0,
                    source_count=0,
                    first_seen_at=now,
                    last_seen_at=now,
                    status=(
                        TermCandidate.Status.PENDING
                    ),
                    decision=(
                        TermCandidate.Decision.PENDING
                    ),
                )
            )

        # ----------------------------------------------------
        # OBSERVATION
        # ----------------------------------------------------

        self._save_observation(
            candidate=candidate,
            raw_term=raw_term,
            raw_text=raw_text,
            source=source,
            source_type=source_type,
            source_entity_id=source_entity_id,
            source_field=source_field,
            residual_text=residual_text,
        )

        self._refresh_candidate_counts(
            candidate
        )

        return candidate

    # ========================================================
    # OBSERVE EXISTING CANDIDATE ONLY
    # ========================================================

    @transaction.atomic
    def observe_existing_candidate(
        self,
        *,
        candidate: TermCandidate,
        raw_text: str,
        source=None,
        source_type: str,
        source_entity_id: str | None = None,
        source_field: str | None = None,
        residual_text: str | None = None,
    ) -> TermCandidate:
        """
        DESCRIPTION / OCR / TRANSCRIPT / REVIEW 등에서
        신규 후보를 만들지 않고 기존 후보에 Observation만 추가.
        """

        if candidate is None:
            raise ValueError(
                "candidate가 None입니다."
            )

        self._save_observation(
            candidate=candidate,
            raw_term=candidate.raw_term,
            raw_text=raw_text,
            source=source,
            source_type=source_type,
            source_entity_id=source_entity_id,
            source_field=source_field,
            residual_text=residual_text,
        )

        self._refresh_candidate_counts(
            candidate
        )

        return candidate

    # ========================================================
    # PRIVATE - OBSERVATION
    # ========================================================

    def _save_observation(
        self,
        *,
        candidate: TermCandidate,
        raw_term: str,
        raw_text: str,
        source,
        source_type: str,
        source_entity_id: str | None,
        source_field: str | None,
        residual_text: str | None,
    ) -> bool:

        now = timezone.now()

        duplicate_filter = {
            "candidate": candidate,
            "source_type": source_type,
            "source_field": source_field,
        }

        # source가 있으면 같이 사용
        if source is not None:
            duplicate_filter[
                "source"
            ] = source

        # entity id가 있으면 entity 단위 중복 방지
        if source_entity_id:
            duplicate_filter[
                "source_entity_id"
            ] = source_entity_id

        # entity id가 없으면 raw_text까지 비교
        else:
            duplicate_filter[
                "raw_text"
            ] = raw_text

        already_exists = (
            TermCandidateObservation.objects
            .filter(
                **duplicate_filter
            )
            .exists()
        )

        if already_exists:

            candidate.last_seen_at = now

            candidate.save(
                update_fields=[
                    "last_seen_at",
                    "updated_at",
                ]
            )

            return False

        TermCandidateObservation.objects.create(
            candidate=candidate,
            source=source,
            source_type=source_type,
            source_entity_id=source_entity_id,
            source_field=source_field,
            detected_phrase=raw_term,
            raw_text=raw_text,
            residual_text=residual_text,
            detected_at=now,
        )

        candidate.last_seen_at = now

        candidate.save(
            update_fields=[
                "last_seen_at",
                "updated_at",
            ]
        )

        return True

    # ========================================================
    # PRIVATE - COUNTS
    # ========================================================

    @staticmethod
    def _refresh_candidate_counts(
        candidate: TermCandidate,
    ) -> None:
        """
        detected_count:
            Observation row 수

        source_count:
            실제 Source FK distinct 수
        """

        observation_count = (
            candidate.observations
            .count()
        )

        source_count = (
            candidate.observations
            .exclude(
                source__isnull=True,
            )
            .values(
                "source_id"
            )
            .distinct()
            .count()
        )

        candidate.detected_count = (
            observation_count
        )

        candidate.source_count = (
            source_count
        )

        candidate.save(
            update_fields=[
                "detected_count",
                "source_count",
                "updated_at",
            ]
        )