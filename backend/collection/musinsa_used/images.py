from __future__ import annotations

from .constants import IMAGE_BASE_URL


def normalize_image_url(value) -> str | None:
    """Preserve absolute URLs and normalize only source-relative images."""
    if not value:
        return None
    url = str(value).strip()
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return IMAGE_BASE_URL + url
    return url
