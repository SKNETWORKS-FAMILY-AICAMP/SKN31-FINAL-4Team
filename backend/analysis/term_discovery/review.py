from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.utils import timezone
from pgvector.django import CosineDistance

from apps.core.models import DictionaryTerm, TermCandidate
from .observation import CandidateEvidence, CandidateEvidenceBuilder


# ============================================================
# CONFIG / DTO
# ============================================================

@dataclass(frozen=True)
class ReviewerConfig:
    vector_top_k: int = 5

    min_detected_count: int = 3
    min_entity_count: int = 2
    min_source_count: int = 2
    min_context_diversity: int = 2

    embedding_model: str = os.getenv(
        "FEEDIT_EMBEDDING_MODEL",
        "text-embedding-3-small",
    )
    llm_model: str = os.getenv(
        "FEEDIT_TERM_LLM_MODEL",
        "",
    )


@dataclass(frozen=True)
class DictionaryVectorMatch:
    term_id: int
    canonical_name: str
    term_type: str
    similarity: float
    description: str | None

    def to_dict(self) -> dict:
        return {
            "term_id": self.term_id,
            "canonical_name": self.canonical_name,
            "term_type": self.term_type,
            "similarity": self.similarity,
            "description": self.description,
        }


@dataclass(frozen=True)
class CandidateVectorResult:
    candidate_id: int
    candidate_term: str
    matches: list[DictionaryVectorMatch]

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "candidate_term": self.candidate_term,
            "matches": [
                match.to_dict()
                for match in self.matches
            ],
        }


@dataclass(frozen=True)
class CandidateDecisionResult:
    term_type: str | None
    attribute_type: str | None
    decision: str
    nearest_term_id: int | None
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "term_type": self.term_type,
            "attribute_type": self.attribute_type,
            "decision": self.decision,
            "nearest_term_id": self.nearest_term_id,
            "confidence": self.confidence,
            "reason": self.reason,
        }


# ============================================================
# VECTOR MATCHER
# ============================================================

class TermVectorMatcher:
    """
    TermCandidate -> embedding -> DictionaryTerm Top-K.
    객체 생성만으로는 API 호출하지 않는다.
    """

    def __init__(
        self,
        *,
        client=None,
        config: ReviewerConfig | None = None,
        evidence_builder: CandidateEvidenceBuilder | None = None,
    ):
        self._client = client
        self.config = config or ReviewerConfig()
        self.evidence_builder = (
            evidence_builder
            or CandidateEvidenceBuilder(self.config)
        )

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def embed(self, text: str) -> list[float]:
        text = (text or "").strip()
        if not text:
            raise ValueError("Embedding할 텍스트가 비어 있습니다.")

        response = self._get_client().embeddings.create(
            model=self.config.embedding_model,
            input=text,
        )
        return response.data[0].embedding

    @staticmethod
    def build_dictionary_embedding_text(
        term: DictionaryTerm,
    ) -> str:
        parts = [
            f"표준 용어: {term.canonical_name}",
            f"용어 유형: {term.term_type}",
        ]

        if term.english_name:
            parts.append(f"영문명: {term.english_name}")
        if term.description:
            parts.append(f"설명: {term.description}")

        subtype = {
            DictionaryTerm.TermType.DETAIL: "detail",
            DictionaryTerm.TermType.MATERIAL: "material",
            DictionaryTerm.TermType.STYLE: "style",
            DictionaryTerm.TermType.TPO: "tpo",
        }.get(term.term_type)

        detail = getattr(term, subtype, None) if subtype else None

        if subtype == "detail" and detail:
            if detail.attribute_type:
                parts.append(f"세부 속성: {detail.attribute_type}")
            if detail.target_type:
                parts.append(f"적용 대상: {detail.target_type}")

        elif subtype == "material" and detail:
            if detail.material_type:
                parts.append(f"소재 유형: {detail.material_type}")
            if detail.process_type:
                parts.append(f"가공 유형: {detail.process_type}")

        elif subtype == "style" and detail and detail.style_group:
            parts.append(f"스타일 그룹: {detail.style_group}")

        elif subtype == "tpo" and detail and detail.tpo_type:
            parts.append(f"TPO 유형: {detail.tpo_type}")

        return "\n".join(parts)

    @staticmethod
    def build_candidate_embedding_text(
        evidence: CandidateEvidence,
    ) -> str:
        parts = [
            f"후보 용어: {evidence.term}",
            f"총 관측 횟수: {evidence.detected_count}",
            f"상품/엔터티 다양성: {evidence.entity_count}",
            f"문맥 다양성: {evidence.context_diversity}",
        ]

        for label, values in (
            ("좌측 인접 표현", evidence.left_neighbors),
            ("우측 인접 표현", evidence.right_neighbors),
        ):
            if values:
                parts.append(
                    f"{label}: "
                    + ", ".join(
                        f"{key}({count})"
                        for key, count in values.items()
                    )
                )

        if evidence.known_term_cooccurrence:
            parts.append(
                "기존 용어 동시출현: "
                + ", ".join(
                    (
                        f"{item.get('canonical_name')}"
                        f"[{item.get('term_type')}]"
                        f"({item.get('count')})"
                    )
                    for item
                    in evidence.known_term_cooccurrence
                )
            )

        seen = set()
        for observation in evidence.observations:
            text = (observation.get("raw_text") or "").strip()
            if text and text not in seen:
                seen.add(text)
                parts.append(f"사용 문맥: {text}")

        return "\n".join(parts)

    def ensure_dictionary_embeddings(self) -> int:
        queryset = (
            DictionaryTerm.objects
            .filter(
                status=DictionaryTerm.Status.ACTIVE,
                embedding__isnull=True,
            )
            .order_by("id")
        )

        updated = 0

        for term in queryset.iterator():
            term.embedding = self.embed(
                self.build_dictionary_embedding_text(term)
            )
            term.embedding_updated_at = timezone.now()
            term.save(
                update_fields=[
                    "embedding",
                    "embedding_updated_at",
                    "updated_at",
                ]
            )
            updated += 1

        return updated

    def ensure_candidate_embedding(
        self,
        candidate: TermCandidate,
        *,
        evidence: CandidateEvidence | None = None,
        force: bool = False,
    ) -> list[float]:
        if candidate.embedding is not None and not force:
            return list(candidate.embedding)

        evidence = (
            evidence
            or self.evidence_builder.build(candidate)
        )

        candidate.embedding = self.embed(
            self.build_candidate_embedding_text(evidence)
        )
        candidate.embedding_updated_at = timezone.now()
        candidate.save(
            update_fields=[
                "embedding",
                "embedding_updated_at",
                "updated_at",
            ]
        )

        return list(candidate.embedding)

    def match_candidate(
        self,
        candidate: TermCandidate,
        *,
        evidence: CandidateEvidence | None = None,
        top_k: int | None = None,
        ensure_dictionary_embeddings: bool = True,
        force_candidate_embedding: bool = False,
    ) -> CandidateVectorResult:
        if candidate is None:
            raise ValueError("TermCandidate가 None입니다.")

        evidence = (
            evidence
            or self.evidence_builder.build(candidate)
        )

        if ensure_dictionary_embeddings:
            self.ensure_dictionary_embeddings()

        candidate_vector = self.ensure_candidate_embedding(
            candidate,
            evidence=evidence,
            force=force_candidate_embedding,
        )

        queryset = (
            DictionaryTerm.objects
            .filter(
                status=DictionaryTerm.Status.ACTIVE,
                embedding__isnull=False,
            )
            .annotate(
                distance=CosineDistance(
                    "embedding",
                    candidate_vector,
                )
            )
            .order_by("distance")[
                : top_k or self.config.vector_top_k
            ]
        )

        matches = [
            DictionaryVectorMatch(
                term_id=term.id,
                canonical_name=term.canonical_name,
                term_type=term.term_type,
                similarity=round(
                    max(
                        -1.0,
                        min(
                            1.0,
                            1.0 - float(term.distance),
                        ),
                    ),
                    5,
                ),
                description=term.description,
            )
            for term in queryset
        ]

        if matches:
            candidate.nearest_term_id = matches[0].term_id
            candidate.similarity_score = matches[0].similarity
        else:
            candidate.nearest_term = None
            candidate.similarity_score = None

        candidate.save(
            update_fields=[
                "nearest_term",
                "similarity_score",
                "updated_at",
            ]
        )

        return CandidateVectorResult(
            candidate_id=candidate.id,
            candidate_term=candidate.raw_term,
            matches=matches,
        )


# ============================================================
# LLM REVIEWER
# ============================================================

class CandidateDecisionService:
    """
    LLM은 '추천'만 저장한다.
    실제 Dictionary 반영은 TermPromotionService에서 수행.
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
    VALID_DECISIONS = {
        "ALIAS",
        "NEW_TERM",
        "PENDING",
        "REJECT",
    }

    SYSTEM_PROMPT = """
You are the final fashion terminology reviewer for FEEDIT.

Inputs:
1. candidate_evidence: factual usage evidence.
2. related_dictionary_terms: semantic vector search results.

Return one recommendation:
- ALIAS: same concept as an existing term.
- NEW_TERM: independent reusable fashion concept.
- PENDING: meaningful but evidence is insufficient.
- REJECT: noise, marketing, product-specific naming, or unstable concept.

Allowed term_type:
STYLE, ITEM, DETAIL, MATERIAL, COLOR, TPO, null

If term_type is DETAIL, attribute_type must be one of:
FIT, SILHOUETTE, NECKLINE, SLEEVE, LENGTH, DETAIL

Rules:
- Vector similarity is retrieval evidence, not an ALIAS threshold.
- ALIAS requires semantic equivalence.
- ALIAS nearest_term_id must be in related_dictionary_terms.
- NEW_TERM nearest_term_id may be related term or null.
- REJECT nearest_term_id must be null.
- Explain the reason using both evidence and fashion-domain meaning.
""".strip()

    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "term_type": {
                "type": ["string", "null"],
                "enum": [
                    "STYLE",
                    "ITEM",
                    "DETAIL",
                    "MATERIAL",
                    "COLOR",
                    "TPO",
                    None,
                ],
            },
            "attribute_type": {
                "type": ["string", "null"],
                "enum": [
                    "FIT",
                    "SILHOUETTE",
                    "NECKLINE",
                    "SLEEVE",
                    "LENGTH",
                    "DETAIL",
                    None,
                ],
            },
            "decision": {
                "type": "string",
                "enum": [
                    "ALIAS",
                    "NEW_TERM",
                    "PENDING",
                    "REJECT",
                ],
            },
            "nearest_term_id": {
                "type": ["integer", "null"],
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "reason": {
                "type": "string",
            },
        },
        "required": [
            "term_type",
            "attribute_type",
            "decision",
            "nearest_term_id",
            "confidence",
            "reason",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        client=None,
        config: ReviewerConfig | None = None,
        evidence_builder: CandidateEvidenceBuilder | None = None,
        vector_matcher: TermVectorMatcher | None = None,
    ):
        self._client = client
        self.config = config or ReviewerConfig()

        self.evidence_builder = (
            evidence_builder
            or CandidateEvidenceBuilder(self.config)
        )

        self.vector_matcher = (
            vector_matcher
            or TermVectorMatcher(
                client=client,
                config=self.config,
                evidence_builder=self.evidence_builder,
            )
        )

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def prepare_review_payload(
        self,
        candidate: TermCandidate,
        *,
        top_k: int | None = None,
        require_eligible: bool = True,
    ) -> dict:
        evidence = self.evidence_builder.build(candidate)

        if require_eligible and not evidence.eligible:
            return {
                "ready": False,
                "candidate_id": candidate.id,
                "candidate_term": candidate.raw_term,
                "reason": evidence.eligibility_reason,
                "candidate_evidence": evidence.to_dict(),
                "related_dictionary_terms": [],
            }

        vector_result = self.vector_matcher.match_candidate(
            candidate,
            evidence=evidence,
            top_k=top_k,
        )

        return {
            "ready": True,
            "candidate_id": candidate.id,
            "candidate_term": candidate.raw_term,
            "candidate_evidence": evidence.to_dict(),
            "related_dictionary_terms": (
                vector_result.to_dict()["matches"]
            ),
        }

    def decide_candidate(
        self,
        candidate: TermCandidate,
        *,
        vector_result: CandidateVectorResult | None = None,
        evidence: CandidateEvidence | None = None,
        top_k: int | None = None,
        save: bool = False,
        require_eligible: bool = True,
    ) -> CandidateDecisionResult:
        evidence = (
            evidence
            or self.evidence_builder.build(candidate)
        )

        if require_eligible and not evidence.eligible:
            return CandidateDecisionResult(
                term_type=None,
                attribute_type=None,
                decision="PENDING",
                nearest_term_id=None,
                confidence=0.0,
                reason=evidence.eligibility_reason,
            )

        vector_result = (
            vector_result
            or self.vector_matcher.match_candidate(
                candidate,
                evidence=evidence,
                top_k=top_k,
            )
        )

        result = self._call_llm(
            {
                "candidate_evidence": evidence.to_dict(),
                "related_dictionary_terms": (
                    vector_result.to_dict()["matches"]
                ),
            }
        )

        decision = self._validate_result(
            result=result,
            vector_result=vector_result,
        )

        if save:
            self.save_suggestion(
                candidate=candidate,
                result=decision,
            )

        return decision

    def _call_llm(
        self,
        payload: dict[str, Any],
    ) -> dict:
        if not self.config.llm_model:
            raise RuntimeError(
                "FEEDIT_TERM_LLM_MODEL이 설정되지 않았습니다."
            )

        response = self._get_client().responses.create(
            model=self.config.llm_model,
            input=[
                {
                    "role": "system",
                    "content": self.SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "Review this FEEDIT term candidate.\n\n"
                        + json.dumps(
                            payload,
                            ensure_ascii=False,
                            indent=2,
                            default=str,
                        )
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "term_candidate_decision",
                    "strict": True,
                    "schema": self.RESPONSE_SCHEMA,
                }
            },
        )

        return json.loads(response.output_text)

    def _validate_result(
        self,
        *,
        result: dict,
        vector_result: CandidateVectorResult,
    ) -> CandidateDecisionResult:
        term_type = result.get("term_type")
        attribute_type = result.get("attribute_type")
        decision = result.get("decision")
        nearest_term_id = result.get("nearest_term_id")
        confidence = float(result.get("confidence", 0.0))
        reason = str(result.get("reason") or "").strip()

        if decision not in self.VALID_DECISIONS:
            raise ValueError(f"잘못된 decision: {decision}")

        if (
            term_type is not None
            and term_type not in self.VALID_TERM_TYPES
        ):
            raise ValueError(f"잘못된 term_type: {term_type}")

        if term_type == "DETAIL":
            if attribute_type not in self.VALID_ATTRIBUTE_TYPES:
                raise ValueError(
                    "DETAIL인데 올바른 "
                    f"attribute_type이 없습니다: {attribute_type}"
                )
        else:
            attribute_type = None

        if decision == "REJECT":
            nearest_term_id = None

        if decision == "ALIAS":
            allowed_ids = {
                item.term_id
                for item in vector_result.matches
            }

            if nearest_term_id is None:
                raise ValueError(
                    "ALIAS인데 nearest_term_id가 없습니다."
                )

            if nearest_term_id not in allowed_ids:
                raise ValueError(
                    "ALIAS nearest_term_id가 "
                    f"Vector Top-K에 없습니다: {nearest_term_id}"
                )

        confidence = max(
            0.0,
            min(confidence, 1.0),
        )

        if not reason:
            raise ValueError("LLM reason이 비어 있습니다.")

        return CandidateDecisionResult(
            term_type=term_type,
            attribute_type=attribute_type,
            decision=decision,
            nearest_term_id=nearest_term_id,
            confidence=confidence,
            reason=reason,
        )

    @staticmethod
    def save_suggestion(
        *,
        candidate: TermCandidate,
        result: CandidateDecisionResult,
    ) -> None:
        candidate.suggested_type = result.term_type
        candidate.suggested_attribute_type = (
            result.attribute_type
        )
        candidate.decision = result.decision
        candidate.decision_reason = result.reason
        candidate.confidence = Decimal(
            str(round(result.confidence, 4))
        )

        if result.nearest_term_id is not None:
            candidate.nearest_term_id = result.nearest_term_id
        elif result.decision == "REJECT":
            candidate.nearest_term = None

        candidate.status = TermCandidate.Status.REVIEWING
        candidate.reviewed_at = timezone.now()

        candidate.save(
            update_fields=[
                "suggested_type",
                "suggested_attribute_type",
                "decision",
                "decision_reason",
                "confidence",
                "nearest_term",
                "status",
                "reviewed_at",
                "updated_at",
            ]
        )
