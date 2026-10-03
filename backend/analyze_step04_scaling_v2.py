from __future__ import annotations

"""
FEEDIT STEP04 Scaling Diagnostic v2

목적
----
STEP04 최종 점수 공식을 확정하기 전에 실제 DB의 최근 기간 분포를 진단한다.

핵심 원칙
--------
1. READ ONLY. DB에 INSERT / UPDATE / DELETE 하지 않는다.
2. 최근 28일을 기본 분석 기간으로 사용한다.
3. TermMetricDaily만 보지 않고 가능한 원천 테이블도 직접 읽는다.
4. 플랫폼(source)별로 분포를 분리한다.
5. 0은 0으로 유지하는 zero-preserving scaling을 비교한다.
6. count형 데이터는 raw / log1p / share / log-minmax /
   positive-only percentile / zero-preserving percentile을 함께 출력한다.
7. 모델/컬럼이 프로젝트 버전에 따라 조금 달라도 가능한 필드를 자동 탐색한다.
8. 읽을 수 없는 원천은 실패시키지 않고 SKIP 사유를 출력한다.

기본 실행
---------
cd C:\feedit\backend
python analyze_step04_scaling_v2.py

기간 변경
---------
python analyze_step04_scaling_v2.py --days 14

종료일 지정
-----------
python analyze_step04_scaling_v2.py --end-date 2026-09-30 --days 28

출력
----
metric_diagnostics_v2/
    step04_v2_source_summary.csv
    step04_v2_scaling_samples.csv
    step04_v2_source_totals.csv
    step04_v2_diagnostics.txt
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

BACKEND_DIR = Path(__file__).resolve().parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.apps import apps
from django.db.models import Max


# ============================================================
# MODEL DISCOVERY
# ============================================================

def find_model(*names):
    wanted = {name.lower() for name in names}

    for model in apps.get_models():
        if model.__name__.lower() in wanted:
            return model

    return None


ProductSource = find_model("ProductSource")
ProductSourceSnapshot = find_model("ProductSourceSnapshot")
ContentItem = find_model("ContentItem")
ContentSnapshot = find_model("ContentSnapshot")
TextDocument = find_model("TextDocument")
TextTermMention = find_model("TextTermMention")
TermMetricDaily = find_model("TermMetricDaily")
TermSearchMetricMonthly = find_model("TermSearchMetricMonthly")


# ============================================================
# GENERIC HELPERS
# ============================================================

def concrete_fields(model):
    if model is None:
        return {}

    return {
        field.name: field
        for field in model._meta.get_fields()
        if getattr(field, "concrete", False)
    }


def relation_names(model):
    if model is None:
        return set()

    return {
        field.name
        for field in model._meta.get_fields()
        if getattr(field, "is_relation", False)
    }


def first_existing(fields, candidates):
    for name in candidates:
        if name in fields:
            return name
    return None


def number(value):
    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value):
        return None

    return value


def obj_number(obj, candidates):
    for name in candidates:
        if hasattr(obj, name):
            value = number(getattr(obj, name, None))
            if value is not None:
                return value

    return None


def nested_number(payload, paths):
    if not isinstance(payload, dict):
        return None

    for path in paths:
        current = payload

        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]

        value = number(current)

        if value is not None:
            return value

    return None


def source_label(obj):
    source = getattr(obj, "source", None)

    if source is not None:
        return str(
            getattr(source, "code", None)
            or getattr(source, "name", None)
            or getattr(source, "pk", None)
            or "UNKNOWN"
        )

    source_code = getattr(obj, "source_code", None)

    if source_code:
        return str(source_code)

    platform = getattr(obj, "platform", None)

    if platform:
        return str(platform)

    return "UNKNOWN"


def term_label(obj):
    term = getattr(obj, "term", None)

    if term is None:
        return str(getattr(obj, "term_id", ""))

    return str(
        getattr(term, "term", None)
        or getattr(term, "canonical_name", None)
        or getattr(term, "normalized_name", None)
        or getattr(term, "pk", "")
    )


def date_value(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).date()
        except ValueError:
            return None

    return None


def quantile(values, q):
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)

    if lo == hi:
        return ordered[lo]

    frac = pos - lo

    return (
        ordered[lo] * (1.0 - frac)
        + ordered[hi] * frac
    )


def fmt(value):
    if value is None:
        return "-"

    value = float(value)

    if abs(value) >= 1000:
        return f"{value:,.0f}"

    if value.is_integer():
        return str(int(value))

    return f"{value:.3f}"


# ============================================================
# SCALERS
# ============================================================

def minmax(values_by_key, zero_preserving=False):
    if not values_by_key:
        return {}

    if zero_preserving:
        positives = {
            key: value
            for key, value in values_by_key.items()
            if value > 0
        }

        result = {
            key: 0.0
            for key, value in values_by_key.items()
            if value <= 0
        }

        if not positives:
            return {
                key: 0.0
                for key in values_by_key
            }

        lo = min(positives.values())
        hi = max(positives.values())

        if hi == lo:
            for key in positives:
                result[key] = 100.0
            return result

        for key, value in positives.items():
            result[key] = round(
                100.0 * (value - lo) / (hi - lo),
                6,
            )

        return result

    lo = min(values_by_key.values())
    hi = max(values_by_key.values())

    if hi == lo:
        # v1의 50점 문제 수정:
        # 전부 0이면 0, 같은 positive 값이면 100.
        score = 0.0 if hi <= 0 else 100.0

        return {
            key: score
            for key in values_by_key
        }

    return {
        key: round(
            100.0 * (value - lo) / (hi - lo),
            6,
        )
        for key, value in values_by_key.items()
    }


def log_minmax(values_by_key, zero_preserving=True):
    logged = {
        key: math.log1p(max(0.0, value))
        for key, value in values_by_key.items()
    }

    return minmax(
        logged,
        zero_preserving=zero_preserving,
    )


def tie_percentile(values_by_key, positive_only=False):
    if not values_by_key:
        return {}

    result = {}

    if positive_only:
        work = {
            key: value
            for key, value in values_by_key.items()
            if value > 0
        }

        for key, value in values_by_key.items():
            if value <= 0:
                result[key] = 0.0
    else:
        work = dict(values_by_key)

    if not work:
        return {
            key: 0.0
            for key in values_by_key
        }

    grouped = defaultdict(list)

    for key, value in work.items():
        grouped[value].append(key)

    ordered = sorted(grouped)
    n = len(work)

    if n == 1:
        only = next(iter(work))
        result[only] = 100.0
        return result

    seen = 0

    for value in ordered:
        keys = grouped[value]
        size = len(keys)

        avg_rank = seen + (size + 1.0) / 2.0
        pct = (avg_rank - 1.0) / (n - 1.0) * 100.0

        for key in keys:
            result[key] = round(pct, 6)

        seen += size

    return result


def zero_preserving_percentile(values_by_key):
    return tie_percentile(
        values_by_key,
        positive_only=True,
    )


# ============================================================
# OBSERVATION FORMAT
# ============================================================

def observation(
    *,
    dataset,
    source,
    metric,
    key,
    raw,
    observed_date=None,
    term_id=None,
    term=None,
):
    raw = number(raw)

    if raw is None:
        return None

    return {
        "dataset": dataset,
        "source": str(source or "UNKNOWN"),
        "metric": metric,
        "key": str(key),
        "raw": raw,
        "observed_date": (
            observed_date.isoformat()
            if isinstance(observed_date, date)
            else observed_date
        ),
        "term_id": term_id,
        "term": term,
    }


# ============================================================
# 1. TERM METRIC DAILY
# ============================================================

def collect_term_metric_daily(start_date, end_date, log):
    if TermMetricDaily is None:
        log.append("SKIP TermMetricDaily: model not found")
        return []

    fields = concrete_fields(TermMetricDaily)

    if "metric_date" not in fields:
        log.append("SKIP TermMetricDaily: metric_date field not found")
        return []

    qs = TermMetricDaily.objects.filter(
        metric_date__gte=start_date,
        metric_date__lte=end_date,
    )

    rels = relation_names(TermMetricDaily)
    selects = [
        name
        for name in ("source", "term")
        if name in rels
    ]

    if selects:
        qs = qs.select_related(*selects)

    rows = []

    for row in qs.iterator(chunk_size=2000):
        payload = getattr(row, "metrics", None) or {}

        commerce = payload.get("commerce", {}) if isinstance(payload, dict) else {}
        content = payload.get("content", {}) if isinstance(payload, dict) else {}

        candidates = {
            "product_count": (
                obj_number(row, ("product_count",)),
                nested_number(payload, (("commerce", "product_count"),)),
            ),
            "ranked_product_count": (
                obj_number(row, ("ranked_product_count",)),
                nested_number(payload, (("commerce", "ranked_product_count"),)),
            ),
            "review_count": (
                obj_number(row, ("review_count",)),
                nested_number(
                    payload,
                    (
                        ("commerce", "review_count"),
                        ("commerce", "max_review_count"),
                    ),
                ),
            ),
            "commerce_like_count": (
                nested_number(
                    payload,
                    (
                        ("commerce", "like_count"),
                        ("commerce", "max_like_count"),
                    ),
                ),
            ),
            "content_count": (
                obj_number(row, ("content_count",)),
                nested_number(payload, (("content", "content_count"),)),
            ),
            "creator_count": (
                obj_number(row, ("creator_count",)),
                nested_number(payload, (("content", "creator_count"),)),
            ),
            "view_count": (
                nested_number(
                    payload,
                    (
                        ("content", "view_count"),
                        ("content", "max_view_count"),
                    ),
                ),
            ),
            "content_like_count": (
                nested_number(
                    payload,
                    (
                        ("content", "like_count"),
                        ("content", "max_like_count"),
                    ),
                ),
            ),
            "comment_count": (
                nested_number(
                    payload,
                    (
                        ("content", "comment_count"),
                        ("content", "max_comment_count"),
                    ),
                ),
            ),
            "mention_count": (
                obj_number(row, ("mention_count",)),
                nested_number(payload, (("reaction", "mention_count"),)),
            ),
            "document_count": (
                obj_number(row, ("document_count",)),
            ),
        }

        for metric, options in candidates.items():
            value = next(
                (
                    number(item)
                    for item in options
                    if number(item) is not None
                ),
                None,
            )

            if value is None:
                continue

            item = observation(
                dataset="term_metric_daily",
                source=source_label(row),
                metric=metric,
                key=f"{row.pk}:{metric}",
                raw=value,
                observed_date=getattr(row, "metric_date", None),
                term_id=getattr(row, "term_id", None),
                term=term_label(row),
            )

            if item:
                rows.append(item)

    log.append(
        f"OK TermMetricDaily: {len(rows):,} metric observations"
    )

    return rows


# ============================================================
# 2. PRODUCT SOURCE SNAPSHOT
# ============================================================

def collect_product_snapshots(start_date, end_date, log):
    if ProductSourceSnapshot is None:
        log.append("SKIP ProductSourceSnapshot: model not found")
        return []

    fields = concrete_fields(ProductSourceSnapshot)
    rels = relation_names(ProductSourceSnapshot)

    date_field = first_existing(
        fields,
        (
            "observed_at",
            "snapshot_at",
            "collected_at",
            "created_at",
            "metric_date",
            "date",
        ),
    )

    if date_field is None:
        log.append(
            "SKIP ProductSourceSnapshot: no usable date field"
        )
        return []

    qs = ProductSourceSnapshot.objects.all()

    field = fields[date_field]

    if field.get_internal_type() == "DateField":
        qs = qs.filter(
            **{
                f"{date_field}__gte": start_date,
                f"{date_field}__lte": end_date,
            }
        )
    else:
        qs = qs.filter(
            **{
                f"{date_field}__date__gte": start_date,
                f"{date_field}__date__lte": end_date,
            }
        )

    selects = []

    if "product_source" in rels:
        selects.append("product_source")

        ps_rels = relation_names(ProductSource)

        if ProductSource is not None and "source" in ps_rels:
            selects.append("product_source__source")

    if "source" in rels:
        selects.append("source")

    if selects:
        qs = qs.select_related(*selects)

    metric_candidates = {
        "snapshot_rank": (
            "rank",
            "ranking",
            "rank_no",
        ),
        "snapshot_review_count": (
            "review_count",
            "reviews_count",
        ),
        "snapshot_like_count": (
            "like_count",
            "likes_count",
            "wish_count",
        ),
        "snapshot_view_count": (
            "view_count",
            "views_count",
        ),
        "snapshot_sales_count": (
            "sales_count",
            "sale_count",
            "sold_count",
        ),
        "snapshot_trade_count": (
            "trade_count",
            "transaction_count",
        ),
        "snapshot_buy_count": (
            "buy_count",
            "purchase_count",
        ),
    }

    rows = []

    for row in qs.iterator(chunk_size=2000):
        observed = date_value(
            getattr(row, date_field, None)
        )

        ps = getattr(row, "product_source", None)

        if ps is not None:
            src = source_label(ps)
        else:
            src = source_label(row)

        for metric, candidates in metric_candidates.items():
            value = obj_number(row, candidates)

            if value is None:
                continue

            item = observation(
                dataset="product_source_snapshot",
                source=src,
                metric=metric,
                key=f"{row.pk}:{metric}",
                raw=value,
                observed_date=observed,
            )

            if item:
                rows.append(item)

    log.append(
        f"OK ProductSourceSnapshot: {len(rows):,} metric observations"
    )

    return rows


# ============================================================
# 3. CONTENT SNAPSHOT
# ============================================================

def collect_content_snapshots(start_date, end_date, log):
    if ContentSnapshot is None:
        log.append("SKIP ContentSnapshot: model not found")
        return []

    fields = concrete_fields(ContentSnapshot)
    rels = relation_names(ContentSnapshot)

    date_field = first_existing(
        fields,
        (
            "observed_at",
            "snapshot_at",
            "collected_at",
            "created_at",
            "metric_date",
            "date",
        ),
    )

    if date_field is None:
        log.append(
            "SKIP ContentSnapshot: no usable date field"
        )
        return []

    qs = ContentSnapshot.objects.all()
    field = fields[date_field]

    if field.get_internal_type() == "DateField":
        qs = qs.filter(
            **{
                f"{date_field}__gte": start_date,
                f"{date_field}__lte": end_date,
            }
        )
    else:
        qs = qs.filter(
            **{
                f"{date_field}__date__gte": start_date,
                f"{date_field}__date__lte": end_date,
            }
        )

    selects = []

    if "content" in rels:
        selects.append("content")

        if ContentItem is not None:
            item_rels = relation_names(ContentItem)

            if "source" in item_rels:
                selects.append("content__source")

    if "content_item" in rels:
        selects.append("content_item")

        if ContentItem is not None:
            item_rels = relation_names(ContentItem)

            if "source" in item_rels:
                selects.append("content_item__source")

    if "source" in rels:
        selects.append("source")

    if selects:
        qs = qs.select_related(*selects)

    metrics = {
        "snapshot_view_count": (
            "view_count",
            "views_count",
        ),
        "snapshot_like_count": (
            "like_count",
            "likes_count",
        ),
        "snapshot_comment_count": (
            "comment_count",
            "comments_count",
        ),
        "snapshot_share_count": (
            "share_count",
            "shares_count",
        ),
    }

    rows = []

    for row in qs.iterator(chunk_size=2000):
        content = (
            getattr(row, "content", None)
            or getattr(row, "content_item", None)
        )

        src = (
            source_label(content)
            if content is not None
            else source_label(row)
        )

        observed = date_value(
            getattr(row, date_field, None)
        )

        for metric, candidates in metrics.items():
            value = obj_number(row, candidates)

            if value is None:
                continue

            item = observation(
                dataset="content_snapshot",
                source=src,
                metric=metric,
                key=f"{row.pk}:{metric}",
                raw=value,
                observed_date=observed,
            )

            if item:
                rows.append(item)

    log.append(
        f"OK ContentSnapshot: {len(rows):,} metric observations"
    )

    return rows


# ============================================================
# 4. SEARCH MONTHLY
# ============================================================

def collect_search(start_date, end_date, log):
    if TermSearchMetricMonthly is None:
        log.append("SKIP TermSearchMetricMonthly: model not found")
        return []

    fields = concrete_fields(TermSearchMetricMonthly)
    rels = relation_names(TermSearchMetricMonthly)

    month_field = first_existing(
        fields,
        (
            "metric_month",
            "month",
            "date",
        ),
    )

    if month_field is None:
        log.append(
            "SKIP TermSearchMetricMonthly: no month/date field"
        )
        return []

    start_month = start_date.replace(day=1)
    end_month = end_date.replace(day=1)

    qs = TermSearchMetricMonthly.objects.filter(
        **{
            f"{month_field}__gte": start_month,
            f"{month_field}__lte": end_month,
        }
    )

    selects = [
        name
        for name in ("term", "source")
        if name in rels
    ]

    if selects:
        qs = qs.select_related(*selects)

    rows = []

    for row in qs.iterator(chunk_size=2000):
        value = obj_number(
            row,
            (
                "total_search_volume",
                "search_volume",
                "volume",
            ),
        )

        if value is None:
            continue

        platform = getattr(row, "platform", None)
        src = (
            source_label(row)
            if "source" in rels
            else str(platform or "SEARCH")
        )

        item = observation(
            dataset="search_monthly",
            source=src,
            metric="search_volume",
            key=f"{row.pk}:search_volume",
            raw=value,
            observed_date=date_value(
                getattr(row, month_field, None)
            ),
            term_id=getattr(row, "term_id", None),
            term=term_label(row),
        )

        if item:
            rows.append(item)

    log.append(
        f"OK TermSearchMetricMonthly: {len(rows):,} metric observations"
    )

    return rows


# ============================================================
# SOURCE TOTALS / SHARE
# ============================================================

def collect_product_source_totals(log):
    """
    현재 inventory 크기 진단용.
    날짜별 exposure denominator로 확정해서 쓰는 것은 아니다.
    STEP04 최종 share denominator 결정 전 참고값으로만 출력한다.
    """
    if ProductSource is None:
        log.append("SKIP ProductSource totals: model not found")
        return {}

    rels = relation_names(ProductSource)
    qs = ProductSource.objects.all()

    if "source" in rels:
        qs = qs.select_related("source")

    totals = defaultdict(int)

    for row in qs.iterator(chunk_size=5000):
        totals[source_label(row)] += 1

    log.append(
        "OK ProductSource totals: "
        + ", ".join(
            f"{source}={count:,}"
            for source, count in sorted(totals.items())
        )
    )

    return dict(totals)


# ============================================================
# SCALING
# ============================================================

def apply_scaling(rows, source_totals):
    grouped = defaultdict(list)

    for row in rows:
        grouped[
            (
                row["dataset"],
                row["source"],
                row["metric"],
            )
        ].append(row)

    output = []

    for group_key, group in grouped.items():
        raw_by_key = {
            row["key"]: row["raw"]
            for row in group
        }

        raw_mm = minmax(
            raw_by_key,
            zero_preserving=True,
        )

        log_mm = log_minmax(
            raw_by_key,
            zero_preserving=True,
        )

        pos_pct = tie_percentile(
            raw_by_key,
            positive_only=True,
        )

        zero_pct = zero_preserving_percentile(
            raw_by_key
        )

        source = group_key[1]
        denominator = source_totals.get(source)

        for row in group:
            item = dict(row)
            item["log1p"] = round(
                math.log1p(max(0.0, row["raw"])),
                8,
            )
            item["zero_minmax"] = raw_mm[row["key"]]
            item["zero_log_minmax"] = log_mm[row["key"]]
            item["positive_percentile"] = pos_pct[row["key"]]
            item["zero_percentile"] = zero_pct[row["key"]]

            if (
                denominator
                and row["metric"]
                in {
                    "product_count",
                    "ranked_product_count",
                }
            ):
                item["inventory_share_pct"] = round(
                    row["raw"] / denominator * 100.0,
                    8,
                )
            else:
                item["inventory_share_pct"] = None

            output.append(item)

    return output


# ============================================================
# SUMMARY
# ============================================================

def summarize(rows):
    grouped = defaultdict(list)

    for row in rows:
        grouped[
            (
                row["dataset"],
                row["source"],
                row["metric"],
            )
        ].append(row["raw"])

    result = []

    for (dataset, source, metric), values in sorted(grouped.items()):
        n = len(values)
        zero_count = sum(value <= 0 for value in values)
        positives = [value for value in values if value > 0]

        p99 = quantile(values, 0.99)
        max_value = max(values)

        result.append(
            {
                "dataset": dataset,
                "source": source,
                "metric": metric,
                "n": n,
                "zero_count": zero_count,
                "zero_rate_pct": round(
                    zero_count / n * 100.0,
                    6,
                ) if n else None,
                "positive_count": len(positives),
                "min": min(values),
                "median": median(values),
                "mean": round(
                    sum(values) / n,
                    8,
                ),
                "p90": quantile(values, 0.90),
                "p95": quantile(values, 0.95),
                "p99": p99,
                "max": max_value,
                "max_over_p99": (
                    round(max_value / p99, 8)
                    if p99 and p99 > 0
                    else None
                ),
                "positive_min": (
                    min(positives)
                    if positives
                    else None
                ),
                "positive_median": (
                    median(positives)
                    if positives
                    else None
                ),
                "positive_max": (
                    max(positives)
                    if positives
                    else None
                ),
                "unique_values": len(set(values)),
            }
        )

    return result


def choose_samples(rows, limit=40):
    grouped = defaultdict(list)

    for row in rows:
        grouped[
            (
                row["dataset"],
                row["source"],
                row["metric"],
            )
        ].append(row)

    result = []

    for _, group in sorted(grouped.items()):
        ordered = sorted(
            group,
            key=lambda row: row["raw"],
        )

        n = len(ordered)

        if n <= limit:
            selected = ordered
        else:
            indexes = sorted(
                {
                    round(
                        i * (n - 1) / (limit - 1)
                    )
                    for i in range(limit)
                }
            )

            selected = [
                ordered[index]
                for index in indexes
            ]

        for row in selected:
            result.append(
                {
                    key: value
                    for key, value in row.items()
                    if key != "key"
                }
            )

    return result


# ============================================================
# OUTPUT
# ============================================================

def write_csv(path, rows):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        path.write_text(
            "",
            encoding="utf-8-sig",
        )
        return

    fieldnames = []

    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def print_summary(summary):
    print()
    print("=" * 150)
    print("STEP04 SCALING DIAGNOSTIC V2")
    print("=" * 150)

    header = (
        f"{'DATASET':<24}"
        f"{'SOURCE':<16}"
        f"{'METRIC':<26}"
        f"{'N':>8}"
        f"{'ZERO%':>9}"
        f"{'MEDIAN':>12}"
        f"{'P95':>12}"
        f"{'P99':>12}"
        f"{'MAX':>14}"
        f"{'UNIQUE':>9}"
    )

    print(header)
    print("-" * len(header))

    for row in summary:
        print(
            f"{row['dataset'][:23]:<24}"
            f"{row['source'][:15]:<16}"
            f"{row['metric'][:25]:<26}"
            f"{row['n']:>8}"
            f"{row['zero_rate_pct']:>9.2f}"
            f"{fmt(row['median']):>12}"
            f"{fmt(row['p95']):>12}"
            f"{fmt(row['p99']):>12}"
            f"{fmt(row['max']):>14}"
            f"{row['unique_values']:>9}"
        )


def write_diagnostics(
    path,
    *,
    start_date,
    end_date,
    logs,
    summary,
):
    lines = []

    lines.append("FEEDIT STEP04 SCALING DIAGNOSTIC V2")
    lines.append("=" * 80)
    lines.append(f"PERIOD: {start_date} ~ {end_date}")
    lines.append("")
    lines.append("[COLLECTION]")
    lines.extend(logs)
    lines.append("")
    lines.append("[AUTOMATIC FLAGS]")

    flags = []

    for row in summary:
        name = (
            f"{row['dataset']} / "
            f"{row['source']} / "
            f"{row['metric']}"
        )

        if row["zero_rate_pct"] >= 80:
            flags.append(
                f"HIGH ZERO: {name} "
                f"zero={row['zero_rate_pct']:.2f}%"
            )

        if (
            row["max_over_p99"] is not None
            and row["max_over_p99"] >= 2
        ):
            flags.append(
                f"OUTLIER: {name} "
                f"max/p99={row['max_over_p99']:.2f}"
            )

        if row["unique_values"] <= 3:
            flags.append(
                f"TIE HEAVY: {name} "
                f"unique={row['unique_values']}"
            )

        if row["positive_count"] == 0:
            flags.append(
                f"ALL ZERO: {name}"
            )

    if flags:
        lines.extend(flags)
    else:
        lines.append("No automatic warning.")

    lines.append("")
    lines.append("[SCALING RULES TESTED]")
    lines.append("zero_minmax: zero stays 0; positive values min-max")
    lines.append("zero_log_minmax: zero stays 0; positive log1p then min-max")
    lines.append("positive_percentile: zero stays 0; percentile among positives only")
    lines.append("zero_percentile: same zero-preserving percentile candidate")
    lines.append("")
    lines.append("[IMPORTANT]")
    lines.append(
        "inventory_share_pct uses current ProductSource inventory only as a diagnostic denominator."
    )
    lines.append(
        "Do not adopt it as the final daily exposure denominator until STEP04 semantics are fixed."
    )
    lines.append(
        "Search monthly data is kept in its own monthly cohort and must not be added directly to daily raw counts."
    )

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ============================================================
# MAIN
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--days",
        type=int,
        default=28,
    )

    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="YYYY-MM-DD",
    )

    parser.add_argument(
        "--output-dir",
        default="metric_diagnostics_v2",
    )

    return parser.parse_args()


def infer_end_date():
    if TermMetricDaily is not None:
        fields = concrete_fields(TermMetricDaily)

        if "metric_date" in fields:
            latest = TermMetricDaily.objects.aggregate(
                value=Max("metric_date")
            )["value"]

            if latest is not None:
                return latest

    return date.today()


def main():
    args = parse_args()

    if args.days < 1:
        raise ValueError("--days must be >= 1")

    end_date = args.end_date or infer_end_date()
    start_date = end_date - timedelta(
        days=args.days - 1
    )

    print("=" * 100)
    print("FEEDIT STEP04 Scaling Diagnostic v2")
    print("=" * 100)
    print("기간:", start_date, "~", end_date)
    print("DB WRITE: NONE")
    print()

    logs = []

    source_totals = collect_product_source_totals(
        logs
    )

    observations = []

    observations.extend(
        collect_term_metric_daily(
            start_date,
            end_date,
            logs,
        )
    )

    observations.extend(
        collect_product_snapshots(
            start_date,
            end_date,
            logs,
        )
    )

    observations.extend(
        collect_content_snapshots(
            start_date,
            end_date,
            logs,
        )
    )

    observations.extend(
        collect_search(
            start_date,
            end_date,
            logs,
        )
    )

    for line in logs:
        print(line)

    if not observations:
        raise RuntimeError(
            "분석 가능한 observation이 없습니다. "
            "위 SKIP 로그에서 모델/날짜 필드를 확인하세요."
        )

    scaled = apply_scaling(
        observations,
        source_totals,
    )

    summary = summarize(
        observations
    )

    print_summary(summary)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_path = (
        output_dir
        / "step04_v2_source_summary.csv"
    )

    sample_path = (
        output_dir
        / "step04_v2_scaling_samples.csv"
    )

    totals_path = (
        output_dir
        / "step04_v2_source_totals.csv"
    )

    diagnostic_path = (
        output_dir
        / "step04_v2_diagnostics.txt"
    )

    write_csv(
        summary_path,
        summary,
    )

    write_csv(
        sample_path,
        choose_samples(scaled),
    )

    write_csv(
        totals_path,
        [
            {
                "source": source,
                "product_source_inventory": count,
            }
            for source, count
            in sorted(source_totals.items())
        ],
    )

    write_diagnostics(
        diagnostic_path,
        start_date=start_date,
        end_date=end_date,
        logs=logs,
        summary=summary,
    )

    print()
    print("=" * 100)
    print("DONE")
    print("=" * 100)
    print("SUMMARY    :", summary_path.resolve())
    print("SAMPLES    :", sample_path.resolve())
    print("TOTALS     :", totals_path.resolve())
    print("DIAGNOSTIC :", diagnostic_path.resolve())
    print("DB WRITE   : NONE")


if __name__ == "__main__":
    main()
