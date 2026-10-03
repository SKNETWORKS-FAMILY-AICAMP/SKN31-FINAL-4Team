from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.core.models import TermMetricDaily
from .common import available_weighted_mean, clamp, merge_json
from .config import (
    AXIS_SIGNAL_WEIGHTS,
    LEVEL_WEIGHTS,
    METRIC_VERSION,
    REACTION_PRIOR_STRENGTH,
)


def _normalized_score(row, name):
    signal = (
        ((row.metrics or {}).get("normalization") or {})
        .get("signals", {})
        .get(name, {})
    )
    value = signal.get("score")
    return float(value) if value is not None else None


def _reaction_denominator(row):
    reaction = (row.metrics or {}).get("reaction") or {}
    return float(reaction.get("reaction_document_count") or 0)


def _empirical_bayes_rates(rows):
    """
    Shrink reaction rates toward the source/date cohort mean.
    This prevents 1/1 from becoming an unqualified 100-point intent signal.
    """
    specs = {
        "positive_rate_adjusted": "positive_count",
        "praise_rate_adjusted": "praise_count",
        "purchase_rate_adjusted": "purchase_count",
        "question_rate_adjusted": "question_count",
    }
    totals = {}
    total_den = sum(_reaction_denominator(row) for row in rows)

    for score_name, count_field in specs.items():
        total_num = sum(float(getattr(row, count_field, 0) or 0) for row in rows)
        prior = (total_num / total_den) if total_den > 0 else None
        totals[score_name] = prior

    result = {}
    for row in rows:
        denominator = _reaction_denominator(row)
        values = {}
        for score_name, count_field in specs.items():
            prior = totals[score_name]
            if prior is None or denominator <= 0:
                values[score_name] = None
                continue
            numerator = float(getattr(row, count_field, 0) or 0)
            adjusted = (
                numerator + prior * REACTION_PRIOR_STRENGTH
            ) / (
                denominator + REACTION_PRIOR_STRENGTH
            )
            values[score_name] = round(clamp(adjusted * 100.0), 4)
        result[row.id] = values
    return result


def _search_score(row):
    search = (row.metrics or {}).get("search") or {}
    for key in ("percentile", "score", "volume_percentile"):
        value = search.get(key)
        if value is not None:
            try:
                return clamp(float(value))
            except (TypeError, ValueError):
                pass
    return None


@transaction.atomic
def calculate_axis_scores(metric_date: date, *, metric_version: str = METRIC_VERSION) -> dict:
    updated = 0

    source_ids = (
        TermMetricDaily.objects
        .filter(metric_date=metric_date, metric_version=metric_version, source__isnull=False)
        .values_list("source_id", flat=True)
        .distinct()
    )

    for source_id in source_ids:
        rows = list(
            TermMetricDaily.objects.filter(
                metric_date=metric_date,
                metric_version=metric_version,
                source_id=source_id,
            )
        )
        adjusted_rates = _empirical_bayes_rates(rows)

        for row in rows:
            signals = {}
            normalization = (
                ((row.metrics or {}).get("normalization") or {})
                .get("signals", {})
            )
            for name, payload in normalization.items():
                signals[name] = payload.get("score")

            signals.update(adjusted_rates.get(row.id, {}))
            signals["search_volume"] = _search_score(row)

            axes = {}
            axis_coverage = {}
            for axis, weights in AXIS_SIGNAL_WEIGHTS.items():
                value = available_weighted_mean(signals, weights)
                axes[axis] = round(value, 4) if value is not None else None
                available = [name for name in weights if signals.get(name) is not None]
                axis_coverage[axis] = {
                    "available": available,
                    "available_weight": round(sum(weights[name] for name in available), 4),
                    "configured_weight": round(sum(weights.values()), 4),
                }

            level = available_weighted_mean(axes, LEVEL_WEIGHTS)
            level = round(clamp(level), 4) if level is not None else None

            row.level = Decimal(str(level)) if level is not None else None
            row.metrics = merge_json(row.metrics, {
                "scoring": {
                    "signals": signals,
                    "axes": axes,
                    "axis_coverage": axis_coverage,
                    "level": level,
                    "level_method": "available_weight_renormalized_mean",
                    "level_weights": LEVEL_WEIGHTS,
                    "reaction_prior_strength": REACTION_PRIOR_STRENGTH,
                }
            })
            row.save(update_fields=["level", "metrics", "updated_at"])
            updated += 1

    return {"updated": updated}
