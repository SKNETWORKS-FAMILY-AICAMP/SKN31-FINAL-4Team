# analysis/vision/utils.py
from io import BytesIO
from typing import Iterable

import requests
from PIL import Image

from .schemas import Detection


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
DEFAULT_TIMEOUT = 20


def load_image_from_url(url: str) -> Image.Image:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")


def split_vertical_image(
    image: Image.Image,
    slice_height: int = 1024,
    overlap: int = 200,
) -> list[dict]:
    width, height = image.size
    results = []

    y = 0
    index = 0
    while y < height:
        bottom = min(y + slice_height, height)
        crop = image.crop((0, y, width, bottom))
        results.append(
            {
                "image": crop,
                "offset_y": y,
                "index": index,
            }
        )
        if bottom >= height:
            break
        y += slice_height - overlap
        index += 1

    return results

def restore_coordinates(
    detection: Detection,
    offset_y: int,
) -> Detection:
    return Detection(
        label=detection.label,
        normalized_category=detection.normalized_category,
        score=detection.score,
        x1=detection.x1,
        y1=detection.y1 + offset_y,
        x2=detection.x2,
        y2=detection.y2 + offset_y,
        source_slice_index=detection.source_slice_index,
    )

def clamp_detection(
    d: Detection,
    image_width: int,
    image_height: int,
) -> Detection:
    x1 = max(0, min(d.x1, image_width))
    y1 = max(0, min(d.y1, image_height))
    x2 = max(0, min(d.x2, image_width))
    y2 = max(0, min(d.y2, image_height))

    return Detection(
        label=d.label,
        normalized_category=d.normalized_category,
        score=d.score,
        x1=min(x1, x2),
        y1=min(y1, y2),
        x2=max(x1, x2),
        y2=max(y1, y2),
        source_slice_index=d.source_slice_index,
    )
def add_padding(
    d: Detection,
    image_width: int,
    image_height: int,
    pad_ratio: float = 0.05,
) -> Detection:
    pad_x = int(d.width * pad_ratio)
    pad_y = int(d.height * pad_ratio)

    return clamp_detection(
        Detection(
            label=d.label,
            normalized_category=d.normalized_category,
            score=d.score,
            x1=d.x1 - pad_x,
            y1=d.y1 - pad_y,
            x2=d.x2 + pad_x,
            y2=d.y2 + pad_y,
            source_slice_index=d.source_slice_index,
        ),
        image_width=image_width,
        image_height=image_height,
    )


def iou(a: Detection, b: Detection) -> float:
    inter_x1 = max(a.x1, b.x1)
    inter_y1 = max(a.y1, b.y1)
    inter_x2 = min(a.x2, b.x2)
    inter_y2 = min(a.y2, b.y2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    union_area = a.area + b.area - inter_area
    if union_area <= 0:
        return 0.0

    return inter_area / union_area


def nms(detections: Iterable[Detection], iou_threshold: float = 0.5) -> list[Detection]:
    sorted_dets = sorted(detections, key=lambda x: x.score, reverse=True)
    kept: list[Detection] = []

    while sorted_dets:
        current = sorted_dets.pop(0)
        kept.append(current)

        remain = []
        for det in sorted_dets:
            if iou(current, det) < iou_threshold:
                remain.append(det)
        sorted_dets = remain

    return kept