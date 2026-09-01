from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .constants import IMAGE_BASE_URL


def normalize_image_url(url: str | None) -> str | None:
    if url is None:
        return None
    url = str(url).strip()
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return urljoin(IMAGE_BASE_URL, url)
    return url


def parse_product_images(goods_images) -> list[dict]:
    if not isinstance(goods_images, list):
        return []
    result = []
    seen = set()
    for sequence, item in enumerate(goods_images):
        if isinstance(item, dict):
            url = normalize_image_url(item.get("imageUrl"))
        else:
            url = normalize_image_url(item)
        if not url or url in seen:
            continue
        seen.add(url)
        result.append({"sequence": sequence, "image_url": url, "image_type": "PRODUCT"})
    return result


def parse_detail_content(goods_contents: str | None) -> dict:
    html = (goods_contents or "").strip()
    if not html:
        return {"html": None, "images": [], "videos": []}

    soup = BeautifulSoup(html, "html.parser")
    images = []
    seen_images = set()
    for sequence, tag in enumerate(soup.find_all("img")):
        url = normalize_image_url(tag.get("src") or tag.get("data-src"))
        if not url or url in seen_images:
            continue
        seen_images.add(url)
        images.append({
            "sequence": sequence,
            "image_url": url,
            "image_type": "DETAIL",
            "alt": (tag.get("alt") or "").strip() or None,
        })

    videos = []
    seen_videos = set()
    for tag in soup.find_all(["iframe", "video", "source"]):
        url = (tag.get("src") or "").strip()
        if not url or url in seen_videos:
            continue
        seen_videos.add(url)
        videos.append(url)

    return {"html": html, "images": images, "videos": videos}
