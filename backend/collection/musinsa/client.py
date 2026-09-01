from __future__ import annotations

from curl_cffi import requests

from .constants import REQUEST_TIMEOUT
from .exceptions import MusinsaCollectError


class MusinsaClient:
    """
    Musinsa HTTP Client.

    - requests 대신 curl_cffi 사용
    - Chrome TLS / HTTP2 fingerprint impersonation
    - HTML / API 모두 동일 세션 사용
    """

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session=None,
    ):
        self.timeout = timeout or REQUEST_TIMEOUT

        self.session = session or requests.Session(
            impersonate="chrome",
        )

    def close(self) -> None:
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        self.close()

    # ============================================================
    # HTML
    # ============================================================

    def get_html(
        self,
        url: str,
        *,
        params: dict | None = None,
        referer: str | None = None,
        headers: dict | None = None,
    ):
        request_headers = {}

        if referer:
            request_headers["Referer"] = referer

        if headers:
            request_headers.update(headers)

        return self.get(
            url,
            params=params,
            headers=request_headers or None,
        )

    # ============================================================
    # JSON GET
    # ============================================================

    def get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        referer: str | None = None,
        headers: dict | None = None,
    ) -> dict:
        request_headers = {
            "Accept": "application/json, text/plain, */*",
        }

        if referer:
            request_headers["Referer"] = referer

        if headers:
            request_headers.update(headers)

        response = self.get(
            url,
            params=params,
            headers=request_headers,
        )

        return self._response_json(response)

    # ============================================================
    # JSON POST
    # ============================================================

    def post_json(
        self,
        url: str,
        *,
        json: dict | None = None,
        referer: str | None = None,
        headers: dict | None = None,
    ) -> dict:
        request_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }

        if referer:
            request_headers["Referer"] = referer

        if headers:
            request_headers.update(headers)

        response = self.post(
            url,
            json=json,
            headers=request_headers,
        )

        return self._response_json(response)

    # ============================================================
    # LOW LEVEL GET
    # ============================================================

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ):
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )

            response.raise_for_status()

            return response

        except Exception as exc:
            raise MusinsaCollectError(
                f"GET 요청 실패: {url} / {exc}"
            ) from exc

    # ============================================================
    # LOW LEVEL POST
    # ============================================================

    def post(
        self,
        url: str,
        *,
        json: dict | None = None,
        data=None,
        headers: dict | None = None,
    ):
        try:
            response = self.session.post(
                url,
                json=json,
                data=data,
                headers=headers,
                timeout=self.timeout,
            )

            response.raise_for_status()

            return response

        except Exception as exc:
            raise MusinsaCollectError(
                f"POST 요청 실패: {url} / {exc}"
            ) from exc

    # ============================================================
    # JSON PARSER
    # ============================================================

    @staticmethod
    def _response_json(response) -> dict:
        try:
            body = response.json()

        except Exception as exc:
            raise MusinsaCollectError(
                f"JSON 응답 파싱 실패: {response.url}"
            ) from exc

        if not isinstance(body, dict):
            raise MusinsaCollectError(
                f"JSON object 응답이 아닙니다: {response.url}"
            )

        return body