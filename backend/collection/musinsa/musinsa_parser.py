import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class MusinsaParseError(Exception):
    """
    무신사 상품 페이지에서 필요한 데이터를
    정상적으로 추출하지 못했을 때 발생하는 예외
    """

    pass


class MusinsaParser:
    """
    무신사 상품 상세 페이지 Parser

    역할:
    1. HTML에서 상품 JSON 추출
    2. MusinsaBrand용 데이터 생성
    3. MusinsaProduct용 데이터 생성
    4. MusinsaProductSnapshot용 데이터 생성

    HTTP 요청과 DB 저장은 담당하지 않는다.
    """

    IMAGE_BASE_URL = "https://image.msscdn.net"

    PARSER_VERSION = "musinsa-product-v0.2"

    # ---------------------------------------------------------
    # PUBLIC
    # ---------------------------------------------------------

    @classmethod
    def parse_product(cls, html: str) -> dict:
        """
        상품 HTML 하나를 받아 DB 저장 직전 형태로 반환한다.
        """

        product_state = cls._extract_product_state(html)

        next_data = cls._extract_next_data(html)

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
                "parser_version": cls.PARSER_VERSION,
            },
        }

    # ---------------------------------------------------------
    # PRODUCT STATE
    # ---------------------------------------------------------

    @classmethod
    def _extract_product_state(cls, html: str) -> dict:
        """
        <script id="pdp-data"> 내부의

        window.__MSS_FE__.product.state = {...};

        JSON 추출
        """

        if not html:
            raise MusinsaParseError("HTML이 비어 있습니다.")

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        script = soup.find(
            "script",
            id="pdp-data",
        )

        if script is None:
            raise MusinsaParseError("pdp-data script를 찾을 수 없습니다.")

        script_text = script.get_text()

        pattern = re.compile(
            r"window\.__MSS_FE__\.product\.state\s*=\s*(\{.*?\});"
            r"\s*window\.__MSS_FE__\.experimentVariant",
            re.DOTALL,
        )

        match = pattern.search(script_text)

        if match is None:
            raise MusinsaParseError(
                "window.__MSS_FE__.product.state를 찾을 수 없습니다."
            )

        raw_json = match.group(1)

        try:
            data = json.loads(raw_json)

        except json.JSONDecodeError as exc:
            raise MusinsaParseError(f"상품 JSON 파싱 실패: {exc}") from exc

        if not data.get("goodsNo"):
            raise MusinsaParseError("goodsNo가 존재하지 않습니다.")

        if not data.get("goodsNm"):
            raise MusinsaParseError("goodsNm이 존재하지 않습니다.")

        return data

    # ---------------------------------------------------------
    # NEXT DATA
    # ---------------------------------------------------------

    @classmethod
    def _extract_next_data(
        cls,
        html: str,
    ) -> dict | None:
        """
        Next.js SSR 데이터.

        상품 태그 등 product.state에 없는
        추가 정보를 찾기 위해 사용.
        """

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        script = soup.find(
            "script",
            id="__NEXT_DATA__",
        )

        if script is None:
            return None

        raw_json = script.get_text()

        if not raw_json:
            return None

        try:
            return json.loads(raw_json)

        except json.JSONDecodeError:
            return None

    # ---------------------------------------------------------
    # TAGS
    # ---------------------------------------------------------

    @classmethod
    def _extract_product_tags(
        cls,
        next_data: dict | None,
        goods_no: int | None,
    ) -> list[str] | None:
        """
        __NEXT_DATA__ 전체를 순회하면서

        goodsNo == 현재 상품번호

        이면서 tags가 존재하는 상품 객체를 찾는다.

        예:
        [
            "반팔",
            "반팔셔츠",
            "캐주얼셔츠",
            ...
        ]
        """

        if not next_data or goods_no is None:
            return None

        target_goods_no = str(goods_no)

        tags = cls._find_tags_recursive(
            next_data,
            target_goods_no,
        )

        if not tags:
            return None

        # 중복 제거 + 순서 유지
        return list(dict.fromkeys(tags))

    @classmethod
    def _find_tags_recursive(
        cls,
        value,
        target_goods_no: str,
    ) -> list[str] | None:

        if isinstance(value, dict):

            current_goods_no = value.get("goodsNo")

            if (
                current_goods_no is not None
                and str(current_goods_no) == target_goods_no
            ):

                tags = value.get("tags")

                if isinstance(
                    tags,
                    list,
                ):
                    return [str(tag) for tag in tags if tag]

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

    # ---------------------------------------------------------
    # BRAND
    # ---------------------------------------------------------

    @classmethod
    def _parse_brand(
        cls,
        data: dict,
    ) -> dict:

        brand_info = data.get("brandInfo") or {}

        return {
            "brand_id": (brand_info.get("brand") or data.get("brand")),
            "name_ko": brand_info.get("brandName"),
            "name_en": brand_info.get("brandEnglishName"),
            "nation": (
                brand_info.get("brandNationName") or brand_info.get("brandNationCode")
            ),
            "since_year": cls._to_int(brand_info.get("sinceYear")),
            "logo_url": (cls._normalize_image_url(brand_info.get("brandLogoImage"))),
            "description": brand_info.get("memo"),
        }

    # ---------------------------------------------------------
    # PRODUCT
    # ---------------------------------------------------------

    @classmethod
    def _parse_product(
        cls,
        data: dict,
        tags=None,
    ) -> dict:

        category = data.get("category") or {}

        brand_info = data.get("brandInfo") or {}

        sex_values = data.get("sex") or []

        if isinstance(
            sex_values,
            list,
        ):

            sex = ", ".join(str(value) for value in sex_values)

        else:
            sex = str(sex_values)

        return {
            "goods_no": cls._to_int(data.get("goodsNo")),
            "style_no": data.get("styleNo"),
            "name": data.get("goodsNm"),
            "brand_id": (brand_info.get("brand") or data.get("brand")),
            "category_depth1": (category.get("categoryDepth1Name")),
            "category_depth2": (category.get("categoryDepth2Name")),
            "sex": (sex or None),
            "season_year": cls._to_int(data.get("seasonYear")),
            "season": data.get("season"),
            "thumbnail_url": (cls._normalize_image_url(data.get("thumbnailImageUrl"))),
            "material_info": cls._parse_material_info(data.get("goodsMaterial")),
            # 새로 추가
            "tags": tags,
        }

    # ---------------------------------------------------------
    # SNAPSHOT
    # ---------------------------------------------------------

    @classmethod
    def _parse_snapshot(
        cls,
        data: dict,
    ) -> dict:

        price = data.get("goodsPrice") or {}

        review = data.get("goodsReview") or {}

        ranking_record = data.get("rankingRecord") or {}

        ranking_badge = ranking_record.get("rankingArchiveBadge") or {}

        is_out_of_stock = bool(
            data.get(
                "isOutOfStock",
                False,
            )
        )

        availability = "품절" if is_out_of_stock else "주문가능"

        return {
            # -------------------------
            # 가격
            # -------------------------
            "regular_price": cls._to_int(price.get("normalPrice")),
            "sale_price": cls._to_int(price.get("salePrice")),
            "discount_rate": cls._to_float(price.get("discountRate")),
            # -------------------------
            # 랭킹
            # -------------------------
            "rank": cls._to_int(ranking_badge.get("rank")),
            "ranking_period": (ranking_badge.get("period")),
            "ranking_year": cls._to_int(ranking_badge.get("year")),
            "ranking_month": cls._to_int(ranking_badge.get("month")),
            "ranking_gender": (ranking_badge.get("gender")),
            "ranking_category_depth1_code": (ranking_badge.get("depth1CategoryCode")),
            "ranking_category_depth1_name": (ranking_badge.get("depth1CategoryName")),
            "ranking_category_depth2_code": (ranking_badge.get("depth2CategoryCode")),
            "ranking_category_depth2_name": (ranking_badge.get("depth2CategoryName")),
            # -------------------------
            # 후기 / 반응
            # -------------------------
            "review_count": cls._to_int(review.get("totalCount")),
            "satisfaction_score": (cls._to_float(review.get("satisfactionScore"))),
            # 상품 좋아요 수는
            # 현재 HTML의 product.state / __NEXT_DATA__
            # 에서 신뢰 가능한 값을 찾지 못했음.
            #
            # __NEXT_DATA__의 likeCount는
            # SNAP 게시물 좋아요이므로 사용하면 안 됨.
            "like_count": None,
            # 상품 최근 조회수
            "view_count": None,
            # 상품 누적 판매량
            "sales_count": None,
            "availability": (availability),
            "is_out_of_stock": (is_out_of_stock),
        }

    # ---------------------------------------------------------
    # UTIL
    # ---------------------------------------------------------

    @staticmethod
    def _to_int(value):

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_float(value):

        if value is None:
            return None

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @classmethod
    def _normalize_image_url(
        cls,
        url: str | None,
    ) -> str | None:

        if not url:
            return None

        if url.startswith("//"):
            return f"https:{url}"

        if url.startswith("/"):
            return urljoin(
                cls.IMAGE_BASE_URL,
                url,
            )

        return url

    @staticmethod
    def _parse_material_info(material_data):

        if not material_data:
            return None

        result = {}

        materials = material_data.get("materials", [])

        for material in materials:

            category = material.get("name")

            if not category:
                continue

            for item in material.get("items", []):

                if item.get("isSelected"):

                    value = item.get("name")

                    if value:
                        result[category] = value.replace("|", " ")

                    break

        return result or None
