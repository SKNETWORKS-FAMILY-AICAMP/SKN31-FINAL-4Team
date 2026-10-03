from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from apps.core.models import TermMetricDaily
from .common import available_weighted_mean, clamp, merge_json, momentum_score
from .config import LEVEL_WEIGHTS, METRIC_VERSION, TEMPERATURE_WEIGHTS


def _mean(values):
    values = [float(v) for v in values if v is not None]
    return sum(values) / len(values) if values else None


@transaction.atomic
def compute_temporal_metrics(metric_date: date, *, metric_version: str = METRIC_VERSION) -> dict:
    """
    Axis-first temporal calculation.

    MA7/MA28 DB columns remain the level moving averages for API compatibility.
    Axis MA/momentum is preserved in metrics.temporal.axes.
    Final momentum is the available-weight mean of axis momentums.
    """
    rows = list(
        TermMetricDaily.objects.filter(
            metric_date=metric_date,
            metric_version=metric_version,
        )
    )
    updated = 0
    start = metric_date - timedelta(days=27)

    for row in rows:
        history = list(
            TermMetricDaily.objects.filter(
                term_id=row.term_id,
                source_id=row.source_id,
                metric_version=metric_version,
                metric_date__gte=start,
                metric_date__lte=metric_date,
            ).order_by("metric_date")
        )

        level_values = [
            float(item.level) if item.level is not None else None
            for item in history
        ]
        # Calendar windows, not "last N existing rows". Missing dates remain missing
        # and are not silently converted to observed zero.
        last7_start = metric_date - timedelta(days=6)
        ma7 = _mean([
            float(item.level) if item.level is not None else None
            for item in history if item.metric_date >= last7_start
        ])
        ma28 = _mean(level_values)

        axis_temporal = {}
        axis_momentum = {}
        for axis in LEVEL_WEIGHTS:
            axis_values = [
                (((item.metrics or {}).get("scoring") or {}).get("axes") or {}).get(axis)
                if item.source_id is not None
                else (((item.metrics or {}).get("aggregate") or {}).get("axes") or {}).get(axis)
                for item in history
            ]
            dated_axis_values = list(zip([item.metric_date for item in history], axis_values))
            a7 = _mean([v for d, v in dated_axis_values if d >= last7_start])
            a28 = _mean(axis_values)
            mom = (
                round(momentum_score(a7, a28), 4)
                if a7 is not None and a28 is not None
                else None
            )
            axis_temporal[axis] = {"ma7": a7, "ma28": a28, "momentum": mom}
            axis_momentum[axis] = mom

        momentum = available_weighted_mean(axis_momentum, LEVEL_WEIGHTS)
        momentum = round(clamp(momentum), 4) if momentum is not None else None

        level = float(row.level) if row.level is not None else None
        temperature = available_weighted_mean(
            {"level": level, "momentum": momentum},
            TEMPERATURE_WEIGHTS,
        )
        temperature = round(clamp(temperature), 4) if temperature is not None else None

        row.ma7 = Decimal(str(round(ma7, 4))) if ma7 is not None else None
        row.ma28 = Decimal(str(round(ma28, 4))) if ma28 is not None else None
        row.momentum = Decimal(str(momentum)) if momentum is not None else None
        row.trend_temperature = Decimal(str(temperature)) if temperature is not None else None
        row.metrics = merge_json(row.metrics, {
            "temporal": {
                "axes": axis_temporal,
                "momentum": momentum,
                "trend_temperature": temperature,
                "temperature_weights": TEMPERATURE_WEIGHTS,
            }
        })
        row.save(update_fields=[
            "ma7", "ma28", "momentum", "trend_temperature", "metrics", "updated_at",
        ])
        updated += 1

    return {"updated": updated}
