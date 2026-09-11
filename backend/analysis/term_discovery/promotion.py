# backend/analysis/term_discovery/promotion_service.py

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    DictionaryTerm,
    TermAlias,
    TermCandidate,
    Detail,
    Material,
    Item,
    Style,
    Color,
    TPO,
)

from .candidate import CandidateNormalizer


class TermPromotionService:
    """
    FEEDIT Dictionary 최종 관리자 승인 서비스.

    중요:
    ----------------------------------------------------------
    LLM 판정 결과는 참고용 제안이다.

    실제 Dictionary 반영은
    반드시 관리자가 이 서비스를 통해 승인할 때만 발생한다.

    지원:
    - NEW_TERM 승인
    - ALIAS 승인
    - REJECT
    - HOLD

    관리자는 LLM 제안과 다른 값으로 승인할 수 있다.
    """

    VALID_TERM_TYPES = {
        "STYLE",
        "ITEM",
        "DETAIL",
        "MATERIAL",
        "COLOR",
        "TPO",
    }

    VALID_ATTRIBUTE_TYPES = {
        "FIT",
        "SILHOUETTE",
        "NECKLINE",
        "SLEEVE",
        "LENGTH",
        "DETAIL",
    }

    def __init__(self):
        self.normalizer = CandidateNormalizer()

    # ========================================================
    # NEW TERM APPROVE
    # ========================================================

    @transaction.atomic
    def approve_new_term(
        self,
        candidate: TermCandidate | int,
        *,
        term_type: str,
        canonical_name: str | None = None,
        english_name: str | None = None,
        description: str | None = None,
        attribute_type: str | None = None,
    ) -> DictionaryTerm:
        """
        관리자가 신규 DictionaryTerm으로 승인.

        LLM suggested_type과 달라도 허용.
        """

        candidate = self._resolve_candidate(candidate)

        term_type = (
            term_type
            or ""
        ).strip().upper()

        if term_type not in self.VALID_TERM_TYPES:
            raise ValueError(
                f"지원하지 않는 term_type: {term_type}"
            )

        # ----------------------------------------------------
        # DETAIL ATTRIBUTE TYPE
        # ----------------------------------------------------

        if term_type == "DETAIL":

            if attribute_type is None:
                raise ValueError(
                    "DETAIL 승인 시 attribute_type이 필요합니다."
                )

            attribute_type = (
                attribute_type
                .strip()
                .upper()
            )

            if (
                attribute_type
                not in self.VALID_ATTRIBUTE_TYPES
            ):
                raise ValueError(
                    (
                        "지원하지 않는 "
                        f"attribute_type: {attribute_type}"
                    )
                )

        else:
            attribute_type = None

        # ----------------------------------------------------
        # CANONICAL NAME
        # ----------------------------------------------------

        canonical_name = (
            canonical_name
            or candidate.raw_term
        ).strip()

        if not canonical_name:
            raise ValueError(
                "canonical_name이 비어 있습니다."
            )

        normalized_name = (
            self.normalizer
            .normalize(
                canonical_name
            )
        )

        if not normalized_name:
            raise ValueError(
                "normalized_name 생성에 실패했습니다."
            )

        # ----------------------------------------------------
        # DUPLICATE CHECK
        # ----------------------------------------------------

        existing = (
            DictionaryTerm.objects
            .filter(
                normalized_name=normalized_name
            )
            .first()
        )

        if existing is not None:
            raise ValueError(
                (
                    "동일 normalized_name의 DictionaryTerm이 "
                    f"이미 존재합니다: "
                    f"{existing.id} / "
                    f"{existing.canonical_name}"
                )
            )

        # ----------------------------------------------------
        # CREATE TERM
        # ----------------------------------------------------

        term = (
            DictionaryTerm.objects
            .create(
                canonical_name=canonical_name,
                normalized_name=normalized_name,
                english_name=english_name,
                term_type=term_type,
                description=(
                    description
                    or candidate.decision_reason
                ),
                status=(
                    DictionaryTerm.Status.ACTIVE
                ),
                first_seen_at=(
                    candidate.first_seen_at
                ),
                last_seen_at=(
                    candidate.last_seen_at
                ),
                embedding=(
                    candidate.embedding
                ),
                embedding_updated_at=(
                    candidate.embedding_updated_at
                ),
            )
        )

        # ----------------------------------------------------
        # TYPE DETAIL
        # ----------------------------------------------------

        self._create_type_detail(
            term=term,
            term_type=term_type,
            attribute_type=attribute_type,
        )

        # ----------------------------------------------------
        # CANDIDATE RESOLVE
        # ----------------------------------------------------

        self._resolve_as_approved(
            candidate=candidate,
        )

        return term

    # ========================================================
    # ALIAS APPROVE
    # ========================================================

    @transaction.atomic
    def approve_alias(
        self,
        candidate: TermCandidate | int,
        *,
        target_term_id: int,
        alias_text: str | None = None,
    ) -> TermAlias:
        """
        관리자가 기존 DictionaryTerm의 Alias로 승인.

        LLM nearest_term과 다른 target_term_id도 허용.
        """

        candidate = self._resolve_candidate(
            candidate
        )

        target_term = (
            DictionaryTerm.objects
            .filter(
                pk=target_term_id,
                status=(
                    DictionaryTerm.Status.ACTIVE
                ),
            )
            .first()
        )

        if target_term is None:
            raise ValueError(
                (
                    "승인 대상 DictionaryTerm이 "
                    f"없거나 ACTIVE가 아닙니다: "
                    f"{target_term_id}"
                )
            )

        alias_text = (
            alias_text
            or candidate.raw_term
        ).strip()

        if not alias_text:
            raise ValueError(
                "alias_text가 비어 있습니다."
            )

        normalized_alias = (
            self.normalizer
            .normalize(
                alias_text
            )
        )

        if not normalized_alias:
            raise ValueError(
                "normalized_alias 생성에 실패했습니다."
            )

        # ----------------------------------------------------
        # 이미 canonical로 존재하는지 확인
        # ----------------------------------------------------

        canonical_conflict = (
            DictionaryTerm.objects
            .filter(
                normalized_name=normalized_alias
            )
            .exclude(
                pk=target_term.pk
            )
            .first()
        )

        if canonical_conflict is not None:
            raise ValueError(
                (
                    "해당 alias 표현이 다른 "
                    "DictionaryTerm canonical과 충돌합니다: "
                    f"{canonical_conflict.id} / "
                    f"{canonical_conflict.canonical_name}"
                )
            )

        # ----------------------------------------------------
        # 기존 alias 확인
        # ----------------------------------------------------

        existing_alias = (
            TermAlias.objects
            .filter(
                normalized_alias=normalized_alias
            )
            .first()
        )

        if existing_alias is not None:

            if (
                existing_alias.term_id
                != target_term.id
            ):
                raise ValueError(
                    (
                        "동일 alias가 이미 다른 term에 "
                        "연결되어 있습니다: "
                        f"{existing_alias.term_id}"
                    )
                )

            alias = existing_alias

        else:

            alias = (
                TermAlias.objects
                .create(
                    term=target_term,
                    alias=alias_text,
                    normalized_alias=normalized_alias,
                )
            )

        # ----------------------------------------------------
        # 실제 관리자 승인 target 기록
        # ----------------------------------------------------

        candidate.nearest_term = (
            target_term
        )

        candidate.save(
            update_fields=[
                "nearest_term",
                "updated_at",
            ]
        )

        self._resolve_as_approved(
            candidate=candidate
        )

        return alias

    # ========================================================
    # REJECT
    # ========================================================

    @transaction.atomic
    def reject(
        self,
        candidate: TermCandidate | int,
        *,
        reason: str | None = None,
    ) -> TermCandidate:

        candidate = (
            self._resolve_candidate(
                candidate
            )
        )

        candidate.status = (
            TermCandidate.Status.REJECTED
        )

        candidate.reviewed_at = (
            timezone.now()
        )

        if reason:
            candidate.decision_reason = (
                reason
            )

        candidate.save(
            update_fields=[
                "status",
                "reviewed_at",
                "decision_reason",
                "updated_at",
            ]
        )

        return candidate

    # ========================================================
    # HOLD
    # ========================================================

    @transaction.atomic
    def hold(
        self,
        candidate: TermCandidate | int,
        *,
        reason: str | None = None,
    ) -> TermCandidate:

        candidate = (
            self._resolve_candidate(
                candidate
            )
        )

        candidate.status = (
            TermCandidate.Status.REVIEWING
        )

        candidate.reviewed_at = (
            timezone.now()
        )

        if reason:
            candidate.decision_reason = (
                reason
            )

        candidate.save(
            update_fields=[
                "status",
                "reviewed_at",
                "decision_reason",
                "updated_at",
            ]
        )

        return candidate

    # ========================================================
    # TYPE DETAIL
    # ========================================================

    def _create_type_detail(
        self,
        *,
        term: DictionaryTerm,
        term_type: str,
        attribute_type: str | None,
    ) -> None:

        if term_type == "DETAIL":

            Detail.objects.create(
                term=term,
                attribute_type=attribute_type,
            )

            return

        if term_type == "MATERIAL":

            Material.objects.create(
                term=term,
            )

            return

        if term_type == "ITEM":

            Item.objects.create(
                term=term,
            )

            return

        if term_type == "STYLE":

            Style.objects.create(
                term=term,
            )

            return

        if term_type == "COLOR":

            Color.objects.create(
                term=term,
            )

            return

        if term_type == "TPO":

            TPO.objects.create(
                term=term,
            )

            return

    # ========================================================
    # APPROVED
    # ========================================================

    def _resolve_as_approved(
        self,
        *,
        candidate: TermCandidate,
    ) -> None:

        candidate.status = (
            TermCandidate.Status.RESOLVED
        )

        candidate.reviewed_at = (
            timezone.now()
        )

        candidate.save(
            update_fields=[
                "status",
                "reviewed_at",
                "updated_at",
            ]
        )

    # ========================================================
    # RESOLVE CANDIDATE
    # ========================================================

    @staticmethod
    def _resolve_candidate(
        candidate: TermCandidate | int,
    ) -> TermCandidate:

        if isinstance(
            candidate,
            TermCandidate,
        ):
            return candidate

        return (
            TermCandidate.objects
            .get(
                pk=int(
                    candidate
                )
            )
        )