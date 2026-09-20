from __future__ import annotations

import time
from typing import Any

from curl_cffi import requests
import json
from bs4 import BeautifulSoup
from .filter_config import (
    API_URL,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SLEEP_SECONDS,
    FILTER_PARAMETER_RULES,
    PRICE_ANCHOR_URL,
    PRODUCT_URL,
    RELATED_GOODS_URL,
    SALE_INFORMATION_URL,
)
from .product_parser import MusinsaUsedProductParser


class MusinsaUsedFilterCollectError(RuntimeError):
    pass


class MusinsaUsedFilterCollector:
    """
    MUSINSA USED filter PLP collector.

    - curl_cffi Chrome impersonation 사용
    - 첫 페이지 전에 MUSINSA 페이지를 한 번 열어 세션/cookie bootstrap
    - 2페이지부터는 API가 내려준 pagination.nextPageUrl을 그대로 사용
      (hmacId 포함)
    """

    def __init__(
        self,
        *,
        timeout: int = 20,
        sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
        impersonate: str = "chrome",
    ):
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds

        self.session = requests.Session(
            impersonate=impersonate,
        )

        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.musinsa.com/",
            "Origin": "https://www.musinsa.com",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        })

        self._bootstrapped = False

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        self.close()

    def close(self):
        self.session.close()

    def _bootstrap(
        self,
        *,
        category_id: str,
    ) -> None:
        if self._bootstrapped:
            return

        # 실패해도 API 호출 자체는 시도한다.
        urls = [
            "https://www.musinsa.com/",
            f"https://www.musinsa.com/category/{category_id}/goods",
        ]

        for url in urls:
            try:
                self.session.get(
                    url,
                    timeout=self.timeout,
                )
            except Exception:
                pass

        self._bootstrapped = True

    def _get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        referer: str | None = None,
    ) -> dict:
        headers = {"Referer": referer} if referer else None
        response = self.session.get(
            url,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            raise MusinsaUsedFilterCollectError(
                "MUSINSA_USED API 요청 실패 "
                f"status={response.status_code} "
                f"url={response.url} "
                f"body={response.text[:700]}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise MusinsaUsedFilterCollectError(
                "MUSINSA_USED 응답 JSON 파싱 실패 "
                f"url={response.url} "
                f"body={response.text[:700]}"
            ) from exc

        if not isinstance(body, dict):
            raise MusinsaUsedFilterCollectError(
                "MUSINSA_USED API root가 dict가 아닙니다."
            )

        meta = body.get("meta") or {}

        if meta.get("result") not in {
            None,
            "SUCCESS",
        }:
            raise MusinsaUsedFilterCollectError(
                f"MUSINSA_USED API 실패: {meta}"
            )

        return body

    @staticmethod
    def extract_filter_metadata(
        raw: dict,
    ) -> list[dict]:

        FILTER_TYPE_BY_PARAMETER = {
            "attributePattern": "pattern",
            "attributeMaterial": "material",
            "attributeFit": "fit",
            "color": "color",
            "conditionGradeCodes": "condition",
            "attributeCooling": "cooling",
            "standardSize": "standard_size",
            "measurement": "measurement",
            "shoeSize": "shoe_size",
            "attribute": "attribute",
            "saleType": "sale_type",
            "theme": "theme",
        }

        detail = raw.get("detail") or {}

        results = []

        if not isinstance(
            detail,
            dict,
        ):
            return results

        for group_key, group in detail.items():

            if not isinstance(
                group,
                dict,
            ):
                continue

            filter_label = (
                group.get("title")
                or group_key
            )

            items = (
                group.get("list")
                or []
            )

            if not isinstance(
                items,
                list,
            ):
                continue

            for item in items:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                parameter = item.get(
                    "parameterKey"
                )

                filter_name = item.get(
                    "displayText"
                )

                filter_value = item.get(
                    "value"
                )

                if (
                    not parameter
                    or not filter_name
                    or filter_value in (
                        None,
                        "",
                    )
                ):
                    continue

                filter_type = (
                    FILTER_TYPE_BY_PARAMETER
                    .get(
                        parameter
                    )
                )

                # 우리가 수집 대상으로 정의하지 않은 필터는 제외
                if not filter_type:
                    continue

                results.append({
                    "filter_type":
                        filter_type,

                    "filter_label":
                        filter_label,

                    "filter_name":
                        str(
                            filter_name
                        ).strip(),

                    "filter_parameter":
                        str(
                            parameter
                        ).strip(),

                    "filter_value":
                        str(
                            filter_value
                        ).strip(),

                    "filter_group_key":
                        group_key,
                })

        return results

    def collect_filter_metadata(
        self,
        *,
        category_id: str,
    ) -> dict:
        """
        MUSINSA category page SSR(__NEXT_DATA__)에서
        category/filters 데이터를 추출한다.
        """

        url = (
            f"https://www.musinsa.com/category/"
            f"{category_id}/goods"
        )

        response = self.session.get(
            url,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            raise MusinsaUsedFilterCollectError(
                "MUSINSA_USED filter metadata page 요청 실패 "
                f"status={response.status_code} "
                f"url={url}"
            )

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        script = soup.find(
            "script",
            id="__NEXT_DATA__",
        )

        if script is None or not script.string:
            raise MusinsaUsedFilterCollectError(
                "__NEXT_DATA__를 찾지 못했습니다."
            )

        try:
            next_data = json.loads(
                script.string
            )
        except json.JSONDecodeError as exc:
            raise MusinsaUsedFilterCollectError(
                "__NEXT_DATA__ JSON 파싱 실패"
            ) from exc

        queries = (
            next_data
            .get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )

        for query in queries:
            if not isinstance(query, dict):
                continue

            query_key = (
                query.get("queryKey")
                or []
            )

            if (
                isinstance(query_key, list)
                and len(query_key) >= 2
                and query_key[0] == "category/filters"
                and str(query_key[1]) == str(category_id)
            ):
                data = (
                    query
                    .get("state", {})
                    .get("data", {})
                    .get("data", {})
                )

                if isinstance(data, dict):
                    return data

        raise MusinsaUsedFilterCollectError(
            "category/filters metadata를 찾지 못했습니다. "
            f"category_id={category_id}"
        )

    def collect_product(
        self,
        goods_no: str,
        *,
        ranking_context: dict | None = None,
    ) -> dict:
        """Reuse the v2 collector session for one complete USED PRODUCT."""
        goods_no = str(goods_no)
        product_url = PRODUCT_URL.format(goods_no=goods_no)
        response = self.session.get(product_url, timeout=self.timeout)
        if response.status_code != 200:
            raise MusinsaUsedFilterCollectError(
                "MUSINSA_USED detail request failed "
                f"goods_no={goods_no} status={response.status_code}"
            )

        enrichments: dict[str, dict | None] = {}
        errors: list[dict] = []
        endpoints = {
            "sale_information": SALE_INFORMATION_URL,
            "related_goods": RELATED_GOODS_URL,
            "price_anchor": PRICE_ANCHOR_URL,
        }
        for name, template in endpoints.items():
            try:
                enrichments[name] = self._get_json(
                    template.format(goods_no=goods_no),
                    referer=product_url,
                )
            except Exception as exc:
                enrichments[name] = None
                errors.append({
                    "source": "MUSINSA_USED",
                    "goods_no": goods_no,
                    "endpoint": name,
                    "error_type": exc.__class__.__name__,
                    "error_reason": str(exc),
                })

        return MusinsaUsedProductParser.parse(
            response.text,
            goods_no=goods_no,
            sale_information=enrichments["sale_information"],
            related_goods_response=enrichments["related_goods"],
            price_anchor=enrichments["price_anchor"],
            ranking_context=ranking_context,
            meta={
                "request_url": product_url,
                "final_url": str(response.url),
                "http_status": response.status_code,
                "content_type": response.headers.get("Content-Type"),
                "enrichment_errors": errors,
            },
        )

    @staticmethod
    def normalize_item(
        raw: dict[str, Any],
        *,
        rank: int,
        context: dict,
    ) -> dict:
        """
        원본 키를 버리지 않고 alias + ranking_context를 추가한다.
        """
        item = dict(raw)

        goods_no = raw.get("goodsNo")

        item.update({
            "rank":
                rank,

            "source_product_id":
                (
                    str(goods_no)
                    if goods_no is not None
                    else None
                ),

            "goods_id":
                (
                    str(goods_no)
                    if goods_no is not None
                    else None
                ),

            "product_name":
                raw.get("goodsName"),

            "name":
                raw.get("goodsName"),

            "product_url":
                raw.get("goodsLinkUrl"),

            "thumbnail_url":
                raw.get("thumbnail"),

            "image_url":
                raw.get("thumbnail"),

            "gender":
                raw.get("displayGenderText"),

            "normal_price":
                raw.get("normalPrice"),

            "regular_price":
                raw.get("normalPrice"),

            "list_price":
                raw.get("normalPrice"),

            "sale_price":
                (
                    raw.get("finalPrice")
                    if raw.get("finalPrice")
                    is not None
                    else raw.get("price")
                ),

            "final_price":
                raw.get("finalPrice"),

            "discount_rate":
                (
                    raw.get("finalDiscount")
                    if raw.get("finalDiscount")
                    is not None
                    else raw.get("saleRate")
                ),

            "is_sold_out":
                raw.get("isSoldOut"),

            "used_condition_grade":
                raw.get("usedConditionGrade"),

            "ranking_context": {
                **context,
                "rank": rank,
                "goods_no": (
                    str(goods_no)
                    if goods_no is not None
                    else None
                ),
                "product_name": raw.get("goodsName"),
                "product_url": raw.get("goodsLinkUrl"),
                "thumbnail_url": raw.get("thumbnail"),
                "brand_code": raw.get("brand"),
                "brand_name": raw.get("brandName"),
                "normal_price": raw.get("normalPrice"),
                "price": (
                    raw.get("finalPrice")
                    if raw.get("finalPrice") is not None
                    else raw.get("price")
                ),
                "discount_rate": (
                    raw.get("finalDiscount")
                    if raw.get("finalDiscount") is not None
                    else raw.get("saleRate")
                ),
                "used_condition_grade":
                    raw.get("usedConditionGrade"),
                "is_sold_out":
                    raw.get("isSoldOut"),
            },

            "brand_info": {
                "source_brand_id": raw.get("brand"),
                "name": raw.get("brandName"),
                "url": raw.get("brandLinkUrl"),
            },

            "category": {
                "source_category_id":
                    context["category_id"],
                "name":
                    context["category_name"],
                "source_category_path":
                    f"USED>{context['category_name']}",
            },
        })

        return item

    def collect(
        self,
        *,
        category_id: str,
        category_name: str,
        filter_type: str,
        filter_name: str,
        filter_parameter: str,
        filter_value: str,
        sort_code: str,
        gender: str = "A",
        page_size: int = DEFAULT_PAGE_SIZE,
        limit: int = 100,
    ) -> list[dict]:
        self._bootstrap(
            category_id=str(category_id),
        )

        context = {
            "observation_type":
                "FILTER",
            "filter_type":
                filter_type,
            "filter_name":
                filter_name,
            "filter_parameter":
                filter_parameter,
            "filter_value":
                filter_value,
            "category_id":
                str(category_id),
            "category_name":
                category_name,
            "sort":
                sort_code,
            "sort_code":
                sort_code,
            "gender":
                gender,
        }

        params = {
            "gf":
                gender,
            filter_parameter:
                filter_value,
            "sortCode":
                sort_code,
            "category":
                str(category_id),
            "size":
                int(page_size),
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
        }

        url = API_URL
        first = True
        results: list[dict] = []

        while (
            url
            and len(results) < limit
        ):
            body = self._get_json(
                url,
                params=(
                    params
                    if first
                    else None
                ),
            )

            first = False

            data = body.get("data") or {}
            raw_items = data.get("list") or []
            pagination = (
                data.get("pagination")
                or {}
            )

            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue

                rank = len(results) + 1

                results.append(
                    self.normalize_item(
                        raw,
                        rank=rank,
                        context=context,
                    )
                )

                if len(results) >= limit:
                    break

            if not pagination.get("hasNext"):
                break

            # hmacId 포함 URL을 그대로 따라간다.
            url = pagination.get(
                "nextPageUrl"
            )

            if not url:
                break

            if self.sleep_seconds > 0:
                time.sleep(
                    self.sleep_seconds
                )

        return results[:limit]
