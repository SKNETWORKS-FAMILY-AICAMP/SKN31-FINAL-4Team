from __future__ import annotations

import json
from datetime import date, datetime, timezone

import boto3
from django.conf import settings

from .candidate import (
    CandidateBuilder,
)


class TermObservationStore:
    """
    Term Discovery S3 저장소.

    담당:
    1. ProductSource UNKNOWN -> S3 Observation 저장
    2. 특정 날짜 Observation 로드
    3. Candidate별 Evidence 저장
    """

    OBSERVATION_PREFIX = (
        "term-discovery/observations"
    )

    CANDIDATE_PREFIX = (
        "term-discovery/candidates"
    )

    def __init__(
        self,
        *,
        bucket: str | None = None,
        s3_client=None,
    ):
        self.bucket = (
            bucket
            or getattr(
                settings,
                "AWS_STORAGE_BUCKET_NAME",
                None,
            )
            or getattr(
                settings,
                "AWS_S3_BUCKET_NAME",
                None,
            )
        )

        if not self.bucket:
            raise ValueError(
                "S3 bucket 설정을 찾을 수 없습니다. "
                "AWS_STORAGE_BUCKET_NAME 또는 "
                "AWS_S3_BUCKET_NAME을 확인하세요."
            )

        self.s3 = (
            s3_client
            or boto3.client("s3")
        )

    # ========================================================
    # PRODUCT SOURCE -> S3
    # ========================================================

    def write_product_sources(
        self,
        product_sources,
    ) -> dict:
        """
        ProductSource
        -> feedit_analysis.unknown_evidence
        -> CandidateBuilder
        -> PreparedObservation
        -> S3 JSONL

        DB Candidate 생성 없음.
        """

        builder = CandidateBuilder()

        result = (
            builder.prepare_product_observations(
                product_sources
            )
        )

        prepared = result["prepared"]

        if not prepared:
            return {
                "uris": [],
                "evidence_count": result[
                    "evidence_count"
                ],
                "prepared_count": 0,
                "dropped_count": result[
                    "dropped_count"
                ],
            }

        rows = [
            item.to_dict()
            for item in prepared
        ]

        # Source별 파일 분리
        grouped: dict[
            str,
            list[dict],
        ] = {}

        for row in rows:
            source = (
                row.get("source")
                or "UNKNOWN"
            ).upper()

            grouped.setdefault(
                source,
                [],
            ).append(row)

        uris = []

        for source, source_rows in (
            grouped.items()
        ):
            uri = (
                self.write_observation_rows(
                    rows=source_rows,
                    source=source,
                )
            )

            if uri:
                uris.append(uri)

        return {
            "uris": uris,
            "evidence_count": result[
                "evidence_count"
            ],
            "prepared_count": result[
                "prepared_count"
            ],
            "dropped_count": result[
                "dropped_count"
            ],
        }

    # ========================================================
    # WRITE OBSERVATIONS
    # ========================================================

    def write_observation_rows(
        self,
        *,
        rows: list[dict],
        source: str,
        target_date: date | None = None,
    ) -> str | None:

        if not rows:
            return None

        now = datetime.now(
            timezone.utc
        )

        target_date = (
            target_date
            or now.date()
        )

        timestamp = now.strftime(
            "%Y%m%dT%H%M%S%f"
        )

        key = (
            f"{self.OBSERVATION_PREFIX}/"
            f"date={target_date.isoformat()}/"
            f"source={source.lower()}/"
            f"observations-{timestamp}.jsonl"
        )

        self._put_jsonl(
            key=key,
            rows=rows,
        )

        return self._uri(key)

    # ========================================================
    # LOAD DAILY OBSERVATIONS
    # ========================================================

    def load_observations(
        self,
        target_date: date,
    ) -> list[dict]:
        """
        특정 날짜의 모든 source observation 로드.
        """

        prefix = (
            f"{self.OBSERVATION_PREFIX}/"
            f"date={target_date.isoformat()}/"
        )

        rows: list[dict] = []

        paginator = (
            self.s3.get_paginator(
                "list_objects_v2"
            )
        )

        for page in paginator.paginate(
            Bucket=self.bucket,
            Prefix=prefix,
        ):
            for obj in page.get(
                "Contents",
                [],
            ):
                key = obj["Key"]

                if not key.endswith(
                    ".jsonl"
                ):
                    continue

                rows.extend(
                    self._read_jsonl(
                        key
                    )
                )

        return rows

    # ========================================================
    # CANDIDATE EVIDENCE
    # ========================================================

    def write_candidate_evidence(
        self,
        *,
        candidate_id: int,
        normalized_term: str,
        observations: list[dict],
        target_date: date,
        summary: dict,
    ) -> str:
        """
        Candidate 승격 후 해당 용어 관측치만
        candidate별 Evidence 경로에 저장.
        """

        evidence_rows = [
            row
            for row in observations
            if (
                row.get(
                    "normalized_term"
                )
                == normalized_term
            )
        ]

        base_key = (
            f"{self.CANDIDATE_PREFIX}/"
            f"candidate_id={candidate_id}"
        )

        evidence_key = (
            f"{base_key}/"
            f"evidence/"
            f"date={target_date.isoformat()}/"
            f"evidence.jsonl"
        )

        summary_key = (
            f"{base_key}/summary.json"
        )

        self._put_jsonl(
            key=evidence_key,
            rows=evidence_rows,
        )

        self._put_json(
            key=summary_key,
            data=summary,
        )

        return self._uri(
            base_key + "/"
        )

    # ========================================================
    # INTERNAL
    # ========================================================

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

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body.encode(
                "utf-8"
            ),
            ContentType=(
                "application/x-ndjson"
            ),
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

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body.encode(
                "utf-8"
            ),
            ContentType=(
                "application/json"
            ),
        )

    def _read_jsonl(
        self,
        key: str,
    ) -> list[dict]:

        response = (
            self.s3.get_object(
                Bucket=self.bucket,
                Key=key,
            )
        )

        body = (
            response["Body"]
            .read()
            .decode("utf-8")
        )

        rows = []

        for line in body.splitlines():

            line = line.strip()

            if not line:
                continue

            rows.append(
                json.loads(line)
            )

        return rows

    def _uri(
        self,
        key: str,
    ) -> str:

        return (
            f"s3://{self.bucket}/{key}"
        )


# ============================================================
# OBSERVATION AGGREGATION
# ============================================================

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone

import boto3
from django.conf import settings


@dataclass
class AggregatedTerm:
    raw_term: str
    normalized_term: str

    detected_count: int
    document_count: int
    source_count: int

    source_breakdown: dict[str, int]
    field_breakdown: dict[str, int]

    sample_contexts: list[dict]

    first_seen_at: str | None
    last_seen_at: str | None


class TermObservationAggregator:

    BASE_PREFIX = (
        "term-discovery/batches"
    )

    SAMPLE_LIMIT = 5

    def __init__(
        self,
        *,
        bucket: str | None = None,
        s3_client=None,
    ):
        self.bucket = (
            bucket
            or getattr(
                settings,
                "AWS_STORAGE_BUCKET_NAME",
                None,
            )
            or getattr(
                settings,
                "AWS_S3_BUCKET_NAME",
                None,
            )
        )

        if not self.bucket:
            raise ValueError(
                "S3 bucket 설정을 찾을 수 없습니다."
            )

        self.s3 = (
            s3_client
            or boto3.client("s3")
        )

    # ========================================================
    # AGGREGATE
    # ========================================================

    def aggregate(
        self,
        observations: list[dict],
    ) -> list[AggregatedTerm]:

        groups: dict[
            str,
            list[dict],
        ] = defaultdict(list)

        for observation in observations:

            normalized = (
                observation.get(
                    "normalized_term"
                )
                or ""
            ).strip()

            if not normalized:
                continue

            groups[normalized].append(
                observation
            )

        results: list[
            AggregatedTerm
        ] = []

        for normalized_term, rows in (
            groups.items()
        ):

            sources = [
                row.get("source")
                for row in rows
                if row.get("source")
            ]

            source_types = [
                row.get("source_type")
                for row in rows
                if row.get(
                    "source_type"
                )
            ]

            document_keys = set()

            for row in rows:

                source = (
                    row.get("source")
                    or ""
                )

                source_type = (
                    row.get(
                        "source_type"
                    )
                    or ""
                )

                entity_id = (
                    row.get(
                        "source_entity_id"
                    )
                    or ""
                )

                if entity_id:
                    document_keys.add(
                        (
                            source,
                            source_type,
                            entity_id,
                        )
                    )

            detected_times = []

            for row in rows:

                detected_at = (
                    row.get(
                        "detected_at"
                    )
                )

                if detected_at:
                    detected_times.append(
                        detected_at
                    )

            detected_times.sort()

            sample_contexts = []

            seen_contexts = set()

            for row in rows:

                raw_text = (
                    row.get(
                        "raw_text"
                    )
                    or ""
                ).strip()

                if not raw_text:
                    continue

                if raw_text in seen_contexts:
                    continue

                seen_contexts.add(
                    raw_text
                )

                sample_contexts.append(
                    {
                        "source": (
                            row.get(
                                "source"
                            )
                        ),
                        "source_type": (
                            row.get(
                                "source_type"
                            )
                        ),
                        "source_entity_id": (
                            row.get(
                                "source_entity_id"
                            )
                        ),
                        "text": raw_text,
                    }
                )

                if (
                    len(sample_contexts)
                    >= self.SAMPLE_LIMIT
                ):
                    break

            raw_term = (
                rows[0].get("term")
                or normalized_term
            )

            results.append(
                AggregatedTerm(
                    raw_term=raw_term,
                    normalized_term=(
                        normalized_term
                    ),
                    detected_count=(
                        len(rows)
                    ),
                    document_count=(
                        len(document_keys)
                    ),
                    source_count=(
                        len(set(sources))
                    ),
                    source_breakdown=dict(
                        Counter(sources)
                    ),
                    field_breakdown=dict(
                        Counter(
                            source_types
                        )
                    ),
                    sample_contexts=(
                        sample_contexts
                    ),
                    first_seen_at=(
                        detected_times[0]
                        if detected_times
                        else None
                    ),
                    last_seen_at=(
                        detected_times[-1]
                        if detected_times
                        else None
                    ),
                )
            )

        results.sort(
            key=lambda item: (
                -item.detected_count,
                item.normalized_term,
            )
        )

        return results

    # ========================================================
    # S3 WRITE
    # ========================================================

    def write_result(
        self,
        *,
        target_date: date,
        rows: list[
            AggregatedTerm
        ],
    ) -> str:

        key = (
            f"{self.BASE_PREFIX}/"
            f"date={target_date.isoformat()}/"
            f"aggregated.jsonl"
        )

        body = "\n".join(
            json.dumps(
                asdict(row),
                ensure_ascii=False,
            )
            for row in rows
        )

        if body:
            body += "\n"

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body.encode(
                "utf-8"
            ),
            ContentType=(
                "application/x-ndjson"
            ),
        )

        return (
            f"s3://{self.bucket}/{key}"
        )


# ============================================================
# DISCOVERY DECISION
# ============================================================

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from apps.core.models import (
    DictionaryTerm,
    DiscoveryExclusion,
    TermAlias,
)


@dataclass
class AggregatedCandidate:
    raw_term: str
    normalized_term: str
    detected_count: int
    document_count: int
    source_count: int
    source_breakdown: dict[str, int]
    field_breakdown: dict[str, int]
    sample_contexts: list[dict]
    first_seen_at: str | None
    last_seen_at: str | None
    standalone_count: int
    standalone_ratio: float


@dataclass
class DiscoveryDecision:
    candidate: AggregatedCandidate
    decision: str
    reason: str


class TermDiscovery:
    """
    S3 Observation을 하루 단위로 읽은 뒤
    Candidate Refine 단계로 넘길 후보군을 만든다.

    순서:
    aggregate
    -> Dictionary/Alias 제거
    -> DiscoveryExclusion 제거
    -> Fragment Quality Gate
    -> Frequency/Document Gate
    """

    SAMPLE_LIMIT = 5

    MIN_DETECTED_COUNT = 3
    MIN_DOCUMENT_COUNT = 2

    FRAGMENT_HOLD_STANDALONE_RATIO = 0.30

    SHORT_LATIN_MAX_LENGTH = 2

    def __init__(self):
        self.global_exclusions: dict[str, str] = {}
        self.source_exclusions: dict[tuple[str, str], str] = {}
        self._load_exclusions()

    @staticmethod
    def _is_standalone(
        term: str,
        raw_text: str,
    ) -> bool:
        term = (term or "").strip()
        raw_text = (raw_text or "").strip()

        if not term or not raw_text:
            return False

        pattern = (
            r"(?<![0-9A-Za-z가-힣])"
            + re.escape(term)
            + r"(?![0-9A-Za-z가-힣])"
        )

        return bool(
            re.search(
                pattern,
                raw_text,
                flags=re.IGNORECASE,
            )
        )

    def aggregate(
        self,
        observations: list[dict],
    ) -> list[AggregatedCandidate]:

        grouped: dict[str, list[dict]] = defaultdict(list)

        for row in observations:
            normalized = str(
                row.get("normalized_term")
                or ""
            ).strip()

            if not normalized:
                continue

            grouped[normalized].append(row)

        results: list[AggregatedCandidate] = []

        for normalized_term, rows in grouped.items():
            source_counter = Counter()
            field_counter = Counter()
            document_keys = set()

            sample_contexts: list[dict] = []
            seen_contexts = set()

            detected_times: list[str] = []
            standalone_count = 0

            for row in rows:
                source = str(
                    row.get("source")
                    or "UNKNOWN"
                ).upper()

                source_type = str(
                    row.get("source_type")
                    or "OTHER"
                ).upper()

                source_entity_id = row.get(
                    "source_entity_id"
                )

                source_counter[source] += 1
                field_counter[source_type] += 1

                if source_entity_id not in (None, ""):
                    document_keys.add(
                        (
                            source,
                            source_type,
                            str(source_entity_id),
                        )
                    )

                detected_at = row.get(
                    "detected_at"
                )

                if detected_at:
                    detected_times.append(
                        str(detected_at)
                    )

                raw_text = str(
                    row.get("raw_text")
                    or ""
                ).strip()

                if self._is_standalone(
                    normalized_term,
                    raw_text,
                ):
                    standalone_count += 1

                if (
                    raw_text
                    and raw_text not in seen_contexts
                    and len(sample_contexts) < self.SAMPLE_LIMIT
                ):
                    seen_contexts.add(raw_text)

                    sample_contexts.append(
                        {
                            "source": source,
                            "source_type": source_type,
                            "source_entity_id": (
                                str(source_entity_id)
                                if source_entity_id is not None
                                else None
                            ),
                            "source_field": row.get(
                                "source_field"
                            ),
                            "text": raw_text,
                        }
                    )

            detected_times.sort()

            detected_count = len(rows)

            standalone_ratio = (
                standalone_count / detected_count
                if detected_count
                else 0.0
            )

            raw_term = str(
                rows[0].get("term")
                or normalized_term
            ).strip()

            results.append(
                AggregatedCandidate(
                    raw_term=raw_term,
                    normalized_term=normalized_term,
                    detected_count=detected_count,
                    document_count=len(document_keys),
                    source_count=len(source_counter),
                    source_breakdown=dict(source_counter),
                    field_breakdown=dict(field_counter),
                    sample_contexts=sample_contexts,
                    first_seen_at=(
                        detected_times[0]
                        if detected_times
                        else None
                    ),
                    last_seen_at=(
                        detected_times[-1]
                        if detected_times
                        else None
                    ),
                    standalone_count=standalone_count,
                    standalone_ratio=round(
                        standalone_ratio,
                        4,
                    ),
                )
            )

        results.sort(
            key=lambda row: (
                -row.document_count,
                -row.detected_count,
                row.normalized_term,
            )
        )

        return results

    def remove_known(
        self,
        rows: list[AggregatedCandidate],
    ) -> tuple[
        list[AggregatedCandidate],
        list[DiscoveryDecision],
    ]:

        if not rows:
            return [], []

        normalized_terms = {
            row.normalized_term
            for row in rows
            if row.normalized_term
        }

        known_terms = set(
            DictionaryTerm.objects.filter(
                normalized_name__in=normalized_terms,
                status=DictionaryTerm.Status.ACTIVE,
            ).values_list(
                "normalized_name",
                flat=True,
            )
        )

        known_aliases = set(
            TermAlias.objects.filter(
                normalized_alias__in=normalized_terms,
            ).values_list(
                "normalized_alias",
                flat=True,
            )
        )

        remaining: list[AggregatedCandidate] = []
        removed: list[DiscoveryDecision] = []

        for row in rows:
            if row.normalized_term in known_terms:
                removed.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="DROP",
                        reason="KNOWN_DICTIONARY_TERM",
                    )
                )
                continue

            if row.normalized_term in known_aliases:
                removed.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="DROP",
                        reason="KNOWN_ALIAS",
                    )
                )
                continue

            remaining.append(row)

        return remaining, removed

    def _load_exclusions(
        self,
    ) -> None:

        self.global_exclusions.clear()
        self.source_exclusions.clear()

        rows = (
            DiscoveryExclusion.objects
            .filter(is_active=True)
            .select_related("source")
        )

        for row in rows:
            normalized = str(
                row.normalized_term
                or ""
            ).strip()

            if not normalized:
                continue

            if row.source_id is None:
                self.global_exclusions[
                    normalized
                ] = row.reason
                continue

            source_code = str(
                row.source.code
                or ""
            ).upper()

            if not source_code:
                continue

            self.source_exclusions[
                (
                    source_code,
                    normalized,
                )
            ] = row.reason

    def reload_exclusions(
        self,
    ) -> None:
        self._load_exclusions()

    def get_exclusion_reason(
        self,
        row: AggregatedCandidate,
    ) -> str | None:

        term = (
            row.normalized_term
            or ""
        ).strip()

        if not term:
            return "EMPTY"

        reason = self.global_exclusions.get(
            term
        )

        if reason:
            return reason

        for source in row.source_breakdown.keys():
            reason = (
                self.source_exclusions
                .get(
                    (
                        str(source).upper(),
                        term,
                    )
                )
            )

            if reason:
                return reason

        lower_term = term.lower()

        if re.fullmatch(
            r"(?:20)?\d{2}(?:ss|fw)",
            lower_term,
            flags=re.IGNORECASE,
        ):
            return "SEASON"

        if re.fullmatch(
            r"\d+\s*(?:pack|pcs?|colors?)",
            lower_term,
            flags=re.IGNORECASE,
        ):
            return "PRODUCT_META"

        if re.fullmatch(
            r"\d+",
            lower_term,
        ):
            return "PRODUCT_META"

        if re.fullmatch(
            r"[\d\s.,%+\-_/&|]+",
            lower_term,
        ):
            return "PRODUCT_META"

        return None

    def remove_exclusions(
        self,
        rows: list[AggregatedCandidate],
    ) -> tuple[
        list[AggregatedCandidate],
        list[DiscoveryDecision],
    ]:

        remaining: list[AggregatedCandidate] = []
        removed: list[DiscoveryDecision] = []

        for row in rows:
            reason = self.get_exclusion_reason(
                row
            )

            if reason:
                removed.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="DROP",
                        reason=f"EXCLUSION_{reason}",
                    )
                )
                continue

            remaining.append(row)

        return remaining, removed

    def apply_fragment_gate(
        self,
        rows: list[AggregatedCandidate],
    ) -> tuple[
        list[AggregatedCandidate],
        list[DiscoveryDecision],
    ]:
        """
        파편 후보를 DROP/HOLD한다.

        1~2자 영문 UNKNOWN:
            HOLD

        다른 더 긴 후보 내부에 포함되고
        standalone_ratio < 0.10:
            DROP

        다른 더 긴 후보 내부에 포함되고
        standalone_ratio < 0.30:
            HOLD

        나머지:
            통과
        """

        if not rows:
            return [], []

        all_terms = {
            row.normalized_term
            for row in rows
            if row.normalized_term
        }

        remaining: list[AggregatedCandidate] = []
        decisions: list[DiscoveryDecision] = []

        for row in rows:
            term = (
                row.normalized_term
                or ""
            ).strip()

            if not term:
                decisions.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="DROP",
                        reason="FRAGMENT_EMPTY",
                    )
                )
                continue

            if re.fullmatch(
                rf"[A-Za-z]{{1,{self.SHORT_LATIN_MAX_LENGTH}}}",
                term,
            ):
                decisions.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="HOLD",
                        reason="SHORT_LATIN_UNKNOWN",
                    )
                )
                continue

            # -----------------------------------------------
            # 2. ZERO STANDALONE
            #
            # 화이트라 / x멋처럼 반복 관측되지만
            # 독립 경계로 한 번도 등장하지 않은 표현은
            # 즉시 KEEP하지 않고 HOLD한다.
            # -----------------------------------------------

            if (
                row.standalone_ratio == 0
                and row.detected_count >= self.MIN_DETECTED_COUNT
            ):
                decisions.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="HOLD",
                        reason="ZERO_STANDALONE_REPEATED",
                    )
                )
                continue

            # -----------------------------------------------
            # 3. CONTAINER TERMS
            #
            # 한국어 복합어는 정상 패션 용어도 긴 표현 내부에
            # 포함되는 경우가 많으므로 포함 관계만으로 DROP하지 않는다.
            #
            # 경량 -> 경량패딩
            # 컬러 -> 컬러블록
            # 하드쉘 -> 하드쉘재킷
            # -----------------------------------------------

            container_terms = [
                other
                for other in all_terms
                if (
                    other != term
                    and len(other) > len(term)
                    and term in other
                )
            ]

            if (
                container_terms
                and row.standalone_ratio
                < self.FRAGMENT_HOLD_STANDALONE_RATIO
            ):
                decisions.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="HOLD",
                        reason="POSSIBLE_FRAGMENT_IN_LONGER_TERM",
                    )
                )
                continue

            remaining.append(row)

        return remaining, decisions

    def apply_gate(
        self,
        rows: list[AggregatedCandidate],
    ) -> tuple[
        list[AggregatedCandidate],
        list[DiscoveryDecision],
    ]:

        refine_input: list[AggregatedCandidate] = []
        held: list[DiscoveryDecision] = []

        for row in rows:
            if (
                row.detected_count
                < self.MIN_DETECTED_COUNT
            ):
                held.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="HOLD",
                        reason="LOW_FREQUENCY",
                    )
                )
                continue

            if (
                row.document_count
                < self.MIN_DOCUMENT_COUNT
            ):
                held.append(
                    DiscoveryDecision(
                        candidate=row,
                        decision="HOLD",
                        reason="LOW_DOCUMENT_DIVERSITY",
                    )
                )
                continue

            refine_input.append(row)

        return refine_input, held

    def discover(
        self,
        observations: list[dict],
    ) -> dict:

        aggregated = self.aggregate(
            observations
        )

        unknown, known_removed = (
            self.remove_known(
                aggregated
            )
        )

        cleaned, excluded = (
            self.remove_exclusions(
                unknown
            )
        )

        fragment_cleaned, fragment_decisions = (
            self.apply_fragment_gate(
                cleaned
            )
        )

        refine_input, held = (
            self.apply_gate(
                fragment_cleaned
            )
        )

        fragment_dropped = [
            item
            for item in fragment_decisions
            if item.decision == "DROP"
        ]

        fragment_held = [
            item
            for item in fragment_decisions
            if item.decision == "HOLD"
        ]

        return {
            "aggregated": aggregated,
            "known_removed": known_removed,
            "excluded": excluded,
            "fragment_dropped": fragment_dropped,
            "fragment_held": fragment_held,
            "held": held,
            "refine_input": refine_input,
        }


# ============================================================
# CANDIDATE EVIDENCE
# ============================================================

# backend/analysis/term_discovery/candidate_evidence.py

from collections import Counter
from dataclasses import dataclass
from typing import Any

from apps.core.models import (
    TermCandidate,
    TermCandidateObservation,
)

from .candidate import CandidateNormalizer
from .repository import DictionaryRepository
from dataclasses import dataclass as _config_dataclass

@_config_dataclass
class TermDiscoveryConfig:
    min_detected_count: int = 3
    min_entity_count: int = 2
    min_source_count: int = 2
    min_context_diversity: int = 2





@dataclass
class MatchedTerm:
    term_id: int | None
    matched_text: str
    canonical_term: str
    normalized_term: str
    term_type: str | None
    match_type: str
    start: int
    end: int


class DictionaryMatcher:
    """
    FEEDIT Dictionary Matcher.

    DictionaryTerm canonical + TermAlias를
    longest-first 방식으로 매칭한다.
    """

    def __init__(
        self,
        terms: Iterable[dict],
    ):
        self.normalizer = CandidateNormalizer()

        self.term_map: dict[str, dict] = {}

        # ====================================================
        # DICTIONARY BUILD
        # ====================================================

        for item in terms:

            canonical = item["term"]

            normalized_canonical = (
                item.get("normalized_name")
                or self.normalizer.normalize(
                    canonical
                )
            )

            if normalized_canonical:

                self.term_map[
                    normalized_canonical
                ] = {
                    "term_id": item.get("id"),
                    "canonical_term": canonical,
                    "normalized_term": (
                        normalized_canonical
                    ),
                    "term_type": (
                        item.get("term_type")
                    ),
                    "match_type": "CANONICAL",
                }

            # -----------------------------------------------
            # ALIASES
            # -----------------------------------------------

            for alias_item in (
                item.get(
                    "aliases",
                    [],
                )
            ):

                if isinstance(
                    alias_item,
                    dict,
                ):

                    alias = (
                        alias_item.get(
                            "alias"
                        )
                    )

                    normalized_alias = (
                        alias_item.get(
                            "normalized_alias"
                        )
                        or
                        self.normalizer
                        .normalize(
                            alias
                        )
                    )

                else:

                    alias = alias_item

                    normalized_alias = (
                        self.normalizer
                        .normalize(
                            alias
                        )
                    )

                if not normalized_alias:
                    continue

                # canonical 우선
                if (
                    normalized_alias
                    in self.term_map
                ):
                    continue

                self.term_map[
                    normalized_alias
                ] = {
                    "term_id": item.get("id"),
                    "canonical_term": canonical,
                    "normalized_term": (
                        normalized_canonical
                    ),
                    "term_type": (
                        item.get("term_type")
                    ),
                    "match_type": "ALIAS",
                }

        # 긴 표현 먼저 검색
        self.sorted_terms = sorted(
            self.term_map.keys(),
            key=len,
            reverse=True,
        )

    # ========================================================
    # NORMALIZE
    # ========================================================

    def normalize(
        self,
        text: str,
    ) -> str:

        return (
            self.normalizer
            .normalize(
                text
            )
        )

    # ========================================================
    # FIND MATCHES
    # ========================================================

    def find_matches(
        self,
        text: str,
    ) -> list[MatchedTerm]:

        normalized_text = (
            self.normalize(
                text
            )
        )

        matches: list[
            MatchedTerm
        ] = []

        occupied: list[
            tuple[int, int]
        ] = []

        for dictionary_text in (
            self.sorted_terms
        ):

            start = 0

            while True:

                idx = (
                    normalized_text
                    .find(
                        dictionary_text,
                        start,
                    )
                )

                if idx == -1:
                    break

                end = (
                    idx
                    + len(
                        dictionary_text
                    )
                )

                overlap = any(
                    not (
                        end <= occupied_start
                        or
                        idx >= occupied_end
                    )
                    for (
                        occupied_start,
                        occupied_end,
                    )
                    in occupied
                )

                if not overlap:

                    meta = (
                        self.term_map[
                            dictionary_text
                        ]
                    )

                    matches.append(
                        MatchedTerm(
                            term_id=(
                                meta["term_id"]
                            ),
                            matched_text=(
                                dictionary_text
                            ),
                            canonical_term=(
                                meta[
                                    "canonical_term"
                                ]
                            ),
                            normalized_term=(
                                meta[
                                    "normalized_term"
                                ]
                            ),
                            term_type=(
                                meta[
                                    "term_type"
                                ]
                            ),
                            match_type=(
                                meta[
                                    "match_type"
                                ]
                            ),
                            start=idx,
                            end=end,
                        )
                    )

                    occupied.append(
                        (
                            idx,
                            end,
                        )
                    )

                start = max(
                    end,
                    start + 1,
                )

        return sorted(
            matches,
            key=lambda x: x.start,
        )

    # ========================================================
    # REMOVE KNOWN TERMS
    # ========================================================

    def remove_known_terms(
        self,
        text: str,
    ) -> tuple[
        str,
        list[MatchedTerm],
    ]:

        normalized_text = (
            self.normalize(
                text
            )
        )

        matches = (
            self.find_matches(
                normalized_text
            )
        )

        chars = list(
            normalized_text
        )

        for match in matches:

            for i in range(
                match.start,
                match.end,
            ):
                chars[i] = " "

        residual_text = (
            " ".join(
                "".join(chars)
                .split()
            )
        )

        return (
            residual_text,
            matches,
        )

# ============================================================
# EVIDENCE DTO
# ============================================================

@dataclass
class CandidateEvidence:
    candidate_id: int
    term: str
    normalized_term: str

    detected_count: int
    source_count: int
    observation_count: int
    entity_count: int
    context_diversity: int

    source_distribution: dict[str, int]
    source_type_distribution: dict[str, int]
    source_field_distribution: dict[str, int]

    left_neighbors: dict[str, int]
    right_neighbors: dict[str, int]

    known_term_cooccurrence: list[dict[str, Any]]

    observations: list[dict[str, Any]]

    eligible: bool
    eligibility_reason: str

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "term": self.term,
            "normalized_term": self.normalized_term,

            "detected_count": self.detected_count,
            "source_count": self.source_count,
            "observation_count": self.observation_count,
            "entity_count": self.entity_count,
            "context_diversity": self.context_diversity,

            "source_distribution": self.source_distribution,
            "source_type_distribution": self.source_type_distribution,
            "source_field_distribution": self.source_field_distribution,

            "left_neighbors": self.left_neighbors,
            "right_neighbors": self.right_neighbors,

            "known_term_cooccurrence": self.known_term_cooccurrence,

            "observations": self.observations,

            "eligible": self.eligible,
            "eligibility_reason": self.eligibility_reason,
        }


# ============================================================
# BUILDER
# ============================================================

class CandidateEvidenceBuilder:
    """
    Candidate에 대한 '관측 사실'만 만든다.

    절대 하지 않는 것:
    ----------------------------------------------------------
    - term type 추론
    - MATERIAL 가능성 높음 같은 해석
    - ALIAS / NEW_TERM 판단
    - semantic meaning 추론
    - LLM 호출

    여기서는 오직:
    ----------------------------------------------------------
    - 몇 번 등장했는가
    - 어디서 등장했는가
    - 어떤 문맥에 등장했는가
    - 좌우에 어떤 단어가 있었는가
    - 기존 DictionaryTerm 중 무엇과 같이 등장했는가

    만 계산한다.
    """


    NEIGHBOR_WINDOW = 1

    def __init__(self, config: TermDiscoveryConfig | None = None):
        self.config = config or TermDiscoveryConfig()
        self.normalizer = CandidateNormalizer()

        dictionary_repository = DictionaryRepository()

        dictionary_terms = (
            dictionary_repository
            .load_active_terms()
        )

        self.dictionary_matcher = (
            DictionaryMatcher(
                dictionary_terms
            )
        )

    # ========================================================
    # PUBLIC
    # ========================================================

    def build(
        self,
        candidate: TermCandidate,
    ) -> CandidateEvidence:

        observations_qs = (
            TermCandidateObservation.objects
            .filter(
                candidate=candidate
            )
            .select_related(
                "source"
            )
            .order_by(
                "detected_at",
                "id",
            )
        )

        observations = list(
            observations_qs
        )

        entity_count = len({
            str(obs.source_entity_id)
            for obs in observations
            if obs.source_entity_id
        })

        source_distribution = (
            self._source_distribution(
                observations
            )
        )

        source_type_distribution = (
            self._source_type_distribution(
                observations
            )
        )

        source_field_distribution = (
            self._source_field_distribution(
                observations
            )
        )

        context_diversity = (
            self._context_diversity(
                observations
            )
        )

        (
            left_neighbors,
            right_neighbors,
        ) = (
            self._neighbor_counts(
                candidate=candidate,
                observations=observations,
            )
        )

        known_term_cooccurrence = (
            self._known_term_cooccurrence(
                candidate=candidate,
                observations=observations,
            )
        )

        observation_payload = (
            self._observation_payload(
                observations
            )
        )

        eligible, reason = (
            self._eligibility(
                candidate=candidate,
                source_distribution=source_distribution,
                context_diversity=context_diversity,
            )
        )

        return CandidateEvidence(
            candidate_id=candidate.id,
            term=candidate.raw_term,
            normalized_term=candidate.normalized_term,

            detected_count=candidate.detected_count,
            source_count=candidate.source_count,
            observation_count=len(observations),
            entity_count=entity_count,
            context_diversity=context_diversity,

            source_distribution=source_distribution,
            source_type_distribution=source_type_distribution,
            source_field_distribution=source_field_distribution,

            left_neighbors=left_neighbors,
            right_neighbors=right_neighbors,

            known_term_cooccurrence=known_term_cooccurrence,

            observations=observation_payload,

            eligible=eligible,
            eligibility_reason=reason,
        )

    # ========================================================
    # SOURCE DISTRIBUTION
    # ========================================================

    def _source_distribution(
        self,
        observations: list[TermCandidateObservation],
    ) -> dict[str, int]:

        counter = Counter()

        for obs in observations:

            if obs.source_id is None:
                continue

            source = obs.source

            label = (
                getattr(source, "code", None)
                or getattr(source, "name", None)
                or str(source.id)
            )

            counter[
                str(label)
            ] += 1

        return dict(
            counter.most_common()
        )

    # ========================================================
    # SOURCE TYPE
    # ========================================================

    def _source_type_distribution(
        self,
        observations: list[TermCandidateObservation],
    ) -> dict[str, int]:

        counter = Counter()

        for obs in observations:

            if not obs.source_type:
                continue

            counter[
                obs.source_type
            ] += 1

        return dict(
            counter.most_common()
        )

    # ========================================================
    # SOURCE FIELD
    # ========================================================

    def _source_field_distribution(
        self,
        observations: list[TermCandidateObservation],
    ) -> dict[str, int]:

        counter = Counter()

        for obs in observations:

            field = (
                obs.source_field
                or "UNKNOWN"
            )

            counter[
                field
            ] += 1

        return dict(
            counter.most_common()
        )

    # ========================================================
    # CONTEXT DIVERSITY
    # ========================================================

    def _context_diversity(
        self,
        observations: list[TermCandidateObservation],
    ) -> int:

        unique_contexts = set()

        for obs in observations:

            raw_text = (
                obs.raw_text
                or ""
            )

            normalized = (
                self.normalizer
                .normalize(
                    raw_text
                )
            )

            if normalized:
                unique_contexts.add(
                    normalized
                )

        return len(
            unique_contexts
        )

    # ========================================================
    # NEIGHBORS
    # ========================================================

    def _neighbor_counts(
        self,
        *,
        candidate: TermCandidate,
        observations: list[TermCandidateObservation],
    ) -> tuple[
        dict[str, int],
        dict[str, int],
    ]:

        left_counter = Counter()
        right_counter = Counter()

        target = (
            candidate.normalized_term
            or self.normalizer.normalize(
                candidate.raw_term
            )
        )

        if not target:
            return {}, {}

        target_tokens = (
            target.split()
        )

        if not target_tokens:
            return {}, {}

        for obs in observations:

            raw_text = (
                obs.raw_text
                or ""
            )

            normalized_text = (
                self.normalizer
                .normalize(
                    raw_text
                )
            )

            if not normalized_text:
                continue

            tokens = (
                normalized_text
                .split()
            )

            if not tokens:
                continue

            target_len = len(
                target_tokens
            )

            for i in range(
                len(tokens)
                - target_len
                + 1
            ):

                window = (
                    tokens[
                        i:
                        i + target_len
                    ]
                )

                if window != target_tokens:
                    continue

                # LEFT
                if i > 0:

                    left = (
                        tokens[
                            i - 1
                        ]
                    )

                    if left:
                        left_counter[
                            left
                        ] += 1

                # RIGHT
                right_index = (
                    i + target_len
                )

                if (
                    right_index
                    < len(tokens)
                ):

                    right = (
                        tokens[
                            right_index
                        ]
                    )

                    if right:
                        right_counter[
                            right
                        ] += 1

        return (
            dict(
                left_counter
                .most_common()
            ),
            dict(
                right_counter
                .most_common()
            ),
        )

    # ========================================================
    # KNOWN TERM COOCCURRENCE
    # ========================================================

    def _known_term_cooccurrence(
        self,
        *,
        candidate: TermCandidate,
        observations: list[TermCandidateObservation],
    ) -> list[dict]:

        counter = Counter()

        candidate_normalized = (
            candidate.normalized_term
        )

        term_meta = {}

        for obs in observations:

            raw_text = (
                obs.raw_text
                or ""
            )

            if not raw_text:
                continue

            matches = (
                self.dictionary_matcher
                .find_matches(
                    raw_text
                )
            )

            # 같은 observation 안에서 같은 DictionaryTerm이
            # 여러 번 등장하더라도 1회만 count
            seen_term_ids = set()

            for match in matches:

                if match.term_id is None:
                    continue

                # 후보 자기 자신과 동일한 normalized 표현이면 제외
                if (
                    match.normalized_term
                    == candidate_normalized
                ):
                    continue

                if (
                    match.term_id
                    in seen_term_ids
                ):
                    continue

                seen_term_ids.add(
                    match.term_id
                )

                counter[
                    match.term_id
                ] += 1

                term_meta[
                    match.term_id
                ] = {
                    "term_id": match.term_id,
                    "canonical_name": (
                        match.canonical_term
                    ),
                    "term_type": (
                        match.term_type
                    ),
                }

        results = []

        for (
            term_id,
            count,
        ) in counter.most_common():

            meta = (
                term_meta[
                    term_id
                ]
            )

            results.append(
                {
                    **meta,
                    "count": count,
                }
            )

        return results

    # ========================================================
    # OBSERVATION PAYLOAD
    # ========================================================

    def _observation_payload(
        self,
        observations: list[TermCandidateObservation],
    ) -> list[dict]:

        payload = []

        for obs in observations:

            source_label = None

            if obs.source_id is not None:

                source_label = (
                    getattr(
                        obs.source,
                        "code",
                        None,
                    )
                    or getattr(
                        obs.source,
                        "name",
                        None,
                    )
                    or str(
                        obs.source_id
                    )
                )

            payload.append(
                {
                    "observation_id": (
                        obs.id
                    ),

                    "source": (
                        source_label
                    ),

                    "source_type": (
                        obs.source_type
                    ),

                    "source_field": (
                        obs.source_field
                    ),

                    "source_entity_id": (
                        obs.source_entity_id
                    ),

                    "detected_phrase": (
                        obs.detected_phrase
                    ),

                    "raw_text": (
                        obs.raw_text
                    ),

                    "residual_text": (
                        obs.residual_text
                    ),

                    "detected_at": (
                        obs.detected_at.isoformat()
                        if obs.detected_at
                        else None
                    ),
                }
            )

        return payload

    # ========================================================
    # ELIGIBILITY
    # ========================================================

    def _eligibility(
        self,
        *,
        candidate: TermCandidate,
        source_distribution: dict[str, int],
        context_diversity: int,
    ) -> tuple[bool, str]:
        """
        This is a readiness gate only.
        It does NOT mean NEW_TERM / ALIAS.

        Require minimum total observations, then enough diversity from
        at least one axis: entity, source, or context.
        """

        detected_count = int(candidate.detected_count or 0)

        observations = (
            TermCandidateObservation.objects
            .filter(candidate=candidate)
        )

        entity_count = (
            observations
            .exclude(source_entity_id__isnull=True)
            .exclude(source_entity_id="")
            .values("source_entity_id")
            .distinct()
            .count()
        )

        source_count = len(source_distribution)

        if detected_count < self.config.min_detected_count:
            return (
                False,
                (
                    "detected_count 부족: "
                    f"{detected_count}/"
                    f"{self.config.min_detected_count}"
                ),
            )

        diversity_ok = (
            entity_count >= self.config.min_entity_count
            or source_count >= self.config.min_source_count
            or context_diversity >= self.config.min_context_diversity
        )

        if not diversity_ok:
            return (
                False,
                (
                    "다양성 부족: "
                    f"entity={entity_count}/"
                    f"{self.config.min_entity_count}, "
                    f"source={source_count}/"
                    f"{self.config.min_source_count}, "
                    f"context={context_diversity}/"
                    f"{self.config.min_context_diversity}"
                ),
            )

        return (
            True,
            (
                "eligible: "
                f"detected={detected_count}, "
                f"entity={entity_count}, "
                f"source={source_count}, "
                f"context={context_diversity}"
            ),
        )
