from __future__ import annotations

import random
import time
from typing import Any

import requests

from .config import (
    CNV_ENDPOINT,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
)
from .query import GET_CNV_PAGE_ACTION_QUERY


class ZigzagCnvError(RuntimeError):
    pass


class ZigzagCnvCollector:
    def __init__(
        self,
        *,
        min_delay: float = DEFAULT_MIN_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        timeout: int = 20,
        session: requests.Session | None = None,
    ):
        self.min_delay = float(min_delay)
        self.max_delay = float(max_delay)
        self.timeout = int(timeout)
        self.session = session or requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://zigzag.kr",
                "Referer": "https://zigzag.kr/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/152.0.0.0 Safari/537.36"
                ),
            }
        )

    def close(self) -> None:
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ============================================================
    # HTTP
    # ============================================================

    def _post(
        self,
        payload: list[dict[str, Any]],
        *,
        max_retries: int = 4,
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = self.session.post(
                    CNV_ENDPOINT,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")

                    if retry_after:
                        try:
                            wait_seconds = float(retry_after)
                        except ValueError:
                            wait_seconds = 0.0
                    else:
                        wait_seconds = 0.0

                    if wait_seconds <= 0:
                        wait_seconds = (
                            min(60.0, 2 ** attempt)
                            + random.uniform(0.5, 1.5)
                        )

                    if attempt >= max_retries:
                        raise ZigzagCnvError(
                            f"Zigzag HTTP 429 after retries: {response.text[:500]}"
                        )

                    time.sleep(wait_seconds)
                    continue

                response.raise_for_status()

                data = response.json()

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("errors"):
                            raise ZigzagCnvError(
                                f"GraphQL errors: {item['errors']}"
                            )

                return data

            except (requests.RequestException, ValueError, ZigzagCnvError) as exc:
                last_error = exc

                if attempt >= max_retries:
                    break

                time.sleep(
                    min(30.0, 2 ** attempt)
                    + random.uniform(0.3, 1.0)
                )

        raise ZigzagCnvError(
            f"Zigzag CNV request failed: {last_error}"
        ) from last_error

    # ============================================================
    # FILTER
    # ============================================================
    @staticmethod
    def _to_int(value):
        if value is None or isinstance(value, bool):
            return None

        try:
            return int(
                float(
                    str(value)
                    .replace(",", "")
                    .strip()
                )
            )
        except (TypeError, ValueError):
            return None


    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value

        if value is None:
            return None

        text = str(value).strip().lower()

        if text in {"true", "1", "yes", "y"}:
            return True

        if text in {"false", "0", "no", "n"}:
            return False

        return None
        
    @staticmethod
    def make_combined_tag(
        value: str,
        *,
        attribute: str,
        name: str,
    ) -> dict[str, Any]:
        return {
            "filter_type": "COMBINED_TAG",
            "value_list": [
                {
                    "label": value,
                    "value": value,
                    "attribute": attribute,
                    "name": name,
                    "rangeGte": None,
                    "rangeLte": None,
                    "campaignId": None,
                    "campaignTagType": None,
                }
            ],
        }

    @staticmethod
    def build_search_state(
        *,
        category_id: str,
        order: str,
        filters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        filter_list: list[dict[str, Any]] = [
            {
                "filter_type": "CATEGORY",
                "value_list": [
                    {
                        "label": None,
                        "value": str(category_id),
                        "attribute": None,
                        "name": None,
                        "rangeGte": None,
                        "rangeLte": None,
                        "campaignId": None,
                        "campaignTagType": None,
                    }
                ],
            }
        ]

        if filters:
            filter_list.extend(filters)

        return {
            "filter_list": filter_list,
            "order": order,
        }

    # ============================================================
    # REQUEST
    # ============================================================

    def fetch_initial(
        self,
        *,
        category_id: str,
        layout_id: str,
        action_id: str,
        module_slot_id: str,
        order: str,
        filters: list[dict[str, Any]] | None = None,
    ) -> Any:
        search_state = self.build_search_state(
            category_id=category_id,
            order=order,
            filters=filters,
        )

        payload = [
            {
                "operationName": "GetCnvPageAction",
                "variables": {
                    "layout_id": str(layout_id),
                    "input_list": [
                        {
                            "action_id": action_id,
                            "type": "MODULE_REFETCH",
                            "target": {
                                "module_slot_id": module_slot_id,
                            },
                            "option": {
                                "__typename": "CnvModuleRefetchActionOption",
                                "type": "MODULE_REFETCH",
                                "server_option": {
                                    "delay": 0,
                                    "tryCount": 1,
                                    "initial": True,
                                    "renderParams": [
                                        {
                                            "changedFilterType": None,
                                            "filterDetailUiHints": {
                                                "keywordsByFilterType": {},
                                                "rangeBoundsByType": {},
                                            },
                                            "search_query_state": search_state,
                                            "base_search_query_state": None,
                                            "type": "SEARCH_FILTER_CHANGE",
                                        }
                                    ],
                                    "includeSelfOnUnwrap": True,
                                    "type": "MODULE_REFETCH",
                                },
                                "delay": 0,
                            },
                        }
                    ],
                },
                "query": GET_CNV_PAGE_ACTION_QUERY,
            }
        ]

        return self._post(payload)

    def fetch_next(
        self,
        *,
        layout_id: str,
        action_id: str,
        module_slot_id: str,
        server_option: dict[str, Any],
    ) -> Any:
        payload = [
            {
                "operationName": "GetCnvPageAction",
                "variables": {
                    "layout_id": str(layout_id),
                    "input_list": [
                        {
                            "action_id": action_id,
                            "type": "PAGINATION",
                            "target": {
                                "module_slot_id": module_slot_id,
                            },
                            "option": {
                                "__typename": "CnvBaseActionOption",
                                "type": "PAGINATION",
                                "server_option": server_option,
                            },
                        }
                    ],
                },
                "query": GET_CNV_PAGE_ACTION_QUERY,
            }
        ]

        time.sleep(
            random.uniform(
                self.min_delay,
                self.max_delay,
            )
        )

        return self._post(payload)

    # ============================================================
    # RESPONSE WALKERS
    # ============================================================

    @staticmethod
    def _walk(value: Any):
        yield value

        if isinstance(value, dict):
            for child in value.values():
                yield from ZigzagCnvCollector._walk(child)

        elif isinstance(value, list):
            for child in value:
                yield from ZigzagCnvCollector._walk(child)

    @staticmethod
    def _get_result(data: Any) -> dict[str, Any]:
        if not isinstance(data, list) or not data:
            raise ZigzagCnvError(
                "CNV response top-level is not a non-empty list."
            )

        first = data[0]

        if not isinstance(first, dict):
            raise ZigzagCnvError(
                "CNV response first item is not an object."
            )

        result = (
            (first.get("data") or {}).get("result")
        )

        if not isinstance(result, dict):
            raise ZigzagCnvError(
                "CNV response data.result was not found."
            )

        return result

    def parse_products(
        self,
        data: Any,
    ) -> list[dict[str, Any]]:

        products: list[dict[str, Any]] = []

        for node in self._walk(data):

            if not isinstance(node, dict):
                continue

            # ========================================================
            # 실제 구조
            #
            # wrapper
            # {
            #     "product_card": {
            #         "product_id": ...,
            #         "product": {...},
            #         "price": {...},
            #         ...
            #     },
            #     "ubl": {
            #         "server_log": {...}
            #     }
            # }
            # ========================================================

            card = node.get("product_card")

            if not isinstance(card, dict):
                continue

            product_id = card.get("product_id")

            product = card.get("product")

            if (
                not product_id
                or not isinstance(product, dict)
            ):
                continue

            # --------------------------------------------------------
            # PRODUCT
            # --------------------------------------------------------

            image = (
                product.get("image")
                if isinstance(
                    product.get("image"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # PRICE
            # card.price 임
            # --------------------------------------------------------

            price = (
                card.get("price")
                if isinstance(
                    card.get("price"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # REVIEW
            # --------------------------------------------------------

            review = (
                card.get("review")
                if isinstance(
                    card.get("review"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # SHOP
            # --------------------------------------------------------

            shop = (
                card.get("shop")
                if isinstance(
                    card.get("shop"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # SHIPPING
            # --------------------------------------------------------

            shipping = (
                card.get("shipping")
                if isinstance(
                    card.get("shipping"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # ENGAGEMENT
            # --------------------------------------------------------

            engagement = (
                card.get("engagement")
                if isinstance(
                    card.get("engagement"),
                    dict,
                )
                else {}
            )

            fomo = (
                engagement.get("fomo")
                if isinstance(
                    engagement.get("fomo"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # META
            # --------------------------------------------------------

            meta = (
                card.get("meta")
                if isinstance(
                    card.get("meta"),
                    dict,
                )
                else {}
            )

            shop_meta = (
                meta.get("shop")
                if isinstance(
                    meta.get("shop"),
                    dict,
                )
                else {}
            )

            state = (
                meta.get("state")
                if isinstance(
                    meta.get("state"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # UBL
            #
            # 중요:
            # ubl은 card 안이 아니라
            # card를 감싸고 있는 wrapper(node)에 있음
            # --------------------------------------------------------

            ubl = (
                node.get("ubl")
                if isinstance(
                    node.get("ubl"),
                    dict,
                )
                else {}
            )

            server_log = (
                ubl.get("server_log")
                if isinstance(
                    ubl.get("server_log"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # OUTPUT
            # --------------------------------------------------------

            products.append(
                {
                    "product_id":
                        str(product_id),

                    "product_name":
                        product.get("title"),

                    "image_url":
                        image.get("normal"),

                    "shop_id":
                        shop_meta.get("shop_id"),

                    "shop_name":
                        shop.get("name"),

                    "final_price":
                        price.get("final_price"),

                    "max_price":
                        price.get("max_price"),

                    "discount_rate":
                        price.get(
                            "final_price_discount_rate"
                        ),

                    "review_count": self._to_int(
                        review.get("count")
                    ),

                    "review_score":
                        review.get("score"),

                    "sales_status":
                        state.get("sales_status"),

                    "shipping_type":
                        state.get("shipping_type"),

                    "arrival_text":
                        shipping.get(
                            "arrival_text"
                        ),

                    "is_saved_product":
                        engagement.get(
                            "is_saved_product"
                        ),

                    "fomo_text":
                        fomo.get("fomo_text"),

                    # --------------------------------------------
                    # server log
                    # --------------------------------------------

                    "social_proof_value":
                        server_log.get(
                            "social_proof_value"
                        ),

                    "organic_position":
                        server_log.get(
                            "organic_position"
                        ),

                    "display_category_id":
                        server_log.get(
                            "display_category_id"
                        ),

                    "is_new": self._to_bool(
                        server_log.get("is_new")
                    ),

                    "is_ad":
                        bool(
                            server_log.get("ad_key")
                        ),

                    "recommend_score":
                        server_log.get(
                            "recommend_score"
                        ),

                    "badge_list":
                        server_log.get(
                            "badge_list"
                        ),

                    "server_log":
                        server_log,
                }
            )

        return products

    def extract_result_count(
        self,
        data: Any,
    ) -> int | None:
        for node in self._walk(data):
            if not isinstance(node, dict):
                continue

            value = node.get("result_count")

            if isinstance(value, bool):
                continue

            if isinstance(value, (int, float)):
                return int(value)

            if isinstance(value, str):
                try:
                    return int(
                        value.replace(",", "").strip()
                    )
                except ValueError:
                    pass

        return None

    def extract_pagination(
        self,
        data: Any,
    ) -> dict[str, Any] | None:
        for node in self._walk(data):
            if not isinstance(node, dict):
                continue

            if str(node.get("type") or "").upper() != "PAGINATION":
                continue

            option = node.get("option")

            if not isinstance(option, dict):
                continue

            server_option = option.get("server_option")

            if not isinstance(server_option, dict):
                continue
            return {
                "action": node,
                "server_option": server_option,
            }

        return None

    def get_next_request_info(
        self,
        data: Any,
    ) -> dict[str, Any] | None:
        pagination = self.extract_pagination(data)

        if not pagination:
            return None

        action = pagination["action"]
        server_option = pagination["server_option"]

        target = (
            action.get("target")
            if isinstance(action.get("target"), dict)
            else {}
        )

        module_slot_id = (
            target.get("module_slot_id")
            or server_option.get("moduleSlotId")
        )

        if not module_slot_id:
            return None

        return {
            "module_slot_id": module_slot_id,
            "server_option": server_option,
        }

    # ============================================================
    # SNAPSHOT
    # ============================================================

    def collect_snapshot(
        self,
        *,
        category_id: str,
        layout_id: str,
        action_id: str,
        module_slot_id: str,
        order: str = "SCORE_DESC",
        filters: list[dict[str, Any]] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if limit <= 0:
            raise ValueError("limit은 1 이상이어야 합니다.")

        first_response = self.fetch_initial(
            category_id=category_id,
            layout_id=layout_id,
            action_id=action_id,
            module_slot_id=module_slot_id,
            order=order,
            filters=filters,
        )

        result_count = self.extract_result_count(
            first_response
        )

        all_products: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        response = first_response
        page_no = 1

        while True:
            products = self.parse_products(response)
            new_count = 0

            for product in products:
                product_id = product.get("product_id")

                if not product_id:
                    continue

                if product_id in seen_ids:
                    continue

                seen_ids.add(product_id)

                product["rank"] = len(all_products) + 1

                all_products.append(product)
                new_count += 1

                if len(all_products) >= limit:
                    break

            print(
                f"[ZIGZAG] page={page_no} "
                f"received={len(products)} "
                f"new={new_count} "
                f"total={len(all_products)}"
            )

            if len(all_products) >= limit:
                break

            next_info = self.get_next_request_info(
                response
            )

            if not next_info:
                break

            page_no += 1

            response = self.fetch_next(
                layout_id=layout_id,
                action_id=action_id,
                module_slot_id=(
                    next_info.get("module_slot_id")
                    or module_slot_id
                ),
                server_option=next_info[
                    "server_option"
                ],
            )

        return {
            "category_id": str(category_id),
            "order": order,
            "filters": filters or [],
            "result_count": result_count,
            "is_count_capped": (
                result_count is not None
                and result_count >= 10000
            ),
            "collected_count": len(all_products),
            "products": all_products[:limit],
        }
