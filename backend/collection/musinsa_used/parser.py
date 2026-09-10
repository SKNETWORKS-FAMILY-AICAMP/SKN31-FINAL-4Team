from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from .constants import (
    IMAGE_BASE_URL,
    PARSER_VERSION,
    PRODUCT_BASE_URL,
)
from .exceptions import MusinsaUsedParseError
from .images import normalize_image_url


class MusinsaUsedParser:
    """
    MUSINSA USED saved-HTML parser.

    우선순위:
    1. HTML 내부 JSON/script 데이터
    2. DOM 상품 링크 fallback

    USED 판별:
    - usedConditionGrade 값이 있으면 USED 상품으로 간주
    """

    PRODUCT_LINK_PATTERN = re.compile(
        r"/products/(\d+)"
    )

    PRODUCT_URL_TEMPLATE = PRODUCT_BASE_URL

    NEXT_DATA_PATTERN = re.compile(
        r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        re.DOTALL,
    )

    # ============================================================
    # PUBLIC
    # ============================================================

    @classmethod
    def parse_ranking(
        cls,
        html: str,
        *,
        limit: int | None = None,
    ) -> list[dict]:
        if not html:
            return []

        results: list[dict] = []
        seen_goods_no: set[str] = set()

        # USED 카테고리의 dehydratedState를 가장 먼저 사용한다. 일반
        # script 순회보다 범위가 명확해 신품 상품이 섞이는 것을 막는다.
        next_data = cls.next_data(html)
        if next_data:
            if not cls.is_used_html(html):
                raise MusinsaUsedParseError(
                    "저장된 HTML이 MUSINSA USED 목록 페이지가 아닙니다."
                )

            for raw in cls._extract_used_list(next_data):
                parsed = cls._normalize_goods(raw, confirmed_used=True)
                if not parsed:
                    continue

                goods_no = str(parsed["goods_no"])
                if goods_no in seen_goods_no:
                    continue

                seen_goods_no.add(goods_no)
                parsed["rank"] = len(results) + 1
                results.append(parsed)

                if limit is not None and len(results) >= limit:
                    return results

        # --------------------------------------------------------
        # 1. script/json 안의 상품 데이터 우선
        # --------------------------------------------------------

        json_items = (
            cls._extract_goods_from_scripts(
                html
            )
        )

        for raw in json_items:
            parsed = (
                cls._normalize_goods(
                    raw
                )
            )

            if not parsed:
                continue

            goods_no = (
                parsed.get(
                    "goods_no"
                )
            )

            if not goods_no:
                continue

            goods_no = str(
                goods_no
            )

            if goods_no in seen_goods_no:
                continue

            seen_goods_no.add(
                goods_no
            )

            parsed["rank"] = (
                len(results) + 1
            )

            results.append(
                parsed
            )

            if (
                limit is not None
                and len(results) >= limit
            ):
                return results

        # --------------------------------------------------------
        # 2. DOM fallback
        # --------------------------------------------------------

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        for anchor in soup.find_all(
            "a",
            href=True,
        ):
            href = str(
                anchor.get(
                    "href",
                    ""
                )
            )

            match = (
                cls.PRODUCT_LINK_PATTERN.search(
                    href
                )
            )

            if not match:
                continue

            goods_no = (
                match.group(1)
            )

            if goods_no in seen_goods_no:
                continue

            seen_goods_no.add(
                goods_no
            )

            text = " ".join(
                anchor.stripped_strings
            ).strip()

            results.append(
                {
                    "rank": (
                        len(results) + 1
                    ),
                    "goods_no": (
                        goods_no
                    ),
                    "goods_name": (
                        text or None
                    ),
                    "goods_url": (
                        cls.PRODUCT_URL_TEMPLATE.format(
                            goods_no=goods_no
                        )
                    ),

                    "brand_code": None,
                    "brand_name": None,

                    "normal_price": None,
                    "price": None,
                    "final_price": None,

                    "is_sold_out": None,

                    "used_condition_grade": None,

                    # HTML fallback만으로는
                    # USED 여부를 확정할 수 없음.
                    "is_used": None,
                }
            )

            if (
                limit is not None
                and len(results) >= limit
            ):
                break

        return results

    @classmethod
    def parse_product(
        cls,
        html: str,
        *,
        goods_no: str | int | None = None,
    ) -> dict:
        """
        저장된 상품 상세 HTML에서
        해당 goodsNo의 JSON 데이터를 찾는다.
        """

        if not html:
            raise MusinsaUsedParseError(
                "MUSINSA USED HTML이 비어 있습니다."
            )

        target_goods_no = (
            str(goods_no)
            if goods_no is not None
            else None
        )

        # 상세 페이지의 meta/Detail query는 일반 재귀 탐색보다 정확하고,
        # usedProduct의 원상품 연결 정보까지 포함한다.
        next_data = cls.next_data(html)
        if next_data:
            if not cls.is_used_html(html):
                raise MusinsaUsedParseError(
                    "저장된 HTML이 MUSINSA USED 상품 페이지가 아닙니다."
                )

            detail = cls._extract_detail(next_data)
            parsed_detail = cls._normalize_goods(
                detail,
                confirmed_used=True,
            )
            if parsed_detail:
                parsed_goods_no = str(parsed_detail["goods_no"])
                if target_goods_no is None or parsed_goods_no == target_goods_no:
                    return parsed_detail

        items = (
            cls._extract_goods_from_scripts(
                html
            )
        )

        for raw in items:
            parsed = (
                cls._normalize_goods(
                    raw
                )
            )

            if not parsed:
                continue

            parsed_goods_no = str(
                parsed.get(
                    "goods_no",
                    "",
                )
            )

            if (
                target_goods_no is None
                or parsed_goods_no
                == target_goods_no
            ):
                return parsed

        # JSON에서 찾지 못한 경우
        # URL/DOM에서 최소 정보 확보.
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        if target_goods_no:
            return {
                "goods_no":
                    target_goods_no,

                "goods_name":
                    cls._extract_title(
                        soup
                    ),

                "goods_url":
                    cls.PRODUCT_URL_TEMPLATE.format(
                        goods_no=target_goods_no
                    ),

                "brand_code": None,
                "brand_name": None,

                "normal_price": None,
                "price": None,
                "final_price": None,

                "is_sold_out": None,
                "used_condition_grade": (
                    cls._extract_used_grade_text(
                        html
                    )
                ),

                "is_used": (
                    cls._extract_used_grade_text(
                        html
                    )
                    is not None
                ),
            }

        raise MusinsaUsedParseError(
            "MUSINSA USED 상품 정보를 "
            "HTML에서 찾지 못했습니다."
        )

    @classmethod
    def parse_ranking_response(
        cls,
        body: dict,
        *,
        ranking_scope: dict,
        limit: int | None = None,
    ) -> list[dict]:
        """Convert the ranking API response without inventing ranks."""
        data = body.get("data") if isinstance(body, dict) else {}
        data = data if isinstance(data, dict) else {}
        modules = data.get("modules") or []
        if not isinstance(modules, list):
            modules = []

        result: list[dict] = []
        for module in modules:
            if not isinstance(module, dict):
                continue
            if module.get("type") == "PRODUCT_COLUMN":
                item = cls._ranking_product_column_item(module, ranking_scope)
                if item is not None:
                    result.append(item)
                    if limit is not None and len(result) >= limit:
                        return result
                continue
            items = module.get("items") or []
            if not isinstance(items, list):
                continue
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                item = (
                    cls._ranking_product_column_item(raw, ranking_scope)
                    if raw.get("type") == "PRODUCT_COLUMN"
                    else cls._ranking_item(raw, ranking_scope)
                )
                if item is None:
                    continue
                result.append(item)
                if limit is not None and len(result) >= limit:
                    return result
        return result

    @classmethod
    def _ranking_product_column_item(
        cls,
        module: dict,
        ranking_scope: dict,
    ) -> dict | None:
        """Parse the confirmed live `PRODUCT_COLUMN` ranking module shape."""
        image = module.get("image")
        image = image if isinstance(image, dict) else {}
        info = module.get("info")
        info = info if isinstance(info, dict) else {}
        on_click = module.get("onClick")
        on_click = on_click if isinstance(on_click, dict) else {}
        event_log = on_click.get("eventLog")
        event_log = event_log if isinstance(event_log, dict) else {}
        ga4 = event_log.get("ga4")
        ga4 = ga4 if isinstance(ga4, dict) else {}
        payload = ga4.get("payload")
        payload = payload if isinstance(payload, dict) else {}

        goods_no = module.get("id") or payload.get("item_id")
        if goods_no is None:
            match = cls.PRODUCT_LINK_PATTERN.search(str(on_click.get("url") or ""))
            if match:
                goods_no = match.group(1)
        if goods_no is None:
            return None

        raw = {
            "goodsNo": goods_no,
            "rank": image.get("rank"),
            "goodsName": info.get("productName"),
            "brandCode": payload.get("item_brand"),
            "brandName": info.get("brandName"),
            "normalPrice": payload.get("original_price"),
            "price": info.get("finalPrice"),
            "saleRate": info.get("discountRatio"),
            "usedConditionGrade": payload.get("item_used_grade"),
            "isSoldOut": info.get("isSoldOut"),
            "thumbnail": image.get("url"),
            "onClick": on_click,
        }
        return cls._ranking_item(raw, ranking_scope)

    @classmethod
    def build_product_record(
        cls,
        detail: dict,
        *,
        sale_information: dict | None = None,
        related_goods: dict | None = None,
        options: dict | None = None,
        reviews: dict | None = None,
        ranking_context: dict | None = None,
        meta: dict | None = None,
    ) -> dict:
        """Build the shared MUSINSA RAW product shape from confirmed fields."""
        if not isinstance(detail, dict):
            raise MusinsaUsedParseError("MUSINSA USED 상품 상세 응답이 object가 아닙니다.")

        normalized = cls._normalize_goods(detail, confirmed_used=True)
        if not normalized or not normalized.get("goods_no"):
            raise MusinsaUsedParseError("MUSINSA USED goods_no가 없습니다.")

        category = detail.get("category")
        category = category if isinstance(category, dict) else {}
        brand = detail.get("brandInfo")
        brand = brand if isinstance(brand, dict) else {}
        price = detail.get("goodsPrice")
        price = price if isinstance(price, dict) else {}
        review = detail.get("goodsReview")
        review = review if isinstance(review, dict) else {}

        def value(*names):
            for name in names:
                candidate = detail.get(name)
                if candidate is not None:
                    return candidate
            return None

        raw_tags = detail.get("tags")
        tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()] if isinstance(raw_tags, list) else []
        source_attributes = detail.get("sourceAttributes")
        if not isinstance(source_attributes, dict):
            source_attributes = None
        source_options = detail.get("options")
        if not isinstance(source_options, dict):
            source_options = {}
        ranking_thumbnail = (
            ranking_context.get("thumbnail_url")
            if isinstance(ranking_context, dict)
            else None
        )
        detail_product_type = {
            "type_no": cls._to_int(value("typeNumber", "typeNo")),
            "type_name": cls._clean_text(value("typeName")),
        }
        detail_size = cls._clean_text(value("size", "goodsSize"))
        record_meta = {"parser_version": PARSER_VERSION}
        if isinstance(meta, dict):
            record_meta.update(meta)

        return {
            "brand": {
                "brand_code": cls._clean_text(
                    brand.get("brand") or brand.get("brandCode") or detail.get("brandCode")
                ),
                "name_ko": cls._clean_text(brand.get("brandName") or detail.get("brandName")),
                "name_en": cls._clean_text(brand.get("brandEnglishName")),
                "nation_code": cls._clean_text(brand.get("brandNationCode")),
                "nation_name": cls._clean_text(brand.get("brandNationName")),
                "since_year": cls._to_int(brand.get("sinceYear")),
                "logo_url": cls._image_url(brand.get("brandLogoImage")),
                "description": cls._clean_text(brand.get("memo")),
            },
            "product": {
                "goods_no": normalized["goods_no"],
                "original_goods_no": cls.parse_original_goods_no(related_goods),
                "style_no": cls._clean_text(detail.get("styleNo")),
                "name": cls._clean_text(detail.get("goodsNm") or detail.get("goodsName")),
                "name_en": cls._clean_text(detail.get("goodsNmEng")),
                "brand_code": cls._clean_text(
                    brand.get("brand") or brand.get("brandCode") or detail.get("brandCode")
                ),
                "category": cls._category(category),
                "product_type": detail_product_type,
                "genders": cls._genders(value("genders", "sex", "gender")),
                "size": detail_size,
                "measurements": {},
                "thumbnail_url": cls._image_url(
                    detail.get("thumbnailImageUrl")
                    or detail.get("thumbnail")
                    or ranking_thumbnail
                ),
                "source_attributes": source_attributes,
                "tags": list(dict.fromkeys(tags)),
            },
            "snapshot": {
                "regular_price": cls._to_int(detail.get("normalPrice") or price.get("normalPrice")),
                "sale_price": cls._to_int(
                    detail.get("price") or detail.get("finalPrice") or price.get("finalPrice") or price.get("salePrice")
                ),
                "discount_rate": cls._to_float(
                    detail.get("saleRate") or detail.get("finalDiscount") or price.get("saleRate") or price.get("discountRate")
                ),
                "currency": cls._clean_text(detail.get("currency") or price.get("currency")) or "KRW",
                "review_count": cls._to_int(detail.get("reviewCount") or review.get("totalCount")),
                "satisfaction_score": cls._to_float(detail.get("reviewScore") or review.get("satisfactionScore")),
                "like_count": cls._to_int(detail.get("likeCount")),
                "brand_like_count": cls._to_int(detail.get("brandLikeCount")),
                "view_count": cls._to_int(detail.get("goodsPageViewCount")),
                "page_view_total": cls._to_int(detail.get("pageViewTotal")),
                "purchase_total": cls._to_int(detail.get("purchaseTotal")),
                "availability": cls._clean_text(detail.get("availability")),
                "used_condition_grade": cls._clean_text(
                    detail.get("usedConditionGrade")
                    or (detail.get("usedProduct") or {}).get("usedConditionGrade")
                ),
                "is_sold_out": cls._to_bool(
                    detail.get("isSoldOut") if "isSoldOut" in detail else detail.get("isOutOfStock")
                ),
            },
            "used_price_history": cls.parse_used_price_history(sale_information),
            "options": options if isinstance(options, dict) else source_options,
            "reviews": reviews if isinstance(reviews, dict) else {"summary": {}, "items": []},
            "ranking_context": ranking_context,
            "meta": record_meta,
        }

    @classmethod
    def parse_product_record_from_html(
        cls,
        html: str,
        *,
        goods_no: str | int | None = None,
        sale_information: dict | None = None,
        related_goods: dict | None = None,
        options: dict | None = None,
        reviews: dict | None = None,
        ranking_context: dict | None = None,
        meta: dict | None = None,
    ) -> dict:
        parsed = cls.parse_product(html, goods_no=goods_no)
        if parsed.get("is_used") is not True:
            raise MusinsaUsedParseError("MUSINSA USED 상품으로 확인되지 않았습니다.")
        raw = parsed.get("raw_goods")
        if not isinstance(raw, dict):
            raise MusinsaUsedParseError("MUSINSA USED 상세 원본을 찾지 못했습니다.")
        return cls.build_product_record(
            raw,
            sale_information=sale_information,
            related_goods=related_goods,
            options=options,
            reviews=reviews,
            ranking_context=ranking_context,
            meta=meta,
        )

    @classmethod
    def parse_used_price_history(cls, body: dict | None) -> dict:
        data = body.get("data") if isinstance(body, dict) else {}
        data = data if isinstance(data, dict) else {}
        root = (
            data.get("usedProductPriceInfo")
            if data
            else (body.get("usedProductPriceInfo") if isinstance(body, dict) else {})
        )
        root = root if isinstance(root, dict) else {}

        def event(value):
            if not isinstance(value, dict):
                return None
            return {
                "changed_at": value.get("priceChangeDate"),
                "price": cls._to_int(value.get("price")),
                "discount_rate": cls._to_float(value.get("priceSaleRate")),
            }

        histories = root.get("changeHistories") or []
        histories = [event(value) for value in histories if isinstance(value, dict)]
        return {
            "price_anchor_type": root.get("priceAnchorType"),
            "first_sale_start": event(root.get("firstSaleStartDate")),
            "price_change_histories": histories,
            "discount_scheduled_at": root.get("discountScheduledDate"),
        }

    @staticmethod
    def parse_original_goods_no(body: dict | None) -> str | None:
        data = body.get("data") if isinstance(body, dict) else {}
        data = data if isinstance(data, dict) else {}
        original = data.get("originalGoods")
        if not isinstance(original, dict) or original.get("goodsNo") is None:
            return None
        return str(original["goodsNo"])

    # ============================================================
    # JSON SCRIPT
    # ============================================================

    @classmethod
    def next_data(cls, html: str) -> dict[str, Any]:
        """저장 HTML의 Next.js ``__NEXT_DATA__``를 반환한다."""
        match = cls.NEXT_DATA_PATTERN.search(html or "")
        if not match:
            return {}

        try:
            data = json.loads(match.group(1))
        except (TypeError, json.JSONDecodeError):
            return {}

        return data if isinstance(data, dict) else {}

    @classmethod
    def is_used_html(cls, html: str) -> bool:
        """신품 무신사 HTML을 USED 소스로 처리하지 않도록 판별한다."""
        data = cls.next_data(html)
        if not data:
            return False

        props = data.get("props", {}).get("pageProps", {})
        if not isinstance(props, dict):
            props = {}

        page = str(data.get("page") or "")
        query = props.get("query") or data.get("query") or {}
        if page == "/category/[[...slug]]" and "109" in json.dumps(
            query,
            ensure_ascii=False,
        ):
            return True

        compact = json.dumps(
            props,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            '"comId":"musinsa_used"' in compact
            or '"usedProduct":{' in compact
        )

    @staticmethod
    def _queries(data: dict) -> list:
        props = data.get("props", {}).get("pageProps", {})
        if not isinstance(props, dict):
            return []
        state = props.get("dehydratedState", {})
        if not isinstance(state, dict):
            return []
        queries = state.get("queries") or []
        return queries if isinstance(queries, list) else []

    @classmethod
    def _extract_used_list(cls, data: dict) -> list[dict]:
        items: list[dict] = []
        for query in cls._queries(data):
            if not isinstance(query, dict):
                continue
            query_key = query.get("queryKey") or []
            if not query_key or str(query_key[0]) != "109":
                continue

            root = query.get("state", {}).get("data", {})
            if not isinstance(root, dict):
                break
            pages = root.get("pages") or []
            if not isinstance(pages, list):
                break

            for page in pages:
                if not isinstance(page, dict):
                    continue
                block = page.get("data", page)
                if not isinstance(block, dict):
                    continue
                page_items = block.get("list") or []
                if isinstance(page_items, list):
                    items.extend(x for x in page_items if isinstance(x, dict))
            break
        return items

    @classmethod
    def _extract_detail(cls, data: dict) -> dict:
        props = data.get("props", {}).get("pageProps", {})
        if not isinstance(props, dict):
            return {}

        meta = props.get("meta") or {}
        detail = meta.get("data") if isinstance(meta, dict) else None
        if isinstance(detail, dict) and detail.get("goodsNo"):
            return detail

        for query in cls._queries(data):
            if not isinstance(query, dict):
                continue
            query_key = query.get("queryKey") or []
            if not query_key or query_key[0] != "Detail":
                continue
            root = query.get("state", {}).get("data", {})
            if isinstance(root, dict):
                root = root.get("data", root)
            if isinstance(root, dict) and root.get("goodsNo"):
                return root
        return {}

    @classmethod
    def _extract_goods_from_scripts(
        cls,
        html: str,
    ) -> list[dict]:
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        discovered: list[dict] = []

        for script in soup.find_all(
            "script"
        ):
            text = (
                script.string
                or script.get_text()
                or ""
            ).strip()

            if not text:
                continue

            # JSON일 가능성이 낮은 script는 빠르게 제외.
            if (
                "goodsNo" not in text
                and "usedConditionGrade"
                not in text
                and "goodsName" not in text
            ):
                continue

            # -----------------------------------------------
            # 순수 JSON script
            # -----------------------------------------------

            try:
                data = json.loads(
                    text
                )

                cls._walk_json(
                    data,
                    discovered,
                )

                continue

            except Exception:
                pass

            # -----------------------------------------------
            # JS 안에 들어 있는 JSON object fallback
            # -----------------------------------------------

            cls._extract_json_objects_from_text(
                text,
                discovered,
            )

        return discovered

    @classmethod
    def _walk_json(
        cls,
        value: Any,
        output: list[dict],
    ) -> None:
        if isinstance(
            value,
            dict,
        ):
            if (
                "goodsNo" in value
                or "goods_no" in value
            ):
                output.append(
                    value
                )

            for child in (
                value.values()
            ):
                cls._walk_json(
                    child,
                    output,
                )

        elif isinstance(
            value,
            list,
        ):
            for child in value:
                cls._walk_json(
                    child,
                    output,
                )

    @classmethod
    def _extract_json_objects_from_text(
        cls,
        text: str,
        output: list[dict],
    ) -> None:
        """
        완전한 JSON script가 아닌 경우
        goodsNo 주변 object를 제한적으로 탐색.

        실패해도 DOM fallback이 있기 때문에
        parser 전체를 중단하지 않는다.
        """

        pattern = re.compile(
            r'\{[^{}]*"goodsNo"\s*:\s*'
            r'(?:"?\d+"?)[^{}]*\}',
            re.DOTALL,
        )

        for match in pattern.finditer(
            text
        ):
            raw = (
                match.group(0)
            )

            try:
                data = json.loads(
                    raw
                )

            except Exception:
                continue

            if isinstance(
                data,
                dict,
            ):
                output.append(
                    data
                )

    # ============================================================
    # NORMALIZE
    # ============================================================

    @classmethod
    def _normalize_goods(
        cls,
        raw: dict,
        *,
        confirmed_used: bool = False,
    ) -> dict | None:
        goods_no = (
            raw.get("goodsNo")
            or raw.get("goods_no")
            or raw.get("productId")
            or raw.get("product_id")
        )

        if goods_no is None:
            return None

        goods_no = str(
            goods_no
        )

        used = raw.get("usedProduct") or {}
        if not isinstance(used, dict):
            used = {}

        price_info = raw.get("goodsPrice") or {}
        if not isinstance(price_info, dict):
            price_info = {}

        review = raw.get("goodsReview") or {}
        if not isinstance(review, dict):
            review = {}

        brand = raw.get("brandInfo") or {}
        if not isinstance(brand, dict):
            brand = {}

        grade = (
            raw.get(
                "usedConditionGrade"
            )
            or raw.get(
                "used_condition_grade"
            )
            or used.get("usedConditionGrade")
        )

        goods_url = (
            raw.get(
                "goodsLinkUrl"
            )
            or raw.get(
                "goodsUrl"
            )
            or cls.PRODUCT_URL_TEMPLATE.format(
                goods_no=goods_no
            )
        )

        return {
            "goods_no":
                goods_no,

            "goods_name": (
                raw.get(
                    "goodsName"
                )
                or raw.get(
                    "goods_name"
                )
                or raw.get("goodsNm")
            ),

            "goods_url":
                goods_url,

            "brand_code": (
                raw.get("brandCode")
                or brand.get("brandCode")
                or brand.get("brand")
                or raw.get("brand")
            ),

            "brand_name": (
                raw.get("brandName")
                or brand.get("brandName")
                or raw.get("brand")
            ),

            "normal_price":
                cls._to_int(
                    raw.get(
                        "normalPrice"
                    )
                    or price_info.get("normalPrice")
                ),

            "price":
                cls._to_int(
                    raw.get(
                        "price"
                    )
                    or price_info.get("finalPrice")
                    or price_info.get("salePrice")
                ),

            "final_price":
                cls._to_int(
                    raw.get(
                        "finalPrice"
                    )
                    or price_info.get("finalPrice")
                    or price_info.get("salePrice")
                ),

            "is_sold_out": (
                raw.get("isSoldOut")
                if "isSoldOut" in raw
                else raw.get("isOutOfStock")
            ),

            "used_condition_grade":
                grade,

            "is_used": (
                confirmed_used
                or grade is not None
            ),

            "model_code": raw.get("styleNo"),
            "category_path": raw.get("baseCategoryFullPath"),
            "thumbnail_url": cls._image_url(
                raw.get("thumbnailImageUrl") or raw.get("thumbnail")
            ),
            "initial_ask_price": cls._to_int(
                raw.get("normalPrice") or price_info.get("normalPrice")
            ),
            "discount": (
                raw.get("finalDiscount")
                or raw.get("saleRate")
                or price_info.get("finalDiscount")
                or price_info.get("discountRate")
            ),
            "review_count": cls._to_int(
                raw.get("reviewCount") or review.get("totalCount")
            ),
            "review_score": raw.get("reviewScore") or review.get("satisfactionScore"),
            "original_goods_no": (
                str(used["originalGoodsNo"])
                if used.get("originalGoodsNo") is not None
                else None
            ),
            "availability_state": (
                "sold_out"
                if (raw.get("isSoldOut") or raw.get("isOutOfStock"))
                else "available"
            ),
            "sell_start": raw.get("sellStartDate"),
            "listing_type": "ask",

            # 원본 일부 보존
            "raw_goods":
                raw,
        }

    @classmethod
    def _ranking_item(
        cls,
        raw: dict,
        ranking_scope: dict,
    ) -> dict | None:
        candidate = raw
        if not any(
            raw.get(key) is not None
            for key in ("goodsNo", "goods_no", "productId", "product_id")
        ):
            onclick = raw.get("onClick")
            onclick = onclick if isinstance(onclick, dict) else {}
            match = cls.PRODUCT_LINK_PATTERN.search(str(onclick.get("url") or ""))
            if match:
                candidate = {**raw, "goodsNo": match.group(1)}

        normalized = cls._normalize_goods(candidate, confirmed_used=True)
        if not normalized:
            return None

        rank = cls._to_int(raw.get("rank"))
        if rank is None:
            # Ranking API의 명시적 rank가 없는 항목은 순위로 만들지 않는다.
            return None

        goods_no = normalized["goods_no"]
        return {
            "rank": rank,
            "goods_no": goods_no,
            "product_url": cls.PRODUCT_URL_TEMPLATE.format(goods_no=goods_no),
            "ranking_period": ranking_scope.get("period"),
            "ranking_gender": ranking_scope.get("gender"),
            "ranking_category_code": ranking_scope.get("category_code"),
            "ranking_age_band": ranking_scope.get("age_band"),
            "ranking_type": ranking_scope.get("ranking_type"),
            "viewing_count": cls._to_int(raw.get("viewingCount")),
            "ranking_updated_at": raw.get("rankingUpdatedAt"),
            "product_name": normalized.get("goods_name"),
            "brand_code": normalized.get("brand_code"),
            "brand_name": normalized.get("brand_name"),
            "price": normalized.get("price"),
            "normal_price": normalized.get("normal_price"),
            "discount_rate": cls._to_float(normalized.get("discount")),
            "used_condition_grade": normalized.get("used_condition_grade"),
            "is_sold_out": cls._to_bool(normalized.get("is_sold_out")),
            "thumbnail_url": normalized.get("thumbnail_url"),
        }

    @classmethod
    def _category(cls, value: dict) -> dict:
        return {
            "depth1_code": cls._clean_text(value.get("categoryDepth1Code")),
            "depth1_name": cls._clean_text(value.get("categoryDepth1Name")),
            "depth2_code": cls._clean_text(value.get("categoryDepth2Code")),
            "depth2_name": cls._clean_text(value.get("categoryDepth2Name")),
            "depth3_code": cls._clean_text(value.get("categoryDepth3Code")),
            "depth3_name": cls._clean_text(value.get("categoryDepth3Name")),
            "depth4_code": cls._clean_text(value.get("categoryDepth4Code")),
            "depth4_name": cls._clean_text(value.get("categoryDepth4Name")),
        }

    @classmethod
    def _genders(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        values = value if isinstance(value, list) else [value]
        result = [cls._clean_text(item) for item in values]
        result = [item for item in result if item]
        return list(dict.fromkeys(result)) or None

    # ============================================================
    # DOM HELPERS
    # ============================================================

    @staticmethod
    def _image_url(value: Any) -> str | None:
        return normalize_image_url(value)

    @staticmethod
    def _extract_title(
        soup: BeautifulSoup,
    ) -> str | None:
        if soup.title:
            title = (
                soup.title.get_text(
                    " ",
                    strip=True,
                )
            )

            if title:
                return title

        h1 = soup.find(
            "h1"
        )

        if h1:
            return h1.get_text(
                " ",
                strip=True,
            )

        return None

    @staticmethod
    def _extract_used_grade_text(
        html: str,
    ) -> str | None:
        match = re.search(
            r"\b(A\+|A|B\+|B|C\+|C)\s*등급\b",
            html,
        )

        if not match:
            return None

        return (
            match.group(1)
            + "등급"
        )

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _to_int(
        value: Any,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        if isinstance(
            value,
            int,
        ):
            return value

        text = re.sub(
            r"[^\d-]",
            "",
            str(value),
        )

        if not text:
            return None

        try:
            return int(
                text
            )

        except ValueError:
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(str(value).replace(",", "").replace("%", "").strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
        return None


# 이전 단독 함수형 파서와의 호환 API
def next_data(html: str) -> dict[str, Any]:
    return MusinsaUsedParser.next_data(html)


def is_used_html(html: str) -> bool:
    return MusinsaUsedParser.is_used_html(html)


def parse_detail(html: str) -> dict:
    parsed = MusinsaUsedParser.parse_product(html)
    return {
        "source_uid": parsed.get("goods_no"),
        "source_url": parsed.get("goods_url"),
        "name": parsed.get("goods_name"),
        "brand": parsed.get("brand_name") or parsed.get("brand_code"),
        "model_code": parsed.get("model_code"),
        "category_path": parsed.get("category_path"),
        "image_url": parsed.get("thumbnail_url"),
        "price": parsed.get("final_price") or parsed.get("price"),
        "initial_ask_price": parsed.get("initial_ask_price"),
        "discount": parsed.get("discount"),
        "review_count": parsed.get("review_count"),
        "review_score": parsed.get("review_score"),
        "condition_grade": parsed.get("used_condition_grade"),
        "original_goods_no": parsed.get("original_goods_no"),
        "availability_state": parsed.get("availability_state"),
        "is_sold_out": parsed.get("is_sold_out"),
        "sell_start": parsed.get("sell_start"),
        "listing_type": parsed.get("listing_type"),
    }


def parse_list(html: str) -> list[dict]:
    return [
        {
            "source_uid": item.get("goods_no"),
            "source_url": item.get("goods_url"),
            "name": item.get("goods_name"),
            "brand": item.get("brand_name") or item.get("brand_code"),
            "image_url": item.get("thumbnail_url"),
            "price": item.get("final_price") or item.get("price"),
            "initial_ask_price": item.get("initial_ask_price"),
            "discount": item.get("discount"),
            "review_count": item.get("review_count"),
            "review_score": item.get("review_score"),
            "condition_grade": item.get("used_condition_grade"),
            "availability_state": item.get("availability_state"),
            "is_sold_out": item.get("is_sold_out"),
            "listing_type": item.get("listing_type"),
        }
        for item in MusinsaUsedParser.parse_ranking(html)
    ]
