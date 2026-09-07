from __future__ import annotations

import time
from io import BytesIO
import numpy as np

import easyocr
import requests
import torch
from PIL import Image


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def load_image_from_url(
    image_url: str,
    timeout: int = 20,
) -> Image.Image:

    response = requests.get(
        image_url,
        headers=DEFAULT_HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    return Image.open(
        BytesIO(response.content)
    ).convert("RGB")


class ProductDetailOCR:

    def __init__(
        self,
        languages: list[str] | None = None,
        gpu: bool | None = None,
    ):
        self.languages = languages or ["ko", "en"]

        if gpu is None:
            gpu = torch.cuda.is_available()

        self.gpu = gpu

        print(
            f"[ProductDetailOCR] loading EasyOCR "
            f"languages={self.languages}, gpu={self.gpu}"
        )

        started_at = time.perf_counter()

        self.reader = easyocr.Reader(
            self.languages,
            gpu=self.gpu,
        )

        elapsed = time.perf_counter() - started_at

        print(
            f"[ProductDetailOCR] loaded in {elapsed:.2f}s"
        )

    def extract(
        self,
        image_url: str,
        min_confidence: float = 0.25,
    ) -> dict:

        total_start = time.perf_counter()

        # --------------------------
        # 1. 이미지 다운로드
        # --------------------------

        load_start = time.perf_counter()

        image = load_image_from_url(
            image_url
        )

        image_load_elapsed = (
            time.perf_counter()
            - load_start
        )

        # PIL -> numpy
        image_np = np.array(image)

        # --------------------------
        # 2. OCR
        # --------------------------

        ocr_start = time.perf_counter()

        results = self.reader.readtext(
            image_np,
            detail=1,
            paragraph=False,
        )

        ocr_elapsed = (
            time.perf_counter()
            - ocr_start
        )

        blocks = []

        for bbox, text, confidence in results:

            confidence = float(confidence)

            if confidence < min_confidence:
                continue

            text = text.strip()

            if not text:
                continue

            x_values = [
                float(point[0])
                for point in bbox
            ]

            y_values = [
                float(point[1])
                for point in bbox
            ]

            x_min = min(x_values)
            x_max = max(x_values)
            y_min = min(y_values)
            y_max = max(y_values)

            blocks.append(
                {
                    "text": text,
                    "confidence": round(
                        confidence,
                        4,
                    ),
                    "bbox": {
                        "x_min": round(
                            x_min,
                            2,
                        ),
                        "y_min": round(
                            y_min,
                            2,
                        ),
                        "x_max": round(
                            x_max,
                            2,
                        ),
                        "y_max": round(
                            y_max,
                            2,
                        ),
                    },
                    "center": {
                        "x": round(
                            (x_min + x_max) / 2,
                            2,
                        ),
                        "y": round(
                            (y_min + y_max) / 2,
                            2,
                        ),
                    },
                }
            )

        # 위 → 아래 순서
        blocks.sort(
            key=lambda item: (
                item["center"]["y"],
                item["center"]["x"],
            )
        )

        raw_text = "\n".join(
            block["text"]
            for block in blocks
        )

        total_elapsed = (
            time.perf_counter()
            - total_start
        )

        return {
            "image_url": image_url,
            "raw_text": raw_text,
            "blocks": blocks,
            "block_count": len(blocks),
            "timing": {
                "image_load_ms": round(
                    image_load_elapsed * 1000,
                    2,
                ),
                "ocr_ms": round(
                    ocr_elapsed * 1000,
                    2,
                ),
                "total_ms": round(
                    total_elapsed * 1000,
                    2,
                ),
            },
        }