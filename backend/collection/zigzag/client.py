from __future__ import annotations

from curl_cffi import requests

from .constants import (
    DEFAULT_HEADERS,
    DEFAULT_RENDER_WAIT_MS,
    DEFAULT_SCROLL_COUNT,
    DEFAULT_SCROLL_WAIT_MS,
    PRODUCT_CARD_SELECTOR,
    REQUEST_TIMEOUT,
)
from .exceptions import ZigzagCollectError


class ZigzagClient:
    """
    ZIGZAG Client.

    PRODUCT:
    - curl_cffi HTTP 요청

    RANKING:
    - Playwright Chromium 렌더링

    저장/S3/DB 처리는 하지 않는다.
    """

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session=None,
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
        request_headers = {
            **DEFAULT_HEADERS,
        }

        if referer:
            request_headers[
                "Referer"
            ] = referer

        if headers:
            request_headers.update(
                headers
            )

        return self.get(
            url,
            params=params,
            headers=request_headers,
        )

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
            response = (
                self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            )

            response.raise_for_status()

            return response

        except Exception as exc:
            raise ZigzagCollectError(
                "ZIGZAG GET 요청 실패: "
                f"{url} / {exc}"
            ) from exc

    # ============================================================
    # PLAYWRIGHT RENDER
    # ============================================================

    def render_html(
        self,
        url: str,
        *,
        limit: int | None = None,
        scroll_count: int = (
            DEFAULT_SCROLL_COUNT
        ),
        wait_ms: int = (
            DEFAULT_RENDER_WAIT_MS
        ),
        scroll_wait_ms: int = (
            DEFAULT_SCROLL_WAIT_MS
        ),
        mobile: bool = True,
    ) -> str:
        """
        JavaScript 렌더링이 필요한 ZIGZAG 목록 페이지를
        Chromium으로 렌더링한 뒤 최종 HTML을 반환한다.
        """

        try:
            from playwright.sync_api import (
                sync_playwright,
            )

        except ImportError as exc:
            raise ZigzagCollectError(
                "Playwright가 설치되어 있지 않습니다. "
                "`pip install playwright` 후 "
                "`playwright install chromium`을 "
                "실행하세요."
            ) from exc

        try:
            with sync_playwright() as playwright:
                browser = (
                    playwright.chromium.launch(
                        headless=True,
                    )
                )

                context_options = {
                    "locale": "ko-KR",
                    "user_agent": (
                        DEFAULT_HEADERS[
                            "User-Agent"
                        ]
                    ),
                }

                if mobile:
                    context_options.update(
                        {
                            "viewport": {
                                "width": 430,
                                "height": 932,
                            },
                            "is_mobile": True,
                            "has_touch": True,
                        }
                    )

                context = (
                    browser.new_context(
                        **context_options
                    )
                )

                page = context.new_page()

                page.goto(
                    url,
                    wait_until=(
                        "domcontentloaded"
                    ),
                    timeout=int(
                        self.timeout
                        * 1000
                    ),
                )

                page.wait_for_timeout(
                    wait_ms
                )

                previous_count = -1
                stale_rounds = 0

                for _ in range(
                    max(
                        0,
                        int(scroll_count),
                    )
                ):
                    current_count = (
                        page.locator(
                            PRODUCT_CARD_SELECTOR
                        )
                        .count()
                    )

                    if (
                        limit is not None
                        and current_count
                        >= limit
                    ):
                        break

                    page.evaluate(
                        """
                        window.scrollTo(
                            0,
                            document.body.scrollHeight
                        )
                        """
                    )

                    page.wait_for_timeout(
                        scroll_wait_ms
                    )

                    next_count = (
                        page.locator(
                            PRODUCT_CARD_SELECTOR
                        )
                        .count()
                    )

                    if (
                        next_count
                        <= current_count
                    ):
                        stale_rounds += 1
                    else:
                        stale_rounds = 0

                    previous_count = (
                        next_count
                    )

                    # 4회 연속 상품 증가 없음
                    if stale_rounds >= 4:
                        break

                html = page.content()

                context.close()
                browser.close()

                return html

        except ZigzagCollectError:
            raise

        except Exception as exc:
            raise ZigzagCollectError(
                "ZIGZAG 브라우저 렌더링 실패: "
                f"{url} / {exc}"
            ) from exc