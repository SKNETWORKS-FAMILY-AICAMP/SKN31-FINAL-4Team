from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from collection.common.pipeline import (
    BasePlatformPipeline,
)

from .filter_collector import (
    MusinsaUsedFilterCollector,
)
from .filter_config import (
    API_URL,
    DEFAULT_LIMIT,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_CODE,
    get_filter_group,
)


class MusinsaUsedFilterPipeline(
    BasePlatformPipeline
):
    SOURCE = "MUSINSA_USED"

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:
        if (
            target_type
            or ""
        ).upper() != "RANKING":
            raise ValueError(
                "MUSINSA_USED FILTER는 "
                "RANKING target만 지원합니다."
            )

        params = dict(
            params or {}
        )

        if str(
            params.get(
                "observation_type",
                "",
            )
        ).upper() != "FILTER":
            raise ValueError(
                "observation_type=FILTER "
                "타깃 전용 pipeline입니다."
            )

        filter_type = str(
            params["filter_type"]
        )

        filter_name = str(
            params["filter_name"]
        )

        category_id = str(
            params["category_id"]
        )

        category_name = str(
            params.get(
                "category_name"
            )
            or category_id
        )

        # 신규 동적 target은 parameter/value/label을 params에 직접 보존한다.
        # 기존 정적 target도 깨지지 않도록 FILTER_GROUPS fallback을 유지한다.
        group = None

        if (
            not params.get("filter_parameter")
            or params.get("filter_value") in (None, "")
            or not params.get("filter_label")
        ):
            try:
                group = get_filter_group(
                    filter_type
                )
            except ValueError:
                group = None

        filter_parameter = params.get(
            "filter_parameter"
        )

        if not filter_parameter and group:
            filter_parameter = group.get(
                "parameter"
            )

        if not filter_parameter:
            raise ValueError(
                "filter_parameter가 없습니다. "
                f"filter_type={filter_type}"
            )

        filter_value = params.get(
            "filter_value"
        )

        if (
            filter_value in (None, "")
            and group
        ):
            filter_value = (
                group.get("values")
                or {}
            ).get(filter_name)

        if filter_value in (None, ""):
            raise ValueError(
                "filter_value가 없습니다. "
                f"filter_type={filter_type} "
                f"filter_name={filter_name}"
            )

        filter_parameter = str(
            filter_parameter
        )
        filter_value = str(
            filter_value
        )

        filter_label = str(
            params.get("filter_label")
            or (
                group.get("label")
                if group
                else filter_type
            )
        )

        sort_code = str(
            params.get(
                "sort_code"
            )
            or DEFAULT_SORT_CODE
        )

        gender = str(
            params.get("gender")
            or "A"
        )

        limit = int(
            params.get(
                "limit",
                DEFAULT_LIMIT,
            )
        )

        page_size = int(
            params.get(
                "page_size",
                DEFAULT_PAGE_SIZE,
            )
        )

        with MusinsaUsedFilterCollector() as collector:
            products = collector.collect(
                category_id=category_id,
                category_name=category_name,
                filter_type=filter_type,
                filter_name=filter_name,
                filter_parameter=filter_parameter,
                filter_value=filter_value,
                sort_code=sort_code,
                gender=gender,
                page_size=page_size,
                limit=limit,
            )

        collected_at = datetime.now(
            timezone.utc
        ).isoformat()

        source_url = (
            target_url
            or self._build_source_url(
                category_id=category_id,
                filter_parameter=(
                    filter_parameter
                ),
                filter_value=filter_value,
                sort_code=sort_code,
                gender=gender,
                page_size=page_size,
            )
        )

        ranking = {
            "source_url":
                source_url,
            "observation_type":
                "FILTER",
            "filter_type":
                filter_type,
            "filter_label":
                filter_label,
            "filter_name":
                filter_name,
            "filter_parameter":
                filter_parameter,
            "filter_value":
                filter_value,
            "category_id":
                category_id,
            "category_name":
                category_name,
            "gender":
                gender,
            "sort":
                sort_code,
            "sort_code":
                sort_code,
            "requested_limit":
                limit,
            "discovered_count":
                len(products),
            "collected_at":
                collected_at,
        }

        payload = {
            "schema_version":
                "MUSINSA_USED_FILTER_V2",
            "source":
                self.SOURCE,
            "entity_type":
                "RANKING",
            "ranking":
                ranking,
            "ranking_items":
                products,
            "products":
                products,
            "errors":
                [],
        }

        return {
            "entity_type":
                "RANKING",

            "source_entity_id":
                (
                    "musinsa-used-filter:"
                    f"{category_id}:"
                    f"{filter_type}:"
                    f"{filter_name}:"
                    f"{gender}:"
                    f"{sort_code}"
                ),

            "source_url":
                source_url,

            "collected_at":
                collected_at,

            "http_status":
                200,

            "content_type":
                "application/json",

            "payload":
                payload,

            "discovered_count":
                len(products),

            "success_count":
                len(products),

            "failure_count":
                0,
        }

    @staticmethod
    def _build_source_url(
        *,
        category_id: str,
        filter_parameter: str,
        filter_value: str,
        sort_code: str,
        gender: str,
        page_size: int,
    ) -> str:
        return (
            API_URL
            + "?"
            + urlencode({
                "gf": gender,
                filter_parameter:
                    filter_value,
                "sortCode":
                    sort_code,
                "category":
                    category_id,
                "size":
                    page_size,
                "testGroup":
                    "",
                "ampGroup":
                    "",
                "caller":
                    "CATEGORY",
                "page":
                    1,
                "seen":
                    0,
                "seenAds":
                    "",
            })
        )
