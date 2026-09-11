from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class TermhoodResult:
    score: float
    decision: str
    reason: str
    features: dict


class TermhoodScorer:
    def __init__(
        self,
        *,
        min_document_frequency: int = 3,
        review_threshold: float = 0.55,
        high_threshold: float = 0.75,
    ):
        self.min_document_frequency = min_document_frequency
        self.review_threshold = review_threshold
        self.high_threshold = high_threshold

    @staticmethod
    def _clip01(value: float) -> float:
        return max(0.0, min(1.0, value))

    def score(
        self,
        *,
        document_frequency: int,
        observation_count: int,
        source_diversity: int,
        fashion_context_ratio: float,
        concentration: float,
    ) -> TermhoodResult:
        df_score = self._clip01(
            math.log1p(max(document_frequency, 0)) / math.log(11)
        )
        obs_score = self._clip01(
            math.log1p(max(observation_count, 0)) / math.log(21)
        )
        source_score = self._clip01(source_diversity / 3.0)
        context_score = self._clip01(fashion_context_ratio)
        dispersion_score = self._clip01(1.0 - concentration)

        score = (
            0.30 * df_score
            + 0.15 * obs_score
            + 0.15 * source_score
            + 0.25 * context_score
            + 0.15 * dispersion_score
        )
        score = round(self._clip01(score), 4)

        if document_frequency < self.min_document_frequency:
            decision = "DROP"
            reason = "서로 다른 상품 기준 최소 관측 횟수 미달"
        elif score >= self.high_threshold:
            decision = "HIGH"
            reason = "반복성·패션 문맥·분산도가 강한 표현"
        elif score >= self.review_threshold:
            decision = "REVIEW"
            reason = "최소 반복성과 패션 문맥 근거 충족"
        else:
            decision = "HOLD"
            reason = "관측은 있으나 패션 용어성 근거가 약함"

        return TermhoodResult(
            score=score,
            decision=decision,
            reason=reason,
            features={
                "document_frequency": document_frequency,
                "observation_count": observation_count,
                "source_diversity": source_diversity,
                "fashion_context_ratio": round(fashion_context_ratio, 4),
                "concentration": round(concentration, 4),
            },
        )
