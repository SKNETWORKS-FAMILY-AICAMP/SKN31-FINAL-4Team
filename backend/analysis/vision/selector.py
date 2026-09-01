# analysis/vision/selector.py
from pathlib import Path
from uuid import uuid4

import imagehash
from PIL import Image

from .schemas import Detection, CropCandidate


def filter_small_detections(
    detections: list[Detection],
    image_width: int,
    image_height: int,
    min_area_ratio: float = 0.02,
    min_width: int = 80,
    min_height: int = 80,
) -> list[Detection]:
    image_area = image_width * image_height
    results = []

    for d in detections:
        if d.width < min_width or d.height < min_height:
            continue
        if image_area > 0 and (d.area / image_area) < min_area_ratio:
            continue
        results.append(d)

    return results


def compute_rank_score(
    detection: Detection,
    image_width: int,
    image_height: int,
) -> float:
    image_area = max(1, image_width * image_height)
    area_ratio = detection.area / image_area

    center_x = (detection.x1 + detection.x2) / 2
    center_y = (detection.y1 + detection.y2) / 2
    image_center_x = image_width / 2
    image_center_y = image_height / 2

    dx = abs(center_x - image_center_x) / max(1, image_width / 2)
    dy = abs(center_y - image_center_y) / max(1, image_height / 2)

    center_score = 1.0 - min(1.0, (dx + dy) / 2)

    score = (
        detection.score * 0.65
        + area_ratio * 0.25
        + center_score * 0.10
    )
    return score


def save_crop(
    image: Image.Image,
    detection: Detection,
    output_dir: str,
) -> tuple[str, Image.Image]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    crop = image.crop((detection.x1, detection.y1, detection.x2, detection.y2))
    filename = f"{uuid4().hex}.jpg"
    path = output_path / filename
    crop.save(path, format="JPEG", quality=95)

    return str(path), crop


def deduplicate_by_phash(
    candidates: list[CropCandidate],
    distance_threshold: int = 6,
) -> list[CropCandidate]:
    unique: list[CropCandidate] = []

    for candidate in candidates:
        current_hash = imagehash.hex_to_hash(candidate.hash_value)

        duplicated = False
        for kept in unique:
            kept_hash = imagehash.hex_to_hash(kept.hash_value)
            if current_hash - kept_hash <= distance_threshold:
                duplicated = True
                if candidate.rank_score > kept.rank_score:
                    unique.remove(kept)
                    unique.append(candidate)
                break

        if not duplicated:
            unique.append(candidate)

    unique.sort(key=lambda x: x.rank_score, reverse=True)
    return unique