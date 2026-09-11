from __future__ import annotations

import re
import unicodedata
from typing import Iterable


class ProductNamePreprocessor:
    """
    FEEDIT 공통 상품명 1차 파서.

    목적
    ----
    RAW 상품명 -> 사람이 읽기 쉬운 source_name + 분석용 tags

    원칙
    ----
    1) [] / () / {} / <> 내부 표현은 버리지 않고 tags로 보존
    2) 괄호 밖 "/" 뒤의 부가 표현도 tags로 보존
    3) " / 영문 상품명" 형태는 alternate_names로 보존
    4) " - 옵션" 형태는 suffix_terms로 보존
    5) 기존 플랫폼 tags는 절대 덮어쓰지 않고 추출 tags를 뒤에 append
    6) 이 단계에서는 DictionaryTerm/속성 의미 판정을 하지 않음
    7) normalized_name은 이 단계에서 생성하지 않음
    """

    BLOCK_PATTERNS = {
        "square_blocks": re.compile(r"\[([^\]]*)\]"),
        "round_blocks": re.compile(r"\(([^)]*)\)"),
        "curly_blocks": re.compile(r"\{([^}]*)\}"),
        "angle_blocks": re.compile(r"<([^>]*)>"),
    }

    BLOCK_REMOVE_RE = re.compile(
        r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|<[^>]*>"
    )

    EMOJI_RE = re.compile(
        "["
        "\U0001F300-\U0001FAFF"
        "\U00002700-\U000027BF"
        "\U00002600-\U000026FF"
        "\uFE0F"
        "]",
        flags=re.UNICODE,
    )

    MULTISPACE_RE = re.compile(r"\s+")
    TAG_SEPARATOR_RE = re.compile(r"[/|,·•]+")
    SPACED_DASH_RE = re.compile(r"\s+-\s+")

    # 괄호 밖 "_" 뒤에 붙는 대표적인 옵션/컬러 표현.
    COLOR_OR_OPTION_SUFFIX_RE = re.compile(
        r"^(?:"
        r"블랙|화이트|아이보리|오프화이트|크림|베이지|브라운|카멜|"
        r"그레이|차콜|네이비|블루|스카이블루|소라|데님|"
        r"레드|와인|버건디|핑크|퍼플|라벤더|그린|카키|민트|"
        r"옐로우|오렌지|실버|골드|"
        r"black|white|ivory|cream|beige|brown|camel|gray|grey|"
        r"charcoal|navy|blue|red|wine|burgundy|pink|purple|green|"
        r"khaki|mint|yellow|orange|silver|gold|"
        r"\d+\s*(?:color|colors|컬러)|"
        r"[xsml]{1,4}|free|f"
        r")$",
        re.IGNORECASE,
    )

    @classmethod
    def normalize_unicode(cls, text: str | None) -> str:
        if not text:
            return ""
        return unicodedata.normalize("NFKC", str(text))

    @classmethod
    def clean_token(cls, text: str | None) -> str:
        text = cls.normalize_unicode(text)
        text = cls.EMOJI_RE.sub("", text)
        text = cls.MULTISPACE_RE.sub(" ", text)
        return text.strip(" _-/|·•,.:;!?~\'\\\"")

    @classmethod
    def _dedupe(cls, values: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for value in values:
            value = cls.clean_token(value)
            if not value:
                continue

            key = value.casefold()
            if key in seen:
                continue

            seen.add(key)
            result.append(value)

        return result

    @classmethod
    def _split_tag_text(cls, text: str | None) -> list[str]:
        text = cls.normalize_unicode(text)
        if not text:
            return []

        # 괄호 내부 emoji는 장식이면서 실질적인 구분자로 쓰이는 경우가 많다.
        # 예: "가을🍁직진배송/2천장돌파"
        #     -> 가을 / 직진배송 / 2천장돌파
        text = cls.EMOJI_RE.sub("/", text)

        parts = cls.TAG_SEPARATOR_RE.split(text)
        return cls._dedupe(parts)

    @classmethod
    def _looks_like_english_alternate_name(cls, text: str) -> bool:
        """
        '/ LINA SHIRRING WINDBREAKER JUMPER_CHARCOAL'
        같은 영문 중복 상품명을 tag로 만들지 않기 위한 휴리스틱.
        """
        text = cls.clean_token(text)
        if not text:
            return False

        letters = re.findall(r"[A-Za-z]", text)
        visible = re.findall(r"[A-Za-z가-힣0-9]", text)

        if not visible:
            return False

        english_ratio = len(letters) / len(visible)
        word_count = len(re.findall(r"[A-Za-z]+", text))

        return english_ratio >= 0.75 and word_count >= 2

    @classmethod
    def _extract_blocks(cls, text: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}

        for key, pattern in cls.BLOCK_PATTERNS.items():
            values = []

            for value in pattern.findall(text):
                value = cls.normalize_unicode(value).strip()

                if value:
                    values.append(value)

            result[key] = values

        return result

    @classmethod
    def parse(
        cls,
        text: str | None,
        *,
        existing_tags: Iterable[str] | None = None,
        source_code: str | None = None,
    ) -> dict:
        """
        공통 파서.

        source_code는 현재 결과 포맷을 바꾸지 않는다.
        추후 플랫폼별 아주 제한적인 예외 규칙을 넣기 위한 profile 값이다.
        """
        original_name = cls.normalize_unicode(text)
        existing_tags = list(existing_tags or [])

        if not original_name.strip():
            return {
                "source_name": "",
                "tags": cls._dedupe(existing_tags),
                "source_name_meta": {
                    "version": 1,
                    "source_code": (source_code or "").upper() or None,
                    "original_name": original_name,
                    "square_blocks": [],
                    "round_blocks": [],
                    "curly_blocks": [],
                    "angle_blocks": [],
                    "slash_terms": [],
                    "suffix_terms": [],
                    "alternate_names": [],
                    "extracted_tags": [],
                },
            }

        blocks = cls._extract_blocks(original_name)

        extracted_tags: list[str] = []
        for block_values in blocks.values():
            for block in block_values:
                extracted_tags.extend(cls._split_tag_text(block))

        # 블록 제거 후 본문만 남긴다.
        body = cls.BLOCK_REMOVE_RE.sub(" ", original_name)
        body = cls.EMOJI_RE.sub(" ", body)
        body = re.sub(r"[©®™]", " ", body)
        body = cls.MULTISPACE_RE.sub(" ", body).strip()

        alternate_names: list[str] = []
        slash_terms: list[str] = []
        suffix_terms: list[str] = []

        # 괄호 밖 "/" 처리.
        slash_parts = [p.strip() for p in body.split("/")]

        if slash_parts:
            core = slash_parts[0]

            for part in slash_parts[1:]:
                part = cls.clean_token(part)
                if not part:
                    continue

                if cls._looks_like_english_alternate_name(part):
                    alternate_names.append(part)
                else:
                    slash_terms.append(part)
                    extracted_tags.append(part)
        else:
            core = body

        # "상품명 - 옵션/타입"은 우측을 tag로 이동.
        dash_parts = cls.SPACED_DASH_RE.split(core, maxsplit=1)
        if len(dash_parts) == 2:
            left = cls.clean_token(dash_parts[0])
            right = cls.clean_token(dash_parts[1])

            # A-라인, MA-1 같은 내부 하이픈에는 반응하지 않고
            # 공백 dash(" - ")만 처리한다.
            core = left
            if right:
                suffix_terms.append(right)
                extracted_tags.append(right)

        # "_차콜" 같은 대표적인 끝 옵션만 분리.
        if "_" in core:
            left, right = core.rsplit("_", 1)
            right_clean = cls.clean_token(right)

            if (
                right_clean
                and cls.COLOR_OR_OPTION_SUFFIX_RE.fullmatch(right_clean)
            ):
                core = cls.clean_token(left)
                suffix_terms.append(right_clean)
                extracted_tags.append(right_clean)

        source_name = cls.clean_token(core)

        extracted_tags = cls._dedupe(extracted_tags)

        # 핵심: 기존 무신사/플랫폼 태그를 먼저 유지하고,
        # 상품명에서 새로 추출한 태그를 뒤에 append한다.
        merged_tags = cls._dedupe(
            [*existing_tags, *extracted_tags]
        )

        return {
            "source_name": source_name,
            "tags": merged_tags,
            "source_name_meta": {
                "version": 1,
                "source_code": (source_code or "").upper() or None,
                "original_name": original_name,
                "square_blocks": blocks["square_blocks"],
                "round_blocks": blocks["round_blocks"],
                "curly_blocks": blocks["curly_blocks"],
                "angle_blocks": blocks["angle_blocks"],
                "slash_terms": cls._dedupe(slash_terms),
                "suffix_terms": cls._dedupe(suffix_terms),
                "alternate_names": cls._dedupe(alternate_names),
                "extracted_tags": extracted_tags,
            },
        }

    # -----------------------------------------------------------------
    # 기존 코드 호환용.
    # 신규 코드는 parse() 사용 권장.
    # -----------------------------------------------------------------

    @classmethod
    def normalize(cls, text: str | None) -> str:
        return cls.parse(text)["source_name"]

    @classmethod
    def parse_zigzag(
        cls,
        text: str | None,
        *,
        existing_tags: Iterable[str] | None = None,
    ) -> dict:
        parsed = cls.parse(
            text,
            existing_tags=existing_tags,
            source_code="ZIGZAG",
        )
        meta = parsed["source_name_meta"]

        return {
            "source_name": parsed["source_name"],
            "tags": parsed["tags"],
            "square_blocks": meta["square_blocks"],
            "round_blocks": meta["round_blocks"],
            "source_name_meta": meta,
        }
