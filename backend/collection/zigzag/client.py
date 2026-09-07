from __future__ import annotations

import logging
from typing import Any

import requests

from collection.common.http import DEFAULT_HEADERS

from .constants import (
    REQUEST_TIMEOUT,
    SEARCH_RESULT_API_URL,
    ZIGZAG_BASE_URL,
)
from .exceptions import ZigzagCollectError


logger = logging.getLogger(__name__)


class ZigzagClient:
    """
    ZIGZAG GraphQL HTTP client.

    책임:
    - HTTP 세션
    - GraphQL POST
    - HTTP/JSON/GraphQL 오류 처리

    하지 않는 일:
    - pagination
    - 상품 파싱
    - S3 저장
    - Django ORM
    """

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout or REQUEST_TIMEOUT
        self.session = session or requests.Session()

        self.session.headers.update(DEFAULT_HEADERS)
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Origin": ZIGZAG_BASE_URL,
                "Referer": f"{ZIGZAG_BASE_URL}/",
            }
        )

    def close(self) -> None:
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def post_graphql(
        self,
        *,
        query: str,
        variables: dict[str, Any],
        url: str = SEARCH_RESULT_API_URL,
    ) -> dict[str, Any]:
        response = None

        try:
            response = self.session.post(
                url,
                json={
                    "query": query,
                    "variables": variables,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            status_code = getattr(response, "status_code", None)
            body_preview = None

            if response is not None:
                try:
                    body_preview = response.text[:500]
                except Exception:
                    body_preview = None

            logger.exception(
                "ZIGZAG GraphQL request failed url=%s status=%s body=%r",
                url,
                status_code,
                body_preview,
            )

            raise ZigzagCollectError(
                "ZIGZAG GraphQL 요청 실패: "
                f"url={url} status={status_code} error={exc}"
            ) from exc

        try:
            body = response.json()

        except ValueError as exc:
            raise ZigzagCollectError(
                f"ZIGZAG JSON 응답 파싱 실패: {url}"
            ) from exc

        if not isinstance(body, dict):
            raise ZigzagCollectError(
                f"ZIGZAG GraphQL 응답이 object가 아닙니다: {url}"
            )

        errors = body.get("errors")

        if errors:
            raise ZigzagCollectError(
                f"ZIGZAG GraphQL 응답 에러: {errors}"
            )

        return body
