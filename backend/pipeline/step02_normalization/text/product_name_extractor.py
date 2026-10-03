from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from kiwipiepy import Kiwi

from pipeline.step02_normalization.semantic_tokenizer.tokenizer import (
    get_feedit_tokenizer,
)


@dataclass
class ProductNameCandidate:
    """
    TextDocument 안에서 발견된 상품명 후보.
    """

    text: str
    source_text: str

    line_index: int

    confidence: float

    item_term_ids: list[int]
    item_names: list[str]

    term_count: int

    detection_reasons: list[str]


@dataclass
class ProductNameExtractionResult:
    raw_text: str

    line_count: int
    candidate_count: int

    candidates: list[ProductNameCandidate]


class ProductNameExtractor:
    """
    YouTube DESCRIPTION 등 긴 텍스트에서
    상품명처럼 보이는 문자열만 추출한다.

    DB write 없음.

    판단 기준:
    1. 상품 목록 구조 신호
    2. SemanticTokenizer의 ITEM term
    3. 상품명다운 문자열 길이
    4. URL / 가격 / 연락처 / 설명문 제거

    주의:
    특정 유튜버의 '└' 형식에만 의존하지 않는다.
    """

    PRODUCT_PREFIX_RE = re.compile(
        r"""
        ^\s*
        (?:
            [└├│▶▷►▸\-–—•·*]+
            |
            \d{1,3}
            [.)]
        )
        \s*
        """,
        re.VERBOSE,
    )

    URL_RE = re.compile(
        r"https?://\S+|www\.\S+",
        re.IGNORECASE,
    )

    EMAIL_RE = re.compile(
        r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
        re.IGNORECASE,
    )

    PRICE_RE = re.compile(
        r"""
        (?:
            ₩\s*[\d,]+
            |
            [\d,]+\s*원
            |
            [\d,.]+\s*(?:KRW|USD|EUR)
            |
            \d+\s*%
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    TIMESTAMP_RE = re.compile(
        r"^\s*\d{1,2}:\d{2}(?::\d{2})?\s*"
    )

    SECTION_RE = re.compile(
        r"""
        ^\s*
        (?:
            look\s*\d+
            |
            outfit\s*\d+
            |
            item\s*\d+
            |
            product\s*\d+
            |
            chapter\s*\d+
            |
            category\s*\d*
        )
        \s*[:._-]?\s*$
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    CONTACT_RE = re.compile(
        r"""
        (?:
            contact
            |
            business
            |
            instagram
            |
            insta
            |
            e-?mail
            |
            email
            |
            문의
            |
            협찬
            |
            광고
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    SENTENCE_END_RE = re.compile(
        r"[.!?。！？]\s*$"
    )

    def __init__(
        self,
        *,
        tokenizer=None,
        kiwi: Kiwi | None = None,
    ):
        self.tokenizer = (
            tokenizer
            if tokenizer is not None
            else get_feedit_tokenizer()
        )

        self.kiwi = (
            kiwi
            if kiwi is not None
            else Kiwi()
        )

    def extract(
        self,
        text: str | None,
    ) -> ProductNameExtractionResult:
        raw_text = str(
            text or ""
        )

        lines = raw_text.splitlines()

        candidates: list[
            ProductNameCandidate
        ] = []

        for line_index, raw_line in enumerate(
            lines
        ):
            candidate = self._analyze_line(
                raw_line=raw_line,
                line_index=line_index,
            )

            if candidate is None:
                continue

            candidates.append(
                candidate
            )

        candidates = self._deduplicate(
            candidates
        )

        return ProductNameExtractionResult(
            raw_text=raw_text,
            line_count=len(lines),
            candidate_count=len(candidates),
            candidates=candidates,
        )

    def _analyze_line(
        self,
        *,
        raw_line: str,
        line_index: int,
    ) -> ProductNameCandidate | None:
        source_text = str(
            raw_line or ""
        ).strip()

        if not source_text:
            return None

        # ---------------------------------------------
        # 명백한 비상품 데이터 제거
        # ---------------------------------------------

        if self.URL_RE.search(
            source_text
        ):
            return None

        if self.EMAIL_RE.search(
            source_text
        ):
            return None

        if self._is_price_line(
            source_text
        ):
            return None

        if self.SECTION_RE.match(
            source_text
        ):
            return None

        if self.CONTACT_RE.search(
            source_text
        ):
            return None

        # ---------------------------------------------
        # 구조 정보
        # ---------------------------------------------

        has_product_prefix = bool(
            self.PRODUCT_PREFIX_RE.match(
                source_text
            )
        )

        has_timestamp = bool(
            self.TIMESTAMP_RE.match(
                source_text
            )
        )

        # 타임스탬프 자체는 제거하고 뒤의 문자열은 살린다.
        text = self.TIMESTAMP_RE.sub(
            "",
            source_text,
        )

        # └, -, 1. 같은 목록 prefix 제거
        text = self.PRODUCT_PREFIX_RE.sub(
            "",
            text,
        )

        text = self._clean_candidate_text(
            text
        )

        if not text:
            return None

        # ---------------------------------------------
        # 너무 짧거나 너무 긴 문자열 제거
        # ---------------------------------------------

        if len(text) < 2:
            return None

        if len(text) > 120:
            return None

        # ---------------------------------------------
        # SemanticTokenizer
        # ---------------------------------------------

        tokenized = self.tokenizer.tokenize(
            text
        )

        known_tokens = [
            token
            for token in tokenized.get(
                "tokens",
                [],
            )
            if (
                token.get("kind") == "KNOWN"
                and token.get("term_id") is not None
            )
        ]

        if not known_tokens:
            return None

        item_tokens = [
            token
            for token in known_tokens
            if token.get("term_type") == "ITEM"
        ]

        # 상품명 후보는 ITEM 하나 이상 필수.
        if not item_tokens:
            return None

        # ---------------------------------------------
        # 자연어 문장 여부
        # ---------------------------------------------

        morph_count = self._count_morphs(
            text
        )

        sentence_like = (
            self._looks_like_sentence(
                text=text,
                morph_count=morph_count,
            )
        )

        # ---------------------------------------------
        # confidence 계산
        # ---------------------------------------------

        score = 0.0
        reasons: list[str] = []

        # ITEM term은 가장 강한 의미 신호
        score += 0.40
        reasons.append(
            "HAS_ITEM_TERM"
        )

        # 목록 prefix가 있으면 매우 강한 구조 신호
        if has_product_prefix:
            score += 0.30
            reasons.append(
                "PRODUCT_LIST_PREFIX"
            )

        # 여러 fashion term이 같이 있으면
        # 상품명일 가능성이 높음
        if len(known_tokens) >= 2:
            score += 0.10
            reasons.append(
                "MULTIPLE_FASHION_TERMS"
            )

        if len(known_tokens) >= 3:
            score += 0.05
            reasons.append(
                "HIGH_TERM_DENSITY"
            )

        # 적당한 상품명 길이
        if 2 <= morph_count <= 12:
            score += 0.10
            reasons.append(
                "PRODUCT_NAME_LENGTH"
            )

        # 타임스탬프 뒤에 바로 상품명이 나오는 형식도 존재
        if has_timestamp:
            score += 0.05
            reasons.append(
                "TIMESTAMP_PREFIX"
            )

        # 완전한 설명 문장처럼 보이면 감점
        if sentence_like:
            score -= 0.30
            reasons.append(
                "SENTENCE_LIKE"
            )

        score = max(
            0.0,
            min(
                score,
                1.0,
            ),
        )

        # ---------------------------------------------
        # 최종 판정
        # ---------------------------------------------

        # 구조적으로 상품 목록임이 명확한 경우
        if has_product_prefix:
            threshold = 0.55

        # 구조 신호가 없는 경우에는
        # 의미적 근거를 더 강하게 요구
        else:
            threshold = 0.65

        if score < threshold:
            return None

        item_term_ids = sorted(
            {
                int(item_token["term_id"])
                for item_token in item_tokens
                if item_token.get("term_id") is not None
            }
        )

        item_names = sorted(
            {
                str(
                    item_token.get("canonical_name")
                    or item_token.get("surface")
                    or ""
                )
                for item_token in item_tokens
                if (
                    item_token.get("canonical_name")
                    or item_token.get("surface")
                )
            }
        )

        return ProductNameCandidate(
            text=text,
            source_text=source_text,
            line_index=line_index,
            confidence=round(
                score,
                3,
            ),
            item_term_ids=item_term_ids,
            item_names=item_names,
            term_count=len(known_tokens),
            detection_reasons=reasons,
        )

    def _is_price_line(
        self,
        text: str,
    ) -> bool:
        """
        가격/할인 정보가 중심인 줄인지 판정.
        """

        price_matches = list(
            self.PRICE_RE.finditer(
                text
            )
        )

        if not price_matches:
            return False

        remaining = self.PRICE_RE.sub(
            "",
            text,
        )

        remaining = re.sub(
            r"[\s→>-]+",
            "",
            remaining,
        )

        return len(remaining) <= 15

    @staticmethod
    def _clean_candidate_text(
        text: str,
    ) -> str:
        text = str(
            text or ""
        )

        text = text.strip()

        # 앞쪽 tree/list 문자 한 번 더 정리
        text = re.sub(
            r"^[└├│▶▷►▸•·*]+\s*",
            "",
            text,
        )

        # 양쪽 불필요한 구분자
        text = text.strip(
            " \t\r\n|_-–—:;"
        )

        # 공백 정규화
        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    def _count_morphs(
        self,
        text: str,
    ) -> int:
        try:
            tokens = self.kiwi.tokenize(
                text
            )

            return len(
                [
                    token
                    for token in tokens
                    if token.form.strip()
                ]
            )

        except Exception:
            return len(
                text.split()
            )

    def _looks_like_sentence(
        self,
        *,
        text: str,
        morph_count: int,
    ) -> bool:
        """
        상품명보다 일반 설명 문장에 가까운지 판정.

        너무 공격적으로 제거하지 않고,
        명백한 자연어 문장만 감점한다.
        """

        if self.SENTENCE_END_RE.search(
            text
        ):
            return True

        if morph_count >= 15:
            return True

        sentence_patterns = (
            "입니다",
            "이에요",
            "예요",
            "했어요",
            "했는데",
            "있어요",
            "없어요",
            "좋아요",
            "추천해요",
            "입었어요",
            "보여드릴",
            "소개해",
            "준비했",
        )

        if any(
            pattern in text
            for pattern in sentence_patterns
        ):
            return True

        return False

    @staticmethod
    def _deduplicate(
        candidates: list[
            ProductNameCandidate
        ],
    ) -> list[
        ProductNameCandidate
    ]:
        """
        같은 line에서 동일 상품명이 중복 생성되는 것을 방지.

        서로 다른 line에서 같은 상품명이 다시 등장하는 것은
        현재 단계에서는 보존한다.
        """

        seen: set[
            tuple[int, str]
        ] = set()

        result: list[
            ProductNameCandidate
        ] = []

        for candidate in candidates:
            key = (
                candidate.line_index,
                candidate.text,
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            result.append(
                candidate
            )

        return result