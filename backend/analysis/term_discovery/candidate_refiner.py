from __future__ import annotations


class CandidateRefiner:

    def __init__(self):
        self.generic_tokens = {
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

    def is_composite_candidate(
        self,
        term: str,
    ) -> bool:
        return len(term.split()) >= 2

    def should_keep(
        self,
        term: str,
        known_subterms: set[str] | None = None,
    ) -> bool:

        term = term.strip()

        if not term:
            return False

        tokens = term.split()

        # 단일 후보는 우선 유지
        if len(tokens) == 1:
            return True

        # 모두 일반적인 단어면 제거
        if all(
            token in self.generic_tokens
            for token in tokens
        ):
            return False

        # 조합을 구성하는 각 단어가
        # 이미 개별 후보로 존재하면
        # 단순 조합으로 보고 일단 제거
        if known_subterms:
            if all(
                token in known_subterms
                for token in tokens
            ):
                return False

        return True