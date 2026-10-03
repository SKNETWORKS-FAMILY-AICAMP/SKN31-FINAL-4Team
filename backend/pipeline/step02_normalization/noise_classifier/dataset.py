from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from apps.core.models import ProductSource

from pipeline.step02_normalization import (
    ProductNormalizationPipeline,
)


SUPPORTED_SOURCES = (
    "zigzag",
    "ABLY",
    "musinsa",
)


@dataclass
class CandidateStat:
    text: str
    count: int = 0
    source_counts: Counter = field(
        default_factory=Counter
    )
    examples: list[dict] = field(
        default_factory=list
    )


class NoiseDatasetBuilder:
    """
    FEEDIT Noise Classifier 학습 후보 생성기.

    대상 플랫폼:
    - zigzag
    - ABLY
    - musinsa

    classifier가 해결할 대상:
    - MARKETING
    - ATTRIBUTE_CANDIDATE
    - KEEP

    Structural에서 해결할 표현은 학습 대상에서 제외한다.
    """

    def __init__(
        self,
        *,
        sources: tuple[str, ...] = SUPPORTED_SOURCES,
    ):
        self.sources = sources

    # ========================================================
    # 전체 수집
    # ========================================================

    def collect(
        self,
        *,
        per_source_limit: int | None = None,
        min_count: int = 1,
        example_limit: int = 5,
    ) -> list[CandidateStat]:

        stats: dict[str, CandidateStat] = {}

        for source_code in self.sources:

            print()
            print("=" * 100)
            print("SOURCE:", source_code)
            print("=" * 100)

            self._collect_source(
                source_code=source_code,
                stats=stats,
                limit=per_source_limit,
                example_limit=example_limit,
            )

        rows = [
            row
            for row in stats.values()
            if row.count >= min_count
        ]

        rows.sort(
            key=lambda row: (
                -row.count,
                row.text,
            )
        )

        return rows

    # ========================================================
    # 플랫폼별 수집
    # ========================================================

    def _collect_source(
        self,
        *,
        source_code: str,
        stats: dict[str, CandidateStat],
        limit: int | None,
        example_limit: int,
    ) -> None:

        pipeline = ProductNormalizationPipeline(
            source_code=source_code,
        )

        queryset = (
            ProductSource.objects
            .filter(
                source__code__iexact=source_code,
            )
            .select_related("source")
            .order_by("id")
        )

        if limit is not None:
            queryset = queryset[:limit]

        rows = list(queryset)

        total = len(rows)

        print(
            "상품 수:",
            total,
        )

        success = 0
        failed = 0

        for index, product_source in enumerate(
            rows,
            start=1,
        ):
            try:
                result = pipeline.run(
                    product_source
                )

                candidates = (
                    self._extract_candidates(
                        result
                    )
                )

                raw_name = str(
                    product_source.source_name
                    or ""
                ).strip()

                for candidate in candidates:

                    text = self._normalize_text(
                        candidate
                    )

                    if not text:
                        continue

                    stat = stats.get(text)

                    if stat is None:
                        stat = CandidateStat(
                            text=text,
                        )
                        stats[text] = stat

                    stat.count += 1

                    stat.source_counts[
                        source_code.lower()
                    ] += 1

                    if (
                        len(stat.examples)
                        < example_limit
                    ):
                        example_key = (
                            source_code.lower(),
                            product_source.id,
                        )

                        existing_keys = {
                            (
                                row["source_code"],
                                row["product_source_id"],
                            )
                            for row in stat.examples
                        }

                        if (
                            example_key
                            not in existing_keys
                        ):
                            stat.examples.append(
                                {
                                    "source_code": (
                                        source_code.lower()
                                    ),
                                    "product_source_id": (
                                        product_source.id
                                    ),
                                    "source_name": raw_name,
                                }
                            )

                success += 1

            except Exception as exc:
                failed += 1

                print(
                    f"FAILED #{product_source.id} "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

            if (
                index % 100 == 0
                or index == total
            ):
                print(
                    f"[{index}/{total}] "
                    f"성공={success} "
                    f"실패={failed} "
                    f"누적후보={len(stats)}"
                )

    # ========================================================
    # STEP02 결과 -> 후보
    # ========================================================

    @staticmethod
    def _extract_candidates(
        result: dict,
    ) -> set[str]:

        candidates: set[str] = set()

        # ----------------------------------------------------
        # Semantic UNKNOWN
        # ----------------------------------------------------

        for row in (
            result.get("unknown_terms")
            or []
        ):
            if isinstance(row, str):
                value = row

            elif isinstance(row, dict):
                value = (
                    row.get("text")
                    or row.get("surface")
                    or ""
                )

            else:
                continue

            value = str(
                value or ""
            ).strip()

            if value:
                candidates.add(value)

        # ----------------------------------------------------
        # Residual
        # ----------------------------------------------------

        residual = (
            result.get("residual_tags")
            or []
        )

        if isinstance(residual, dict):
            residual = (
                residual.get("tags")
                or residual.get("items")
                or residual.get("unknown")
                or []
            )

        if isinstance(residual, str):
            residual = [residual]

        for row in residual:

            if isinstance(row, str):
                value = row

            elif isinstance(row, dict):
                value = (
                    row.get("text")
                    or row.get("surface")
                    or row.get("tag")
                    or ""
                )

            else:
                continue

            value = str(
                value or ""
            ).strip()

            if value:
                candidates.add(value)

        return candidates

    # ========================================================
    # Normalization
    # ========================================================

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:

        import re

        text = str(
            text or ""
        ).strip()

        text = " ".join(
            text.split()
        )

        # 영문 대소문자 통일
        text = text.lower()

        # 후보 양끝의 의미 없는 punctuation 제거
        text = re.sub(
            r"^[\s.,!?#*~_\-]+|[\s.,!?#*~_\-]+$",
            "",
            text,
        )

        if len(text) < 2:
            return ""

        return text

    # ========================================================
    # CSV
    # ========================================================

    @staticmethod
    def save_csv(
        rows: list[CandidateStat],
        path: str | Path,
    ) -> Path:

        path = Path(path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as f:

            writer = csv.writer(f)

            writer.writerow(
                [
                    "text",
                    "count",
                    "zigzag_count",
                    "ably_count",
                    "musinsa_count",
                    "label",
                    "example_1_source",
                    "example_1",
                    "example_2_source",
                    "example_2",
                    "example_3_source",
                    "example_3",
                ]
            )

            for row in rows:

                examples = (
                    row.examples
                    + [{}, {}, {}]
                )[:3]

                writer.writerow(
                    [
                        row.text,
                        row.count,
                        row.source_counts.get(
                            "zigzag",
                            0,
                        ),
                        row.source_counts.get(
                            "ably",
                            0,
                        ),
                        row.source_counts.get(
                            "musinsa",
                            0,
                        ),
                        "",
                        examples[0].get(
                            "source_code",
                            "",
                        ),
                        examples[0].get(
                            "source_name",
                            "",
                        ),
                        examples[1].get(
                            "source_code",
                            "",
                        ),
                        examples[1].get(
                            "source_name",
                            "",
                        ),
                        examples[2].get(
                            "source_code",
                            "",
                        ),
                        examples[2].get(
                            "source_name",
                            "",
                        ),
                    ]
                )

        return path