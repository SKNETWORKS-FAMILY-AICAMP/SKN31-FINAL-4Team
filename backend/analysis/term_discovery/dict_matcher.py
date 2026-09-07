from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class MatchedTerm:
    term: str
    canonical_term: str
    term_type: str | None
    start: int
    end: int


class DictionaryMatcher:
    """
    FEEDIT 기존 term_dict / term_alias 기반 known term matcher.

    MVP에서는 dict 형태로 받아 사용.
    추후 Django ORM / PostgreSQL 로딩으로 교체.
    """

    def __init__(
        self,
        terms: Iterable[dict],
    ):
        self.term_map: dict[str, dict] = {}

        for item in terms:
            canonical = self._normalize(item["term"])

            self.term_map[canonical] = {
                "canonical_term": item["term"],
                "term_type": item.get("term_type"),
            }

            for alias in item.get("aliases", []):
                normalized_alias = self._normalize(alias)

                self.term_map[normalized_alias] = {
                    "canonical_term": item["term"],
                    "term_type": item.get("term_type"),
                }

        # 긴 표현부터 검색
        self.sorted_terms = sorted(
            self.term_map.keys(),
            key=len,
            reverse=True,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(
            text.lower()
            .strip()
            .replace("_", " ")
            .replace("-", " ")
            .split()
        )

    def find_matches(
        self,
        text: str,
    ) -> list[MatchedTerm]:

        normalized_text = self._normalize(text)

        matches: list[MatchedTerm] = []
        occupied: list[tuple[int, int]] = []

        for term in self.sorted_terms:

            start = 0

            while True:
                idx = normalized_text.find(term, start)

                if idx == -1:
                    break

                end = idx + len(term)

                overlap = any(
                    not (
                        end <= occupied_start
                        or idx >= occupied_end
                    )
                    for occupied_start, occupied_end in occupied
                )

                if not overlap:
                    meta = self.term_map[term]

                    matches.append(
                        MatchedTerm(
                            term=term,
                            canonical_term=meta[
                                "canonical_term"
                            ],
                            term_type=meta["term_type"],
                            start=idx,
                            end=end,
                        )
                    )

                    occupied.append(
                        (idx, end)
                    )

                start = end

        return sorted(
            matches,
            key=lambda x: x.start,
        )

    def remove_known_terms(
        self,
        text: str,
    ) -> tuple[str, list[MatchedTerm]]:

        normalized_text = self._normalize(text)

        matches = self.find_matches(
            normalized_text
        )

        chars = list(normalized_text)

        for match in matches:
            for i in range(
                match.start,
                match.end,
            ):
                chars[i] = " "

        residual_text = "".join(chars)

        residual_text = " ".join(
            residual_text.split()
        )

        return residual_text, matches