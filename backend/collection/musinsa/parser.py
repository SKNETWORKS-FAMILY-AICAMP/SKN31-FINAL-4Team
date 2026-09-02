from __future__ import annotations

import json

from bs4 import BeautifulSoup

from .constants import PARSER_VERSION
from .exceptions import MusinsaParseError
from .images import (
    normalize_image_url,
    parse_detail_content,
    parse_product_images,
)

class MusinsaParser:
    PRODUCT_STATE_MARKER = "window.__MSS_FE__.product.state"

    @classmethod
    def parse_product(cls, html: str) -> dict:
        if not html or not html.strip():
            raise MusinsaParseError("HTML이 비어 있습니다.")

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        state = cls._extract_product_state(
            soup
        )

        next_data = cls._extract_next_data(
            soup
        )

        goods_no = cls._to_int(
            state.get("goodsNo")
        )

        detail = parse_detail_content(
            state.get("goodsContents")
        )

        return {
            "brand": cls._parse_brand(
                state
            ),
            "product": cls._parse_product(
                state,
                tags=cls._extract_product_tags(
                    next_data,
                    goods_no,
                ),
                detail=detail,
            ),
            "snapshot": cls._parse_snapshot(
                state
            ),
            "meta": {
                "parser_version": PARSER_VERSION,
            },
        }

    @classmethod
    def _extract_product_state(
        cls,
        soup: BeautifulSoup,
    ) -> dict:
        script = soup.find(
            "script",
            id="pdp-data",
        )

        if script is None:
            raise MusinsaParseError(
                "pdp-data script를 찾을 수 없습니다."
            )

        text = (
            script.string
            or script.get_text()
            or ""
        )

        marker_index = text.find(
            cls.PRODUCT_STATE_MARKER
        )

        if marker_index < 0:
            raise MusinsaParseError(
                "window.__MSS_FE__.product.state를 찾을 수 없습니다."
            )

        assignment_index = text.find(
            "=",
            marker_index,
        )

        json_start = text.find(
            "{",
            assignment_index,
        )

        if (
            assignment_index < 0
            or json_start < 0
        ):
            raise MusinsaParseError(
                "상품 state 할당식을 찾을 수 없습니다."
            )

        try:
            data, _ = (
                json.JSONDecoder()
                .raw_decode(
                    text[json_start:]
                )
            )

        except json.JSONDecodeError as exc:
            raise MusinsaParseError(
                f"상품 JSON 파싱 실패: {exc}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise MusinsaParseError(
                "상품 state가 object 형식이 아닙니다."
            )

        if cls._to_int(
            data.get("goodsNo")
        ) is None:
            raise MusinsaParseError(
                "상품번호가 없는 상품 state입니다."
            )

        if not data.get(
            "goodsNm"
        ):
            raise MusinsaParseError(
                "상품명이 없는 상품 state입니다."
            )

        return data

    @staticmethod
    def _extract_next_data(
        soup: BeautifulSoup,
    ) -> dict | None:
        script = soup.find(
            "script",
            id="__NEXT_DATA__",
        )

        if script is None:
            return None

        raw = (
            script.string
            or script.get_text()
            or ""
        )

        if not raw.strip():
            return None

        try:
            value = json.loads(
                raw
            )

        except json.JSONDecodeError:
            return None

        return (
            value
            if isinstance(
                value,
                dict,
            )
            else None
        )

    @classmethod
    def _extract_product_tags(
        cls,
        next_data: dict | None,
        goods_no: int | None,
    ) -> list[str] | None:
        if (
            not next_data
            or goods_no is None
        ):
            return None

        tags = cls._find_tags_recursive(
            next_data,
            str(goods_no),
        )

        if not tags:
            return None

        values = [
            str(tag).strip()
            for tag in tags
            if (
                tag is not None
                and str(tag).strip()
            )
        ]

        return (
            list(
                dict.fromkeys(
                    values
                )
            )
            or None
        )

    @classmethod
    def _find_tags_recursive(
        cls,
        value,
        target_goods_no: str,
    ):
        if isinstance(
            value,
            dict,
        ):
            if (
                str(
                    value.get(
                        "goodsNo"
                    )
                )
                == target_goods_no
                and isinstance(
                    value.get(
                        "tags"
                    ),
                    list,
                )
            ):
                return value[
                    "tags"
                ]

            for child in value.values():
                found = (
                    cls._find_tags_recursive(
                        child,
                        target_goods_no,
                    )
                )

                if found:
                    return found

        elif isinstance(
            value,
            list,
        ):
            for child in value:
                found = (
                    cls._find_tags_recursive(
                        child,
                        target_goods_no,
                    )
                )

                if found:
                    return found

        return None

    @classmethod
    def _parse_brand(
        cls,
        data: dict,
    ) -> dict:
        info = (
            data.get("brandInfo")
            if isinstance(
                data.get(
                    "brandInfo"
                ),
                dict,
            )
            else {}
        )

        return {
            "brand_code": cls._clean_text(
                info.get("brand")
                or data.get("brand")
            ),
            "name_ko": cls._clean_text(
                info.get(
                    "brandName"
                )
            ),
            "name_en": cls._clean_text(
                info.get(
                    "brandEnglishName"
                )
            ),
            "nation_code": cls._clean_text(
                info.get(
                    "brandNationCode"
                )
            ),
            "nation_name": cls._clean_text(
                info.get(
                    "brandNationName"
                )
            ),
            "since_year": cls._to_int(
                info.get(
                    "sinceYear"
                )
            ),
            "logo_url": normalize_image_url(
                info.get(
                    "brandLogoImage"
                )
            ),
            "description": cls._clean_text(
                info.get("memo")
            ),
        }

    @classmethod
    def _parse_product(
        cls,
        data: dict,
        *,
        tags: list[str] | None,
        detail: dict,
    ) -> dict:
        category = (
            data.get("category")
            if isinstance(
                data.get("category"),
                dict,
            )
            else {}
        )

        brand_info = (
            data.get("brandInfo")
            if isinstance(
                data.get(
                    "brandInfo"
                ),
                dict,
            )
            else {}
        )

        return {
            "goods_no": cls._to_int(
                data.get("goodsNo")
            ),

            "style_no": cls._clean_text(
                data.get("styleNo")
            ),

            "name": cls._clean_text(
                data.get("goodsNm")
            ),

            "name_en": cls._clean_text(
                data.get(
                    "goodsNmEng"
                )
            ),

            "brand_code": cls._clean_text(
                brand_info.get(
                    "brand"
                )
                or data.get(
                    "brand"
                )
            ),

            # 무신사 원본 카테고리.
            # FEEDIT 표준 카테고리 정규화는 analysis 단계에서 처리.
            "category": {
                "depth1_code": cls._clean_text(
                    category.get(
                        "categoryDepth1Code"
                    )
                ),
                "depth1_name": cls._clean_text(
                    category.get(
                        "categoryDepth1Name"
                    )
                ),
                "depth2_code": cls._clean_text(
                    category.get(
                        "categoryDepth2Code"
                    )
                ),
                "depth2_name": cls._clean_text(
                    category.get(
                        "categoryDepth2Name"
                    )
                ),
                "depth3_code": cls._clean_text(
                    category.get(
                        "categoryDepth3Code"
                    )
                ),
                "depth3_name": cls._clean_text(
                    category.get(
                        "categoryDepth3Name"
                    )
                ),
                "depth4_code": cls._clean_text(
                    category.get(
                        "categoryDepth4Code"
                    )
                ),
                "depth4_name": cls._clean_text(
                    category.get(
                        "categoryDepth4Name"
                    )
                ),
            },

            "genders": cls._parse_genders(
                data.get("genders")
                or data.get("sex")
            ),

            "season_year": cls._to_int(
                data.get(
                    "seasonYear"
                )
            ),

            "season": cls._clean_text(
                data.get("season")
            ),

            "sell_start_date": cls._clean_text(
                data.get(
                    "sellStartDate"
                )
            ),

            "sell_end_date": cls._clean_text(
                data.get(
                    "sellEndDate"
                )
            ),

            "sale_start_date": cls._clean_text(
                data.get(
                    "saleStartDate"
                )
            ),

            "sale_end_date": cls._clean_text(
                data.get(
                    "saleEndDate"
                )
            ),

            # 대표 썸네일
            "thumbnail_url": (
                normalize_image_url(
                    data.get(
                        "thumbnailImageUrl"
                    )
                )
            ),

            # 상품 갤러리 이미지.
            # OCR용 상세 본문 이미지와 반드시 분리해서 보존.
            "product_images": (
                parse_product_images(
                    data.get(
                        "goodsImages"
                    )
                )
            ),

            # 상품 상세페이지 원문.
            # 향후 OCR/클리닝/재파싱을 위해 HTML까지 S3 RAW에 보존.
            "detail_content": {
                "html": detail.get(
                    "html"
                ),
                "images": detail.get(
                    "images",
                    [],
                ),
                "videos": detail.get(
                    "videos",
                    [],
                ),
            },

            "source_attributes": (
                cls._parse_source_attributes(
                    data.get(
                        "goodsMaterial"
                    )
                )
            ),

            # None을 빈 리스트 등으로 강제 변환하지 않음.
            "tags": tags,
        }

    @classmethod
    def _parse_snapshot(
        cls,
        data: dict,
    ) -> dict:
        price = (
            data.get("goodsPrice")
            if isinstance(
                data.get(
                    "goodsPrice"
                ),
                dict,
            )
            else {}
        )

        review = (
            data.get("goodsReview")
            if isinstance(
                data.get(
                    "goodsReview"
                ),
                dict,
            )
            else {}
        )

        return {
            "regular_price": cls._to_int(
                price.get(
                    "normalPrice"
                )
            ),

            "sale_price": cls._to_int(
                price.get(
                    "salePrice"
                )
            ),

            "discount_rate": cls._to_float(
                price.get(
                    "discountRate"
                )
            ),

            "currency": (
                cls._clean_text(
                    price.get(
                        "currency"
                    )
                )
                or "KRW"
            ),

            "review_count": cls._to_int(
                review.get(
                    "totalCount"
                )
            ),

            "satisfaction_score": (
                cls._to_float(
                    review.get(
                        "satisfactionScore"
                    )
                )
            ),

            # Collector가 API로 보강.
            "like_count": None,
            "view_count": None,
            "sales_count": None,

            "availability": (
                "품절"
                if cls._to_bool(
                    data.get(
                        "isOutOfStock"
                    )
                )
                else "주문가능"
            ),

            "is_out_of_stock": (
                cls._to_bool(
                    data.get(
                        "isOutOfStock"
                    )
                )
            ),
        }

    @classmethod
    def _parse_source_attributes(
        cls,
        material_data,
    ) -> dict | None:
        if (
            not isinstance(
                material_data,
                dict,
            )
            or not isinstance(
                material_data.get(
                    "materials"
                ),
                list,
            )
        ):
            return None

        result: dict[
            str,
            list[str],
        ] = {}

        for group in material_data[
            "materials"
        ]:
            if not isinstance(
                group,
                dict,
            ):
                continue

            name = cls._clean_text(
                group.get("name")
            )

            items = group.get(
                "items"
            )

            if (
                not name
                or not isinstance(
                    items,
                    list,
                )
            ):
                continue

            selected = []

            for item in items:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                if not cls._to_bool(
                    item.get(
                        "isSelected"
                    )
                ):
                    continue

                value = cls._clean_text(
                    item.get("name")
                )

                if value:
                    selected.append(
                        value.replace(
                            "|",
                            " ",
                        )
                    )

            if selected:
                result[name] = (
                    selected
                )

        return result or None

    @classmethod
    def _parse_genders(
        cls,
        value,
    ) -> list[str] | None:
        if value is None:
            return None

        values = (
            value
            if isinstance(
                value,
                list,
            )
            else [value]
        )

        result = [
            cls._clean_text(v)
            for v in values
        ]

        result = [
            value
            for value in result
            if value
        ]

        return (
            list(
                dict.fromkeys(
                    result
                )
            )
            or None
        )

    @staticmethod
    def _clean_text(
        value,
    ):
        if value is None:
            return None

        text = str(
            value
        ).strip()

        return text or None

    @staticmethod
    def _to_int(
        value,
    ):
        if (
            value is None
            or isinstance(
                value,
                bool,
            )
        ):
            return None

        try:
            return int(
                float(
                    str(value)
                    .replace(",", "")
                    .replace("원", "")
                    .replace("%", "")
                    .strip()
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_float(
        value,
    ):
        if (
            value is None
            or isinstance(
                value,
                bool,
            )
        ):
            return None

        try:
            return float(
                str(value)
                .replace(",", "")
                .replace("%", "")
                .strip()
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_bool(
        value,
        default: bool = False,
    ):
        if value is None:
            return default

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            (int, float),
        ):
            return bool(value)

        text = str(
            value
        ).strip().lower()

        if text in {
            "true",
            "1",
            "yes",
            "y",
        }:
            return True

        if text in {
            "false",
            "0",
            "no",
            "n",
            "",
        }:
            return False

        return default
