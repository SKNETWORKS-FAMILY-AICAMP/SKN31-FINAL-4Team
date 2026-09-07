from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class CandidateClassificationResult:
    term_type: str
    attribute_type: str | None
    confidence: float
    reason: str


class CandidateClassifier:

    MODEL = "gpt-5.6"

    TERM_TYPES = [
        "STYLE",
        "ITEM",
        "DETAIL",
        "MATERIAL",
        "COLOR",
        "TPO",
    ]

    DETAIL_TYPES = [
        "FIT",
        "SILHOUETTE",
        "NECKLINE",
        "SLEEVE",
        "LENGTH",
        "DETAIL",
    ]

    def __init__(self):
        self.client = OpenAI()

    def classify_candidate(
        self,
        candidate,
    ) -> CandidateClassificationResult:

        observations = (
            candidate.observations
            .order_by("-detected_at")[:8]
        )

        contexts = [
            obs.raw_text
            for obs in observations
        ]

        context_text = "\n".join(
            f"- {text}"
            for text in contexts
        )

        prompt = f"""
다음은 FEEDIT 패션 용어 사전에서 아직 등록되지 않은 신규 후보 표현이다.

후보:
{candidate.raw_term}

실제 사용 문맥:
{context_text}

이 후보 표현 자체가 패션 문맥에서 어떤 역할을 하는지 분류하라.

FEEDIT의 타입 정의:

STYLE:
고프코어, 발레코어, 클래식, 아메카지, 긱시크처럼
전체적인 패션 미학, 스타일 정체성, 코어, 룩을 나타내는 개념.

ITEM:
팬츠, 재킷, 셔츠, 스커트, 부츠처럼
상품 종류 자체를 나타내는 개념.

DETAIL:
상품의 형태적 특징이나 구조적 속성.
핏, 실루엣, 넥라인, 기장, 소매, 셔링, 절개 등을 포함.

MATERIAL:
데님, 스웨이드, 트위드, 울, 레더, 피치스킨처럼
상품의 소재나 원단을 나타내는 개념.

COLOR:
블랙, 버건디, 코발트블루 등 색상 개념.

TPO:
하객룩, 출근룩, 공항룩처럼
착용 상황이나 목적을 나타내는 개념.

DETAIL인 경우 attribute_type도 분류하라:

FIT
SILHOUETTE
NECKLINE
SLEEVE
LENGTH
DETAIL

중요:
주변에 '팬츠'라는 단어가 등장한다고 해서 후보를 ITEM으로 분류하지 마라.
후보 표현 자체가 무엇을 의미하는지 판단해야 한다.

JSON만 반환하라.

{{
  "term_type": "...",
  "attribute_type": null,
  "confidence": 0.0,
  "reason": "..."
}}
"""

        response = self.client.responses.create(
            model=self.MODEL,
            input=prompt,
        )

        text = response.output_text.strip()

        data = json.loads(text)

        result = CandidateClassificationResult(
            term_type=data["term_type"],
            attribute_type=data.get(
                "attribute_type"
            ),
            confidence=float(
                data["confidence"]
            ),
            reason=data["reason"],
        )

        candidate.suggested_type = (
            result.term_type
        )

        candidate.suggested_attribute_type = (
            result.attribute_type
        )

        candidate.confidence = (
            result.confidence
        )

        candidate.note = (
            result.reason
        )

        candidate.save(
            update_fields=[
                "suggested_type",
                "suggested_attribute_type",
                "confidence",
                "note",
                "updated_at",
            ]
        )

        return result