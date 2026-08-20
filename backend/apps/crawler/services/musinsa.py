from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.crawler.models import (
    MusinsaBrand,
    MusinsaProduct,
    MusinsaProductSnapshot,
)


class MusinsaStorageService:

    @staticmethod
    def _decimal(value):
        if value is None:
            return None

        try:
            return Decimal(str(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    @transaction.atomic
    def save_product(
        cls,
        parsed,
        crawl_job,
        crawl_target,
    ):
        brand_data = parsed["brand"]
        product_data = parsed["product"]
        snapshot_data = parsed["snapshot"]

        brand = cls._save_brand(brand_data)

        product, created = cls._save_product(
            product_data,
            brand,
        )

        snapshot = cls._save_snapshot(
            product,
            snapshot_data,
            crawl_job,
            crawl_target,
        )

        return {
            "product": product,
            "snapshot": snapshot,
            "created": created,
        }

    @classmethod
    def _save_brand(cls, brand_data):
        brand_id = brand_data.get("brand_id")

        if not brand_id:
            return None

        brand, _ = MusinsaBrand.objects.update_or_create(
            brand_id=brand_id,
            defaults={
                "name_ko": brand_data.get("name_ko") or brand_id,
                "name_en": brand_data.get("name_en"),
                "nation": brand_data.get("nation"),
                "since_year": brand_data.get("since_year"),
                "logo_url": brand_data.get("logo_url"),
                "description": brand_data.get("description"),
            },
        )

        return brand

    @classmethod
    def _save_product(cls, product_data, brand):
        return MusinsaProduct.objects.update_or_create(
            goods_no=product_data["goods_no"],
            defaults={
                "style_no": product_data.get("style_no"),
                "name": product_data.get("name"),
                "brand": brand,
                "category_depth1": product_data.get("category_depth1"),
                "category_depth2": product_data.get("category_depth2"),
                "sex": product_data.get("sex"),
                "season_year": product_data.get("season_year"),
                "season": product_data.get("season"),
                "thumbnail_url": product_data.get("thumbnail_url"),
                "material_info": product_data.get("material_info"),
                "tags": product_data.get("tags"),
            },
        )

    @classmethod
    def _save_snapshot(
        cls,
        product,
        snapshot_data,
        crawl_job,
        crawl_target,
    ):
        return MusinsaProductSnapshot.objects.create(
            product=product,
            crawl_job=crawl_job,
            crawl_target=crawl_target,
            regular_price=snapshot_data.get("regular_price"),
            sale_price=snapshot_data.get("sale_price"),
            discount_rate=cls._decimal(snapshot_data.get("discount_rate")),
            rank=snapshot_data.get("rank"),
            ranking_period=snapshot_data.get("ranking_period"),
            ranking_year=snapshot_data.get("ranking_year"),
            ranking_month=snapshot_data.get("ranking_month"),
            ranking_gender=snapshot_data.get("ranking_gender"),
            review_count=snapshot_data.get("review_count"),
            satisfaction_score=cls._decimal(snapshot_data.get("satisfaction_score")),
            like_count=snapshot_data.get("like_count"),
            view_count=snapshot_data.get("view_count"),
            sales_count=snapshot_data.get("sales_count"),
            availability=snapshot_data.get("availability"),
            is_out_of_stock=snapshot_data.get(
                "is_out_of_stock",
                False,
            ),
            observed_at=timezone.now(),
        )
