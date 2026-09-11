# backend/analysis/term_discovery/candidate_evidence.py

from __future__ import annotations

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

