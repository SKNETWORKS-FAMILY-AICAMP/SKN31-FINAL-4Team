# analysis/metrics/search.py

from __future__ import annotations

from datetime import date
from math import log

import pandas as pd
from django.db import transaction

from apps.core.models import (
    DictionaryTerm,
    Source,
    TermAlias,
    TermSearchMetricMonthly,
)


SEARCH_METRIC_VERSION = "feedit-search-v1"


# ============================================================
# NORMALIZE
# ============================================================

def _normalize(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
    )


# ============================================================
# TERM MATCH
# ============================================================

def _find_term(
    *,
    keyword: str,
    term_type: str,
):
    keyword = str(
        keyword or ""
    ).strip()

    term_type = str(
        term_type or ""
    ).strip().upper()

    if not keyword:
        return None

    # 1. canonical
    term = (
        DictionaryTerm.objects
        .filter(
            canonical_name__iexact=keyword,
            term_type=term_type,
            status="ACTIVE",
        )
        .first()
    )

    if term:
        return term

    # 2. normalized
    term = (
        DictionaryTerm.objects
        .filter(
            normalized_name__iexact=_normalize(
                keyword
            ),
            term_type=term_type,
            status="ACTIVE",
        )
        .first()
    )

    if term:
        return term

    # 3. alias
    alias = (
        TermAlias.objects
        .select_related("term")
        .filter(
            alias__iexact=keyword,
            term__term_type=term_type,
            term__status="ACTIVE",
        )
        .first()
    )

    if alias:
        return alias.term

    return None


# ============================================================
# SOURCE MATCH
# ============================================================

def _find_source(
    platform: str,
):
    platform = str(
        platform or ""
    ).strip()

    return (
        Source.objects
        .filter(
            code__iexact=platform
        )
        .first()
    )


# ============================================================
# CSV IMPORT
# ============================================================

@transaction.atomic
def import_search_volume_csv(
    csv_path: str,
    *,
    metric_month: date,
    metric_version: str = SEARCH_METRIC_VERSION,
) -> dict:

    df = pd.read_csv(
        csv_path
    )

    required = {
        "keyword",
        "term_type",
        "platform",
        "total_search_volume",
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"CSV missing columns: {sorted(missing)}"
        )

    saved = 0

    skipped = []

    for row in df.to_dict(
        "records"
    ):

        keyword = str(
            row.get("keyword")
            or ""
        ).strip()

        term_type = str(
            row.get("term_type")
            or ""
        ).strip().upper()

        platform = str(
            row.get("platform")
            or ""
        ).strip().lower()

        try:
            volume = int(
                float(
                    row.get(
                        "total_search_volume"
                    )
                    or 0
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            volume = 0

        # --------------------------------------------
        # TERM
        # --------------------------------------------

        term = _find_term(
            keyword=keyword,
            term_type=term_type,
        )

        if term is None:
            skipped.append(
                {
                    "keyword": keyword,
                    "term_type": term_type,
                    "platform": platform,
                    "reason": "TERM_NOT_FOUND",
                }
            )

            continue

        # --------------------------------------------
        # SOURCE
        # --------------------------------------------

        source = _find_source(
            platform
        )

        if source is None:
            skipped.append(
                {
                    "keyword": keyword,
                    "term_type": term_type,
                    "platform": platform,
                    "reason": "SOURCE_NOT_FOUND",
                }
            )

            continue

        # --------------------------------------------
        # SAVE
        # --------------------------------------------

        TermSearchMetricMonthly.objects.update_or_create(
            term=term,
            source=source,
            metric_month=metric_month,
            metric_version=metric_version,

            defaults={
                "search_volume": volume,

                "log_volume": round(
                    log(
                        1
                        + max(
                            0,
                            volume,
                        )
                    ),
                    6,
                ),

                "data_type": str(
                    row.get(
                        "data_type"
                    )
                    or "monthly_absolute"
                ),
            },
        )

        saved += 1

    return {
        "metric_month": str(
            metric_month
        ),

        "saved": saved,

        "skipped": len(
            skipped
        ),

        "skipped_rows": skipped,
    }


# ============================================================
# PERCENTILE
# ============================================================

@transaction.atomic
def normalize_search_percentiles(
    *,
    metric_month: date,
    metric_version: str = SEARCH_METRIC_VERSION,
) -> dict:
    """
    Google / Naver를 서로 섞지 않고
    플랫폼 내부 percentile 계산.
    """

    source_ids = (
        TermSearchMetricMonthly.objects
        .filter(
            metric_month=metric_month,
            metric_version=metric_version,
        )
        .values_list(
            "source_id",
            flat=True,
        )
        .distinct()
    )

    updated = 0

    for source_id in source_ids:

        rows = list(
            TermSearchMetricMonthly.objects
            .filter(
                metric_month=metric_month,
                metric_version=metric_version,
                source_id=source_id,
            )
            .order_by(
                "log_volume",
                "id",
            )
        )

        n = len(
            rows
        )

        if n == 0:
            continue

        if n == 1:

            row = rows[0]

            row.percentile = 100

            row.save(
                update_fields=[
                    "percentile",
                    "updated_at",
                ]
            )

            updated += 1

            continue

        # --------------------------------------------
        # tie-aware percentile
        # --------------------------------------------

        i = 0

        while i < n:

            j = i + 1

            current = float(
                rows[i].log_volume
                or 0
            )

            while (
                j < n
                and float(
                    rows[j].log_volume
                    or 0
                )
                == current
            ):
                j += 1

            avg_rank = (
                i
                + j
                - 1
            ) / 2

            percentile = (
                100.0
                * avg_rank
                / (n - 1)
            )

            for k in range(
                i,
                j,
            ):

                rows[k].percentile = round(
                    percentile,
                    4,
                )

                rows[k].save(
                    update_fields=[
                        "percentile",
                        "updated_at",
                    ]
                )

                updated += 1

            i = j

    return {
        "updated": updated,
    }


# ============================================================
# FULL SEARCH IMPORT
# ============================================================

def run_search_metric_import(
    csv_path: str,
    *,
    metric_month: date,
    metric_version: str = SEARCH_METRIC_VERSION,
) -> dict:

    imported = (
        import_search_volume_csv(
            csv_path,
            metric_month=metric_month,
            metric_version=metric_version,
        )
    )

    normalized = (
        normalize_search_percentiles(
            metric_month=metric_month,
            metric_version=metric_version,
        )
    )

    return {
        "import": imported,
        "normalize": normalized,
    }