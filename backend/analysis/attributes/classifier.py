# backend/analysis/attributes/classifier.py
from __future__ import annotations

from io import BytesIO
import time

import requests
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoModel, AutoProcessor

from analysis.attributes.prompts import (
    build_label_prompt,
    build_product_text,
)
from analysis.attributes.schemas import (
    ATTRIBUTE_WEIGHTS,
    MODEL_LABELS_V1,
)

MODEL_LABELS = MODEL_LABELS_V1
MODEL_NAME = "google/siglip2-base-patch16-224"


def load_image_from_url(
    image_url: str,
    timeout: int = 20,
) -> Image.Image:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        )
    }

    response = requests.get(
        image_url,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()

    return Image.open(BytesIO(response.content)).convert("RGB")


class FashionAttributeClassifier:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: str | None = None,
    ):
        if device:
            self.device = device
        elif torch.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"

        print(f"[AttributeClassifier] loading model: {model_name}")
        print(f"[AttributeClassifier] device: {self.device}")

        start = time.perf_counter()

        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

        elapsed = time.perf_counter() - start
        print(f"[AttributeClassifier] model loaded in {elapsed:.2f}s")

        self._label_embedding_cache: dict[
            str,
            tuple[list[str], torch.Tensor],
        ] = {}

    @staticmethod
    def _unwrap_features(outputs) -> torch.Tensor:
        """transformers 버전별 feature 반환형을 Tensor로 통일한다."""
        if isinstance(outputs, torch.Tensor):
            return outputs

        pooler_output = getattr(outputs, "pooler_output", None)
        if isinstance(pooler_output, torch.Tensor):
            return pooler_output

        image_embeds = getattr(outputs, "image_embeds", None)
        if isinstance(image_embeds, torch.Tensor):
            return image_embeds

        text_embeds = getattr(outputs, "text_embeds", None)
        if isinstance(text_embeds, torch.Tensor):
            return text_embeds

        last_hidden_state = getattr(outputs, "last_hidden_state", None)
        if isinstance(last_hidden_state, torch.Tensor):
            return last_hidden_state.mean(dim=1)

        raise TypeError(
            "Unsupported model feature output type: "
            f"{type(outputs).__name__}"
        )

    # --------------------------------------------------
    # Image embedding
    # --------------------------------------------------
    @torch.inference_mode()
    def _encode_image(
        self,
        image: Image.Image,
    ) -> torch.Tensor:
        inputs = self.processor(
            images=image,
            return_tensors="pt",
        )

        inputs = {
            key: value.to(self.device)
            for key, value in inputs.items()
        }

        outputs = self.model.get_image_features(**inputs)
        features = self._unwrap_features(outputs)

        return F.normalize(
            features,
            p=2,
            dim=-1,
        )

    # --------------------------------------------------
    # Text embedding
    # --------------------------------------------------
    @torch.inference_mode()
    def _encode_texts(
        self,
        texts: list[str],
    ) -> torch.Tensor:
        inputs = self.processor(
            text=texts,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )

        inputs = {
            key: value.to(self.device)
            for key, value in inputs.items()
        }

        outputs = self.model.get_text_features(**inputs)
        features = self._unwrap_features(outputs)

        return F.normalize(
            features,
            p=2,
            dim=-1,
        )

    # --------------------------------------------------
    # Label embeddings
    # --------------------------------------------------
    def _get_label_embeddings(
        self,
        attribute: str,
    ) -> tuple[list[str], torch.Tensor]:
        if attribute in self._label_embedding_cache:
            return self._label_embedding_cache[attribute]

        labels = MODEL_LABELS[attribute]
        prompts = [
            build_label_prompt(label)
            for label in labels
        ]

        embeddings = self._encode_texts(prompts)
        self._label_embedding_cache[attribute] = (
            labels,
            embeddings,
        )
        return labels, embeddings

    # --------------------------------------------------
    # One attribute
    # --------------------------------------------------
    def _predict_attribute(
        self,
        attribute: str,
        image_embedding: torch.Tensor,
        product_text_embedding: torch.Tensor,
        top_k: int = 3,
    ) -> list[dict]:
        labels, label_embeddings = self._get_label_embeddings(
            attribute
        )

        image_similarity = (
            image_embedding @ label_embeddings.T
        ).squeeze(0)

        text_similarity = (
            product_text_embedding @ label_embeddings.T
        ).squeeze(0)

        weights = ATTRIBUTE_WEIGHTS[attribute]
        combined = (
            image_similarity * weights["image"]
            + text_similarity * weights["text"]
        )

        # 확률값이 아니라 비교용 similarity score.
        normalized_score = (combined + 1) / 2

        top_k = min(top_k, len(labels))
        scores, indices = torch.topk(
            normalized_score,
            k=top_k,
        )

        results = []

        for score, index in zip(
            scores.tolist(),
            indices.tolist(),
        ):
            results.append(
                {
                    "label": labels[index],
                    "score": round(float(score), 4),
                    "image_score": round(
                        float((image_similarity[index] + 1) / 2),
                        4,
                    ),
                    "text_score": round(
                        float((text_similarity[index] + 1) / 2),
                        4,
                    ),
                }
            )

        return results

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------
    def predict(
        self,
        image_url: str,
        product_name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        top_k: int = 3,
    ) -> dict:
        total_start = time.perf_counter()

        image_start = time.perf_counter()
        image = load_image_from_url(image_url)
        image_load_elapsed = time.perf_counter() - image_start

        product_text = build_product_text(
            product_name=product_name,
            description=description,
            category=category,
            brand=brand,
        )

        if not product_text:
            product_text = "fashion product"

        encode_start = time.perf_counter()

        image_embedding = self._encode_image(image)
        product_text_embedding = self._encode_texts([product_text])

        encode_elapsed = time.perf_counter() - encode_start

        classify_start = time.perf_counter()
        attributes = {
            attribute: self._predict_attribute(
                attribute=attribute,
                image_embedding=image_embedding,
                product_text_embedding=product_text_embedding,
                top_k=top_k,
            )
            for attribute in MODEL_LABELS
        }
        classify_elapsed = time.perf_counter() - classify_start

        total_elapsed = time.perf_counter() - total_start

        return {
            "product": {
                "name": product_name,
                "category": category,
                "brand": brand,
                "image_url": image_url,
            },
            "attributes": attributes,
            "timing": {
                "image_load_ms": round(image_load_elapsed * 1000, 2),
                "encoding_ms": round(encode_elapsed * 1000, 2),
                "classification_ms": round(
                    classify_elapsed * 1000,
                    2,
                ),
                "total_ms": round(total_elapsed * 1000, 2),
            },
        }