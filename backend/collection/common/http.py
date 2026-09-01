import requests

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

DEFAULT_TIMEOUT = 20

def get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
):
    request_headers = DEFAULT_HEADERS.copy()

    if headers:
        request_headers.update(headers)

    response = requests.get(
        url,
        params=params,
        headers=request_headers,
        timeout=timeout,
    )

    response.raise_for_status()

    return response