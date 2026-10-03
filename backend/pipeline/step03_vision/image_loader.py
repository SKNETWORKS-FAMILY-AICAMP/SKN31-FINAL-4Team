from __future__ import annotations

import io
from typing import Any

import requests
from PIL import Image


def _clean_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    if value.startswith("//"):
        return "https:" + value

    if value.startswith("/images/"):
        return "https://image.msscdn.net" + value

    if value.startswith(("http://", "https://")):
        return value

    return None


def get_product_image_url(product_source) -> str | None:
    """
    ProductSource의 대표 이미지 URL을 찾는다.

    우선순위:
    1. thumbnail_url / image_url 등 실제 model field
    2. attributes 내부의 흔한 이미지 키

    프로젝트별 attributes 구조가 달라도 최대한 보수적으로 찾는다.
    """

    field_candidates = (
        "thumbnail_url",
        "image_url",
        "thumbnail",
        "image",
    )

    field_names = {
        field.name
        for field in product_source._meta.fields
    }

    for field_name in field_candidates:
        if field_name not in field_names:
            continue

        url = _clean_url(
            getattr(product_source, field_name, None)
        )

        if url:
            return url

    attributes = getattr(
        product_source,
        "attributes",
        None,
    )

    if not isinstance(attributes, dict):
        return None

    attr_candidates = (
        "thumbnail_url",
        "image_url",
        "thumbnail",
        "image",
        "main_image",
        "main_image_url",
    )

    for key in attr_candidates:
        url = _clean_url(attributes.get(key))

        if url:
            return url

    product = attributes.get("product")

    if isinstance(product, dict):
        for key in attr_candidates:
            url = _clean_url(product.get(key))

            if url:
                return url

    return None


def download_rgb_image(
    image_url: str,
    *,
    timeout: int,
    user_agent: str,
) -> Image.Image:
    response = requests.get(
        image_url,
        timeout=timeout,
        headers={
            "User-Agent": user_agent,
        },
    )

    response.raise_for_status()

    return Image.open(
        io.BytesIO(response.content)
    ).convert("RGB")
