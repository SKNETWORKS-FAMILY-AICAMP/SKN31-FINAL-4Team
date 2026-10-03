from __future__ import annotations

from datetime import date, timedelta
from django.db import transaction

from apps.core.models import TermMetricDaily
from .config import METRIC_VERSION
from .reaction import apply_reaction_metrics
from .commerce import apply_commerce_metrics
from .content import apply_content_metrics
from .normalize import normalize_source_signals
from .scoring import calculate_axis_scores
from .aggregate import aggregate_all_sources
from .search_bridge import attach_search_to_all, apply_search_to_all_axes
from .temporal import compute_temporal_metrics
from .coverage import attach_coverage


@transaction.atomic
def run_term_metric_pipeline(metric_date: date, *, metric_version: str = METRIC_VERSION,
                             reaction: bool = True, commerce: bool = True,
                             content: bool = True, search: bool = True) -> dict:
    """Raw facts -> rolling normalization -> source axes -> ALL -> monthly search -> temporal -> coverage."""
    TermMetricDaily.objects.filter(metric_date=metric_date, metric_version=metric_version).delete()
    result = {"metric_date": str(metric_date), "metric_version": metric_version}
    result["reaction"] = apply_reaction_metrics(metric_date=metric_date, metric_version=metric_version) if reaction else {"skipped": True}
    result["commerce"] = apply_commerce_metrics(metric_date=metric_date, metric_version=metric_version) if commerce else {"skipped": True}
    result["content"] = apply_content_metrics(metric_date=metric_date, metric_version=metric_version) if content else {"skipped": True}
    result["normalize"] = normalize_source_signals(metric_date, metric_version=metric_version)
    result["scoring"] = calculate_axis_scores(metric_date, metric_version=metric_version)
    result["all_sources"] = aggregate_all_sources(metric_date, metric_version=metric_version)
    if search:
        result["search"] = attach_search_to_all(metric_date, metric_version=metric_version)
        result["search_axes"] = apply_search_to_all_axes(metric_date, metric_version=metric_version)
    else:
        result["search"] = {"skipped": True}
    result["temporal"] = compute_temporal_metrics(metric_date, metric_version=metric_version)
    result["coverage"] = attach_coverage(metric_date, metric_version=metric_version)
    return result


def run_term_metric_range(start_date: date, end_date: date, *, metric_version: str = METRIC_VERSION,
                          reaction: bool = True, commerce: bool = True, content: bool = True,
                          search: bool = True):
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")
    results = []
    current = start_date
    while current <= end_date:
        results.append(run_term_metric_pipeline(
            current, metric_version=metric_version, reaction=reaction,
            commerce=commerce, content=content, search=search,
        ))
        current += timedelta(days=1)
    return results
