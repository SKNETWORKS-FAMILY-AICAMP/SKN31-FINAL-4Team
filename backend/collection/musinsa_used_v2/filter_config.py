from __future__ import annotations

API_URL = "https://api.musinsa.com/api2/dp/v2/plp/goods"
PRODUCT_URL = "https://www.musinsa.com/products/{goods_no}"
SALE_INFORMATION_URL = (
    "https://goods-detail.musinsa.com/api2/used/goods/"
    "{goods_no}/sale-information"
)
RELATED_GOODS_URL = (
    "https://goods-detail.musinsa.com/api2/used/goods/"
    "{goods_no}/related-goods"
)
PRICE_ANCHOR_URL = (
    "https://goods-detail.musinsa.com/api2/used/goods/"
    "{goods_no}/price-anchor"
)

DEFAULT_SORT_CODE = "USED_SALE_PRICE_CHANGE_DATE"
DEFAULT_PAGE_SIZE = 30
DEFAULT_LIMIT = 100
DEFAULT_SLEEP_SECONDS = 0.8

CATEGORY_MAP = {
    "상의": "109001",
    "아우터": "109002",
    "바지": "109003",
    "원피스/스커트": "109004",
}

FILTER_TYPES = [
    "condition",
    "color",
    "cooling",
    "pattern",
    "material",
    "standard_size",
    "measurement",
    "shoe_size",
    "fit",
    "attribute",
    "sale_type",
    "theme",
]


# 기존 수동/정적 타깃 호환용.
# 신규 등록은 API filter metadata를 우선 사용한다.
FILTER_GROUPS = {
    "pattern": {
        "label": "패턴/무늬",
        "parameter": "attributePattern",
        "values": {
            "단색": "UkBJuUOWbLgc^n4ehCSM2I6cn",
            "로고/그래픽": "UkBJuUOWbLgc^hxbmRhPzNCbD",
            "스트라이프": "UkBJuUOWbLgc^YbhxtFSYTEGM",
            "컬러블록": "UkBJuUOWbLgc^uBYH5gy8WZsj",
            "체크": "UkBJuUOWbLgc^28crelau1gpm",
            "아가일": "UkBJuUOWbLgc^5EpJbPkbald4",
            "플라워": "UkBJuUOWbLgc^TuYRkFqID44S",
            "그라데이션": "UkBJuUOWbLgc^KgqPH34X05eo",
            "디스트로이드": "UkBJuUOWbLgc^JtoTaJGxjrSV",
            "애니멀패턴": "UkBJuUOWbLgc^JubJhUVJfISk",
            "도트": "UkBJuUOWbLgc^gv91Cmjk48cR",
            "카모플라쥬": "UkBJuUOWbLgc^OhggxkPatzUL",
            "가먼트 다잉": "UkBJuUOWbLgc^ThLgF0I2xk9W",
            "하운드투스": "UkBJuUOWbLgc^CFd4dcvCquhm",
            "헤링본": "UkBJuUOWbLgc^r5K0zCg8jGiF",
            "타이다이": "UkBJuUOWbLgc^ln9XgwTNBc6g",
            "니트패널": "UkBJuUOWbLgc^Mr48cnkBO9S7",
            "체커보드": "UkBJuUOWbLgc^tytNCQTzb6Rv",
            "페이즐리": "UkBJuUOWbLgc^bJeZa9JjVOQP",
            "캐릭터": "UkBJuUOWbLgc^AfrFDPnpKGwM",
            "패치워크": "UkBJuUOWbLgc^XM6n7zS0xuY8",
        },
    },
    "material": {
        "label": "소재",
        "parameter": "attributeMaterial",
        "values": {
            "면(코튼)": "g_material^rYIBGq2Ot2Qh",
            "니트": "g_material^Jil9msfdxIv5",
            "폴리에스테르": "g_material^RedzeswVYYOa",
            "아크릴": "g_material^rMpeCJlgNjp1",
            "나일론": "g_material^vGbOb7CVby3q",
            "울/모": "g_material^UBSB4AP5JfAA",
            "스판덱스": "g_material^HLlXIp8L4jxF",
            "레이온/인견": "g_material^MQMwTUHYfilr",
            "캐시미어": "g_material^gX22wnplycyJ",
            "데님": "g_material^7hzHO7WT8tLe",
            "린넨": "g_material^QXm8shmCAi1j",
            "메시": "g_material^M64ETV0XqLvo",
            "실크": "g_material^D0YHmjCqsXSb",
            "기모": "g_material^fZms24b7AKtm",
            "인조가죽": "g_material^atfL29ufp3Yy",
            "코듀로이": "g_material^BpPKYb8ezDnJ",
            "플리스": "g_material^K5G86b9O8q37",
            "천연가죽": "g_material^meapgFVZB5L2",
        },
    },
    "fit": {
        "label": "핏",
        "parameter": "attributeFit",
        "values": {
            "기본": "g_fit^x7imVBxHnpKM",
            "오버": "g_fit^S5JWveeUyrw4",
            "와이드": "g_fit^1G1BTZmN9RnS",
            "스트레이트": "g_fit^N5LCh096O1MN",
            "슬림": "g_fit^1ev2RqRx5OKT.efMbpVoTf7eV",
            "테이퍼드": "g_fit^JzpcZkg1YWBw",
            "부츠컷": "g_fit^SfRNI13wsS0E",
            "배기": "g_fit^CsiPJVvpAAEz",
            "조거": "g_fit^3UJZaBRKjYqI",
        },
    },
    "condition": {
        "label": "컨디션",
        "parameter": "conditionGradeCodes",
        "values": {
            "S+등급": "1",
            "S등급": "2",
            "A+등급": "3",
            "A등급": "4",
            "B등급": "5",
        },
    },
}

# API가 내려주는 parameterKey 중 FEEDIT에서 상품 속성 evidence로 쓸 축.
# brand/category/price/discount 등은 다른 정규화 경로가 있으므로 제외한다.
FILTER_PARAMETER_RULES = {
    "conditionGradeCodes": {
        "type": "condition",
        "label": "컨디션",
    },
    "color": {
        "type": "color",
        "label": "컬러",
    },
    "attributeCooling": {
        "type": "cooling",
        "label": "냉감",
    },
    "attributePattern": {
        "type": "pattern",
        "label": "패턴/무늬",
    },
    "attributeMaterial": {
        "type": "material",
        "label": "소재",
    },
    "standardSize": {
        "type": "standard_size",
        "label": "사이즈",
    },
    "measurement": {
        "type": "measurement",
        "label": "실측/치수",
    },
    "shoeSize": {
        "type": "shoe_size",
        "label": "신발 사이즈",
    },
    "attributeFit": {
        "type": "fit",
        "label": "핏",
    },
    "attribute": {
        "type": "attribute",
        "label": "상세옵션",
    },
    "saleType": {
        "type": "sale_type",
        "label": "상품유형",
    },
    "theme": {
        "type": "theme",
        "label": "테마",
    },
}

FILTER_TYPES = sorted({
    rule["type"]
    for rule in FILTER_PARAMETER_RULES.values()
})


def get_filter_group(key: str) -> dict:
    try:
        return FILTER_GROUPS[key]
    except KeyError as exc:
        raise ValueError(
            f"지원하지 않는 정적 filter_type={key!r}. "
            f"가능: {', '.join(FILTER_GROUPS)}"
        ) from exc


def get_filter_rule(parameter: str) -> dict | None:
    return FILTER_PARAMETER_RULES.get(str(parameter))
