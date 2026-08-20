import logging
import os

import requests

logger = logging.getLogger(__name__)


class NaverApiError(RuntimeError):
    """Raised when NAVER API HUB cannot complete a request."""


class NaverApiClient:
    BASE_URL = "https://naverapihub.apigw.ntruss.com"

    def __init__(self, timeout: int = 20):
        key_id = os.getenv("X-NCP-APIGW-API-KEY-ID", "").strip()
        api_key = os.getenv("X-NCP-APIGW-API-KEY", "").strip()
        if not key_id or not api_key:
            raise NaverApiError(".env에 NAVER API HUB 키를 설정하세요.")
        self.timeout = timeout
        self.headers = {
            "X-NCP-APIGW-API-KEY-ID": key_id,
            "X-NCP-APIGW-API-KEY": api_key,
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, *, params=None, json=None) -> dict:
        try:
            response = requests.request(
                method,
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                params=params,
                json=json,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning("NAVER API request failed endpoint=%s status=%s", path, status_code)
            raise NaverApiError(f"NAVER API 요청 실패: {path}") from exc
