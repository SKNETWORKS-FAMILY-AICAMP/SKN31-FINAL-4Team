from django.db import transaction

from apps.crawler.models import (
    ZigzagProduct,
    ZigzagProductSnapshot,
    ZigzagStore,
)


class ZigzagProductRepository:
    """
    Collector가 파싱한 지그재그 상품 데이터를
    ZigzagStore / ZigzagProduct / ZigzagProductSnapshot으로 저장한다.

    책임:
    - ZigzagStore upsert
    - ZigzagProduct upsert
    - ZigzagProductSnapshot 생성
    - 리스트 순서 기준 rank 부여

    하지 않는 일:
    - HTTP 요청 / GraphQL 파싱
    - CrawlJob 상태 관리
    - RawObject 저장
    """

    # ============================================================
    # PUBLIC
    # ============================================================

    @transaction.atomic
    def save_ranked_items(
        self,
        *,
        items: list[dict],
        crawl_target,
        crawl_job,
        observed_at,
    ) -> tuple[int, int]:

        created_count = 0
        updated_count = 0

        for rank, item in enumerate(
            items,
            start=1,
        ):
            product, created = self._upsert_product(
                item,
                observed_at=observed_at,
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

            self._save_snapshot(
                product=product,
                item=item,
                rank=rank,
                crawl_target=crawl_target,
                crawl_job=crawl_job,
                observed_at=observed_at,
            )

        return (
            created_count,
            updated_count,
        )

    # ============================================================
    # STORE
    # ============================================================

    @staticmethod
    def _upsert_store(
        item: dict,
        *,
        observed_at,
    ) -> ZigzagStore | None:

        raw_store_id = item.get("store_id")

        if raw_store_id is None:
            return None

        source_store_id = str(raw_store_id).strip()

        if not source_store_id:
            return None

        store_name = (item.get("store_name") or "").strip()

        is_brand = bool(item.get("is_brand"))

        store, created = ZigzagStore.objects.get_or_create(
            source_store_id=source_store_id,
            defaults={
                "store_name": store_name,
                "is_brand": is_brand,
                "first_seen_at": observed_at,
                "last_seen_at": observed_at,
            },
        )

        if created:
            return store

        update_fields = [
            "last_seen_at",
            "updated_at",
        ]

        if store_name and store_name != store.store_name:
            store.store_name = store_name

            update_fields.append("store_name")

        if is_brand != store.is_brand:
            store.is_brand = is_brand

            update_fields.append("is_brand")

        store.last_seen_at = observed_at

        store.save(
            update_fields=update_fields,
        )

        return store

    # ============================================================
    # PRODUCT
    # ============================================================

    def _upsert_product(
        self,
        item: dict,
        *,
        observed_at,
    ) -> tuple[
        ZigzagProduct,
        bool,
    ]:

        source_product_id = str(item["source_product_id"]).strip()

        if not source_product_id:
            raise ValueError("ZIGZAG 상품의 source_product_id가 비어 있습니다.")

        store = self._upsert_store(
            item,
            observed_at=observed_at,
        )

        product, created = ZigzagProduct.objects.get_or_create(
            source_product_id=source_product_id,
            defaults={
                "product_name": (item.get("product_name") or ""),
                "store": store,
                "category_id": item.get("category_id"),
                "category_name": item.get("category_name"),
                "product_url": (item.get("product_url") or ""),
                "thumbnail_url": item.get("thumbnail_url"),
                "first_seen_at": observed_at,
                "last_seen_at": observed_at,
            },
        )

        if created:
            return (
                product,
                True,
            )

        update_fields = [
            "last_seen_at",
            "updated_at",
        ]

        # --------------------------------------------------------
        # STORE FK
        # --------------------------------------------------------

        if store is not None and product.store_id != store.pk:
            product.store = store

            update_fields.append("store")

        # --------------------------------------------------------
        # PRODUCT FIELDS
        # --------------------------------------------------------

        field_map = {
            "product_name": item.get("product_name"),
            "category_id": item.get("category_id"),
            "category_name": item.get("category_name"),
            "product_url": item.get("product_url"),
            "thumbnail_url": item.get("thumbnail_url"),
        }

        for (
            field_name,
            value,
        ) in field_map.items():

            if value is None:
                continue

            if (
                getattr(
                    product,
                    field_name,
                )
                == value
            ):
                continue

            setattr(
                product,
                field_name,
                value,
            )

            update_fields.append(field_name)

        product.last_seen_at = observed_at

        product.save(
            update_fields=update_fields,
        )

        return (
            product,
            False,
        )

    # ============================================================
    # SNAPSHOT
    # ============================================================

    @staticmethod
    def _save_snapshot(
        *,
        product: ZigzagProduct,
        item: dict,
        rank: int,
        crawl_target,
        crawl_job,
        observed_at,
    ) -> ZigzagProductSnapshot:

        snapshot, _ = ZigzagProductSnapshot.objects.update_or_create(
            product=product,
            crawl_target=crawl_target,
            observed_at=observed_at,
            defaults={
                "crawl_job": crawl_job,
                "regular_price": item.get("regular_price"),
                "sale_price": item.get("sale_price"),
                "discount_rate": item.get("discount_rate"),
                "rank": rank,
                "review_count": item.get("review_count"),
                "availability": item.get("sellable_status"),
            },
        )

        return snapshot
