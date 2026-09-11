from __future__ import annotations

from dataclasses import dataclass

from .compound_resolver import CompoundResolver


@dataclass
class EligibilityResult:
    label: str
    reason: str
    compound: dict | None = None


class SemanticEligibilityClassifier:
    """
    Termhood 이후 의미 역할 분류.

    v4 원칙:
    - 기존 Dict / Alias / Brand / Category는 CandidateGate에서 이미 제거
    - multi-part compound는 COMPONENT
    - 단일 metadata/generic/marketing은 별도 분류
    - 나머지만 DICT_CANDIDATE

    Generic/Marketing seed는 무한 blacklist가 아니라
    역할 분류 seed로만 사용한다.
    """

    METADATA = {
        "여성",
        "여자",
        "남성",
        "남자",
        "공용",
        "유니섹스",
        "봄",
        "여름",
        "가을",
        "겨울",
        "간절기",
        "ss",
        "fw",
        "spring",
        "summer",
        "fall",
        "autumn",
        "winter",
        "썸머",
    }

    GENERIC = {
        "기본",
        "베이직",
        "소프트",
        "라이트",
        "하프",
        "세미",
        "사이드",
        "라인",
        "더블",
    }

    MARKETING = {
        "에센셜",
        "프리미엄",
        "시그니처",
        "스테디",
    }

    def __init__(self, dictionary_guard):
        self.guard = dictionary_guard
        self.compound_resolver = CompoundResolver(
            dictionary_guard
        )

    def classify(self, term: str) -> EligibilityResult:
        normalized = self.guard.normalize(term)

        compound = self.compound_resolver.resolve(
            normalized
        )

        if compound.is_compound:
            return EligibilityResult(
                label="COMPONENT",
                reason=compound.reason or "분해 가능한 복합 표현",
                compound={
                    "parts": [
                        {
                            "text": part.text,
                            "role": part.role,
                        }
                        for part in compound.parts
                    ]
                },
            )

        if normalized in self.METADATA:
            return EligibilityResult(
                label="METADATA",
                reason="성별/시즌 등 상품 메타데이터 표현",
            )

        if normalized in self.GENERIC:
            return EligibilityResult(
                label="GENERIC",
                reason="독립 패션 개념보다 범용 수식 성격이 강함",
            )

        if normalized in self.MARKETING:
            return EligibilityResult(
                label="MARKETING",
                reason="독립 패션 개념보다 상품 마케팅 수식 성격이 강함",
            )

        return EligibilityResult(
            label="DICT_CANDIDATE",
            reason=(
                "Known/Brand/Category/Compound/"
                "Metadata 필터를 통과한 표현"
            ),
        )
