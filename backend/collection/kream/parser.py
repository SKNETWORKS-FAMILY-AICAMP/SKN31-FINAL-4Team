from __future__ import annotations

import json
import re
from typing import Any

from .exceptions import KreamParseError


class KreamParser:
    VIEWER_PATTERN = re.compile(r"([\d,]+)명이\s*보고\s*있어요")
    RANK_PATTERN = re.compile(
        r"(?P<prefix>급상승|일간|주간|월간)\s+"
        r"(?P<category>.+?)\s+"
        r"(?P<rank>\d+)위"
    )

    @classmethod
    def parse_product(cls, *, product_id: int, screen: dict, header: dict) -> dict:
        if not isinstance(screen, dict):
            raise KreamParseError("screen 응답이 dict가 아닙니다.")
        if not isinstance(header, dict):
            header = {}

        meta = screen.get("meta") or {}
        if not isinstance(meta, dict):
            meta = {}

        analytics = cls._extract_best_product_analytics(
            [screen, header], target_product_id=product_id
        )

        transaction_history = cls._find_first_key(screen, "transaction_history") or {}
        if not isinstance(transaction_history, dict):
            transaction_history = {}

        review = meta.get("review") or {}
        if not isinstance(review, dict):
            review = {}

        return {
            "product": cls._parse_product_master(
                product_id=product_id, meta=meta, analytics=analytics
            ),
            "snapshot": cls._parse_snapshot(
                product_id=product_id,
                meta=meta,
                review=review,
                screen=screen,
                header=header,
                analytics=analytics,
            ),
            "ranking_signals": cls._extract_ranking_signals(
                header, product_id=product_id
            ),
            "options": cls._extract_options(screen),
            "market": {
                "sales": cls._parse_market_items(
                    transaction_history.get("sales"), side="SALE"
                ),
                "asks": cls._parse_market_items(
                    transaction_history.get("asks"), side="ASK"
                ),
                "bids": cls._parse_market_items(
                    transaction_history.get("bids"), side="BID"
                ),
                "listings": cls._extract_inventory_listings(
                    screen, product_id=product_id
                ),
            },
        }

    @classmethod
    def _parse_product_master(cls, *, product_id: int, meta: dict, analytics: dict) -> dict:
        image_urls = cls._clean_string_list(meta.get("image_urls"))
        if not image_urls:
            image_urls = cls._extract_product_images(meta)

        return {
            "product_id": product_id,
            "name_en": cls._clean_text(meta.get("name"))
            or cls._clean_text(analytics.get("product_name_en")),
            "name_ko": cls._clean_text(meta.get("translated_name"))
            or cls._clean_text(analytics.get("product_name_ko")),
            "style_code": cls._clean_text(meta.get("style_code"))
            or cls._clean_text(analytics.get("product_style_code")),
            "brand": {
                "brand_id": cls._to_int(analytics.get("brand_id")),
                "name": cls._clean_text(meta.get("brand_name"))
                or cls._clean_text(analytics.get("brand_name")),
            },
            "category": {
                "source_type": cls._clean_text(meta.get("category")),
                "source_category_id": cls._to_int(analytics.get("shop_category_id")),
                "depth1_name": cls._clean_text(analytics.get("shop_category_name_1d")),
                "depth2_name": cls._clean_text(analytics.get("shop_category_name_2d")),
            },
            "product_type": cls._clean_text(analytics.get("product_type")),
            "product_gender": cls._to_int(analytics.get("product_gender")),
            "color": cls._clean_text(meta.get("color")),
            "image_urls": image_urls,
            "currency": cls._clean_text(meta.get("local_price_currency")) or "KRW",
        }

    @classmethod
    def _parse_snapshot(
        cls,
        *,
        product_id: int,
        meta: dict,
        review: dict,
        screen: dict,
        header: dict,
        analytics: dict,
    ) -> dict:
        return {
            "current_price": cls._to_int(meta.get("price"))
            or cls._to_int(analytics.get("price")),
            "last_sale_price": cls._to_int(meta.get("last_sale_price")),
            "original_price": cls._to_int(analytics.get("original_price")),
            "max_benefit_price": cls._to_int(meta.get("max_benefit_price")),
            "review_rating": cls._to_float(review.get("review_rating")),
            "review_count": cls._to_int(review.get("review_count")),
            "total_review_count": cls._extract_total_review_count(screen),
            "viewer_count": cls._extract_current_product_viewer_count(
                header, product_id=product_id
            ),
            "wish_count": cls._extract_wish_count(
                screen, product_id=product_id
            ),
            "is_active": meta.get("is_active"),
            "availability": meta.get("availability"),
            "status": meta.get("status"),
            "has_immediate_delivery_item": (
                meta.get("has_immediate_delivery_item")
                if meta.get("has_immediate_delivery_item") is not None
                else analytics.get("has_immediate_delivery_item")
            ),
        }

    @classmethod
    def _extract_best_product_analytics(cls, roots: list, *, target_product_id: int) -> dict:
        candidates = []

        def walk(obj):
            if isinstance(obj, dict):
                parameters = obj.get("parameters")
                if isinstance(parameters, dict):
                    properties = parameters.get("properties")
                    if isinstance(properties, list):
                        for raw in properties:
                            parsed = cls._decode_json_property(raw)
                            if (
                                isinstance(parsed, dict)
                                and cls._to_int(parsed.get("product_id")) == target_product_id
                            ):
                                candidates.append(parsed)

                for child in obj.values():
                    walk(child)

            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        for root in roots:
            walk(root)

        if not candidates:
            return {}

        preferred_keys = {
            "product_name_en",
            "product_name_ko",
            "product_style_code",
            "brand_id",
            "brand_name",
            "shop_category_id",
            "shop_category_name_1d",
            "shop_category_name_2d",
            "product_type",
            "product_gender",
            "price",
            "original_price",
            "has_immediate_delivery_item",
        }

        return max(
            candidates,
            key=lambda item: sum(item.get(key) is not None for key in preferred_keys),
        )

    @classmethod
    def _find_current_product_series_item(
        cls, header: dict, *, product_id: int
    ) -> dict | None:
        meta = header.get("meta") or {}
        if not isinstance(meta, dict):
            return None

        series = meta.get("product_series") or []
        if not isinstance(series, list):
            return None

        for item in series:
            if isinstance(item, dict) and cls._to_int(item.get("product_id")) == product_id:
                return item

        return None

    @classmethod
    def _extract_current_product_viewer_count(
        cls, header: dict, *, product_id: int
    ) -> int | None:
        current_item = cls._find_current_product_series_item(
            header, product_id=product_id
        )
        if not current_item:
            return None

        values = []

        def walk(obj):
            if isinstance(obj, dict):
                for key, child in obj.items():
                    if key == "text" and isinstance(child, str):
                        match = cls.VIEWER_PATTERN.search(child)
                        if match:
                            try:
                                values.append(int(match.group(1).replace(",", "")))
                            except ValueError:
                                pass
                    walk(child)
            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        walk(current_item)
        return values[0] if values else None

    @classmethod
    def _extract_total_review_count(cls, screen: dict) -> int | None:
        def find_review_tab(obj):
            if isinstance(obj, dict):
                if obj.get("anchor_key") == "product_detail-review":
                    return obj
                for child in obj.values():
                    found = find_review_tab(child)
                    if found is not None:
                        return found
            elif isinstance(obj, list):
                for child in obj:
                    found = find_review_tab(child)
                    if found is not None:
                        return found
            return None

        review_tab = find_review_tab(screen)
        if not isinstance(review_tab, dict):
            return None

        counts = []

        def walk(obj):
            if isinstance(obj, dict):
                lookups = obj.get("text_lookups")
                if isinstance(lookups, list):
                    has_review = any(
                        isinstance(item, dict)
                        and cls._clean_text(item.get("text")) == "리뷰"
                        for item in lookups
                    )
                    if has_review:
                        for item in lookups:
                            if not isinstance(item, dict):
                                continue
                            text = cls._clean_text(item.get("text"))
                            if text and text.replace(",", "").isdigit():
                                counts.append(int(text.replace(",", "")))

                for child in obj.values():
                    walk(child)

            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        walk(review_tab)
        return counts[0] if counts else None

    @classmethod
    def _extract_wish_count(
        cls, screen: dict, *, product_id: int
    ) -> int | None:
        target_id = f"product_wish/{product_id}"

        def walk(obj):
            if isinstance(obj, dict):
                if obj.get("id") == target_id:
                    for key in ("count", "wish_count", "total_count", "interest_count"):
                        value = cls._to_int(obj.get(key))
                        if value is not None:
                            return value

                    meta = obj.get("meta")
                    if isinstance(meta, dict):
                        for key in ("count", "wish_count", "total_count", "interest_count"):
                            value = cls._to_int(meta.get(key))
                            if value is not None:
                                return value
                    return None

                for child in obj.values():
                    found = walk(child)
                    if found is not None:
                        return found

            elif isinstance(obj, list):
                for child in obj:
                    found = walk(child)
                    if found is not None:
                        return found

            return None

        return walk(screen)

    @classmethod
    def _extract_ranking_signals(
        cls, header: dict, *, product_id: int
    ) -> list[dict]:
        current_item = cls._find_current_product_series_item(
            header, product_id=product_id
        )
        if not current_item:
            return []

        results = []
        seen = set()

        def add(text: str):
            match = cls.RANK_PATTERN.search(text.strip())
            if not match:
                return

            label = match.group(0)
            if label in seen:
                return
            seen.add(label)

            type_map = {
                "급상승": "RISING",
                "일간": "DAILY",
                "주간": "WEEKLY",
                "월간": "MONTHLY",
            }

            results.append(
                {
                    "label": label,
                    "ranking_type": type_map.get(
                        match.group("prefix"), match.group("prefix")
                    ),
                    "category": match.group("category").strip(),
                    "rank": int(match.group("rank")),
                }
            )

        def walk(obj):
            if isinstance(obj, dict):
                for key in ("text", "screen_query_id"):
                    raw = obj.get(key)
                    if isinstance(raw, str):
                        add(raw)

                parameters = obj.get("parameters")
                if isinstance(parameters, dict):
                    properties = parameters.get("properties")
                    if isinstance(properties, list):
                        for raw in properties:
                            parsed = cls._decode_json_property(raw)
                            if isinstance(parsed, dict):
                                signal = parsed.get("screen_query_id")
                                if isinstance(signal, str):
                                    add(signal)

                for child in obj.values():
                    walk(child)

            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        walk(current_item)
        return results

    @classmethod
    def _extract_options(cls, value) -> list[dict]:
        options = {}

        def add_option(option):
            if not isinstance(option, dict):
                return

            option_id = cls._to_int(option.get("id"))
            display = (
                cls._clean_text(option.get("name_display"))
                or cls._clean_text(option.get("name"))
                or cls._clean_text(option.get("key"))
            )
            if not display:
                return

            options[(option_id, display)] = {
                "option_id": option_id,
                "value": display,
            }

        def walk(obj):
            if isinstance(obj, dict):
                product_option = obj.get("product_option")
                if isinstance(product_option, dict):
                    add_option(product_option)

                raw_options = obj.get("product_options")
                if isinstance(raw_options, list):
                    for option in raw_options:
                        if isinstance(option, dict):
                            add_option(option)
                        elif isinstance(option, str):
                            decoded = cls._decode_json_property(option)
                            if isinstance(decoded, dict):
                                add_option(decoded)

                for child in obj.values():
                    walk(child)

            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        walk(value)
        return list(options.values())

    @classmethod
    def _parse_market_items(
        cls, group, *, side: str
    ) -> list[dict]:
        if not isinstance(group, dict):
            return []

        items = group.get("items") or []
        if not isinstance(items, list):
            return []

        result = []

        for item in items[:5]:
            if not isinstance(item, dict):
                continue

            option = item.get("product_option") or {}
            if not isinstance(option, dict):
                option = {}

            result.append(
                {
                    "option_id": cls._to_int(option.get("id")),
                    "size": (
                        cls._clean_text(option.get("name_display"))
                        or cls._clean_text(option.get("name"))
                        or cls._clean_text(option.get("key"))
                    ),
                    "price": cls._to_int(item.get("price")),
                    "quantity": (
                        cls._to_int(item.get("quantity"))
                        if side in {"ASK", "BID"}
                        else None
                    ),
                    "is_immediate_delivery": item.get(
                        "is_immediate_delivery_item"
                    ),
                    "occurred_at": (
                        cls._clean_text(item.get("date_created"))
                        if side == "SALE"
                        else None
                    ),
                }
            )

        return result

    @classmethod
    def _extract_inventory_listings(
        cls, value, *, product_id: int
    ) -> list[dict]:
        results = []
        seen = set()

        def walk(obj):
            if isinstance(obj, dict):
                parameters = obj.get("parameters")
                if isinstance(parameters, dict):
                    properties = parameters.get("properties")
                    if isinstance(properties, list):
                        for raw in properties:
                            parsed = cls._decode_json_property(raw)

                            if not isinstance(parsed, dict):
                                continue
                            if cls._to_int(parsed.get("product_id")) != product_id:
                                continue

                            inventory_id = cls._to_int(
                                parsed.get("inventory_item_id")
                            )
                            if inventory_id is None:
                                continue

                            price = cls._to_int(parsed.get("price"))
                            key = (inventory_id, price)

                            if key in seen:
                                continue
                            seen.add(key)

                            results.append(
                                {
                                    "inventory_item_id": inventory_id,
                                    "price": price,
                                    "has_immediate_delivery_item": parsed.get(
                                        "has_immediate_delivery_item"
                                    ),
                                    "product_type": cls._clean_text(
                                        parsed.get("product_type")
                                    ),
                                }
                            )

                for child in obj.values():
                    walk(child)

            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        walk(value)
        return results

    @classmethod
    def _extract_product_images(cls, value) -> list[str]:
        results = []

        def walk(obj):
            if isinstance(obj, dict):
                for key in ("image_url", "url"):
                    raw = obj.get(key)
                    if isinstance(raw, str) and "kream-phinf" in raw:
                        results.append(raw)

                for child in obj.values():
                    walk(child)

            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        walk(value)
        return list(dict.fromkeys(results))

    @classmethod
    def _find_first_key(cls, value, target_key: str) -> Any:
        if isinstance(value, dict):
            if target_key in value:
                return value[target_key]

            for child in value.values():
                found = cls._find_first_key(child, target_key)
                if found is not None:
                    return found

        elif isinstance(value, list):
            for child in value:
                found = cls._find_first_key(child, target_key)
                if found is not None:
                    return found

        return None

    @staticmethod
    def _decode_json_property(raw):
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _clean_text(value) -> str | None:
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @classmethod
    def _clean_string_list(cls, value) -> list[str]:
        if not isinstance(value, list):
            return []

        result = []

        for item in value:
            text = cls._clean_text(item)
            if text:
                result.append(text)

        return list(dict.fromkeys(result))

    @staticmethod
    def _to_int(value) -> int | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

        text = (
            str(value)
            .strip()
            .replace(",", "")
            .replace("원", "")
            .replace("%", "")
        )

        if not text:
            return None

        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None
