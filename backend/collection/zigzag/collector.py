from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import (
    parse_qs,
    urljoin,
    urlparse,
)

from .client import ZigzagClient
from .constants import (
    DEFAULT_RANKING_LIMIT,
    DEFAULT_SCROLL_COUNT,
    PRODUCT_PAGE_URL,
    ZIGZAG_BASE_URL,
)
from .exceptions import (
    ZigzagCollectError,
)
from .parser import ZigzagParser


class ZigzagCollector:
    """
    ZIGZAG source-level collector.

    PRODUCT:
    - 상품 상세 HTML
    - 브랜드 대신 입점 쇼핑몰
    - 가격
    - 카테고리
    - 상품 이미지
    - 상세 HTML/이미지

    RANKING:
    - Playwright 목록 렌더링
    - 랭킹 상품 발견
    - 각 상품 상세 수집

    저장(S3/DB), Celery는 하지 않는다.
    """

    PRODUCT_PATTERN = re.compile(
        r"/catalog/products/(\d+)"
    )

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session=None,
    ):
        self.client = ZigzagClient(
            timeout=timeout,
            session=session,
        )

    def close(self) -> None:
        self.client.close()

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
    # PRODUCT URL DISCOVERY
    # ============================================================

    def discover_product_urls(
        self,
        target_url: str,
    ) -> list[str]:
        if not target_url:
            return []

        if self.PRODUCT_PATTERN.search(
            target_url
        ):
            return [
                self._normalize_product_url(
                    target_url
                )
            ]

        return [
            item["product_url"]
            for item in self.discover_ranking(
                target_url
            )
        ]

    # ============================================================
    # PRODUCT
    # ============================================================

    def collect_product(
        self,
        product: str | int,
    ) -> dict:
        product_id = self.extract_product_id(
            product
        )

        product_url = (
            PRODUCT_PAGE_URL.format(
                product_id=product_id,
            )
        )

        response = self.client.get_html(
            product_url
        )

        parsed = ZigzagParser.parse_product(
            response.text,
            product_id=product_id,
        )

        result = {
            "schema_version": "1.0",
            "source": "ZIGZAG",
            "entity_type": "PRODUCT",
            "source_product_id": str(
                product_id
            ),
            "source_url": str(
                response.url
            ),
            "collected_at": (
                datetime.now()
                .astimezone()
                .isoformat()
            ),
            "http_status": (
                response.status_code
            ),
            "content_type": (
                response.headers.get(
                    "Content-Type"
                )
            ),
            **parsed,
        }

        return result

    # ============================================================
    # RANKING
    # ============================================================

    def discover_ranking(
        self,
        target_url: str,
        *,
        limit: int | None = (
            DEFAULT_RANKING_LIMIT
        ),
        scroll_count: int = (
            DEFAULT_SCROLL_COUNT
        ),
    ) -> list[dict]:
        """
        Zigzag 카테고리 인기순 페이지를 브라우저로 렌더링하고,
        각 상품의 product_id / URL / rank를 반환한다.
        """

        if not target_url:
            raise ZigzagCollectError(
                "ZIGZAG RANKING URL이 없습니다."
            )

        html = (
            self.client.render_html(
                target_url,
                limit=limit,
                scroll_count=scroll_count,
            )
        )

        result = (
            ZigzagParser.parse_ranking(
                html
            )
        )

        scope = (
            self._parse_ranking_scope(
                target_url
            )
        )

        output: list[dict] = []

        for item in result:
            context = {
                **item,
                "ranking_category_id":
                    scope.get(
                        "category_id"
                    ),
            }

            output.append(
                context
            )

            if (
                limit is not None
                and len(output)
                >= limit
            ):
                break

        return output

    # ============================================================
    # PRODUCT ID / URL
    # ============================================================

    @classmethod
    def extract_product_id(
        cls,
        value: str | int,
    ) -> int:
        if isinstance(
            value,
            int,
        ):
            return value

        text = str(
            value
        ).strip()

        if text.isdigit():
            return int(
                text
            )

        absolute = urljoin(
            ZIGZAG_BASE_URL,
            text,
        )

        path = urlparse(
            absolute
        ).path

        match = (
            cls.PRODUCT_PATTERN.search(
                path
            )
        )

        if not match:
            raise ZigzagCollectError(
                "ZIGZAG 상품 ID를 "
                f"찾을 수 없습니다: {value}"
            )

        return int(
            match.group(1)
        )

    @classmethod
    def _normalize_product_url(
        cls,
        url: str,
    ) -> str:
        product_id = (
            cls.extract_product_id(
                url
            )
        )

        return (
            PRODUCT_PAGE_URL.format(
                product_id=product_id
            )
        )

    # ============================================================
    # RANKING SCOPE
    # ============================================================

    @staticmethod
    def _parse_ranking_scope(
        target_url: str,
    ) -> dict:
        query = parse_qs(
            urlparse(
                target_url
            ).query,
            keep_blank_values=True,
        )

        category_values = (
            query.get(
                "category_id"
            )
            or query.get(
                "middle_category_id"
            )
            or []
        )

        category_id = (
            category_values[0]
            if category_values
            else None
        )

        return {
            "category_id":
                category_id,
        }
