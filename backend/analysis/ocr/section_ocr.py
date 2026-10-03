from __future__ import annotations

import time
from io import BytesIO

import easyocr
import numpy as np
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
    "Accept": (
        "image/avif,image/webp,"
        "image/apng,image/svg+xml,"
        "image/*,*/*;q=0.8"
    ),
    "Accept-Language": (
        "ko-KR,ko;q=0.9,en;q=0.8"
    ),
}


OCR_POLICY = {
    "INTRO": {
        "use_ocr": True,
        "max_height": 6000,
    },

    "FABRIC": {
        "use_ocr": True,
        "max_height": 5000,
    },

    "DETAIL": {
        "use_ocr": True,
        "max_height": 8000,
    },
}


class SectionOCR:

    def __init__(
        self,
        languages: list[str] | None = None,
        gpu: bool | None = None,
    ):
        self.languages = (
            languages
            or ["ko", "en"]
        )

        if gpu is None:
            gpu = torch.cuda.is_available()

        self.gpu = gpu

        print(
            f"[SectionOCR] loading EasyOCR "
            f"languages={self.languages}, "
            f"gpu={self.gpu}"
        )

        start = time.perf_counter()

        self.reader = easyocr.Reader(
            self.languages,
            gpu=self.gpu,
        )

        print(
            f"[SectionOCR] loaded in "
            f"{time.perf_counter() - start:.2f}s"
        )

    def _load_image(
        self,
        image_url: str,
        timeout: int = 30,
    ) -> Image.Image:

        response = requests.get(
            image_url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
        )

        response.raise_for_status()

        return Image.open(
            BytesIO(
                response.content
            )
        ).convert(
            "RGB"
        )

    def _crop_by_policy(
        self,
        image: Image.Image,
        section_type: str,
    ) -> Image.Image:

        policy = OCR_POLICY.get(
            section_type
        )

        if not policy:
            return image

        max_height = policy.get(
            "max_height"
        )

        if not max_height:
            return image

        width, height = image.size

        if height <= max_height:
            return image

        print(
            f"[SectionOCR] crop "
            f"{width}x{height} "
            f"-> {width}x{max_height}"
        )

        return image.crop(
            (
                0,
                0,
                width,
                max_height,
            )
        )

    def extract(
        self,
        image_url: str,
        section_type: str,
        min_confidence: float = 0.25,
    ) -> dict:

        total_start = (
            time.perf_counter()
        )

        policy = OCR_POLICY.get(
            section_type
        )

        if not policy:
            return {
                "image_url": image_url,
                "section_type": section_type,
                "skipped": True,
                "raw_text": "",
                "blocks": [],
                "block_count": 0,
                "timing": {
                    "total_ms": 0,
                },
            }

        load_start = (
            time.perf_counter()
        )

        image = self._load_image(
            image_url
        )

        original_width, (
            original_height
        ) = image.size

        load_elapsed = (
            time.perf_counter()
            - load_start
        )

        image = self._crop_by_policy(
            image=image,
            section_type=section_type,
        )

        processed_width, (
            processed_height
        ) = image.size

        ocr_start = (
            time.perf_counter()
        )

        image_np = np.array(
            image
        )

        results = self.reader.readtext(
            image_np,
            detail=1,
            paragraph=False,
            canvas_size=2560,
            mag_ratio=1.0,
        )

        ocr_elapsed = (
            time.perf_counter()
            - ocr_start
        )

        blocks = []

        for (
            bbox,
            text,
            confidence,
        ) in results:

            confidence = float(
                confidence
            )

            if (
                confidence
                < min_confidence
            ):
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
                        "x_min": x_min,
                        "y_min": y_min,
                        "x_max": x_max,
                        "y_max": y_max,
                    },

                    "center": {
                        "x": (
                            x_min
                            + x_max
                        ) / 2,

                        "y": (
                            y_min
                            + y_max
                        ) / 2,
                    },
                }
            )

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

        print(
            f"[SectionOCR] "
            f"{section_type} "
            f"blocks={len(blocks)} "
            f"ocr={ocr_elapsed:.2f}s"
        )

        return {
            "image_url": image_url,

            "section_type": (
                section_type
            ),

            "skipped": False,

            "original_size": {
                "width": original_width,
                "height": original_height,
            },

            "processed_size": {
                "width": processed_width,
                "height": processed_height,
            },

            "block_count": len(
                blocks
            ),

            "raw_text": raw_text,

            "blocks": blocks,

            "timing": {
                "image_load_ms": round(
                    load_elapsed * 1000,
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