from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DecisionResult:
    decision: str
    reason: str
    confidence: float


class CandidateDecisionService:

    def decide(
        self,
        *,
        similarity: float | None,
        fashion_confidence: float | None = None,
    ) -> DecisionResult:

        if similarity is None:
            return DecisionResult(
                decision="PENDING",
                reason="기존 용어 유사도 결과 없음",
                confidence=0.0,
            )

        # 패션 용어 신뢰도가 너무 낮으면
        if (
            fashion_confidence is not None
            and fashion_confidence < 0.40
        ):
            return DecisionResult(
                decision="REJECT",
                reason="패션 용어 관련성이 낮음",
                confidence=0.80,
            )

        # 일단 임시 threshold
        if similarity >= 0.90:
            return DecisionResult(
                decision="ALIAS",
                reason=(
                    f"기존 용어와 높은 의미 유사도 "
                    f"({similarity:.3f})"
                ),
                confidence=similarity,
            )

        if similarity <= 0.65:
            return DecisionResult(
                decision="NEW_TERM",
                reason=(
                    f"기존 용어와 의미 차이가 큼 "
                    f"({similarity:.3f})"
                ),
                confidence=1 - similarity,
            )

        return DecisionResult(
            decision="PENDING",
            reason=(
                f"유사도가 애매한 구간 "
                f"({similarity:.3f})"
            ),
            confidence=0.5,
        )