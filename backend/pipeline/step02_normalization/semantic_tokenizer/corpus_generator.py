from __future__ import annotations

import re
import unicodedata

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.db import connection

from apps.core.models import (
    Brand,
    DictionaryTerm,
    TermRelation,
)
@dataclass
class CorpusStats:
    total_rows: int = 0
    written_rows: int = 0
    skipped_empty: int = 0
    skipped_duplicate: int = 0
    total_chars: int = 0
    max_length: int = 0

    # v2 diagnostics
    product_rows: int = 0
    dictionary_rows: int = 0
    compound_rows: int = 0
    brand_rows: int = 0

    @property
    def avg_length(self) -> float:
        if self.written_rows == 0:
            return 0.0
        return self.total_chars / self.written_rows

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "written_rows": self.written_rows,
            "skipped_empty": self.skipped_empty,
            "skipped_duplicate": self.skipped_duplicate,
            "total_chars": self.total_chars,
            "max_length": self.max_length,
            "avg_length": round(self.avg_length, 2),
            "product_rows": self.product_rows,
            "dictionary_rows": self.dictionary_rows,
            "compound_rows": self.compound_rows,
            "brand_rows": self.brand_rows,
        }


class FeedItCorpusGenerator:
    """
    FEEDIT SentencePiece 학습용 corpus generator.

    구성
    ----
    1. commerce.product_source.source_name 실제 상품명
    2. ACTIVE DictionaryTerm canonical_name 가중 반복
    3. ACTIVE TermAlias 가중 반복
    4. TermRelation을 가진 compound/reusable concept 추가 가중

    의도
    ----
    - 실제 커머스 상품명 분포는 그대로 학습한다.
    - FEEDIT 사전의 핵심 표현은 corpus에서 더 자주 보이게 한다.
    - 상품명은 deduplicate하지만 dictionary 가중 반복은 의도적으로 유지한다.
    - SentencePiece는 semantic authority가 아니라 UNKNOWN 보조 분절 품질을 높이는 용도다.
    """

    SPACE_RE = re.compile(r"\s+")
    CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
    BRACKET_RE = re.compile(r"[\[\]\(\)\{\}]")
    SEPARATOR_RE = re.compile(r"[|/+,·ㆍ]+")

    COMPOUND_RELATION_TYPES = {
        "BASE_ITEM",
        "HAS_ITEM",
        "HAS_ATTRIBUTE",
        "HAS_MATERIAL",
        "HAS_COLOR",
        "IS_A",
    }

    def __init__(
        self,
        *,
        output_path: str | Path,
        source_codes: list[str] | None = None,
        min_length: int = 2,
        deduplicate: bool = True,
        canonical_weight: int = 5,
        alias_weight: int = 3,
        compound_weight: int = 8,
        brand_weight: int = 6,
    ):
        self.output_path = Path(output_path)
        self.source_codes = [
            code.upper()
            for code in (source_codes or [])
        ]
        self.min_length = min_length
        self.deduplicate = deduplicate

        self.canonical_weight = max(1, int(canonical_weight))
        self.alias_weight = max(1, int(alias_weight))
        self.compound_weight = max(1, int(compound_weight))
        self.brand_weight = max(1, int(brand_weight))

    # ========================================================
    # NORMALIZATION
    # ========================================================

    def normalize_text(
        self,
        text: str | None,
    ) -> str:
        if not text:
            return ""

        text = unicodedata.normalize(
            "NFKC",
            str(text),
        )
        text = self.CONTROL_RE.sub(" ", text)
        text = self.BRACKET_RE.sub(" ", text)
        text = self.SEPARATOR_RE.sub(" ", text)
        text = text.replace("_", " ")
        text = self.SPACE_RE.sub(" ", text)

        return text.strip()

    # ========================================================
    # PRODUCT CORPUS
    # ========================================================

    def iter_product_names(
        self,
        *,
        limit: int | None = None,
    ) -> Iterable[str]:
        params: list = []

        sql = """
        SELECT ps.source_name
        FROM commerce.product_source ps
        JOIN collection.source s
          ON s.id = ps.source_id
        WHERE ps.source_name IS NOT NULL
          AND BTRIM(ps.source_name) <> ''
        """

        if self.source_codes:
            placeholders = ", ".join(
                ["%s"] * len(self.source_codes)
            )

            sql += f"""
            AND UPPER(s.code) IN ({placeholders})
            """

            params.extend(self.source_codes)

        sql += " ORDER BY ps.id "

        if limit is not None:
            sql += " LIMIT %s "
            params.append(limit)

        with connection.cursor() as cursor:
            cursor.execute(sql, params)

            while True:
                rows = cursor.fetchmany(2000)

                if not rows:
                    break

                for row in rows:
                    yield row[0]

    # ========================================================
    # DICTIONARY CORPUS
    # ========================================================

    def _compound_term_ids(self) -> set[int]:
        """
        TermRelation이 존재하는 reusable/compound concept 식별.

        예:
            반팔티셔츠 --BASE_ITEM--> 티셔츠
            반팔티셔츠 --HAS_ATTRIBUTE--> 반소매
        """

        return set(
            TermRelation.objects
            .filter(
                relation_type__in=self.COMPOUND_RELATION_TYPES,
                source_term__status=DictionaryTerm.Status.ACTIVE,
                target_term__status=DictionaryTerm.Status.ACTIVE,
            )
            .values_list(
                "source_term_id",
                flat=True,
            )
            .distinct()
        )

    def iter_dictionary_texts(
        self,
    ) -> Iterable[tuple[str, str]]:
        """
        (text, kind) 반환.

        kind:
            CANONICAL
            ALIAS
            COMPOUND_CANONICAL
            COMPOUND_ALIAS

        dictionary 텍스트는 generate()에서 의도적으로 반복 기록한다.
        """

        compound_ids = self._compound_term_ids()

        terms = (
            DictionaryTerm.objects
            .filter(
                status=DictionaryTerm.Status.ACTIVE,
            )
            .prefetch_related("aliases")
            .order_by("id")
        )

        for term in terms:
            canonical = (
                term.canonical_name or ""
            ).strip()

            is_compound = term.id in compound_ids

            if canonical:
                yield (
                    canonical,
                    (
                        "COMPOUND_CANONICAL"
                        if is_compound
                        else "CANONICAL"
                    ),
                )

            for alias_obj in term.aliases.all():
                alias = (
                    alias_obj.alias or ""
                ).strip()

                if not alias:
                    continue

                yield (
                    alias,
                    (
                        "COMPOUND_ALIAS"
                        if is_compound
                        else "ALIAS"
                    ),
                )

    def _dictionary_weight(
        self,
        kind: str,
    ) -> int:
        if kind == "COMPOUND_CANONICAL":
            return self.compound_weight

        if kind == "COMPOUND_ALIAS":
            return max(
                self.alias_weight,
                self.compound_weight - 2,
            )

        if kind == "CANONICAL":
            return self.canonical_weight

        return self.alias_weight

    # ========================================================
    # BRAND CORPUS
    # ========================================================

    def iter_brand_texts(self) -> Iterable[str]:
        """
        Brand의 자연어 이름만 학습 corpus에 추가한다.

        포함:
        - Brand.name
        - Brand.english_name
        - 연결된 BrandSource.name / english_name

        제외:
        - source_brand_id 같은 내부 식별자
        - 리뷰 본문
        - 상품 attributes JSON 전체

        브랜드 의미 판정은 여전히 Dictionary exact matcher가 authority이고,
        SentencePiece에는 UNKNOWN 분절 품질을 위한 보조 노출만 제공한다.
        """
        qs = Brand.objects.all().order_by("id")
        field_names = {f.name for f in Brand._meta.fields}
        if "status" in field_names:
            active = getattr(getattr(Brand, "Status", object), "ACTIVE", "ACTIVE")
            qs = qs.filter(status=active)

        seen = set()

        for brand in qs.iterator(chunk_size=1000):
            values = [
                getattr(brand, "name", None),
                getattr(brand, "english_name", None),
            ]

            for rel in Brand._meta.related_objects:
                model = getattr(rel, "related_model", None)
                if model is None or model.__name__ != "BrandSource":
                    continue
                manager = getattr(brand, rel.get_accessor_name(), None)
                if manager is None:
                    continue
                try:
                    rows = manager.all()
                except Exception:
                    continue
                for row in rows:
                    if getattr(row, "mapping_status", None) == "EXCLUDED":
                        continue
                    values.extend([
                        getattr(row, "name", None),
                        getattr(row, "english_name", None),
                    ])

            for value in values:
                text = self.normalize_text(value)
                if not text or len(text) < self.min_length:
                    continue
                key = text.casefold()
                if key in seen:
                    continue
                seen.add(key)
                yield text

    # ========================================================
    # WRITING
    # ========================================================

    def _write_line(
        self,
        *,
        file,
        text: str,
        stats: CorpusStats,
        kind: str,
    ) -> None:
        file.write(text + "\n")

        length = len(text)

        stats.written_rows += 1
        stats.total_chars += length
        stats.max_length = max(
            stats.max_length,
            length,
        )

        if kind == "PRODUCT":
            stats.product_rows += 1
        elif kind == "BRAND":
            stats.brand_rows += 1
        else:
            stats.dictionary_rows += 1

            if kind.startswith("COMPOUND_"):
                stats.compound_rows += 1

    # ========================================================
    # GENERATE
    # ========================================================

    def generate(
        self,
        *,
        limit: int | None = None,
        include_dictionary: bool = True,
    ) -> CorpusStats:
        stats = CorpusStats()

        # 상품명 dedupe 전용.
        # dictionary weighted corpus는 의도적으로 중복을 허용한다.
        seen_product_texts: set[str] = set()

        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.output_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            # ------------------------------------------------
            # 1. 실제 상품명
            # ------------------------------------------------
            for raw_text in self.iter_product_names(
                limit=limit,
            ):
                stats.total_rows += 1

                text = self.normalize_text(raw_text)

                if (
                    not text
                    or len(text) < self.min_length
                ):
                    stats.skipped_empty += 1
                    continue

                if self.deduplicate:
                    key = text.casefold()

                    if key in seen_product_texts:
                        stats.skipped_duplicate += 1
                        continue

                    seen_product_texts.add(key)

                self._write_line(
                    file=file,
                    text=text,
                    stats=stats,
                    kind="PRODUCT",
                )

            # ------------------------------------------------
            # 2. Dictionary weighted corpus
            # ------------------------------------------------
            if include_dictionary:
                for raw_text, kind in self.iter_dictionary_texts():
                    text = self.normalize_text(raw_text)

                    if (
                        not text
                        or len(text) < self.min_length
                    ):
                        continue

                    weight = self._dictionary_weight(kind)

                    # 중요:
                    # dictionary corpus는 반복 자체가 학습 weight 역할.
                    for _ in range(weight):
                        self._write_line(
                            file=file,
                            text=text,
                            stats=stats,
                            kind=kind,
                        )

            # ------------------------------------------------
            # 3. Brand / BrandSource 자연어 이름
            # ------------------------------------------------
            for brand_text in self.iter_brand_texts():
                for _ in range(self.brand_weight):
                    self._write_line(
                        file=file,
                        text=brand_text,
                        stats=stats,
                        kind="BRAND",
                    )

        return stats
