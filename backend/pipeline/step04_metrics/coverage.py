from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.core.models import TermMetricDaily
from .common import merge_json
from .config import METRIC_VERSION


@transaction.atomic
def attach_coverage(metric_date: date, *, metric_version: str = METRIC_VERSION) -> dict:
    """
    Coverage is diagnostic confidence metadata only.
    It NEVER multiplies Level or Trend Temperature.
    """
    rows = list(
        TermMetricDaily.objects.filter(
            metric_date=metric_date,
            metric_version=metric_version,
        )
    )
    updated = 0

    for row in rows:
        if row.source_id is None:
            source_axes = ((row.metrics or {}).get("aggregate") or {}).get("source_axes") or {}
            source_coverage = len(source_axes)
            axes = ((row.metrics or {}).get("aggregate") or {}).get("axes") or {}
        else:
            source_coverage = 1
            axes = ((row.metrics or {}).get("scoring") or {}).get("axes") or {}

        available_axes = sum(value is not None for value in axes.values())
        row.metrics = merge_json(row.metrics, {
            "coverage": {
                "source_count": source_coverage,
                "available_axis_count": available_axes,
                "axis_count": 4,
                "axis_coverage_rate": round(available_axes / 4.0, 4),
                "affects_score": False,
            }
        })
        row.save(update_fields=["metrics", "updated_at"])
        updated += 1

    return {"updated": updated}
