# backend/analysis/ocr/aggregator.py

from __future__ import annotations

from collections import defaultdict


class AttributeEvidenceAggregator:

    def aggregate(
        self,
        evidences: list[dict],
    ) -> dict[str, list[dict]]:

        grouped = defaultdict(list)

        seen = set()

        for evidence in evidences:

            attribute = evidence[
                "attribute"
            ]

            text = evidence[
                "text"
            ].strip()

            dedupe_key = (
                attribute,
                text.lower(),
            )

            if dedupe_key in seen:
                continue

            seen.add(
                dedupe_key
            )

            grouped[
                attribute
            ].append(
                evidence
            )

        # 높은 score 우선
        for attribute in grouped:

            grouped[
                attribute
            ].sort(
                key=lambda item: (
                    item.get(
                        "score",
                        0,
                    )
                ),
                reverse=True,
            )

        return dict(grouped)