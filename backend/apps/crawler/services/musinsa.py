from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.crawler.models import (
    MusinsaBrand,
    MusinsaProduct,
    MusinsaProductSnapshot,
)


class MusinsaService:
    """
    무신사 수집 결과를 Django ORM으로 저장하는 서비스.

    책임:
    - MusinsaBrand upsert
    - MusinsaProduct upsert
    - MusinsaProductSnapshot create

    하지 않는 일:
    - HTTP 요청
    - HTML 파싱
    - Celery 실행
    - CrawlJob 상태 변경
    """

    @classmethod
    @transaction.atomic
    def save_product(
        cls,
        *,
        parsed: dict,
        crawl_job=None,
        crawl_target=None,
        observed_at=None,
    ) -> dict:
        """
        MusinsaCollector.collect_product()의 반환값 1건을 저장한다.

        return:
        {
            "brand": MusinsaBrand | None,
            "product": MusinsaProduct,
            "snapshot": MusinsaProductSnapshot,
            "created": bool,
        }
        """
        if not isinstance(parsed, dict):
            raise ValueError("parsed는 dict여야 합니다.")

        brand_data = parsed.get("brand") or {}
        product_data = parsed.get("product") or {}
        snapshot_data = parsed.get("snapshot") or {}

        goods_no = product_data.get("goods_no")

        if goods_no is None:
            raise ValueError("product.goods_no가 없습니다.")

        # ========================================================
        # 1. BRAND
        # ========================================================

        brand = cls._save_brand(
            brand_data=brand_data,
        )

        # ========================================================
        # 2. PRODUCT
        # ========================================================

        product, created = MusinsaProduct.objects.update_or_create(
            goods_no=goods_no,
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

        # ========================================================
        # 3. SNAPSHOT
        # ========================================================

        snapshot = MusinsaProductSnapshot.objects.create(
            product=product,
            crawl_job=crawl_job,
            crawl_target=crawl_target,
            regular_price=snapshot_data.get("regular_price"),
            sale_price=snapshot_data.get("sale_price"),
            discount_rate=snapshot_data.get("discount_rate"),
            rank=snapshot_data.get("rank"),
            ranking_period=snapshot_data.get("ranking_period"),
            ranking_year=snapshot_data.get("ranking_year"),
            ranking_month=snapshot_data.get("ranking_month"),
            ranking_gender=snapshot_data.get("ranking_gender"),
            ranking_age_band=snapshot_data.get("ranking_age_band"),
            ranking_category_depth1_code=(
                snapshot_data.get("ranking_category_depth1_code")
            ),
            ranking_category_depth1_name=(
                snapshot_data.get("ranking_category_depth1_name")
            ),
            ranking_category_depth2_code=(
                snapshot_data.get("ranking_category_depth2_code")
            ),
            ranking_category_depth2_name=(
                snapshot_data.get("ranking_category_depth2_name")
            ),
            review_count=snapshot_data.get("review_count"),
            satisfaction_score=snapshot_data.get("satisfaction_score"),
            like_count=snapshot_data.get("like_count"),
            view_count=snapshot_data.get("view_count"),
            sales_count=snapshot_data.get("sales_count"),
            availability=snapshot_data.get("availability"),
            is_out_of_stock=snapshot_data.get(
                "is_out_of_stock",
                False,
            ),
            observed_at=(observed_at or timezone.now()),
        )

        return {
            "brand": brand,
            "product": product,
            "snapshot": snapshot,
            "created": created,
        }

    @classmethod
    def _save_brand(
        cls,
        *,
        brand_data: dict,
    ):
        """
        brand_id가 없는 상품도 있을 수 있으므로 None 허용.
        """
        if not isinstance(
            brand_data,
            dict,
        ):
            return None

        brand_id = brand_data.get("brand_id")

        if not brand_id:
            return None

        brand, _ = MusinsaBrand.objects.update_or_create(
            brand_id=brand_id,
            defaults={
                "name_ko": brand_data.get("name_ko"),
                "name_en": brand_data.get("name_en"),
                "nation": brand_data.get("nation"),
                "since_year": brand_data.get("since_year"),
                "logo_url": brand_data.get("logo_url"),
                "description": brand_data.get("description"),
            },
        )

        return brand
