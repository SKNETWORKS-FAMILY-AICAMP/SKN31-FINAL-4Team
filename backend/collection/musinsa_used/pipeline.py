from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from collection.common.pipeline import BasePlatformPipeline

from .collector import MusinsaUsedCollector
from .constants import (
    DEFAULT_RANKING_LIMIT,
    MUSINSA_USED_PRODUCT_WORKERS,
    MUSINSA_USED_TARGET_COOLDOWN_SECONDS,
    PRODUCT_BASE_URL,
)
from .pacing import TargetCooldownCoordinator


MUSINSA_USED_TARGET_COORDINATOR = TargetCooldownCoordinator(
    cooldown_seconds=MUSINSA_USED_TARGET_COOLDOWN_SECONDS,
)


class MusinsaUsedPipeline(BasePlatformPipeline):
    SOURCE = "MUSINSA_USED"

    def run_target(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict | None = None,
    ) -> dict:
        with MUSINSA_USED_TARGET_COORDINATOR.execution():
            return super().run_target(
                target_type=target_type,
                target_url=target_url,
                params=params,
            )

    @classmethod
    def build_ranking_payload(
        cls,
        *,
        ranking_scope: dict,
        ranking_items: list[dict],
        collect_product,
        source_url: str | None,
        collected_at: str,
        product_workers: int = 1,
    ) -> dict:
        """Join ranking rows to detail records without losing failed rows."""
        products: list[dict] = []
        errors: list[dict] = []
        seen_goods_no: set[str] = set()

        outcomes: list[tuple[str, dict]] = []
        work_items: list[dict] = []
        for ranking_item in ranking_items:
            goods_no = ranking_item.get("goods_no")
            if goods_no is None:
                outcomes.append(
                    ("error", {
                        "rank": ranking_item.get("rank"),
                        "goods_no": None,
                        "stage": "PRODUCT",
                        "error_type": "MissingGoodsNo",
                        "error_message": "ranking item에 goods_no가 없습니다.",
                    })
                )
                continue

            goods_key = str(goods_no)
            if goods_key in seen_goods_no:
                continue
            seen_goods_no.add(goods_key)
            work_items.append(ranking_item)
            outcomes.append(("product", ranking_item))

        workers = min(max(1, int(product_workers)), len(work_items) or 1)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(collect_product, ranking_item)
                for ranking_item in work_items
            ]
            product_futures = iter(futures)
            for outcome_type, value in outcomes:
                if outcome_type == "error":
                    errors.append(value)
                    continue

                ranking_item = value
                try:
                    product = next(product_futures).result()
                    product["ranking_context"] = dict(ranking_item)
                    products.append(product)
                except Exception as exc:
                    errors.append(
                        {
                            "rank": ranking_item.get("rank"),
                            "goods_no": ranking_item.get("goods_no"),
                            "stage": "PRODUCT",
                            "error_type": exc.__class__.__name__,
                            "error_message": str(exc),
                        }
                    )

        return {
            "ranking": {
                **ranking_scope,
                "source_url": source_url,
                "collected_at": collected_at,
                "discovered_count": len(seen_goods_no),
                "success_count": len(products),
                "failure_count": len(errors),
            },
            "ranking_items": ranking_items,
            "products": products,
            "errors": errors,
        }

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:
        target_type = (target_type or "").upper()
        params = params or {}
        if target_type == "RANKING":
            return self._collect_ranking(target_url=target_url, params=params)
        if target_type == "PRODUCT":
            return self._collect_product(target_url=target_url, params=params)
        raise ValueError(f"MUSINSA USED에서 지원하지 않는 target_type입니다: {target_type}")

    def _collect_ranking(self, *, target_url: str | None, params: dict) -> dict:
        limit = int(params.get("limit", DEFAULT_RANKING_LIMIT))
        if limit <= 0:
            raise ValueError("MUSINSA USED ranking limit은 1 이상이어야 합니다.")
        limit = min(limit, DEFAULT_RANKING_LIMIT)
        live = bool(params.get("live", False))
        html_path = params.get("html_path")

        with MusinsaUsedCollector() as collector:
            if live:
                if not target_url:
                    raise ValueError("live MUSINSA USED ranking에는 target_url이 필요합니다.")
                ranking_result = collector.collect_ranking_live(target_url, limit=limit)
                ranking_scope = collector.ranking_scope(target_url)
                ranking_items = ranking_result["items"]
            elif html_path:
                ranking_result = collector.collect_ranking(
                    html_path, limit=limit, source_url=target_url
                )
                ranking_scope = collector.ranking_scope(target_url or "")
                ranking_items = [
                    self._manual_ranking_item(item, ranking_scope)
                    for item in ranking_result["items"]
                ]
            else:
                raise ValueError(
                    "MUSINSA USED ranking에는 html_path 또는 live=true가 필요합니다."
                )

            product_paths = params.get("product_html_paths") or {}
            sale_paths = params.get("sale_information_paths") or {}
            related_paths = params.get("related_goods_paths") or {}

            def collect_product(ranking_item: dict) -> dict:
                goods_key = str(ranking_item["goods_no"])
                if live:
                    return collector.collect_product_live(
                        goods_key,
                        ranking_context=ranking_item,
                    )
                html = product_paths.get(goods_key)
                if not html:
                    raise ValueError(f"goods_no={goods_key}의 product_html_paths가 없습니다.")
                return collector.collect_product_record_from_html(
                    html,
                    goods_no=goods_key,
                    sale_information_path=sale_paths.get(goods_key),
                    related_goods_path=related_paths.get(goods_key),
                    ranking_context=ranking_item,
                    source_url=ranking_item.get("product_url"),
                )

            collected_at = ranking_result["collected_at"]
            payload = self.build_ranking_payload(
                ranking_scope=ranking_scope,
                ranking_items=ranking_items,
                collect_product=collect_product,
                source_url=target_url,
                collected_at=collected_at,
                product_workers=(MUSINSA_USED_PRODUCT_WORKERS if live else 1),
            )
            request_metrics = collector.aggregate_request_metrics()

        return {
            "entity_type": "RANKING",
            "source_entity_id": self._build_ranking_id(ranking_scope),
            "source_url": target_url,
            "collected_at": collected_at,
            "http_status": None,
            "content_type": "application/json",
            "payload": payload,
            "discovered_count": payload["ranking"]["discovered_count"],
            "success_count": payload["ranking"]["success_count"],
            "failure_count": payload["ranking"]["failure_count"],
            "platform_data": {"request_metrics": request_metrics},
        }

    def _collect_product(self, *, target_url: str | None, params: dict) -> dict:
        goods_no = params.get("goods_no")
        if goods_no is None:
            raise ValueError("MUSINSA USED PRODUCT에는 params.goods_no가 필요합니다.")
        live = bool(params.get("live", False))
        html_path = params.get("html_path")

        with MusinsaUsedCollector() as collector:
            if live:
                record = collector.collect_product_live(
                    goods_no,
                )
            elif html_path:
                record = collector.collect_product_record_from_html(
                    html_path,
                    goods_no=goods_no,
                    sale_information_path=params.get("sale_information_path"),
                    related_goods_path=params.get("related_goods_path"),
                    source_url=target_url,
                )
            else:
                raise ValueError(
                    "MUSINSA USED PRODUCT에는 html_path 또는 live=true가 필요합니다."
                )
            request_metrics = collector.aggregate_request_metrics()

        product = record["product"]
        collected_at = datetime.now(timezone.utc).isoformat()
        return {
            "entity_type": "PRODUCT",
            "source_entity_id": str(product["goods_no"]),
            "source_url": target_url or PRODUCT_BASE_URL.format(goods_no=goods_no),
            "collected_at": collected_at,
            "http_status": (record.get("meta") or {}).get("http_status"),
            "content_type": "application/json",
            "payload": record,
            "discovered_count": 1,
            "success_count": 1,
            "failure_count": 0,
            "platform_data": {"request_metrics": request_metrics},
        }

    @staticmethod
    def _manual_ranking_item(item: dict, scope: dict) -> dict:
        goods_no = item.get("goods_no")
        return {
            "rank": item.get("rank"),
            "goods_no": goods_no,
            "product_url": PRODUCT_BASE_URL.format(goods_no=goods_no) if goods_no else None,
            "ranking_period": scope["period"],
            "ranking_gender": scope["gender"],
            "ranking_category_code": scope["category_code"],
            "ranking_age_band": scope["age_band"],
            "ranking_type": scope["ranking_type"],
            "viewing_count": None,
            "ranking_updated_at": None,
            "product_name": item.get("goods_name"),
            "brand_code": item.get("brand_code"),
            "brand_name": item.get("brand_name"),
            "price": item.get("price"),
            "normal_price": item.get("normal_price"),
            "discount_rate": item.get("discount"),
            "used_condition_grade": item.get("used_condition_grade"),
            "is_sold_out": item.get("is_sold_out"),
            "thumbnail_url": item.get("thumbnail_url"),
        }

    @staticmethod
    def _build_ranking_id(scope: dict) -> str:
        values = [
            scope.get("period") or "DAILY",
            scope.get("gender") or "A",
            scope.get("category_code") or "109",
            scope.get("age_band") or "AGE_BAND_ALL",
        ]
        return "_".join(str(value).strip().replace("/", "-") for value in values)
