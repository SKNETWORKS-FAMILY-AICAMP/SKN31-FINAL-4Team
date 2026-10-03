from __future__ import annotations

from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
ASSET_DIR = THIS_DIR / "assets"

MODEL_ID = "srpone/zooclaw-fashionsiglip2"
ADAPTER_DIR = ASSET_DIR
SCALE_PATH = ASSET_DIR / "scale.pt"
PROMPTS_PATH = ASSET_DIR / "style_prompts_en.json"

MODEL_VERSION = "fashionsiglip2_lora_v11_en"

STYLE_LABELS = (
    "고프코어",
    "그런지",
    "놈코어",
    "바이크코어",
    "블록코어",
    "스트릿웨어",
    "아메카지",
    "애슬레저",
    "클래식",
    "페미닌",
)

RELATION_TYPE = "HAS_STYLE"

# 0.0이면 Top1을 항상 채택.
# 나중에 검증 후 threshold를 올리고 싶으면 이 값만 변경.
MIN_CONFIDENCE = 0.0

REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0"
