from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from .constants import (
    MUSINSA_USED_MAX_RETRIES,
    MUSINSA_USED_MAX_INFLIGHT_REQUESTS,
    MUSINSA_USED_RETRY_INITIAL_DELAY_SEC,
    MUSINSA_USED_RETRY_MAX_DELAY_SEC,
    MUSINSA_USED_RETRY_MULTIPLIER,
)
from .exceptions import MusinsaUsedCollectError
from .pacing import (
    AdaptiveBackoffPolicy,
    HostBackoffCoordinator,
    InFlightRequestLimiter,
)


DEFAULT_HOST_BACKOFF_COORDINATOR = HostBackoffCoordinator()
DEFAULT_REQUEST_LIMITER = InFlightRequestLimiter(
    MUSINSA_USED_MAX_INFLIGHT_REQUESTS
)


class MusinsaUsedClient:
    """MUSINSA USED transport with adaptive, bounded retries.

    A successful 2xx response is returned immediately.  All live endpoints
    use ``_request`` so retry and request metrics stay consistent.
    """

    RETRYABLE_STATUS_CODES = {429}

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session=None,
        backoff_policy: AdaptiveBackoffPolicy | None = None,
        backoff_coordinator: HostBackoffCoordinator | None = None,
        request_limiter: InFlightRequestLimiter | None = None,
    ):
        self.timeout = timeout or 30
        if session is not None:
            self.session = session
            self._owns_session = False
        else:
            self.session = requests.Session(impersonate="chrome")
            self._owns_session = True
        self.backoff_policy = backoff_policy or AdaptiveBackoffPolicy(
            max_retries=MUSINSA_USED_MAX_RETRIES,
            initial_delay_sec=MUSINSA_USED_RETRY_INITIAL_DELAY_SEC,
            multiplier=MUSINSA_USED_RETRY_MULTIPLIER,
            max_delay_sec=MUSINSA_USED_RETRY_MAX_DELAY_SEC,
        )
        self.backoff_coordinator = backoff_coordinator or DEFAULT_HOST_BACKOFF_COORDINATOR
        self.request_limiter = request_limiter or DEFAULT_REQUEST_LIMITER
        self.request_metrics: list[dict] = []

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def read_html(self, file_path: str | Path) -> str:
        path = Path(file_path)
        if not path.exists():
            raise MusinsaUsedCollectError(f"MUSINSA USED HTML file does not exist: {path}")
        if not path.is_file():
            raise MusinsaUsedCollectError(f"MUSINSA USED HTML path is not a file: {path}")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="utf-8-sig")
            except Exception as exc:
                raise MusinsaUsedCollectError(
                    f"Unable to decode MUSINSA USED HTML file: {path}"
                ) from exc
        except Exception as exc:
            raise MusinsaUsedCollectError(
                f"Unable to read MUSINSA USED HTML file: {path} / {exc}"
            ) from exc

    def read_json(self, file_path: str | Path) -> dict[str, Any]:
        try:
            value = json.loads(self.read_html(file_path))
        except (json.JSONDecodeError, MusinsaUsedCollectError) as exc:
            raise MusinsaUsedCollectError(
                f"Unable to read MUSINSA USED JSON file: {file_path}"
            ) from exc
        if not isinstance(value, dict):
            raise MusinsaUsedCollectError(
                f"MUSINSA USED JSON response is not an object: {file_path}"
            )
        return value

    def get_html(
        self,
        url: str,
        *,
        params: dict | None = None,
        referer: str | None = None,
        headers: dict | None = None,
    ):
        request_headers = dict(headers or {})
        if referer:
            request_headers["Referer"] = referer
        return self._request("GET", url, params=params, headers=request_headers or None)

    def get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        referer: str | None = None,
        headers: dict | None = None,
    ) -> dict:
        request_headers = {"Accept": "application/json, text/plain, */*"}
        if referer:
            request_headers["Referer"] = referer
        if headers:
            request_headers.update(headers)
        response = self._request("GET", url, params=params, headers=request_headers)
        try:
            body = response.json()
        except Exception as exc:
            raise MusinsaUsedCollectError(f"JSON response parsing failed: {url}") from exc
        if not isinstance(body, dict):
            raise MusinsaUsedCollectError(f"JSON response is not an object: {url}")
        return body

    def _request(self, method: str, url: str, **kwargs):
        max_attempts = self.backoff_policy.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            global_wait_sec = self.backoff_coordinator.wait_if_needed()
            started_at = time.monotonic()
            response = None
            try:
                with self.request_limiter.slot():
                    response = self.session.request(
                        method,
                        url,
                        timeout=self.timeout,
                        **kwargs,
                    )
                status_code = getattr(response, "status_code", 200)
                duration_sec = time.monotonic() - started_at
                if 200 <= status_code < 300:
                    self._record_metric(
                        method, url, status_code, duration_sec, attempt, 0.0, global_wait_sec
                    )
                    return response

                error = self._http_error(response, method, url)
                if not self._is_retryable_status(status_code):
                    self._record_metric(
                        method, url, status_code, duration_sec, attempt, 0.0, global_wait_sec
                    )
                    raise error
                last_error = error
            except RequestException as exc:
                duration_sec = time.monotonic() - started_at
                last_error = exc
                status_code = self._status_code(getattr(exc, "response", None))
                response = getattr(exc, "response", None)
            except MusinsaUsedCollectError:
                raise

            if attempt + 1 >= max_attempts:
                status_code = self._status_code(response)
                cooldown_imposed = False
                backoff_sec = 0.0
                if status_code == 429:
                    backoff_sec = self.backoff_policy.delay_for_retry(
                        attempt + 1,
                        response,
                    )
                    cooldown_imposed = self.backoff_coordinator.impose_cooldown(
                        backoff_sec
                    )
                self._record_metric(
                    method,
                    url,
                    status_code,
                    duration_sec,
                    attempt,
                    backoff_sec,
                    global_wait_sec,
                    cooldown_imposed,
                )
                break

            retry_number = attempt + 1
            status_code = self._status_code(response)
            cooldown_imposed = False
            if status_code == 429:
                backoff_sec = self.backoff_policy.delay_for_retry(retry_number, response)
                cooldown_imposed = self.backoff_coordinator.impose_cooldown(backoff_sec)
            else:
                backoff_sec = self.backoff_policy.sleep_before_retry(retry_number, response)
            self._record_metric(
                method,
                url,
                self._status_code(response),
                duration_sec,
                attempt,
                backoff_sec,
                global_wait_sec,
                cooldown_imposed,
            )

        raise MusinsaUsedCollectError(
            f"{method} request failed after {max_attempts} attempts: {url} / {last_error}"
        ) from last_error

    @classmethod
    def _is_retryable_status(cls, status_code: int | None) -> bool:
        return status_code in cls.RETRYABLE_STATUS_CODES or (
            status_code is not None and 500 <= status_code < 600
        )

    @staticmethod
    def _status_code(response) -> int | None:
        status_code = getattr(response, "status_code", None)
        return status_code if isinstance(status_code, int) else None

    @staticmethod
    def _http_error(response, method: str, url: str) -> MusinsaUsedCollectError:
        status_code = getattr(response, "status_code", None)
        return MusinsaUsedCollectError(f"{method} request failed: {url} / HTTP {status_code}")

    def _record_metric(
        self,
        method: str,
        url: str,
        status_code: int | None,
        duration_sec: float,
        attempt: int,
        backoff_sec: float,
        global_wait_sec: float = 0.0,
        cooldown_imposed: bool = False,
    ) -> None:
        self.request_metrics.append(
            {
                "method": method,
                "url": url,
                "status_code": status_code,
                "duration_sec": round(duration_sec, 6),
                "attempt": attempt + 1,
                "retry": attempt > 0,
                "backoff_sec": backoff_sec,
                "global_wait_sec": global_wait_sec,
                "cooldown_imposed": cooldown_imposed,
            }
        )
