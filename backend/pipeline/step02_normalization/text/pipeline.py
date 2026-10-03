from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.core.models import (
    TextDocument,
    TextTermMention,
)

from .writer import TextMentionWriter
from .legacy_mentions import MentionMerger
from .mention_extractor import TextMentionExtractor



@dataclass
class TextNormalizationResult:
    document_id: int
    source_code: str | None
    document_type: str

    segment_count: int
    product_name_candidate_count: int

    mention_count: int
    unique_term_count: int

    deleted: int
    created: int
    skipped: int

    db_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_code": self.source_code,
            "document_type": self.document_type,
            "segment_count": self.segment_count,
            "product_name_candidate_count": (
                self.product_name_candidate_count
            ),
            "mention_count": self.mention_count,
            "unique_term_count": self.unique_term_count,
            "deleted": self.deleted,
            "created": self.created,
            "skipped": self.skipped,
            "db_count": self.db_count,
        }


class TextNormalizationPipeline:
    """
    FEEDIT STEP02 Text Normalization Pipeline.

    Input
    -----
    TextDocument

    Flow
    ----
    TextDocument.body
        -> TextMentionExtractor
            -> ProductNameExtractor
            -> KiwiTextPreprocessor
            -> SemanticTokenizer
        -> TextMentionWriter
        -> TextTermMention

    Policy
    ------
    - TextDocument는 STEP02의 입력이다.
    - TextDocument 생성은 이 파이프라인에서 하지 않는다.
    - DictionaryTerm으로 확인된 mention만 저장한다.
    - Brand-only match처럼 term_id가 없는 결과는 저장하지 않는다.
    - 문서 단위 replace 방식으로 TextTermMention을 저장한다.
    - sentiment / intent 분석은 여기서 수행하지 않는다.
    - 구버전 text_signals pipeline을 사용하지 않는다.
    """

    VERSION = 1

    def __init__(self) -> None:
        # -----------------------------------------------------
        # Component는 pipeline 생성 시 한 번만 준비한다.
        #
        # TextMentionExtractor 내부에서
        # get_feedit_tokenizer() singleton을 사용한다.
        # -----------------------------------------------------

        self.extractor = TextMentionExtractor()
        self.writer = TextMentionWriter()
        self.merger = MentionMerger()

    # =========================================================
    # Dictionary reload
    # =========================================================

    def reload_dictionary(self) -> None:
        """
        DictionaryTerm / TermAlias / Brand dictionary 변경 후
        semantic tokenizer를 다시 로드한다.
        """

        tokenizer = getattr(
            self.extractor,
            "tokenizer",
            None,
        )

        if tokenizer is None:
            raise RuntimeError(
                "TextMentionExtractor tokenizer를 찾을 수 없습니다."
            )

        reload_method = getattr(
            tokenizer,
            "reload_dictionary",
            None,
        )

        if callable(reload_method):
            reload_method()
            return

        # 현재 tokenizer 구현이 reload_dictionary()를 제공하지 않는
        # 경우 singleton을 강제 재생성한다.
        from pipeline.step02_normalization.semantic_tokenizer.tokenizer import (
            get_feedit_tokenizer,
        )

        tokenizer = get_feedit_tokenizer(
            force_reload=True,
        )

        self.extractor.tokenizer = tokenizer

        product_name_extractor = getattr(
            self.extractor,
            "product_name_extractor",
            None,
        )

        if product_name_extractor is not None:
            product_name_extractor.tokenizer = tokenizer

    # =========================================================
    # Run by ID
    # =========================================================

    def run_by_id(
        self,
        document_id: int,
    ) -> TextNormalizationResult:
        document = (
            TextDocument.objects
            .select_related("source")
            .get(id=document_id)
        )

        return self.run(document)

    # =========================================================
    # Main
    # =========================================================

    def run(
        self,
        document: TextDocument,
    ) -> TextNormalizationResult:
        self._validate_document(document)

        raw_text = str(
            document.body or ""
        ).strip()

        document_type = str(
            document.document_type or ""
        ).strip().upper()

        # -----------------------------------------------------
        # 1. Extract
        # -----------------------------------------------------

        extraction = self.extractor.extract(
            raw_text,
            document_type=document_type,
        )
        
        merged = self.merger.merge(
            document=document,
            result=extraction,
        )

        # -----------------------------------------------------
        # 2. Write
        #
        # Writer 내부에서도 transaction을 사용하더라도
        # pipeline 단위에서 한 번 더 atomic boundary를 둔다.
        # -----------------------------------------------------

        with transaction.atomic():
            write_result = self.writer.write(
                document=document,
                result=extraction,
            )

        # -----------------------------------------------------
        # 3. Verify persisted count
        # -----------------------------------------------------

        db_count = (
            TextTermMention.objects
            .filter(document_id=document.id)
            .count()
        )

        expected_count = int(
            write_result.created
        )

        if db_count != expected_count:
            raise RuntimeError(
                "TextTermMention 저장 검증 실패: "
                f"document_id={document.id}, "
                f"created={expected_count}, "
                f"db_count={db_count}"
            )

        # -----------------------------------------------------
        # 4. Result
        # -----------------------------------------------------

        source_code = None

        if document.source_id:
            source_code = str(
                document.source.code or ""
            ).strip()

        return TextNormalizationResult(
            document_id=document.id,
            source_code=source_code,
            document_type=document_type,
            segment_count=extraction.segment_count,
            product_name_candidate_count=(
                extraction.product_name_candidate_count
            ),
            mention_count=extraction.mention_count,
            unique_term_count=extraction.unique_term_count,
            deleted=write_result.deleted,
            created=write_result.created,
            skipped=write_result.skipped,
            db_count=db_count,
        )

    # =========================================================
    # Validation
    # =========================================================

    @staticmethod
    def _validate_document(
        document: TextDocument,
    ) -> None:
        if not isinstance(
            document,
            TextDocument,
        ):
            raise TypeError(
                "document는 TextDocument 인스턴스여야 합니다."
            )

        if document.pk is None:
            raise ValueError(
                "저장되지 않은 TextDocument는 "
                "STEP02에서 처리할 수 없습니다."
            )

        if not str(
            document.body or ""
        ).strip():
            raise ValueError(
                "TextDocument.body가 비어 있습니다. "
                f"document_id={document.id}"
            )