from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from apps.core.models import Source, TermMetricDaily
from .common import log_compress, merge_json
from .config import COUNT_SIGNAL_PATHS, METRIC_VERSION, NORMALIZATION_WINDOW_DAYS


def _nested(metrics: dict, path: tuple[str, ...]):
    current = metrics or {}
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    try:
        return float(current) if current is not None else None
    except (TypeError, ValueError):
        return None


def _raw_signals(row: TermMetricDaily) -> dict[str, float | None]:
    out = {name: _nested(row.metrics or {}, path) for name, path in COUNT_SIGNAL_PATHS.items()}
    out["mention_count"] = float(row.mention_count or 0)
    out["document_count"] = float(row.document_count or 0)
    return out


def _percentile_against_distribution(value: float, positives: list[float]) -> float | None:
    """Zero-preserving, tie-aware percentile against a rolling positive distribution."""
    if value <= 0:
        return 0.0
    if not positives:
        return None
    if len(positives) == 1:
        return 100.0
    less = sum(1 for x in positives if x < value)
    equal = sum(1 for x in positives if x == value)
    avg_rank = less + (equal - 1) / 2.0
    return round(100.0 * avg_rank / (len(positives) - 1), 4)


@transaction.atomic
def normalize_source_signals(metric_date: date, *, metric_version: str = METRIC_VERSION) -> dict:
    """
    Rolling source normalization.

    Cohort = [metric_date-(window-1), metric_date] x source x signal, pooled as
    term-day observations. Current-day observed zero stays 0 only when the rolling
    cohort contains a positive observation. If the entire rolling cohort is zero or
    absent, the signal is unavailable (NULL).
    """
    updated = 0
    unavailable = 0
    start = metric_date - timedelta(days=NORMALIZATION_WINDOW_DAYS - 1)

    for source in Source.objects.all():
        current_rows = list(TermMetricDaily.objects.filter(
            source=source, metric_date=metric_date, metric_version=metric_version,
        ))
        if not current_rows:
            continue

        cohort_rows = list(TermMetricDaily.objects.filter(
            source=source,
            metric_date__gte=start,
            metric_date__lte=metric_date,
            metric_version=metric_version,
        ))

        current_signals = {row.id: _raw_signals(row) for row in current_rows}
        distributions: dict[str, list[float]] = {}
        observed: dict[str, int] = {}
        for item in cohort_rows:
            for name, value in _raw_signals(item).items():
                if value is None:
                    continue
                observed[name] = observed.get(name, 0) + 1
                if value > 0:
                    distributions.setdefault(name, []).append(float(value))

        for row in current_rows:
            normalized = {}
            for name, raw in current_signals[row.id].items():
                positives = distributions.get(name, [])
                available = bool(positives)
                if raw is None:
                    payload = {"raw": None, "log": None, "score": None, "available": False}
                elif not available:
                    payload = {
                        "raw": raw, "log": round(log_compress(raw), 6), "score": None,
                        "available": False, "method": "unavailable_all_zero_rolling_cohort",
                    }
                    unavailable += 1
                else:
                    payload = {
                        "raw": raw,
                        "log": round(log_compress(raw), 6),
                        "score": _percentile_against_distribution(float(raw), positives),
                        "available": True,
                        "method": "rolling_zero_preserving_positive_percentile",
                    }
                normalized[name] = payload

            row.metrics = merge_json(row.metrics, {
                "normalization": {
                    "version": "step04-v1",
                    "source_code": source.code,
                    "window_days": NORMALIZATION_WINDOW_DAYS,
                    "window_start": str(start),
                    "window_end": str(metric_date),
                    "cohort_unit": "term_day",
                    "signals": normalized,
                }
            })

            # Compatibility columns: mention normalization only; canonical scoring lives in metrics JSON.
            mention = normalized.get("mention_count") or {}
            row.raw_count = Decimal(str(round(float(mention["raw"]), 4))) if mention.get("raw") is not None else None
            row.log_count = Decimal(str(round(float(mention["log"]), 6))) if mention.get("log") is not None else None
            row.percentile = Decimal(str(round(float(mention["score"]), 4))) if mention.get("score") is not None else None
            row.save(update_fields=["metrics", "raw_count", "log_count", "percentile", "updated_at"])
            updated += 1

    return {
        "updated": updated,
        "window_days": NORMALIZATION_WINDOW_DAYS,
        "window_start": str(start),
        "unavailable_current_signals": unavailable,
    }
