from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from collection.common.pipeline import BasePlatformPipeline

from .collector import ZigzagCollector


class ZigzagPipeline(BasePlatformPipeline):
    """
    FEEDIT Zigzag pipeline.

    CrawlTarget 지원 방식

    1) RANKING / CATEGORY
       예:
       https://zigzag.kr/categories/-1?middle_category_id=507&sort=200

       -> URL에서 category_id / sort 추출
       -> Zigzag GraphQL category collector 실행
       -> 상품 카드 최대 limit개 저장

    2) OTHER + params.mode=SHOP
       예:
       target_url = https://zigzag.kr/naeni

       params:
       {
           "mode": "SHOP",
           "product_limit": 100,
           "max_pages": null
       }

       -> 스토어 프로필
       -> 스타일
       -> 북마크
       -> 카테고리
       -> 쿠폰
       -> 배너
       -> 스토어 상품
       를 하나의 S3 raw document로 저장한다.
    """

    SOURCE = "ZIGZAG"

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:

        if not target_url:
            raise ValueError(
                "ZIGZAG target_url이 없습니다."
            )

        target_type = (
            target_type or ""
        ).upper().strip()

        params = params or {}

        mode = str(
            params.get("mode") or ""
        ).upper().strip()

        # ========================================================
        # SHOP
        # ========================================================

        if (
            mode == "SHOP"
            or (
                target_type == "OTHER"
                and "/categories/" not in target_url
            )
        ):
            return self._collect_shop(
                target_url=target_url,
                params=params,
            )

        # ========================================================
        # CATEGORY / RANKING
        # ========================================================

        if target_type in {
            "CATEGORY",
            "RANKING",
        }:
            return self._collect_category(
                target_url=target_url,
                params=params,
                entity_type=target_type,
            )

        raise ValueError(
            "ZIGZAG에서 지원하지 않는 target입니다. "
            f"target_type={target_type}, mode={mode or '-'}"
        )

    # ============================================================
    # SHOP
    # ============================================================

    def _collect_shop(
        self,
        *,
        target_url: str,
        params: dict,
    ) -> dict:

        product_limit_raw = params.get(
            "product_limit",
            100,
        )

        product_limit = (
            None
            if product_limit_raw in {
                None,
                "",
                "ALL",
                "all",
            }
            else int(product_limit_raw)
        )

        max_pages_raw = params.get(
            "max_pages"
        )

        max_pages = (
            int(max_pages_raw)
            if max_pages_raw
            not in {
                None,
                "",
            }
            else None
        )

        collect_products = self._to_bool(
            params.get(
                "collect_products",
                True,
            )
        )

        with ZigzagCollector() as collector:

            data = collector.collect_shop(
                target_url,
                product_limit=product_limit,
                max_pages=max_pages,
                collect_products=collect_products,
            )

        shop = (
            data.get("shop")
            if isinstance(
                data.get("shop"),
                dict,
            )
            else {}
        )

        source_brand_id = (
            shop.get("source_brand_id")
        )

        if not source_brand_id:
            raise RuntimeError(
                "ZIGZAG SHOP source_brand_id가 없습니다."
            )

        products = (
            data.get("products")
            if isinstance(
                data.get("products"),
                list,
            )
            else []
        )

        payload = {
            "schema_version": "2.0",
            "source": self.SOURCE,
            "entity_type": "SHOP",

            "shop": shop,

            "categories": (
                data.get("categories")
                or []
            ),

            "coupon": (
                data.get("coupon")
            ),

            "banners": (
                data.get("banners")
                or []
            ),

            "products": products,

            # S3 원본에는 플랫폼 profile raw도 보존.
            # DB normalizer에서는 필요한 값만 사용하면 됨.
            "raw_profile": (
                data.get("raw_profile")
            ),
        }

        collected_at = (
            data.get("collected_at")
            or datetime.now(
                timezone.utc
            ).isoformat()
        )

        return {
            "entity_type": "SHOP",

            "source_entity_id": str(
                source_brand_id
            ),

            "source_url": (
                data.get("source_url")
                or target_url
            ),

            "collected_at": collected_at,

            "http_status": (
                data.get("http_status")
            ),

            "content_type": (
                data.get("content_type")
                or "application/json"
            ),

            "payload": payload,

            "discovered_count": (
                len(products)
            ),

            "success_count": (
                len(products)
            ),

            "failure_count": 0,
        }

    # ============================================================
    # CATEGORY / RANKING
    # ============================================================

    def _collect_category(
        self,
        *,
        target_url: str,
        params: dict,
        entity_type: str,
    ) -> dict:

        (
            category_id,
            sort,
        ) = self._parse_category_scope(
            target_url,
            params=params,
        )

        limit = int(
            params.get(
                "limit",
                100,
            )
        )

        if limit <= 0:
            raise ValueError(
                "ZIGZAG limit은 1 이상이어야 합니다."
            )

        max_pages_raw = params.get(
            "max_pages"
        )

        max_pages = (
            int(max_pages_raw)
            if max_pages_raw
            not in {
                None,
                "",
            }
            else None
        )

        products: list[dict] = []

        with ZigzagCollector() as collector:

            for (
                _raw_body,
                parsed_items,
                _has_next,
            ) in collector.iter_category_pages(
                category_id=category_id,
                sort=sort,
                max_pages=max_pages,
            ):

                for item in parsed_items:

                    # 현재 category 목록 순서를
                    # 해당 관측의 rank로 사용.
                    item = dict(item)

                    item["rank"] = (
                        len(products) + 1
                    )

                    products.append(
                        item
                    )

                    if (
                        len(products)
                        >= limit
                    ):
                        break

                if (
                    len(products)
                    >= limit
                ):
                    break

        collected_at = datetime.now(
            timezone.utc
        ).isoformat()

        payload = {
            "schema_version": "2.0",

            "source": self.SOURCE,

            "entity_type": entity_type,

            "ranking": {
                "source_url": target_url,
                "category_id": category_id,
                "sort": sort,
                "requested_limit": limit,
                "discovered_count": (
                    len(products)
                ),
            },

            "products": products,

            "errors": [],
        }

        return {
            "entity_type": entity_type,

            "source_entity_id": (
                f"zigzag-{entity_type.lower()}:"
                f"{category_id}:{sort}"
            ),

            "source_url": target_url,

            "collected_at": collected_at,

            "http_status": 200,

            "content_type": (
                "application/json"
            ),

            "payload": payload,

            "discovered_count": (
                len(products)
            ),

            "success_count": (
                len(products)
            ),

            "failure_count": 0,
        }

    # ============================================================
    # URL / PARAMS
    # ============================================================

    @staticmethod
    def _parse_category_scope(
        target_url: str,
        *,
        params: dict,
    ) -> tuple[str, str]:

        query = parse_qs(
            urlparse(
                target_url
            ).query,
            keep_blank_values=True,
        )

        category_id = (
            params.get(
                "category_id"
            )
            or (
                query.get(
                    "middle_category_id"
                )
                or query.get(
                    "category_id"
                )
                or query.get(
                    "category"
                )
                or [None]
            )[0]
        )

        sort = (
            params.get(
                "sort"
            )
            or (
                query.get("sort")
                or ["200"]
            )[0]
            or "200"
        )

        if not category_id:
            raise ValueError(
                "ZIGZAG category_id를 "
                "URL 또는 params에서 찾지 못했습니다."
            )

        return (
            str(category_id),
            str(sort),
        )

    @staticmethod
    def _to_bool(
        value,
    ) -> bool:

        if isinstance(
            value,
            bool,
        ):
            return value

        if value is None:
            return False

        return str(
            value
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
