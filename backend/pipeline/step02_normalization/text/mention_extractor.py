from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pipeline.step02_normalization.semantic_tokenizer.tokenizer import (
    get_feedit_tokenizer,
)
from pipeline.step02_normalization.text.preprocessor import (
    KiwiTextPreprocessor,
    TextSegment,
)
from pipeline.step02_normalization.text.product_name_extractor import (
    ProductNameCandidate,
    ProductNameExtractor,
)


@dataclass
class TextMention:
    term_id: int
    term_code: str | None
    term_type: str | None
    canonical_name: str | None

    surface: str
    match_type: str | None

    segment_index: int
    segment_text: str

    start_char: int | None
    end_char: int | None

    brand_id: int | None = None
    brand_code: str | None = None

    confidence: float = 1.0

    # ---------------------------------------------------------
    # Context
    # ---------------------------------------------------------

    context_type: str = "TEXT"

    product_name: str | None = None
    product_name_confidence: float | None = None


@dataclass
class TextMentionExtractionResult:
    raw_text: str
    clean_text: str

    document_type: str | None

    segment_count: int

    product_name_candidate_count: int

    mention_count: int
    unique_term_count: int

    mentions: list[TextMention]

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "clean_text": self.clean_text,
            "document_type": self.document_type,
            "segment_count": self.segment_count,
            "product_name_candidate_count": (
                self.product_name_candidate_count
            ),
            "mention_count": self.mention_count,
            "unique_term_count": self.unique_term_count,
            "mentions": [
                asdict(mention)
                for mention in self.mentions
            ],
        }


class TextMentionExtractor:
    """
    TextDocument.body
        ↓
    ProductNameExtractor
        ↓
    TextPreprocessor
        ↓
    Segment
        ↓
    SemanticTokenizer
        ↓
    TextMention

    상품명 후보는 별도의 mention을 생성하지 않는다.

    기존 TextSegment가 상품명 후보와 일치하면
    해당 segment에서 생성되는 mention에:

        context_type = PRODUCT_NAME
        product_name
        product_name_confidence

    를 부여한다.

    DB write 없음.
    """

    def __init__(
        self,
        *,
        preprocessor: KiwiTextPreprocessor | None = None,
        tokenizer=None,
        product_name_extractor: ProductNameExtractor | None = None,
    ):
        self.preprocessor = (
            preprocessor
            if preprocessor is not None
            else KiwiTextPreprocessor()
        )

        self.tokenizer = (
            tokenizer
            if tokenizer is not None
            else get_feedit_tokenizer()
        )

        self.product_name_extractor = (
            product_name_extractor
            if product_name_extractor is not None
            else ProductNameExtractor(
                tokenizer=self.tokenizer,
            )
        )

    def extract(
        self,
        text: str | None,
        *,
        document_type: str | None = None,
    ) -> TextMentionExtractionResult:
        raw_text = str(
            text or ""
        )

        # -----------------------------------------------------
        # 1. 원문에서 상품명 후보 먼저 추출
        # -----------------------------------------------------

        product_result = (
            self.product_name_extractor.extract(
                raw_text
            )
        )

        product_candidates = (
            product_result.candidates
        )

        # -----------------------------------------------------
        # 2. 일반 Text 전처리
        # -----------------------------------------------------

        preprocess_result = (
            self.preprocessor.process(
                raw_text,
                document_type=document_type,
            )
        )

        # -----------------------------------------------------
        # 3. 상품명 후보 lookup 생성
        # -----------------------------------------------------

        product_lookup = (
            self._build_product_lookup(
                product_candidates
            )
        )

        # -----------------------------------------------------
        # 4. Segment별 mention 추출
        # -----------------------------------------------------

        mentions: list[TextMention] = []

        for segment in preprocess_result.segments:
            product_candidate = (
                self._find_product_candidate(
                    segment=segment,
                    product_lookup=product_lookup,
                )
            )

            segment_mentions = (
                self._extract_segment_mentions(
                    segment=segment,
                    product_candidate=product_candidate,
                )
            )

            mentions.extend(
                segment_mentions
            )

        # -----------------------------------------------------
        # 5. 통계
        # -----------------------------------------------------

        unique_term_ids = {
            mention.term_id
            for mention in mentions
        }

        return TextMentionExtractionResult(
            raw_text=raw_text,
            clean_text=preprocess_result.clean_text,
            document_type=document_type,
            segment_count=len(
                preprocess_result.segments
            ),
            product_name_candidate_count=len(
                product_candidates
            ),
            mention_count=len(
                mentions
            ),
            unique_term_count=len(
                unique_term_ids
            ),
            mentions=mentions,
        )

    def _extract_segment_mentions(
        self,
        *,
        segment: TextSegment,
        product_candidate: ProductNameCandidate | None,
    ) -> list[TextMention]:
        text = str(
            segment.text or ""
        ).strip()

        if not text:
            return []

        tokenized = self.tokenizer.tokenize(
            text
        )

        tokens = tokenized.get(
            "tokens",
            [],
        )

        mentions: list[TextMention] = []

        # 동일 surface가 여러 번 나올 때
        # 앞 occurrence를 계속 잡는 문제 방지
        surface_cursors: dict[str, int] = {}

        for token in tokens:
            if token.get("kind") != "KNOWN":
                continue

            term_id = token.get(
                "term_id"
            )

            # Brand match 등 term_id가 없는 경우
            # TextTermMention으로 저장할 수 없음.
            if term_id is None:
                continue

            surface = str(
                token.get("surface")
                or ""
            ).strip()

            if not surface:
                continue

            start_char, end_char = (
                self._resolve_occurrence(
                    text=text,
                    surface=surface,
                    cursors=surface_cursors,
                )
            )

            # ---------------------------------------------
            # Context
            # ---------------------------------------------

            if product_candidate is not None:
                context_type = (
                    "PRODUCT_NAME"
                )

                product_name = (
                    product_candidate.text
                )

                product_name_confidence = (
                    product_candidate.confidence
                )

            else:
                context_type = "TEXT"
                product_name = None
                product_name_confidence = None

            mention = TextMention(
                term_id=int(
                    term_id
                ),
                term_code=token.get(
                    "term_code"
                ),
                term_type=token.get(
                    "term_type"
                ),
                canonical_name=token.get(
                    "canonical_name"
                ),
                surface=surface,
                match_type=token.get(
                    "match_type"
                ),
                segment_index=segment.index,
                segment_text=text,
                start_char=start_char,
                end_char=end_char,
                brand_id=token.get(
                    "brand_id"
                ),
                brand_code=token.get(
                    "brand_code"
                ),
                confidence=1.0,
                context_type=context_type,
                product_name=product_name,
                product_name_confidence=(
                    product_name_confidence
                ),
            )

            mentions.append(
                mention
            )

        return mentions

    def _build_product_lookup(
        self,
        candidates: list[
            ProductNameCandidate
        ],
    ) -> dict[
        str,
        ProductNameCandidate,
    ]:
        """
        상품명 후보를 normalized text 기준으로 lookup한다.

        동일 문자열이 여러 번 발견되면
        confidence가 높은 후보를 사용한다.
        """

        lookup: dict[
            str,
            ProductNameCandidate,
        ] = {}

        for candidate in candidates:
            key = self._normalize_context_text(
                candidate.text
            )

            if not key:
                continue

            existing = lookup.get(
                key
            )

            if existing is None:
                lookup[key] = candidate
                continue

            if (
                candidate.confidence
                > existing.confidence
            ):
                lookup[key] = candidate

        return lookup

    def _find_product_candidate(
        self,
        *,
        segment: TextSegment,
        product_lookup: dict[
            str,
            ProductNameCandidate,
        ],
    ) -> ProductNameCandidate | None:
        """
        전처리된 segment가 원문의 상품명 후보와
        같은 문자열인지 확인한다.

        1차 버전에서는 exact normalized match만 사용한다.

        substring matching은 일반 문장을 PRODUCT_NAME으로
        잘못 분류할 위험이 있으므로 하지 않는다.
        """

        segment_text = (
            self._normalize_context_text(
                segment.text
            )
        )

        if not segment_text:
            return None

        candidate = product_lookup.get(
            segment_text
        )

        if candidate is None:
            return None

        if candidate.confidence < 0.90:
            return None

        return candidate

    @staticmethod
    def _normalize_context_text(
        text: str | None,
    ) -> str:
        """
        ProductNameExtractor와 TextPreprocessor 사이의
        단순 표기 차이만 정규화한다.
        """

        import re

        value = str(
            text or ""
        ).strip()

        if not value:
            return ""

        # tree/list prefix 제거
        value = re.sub(
            r"^[└├│▶▷►▸•·*]+\s*",
            "",
            value,
        )

        # 1. / 1) 형태 제거
        value = re.sub(
            r"^\d{1,3}[.)]\s*",
            "",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    @staticmethod
    def _resolve_occurrence(
        *,
        text: str,
        surface: str,
        cursors: dict[str, int],
    ) -> tuple[
        int | None,
        int | None,
    ]:
        """
        tokenizer가 현재 source span을 반환하지 않으므로
        surface occurrence를 순차적으로 복원한다.

        예:
            팬츠 ... 팬츠

        첫 번째 팬츠와 두 번째 팬츠가
        서로 다른 위치를 갖도록 cursor를 유지한다.

        주의:
        tokenizer 자체가 native span을 반환하게 되면
        이 함수는 제거하는 것이 가장 좋다.
        """

        if not text:
            return (
                None,
                None,
            )

        if not surface:
            return (
                None,
                None,
            )

        cursor_key = surface.lower()

        start_from = cursors.get(
            cursor_key,
            0,
        )

        # ---------------------------------------------
        # exact
        # ---------------------------------------------

        start = text.find(
            surface,
            start_from,
        )

        # ---------------------------------------------
        # case-insensitive fallback
        # ---------------------------------------------

        if start < 0:
            start = (
                text.lower().find(
                    surface.lower(),
                    start_from,
                )
            )

        # ---------------------------------------------
        # cursor 이후에 없으면
        # 전체 문자열에서 마지막 fallback
        # ---------------------------------------------

        if start < 0:
            start = text.find(
                surface
            )

        if start < 0:
            start = (
                text.lower().find(
                    surface.lower()
                )
            )

        if start < 0:
            return (
                None,
                None,
            )

        end = (
            start
            + len(surface)
        )

        cursors[cursor_key] = end

        return (
            start,
            end,
        )