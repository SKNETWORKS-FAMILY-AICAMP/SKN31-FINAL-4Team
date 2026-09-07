from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    TermCandidate,
    TermCandidateObservation,
)


class TermCandidateRepository:

    @transaction.atomic
    def save_candidate(
        self,
        *,
        raw_term: str,
        raw_text: str,
        source=None,
        source_type: str,
        source_entity_id: str | None = None,
        suggested_type: str | None = None,
        confidence: float | None = None,
    ) -> TermCandidate:

        now = timezone.now()

        # ----------------------------------
        # 1. 기존 후보 찾기
        # ----------------------------------

        candidate = (
            TermCandidate.objects
            .filter(
                raw_term=raw_term,
                suggested_type=suggested_type,
            )
            .first()
        )

        # ----------------------------------
        # 2. 신규 후보
        # ----------------------------------

        if candidate is None:
            candidate = TermCandidate.objects.create(
                raw_term=raw_term,
                suggested_type=suggested_type,
                detected_count=0,
                source_count=0,
                confidence=confidence,
                first_seen_at=now,
                last_seen_at=now,
            )

        # ----------------------------------
        # 3. 같은 source가 기존에 있었는지
        # ----------------------------------

        source_already_seen = False

        if source is not None:
            source_already_seen = (
                candidate.observations
                .filter(source=source)
                .exists()
            )

        # ----------------------------------
        # 4. Observation 중복 체크
        # ----------------------------------

        observation_filter = {
            "candidate": candidate,
            "source_type": source_type,
            "detected_phrase": raw_term,
        }

        if source is not None:
            observation_filter["source"] = source

        if source_entity_id:
            observation_filter[
                "source_entity_id"
            ] = source_entity_id

        already_exists = (
            TermCandidateObservation.objects
            .filter(**observation_filter)
            .exists()
        )

        # 같은 상품/영상에서 다시 발견한 경우
        # 중복 count 방지
        if already_exists:
            candidate.last_seen_at = now
            candidate.save(
                update_fields=[
                    "last_seen_at",
                    "updated_at",
                ]
            )

            return candidate

        # ----------------------------------
        # 5. Observation 생성
        # ----------------------------------

        TermCandidateObservation.objects.create(
            candidate=candidate,
            source=source,
            source_type=source_type,
            source_entity_id=source_entity_id,
            detected_phrase=raw_term,
            raw_text=raw_text,
            detected_at=now,
        )

        # ----------------------------------
        # 6. 후보 집계값 갱신
        # ----------------------------------

        candidate.detected_count += 1
        candidate.last_seen_at = now

        if (
            source is not None
            and not source_already_seen
        ):
            candidate.source_count += 1

        if (
            confidence is not None
            and candidate.confidence is None
        ):
            candidate.confidence = confidence

        candidate.save(
            update_fields=[
                "detected_count",
                "source_count",
                "last_seen_at",
                "confidence",
                "updated_at",
            ]
        )

        return candidate