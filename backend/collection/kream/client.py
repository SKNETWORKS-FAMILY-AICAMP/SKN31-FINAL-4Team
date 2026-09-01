from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from curl_cffi import requests

from .constants import (
    DEFAULT_HEADERS,
    KREAM_API_VERSION,
    KREAM_WEB_BUILD_VERSION,
    KREAM_WEB_REQUEST_SECRET,
    PRODUCT_PAGE_URL,
    REQUEST_TIMEOUT,
)
from .exceptions import (
    KreamCollectError,
)


class KreamClient:

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session=None,
        device_id: str | None = None,
    ):
        self.timeout = (
            timeout
            or REQUEST_TIMEOUT
        )

        self.session = (
            session
            or requests.Session(
                impersonate="chrome",
            )
        )

        self.device_id = (
            device_id
            or f"web;{uuid4()}"
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
    # PARAMS
    # ============================================================

    @staticmethod
    def build_product_params(
        product_id: int,
    ) -> dict:

        return {
            "base_product_id": product_id,
            "request_key": str(
                uuid4()
            ),
        }

    # ============================================================
    # DATETIME
    # ============================================================

    @staticmethod
    def build_client_datetime() -> str:
        """
        HAR 형식:
        20260902060216+0900
        """

        now = datetime.now().astimezone()

        return now.strftime(
            "%Y%m%d%H%M%S%z"
        )

    # ============================================================
    # HEADERS
    # ============================================================

    def build_headers(
        self,
        product_id: int,
    ) -> dict:

        headers = dict(
            DEFAULT_HEADERS
        )

        headers.update(
            {
                "Referer": (
                    PRODUCT_PAGE_URL.format(
                        product_id=product_id,
                    )
                ),

                "x-kream-api-version": (
                    KREAM_API_VERSION
                ),

                "x-kream-client-datetime": (
                    self.build_client_datetime()
                ),

                "x-kream-device-id": (
                    self.device_id
                ),

                "x-kream-web-build-version": (
                    KREAM_WEB_BUILD_VERSION
                ),

                "x-kream-web-request-secret": (
                    KREAM_WEB_REQUEST_SECRET
                ),
            }
        )

        return headers

    # ============================================================
    # GET JSON
    # ============================================================

    def get_json(
        self,
        url: str,
        *,
        product_id: int,
        params: dict | None = None,
    ) -> dict:

        request_params = (
            params
            or self.build_product_params(
                product_id
            )
        )

        headers = self.build_headers(
            product_id
        )

        try:
            response = (
                self.session.get(
                    url,
                    params=request_params,
                    headers=headers,
                    timeout=self.timeout,
                )
            )

            if response.status_code != 200:
                print()
                print(
                    "[KREAM DEBUG]"
                )
                print(
                    "status:",
                    response.status_code,
                )
                print(
                    "url:",
                    response.url,
                )
                print(
                    "headers:",
                    headers,
                )
                print(
                    "body:",
                    response.text[:500],
                )
                print()

            response.raise_for_status()

        except Exception as exc:
            raise KreamCollectError(
                f"KREAM GET 실패: "
                f"{url} / {exc}"
            ) from exc

        try:
            body = response.json()

        except Exception as exc:
            raise KreamCollectError(
                f"KREAM JSON 파싱 실패: "
                f"{response.url}"
            ) from exc

        if not isinstance(
            body,
            dict,
        ):
            raise KreamCollectError(
                "KREAM JSON object "
                "응답이 아닙니다: "
                f"{response.url}"
            )

        return body