import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .constants import (
    IMAGE_BASE_URL,
    PARSER_VERSION,
)


class MusinsaParseError(Exception):
    """무신사 상품 HTML 파싱 실패 시 사용하는 예외."""

    pass


class MusinsaParser:
    """
    무신사 상품 상세 HTML Parser.

    책임:
    - HTML 안의 product state 추출
    - __NEXT_DATA__에서 보조 정보 추출
    - 수집 결과를 brand / product / snapshot 구조로 정규화

    하지 않는 일:
    - HTTP 요청
    - Django ORM 저장
    - CrawlJob 생성/수정
    - observed_at 결정
    """

    PRODUCT_STATE_MARKER = "window.__MSS_FE__.product.state"

    # ============================================================
    # PUBLIC
    # ============================================================

    @classmethod
    def parse_product(cls, html: str) -> dict:
        """
        상품 상세 HTML 1건을 수집 계층에서 사용할 정규화 dict로 변환한다.

        반환 구조:
        {
            "brand": {...},
            "product": {...},
            "snapshot": {...},
            "meta": {
                "parser_version": "...",
            },
        }

        observed_at / crawl_job / crawl_target 등 실행 메타데이터는
        parser가 아닌 collector/service 계층에서 붙인다.
        """
        if not html or not html.strip():
            raise MusinsaParseError("HTML이 비어 있습니다.")

        soup = BeautifulSoup(html, "html.parser")

        product_state = cls._extract_product_state(soup)
        next_data = cls._extract_next_data(soup)

        goods_no = cls._to_int(product_state.get("goodsNo"))

        tags = cls._extract_product_tags(
            next_data=next_data,
            goods_no=goods_no,
        )

        return {
            "brand": cls._parse_brand(product_state),
            "product": cls._parse_product(
                product_state,
                tags=tags,
            ),
            "snapshot": cls._parse_snapshot(product_state),
            "meta": {
                "parser_version": PARSER_VERSION,
            },
        }

    # ============================================================
    # PRODUCT STATE
    # ============================================================

    @classmethod
    def _extract_product_state(cls, soup: BeautifulSoup) -> dict:
        """
        <script id="pdp-data"> 안의

        window.__MSS_FE__.product.state = {...};

        객체를 추출한다.

        정규식으로 중첩 JSON 전체를 잡지 않고 JSONDecoder.raw_decode를
        사용해서 뒤쪽 JS 코드 형태가 조금 바뀌어도 최대한 안전하게 읽는다.
        """
        script = soup.find("script", id="pdp-data")

        if script is None:
            raise MusinsaParseError("pdp-data script를 찾을 수 없습니다.")

        script_text = script.string or script.get_text() or ""

        marker_index = script_text.find(cls.PRODUCT_STATE_MARKER)

        if marker_index < 0:
            raise MusinsaParseError(
                "window.__MSS_FE__.product.state를 찾을 수 없습니다."
            )

        assignment_index = script_text.find("=", marker_index)

        if assignment_index < 0:
            raise MusinsaParseError(
                "window.__MSS_FE__.product.state 할당식을 찾을 수 없습니다."
            )

        json_start = script_text.find("{", assignment_index)

        if json_start < 0:
            raise MusinsaParseError("상품 JSON 시작 위치를 찾을 수 없습니다.")

        try:
            data, _ = json.JSONDecoder().raw_decode(script_text[json_start:])
        except json.JSONDecodeError as exc:
            raise MusinsaParseError(f"상품 JSON 파싱 실패: {exc}") from exc

        if not isinstance(data, dict):
            raise MusinsaParseError("상품 state가 JSON object 형식이 아닙니다.")

        if cls._to_int(data.get("goodsNo")) is None:
            raise MusinsaParseError("goodsNo가 존재하지 않습니다.")

        if not data.get("goodsNm"):
            raise MusinsaParseError("goodsNm이 존재하지 않습니다.")

        return data

    # ============================================================
    # NEXT DATA
    # ============================================================

    @classmethod
    def _extract_next_data(
        cls,
        soup: BeautifulSoup,
    ) -> dict | None:
        """
        Next.js SSR 데이터.

        product.state에 없는 상품 태그 등 보조 정보를 찾기 위해 사용한다.
        __NEXT_DATA__가 없어도 상품 기본 파싱은 가능하므로 None을 허용한다.
        """
        script = soup.find("script", id="__NEXT_DATA__")

        if script is None:
            return None

        raw_json = script.string or script.get_text() or ""

        if not raw_json.strip():
            return None

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return None

        return data if isinstance(data, dict) else None

    # ============================================================
    # TAGS
    # ============================================================

    @classmethod
    def _extract_product_tags(
        cls,
        next_data: dict | None,
        goods_no: int | None,
    ) -> list[str] | None:
        """
        __NEXT_DATA__ 전체를 순회하면서 현재 goodsNo와 일치하고
        tags가 존재하는 상품 객체를 찾는다.
        """
        if not next_data or goods_no is None:
            return None

        tags = cls._find_tags_recursive(
            next_data,
            target_goods_no=str(goods_no),
        )

        if not tags:
            return None

        cleaned = [
            str(tag).strip() for tag in tags if tag is not None and str(tag).strip()
        ]

        return list(dict.fromkeys(cleaned)) or None

    @classmethod
    def _find_tags_recursive(
        cls,
        value,
        target_goods_no: str,
    ) -> list | None:
        if isinstance(value, dict):
            current_goods_no = value.get("goodsNo")

            if (
                current_goods_no is not None
                and str(current_goods_no) == target_goods_no
            ):
                tags = value.get("tags")

                if isinstance(tags, list):
                    return tags

            for child in value.values():
                result = cls._find_tags_recursive(
                    child,
                    target_goods_no,
                )
                if result:
                    return result

        elif isinstance(value, list):
            for child in value:
                result = cls._find_tags_recursive(
                    child,
                    target_goods_no,
                )
                if result:
                    return result

        return None

    # ============================================================
    # BRAND
    # ============================================================

    @classmethod
    def _parse_brand(
        cls,
        data: dict,
    ) -> dict:
        brand_info = data.get("brandInfo") or {}

        if not isinstance(brand_info, dict):
            brand_info = {}

        brand_id = cls._clean_text(brand_info.get("brand") or data.get("brand"))

        return {
            "brand_id": brand_id,
            "name_ko": cls._clean_text(brand_info.get("brandName")),
            "name_en": cls._clean_text(brand_info.get("brandEnglishName")),
            "nation": cls._clean_text(
                brand_info.get("brandNationName") or brand_info.get("brandNationCode")
            ),
            "since_year": cls._to_int(brand_info.get("sinceYear")),
            "logo_url": cls._normalize_image_url(brand_info.get("brandLogoImage")),
            "description": cls._clean_text(brand_info.get("memo")),
        }

    # ============================================================
    # PRODUCT
    # ============================================================

    @classmethod
    def _parse_product(
        cls,
        data: dict,
        tags: list[str] | None = None,
    ) -> dict:
        category = data.get("category") or {}
        brand_info = data.get("brandInfo") or {}

        if not isinstance(category, dict):
            category = {}

        if not isinstance(brand_info, dict):
            brand_info = {}

        sex = cls._parse_sex(data.get("sex"))

        return {
            "goods_no": cls._to_int(data.get("goodsNo")),
            "style_no": cls._clean_text(data.get("styleNo")),
            "name": cls._clean_text(data.get("goodsNm")),
            "brand_id": cls._clean_text(brand_info.get("brand") or data.get("brand")),
            "category_depth1": cls._clean_text(category.get("categoryDepth1Name")),
            "category_depth2": cls._clean_text(category.get("categoryDepth2Name")),
            "sex": sex,
            "season_year": cls._to_int(data.get("seasonYear")),
            "season": cls._clean_text(data.get("season")),
            "thumbnail_url": cls._normalize_image_url(data.get("thumbnailImageUrl")),
            "material_info": cls._parse_material_info(data.get("goodsMaterial")),
            "tags": tags,
        }

    # ============================================================
    # SNAPSHOT
    # ============================================================

    @classmethod
    def _parse_snapshot(
        cls,
        data: dict,
    ) -> dict:
        price = data.get("goodsPrice") or {}
        review = data.get("goodsReview") or {}
        ranking_record = data.get("rankingRecord") or {}

        if not isinstance(price, dict):
            price = {}

        if not isinstance(review, dict):
            review = {}

        if not isinstance(ranking_record, dict):
            ranking_record = {}

        ranking_badge = ranking_record.get("rankingArchiveBadge") or {}

        if not isinstance(ranking_badge, dict):
            ranking_badge = {}

        is_out_of_stock = cls._to_bool(
            data.get("isOutOfStock"),
            default=False,
        )

        return {
            # 가격
            "regular_price": cls._to_int(price.get("normalPrice")),
            "sale_price": cls._to_int(price.get("salePrice")),
            "discount_rate": cls._to_float(price.get("discountRate")),
            # 랭킹
            "rank": cls._to_int(ranking_badge.get("rank")),
            "ranking_period": cls._clean_text(ranking_badge.get("period")),
            "ranking_year": cls._to_int(ranking_badge.get("year")),
            "ranking_month": cls._to_int(ranking_badge.get("month")),
            "ranking_gender": cls._clean_text(ranking_badge.get("gender")),
            "ranking_category_depth1_code": cls._clean_text(
                ranking_badge.get("depth1CategoryCode")
            ),
            "ranking_category_depth1_name": cls._clean_text(
                ranking_badge.get("depth1CategoryName")
            ),
            "ranking_category_depth2_code": cls._clean_text(
                ranking_badge.get("depth2CategoryCode")
            ),
            "ranking_category_depth2_name": cls._clean_text(
                ranking_badge.get("depth2CategoryName")
            ),
            # 후기 / 반응
            "review_count": cls._to_int(review.get("totalCount")),
            "satisfaction_score": cls._to_float(review.get("satisfactionScore")),
            # 현재 상품 상세 HTML에서 신뢰할 수 있는 값을 확보하지 못한 필드.
            # 별도 endpoint 수집이 생기면 collector/service에서 보완한다.
            "like_count": None,
            "view_count": None,
            "sales_count": None,
            # 상태
            "availability": ("품절" if is_out_of_stock else "주문가능"),
            "is_out_of_stock": is_out_of_stock,
        }

    # ============================================================
    # UTIL
    # ============================================================

    @staticmethod
    def _clean_text(value) -> str | None:
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @classmethod
    def _parse_sex(
        cls,
        value,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, list):
            values = [cls._clean_text(item) for item in value]
            values = [item for item in values if item]
            return ", ".join(values) or None

        return cls._clean_text(value)

    @staticmethod
    def _to_int(value) -> int | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

        text = str(value).strip()

        if not text:
            return None

        text = text.replace(",", "").replace("원", "").replace("%", "").strip()

        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()

        if not text:
            return None

        text = text.replace(",", "").replace("%", "").strip()

        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_bool(
        value,
        default: bool = False,
    ) -> bool:
        if value is None:
            return default

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        text = str(value).strip().lower()

        if text in {"true", "1", "yes", "y"}:
            return True

        if text in {"false", "0", "no", "n", ""}:
            return False

        return default

    @classmethod
    def _normalize_image_url(
        cls,
        url: str | None,
    ) -> str | None:
        url = cls._clean_text(url)

        if not url:
            return None

        if url.startswith("//"):
            return f"https:{url}"

        if url.startswith("/"):
            return urljoin(
                IMAGE_BASE_URL,
                url,
            )

        return url

    @classmethod
    def _parse_material_info(
        cls,
        material_data,
    ) -> dict | None:
        if not isinstance(material_data, dict):
            return None

        materials = material_data.get("materials")

        if not isinstance(materials, list):
            return None

        result = {}

        for material in materials:
            if not isinstance(material, dict):
                continue

            category = cls._clean_text(material.get("name"))

            if not category:
                continue

            items = material.get("items")

            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                if not cls._to_bool(item.get("isSelected")):
                    continue

                value = cls._clean_text(item.get("name"))

                if value:
                    result[category] = value.replace("|", " ")

                break

        return result or None
