from __future__ import annotations

"""
Zigzag BrandSource STORE profile backfill.

목적
------------------------------------------------------------
BrandSource.source_brand_id(shop_id)를 기준으로 Zigzag STORE 프로필을 보강한다.

수집/보강 필드
- name
- english_name
- image_url
- description
- target_age
- source_profile_url
- main_domain
- style_list
- bookmark_count
- seller_badges
- total_product_count

조회 순서
------------------------------------------------------------
1. BrandSource.attributes["main_domain"]이 있으면 STORE 페이지 직접 조회
2. 없으면 해당 BrandSource의 대표 ProductSource.product_url 1건 조회
   -> 상품 상세에서 main_domain 복구
3. https://zigzag.kr/{main_domain}
   -> collect_shop(..., collect_products=False)
4. CSV 저장
5. --update-db 사용 시 BrandSource 보강

중요
------------------------------------------------------------
- Brand / mapping_status / mapping_method / mapping_confidence는 건드리지 않는다.
- detected_count도 증가시키지 않는다. 이건 "재관측"이 아니라 "프로필 보강"이다.
- 기존 값은 새 값이 비어 있으면 유지한다.

실행 예시
------------------------------------------------------------
# 20개만 미리보기 (DB 수정 안 함)
python zigzag_store_profile_backfill.py --limit 20

# 실제 DB 반영
python zigzag_store_profile_backfill.py --limit 100 --update-db

# 특정 shop_id만
python zigzag_store_profile_backfill.py --shop-ids 202,25938,991 --update-db

# Brand 미승격(brand is null)만
python zigzag_store_profile_backfill.py --only-unmapped --update-db

# english_name/image_url 등이 비어있는 대상만
python zigzag_store_profile_backfill.py --missing-only --update-db
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)
import django  # noqa: E402

django.setup()

from django.db.models import Q  # noqa: E402

from apps.core.models import (  # noqa: E402
    BrandSource,
    ProductSource,
    Source,
    Style,
)

try:
    from collection.zigzag.store_collector import ZigzagStoreCollector  # noqa: E402
except ImportError as exc:
    raise ImportError(
        "collection.zigzag.collector.ZigzagCollector를 import할 수 없습니다.\n"
        "현재 프로젝트의 ZigzagCollector 위치를 확인해 import 한 줄만 수정하세요."
    ) from exc


# ============================================================
# HELPERS
# ============================================================

PROFILE_FIELDS = (
    "source_brand_id",
    "name",
    "english_name",
    "main_domain",
    "source_profile_url",
    "image_url",
    "description",
    "target_age",
    "style_list",
    "bookmark_count",
    "seller_badges",
    "total_product_count",
)


def clean(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def nonempty(value: Any) -> bool:
    return value not in (
        None,
        "",
        [],
        {},
    )

def merge_nonempty(
    base: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    result = dict(base or {})

    for key, value in (incoming or {}).items():
        if nonempty(value):
            result[key] = value

    main_domain = clean(
        result.get("main_domain")
        or result.get("shop_domain")
        or result.get("domain")
    )

    if main_domain:
        result["main_domain"] = main_domain

        if not clean(
            result.get("source_profile_url")
        ):
            result["source_profile_url"] = (
                f"https://zigzag.kr/{main_domain}"
            )

    return result


def model_store_payload(
    brand_source: BrandSource,
) -> dict[str, Any]:
    attrs = (
        brand_source.attributes
        if isinstance(
            brand_source.attributes,
            dict,
        )
        else {}
    )

    return {
        "source_brand_id":
            str(
                brand_source.source_brand_id
                or ""
            ),

        "name":
            brand_source.name,

        "english_name":
            brand_source.english_name,

        "main_domain":
            attrs.get("main_domain"),

        "source_profile_url":
            brand_source.source_profile_url,

        "image_url":
            brand_source.image_url,

        "description":
            brand_source.description,

        "target_age":
            brand_source.target_age,

        "style_list":
            attrs.get("style_list")
            or attrs.get("styles")
            or [],

        "bookmark_count":
            attrs.get("bookmark_count"),

        "seller_badges":
            attrs.get("seller_badges"),

        "total_product_count":
            attrs.get("total_product_count"),
    }


def representative_product(
    brand_source: BrandSource,
) -> ProductSource | None:
    return (
        ProductSource.objects
        .filter(
            source=brand_source.source,
            source_brand=brand_source,
        )
        .exclude(
            product_url__isnull=True,
        )
        .exclude(
            product_url="",
        )
        .order_by(
            "-detected_count",
            "-last_seen_at",
            "id",
        )
        .first()
    )


def build_ranking_item(
    brand_source: BrandSource,
    product_source: ProductSource,
) -> dict[str, Any]:
    return {
        "product_url":
            product_source.product_url,

        "store_id":
            str(
                brand_source.source_brand_id
                or ""
            ),

        "store_name":
            brand_source.name,

        "store": {
            "source_brand_id":
                str(
                    brand_source.source_brand_id
                    or ""
                ),

            "name":
                brand_source.name,
        },
    }


def filter_profile(
    payload: dict[str, Any],
) -> dict[str, Any]:
    result = {}

    for field in PROFILE_FIELDS:
        value = payload.get(field)

        if nonempty(value):
            result[field] = value

    return result


# ============================================================
# FETCH
# ============================================================

def fetch_store_profile(
    *,
    collector: ZigzagCollector,
    brand_source: BrandSource,
) -> dict[str, Any]:
    """
    BrandSource(shop_id) -> Zigzag STORE profile.
    """

    expected_shop_id = clean(
        brand_source.source_brand_id
    )

    resolved = model_store_payload(
        brand_source
    )

    # --------------------------------------------------------
    # STEP 1. 이미 main_domain 있으면 바로 STORE 조회
    # --------------------------------------------------------

    main_domain = clean(
        resolved.get("main_domain")
    )

    # --------------------------------------------------------
    # STEP 2. 없으면 대표 상품 상세에서 main_domain 회수
    # --------------------------------------------------------

    product_source = None

    if not main_domain:
        product_source = representative_product(
            brand_source
        )

        if product_source is None:
            raise RuntimeError(
                "main_domain이 없고 대표 ProductSource.product_url도 없습니다."
            )

        if not hasattr(
            collector,
            "collect_product_detail",
        ):
            raise RuntimeError(
                "현재 ZigzagCollector에 collect_product_detail()이 없습니다."
            )

        detail = collector.collect_product_detail(
            build_ranking_item(
                brand_source,
                product_source,
            )
        )

        detail_store = (
            (detail or {}).get("store")
            or {}
        )

        resolved = merge_nonempty(
            resolved,
            detail_store,
        )

        main_domain = clean(
            resolved.get("main_domain")
        )

    if not main_domain:
        raise RuntimeError(
            "대표 상품 상세에서도 main_domain을 찾지 못했습니다."
        )

    # --------------------------------------------------------
    # STEP 3. STORE profile
    # --------------------------------------------------------

    if not hasattr(
        collector,
        "collect_shop",
    ):
        raise RuntimeError(
            "현재 ZigzagCollector에 collect_shop()이 없습니다."
        )

    shop_url = (
        f"https://zigzag.kr/{main_domain}"
    )

    profile_payload = collector.collect_shop(
        shop_url,
        collect_products=False,
    )

    profile_shop = (
        (profile_payload or {}).get("shop")
        or {}
    )

    resolved = merge_nonempty(
        resolved,
        profile_shop,
    )

    resolved["main_domain"] = (
        main_domain
    )
    resolved["source_profile_url"] = (
        clean(
            resolved.get(
                "source_profile_url"
            )
        )
        or shop_url
    )

    # --------------------------------------------------------
    # STEP 4. shop_id 검증
    # --------------------------------------------------------

    fetched_shop_id = clean(
        resolved.get(
            "source_brand_id"
        )
    )

    if (
        expected_shop_id
        and fetched_shop_id
        and expected_shop_id
        != fetched_shop_id
    ):
        raise RuntimeError(
            "shop_id mismatch: "
            f"expected={expected_shop_id}, "
            f"fetched={fetched_shop_id}"
        )

    resolved[
        "source_brand_id"
    ] = (
        expected_shop_id
        or fetched_shop_id
    )

    return {
        "profile":
            filter_profile(
                resolved
            ),

        "product_source_id":
            (
                product_source.id
                if product_source
                else None
            ),

        "product_url":
            (
                product_source.product_url
                if product_source
                else None
            ),

        "shop_url":
            shop_url,
    }


# ============================================================
# DB UPDATE
# ============================================================

def match_styles(
    style_names: list[str],
) -> list[Style]:
    names = [
        clean(x)
        for x in (
            style_names
            or []
        )
    ]

    names = [
        x
        for x in names
        if x
    ]

    if not names:
        return []

    query = Q()

    for name in names:
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


def update_brand_source(
    *,
    brand_source: BrandSource,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """
    기존 매핑 상태는 그대로 두고 STORE profile만 보강.
    """

    changed_fields = []

    scalar_fields = (
        "name",
        "english_name",
        "image_url",
        "description",
        "target_age",
        "source_profile_url",
    )

    for field in scalar_fields:
        value = profile.get(field)

        if (
            field == "english_name"
            and isinstance(value, str)
        ):
            value = value.strip().upper()

        if not nonempty(value):
            continue

        old_value = getattr(
            brand_source,
            field,
        )

        if old_value != value:
            setattr(
                brand_source,
                field,
                value,
            )
            changed_fields.append(
                field
            )

    attrs = (
        dict(
            brand_source.attributes
        )
        if isinstance(
            brand_source.attributes,
            dict,
        )
        else {}
    )

    attr_changed = False

    for key in (
        "main_domain",
        "style_list",
        "bookmark_count",
        "seller_badges",
        "total_product_count",
    ):
        value = profile.get(key)

        if not nonempty(value):
            continue

        if attrs.get(key) != value:
            attrs[key] = value
            attr_changed = True

    if attr_changed:
        brand_source.attributes = attrs
        changed_fields.append(
            "attributes"
        )

    if changed_fields:
        # updated_at이 모델에 있으면 함께 갱신.
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

    style_names = (
        profile.get(
            "style_list"
        )
        or []
    )

    matched_styles = match_styles(
        style_names
    )

    if (
        matched_styles
        and hasattr(
            brand_source,
            "styles",
        )
    ):
        brand_source.styles.add(
            *matched_styles
        )

    return {
        "changed_fields":
            changed_fields,

        "matched_style_count":
            len(
                matched_styles
            ),
    }


# ============================================================
# QUERYSET
# ============================================================

def build_queryset(
    *,
    source: Source,
    shop_ids: list[str] | None,
    only_unmapped: bool,
    missing_only: bool,
):
    qs = (
        BrandSource.objects
        .select_related(
            "source",
            "brand",
        )
        .filter(
            source=source,
        )
        .order_by(
            "-detected_count",
            "id",
        )
    )

    if shop_ids:
        qs = qs.filter(
            source_brand_id__in=[
                str(x)
                for x in shop_ids
            ]
        )

    if only_unmapped:
        qs = qs.filter(
            brand__isnull=True,
        )

    if missing_only:
        qs = qs.filter(
            Q(
                english_name__isnull=True
            )
            | Q(
                english_name=""
            )
            | Q(
                image_url__isnull=True
            )
            | Q(
                image_url=""
            )
            | Q(
                description__isnull=True
            )
            | Q(
                description=""
            )
        )

    return qs


# ============================================================
# CSV
# ============================================================

CSV_FIELDS = (
    "brand_source_id",
    "source_brand_id",
    "old_name",
    "name",
    "english_name",
    "main_domain",
    "source_profile_url",
    "image_url",
    "description",
    "target_age",
    "style_list",
    "bookmark_count",
    "seller_badges",
    "total_product_count",
    "product_source_id",
    "product_url",
    "status",
    "changed_fields",
    "matched_style_count",
    "error_type",
    "error",
)


def serialize_csv_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        (
            list,
            dict,
            tuple,
        ),
    ):
        return json.dumps(
            value,
            ensure_ascii=False,
        )

    return value


def write_csv(
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=CSV_FIELDS,
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    field:
                        serialize_csv_value(
                            row.get(field)
                        )
                    for field
                    in CSV_FIELDS
                }
            )


# ============================================================
# RUN
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--shop-ids",
        type=str,
        default=None,
        help="예: 202,25938,991",
    )

    parser.add_argument(
        "--only-unmapped",
        action="store_true",
        help="brand가 아직 없는 BrandSource만",
    )

    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="english_name/image/description 등이 비어있는 대상만",
    )

    parser.add_argument(
        "--update-db",
        action="store_true",
        help="실제 BrandSource DB 반영",
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=1.5,
        help="스토어 간 sleep 초",
    )

    parser.add_argument(
        "--csv",
        type=str,
        default="zigzag_store_profiles.csv",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    shop_ids = None

    if args.shop_ids:
        shop_ids = [
            x.strip()
            for x in args.shop_ids.split(",")
            if x.strip()
        ]

    source = Source.objects.get(
        code__iexact="ZIGZAG"
    )

    qs = build_queryset(
        source=source,
        shop_ids=shop_ids,
        only_unmapped=(
            args.only_unmapped
        ),
        missing_only=(
            args.missing_only
        ),
    )

    if args.limit is not None:
        qs = qs[:args.limit]

    targets = list(qs)

    print(
        f"[ZIGZAG STORE PROFILE] targets={len(targets)} "
        f"update_db={args.update_db}"
    )

    rows = []

    success = 0
    failed = 0
    updated = 0

    with ZigzagStoreCollector() as collector:
        for index, brand_source in enumerate(
            targets,
            start=1,
        ):
            shop_id = str(
                brand_source.source_brand_id
                or ""
            )

            print(
                f"[{index}/{len(targets)}] "
                f"BrandSource={brand_source.id} "
                f"shop_id={shop_id} "
                f"name={brand_source.name}"
            )

            row = {
                "brand_source_id":
                    brand_source.id,

                "source_brand_id":
                    shop_id,

                "old_name":
                    brand_source.name,

                "status":
                    "PENDING",
            }

            try:
                fetched = fetch_store_profile(
                    collector=collector,
                    brand_source=brand_source,
                )

                profile = (
                    fetched["profile"]
                )

                row.update(
                    profile
                )
                row[
                    "product_source_id"
                ] = fetched.get(
                    "product_source_id"
                )
                row[
                    "product_url"
                ] = fetched.get(
                    "product_url"
                )

                update_result = {
                    "changed_fields": [],
                    "matched_style_count": 0,
                }

                if args.update_db:
                    update_result = (
                        update_brand_source(
                            brand_source=(
                                brand_source
                            ),
                            profile=profile,
                        )
                    )

                    if update_result[
                        "changed_fields"
                    ]:
                        updated += 1

                row.update(
                    update_result
                )

                row["status"] = (
                    "UPDATED"
                    if (
                        args.update_db
                        and update_result[
                            "changed_fields"
                        ]
                    )
                    else "FETCHED"
                )

                success += 1

                print(
                    "  ->",
                    {
                        "english_name":
                            profile.get(
                                "english_name"
                            ),
                        "main_domain":
                            profile.get(
                                "main_domain"
                            ),
                        "image":
                            bool(
                                profile.get(
                                    "image_url"
                                )
                            ),
                        "styles":
                            profile.get(
                                "style_list"
                            ),
                    },
                )

            except Exception as exc:
                failed += 1

                row.update(
                    {
                        "status":
                            "FAILED",

                        "error_type":
                            exc.__class__.__name__,

                        "error":
                            str(exc),
                    }
                )

                print(
                    "  !!",
                    exc.__class__.__name__,
                    str(exc),
                )

            rows.append(row)

            if (
                index < len(targets)
                and args.sleep > 0
            ):
                time.sleep(
                    args.sleep
                )

    csv_path = Path(
        args.csv
    ).resolve()

    write_csv(
        rows,
        csv_path,
    )

    print()
    print(
        {
            "targets": len(targets),
            "success": success,
            "failed": failed,
            "updated": updated,
            "csv": str(csv_path),
        }
    )


if __name__ == "__main__":
    main()
