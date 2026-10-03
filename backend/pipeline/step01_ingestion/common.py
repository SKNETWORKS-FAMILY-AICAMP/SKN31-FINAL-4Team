from __future__ import annotations

import json
import re
import unicodedata
from bs4 import BeautifulSoup

import boto3
from django.conf import settings

from apps.core.models import RawDocument


# ============================================================
# BASE CLEANING
# ============================================================

_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\uFE0E\uFE0F"
    "]+",
    flags=re.UNICODE,
)

_CONTROL_RE = re.compile(
    r"[\u0000-\u0008"
    r"\u000B\u000C"
    r"\u000E-\u001F"
    r"\u007F"
    r"\u200B-\u200D"
    r"\u2060"
    r"\uFEFF]"
)

_NOISE_PUNCTUATION_RE = re.compile(
    r"[!?！？]+"
)

_WHITESPACE_RE = re.compile(
    r"\s+"
)


def base_cleaning(
    value,
) -> str | None:
    """
    STEP 01 최소 클리닝.

    제거:
    - emoji
    - ! ?
    - 제어문자
    - zero-width 문자
    - 연속 공백

    보존:
    - ()
    - []
    - {}
    - *
    - /
    - _
    - -
    - +
    - &
    - .
    - ,
    - :
    - %
    등 의미를 가질 수 있는 표현
    """

    if value is None:
        return None

    text = str(value)

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = _CONTROL_RE.sub(
        "",
        text,
    )

    text = _EMOJI_RE.sub(
        "",
        text,
    )

    text = _NOISE_PUNCTUATION_RE.sub(
        "",
        text,
    )

    text = _WHITESPACE_RE.sub(
        " ",
        text,
    )

    text = text.strip()

    return text or None


# ============================================================
# S3
# ============================================================

def get_s3_client():
    return boto3.client(
        "s3",
        region_name=getattr(
            settings,
            "AWS_REGION",
            "ap-northeast-2",
        ),
    )


def load_raw_json(
    raw_document: RawDocument,
    *,
    s3_client=None,
) -> dict:

    s3_client = (
        s3_client
        or get_s3_client()
    )

    response = s3_client.get_object(
        Bucket=raw_document.s3_bucket,
        Key=raw_document.s3_key,
    )

    body = response["Body"].read()

    data = json.loads(
        body.decode("utf-8")
    )

    if not isinstance(data, dict):
        raise ValueError(
            f"RawDocument #{raw_document.id} "
            "JSON root가 dict가 아닙니다."
        )

    return data


def extract_payload(
    raw_data: dict,
) -> dict:
    """
    collection 저장 포맷 차이 대응.

    {"payload": {...}}
    {"data": {...}}
    {...}

    모두 지원한다.
    """

    payload = raw_data.get(
        "payload"
    )

    if isinstance(payload, dict):
        return payload

    data = raw_data.get(
        "data"
    )

    if isinstance(data, dict):
        return data

    return raw_data


def extract_products(
    payload: dict,
) -> list[dict]:
    """
    Ranking RAW:
        {
            "products": [...]
        }

    단일 상품 RAW:
        {
            "brand": {...},
            "product": {...},
            ...
        }
    """

    products = payload.get(
        "products"
    )

    if isinstance(products, list):
        return [
            item
            for item in products
            if isinstance(item, dict)
        ]

    if isinstance(
        payload.get("product"),
        dict,
    ):
        return [payload]

    return []

from bs4 import BeautifulSoup


def extract_detail_text(
    detail_content: dict | None,
) -> str | None:
    """
    상품 상세 HTML에서 텍스트만 추출한다.

    - img 제거
    - video 제거
    - script/style 제거
    - HTML tag 제거
    - 모델 사이즈 이후 정보 제거
    - 마지막에 base_cleaning 적용

    STEP01에서는 의미 해석을 하지 않고
    원문 텍스트만 보존한다.
    """

    if not isinstance(
        detail_content,
        dict,
    ):
        return None

    html = detail_content.get(
        "html"
    )

    if not html:
        return None

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # 분석에 필요 없는 요소 제거
    for tag in soup.find_all(
        [
            "img",
            "video",
            "script",
            "style",
        ]
    ):
        tag.decompose()

    text = soup.get_text(
        separator=" ",
        strip=True,
    )

    # 모델 신체 정보 제거
    model_markers = [
        "MODEL SIZE",
        "Model Size",
        "model size",
        "모델 사이즈",
    ]

    for marker in model_markers:
        if marker in text:
            text = text.split(
                marker,
                1,
            )[0]
            break

    return base_cleaning(
        text
    )