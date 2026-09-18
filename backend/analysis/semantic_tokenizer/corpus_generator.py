from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.db import connection


@dataclass
class CorpusStats:
    total_rows: int = 0
    written_rows: int = 0
    skipped_empty: int = 0
    skipped_duplicate: int = 0
    total_chars: int = 0
    max_length: int = 0

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
        }


class FeedItCorpusGenerator:
    """FEEDIT tokenizer 학습용 corpus generator."""

    SPACE_RE = re.compile(r"\s+")
    CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
    BRACKET_RE = re.compile(r"[\[\]\(\)\{\}]")
    SEPARATOR_RE = re.compile(r"[|/+,·ㆍ]+")

    def __init__(
        self,
        *,
        output_path: str | Path,
        source_codes: list[str] | None = None,
        min_length: int = 2,
        deduplicate: bool = True,
    ):
        self.output_path = Path(output_path)
        self.source_codes = [
            code.upper()
            for code in (source_codes or [])
        ]
        self.min_length = min_length
        self.deduplicate = deduplicate

    def normalize_text(
        self,
        text: str | None,
    ) -> str:
        if not text:
            return ""

        text = unicodedata.normalize("NFKC", str(text))
        text = self.CONTROL_RE.sub(" ", text)
        text = self.BRACKET_RE.sub(" ", text)
        text = self.SEPARATOR_RE.sub(" ", text)
        text = text.replace("_", " ")
        text = self.SPACE_RE.sub(" ", text)

        return text.strip()

    def iter_product_names(
        self,
        *,
        limit: int | None = None,
    ) -> Iterable[str]:
        params = []

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

    def generate(
        self,
        *,
        limit: int | None = None,
    ) -> CorpusStats:
        stats = CorpusStats()
        seen: set[str] = set()

        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.output_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            for raw_text in self.iter_product_names(
                limit=limit
            ):
                stats.total_rows += 1

                text = self.normalize_text(raw_text)

                if not text or len(text) < self.min_length:
                    stats.skipped_empty += 1
                    continue

                if self.deduplicate:
                    if text in seen:
                        stats.skipped_duplicate += 1
                        continue
                    seen.add(text)

                file.write(text + "\n")

                length = len(text)
                stats.written_rows += 1
                stats.total_chars += length
                stats.max_length = max(
                    stats.max_length,
                    length,
                )

        return stats
