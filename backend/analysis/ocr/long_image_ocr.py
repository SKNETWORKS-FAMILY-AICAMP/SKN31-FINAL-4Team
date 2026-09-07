# backend/analysis/ocr/long_image_ocr.py

from __future__ import annotations

import time
from io import BytesIO

import cv2
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
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


class LongImageOCR:

    def __init__(
        self,
        languages: list[str] | None = None,
        gpu: bool | None = None,
        scout_width: int = 500,
        min_region_height: int = 120,
        region_padding: int = 120,
        merge_gap: int = 700,
        max_region_height: int = 3500,
        max_regions: int = 4,
    ):
        self.languages = languages or ["ko", "en"]

        if gpu is None:
            gpu = torch.cuda.is_available()

        self.gpu = gpu

        self.scout_width = scout_width
        self.min_region_height = min_region_height
        self.region_padding = region_padding
        self.merge_gap = merge_gap
        self.max_region_height = max_region_height
        self.max_regions = max_regions

        print(
            f"[LongImageOCR] loading EasyOCR "
            f"languages={self.languages}, gpu={self.gpu}"
        )

        start = time.perf_counter()

        self.reader = easyocr.Reader(
            self.languages,
            gpu=self.gpu,
        )

        elapsed = time.perf_counter() - start

        print(
            f"[LongImageOCR] loaded in {elapsed:.2f}s"
        )

    # --------------------------------------------------
    # Image load
    # --------------------------------------------------

    def _load_image_from_url(
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
            BytesIO(response.content)
        ).convert("RGB")

    # --------------------------------------------------
    # Scout image
    # --------------------------------------------------

    def _make_scout_image(
        self,
        image: Image.Image,
    ) -> tuple[np.ndarray, float]:

        width, height = image.size

        if width <= self.scout_width:
            scale = 1.0
            scout = image

        else:
            scale = (
                self.scout_width
                / width
            )

            scout_height = int(
                height * scale
            )

            scout = image.resize(
                (
                    self.scout_width,
                    scout_height,
                )
            )

        return (
            np.array(scout),
            scale,
        )

    # --------------------------------------------------
    # Detect rough text regions
    # --------------------------------------------------

    def _detect_text_regions(
        self,
        image: Image.Image,
    ) -> list[tuple[int, int]]:

        scout_np, scale = (
            self._make_scout_image(
                image
            )
        )

        gray = cv2.cvtColor(
            scout_np,
            cv2.COLOR_RGB2GRAY,
        )

        blurred = cv2.GaussianBlur(
            gray,
            (3, 3),
            0,
        )

        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            21,
            9,
        )

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (15, 3),
        )

        morph = cv2.morphologyEx(
            binary,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=1,
        )

        contours, _ = cv2.findContours(
            morph,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        scout_regions = []

        for contour in contours:

            x, y, w, h = (
                cv2.boundingRect(
                    contour
                )
            )

            # 너무 작은 noise 제거
            if w < 40:
                continue

            if h < 8:
                continue

            if (
                w
                < scout_np.shape[1] * 0.12
            ):
                continue

            scout_regions.append(
                (
                    y,
                    y + h,
                )
            )

        if not scout_regions:
            return []

        scout_regions.sort(
            key=lambda item: item[0]
        )

        # ----------------------------------
        # merge nearby y regions
        # ----------------------------------

        merged = []

        scout_merge_gap = max(
            10,
            int(
                self.merge_gap * scale
            ),
        )

        for start, end in scout_regions:

            if not merged:
                merged.append(
                    [start, end]
                )
                continue

            prev = merged[-1]

            gap = (
                start
                - prev[1]
            )

            if gap <= scout_merge_gap:
                prev[1] = max(
                    prev[1],
                    end,
                )
            else:
                merged.append(
                    [start, end]
                )

        # ----------------------------------
        # restore original coordinates
        # ----------------------------------

        image_height = image.size[1]

        original_regions = []

        for start, end in merged:

            y_start = int(
                start / scale
            )

            y_end = int(
                end / scale
            )

            y_start = max(
                0,
                y_start
                - self.region_padding,
            )

            y_end = min(
                image_height,
                y_end
                + self.region_padding,
            )

            if (
                y_end - y_start
                < self.min_region_height
            ):
                continue

            original_regions.append(
                (
                    y_start,
                    y_end,
                )
            )

        return original_regions

    # --------------------------------------------------
    # Split oversized region
    # --------------------------------------------------

    def _split_large_regions(
        self,
        regions: list[
            tuple[int, int]
        ],
    ) -> list[tuple[int, int]]:

        output = []

        for y_start, y_end in regions:

            height = (
                y_end - y_start
            )

            if height <= self.max_region_height:

                output.append(
                    (
                        y_start,
                        y_end,
                    )
                )

                continue

            current = y_start

            while current < y_end:

                end = min(
                    current
                    + self.max_region_height,
                    y_end,
                )

                output.append(
                    (
                        current,
                        end,
                    )
                )

                current = end

        return output

    # --------------------------------------------------
    # Limit region count
    # --------------------------------------------------

    def _limit_regions(
        self,
        regions: list[
            tuple[int, int]
        ],
    ) -> list[tuple[int, int]]:

        if len(regions) <= self.max_regions:
            return regions

        # 넓은 영역 우선
        ranked = sorted(
            regions,
            key=lambda region: (
                region[1]
                - region[0]
            ),
            reverse=True,
        )

        selected = ranked[
            : self.max_regions
        ]

        # 다시 위 -> 아래 순서
        selected.sort(
            key=lambda region: (
                region[0]
            )
        )

        return selected

    # --------------------------------------------------
    # OCR one region
    # --------------------------------------------------

    def _ocr_region(
        self,
        image: Image.Image,
        y_start: int,
        y_end: int,
        region_index: int,
        min_confidence: float,
    ) -> list[dict]:

        crop = image.crop(
            (
                0,
                y_start,
                image.size[0],
                y_end,
            )
        )

        crop_np = np.array(
            crop
        )

        results = self.reader.readtext(
            crop_np,
            detail=1,
            paragraph=False,
            canvas_size=2560,
            mag_ratio=1.0,
        )

        blocks = []

        for bbox, text, confidence in results:

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

            y_min_local = min(
                y_values
            )

            y_max_local = max(
                y_values
            )

            y_min_global = (
                y_min_local
                + y_start
            )

            y_max_global = (
                y_max_local
                + y_start
            )

            blocks.append(
                {
                    "text": text,

                    "confidence": round(
                        confidence,
                        4,
                    ),

                    "region_index": (
                        region_index
                    ),

                    "bbox": {
                        "x_min": round(
                            x_min,
                            2,
                        ),

                        "y_min": round(
                            y_min_global,
                            2,
                        ),

                        "x_max": round(
                            x_max,
                            2,
                        ),

                        "y_max": round(
                            y_max_global,
                            2,
                        ),
                    },

                    "center": {
                        "x": round(
                            (
                                x_min
                                + x_max
                            )
                            / 2,
                            2,
                        ),

                        "y": round(
                            (
                                y_min_global
                                + y_max_global
                            )
                            / 2,
                            2,
                        ),
                    },
                }
            )

        return blocks

    # --------------------------------------------------
    # Deduplicate OCR blocks
    # --------------------------------------------------

    def _dedupe_blocks(
        self,
        blocks: list[dict],
    ) -> list[dict]:

        if not blocks:
            return []

        blocks.sort(
            key=lambda item: (
                item["center"]["y"],
                item["center"]["x"],
            )
        )

        deduped = []

        for block in blocks:

            normalized_text = (
                block["text"]
                .strip()
                .lower()
            )

            duplicate = False

            for existing in deduped[-10:]:

                existing_text = (
                    existing["text"]
                    .strip()
                    .lower()
                )

                if (
                    normalized_text
                    != existing_text
                ):
                    continue

                y_diff = abs(
                    block["center"]["y"]
                    - existing["center"]["y"]
                )

                if y_diff <= 250:
                    duplicate = True
                    break

            if not duplicate:
                deduped.append(
                    block
                )

        return deduped

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def extract(
        self,
        image_url: str,
        min_confidence: float = 0.25,
    ) -> dict:

        total_start = (
            time.perf_counter()
        )

        # ----------------------------------
        # load
        # ----------------------------------

        load_start = (
            time.perf_counter()
        )

        image = (
            self._load_image_from_url(
                image_url
            )
        )

        load_elapsed = (
            time.perf_counter()
            - load_start
        )

        width, height = image.size

        # ----------------------------------
        # scout
        # ----------------------------------

        scout_start = (
            time.perf_counter()
        )

        regions = (
            self._detect_text_regions(
                image
            )
        )

        regions = (
            self._split_large_regions(
                regions
            )
        )

        regions = (
            self._limit_regions(
                regions
            )
        )

        scout_elapsed = (
            time.perf_counter()
            - scout_start
        )

        print(
            f"[LongImageOCR] "
            f"{width}x{height}"
        )

        print(
            f"[LongImageOCR] "
            f"text regions="
            f"{len(regions)} "
            f"scout="
            f"{scout_elapsed * 1000:.1f}ms"
        )

        # ----------------------------------
        # OCR
        # ----------------------------------

        ocr_start = (
            time.perf_counter()
        )

        all_blocks = []

        for position, (
            y_start,
            y_end,
        ) in enumerate(
            regions,
            start=1,
        ):

            region_start = (
                time.perf_counter()
            )

            print(
                f"[LongImageOCR] "
                f"region "
                f"{position}/"
                f"{len(regions)} "
                f"y={y_start}"
                f"~{y_end}"
            )

            blocks = (
                self._ocr_region(
                    image=image,
                    y_start=y_start,
                    y_end=y_end,
                    region_index=(
                        position - 1
                    ),
                    min_confidence=(
                        min_confidence
                    ),
                )
            )

            elapsed = (
                time.perf_counter()
                - region_start
            )

            print(
                f"[LongImageOCR] "
                f"OCR done: "
                f"{len(blocks)} blocks, "
                f"{elapsed:.2f}s"
            )

            all_blocks.extend(
                blocks
            )

        ocr_elapsed = (
            time.perf_counter()
            - ocr_start
        )

        # ----------------------------------
        # dedupe
        # ----------------------------------

        blocks = (
            self._dedupe_blocks(
                all_blocks
            )
        )

        raw_text = "\n".join(
            block["text"]
            for block
            in blocks
        )

        total_elapsed = (
            time.perf_counter()
            - total_start
        )

        return {
            "image_url": (
                image_url
            ),

            "image_size": {
                "width": width,
                "height": height,
            },

            "region_count": (
                len(regions)
            ),

            "regions": [
                {
                    "y_start": (
                        y_start
                    ),
                    "y_end": (
                        y_end
                    ),
                    "height": (
                        y_end
                        - y_start
                    ),
                }
                for y_start, y_end
                in regions
            ],

            "block_count": (
                len(blocks)
            ),

            "raw_text": (
                raw_text
            ),

            "blocks": (
                blocks
            ),

            "timing": {
                "image_load_ms": round(
                    load_elapsed
                    * 1000,
                    2,
                ),

                "scout_ms": round(
                    scout_elapsed
                    * 1000,
                    2,
                ),

                "ocr_ms": round(
                    ocr_elapsed
                    * 1000,
                    2,
                ),

                "total_ms": round(
                    total_elapsed
                    * 1000,
                    2,
                ),
            },
        }