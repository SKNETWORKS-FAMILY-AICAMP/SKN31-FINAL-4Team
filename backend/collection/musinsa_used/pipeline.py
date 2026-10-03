from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse

from collection.common.pipeline import BasePlatformPipeline
from collection.common.schemas import CollectionResult
from collection.musinsa.collector import MusinsaCollector
from collection.musinsa.constants import PRODUCT_BASE_URL

from .filter_collector import MusinsaUsedFilterCollector
from .filter_config import (
    API_URL,
    DEFAULT_LIMIT,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_CODE,
    PRODUCT_URL,
    get_filter_group,
)


class MusinsaUsedPipeline(BasePlatformPipeline):
    SOURCE_CODE = "musinsa_used"
    SOURCE = SOURCE_CODE

    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> CollectionResult:
        target_type = (target_type or "").strip().upper()
        params = dict(params or {})

        if target_type == "PRODUCT":
            return self._collect_product(params=params)

        if target_type != "RANKING":
            raise ValueError(
                "musinsa_used는 RANKING/PRODUCT target만 지원합니다."
            )

        observation_type = str(
            params.get("observation_type") or "RANKING"
        ).strip().upper()

        if observation_type == "FILTER":
            return self._collect_filter_ranking(
                target_url=target_url,
                params=params,
            )

        return self._collect_ranking(
            target_url=target_url,
            params=params,
        )

    # ============================================================
    # PRODUCT
    # ============================================================

    def _collect_product(
        self,
        *,
        params: dict,
    ) -> CollectionResult:
        goods_no = params.get("goods_no")

        if goods_no in (None, ""):
            raise ValueError(
                "MUSINSA_USED PRODUCT goods_no가 없습니다."
            )

        goods_no = str(goods_no)
        collected_at = datetime.now(timezone.utc)

        with MusinsaUsedFilterCollector() as collector:
            record = collector.collect_product(
                goods_no,
                ranking_context={
                    "observation_type": "PRODUCT",
                },
            )

        return CollectionResult(
            source_code=self.SOURCE_CODE,
            entity_type="PRODUCT",
            source_entity_id=goods_no,
            source_url=PRODUCT_URL.format(
                goods_no=goods_no,
            ),
            collected_at=collected_at,
            http_status=(
                (record.get("meta") or {}).get(
                    "http_status"
                )
            ),
            payload=record,
            discovered_count=1,
            success_count=1,
            failure_count=0,
            metadata={
                "content_type": "application/json",
            },
        )

    # ============================================================
    # NORMAL USED RANKING
    # ============================================================

    def _collect_ranking(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> CollectionResult:
        if not target_url:
            raise ValueError(
                "MUSINSA_USED RANKING target_url이 없습니다."
            )

        limit_raw = params.get("limit")
        limit = (
            int(limit_raw)
            if limit_raw not in (None, "")
            else None
        )

        collected_at_dt = datetime.now(timezone.utc)
        collected_at = collected_at_dt.isoformat()

        products: list[dict] = []
        detail_errors: list[dict] = []

        # 일반 USED 랭킹 discovery는 기존 Musinsa ranking API 구조를 사용한다.
        with MusinsaCollector() as ranking_collector:
            ranking_items = (
                ranking_collector.discover_ranking(
                    target_url
                )
            )

        if limit is not None:
            ranking_items = ranking_items[:limit]

        # 상세 상품은 USED 전용 parser/collector로 수집한다.
        with MusinsaUsedFilterCollector() as used_collector:
            for ranking_item in ranking_items:
                goods_no = (
                    ranking_item.get("goods_no")
                    or ranking_item.get(
                        "source_product_id"
                    )
                )

                if goods_no in (None, ""):
                    detail_errors.append({
                        "rank": ranking_item.get("rank"),
                        "goods_no": None,
                        "endpoint": "PRODUCT_DETAIL",
                        "error_type": "MissingGoodsNo",
                        "error_reason": (
                            "ranking item에 goods_no가 없습니다."
                        ),
                    })
                    continue

                goods_no = str(goods_no)

                ranking_context = {
                    "rank": ranking_item.get("rank"),
                }

                try:
                    record = (
                        used_collector.collect_product(
                            goods_no,
                            ranking_context=ranking_context,
                        )
                    )

                    detail_errors.extend(
                        (record.get("meta") or {}).get(
                            "enrichment_errors"
                        )
                        or []
                    )

                    products.append(record)

                except Exception as exc:
                    detail_errors.append({
                        "rank": ranking_item.get("rank"),
                        "goods_no": goods_no,
                        "product_url": (
                            ranking_item.get(
                                "product_url"
                            )
                        ),
                        "endpoint": "PRODUCT_DETAIL",
                        "error_type": (
                            exc.__class__.__name__
                        ),
                        "error_reason": str(exc),
                    })

        ranking_scope = self._parse_ranking_scope(
            target_url
        )

        ranking = {
            **ranking_scope,
            "observation_type": "RANKING",
            "source_url": target_url,
            "requested_limit": limit,
            "discovered_count": len(
                ranking_items
            ),
            "success_count": len(products),
            "failure_count": len(
                detail_errors
            ),
            "collected_at": collected_at,
        }

        payload = {
            "schema_version": (
                "MUSINSA_USED_RANKING_V1"
            ),
            "source": self.SOURCE_CODE,
            "entity_type": "RANKING",
            "collected_at": collected_at,
            "ranking": ranking,
            "products": products,
            "related_products": {
                "musinsa_used": [],
                "musinsa": [],
            },
            "relations": [],
            "errors": detail_errors,
        }

        return CollectionResult(
            source_code=self.SOURCE_CODE,
            entity_type="RANKING",
            source_entity_id=(
                self._build_ranking_id(
                    ranking_scope
                )
            ),
            source_url=target_url,
            collected_at=collected_at_dt,
            http_status=200,
            payload=payload,
            discovered_count=len(
                ranking_items
            ),
            success_count=len(products),
            failure_count=len(
                detail_errors
            ),
            metadata={
                "content_type": (
                    "application/json"
                ),
                "observation_type": "RANKING",
                "direct_product_count": len(
                    products
                ),
            },
        )

    # ============================================================
    # FILTER USED RANKING
    # ============================================================

    def _collect_filter_ranking(
        self,
        *,
        target_url: str | None,
        params: dict,
    ) -> CollectionResult:
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
            params.get("category_name")
            or category_id
        )

        group = None

        if (
            not params.get(
                "filter_parameter"
            )
            or params.get(
                "filter_value"
            ) in (None, "")
            or not params.get(
                "filter_label"
            )
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

        if (
            not filter_parameter
            and group
        ):
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
                group.get("values") or {}
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
            params.get("sort_code")
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

        source_url = (
            target_url
            or self._build_filter_source_url(
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

        collected_at_dt = datetime.now(
            timezone.utc
        )
        collected_at = (
            collected_at_dt.isoformat()
        )

        filter_evidence = {
            "observation_type": "FILTER",
            "filter_type": filter_type,
            "filter_label": filter_label,
            "filter_name": filter_name,
            "filter_parameter": (
                filter_parameter
            ),
            "filter_value": filter_value,
            "category_id": category_id,
            "category_name": category_name,
            "gender": gender,
            "sort": sort_code,
            "sort_code": sort_code,
        }

        direct_products: list[dict] = []
        related_used_products: list[
            dict
        ] = []
        original_products: list[
            dict
        ] = []
        relations: list[dict] = []
        detail_errors: list[dict] = []

        visited: set[
            tuple[str, str]
        ] = set()

        with MusinsaUsedFilterCollector() as collector:
            ranking_items = collector.collect(
                category_id=category_id,
                category_name=category_name,
                filter_type=filter_type,
                filter_name=filter_name,
                filter_parameter=(
                    filter_parameter
                ),
                filter_value=filter_value,
                sort_code=sort_code,
                gender=gender,
                page_size=page_size,
                limit=limit,
            )

            def collect_used(
                goods_no: str,
                *,
                context: dict,
                direct_match: bool,
            ) -> dict | None:
                key = (
                    self.SOURCE_CODE,
                    goods_no,
                )

                if key in visited:
                    return None

                visited.add(key)

                try:
                    record = (
                        collector.collect_product(
                            goods_no,
                            ranking_context=context,
                        )
                    )

                    detail_errors.extend(
                        (
                            record.get("meta")
                            or {}
                        ).get(
                            "enrichment_errors"
                        )
                        or []
                    )

                    if direct_match:
                        direct_products.append(
                            record
                        )
                    else:
                        related_used_products.append(
                            record
                        )

                    return record

                except Exception as exc:
                    detail_errors.append({
                        "source": (
                            self.SOURCE_CODE
                        ),
                        "goods_no": goods_no,
                        "endpoint": (
                            "PRODUCT_DETAIL"
                        ),
                        "error_type": (
                            exc.__class__.__name__
                        ),
                        "error_reason": (
                            str(exc)
                        ),
                    })

                    return None

            with MusinsaCollector() as retail_collector:
                for ranking_item in ranking_items:
                    current_no = (
                        ranking_item.get(
                            "source_product_id"
                        )
                        or ranking_item.get(
                            "goods_no"
                        )
                    )

                    if not current_no:
                        continue

                    current_no = str(
                        current_no
                    )

                    current_context = {
                        "rank": ranking_item.get("rank"),
                    }

                    current = collect_used(
                        current_no,
                        context=(
                            current_context
                        ),
                        direct_match=True,
                    )

                    if current is None:
                        continue

                    related = (
                        current.get(
                            "related_goods"
                        )
                        or {}
                    )
                    original = (
                        related.get(
                            "original_goods"
                        )
                        or {}
                    )
                    original_no = (
                        original.get(
                            "goods_no"
                        )
                    )

                    if not original_no:
                        continue

                    original_no = str(
                        original_no
                    )

                    original_key = (
                        "musinsa",
                        original_no,
                    )

                    if (
                        original_key
                        not in visited
                    ):
                        visited.add(
                            original_key
                        )

                        try:
                            retail = (
                                retail_collector
                                .collect_product(
                                    PRODUCT_BASE_URL.format(
                                        goods_no=original_no
                                    ),
                                    collect_options=False,
                                    collect_reviews=False,
                                )
                            )

                            original_products.append(
                                self._compact_original_musinsa(
                                    original_no=original_no,
                                    payload=retail,
                                )
                            )

                        except Exception as exc:
                            detail_errors.append({
                                "source": "musinsa",
                                "goods_no": (
                                    original_no
                                ),
                                "endpoint": (
                                    "PRODUCT_DETAIL"
                                ),
                                "error_type": (
                                    exc.__class__
                                    .__name__
                                ),
                                "error_reason": (
                                    str(exc)
                                ),
                            })

                    candidate_used_nos = [
                        current_no
                    ]

                    candidate_used_nos.extend(
                        str(
                            item["goods_no"]
                        )
                        for item in (
                            related.get(
                                "used_products"
                            )
                            or []
                        )
                        if (
                            isinstance(
                                item,
                                dict,
                            )
                            and item.get(
                                "goods_no"
                            )
                        )
                    )

                    for related_no in (
                        dict.fromkeys(
                            candidate_used_nos
                        )
                    ):
                        if (
                            related_no
                            != current_no
                        ):
                            collect_used(
                                related_no,
                                context={
                                    "observation_type": (
                                        "RELATED_GOODS"
                                    ),
                                    "discovered_from": (
                                        current_no
                                    ),
                                    "expand_related": (
                                        False
                                    ),
                                },
                                direct_match=False,
                            )

                        relations.append({
                            "from_source": (
                                self.SOURCE_CODE
                            ),
                            "from_source_product_id": (
                                related_no
                            ),
                            "to_source": (
                                "musinsa"
                            ),
                            "to_source_product_id": (
                                original_no
                            ),
                            "relation_type": (
                                "RESALE_OF"
                            ),
                            "evidence_source": (
                                "MUSINSA_RELATED_GOODS"
                            ),
                        })

        ranking = {
            "source_url": source_url,
            **filter_evidence,
            "requested_limit": limit,
            "discovered_count": len(
                ranking_items
            ),
            "success_count": len(
                direct_products
            ),
            "failure_count": len(
                detail_errors
            ),
            "collected_at": collected_at,
        }

        payload = {
            "schema_version": (
                "MUSINSA_USED_FILTER_V3"
            ),
            "source": self.SOURCE_CODE,
            "entity_type": "RANKING",
            "collected_at": collected_at,
            "ranking": ranking,
            "products": direct_products,
            "related_products": {
                "musinsa_used": (
                    related_used_products
                ),
                "musinsa": (
                    original_products
                ),
            },
            "relations": relations,
            "errors": detail_errors,
        }

        return CollectionResult(
            source_code=self.SOURCE_CODE,
            entity_type="RANKING",
            source_entity_id=(
                "musinsa-used-filter:"
                f"{category_id}:"
                f"{filter_type}:"
                f"{filter_name}:"
                f"{gender}:"
                f"{sort_code}"
            ),
            source_url=source_url,
            collected_at=collected_at_dt,
            http_status=200,
            payload=payload,
            discovered_count=len(
                ranking_items
            ),
            success_count=len(
                direct_products
            ),
            failure_count=len(
                detail_errors
            ),
            metadata={
                "content_type": (
                    "application/json"
                ),
                "observation_type": (
                    "FILTER"
                ),
                "direct_product_count": (
                    len(direct_products)
                ),
                "related_used_product_count": (
                    len(
                        related_used_products
                    )
                ),
                "original_product_count": (
                    len(original_products)
                ),
                "relation_count": (
                    len(relations)
                ),
            },
        )

    @staticmethod
    def _compact_original_musinsa(
        *,
        original_no: str,
        payload: dict,
    ) -> dict:
        """RELATED 관계용 원본 무신사 상품은 브랜드/카테고리 enrichment를 저장하지 않는다."""
        payload = payload if isinstance(payload, dict) else {}
        product = payload.get("product") if isinstance(payload.get("product"), dict) else {}
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

        compact_product = {
            key: product.get(key)
            for key in (
                "goods_no",
                "style_no",
                "name",
                "name_en",
                "genders",
                "thumbnail_url",
                "product_url",
            )
            if product.get(key) not in (None, "", [], {})
        }

        compact_snapshot = {
            key: snapshot.get(key)
            for key in (
                "regular_price",
                "sale_price",
                "discount_rate",
                "currency",
                "availability",
                "is_sold_out",
            )
            if snapshot.get(key) is not None
        }

        return {
            "source": "musinsa",
            "source_product_id": str(original_no),
            "product": compact_product,
            "snapshot": compact_snapshot,
            "meta": {
                key: meta.get(key)
                for key in (
                    "request_url",
                    "final_url",
                    "http_status",
                    "content_type",
                )
                if meta.get(key) is not None
            },
        }

    # ============================================================
    # RANKING SCOPE
    # ============================================================

    @staticmethod
    def _parse_ranking_scope(
        target_url: str,
    ) -> dict:
        query = parse_qs(
            urlparse(
                target_url
            ).query,
            keep_blank_values=True,
        )

        return {
            "store_code": (
                query.get(
                    "storeCode",
                    ["used"],
                )[0]
                or "used"
            ),
            "section_id": (
                query.get(
                    "sectionId",
                    ["1830"],
                )[0]
                or "1830"
            ),
            "contents_id": (
                query.get(
                    "contentsId",
                    [""],
                )[0]
            ),
            "category_code": (
                query.get(
                    "categoryCode",
                    [""],
                )[0]
            ),
            "gender": (
                query.get(
                    "gf",
                    ["A"],
                )[0]
                or "A"
            ),
            "age_band": (
                query.get(
                    "ageBand",
                    ["AGE_BAND_ALL"],
                )[0]
                or "AGE_BAND_ALL"
            ),
            "sub_pan": (
                query.get(
                    "subPan",
                    ["product"],
                )[0]
                or "product"
            ),
            "period": (
                query.get(
                    "period",
                    ["DAILY"],
                )[0]
                or "DAILY"
            ),
            "ranking_type": (
                "VIEW_ONE_DAY_DIFF"
            ),
        }

    @staticmethod
    def _build_ranking_id(
        scope: dict,
    ) -> str:
        return (
            "musinsa-used-ranking:"
            f"{scope.get('category_code') or 'ALL'}:"
            f"{scope.get('gender') or 'A'}:"
            f"{scope.get('age_band') or 'AGE_BAND_ALL'}:"
            f"{scope.get('period') or 'DAILY'}"
        )

    # ============================================================
    # FILTER URL
    # ============================================================

    @staticmethod
    def _build_filter_source_url(
        *,
        category_id: str,
        filter_parameter: str,
        filter_value: str,
        sort_code: str,
        gender: str,
        page_size: int,
    ) -> str:
        return API_URL + "?" + urlencode({
            "gf": gender,
            filter_parameter: (
                filter_value
            ),
            "sortCode": sort_code,
            "category": category_id,
            "size": page_size,
            "testGroup": "",
            "ampGroup": "",
            "caller": "CATEGORY",
            "page": 1,
            "seen": 0,
            "seenAds": "",
        })
