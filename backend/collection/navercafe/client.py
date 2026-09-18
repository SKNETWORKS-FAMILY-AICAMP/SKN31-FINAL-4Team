from __future__ import annotations

from curl_cffi import requests

from .constants import (
    CAFE_API_BASE_URL,
    REQUEST_TIMEOUT,
)
from .exceptions import NaverCafeCollectError


class NaverCafeClient:
    """
    Naver Cafe HTTP Client.

    - curl_cffi Session 사용
    - Cafe API 요청
    - HTTP / JSON 응답 처리
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
    # CAFE API
    # ============================================================

    def get_menus(
        self,
        cafe_id: int,
    ) -> dict:
        """
        카페의 게시판/메뉴 목록 조회.
        """

        url = (
            f"{CAFE_API_BASE_URL}"
            f"/cafe-cafemain-api/v1.0"
            f"/cafes/{cafe_id}/menus"
        )

        return self.get_json(url)

    # ============================================================
    # ARTICLE LIST API
    # ============================================================

    def get_articles(
        self,
        cafe_id: int,
        menu_id: int,
        *,
        page: int = 1,
        page_size: int = 15,
        sort_by: str = "TIME",
        view_type: str = "L",
    ) -> dict:
        """
        특정 게시판의 게시글 목록 조회.
        """

        url = (
            f"{CAFE_API_BASE_URL}"
            f"/cafe-boardlist-api/v1"
            f"/cafes/{cafe_id}"
            f"/menus/{menu_id}/articles"
        )

        params = {
            "page": page,
            "pageSize": page_size,
            "sortBy": sort_by,
            "viewType": view_type,
        }

        return self.get_json(
            url,
            params=params,
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
            raise NaverCafeCollectError(
                f"GET 요청 실패: {url} / {exc}"
            ) from exc

    # ============================================================
    # JSON PARSER
    # ============================================================

    @staticmethod
    def _response_json(response) -> dict:

        try:
            body = response.json()

        except Exception as exc:
            raise NaverCafeCollectError(
                f"JSON 응답 파싱 실패: {response.url}"
            ) from exc

        if not isinstance(body, dict):
            raise NaverCafeCollectError(
                f"JSON object 응답이 아닙니다: {response.url}"
            )

        return body