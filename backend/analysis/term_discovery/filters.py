from __future__ import annotations

import re


DEFAULT_STOPWORDS = {
    "상품",
    "제품",
    "추천",
    "신상",
    "코디",
    "스타일링",
    "착용",
    "느낌",
    "포인트",
    "디자인",
    "아이템",
    "컬렉션",
    "이번",
    "요즘",
    "완전",
    "진짜",
    "예쁜",
    "이쁜",
    "멋진",
    "좋은",
    "최고",
    "인기",
    "베스트",
    "남성",
    "여성",
    "공용",
    "unisex",
    "new",
    "best",
}


class CandidateFilter:

    def __init__(
        self,
        stopwords: set[str] | None = None,
    ):
        self.stopwords = (
            stopwords
            or DEFAULT_STOPWORDS
        )

    def is_valid(
        self,
        phrase: str,
    ) -> bool:

        phrase = phrase.strip()

        if not phrase:
            return False

        if len(phrase) < 2:
            return False

        # 숫자만
        if phrase.isdigit():
            return False

        # 숫자/기호 위주
        if re.fullmatch(
            r"[\d\s./%]+",
            phrase,
        ):
            return False

        # 사이즈
        if phrase.lower() in {
            "xs",
            "s",
            "m",
            "l",
            "xl",
            "xxl",
        }:
            return False

        tokens = phrase.split()

        # stopword 단독
        if len(tokens) == 1:
            if phrase in self.stopwords:
                return False

        # 모든 token이 stopword
        if all(
            token in self.stopwords
            for token in tokens
        ):
            return False

        # 너무 긴 표현
        if len(tokens) > 4:
            return False

        return True