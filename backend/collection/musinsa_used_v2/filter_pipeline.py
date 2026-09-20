from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from collection.common.pipeline import (
    BasePlatformPipeline,
)
from collection.musinsa.collector import MusinsaCollector
from collection.musinsa.constants import PRODUCT_BASE_URL

from .filter_collector import (
    MusinsaUsedFilterCollector,
)
from .filter_config import (
    API_URL,
    DEFAULT_LIMIT,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_CODE,
    PRODUCT_URL,
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
        target_type = (target_type or "").upper()
        params = dict(params or {})

        if target_type == "PRODUCT":
            goods_no = params.get("goods_no")
            if goods_no in (None, ""):
                raise ValueError("MUSINSA_USED PRODUCT goods_no가 없습니다.")
            collected_at = datetime.now(timezone.utc).isoformat()
            with MusinsaUsedFilterCollector() as collector:
                record = collector.collect_product(
                    str(goods_no),
                    ranking_context={"observation_type": "PRODUCT"},
                )
            return {
                "entity_type": "PRODUCT",
                "source_entity_id": str(goods_no),
                "source_url": PRODUCT_URL.format(goods_no=goods_no),
                "collected_at": collected_at,
                "http_status": (record.get("meta") or {}).get("http_status"),
                "content_type": "application/json",
                "payload": record,
                "discovered_count": 1,
                "success_count": 1,
                "failure_count": 0,
            }

        if target_type != "RANKING":
            raise ValueError(
                "MUSINSA_USED FILTER는 "
                "RANKING/PRODUCT target만 지원합니다."
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
            ranking_items = collector.collect(
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


            collected_at = datetime.now(timezone.utc).isoformat()
            product_raws: list[dict] = []
            relations: list[dict] = []
            detail_errors: list[dict] = []
            used_records: dict[str, dict] = {}
            visited: set[tuple[str, str]] = set()

            def upload_product(*, source: str, goods_no: str, payload: dict):
                uploaded = self.storage.upload_raw_json(
                    source=source,
                    entity_type="PRODUCT",
                    source_entity_id=goods_no,
                    collected_at=collected_at,
                    data=payload,
                )
                product_raws.append({
                    "source": source,
                    "entity_type": "PRODUCT",
                    "source_entity_id": goods_no,
                    "source_url": (
                        PRODUCT_URL.format(goods_no=goods_no)
                        if source == self.SOURCE
                        else PRODUCT_BASE_URL.format(goods_no=goods_no)
                    ),
                    "collected_at": collected_at,
                    "http_status": (payload.get("meta") or {}).get("http_status"),
                    "content_type": "application/json",
                    "s3": {
                        "bucket": uploaded.bucket,
                        "key": uploaded.key,
                        "uri": uploaded.uri,
                    },
                })

            def collect_used(goods_no: str, context: dict) -> dict | None:
                key = (self.SOURCE, goods_no)
                if key in visited:
                    return used_records.get(goods_no)
                visited.add(key)
                try:
                    record = collector.collect_product(
                        goods_no,
                        ranking_context=context,
                    )
                    used_records[goods_no] = record
                    detail_errors.extend(
                        (record.get("meta") or {}).get("enrichment_errors")
                        or []
                    )
                    upload_product(
                        source=self.SOURCE,
                        goods_no=goods_no,
                        payload=record,
                    )
                    return record
                except Exception as exc:
                    detail_errors.append({
                        "source": self.SOURCE,
                        "goods_no": goods_no,
                        "endpoint": "PRODUCT_DETAIL",
                        "error_type": exc.__class__.__name__,
                        "error_reason": str(exc),
                    })
                    return None

            with MusinsaCollector() as retail_collector:
                for ranking_item in ranking_items:
                    current_no = ranking_item.get("source_product_id")
                    if not current_no:
                        continue
                    current_no = str(current_no)
                    current = collect_used(
                        current_no,
                        {**ranking_item, "expand_related": True},
                    )
                    if current is None:
                        continue

                    related = current.get("related_goods") or {}
                    original = related.get("original_goods") or {}
                    original_no = original.get("goods_no")
                    if not original_no:
                        continue
                    original_no = str(original_no)
                    original_key = ("MUSINSA", original_no)
                    if original_key not in visited:
                        visited.add(original_key)
                        try:
                            retail = retail_collector.collect_product(
                                PRODUCT_BASE_URL.format(goods_no=original_no),
                                collect_options=True,
                                collect_reviews=True,
                                review_limit=20,
                            )
                            upload_product(
                                source="MUSINSA",
                                goods_no=original_no,
                                payload=retail,
                            )
                        except Exception as exc:
                            detail_errors.append({
                                "source": "MUSINSA",
                                "goods_no": original_no,
                                "endpoint": "PRODUCT_DETAIL",
                                "error_type": exc.__class__.__name__,
                                "error_reason": str(exc),
                            })

                    candidate_used_nos = [current_no]
                    candidate_used_nos.extend(
                        str(item["goods_no"])
                        for item in related.get("used_products") or []
                        if isinstance(item, dict) and item.get("goods_no")
                    )
                    for related_no in dict.fromkeys(candidate_used_nos):
                        if related_no != current_no:
                            collect_used(
                                related_no,
                                {
                                    "observation_type": "RELATED_GOODS",
                                    "discovered_from": current_no,
                                    "expand_related": False,
                                },
                            )
                        relations.append({
                            "from_source": self.SOURCE,
                            "from_source_product_id": related_no,
                            "to_source": "MUSINSA",
                            "to_source_product_id": original_no,
                            "relation_type": "RESALE_OF",
                            "evidence_source": "MUSINSA_RELATED_GOODS",
                        })

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
                len(ranking_items),
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
                ranking_items,
            "products":
                [],
            "errors":
                detail_errors,
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
                len(ranking_items),

            "success_count":
                len(product_raws),

            "failure_count":
                len(detail_errors),

            "platform_data": {
                "product_raws": product_raws,
                "relations": relations,
                "visited": [list(key) for key in sorted(visited)],
                "detail_errors": detail_errors,
            },
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
