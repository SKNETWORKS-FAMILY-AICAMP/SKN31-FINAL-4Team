from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlencode


BASE_DIR = (
    Path(__file__)
    .resolve()
    .parents[2]
)

if str(BASE_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(BASE_DIR),
    )


os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)


import django

django.setup()


from apps.core.models import (
    CrawlTarget,
    Source,
)

from collection.musinsa_used_v2.filter_collector import (
    MusinsaUsedFilterCollector,
)

from collection.musinsa_used_v2.filter_config import (
    API_URL,
    CATEGORY_MAP,
    DEFAULT_LIMIT,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_CODE,
    FILTER_TYPES,
)


# ============================================================
# TARGET URL
# ============================================================


def _build_url(
    *,
    gender: str,
    parameter: str,
    value: str,
    sort_code: str,
    category_id: str,
) -> str:

    return (
        API_URL
        + "?"
        + urlencode(
            {
                "gf": gender,
                parameter: value,
                "sortCode": sort_code,
                "category": category_id,
                "size": DEFAULT_PAGE_SIZE,
                "testGroup": "",
                "ampGroup": "",
                "caller": "CATEGORY",
                "page": 1,
                "seen": 0,
                "seenAds": "",
            }
        )
    )


# ============================================================
# MAIN
# ============================================================


def main():

    parser = argparse.ArgumentParser()

    # --------------------------------------------------------
    # FILTER TYPES
    # --------------------------------------------------------

    parser.add_argument(
        "--filter-types",
        nargs="+",
        default=[
            "all",
        ],
        choices=[
            "all",
            *FILTER_TYPES,
        ],
        help=(
            "기본 all. "
            "예: --filter-types "
            "material pattern fit color"
        ),
    )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(
            CATEGORY_MAP
        ),
        choices=sorted(
            CATEGORY_MAP
        ),
    )

    # --------------------------------------------------------
    # ETC
    # --------------------------------------------------------

    parser.add_argument(
        "--gender",
        default="A",
        choices=[
            "A",
            "M",
            "F",
        ],
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
    )

    parser.add_argument(
        "--sort-code",
        default=DEFAULT_SORT_CODE,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    # ========================================================
    # SELECT FILTER TYPES
    # ========================================================

    selected_types = set(
        args.filter_types
    )

    if "all" in selected_types:
        selected_types = set(
            FILTER_TYPES
        )

    print(
        "SELECTED FILTER TYPES:",
        sorted(
            selected_types
        ),
    )

    # ========================================================
    # SOURCE
    # ========================================================

    source = (
        Source.objects.get(
            code__iexact="musinsa_used"
        )
    )

    # ========================================================
    # MODEL FIELD COMPATIBILITY
    # ========================================================

    fields = {
        field.name
        for field
        in CrawlTarget._meta.fields
    }

    name_field = (
        "name"
        if "name" in fields
        else "display_name"
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = {
        "categories": 0,
        "metadata": 0,
        "selected": 0,
        "created": 0,
        "updated": 0,
    }

    # ========================================================
    # COLLECT FILTER METADATA
    # ========================================================

    with MusinsaUsedFilterCollector() as collector:

        for category_name in (
            args.categories
        ):

            category_id = (
                CATEGORY_MAP[
                    category_name
                ]
            )

            summary[
                "categories"
            ] += 1

            print()
            print(
                "=" * 90
            )

            print(
                "CATEGORY",
                category_name,
                category_id,
            )

            # ------------------------------------------------
            # 1. CATEGORY PAGE SSR FILTER RAW
            # ------------------------------------------------

            try:
                raw_metadata = (
                    collector
                    .collect_filter_metadata(
                        category_id=(
                            category_id
                        ),
                    )
                )

            except Exception as exc:

                print(
                    "FILTER METADATA ERROR:",
                    type(exc).__name__,
                    str(exc),
                )

                continue

            # ------------------------------------------------
            # 2. RAW -> NORMALIZED FILTER OPTIONS
            # ------------------------------------------------

            metadata = (
                collector
                .extract_filter_metadata(
                    raw_metadata
                )
            )

            summary[
                "metadata"
            ] += len(
                metadata
            )

            print(
                "ALL METADATA:",
                len(metadata),
            )

            # ------------------------------------------------
            # 3. SELECT FILTER TYPES
            # ------------------------------------------------

            selected_metadata = [
                item
                for item
                in metadata
                if (
                    item.get(
                        "filter_type"
                    )
                    in selected_types
                )
            ]

            summary[
                "selected"
            ] += len(
                selected_metadata
            )

            print(
                "FILTER OPTIONS:",
                len(
                    selected_metadata
                ),
            )

            if not selected_metadata:

                print(
                    "WARN: 선택한 필터 메타가 "
                    "없습니다."
                )

                continue

            # ------------------------------------------------
            # 4. TARGET CREATE / UPDATE
            # ------------------------------------------------

            for item in (
                selected_metadata
            ):

                filter_type = (
                    item[
                        "filter_type"
                    ]
                )

                filter_label = (
                    item[
                        "filter_label"
                    ]
                )

                filter_name = (
                    item[
                        "filter_name"
                    ]
                )

                parameter = (
                    item[
                        "filter_parameter"
                    ]
                )

                filter_value = (
                    item[
                        "filter_value"
                    ]
                )

                # --------------------------------------------
                # TARGET NAME
                # --------------------------------------------

                name = (
                    "musinsa_used "
                    "[FILTER>"
                    f"{filter_label}>"
                    f"{filter_name}>"
                    f"{category_name}]"
                )

                # --------------------------------------------
                # URL
                # --------------------------------------------

                url = _build_url(
                    gender=args.gender,
                    parameter=parameter,
                    value=filter_value,
                    sort_code=(
                        args.sort_code
                    ),
                    category_id=(
                        category_id
                    ),
                )

                # --------------------------------------------
                # PARAMS
                # --------------------------------------------

                params = {
                    "observation_type":
                        "FILTER",

                    "filter_type":
                        filter_type,

                    "filter_label":
                        filter_label,

                    "filter_name":
                        filter_name,

                    "filter_parameter":
                        parameter,

                    "filter_value":
                        filter_value,

                    "category_id":
                        category_id,

                    "category_name":
                        category_name,

                    "gender":
                        args.gender,

                    "sort_code":
                        args.sort_code,

                    "page_size":
                        DEFAULT_PAGE_SIZE,

                    "limit":
                        args.limit,

                    "live":
                        True,
                }

                # --------------------------------------------
                # DRY RUN
                # --------------------------------------------

                if args.dry_run:

                    print(
                        "DRY",
                        filter_type,
                        name,
                    )

                    continue

                # --------------------------------------------
                # CRAWL TARGET
                # --------------------------------------------

                values = {
                    "target_type":
                        "RANKING",

                    "target_url":
                        url,

                    "params":
                        params,

                    "collection_mode":
                        "LIVE",

                    "interval_minutes":
                        1440,

                    "priority":
                        5,

                    "is_active":
                        True,
                }

                # 프로젝트 버전별
                # CrawlTarget field 차이 대응
                defaults = {
                    key: value
                    for key, value
                    in values.items()
                    if key in fields
                }

                obj, created = (
                    CrawlTarget
                    .objects
                    .update_or_create(
                        source=source,
                        **{
                            name_field:
                                name,
                        },
                        defaults=(
                            defaults
                        ),
                    )
                )

                summary[
                    (
                        "created"
                        if created
                        else "updated"
                    )
                ] += 1

                print(
                    (
                        "CREATED"
                        if created
                        else "UPDATED"
                    ),
                    obj.id,
                    name,
                )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print(
        "=" * 90
    )

    print(
        "SUMMARY",
        summary,
    )


# ============================================================
# ENTRYPOINT
# ============================================================


if __name__ == "__main__":
    main()