from __future__ import annotations

# ============================================================================
# marketing_detector.py
# ============================================================================
import re
from dataclasses import dataclass
from typing import Any
from django.db.models import Q

from apps.core.models import DiscoveryExclusion


@dataclass(frozen=True)
class MarketingMatch:
    raw: str
    normalized: str
    start: int
    end: int
    match_type: str
    source: str


class MarketingDetector:
    """
    상품명의 마케팅 / 프로모션 표현 탐지기.

    원칙
    ----
    1. 고정 표현
       -> DiscoveryExclusion(reason="MARKETING")

    2. 숫자 등이 계속 변하는 표현
       -> regex dynamic pattern

    3. MARKETING만 normalized_name에서 제거

    4. PRODUCT_META / SEASON / GENDER / Dictionary 후보는
       이 detector가 제거하지 않음

    5. source_name은 절대 수정하지 않음
    """

    # ============================================================
    # DYNAMIC MARKETING PATTERNS
    # ============================================================

    DYNAMIC_PATTERNS = (
        # --------------------------------------------------------
        # 30% 쿠폰
        # --------------------------------------------------------
        (
            "DISCOUNT_COUPON",
            re.compile(
                r"""
                \d{1,3}
                \s*%
                \s*쿠폰
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),

        # --------------------------------------------------------
        # [얼리어텀 32%]
        # [SALE 20%]
        #
        # 실제 적용은 _detect_dynamic_patterns에서
        # [] 내부인지 추가 검증한다.
        # --------------------------------------------------------
        (
            "DISCOUNT_RATE",
            re.compile(
                r"""
                (?<![\dA-Za-z])
                \d{1,2}
                \s*%
                (?!\s*쿠폰)
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),

        # --------------------------------------------------------
        # 20만장판매
        # 3천개 판매
        # 1000장판매
        # 20만장 판매완료
        # 20만장 판매돌파
        # --------------------------------------------------------
        (
            "SALES_COUNT_PROMO",
            re.compile(
                r"""
                \d+
                \s*
                (?:천|만)?
                \s*
                (?:장|개)
                \s*
                (?:판매돌파|판매완료|판매)
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),

        # --------------------------------------------------------
        # 1천장 돌파
        # 5만장 돌파
        # 1000장 돌파
        # 3만개 돌파
        # --------------------------------------------------------
        (
            "SALES_MILESTONE",
            re.compile(
                r"""
                \d+
                \s*
                (?:천|만)?
                \s*
                (?:장|개)
                \s*
                돌파
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),

        # --------------------------------------------------------
        # 누적5만장
        # 누적 3천개
        # 누적10000장
        # 누적5만장 판매
        # --------------------------------------------------------
        (
            "SALES_ACCUMULATED",
            re.compile(
                r"""
                누적
                \s*
                \d+
                \s*
                (?:천|만)?
                \s*
                (?:장|개)
                (?:\s*(?:판매돌파|판매완료|판매))?
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),

        # --------------------------------------------------------
        # 1등
        # 2위
        # --------------------------------------------------------
        (
            "RANK_PROMO",
            re.compile(
                r"""
                \d+
                \s*
                (?:등|위)
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),

        # --------------------------------------------------------
        # 단 3일
        # 단3일
        # --------------------------------------------------------
        (
            "LIMITED_DAYS",
            re.compile(
                r"""
                단
                \s*
                \d+
                \s*
                일
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),
    )

    # ============================================================
    # PUBLIC API
    # ============================================================

    @classmethod
    def detect(
        cls,
        text: str | None,
        *,
        source=None,
    ) -> list[MarketingMatch]:
        if not text:
            return []

        text = str(text)

        matches: list[MarketingMatch] = []

        matches.extend(
            cls._detect_exclusions(
                text,
                source=source,
            )
        )

        matches.extend(
            cls._detect_dynamic_patterns(text)
        )

        return cls._deduplicate(matches)

    @classmethod
    def normalize(
        cls,
        text: str | None,
        *,
        source=None,
    ) -> dict:
        """
        MARKETING 표현만 제거한 normalized_name을 반환한다.
        """

        if not text:
            return {
                "source_name": text,
                "normalized_name": text,
                "marketing": [],
            }

        text = str(text)

        matches = cls.detect(
            text,
            source=source,
        )

        normalized_name = cls._remove_matches(
            text,
            matches,
        )

        return {
            "source_name": text,
            "normalized_name": normalized_name,
            "marketing": matches,
        }

    # ============================================================
    # DISCOVERY EXCLUSION
    # ============================================================

    @classmethod
    def _detect_exclusions(
        cls,
        text: str,
        *,
        source=None,
    ) -> list[MarketingMatch]:
        qs = DiscoveryExclusion.objects.filter(
            reason="MARKETING",
            is_active=True,
        )

        if source is not None:
            qs = qs.filter(
                Q(source__isnull=True)
                | Q(source=source)
            )
        else:
            qs = qs.filter(
                source__isnull=True,
            )

        rows = list(qs)

        # 긴 표현 우선
        #
        # 무신사단독
        # 단독
        #
        # 둘 다 있으면 무신사단독이 먼저 잡힌다.
        rows.sort(
            key=lambda x: len(x.term or ""),
            reverse=True,
        )

        results: list[MarketingMatch] = []

        for row in rows:
            term = (row.term or "").strip()

            if not term:
                continue

            pattern = cls._term_pattern(term)

            for match in pattern.finditer(text):
                results.append(
                    MarketingMatch(
                        raw=match.group(0),
                        normalized=term.lower(),
                        start=match.start(),
                        end=match.end(),
                        match_type="MARKETING",
                        source="DISCOVERY_EXCLUSION",
                    )
                )

        return results

    # ============================================================
    # DYNAMIC PATTERNS
    # ============================================================

    @classmethod
    def _detect_dynamic_patterns(
        cls,
        text: str,
    ) -> list[MarketingMatch]:
        results: list[MarketingMatch] = []

        for pattern_name, pattern in cls.DYNAMIC_PATTERNS:
            for match in pattern.finditer(text):

                # ------------------------------------------------
                # 순수 할인율은 [] 내부에서만 MARKETING 처리.
                #
                # [얼리어텀 32%]
                #     -> 32% 제거
                #
                # 울 30% 니트
                # 캐시미어 20% 혼방
                #     -> 소재 함량일 수 있으므로 유지
                # ------------------------------------------------
                if pattern_name == "DISCOUNT_RATE":
                    if not cls._is_inside_square_bracket(
                        text,
                        match.start(),
                    ):
                        continue

                results.append(
                    MarketingMatch(
                        raw=match.group(0),
                        normalized=match.group(0).strip().lower(),
                        start=match.start(),
                        end=match.end(),
                        match_type=pattern_name,
                        source="PATTERN",
                    )
                )

        return results

    # ============================================================
    # CONTEXT
    # ============================================================

    @staticmethod
    def _is_inside_square_bracket(
        text: str,
        position: int,
    ) -> bool:
        """
        position이 현재 열려 있는 [] 내부인지 확인한다.

        [얼리어텀 32%]
              ^
              True

        울 30% 니트
          ^
          False
        """

        before = text[:position]

        last_open = before.rfind("[")
        last_close = before.rfind("]")

        if last_open <= last_close:
            return False

        # 현재 열린 [ 뒤에 실제 ]가 존재하는지도 확인.
        next_close = text.find("]", position)

        return next_close != -1

    # ============================================================
    # TERM MATCHING
    # ============================================================

    @staticmethod
    def _term_pattern(
        term: str,
    ) -> re.Pattern:
        """
        MARKETING 표현은 복합어 내부에서도 탐지한다.

        가을신상
            -> 신상

        가을BEST블라우스
            -> BEST

        당일출고/set
            -> 당일출고

        무신사단독
            -> 무신사단독

        긴 표현 우선 + deduplicate로 중복 span을 제거한다.
        """

        return re.compile(
            re.escape(term),
            re.IGNORECASE,
        )

    # ============================================================
    # REMOVE
    # ============================================================

    @classmethod
    def _remove_matches(
        cls,
        text: str,
        matches: list[MarketingMatch],
    ) -> str:
        if not matches:
            return cls._cleanup(text)

        result = text

        # 원래 문자열의 span이므로 반드시 뒤에서부터 제거
        for match in sorted(
            matches,
            key=lambda x: x.start,
            reverse=True,
        ):
            result = (
                result[:match.start]
                + " "
                + result[match.end:]
            )

        return cls._cleanup(result)

    # ============================================================
    # CLEANUP
    # ============================================================

    @staticmethod
    def _cleanup(
        text: str,
    ) -> str:
        """
        MARKETING 제거 후 생긴 문법적 찌꺼기만 정리한다.

        정보가 들어 있는 괄호 자체는 유지한다.

        예:

        [당일출고/set]
            -> [set]

        [단독/MADE]
            -> [MADE]

        [가을신상]
            -> [가을]

        [AUTUMN20%]
            -> [AUTUMN]

        [무료배송/3color]
            -> [3color]

        [주문폭주]
            -> 제거
        """

        # --------------------------------------------------------
        # 기본 whitespace
        # --------------------------------------------------------

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        # --------------------------------------------------------
        # 괄호 시작 직후 separator
        #
        # [ / set] -> [set]
        # ( / set) -> (set)
        # --------------------------------------------------------

        text = re.sub(
            r"([\[\(])\s*[/|｜]+\s*",
            r"\1",
            text,
        )

        # --------------------------------------------------------
        # 괄호 끝 직전 separator
        #
        # [MADE / ] -> [MADE]
        # --------------------------------------------------------

        text = re.sub(
            r"\s*[/|｜]+\s*([\]\)])",
            r"\1",
            text,
        )

        # --------------------------------------------------------
        # separator 사이에 내용이 삭제된 경우
        #
        # [가을 / / 블라우스]
        # -> [가을/블라우스]
        # --------------------------------------------------------

        text = re.sub(
            r"(?:\s*[/|｜]\s*){2,}",
            "/",
            text,
        )

        # --------------------------------------------------------
        # 괄호 내부 불필요 공백
        # --------------------------------------------------------

        text = re.sub(
            r"\[\s+",
            "[",
            text,
        )

        text = re.sub(
            r"\s+\]",
            "]",
            text,
        )

        text = re.sub(
            r"\(\s+",
            "(",
            text,
        )

        text = re.sub(
            r"\s+\)",
            ")",
            text,
        )

        # --------------------------------------------------------
        # 빈 괄호
        # --------------------------------------------------------

        text = re.sub(
            r"\[\s*\]",
            " ",
            text,
        )

        text = re.sub(
            r"\(\s*\)",
            " ",
            text,
        )

        # --------------------------------------------------------
        # 문자열 시작/끝 separator
        # --------------------------------------------------------

        text = re.sub(
            r"^\s*[/|｜]+\s*",
            "",
            text,
        )

        text = re.sub(
            r"\s*[/|｜]+\s*$",
            "",
            text,
        )

        # --------------------------------------------------------
        # 마케팅 제거 때문에 생긴 괄호 사이 불필요 공백
        # --------------------------------------------------------

        text = re.sub(
            r"\]\s+\[",
            "][",
            text,
        )

        # --------------------------------------------------------
        # 최종 whitespace
        # --------------------------------------------------------

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    # ============================================================
    # DEDUP
    # ============================================================

    @staticmethod
    def _deduplicate(
        matches: list[MarketingMatch],
    ) -> list[MarketingMatch]:
        # 같은 시작 위치라면 긴 표현 우선
        matches = sorted(
            matches,
            key=lambda x: (
                x.start,
                -(x.end - x.start),
            ),
        )

        result: list[MarketingMatch] = []
        occupied: list[tuple[int, int]] = []

        for match in matches:
            overlap = any(
                match.start < end
                and match.end > start
                for start, end in occupied
            )

            if overlap:
                continue

            result.append(match)

            occupied.append(
                (
                    match.start,
                    match.end,
                )
            )

        return sorted(
            result,
            key=lambda x: x.start,
        )

# ============================================================================
# size_detector.py
# ============================================================================
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SizeMatch:
    size_type: str
    raw: str
    normalized: str
    start: int
    end: int
    value: Any


class SizeDetector:
    """
    상품명에서 사이즈 관련 표현을 탐지한다.

    역할
    ----
    - FREE_SIZE_RANGE : FREE(55-66), F(44-77)
    - SIZE_VALUES     : S,M,L / S/M/L
    - SIZE_RANGE      : S~L / XS-XL / 44~110 / 25-38
    - SIZE_OPTION     : XXL 추가 / 기장선택
    - SIZE_COUNT      : 2사이즈 / 3SIZE
    - SIZE_VALUE      : 사이즈 240 / 240mm
    - BARE_NUMERIC    : musinsa_used 전용 숫자 사이즈

    주의
    ----
    source_name / normalized_name을 직접 수정하지 않는다.
    구조화된 span만 반환한다.

    bare numeric size는 allow_bare_numeric=True일 때만 탐지한다.
    """

    # 영문 풀네임 사이즈까지 canonical alpha size로 통합한다.
    # 긴 표현을 먼저 둬 SMALL의 S, LARGE의 L 같은 부분 매칭을 방지한다.
    ALPHA_SIZE = (
        r"(?:"
        r"EXTRA\s*SMALL|X[-\s]?SMALL|XSMALL|"
        r"EXTRA\s*LARGE|X[-\s]?LARGE|XLARGE|"
        r"SMALL|MEDIUM|LARGE|"
        r"XXXS|XXS|XS|XXXL|XXL|XL|"
        r"FREE|S|M|L|F"
        r")"
    )

    ALPHA_SIZE_MAP = {
        "SMALL": "S",
        "MEDIUM": "M",
        "LARGE": "L",
        "XSMALL": "XS",
        "X-SMALL": "XS",
        "EXTRA SMALL": "XS",
        "XLARGE": "XL",
        "X-LARGE": "XL",
        "EXTRA LARGE": "XL",
        "FREE": "FREE",
        "F": "F",
        "S": "S",
        "M": "M",
        "L": "L",
        "XS": "XS",
        "XXS": "XXS",
        "XXXS": "XXXS",
        "XL": "XL",
        "XXL": "XXL",
        "XXXL": "XXXL",
    }

    FREE_SIZE_RANGE = re.compile(
        r"""
        (?<![A-Za-z])
        (?P<label>FREE|F)
        \s*
        \(
            \s*
            (?P<min>\d{2,3})
            \s*
            [-~～]
            \s*
            (?P<max>\d{2,3})
            \s*
        \)
        (?![A-Za-z])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    SIZE_RANGE_ALPHA = re.compile(
        rf"""
        (?<![A-Za-z])
        (?P<min>{ALPHA_SIZE})
        \s*
        (?P<separator>[-~～])
        \s*
        (?P<max>{ALPHA_SIZE})
        (?![A-Za-z])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    SIZE_RANGE_NUMERIC = re.compile(
        r"""
        (?<!\d)
        (?P<min>\d{2,3})
        \s*
        (?P<separator>[-~～])
        \s*
        (?P<max>\d{2,3})
        (?!\d)
        """,
        re.VERBOSE,
    )

    # L사이즈 / XL 사이즈 / SMALL SIZE / Medium사이즈처럼
    # 값 뒤에 size label이 붙는 경우 label까지 하나의 span으로 소비한다.
    LABELED_ALPHA_SIZE = re.compile(
        rf"""
        (?<![A-Za-z])
        (?P<size>{ALPHA_SIZE})
        \s*
        (?:사이즈|sizes?)
        (?![A-Za-z가-힣])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    STANDALONE_ALPHA_SIZE = re.compile(
        rf"""
        (?<![A-Za-z])
        (?P<size>{ALPHA_SIZE})
        (?![A-Za-z])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    SIZE_VALUES = re.compile(
        rf"""
        (?<![A-Za-z])
        (?P<values>
            {ALPHA_SIZE}
            (?:
                \s*
                [,/]
                \s*
                {ALPHA_SIZE}
            )+
        )
        (?![A-Za-z])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    SIZE_COUNT = re.compile(
        r"""
        (?<!\d)
        (?P<count>\d{1,2})
        \s*
        (?:사이즈|sizes?)
        (?![A-Za-z가-힣])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    SIZE_ADDED = re.compile(
        rf"""
        (?<![A-Za-z])
        (?P<size>{ALPHA_SIZE})
        \s*
        추가
        (?![A-Za-z가-힣])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    LENGTH_OPTION = re.compile(
        r"""
        기장
        \s*
        선택
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    EXPLICIT_NUMERIC_SIZE = re.compile(
        r"""
        (?:
            (?:사이즈|size)
            \s*
            [:：]?
            \s*
            (?P<prefixed>\d{2,3})
        )
        |
        (?:
            (?P<mm>\d{3})
            \s*
            mm
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # musinsa_used에서만 사용.
    #
    # 허리:
    #   24 ~ 44
    #
    # 한국 의류 호수:
    #   44, 55, 66, 77
    #   85, 90, 95, 100, 105, 110, 115, 120
    #
    # 신발:
    #   220 ~ 320 / 5mm 단위
    BARE_NUMERIC_SIZE = re.compile(
        r"""
        (?<!\d)
        (?P<size>
            2[4-9]
            |
            3[0-9]
            |
            4[0-4]
            |
            55
            |
            66
            |
            77
            |
            85
            |
            90
            |
            95
            |
            100
            |
            105
            |
            110
            |
            115
            |
            120
            |
            2[2-9][05]
            |
            300
            |
            305
            |
            310
            |
            315
            |
            320
        )
        (?!\d)
        """,
        re.VERBOSE,
    )

    @classmethod
    def detect(
        cls,
        text: str | None,
        *,
        allow_bare_numeric: bool = False,
    ) -> list[SizeMatch]:
        if not text:
            return []

        text = str(text)
        matches: list[SizeMatch] = []

        # 긴/명시적인 표현 우선.
        matches.extend(
            cls._detect_free_size_range(text)
        )
        matches.extend(
            cls._detect_alpha_range(text)
        )
        matches.extend(
            cls._detect_numeric_range(text)
        )
        matches.extend(
            cls._detect_size_values(text)
        )
        matches.extend(
            cls._detect_size_count(text)
        )
        matches.extend(
            cls._detect_size_added(text)
        )
        matches.extend(
            cls._detect_length_option(text)
        )
        matches.extend(
            cls._detect_explicit_numeric(text)
        )
        matches.extend(
            cls._detect_labeled_alpha(text)
        )

        # S / M / L / F / SMALL / MEDIUM / LARGE 등의 단독 사이즈.
        #
        # 여기서 f/w, s/s 등 시즌 표기의 F/S는 제외한다.
        matches.extend(
            cls._detect_standalone_alpha(text)
        )

        # musinsa_used 등 호출부에서 명시적으로 허용한 경우에만.
        if allow_bare_numeric:
            matches.extend(
                cls._detect_bare_numeric_size(text)
            )

        return cls._deduplicate(matches)

    @classmethod
    def _detect_free_size_range(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.FREE_SIZE_RANGE.finditer(text):
            label = match.group("label").upper()
            min_size = match.group("min")
            max_size = match.group("max")

            results.append(
                SizeMatch(
                    size_type="SIZE_RANGE",
                    raw=match.group(0),
                    normalized=f"{label}({min_size}-{max_size})",
                    start=match.start(),
                    end=match.end(),
                    value={
                        "label": "FREE",
                        "min": min_size,
                        "max": max_size,
                        "system": "KR_APPAREL",
                    },
                )
            )

        return results

    @classmethod
    def _detect_alpha_range(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.SIZE_RANGE_ALPHA.finditer(text):
            min_size = cls._normalize_alpha_size(match.group("min"))
            max_size = cls._normalize_alpha_size(match.group("max"))

            results.append(
                SizeMatch(
                    size_type="SIZE_RANGE",
                    raw=match.group(0),
                    normalized=f"{min_size}-{max_size}",
                    start=match.start(),
                    end=match.end(),
                    value={
                        "min": min_size,
                        "max": max_size,
                        "system": "ALPHA",
                    },
                )
            )

        return results

    @classmethod
    def _detect_numeric_range(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.SIZE_RANGE_NUMERIC.finditer(text):
            min_size = match.group("min")
            max_size = match.group("max")

            results.append(
                SizeMatch(
                    size_type="SIZE_RANGE",
                    raw=match.group(0),
                    normalized=f"{min_size}-{max_size}",
                    start=match.start(),
                    end=match.end(),
                    value={
                        "min": min_size,
                        "max": max_size,
                        "system": "NUMERIC",
                    },
                )
            )

        return results

    @classmethod
    def _detect_labeled_alpha(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.LABELED_ALPHA_SIZE.finditer(text):
            size = cls._normalize_alpha_size(match.group("size"))

            results.append(
                SizeMatch(
                    size_type="SIZE_VALUE",
                    raw=match.group(0),
                    normalized=size,
                    start=match.start(),
                    end=match.end(),
                    value=size,
                )
            )

        return results

    @classmethod
    def _detect_standalone_alpha(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.STANDALONE_ALPHA_SIZE.finditer(text):
            size = cls._normalize_alpha_size(match.group("size"))

            # -------------------------------------------------
            # 시즌 표현 보호
            #
            # f/w -> F를 FREE SIZE로 오탐하면 안 됨
            # s/s -> S를 SIZE로 오탐하면 안 됨
            # -------------------------------------------------
            if cls._is_season_alpha_fragment(
                text=text,
                start=match.start(),
                end=match.end(),
            ):
                continue

            start = match.start()
            end = match.end()

            # -------------------------------------------------
            # 단독 사이즈 앞의 범위 decorator 포함
            #
            # ~XL
            # ～XL
            #
            # XL만 제거하면 "~"가 core에 고아로 남기 때문에
            # structural raw span에는 decorator까지 포함한다.
            #
            # 단 S~XL 같은 정상 SIZE_RANGE는 이후 deduplicate에서
            # 더 긴 SIZE_RANGE span이 우선된다.
            # -------------------------------------------------
            decorated_start = start

            if start > 0 and text[start - 1] in {"~", "～"}:
                decorated_start = start - 1

            raw = text[decorated_start:end]

            results.append(
                SizeMatch(
                    size_type="SIZE_VALUE",
                    raw=raw,
                    normalized=size,
                    start=decorated_start,
                    end=end,
                    value=size,
                )
            )

        return results

    @classmethod
    def _detect_size_values(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.SIZE_VALUES.finditer(text):
            raw_values = match.group("values")

            values = [
                cls._normalize_alpha_size(value)
                for value in re.split(
                    r"\s*[,/]\s*",
                    raw_values,
                )
                if value
            ]

            results.append(
                SizeMatch(
                    size_type="SIZE_VALUES",
                    raw=match.group(0),
                    normalized=",".join(values),
                    start=match.start(),
                    end=match.end(),
                    value=values,
                )
            )

        return results

    @classmethod
    def _detect_size_count(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.SIZE_COUNT.finditer(text):
            count = int(match.group("count"))

            results.append(
                SizeMatch(
                    size_type="SIZE_COUNT",
                    raw=match.group(0),
                    normalized=str(count),
                    start=match.start(),
                    end=match.end(),
                    value=count,
                )
            )

        return results

    @classmethod
    def _detect_size_added(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.SIZE_ADDED.finditer(text):
            size = cls._normalize_alpha_size(match.group("size"))

            results.append(
                SizeMatch(
                    size_type="SIZE_OPTION",
                    raw=match.group(0),
                    normalized=size,
                    start=match.start(),
                    end=match.end(),
                    value={
                        "option": "ADDED",
                        "size": size,
                    },
                )
            )

        return results

    @classmethod
    def _detect_length_option(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.LENGTH_OPTION.finditer(text):
            results.append(
                SizeMatch(
                    size_type="SIZE_OPTION",
                    raw=match.group(0),
                    normalized="기장선택",
                    start=match.start(),
                    end=match.end(),
                    value={
                        "option": "LENGTH_SELECT",
                    },
                )
            )

        return results

    @classmethod
    def _detect_explicit_numeric(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        results = []

        for match in cls.EXPLICIT_NUMERIC_SIZE.finditer(text):
            value = (
                match.group("prefixed")
                or match.group("mm")
            )

            results.append(
                SizeMatch(
                    size_type="SIZE_VALUE",
                    raw=match.group(0),
                    normalized=value,
                    start=match.start(),
                    end=match.end(),
                    value={
                        "value": value,
                        "system": "NUMERIC",
                    },
                )
            )

        return results

    @classmethod
    def _detect_bare_numeric_size(
        cls,
        text: str,
    ) -> list[SizeMatch]:
        """
        musinsa_used 전용 bare numeric size.

        지원
        ----
        허리:
            24 ~ 44

        의류:
            44, 55, 66, 77
            85, 90, 95, 100, 105, 110, 115, 120

        신발:
            220 ~ 320
            5mm 단위
        """

        results = []

        for match in cls.BARE_NUMERIC_SIZE.finditer(text):
            size = match.group("size")
            numeric_size = int(size)

            if 220 <= numeric_size <= 320:
                value = {
                    "value": numeric_size,
                    "system": "KR_SHOE_MM",
                    "unit": "mm",
                }

            elif 24 <= numeric_size <= 44:
                value = {
                    "value": numeric_size,
                    "system": "WAIST_INCH",
                    "unit": "inch",
                }

            else:
                value = {
                    "value": numeric_size,
                    "system": "KR_APPAREL",
                }

            results.append(
                SizeMatch(
                    size_type="SIZE_VALUE",
                    raw=match.group(0),
                    normalized=size,
                    start=match.start(),
                    end=match.end(),
                    value=value,
                )
            )

        return results

    @classmethod
    def _normalize_alpha_size(
        cls,
        value: str,
    ) -> str:
        normalized = re.sub(
            r"\s+",
            " ",
            str(value or "").strip().upper(),
        )

        return cls.ALPHA_SIZE_MAP.get(
            normalized,
            normalized,
        )

    @staticmethod
    def _is_season_alpha_fragment(
        *,
        text: str,
        start: int,
        end: int,
    ) -> bool:
        """
        단독 F/S 탐지 시 시즌 표기의 일부인지 확인한다.

        보호 대상 예:
        - f/w
        - F/W
        - f / w
        - s/s
        - S/S

        SIZE 예:
        - 티셔츠 S
        - 팬츠 F
        - FREE F
        """

        left = text[max(0, start - 4):start]
        right = text[end:min(len(text), end + 4)]

        size_char = text[start:end].casefold()

        # F/W
        if size_char == "f":
            if re.match(
                r"^\s*/\s*w\b",
                right,
                flags=re.IGNORECASE,
            ):
                return True

        # S/S
        if size_char == "s":
            if re.match(
                r"^\s*/\s*s\b",
                right,
                flags=re.IGNORECASE,
            ):
                return True

        # 혹시 detector가 두 번째 문자를 보게 되는 경우도 보호.
        if size_char == "w":
            if re.search(
                r"\bf\s*/\s*$",
                left,
                flags=re.IGNORECASE,
            ):
                return True

        if size_char == "s":
            if re.search(
                r"\bs\s*/\s*$",
                left,
                flags=re.IGNORECASE,
            ):
                return True

        return False

    @staticmethod
    def _deduplicate(
        matches: list[SizeMatch],
    ) -> list[SizeMatch]:
        matches = sorted(
            matches,
            key=lambda x: (
                x.start,
                -(x.end - x.start),
            ),
        )

        result = []
        occupied = []

        for match in matches:
            overlap = any(
                match.start < end
                and match.end > start
                for start, end in occupied
            )

            if overlap:
                continue

            result.append(match)
            occupied.append(
                (
                    match.start,
                    match.end,
                )
            )

        return sorted(
            result,
            key=lambda x: x.start,
        )

# ============================================================================
# product_season_detector.py
# ============================================================================
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductSeasonMatch:
    season_type: str
    raw: str
    normalized: str
    start: int
    end: int
    year: int | None
    code: str


class ProductSeasonDetector:
    """
    상품명에서 상품 시즌 코드만 탐지한다.

    탐지 대상
    --------
    26FW
    26SS
    2026FW
    2026SS
    FW26
    SS26
    FW2026
    SS2026
    26 F/W
    26 S/S

    탐지하지 않는 대상
    ------------------
    가을
    봄
    여름
    겨울
    간절기
    환절기
    사계절
    AUTUMN
    SPRING

    위 표현들은 Dictionary TPO 영역에서 처리한다.
    """

    CODE_MAP = {
        "FW": "FW",
        "F/W": "FW",
        "SS": "SS",
        "S/S": "SS",
    }

    # 26FW / 2026FW / 26 F/W / 2026 S/S
    YEAR_FIRST = re.compile(
        r"""
        (?<!\d)

        (?P<year>
            20\d{2}
            |
            \d{2}
        )

        \s*

        (?P<code>
            F\s*/?\s*W
            |
            S\s*/?\s*S
        )

        (?![A-Za-z0-9])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # FW26 / FW2026 / F/W 26 / S/S 2026
    CODE_FIRST = re.compile(
        r"""
        (?<![A-Za-z0-9])

        (?P<code>
            F\s*/?\s*W
            |
            S\s*/?\s*S
        )

        \s*

        (?P<year>
            20\d{2}
            |
            \d{2}
        )

        (?!\d)
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    @classmethod
    def detect(
        cls,
        text: str | None,
    ) -> list[ProductSeasonMatch]:

        if not text:
            return []

        text = str(text)

        matches: list[ProductSeasonMatch] = []

        matches.extend(
            cls._detect_pattern(
                text,
                cls.YEAR_FIRST,
            )
        )

        matches.extend(
            cls._detect_pattern(
                text,
                cls.CODE_FIRST,
            )
        )

        return cls._deduplicate(matches)

    @classmethod
    def _detect_pattern(
        cls,
        text: str,
        pattern: re.Pattern,
    ) -> list[ProductSeasonMatch]:

        results = []

        for match in pattern.finditer(text):
            raw_year = match.group("year")
            raw_code = match.group("code")

            year = cls._normalize_year(raw_year)
            code = cls._normalize_code(raw_code)

            if year is None or code is None:
                continue

            results.append(
                ProductSeasonMatch(
                    season_type="SEASON_CODE",
                    raw=match.group(0),
                    normalized=f"{year}{code}",
                    start=match.start(),
                    end=match.end(),
                    year=year,
                    code=code,
                )
            )

        return results

    @staticmethod
    def _normalize_year(
        value: str,
    ) -> int | None:

        value = value.strip()

        if len(value) == 4:
            year = int(value)

        elif len(value) == 2:
            year = 2000 + int(value)

        else:
            return None

        # 상품 데이터에서 터무니없는 연도 오탐 방지
        if not 2000 <= year <= 2099:
            return None

        return year

    @classmethod
    def _normalize_code(
        cls,
        value: str,
    ) -> str | None:

        value = re.sub(
            r"\s+",
            "",
            value.upper(),
        )

        return cls.CODE_MAP.get(value)

    @staticmethod
    def _deduplicate(
        matches: list[ProductSeasonMatch],
    ) -> list[ProductSeasonMatch]:

        matches = sorted(
            matches,
            key=lambda x: (
                x.start,
                -(x.end - x.start),
            ),
        )

        result = []
        occupied = []

        for match in matches:
            overlap = any(
                match.start < end
                and match.end > start
                for start, end in occupied
            )

            if overlap:
                continue

            result.append(match)
            occupied.append(
                (
                    match.start,
                    match.end,
                )
            )

        return sorted(
            result,
            key=lambda x: x.start,
        )

# ============================================================================
# gender_detector.py
# ============================================================================
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GenderMatch:
    gender_type: str
    raw: str
    normalized: str
    start: int
    end: int
    value: str


class GenderDetector:
    """
    상품명에서 성별 / 타깃 성별 표현을 탐지한다.

    역할
    ----
    여성 / 여자 / 여성용
        -> WOMEN

    남성 / 남자 / 남성용
        -> MEN

    우먼 / 우먼즈 / WOMAN / WOMEN / WOMENS
        -> WOMEN

    맨 / 맨즈 / MEN / MENS
        -> MEN

    남녀공용 / UNISEX
        -> UNISEX

    주의
    ----
    - 문자열을 직접 수정하지 않는다.
    - DictionaryTerm 후보로 보내지 않을 메타데이터다.
    - 최종 CoreNameBuilder가 해당 span을 core name에서 제외한다.
    """

    PATTERNS = (
        (
            "UNISEX",
            re.compile(
                r"""
                남녀\s*공용
                |
                공용
                |
                unisex
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),
        (
            "WOMEN",
            re.compile(
                r"""
                여성용
                |
                여성
                |
                여자
                |
                우먼즈
                |
                우먼
                |
                womens
                |
                women
                |
                woman
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),
        (
            "MEN",
            re.compile(
                r"""
                남성용
                |
                남성
                |
                남자
                |
                맨즈
                |
                mens
                |
                men
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),
            (
        "UNISEX",
        re.compile(
            r"""
            남[녀여]\s*공용
            |
            유니섹스
            |
            unisex
            |
            공용
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),

    )

    @classmethod
    def detect(
        cls,
        text: str | None,
    ) -> list[GenderMatch]:

        if not text:
            return []

        text = str(text)

        matches: list[GenderMatch] = []

        for value, pattern in cls.PATTERNS:
            for match in pattern.finditer(text):
                matches.append(
                    GenderMatch(
                        gender_type="GENDER",
                        raw=match.group(0),
                        normalized=value,
                        start=match.start(),
                        end=match.end(),
                        value=value,
                    )
                )

        return cls._deduplicate(matches)

    @staticmethod
    def _deduplicate(
        matches: list[GenderMatch],
    ) -> list[GenderMatch]:

        matches = sorted(
            matches,
            key=lambda x: (
                x.start,
                -(x.end - x.start),
            ),
        )

        result = []
        occupied = []

        for match in matches:
            overlap = any(
                match.start < end
                and match.end > start
                for start, end in occupied
            )

            if overlap:
                continue

            result.append(match)
            occupied.append(
                (
                    match.start,
                    match.end,
                )
            )

        return sorted(
            result,
            key=lambda x: x.start,
        )

# ============================================================================
# product_meta_detector.py
# ============================================================================
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProductMetaMatch:
    meta_type: str
    raw: str
    normalized: str
    start: int
    end: int
    value: Any


class ProductMetaDetector:
    """
    상품명의 구조적 PRODUCT_META를 탐지한다.

    담당
    ----
    COLOR_COUNT
        3color
        6colors
        2컬러
        4col

    PACK_COUNT
        2PACK
        3팩

    COMPOSITION_COUNT
        4종
        2종

    COLOR_OPTION
        컬러추가
        색상추가
        NEW컬러

    LENGTH_OPTION
        숏/롱
        기본/롱
        숏,롱

    담당하지 않음
    --------------
    SIZE_*      -> SizeDetector
    SEASON_CODE -> ProductSeasonDetector
    GENDER      -> GenderDetector
    MARKETING   -> MarketingDetector

    SET / 세트 / 2SET / 3SET / 2종SET / 3종세트
        상품 구성 의미이므로 core name에 보존한다.

    패션 의미가 있는 표현도 여기서 잡지 않는다.

    예:
    캡내장
    끈조절
    체형커버
    부유방커버
    MADE
    자체제작
    국내제작

    위 표현들은 Dictionary Discovery 대상으로 남긴다.
    """

    # ============================================================
    # COLOR COUNT
    # ============================================================

    COLOR_COUNT = re.compile(
        r"""
        (?<![0-9A-Za-z가-힣])

        (?P<count>\d{1,2})

        \s*

        (?:
            colors?
            |
            colours?
            |
            colo
            |
            col
            |
            c
            |
            컬러
        )

        (?![A-Za-z가-힣])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # ============================================================
    # PACK COUNT
    # ============================================================

    PACK_COUNT = re.compile(
        r"""
        (?<![0-9A-Za-z가-힣])

        (?P<count>\d{1,2})

        \s*

        (?:
            packs?
            |
            팩
        )

        (?![A-Za-z가-힣])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    COMPOSITION_COUNT = re.compile(
        r"""
        (?<!\d)

        (?P<count>\d{1,2})

        \s*
        종

        (?!\s*(?:SET|세트))
        (?!\d)
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # ============================================================
    # COLOR OPTION
    # ============================================================

    COLOR_OPTION_PATTERNS = (
        re.compile(
            r"""
            컬러
            \s*
            추가
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            색상
            \s*
            추가
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            NEW
            \s*
            컬러
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    )

    # ============================================================
    # LENGTH OPTION
    #
    # 숏/롱
    # 기본/롱
    # 숏,롱
    #
    # "크롭" 같은 실제 기장 특성은 잡지 않는다.
    # 크롭은 DictionaryTerm 후보.
    # ============================================================

    LENGTH_OPTION = re.compile(
        r"""
        (?P<values>
            (?:숏|기본|롱)
            (?:
                \s*
                [,/]
                \s*
                (?:숏|기본|롱)
            )+
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # ============================================================
    # TARGET + WIDTH
    #
    # (여성 D), (남성 2E), 여성 B 등
    # 성별 표현만 제거되어 width 토큰이 core name에 고아로 남는 것을 방지한다.
    # WIDTH는 DictionaryTerm이 아니라 상품 구조 메타로 보존한다.
    # ============================================================

    TARGET_WIDTH = re.compile(
        r"""
        (?<![0-9A-Za-z가-힣])
        (?P<target>여성|남성|여자|남자|우먼|맨|women?|men?)
        \s*
        (?P<width>2E|4E|6E|B|D|E)
        (?![0-9A-Za-z가-힣])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # ============================================================
    # PUBLIC
    # ============================================================

    @classmethod
    def detect(
        cls,
        text: str | None,
    ) -> list[ProductMetaMatch]:

        if not text:
            return []

        text = str(text)

        matches: list[ProductMetaMatch] = []

        # GenderDetector보다 넓은 span을 잡아 (여성 D)에서 D가 남지 않게 한다.
        matches.extend(
            cls._detect_target_width(text)
        )

        matches.extend(
            cls._detect_count(
                text,
                cls.COLOR_COUNT,
                "COLOR_COUNT",
            )
        )

        matches.extend(
            cls._detect_count(
                text,
                cls.PACK_COUNT,
                "PACK_COUNT",
            )
        )

        matches.extend(
            cls._detect_count(
                text,
                cls.COMPOSITION_COUNT,
                "COMPOSITION_COUNT",
            )
        )

        matches.extend(
            cls._detect_color_options(text)
        )

        matches.extend(
            cls._detect_length_options(text)
        )

        return cls._deduplicate(matches)

    # ============================================================
    # TARGET + WIDTH
    # ============================================================

    @classmethod
    def _detect_target_width(
        cls,
        text: str,
    ) -> list[ProductMetaMatch]:

        results = []

        target_map = {
            "여성": "WOMEN",
            "여자": "WOMEN",
            "우먼": "WOMEN",
            "woman": "WOMEN",
            "women": "WOMEN",
            "남성": "MEN",
            "남자": "MEN",
            "맨": "MEN",
            "man": "MEN",
            "men": "MEN",
        }

        for match in cls.TARGET_WIDTH.finditer(text):
            raw_target = match.group("target")
            width = match.group("width").upper()
            target = target_map.get(raw_target.casefold(), raw_target)

            results.append(
                ProductMetaMatch(
                    meta_type="TARGET_WIDTH",
                    raw=match.group(0),
                    normalized=f"{target}:{width}",
                    start=match.start(),
                    end=match.end(),
                    value={
                        "target": target,
                        "width": width,
                    },
                )
            )

        return results

    # ============================================================
    # COUNT
    # ============================================================

    @classmethod
    def _detect_count(
        cls,
        text: str,
        pattern: re.Pattern,
        meta_type: str,
    ) -> list[ProductMetaMatch]:

        results = []

        for match in pattern.finditer(text):
            count = int(match.group("count"))

            results.append(
                ProductMetaMatch(
                    meta_type=meta_type,
                    raw=match.group(0),
                    normalized=str(count),
                    start=match.start(),
                    end=match.end(),
                    value=count,
                )
            )

        return results

    # ============================================================
    # COLOR OPTION
    # ============================================================

    @classmethod
    def _detect_color_options(
        cls,
        text: str,
    ) -> list[ProductMetaMatch]:

        results = []

        for pattern in cls.COLOR_OPTION_PATTERNS:
            for match in pattern.finditer(text):
                results.append(
                    ProductMetaMatch(
                        meta_type="COLOR_OPTION",
                        raw=match.group(0),
                        normalized="COLOR_ADDED",
                        start=match.start(),
                        end=match.end(),
                        value={
                            "option": "COLOR_ADDED",
                        },
                    )
                )

        return results

    # ============================================================
    # LENGTH OPTION
    # ============================================================

    @classmethod
    def _detect_length_options(
        cls,
        text: str,
    ) -> list[ProductMetaMatch]:

        results = []

        for match in cls.LENGTH_OPTION.finditer(text):
            raw_values = match.group("values")

            values = [
                value.strip()
                for value in re.split(
                    r"\s*[,/]\s*",
                    raw_values,
                )
                if value.strip()
            ]

            results.append(
                ProductMetaMatch(
                    meta_type="LENGTH_OPTION",
                    raw=match.group(0),
                    normalized="/".join(values),
                    start=match.start(),
                    end=match.end(),
                    value={
                        "values": values,
                    },
                )
            )

        return results

    # ============================================================
    # DEDUP
    # ============================================================

    @staticmethod
    def _deduplicate(
        matches: list[ProductMetaMatch],
    ) -> list[ProductMetaMatch]:

        # 같은 시작 위치면 긴 span 우선
        #
        # 2종SET
        # 2종
        # SET
        #
        # -> 2종SET 하나만 남긴다.
        matches = sorted(
            matches,
            key=lambda x: (
                x.start,
                -(x.end - x.start),
            ),
        )

        result = []
        occupied = []

        for match in matches:
            overlap = any(
                match.start < end
                and match.end > start
                for start, end in occupied
            )

            if overlap:
                continue

            result.append(match)

            occupied.append(
                (
                    match.start,
                    match.end,
                )
            )

        return sorted(
            result,
            key=lambda x: x.start,
        )

# ============================================================================
# product_code_detector.py
# ============================================================================
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class ProductCodeMatch:
    code_type: str
    raw: str
    normalized: str
    start: int
    end: int
    confidence: str
    value: str


class ProductCodeDetector:
    """
    상품명에 포함된 상품 코드 / 스타일 코드 후보를 탐지한다.

    탐지 예
    -------
    9766
    483281
    AB1234
    AB-1234
    HQ4307-001
    DV1234-100
    ABC_123

    정책
    ----
    1. 영문 + 숫자 조합 코드는 HIGH
    2. 순수 숫자는 보수적으로 판정
    3. 구조적으로 명확한 숫자 상품코드는 HIGH
    4. 애매한 숫자는 LOW
    5. HIGH만 CoreName에서 자동 제거
    """

    # ============================================================
    # ALPHANUMERIC CODE
    # ============================================================

    # HQ4307-001
    # DV1234-100
    # ABC-1234
    # ABC_123
    ALPHANUMERIC_SEPARATED = re.compile(
        r"""
        (?<![A-Za-z0-9])

        (?P<code>
            (?=[A-Za-z0-9_-]*[A-Za-z])
            (?=[A-Za-z0-9_-]*\d)
            [A-Za-z0-9]+
            (?:[-_][A-Za-z0-9]+)+
        )

        (?![A-Za-z0-9])
        """,
        re.VERBOSE,
    )

    # AB1234
    # ABC123
    # 123ABC
    ALPHANUMERIC_COMPACT = re.compile(
        r"""
        (?<![A-Za-z0-9])

        (?P<code>
            (?=[A-Za-z0-9]*[A-Za-z])
            (?=[A-Za-z0-9]*\d)
            [A-Za-z0-9]{4,20}
        )

        (?![A-Za-z0-9])
        """,
        re.VERBOSE,
    )

    # ============================================================
    # NUMERIC CODE
    # ============================================================

    # 9766
    # 12345
    # 483281
    #
    # 순수 숫자는 사이즈 / 연도 / 수량 등과 충돌 가능성이 있으므로
    # 위치와 주변 구조를 같이 본다.
    NUMERIC_CODE = re.compile(
        r"""
        (?<!\d)

        (?P<code>
            \d{4,10}
        )

        (?!\d)
        """,
        re.VERBOSE,
    )

    # ============================================================
    # EXCLUSION
    # ============================================================

    EXCLUDED_VALUES = {
        "2024",
        "2025",
        "2026",
        "2027",
        "2028",
        "2029",
        "2030",
        "MA-1",
    }

    # 숫자 상품코드 뒤에 올 수 있는 구조 메타.
    #
    # 예:
    # 483281
    # 483281 8컬러
    # 483281 3color
    # 483281 6c
    #
    # 이 경우 숫자가 상품명 본체 뒤에 붙은 코드일 가능성이 높다.
    TRAILING_META = re.compile(
        r"""
        ^
        \s*

        (?:
            \d{1,2}
            \s*
            (?:
                colors?
                |
                colours?
                |
                colo
                |
                col
                |
                c
                |
                컬러
            )
        )?

        \s*
        $
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # ============================================================
    # PUBLIC
    # ============================================================

    @classmethod
    def detect(
        cls,
        text: str | None,
        *,
        blocked_spans: list[
            tuple[int, int]
        ] | None = None,
    ) -> list[ProductCodeMatch]:

        if not text:
            return []

        text = str(text)

        blocked_spans = (
            blocked_spans
            or []
        )

        results: list[
            ProductCodeMatch
        ] = []

        # --------------------------------------------------------
        # 1. separated alphanumeric
        #
        # HQ4307-001
        # DV1234-100
        # --------------------------------------------------------

        results.extend(
            cls._detect_pattern(
                text,
                cls.ALPHANUMERIC_SEPARATED,
                code_type="STYLE_CODE",
                confidence="HIGH",
                blocked_spans=blocked_spans,
            )
        )

        # --------------------------------------------------------
        # 2. compact alphanumeric
        #
        # AB1234
        # --------------------------------------------------------

        results.extend(
            cls._detect_pattern(
                text,
                cls.ALPHANUMERIC_COMPACT,
                code_type="PRODUCT_CODE",
                confidence="HIGH",
                blocked_spans=blocked_spans,
            )
        )

        # --------------------------------------------------------
        # 3. numeric
        #
        # 9766
        # 483281
        # --------------------------------------------------------

        results.extend(
            cls._detect_numeric(
                text,
                blocked_spans=blocked_spans,
            )
        )

        return cls._deduplicate(
            results
        )

    # ============================================================
    # ALPHANUMERIC
    # ============================================================

    @classmethod
    def _detect_pattern(
        cls,
        text: str,
        pattern: re.Pattern,
        *,
        code_type: str,
        confidence: str,
        blocked_spans: list[
            tuple[int, int]
        ],
    ) -> list[ProductCodeMatch]:

        results = []

        for match in pattern.finditer(
            text
        ):
            start = match.start(
                "code"
            )

            end = match.end(
                "code"
            )

            code = match.group(
                "code"
            )

            if cls._overlaps(
                start,
                end,
                blocked_spans,
            ):
                continue

            if (
                code.upper()
                in cls.EXCLUDED_VALUES
            ):
                continue

            # 150ver / 140VER / 2024version 같은 표기는
            # 상품 코드가 아니라 버전/옵션 표기다.
            # [140.150ver]에서 150ver만 PRODUCT_CODE로 제거되어
            # core가 [140.]처럼 깨지는 것을 방지한다.
            if re.fullmatch(
                r"\d+(?:ver|version)",
                code,
                flags=re.IGNORECASE,
            ):
                continue

            results.append(
                ProductCodeMatch(
                    code_type=code_type,
                    raw=code,
                    normalized=(
                        code.upper()
                    ),
                    start=start,
                    end=end,
                    confidence=confidence,
                    value=code,
                )
            )

        return results

    # ============================================================
    # NUMERIC
    # ============================================================

    @classmethod
    def _detect_numeric(
        cls,
        text: str,
        *,
        blocked_spans: list[
            tuple[int, int]
        ],
    ) -> list[ProductCodeMatch]:

        results = []

        for match in (
            cls.NUMERIC_CODE.finditer(
                text
            )
        ):
            code = match.group(
                "code"
            )

            start = match.start(
                "code"
            )

            end = match.end(
                "code"
            )

            # ---------------------------------------------
            # 이미 SIZE / SEASON / META 등으로 해석된
            # 영역이면 PRODUCT_CODE로 잡지 않는다.
            # ---------------------------------------------

            if cls._overlaps(
                start,
                end,
                blocked_spans,
            ):
                continue

            # ---------------------------------------------
            # 연도 등 명시적 exclusion
            # ---------------------------------------------

            if (
                code.upper()
                in cls.EXCLUDED_VALUES
            ):
                continue

            confidence = (
                cls._numeric_confidence(
                    text=text,
                    start=start,
                    end=end,
                )
            )

            if confidence is None:
                continue

            results.append(
                ProductCodeMatch(
                    code_type=(
                        "PRODUCT_CODE"
                    ),
                    raw=code,
                    normalized=code,
                    start=start,
                    end=end,
                    confidence=confidence,
                    value=code,
                )
            )

        return results

    # ============================================================
    # NUMERIC CONFIDENCE
    # ============================================================

    @classmethod
    def _numeric_confidence(
        cls,
        *,
        text: str,
        start: int,
        end: int,
    ) -> str | None:
        """
        순수 숫자 상품코드 confidence 판정.

        HIGH
        ----
        9766 원피스
            -> 상품명 첫 토큰

        [9766] 원피스
            -> wrapper 내부 첫 토큰

        (9766) 원피스
            -> wrapper 내부 첫 토큰

        유니클로 파카 483281
            -> 상품명 마지막 숫자 토큰

        유니클로 파카 483281 8컬러
            -> 숫자 뒤에는 구조 메타만 존재

        LOW
        ---
        상품명 중간에 존재하면서
        뒤에 실제 상품명 텍스트가 계속되는 숫자.

        중요
        ----
        HIGH만 CoreName에서 제거한다.
        """

        before_raw = text[:start]
        after_raw = text[end:]

        before = before_raw.strip()
        after = after_raw.strip()

        # --------------------------------------------------------
        # 1. 상품명 맨 앞
        #
        # 9766 원피스
        # --------------------------------------------------------

        if not before:
            return "HIGH"

        # --------------------------------------------------------
        # 2. 괄호 / 대괄호 첫 토큰
        #
        # [9766] 원피스
        # (9766) 원피스
        # --------------------------------------------------------

        if (
            before.endswith("[")
            or before.endswith("(")
        ):
            return "HIGH"

        # --------------------------------------------------------
        # 3. 상품명 마지막 토큰
        #
        # 유니클로 파카 483281
        # --------------------------------------------------------

        if not after:
            return "HIGH"

        # --------------------------------------------------------
        # 4. 숫자 코드 뒤에 닫는 wrapper만 존재
        #
        # [9766]
        # (9766)
        # --------------------------------------------------------

        if re.fullmatch(
            r"[\]\)]",
            after,
        ):
            return "HIGH"

        # --------------------------------------------------------
        # 5. 숫자 코드 뒤에 PRODUCT_META만 존재
        #
        # 483281 8컬러
        # 483281 3color
        # 483281 6c
        #
        # ProductMetaDetector가 이미 해당 영역을 blocked span으로
        # 잡더라도 numeric code 자체는 겹치지 않으므로 여기까지 온다.
        # --------------------------------------------------------

        if cls.TRAILING_META.fullmatch(
            after
        ):
            return "HIGH"

        # --------------------------------------------------------
        # 나머지 순수 숫자는 보수적으로 LOW
        #
        # 예:
        # SOME 1234 DENIM PANTS
        #
        # 숫자만 보고 자동 삭제하지 않는다.
        # --------------------------------------------------------

        return "LOW"

    # ============================================================
    # OVERLAP
    # ============================================================

    @staticmethod
    def _overlaps(
        start: int,
        end: int,
        blocked_spans: list[
            tuple[int, int]
        ],
    ) -> bool:

        return any(
            start < blocked_end
            and end > blocked_start
            for (
                blocked_start,
                blocked_end,
            )
            in blocked_spans
        )

    # ============================================================
    # DEDUP
    # ============================================================

    @staticmethod
    def _deduplicate(
        matches: list[
            ProductCodeMatch
        ],
    ) -> list[
        ProductCodeMatch
    ]:

        matches = sorted(
            matches,
            key=lambda x: (
                x.start,
                -(x.end - x.start),
            ),
        )

        result = []
        occupied = []

        for match in matches:
            overlap = any(
                match.start < end
                and match.end > start
                for start, end
                in occupied
            )

            if overlap:
                continue

            result.append(
                match
            )

            occupied.append(
                (
                    match.start,
                    match.end,
                )
            )

        return sorted(
            result,
            key=lambda x: x.start,
        )

# ============================================================================
# tag_list_detector.py
# ============================================================================
import re
from dataclasses import dataclass
from typing import Any



@dataclass(frozen=True)
class TagListMatch:
    raw: str
    normalized: str
    start: int
    end: int
    match_type: str
    confidence: str
    value: Any


class TagListDetector:
    """
    상품명 뒤에 붙는 검색 / SEO 태그 나열 블록 탐지.

    역할
    ----
    1. 괄호 / 대괄호 내부의 명시적 separator 나열 탐지
    2. 괄호 없는 후행 separator 나열 탐지
    3. 상품명 끝의 대괄호 내부 공백형 SEO 태그 나열 탐지

    중요한 원칙
    -----------
    이 detector는 semantic tokenizer의 입력을 수정하지 않는다.

    즉:

        RAW
        [1만장판매] [B-BASIC] 텐션 스탠다드 슬림 유넥 반팔티
        (2SIZE)
        [비베이직 자체제작 제작상품 스탠다드핏 반소매
         기본템 꾸안꾸 데일리 사계절]

    semantic tokenizer는 RAW 전체를 보고:

        반소매
        꾸안꾸
        데일리
        사계절

    등을 정상적으로 추출할 수 있다.

    다만 마지막 SEO tag block은 StructuralSpan으로 잡아서
    최종 core_name에서는 통째로 제거한다.

    보호
    ----
    아래와 같은 일반 label / 상품명 요소는 제거하지 않는다.

        [B-BASIC]
        [BLACK]
        [MADE]
        [SET]
        [UNISEX]

    단순히 대괄호라는 이유만으로 제거하지 않는다.
    """

    # ============================================================
    # COMMON
    # ============================================================

    SEPARATOR_RE = re.compile(
        r"\s*[/|,·•;]\s*"
    )

    # 쇼핑몰이 괄호 안 SEO keyword chain에 자주 쓰는 하이픈.
    # 일반 상품명(A-라인, MA-1, XS-XL)을 보호하기 위해
    # trailing wrapper 안에서만 별도 판정한다.
    HYPHEN_SEPARATOR_RE = re.compile(r"\s*[-–—]\s*")
    MIN_HYPHEN_TAG_COUNT = 4

    # ============================================================
    # WRAPPED SEPARATOR LIST
    #
    # [반팔/긴팔/7부/루즈핏/기모ver]
    # (블랙,화이트,네이비)
    # ============================================================

    WRAPPED_RE = re.compile(
        r"""
        (?P<open>[\(\[])
        (?P<body>[^()\[\]]+)
        (?P<close>[\)\]])
        """,
        re.VERBOSE,
    )

    # ============================================================
    # TRAILING SEPARATOR LIST
    #
    # 상품명 ... 반팔/긴팔/루즈핏
    # ============================================================

    TRAILING_LIST_RE = re.compile(
        r"""
        (?P<body>
            (?:[/|;]\s*[^/|;()\[\]]+){3,}
        )
        \s*
        $
        """,
        re.VERBOSE,
    )

    # ============================================================
    # TRAILING SPACE SEO BLOCK
    #
    # ABLY 계열에서 자주 등장하는:
    #
    # [비베이직 자체제작 제작상품 스탠다드핏
    #  반소매 기본템 꾸안꾸 데일리 사계절]
    #
    # 반드시 문자열 끝의 []만 본다.
    # ============================================================

    TRAILING_SPACE_BLOCK_RE = re.compile(
        r"""
        (?P<block>
            \[
            (?P<body>
                [^\[\]]+
            )
            \]
        )
        \s*
        $
        """,
        re.VERBOSE,
    )

    # 공백형 SEO block으로 인정하기 위한 최소 토큰 수.
    #
    # [B-BASIC]
    # [BLACK]
    # [MADE]
    #
    # 같은 label을 보호하기 위해 충분히 보수적으로 둔다.
    MIN_SPACE_TAG_COUNT = 4

    # 지나치게 긴 개별 token은 설명문일 가능성이 높다.
    MAX_TAG_LENGTH = 30

    # ============================================================
    # PUBLIC
    # ============================================================

    @classmethod
    def detect(
        cls,
        text: str | None,
    ) -> list[TagListMatch]:

        raw = str(
            text or ""
        )

        if not raw:
            return []

        results: list[
            TagListMatch
        ] = []

        # --------------------------------------------------------
        # 1. (...) / [...] 내부 separator 나열
        # --------------------------------------------------------

        for match in cls.WRAPPED_RE.finditer(
            raw
        ):
            body = (
                match.group("body")
                or ""
            ).strip()

            # separator가 실제로 존재해야 한다.
            #
            # [B-BASIC]
            # [BLACK]
            #
            # 같은 label은 여기서 제외.
            has_standard_separator = cls._has_separator(body)
            is_trailing_wrapper = not raw[match.end():].strip()
            has_hyphen_chain = (
                is_trailing_wrapper
                and cls._looks_like_hyphen_tag_chain(body)
            )

            if not has_standard_separator and not has_hyphen_chain:
                continue

            items = (
                cls._split(body)
                if has_standard_separator
                else cls._split_hyphen_chain(body)
            )

            if not cls._looks_like_tag_list(items):
                continue

            results.append(
                TagListMatch(
                    raw=match.group(0),
                    normalized=" ".join(
                        items
                    ),
                    start=match.start(),
                    end=match.end(),
                    match_type=(
                        "WRAPPED_TAG_LIST"
                    ),
                    confidence="HIGH",
                    value={
                        "items": items,
                        "wrapper": (
                            match.group(
                                "open"
                            )
                        ),
                    },
                )
            )

        # --------------------------------------------------------
        # 2. wrapper 없는 후행 separator 나열
        # --------------------------------------------------------
        # 여기서는 제거하지 않는다.
        #
        # naked slash list는 Structural 단계에서 ITEM 의미를 알 수 없어
        # 실제 상품명 본체까지 TAG_LIST로 먹을 위험이 크다.
        #
        # 예:
        #   원피스인기팅커벨 미니원피스/레이어드원피스/...
        #
        # 이런 전행/후행 SEO 경계는 Semantic 분석 이후
        # ProductCoreNameBuilder의 ITEM anchor boundary에서 판단한다.

        # --------------------------------------------------------
        # 3. 문자열 끝의 공백형 [] SEO block
        #
        # 핵심 추가 부분.
        #
        # [비베이직 자체제작 제작상품 스탠다드핏
        #  반소매 기본템 꾸안꾸 데일리 사계절]
        #
        # Semantic에는 RAW 전체가 전달되므로
        # 이 안의 DictionaryTerm도 그대로 추출된다.
        #
        # Structural에서는 wrapper 전체를 remove=True로
        # 전달하여 core_name에서만 제거한다.
        # --------------------------------------------------------

        space_match = (
            cls.TRAILING_SPACE_BLOCK_RE.search(
                raw
            )
        )

        if space_match is not None:
            start = space_match.start(
                "block"
            )

            end = space_match.end(
                "block"
            )

            # 앞에 실제 상품명 본체가 있어야 한다.
            prefix = raw[
                :start
            ].strip()

            if prefix:
                body = (
                    space_match.group(
                        "body"
                    )
                    or ""
                ).strip()

                items = (
                    cls._split_space_block(
                        body
                    )
                )

                if (
                    cls._looks_like_space_tag_list(
                        items
                    )
                ):
                    # 기존 separator 기반 wrapped list와
                    # 같은 span이면 중복 추가하지 않는다.
                    if not cls._overlaps(
                        start,
                        end,
                        [
                            (
                                row.start,
                                row.end,
                            )
                            for row
                            in results
                        ],
                    ):
                        results.append(
                            TagListMatch(
                                raw=(
                                    space_match.group(
                                        "block"
                                    )
                                ),
                                normalized=(
                                    " ".join(
                                        items
                                    )
                                ),
                                start=start,
                                end=end,
                                match_type=(
                                    "TRAILING_SPACE_TAG_LIST"
                                ),
                                confidence="HIGH",
                                value={
                                    "items": items,
                                    "wrapper": "[",
                                },
                            )
                        )

        return cls._deduplicate(
            results
        )

    @classmethod
    def _has_separator(
        cls,
        value: str,
    ) -> bool:
        return bool(
            re.search(
                r"[/|,·•;]",
                value,
            )
        )

    @classmethod
    def _looks_like_hyphen_tag_chain(
        cls,
        value: str,
    ) -> bool:
        # 하이픈은 정상 패션 용어에도 많이 쓰이므로 trailing wrapper에서만
        # 최소 4개 이상의 keyword chain일 때 SEO block으로 인정한다.
        items = cls._split_hyphen_chain(value)

        if len(items) < cls.MIN_HYPHEN_TAG_COUNT:
            return False

        if any(len(item) > cls.MAX_TAG_LENGTH for item in items):
            return False

        # 문장형 설명을 잘못 제거하지 않도록 각 조각은 짧은 tag 형태여야 한다.
        short_items = sum(1 for item in items if len(item) <= 20)
        return short_items / len(items) >= 0.8

    @classmethod
    def _split_hyphen_chain(
        cls,
        value: str,
    ) -> list[str]:
        return [
            item.strip()
            for item in cls.HYPHEN_SEPARATOR_RE.split(str(value or ""))
            if item.strip()
        ]

    @staticmethod
    def _split_space_block(
        value: str,
    ) -> list[str]:
        return [
            item.strip()
            for item in re.split(
                r"\s+",
                str(value or "").strip(),
            )
            if item.strip()
        ]

    @classmethod
    def _looks_like_space_tag_list(
        cls,
        items: list[str],
    ) -> bool:
        if len(items) < cls.MIN_SPACE_TAG_COUNT:
            return False

        if any(
            len(item) > cls.MAX_TAG_LENGTH
            for item in items
        ):
            return False

        return all(bool(item) for item in items)

    @classmethod
    def _split(
        cls,
        value: str,
    ) -> list[str]:
        return [
            item.strip()
            for item in cls.SEPARATOR_RE.split(value)
            if item.strip()
        ]

    @staticmethod
    def _looks_like_tag_list(
        items: list[str],
    ) -> bool:
        # 2개짜리:
        # 블랙/화이트
        # 울/캐시미어
        # S/M
        # 같은 정상 옵션일 가능성이 너무 높음.
        if len(items) < 3:
            return False

        # 너무 긴 문장은 tag가 아니라 설명문일 가능성.
        if any(len(item) > 30 for item in items):
            return False

        return True

    @staticmethod
    def _overlaps(
        start: int,
        end: int,
        spans: list[tuple[int, int]],
    ) -> bool:
        return any(
            start < right and end > left
            for left, right in spans
        )

    @staticmethod
    def _deduplicate(
        rows: list[TagListMatch],
    ) -> list[TagListMatch]:
        rows = sorted(
            rows,
            key=lambda x: (
                x.start,
                -(x.end - x.start),
            ),
        )

        result: list[TagListMatch] = []

        for row in rows:
            if any(
                row.start < saved.end
                and row.end > saved.start
                for saved in result
            ):
                continue

            result.append(row)

        return result

# ============================================================================
# ProductStructuralAnalyzer
# ============================================================================
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StructuralSpan:
    category: str
    subtype: str
    raw: str
    start: int
    end: int
    value: Any = None
    remove_from_core: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "subtype": self.subtype,
            "raw": self.raw,
            "start": self.start,
            "end": self.end,
            "value": self.value,
            "remove_from_core": self.remove_from_core,
        }


@dataclass
class StructuralAnalysis:
    spans: list[StructuralSpan] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


class ProductStructuralAnalyzer:
    """상품명에서 사전 의미분석 전에 구조 메타를 먼저 분리한다."""

    def analyze(
        self,
        text: str | None,
        *,
        source=None,
        allow_bare_numeric_size: bool = False,
    ) -> StructuralAnalysis:
        raw = str(text or "")
        spans: list[StructuralSpan] = []
        attributes: dict[str, Any] = {}

        marketing = MarketingDetector.detect(raw, source=source)
        sizes = SizeDetector.detect(
            raw,
            allow_bare_numeric=allow_bare_numeric_size,
        )
        seasons = ProductSeasonDetector.detect(raw)
        genders = GenderDetector.detect(raw)
        meta = ProductMetaDetector.detect(raw)
        tag_lists = TagListDetector.detect(raw)

        source_code = str(
            getattr(source, "code", source) or ""
        ).strip().lower()

        # Musinsa / KREAM은 상품 식별에 성별 표현이 중요하다.
        # gender attribute 추출은 그대로 수행하되 normalized_name에서는
        # 원문에 있던 남성/여성/맨즈/우먼즈 등을 제거하지 않는다.
        preserve_gender_in_core = source_code in {
            "musinsa",
            "kream",
        }

        for category, rows in (
            ("MARKETING", marketing),
            ("SIZE", sizes),
            ("SEASON", seasons),
            ("GENDER", genders),
            ("PRODUCT_META", meta),
            ("TAG_LIST", tag_lists),
        ):
            for row in rows:
                remove = True

                if preserve_gender_in_core and category == "GENDER":
                    remove = False

                # 여성 D / 남성 2E 같은 TARGET_WIDTH는 성별과 폭이
                # 하나의 span이므로 일부만 제거하면 성별까지 사라진다.
                # 보수적 플랫폼에서는 원문 식별 정보를 통째로 보존한다.
                if (
                    preserve_gender_in_core
                    and category == "PRODUCT_META"
                    and getattr(row, "meta_type", None) == "TARGET_WIDTH"
                ):
                    remove = False

                spans.append(
                    self._span(
                        category,
                        row,
                        remove=remove,
                    )
                )

        blocked = [(x.start, x.end) for x in spans]
        codes = ProductCodeDetector.detect(raw, blocked_spans=blocked)
        for row in codes:
            confidence = str(getattr(row, "confidence", "") or "").upper()
            spans.append(
                self._span(
                    "PRODUCT_CODE",
                    row,
                    remove=(confidence == "HIGH"),
                )
            )

        self._add_attributes(attributes, sizes, seasons, genders, meta, codes)
        spans.sort(key=lambda x: (x.start, x.end))
        return StructuralAnalysis(spans=spans, attributes=attributes)

    @staticmethod
    def _span(category: str, row, *, remove: bool) -> StructuralSpan:
        subtype = (
            getattr(row, "marketing_type", None)
            or getattr(row, "size_type", None)
            or getattr(row, "season_type", None)
            or getattr(row, "gender_type", None)
            or getattr(row, "meta_type", None)
            or getattr(row, "code_type", None)
            or getattr(row, "match_type", None)
            or category
        )
        value = getattr(row, "value", None)
        if value is None:
            value = getattr(row, "normalized", None)
        return StructuralSpan(
            category=category,
            subtype=str(subtype),
            raw=str(getattr(row, "raw", "")),
            start=int(getattr(row, "start")),
            end=int(getattr(row, "end")),
            value=value,
            remove_from_core=remove,
        )

    @staticmethod
    def _add_attributes(attributes, sizes, seasons, genders, meta, codes):
        def add(key, value):
            if value in (None, "", [], {}):
                return
            attributes.setdefault(key, [])
            if value not in attributes[key]:
                attributes[key].append(value)

        for row in sizes:
            add("sizes", getattr(row, "value", None) or getattr(row, "normalized", None))
        for row in seasons:
            add("season_codes", getattr(row, "normalized", None) or getattr(row, "raw", None))
        for row in genders:
            add("genders", getattr(row, "value", None) or getattr(row, "normalized", None))
        for row in meta:
            add("product_meta", {
                "type": getattr(row, "meta_type", None),
                "raw": getattr(row, "raw", None),
                "value": getattr(row, "value", None),
            })
        for row in codes:
            add("product_codes", {
                "code": getattr(row, "normalized", None) or getattr(row, "value", None),
                "type": getattr(row, "code_type", None),
                "confidence": getattr(row, "confidence", None),
            })
