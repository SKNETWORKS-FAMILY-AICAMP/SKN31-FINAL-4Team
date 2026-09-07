from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    DictionaryTerm,
    TermAlias,
    TermCandidate,
    Style,
    Item,
    Detail,
    Material,
    Color,
    TPO,
)


@dataclass
class PromotionResult:
    success: bool
    action: str
    message: str

    term: DictionaryTerm | None = None
    alias: TermAlias | None = None


class TermPromotionService:

    # =========================================================
    # Public
    # =========================================================

    @transaction.atomic
    def promote(
        self,
        candidate: TermCandidate,
    ) -> PromotionResult:

        decision = candidate.decision

        # -----------------------------------------------------
        # PENDING
        # -----------------------------------------------------

        if decision == TermCandidate.Decision.PENDING:
            return PromotionResult(
                success=False,
                action="PENDING",
                message=(
                    "아직 판정이 완료되지 않은 후보입니다."
                ),
            )

        # -----------------------------------------------------
        # ALIAS
        # -----------------------------------------------------

        if decision == TermCandidate.Decision.ALIAS:
            return self._promote_alias(
                candidate
            )

        # -----------------------------------------------------
        # NEW TERM
        # -----------------------------------------------------

        if decision == TermCandidate.Decision.NEW_TERM:
            return self._promote_new_term(
                candidate
            )

        # -----------------------------------------------------
        # REJECT
        # -----------------------------------------------------

        if decision == TermCandidate.Decision.REJECT:
            return self._reject_candidate(
                candidate
            )

        raise ValueError(
            f"지원하지 않는 decision: {decision}"
        )

    # =========================================================
    # ALIAS
    # =========================================================

    def _promote_alias(
        self,
        candidate: TermCandidate,
    ) -> PromotionResult:

        if candidate.nearest_term is None:
            raise ValueError(
                "ALIAS 승격에는 nearest_term이 필요합니다."
            )

        term = candidate.nearest_term

        alias, created = (
            TermAlias.objects.get_or_create(
                term=term,
                alias=candidate.raw_term,
                source=None,
                defaults={
                    "alias_type": (
                        TermAlias.AliasType.SYNONYM
                    ),
                },
            )
        )

        self._resolve_candidate(
            candidate
        )

        return PromotionResult(
            success=True,
            action="ALIAS",
            message=(
                f"'{candidate.raw_term}'을 "
                f"'{term.canonical_name}'의 "
                f"별칭으로 "
                f"{'생성' if created else '확인'}했습니다."
            ),
            term=term,
            alias=alias,
        )

    # =========================================================
    # NEW TERM
    # =========================================================

    def _promote_new_term(
        self,
        candidate: TermCandidate,
    ) -> PromotionResult:

        if not candidate.suggested_type:
            raise ValueError(
                "NEW_TERM 승격에는 suggested_type이 "
                "필요합니다."
            )

        # 같은 타입 + 같은 표준명이 이미 있는지
        existing = (
            DictionaryTerm.objects
            .filter(
                term_type=candidate.suggested_type,
                canonical_name=candidate.raw_term,
            )
            .first()
        )

        if existing:
            raise ValueError(
                (
                    f"이미 동일한 표준 용어가 존재합니다: "
                    f"[{existing.term_type}] "
                    f"{existing.canonical_name}"
                )
            )

        # -----------------------------------------------------
        # DictionaryTerm 생성
        # -----------------------------------------------------

        term = DictionaryTerm.objects.create(
            canonical_name=candidate.raw_term,
            term_type=candidate.suggested_type,

            # 후보에서 이미 생성한 vector 재사용
            embedding=candidate.embedding,
            embedding_updated_at=(
                candidate.embedding_updated_at
            ),

            first_seen_at=candidate.first_seen_at,
            last_seen_at=candidate.last_seen_at,

            status=DictionaryTerm.Status.ACTIVE,
        )

        # -----------------------------------------------------
        # 타입별 상세 테이블
        # -----------------------------------------------------

        self._create_type_detail(
            term=term,
            candidate=candidate,
        )

        self._resolve_candidate(
            candidate
        )

        return PromotionResult(
            success=True,
            action="NEW_TERM",
            message=(
                f"신규 표준 용어 "
                f"'[{term.term_type}] "
                f"{term.canonical_name}'를 "
                f"생성했습니다."
            ),
            term=term,
        )

    # =========================================================
    # Type Detail
    # =========================================================

    def _create_type_detail(
        self,
        *,
        term: DictionaryTerm,
        candidate: TermCandidate,
    ) -> None:

        term_type = term.term_type

        # -----------------------------------------------------
        # STYLE
        # -----------------------------------------------------

        if term_type == DictionaryTerm.TermType.STYLE:

            Style.objects.get_or_create(
                term=term,
                defaults={
                    "is_core": self._looks_like_core(
                        candidate.raw_term
                    ),
                },
            )

            return

        # -----------------------------------------------------
        # ITEM
        # -----------------------------------------------------

        if term_type == DictionaryTerm.TermType.ITEM:

            Item.objects.get_or_create(
                term=term,
            )

            return

        # -----------------------------------------------------
        # DETAIL
        # -----------------------------------------------------

        if term_type == DictionaryTerm.TermType.DETAIL:

            Detail.objects.get_or_create(
                term=term,
                defaults={
                    "attribute_type": (
                        candidate
                        .suggested_attribute_type
                    ),
                },
            )

            return

        # -----------------------------------------------------
        # MATERIAL
        # -----------------------------------------------------

        if term_type == DictionaryTerm.TermType.MATERIAL:

            Material.objects.get_or_create(
                term=term,
            )

            return

        # -----------------------------------------------------
        # COLOR
        # -----------------------------------------------------

        if term_type == DictionaryTerm.TermType.COLOR:

            Color.objects.get_or_create(
                term=term,
            )

            return

        # -----------------------------------------------------
        # TPO
        # -----------------------------------------------------

        if term_type == DictionaryTerm.TermType.TPO:

            TPO.objects.get_or_create(
                term=term,
            )

            return

    # =========================================================
    # STYLE helper
    # =========================================================

    @staticmethod
    def _looks_like_core(
        term: str,
    ) -> bool:

        term_lower = term.lower().strip()

        return (
            term_lower.endswith("코어")
            or term_lower.endswith("core")
        )

    # =========================================================
    # REJECT
    # =========================================================

    def _reject_candidate(
        self,
        candidate: TermCandidate,
    ) -> PromotionResult:

        candidate.status = (
            TermCandidate.Status.REJECTED
        )

        candidate.reviewed_at = timezone.now()

        candidate.save(
            update_fields=[
                "status",
                "reviewed_at",
                "updated_at",
            ]
        )

        return PromotionResult(
            success=True,
            action="REJECT",
            message=(
                f"'{candidate.raw_term}' 후보를 "
                f"제외 처리했습니다."
            ),
        )

    # =========================================================
    # Candidate resolve
    # =========================================================

    @staticmethod
    def _resolve_candidate(
        candidate: TermCandidate,
    ) -> None:

        candidate.status = (
            TermCandidate.Status.RESOLVED
        )

        candidate.reviewed_at = timezone.now()

        candidate.save(
            update_fields=[
                "status",
                "reviewed_at",
                "updated_at",
            ]
        )