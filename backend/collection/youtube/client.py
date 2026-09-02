from __future__ import annotations

import requests

from .constants import (
    REQUEST_TIMEOUT,
)
from .exceptions import (
    YoutubeCollectError,
)


class YoutubeClient:

    def __init__(
        self,
        *,
        api_key: str,
        timeout: int = REQUEST_TIMEOUT,
        session=None,
    ):
        if not api_key:
            raise ValueError(
                "YOUTUBE_API_KEY가 없습니다."
            )

        self.api_key = api_key
        self.timeout = timeout

        self.session = (
            session
            or requests.Session()
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

    def get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
    ) -> dict:

        request_params = {
            **(params or {}),
            "key": self.api_key,
        }

        try:
            response = self.session.get(
                url,
                params=request_params,
                timeout=self.timeout,
            )

            response.raise_for_status()

            body = response.json()

        except Exception as exc:
            raise YoutubeCollectError(
                f"YouTube API 요청 실패: "
                f"{url} / {exc}"
            ) from exc

        if not isinstance(
            body,
            dict,
        ):
            raise YoutubeCollectError(
                "YouTube API 응답이 JSON object가 아닙니다."
            )

        return body