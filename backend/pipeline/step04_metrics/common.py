from __future__ import annotations

from collections import defaultdict
from math import exp, log
from typing import Iterable

from django.db import connection

from apps.core.models import DictionaryTerm, Source, TermAlias, TermMetricDaily
from .config import METRIC_VERSION


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def safe_rate(numerator, denominator):
    denominator = float(denominator or 0)
    if denominator <= 0:
        return None
    return round(float(numerator or 0) / denominator * 100.0, 4)


def log_compress(value):
    return log(1.0 + max(0.0, float(value or 0)))


def available_weighted_mean(values: dict[str, float | None], weights: dict[str, float]):
    pairs = [
        (float(values[name]), float(weight))
        for name, weight in weights.items()
        if values.get(name) is not None and float(weight) > 0
    ]
    if not pairs:
        return None
    denominator = sum(weight for _, weight in pairs)
    return sum(value * weight for value, weight in pairs) / denominator


def zero_preserving_percentile(values_by_id: dict[int, float]) -> dict[int, float]:
    """0 -> 0. Positive values receive a tie-aware percentile among positives."""
    result = {obj_id: 0.0 for obj_id, value in values_by_id.items() if float(value or 0) <= 0}
    positive = {
        obj_id: float(value)
        for obj_id, value in values_by_id.items()
        if float(value or 0) > 0
    }
    if not positive:
        return result
    if len(positive) == 1:
        result[next(iter(positive))] = 100.0
        return result

    grouped = defaultdict(list)
    for obj_id, value in positive.items():
        grouped[value].append(obj_id)

    n = len(positive)
    seen = 0
    for value in sorted(grouped):
        ids = grouped[value]
        size = len(ids)
        avg_rank = seen + (size + 1.0) / 2.0
        pct = (avg_rank - 1.0) / (n - 1.0) * 100.0
        for obj_id in ids:
            result[obj_id] = round(clamp(pct), 4)
        seen += size
    return result

def percentile_rank(
    value: float,
    population: list[float],
) -> float:
    """
    population 내 value의 tie-aware percentile rank.

    - 빈 population -> 0
    - 값 1개 -> 100
    - 동점은 평균 rank 사용
    - 결과 범위 0~100
    """
    if value is None:
        return 0.0

    values = [
        float(v)
        for v in population
        if v is not None
    ]

    if not values:
        return 0.0

    if len(values) == 1:
        return 100.0

    value = float(value)

    below = sum(
        1
        for v in values
        if v < value
    )

    equal = sum(
        1
        for v in values
        if v == value
    )

    rank = below + (equal - 1) / 2.0

    return clamp(
        rank / (len(values) - 1) * 100.0
    )
    
def momentum_score(ma7, ma28):
    """Neutral 50 when both windows are empty/equal; logistic growth score otherwise."""
    ma7 = float(ma7 or 0)
    ma28 = float(ma28 or 0)
    if ma28 <= 0:
        return 50.0 if ma7 <= 0 else 100.0
    return clamp(100.0 / (1.0 + exp(-6.0 * (ma7 / ma28 - 1.0))))


def moving_average(values: Iterable, window: int) -> float | None:
    rows = [float(v) for v in values if v is not None]
    tail = rows[-window:]
    return sum(tail) / len(tail) if tail else None


def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def execute_query(sql: str, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return dictfetchall(cursor)


def normalize_term_key(value):
    return " ".join(str(value or "").strip().casefold().split())


def build_term_lookup():
    lookup = {}
    for term in DictionaryTerm.objects.filter(status="ACTIVE"):
        for value in (term.canonical_name, term.normalized_name):
            key = normalize_term_key(value)
            if key:
                lookup[key] = term
    for alias in TermAlias.objects.select_related("term").filter(term__status="ACTIVE"):
        for value in (alias.alias, alias.normalized_alias):
            key = normalize_term_key(value)
            if key:
                lookup.setdefault(key, alias.term)
    return lookup


def source_lookup():
    return {source.id: source for source in Source.objects.all()}


def ensure_metric(*, term, source, metric_date, metric_version=METRIC_VERSION):
    metric = TermMetricDaily.objects.filter(
        term=term,
        source=source,
        metric_date=metric_date,
        metric_version=metric_version,
    ).first()
    if metric is not None:
        return metric
    return TermMetricDaily.objects.create(
        term=term,
        source=source,
        metric_date=metric_date,
        metric_version=metric_version,
    )


def merge_json(base, patch):
    result = dict(base or {})
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_json(result[key], value)
        else:
            result[key] = value
    return result
