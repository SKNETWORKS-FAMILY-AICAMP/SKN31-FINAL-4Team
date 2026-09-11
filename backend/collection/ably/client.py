from __future__ import annotations

import os
from uuid import uuid4

import requests

from .constants import (
    ANONYMOUS_TOKEN_API_URL,
    ANONYMOUS_TOKEN_ENV,
    DEFAULT_HEADERS,
    DEVICE_ID_ENV,
    RANKING_FILTERS_API_URL,
    RANKING_GOODS_API_URL,
    REQUEST_TIMEOUT,
)
from .exceptions import AblyAuthenticationError, AblyCollectError


class AblyClient:
    """ABLY JSON API 전용 HTTP client.

    ABLY Web과 같이 익명 토큰이 없으면 공식 anonymous token API에서
    발급받는다. 환경변수 토큰은 선택적 override이며 오류 메시지나 로그에
    토큰과 device ID를 포함하지 않는다.
    """

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session: requests.Session | None = None,
        anonymous_token: str | None = None,
        device_id: str | None = None,
    ):
        self.timeout = timeout or REQUEST_TIMEOUT
        self.session = session or requests.Session()
        self.anonymous_token = (
            anonymous_token or os.getenv(ANONYMOUS_TOKEN_ENV) or ""
        ).strip()
        self.device_id = (
            device_id or os.getenv(DEVICE_ID_ENV) or str(uuid4())
        ).strip()

        self.session.headers.update(DEFAULT_HEADERS)

    def close(self) -> None:
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def get_json(
        self,
        url: str,
        *,
        params: dict | list[tuple[str, object]] | None = None,
    ) -> dict:
        return self._get_authenticated_json(url, params=params)

    def get_ranking_goods(
        self,
        *,
        params: dict | list[tuple[str, object]] | None = None,
    ) -> dict:
        return self.get_json(RANKING_GOODS_API_URL, params=params)

    def get_ranking_filters(self) -> dict:
        return self.get_json(RANKING_FILTERS_API_URL)

    def _get_authenticated_json(
        self,
        url: str,
        *,
        params: dict | list[tuple[str, object]] | None = None,
    ) -> dict:
        token = self._ensure_anonymous_token()
        response = self._request(
            url,
            params=params,
            headers=self._authentication_headers(token),
        )

        # 오래된 환경변수/프로세스 캐시 토큰도 자동 복구한다.
        if response.status_code in {401, 403}:
            self.anonymous_token = ""
            token = self._issue_anonymous_token()
            response = self._request(
                url,
                params=params,
                headers=self._authentication_headers(token),
            )

        self._raise_for_status(response, url=url)
        return self._response_json(response, url=url)

    def _ensure_anonymous_token(self) -> str:
        if self.anonymous_token:
            return self.anonymous_token
        return self._issue_anonymous_token()

    def _issue_anonymous_token(self) -> str:
        response = self._request(ANONYMOUS_TOKEN_API_URL)
        self._raise_for_status(
            response,
            url=ANONYMOUS_TOKEN_API_URL,
            authentication_error=True,
        )
        body = self._response_json(response, url=ANONYMOUS_TOKEN_API_URL)
        token = body.get("token")
        if not isinstance(token, str) or not token.strip():
            raise AblyAuthenticationError(
                "ABLY anonymous token 응답에 token이 없습니다."
            )
        self.anonymous_token = token.strip()
        return self.anonymous_token

    def _authentication_headers(self, token: str) -> dict[str, str]:
        return {
            "x-anonymous-token": token,
            "x-device-id": self.device_id,
        }

    def _request(
        self,
        url: str,
        *,
        params: dict | list[tuple[str, object]] | None = None,
        headers: dict[str, str] | None = None,
    ):
        response = None

        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            status_code = getattr(response, "status_code", None)
            raise AblyCollectError(
                "ABLY GET 요청 실패: "
                f"url={url} status={status_code} error={exc.__class__.__name__}"
            ) from exc
        except Exception as exc:
            raise AblyCollectError(
                "ABLY GET 요청 실패: "
                f"url={url} error={exc.__class__.__name__}"
            ) from exc
        return response

    @staticmethod
    def _raise_for_status(
        response,
        *,
        url: str,
        authentication_error: bool = False,
    ) -> None:
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            status_code = getattr(response, "status_code", None)
            error_class = (
                AblyAuthenticationError
                if authentication_error or status_code in {401, 403}
                else AblyCollectError
            )
            raise error_class(
                "ABLY GET 요청 실패: "
                f"url={url} status={status_code} error={exc.__class__.__name__}"
            ) from exc

    @staticmethod
    def _response_json(response, *, url: str) -> dict:
        try:
            body = response.json()
        except ValueError as exc:
            raise AblyCollectError(
                f"ABLY JSON 응답 파싱 실패: {url}"
            ) from exc

        if not isinstance(body, dict):
            raise AblyCollectError(
                f"ABLY JSON object 응답이 아닙니다: {url}"
            )

        return body
