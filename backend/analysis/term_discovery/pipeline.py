from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from .candidate_normalizer import CandidateNormalizer
from .dict_matcher import DictionaryMatcher
from .filters import CandidateFilter
from .phrase_extractor import PhraseExtractor
from .repository import TermCandidateRepository

@dataclass
class CandidateObservation:
    source_type: str
    raw_text: str
    residual_text: str


@dataclass
class CandidateResult:
    term: str

    mention_count: int = 0

    observations: list[
        CandidateObservation
    ] = field(
        default_factory=list
    )


class TermDiscoveryPipeline:

    def __init__(
        self,
        dictionary_terms: list[dict],
    ):
        self.matcher = (
            DictionaryMatcher(
                dictionary_terms
            )
        )
        self.repository = TermCandidateRepository()
        self.extractor = (
            PhraseExtractor()
        )

        self.filter = (
            CandidateFilter()
        )

        self.normalizer = (
            CandidateNormalizer()
        )

    def process_text(
        self,
        text: str,
        source_type: str = "PRODUCT_NAME",
    ) -> dict:

        # -----------------------------
        # 1. 기존 사전 매칭
        # -----------------------------

        residual_text, known_terms = (
            self.matcher
            .remove_known_terms(
                text
            )
        )

        # -----------------------------
        # 2. 잔차 phrase 추출
        # -----------------------------

        raw_candidates = (
            self.extractor.extract(
                residual_text
            )
        )

        # -----------------------------
        # 3. normalize + filter
        # -----------------------------

        candidates: list[str] = []

        for candidate in raw_candidates:

            normalized = (
                self.normalizer
                .normalize(
                    candidate
                )
            )

            if not (
                self.filter
                .is_valid(
                    normalized
                )
            ):
                continue

            candidates.append(
                normalized
            )

        return {
            "raw_text": text,
            "known_terms": [
                {
                    "term": match.term,
                    "canonical_term": (
                        match.canonical_term
                    ),
                    "type": (
                        match.term_type
                    ),
                }
                for match
                in known_terms
            ],
            "residual_text": (
                residual_text
            ),
            "candidates": list(
                dict.fromkeys(
                    candidates
                )
            ),
            "source_type": (
                source_type
            ),
        }

    def process_batch(
        self,
        texts: list[str],
        source_type: str = "PRODUCT_NAME",
        min_count: int = 2,
    ) -> list[CandidateResult]:

        candidate_map: dict[
            str,
            CandidateResult,
        ] = {}

        for text in texts:

            result = (
                self.process_text(
                    text=text,
                    source_type=(
                        source_type
                    ),
                )
            )

            for candidate in (
                result["candidates"]
            ):

                if (
                    candidate
                    not in candidate_map
                ):
                    candidate_map[
                        candidate
                    ] = (
                        CandidateResult(
                            term=candidate
                        )
                    )

                item = candidate_map[
                    candidate
                ]

                item.mention_count += 1

                # 동일 상품 내 중복은
                # process_text에서 제거됨
                if (
                    len(
                        item.observations
                    )
                    < 5
                ):
                    item.observations.append(
                        CandidateObservation(
                            source_type=(
                                source_type
                            ),
                            raw_text=text,
                            residual_text=(
                                result[
                                    "residual_text"
                                ]
                            ),
                        )
                    )

        results = [
            item
            for item
            in candidate_map.values()
            if (
                item.mention_count
                >= min_count
            )
        ]

        results.sort(
            key=lambda x: (
                x.mention_count
            ),
            reverse=True,
        )

        return results
    
    def process_and_save(
        self,
        *,
        text: str,
        source=None,
        source_type: str = "PRODUCT_NAME",
        source_entity_id: str | None = None,
    ):
        result = self.process_text(
            text=text,
            source_type=source_type,
        )

        saved_candidates = []

        for term in result["candidates"]:

            candidate = (
                self.repository.save_candidate(
                    raw_term=term,
                    raw_text=text,
                    source=source,
                    source_type=source_type,
                    source_entity_id=source_entity_id,
                )
            )

            saved_candidates.append(
                candidate
            )

        result["saved_candidates"] = (
            saved_candidates
        )

        return result