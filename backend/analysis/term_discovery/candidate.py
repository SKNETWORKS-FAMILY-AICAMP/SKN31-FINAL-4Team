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
class PreparedCandidate:
    raw_term: str
    normalized_term: str
    evidence: ProductUnknownEvidence

    def to_dict(self) -> dict:
        return {
            "raw_term": self.raw_term,
            "normalized_term": self.normalized_term,
            "product_source_id": (
                self.evidence.product_source_id
            ),
            "source_code": self.evidence.source_code,
            "source_field": self.evidence.source_field,
            "source_text": self.evidence.source_text,
            "candidate_source": (
                self.evidence.candidate_source
            ),
        }


class CandidateBuilder:
    """
    STEP 2 clean UNKNOWN
    -> load
    -> normalize
    -> shape filter
    -> dedupe
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
            attributes.get("feedit_analysis")
            or {}
        )
        rows = analysis.get("unknown_evidence") or []

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

        result = []

        for row in rows:
            if not isinstance(row, dict):
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
                    surface=row.get("surface"),
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
                    source_code=source_code,
                    source_object=source_obj,
                    reason=row.get("reason"),
                    tags=row.get("tags"),
                )
            )

        return result

    def prepare_products(
        self,
        product_sources,
    ) -> dict:
        evidences = []

        for product_source in product_sources:
            evidences.extend(
                self.load_product_unknowns(
                    product_source
                )
            )

        prepared = []
        dropped = []
        seen = set()

        for evidence in evidences:
            normalized = self.normalizer.normalize(
                evidence.text
            )

            check = self.filter.check(normalized)

            if not check["keep"]:
                dropped.append({
                    "text": evidence.text,
                    "normalized_term": normalized,
                    "reason": check["reason"],
                    "product_source_id": (
                        evidence.product_source_id
                    ),
                    "source_field": (
                        evidence.source_field
                    ),
                })
                continue

            key = (
                evidence.product_source_id,
                evidence.source_field,
                normalized,
            )

            if key in seen:
                continue

            seen.add(key)

            prepared.append(
                PreparedCandidate(
                    raw_term=evidence.text,
                    normalized_term=normalized,
                    evidence=evidence,
                )
            )

        return {
            "prepared": prepared,
            "dropped": dropped,
            "evidence_count": len(evidences),
        }
