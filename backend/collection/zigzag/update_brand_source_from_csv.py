from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

# ============================================================
# DJANGO BOOTSTRAP
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

import django

django.setup()


from django.db import transaction
from django.db.models import Q

from apps.core.models import (
    BrandSource,
    Source,
    Style,
)
DEFAULT_CSV = Path(
    r"C:\SKN31-FINAL-4Team\backend\zigzag_store_profiles.csv"
)
# ============================================================
# HELPERS
# ============================================================

def clean(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def parse_json_value(value):
    """
    CSV에 JSON string으로 저장된 list/dict 복구.
    예:
        ["캐주얼", "러블리"]
        {"a": 1}
    """
    value = clean(value)

    if not value:
        return None

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def parse_int(value):
    value = clean(value)

    if value is None:
        return None

    try:
        return int(float(value.replace(",", "")))
    except (TypeError, ValueError):
        return None


def match_styles(style_names):
    if not isinstance(style_names, list):
        return []

    style_names = [
        clean(x)
        for x in style_names
        if clean(x)
    ]

    if not style_names:
        return []

    query = Q()

    for name in style_names:
        query |= Q(
            term__canonical_name__iexact=name
        )
        query |= Q(
            term__english_name__iexact=name
        )

    return list(
        Style.objects
        .select_related("term")
        .filter(query)
        .distinct()
    )


# ============================================================
# UPDATE
# ============================================================

@transaction.atomic
def update_brand_source(
    *,
    source,
    row,
):
    source_brand_id = clean(
        row.get("source_brand_id")
    )

    if not source_brand_id:
        return {
            "status": "SKIP",
            "reason": "NO_SOURCE_BRAND_ID",
        }

    brand_source = (
        BrandSource.objects
        .select_related(
            "source",
            "brand",
        )
        .filter(
            source=source,
            source_brand_id=source_brand_id,
        )
        .first()
    )

    if brand_source is None:
        return {
            "status": "NOT_FOUND",
            "source_brand_id": source_brand_id,
        }

    changed_fields = []

    # --------------------------------------------------------
    # SCALAR FIELDS
    # --------------------------------------------------------

    name = clean(
        row.get("name")
    )

    english_name = clean(
        row.get("english_name")
    )

    image_url = clean(
        row.get("image_url")
    )

    description = clean(
        row.get("description")
    )

    source_profile_url = clean(
        row.get("source_profile_url")
    )

    target_age = parse_json_value(
        row.get("target_age")
    )

    # english_name 무조건 대문자
    if english_name:
        english_name = english_name.upper()

    scalar_values = {
        "name": name,
        "english_name": english_name,
        "image_url": image_url,
        "description": description,
        "source_profile_url": source_profile_url,
        "target_age": target_age,
    }

    for field, value in scalar_values.items():

        if value in (
            None,
            "",
            [],
            {},
        ):
            continue

        current = getattr(
            brand_source,
            field,
            None,
        )

        if current != value:
            setattr(
                brand_source,
                field,
                value,
            )

            changed_fields.append(
                field
            )

    # --------------------------------------------------------
    # ATTRIBUTES
    # --------------------------------------------------------

    attrs = (
        dict(brand_source.attributes)
        if isinstance(
            brand_source.attributes,
            dict,
        )
        else {}
    )

    attr_changed = False

    main_domain = clean(
        row.get("main_domain")
    )

    style_list = parse_json_value(
        row.get("style_list")
    )

    bookmark_count = parse_int(
        row.get("bookmark_count")
    )

    seller_badges = parse_json_value(
        row.get("seller_badges")
    )

    total_product_count = parse_int(
        row.get("total_product_count")
    )

    csv_attrs = {
        "main_domain": main_domain,
        "style_list": style_list,
        "bookmark_count": bookmark_count,
        "seller_badges": seller_badges,
        "total_product_count": (
            total_product_count
        ),
    }

    for key, value in csv_attrs.items():

        if value in (
            None,
            "",
            [],
            {},
        ):
            continue

        if attrs.get(key) != value:
            attrs[key] = value
            attr_changed = True

    if attr_changed:
        brand_source.attributes = attrs

        changed_fields.append(
            "attributes"
        )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    if changed_fields:

        if hasattr(
            brand_source,
            "updated_at",
        ):
            changed_fields.append(
                "updated_at"
            )

        brand_source.save(
            update_fields=list(
                dict.fromkeys(
                    changed_fields
                )
            )
        )

    # --------------------------------------------------------
    # STYLE M2M
    # --------------------------------------------------------

    matched_styles = []

    if isinstance(
        style_list,
        list,
    ):
        matched_styles = match_styles(
            style_list
        )

        if (
            matched_styles
            and hasattr(
                brand_source,
                "styles",
            )
        ):
            # 기존 styles 유지 + 신규 추가
            brand_source.styles.add(
                *matched_styles
            )

    return {
        "status": (
            "UPDATED"
            if changed_fields
            else "UNCHANGED"
        ),
        "brand_source_id":
            brand_source.id,
        "source_brand_id":
            source_brand_id,
        "name":
            brand_source.name,
        "english_name":
            brand_source.english_name,
        "changed_fields":
            changed_fields,
        "matched_style_count":
            len(matched_styles),
    }


# ============================================================
# MAIN
# ============================================================

def main(
    csv_path: str | Path = DEFAULT_CSV,
):
    csv_path = Path(
        csv_path
    )

    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV 없음: {csv_path}"
        )

    source = Source.objects.get(
        code__iexact="zigzag"
    )

    summary = {
        "total": 0,
        "updated": 0,
        "unchanged": 0,
        "not_found": 0,
        "skipped": 0,
        "failed": 0,
    }

    errors = []

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as fp:

        reader = csv.DictReader(
            fp
        )

        for index, row in enumerate(
            reader,
            start=1,
        ):
            summary["total"] += 1

            try:
                result = (
                    update_brand_source(
                        source=source,
                        row=row,
                    )
                )

                status = result[
                    "status"
                ]

                if status == "UPDATED":
                    summary[
                        "updated"
                    ] += 1

                elif status == "UNCHANGED":
                    summary[
                        "unchanged"
                    ] += 1

                elif status == "NOT_FOUND":
                    summary[
                        "not_found"
                    ] += 1

                else:
                    summary[
                        "skipped"
                    ] += 1

                if (
                    status == "UPDATED"
                    or index % 100 == 0
                ):
                    print(
                        f"[{index}]",
                        result,
                    )

            except Exception as exc:
                summary[
                    "failed"
                ] += 1

                errors.append(
                    {
                        "row": index,
                        "source_brand_id":
                            row.get(
                                "source_brand_id"
                            ),
                        "error_type":
                            exc.__class__.__name__,
                        "error":
                            str(exc),
                    }
                )

                print(
                    f"[{index}] FAILED",
                    row.get(
                        "source_brand_id"
                    ),
                    exc,
                )

    print()
    print(
        "=============================="
    )
    print(
        "ZIGZAG BRAND SOURCE UPDATE DONE"
    )
    print(
        "=============================="
    )

    print(
        summary
    )

    if errors:
        print()
        print(
            "ERROR SAMPLE"
        )

        for error in errors[:20]:
            print(error)


if __name__ == "__main__":

    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else DEFAULT_CSV
    )

    main(path)