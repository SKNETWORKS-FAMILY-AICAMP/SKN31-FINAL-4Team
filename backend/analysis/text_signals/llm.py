from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from .prompts import RESPONSE_SCHEMA, SYSTEM_PROMPT


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0


class TextSignalLLMError(RuntimeError):
    pass


def _output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    parts: list[str] = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"}:
                parts.append(str(content.get("text") or ""))
    return "".join(parts).strip()


class OpenAITextSignalClient:
    """Responses API의 구조화 출력만 사용하는 작은 클라이언트."""

    def __init__(self):
        # ★ 2026-09-20 — 챗봇(OPENAI_API_KEY)과 키를 나눈다. 리뷰·댓글 분석은 이 키만 쓴다.
        #   챗봇 키로 몰래 넘어가지 않도록 OPENAI_API_KEY 로 대신하지 않는다.
        self.api_key = (os.getenv("FEEDIT_TEXT_OPENAI_API_KEY") or "").strip()
        self.base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("FEEDIT_TEXT_LLM_MODEL", "gpt-6-luna")
        self.effort = os.getenv("FEEDIT_TEXT_LLM_EFFORT", "low")
        self.timeout = int(os.getenv("FEEDIT_TEXT_LLM_TIMEOUT", "90"))
        self.max_output_tokens = int(os.getenv("FEEDIT_TEXT_LLM_MAX_OUTPUT_TOKENS", "12000"))
        if not self.api_key:
            raise TextSignalLLMError("FEEDIT_TEXT_OPENAI_API_KEY가 없습니다 (리뷰·댓글 분석 전용 키).")

    def analyze(
        self,
        documents: list[dict[str, Any]],
        *,
        dictionary_text: str,
    ) -> tuple[list[dict], LLMUsage]:
        body = {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": self.effort},
            "max_output_tokens": self.max_output_tokens,
            "instructions": SYSTEM_PROMPT + "\n\n[표준 사전]\n" + dictionary_text,
            "input": json.dumps({"documents": documents}, ensure_ascii=False),
            "text": {"format": RESPONSE_SCHEMA},
        }

        last_error = ""
        for attempt in range(3):
            try:
                response = requests.post(
                    f"{self.base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = type(exc).__name__
                time.sleep(2 * (attempt + 1))
                continue

            if response.status_code >= 400:
                code = ""
                try:
                    code = str(((response.json().get("error") or {}).get("code") or ""))[:50]
                except ValueError:
                    pass
                last_error = f"HTTP {response.status_code}" + (f" ({code})" if code else "")
                if response.status_code in {408, 409, 429} or response.status_code >= 500:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise TextSignalLLMError(last_error)

            envelope = response.json()
            try:
                parsed = json.loads(_output_text(envelope))
            except (TypeError, ValueError) as exc:
                raise TextSignalLLMError("구조화 출력 JSON을 읽을 수 없습니다.") from exc

            usage = envelope.get("usage") or {}
            details = usage.get("input_tokens_details") or {}
            return list(parsed.get("documents") or []), LLMUsage(
                input_tokens=int(usage.get("input_tokens") or 0),
                cached_tokens=int(details.get("cached_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            )

        raise TextSignalLLMError(last_error or "LLM 호출 실패")
