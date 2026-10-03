from __future__ import annotations

from .config import (
    MODEL_VERSION,
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from .image_loader import download_rgb_image
from .model_loader import get_fashion_style_model
from .types import VisionPrediction


class FashionStylePredictor:
    def __init__(self):
        self.model = get_fashion_style_model()

    def predict(
        self,
        image_url: str,
    ) -> VisionPrediction:
        image = download_rgb_image(
            image_url,
            timeout=REQUEST_TIMEOUT,
            user_agent=USER_AGENT,
        )

        label, score = (
            self.model.predict_top1(image)
        )

        return VisionPrediction(
            label=label,
            score=score,
            model_version=MODEL_VERSION,
        )
