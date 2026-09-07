from pathlib import Path
from pprint import pprint

from analysis.vision.detector import (
    FashionDetector,
)
from analysis.vision.normalizer import (
    ProductImageNormalizer,
)


BASE_DIR = Path(__file__).resolve().parent

MODEL_PATH = (
    BASE_DIR
    / "models"
    / "results"
    / "yolov8n-fashionpedia-1.onnx"
)


IMAGE_URL = "https://image.msscdn.net/thumbnails/images/goods_img/20260806/7011611/7011611_17877304589326_big.jpg?w=1200"


def main():

    detector = FashionDetector(
        model_path=str(MODEL_PATH),
        device="cpu",
        imgsz=640,
    )

    normalizer = ProductImageNormalizer(
        detector=detector,

        slice_height=1280,
        overlap=128,

        box_threshold=0.25,

        nms_iou_threshold=0.45,

        min_area_ratio=0.01,

        crop_pad_ratio=0.04,

        top_n=5,
    )

    result = normalizer.normalize(
        image_url=IMAGE_URL,

        # ===================
        # DB 상품 대분류
        # ===================
        category="TOP",

        output_dir="./data/product_crops",

        product_id=1234,
    )

    pprint(result)


if __name__ == "__main__":
    main()