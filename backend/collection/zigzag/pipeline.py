from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from collection.common.pipeline import BasePlatformPipeline

from .config import (
    DEFAULT_ACTION_ID,
    DEFAULT_GROUPS,
    DEFAULT_LAYOUT_ID,
    DEFAULT_LIMITS,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
    DEFAULT_MODULE_SLOT_ID,
    DEFAULT_ORDER,
)
from .service import ZigzagCnvService


class ZigzagPipeline(BasePlatformPipeline):
    """
    FEEDIT Zigzag CNV pipeline.

    역할:
    CrawlTarget
      -> Zigzag CNV category/tag item collection
      -> BasePlatformPipeline
      -> S3 raw JSON
      -> RawDocument

    이 파일에서는 S3/RawDocument를 직접 저장하지 않는다.
    공통 BasePlatformPipeline의 기존 저장 프로세스를 그대로 사용한다.
    """

    SOURCE = "ZIGZAG"

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:
        params = params or {}

        target_type = (
            target_type
            or ""
        ).upper().strip()

        if target_type != "RANKING":
            raise ValueError(
                "새 ZigzagPipeline은 "
                f"RANKING target만 지원합니다. "
                f"target_type={target_type}"
            )

        category_id = self._resolve_category_id(
            target_url=target_url,
            params=params,
        )

        groups = params.get("groups") or DEFAULT_GROUPS

        limits = {
            **DEFAULT_LIMITS,
            **(params.get("limits") or {}),
        }

        order = str(
            params.get("order")
            or DEFAULT_ORDER
        ).strip()

        layout_id = str(
            params.get("layout_id")
            or DEFAULT_LAYOUT_ID
        )

        action_id = str(
            params.get("action_id")
            or DEFAULT_ACTION_ID
        )

        module_slot_id = str(
            params.get("module_slot_id")
            or DEFAULT_MODULE_SLOT_ID
        )

        min_delay = float(
            params.get(
                "min_delay",
                DEFAULT_MIN_DELAY,
            )
        )

        max_delay = float(
            params.get(
                "max_delay",
                DEFAULT_MAX_DELAY,
            )
        )

        with ZigzagCnvService(
            layout_id=layout_id,
            action_id=action_id,
            module_slot_id=module_slot_id,
            min_delay=min_delay,
            max_delay=max_delay,
        ) as service:
            data = service.collect_category(
                category_id=category_id,
                groups=groups,
                limits=limits,
                order=order,
            )

        collected_at = datetime.now(
            timezone.utc
        ).isoformat()

        tag_snapshot_count = 0
        product_occurrence_count = 0
        unique_product_ids: set[str] = set()

        group_stats: dict[str, dict] = {}

        for group, rows in data["groups"].items():
            group_occurrences = 0

            for row in rows:
                products = row.get("products") or []

                tag_snapshot_count += 1
                product_occurrence_count += len(products)
                group_occurrences += len(products)

                for product in products:
                    product_id = product.get("product_id")

                    if product_id:
                        unique_product_ids.add(
                            str(product_id)
                        )

            group_stats[group] = {
                "tag_snapshot_count": len(rows),
                "product_occurrence_count":
                    group_occurrences,
            }

        unique_product_count = len(
            unique_product_ids
        )

        payload = {
            "schema_version": "1.0",
            "source": self.SOURCE,
            "entity_type": "CNV_CATEGORY",
            "collected_at": collected_at,
            "cnv": {
                "category_id": category_id,
                "order": order,
                "groups": groups,
                "limits": limits,
                "layout_id": layout_id,
                "module_slot_id": module_slot_id,
                "tag_snapshot_count":
                    tag_snapshot_count,
                "product_occurrence_count":
                    product_occurrence_count,
                "unique_product_count":
                    unique_product_count,
                "group_stats": group_stats,
            },
            "groups": data["groups"],
        }

        return {
            "entity_type": "CNV_CATEGORY",
            "source_entity_id": (
                f"zigzag-cnv:{category_id}"
            ),
            "source_url": (
                target_url
                or (
                    "https://zigzag.kr/pages/"
                    "srp-clp-category"
                    f"?category_id={category_id}"
                )
            ),
            "collected_at": collected_at,
            "http_status": 200,
            "content_type": "application/json",
            "payload": payload,

            # CrawlRun count는 태그 중복을 제외한 unique product 기준.
            "discovered_count": unique_product_count,
            "success_count": unique_product_count,
            "failure_count": 0,
        }

    @staticmethod
    def _resolve_category_id(
        *,
        target_url: str | None,
        params: dict,
    ) -> str:
        category_id = params.get("category_id")

        if category_id not in {
            None,
            "",
        }:
            return str(category_id)

        if target_url:
            parsed = urlparse(target_url)
            query = parse_qs(parsed.query)

            for key in (
                "category_id",
                "middle_category_id",
            ):
                values = query.get(key)

                if values and values[0]:
                    return str(values[0])

        raise ValueError(
            "Zigzag category_id를 찾지 못했습니다. "
            "CrawlTarget.params.category_id 또는 "
            "target URL의 category_id를 설정하세요."
        )
