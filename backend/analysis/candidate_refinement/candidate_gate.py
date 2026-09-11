from __future__ import annotations

from collections import defaultdict

from apps.core.models import ProductSource

from .dictionary_guard import DictionaryGuard
from .structural_filter import StructuralFilter
from .termhood_scorer import TermhoodScorer


class CandidateGate:
    ALLOWED_SOURCES = {
        "ORIGINAL",
        "WHITESPACE",
        "UNKNOWN_SURFACE",
        None,
        "",
    }

    def __init__(
        self,
        *,
        min_document_frequency: int = 3,
    ):
        self.dictionary_guard = DictionaryGuard()
        self.structural_filter = StructuralFilter()
        self.scorer = TermhoodScorer(
            min_document_frequency=min_document_frequency
        )

    def build(self, queryset=None) -> dict:
        if queryset is None:
            queryset = (
                ProductSource.objects
                .exclude(normalized_name__isnull=True)
                .exclude(normalized_name="")
                .select_related("source")
                .order_by("id")
            )

        stats = defaultdict(
            lambda: {
                "raw_terms": defaultdict(int),
                "product_ids": set(),
                "source_ids": set(),
                "observation_count": 0,
                "fashion_context_hits": 0,
                "product_observation_counts": defaultdict(int),
                "observations": [],
            }
        )

        for product in queryset.iterator(chunk_size=500):
            attrs = (
                product.attributes
                if isinstance(product.attributes, dict)
                else {}
            )

            analysis = attrs.get("feedit_analysis")
            if not isinstance(analysis, dict):
                continue

            known_context_keys = set()

            for row in analysis.get("known_evidence") or []:
                known_context_keys.add(
                    (
                        row.get("source_field"),
                        row.get("source_index"),
                    )
                )

            for row in analysis.get("unknown_evidence") or []:
                candidate_source = row.get("candidate_source")

                if candidate_source not in self.ALLOWED_SOURCES:
                    continue

                raw_term = str(row.get("text") or "").strip()
                if not raw_term:
                    continue

                normalized = self.dictionary_guard.normalize(
                    raw_term
                )

                if not normalized:
                    continue

                # Dictionary / Alias / Brand / Category 모두 차단
                if self.dictionary_guard.is_known(normalized):
                    continue

                passed, _ = self.structural_filter.check(
                    normalized
                )
                if not passed:
                    continue

                stat = stats[normalized]
                stat["raw_terms"][raw_term] += 1
                stat["product_ids"].add(product.id)

                source_id = getattr(product, "source_id", None)
                if source_id is not None:
                    stat["source_ids"].add(source_id)

                stat["observation_count"] += 1
                stat["product_observation_counts"][
                    product.id
                ] += 1

                context_key = (
                    row.get("source_field"),
                    row.get("source_index"),
                )

                if context_key in known_context_keys:
                    stat["fashion_context_hits"] += 1

                stat["observations"].append({
                    "product_source_id": product.id,
                    "source_id": source_id,
                    "source_field": row.get("source_field"),
                    "source_index": row.get("source_index"),
                    "source_text": row.get("source_text"),
                    "candidate_source": candidate_source,
                })

        output = {}

        for normalized, stat in stats.items():
            document_frequency = len(stat["product_ids"])
            observation_count = stat["observation_count"]
            source_diversity = len(stat["source_ids"])

            fashion_context_ratio = (
                stat["fashion_context_hits"] / observation_count
                if observation_count
                else 0.0
            )

            max_product_obs = max(
                stat["product_observation_counts"].values(),
                default=0,
            )

            concentration = (
                max_product_obs / observation_count
                if observation_count
                else 1.0
            )

            result = self.scorer.score(
                document_frequency=document_frequency,
                observation_count=observation_count,
                source_diversity=source_diversity,
                fashion_context_ratio=fashion_context_ratio,
                concentration=concentration,
            )

            raw_term = max(
                stat["raw_terms"],
                key=stat["raw_terms"].get,
            )

            output[normalized] = {
                "raw_term": raw_term,
                "normalized_term": normalized,
                "score": result.score,
                "decision": result.decision,
                "reason": result.reason,
                "features": result.features,
                "observations": stat["observations"],
            }

        return output
