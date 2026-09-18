from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    ProductSource,
    ProductTerm,
    TermCandidate,
    TermCandidateObservation,
)


def normalize_dictionary_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    text = str(value).lower().strip()
    if not text:
        return ""

    text = text.replace("_", " ")
    text = text.replace("-", " ")
    text = re.sub(r"[^\w가-힣\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class ProductAnalysisRepository:
    ANALYSIS_KEY = "feedit_analysis"

    # ============================================================
    # STEP 3: JSON + normalized_name
    # ============================================================

    @transaction.atomic
    def save_analysis_json(
        self,
        product_source: ProductSource,
        result: dict[str, Any],
    ) -> dict[str, Any]:

        locked = (
            ProductSource.objects
            .select_for_update()
            .get(pk=product_source.pk)
        )

        attributes = (
            deepcopy(locked.attributes)
            if isinstance(locked.attributes, dict)
            else {}
        )

        payload = {
            "version": 3,
            "analyzed_at": timezone.now().isoformat(),
            "normalized_name": result.get("normalized_name") or "",
            "tags": result.get("tags") or [],
            "known_terms": result.get("known_terms") or [],
            "known_by_type": result.get("known_by_type") or {},
            "unknown_terms": result.get("unknown_terms") or [],
            "known_evidence": result.get("known_evidence") or [],
            "unknown_evidence": result.get("unknown_evidence") or [],
            "evidence_summary": result.get("evidence_summary") or {},
            "summary": result.get("summary") or {},
        }

        attributes[self.ANALYSIS_KEY] = payload

        locked.attributes = attributes
        locked.normalized_name = payload["normalized_name"] or None

        locked.save(
            update_fields=[
                "normalized_name",
                "attributes",
                "updated_at",
            ]
        )

        return payload

    # ============================================================
    # STEP 4: known_terms -> ProductTerm
    # ============================================================

    @transaction.atomic
    def persist_known_terms(
        self,
        product_source: ProductSource,
    ) -> dict[str, int]:

        analysis = self._get_analysis(product_source)
        known_terms = analysis.get("known_terms") or []

        created_count = 0
        existing_count = 0
        skipped_count = 0

        for row in known_terms:
            term_id = row.get("term_id")

            if not term_id:
                skipped_count += 1
                continue

            _, created = ProductTerm.objects.get_or_create(
                product_source=product_source,
                term_id=term_id,
            )

            if created:
                created_count += 1
            else:
                existing_count += 1

        return {
            "created": created_count,
            "existing": existing_count,
            "skipped": skipped_count,
        }

    # ============================================================
    # STEP 5: CNV unknown -> TermCandidate/Observation
    # ============================================================

    @transaction.atomic
    def persist_unknown_candidates(
        self,
        product_source: ProductSource,
        *,
        cnv_only: bool = True,
    ) -> dict[str, int]:
        """
        기본은 cnv_only=True.

        이유:
        PRODUCT_NAME/TAG unknown에는 MADE, mlt, 사이즈, 판매문구 등
        노이즈가 많다.

        ZIGZAG_CNV_TPO/TREND/STYLE은 플랫폼 taxonomy signal이므로
        신규 용어 후보로 우선 저장한다.
        """

        analysis = self._get_analysis(product_source)
        evidence_rows = analysis.get("unknown_evidence") or []

        created_candidates = 0
        created_observations = 0
        existing_observations = 0
        skipped = 0
        touched_candidate_ids = set()

        source = getattr(product_source, "source", None)
        detected_at = timezone.now()

        for row in evidence_rows:

            source_field_raw = str(
                row.get("source_field") or ""
            ).upper()

            if (
                cnv_only
                and not source_field_raw.startswith(
                    "ZIGZAG_CNV_"
                )
            ):
                skipped += 1
                continue

            raw_term = str(
                row.get("text") or ""
            ).strip()

            if not raw_term:
                skipped += 1
                continue

            normalized_term = normalize_dictionary_text(
                raw_term
            )

            suggested_type = (
                row.get("suggested_type")
                or self._suggested_type_from_source_field(
                    source_field_raw
                )
                or None
            )

            suggested_attribute_type = (
                row.get("suggested_attribute_type")
                or row.get("attribute_type")
                or None
            )

            candidate = (
                TermCandidate.objects
                .filter(
                    normalized_term=normalized_term,
                    suggested_type=suggested_type,
                )
                .order_by("id")
                .first()
            )

            if candidate is None:
                candidate = TermCandidate.objects.create(
                    raw_term=raw_term,
                    suggested_type=suggested_type,
                    suggested_attribute_type=(
                        suggested_attribute_type
                    ),
                    detected_count=0,
                    source_count=0,
                    status=TermCandidate.Status.PENDING,
                    decision=TermCandidate.Decision.PENDING,
                    first_seen_at=detected_at,
                    last_seen_at=detected_at,
                )
                created_candidates += 1

            touched_candidate_ids.add(candidate.id)

            source_field = self._build_source_field(row)
            source_type = self._map_source_type(
                source_field_raw
            )

            detected_phrase = raw_term
            raw_text = str(
                row.get("source_text")
                or row.get("surface")
                or raw_term
            )
            residual_text = str(
                row.get("surface")
                or raw_term
            )

            _, created = (
                TermCandidateObservation.objects
                .get_or_create(
                    candidate=candidate,
                    source=source,
                    source_type=source_type,
                    source_entity_id=str(
                        product_source.id
                    ),
                    source_field=source_field,
                    detected_phrase=detected_phrase,
                    defaults={
                        "raw_text": raw_text,
                        "residual_text": residual_text,
                        "detected_at": detected_at,
                    },
                )
            )

            if created:
                created_observations += 1
            else:
                existing_observations += 1

        # 집계값은 observation 실데이터 기준 재계산.
        for candidate_id in touched_candidate_ids:
            candidate = TermCandidate.objects.get(
                id=candidate_id
            )

            observations = candidate.observations.all()

            candidate.detected_count = observations.count()
            candidate.source_count = (
                observations
                .exclude(source__isnull=True)
                .values("source_id")
                .distinct()
                .count()
            )

            first_obs = (
                observations
                .order_by("detected_at")
                .first()
            )
            last_obs = (
                observations
                .order_by("-detected_at")
                .first()
            )

            if first_obs:
                candidate.first_seen_at = (
                    first_obs.detected_at
                )

            if last_obs:
                candidate.last_seen_at = (
                    last_obs.detected_at
                )

            candidate.save(
                update_fields=[
                    "detected_count",
                    "source_count",
                    "first_seen_at",
                    "last_seen_at",
                    "updated_at",
                ]
            )

        return {
            "candidate_created": created_candidates,
            "observation_created": created_observations,
            "observation_existing": existing_observations,
            "skipped": skipped,
        }

    # ============================================================
    # HELPERS
    # ============================================================

    def _get_analysis(
        self,
        product_source: ProductSource,
    ) -> dict[str, Any]:

        attributes = (
            product_source.attributes
            if isinstance(product_source.attributes, dict)
            else {}
        )

        analysis = attributes.get(self.ANALYSIS_KEY)

        if not isinstance(analysis, dict):
            raise ValueError(
                "feedit_analysis JSON이 없습니다. "
                "분석 단계를 먼저 실행하세요."
            )

        return analysis

    @staticmethod
    def _suggested_type_from_source_field(
        source_field: str,
    ) -> str | None:

        mapping = {
            "ZIGZAG_CNV_TREND": "STYLE",
            "ZIGZAG_CNV_STYLE": "STYLE",
            "ZIGZAG_CNV_TPO": "TPO",
        }

        return mapping.get(source_field)

    @staticmethod
    def _map_source_type(
        source_field: str | None,
    ) -> str:

        source_field = str(
            source_field or ""
        ).upper()

        if source_field == "PRODUCT_NAME":
            return (
                TermCandidateObservation
                .SourceType
                .PRODUCT_NAME
            )

        if (
            source_field == "TAG"
            or source_field.startswith(
                "ZIGZAG_CNV_"
            )
        ):
            return (
                TermCandidateObservation
                .SourceType
                .PRODUCT_ATTRIBUTE
            )

        return (
            TermCandidateObservation
            .SourceType
            .OTHER
        )

    @staticmethod
    def _build_source_field(
        row: dict,
    ) -> str:

        source_field = str(
            row.get("source_field")
            or "OTHER"
        ).upper()

        source_index = row.get(
            "source_index"
        )

        if source_field == "PRODUCT_NAME":
            return "normalized_name"

        if source_field == "TAG":
            if source_index is None:
                return "attributes.tags"

            return (
                f"attributes.tags[{source_index}]"
            )

        if source_field.startswith(
            "ZIGZAG_CNV_"
        ):
            if source_index is None:
                return "attributes.observed_tags"

            return (
                "attributes.observed_tags"
                f"[{source_index}]"
            )

        return source_field.lower()
