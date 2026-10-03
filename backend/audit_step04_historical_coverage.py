from __future__ import annotations

"""
FEEDIT STEP04 Historical Coverage Audit

목적
----
기존 TermMetricDaily의 오래된 날짜가 실제 과거 반응 작성일
(ProductReview.source_created_at / TextDocument.analysis_metadata.published_at 등)
때문인지 확인하고, STEP04를 어느 날짜까지 원천 데이터에서 재계산할 수 있는지 진단한다.

DB WRITE: NONE

실행
----
cd C:\feedit\backend
python audit_step04_historical_coverage.py

출력
----
step04_history_audit/
    step04_history_daily_coverage.csv
    step04_history_monthly_coverage.csv
    step04_history_metric_versions.csv
    step04_history_summary.txt
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.apps import apps
from django.db import connection
from django.db.models import Count, Min, Max


def find_model(*names):
    wanted = {x.lower() for x in names}
    for model in apps.get_models():
        if model.__name__.lower() in wanted:
            return model
    return None


TermMetricDaily = find_model("TermMetricDaily")
ProductReview = find_model("ProductReview")
TextDocument = find_model("TextDocument")
TextTermMention = find_model("TextTermMention")
ProductSourceSnapshot = find_model("ProductSourceSnapshot")
ContentSnapshot = find_model("ContentSnapshot")
TermSearchMetricMonthly = find_model("TermSearchMetricMonthly")


def concrete_fields(model):
    if model is None:
        return {}
    return {
        f.name: f
        for f in model._meta.get_fields()
        if getattr(f, "concrete", False)
    }


def table_name(model):
    return model._meta.db_table if model else None


def qident(name):
    return connection.ops.quote_name(name)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def fetch(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def add_daily(bucket, source_name, rows, date_key="day", count_key="n"):
    for row in rows:
        day = row.get(date_key)
        if isinstance(day, datetime):
            day = day.date()
        if not day:
            continue
        bucket[day][source_name] += int(row.get(count_key) or 0)


def django_date_expr(field):
    return f"DATE({qident(field)})"


def collect_metric_versions(logs):
    if TermMetricDaily is None:
        logs.append("SKIP TermMetricDaily: model not found")
        return []
    rows = list(
        TermMetricDaily.objects
        .values("metric_version")
        .annotate(
            rows=Count("id"),
            first_date=Min("metric_date"),
            last_date=Max("metric_date"),
        )
        .order_by("metric_version")
    )
    logs.append(f"OK TermMetricDaily versions: {len(rows)}")
    return rows


def collect_reviews(bucket, logs):
    """
    ProductReview의 실제 작성일을 우선 사용한다.
    STEP03 validator에서 사용하던 기준: source_created_at.
    """
    if ProductReview is None:
        logs.append("SKIP ProductReview: model not found")
        return

    fields = concrete_fields(ProductReview)
    date_field = next(
        (x for x in ("source_created_at", "created_at", "reviewed_at")
         if x in fields),
        None,
    )
    if not date_field:
        logs.append("SKIP ProductReview: no usable date field")
        return

    table = qident(table_name(ProductReview))
    rows = fetch(f"""
        SELECT {django_date_expr(date_field)} AS day,
               COUNT(*) AS n
        FROM {table}
        WHERE {qident(date_field)} IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)
    add_daily(bucket, "review_rows", rows)
    logs.append(
        f"OK ProductReview ({date_field}): "
        f"{sum(int(r['n']) for r in rows):,} rows / {len(rows):,} days"
    )


def collect_text_documents(bucket, logs):
    """
    TextDocument의 경우:
    1) analysis_metadata.published_at JSON timestamp가 있으면 작성일 기준
    2) 없으면 모델의 published_at/source_created_at 계열 필드
    3) created_at은 별도 ingestion 날짜이므로 최후 fallback만 사용

    PostgreSQL JSON extraction을 우선 시도한다.
    """
    if TextDocument is None:
        logs.append("SKIP TextDocument: model not found")
        return

    fields = concrete_fields(TextDocument)
    table = qident(table_name(TextDocument))

    if "analysis_metadata" in fields:
        try:
            rows = fetch(f"""
                SELECT
                    DATE(
                        NULLIF(
                            {qident("analysis_metadata")} ->> 'published_at',
                            ''
                        )::timestamptz
                    ) AS day,
                    COUNT(*) AS n
                FROM {table}
                WHERE NULLIF(
                    {qident("analysis_metadata")} ->> 'published_at',
                    ''
                ) IS NOT NULL
                GROUP BY 1
                ORDER BY 1
            """)
            add_daily(bucket, "text_document_published", rows)
            logs.append(
                "OK TextDocument analysis_metadata.published_at: "
                f"{sum(int(r['n']) for r in rows):,} rows / {len(rows):,} days"
            )
        except Exception as exc:
            logs.append(
                "WARN TextDocument JSON published_at query failed: "
                f"{type(exc).__name__}: {exc}"
            )

    direct = next(
        (x for x in ("published_at", "source_created_at", "posted_at")
         if x in fields),
        None,
    )
    if direct:
        rows = fetch(f"""
            SELECT {django_date_expr(direct)} AS day,
                   COUNT(*) AS n
            FROM {table}
            WHERE {qident(direct)} IS NOT NULL
            GROUP BY 1
            ORDER BY 1
        """)
        add_daily(bucket, "text_document_direct_date", rows)
        logs.append(
            f"OK TextDocument {direct}: "
            f"{sum(int(r['n']) for r in rows):,} rows / {len(rows):,} days"
        )

    if "created_at" in fields:
        rows = fetch(f"""
            SELECT {django_date_expr("created_at")} AS day,
                   COUNT(*) AS n
            FROM {table}
            WHERE {qident("created_at")} IS NOT NULL
            GROUP BY 1
            ORDER BY 1
        """)
        add_daily(bucket, "text_document_ingested", rows)
        logs.append(
            "OK TextDocument created_at (ingestion reference only): "
            f"{sum(int(r['n']) for r in rows):,} rows / {len(rows):,} days"
        )


def collect_mentions(bucket, logs):
    """
    Mention 자체의 작성일이 아니라 연결된 TextDocument의 작성일을 사용.
    TextTermMention -> TextDocument FK 이름을 자동 탐색한다.
    """
    if TextTermMention is None or TextDocument is None:
        logs.append("SKIP TextTermMention coverage: model missing")
        return

    mention_fields = concrete_fields(TextTermMention)
    doc_fields = concrete_fields(TextDocument)

    fk = None
    for field in TextTermMention._meta.get_fields():
        if (
            getattr(field, "is_relation", False)
            and getattr(field, "many_to_one", False)
            and getattr(field, "related_model", None) is TextDocument
        ):
            fk = field
            break

    if fk is None:
        logs.append("SKIP TextTermMention: TextDocument FK not found")
        return

    mt = qident(table_name(TextTermMention))
    dt = qident(table_name(TextDocument))
    fk_col = qident(fk.column)
    doc_pk_col = qident(TextDocument._meta.pk.column)

    if "analysis_metadata" in doc_fields:
        try:
            rows = fetch(f"""
                SELECT
                    DATE(
                        NULLIF(
                            d.{qident("analysis_metadata")} ->> 'published_at',
                            ''
                        )::timestamptz
                    ) AS day,
                    COUNT(*) AS n
                FROM {mt} m
                JOIN {dt} d
                  ON m.{fk_col} = d.{doc_pk_col}
                WHERE NULLIF(
                    d.{qident("analysis_metadata")} ->> 'published_at',
                    ''
                ) IS NOT NULL
                GROUP BY 1
                ORDER BY 1
            """)
            add_daily(bucket, "term_mentions_by_published_date", rows)
            logs.append(
                "OK TextTermMention by document published_at: "
                f"{sum(int(r['n']) for r in rows):,} mentions / {len(rows):,} days"
            )
            return
        except Exception as exc:
            logs.append(
                "WARN mention published_at query failed: "
                f"{type(exc).__name__}: {exc}"
            )

    direct = next(
        (x for x in ("published_at", "source_created_at", "posted_at", "created_at")
         if x in doc_fields),
        None,
    )
    if direct:
        rows = fetch(f"""
            SELECT DATE(d.{qident(direct)}) AS day,
                   COUNT(*) AS n
            FROM {mt} m
            JOIN {dt} d
              ON m.{fk_col} = d.{doc_pk_col}
            WHERE d.{qident(direct)} IS NOT NULL
            GROUP BY 1
            ORDER BY 1
        """)
        add_daily(bucket, "term_mentions_by_document_date", rows)
        logs.append(
            f"OK TextTermMention by TextDocument.{direct}: "
            f"{sum(int(r['n']) for r in rows):,} mentions / {len(rows):,} days"
        )


def collect_simple_model_dates(model, label, candidates, bucket, logs):
    if model is None:
        logs.append(f"SKIP {label}: model not found")
        return

    fields = concrete_fields(model)
    field = next((x for x in candidates if x in fields), None)
    if not field:
        logs.append(f"SKIP {label}: no usable date field")
        return

    table = qident(table_name(model))
    f = fields[field]

    if f.get_internal_type() == "DateField":
        expr = qident(field)
    else:
        expr = django_date_expr(field)

    rows = fetch(f"""
        SELECT {expr} AS day, COUNT(*) AS n
        FROM {table}
        WHERE {qident(field)} IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)
    add_daily(bucket, label, rows)
    logs.append(
        f"OK {label} ({field}): "
        f"{sum(int(r['n']) for r in rows):,} rows / {len(rows):,} days"
    )


def collect_search_months(logs):
    if TermSearchMetricMonthly is None:
        logs.append("SKIP TermSearchMetricMonthly: model not found")
        return []

    fields = concrete_fields(TermSearchMetricMonthly)
    month_field = next(
        (x for x in ("metric_month", "month", "date") if x in fields),
        None,
    )
    if not month_field:
        logs.append("SKIP TermSearchMetricMonthly: month field not found")
        return []

    qs = (
        TermSearchMetricMonthly.objects
        .values(month_field)
        .annotate(rows=Count("id"))
        .order_by(month_field)
    )
    rows = []
    for row in qs:
        month = row[month_field]
        if isinstance(month, datetime):
            month = month.date()
        rows.append({
            "month": str(month)[:7],
            "search_rows": row["rows"],
        })
    logs.append(f"OK TermSearchMetricMonthly: {sum(r['search_rows'] for r in rows):,} rows")
    return rows


def collect_metric_daily(bucket, logs):
    if TermMetricDaily is None:
        return

    rows = (
        TermMetricDaily.objects
        .values("metric_date")
        .annotate(n=Count("id"))
        .order_by("metric_date")
    )
    for row in rows.iterator(chunk_size=2000):
        bucket[row["metric_date"]]["legacy_metric_rows"] += row["n"]


def build_daily_rows(bucket):
    if not bucket:
        return []

    keys = sorted({
        key
        for values in bucket.values()
        for key in values
    })

    rows = []
    for day in sorted(bucket):
        values = bucket[day]
        row = {"date": day.isoformat()}
        for key in keys:
            row[key] = int(values.get(key, 0))

        # STEP04 재계산 가능성 힌트.
        reaction = (
            row.get("review_rows", 0)
            + row.get("term_mentions_by_published_date", 0)
            + row.get("term_mentions_by_document_date", 0)
        )
        commerce = row.get("product_snapshot_rows", 0)
        content = row.get("content_snapshot_rows", 0)

        row["has_reaction_source"] = int(reaction > 0)
        row["has_commerce_source"] = int(commerce > 0)
        row["has_content_source"] = int(content > 0)
        row["available_signal_families"] = (
            int(reaction > 0)
            + int(commerce > 0)
            + int(content > 0)
        )
        rows.append(row)

    return rows


def build_monthly_rows(daily_rows, search_rows):
    bucket = defaultdict(lambda: defaultdict(int))

    for row in daily_rows:
        month = row["date"][:7]
        for key, value in row.items():
            if key == "date":
                continue
            if isinstance(value, (int, float)):
                bucket[month][key] += value

    search_map = defaultdict(int)
    for row in search_rows:
        search_map[row["month"]] += row["search_rows"]

    output = []
    for month in sorted(set(bucket) | set(search_map)):
        data = bucket[month]
        output.append({
            "month": month,
            "review_rows": data.get("review_rows", 0),
            "term_mentions_by_published_date": data.get(
                "term_mentions_by_published_date", 0
            ),
            "text_document_published": data.get(
                "text_document_published", 0
            ),
            "product_snapshot_rows": data.get(
                "product_snapshot_rows", 0
            ),
            "content_snapshot_rows": data.get(
                "content_snapshot_rows", 0
            ),
            "search_rows": search_map.get(month, 0),
            "legacy_metric_rows": data.get(
                "legacy_metric_rows", 0
            ),
            "days_with_reaction": data.get(
                "has_reaction_source", 0
            ),
            "days_with_commerce": data.get(
                "has_commerce_source", 0
            ),
            "days_with_content": data.get(
                "has_content_source", 0
            ),
        })

    return output


def span(rows, date_key, count_keys):
    active = []
    for row in rows:
        if any(int(row.get(k, 0) or 0) > 0 for k in count_keys):
            active.append(row[date_key])
    if not active:
        return None, None
    return min(active), max(active)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="step04_history_audit",
    )
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    logs = []
    bucket = defaultdict(lambda: defaultdict(int))

    versions = collect_metric_versions(logs)
    collect_metric_daily(bucket, logs)

    collect_reviews(bucket, logs)
    collect_text_documents(bucket, logs)
    collect_mentions(bucket, logs)

    collect_simple_model_dates(
        ProductSourceSnapshot,
        "product_snapshot_rows",
        ("observed_at", "snapshot_at", "collected_at", "created_at", "metric_date"),
        bucket,
        logs,
    )
    collect_simple_model_dates(
        ContentSnapshot,
        "content_snapshot_rows",
        ("observed_at", "snapshot_at", "collected_at", "created_at", "metric_date"),
        bucket,
        logs,
    )

    search_rows = collect_search_months(logs)

    daily = build_daily_rows(bucket)
    monthly = build_monthly_rows(daily, search_rows)

    version_rows = []
    for row in versions:
        version_rows.append({
            "metric_version": row["metric_version"],
            "rows": row["rows"],
            "first_date": row["first_date"],
            "last_date": row["last_date"],
        })

    write_csv(
        out / "step04_history_daily_coverage.csv",
        daily,
    )
    write_csv(
        out / "step04_history_monthly_coverage.csv",
        monthly,
    )
    write_csv(
        out / "step04_history_metric_versions.csv",
        version_rows,
    )

    reaction_first, reaction_last = span(
        daily,
        "date",
        (
            "review_rows",
            "term_mentions_by_published_date",
            "term_mentions_by_document_date",
        ),
    )
    commerce_first, commerce_last = span(
        daily,
        "date",
        ("product_snapshot_rows",),
    )
    content_first, content_last = span(
        daily,
        "date",
        ("content_snapshot_rows",),
    )

    summary = [
        "FEEDIT STEP04 HISTORICAL COVERAGE AUDIT",
        "=" * 80,
        "",
        "[COLLECTION]",
        *logs,
        "",
        "[SOURCE DATE SPANS]",
        f"REACTION : {reaction_first or '-'} ~ {reaction_last or '-'}",
        f"COMMERCE : {commerce_first or '-'} ~ {commerce_last or '-'}",
        f"CONTENT  : {content_first or '-'} ~ {content_last or '-'}",
        "",
        "[INTERPRETATION]",
        "ProductReview는 source_created_at을 우선 사용합니다.",
        "TextTermMention은 mention 생성일이 아니라 연결된 TextDocument의 published_at을 우선 사용합니다.",
        "TextDocument.created_at은 ingestion 시각 참고용이며 과거 반응 작성일로 간주하지 않습니다.",
        "오래된 날짜에 reaction 원천이 실제 존재하면 legacy metric의 과거 날짜는 정상일 가능성이 높습니다.",
        "STEP04는 해당 날짜에 존재하는 signal family만 사용하고 missing family를 0점 처리하면 안 됩니다.",
        "",
        "[DB WRITE]",
        "NONE",
    ]
    (out / "step04_history_summary.txt").write_text(
        "\n".join(summary),
        encoding="utf-8",
    )

    print("=" * 100)
    print("FEEDIT STEP04 HISTORICAL COVERAGE AUDIT")
    print("=" * 100)
    for line in logs:
        print(line)

    print()
    print("REACTION :", reaction_first, "~", reaction_last)
    print("COMMERCE :", commerce_first, "~", commerce_last)
    print("CONTENT  :", content_first, "~", content_last)
    print()
    print("OUTPUT:", out.resolve())
    print("DB WRITE: NONE")


if __name__ == "__main__":
    main()
