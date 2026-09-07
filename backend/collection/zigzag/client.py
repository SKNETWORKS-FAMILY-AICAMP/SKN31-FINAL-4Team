from __future__ import annotations

import logging
from typing import Any

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


logger = logging.getLogger(__name__)


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
        self.timeout = timeout or REQUEST_TIMEOUT

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
            request_headers["Referer"] = referer

        if headers:
            request_headers.update(headers)

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
        """
        상세 상품 페이지 GET.

        기존 코드보다 실패 원인을 더 자세히 남긴다.
        """

        response = None

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
            status_code = getattr(
                response,
                "status_code",
                None,
            )

            response_url = getattr(
                response,
                "url",
                url,
            )

            body_preview = None

            if response is not None:
                try:
                    body_preview = (
                        response.text[:300]
                        if response.text
                        else None
                    )
                except Exception:
                    body_preview = None

            logger.exception(
                "ZIGZAG GET failed "
                "url=%s status=%s error=%s body_preview=%r",
                response_url,
                status_code,
                exc,
                body_preview,
            )

            raise ZigzagCollectError(
                "ZIGZAG GET 요청 실패: "
                f"url={response_url} "
                f"status={status_code} "
                f"error={exc}"
            ) from exc

    # ============================================================
    # PLAYWRIGHT HELPERS
    # ============================================================

    @staticmethod
    def _page_metrics(page) -> dict[str, Any]:
        """
        현재 브라우저 스크롤 상태를 디버깅하기 위한 값.
        """

        try:
            return page.evaluate(
                """
                () => ({
                    scrollY: window.scrollY,
                    innerHeight: window.innerHeight,
                    bodyHeight: document.body
                        ? document.body.scrollHeight
                        : null,
                    documentHeight: document.documentElement
                        ? document.documentElement.scrollHeight
                        : null
                })
                """
            )
        except Exception:
            return {
                "scrollY": None,
                "innerHeight": None,
                "bodyHeight": None,
                "documentHeight": None,
            }

    @staticmethod
    def _log_network_request(request) -> None:
        """
        XHR/fetch 요청만 debug 로그에 기록.
        """

        if request.resource_type not in {
            "xhr",
            "fetch",
        }:
            return

        logger.debug(
            "ZIGZAG NETWORK request "
            "method=%s type=%s url=%s",
            request.method,
            request.resource_type,
            request.url,
        )

    @staticmethod
    def _log_network_response(response) -> None:
        """
        XHR/fetch 응답 상태를 debug 로그에 기록.
        """

        try:
            request = response.request

            if request.resource_type not in {
                "xhr",
                "fetch",
            }:
                return

            logger.debug(
                "ZIGZAG NETWORK response "
                "status=%s type=%s url=%s",
                response.status,
                request.resource_type,
                response.url,
            )

        except Exception:
            return

    @staticmethod
    def _scroll_last_card_into_view(
        page,
        *,
        selector: str,
        card_count: int,
    ) -> bool:
        """
        마지막 상품 카드를 viewport 안으로 이동시킨다.

        지그재그가 IntersectionObserver 기반으로
        다음 페이지를 로드하는 경우 window.scrollTo()보다
        안정적으로 trigger될 가능성이 높다.
        """

        if card_count <= 0:
            return False

        try:
            locator = page.locator(selector)

            locator.nth(
                card_count - 1
            ).scroll_into_view_if_needed()

            return True

        except Exception as exc:
            logger.debug(
                "ZIGZAG last-card scroll failed: %s",
                exc,
            )

            return False

    @staticmethod
    def _scroll_window_to_bottom(page) -> None:
        """
        마지막 카드 scroll이 실패하거나
        document 전체 scroll이 필요한 경우 fallback.
        """

        page.evaluate(
            """
            () => {
                const height = Math.max(
                    document.body
                        ? document.body.scrollHeight
                        : 0,
                    document.documentElement
                        ? document.documentElement.scrollHeight
                        : 0
                );

                window.scrollTo({
                    top: height,
                    behavior: "instant"
                });
            }
            """
        )

    @staticmethod
    def _scroll_near_bottom(page) -> None:
        """
        맨 아래로 순간 이동하는 것만으로 observer가 동작하지 않는
        경우를 위해 작은 스크롤도 추가한다.
        """

        page.evaluate(
            """
            () => {
                window.scrollBy({
                    top: Math.max(
                        window.innerHeight * 0.85,
                        500
                    ),
                    behavior: "instant"
                });
            }
            """
        )

    @staticmethod
    def _wait_for_card_growth(
        page,
        *,
        selector: str,
        previous_count: int,
        timeout_ms: int,
    ) -> bool:
        """
        카드 수가 previous_count보다 증가할 때까지 기다린다.

        고정 sleep만 사용하는 것보다 React 렌더링 지연에 안전하다.
        """

        try:
            page.wait_for_function(
                """
                ([selector, previousCount]) => {
                    return (
                        document.querySelectorAll(selector).length
                        > previousCount
                    );
                }
                """,
                arg=[
                    selector,
                    previous_count,
                ],
                timeout=timeout_ms,
            )

            return True

        except Exception:
            return False

    @staticmethod
    def _find_scrollable_parent_for_last_card(
        page,
        *,
        selector: str,
    ) -> bool:
        """
        window가 아니라 내부 scroll container를 사용하는 경우
        마지막 카드의 scroll 가능한 부모를 찾아 끝까지 스크롤한다.

        발견한 경우 True.
        """

        try:
            return bool(
                page.evaluate(
                    """
                    (selector) => {
                        const cards =
                            document.querySelectorAll(selector);

                        if (!cards.length) {
                            return false;
                        }

                        let node =
                            cards[cards.length - 1].parentElement;

                        while (node) {
                            const style =
                                window.getComputedStyle(node);

                            const overflowY =
                                style.overflowY;

                            const scrollable =
                                (
                                    overflowY === "auto"
                                    || overflowY === "scroll"
                                )
                                && node.scrollHeight
                                    > node.clientHeight;

                            if (scrollable) {
                                node.scrollTop =
                                    node.scrollHeight;

                                return true;
                            }

                            node = node.parentElement;
                        }

                        return false;
                    }
                    """,
                    selector,
                )
            )

        except Exception:
            return False

    # ============================================================
    # PLAYWRIGHT RENDER
    # ============================================================

    def render_html(
        self,
        url: str,
        *,
        limit: int | None = None,
        scroll_count: int = DEFAULT_SCROLL_COUNT,
        wait_ms: int = DEFAULT_RENDER_WAIT_MS,
        scroll_wait_ms: int = DEFAULT_SCROLL_WAIT_MS,
        mobile: bool = True,
    ) -> str:
        """
        JavaScript 렌더링이 필요한 ZIGZAG 목록 페이지를
        Chromium으로 렌더링한 뒤 최종 HTML을 반환한다.

        개선 사항:
        - 마지막 카드 scroll_into_view
        - 내부 scroll container fallback
        - window scroll fallback
        - 카드 수 증가를 조건 기반으로 대기
        - XHR/fetch debug logging
        - stale 종료 조건 완화
        - limit 도달 여부 명확히 확인
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
                browser = playwright.chromium.launch(
                    headless=True,
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

                context = browser.new_context(
                    **context_options
                )

                page = context.new_page()

                # --------------------------------------------
                # Network debug
                # --------------------------------------------

                page.on(
                    "request",
                    self._log_network_request,
                )

                page.on(
                    "response",
                    self._log_network_response,
                )

                # --------------------------------------------
                # Navigate
                # --------------------------------------------

                logger.info(
                    "ZIGZAG ranking render start "
                    "url=%s limit=%s",
                    url,
                    limit,
                )

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(
                        self.timeout * 1000
                    ),
                )

                # 초기 React/Next 렌더링 대기
                page.wait_for_timeout(
                    max(
                        int(wait_ms),
                        1000,
                    )
                )

                cards = page.locator(
                    PRODUCT_CARD_SELECTOR
                )

                initial_count = cards.count()

                logger.info(
                    "ZIGZAG initial cards=%s "
                    "selector=%s",
                    initial_count,
                    PRODUCT_CARD_SELECTOR,
                )

                # --------------------------------------------
                # Scroll loop
                # --------------------------------------------

                stale_rounds = 0

                # 너무 빨리 중단되지 않도록 최소 6회 stale 허용
                max_stale_rounds = 6

                # React/API 응답까지 기다릴 최대 시간
                growth_timeout_ms = max(
                    int(scroll_wait_ms * 4),
                    5000,
                )

                max_scroll_rounds = max(
                    1,
                    int(scroll_count),
                )

                for round_no in range(
                    1,
                    max_scroll_rounds + 1,
                ):
                    current_count = cards.count()

                    if (
                        limit is not None
                        and current_count >= limit
                    ):
                        logger.info(
                            "ZIGZAG ranking limit reached "
                            "round=%s count=%s limit=%s",
                            round_no,
                            current_count,
                            limit,
                        )

                        break

                    before_metrics = (
                        self._page_metrics(page)
                    )

                    # ----------------------------------------
                    # 1. 마지막 카드 viewport 진입
                    # ----------------------------------------

                    last_card_scrolled = (
                        self._scroll_last_card_into_view(
                            page,
                            selector=(
                                PRODUCT_CARD_SELECTOR
                            ),
                            card_count=current_count,
                        )
                    )

                    # IntersectionObserver가 반응할 시간
                    page.wait_for_timeout(
                        max(
                            250,
                            min(
                                int(scroll_wait_ms),
                                1000,
                            ),
                        )
                    )

                    # ----------------------------------------
                    # 2. 내부 scroll container도 시도
                    # ----------------------------------------

                    internal_scrolled = (
                        self._find_scrollable_parent_for_last_card(
                            page,
                            selector=(
                                PRODUCT_CARD_SELECTOR
                            ),
                        )
                    )

                    # ----------------------------------------
                    # 3. 작은 scroll + document bottom fallback
                    # ----------------------------------------

                    self._scroll_near_bottom(page)

                    page.wait_for_timeout(250)

                    self._scroll_window_to_bottom(
                        page
                    )

                    # ----------------------------------------
                    # 4. 카드 증가 조건 대기
                    # ----------------------------------------

                    grew = self._wait_for_card_growth(
                        page,
                        selector=(
                            PRODUCT_CARD_SELECTOR
                        ),
                        previous_count=current_count,
                        timeout_ms=growth_timeout_ms,
                    )

                    if not grew:
                        # wait_for_function timeout 후에도
                        # 늦게 DOM 반영되는 경우 한 번 더 여유
                        page.wait_for_timeout(
                            max(
                                int(scroll_wait_ms),
                                1000,
                            )
                        )

                    next_count = cards.count()

                    after_metrics = (
                        self._page_metrics(page)
                    )

                    logger.info(
                        "ZIGZAG ranking scroll "
                        "round=%s "
                        "current=%s "
                        "next=%s "
                        "grew=%s "
                        "last_card_scroll=%s "
                        "internal_scroll=%s "
                        "before=%s "
                        "after=%s",
                        round_no,
                        current_count,
                        next_count,
                        grew,
                        last_card_scrolled,
                        internal_scrolled,
                        before_metrics,
                        after_metrics,
                    )

                    if next_count > current_count:
                        stale_rounds = 0
                    else:
                        stale_rounds += 1

                    if (
                        limit is not None
                        and next_count >= limit
                    ):
                        logger.info(
                            "ZIGZAG ranking limit reached "
                            "after scroll "
                            "round=%s count=%s limit=%s",
                            round_no,
                            next_count,
                            limit,
                        )

                        break

                    # 연속해서 카드 증가가 없으면 종료.
                    #
                    # 기존 4회보다 여유를 두고,
                    # 네트워크/React 렌더링이 늦은 상황을 고려한다.
                    if (
                        stale_rounds
                        >= max_stale_rounds
                    ):
                        logger.warning(
                            "ZIGZAG ranking stale stop "
                            "round=%s count=%s "
                            "stale_rounds=%s",
                            round_no,
                            next_count,
                            stale_rounds,
                        )

                        break

                final_count = cards.count()

                logger.info(
                    "ZIGZAG ranking render finished "
                    "url=%s "
                    "initial_count=%s "
                    "final_count=%s "
                    "limit=%s",
                    url,
                    initial_count,
                    final_count,
                    limit,
                )

                html = page.content()

                context.close()
                browser.close()

                return html

        except ZigzagCollectError:
            raise

        except Exception as exc:
            logger.exception(
                "ZIGZAG browser rendering failed "
                "url=%s",
                url,
            )

            raise ZigzagCollectError(
                "ZIGZAG 브라우저 렌더링 실패: "
                f"{url} / {exc}"
            ) from exc