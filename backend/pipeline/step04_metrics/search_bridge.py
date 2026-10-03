from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.core.models import TermMetricDaily, TermSearchMetricMonthly
from .common import merge_json
from .config import METRIC_VERSION, SEARCH_METRIC_VERSION


@transaction.atomic
def attach_search_to_all(metric_date: date, *, metric_version: str = METRIC_VERSION,
                         search_metric_version: str = SEARCH_METRIC_VERSION) -> dict:
    """Attach monthly search as a separate normalized signal to existing ALL rows.

    Search is never added to daily raw counts. Google/Naver percentiles remain normalized
    in their own platform/month cohorts. Their available percentiles are averaged per term.
    """
    month = metric_date.replace(day=1)
    rows = TermSearchMetricMonthly.objects.filter(
        metric_month=month, metric_version=search_metric_version,
    ).select_related("source")

    by_term = {}
    for row in rows:
        item = by_term.setdefault(row.term_id, {})
        item[(row.source.code or "").lower()] = {
            "search_volume": int(row.search_volume or 0),
            "percentile": float(row.percentile) if row.percentile is not None else None,
        }

    updated = 0
    for metric in TermMetricDaily.objects.filter(
        metric_date=metric_date, metric_version=metric_version, source__isnull=True,
    ).iterator(chunk_size=500):
        platforms = by_term.get(metric.term_id)
        if not platforms:
            continue
        vals = [x["percentile"] for x in platforms.values() if x.get("percentile") is not None]
        score = round(sum(vals) / len(vals), 4) if vals else None
        metric.metrics = merge_json(metric.metrics, {"search": {
            "metric_month": str(month), "platforms": platforms, "score": score,
            "method": "mean_available_platform_month_percentile",
            "daily_raw_count_included": False,
        }})
        metric.save(update_fields=["metrics", "updated_at"])
        updated += 1
    return {"updated": updated, "metric_month": str(month)}

@transaction.atomic
def apply_search_to_all_axes(metric_date: date, *, metric_version: str = METRIC_VERSION) -> dict:
    """Blend attached monthly search percentile into ALL attention/intent axes."""
    from decimal import Decimal
    from .common import available_weighted_mean, clamp
    from .config import AXIS_SIGNAL_WEIGHTS, LEVEL_WEIGHTS

    updated = 0
    for row in TermMetricDaily.objects.filter(
        metric_date=metric_date, metric_version=metric_version, source__isnull=True,
    ):
        metrics = row.metrics or {}
        aggregate = metrics.get("aggregate") or {}
        base_axes = dict(aggregate.get("axes") or {})
        search = metrics.get("search") or {}
        score = search.get("score")
        try:
            score = clamp(float(score)) if score is not None else None
        except (TypeError, ValueError):
            score = None

        axes = dict(base_axes)
        if score is not None:
            for axis in ("attention", "intent"):
                weights = AXIS_SIGNAL_WEIGHTS.get(axis, {})
                sw = float(weights.get("search_volume", 0.0))
                bw = sum(float(v) for k, v in weights.items() if k != "search_volume")
                base = base_axes.get(axis)
                if base is None:
                    axes[axis] = round(score, 4)
                elif sw > 0:
                    axes[axis] = round((float(base) * bw + score * sw) / (bw + sw), 4)

        level = available_weighted_mean(axes, LEVEL_WEIGHTS)
        level = round(clamp(level), 4) if level is not None else None
        aggregate["axes_before_search"] = base_axes
        aggregate["axes"] = axes
        aggregate["search_score"] = score
        aggregate["level"] = level
        aggregate["search_blend_method"] = "configured_axis_signal_weight"
        row.level = Decimal(str(level)) if level is not None else None
        row.metrics = merge_json(metrics, {"aggregate": aggregate})
        row.save(update_fields=["level", "metrics", "updated_at"])
        updated += 1
    return {"updated": updated}
