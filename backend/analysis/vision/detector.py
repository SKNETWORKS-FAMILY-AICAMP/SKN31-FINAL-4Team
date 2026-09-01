# backend/analysis/vision/detector.py

from pathlib import Path

from PIL import Image
from ultralytics import YOLO

from .schemas import Detection
from .category_map import normalize_fashion_label


class FashionDetector:

    def __init__(
        self,
        model_path: str,
        device: str | int | None = None,
        imgsz: int = 640,
    ):
        model_path = Path(model_path)

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}"
            )

        self.model = YOLO(
            str(model_path)
        )

        self.device = device
        self.imgsz = imgsz

        print()
        print("===== FashionDetector =====")
        print("model :", model_path)
        print("device:", device)
        print("imgsz :", imgsz)
        print("===========================")
        print()

    def detect(
        self,
        image: Image.Image,
        target_category: str | None = None,
        confidence: float = 0.25,
        source_slice_index: int | None = None,
    ) -> list[Detection]:

        results = self.model.predict(
            source=image,
            conf=confidence,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )

        detections: list[Detection] = []

        for result in results:

            if result.boxes is None:
                continue

            names = result.names

            for box in result.boxes:

                class_id = int(
                    box.cls[0].item()
                )

                label = str(
                    names[class_id]
                ).strip().lower()

                score = float(
                    box.conf[0].item()
                )

                # -------------------------
                # Fashionpedia → FEEDIT
                # -------------------------

                normalized_category = (
                    normalize_fashion_label(
                        label
                    )
                )

                # FEEDIT에서 사용하지 않는 class
                if normalized_category is None:
                    continue

                # -------------------------
                # 상품 category filter
                # -------------------------

                if (
                    target_category
                    and normalized_category
                    != target_category.upper()
                ):
                    continue

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0].tolist(),
                )

                detections.append(
                    Detection(
                        label=label,
                        normalized_category=normalized_category,
                        score=score,
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        source_slice_index=source_slice_index,
                    )
                )

        return detections