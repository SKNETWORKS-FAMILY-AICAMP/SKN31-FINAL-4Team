# analysis/metrics/commerce.py
from __future__ import annotations

from collections import defaultdict
from zoneinfo import ZoneInfo

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from apps.core.models import (
    Brand,
    DictionaryTerm,
    ProductSourceSnapshot,
    ProductTerm,
    Source,
)

from .common import METRIC_VERSION, ensure_metric, merge_json


def _day_bounds(metric_date: date):
    tz = ZoneInfo("Asia/Seoul")
    start = timezone.make_aware(datetime.combine(metric_date, time.min), tz)
    return start, start + timedelta(days=1)


def _num(value, default=0.0):
    try:
        return float(value) if value is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _snapshot_fields() -> set[str]:
    return {
        f.name for f in ProductSourceSnapshot._meta.get_fields()
        if getattr(f, "concrete", False)
    }


def get_metric_eligible_brand_ids() -> set[int]:
    """
    BRAND metric eligibility:
    - ACTIVE
    - BRAND_NON_BRAND excluded
    - MUSINSA required
    - >=2 independent sources, MUSINSA_USED not counted
    - EXCLUDED BrandSource ignored
    """
    return set(
        Brand.objects
        .filter(status="ACTIVE")
        .exclude(category__code="BRAND_NON_BRAND")
        .annotate(
            independent_source_count=Count(
                "brand_sources__source",
                filter=(
                    ~Q(brand_sources__mapping_status="EXCLUDED")
                    & ~Q(brand_sources__source__code__iexact="MUSINSA_USED")
                ),
                distinct=True,
            ),
            musinsa_count=Count(
                "brand_sources__source",
                filter=(
                    Q(brand_sources__source__code__iexact="MUSINSA")
                    & ~Q(brand_sources__mapping_status="EXCLUDED")
                ),
                distinct=True,
            ),
        )
        .filter(musinsa_count__gte=1, independent_source_count__gte=2)
        .values_list("id", flat=True)
    )


def _allowed_term_ids() -> tuple[set[int], set[int]]:
    eligible_brand_ids = get_metric_eligible_brand_ids()

    # All active non-brand terms + eligible brand terms only.
    ids = set(
        DictionaryTerm.objects
        .filter(status="ACTIVE")
        .filter(
            ~Q(term_type="BRAND")
            | Q(term_type="BRAND", brand_id__in=eligible_brand_ids)
        )
        .values_list("id", flat=True)
    )
    return ids, eligible_brand_ids


def _update_stat(stat: dict, snap, fields: set[str]):
    ps_id = snap.product_source_id
    stat["snapshot_count"] += 1
    stat["product_ids"].add(ps_id)

    rank = getattr(snap, "rank_position", None)
    if rank is not None:
        stat["ranked_product_ids"].add(ps_id)
        rank_f = _num(rank)
        stat["rank_sum"] += rank_f
        stat["rank_n"] += 1
        stat["best_rank"] = (
            rank_f if stat["best_rank"] is None
            else min(stat["best_rank"], rank_f)
        )

    rating = getattr(snap, "rating", None)
    if rating is not None:
        stat["rating_sum"] += _num(rating)
        stat["rating_n"] += 1

    for name in ("review_count", "like_count", "view_count", "sales_count",
                 "trade_count", "wish_count", "buy_count"):
        if name not in fields:
            continue
        value = getattr(snap, name, None)
        if value is None:
            continue
        key = f"max_{name}"
        stat[key] = max(stat.get(key, 0), _int(value))


def _empty_stat():
    return {
        "snapshot_count": 0,
        "product_ids": set(),
        "ranked_product_ids": set(),
        "best_rank": None,
        "rank_sum": 0.0,
        "rank_n": 0,
        "rating_sum": 0.0,
        "rating_n": 0,
    }


def _payload(stat: dict) -> dict:
    out = {
        "snapshot_count": stat["snapshot_count"],
        "product_count": len(stat["product_ids"]),
        "ranked_product_count": len(stat["ranked_product_ids"]),
        "best_rank": int(stat["best_rank"]) if stat["best_rank"] is not None else None,
        "avg_rank": round(stat["rank_sum"] / stat["rank_n"], 4) if stat["rank_n"] else None,
        "avg_rating": round(stat["rating_sum"] / stat["rating_n"], 4) if stat["rating_n"] else None,
        "max_review_count": stat.get("max_review_count", 0),
        "max_like_count": stat.get("max_like_count", 0),
    }
    for name in ("view_count", "sales_count", "trade_count", "wish_count", "buy_count"):
        key = f"max_{name}"
        if key in stat:
            out[key] = stat[key]
    return out


def apply_commerce_metrics(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
) -> dict:
    """
    Fast ProductTerm-based commerce aggregation.

    IMPORTANT:
    Old implementation executed exists()+aggregate() for every source x term.
    This version reads the day's snapshots once, preloads ProductTerm mappings,
    aggregates in memory, then writes only actual source/term rows.
    """
    start, end = _day_bounds(metric_date)
    fields = _snapshot_fields()
    allowed_term_ids, eligible_brand_ids = _allowed_term_ids()

    snapshots = list(
        ProductSourceSnapshot.objects
        .filter(observed_at__gte=start, observed_at__lt=end)
        .select_related("product_source", "product_source__source")
    )

    if not snapshots:
        return {
            "metric_date": str(metric_date),
            "saved": 0,
            "eligible_brand_count": len(eligible_brand_ids),
            "snapshot_count": 0,
            "sources": {},
        }

    product_source_ids = {s.product_source_id for s in snapshots}

    # product_source_id -> [term_id, ...]
    terms_by_product = defaultdict(list)
    for ps_id, term_id in (
        ProductTerm.objects
        .filter(
            product_source_id__in=product_source_ids,
            term_id__in=allowed_term_ids,
        )
        .values_list("product_source_id", "term_id")
        .iterator(chunk_size=10000)
    ):
        terms_by_product[ps_id].append(term_id)

    # (source_id, term_id) -> aggregated stats
    stats = {}
    source_codes = {}

    for snap in snapshots:
        source = snap.product_source.source
        source_codes[source.id] = source.code
        term_ids = terms_by_product.get(snap.product_source_id, ())
        if not term_ids:
            continue

        for term_id in term_ids:
            key = (source.id, term_id)
            stat = stats.get(key)
            if stat is None:
                stat = _empty_stat()
                stats[key] = stat
            _update_stat(stat, snap, fields)

    terms = DictionaryTerm.objects.in_bulk({term_id for _, term_id in stats})
    sources = Source.objects.in_bulk({source_id for source_id, _ in stats})

    saved = 0
    source_results = defaultdict(int)

    for (source_id, term_id), stat in stats.items():
        term = terms.get(term_id)
        source = sources.get(source_id)
        if term is None or source is None:
            continue

        metric = ensure_metric(
            term=term,
            source=source,
            metric_date=metric_date,
            metric_version=metric_version,
        )
        metric.metrics = merge_json(
            metric.metrics,
            {"commerce": _payload(stat)},
        )
        metric.save(update_fields=["metrics", "updated_at"])
        saved += 1
        source_results[source.code] += 1

    return {
        "metric_date": str(metric_date),
        "saved": saved,
        "eligible_brand_count": len(eligible_brand_ids),
        "snapshot_count": len(snapshots),
        "mapped_product_source_count": len(terms_by_product),
        "sources": dict(source_results),
    }
