from __future__ import annotations

from datetime import date
from .associations import build_term_associations
from .config import METRIC_VERSION
from .pipeline import run_term_metric_pipeline, run_term_metric_range
from .validator import validate_term_metrics


def run_daily_metrics(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
    associations: bool = True,
    validate: bool = True,
):
    result = run_term_metric_pipeline(metric_date, metric_version=metric_version)
    if associations:
        result["associations"] = build_term_associations(
            metric_date, metric_version=metric_version
        )
    if validate:
        result["validation"] = validate_term_metrics(
            metric_date, metric_version=metric_version
        )
    return result


__all__ = ["run_daily_metrics", "run_term_metric_pipeline", "run_term_metric_range"]
