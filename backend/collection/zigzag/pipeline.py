from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import (
    parse_qs,
    urlparse,
)

from collection.common.pipeline import (
    BasePlatformPipeline,
)

from .collector import ZigzagCollector
from .constants import (
    DEFAULT_LIMIT,
    DEFAULT_PAGE_ID,
    DEFAULT_SORT,
    SEARCH_RESULT_API_URL,
    ZIGZAG_BASE_URL,
)


class ZigzagPipeline(
    BasePlatformPipeline
):

    SOURCE = "ZIGZAG"

    # ============================================================
    # PUBLIC
    # ============================================================

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:

        target_type = (
            str(
                target_type
                or ""
            )
            .upper()
            .strip()
        )

        params = (
            params
            or {}
        )

        if (
            target_type
            == "RANKING"
        ):
            return self._collect_ranking(
                target_url=target_url,
                params=params,
            )

        raise ValueError(
            "지원하지 않는 "
            "ZIGZAG target_type입니다: "
            f"{target_type}"
        )

    # ============================================================
    # RANKING
    # ============================================================

    def _collect_ranking(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> dict:

        # --------------------------------------------------------
        # URL QUERY PARSE
        # --------------------------------------------------------

        url_params = (
            self._parse_target_url(
                target_url
            )
        )

        # --------------------------------------------------------
        # CATEGORY
        #
        # 우선순위:
        # params.category_id
        # → URL middle_category_id
        # → URL category_id
        # --------------------------------------------------------

        category_id = (
            params.get(
                "category_id"
            )
            or url_params.get(
                "category_id"
            )
        )

        if (
            category_id is None
            or str(
                category_id
            ).strip()
            == ""
        ):
            raise ValueError(
                "ZIGZAG category_id를 "
                "찾을 수 없습니다. "
                "CrawlTarget.target_url의 "
                "middle_category_id 또는 "
                "params.category_id를 "
                "확인하세요."
            )

        category_id = (
            str(
                category_id
            )
            .strip()
        )

        # --------------------------------------------------------
        # SORT
        # --------------------------------------------------------

        sort = str(
            params.get(
                "sort"
            )
            or url_params.get(
                "sort"
            )
            or DEFAULT_SORT
        )

        # --------------------------------------------------------
        # LIMIT
        # --------------------------------------------------------

        limit = int(
            params.get(
                "limit",
                DEFAULT_LIMIT,
            )
        )

        if limit <= 0:
            raise ValueError(
                "limit은 1 이상이어야 합니다."
            )

        # --------------------------------------------------------
        # PAGE ID
        # --------------------------------------------------------

        page_id = str(
            params.get(
                "page_id",
                DEFAULT_PAGE_ID,
            )
        )

        # --------------------------------------------------------
        # ADS
        # --------------------------------------------------------

        include_ads = (
            self._as_bool(
                params.get(
                    "include_ads",
                    False,
                )
            )
        )

        # --------------------------------------------------------
        # MAX PAGES
        # --------------------------------------------------------

        max_pages_raw = (
            params.get(
                "max_pages"
            )
        )

        max_pages = (
            int(
                max_pages_raw
            )
            if max_pages_raw
            not in (
                None,
                "",
            )
            else None
        )

        # --------------------------------------------------------
        # DETAIL
        # --------------------------------------------------------

        include_detail = (
            self._as_bool(
                params.get(
                    "include_detail",
                    True,
                )
            )
        )

        detail_limit_raw = (
            params.get(
                "detail_limit",
                limit,
            )
        )

        detail_limit = int(
            detail_limit_raw
        )

        detail_limit = max(
            0,
            min(
                detail_limit,
                limit,
            ),
        )

        # --------------------------------------------------------
        # COLLECT
        # --------------------------------------------------------

        with ZigzagCollector() as collector:

            ranking_result = (
                collector
                .collect_category_ranking(
                    category_id=category_id,
                    limit=limit,
                    sort=sort,
                    page_id=page_id,
                    max_pages=max_pages,
                    include_ads=include_ads,
                )
            )

            items = (
                ranking_result.get(
                    "items"
                )
                or []
            )

            # ====================================================
            # DETAIL ENRICHMENT
            # ====================================================

            detail_success_count = 0
            detail_failure_count = 0

            if (
                include_detail
                and items
                and detail_limit > 0
            ):

                enriched = (
                    collector
                    .enrich_ranking_details(
                        items,
                        detail_limit=detail_limit,
                    )
                )

                items = (
                    enriched.get(
                        "items"
                    )
                    or items
                )

                detail_success_count = int(
                    enriched.get(
                        "detail_success_count",
                        0,
                    )
                    or 0
                )

                detail_failure_count = int(
                    enriched.get(
                        "detail_failure_count",
                        0,
                    )
                    or 0
                )

        # --------------------------------------------------------
        # COLLECTED AT
        # --------------------------------------------------------

        collected_at = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

        # --------------------------------------------------------
        # PAYLOAD
        # --------------------------------------------------------

        payload = {

            "schema_version": "2.1",

            "source": self.SOURCE,

            "document_type": "RANKING",

            "collected_at":
                collected_at,

            # ====================================================
            # TARGET
            # ====================================================

            "target": {

                "target_url":
                    target_url,

                "category_id":
                    category_id,

                "sort":
                    sort,

                "page_id":
                    page_id,

                "limit":
                    limit,

                "include_ads":
                    include_ads,

                "include_detail":
                    include_detail,

                "detail_limit":
                    detail_limit,
            },

            # ====================================================
            # RANKING
            # ====================================================

            "ranking": {

                "category_id":
                    category_id,

                "sort":
                    sort,

                "page_id":
                    page_id,

                "requested_limit":
                    limit,

                "count":
                    len(items),

                "include_detail":
                    include_detail,

                "detail_limit":
                    detail_limit,

                "detail_success_count":
                    detail_success_count,

                "detail_failure_count":
                    detail_failure_count,

                "items":
                    items,
            },

            # ====================================================
            # RAW GRAPHQL
            # ====================================================

            "raw_pages": (
                ranking_result.get(
                    "raw_pages"
                )
                or []
            ),
        }

        # --------------------------------------------------------
        # RESULT
        #
        # 여기 counts는 "랭킹 수집" 기준.
        #
        # 상세 수집 실패는
        # ranking.detail_failure_count에서 별도 관리.
        # --------------------------------------------------------

        ranking_count = (
            len(items)
        )

        return {

            "entity_type":
                "RANKING",

            "source_entity_id": (
                f"zigzag-ranking:"
                f"{category_id}"
            ),

            "source_url": (
                target_url
                or ZIGZAG_BASE_URL
            ),

            "request_url":
                SEARCH_RESULT_API_URL,

            "collected_at":
                collected_at,

            "http_status":
                200,

            "content_type":
                "application/json",

            "payload":
                payload,

            "discovered_count":
                ranking_count,

            "success_count":
                ranking_count,

            "failure_count":
                0,

            # BasePlatformPipeline.run_target()
            # 에서 전달되는 작은 데이터
            "platform_data": {

                "category_id":
                    category_id,

                "ranking_count":
                    ranking_count,

                "include_detail":
                    include_detail,

                "detail_success_count":
                    detail_success_count,

                "detail_failure_count":
                    detail_failure_count,
            },
        }

    # ============================================================
    # TARGET URL
    # ============================================================

    @staticmethod
    def _parse_target_url(
        target_url: str | None,
    ) -> dict:

        if not target_url:
            return {}

        parsed = urlparse(
            target_url
        )

        query = parse_qs(
            parsed.query
        )

        # Zigzag category URL 예:
        #
        # https://zigzag.kr/categories/-1
        # ?middle_category_id=507
        # &sort=200

        category_id = (
            query.get(
                "middle_category_id",
                [None],
            )[0]
            or query.get(
                "category_id",
                [None],
            )[0]
        )

        sort = (
            query.get(
                "sort",
                [None],
            )[0]
        )

        return {
            "category_id":
                category_id,

            "sort":
                sort,
        }

    # ============================================================
    # BOOL
    # ============================================================

    @staticmethod
    def _as_bool(
        value,
    ) -> bool:

        if isinstance(
            value,
            bool,
        ):
            return value

        if value is None:
            return False

        if isinstance(
            value,
            int,
        ):
            return bool(
                value
            )

        value = (
            str(
                value
            )
            .strip()
            .lower()
        )

        return value in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }