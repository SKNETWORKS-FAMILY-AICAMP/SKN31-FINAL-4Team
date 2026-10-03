from __future__ import annotations

from typing import Any

import requests


DEFAULT_TIMEOUT = 20

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


class HttpClient:
    def __init__(
        self,
        *,
        headers: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        if headers:
            self.session.headers.update(headers)

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> requests.Response:

        response = self.session.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout or self.timeout,
            **kwargs,
        )

        response.raise_for_status()

        return response

    def post(
        self,
        url: str,
        *,
        params: dict | None = None,
        json: Any = None,
        data: Any = None,
        headers: dict | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> requests.Response:

        response = self.session.post(
            url,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout or self.timeout,
            **kwargs,
        )

        response.raise_for_status()

        return response

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.close()