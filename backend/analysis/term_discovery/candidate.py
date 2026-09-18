from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from kiwipiepy import Kiwi


class CandidateNormalizer:
    """
    후보 문자열 표기 통합만 담당.
    의미 판단 / 승격 판단은 하지 않는다.
    """

    _SPACE_RE = re.compile(r"\s+")
    _EDGE_PUNCT_RE = re.compile(
        r"^[\s\[\]\(\)\{\}<>\"'`~!@#$%^&*+=|\\/:;,.?·•_-]+"
        r"|"
        r"[\s\[\]\(\)\{\}<>\"'`~!@#$%^&*+=|\\/:;,.?·•_-]+$"
    )

    @classmethod
    def normalize(cls, text: str | None) -> str:
        value = str(text or "")
        value = unicodedata.normalize("NFKC", value)
        value = value.strip()
        value = cls._EDGE_PUNCT_RE.sub("", value)
        value = cls._SPACE_RE.sub(" ", value)
        return value.casefold().strip()


class CandidateFilter:
    """
    후보 문자열 자체의 명백한 형태 노이즈만 제거.
    애매하면 KEEP.
    """

    _ONLY_NUMBER_SYMBOL_RE = re.compile(
        r"^[\d\s.,%+\-_/&|]+$"
    )

    def __init__(
        self,
        *,
        min_length: int = 2,
        max_length: int = 40,
    ):
        self.min_length = min_length
        self.max_length = max_length

    def check(self, text: str) -> dict:
        value = str(text or "").strip()

        if not value:
            return {"keep": False, "reason": "EMPTY"}

        if len(value) < self.min_length:
            return {"keep": False, "reason": "TOO_SHORT"}

        if len(value) > self.max_length:
            return {"keep": False, "reason": "TOO_LONG"}

        if self._ONLY_NUMBER_SYMBOL_RE.fullmatch(value):
            return {
                "keep": False,
                "reason": "ONLY_NUMBER_SYMBOL",
            }

        return {"keep": True, "reason": None}


@dataclass
class ExtractedPhrase:
    text: str
    tokens: list[str]
    pos_tags: list[str]

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "tokens": self.tokens,
            "pos_tags": self.pos_tags,
        }


class PhraseExtractor:
    """
    YouTube / transcript / review 등 raw text용.
    ProductSource clean-UNKNOWN 경로에서는 현재 사용하지 않는다.
    """

    TERM_POS = {"NNG", "NNP", "SL", "SH"}
    DERIVATIONAL_SUFFIX_POS = {"XSV", "XSA", "XSA-I"}

    def __init__(
        self,
        *,
        max_phrase_tokens: int = 3,
    ):
        self.kiwi = Kiwi()
        self.max_phrase_tokens = max_phrase_tokens

    def extract(
        self,
        text: str,
        *,
        max_n: int | None = None,
    ) -> list[ExtractedPhrase]:
        if not text:
            return []

        max_n = max_n or self.max_phrase_tokens
        tokens = list(
            self.kiwi.tokenize(
                text,
                normalize_coda=True,
            )
        )

        candidates: dict[str, ExtractedPhrase] = {}

        for i, token in enumerate(tokens):
            if token.tag not in self.TERM_POS:
                continue

            if (
                i + 1 < len(tokens)
                and tokens[i + 1].tag
                in self.DERIVATIONAL_SUFFIX_POS
            ):
                continue

            phrase = ExtractedPhrase(
                text=token.form,
                tokens=[token.form],
                pos_tags=[token.tag],
            )
            candidates[phrase.text] = phrase

        chunks: list[list[Any]] = []
        current: list[Any] = []

        for token in tokens:
            if token.tag in self.TERM_POS:
                current.append(token)
            else:
                if current:
                    chunks.append(current)
                    current = []

        if current:
            chunks.append(current)

        for chunk in chunks:
            if len(chunk) < 2:
                continue

            upper_n = min(max_n, len(chunk))

            for n in range(2, upper_n + 1):
                for start in range(
                    0,
                    len(chunk) - n + 1,
                ):
                    window = chunk[start:start + n]
                    phrase = ExtractedPhrase(
                        text=" ".join(
                            token.form
                            for token in window
                        ),
                        tokens=[
                            token.form
                            for token in window
                        ],
                        pos_tags=[
                            token.tag
                            for token in window
                        ],
                    )
                    candidates[phrase.text] = phrase

        return list(candidates.values())


class TermhoodFilter:
    """
    raw-text PhraseExtractor 결과가 후보가 될 만한지
    LLM 없이 보수적으로 판단.
    """

    NOUN_POS = {"NNG", "NNP", "NNB"}
    FOREIGN_POS = {"SL", "SH"}

    GENERIC_HEADS = {
        "소재",
        "원단",
        "상품",
        "제품",
        "아이템",
        "디자인",
    }

    STOP_TERMS = {
        "것",
        "수",
        "때",
        "중",
        "등",
        "부분",
        "정도",
        "경우",
        "이번",
        "요즘",
        "상품",
        "제품",
        "추천",
        "아이템",
        "스타일링",
        "디자인",
        "특유",
        "특징",
    }

    FASHION_HEADS = {
        "핏",
        "실루엣",
        "라인",
        "넥",
        "넥라인",
        "슬리브",
        "소매",
        "기장",
        "길이",
        "디테일",
        "소재",
        "원단",
        "조직",
        "조직감",
        "질감",
        "텍스처",
        "촉감",
        "터치감",
        "광택",
        "광택감",
        "착용감",
        "신축성",
        "통기성",
        "보온성",
        "내구성",
        "유연성",
        "워싱",
        "가공",
        "염색",
        "팬츠",
        "셔츠",
        "재킷",
        "자켓",
        "스커트",
        "원피스",
        "쇼츠",
        "부츠",
        "로퍼",
        "룩",
        "스타일",
        "코어",
        "무드",
    }

    BAD_ENDINGS = (
        "하다",
        "한다",
        "하는",
        "한",
        "하고",
        "해서",
        "하면",
        "되어",
        "되는",
        "같은",
        "있는",
        "없는",
    )

    def __init__(self):
        self.normalizer = CandidateNormalizer()

    def is_valid(
        self,
        phrase: ExtractedPhrase,
    ) -> bool:
        normalized = self.normalizer.normalize(
            phrase.text
        )

        if not normalized:
            return False

        if len(normalized) < 2:
            return False

        if normalized in self.STOP_TERMS:
            return False

        if normalized.isdigit():
            return False

        if re.fullmatch(r"[\d\W_]+", normalized):
            return False

        if any(
            normalized.endswith(ending)
            for ending in self.BAD_ENDINGS
        ):
            return False

        if not phrase.pos_tags:
            return False

        head_tag = phrase.pos_tags[-1]

        if (
            head_tag not in self.NOUN_POS
            and head_tag not in self.FOREIGN_POS
        ):
            return False

        if len(phrase.tokens) == 1:
            return True

        head = phrase.tokens[-1].lower()

        if head in self.GENERIC_HEADS:
            return False

        if head in self.FASHION_HEADS:
            return True

        if all(
            tag in self.FOREIGN_POS
            for tag in phrase.pos_tags
        ):
            return True

        return True


@dataclass
class ProductUnknownEvidence:
    text: str
    surface: str | None
    source_field: str | None
    source_index: int | None
    source_text: str | None
    candidate_source: str | None
    product_source_id: int | None
    source_code: str | None
    source_object: Any | None
    reason: str | None = None
    tags: list[str] | None = None

@dataclass
class PreparedObservation:
    """
    S3 Term Observation으로 저장하기 직전의 형태.

    Candidate가 아니다.

    UNKNOWN
    -> normalize
    -> shape filter
    -> dedupe
    -> PreparedObservation
    -> S3
    """

    raw_term: str
    normalized_term: str
    evidence: ProductUnknownEvidence

    def to_dict(self) -> dict:
        raw_text = (
            self.evidence.source_text
            or self.evidence.text
            or self.raw_term
        )

        return {
            "term": self.raw_term,
            "normalized_term": self.normalized_term,

            "source": (
                self.evidence.source_code
                or "UNKNOWN"
            ),

            "source_type": (
                self._resolve_source_type()
            ),

            "source_entity_id": (
                str(
                    self.evidence.product_source_id
                )
                if self.evidence.product_source_id
                is not None
                else None
            ),

            "source_field": (
                self.evidence.source_field
            ),

            "raw_text": raw_text,

            "residual_text": (
                self.evidence.text
            ),

            "candidate_source": (
                self.evidence.candidate_source
            ),

            "reason": (
                self.evidence.reason
            ),

            "tags": (
                self.evidence.tags
                or []
            ),
        }

    def _resolve_source_type(
        self,
    ) -> str:
        """
        ProductSource unknown_evidence의 source_field를
        Term Observation source_type으로 변환.

        너무 복잡하게 추론하지 않고
        명확한 것만 분류한다.
        """

        field = (
            self.evidence.source_field
            or ""
        ).strip().lower()

        candidate_source = (
            self.evidence.candidate_source
            or ""
        ).strip().lower()

        if field in {
            "source_name",
            "normalized_name",
            "product_name",
            "name",
        }:
            return "PRODUCT_NAME"

        if (
            "attribute" in field
            or "attribute" in candidate_source
            or field in {
                "tag",
                "tags",
                "option",
                "options",
            }
        ):
            return "PRODUCT_ATTRIBUTE"

        if field in {
            "description",
            "product_description",
        }:
            return "PRODUCT_DESCRIPTION"

        return "OTHER"


# ============================================================
# OBSERVATION BUILDER
# ============================================================


class CandidateBuilder:
    """
    이름은 기존 호출부 영향 때문에 당장은 유지.

    실제 역할:

    ProductSource
    -> feedit_analysis.unknown_evidence
    -> normalize
    -> shape filter
    -> dedupe
    -> PreparedObservation

    DB Candidate는 여기서 생성하지 않는다.
    """

    def __init__(
        self,
        *,
        min_length: int = 2,
        max_length: int = 40,
    ):
        self.normalizer = CandidateNormalizer()

        self.filter = CandidateFilter(
            min_length=min_length,
            max_length=max_length,
        )

    # ========================================================
    # LOAD
    # ========================================================

    def load_product_unknowns(
        self,
        product_source,
    ) -> list[ProductUnknownEvidence]:

        attributes = (
            getattr(
                product_source,
                "attributes",
                None,
            )
            or {}
        )

        analysis = (
            attributes.get(
                "feedit_analysis"
            )
            or {}
        )

        rows = (
            analysis.get(
                "unknown_evidence"
            )
            or []
        )

        source_obj = getattr(
            product_source,
            "source",
            None,
        )

        source_code = getattr(
            source_obj,
            "code",
            None,
        )

        result: list[
            ProductUnknownEvidence
        ] = []

        for row in rows:

            if not isinstance(
                row,
                dict,
            ):
                continue

            text = str(
                row.get("text")
                or row.get("surface")
                or ""
            ).strip()

            if not text:
                continue

            result.append(
                ProductUnknownEvidence(
                    text=text,

                    surface=row.get(
                        "surface"
                    ),

                    source_field=row.get(
                        "source_field"
                    ),

                    source_index=row.get(
                        "source_index"
                    ),

                    source_text=row.get(
                        "source_text"
                    ),

                    candidate_source=row.get(
                        "candidate_source"
                    ),

                    product_source_id=getattr(
                        product_source,
                        "id",
                        None,
                    ),

                    source_code=(
                        source_code
                    ),

                    source_object=(
                        source_obj
                    ),

                    reason=row.get(
                        "reason"
                    ),

                    tags=row.get(
                        "tags"
                    ),
                )
            )

        return result

    # ========================================================
    # PREPARE OBSERVATIONS
    # ========================================================

    def prepare_product_observations(
        self,
        product_sources,
    ) -> dict:
        """
        ProductSource 여러 건의 UNKNOWN evidence를
        S3 저장 가능한 Observation으로 준비한다.

        여기서는:
        - DB 저장 안 함
        - Candidate 생성 안 함
        - Embedding 안 함
        - Refiner 안 함
        """

        evidences: list[
            ProductUnknownEvidence
        ] = []

        for product_source in (
            product_sources
        ):
            evidences.extend(
                self.load_product_unknowns(
                    product_source
                )
            )

        prepared: list[
            PreparedObservation
        ] = []

        dropped: list[dict] = []

        seen = set()

        for evidence in evidences:

            normalized = (
                self.normalizer.normalize(
                    evidence.text
                )
            )

            check = (
                self.filter.check(
                    normalized
                )
            )

            if not check["keep"]:
                dropped.append(
                    {
                        "text": (
                            evidence.text
                        ),
                        "normalized_term": (
                            normalized
                        ),
                        "reason": (
                            check["reason"]
                        ),
                        "product_source_id": (
                            evidence
                            .product_source_id
                        ),
                        "source_field": (
                            evidence
                            .source_field
                        ),
                    }
                )
                continue

            # 같은 ProductSource,
            # 같은 field,
            # 같은 normalized term
            # 중복 관측 방지
            key = (
                evidence.product_source_id,
                evidence.source_field,
                normalized,
            )

            if key in seen:
                continue

            seen.add(key)

            prepared.append(
                PreparedObservation(
                    raw_term=(
                        evidence.text
                    ),
                    normalized_term=(
                        normalized
                    ),
                    evidence=evidence,
                )
            )

        return {
            "prepared": prepared,
            "dropped": dropped,
            "evidence_count": (
                len(evidences)
            ),
            "prepared_count": (
                len(prepared)
            ),
            "dropped_count": (
                len(dropped)
            ),
        }


# ============================================================
# KNOWN ENTITY GUARD
# ============================================================

import re

from apps.core.models import (
    Brand,
    Category,
    CategorySource,
    DictionaryTerm,
    TermAlias,
)


class DictionaryGuard:
    """
    FEEDIT Known Entity Guard v5

    역할
    ------------------------------------------------------------
    신규 Term Discovery로 보내면 안 되는 기존 지식을 식별한다.

    우선순위
    ------------------------------------------------------------
    1. DictionaryTerm / TermAlias -> KNOWN_TERM
    2. Brand                      -> BRAND
    3. Category / CategorySource  -> CATEGORY
    4. 그 외                      -> None

    중요
    ------------------------------------------------------------
    CategorySource까지 CATEGORY로 취급한다.

    예:
        봄        -> KNOWN_TERM   (DictionaryTerm / TPO)
        아우터    -> CATEGORY     (CategorySource)
        치마      -> CATEGORY
        구두      -> CATEGORY
        면바지    -> CATEGORY

    따라서 이후 CompoundResolver에서:

        봄아우터
        -> 봄(KNOWN_TERM)
        -> 아우터(CATEGORY)

    처럼 기존 지식으로 회수할 수 있다.
    """

    # ---------------------------------------------------------
    # 일반 모델에서 읽을 수 있는 텍스트 필드 후보
    # ---------------------------------------------------------
    TEXT_FIELD_CANDIDATES = (
        "name",
        "normalized_name",
        "canonical_name",
        "english_name",
        "brand_code",
        "code",
        "category_code",
        "slug",
    )

    # ---------------------------------------------------------
    # CategorySource 전용
    #
    # 플랫폼별 모델 필드명이 달라도 동적으로 존재하는 것만 사용.
    # ID 필드보다는 실제 사람이 읽는 카테고리명 위주.
    # ---------------------------------------------------------
    CATEGORY_SOURCE_TEXT_FIELD_CANDIDATES = (
        "name",
        "source_name",
        "category_name",
        "source_category_name",
        "normalized_name",
        "canonical_name",
        "english_name",
        "slug",
    )

    def __init__(self):
        self.term_lookup: set[str] = set()
        self.brand_lookup: set[str] = set()

        self.category_lookup: set[str] = set()
        self.category_source_lookup: set[str] = set()

        self.reload()

    # =========================================================
    # NORMALIZE
    # =========================================================

    @staticmethod
    def normalize(
        value: str | None,
    ) -> str:
        if value is None:
            return ""

        text = str(value).lower().strip()

        if not text:
            return ""

        # underscore / hyphen은 의미 경계로 취급
        text = (
            text
            .replace("_", " ")
            .replace("-", " ")
        )

        # 문자/숫자/한글/공백 외 제거
        text = re.sub(
            r"[^\w가-힣\s]",
            " ",
            text,
        )

        # 중복 공백 정리
        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    # =========================================================
    # MODEL FIELD UTIL
    # =========================================================

    @classmethod
    def _model_text_fields(
        cls,
        model,
        *,
        candidates: tuple[str, ...] | None = None,
    ) -> list[str]:
        """
        모델에 실제 존재하는 텍스트 후보 필드만 반환.
        """

        candidates = (
            candidates
            or cls.TEXT_FIELD_CANDIDATES
        )

        available = {
            field.name
            for field in model._meta.fields
        }

        return [
            field_name
            for field_name in candidates
            if field_name in available
        ]

    @classmethod
    def _load_model_texts(
        cls,
        model,
        *,
        candidates: tuple[str, ...] | None = None,
    ) -> set[str]:
        """
        모델의 텍스트 필드를 읽어서 normalized lookup 생성.
        """

        fields = cls._model_text_fields(
            model,
            candidates=candidates,
        )

        if not fields:
            return set()

        result: set[str] = set()

        queryset = (
            model.objects
            .all()
            .values(*fields)
        )

        for row in queryset.iterator(
            chunk_size=1000,
        ):
            for value in row.values():
                normalized = cls.normalize(value)

                if normalized:
                    result.add(normalized)

        return result

    # =========================================================
    # LOAD
    # =========================================================

    def reload(self) -> None:
        """
        DB의 현재 Dictionary / Brand / Category 정보를
        메모리 lookup으로 다시 적재한다.
        """

        # -----------------------------------------------------
        # DictionaryTerm
        # -----------------------------------------------------

        term_values = (
            DictionaryTerm.objects
            .filter(status="ACTIVE")
            .exclude(
                normalized_name__isnull=True,
            )
            .exclude(
                normalized_name="",
            )
            .values_list(
                "normalized_name",
                flat=True,
            )
        )

        # -----------------------------------------------------
        # TermAlias
        # -----------------------------------------------------

        alias_values = (
            TermAlias.objects
            .filter(
                term__status="ACTIVE",
            )
            .exclude(
                normalized_alias__isnull=True,
            )
            .exclude(
                normalized_alias="",
            )
            .values_list(
                "normalized_alias",
                flat=True,
            )
        )

        self.term_lookup = {
            normalized
            for value in (
                list(term_values)
                + list(alias_values)
            )
            if value
            if (
                normalized := self.normalize(
                    value
                )
            )
        }

        # -----------------------------------------------------
        # Brand
        # -----------------------------------------------------

        self.brand_lookup = (
            self._load_model_texts(
                Brand,
            )
        )

        # -----------------------------------------------------
        # Canonical Category
        # -----------------------------------------------------

        self.category_lookup = (
            self._load_model_texts(
                Category,
            )
        )

        # -----------------------------------------------------
        # Source Category
        #
        # 무신사 / 지그재그 / 에이블리 등의 원본 카테고리 표현.
        # -----------------------------------------------------

        self.category_source_lookup = (
            self._load_model_texts(
                CategorySource,
                candidates=(
                    self
                    .CATEGORY_SOURCE_TEXT_FIELD_CANDIDATES
                ),
            )
        )

        # 최종 CATEGORY lookup
        self.category_lookup |= (
            self.category_source_lookup
        )

    # =========================================================
    # ROLE
    # =========================================================

    def role_of(
        self,
        value: str | None,
    ) -> str | None:
        normalized = self.normalize(value)

        if not normalized:
            return None

        # -----------------------------------------------------
        # 1. Dictionary가 최우선
        #
        # 봄/여름/가을/겨울처럼 CategorySource와 겹치더라도
        # DictionaryTerm이면 기존 패션 개념으로 처리.
        # -----------------------------------------------------

        if normalized in self.term_lookup:
            return "KNOWN_TERM"

        # -----------------------------------------------------
        # 2. Brand
        # -----------------------------------------------------

        if normalized in self.brand_lookup:
            return "BRAND"

        # -----------------------------------------------------
        # 3. Category + CategorySource
        # -----------------------------------------------------

        if normalized in self.category_lookup:
            return "CATEGORY"

        return None

    # =========================================================
    # HELPERS
    # =========================================================

    def is_dictionary_known(
        self,
        value: str | None,
    ) -> bool:
        return (
            self.role_of(value)
            == "KNOWN_TERM"
        )

    def is_brand(
        self,
        value: str | None,
    ) -> bool:
        return (
            self.role_of(value)
            == "BRAND"
        )

    def is_category(
        self,
        value: str | None,
    ) -> bool:
        return (
            self.role_of(value)
            == "CATEGORY"
        )

    def is_known(
        self,
        value: str | None,
    ) -> bool:
        return (
            self.role_of(value)
            is not None
        )

    # =========================================================
    # DEBUG
    # =========================================================

    def stats(self) -> dict:
        return {
            "dictionary": len(
                self.term_lookup
            ),
            "brand": len(
                self.brand_lookup
            ),
            "category_total": len(
                self.category_lookup
            ),
            "category_source": len(
                self.category_source_lookup
            ),
        }


# ============================================================
# COMPOUND RESOLUTION
# ============================================================

import re
from dataclasses import dataclass

from apps.core.models import DiscoveryExclusion

@dataclass(frozen=True)
class Part:
    text: str
    role: str
    exclusion_reason: str | None = None


@dataclass
class CompoundResult:
    is_compound: bool
    label: str
    parts: list[Part]
    reason: str | None = None

    @property
    def unknown_parts(self) -> list[Part]:
        return [p for p in self.parts if p.role == "UNKNOWN"]

    @property
    def known_parts(self) -> list[Part]:
        return [p for p in self.parts if p.role != "UNKNOWN"]


class CompoundResolver:
    """
    FEEDIT Compound Resolver v6 - conservative

    핵심:
    1) 구분자(/, &, _, × 등)는 먼저 경계로 보존한다.
    2) 붙여쓰기 compound는 prefix/suffix 2-way split만 허용한다.
    3) 1글자/너무 짧은 KNOWN/BRAND anchor는 금지한다.
    4) ss/fw 같은 짧은 시즌 코드는 문자열 내부 anchor로 쓰지 않는다.
    5) 숫자/모델번호/연도성 표현은 PRODUCT_META로 처리한다.
    6) UNKNOWN remainder가 1글자면 억지 분해하지 않는다.

    목적은 "최대한 많이 쪼개기"가 아니라
    "확실한 경우만 분해하기"다.
    """

    # slash/list separators. Hyphen is intentionally excluded because
    # it may be part of an English fashion expression.
    SEPARATOR_RE = re.compile(r"[\/_|,&+×·•;:()\[\]{}]+")

    EXCLUSION_ROLE_MAP = {
        "GENERIC": "GENERIC",
        "GENDER": "METADATA_GENDER",
        "CATEGORY": "CATEGORY",
        "PRODUCT_META": "PRODUCT_META",
        "MARKETING": "MARKETING",
        "SEASON": "METADATA_SEASON",
        "OTHER": "EXCLUSION",
    }

    FALLBACK = {
        "여성": "METADATA_GENDER",
        "여자": "METADATA_GENDER",
        "남성": "METADATA_GENDER",
        "남자": "METADATA_GENDER",
        "공용": "METADATA_GENDER",
        "유니섹스": "METADATA_GENDER",

        "봄": "METADATA_SEASON",
        "여름": "METADATA_SEASON",
        "가을": "METADATA_SEASON",
        "겨울": "METADATA_SEASON",
        "간절기": "METADATA_SEASON",

        "추천": "INTENT",
        "코디": "INTENT",
        "선물": "INTENT",

        "쿠폰": "COMMERCE",
        "배송": "COMMERCE",
        "무료배송": "COMMERCE",

        "단독": "MARKETING",
        "한정": "MARKETING",
        "특가": "MARKETING",
        "할인": "MARKETING",
    }

    # These can be atomic tokens, but must never become substring anchors.
    SHORT_META_TOKENS = {
        "ss",
        "fw",
        "s/s",
        "f/w",
    }

    def __init__(
        self,
        dictionary_guard: DictionaryGuard | None = None,
    ):
        self.guard = dictionary_guard or DictionaryGuard()
        self.global_exclusions: dict[str, str] = {}
        self.source_exclusions: dict[int, dict[str, str]] = {}
        self.reload_exclusions()

    # =========================================================
    # EXCLUSION
    # =========================================================

    def reload_exclusions(self) -> None:
        self.global_exclusions.clear()
        self.source_exclusions.clear()

        rows = (
            DiscoveryExclusion.objects
            .filter(is_active=True)
            .only("normalized_term", "reason", "source_id")
        )

        for row in rows.iterator(chunk_size=1000):
            term = self.guard.normalize(row.normalized_term)
            if not term:
                continue

            if row.source_id is None:
                self.global_exclusions[term] = row.reason
            else:
                self.source_exclusions.setdefault(
                    row.source_id, {}
                )[term] = row.reason

    def _exclusion_reason(
        self,
        normalized: str,
        *,
        source_id: int | None = None,
    ) -> str | None:
        if source_id is not None:
            reason = self.source_exclusions.get(
                source_id, {}
            ).get(normalized)
            if reason:
                return reason

        return self.global_exclusions.get(normalized)

    # =========================================================
    # BASIC CLASSIFICATION
    # =========================================================

    @staticmethod
    def _looks_like_product_meta(text: str) -> bool:
        """
        모델번호 / 연도코드 / 숫자성 fragment 방어.
        """
        compact = re.sub(r"\s+", "", text.lower())

        if not compact:
            return False

        # pure digits: 26, 808, 1911, 597 ...
        if compact.isdigit():
            return True

        # 26wt, 26fw, 2026ss, 8홀, 6인치 등
        if re.fullmatch(r"\d{1,4}[a-z가-힣]{1,6}", compact):
            return True

        # letters+digits or digits+letters model-like token
        if (
            re.search(r"\d", compact)
            and re.search(r"[a-z가-힣]", compact)
            and len(compact) <= 10
        ):
            return True

        return False

    def _atomic_part(
        self,
        text: str,
        *,
        source_id: int | None = None,
    ) -> Part | None:
        normalized = self.guard.normalize(text)
        if not normalized:
            return None

        # 1. Dictionary/Alias/Brand/Category
        role = self.guard.role_of(normalized)
        if role:
            return Part(text=text, role=role)

        # 2. DiscoveryExclusion
        reason = self._exclusion_reason(
            normalized,
            source_id=source_id,
        )
        if reason:
            return Part(
                text=text,
                role=self.EXCLUSION_ROLE_MAP.get(
                    reason, "EXCLUSION"
                ),
                exclusion_reason=reason,
            )

        # 3. Pattern metadata
        if self._looks_like_product_meta(normalized):
            return Part(
                text=text,
                role="PRODUCT_META",
            )

        # 4. Fallback role lexicon
        fallback = self.FALLBACK.get(normalized)
        if fallback:
            return Part(text=text, role=fallback)

        # 5. short season codes are only atomic exact tokens
        if normalized in self.SHORT_META_TOKENS:
            return Part(
                text=text,
                role="METADATA_SEASON",
            )

        return None

    # =========================================================
    # ANCHOR SAFETY
    # =========================================================

    def _safe_anchor(
        self,
        text: str,
        part: Part,
    ) -> bool:
        normalized = self.guard.normalize(text).replace(" ", "")

        if not normalized:
            return False

        # ss/fw may be exact atomic tokens, not substring anchors.
        if normalized in self.SHORT_META_TOKENS:
            return False

        # one-character anchors are forbidden.
        if len(normalized) < 2:
            return False

        # English anchors shorter than 3 chars are too dangerous:
        # ee(BRAND), ss(SEASON), etc.
        if re.fullmatch(r"[a-z]+", normalized) and len(normalized) < 3:
            return False

        # Numeric / product meta must not be segmentation anchors.
        if part.role == "PRODUCT_META":
            return False

        return True

    @staticmethod
    def _valid_unknown_remainder(text: str) -> bool:
        """
        UNKNOWN piece가 candidate로서 최소 형태를 갖는지.
        """
        compact = re.sub(r"\s+", "", text)

        if len(compact) < 2:
            return False

        # pure numeric should not become candidate.
        if compact.isdigit():
            return False

        return True

    # =========================================================
    # SEGMENT
    # =========================================================

    def _resolve_segment(
        self,
        segment: str,
        *,
        source_id: int | None = None,
    ) -> list[Part]:
        normalized = self.guard.normalize(segment)
        compact = normalized.replace(" ", "")

        if not compact:
            return []

        # Whole segment known first.
        whole = self._atomic_part(
            compact,
            source_id=source_id,
        )
        if whole is not None:
            return [whole]

        # Conservative 2-way split only.
        candidates: list[
            tuple[
                tuple[int, int, int],
                list[Part],
            ]
        ] = []

        for i in range(1, len(compact)):
            left = compact[:i]
            right = compact[i:]

            left_part = self._atomic_part(
                left,
                source_id=source_id,
            )
            right_part = self._atomic_part(
                right,
                source_id=source_id,
            )

            # KNOWN + KNOWN
            if (
                left_part is not None
                and right_part is not None
                and self._safe_anchor(left, left_part)
                and self._safe_anchor(right, right_part)
            ):
                candidates.append(
                    (
                        (0, 2, -min(len(left), len(right))),
                        [left_part, right_part],
                    )
                )
                continue

            # KNOWN + UNKNOWN
            if (
                left_part is not None
                and self._safe_anchor(left, left_part)
                and right_part is None
                and self._valid_unknown_remainder(right)
            ):
                candidates.append(
                    (
                        (len(right), 1, -len(left)),
                        [
                            left_part,
                            Part(right, "UNKNOWN"),
                        ],
                    )
                )
                continue

            # UNKNOWN + KNOWN
            if (
                right_part is not None
                and self._safe_anchor(right, right_part)
                and left_part is None
                and self._valid_unknown_remainder(left)
            ):
                candidates.append(
                    (
                        (len(left), 1, -len(right)),
                        [
                            Part(left, "UNKNOWN"),
                            right_part,
                        ],
                    )
                )

        if not candidates:
            # no safe split: keep whole expression as UNKNOWN.
            return [
                Part(
                    text=compact,
                    role="UNKNOWN",
                )
            ]

        # less unknown chars -> fewer unknown parts -> longer anchor
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    # =========================================================
    # PUBLIC
    # =========================================================

    def resolve(
        self,
        text: str,
        *,
        source_id: int | None = None,
    ) -> CompoundResult:
        raw = str(text or "").strip()

        if not raw:
            return CompoundResult(
                is_compound=False,
                label="NOT_COMPOUND",
                parts=[],
            )

        # IMPORTANT: preserve list boundaries instead of deleting them.
        segments = [
            seg.strip()
            for seg in self.SEPARATOR_RE.split(raw)
            if seg.strip()
        ]

        if not segments:
            segments = [raw]

        parts: list[Part] = []

        for segment in segments:
            parts.extend(
                self._resolve_segment(
                    segment,
                    source_id=source_id,
                )
            )

        # Single unresolved atomic expression = not a compound.
        if (
            len(parts) == 1
            and parts[0].role == "UNKNOWN"
        ):
            return CompoundResult(
                is_compound=False,
                label="NOT_COMPOUND",
                parts=parts,
                reason=f"{parts[0].text}(UNKNOWN)",
            )

        # Single known expression = atomic known.
        if len(parts) == 1:
            part = parts[0]
            return CompoundResult(
                is_compound=False,
                label="ATOMIC_KNOWN",
                parts=parts,
                reason=f"{part.text}({part.role})",
            )

        # If a separator list contains only unrelated UNKNOWN items,
        # don't pretend it is a meaningful compound.
        if all(p.role == "UNKNOWN" for p in parts):
            return CompoundResult(
                is_compound=False,
                label="NOT_COMPOUND",
                parts=parts,
                reason=" + ".join(
                    f"{p.text}(UNKNOWN)"
                    for p in parts
                ),
            )

        reason = " + ".join(
            (
                f"{p.text}({p.role}"
                + (
                    f":{p.exclusion_reason}"
                    if p.exclusion_reason
                    else ""
                )
                + ")"
            )
            for p in parts
        )

        return CompoundResult(
            is_compound=True,
            label="COMPONENT",
            parts=parts,
            reason=reason,
        )
