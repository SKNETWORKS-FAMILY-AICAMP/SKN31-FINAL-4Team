from __future__ import annotations

import random
import time
from typing import Any

import requests


REVIEW_ENDPOINT = (
    "https://api.zigzag.kr/api/2/graphql/GetNormalReviewFeedList"
)

DEFAULT_REVIEW_LIMIT = 20
DEFAULT_REVIEW_MIN_DELAY = 0.2
DEFAULT_REVIEW_MAX_DELAY = 0.5


GET_NORMAL_REVIEW_FEED_LIST_QUERY = """
query GetNormalReviewFeedList(
  $product_id: ID!
  $limit_count: Int
  $skip_count: Int
  $order: UxReviewListOrderType
) {
  feed_list: ux_review_list(
    input: {
      product_id: $product_id
      order: $order
      pagination: {
        limit_count: $limit_count
        skip_count: $skip_count
      }
    }
  ) {
    total_count

    item_list {
      id
      product_id
      type
      contents
      date_created
      date_updated
      rating
      like_count
      additional_description
      country

      image_list {
        id
        original_url
        thumbnail_url
      }

      video_list {
        id
        url
        thumbnail_url
      }

      attribute_list {
        question {
          label
          value
          category
        }
        answer {
          label
          value
        }
      }

      reviewer {
        body_text
        reviewer_id

        profile {
          nickname
          masked_email
        }
      }

      product_info {
        option_detail_list {
          name
          value
        }
      }
    }
  }
}
""".strip()


class ZigzagReviewError(RuntimeError):
    pass


class ZigzagReviewCollector:
    """
    Zigzag 상품 리뷰 수집기.

    정책:
    - 상품당 현재 리뷰 페이지 1회 수집
    - 최대 20개
    - 요청한 product_id와 동일한 리뷰만 저장
    - 다른 상품 리뷰는 제외
    - survey는 question/answer 전체 객체를 반복 저장하지 않고
      question.value -> answer.value 형태로 압축
    """

    def __init__(
        self,
        *,
        min_delay: float = DEFAULT_REVIEW_MIN_DELAY,
        max_delay: float = DEFAULT_REVIEW_MAX_DELAY,
        timeout: int = 20,
        session: requests.Session | None = None,
    ):
        self.min_delay = float(min_delay)
        self.max_delay = float(max_delay)

        if (
            self.min_delay < 0
            or self.max_delay < self.min_delay
        ):
            raise ValueError(
                "Zigzag review delay 범위가 올바르지 않습니다."
            )

        self.timeout = int(timeout)

        self.session = (
            session
            or requests.Session()
        )

        self.session.headers.update(
            {
                "Accept":
                    "application/json, text/plain, */*",

                "Content-Type":
                    "application/json",

                "Origin":
                    "https://zigzag.kr",

                "Referer":
                    "https://zigzag.kr/",

                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/152.0.0.0 "
                    "Safari/537.36"
                ),
            }
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
    # PUBLIC
    # ============================================================

    def collect_reviews(
        self,
        product_id: str | int,
        *,
        limit: int = DEFAULT_REVIEW_LIMIT,
        order: str = "SCORE_DESC",
    ) -> dict:
        limit = self._validate_limit(
            limit
        )

        requested_product_id = (
            self._clean_id(product_id)
        )

        if requested_product_id is None:
            raise ValueError(
                "Zigzag review product_id가 없습니다."
            )

        if self.max_delay:
            time.sleep(
                random.uniform(
                    self.min_delay,
                    self.max_delay,
                )
            )

        payload = {
            "operationName":
                "GetNormalReviewFeedList",

            "variables": {
                "product_id":
                    requested_product_id,

                "limit_count":
                    limit,

                "skip_count":
                    0,

                "order":
                    order,
            },

            "query":
                GET_NORMAL_REVIEW_FEED_LIST_QUERY,
        }

        body = self._post(
            payload
        )

        return self._normalize_bundle(
            body,
            requested_product_id=(
                requested_product_id
            ),
            limit=limit,
        )

    # ============================================================
    # HTTP
    # ============================================================

    def _post(
        self,
        payload: dict,
        *,
        max_retries: int = 3,
    ) -> dict:
        last_error: Exception | None = None

        for attempt in range(
            max_retries + 1
        ):
            try:
                response = (
                    self.session.post(
                        REVIEW_ENDPOINT,
                        json=payload,
                        timeout=self.timeout,
                    )
                )

                if (
                    response.status_code == 429
                    and attempt < max_retries
                ):
                    retry_after = (
                        response.headers.get(
                            "Retry-After"
                        )
                    )

                    try:
                        wait_seconds = (
                            float(retry_after)
                            if retry_after
                            else 0.0
                        )

                    except ValueError:
                        wait_seconds = 0.0

                    time.sleep(
                        wait_seconds
                        if wait_seconds > 0
                        else (
                            min(
                                30.0,
                                2 ** attempt,
                            )
                            + random.uniform(
                                0.3,
                                1.0,
                            )
                        )
                    )

                    continue

                response.raise_for_status()

                body = response.json()

                if not isinstance(
                    body,
                    dict,
                ):
                    raise ZigzagReviewError(
                        "Zigzag review 응답이 "
                        "object가 아닙니다."
                    )

                if body.get("errors"):
                    raise ZigzagReviewError(
                        "Zigzag review "
                        "GraphQL errors: "
                        f"{body['errors']}"
                    )

                return body

            except (
                requests.RequestException,
                ValueError,
                ZigzagReviewError,
            ) as exc:
                last_error = exc

                if attempt >= max_retries:
                    break

                time.sleep(
                    min(
                        30.0,
                        2 ** attempt,
                    )
                    + random.uniform(
                        0.3,
                        1.0,
                    )
                )

        raise ZigzagReviewError(
            "Zigzag review request failed: "
            f"{last_error}"
        ) from last_error

    # ============================================================
    # NORMALIZE BUNDLE
    # ============================================================

    @classmethod
    def _normalize_bundle(
        cls,
        body: dict,
        *,
        requested_product_id: str,
        limit: int,
    ) -> dict:
        data = body.get(
            "data"
        )

        feed = (
            data.get("feed_list")
            if isinstance(data, dict)
            else None
        )

        if not isinstance(
            feed,
            dict,
        ):
            raise ZigzagReviewError(
                "Zigzag review "
                "data.feed_list가 없습니다."
            )

        raw_items = feed.get(
            "item_list"
        )

        if not isinstance(
            raw_items,
            list,
        ):
            raise ZigzagReviewError(
                "Zigzag review "
                "item_list가 list가 아닙니다."
            )

        normalized_items: list[dict] = []

        mismatched_count = 0
        missing_product_id_count = 0

        for raw in raw_items:
            if not isinstance(
                raw,
                dict,
            ):
                continue

            review_product_id = (
                cls._clean_id(
                    raw.get(
                        "product_id"
                    )
                )
            )

            # ----------------------------------------------------
            # product_id가 없는 리뷰
            # ----------------------------------------------------

            if review_product_id is None:
                missing_product_id_count += 1
                continue

            # ----------------------------------------------------
            # 요청 상품과 다른 상품 리뷰
            # ----------------------------------------------------

            if (
                review_product_id
                != requested_product_id
            ):
                mismatched_count += 1
                continue

            normalized_items.append(
                cls._normalize_review(
                    raw
                )
            )

            if (
                len(normalized_items)
                >= limit
            ):
                break

        return {
            "summary": {
                # Zigzag API가 알려준 전체 리뷰 수
                "total_count":
                    cls._to_int(
                        feed.get(
                            "total_count"
                        )
                    ),

                # 이번 API 응답에 실제 포함된 개수
                "response_item_count":
                    len(raw_items),

                # product_id 검증 후 실제 저장 개수
                "collected_count":
                    len(
                        normalized_items
                    ),

                # 다른 상품이라 제외한 리뷰 수
                "mismatched_product_count":
                    mismatched_count,

                # product_id가 없어 제외한 리뷰 수
                "missing_product_id_count":
                    missing_product_id_count,
            },

            "items":
                normalized_items,
        }

    # ============================================================
    # NORMALIZE REVIEW
    # ============================================================

    @classmethod
    def _normalize_review(
        cls,
        raw: Any,
    ) -> dict:
        if (
            not isinstance(
                raw,
                dict,
            )
            or raw.get("id") in (
                None,
                "",
            )
        ):
            raise ZigzagReviewError(
                "Zigzag review 항목의 "
                "id가 없습니다."
            )

        reviewer = raw.get(
            "reviewer"
        )

        reviewer = (
            reviewer
            if isinstance(
                reviewer,
                dict,
            )
            else {}
        )

        profile = reviewer.get(
            "profile"
        )

        profile = (
            profile
            if isinstance(
                profile,
                dict,
            )
            else {}
        )

        product_info = raw.get(
            "product_info"
        )

        product_info = (
            product_info
            if isinstance(
                product_info,
                dict,
            )
            else {}
        )

        return {
            "source_review_id":
                str(raw["id"]),

            "source_product_id":
                cls._clean_id(
                    raw.get(
                        "product_id"
                    )
                ),

            "review_type":
                raw.get(
                    "type"
                ),

            "content":
                raw.get(
                    "contents"
                ),

            "grade":
                cls._to_float(
                    raw.get(
                        "rating"
                    )
                ),

            "like_count":
                cls._to_int(
                    raw.get(
                        "like_count"
                    )
                ),

            "created_at":
                raw.get(
                    "date_created"
                ),

            "updated_at":
                raw.get(
                    "date_updated"
                ),

            "additional_description":
                raw.get(
                    "additional_description"
                ),

            "country":
                raw.get(
                    "country"
                ),

            "images": (
                raw.get(
                    "image_list"
                )
                if isinstance(
                    raw.get(
                        "image_list"
                    ),
                    list,
                )
                else []
            ),

            "videos": (
                raw.get(
                    "video_list"
                )
                if isinstance(
                    raw.get(
                        "video_list"
                    ),
                    list,
                )
                else []
            ),

            "goods_option": (
                product_info.get(
                    "option_detail_list"
                )
                or []
            ),

            "survey":
                cls._normalize_survey(
                    raw.get(
                        "attribute_list"
                    )
                ),

            "reviewer": {
                "source_reviewer_id":
                    cls._clean_id(
                        reviewer.get(
                            "reviewer_id"
                        )
                    ),

                "body_text":
                    reviewer.get(
                        "body_text"
                    ),

                "nickname":
                    profile.get(
                        "nickname"
                    ),

                "masked_email":
                    profile.get(
                        "masked_email"
                    ),
            },
        }

    # ============================================================
    # SURVEY
    # ============================================================

    @classmethod
    def _normalize_survey(
        cls,
        value: Any,
    ) -> dict[str, str]:
        """
        Zigzag 원본:

        [
            {
                "question": {
                    "label": "...",
                    "value": "SIZE",
                    "category": "..."
                },
                "answer": {
                    "label": "...",
                    "value": "FIT"
                }
            }
        ]

        저장:

        {
            "SIZE": "FIT"
        }
        """

        if not isinstance(
            value,
            list,
        ):
            return {}

        survey: dict[str, str] = {}

        for row in value:
            if not isinstance(
                row,
                dict,
            ):
                continue

            question = row.get(
                "question"
            )

            answer = row.get(
                "answer"
            )

            if not isinstance(
                question,
                dict,
            ):
                continue

            if not isinstance(
                answer,
                dict,
            ):
                continue

            question_code = (
                question.get(
                    "value"
                )
            )

            answer_code = (
                answer.get(
                    "value"
                )
            )

            if question_code in (
                None,
                "",
            ):
                continue

            if answer_code in (
                None,
                "",
            ):
                continue

            survey[
                str(question_code)
            ] = str(answer_code)

        return survey

    # ============================================================
    # VALIDATION
    # ============================================================

    @staticmethod
    def _validate_limit(
        value: Any,
    ) -> int:
        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "Zigzag review_limit은 "
                "양의 정수여야 합니다."
            )

        try:
            parsed = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Zigzag review_limit은 "
                "양의 정수여야 합니다."
            ) from exc

        if (
            parsed <= 0
            or parsed
            > DEFAULT_REVIEW_LIMIT
        ):
            raise ValueError(
                "Zigzag review_limit은 "
                f"1~{DEFAULT_REVIEW_LIMIT}"
                "여야 합니다."
            )

        return parsed

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _clean_id(
        value: Any,
    ) -> str | None:
        return (
            None
            if value in (
                None,
                "",
            )
            else str(value)
        )

    @staticmethod
    def _to_int(
        value: Any,
    ) -> int | None:
        if (
            value is None
            or isinstance(
                value,
                bool,
            )
        ):
            return None

        try:
            return int(
                float(
                    str(value)
                    .replace(",", "")
                    .strip()
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_float(
        value: Any,
    ) -> float | None:
        if (
            value is None
            or isinstance(
                value,
                bool,
            )
        ):
            return None

        try:
            return float(
                str(value)
                .replace(",", "")
                .strip()
            )

        except (
            TypeError,
            ValueError,
        ):
            return None