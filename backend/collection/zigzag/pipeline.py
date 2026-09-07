from __future__ import annotations

from datetime import datetime, timezone

from collection.common.pipeline import BasePlatformPipeline

from .collector import ZigzagCollector


class ZigzagPipeline(BasePlatformPipeline):
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
        ).upper()

        params = params or {}

        # ========================================================
        # PRODUCT
        # ========================================================

        if target_type == "PRODUCT":
            return self._collect_product(
                target_url=target_url,
            )

        # ========================================================
        # RANKING
        # ========================================================

        if target_type == "RANKING":
            return self._collect_ranking(
                target_url=target_url,
                params=params,
            )

        raise ValueError(
            "ZIGZAG에서 지원하지 않는 "
            f"target_type입니다: {target_type}"
        )

    # ============================================================
    # PRODUCT
    # ============================================================

    def _collect_product(
        self,
        *,
        target_url: str,
    ) -> dict:
        with ZigzagCollector() as collector:
            data = collector.collect_product(
                target_url
            )

        product_id = data.get(
            "source_product_id"
        )

        if not product_id:
            raise RuntimeError(
                "ZIGZAG source_product_id가 없습니다."
            )

        return {
            "entity_type": "PRODUCT",
            "source_entity_id": str(
                product_id
            ),
            "source_url": (
                data["source_url"]
            ),
            "collected_at": (
                data["collected_at"]
            ),
            "http_status": (
                data.get("http_status")
            ),
            "content_type": (
                data.get("content_type")
            ),
            "payload": data,
            "discovered_count": 1,
            "success_count": 1,
            "failure_count": 0,
        }

    # ============================================================
    # RANKING
    # ============================================================

    def _collect_ranking(
        self,
        *,
        target_url: str,
        params: dict,
    ) -> dict:
        # 기본 100개
        limit = int(
            params.get(
                "limit",
                100,
            )
        )

        # Ranking 페이지 스크롤 횟수
        scroll_count = int(
            params.get(
                "scroll_count",
                30,
            )
        )

        if limit <= 0:
            raise ValueError(
                "ZIGZAG ranking limit은 "
                "1 이상이어야 합니다."
            )

        if scroll_count <= 0:
            raise ValueError(
                "ZIGZAG scroll_count는 "
                "1 이상이어야 합니다."
            )

        with ZigzagCollector() as collector:
            # ----------------------------------------------------
            # 1. Ranking 목록 발견
            # ----------------------------------------------------

            ranking_items = (
                collector.discover_ranking(
                    target_url,
                    limit=limit,
                    scroll_count=scroll_count,
                )
            )

            products: list[dict] = []
            errors: list[dict] = []

            # ----------------------------------------------------
            # 2. Ranking 상품 각각 상세 수집
            # ----------------------------------------------------

            for ranking_context in ranking_items:
                product_id = (
                    ranking_context.get(
                        "product_id"
                    )
                )

                if not product_id:
                    errors.append(
                        {
                            "rank": (
                                ranking_context.get(
                                    "rank"
                                )
                            ),
                            "product_id": None,
                            "error": (
                                "Ranking item에 "
                                "product_id가 없습니다."
                            ),
                        }
                    )
                    continue

                try:
                    product = (
                        collector.collect_product(
                            product_id
                        )
                    )

                    products.append(
                        product
                    )

                except Exception as exc:
                    errors.append(
                        {
                            "rank": (
                                ranking_context.get(
                                    "rank"
                                )
                            ),
                            "product_id": str(
                                product_id
                            ),
                            "product_url": (
                                ranking_context.get(
                                    "product_url"
                                )
                            ),
                            "error": str(exc),
                        }
                    )

        # --------------------------------------------------------
        # 3. Ranking 결과 전체 묶기
        # --------------------------------------------------------

        collected_at = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        payload = {
            "schema_version": "1.0",
            "source": "ZIGZAG",
            "entity_type": "RANKING",

            "ranking": {
                "source_url": (
                    target_url
                ),
                "requested_limit": (
                    limit
                ),
                "discovered_count": (
                    len(ranking_items)
                ),

                # Ranking에서 직접 얻은 값
                "items": ranking_items,
            },

            # Ranking 상품 각각의 PRODUCT 상세
            "products": products,

            # 상세 수집 실패 목록

        }

        return {
            "entity_type": "RANKING",

            "source_entity_id": (
                "zigzag-ranking"
            ),

            "source_url": (
                target_url
            ),

            "collected_at": (
                collected_at
            ),

            "http_status": 200,

            "content_type": (
                "application/json"
            ),

            "payload": payload,

            # Ranking에서 발견한 상품 수
            "discovered_count": (
                len(ranking_items)
            ),

            # 상세 PRODUCT까지 성공한 수
            "success_count": (
                len(products)
            ),

            # 상세 PRODUCT 수집 실패한 수
            "failure_count": (
                len(errors)
            ),
        }
