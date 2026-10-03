from __future__ import annotations

import re
import unicodedata
from typing import Any


class ProductCoreNameBuilder:
    """
    FEEDIT normalized/core name builder.

    원칙
    ------------------------------------------------------------
    1. RAW 상품명을 기준으로 한다.
    2. Dictionary canonical term을 이어 붙여 상품명을 만들지 않는다.
    3. Structural Analyzer가 remove_from_core=True로 판단한 span만 제거한다.
    4. Noise Classifier가 REMOVE로 확정한 surface만 추가 제거한다.
    5. 제거 과정에서 생긴 punctuation / 빈 wrapper / 범위 표현 찌꺼기를 정리한다.
    6. 모르는 표현은 가능한 한 보존한다.
    """

    def build(
        self,
        *,
        raw_name: str,
        known_terms: list[dict[str, Any]] | None = None,
        structural_spans: list[dict[str, Any]] | None = None,
        noise_surfaces: list[str] | None = None,
        remove_spans: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:

        raw = str(raw_name or "")

        if not raw.strip():
            return {
                "core_name": "",
                "normalized_name": "",
                "used_surfaces": [],
                "used_term_ids": [],
                "core_terms": [],
                "removed_surfaces": [],
                "piece_count": None,
            }

        # semantic 결과를 canonical name으로 재조립하지 않는다.
        _ = known_terms

        removable: list[tuple[int, int, str]] = []

        # ========================================================
        # 1. STRUCTURAL SPANS
        # ========================================================

        for span in structural_spans or []:

            if not isinstance(span, dict):
                continue

            if span.get("remove_from_core") is not True:
                continue

            try:
                start = max(
                    0,
                    int(span.get("start", 0)),
                )
                end = min(
                    len(raw),
                    int(span.get("end", 0)),
                )
            except (TypeError, ValueError):
                continue

            if end <= start:
                continue

            removable.append(
                (
                    start,
                    end,
                    raw[start:end],
                )
            )

        # Unified ProductNameNoiseProcessor decisions.
        # Precise offsets are preferred over surface-wide deletion.
        for span in remove_spans or []:
            if str(span.get("action") or "").upper() != "REMOVE":
                continue
            try:
                start = max(0, int(span.get("start")))
                end = min(len(raw), int(span.get("end")))
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue
            removable.append((start, end, raw[start:end]))

        # ========================================================
        # 2. NOISE SURFACES
        # ========================================================

        # Noise classifier에서 REMOVE로 확정된 표현만 제거한다.
        #
        # 동일 surface가 RAW에 여러 번 있으면
        # 모든 exact occurrence를 제거한다.

        for surface in noise_surfaces or []:

            value = str(
                surface or ""
            ).strip()

            if not value:
                continue

            pattern = re.compile(
                re.escape(value),
                flags=re.IGNORECASE,
            )

            for match in pattern.finditer(raw):

                removable.append(
                    (
                        match.start(),
                        match.end(),
                        raw[
                            match.start():
                            match.end()
                        ],
                    )
                )

        # ========================================================
        # 3. MERGE OVERLAPPING SPANS
        # ========================================================

        merged: list[tuple[int, int]] = []

        for start, end, _ in sorted(
            removable,
            key=lambda row: (
                row[0],
                row[1],
            ),
        ):

            if (
                merged
                and start <= merged[-1][1]
            ):
                merged[-1] = (
                    merged[-1][0],
                    max(
                        merged[-1][1],
                        end,
                    ),
                )

            else:
                merged.append(
                    (
                        start,
                        end,
                    )
                )

        # ========================================================
        # 4. REMOVE
        # ========================================================

        chars = list(raw)

        for start, end in merged:

            for index in range(
                start,
                end,
            ):
                chars[index] = " "

        normalized_name = self._clean(
            "".join(chars)
        )

        # ========================================================
        # 5. SAFETY FALLBACK
        # ========================================================

        # detector 오탐으로 전부 삭제되는 경우
        # 빈 문자열 대신 RAW 최소 정리본을 보존한다.

        if not normalized_name:
            normalized_name = self._fallback_clean(
                raw
            )

        # ========================================================
        # 6. REMOVED SURFACES
        # ========================================================

        removed_surfaces: list[str] = []
        seen_removed: set[
            tuple[int, int, str]
        ] = set()

        for start, end, surface in removable:

            if not surface:
                continue

            key = (
                start,
                end,
                surface,
            )

            if key in seen_removed:
                continue

            seen_removed.add(key)

            removed_surfaces.append(
                surface
            )

        return {
            "core_name": normalized_name,
            "normalized_name": normalized_name,
            "used_surfaces": [],
            "used_term_ids": [],
            "core_terms": [],
            "removed_surfaces": removed_surfaces,
            "piece_count": None,
        }

    # ============================================================
    # CLEAN
    # ============================================================

    @classmethod
    def _clean(
        cls,
        value: str,
    ) -> str:

        text = unicodedata.normalize(
            "NFKC",
            str(value or ""),
        )

        # ========================================================
        # 1. CONTROL CHARACTERS
        # ========================================================

        text = "".join(
            char
            for char in text
            if (
                char in "\n\t"
                or unicodedata.category(
                    char
                )[0] != "C"
            )
        )

        # ========================================================
        # 2. WRAPPER 내부 연속 SEPARATOR
        #
        # [가을/ /Essential]
        # -> [가을/Essential]
        # ========================================================

        text = re.sub(
            r"([/|,+·;:])\s*(?=[/|,+·;:])",
            "",
            text,
        )

        # wrapper 시작 직후 separator

        text = re.sub(
            r"([\[\(\{])"
            r"\s*[/|,+·;:]+\s*",
            r"\1",
            text,
        )

        # wrapper 종료 직전 separator

        text = re.sub(
            r"\s*[/|,+·;:]+\s*"
            r"([\]\)\}])",
            r"\1",
            text,
        )

        # ========================================================
        # 3. SLASH 주변 공백
        # ========================================================

        text = re.sub(
            r"\s*/\s*",
            "/",
            text,
        )

        # ========================================================
        # 4. STRUCTURAL 제거 후 SIZE RANGE 찌꺼기
        #
        # (~XXL까지)
        # -> (~ 까지)
        # -> 삭제
        #
        # (XXL까지)
        # -> (까지)
        # -> 삭제
        #
        # (44~99)
        # -> (~)
        # -> 삭제
        #
        # [~ 까지]
        # -> 삭제
        # ========================================================

        text = re.sub(
            r"""
            \(
                \s*
                [~～\-–—_/|.,·:;]*
                \s*
                (?:까지|부터)?
                \s*
                [~～\-–—_/|.,·:;]*
                \s*
            \)
            """,
            " ",
            text,
            flags=re.VERBOSE,
        )

        text = re.sub(
            r"""
            \[
                \s*
                [~～\-–—_/|.,·:;]*
                \s*
                (?:까지|부터)?
                \s*
                [~～\-–—_/|.,·:;]*
                \s*
            \]
            """,
            " ",
            text,
            flags=re.VERBOSE,
        )

        text = re.sub(
            r"""
            \{
                \s*
                [~～\-–—_/|.,·:;]*
                \s*
                (?:까지|부터)?
                \s*
                [~～\-–—_/|.,·:;]*
                \s*
            \}
            """,
            " ",
            text,
            flags=re.VERBOSE,
        )

        # ========================================================
        # 5. EMPTY WRAPPER
        # ========================================================

        text = cls._remove_empty_wrappers(
            text
        )

        # ========================================================
        # 6. WRAPPER 내부 양끝 공백
        # ========================================================

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

        text = re.sub(
            r"\{\s+",
            "{",
            text,
        )
        text = re.sub(
            r"\s+\}",
            "}",
            text,
        )

        # ========================================================
        # 7. 닫는 WRAPPER와 상품명 사이 공백
        #
        # [기모]시그니처
        # -> [기모] 시그니처
        # ========================================================

        text = re.sub(
            r"([\]\)\}])"
            r"(?=[가-힣A-Za-z0-9])",
            r"\1 ",
            text,
        )

        # ========================================================
        # 8. UNDERSCORE
        #
        # structural 삭제 뒤 남은 underscore는
        # 공백 separator로 취급
        # ========================================================

        text = re.sub(
            r"\s*_\s*",
            " ",
            text,
        )

        # underscore 제거 후 빈 wrapper가 될 수 있으므로 재검사

        text = cls._remove_empty_wrappers(
            text
        )

        # ========================================================
        # 9. DECORATIVE PUNCTUATION
        # 의미 연결자인 + / - 는 건드리지 않는다. 장식 문자만 정리한다.
        # ========================================================
        text = re.sub(r"[★☆♥♡◆◇※]+", " ", text)
        text = re.sub(r"\*{1,}", " ", text)
        text = re.sub(r"[!！?？]{1,}", " ", text)

        # ========================================================
        # 10. WHITESPACE
        # ========================================================

        text = re.sub(
            r"[ \t]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s*\n\s*",
            " ",
            text,
        )

        text = text.strip()

        # ========================================================
        # 10. LEADING ORPHAN PUNCTUATION
        #
        # 특가!! 상품
        # -> !! 상품
        # -> 상품
        #
        # 4268. 상품
        # -> . 상품
        # -> 상품
        #
        # 당일출고! 상품
        # -> ! 상품
        # -> 상품
        # ========================================================

        text = re.sub(
            r"""
            ^
            \s*
            [
                !！?？
                \.,，:
                ;|·•
                ~～
            ]+
            \s*
            """,
            "",
            text,
            flags=re.VERBOSE,
        )

        # ========================================================
        # 11. TRAILING ORPHAN PUNCTUATION
        # ========================================================

        text = re.sub(
            r"""
            \s*
            [
                !！?？
                \.,，:
                ;|·•
                ~～
            ]+
            \s*
            $
            """,
            "",
            text,
            flags=re.VERBOSE,
        )

        # ========================================================
        # 12. 양끝에 남은 STRUCTURAL SEPARATOR
        #
        # 상품명 내부의 -, /, + 등은 유지한다.
        # 양끝에 고립된 경우에만 제거한다.
        # ========================================================

        text = text.strip(
            " \t\r\n"
            "!！?？"
            ".,，"
            ":;"
            "-_"
            "/|"
            "+·•"
            "~～"
        )

        # ========================================================
        # 13. CLEANUP으로 새로 생긴 빈 wrapper 마지막 검사
        # ========================================================

        text = cls._remove_empty_wrappers(
            text
        )

        # ========================================================
        # 14. FINAL WHITESPACE
        # ========================================================

        text = re.sub(
            r"[ \t]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s*\n\s*",
            " ",
            text,
        )

        return text.strip()

    # ============================================================
    # EMPTY WRAPPER
    # ============================================================

    @staticmethod
    def _remove_empty_wrappers(
        value: str,
    ) -> str:

        text = str(value or "")

        previous = None

        while previous != text:

            previous = text

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

            text = re.sub(
                r"\{\s*\}",
                " ",
                text,
            )

            text = re.sub(
                r"<\s*>",
                " ",
                text,
            )

        return text

    # ============================================================
    # FALLBACK
    # ============================================================

    @classmethod
    def _fallback_clean(
        cls,
        value: str,
    ) -> str:
        """
        모든 제거 결과가 빈 문자열이 되었을 때만 사용한다.

        이 경우 RAW를 공격적으로 가공하지 않고
        Unicode / whitespace만 최소 정리한다.
        """

        text = unicodedata.normalize(
            "NFKC",
            str(value or ""),
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s*\n\s*",
            " ",
            text,
        )

        return text.strip()