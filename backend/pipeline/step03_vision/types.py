from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisionPrediction:
    label: str
    score: float
    model_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score": self.score,
            "model_version": self.model_version,
        }
