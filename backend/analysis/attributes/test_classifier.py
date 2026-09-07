# backend/analysis/attributes/test_classifier.py

from pprint import pprint

from analysis.attributes.classifier import (
    FashionAttributeClassifier,
)
from analysis.attributes.normalizer import (
    AttributeNormalizer,
)


classifier = FashionAttributeClassifier()

result = classifier.predict(
    image_url=(
        "https://image.msscdn.net/"
        "thumbnails/images/goods_img/"
        "20260331/6230383/"
        "6230383_17751258296095_big.jpg?w=1200"
    ),
    product_name=(
        "에센셜 옥스포드 크롭 반팔 셔츠_5color"
    ),

    description=(
        "허리 선에서 끊기는 크롭한 기장감과 자연스럽게 떨어지는 실루엣으로 트렌디하고 미니멀한 아웃핏 연출. "
        "면 폴리 혼방의 밀도 높은 소재로 부드러운 터치감과 자유로운 활동성도 높은 데일리 아이템. "
        "전면에 간단한 소지품 수납이 가능한 포켓을 배치해 디테일적 포인트는 물론 높은 실용성. "
        "탄탄한 조직감이 느껴지는 16수의 옥스포드 소재로 클래식한 색감과 튼튼한 내구성. "
        "세트 구성된 4 컬러의 넥타이와 함께 매치하여 TPO에 맞는 다양한 스타일링 가능. "
        "전문 모델리스트의 인체 공학적 패턴 작업을 통해 트릴리온만의 편안한 착용감."
    ),

    category="셔츠",  # 원본 코드의 "데님 팬츠"는 이미지 내용(셔츠)과 맞지 않아 수정했습니다

    brand="TRILLION",  # 이미지 하단 워터마크 기준. 확실치 않으면 TEST 유지하세요

    top_k=3,
)

print("\n========================")
print("RAW RESULT")
print("========================")

pprint(result)


normalizer = AttributeNormalizer()

normalized = normalizer.normalize(
    result
)

print("\n========================")
print("NORMALIZED")
print("========================")

pprint(normalized)


print("\n========================")
print("TIMING")
print("========================")

print(
    f"Encoding       : "
    f"{result['timing']['encoding_ms']} ms"
)

print(
    f"Classification : "
    f"{result['timing']['classification_ms']} ms"
)

print(
    f"TOTAL          : "
    f"{result['timing']['total_ms']} ms"
)