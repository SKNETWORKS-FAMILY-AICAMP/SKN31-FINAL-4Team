from __future__ import annotations

import json
import os
from decimal import Decimal

from pgvector.django import CosineDistance
from dataclasses import dataclass

from .evidence import CandidateEvidence, CandidateEvidenceBuilder


@dataclass(frozen=True)
class ReviewerConfig:
    vector_top_k: int = 10
    embedding_model: str = os.getenv(
        "FEEDIT_EMBEDDING_MODEL",
        "text-embedding-3-small",
    )
    llm_model: str = os.getenv(
        "FEEDIT_TERM_LLM_MODEL",
        "",
    )


from dataclasses import dataclass

from django.utils import timezone
from pgvector.django import CosineDistance

from apps.core.models import DictionaryTerm, TermCandidate


@dataclass
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


@dataclass
class CandidateVectorResult:
    candidate_id: int
    candidate_term: str
    matches: list[DictionaryVectorMatch]

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "candidate_term": self.candidate_term,
            "matches": [
                item.to_dict()
                for item in self.matches
            ],
        }


class TermVectorMatcher:
    """
    Optional explicit stage.

    IMPORTANT:
    constructing this class does NOT call an API.
    API calls happen only when embed()/match_candidate() is invoked.
    """

    def __init__(
        self,
        *,
        client=None,
        evidence_builder: CandidateEvidenceBuilder | None = None,
        config: ReviewerConfig | None = None,
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
        value = (text or "").strip()

        if not value:
            raise ValueError("Embedding할 텍스트가 비어 있습니다.")

        response = self._get_client().embeddings.create(
            model=self.config.embedding_model,
            input=value,
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

        if term.term_type == DictionaryTerm.TermType.DETAIL:
            detail = getattr(term, "detail", None)
            if detail:
                if detail.attribute_type:
                    parts.append(
                        f"세부 속성: {detail.attribute_type}"
                    )
                if detail.target_type:
                    parts.append(
                        f"적용 대상: {detail.target_type}"
                    )

        elif term.term_type == DictionaryTerm.TermType.MATERIAL:
            material = getattr(term, "material", None)
            if material:
                if material.material_type:
                    parts.append(
                        f"소재 유형: {material.material_type}"
                    )
                if material.process_type:
                    parts.append(
                        f"가공 유형: {material.process_type}"
                    )

        elif term.term_type == DictionaryTerm.TermType.STYLE:
            style = getattr(term, "style", None)
            if style and style.style_group:
                parts.append(
                    f"스타일 그룹: {style.style_group}"
                )

        elif term.term_type == DictionaryTerm.TermType.TPO:
            tpo = getattr(term, "tpo", None)
            if tpo and tpo.tpo_type:
                parts.append(
                    f"TPO 유형: {tpo.tpo_type}"
                )

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

        if evidence.left_neighbors:
            parts.append(
                "좌측 인접 표현: "
                + ", ".join(
                    f"{k}({v})"
                    for k, v
                    in evidence.left_neighbors.items()
                )
            )

        if evidence.right_neighbors:
            parts.append(
                "우측 인접 표현: "
                + ", ".join(
                    f"{k}({v})"
                    for k, v
                    in evidence.right_neighbors.items()
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

        for obs in evidence.observations:
            text = (obs.get("raw_text") or "").strip()

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

        count = 0

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
            count += 1

        return count

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

        limit = top_k or self.config.vector_top_k

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
            .order_by("distance")[:limit]
        )

        matches = []

        for term in queryset:
            similarity = max(
                -1.0,
                min(
                    1.0,
                    1.0 - float(term.distance),
                ),
            )

            matches.append(
                DictionaryVectorMatch(
                    term_id=term.id,
                    canonical_name=term.canonical_name,
                    term_type=term.term_type,
                    similarity=round(similarity, 5),
                    description=term.description,
                )
            )

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




@dataclass
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


class CandidateDecisionService:
    """
    OPTIONAL future reviewer.

    This is the ONLY module that asks an LLM for:
      - term_type
      - attribute_type
      - ALIAS / NEW_TERM / PENDING / REJECT suggestion

    IMPORTANT:
      - __init__ performs no API call.
      - Nothing calls this automatically.
      - decide_candidate() must be invoked explicitly.
      - Human promotion remains a separate service.
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
                evidence_builder=self.evidence_builder,
                config=self.config,
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
        """
        Builds the exact LLM input payload.

        NOTE:
        This may invoke EMBEDDING calls through vector_matcher,
        but it does NOT invoke the LLM.
        """

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
        """
        Explicit LLM call for ONE candidate only.

        Default save=False on purpose.
        """

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

        llm_input = {
            "candidate_evidence": evidence.to_dict(),
            "related_dictionary_terms": (
                vector_result.to_dict()["matches"]
            ),
        }

        raw_result = self._call_llm(llm_input)

        validated = self._validate_result(
            result=raw_result,
            vector_result=vector_result,
        )

        if save:
            self.save_suggestion(
                candidate=candidate,
                result=validated,
            )

        return validated

    def _call_llm(self, payload: dict) -> dict:
        if not self.config.llm_model:
            raise RuntimeError(
                "FEEDIT_TERM_LLM_MODEL이 설정되지 않았습니다. "
                "LLM 판정은 명시적으로 모델을 설정한 뒤 사용하세요."
            )

        system_prompt = """
You are the final fashion terminology reviewer for FEEDIT,
a fashion trend analysis platform.

You receive:
1. candidate_evidence: factual usage evidence collected by FEEDIT.
2. related_dictionary_terms: existing DictionaryTerms retrieved
   by semantic similarity.

Use both the supplied evidence and general fashion-domain knowledge.

Return one recommendation:
- ALIAS: same canonical concept as an existing dictionary term.
- NEW_TERM: reusable fashion concept that should stand independently.
- PENDING: meaningful but insufficient/ambiguous evidence.
- REJECT: generic fragment, marketing/noise, product-specific naming,
  or not a stable reusable fashion concept.

Allowed term_type:
STYLE, ITEM, DETAIL, MATERIAL, COLOR, TPO, null

If term_type is DETAIL, attribute_type must be one of:
FIT, SILHOUETTE, NECKLINE, SLEEVE, LENGTH, DETAIL

For non-DETAIL, attribute_type must be null.

Rules:
- Similarity is retrieval evidence, not an ALIAS threshold.
- ALIAS requires semantic equivalence, not mere relatedness.
- If ALIAS, nearest_term_id must be one of the supplied
  related_dictionary_terms.
- NEW_TERM may keep the nearest related term for comparison or null.
- REJECT must use nearest_term_id=null.
- Explain meaning, observed usage, relationship to existing terms,
  and why the decision follows.
- Do not merely repeat counts.
""".strip()

        user_prompt = (
            "Review this FEEDIT term candidate.\n\n"
            + json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        response = self._get_client().responses.create(
            model=self.config.llm_model,
            input=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "term_candidate_decision",
                    "strict": True,
                    "schema": {
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
                    },
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
            raise ValueError(
                f"잘못된 decision: {decision}"
            )

        if (
            term_type is not None
            and term_type not in self.VALID_TERM_TYPES
        ):
            raise ValueError(
                f"잘못된 term_type: {term_type}"
            )

        if term_type == "DETAIL":
            if attribute_type not in self.VALID_ATTRIBUTE_TYPES:
                raise ValueError(
                    "DETAIL인데 올바른 attribute_type이 없습니다: "
                    f"{attribute_type}"
                )
        else:
            attribute_type = None

        if decision == "REJECT":
            nearest_term_id = None

        if decision == "ALIAS":
            if nearest_term_id is None:
                raise ValueError(
                    "ALIAS인데 nearest_term_id가 없습니다."
                )

            allowed_ids = {
                item.term_id
                for item in vector_result.matches
            }

            if nearest_term_id not in allowed_ids:
                raise ValueError(
                    "ALIAS nearest_term_id가 Vector Top-K에 없습니다: "
                    f"{nearest_term_id}"
                )

        confidence = max(
            0.0,
            min(confidence, 1.0),
        )

        if not reason:
            raise ValueError(
                "LLM reason이 비어 있습니다."
            )

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
        """
        Stores LLM suggestion only.
        Does NOT promote DictionaryTerm / TermAlias.
        """

        candidate.suggested_type = result.term_type
        candidate.suggested_attribute_type = result.attribute_type
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