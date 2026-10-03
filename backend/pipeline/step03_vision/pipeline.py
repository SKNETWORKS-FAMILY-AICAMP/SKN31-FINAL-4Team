from __future__ import annotations

from apps.core.models import (
    DictionaryTerm,
    ProductSource,
    ProductTerm,
)

from .config import (
    MIN_CONFIDENCE,
    MODEL_VERSION,
    STYLE_LABELS,
)
from .image_loader import get_product_image_url
from .predictor import FashionStylePredictor
from .writer import save_vision_style


class ProductVisionPipeline:
    """
    FEEDIT STYLE fallback pipeline.

    실행 대상:
    - STEP02 텍스트 분석 완료
    - ProductTerm STYLE이 하나도 없는 ProductSource

    결과:
    - FashionSigLIP2 + LoRA Top1 하나
    - DictionaryTerm(STYLE) 검증
    - ProductTerm HAS_STYLE 추가

    기존 STYLE이 있으면 모델 추론 자체를 하지 않는다.
    """

    def __init__(
        self,
        *,
        min_confidence: float = MIN_CONFIDENCE,
    ):
        self.min_confidence = float(
            min_confidence
        )

        self._validate_style_dictionary()

        # 실제 모델은 첫 추론 때 singleton으로 로드.
        self._predictor = None

    @property
    def predictor(self) -> FashionStylePredictor:
        if self._predictor is None:
            self._predictor = (
                FashionStylePredictor()
            )

        return self._predictor

    @staticmethod
    def _validate_style_dictionary() -> None:
        existing = set(
            DictionaryTerm.objects
            .filter(
                term_type="STYLE",
                status="ACTIVE",
                canonical_name__in=STYLE_LABELS,
            )
            .values_list(
                "canonical_name",
                flat=True,
            )
        )

        missing = [
            label
            for label in STYLE_LABELS
            if label not in existing
        ]

        if missing:
            raise RuntimeError(
                "Vision STYLE DictionaryTerm 누락: "
                + ", ".join(missing)
            )

    @staticmethod
    def has_style(
        product_source_id: int,
    ) -> bool:
        return (
            ProductTerm.objects
            .filter(
                product_source_id=product_source_id,
                term__term_type="STYLE",
            )
            .exists()
        )

    def run(
        self,
        product_source: ProductSource | int,
        *,
        save: bool = True,
    ) -> dict:
        if isinstance(product_source, int):
            product_source = (
                ProductSource.objects
                .get(id=product_source)
            )

        ps_id = product_source.id

        # 가장 먼저 검사해서 STYLE 있는 상품은
        # GPU/model/image download를 전혀 사용하지 않는다.
        if self.has_style(ps_id):
            return {
                "status": "SKIPPED",
                "reason": "STYLE_ALREADY_EXISTS",
                "product_source_id": ps_id,
            }

        image_url = get_product_image_url(
            product_source
        )

        if not image_url:
            return {
                "status": "SKIPPED",
                "reason": "NO_IMAGE",
                "product_source_id": ps_id,
            }

        try:
            prediction = (
                self.predictor.predict(
                    image_url
                )
            )
        except Exception as exc:
            return {
                "status": "FAILED",
                "reason": "VISION_FAILED",
                "product_source_id": ps_id,
                "image_url": image_url,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

        result = {
            "status": "PREDICTED",
            "product_source_id": ps_id,
            "image_url": image_url,
            "style": prediction.label,
            "score": prediction.score,
            "model": MODEL_VERSION,
        }

        if (
            prediction.score
            < self.min_confidence
        ):
            result.update({
                "status": "SKIPPED",
                "reason": "LOW_CONFIDENCE",
            })

            return result

        if not save:
            return result

        saved = save_vision_style(
            product_source_id=ps_id,
            style_label=prediction.label,
        )

        result.update(saved)

        result["score"] = prediction.score
        result["model"] = MODEL_VERSION
        result["image_url"] = image_url

        return result
