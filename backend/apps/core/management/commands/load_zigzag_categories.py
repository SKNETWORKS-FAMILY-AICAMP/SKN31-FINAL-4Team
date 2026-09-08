from __future__ import annotations

import json
import re
from collections import Counter

import boto3

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    Source,
    Category,
    CategorySource,
)

from analysis.normalization.common import (
    clean_text,
    normalize_category_name,
)


BUCKET_NAME = "feedit-data-team4"
DEFAULT_PREFIX = "raw/zigzag/ranking/"


# ============================================================
# CATEGORY FIELD HELPERS
# ============================================================


CATEGORY_ID_KEYS = (
    "category_id",
    "categoryId",
    "category_code",
    "categoryCode",
    "id",
    "code",
)

CATEGORY_NAME_KEYS = (
    "category_name",
    "categoryName",
    "name",
    "display_name",
    "displayName",
    "title",
)


def _get_first(data: dict, keys: tuple[str, ...]):
    for key in keys:
        value = data.get(key)

        if value not in (None, ""):
            return value

    return None


def _looks_like_category_dict(
    data: dict,
    *,
    parent_key: str | None = None,
) -> bool:
    """
    아무 dict나 category로 잡지 않도록 제한한다.

    다음 중 하나면 category 후보:
    - 부모 key에 category 포함
    - 현재 dict key 중 category_* 존재
    """

    parent_key_normalized = (
        str(parent_key).lower()
        if parent_key
        else ""
    )

    if "category" in parent_key_normalized:
        return True

    for key in data.keys():
        if "category" in str(key).lower():
            return True

    return False


# ============================================================
# DIRECT CATEGORY STRUCTURES
# ============================================================


def extract_depth_categories(
    data: dict,
) -> list[dict]:
    """
    depth1_code / depth1_name
    depth2_code / depth2_name
    같은 구조 대응.
    """

    result = []
    path_parts = []

    for depth in range(1, 10):

        code = clean_text(
            data.get(f"depth{depth}_code")
            or data.get(f"depth{depth}_id")
            or data.get(f"depth{depth}Code")
            or data.get(f"depth{depth}Id")
        )

        name = clean_text(
            data.get(f"depth{depth}_name")
            or data.get(f"depth{depth}Name")
        )

        if code is None:
            continue

        if name:
            path_parts.append(name)

        result.append(
            {
                "source_category_id": code,
                "source_category_name": name,
                "source_category_path": (
                    " > ".join(path_parts)
                    if path_parts
                    else name
                ),
                "depth": depth,
            }
        )

    return result


def extract_category_list(
    data: list,
) -> list[dict]:
    """
    categories: [
        {"id": ..., "name": ...},
        {"id": ..., "name": ...}
    ]

    계층 배열 형태 대응.
    """

    result = []
    path_parts = []

    for depth, item in enumerate(
        data,
        start=1,
    ):
        if not isinstance(item, dict):
            continue

        category_id = clean_text(
            _get_first(
                item,
                CATEGORY_ID_KEYS,
            )
        )

        category_name = clean_text(
            _get_first(
                item,
                CATEGORY_NAME_KEYS,
            )
        )

        if category_id is None:
            continue

        if category_name:
            path_parts.append(
                category_name
            )

        result.append(
            {
                "source_category_id": (
                    category_id
                ),
                "source_category_name": (
                    category_name
                ),
                "source_category_path": (
                    " > ".join(path_parts)
                    if path_parts
                    else category_name
                ),
                "depth": depth,
            }
        )

    return result


# ============================================================
# RECURSIVE EXTRACTOR
# ============================================================


def extract_categories_recursive(
    data,
    *,
    parent_key: str | None = None,
    inherited_path: list[str] | None = None,
) -> list[dict]:
    """
    지그재그 raw JSON 구조가 날짜/collector 버전에 따라
    조금 달라도 category 계열 필드를 찾아낸다.

    단순 id/name dict는 잡지 않고
    category 문맥 안에 있는 dict만 대상으로 한다.
    """

    if inherited_path is None:
        inherited_path = []

    result = []

    # --------------------------------------------------------
    # DICT
    # --------------------------------------------------------
    if isinstance(data, dict):

        # depthN 구조 우선
        depth_categories = (
            extract_depth_categories(data)
        )

        if depth_categories:
            result.extend(
                depth_categories
            )

        # category 문맥의 단일 dict
        if _looks_like_category_dict(
            data,
            parent_key=parent_key,
        ):
            category_id = clean_text(
                data.get("category_id")
                or data.get("categoryId")
                or data.get("category_code")
                or data.get("categoryCode")
            )

            category_name = clean_text(
                data.get("category_name")
                or data.get("categoryName")
            )

            # 부모 key 자체가 category인 경우에는
            # id/name 일반키도 허용
            if (
                category_id is None
                and parent_key
                and "category"
                in parent_key.lower()
            ):
                category_id = clean_text(
                    data.get("id")
                    or data.get("code")
                )

            if (
                category_name is None
                and parent_key
                and "category"
                in parent_key.lower()
            ):
                category_name = clean_text(
                    data.get("name")
                    or data.get("title")
                )

            if category_id is not None:

                current_path = list(
                    inherited_path
                )

                if (
                    category_name
                    and category_name
                    not in current_path
                ):
                    current_path.append(
                        category_name
                    )

                result.append(
                    {
                        "source_category_id": (
                            category_id
                        ),
                        "source_category_name": (
                            category_name
                        ),
                        "source_category_path": (
                            " > ".join(
                                current_path
                            )
                            if current_path
                            else category_name
                        ),
                        "depth": (
                            len(current_path)
                            if current_path
                            else None
                        ),
                    }
                )

        # 자식 순회
        for key, value in data.items():

            key_text = str(key)

            next_path = list(
                inherited_path
            )

            # category 객체가 이름을 가지고 있으면
            # 하위 category path에 계승
            if (
                isinstance(value, dict)
                and "category"
                in key_text.lower()
            ):
                child_name = clean_text(
                    value.get("category_name")
                    or value.get("categoryName")
                    or value.get("name")
                )

                if (
                    child_name
                    and child_name
                    not in next_path
                ):
                    next_path.append(
                        child_name
                    )

            # categories 배열이면
            # 계층형으로 먼저 처리
            if (
                isinstance(value, list)
                and "categor"
                in key_text.lower()
            ):
                list_categories = (
                    extract_category_list(
                        value
                    )
                )

                if list_categories:
                    result.extend(
                        list_categories
                    )

            result.extend(
                extract_categories_recursive(
                    value,
                    parent_key=key_text,
                    inherited_path=next_path,
                )
            )

    # --------------------------------------------------------
    # LIST
    # --------------------------------------------------------
    elif isinstance(data, list):

        for item in data:
            result.extend(
                extract_categories_recursive(
                    item,
                    parent_key=parent_key,
                    inherited_path=(
                        inherited_path
                    ),
                )
            )

    return result


# ============================================================
# CATEGORY CLEANUP / DEDUP
# ============================================================


def deduplicate_categories(
    categories: list[dict],
) -> dict[str, dict]:
    """
    source_category_id 기준 통합.

    동일 ID가 여러 번 발견된 경우
    이름/path가 더 풍부한 값을 우선한다.
    """

    result = {}

    for item in categories:

        category_id = clean_text(
            item.get(
                "source_category_id"
            )
        )

        if category_id is None:
            continue

        category_name = clean_text(
            item.get(
                "source_category_name"
            )
        )

        category_path = clean_text(
            item.get(
                "source_category_path"
            )
        )

        candidate = {
            "source_category_id": (
                category_id
            ),
            "source_category_name": (
                category_name
            ),
            "source_category_path": (
                category_path
            ),
            "depth": item.get("depth"),
        }

        existing = result.get(
            category_id
        )

        if existing is None:
            result[category_id] = (
                candidate
            )
            continue

        # 이름 없는 값보다 이름 있는 값
        if (
            not existing.get(
                "source_category_name"
            )
            and category_name
        ):
            existing[
                "source_category_name"
            ] = category_name

        # 짧은 path보다 긴 path 우선
        old_path = (
            existing.get(
                "source_category_path"
            )
            or ""
        )

        new_path = (
            category_path
            or ""
        )

        if (
            new_path.count(">")
            > old_path.count(">")
        ):
            existing[
                "source_category_path"
            ] = category_path

            existing["depth"] = (
                item.get("depth")
            )

    return result


# ============================================================
# FEEDIT CATEGORY MATCH
# ============================================================


def build_category_index():
    """
    FEEDIT Category 이름 정규화 index.

    이름이 중복되는 경우 자동 매핑하지 않는다.
    """

    index: dict[
        str,
        list[Category],
    ] = {}

    queryset = (
        Category.objects
        .filter(
            category_type=(
                Category
                .CategoryType
                .PRODUCT
            ),
            status=(
                Category
                .Status
                .ACTIVE
            ),
        )
        .only(
            "id",
            "code",
            "name",
        )
    )

    for category in queryset:

        normalized = (
            normalize_category_name(
                category.name
            )
        )

        if normalized is None:
            continue

        index.setdefault(
            normalized,
            [],
        ).append(category)

    return index


def find_feedit_category(
    *,
    source_category_name: str | None,
    category_index: dict,
) -> Category | None:

    normalized = (
        normalize_category_name(
            source_category_name
        )
    )

    if normalized is None:
        return None

    matches = category_index.get(
        normalized,
        [],
    )

    if len(matches) != 1:
        return None

    return matches[0]


# ============================================================
# COMMAND
# ============================================================


class Command(BaseCommand):

    help = (
        "S3 raw/zigzag/ranking/ 전체를 읽어 "
        "지그재그 카테고리를 CategorySource에 적재합니다."
    )

    def add_arguments(
        self,
        parser,
    ):
        parser.add_argument(
            "--bucket",
            default=BUCKET_NAME,
        )

        parser.add_argument(
            "--prefix",
            default=DEFAULT_PREFIX,
        )

        parser.add_argument(
            "--source-code",
            default="ZIGZAG",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
        )

    def handle(
        self,
        *args,
        **options,
    ):

        bucket = options["bucket"]
        prefix = options["prefix"]
        source_code = (
            options["source_code"]
        )
        dry_run = options["dry_run"]

        self.stdout.write(
            ""
        )

        self.stdout.write(
            "======================================"
        )
        self.stdout.write(
            " ZIGZAG CATEGORY S3 LOAD"
        )
        self.stdout.write(
            "======================================"
        )

        self.stdout.write(
            f"BUCKET : {bucket}"
        )

        self.stdout.write(
            f"PREFIX : {prefix}"
        )

        if dry_run:
            self.stdout.write(
                "MODE   : DRY RUN"
            )

        # ----------------------------------------------------
        # SOURCE
        # ----------------------------------------------------

        source = (
            Source.objects
            .filter(
                code__iexact=source_code
            )
            .first()
        )

        if source is None:
            raise RuntimeError(
                f"Source(code={source_code})가 없습니다."
            )

        self.stdout.write(
            f"SOURCE : {source.code}"
        )

        # ----------------------------------------------------
        # CATEGORY INDEX
        # ----------------------------------------------------

        category_index = (
            build_category_index()
        )

        self.stdout.write(
            "FEEDIT CATEGORY INDEX: "
            f"{len(category_index):,}"
        )

        # ----------------------------------------------------
        # S3
        # ----------------------------------------------------

        s3 = boto3.client("s3")

        paginator = (
            s3.get_paginator(
                "list_objects_v2"
            )
        )

        total_objects = 0
        json_objects = 0
        failed_objects = 0

        extracted_total = 0

        all_categories: dict[
            str,
            dict,
        ] = {}

        # ----------------------------------------------------
        # 모든 JSON 읽기
        # ----------------------------------------------------

        for page in paginator.paginate(
            Bucket=bucket,
            Prefix=prefix,
        ):

            objects = page.get(
                "Contents",
                [],
            )

            for obj in objects:

                total_objects += 1

                key = obj["Key"]

                if not key.lower().endswith(
                    ".json"
                ):
                    continue

                json_objects += 1

                try:
                    response = (
                        s3.get_object(
                            Bucket=bucket,
                            Key=key,
                        )
                    )

                    raw = (
                        response[
                            "Body"
                        ]
                        .read()
                        .decode(
                            "utf-8-sig"
                        )
                    )

                    data = json.loads(
                        raw
                    )

                except Exception as exc:

                    failed_objects += 1

                    self.stderr.write(
                        "[READ ERROR] "
                        f"{key}"
                        f" | {exc}"
                    )

                    continue

                categories = (
                    extract_categories_recursive(
                        data
                    )
                )

                categories = list(
                    deduplicate_categories(
                        categories
                    ).values()
                )

                extracted_total += (
                    len(categories)
                )

                for item in categories:

                    category_id = clean_text(
                        item.get(
                            "source_category_id"
                        )
                    )

                    if category_id is None:
                        continue

                    existing = (
                        all_categories.get(
                            category_id
                        )
                    )

                    if existing is None:

                        all_categories[
                            category_id
                        ] = item

                        continue

                    # 기존보다 좋은 이름이면 교체
                    if (
                        not existing.get(
                            "source_category_name"
                        )
                        and item.get(
                            "source_category_name"
                        )
                    ):
                        existing[
                            "source_category_name"
                        ] = item[
                            "source_category_name"
                        ]

                    old_path = (
                        existing.get(
                            "source_category_path"
                        )
                        or ""
                    )

                    new_path = (
                        item.get(
                            "source_category_path"
                        )
                        or ""
                    )

                    if (
                        new_path.count(">")
                        > old_path.count(">")
                    ):
                        existing[
                            "source_category_path"
                        ] = new_path

                self.stdout.write(
                    "[READ] "
                    f"{json_objects:>4}"
                    f" | found="
                    f"{len(categories):>3}"
                    f" | {key}"
                )

        # ----------------------------------------------------
        # SUMMARY BEFORE SAVE
        # ----------------------------------------------------

        self.stdout.write("")
        self.stdout.write(
            "--------------------------------------"
        )
        self.stdout.write(
            " S3 SCAN RESULT"
        )
        self.stdout.write(
            "--------------------------------------"
        )

        self.stdout.write(
            f"OBJECTS           : {total_objects:,}"
        )

        self.stdout.write(
            f"JSON FILES        : {json_objects:,}"
        )

        self.stdout.write(
            f"FAILED JSON       : {failed_objects:,}"
        )

        self.stdout.write(
            f"RAW CATEGORY HITS : {extracted_total:,}"
        )

        self.stdout.write(
            "UNIQUE CATEGORY   : "
            f"{len(all_categories):,}"
        )

        if not all_categories:
            self.stdout.write(
                self.style.WARNING(
                    "카테고리를 찾지 못했습니다."
                )
            )
            return

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        now = timezone.now()

        created_count = 0
        updated_count = 0
        mapped_count = 0
        unmapped_count = 0

        if dry_run:

            self.stdout.write("")
            self.stdout.write(
                "=== DRY RUN CATEGORY ==="
            )

        with transaction.atomic():

            for category_id, item in sorted(
                all_categories.items(),
                key=lambda x: str(x[0]),
            ):

                name = clean_text(
                    item.get(
                        "source_category_name"
                    )
                )

                path = clean_text(
                    item.get(
                        "source_category_path"
                    )
                )

                feedit_category = (
                    find_feedit_category(
                        source_category_name=name,
                        category_index=(
                            category_index
                        ),
                    )
                )

                if feedit_category:
                    mapped_count += 1
                else:
                    unmapped_count += 1

                mapped_name = (
                    feedit_category.name
                    if feedit_category
                    else "UNMAPPED"
                )

                if dry_run:

                    self.stdout.write(
                        "[DRY] "
                        f"{category_id}"
                        f" | {name}"
                        f" | {path}"
                        f" -> {mapped_name}"
                    )

                    continue

                category_source = (
                    CategorySource.objects
                    .filter(
                        source=source,
                        source_category_id=(
                            category_id
                        ),
                    )
                    .first()
                )

                # --------------------------------------------
                # CREATE
                # --------------------------------------------

                if category_source is None:

                    CategorySource.objects.create(
                        source=source,
                        category=(
                            feedit_category
                        ),
                        source_category_id=(
                            category_id
                        ),
                        source_category_name=(
                            name
                        ),
                        source_category_path=(
                            path
                        ),
                        first_seen_at=now,
                        last_seen_at=now,
                    )

                    created_count += 1

                    action = "CREATE"

                # --------------------------------------------
                # UPDATE
                # --------------------------------------------

                else:

                    category_source.source_category_name = (
                        name
                    )

                    category_source.source_category_path = (
                        path
                    )

                    category_source.last_seen_at = (
                        now
                    )

                    # 기존 연결이 있으면 보존.
                    # 아직 unmapped인 것만 자동 연결.
                    if (
                        category_source.category_id
                        is None
                        and feedit_category
                        is not None
                    ):
                        category_source.category = (
                            feedit_category
                        )

                    category_source.save()

                    updated_count += 1

                    action = "UPDATE"

                self.stdout.write(
                    f"[{action}] "
                    f"{category_id}"
                    f" | {name}"
                    f" | {path}"
                    f" -> {mapped_name}"
                )

        # ----------------------------------------------------
        # FINAL
        # ----------------------------------------------------

        self.stdout.write("")
        self.stdout.write(
            "======================================"
        )
        self.stdout.write(
            " DONE"
        )
        self.stdout.write(
            "======================================"
        )

        self.stdout.write(
            f"JSON FILES       : {json_objects:,}"
        )

        self.stdout.write(
            "UNIQUE CATEGORY  : "
            f"{len(all_categories):,}"
        )

        if not dry_run:

            self.stdout.write(
                self.style.SUCCESS(
                    f"CREATED           : "
                    f"{created_count:,}"
                )
            )

            self.stdout.write(
                f"UPDATED           : "
                f"{updated_count:,}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"AUTO MAPPED       : "
                f"{mapped_count:,}"
            )
        )

        if unmapped_count:

            self.stdout.write(
                self.style.WARNING(
                    f"UNMAPPED          : "
                    f"{unmapped_count:,}"
                )
            )