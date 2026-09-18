from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from apps.core.models import TermCandidate

from .review import (
    CandidateDecisionService,
    TermVectorMatcher,
)


class CandidateReviewPipeline:
    """
    FEEDIT TermCandidate 검토 파이프라인.

    단계
    ------------------------------------------------------------
    1. vector_preview()
       - candidate embedding 생성
       - DictionaryTerm Top-K 조회
       - nearest_term / similarity_score 저장
       - LLM 호출 없음

    2. decide_one()
       - 명시적으로 호출할 때만 LLM 1회
       - ALIAS / NEW_TERM / PENDING / REJECT 제안
       - save=True일 때 후보에 suggestion 저장
       - Dictionary 승격은 절대 하지 않음

    3. batch_vector()
       - 여러 후보의 vector 단계
       - LLM 호출 없음

    4. batch_decide()
       - 여러 후보 LLM 검토
       - 반드시 limit을 작게 두고 명시적으로 호출 권장

    Human promotion은 TermPromotionService에서 별도 실행.
    """

    def __init__(self):
        self.vector_matcher = TermVectorMatcher()

        self.decision_service = CandidateDecisionService(
            vector_matcher=self.vector_matcher,
        )

    # ============================================================
    # QUERYSET
    # ============================================================

    @staticmethod
    def queryset(
        *,
        cnv_only: bool = True,
        pending_only: bool = True,
    ) -> QuerySet:

        qs = (
            TermCandidate.objects
            .all()
            .order_by(
                "-detected_count",
                "-last_seen_at",
                "id",
            )
        )

        if pending_only:
            qs = qs.filter(
                status=TermCandidate.Status.PENDING,
            )

        if cnv_only:
            # Product Enrichment에서 저장한 CNV observation provenance.
            qs = (
                qs.filter(
                    observations__source_field__startswith=(
                        "attributes.observed_tags"
                    )
                )
                .distinct()
            )

        return qs

    # ============================================================
    # ONE: VECTOR ONLY
    # ============================================================

    def vector_preview(
        self,
        candidate: TermCandidate | int,
        *,
        top_k: int = 5,
        force_candidate_embedding: bool = False,
    ) -> dict[str, Any]:

        candidate = self._resolve_candidate(
            candidate
        )

        evidence = (
            self.vector_matcher
            .evidence_builder
            .build(candidate)
        )

        vector_result = (
            self.vector_matcher
            .match_candidate(
                candidate,
                evidence=evidence,
                top_k=top_k,
                force_candidate_embedding=(
                    force_candidate_embedding
                ),
            )
        )

        candidate.refresh_from_db()

        return {
            "candidate": {
                "id": candidate.id,
                "raw_term": candidate.raw_term,
                "normalized_term": (
                    candidate.normalized_term
                ),
                "suggested_type": (
                    candidate.suggested_type
                ),
                "detected_count": (
                    candidate.detected_count
                ),
                "source_count": (
                    candidate.source_count
                ),
                "nearest_term_id": (
                    candidate.nearest_term_id
                ),
                "similarity_score": (
                    float(candidate.similarity_score)
                    if candidate.similarity_score
                    is not None
                    else None
                ),
            },
            "eligible": evidence.eligible,
            "eligibility_reason": (
                evidence.eligibility_reason
            ),
            "evidence": evidence.to_dict(),
            "matches": (
                vector_result.to_dict()["matches"]
            ),
        }

    # ============================================================
    # ONE: LLM DECISION
    # ============================================================

    def decide_one(
        self,
        candidate: TermCandidate | int,
        *,
        top_k: int = 5,
        save: bool = True,
        require_eligible: bool = False,
    ) -> dict[str, Any]:
        """
        LLM 호출 발생.

        CNV처럼 플랫폼 taxonomy에서 직접 들어온 후보는
        관측 횟수가 1회여도 의미가 있으므로,
        이 wrapper의 기본 require_eligible=False.
        """

        candidate = self._resolve_candidate(
            candidate
        )

        evidence = (
            self.decision_service
            .evidence_builder
            .build(candidate)
        )

        vector_result = (
            self.vector_matcher
            .match_candidate(
                candidate,
                evidence=evidence,
                top_k=top_k,
            )
        )

        decision = (
            self.decision_service
            .decide_candidate(
                candidate,
                vector_result=vector_result,
                evidence=evidence,
                top_k=top_k,
                save=save,
                require_eligible=require_eligible,
            )
        )

        candidate.refresh_from_db()

        return {
            "candidate_id": candidate.id,
            "raw_term": candidate.raw_term,
            "vector_matches": (
                vector_result.to_dict()["matches"]
            ),
            "decision": decision.to_dict(),
            "saved": save,
            "candidate_state": {
                "status": candidate.status,
                "suggested_type": (
                    candidate.suggested_type
                ),
                "suggested_attribute_type": (
                    candidate
                    .suggested_attribute_type
                ),
                "decision": candidate.decision,
                "decision_reason": (
                    candidate.decision_reason
                ),
                "confidence": (
                    float(candidate.confidence)
                    if candidate.confidence
                    is not None
                    else None
                ),
                "nearest_term_id": (
                    candidate.nearest_term_id
                ),
                "similarity_score": (
                    float(candidate.similarity_score)
                    if candidate.similarity_score
                    is not None
                    else None
                ),
            },
        }

    # ============================================================
    # BATCH: VECTOR ONLY
    # ============================================================

    def batch_vector(
        self,
        *,
        limit: int = 20,
        top_k: int = 5,
        cnv_only: bool = True,
        pending_only: bool = True,
    ) -> dict[str, Any]:

        qs = self.queryset(
            cnv_only=cnv_only,
            pending_only=pending_only,
        )[:limit]

        output = {
            "requested_limit": limit,
            "processed": 0,
            "failed": 0,
            "items": [],
            "errors": [],
        }

        for candidate in qs:
            try:
                row = self.vector_preview(
                    candidate,
                    top_k=top_k,
                )

                output["processed"] += 1
                output["items"].append(row)

            except Exception as exc:
                output["failed"] += 1
                output["errors"].append(
                    {
                        "candidate_id":
                            candidate.id,
                        "raw_term":
                            candidate.raw_term,
                        "error_type":
                            type(exc).__name__,
                        "error":
                            str(exc),
                    }
                )

        return output

    # ============================================================
    # BATCH: EXPLICIT LLM
    # ============================================================

    def batch_decide(
        self,
        *,
        limit: int = 5,
        top_k: int = 5,
        cnv_only: bool = True,
        pending_only: bool = True,
        save: bool = True,
        require_eligible: bool = False,
    ) -> dict[str, Any]:
        """
        주의: 후보마다 LLM 호출 1회.

        먼저 batch_vector() 결과를 사람이 보고,
        작은 limit으로 실행하는 것을 권장.
        """

        qs = self.queryset(
            cnv_only=cnv_only,
            pending_only=pending_only,
        )[:limit]

        output = {
            "requested_limit": limit,
            "processed": 0,
            "failed": 0,
            "items": [],
            "errors": [],
        }

        for candidate in qs:
            try:
                row = self.decide_one(
                    candidate,
                    top_k=top_k,
                    save=save,
                    require_eligible=(
                        require_eligible
                    ),
                )

                output["processed"] += 1
                output["items"].append(row)

            except Exception as exc:
                output["failed"] += 1
                output["errors"].append(
                    {
                        "candidate_id":
                            candidate.id,
                        "raw_term":
                            candidate.raw_term,
                        "error_type":
                            type(exc).__name__,
                        "error":
                            str(exc),
                    }
                )

        return output

    # ============================================================
    # HELPERS
    # ============================================================

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
            .get(pk=int(candidate))
        )
