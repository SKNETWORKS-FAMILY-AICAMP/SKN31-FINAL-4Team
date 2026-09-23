from __future__ import annotations

import os
from uuid import uuid4

import requests

from .constants import (
    ANONYMOUS_TOKEN_API_URL,
    ANONYMOUS_TOKEN_ENV,
    DEFAULT_HEADERS,
    DEVICE_ID_ENV,
    COMPONENT_LIST_API_URL,
    GOODS_REVIEWS_API_URL_TEMPLATE,
    RANKING_FILTERS_API_URL,
    RANKING_GOODS_API_URL,
    RANKING_PAGE_URL,
    REQUEST_TIMEOUT,
)
from .exceptions import AblyAuthenticationError, AblyCollectError


class AblyClient:
    """ABLY JSON API 전용 HTTP client.

    핵심:
    - anonymous token 발급과 goods API 요청에 동일한 x-device-id를 사용한다.
    - 401/403 발생 시 anonymous token + 자동 생성 device id를 함께 갱신한다.
    - Origin/Referer를 실제 mobile ranking 페이지 기준으로 맞춘다.
    - 인증값 자체는 로그/예외에 노출하지 않는다.
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

        env_token = (os.getenv(ANONYMOUS_TOKEN_ENV) or "").strip()
        env_device = (os.getenv(DEVICE_ID_ENV) or "").strip()

        self.anonymous_token = (
            (anonymous_token or "").strip()
            or env_token
        )

        self._fixed_device_id = bool(
            (device_id or "").strip()
            or env_device
        )

        self.device_id = (
            (device_id or "").strip()
            or env_device
            or str(uuid4())
        )

        self.session.headers.update(DEFAULT_HEADERS)
        self.session.headers.update(
            {
                "Origin": "https://mobile.a-bly.com",
                "Referer": RANKING_PAGE_URL,
            }
        )

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

    def get_goods_reviews(self, goods_sno: str | int) -> dict:
        return self.get_json(
            GOODS_REVIEWS_API_URL_TEMPLATE.format(goods_sno=goods_sno)
        )

    def get_component_list(
        self,
        *,
        category_sno: int,
        next_token: str,
    ) -> dict:
        """브랜드관 COMPONENT_LIST 한 페이지를 조회한다.

        ``next_token``은 opaque cursor이므로 decode/re-encode하지 않는다.
        requests가 query string 전송 시 필요한 URL encoding만 담당한다.
        """
        return self.get_json(
            COMPONENT_LIST_API_URL,
            params={
                "next_token": next_token,
                "category_sno": category_sno,
            },
        )

    # ============================================================
    # AUTHENTICATED GET
    # ============================================================

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

        if response.status_code in {401, 403}:
            # 환경변수 token이 만료됐거나
            # token/device pair가 맞지 않는 경우 복구.
            self.anonymous_token = ""

            # 사용자가 ABLY_DEVICE_ID를 명시하지 않은 경우에는
            # device id도 새로 만들어 token과 새 pair를 구성한다.
            if not self._fixed_device_id:
                self.device_id = str(uuid4())

            token = self._issue_anonymous_token()

            response = self._request(
                url,
                params=params,
                headers=self._authentication_headers(token),
            )

        self._raise_for_status(response, url=url)
        return self._response_json(response, url=url)

    # ============================================================
    # ANONYMOUS TOKEN
    # ============================================================

    def _ensure_anonymous_token(self) -> str:
        if self.anonymous_token:
            return self.anonymous_token

        return self._issue_anonymous_token()

    def _issue_anonymous_token(self) -> str:
        # 중요:
        # token 발급 요청부터 실제 goods 요청과 동일한 device id 사용.
        response = self._request(
            ANONYMOUS_TOKEN_API_URL,
            headers=self._token_issue_headers(),
        )

        self._raise_for_status(
            response,
            url=ANONYMOUS_TOKEN_API_URL,
            authentication_error=True,
        )

        body = self._response_json(
            response,
            url=ANONYMOUS_TOKEN_API_URL,
        )

        token = body.get("token")

        if not isinstance(token, str) or not token.strip():
            raise AblyAuthenticationError(
                "ABLY anonymous token 응답에 token이 없습니다."
            )

        self.anonymous_token = token.strip()
        return self.anonymous_token

    def _token_issue_headers(self) -> dict[str, str]:
        return {
            "x-device-id": self.device_id,
            "Origin": "https://mobile.a-bly.com",
            "Referer": RANKING_PAGE_URL,
        }

    def _authentication_headers(
        self,
        token: str,
    ) -> dict[str, str]:
        return {
            "x-anonymous-token": token,
            "x-device-id": self.device_id,
            "Origin": "https://mobile.a-bly.com",
            "Referer": RANKING_PAGE_URL,
        }

    # ============================================================
    # HTTP
    # ============================================================

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
            status_code = getattr(
                response,
                "status_code",
                None,
            )

            raise AblyCollectError(
                "ABLY GET 요청 실패: "
                f"url={url} "
                f"status={status_code} "
                f"error={exc.__class__.__name__}"
            ) from exc

        except Exception as exc:
            raise AblyCollectError(
                "ABLY GET 요청 실패: "
                f"url={url} "
                f"error={exc.__class__.__name__}"
            ) from exc

        return response

    # ============================================================
    # RESPONSE
    # ============================================================

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
            status_code = getattr(
                response,
                "status_code",
                None,
            )

            error_class = (
                AblyAuthenticationError
                if authentication_error
                or status_code in {401, 403}
                else AblyCollectError
            )

            # token/device 값은 절대 출력하지 않는다.
            body_preview = None

            try:
                if response.text:
                    body_preview = response.text[:300]
            except Exception:
                pass

            raise error_class(
                "ABLY GET 요청 실패: "
                f"url={url} "
                f"status={status_code} "
                f"error={exc.__class__.__name__} "
                f"body={body_preview!r}"
            ) from exc

    @staticmethod
    def _response_json(
        response,
        *,
        url: str,
    ) -> dict:
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
