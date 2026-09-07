from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from collection.common.pipeline import BasePlatformPipeline

from .collector import MusinsaCollector


class MusinsaPipeline(BasePlatformPipeline):
    SOURCE = "MUSINSA"

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:
        if not target_url:
            raise ValueError(
                "MUSINSA target_url이 없습니다."
            )

        target_type = (target_type or "").upper()
        params = params or {}

        if target_type == "PRODUCT":
            return self._collect_product(
                target_url=target_url,
                params=params,
            )

        if target_type == "RANKING":
            return self._collect_ranking(
                target_url=target_url,
                params=params,
            )

        raise ValueError(
            "MUSINSA에서 지원하지 않는 "
            f"target_type입니다: {target_type}"
        )

    # ============================================================
    # PRODUCT
    # ============================================================

    def _collect_product(
        self,
        *,
        target_url: str,
        params: dict,
    ) -> dict:
        with MusinsaCollector() as collector:
            data = collector.collect_product(
                target_url,
                collect_options=params.get(
                    "collect_options",
                    True,
                ),
                collect_reviews=params.get(
                    "collect_reviews",
                    True,
                ),
                review_limit=int(
                    params.get(
                        "review_limit",
                        50,
                    )
                ),
            )

        product = data.get("product") or {}
        meta = data.get("meta") or {}
        goods_no = product.get("goods_no")

        if goods_no is None:
            raise RuntimeError(
                "MUSINSA goods_no가 없습니다."
            )

        collected_at = datetime.now(
            timezone.utc
        ).isoformat()

        return {
            "entity_type": "PRODUCT",
            "source_entity_id": str(goods_no),
            "source_url": (
                meta.get("final_url")
                or meta.get("request_url")
                or target_url
            ),
            "collected_at": collected_at,
            "http_status": meta.get("http_status"),
            "content_type": (
                meta.get("content_type")
                or "application/json"
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
        limit = params.get("limit")

        if limit is not None:
            limit = int(limit)

        collect_options = params.get(
            "collect_options",
            True,
        )

        collect_reviews = params.get(
            "collect_reviews",
            True,
        )

        review_limit = int(
            params.get(
                "review_limit",
                20,
            )
        )

        with MusinsaCollector() as collector:
            ranking_items = collector.discover_ranking(
                target_url
            )

            if limit is not None:
                ranking_items = ranking_items[:limit]

            products: list[dict] = []
            errors: list[dict] = []

            for ranking_context in ranking_items:
                try:
                    data = collector.collect_product(
                        ranking_context["product_url"],
                        ranking_context=ranking_context,
                        collect_options=collect_options,
                        collect_reviews=collect_reviews,
                        review_limit=review_limit,
                    )
                    products.append(data)

                except Exception as exc:
                    errors.append(
                        {
                            "rank": ranking_context.get(
                                "rank"
                            ),
                            "goods_no": ranking_context.get(
                                "goods_no"
                            ),
                            "product_url": ranking_context.get(
                                "product_url"
                            ),
                            "error_type": (
                                exc.__class__.__name__
                            ),
                            "error_message": str(exc),
                        }
                    )

        collected_at = datetime.now(
            timezone.utc
        ).isoformat()

        ranking_scope = self._parse_ranking_scope(
            target_url
        )

        payload = {
            "ranking": {
                **ranking_scope,
                "source_url": target_url,
                "collected_at": collected_at,
                "discovered_count": len(
                    ranking_items
                ),
                "success_count": len(
                    products
                ),
                "failure_count": len(
                    errors
                ),
            },
            "ranking_items": ranking_items,
            "products": products,
            "errors": errors,
        }

        return {
            "entity_type": "RANKING",
            "source_entity_id": (
                self._build_ranking_id(
                    ranking_scope
                )
            ),
            "source_url": target_url,
            "collected_at": collected_at,
            "http_status": None,
            "content_type": "application/json",
            "payload": payload,
            "discovered_count": len(
                ranking_items
            ),
            "success_count": len(
                products
            ),
            "failure_count": len(
                errors
            ),
        }

    # ============================================================
    # RANKING SCOPE
    # ============================================================

    @staticmethod
    def _parse_ranking_scope(
        target_url: str,
    ) -> dict:
        query = parse_qs(
            urlparse(target_url).query,
            keep_blank_values=True,
        )

        def get(
            key: str,
            default=None,
        ):
            values = query.get(key)

            if not values:
                return default

            return values[0]

        return {
            "store_code": get(
                "storeCode",
                "musinsa",
            ),
            "section_id": get(
                "sectionId"
            ),
            "contents_id": get(
                "contentsId"
            ),
            "category_code": get(
                "categoryCode"
            ),
            "gender": get(
                "gf",
                "A",
            ),
            "age_band": get(
                "ageBand",
                "AGE_BAND_ALL",
            ),
            "sub_pan": get(
                "subPan",
                "product",
            ),
            "period": get(
                "period",
                "DAILY",
            ),
        }

    @staticmethod
    def _build_ranking_id(
        scope: dict,
    ) -> str:
        values = [
            scope.get("period")
            or "DAILY",
            scope.get("gender")
            or "A",
            scope.get("category_code")
            or "ALL",
            scope.get("age_band")
            or "AGE_BAND_ALL",
        ]

        return "_".join(
            str(value)
            .strip()
            .replace("/", "-")
            for value in values
        )
