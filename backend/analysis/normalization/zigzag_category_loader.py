from __future__ import annotations

import json

import boto3

from django.conf import settings
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
    extract_zigzag_categories,
)


class ZigzagCategoryLoader:

    def __init__(
        self,
        *,
        bucket_name: str,
        prefix: str,
    ):
        self.bucket_name = bucket_name
        self.prefix = prefix

        self.s3 = boto3.client("s3")

        self.source = Source.objects.get(
            code="ZIGZAG"
        )

    # ============================================================
    # FEEDIT CATEGORY MATCH
    # ============================================================

    @staticmethod
    def _find_category(
        normalized_name: str | None,
    ) -> Category | None:

        if normalized_name is None:
            return None

        categories = (
            Category.objects
            .filter(
                category_type=(
                    Category.CategoryType.PRODUCT
                ),
                status=Category.Status.ACTIVE,
            )
            .only(
                "id",
                "code",
                "name",
            )
        )

        matches = []

        for category in categories:

            category_name = (
                normalize_category_name(
                    category.name
                )
            )

            if (
                category_name
                == normalized_name
            ):
                matches.append(category)

        # 하나만 정확하게 일치하는 경우만
        # 자동 매핑
        if len(matches) != 1:
            return None

        return matches[0]

    # ============================================================
    # CATEGORY SOURCE SAVE
    # ============================================================

    @transaction.atomic
    def save_category(
        self,
        category_data: dict,
    ) -> tuple[CategorySource, bool]:

        source_category_id = clean_text(
            category_data.get(
                "source_category_id"
            )
        )

        if source_category_id is None:
            raise ValueError(
                "source_category_id가 없습니다."
            )

        source_category_name = clean_text(
            category_data.get(
                "source_category_name"
            )
        )

        source_category_path = clean_text(
            category_data.get(
                "source_category_path"
            )
        )

        normalized_name = (
            normalize_category_name(
                source_category_name
            )
        )

        category = self._find_category(
            normalized_name
        )

        now = timezone.now()

        category_source, created = (
            CategorySource.objects
            .get_or_create(
                source=self.source,
                source_category_id=(
                    source_category_id
                ),
                defaults={
                    "category": category,
                    "source_category_name": (
                        source_category_name
                    ),
                    "source_category_path": (
                        source_category_path
                    ),
                    "first_seen_at": now,
                    "last_seen_at": now,
                },
            )
        )

        if not created:

            category_source.source_category_name = (
                source_category_name
            )

            category_source.source_category_path = (
                source_category_path
            )

            category_source.last_seen_at = now

            # 기존 수동 매핑 등을 날리면 안 됨.
            # 아직 매핑 안 된 경우에만 자동 매핑.
            if (
                category_source.category_id is None
                and category is not None
            ):
                category_source.category = category

            category_source.save()

        return category_source, created

    # ============================================================
    # OBJECT
    # ============================================================

    def process_object(
        self,
        key: str,
    ) -> dict:

        response = self.s3.get_object(
            Bucket=self.bucket_name,
            Key=key,
        )

        body = response["Body"].read()

        data = json.loads(
            body.decode("utf-8")
        )

        categories = (
            extract_zigzag_categories(data)
        )

        created_count = 0
        updated_count = 0

        for category_data in categories:

            _, created = self.save_category(
                category_data
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        return {
            "key": key,
            "found": len(categories),
            "created": created_count,
            "updated": updated_count,
        }

    # ============================================================
    # S3 PREFIX
    # ============================================================

    def run(self) -> dict:

        paginator = (
            self.s3
            .get_paginator("list_objects_v2")
        )

        processed_files = 0

        created_count = 0
        updated_count = 0

        seen_category_ids = set()

        for page in paginator.paginate(
            Bucket=self.bucket_name,
            Prefix=self.prefix,
        ):

            for obj in page.get(
                "Contents",
                [],
            ):

                key = obj["Key"]

                if not key.endswith(".json"):
                    continue

                response = self.s3.get_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )

                try:
                    data = json.loads(
                        response[
                            "Body"
                        ].read().decode(
                            "utf-8"
                        )
                    )

                except Exception as exc:
                    print(
                        f"[SKIP] {key}"
                        f" | {exc}"
                    )
                    continue

                categories = (
                    extract_zigzag_categories(
                        data
                    )
                )

                processed_files += 1

                for category_data in categories:

                    category_id = (
                        category_data.get(
                            "source_category_id"
                        )
                    )

                    # 한 번 실행 내에서는
                    # 같은 카테고리 반복 저장 방지
                    if (
                        not category_id
                        or category_id
                        in seen_category_ids
                    ):
                        continue

                    seen_category_ids.add(
                        category_id
                    )

                    category_source, created = (
                        self.save_category(
                            category_data
                        )
                    )

                    if created:
                        created_count += 1
                        action = "CREATE"
                    else:
                        updated_count += 1
                        action = "UPDATE"

                    mapped = (
                        category_source.category.name
                        if category_source.category
                        else "UNMAPPED"
                    )

                    print(
                        f"[{action}] "
                        f"{category_id}"
                        f" | "
                        f"{category_data.get('source_category_path')}"
                        f" -> {mapped}"
                    )

        result = {
            "processed_files": (
                processed_files
            ),
            "unique_categories": len(
                seen_category_ids
            ),
            "created": created_count,
            "updated": updated_count,
        }

        print()
        print(
            "=== ZIGZAG CATEGORY LOAD ==="
        )

        for key, value in result.items():
            print(
                f"{key}: {value}"
            )

        return result