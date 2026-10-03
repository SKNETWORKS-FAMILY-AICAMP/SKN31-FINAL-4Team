from __future__ import annotations

import json
from functools import lru_cache

import torch
import torch.nn.functional as F
from peft import PeftModel
from transformers import AutoModel, AutoProcessor

from .config import (
    ADAPTER_DIR,
    MODEL_ID,
    PROMPTS_PATH,
    SCALE_PATH,
    STYLE_LABELS,
)


def _as_tensor(output):
    if torch.is_tensor(output):
        return output

    for key in (
        "pooler_output",
        "image_embeds",
        "text_embeds",
    ):
        value = getattr(output, key, None)

        if value is not None:
            return value

    raise TypeError(
        f"Unsupported model output: {type(output)!r}"
    )


class FashionStyleModel:
    """
    lastdance.ipynb의 LoRA(en) inference를 운영 코드로 옮긴 클래스.

    학습 노트북과 동일하게:
    - FashionSigLIP2 base
    - PEFT LoRA adapter
    - scale.pt의 log_scale
    - 영문 style description text embedding
    - normalized image/text embedding cosine logits
    - softmax Top1
    """

    def __init__(self):
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        else:
            self.device = torch.device("cpu")

        if not PROMPTS_PATH.exists():
            raise FileNotFoundError(
                "style_prompts_en.json이 없습니다. "
                "학습에 사용한 lora_pair_v11_en.csv로 "
                "build_prompts.py를 먼저 실행하세요."
            )

        with PROMPTS_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            prompt_map = json.load(file)

        missing = [
            label
            for label in STYLE_LABELS
            if not str(prompt_map.get(label) or "").strip()
        ]

        if missing:
            raise ValueError(
                "영문 style prompt 누락: "
                + ", ".join(missing)
            )

        self.labels = list(STYLE_LABELS)
        self.texts = [
            str(prompt_map[label]).strip()
            for label in self.labels
        ]

        self.processor = (
            AutoProcessor.from_pretrained(
                MODEL_ID
            )
        )

        base_model = AutoModel.from_pretrained(
            MODEL_ID
        )

        self.model = PeftModel.from_pretrained(
            base_model,
            str(ADAPTER_DIR),
        ).to(self.device).eval()

        scale_state = torch.load(
            SCALE_PATH,
            map_location=self.device,
        )

        self.log_scale = torch.tensor(
            float(scale_state["log_scale"]),
            device=self.device,
        )

        text_config = getattr(
            self.model.base_model.model.config,
            "text_config",
            None,
        )

        self.max_len = getattr(
            text_config,
            "max_position_embeddings",
            64,
        )

        image_processor = (
            self.processor.image_processor
        )

        self.mean = torch.tensor(
            image_processor.image_mean,
            device=self.device,
        ).view(1, 3, 1, 1)

        self.std = torch.tensor(
            image_processor.image_std,
            device=self.device,
        ).view(1, 3, 1, 1)

        # 운영에서는 고정된 10개 text embedding을
        # 상품마다 다시 계산하지 않는다.
        self.text_features = (
            self._encode_texts(self.texts)
        )

    @torch.no_grad()
    def _encode_texts(
        self,
        texts: list[str],
    ) -> torch.Tensor:
        tokens = self.processor.tokenizer(
            texts,
            padding="max_length",
            max_length=self.max_len,
            truncation=True,
            return_tensors="pt",
        ).to(self.device)

        output = self.model.get_text_features(
            **tokens
        )

        return F.normalize(
            _as_tensor(output).float(),
            dim=-1,
        )

    @torch.no_grad()
    def _encode_image(
        self,
        image,
    ) -> torch.Tensor:
        # 학습 notebook의 fetch()와 동일:
        # processor로 resize/crop만 수행하고
        # rescale/normalize는 직접 적용한다.
        pixel_values = (
            self.processor.image_processor(
                images=image,
                do_rescale=False,
                do_normalize=False,
                return_tensors="pt",
            )["pixel_values"]
            .to(self.device)
            .float()
        )

        pixel_values = (
            pixel_values / 255.0
            - self.mean
        ) / self.std

        output = self.model.get_image_features(
            pixel_values=pixel_values
        )

        return F.normalize(
            _as_tensor(output).float(),
            dim=-1,
        )

    @torch.no_grad()
    def predict_top1(
        self,
        image,
    ) -> tuple[str, float]:
        image_features = self._encode_image(
            image
        )

        logits = (
            self.log_scale.exp()
            * image_features
            @ self.text_features.T
        )

        probabilities = (
            logits.float()
            .softmax(dim=-1)[0]
        )

        index = int(
            probabilities.argmax().item()
        )

        return (
            self.labels[index],
            float(
                probabilities[index].item()
            ),
        )


@lru_cache(maxsize=1)
def get_fashion_style_model() -> FashionStyleModel:
    """
    프로세스당 모델 1회 로드.
    상품마다 모델을 다시 로드하지 않는다.
    """
    return FashionStyleModel()
