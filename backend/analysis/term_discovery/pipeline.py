from __future__ import annotations

from dataclasses import dataclass

from apps.core.models import TermCandidate

from .candidate import CandidateBuilder
from .evidence import CandidateEvidenceBuilder, TermDiscoveryConfig as EvidenceConfig
from .repository import TermCandidateRepository
from .reviewer import (
    CandidateDecisionService,
    ReviewerConfig,
    TermVectorMatcher,
)


@dataclass(frozen=True)
class PipelineConfig:
    min_length: int = 2
    max_length: int = 40
    min_detected_count: int = 3
    min_entity_count: int = 2
    min_source_count: int = 2
    min_context_diversity: int = 2


class TermDiscoveryPipeline:
    """
    FEEDIT STEP 3.

    일부러 run_all() 없음.

    1) preview()
    2) save_candidates()
    3) evidence()
    4) vector_review()   # 선택
    5) llm_review()      # 선택

    Dictionary 승격은 promotion.py를
    Admin/HITL에서 별도로 호출.
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
    ):
        self.config = (
            config
            or PipelineConfig()
        )

        self.builder = CandidateBuilder(
            min_length=self.config.min_length,
            max_length=self.config.max_length,
        )

        self.repository = (
            TermCandidateRepository()
        )

        self.evidence_builder = (
            CandidateEvidenceBuilder(
                EvidenceConfig(
                    min_detected_count=(
                        self.config.min_detected_count
                    ),
                    min_entity_count=(
                        self.config.min_entity_count
                    ),
                    min_source_count=(
                        self.config.min_source_count
                    ),
                    min_context_diversity=(
                        self.config.min_context_diversity
                    ),
                )
            )
        )

        self.vector_matcher = (
            TermVectorMatcher(
                evidence_builder=(
                    self.evidence_builder
                ),
                config=ReviewerConfig(),
            )
        )

        self.decision_service = (
            CandidateDecisionService(
                evidence_builder=(
                    self.evidence_builder
                ),
                vector_matcher=(
                    self.vector_matcher
                ),
                config=ReviewerConfig(),
            )
        )

    def preview(
        self,
        product_sources,
    ) -> dict:
        """
        STEP 3-A
        DB write 없음.
        API 호출 없음.
        """

        result = (
            self.builder.prepare_products(
                product_sources
            )
        )

        return {
            "prepared": [
                item.to_dict()
                for item
                in result["prepared"]
            ],
            "dropped": result["dropped"],
            "summary": {
                "unknown_evidence_count": (
                    result["evidence_count"]
                ),
                "prepared_count": len(
                    result["prepared"]
                ),
                "dropped_count": len(
                    result["dropped"]
                ),
            },
        }

    def save_candidates(
        self,
        product_sources,
    ) -> dict:
        """
        STEP 3-B
        TermCandidate + Observation 저장.
        API 호출 없음.
        """

        result = (
            self.builder.prepare_products(
                product_sources
            )
        )

        saved = []

        for item in result["prepared"]:
            ev = item.evidence

            candidate = (
                self.repository.save_candidate(
                    raw_term=item.raw_term,
                    raw_text=(
                        ev.source_text
                        or ev.surface
                        or item.raw_term
                    ),
                    source=ev.source_object,
                    source_type=(
                        "PRODUCT_UNKNOWN"
                    ),
                    source_entity_id=(
                        str(
                            ev.product_source_id
                        )
                        if (
                            ev.product_source_id
                            is not None
                        )
                        else None
                    ),
                    source_field=(
                        ev.source_field
                    ),
                    residual_text=(
                        item.raw_term
                    ),
                )
            )

            saved.append(candidate)

        return {
            "saved_candidates": [
                {
                    "id": item.id,
                    "raw_term": (
                        item.raw_term
                    ),
                    "normalized_term": (
                        item.normalized_term
                    ),
                    "detected_count": (
                        item.detected_count
                    ),
                    "source_count": (
                        item.source_count
                    ),
                    "status": item.status,
                    "decision": item.decision,
                }
                for item in saved
            ],
            "dropped": result["dropped"],
        }

    def evidence(
        self,
        candidate: TermCandidate | int,
    ) -> dict:
        """
        STEP 3-C
        관측 사실 + readiness.
        API 호출 없음.
        """

        candidate = self._candidate(
            candidate
        )

        return (
            self.evidence_builder
            .build(candidate)
            .to_dict()
        )

    def vector_review(
        self,
        candidate: TermCandidate | int,
        *,
        top_k: int = 10,
    ) -> dict:
        """
        STEP 3-D
        선택 호출.
        Embedding API 호출 가능.
        """

        candidate = self._candidate(
            candidate
        )

        evidence = (
            self.evidence_builder
            .build(candidate)
        )

        if not evidence.eligible:
            return {
                "candidate_id": candidate.id,
                "eligible": False,
                "reason": (
                    evidence
                    .eligibility_reason
                ),
                "matches": [],
            }

        result = (
            self.vector_matcher
            .match_candidate(
                candidate,
                evidence=evidence,
                top_k=top_k,
            )
        )

        payload = result.to_dict()
        payload["eligible"] = True
        return payload

    def llm_review(
        self,
        candidate: TermCandidate | int,
        *,
        top_k: int = 10,
        save: bool = False,
    ) -> dict:
        """
        STEP 3-E
        선택 호출.
        한 candidate에 대해서만 LLM 판정.
        자동 호출 절대 없음.
        """

        candidate = self._candidate(
            candidate
        )

        result = (
            self.decision_service
            .decide_candidate(
                candidate,
                top_k=top_k,
                save=save,
                require_eligible=True,
            )
        )

        return result.to_dict()

    @staticmethod
    def _candidate(
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
