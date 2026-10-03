from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from collection.common.pipeline import BasePlatformPipeline
from collection.common.schemas import CollectionResult

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
    FEEDIT Zigzag collection pipeline.

    지원 수집 유형:
    1. CNV
       - 카테고리별 trend/style tag 상품 관측

    2. RANKING
       - 세부 카테고리별 상품 랭킹
       - 선택적으로 상품 리뷰 수집

    이 클래스는 수집 결과만 CollectionResult로 반환한다.

    S3 RAW 저장, RawDocument 생성, CrawlRun 처리는
    collection.common.runner에서 담당한다.
    """

    SOURCE_CODE = "ZIGZAG"

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> CollectionResult:
        params = params or {}

        collection_type = str(
            params.get("collection_type") or ""
        ).upper().strip()

        ranking_mode = str(
            params.get("ranking_mode") or ""
        ).lower().strip()

        # ============================================================
        # RANKING
        # ============================================================

        if (
            collection_type == "RANKING"
            or ranking_mode == "detail_category"
        ):
            if ranking_mode not in {
                "",
                "detail_category",
            }:
                raise ValueError(
                    "지원하지 않는 Zigzag "
                    f"ranking_mode: {ranking_mode}"
                )

            from .detail_ranking import (
                collect_detail_category_ranking,
            )

            raw_result = collect_detail_category_ranking(
                target_url=target_url,
                params=params,
            )

            return self._to_collection_result(
                raw_result
            )

        # ============================================================
        # CNV
        # ============================================================

        if collection_type not in {
            "",
            "CNV",
        }:
            raise ValueError(
                "지원하지 않는 Zigzag "
                f"collection_type: {collection_type}"
            )

        normalized_target_type = (
            target_type
            or ""
        ).upper().strip()

        if normalized_target_type != "RANKING":
            raise ValueError(
                "ZigzagPipeline은 현재 "
                "RANKING CrawlTarget만 지원합니다. "
                f"target_type={normalized_target_type}"
            )

        category_id = self._resolve_category_id(
            target_url=target_url,
            params=params,
        )

        groups = (
            params.get("groups")
            or DEFAULT_GROUPS
        )

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

        # ============================================================
        # CNV COLLECTION
        # ============================================================

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
        )

        collected_at_iso = (
            collected_at.isoformat()
        )

        # ============================================================
        # CNV STATISTICS
        # ============================================================

        tag_snapshot_count = 0
        product_occurrence_count = 0

        unique_product_ids: set[str] = set()

        group_stats: dict[str, dict] = {}

        for group, rows in data["groups"].items():
            group_occurrences = 0

            for row in rows:
                products = (
                    row.get("products")
                    or []
                )

                tag_snapshot_count += 1

                product_occurrence_count += (
                    len(products)
                )

                group_occurrences += (
                    len(products)
                )

                for product in products:
                    product_id = (
                        product.get(
                            "product_id"
                        )
                    )

                    if product_id:
                        unique_product_ids.add(
                            str(product_id)
                        )

            group_stats[group] = {
                "tag_snapshot_count":
                    len(rows),

                "product_occurrence_count":
                    group_occurrences,
            }

        unique_product_count = len(
            unique_product_ids
        )

        # ============================================================
        # RAW PAYLOAD
        # ============================================================

        payload = {
            "schema_version": "1.0",
            "source": "ZIGZAG",
            "entity_type": "CNV_CATEGORY",
            "collected_at": collected_at_iso,

            "cnv": {
                "category_id":
                    category_id,

                "order":
                    order,

                "groups":
                    groups,

                "limits":
                    limits,

                "layout_id":
                    layout_id,

                "module_slot_id":
                    module_slot_id,

                "tag_snapshot_count":
                    tag_snapshot_count,

                "product_occurrence_count":
                    product_occurrence_count,

                "unique_product_count":
                    unique_product_count,

                "group_stats":
                    group_stats,
            },

            "groups":
                data["groups"],
        }

        source_url = (
            target_url
            or (
                "https://zigzag.kr/pages/"
                "srp-clp-category"
                f"?category_id={category_id}"
            )
        )

        # ============================================================
        # COLLECTION RESULT
        # ============================================================

        return CollectionResult(
            source_code="ZIGZAG",
            entity_type="CNV_CATEGORY",
            source_entity_id=(
                f"zigzag-cnv:{category_id}"
            ),
            source_url=source_url,
            collected_at=collected_at,
            http_status=200,
            payload=payload,
            discovered_count=(
                unique_product_count
            ),
            success_count=(
                unique_product_count
            ),
            failure_count=0,
        )

    # ================================================================
    # LEGACY DICT -> COLLECTION RESULT
    # ================================================================

    @staticmethod
    def _to_collection_result(
        raw_result,
    ) -> CollectionResult:
        """
        detail_ranking.py의 기존 반환 형식을
        공통 CollectionResult 계약으로 변환한다.

        detail_ranking.py 자체는 수정하지 않는다.
        """

        if isinstance(
            raw_result,
            CollectionResult,
        ):
            return raw_result

        if not isinstance(
            raw_result,
            dict,
        ):
            raise TypeError(
                "Zigzag detail ranking 결과는 "
                "dict 또는 CollectionResult여야 합니다. "
                f"actual={type(raw_result).__name__}"
            )

        required_fields = (
            "entity_type",
            "source_entity_id",
            "source_url",
            "collected_at",
            "payload",
            "discovered_count",
            "success_count",
            "failure_count",
        )

        missing_fields = [
            field
            for field in required_fields
            if field not in raw_result
        ]

        if missing_fields:
            raise ValueError(
                "Zigzag detail ranking 결과에 "
                "필수 필드가 없습니다: "
                + ", ".join(missing_fields)
            )

        collected_at = (
            raw_result["collected_at"]
        )

        if isinstance(
            collected_at,
            str,
        ):
            collected_at = (
                datetime.fromisoformat(
                    collected_at.replace(
                        "Z",
                        "+00:00",
                    )
                )
            )

        return CollectionResult(
            source_code="ZIGZAG",

            entity_type=(
                raw_result[
                    "entity_type"
                ]
            ),

            source_entity_id=(
                raw_result[
                    "source_entity_id"
                ]
            ),

            source_url=(
                raw_result[
                    "source_url"
                ]
            ),

            collected_at=collected_at,

            http_status=(
                raw_result.get(
                    "http_status",
                    200,
                )
            ),

            payload=(
                raw_result[
                    "payload"
                ]
            ),

            discovered_count=int(
                raw_result[
                    "discovered_count"
                ]
            ),

            success_count=int(
                raw_result[
                    "success_count"
                ]
            ),

            failure_count=int(
                raw_result[
                    "failure_count"
                ]
            ),
        )

    # ================================================================
    # CATEGORY
    # ================================================================

    @staticmethod
    def _resolve_category_id(
        *,
        target_url: str | None,
        params: dict,
    ) -> str:
        category_id = (
            params.get(
                "category_id"
            )
        )

        if category_id not in {
            None,
            "",
        }:
            return str(
                category_id
            )

        if target_url:
            parsed = urlparse(
                target_url
            )

            query = parse_qs(
                parsed.query
            )

            for key in (
                "category_id",
                "middle_category_id",
            ):
                values = query.get(
                    key
                )

                if (
                    values
                    and values[0]
                ):
                    return str(
                        values[0]
                    )

        raise ValueError(
            "Zigzag category_id를 "
            "찾지 못했습니다. "
            "CrawlTarget.params.category_id "
            "또는 target URL의 "
            "category_id를 설정하세요."
        )