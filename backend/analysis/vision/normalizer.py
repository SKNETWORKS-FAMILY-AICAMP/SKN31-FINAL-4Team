# backend/analysis/vision/normalizer.py

import time
from typing import Optional

import imagehash
from PIL import Image

from .category_map import SUPPORTED_CATEGORIES
from .detector import FashionDetector
from .schemas import CropCandidate, Detection, NormalizeResult
from .selector import (
    compute_rank_score,
    deduplicate_by_phash,
    filter_small_detections,
    save_crop,
)
from .utils import (
    add_padding,
    clamp_detection,
    load_image_from_url,
    nms,
    restore_coordinates,
    split_vertical_image,
)


class ProductImageNormalizer:
    """
    상품 상세 이미지 정규화 파이프라인

    image_url
        ↓
    이미지 다운로드
        ↓
    긴 이미지면 vertical slicing
        ↓
    Fashion YOLO detection
        ↓
    Fashionpedia label → FEEDIT 대분류
        ↓
    상품 category와 일치하는 bbox만 유지
        ↓
    작은 bbox 제거
        ↓
    NMS
        ↓
    padding
        ↓
    crop 저장
        ↓
    pHash 중복 제거
        ↓
    Top-N 선정
    """

    def __init__(
        self,
        detector: FashionDetector,
        long_image_threshold: int = 1600,
        slice_height: int = 1280,
        overlap: int = 128,
        box_threshold: float = 0.25,
        nms_iou_threshold: float = 0.45,
        min_area_ratio: float = 0.01,
        min_width: int = 80,
        min_height: int = 80,
        crop_pad_ratio: float = 0.04,
        duplicate_hash_distance: int = 6,
        top_n: int = 5,
    ):
        self.detector = detector

        self.long_image_threshold = long_image_threshold
        self.slice_height = slice_height
        self.overlap = overlap

        self.box_threshold = box_threshold
        self.nms_iou_threshold = nms_iou_threshold

        self.min_area_ratio = min_area_ratio
        self.min_width = min_width
        self.min_height = min_height

        self.crop_pad_ratio = crop_pad_ratio
        self.duplicate_hash_distance = duplicate_hash_distance

        self.top_n = top_n

    def _detect_all(
        self,
        image: Image.Image,
        target_category: str,
    ) -> list[Detection]:
        """
        긴 이미지는 slice batch inference 후
        bbox 좌표를 원본 이미지 기준으로 복구한다.
        """

        width, height = image.size

        all_detections: list[Detection] = []

        # =====================================================
        # 긴 이미지
        # =====================================================
        if height > self.long_image_threshold:

            slices = split_vertical_image(
                image=image,
                slice_height=self.slice_height,
                overlap=self.overlap,
            )

            print(f"[YOLO] slices            : {len(slices)}")

            slice_images = [
                item["image"]
                for item in slices
            ]

            batch_results = self.detector.detect_batch(
                images=slice_images,
                target_category=target_category,
                confidence=self.box_threshold,
            )

            for slice_item, detections in zip(
                slices,
                batch_results,
            ):
                offset_y = slice_item["offset_y"]

                for detection in detections:

                    restored = restore_coordinates(
                        detection=detection,
                        offset_y=offset_y,
                    )

                    restored = clamp_detection(
                        d=restored,
                        image_width=width,
                        image_height=height,
                    )

                    all_detections.append(restored)

        # =====================================================
        # 일반 이미지
        # =====================================================
        else:

            print("[YOLO] slices            : 1")

            detections = self.detector.detect(
                image=image,
                target_category=target_category,
                confidence=self.box_threshold,
                source_slice_index=0,
            )

            for detection in detections:

                detection = clamp_detection(
                    d=detection,
                    image_width=width,
                    image_height=height,
                )

                all_detections.append(detection)

        return all_detections

    def normalize(
        self,
        image_url: str,
        category: str,
        output_dir: str,
        product_id: Optional[int] = None,
    ) -> NormalizeResult:

        total_start = time.perf_counter()

        target_category = category.upper().strip()

        print()
        print("==========================================")
        print("[Normalizer] START")
        print(f"[Normalizer] product_id : {product_id}")
        print(f"[Normalizer] category   : {target_category}")
        print("==========================================")

        # =====================================================
        # 0. Category validation
        # =====================================================

        if target_category not in SUPPORTED_CATEGORIES:
            raise ValueError(
                f"Unsupported category: {category}. "
                f"Supported: {sorted(SUPPORTED_CATEGORIES)}"
            )

        # =====================================================
        # 1. 이미지 다운로드
        # =====================================================

        step_start = time.perf_counter()

        image = load_image_from_url(image_url)
        image = image.convert("RGB")

        image_width, image_height = image.size

        print(
            f"[1] Image download      : "
            f"{time.perf_counter() - step_start:.3f} sec"
        )
        print(
            f"    Image size          : "
            f"{image_width} x {image_height}"
        )

        # =====================================================
        # 2. YOLO Detection
        # =====================================================

        step_start = time.perf_counter()

        raw_detections = self._detect_all(
            image=image,
            target_category=target_category,
        )

        detection_time = (
            time.perf_counter() - step_start
        )

        raw_detection_count = len(raw_detections)

        print(
            f"[2] YOLO detection      : "
            f"{detection_time:.3f} sec"
        )
        print(
            f"    Raw detections      : "
            f"{raw_detection_count}"
        )

        # detection 없음
        if not raw_detections:

            total_elapsed = (
                time.perf_counter()
                - total_start
            )

            print("------------------------------------------")
            print(
                f"[TOTAL]                 : "
                f"{total_elapsed:.3f} sec"
            )
            print("[RESULT] final crops    : 0")
            print("==========================================")
            print()

            return NormalizeResult(
                product_id=product_id,
                source_image_url=image_url,
                category=target_category,
                image_width=image_width,
                image_height=image_height,
                raw_detection_count=0,
                final_crop_count=0,
                crops=[],
            )

        # =====================================================
        # 3. 작은 bbox 제거
        # =====================================================

        step_start = time.perf_counter()

        filtered_detections = filter_small_detections(
            detections=raw_detections,
            image_width=image_width,
            image_height=image_height,
            min_area_ratio=self.min_area_ratio,
            min_width=self.min_width,
            min_height=self.min_height,
        )

        print(
            f"[3] Small bbox filter   : "
            f"{time.perf_counter() - step_start:.3f} sec"
        )
        print(
            f"    Remaining           : "
            f"{len(filtered_detections)}"
        )

        if not filtered_detections:

            total_elapsed = (
                time.perf_counter()
                - total_start
            )

            print("------------------------------------------")
            print(
                f"[TOTAL]                 : "
                f"{total_elapsed:.3f} sec"
            )
            print("[RESULT] final crops    : 0")
            print("==========================================")
            print()

            return NormalizeResult(
                product_id=product_id,
                source_image_url=image_url,
                category=target_category,
                image_width=image_width,
                image_height=image_height,
                raw_detection_count=raw_detection_count,
                final_crop_count=0,
                crops=[],
            )

        # =====================================================
        # 4. NMS
        # =====================================================

        step_start = time.perf_counter()

        filtered_detections = nms(
            detections=filtered_detections,
            iou_threshold=self.nms_iou_threshold,
        )

        print(
            f"[4] NMS                 : "
            f"{time.perf_counter() - step_start:.3f} sec"
        )
        print(
            f"    Remaining           : "
            f"{len(filtered_detections)}"
        )

        # =====================================================
        # 5. Padding
        # =====================================================

        step_start = time.perf_counter()

        padded_detections: list[Detection] = []

        for detection in filtered_detections:

            padded = add_padding(
                d=detection,
                image_width=image_width,
                image_height=image_height,
                pad_ratio=self.crop_pad_ratio,
            )

            padded_detections.append(padded)

        print(
            f"[5] BBox padding        : "
            f"{time.perf_counter() - step_start:.3f} sec"
        )

        # =====================================================
        # 6. Crop 저장 + pHash 생성
        # =====================================================

        step_start = time.perf_counter()

        candidates: list[CropCandidate] = []

        image_area = max(
            1,
            image_width * image_height,
        )

        for detection in padded_detections:

            crop_path, crop_image = save_crop(
                image=image,
                detection=detection,
                output_dir=output_dir,
            )

            rank_score = compute_rank_score(
                detection=detection,
                image_width=image_width,
                image_height=image_height,
            )

            hash_value = str(
                imagehash.phash(crop_image)
            )

            area_ratio = (
                detection.area
                / image_area
            )

            candidate = CropCandidate(
                path=crop_path,
                label=detection.label,
                normalized_category=(
                    detection.normalized_category
                ),
                score=detection.score,
                bbox=detection.as_bbox(),
                width=detection.width,
                height=detection.height,
                area_ratio=area_ratio,
                hash_value=hash_value,
                rank_score=rank_score,
            )

            candidates.append(candidate)

        print(
            f"[6] Crop + hash         : "
            f"{time.perf_counter() - step_start:.3f} sec"
        )
        print(
            f"    Crop candidates     : "
            f"{len(candidates)}"
        )

        # =====================================================
        # 7. pHash 중복 제거
        # =====================================================

        step_start = time.perf_counter()

        unique_candidates = deduplicate_by_phash(
            candidates=candidates,
            distance_threshold=(
                self.duplicate_hash_distance
            ),
        )

        print(
            f"[7] Duplicate removal   : "
            f"{time.perf_counter() - step_start:.3f} sec"
        )
        print(
            f"    Unique candidates   : "
            f"{len(unique_candidates)}"
        )

        # =====================================================
        # 8. Top-N ranking
        # =====================================================

        step_start = time.perf_counter()

        unique_candidates.sort(
            key=lambda x: x.rank_score,
            reverse=True,
        )

        final_candidates = (
            unique_candidates[:self.top_n]
        )

        print(
            f"[8] Top-N ranking       : "
            f"{time.perf_counter() - step_start:.3f} sec"
        )

        # =====================================================
        # TOTAL
        # =====================================================

        total_elapsed = (
            time.perf_counter()
            - total_start
        )

        print("------------------------------------------")
        print(
            f"[TOTAL]                 : "
            f"{total_elapsed:.3f} sec"
        )
        print(
            f"[RESULT] final crops    : "
            f"{len(final_candidates)}"
        )
        print("==========================================")
        print()

        return NormalizeResult(
            product_id=product_id,
            source_image_url=image_url,
            category=target_category,
            image_width=image_width,
            image_height=image_height,
            raw_detection_count=raw_detection_count,
            final_crop_count=len(final_candidates),
            crops=final_candidates,
        )