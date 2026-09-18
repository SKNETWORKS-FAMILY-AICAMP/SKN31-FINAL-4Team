from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import TermCandidate

from .observation import (
    AggregatedCandidate,
    DiscoveryDecision,
    TermDiscovery,
)
from .observation import TermObservationStore
from .candidate import DictionaryGuard
from .candidate import CompoundResolver


class TermDiscoveryPipeline:
    """
    FEEDIT Term Discovery Daily Pipeline.

    flow:
        S3 observations
        -> compound resolution
        -> discovery
        -> lightweight refine
        -> KEEP only
        -> TermCandidate DB upsert
        -> candidate-specific S3 evidence

    중요:
    - TermCandidateObservation DB는 사용하지 않는다.
    - 같은 날짜를 재실행해도 candidate count가 중복 증가하지 않는다.
    - candidate별 S3 summary의 dates를 source of truth로 사용한다.
    """

    GENERIC_TOKENS = {
        "팬츠",
        "재킷",
        "자켓",
        "셔츠",
        "스커트",
        "상의",
        "하의",
        "제품",
        "상품",
        "디자인",
    }

    def __init__(
        self,
        *,
        store: TermObservationStore | None = None,
        discovery: TermDiscovery | None = None,
        dictionary_guard: DictionaryGuard | None = None,
        compound_resolver: CompoundResolver | None = None,
    ):
        self.store = store or TermObservationStore()
        self.discovery = discovery or TermDiscovery()

        self.dictionary_guard = (
            dictionary_guard
            or DictionaryGuard()
        )

        self.compound_resolver = (
            compound_resolver
            or CompoundResolver(
                self.dictionary_guard
            )
        )

    # ========================================================
    # STEP 1. LOAD
    # ========================================================

    def load(
        self,
        target_date: date,
    ) -> list[dict]:
        return self.store.load_observations(
            target_date
        )

    # ========================================================
    # STEP 2. DISCOVER
    # ========================================================

    def discover(
        self,
        observations: list[dict],
    ) -> dict:
        return self.discovery.discover(
            observations
        )

    # ========================================================
    # STEP 2.5. COMPOUND RESOLUTION
    # ========================================================

    @staticmethod
    def _observation_source_id(
        observation: dict,
    ) -> int | None:
        """
        Observation 포맷이 소스별로 조금 달라도
        가능한 source_id 후보를 안전하게 읽는다.

        source_id가 없어도 global DiscoveryExclusion /
        DictionaryGuard 기반 분해는 정상 동작한다.
        """

        for key in (
            "source_id",
            "product_source_source_id",
        ):
            value = observation.get(key)

            if value in (
                None,
                "",
            ):
                continue

            try:
                return int(value)
            except (
                TypeError,
                ValueError,
            ):
                pass

        source = observation.get("source")

        if isinstance(source, dict):
            value = source.get("id")

            if value not in (
                None,
                "",
            ):
                try:
                    return int(value)
                except (
                    TypeError,
                    ValueError,
                ):
                    pass

        return None

    def resolve_compounds(
        self,
        observations: list[dict],
    ) -> dict:
        """
        Discovery 전에 UNKNOWN observation의 복합 표현을 해체한다.

        규칙
        --------------------------------------------------------
        1. NOT_COMPOUND
           -> 원 observation 유지

        2. COMPONENT + UNKNOWN 없음
           ex)
               봄아우터
               -> 봄(KNOWN_TERM) + 아우터(CATEGORY)

           -> 원문 candidate를 제거.
              이미 알고 있는 의미만으로 100% 설명되므로
              TermCandidate로 올리지 않는다.

        3. COMPONENT + UNKNOWN 있음
           ex)
               남성정장
               -> 남성(METADATA_GENDER) + 정장(UNKNOWN)

           -> 원문은 제거하고 UNKNOWN part만 새 observation으로 만든다.

        이렇게 해야 compound를 분해한 뒤의
        detected_count / document_count / source_count가
        TermDiscovery aggregate 단계에서 다시 정확히 계산된다.
        """

        resolved_observations: list[dict] = []

        component_removed: list[dict] = []
        component_rewritten: list[dict] = []

        untouched_count = 0
        generated_unknown_count = 0

        for observation in observations:
            term = str(
                observation.get("normalized_term")
                or observation.get("raw_term")
                or ""
            ).strip()

            if not term:
                # 원래 discovery의 empty handling에 맡긴다.
                resolved_observations.append(
                    observation
                )
                untouched_count += 1
                continue

            source_id = self._observation_source_id(
                observation
            )

            result = (
                self.compound_resolver.resolve(
                    term,
                    source_id=source_id,
                )
            )

            if not result.is_compound:
                resolved_observations.append(
                    observation
                )
                untouched_count += 1
                continue

            unknown_parts = [
                part
                for part in result.parts
                if part.role == "UNKNOWN"
            ]

            parts_payload = [
                {
                    "text": part.text,
                    "role": part.role,
                    "exclusion_reason": (
                        part.exclusion_reason
                    ),
                }
                for part in result.parts
            ]

            # -----------------------------------------------
            # 완전히 기존 지식으로 설명되는 compound
            # -----------------------------------------------
            if not unknown_parts:
                component_removed.append(
                    {
                        "original_term": term,
                        "reason": result.reason,
                        "parts": parts_payload,
                    }
                )
                continue

            # -----------------------------------------------
            # UNKNOWN component만 observation으로 재투입
            # -----------------------------------------------
            generated_terms: list[str] = []

            for part in unknown_parts:
                normalized_part = (
                    self.dictionary_guard.normalize(
                        part.text
                    )
                )

                if not normalized_part:
                    continue

                cloned = dict(observation)

                cloned["raw_term"] = part.text
                cloned["normalized_term"] = (
                    normalized_part
                )

                # 원래 compound 추적용 metadata.
                cloned["compound_parent_term"] = term
                cloned["compound_reason"] = (
                    result.reason
                )
                cloned["compound_parts"] = (
                    parts_payload
                )

                resolved_observations.append(
                    cloned
                )

                generated_terms.append(
                    normalized_part
                )
                generated_unknown_count += 1

            component_rewritten.append(
                {
                    "original_term": term,
                    "generated_terms": (
                        generated_terms
                    ),
                    "reason": result.reason,
                    "parts": parts_payload,
                }
            )

        return {
            "observations": resolved_observations,
            "input_count": len(observations),
            "output_count": len(
                resolved_observations
            ),
            "untouched_count": untouched_count,
            "component_removed_count": len(
                component_removed
            ),
            "component_rewritten_count": len(
                component_rewritten
            ),
            "generated_unknown_count": (
                generated_unknown_count
            ),
            "component_removed": (
                component_removed
            ),
            "component_rewritten": (
                component_rewritten
            ),
        }

    # ========================================================
    # STEP 3. REFINE
    # ========================================================

    def refine(
        self,
        rows: list[AggregatedCandidate],
    ) -> dict:
        """
        현재는 보수적인 구조 정제만 수행.

        단일 표현:
            KEEP

        복합 표현:
            - 모두 generic token -> DROP
            - 구성 token들이 이미 각각 atomic candidate -> DROP
            - 그 외 KEEP

        의미 판정 / 임베딩 / LLM은 아직 여기서 하지 않는다.
        """

        if not rows:
            return {
                "keep": [],
                "drop": [],
            }

        atomic_terms = {
            row.normalized_term
            for row in rows
            if (
                row.normalized_term
                and len(
                    row.normalized_term.split()
                ) == 1
            )
        }

        keep: list[AggregatedCandidate] = []
        drop: list[DiscoveryDecision] = []

        for row in rows:
            term = (
                row.normalized_term
                or ""
            ).strip()

            if not term:
                drop.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="DROP",
                        reason="REFINER_EMPTY",
                    )
                )
                continue

            tokens = term.split()

            if len(tokens) == 1:
                keep.append(row)
                continue

            if all(
                token in self.GENERIC_TOKENS
                for token in tokens
            ):
                drop.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="DROP",
                        reason="REFINER_GENERIC_COMPOSITE",
                    )
                )
                continue

            if all(
                token in atomic_terms
                for token in tokens
            ):
                drop.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="DROP",
                        reason="REFINER_KNOWN_SUBTERM_COMPOSITE",
                    )
                )
                continue

            keep.append(row)

        return {
            "keep": keep,
            "drop": drop,
        }

    # ========================================================
    # STEP 4. CANDIDATE DB + S3 EVIDENCE
    # ========================================================

    def promote_keep(
        self,
        *,
        target_date: date,
        observations: list[dict],
        rows: list[AggregatedCandidate],
    ) -> dict:
        """
        Refiner KEEP만 TermCandidate에 반영.

        같은 target_date 재실행:
            S3 dates[target_date]를 overwrite
            totals를 dates 전체에서 다시 계산
            DB count도 totals로 SET

        따라서 += 방식이 아니며 중복 증가하지 않는다.
        """

        created = []
        updated = []
        skipped = []

        observations_by_term: dict[
            str,
            list[dict],
        ] = {}

        for obs in observations:
            term = str(
                obs.get("normalized_term")
                or ""
            ).strip()

            if not term:
                continue

            observations_by_term.setdefault(
                term,
                [],
            ).append(obs)

        for row in rows:
            term_observations = (
                observations_by_term.get(
                    row.normalized_term,
                    [],
                )
            )

            result = self._upsert_candidate(
                target_date=target_date,
                row=row,
                observations=term_observations,
            )

            if result["action"] == "CREATED":
                created.append(result)
            elif result["action"] == "UPDATED":
                updated.append(result)
            else:
                skipped.append(result)

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "created_count": len(created),
            "updated_count": len(updated),
            "skipped_count": len(skipped),
        }

    @transaction.atomic
    def _upsert_candidate(
        self,
        *,
        target_date: date,
        row: AggregatedCandidate,
        observations: list[dict],
    ) -> dict:

        candidate = (
            TermCandidate.objects
            .select_for_update()
            .filter(
                normalized_term=row.normalized_term
            )
            .first()
        )

        # 이미 처리 완료된 candidate는 다시 건드리지 않는다.
        if candidate is not None:
            if candidate.status in {
                TermCandidate.Status.RESOLVED,
                TermCandidate.Status.REJECTED,
            }:
                return {
                    "action": "SKIPPED",
                    "candidate_id": candidate.id,
                    "term": row.normalized_term,
                    "reason": (
                        f"CANDIDATE_{candidate.status}"
                    ),
                }

        created = candidate is None

        first_seen = self._parse_dt(
            row.first_seen_at
        )

        last_seen = self._parse_dt(
            row.last_seen_at
        )

        now = timezone.now()

        if candidate is None:
            candidate = TermCandidate(
                raw_term=(
                    row.raw_term
                    or row.normalized_term
                ),
                normalized_term=row.normalized_term,
                detected_count=0,
                document_count=0,
                source_count=0,
                source_breakdown={},
                field_breakdown={},
                sample_contexts=[],
                first_seen_at=(
                    first_seen
                    or now
                ),
                last_seen_at=(
                    last_seen
                    or now
                ),
                status=TermCandidate.Status.PENDING,
                decision=TermCandidate.Decision.PENDING,
            )

            candidate.save()

        summary = self._upsert_candidate_evidence(
            candidate=candidate,
            target_date=target_date,
            row=row,
            observations=observations,
        )

        totals = summary["totals"]

        candidate.raw_term = (
            candidate.raw_term
            or row.raw_term
            or row.normalized_term
        )

        candidate.detected_count = (
            totals["detected_count"]
        )

        candidate.document_count = (
            totals["document_count"]
        )

        candidate.source_count = len(
            totals["source_breakdown"]
        )

        candidate.source_breakdown = (
            totals["source_breakdown"]
        )

        candidate.field_breakdown = (
            totals["field_breakdown"]
        )

        candidate.sample_contexts = (
            totals["sample_contexts"]
        )

        summary_first_seen = self._parse_dt(
            totals.get("first_seen_at")
        )

        summary_last_seen = self._parse_dt(
            totals.get("last_seen_at")
        )

        if summary_first_seen:
            if (
                candidate.first_seen_at is None
                or summary_first_seen
                < candidate.first_seen_at
            ):
                candidate.first_seen_at = (
                    summary_first_seen
                )

        if summary_last_seen:
            if (
                candidate.last_seen_at is None
                or summary_last_seen
                > candidate.last_seen_at
            ):
                candidate.last_seen_at = (
                    summary_last_seen
                )

        candidate.evidence_s3_uri = (
            self._candidate_base_uri(
                candidate.id
            )
        )

        candidate.evidence_updated_at = now

        candidate.save(
            update_fields=[
                "raw_term",
                "detected_count",
                "document_count",
                "source_count",
                "source_breakdown",
                "field_breakdown",
                "sample_contexts",
                "first_seen_at",
                "last_seen_at",
                "evidence_s3_uri",
                "evidence_updated_at",
                "updated_at",
            ]
        )

        return {
            "action": (
                "CREATED"
                if created
                else "UPDATED"
            ),
            "candidate_id": candidate.id,
            "term": candidate.normalized_term,
            "detected_count": (
                candidate.detected_count
            ),
            "document_count": (
                candidate.document_count
            ),
            "source_count": (
                candidate.source_count
            ),
            "evidence_s3_uri": (
                candidate.evidence_s3_uri
            ),
        }

    # ========================================================
    # S3 CANDIDATE EVIDENCE - IDEMPOTENT
    # ========================================================

    def _upsert_candidate_evidence(
        self,
        *,
        candidate: TermCandidate,
        target_date: date,
        row: AggregatedCandidate,
        observations: list[dict],
    ) -> dict:

        base_key = (
            f"term-discovery/candidates/"
            f"candidate_id={candidate.id}"
        )

        date_key = target_date.isoformat()

        evidence_key = (
            f"{base_key}/evidence/"
            f"date={date_key}/"
            f"evidence.jsonl"
        )

        summary_key = (
            f"{base_key}/summary.json"
        )

        # 같은 날짜는 같은 key에 overwrite.
        self._put_jsonl(
            key=evidence_key,
            rows=observations,
        )

        summary = self._read_json_or_default(
            key=summary_key,
            default={
                "candidate_id": candidate.id,
                "normalized_term": (
                    row.normalized_term
                ),
                "dates": {},
                "totals": {},
            },
        )

        summary["candidate_id"] = (
            candidate.id
        )

        summary["normalized_term"] = (
            row.normalized_term
        )

        dates = summary.setdefault(
            "dates",
            {},
        )

        dates[date_key] = {
            "detected_count": (
                row.detected_count
            ),
            "document_count": (
                row.document_count
            ),
            "source_breakdown": (
                row.source_breakdown
            ),
            "field_breakdown": (
                row.field_breakdown
            ),
            "sample_contexts": (
                row.sample_contexts
            ),
            "first_seen_at": (
                row.first_seen_at
            ),
            "last_seen_at": (
                row.last_seen_at
            ),
            "evidence_key": evidence_key,
        }

        summary["totals"] = (
            self._rebuild_totals(
                dates
            )
        )

        summary["updated_at"] = (
            timezone.now().isoformat()
        )

        self._put_json(
            key=summary_key,
            data=summary,
        )

        return summary

    @staticmethod
    def _rebuild_totals(
        dates: dict,
    ) -> dict:

        detected_count = 0
        document_count = 0

        source_counter = Counter()
        field_counter = Counter()

        contexts: list[dict] = []
        seen_contexts = set()

        first_seen_values = []
        last_seen_values = []

        for date_key in sorted(dates):
            row = dates[date_key]

            detected_count += int(
                row.get(
                    "detected_count",
                    0,
                )
                or 0
            )

            document_count += int(
                row.get(
                    "document_count",
                    0,
                )
                or 0
            )

            source_counter.update(
                row.get(
                    "source_breakdown",
                    {},
                )
                or {}
            )

            field_counter.update(
                row.get(
                    "field_breakdown",
                    {},
                )
                or {}
            )

            first_seen = row.get(
                "first_seen_at"
            )

            last_seen = row.get(
                "last_seen_at"
            )

            if first_seen:
                first_seen_values.append(
                    str(first_seen)
                )

            if last_seen:
                last_seen_values.append(
                    str(last_seen)
                )

            for context in (
                row.get(
                    "sample_contexts",
                    [],
                )
                or []
            ):
                text = str(
                    context.get("text")
                    or ""
                ).strip()

                if not text:
                    continue

                key = (
                    context.get("source"),
                    context.get(
                        "source_type"
                    ),
                    context.get(
                        "source_entity_id"
                    ),
                    text,
                )

                if key in seen_contexts:
                    continue

                seen_contexts.add(key)
                contexts.append(context)

                if len(contexts) >= 10:
                    break

        return {
            "detected_count": (
                detected_count
            ),
            "document_count": (
                document_count
            ),
            "source_breakdown": dict(
                source_counter
            ),
            "field_breakdown": dict(
                field_counter
            ),
            "sample_contexts": (
                contexts[:10]
            ),
            "first_seen_at": (
                min(first_seen_values)
                if first_seen_values
                else None
            ),
            "last_seen_at": (
                max(last_seen_values)
                if last_seen_values
                else None
            ),
        }

    # ========================================================
    # S3 HELPERS
    # ========================================================

    def _read_json_or_default(
        self,
        *,
        key: str,
        default: dict,
    ) -> dict:

        try:
            response = (
                self.store.s3.get_object(
                    Bucket=self.store.bucket,
                    Key=key,
                )
            )

        except self.store.s3.exceptions.NoSuchKey:
            return default

        except Exception as exc:
            response_code = (
                getattr(
                    exc,
                    "response",
                    {},
                )
                .get("Error", {})
                .get("Code")
            )

            if response_code in {
                "NoSuchKey",
                "404",
                "NotFound",
            }:
                return default

            raise

        body = (
            response["Body"]
            .read()
            .decode("utf-8")
        )

        if not body.strip():
            return default

        return json.loads(body)

    def _put_jsonl(
        self,
        *,
        key: str,
        rows: list[dict],
    ) -> None:

        body = "\n".join(
            json.dumps(
                row,
                ensure_ascii=False,
                default=str,
            )
            for row in rows
        )

        if body:
            body += "\n"

        self.store.s3.put_object(
            Bucket=self.store.bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/x-ndjson",
        )

    def _put_json(
        self,
        *,
        key: str,
        data: dict,
    ) -> None:

        body = json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        self.store.s3.put_object(
            Bucket=self.store.bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )

    def _candidate_base_uri(
        self,
        candidate_id: int,
    ) -> str:

        return (
            f"s3://{self.store.bucket}/"
            f"term-discovery/candidates/"
            f"candidate_id={candidate_id}/"
        )

    # ========================================================
    # DATETIME
    # ========================================================

    @staticmethod
    def _parse_dt(
        value,
    ) -> datetime | None:

        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            parsed = value

        else:
            parsed = parse_datetime(
                str(value)
            )

        if parsed is None:
            return None

        if timezone.is_naive(parsed):
            parsed = parsed.replace(
                tzinfo=dt_timezone.utc
            )

        return parsed

    # ========================================================
    # RUN - NO DB WRITE
    # ========================================================

    def run_to_refine(
        self,
        target_date: date,
    ) -> dict:
        """
        S3
        -> Compound Resolution
        -> Discovery
        -> Refine

        DB write 없음.
        """

        raw_observations = self.load(
            target_date
        )

        compound = self.resolve_compounds(
            raw_observations
        )

        observations = compound[
            "observations"
        ]

        discovered = self.discover(
            observations
        )

        refined = self.refine(
            discovered["refine_input"]
        )

        return {
            "target_date": target_date,

            # 원본 S3 observation도 디버깅용으로 유지.
            "raw_observations": (
                raw_observations
            ),

            # 이후 candidate evidence에 사용되는 것은
            # compound 해체 후 observation.
            "observations": observations,

            "compound": compound,

            "aggregated": (
                discovered["aggregated"]
            ),
            "known_removed": (
                discovered["known_removed"]
            ),
            "excluded": (
                discovered["excluded"]
            ),
            "fragment_dropped": (
                discovered[
                    "fragment_dropped"
                ]
            ),
            "fragment_held": (
                discovered[
                    "fragment_held"
                ]
            ),
            "held": discovered["held"],
            "refine_input": (
                discovered["refine_input"]
            ),
            "refined_keep": (
                refined["keep"]
            ),
            "refined_drop": (
                refined["drop"]
            ),
        }

    # ========================================================
    # RUN - FINAL DAILY BATCH
    # ========================================================

    def run_daily(
        self,
        target_date: date,
    ) -> dict:
        """
        실제 Daily Candidate Batch.

        S3 observations
        -> discovery/refine
        -> KEEP only
        -> TermCandidate DB
        -> candidate S3 evidence

        같은 날짜 재실행 가능.
        """

        result = self.run_to_refine(
            target_date
        )

        promoted = self.promote_keep(
            target_date=target_date,
            observations=(
                result["observations"]
            ),
            rows=(
                result["refined_keep"]
            ),
        )

        return {
            **result,
            "promoted": promoted,
        }
