from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.core.models import TermMetricDaily
from .common import available_weighted_mean, ensure_metric, merge_json
from .config import LEVEL_WEIGHTS, METRIC_VERSION


COUNT_FIELDS = (
    "mention_count", "document_count", "content_count", "creator_count",
    "positive_count", "neutral_count", "negative_count",
    "question_count", "purchase_count", "experience_count",
    "praise_count", "critique_count", "chitchat_count",
)


@transaction.atomic
def aggregate_all_sources(metric_date: date, *, metric_version: str = METRIC_VERSION) -> dict:
    """
    No SOURCE_WEIGHTS.

    Source volume differences have already been normalized inside each source.
    ALL combines only available source scores. Missing source/signal is NULL,
    never an implicit zero.
    """
    source_rows = list(
        TermMetricDaily.objects
        .filter(
            metric_date=metric_date,
            metric_version=metric_version,
            source__isnull=False,
        )
        .select_related("source", "term")
    )
    grouped = {}
    for row in source_rows:
        grouped.setdefault(row.term_id, []).append(row)

    saved = 0
    for _, rows in grouped.items():
        all_row = ensure_metric(
            term=rows[0].term,
            source=None,
            metric_date=metric_date,
            metric_version=metric_version,
        )

        for field in COUNT_FIELDS:
            if hasattr(all_row, field):
                setattr(all_row, field, sum(int(getattr(row, field, 0) or 0) for row in rows))

        # Recompute ALL reaction rates from summed counts, never average source rates.
        reaction_den = (
            int(getattr(all_row, "positive_count", 0) or 0)
            + int(getattr(all_row, "neutral_count", 0) or 0)
            + int(getattr(all_row, "negative_count", 0) or 0)
        )
        intent_den = sum(int(getattr(all_row, f, 0) or 0) for f in (
            "question_count", "purchase_count", "experience_count",
            "praise_count", "critique_count", "chitchat_count",
        ))
        for field, numerator, denominator in (
            ("positive_rate", getattr(all_row, "positive_count", 0), reaction_den),
            ("neutral_rate", getattr(all_row, "neutral_count", 0), reaction_den),
            ("negative_rate", getattr(all_row, "negative_count", 0), reaction_den),
            ("question_rate", getattr(all_row, "question_count", 0), intent_den),
            ("purchase_rate", getattr(all_row, "purchase_count", 0), intent_den),
            ("experience_rate", getattr(all_row, "experience_count", 0), intent_den),
            ("praise_rate", getattr(all_row, "praise_count", 0), intent_den),
            ("critique_rate", getattr(all_row, "critique_count", 0), intent_den),
        ):
            if hasattr(all_row, field):
                setattr(all_row, field, round(100.0 * float(numerator or 0) / denominator, 4) if denominator else None)

        source_axes = {}
        for row in rows:
            axes = ((row.metrics or {}).get("scoring") or {}).get("axes") or {}
            source_axes[row.source.code] = axes

        axes = {}
        for axis in LEVEL_WEIGHTS:
            values = [
                float(source_axes[code][axis])
                for code in source_axes
                if source_axes[code].get(axis) is not None
            ]
            axes[axis] = round(sum(values) / len(values), 4) if values else None

        level = available_weighted_mean(axes, LEVEL_WEIGHTS)
        level = round(level, 4) if level is not None else None

        all_row.level = Decimal(str(level)) if level is not None else None
        all_row.percentile = None
        all_row.metrics = merge_json(all_row.metrics, {
            "aggregate": {
                "method": "equal_available_source_mean",
                "source_weights": None,
                "source_axes": source_axes,
                "axes": axes,
                "level": level,
                "level_weights": LEVEL_WEIGHTS,
            }
        })
        all_row.save()
        saved += 1

    return {"saved": saved}
