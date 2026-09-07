# backend/analysis/vision/schemas.py

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Detection:
    label: str
    normalized_category: Optional[str]

    score: float

    x1: int
    y1: int
    x2: int
    y2: int

    source_slice_index: Optional[int] = None

    @property
    def width(self) -> int:
        return max(
            0,
            self.x2 - self.x1,
        )

    @property
    def height(self) -> int:
        return max(
            0,
            self.y2 - self.y1,
        )

    @property
    def area(self) -> int:
        return (
            self.width
            * self.height
        )

    def as_bbox(self) -> list[int]:
        return [
            self.x1,
            self.y1,
            self.x2,
            self.y2,
        ]


@dataclass
class CropCandidate:
    path: str

    label: str
    normalized_category: Optional[str]

    score: float

    bbox: list[int]

    width: int
    height: int

    area_ratio: float

    hash_value: str

    rank_score: float


@dataclass
class NormalizeResult:
    product_id: Optional[int]

    source_image_url: str

    category: str

    image_width: int
    image_height: int

    raw_detection_count: int
    final_crop_count: int

    crops: list[CropCandidate] = field(
        default_factory=list
    )