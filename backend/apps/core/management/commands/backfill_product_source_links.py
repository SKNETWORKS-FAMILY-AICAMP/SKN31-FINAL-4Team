# backend/apps/core/management/commands/backfill_product_source_links.py

from __future__ import annotations

import json

import boto3
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import (
    ProductSource,
    RawDocument,
    Source,
)
from analysis.normalization.musinsa import MusinsaNormalizer


class Command(BaseCommand):
    help = (
        "S3 RawDocument를 다시 읽어 기존 ProductSource의 "
        "source_brand/source_category NULL FK를 복구합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="MUSINSA",
            help="Source.code (기본: MUSINSA)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="처리할 RawDocument 최대 개수",
        )
        parser.add_argument(
            "--crawl-run-id",
            type=int,
            default=None,
            help="특정 crawl_run만 처리",
        )
        parser.add_argument(
            "--only-category",
            action="store_true",
            help="source_category NULL만 복구",
        )
        parser.add_argument(
            "--only-brand",
            action="store_true",
            help="source_brand NULL만 복구",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="DB 변경 없이 복구 대상만 확인",
        )

    def handle(self, *args, **options):
        source_code = options["source"]
        limit = options["limit"]
        crawl_run_id = options["crawl_run_id"]
        only_category = options["only_category"]
        only_brand = options["only_brand"]
        dry_run = options["dry_run"]

        if only_category and only_brand:
            self.stderr.write(
                self.style.ERROR(
                    "--only-category와 --only-brand는 동시에 사용할 수 없습니다."
                )
            )
            return

        source = Source.objects.get(
            code__iexact=source_code,
        )

        normalizer = MusinsaNormalizer(
            source=source,
        )

        s3 = boto3.client("s3")

        raw_documents = (
            RawDocument.objects
            .select_related(
                "source",
                "crawl_run",
            )
            .filter(
                source=source,
                document_type__iexact="RANKING",
            )
            .order_by("id")
        )

        if crawl_run_id is not None:
            raw_documents = raw_documents.filter(
                crawl_run_id=crawl_run_id,
            )

        if limit is not None:
            raw_documents = raw_documents[:limit]

        stats = {
            "raw_documents": 0,
            "products_seen": 0,
            "product_source_found": 0,
            "targets": 0,
            "category_fixed": 0,
            "brand_fixed": 0,
            "already_ok": 0,
            "missing_product_source": 0,
            "missing_category_in_raw": 0,
            "missing_brand_in_raw": 0,
            "failed": 0,
        }

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "[FEEDIT] ProductSource FK backfill start"
            )
        )
        self.stdout.write(
            f"source={source.code} "
            f"dry_run={dry_run} "
            f"crawl_run_id={crawl_run_id} "
            f"limit={limit}"
        )
        self.stdout.write("")

        for raw_document in raw_documents:
            stats["raw_documents"] += 1

            try:
                raw_data = self._load_raw_json(
                    raw_document=raw_document,
                    s3=s3,
                )

                payload = self._extract_payload(
                    raw_data
                )

                products = self._extract_products(
                    payload
                )

                self.stdout.write(
                    f"[RAW #{raw_document.id}] "
                    f"products={len(products)}"
                )

                for parsed in products:
                    stats["products_seen"] += 1

                    try:
                        product_data = (
                            parsed.get("product")
                            if isinstance(
                                parsed.get("product"),
                                dict,
                            )
                            else {}
                        )

                        goods_no = product_data.get(
                            "goods_no"
                        )

                        if goods_no is None:
                            continue

                        product_source = (
                            ProductSource.objects
                            .filter(
                                source=source,
                                source_product_id=str(goods_no),
                            )
                            .first()
                        )

                        if product_source is None:
                            stats[
                                "missing_product_source"
                            ] += 1
                            continue

                        stats[
                            "product_source_found"
                        ] += 1

                        need_category = (
                            product_source.source_category_id
                            is None
                        )

                        need_brand = (
                            product_source.source_brand_id
                            is None
                        )

                        if only_category:
                            need_brand = False

                        if only_brand:
                            need_category = False

                        if not (
                            need_category
                            or need_brand
                        ):
                            stats["already_ok"] += 1
                            continue

                        stats["targets"] += 1

                        if dry_run:
                            self.stdout.write(
                                self.style.NOTICE(
                                    "[DRY-RUN] "
                                    f"{product_source.source_product_id} "
                                    f"| category={need_category} "
                                    f"| brand={need_brand}"
                                )
                            )
                            continue

                        self._repair_one(
                            normalizer=normalizer,
                            product_source=product_source,
                            parsed=parsed,
                            need_category=need_category,
                            need_brand=need_brand,
                            stats=stats,
                        )

                    except Exception as exc:
                        stats["failed"] += 1
                        self.stderr.write(
                            self.style.ERROR(
                                f"[PRODUCT ERROR] "
                                f"raw={raw_document.id} "
                                f"{exc.__class__.__name__}: {exc}"
                            )
                        )

            except Exception as exc:
                stats["failed"] += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"[RAW ERROR] "
                        f"raw={raw_document.id} "
                        f"{exc.__class__.__name__}: {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "========== BACKFILL RESULT =========="
            )
        )

        for key, value in stats.items():
            self.stdout.write(
                f"{key:28} {value}"
            )

        self.stdout.write(
            "====================================="
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN이므로 DB는 변경하지 않았습니다."
                )
            )

    @transaction.atomic
    def _repair_one(
        self,
        *,
        normalizer: MusinsaNormalizer,
        product_source: ProductSource,
        parsed: dict,
        need_category: bool,
        need_brand: bool,
        stats: dict,
    ):
        product_data = (
            parsed.get("product")
            if isinstance(
                parsed.get("product"),
                dict,
            )
            else {}
        )

        brand_data = (
            parsed.get("brand")
            if isinstance(
                parsed.get("brand"),
                dict,
            )
            else {}
        )

        update_fields = []

        # ========================================================
        # CATEGORY
        # ========================================================

        if need_category:
            category_result = (
                normalizer.normalize_category(
                    product_data
                )
            )

            category_source = (
                category_result.get(
                    "category_source"
                )
            )

            if category_source is not None:
                product_source.source_category = (
                    category_source
                )
                update_fields.append(
                    "source_category"
                )
                stats["category_fixed"] += 1
            else:
                stats[
                    "missing_category_in_raw"
                ] += 1

        # ========================================================
        # BRAND
        # ========================================================

        if need_brand:
            merged_brand_data = dict(
                brand_data
            )

            # parser 버전에 따라 brand_code가 product에만
            # 존재하는 경우를 보강한다.
            if not (
                merged_brand_data.get(
                    "brand_code"
                )
                or merged_brand_data.get(
                    "brand_id"
                )
            ):
                fallback_brand_code = (
                    product_data.get(
                        "brand_code"
                    )
                    or product_data.get(
                        "brand_id"
                    )
                )

                if fallback_brand_code:
                    merged_brand_data[
                        "brand_code"
                    ] = fallback_brand_code

            if not (
                merged_brand_data.get(
                    "name_ko"
                )
                or merged_brand_data.get(
                    "brand_name"
                )
                or merged_brand_data.get(
                    "name_en"
                )
            ):
                fallback_brand_name = (
                    product_data.get(
                        "brand_name"
                    )
                    or product_data.get(
                        "brand_name_ko"
                    )
                )

                if fallback_brand_name:
                    merged_brand_data[
                        "brand_name"
                    ] = fallback_brand_name

            brand_result = (
                normalizer.normalize_brand(
                    merged_brand_data
                )
            )

            brand_source = (
                brand_result.get(
                    "brand_source"
                )
            )

            if brand_source is not None:
                product_source.source_brand = (
                    brand_source
                )
                update_fields.append(
                    "source_brand"
                )
                stats["brand_fixed"] += 1
            else:
                stats[
                    "missing_brand_in_raw"
                ] += 1

        if update_fields:
            product_source.save(
                update_fields=update_fields
            )

            self.stdout.write(
                self.style.SUCCESS(
                    "[FIXED] "
                    f"{product_source.source_product_id} "
                    f"| category="
                    f"{product_source.source_category_id} "
                    f"| brand="
                    f"{product_source.source_brand_id}"
                )
            )

    @staticmethod
    def _load_raw_json(
        *,
        raw_document: RawDocument,
        s3,
    ) -> dict:

        response = s3.get_object(
            Bucket=raw_document.s3_bucket,
            Key=raw_document.s3_key,
        )

        body = response["Body"].read()

        data = json.loads(
            body.decode("utf-8")
        )

        if not isinstance(data, dict):
            raise ValueError(
                "S3 JSON root가 dict가 아닙니다."
            )

        return data

    @staticmethod
    def _extract_payload(
        raw_data: dict,
    ) -> dict:

        payload = raw_data.get(
            "payload"
        )

        if isinstance(payload, dict):
            return payload

        data = raw_data.get(
            "data"
        )

        if isinstance(data, dict):
            if (
                "products" in data
                or "product" in data
            ):
                return data

        return raw_data

    @staticmethod
    def _extract_products(
        payload: dict,
    ) -> list[dict]:

        products = payload.get(
            "products"
        )

        if isinstance(products, list):
            return [
                item
                for item in products
                if isinstance(item, dict)
            ]

        if isinstance(
            payload.get("product"),
            dict,
        ):
            return [payload]

        return []
