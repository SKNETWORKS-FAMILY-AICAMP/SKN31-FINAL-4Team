from __future__ import annotations

from urllib.parse import urlparse

from .client import AblyClient
from .constants import (
    DEFAULT_MAX_RANK,
    DEFAULT_MAX_REQUESTS,
    RANKING_PAGE_URL,
    RANKING_GOODS_API_URL,
)
from .exceptions import AblyCollectError, AblyParseError
from .parser import AblyParser


class AblyCollector:
    """ABLY cursor 기반 랭킹 수집기. S3와 DB에는 접근하지 않는다."""

    API_PARAM_NAMES = (
        "filter",
        "market_type_sno",
        "category_sno",
        "period",
    )

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session=None,
        client: AblyClient | None = None,
    ):
        self.client = client or AblyClient(timeout=timeout, session=session)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def collect_ranking(
        self,
        target_url: str,
        *,
        params: dict | None = None,
    ) -> dict:
        self._validate_target_url(target_url)
        params = dict(params or {})
        max_rank = self._positive_int(
            params.get("max_rank", DEFAULT_MAX_RANK), name="max_rank"
        )
        max_requests = self._positive_int(
            params.get("max_requests", DEFAULT_MAX_REQUESTS),
            name="max_requests",
        )
        request_params = self._build_request_params(params)

        products: list[dict] = []
        errors: list[dict] = []
        seen_snos: set[str] = set()
        previous_cursor: tuple[int, int] | None = None
        last_ranking: int | None = None
        completion_reason: str | None = None
        crawl_complete = False
        request_count = 0
        parsed_page_count = 0

        for request_number in range(1, max_requests + 1):
            request_count = request_number
            page_params = list(request_params)
            if previous_cursor is not None:
                page_params.extend(
                    [
                        ("last_ranking", previous_cursor[0]),
                        ("last_sno", previous_cursor[1]),
                    ]
                )

            try:
                body = self.client.get_ranking_goods(params=page_params)
                raw_goods = AblyParser.parse_goods_page(body)
                parsed_page_count += 1
            except (AblyCollectError, AblyParseError) as exc:
                if not products:
                    raise
                errors.append(self._error_record("PAGE", exc, request_number))
                completion_reason = "PAGE_ERROR"
                break

            if not raw_goods:
                crawl_complete = True
                completion_reason = "EMPTY_PAGE"
                break

            page_last_raw = raw_goods[-1]
            if not isinstance(page_last_raw, dict):
                errors.append(
                    {
                        "stage": "PAGINATION",
                        "request_number": request_number,
                        "error_type": "InvalidCursorItem",
                        "error_message": "마지막 goods 항목이 object가 아닙니다.",
                    }
                )
                completion_reason = "INVALID_CURSOR"
                break
            cursor_rank = AblyParser._to_int(page_last_raw.get("ranking"))
            cursor_sno = AblyParser._to_int(page_last_raw.get("sno"))

            if cursor_rank is None or cursor_sno is None:
                errors.append(
                    {
                        "stage": "PAGINATION",
                        "request_number": request_number,
                        "error_type": "InvalidCursor",
                        "error_message": "마지막 상품의 ranking 또는 sno가 없습니다.",
                    }
                )
                completion_reason = "INVALID_CURSOR"
                break

            current_cursor = (cursor_rank, cursor_sno)
            if previous_cursor is not None and (
                current_cursor == previous_cursor
                or cursor_rank <= previous_cursor[0]
            ):
                errors.append(
                    {
                        "stage": "PAGINATION",
                        "request_number": request_number,
                        "error_type": "CursorNotAdvanced",
                        "error_message": "ABLY pagination cursor가 증가하지 않았습니다.",
                    }
                )
                completion_reason = "CURSOR_NOT_ADVANCED"
                break

            for raw in raw_goods:
                if len(products) >= max_rank:
                    break
                try:
                    parsed = AblyParser.parse_goods(raw)
                except AblyParseError as exc:
                    errors.append(self._error_record("PRODUCT", exc, request_number))
                    continue

                source_product_id = parsed["source_product_id"]
                if source_product_id in seen_snos:
                    continue
                seen_snos.add(source_product_id)
                products.append(parsed)

            last_ranking = cursor_rank
            previous_cursor = current_cursor

            if len(products) >= max_rank:
                crawl_complete = not errors
                completion_reason = "MAX_RANK_REACHED"
                break
        else:
            errors.append(
                {
                    "stage": "PAGINATION",
                    "request_number": max_requests,
                    "error_type": "MaxRequestsExceeded",
                    "error_message": "ABLY max_requests 안에 수집을 완료하지 못했습니다.",
                }
            )
            completion_reason = "MAX_REQUESTS_EXCEEDED"

        if errors:
            crawl_complete = False

        return {
            "ranking": {
                "filter": self._param_value(request_params, "filter"),
                "target_url": target_url,
                "api_url": RANKING_GOODS_API_URL,
                "market_type_sno": self._param_value(
                    request_params, "market_type_sno"
                ),
                "category_sno": self._param_value(request_params, "category_sno"),
                "period": self._param_value(request_params, "period"),
                "age_tags": [
                    value for key, value in request_params if key == "age_tags[]"
                ],
                "requested_max_rank": max_rank,
                "crawl_complete": crawl_complete,
                "completion_reason": completion_reason,
                "request_count": request_count,
                "raw_page_count": parsed_page_count,
                "last_ranking": last_ranking,
                "discovered_count": len(products),
                "success_count": len(products),
                "failure_count": len(errors),
            },
            "products": products,
            "errors": errors,
        }

    @classmethod
    def _build_request_params(cls, params: dict) -> list[tuple[str, object]]:
        result: list[tuple[str, object]] = []
        for name in cls.API_PARAM_NAMES:
            value = params.get(name)
            if value is not None and value != "":
                if isinstance(value, (dict, list, tuple, set)):
                    raise ValueError(f"ABLY params.{name}은 단일 값이어야 합니다.")
                result.append((name, value))

        if not any(key == "filter" for key, _ in result):
            result.append(("filter", "best"))

        age_tags = params.get("age_tags", params.get("age_tags[]"))
        if age_tags is not None and age_tags != "" and age_tags != 0 and age_tags != "0":
            values = age_tags if isinstance(age_tags, (list, tuple)) else [age_tags]
            for value in values:
                if value is not None and value != "" and value != 0 and value != "0":
                    if isinstance(value, (dict, list, tuple, set)):
                        raise ValueError("ABLY age_tags 항목은 단일 값이어야 합니다.")
                    result.append(("age_tags[]", value))

        return result

    @staticmethod
    def _param_value(params: list[tuple[str, object]], name: str):
        for key, value in params:
            if key == name:
                return value
        return None

    @staticmethod
    def _positive_int(value, *, name: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"ABLY {name}은 정수여야 합니다.") from exc
        if parsed <= 0:
            raise ValueError(f"ABLY {name}은 1 이상이어야 합니다.")
        return parsed

    @staticmethod
    def _validate_target_url(target_url: str) -> None:
        expected = urlparse(RANKING_PAGE_URL)
        actual = urlparse(target_url)
        if (
            actual.scheme != "https"
            or actual.hostname != expected.hostname
            or actual.path.rstrip("/") != expected.path.rstrip("/")
        ):
            raise ValueError(
                "ABLY RANKING target_url은 "
                f"{RANKING_PAGE_URL} 이어야 합니다."
            )

    @staticmethod
    def _error_record(stage: str, exc: Exception, request_number: int) -> dict:
        return {
            "stage": stage,
            "request_number": request_number,
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
        }
