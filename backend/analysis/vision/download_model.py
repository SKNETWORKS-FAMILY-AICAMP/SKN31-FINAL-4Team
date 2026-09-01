from pathlib import Path

from huggingface_hub import hf_hub_download


BASE_DIR = Path(__file__).resolve().parent

MODEL_DIR = BASE_DIR / "models" / "results"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


model_path = hf_hub_download(
    repo_id="louisJLN/yolo8-fashionpedia",
    filename="results/yolov8n-fashionpedia-1.onnx",
    local_dir=BASE_DIR / "models",
)

print("download complete")
print(model_path)