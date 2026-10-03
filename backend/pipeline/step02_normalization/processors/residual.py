from __future__ import annotations

import re
import unicodedata
from typing import Iterable


class ProductResidualBuilder:
    """
    RAW 상품명에서 이미 분석에 소비된 표현을 제거하고
    아직 해석되지 않은 표현만 residual tag로 만든다.

    핵심 원칙
    ---------
    1. DictionaryTerm으로 매칭된 surface는 residual에서 제외한다.
    2. Structural span은 remove_from_core 여부와 무관하게
       이미 구조 분석에 소비된 표현이므로 residual에서 제외한다.
    3. remove_from_core는 CoreName 정책이고 residual 소비 여부와는 별개다.
    4. punctuation-only / underscore-only 찌꺼기는 residual로 만들지 않는다.
    """

    SPLIT_RE = re.compile(
        r"[\s,/|+·•;:()\[\]{}<>]+"
    )

    def build(
        self,
        *,
        raw_name: str,
        used_surfaces: Iterable[str] | None = None,
        structural_surfaces: Iterable[str] | None = None,
        structural_tags: Iterable[str] | None = None,
    ) -> list[str]:
        text = unicodedata.normalize(
            "NFKC",
            str(raw_name or ""),
        )

        # Dictionary + Structural에서 이미 분석된 표현은 모두 소비 처리한다.
        # Structural은 remove_from_core 여부와 관계없이 여기에 들어와야 한다.
        consumed_surfaces = [
            *(used_surfaces or []),
            *(structural_surfaces or []),
        ]

        # 긴 표현부터 제거해야 짧은 surface가 긴 표현 일부를 먼저 먹지 않는다.
        for surface in self._sorted_unique(consumed_surfaces):
            text = re.sub(
                re.escape(surface),
                " ",
                text,
                flags=re.IGNORECASE,
            )

        tokens: list[str] = []

        for token in self.SPLIT_RE.split(text):
            token = self._clean_token(token)

            if not token:
                continue

            tokens.append(token)

        # 구조 파서가 별도 보존한 tag가 있다면 추가하되,
        # 이미 소비된 표현은 다시 residual로 살리지 않는다.
        consumed_keys = {
            self._normalize_key(value)
            for value in consumed_surfaces
            if str(value or "").strip()
        }

        for tag in structural_tags or []:
            tag = self._clean_token(tag)

            if not tag:
                continue

            if self._normalize_key(tag) in consumed_keys:
                continue

            tokens.append(tag)

        return self._dedupe(tokens)

    @staticmethod
    def _normalize_key(value: str) -> str:
        return unicodedata.normalize(
            "NFKC",
            str(value or ""),
        ).strip().casefold()

    @staticmethod
    def _clean_token(value: str) -> str:
        value = unicodedata.normalize(
            "NFKC",
            str(value or ""),
        ).strip()

        if not value:
            return ""

        # Python의 \w에는 underscore가 포함된다.
        # 상품코드 제거 후 남는 '_' / '__' 같은 찌꺼기를 명시적으로 제거한다.
        value = re.sub(
            r"^[\W_]+|[\W_]+$",
            "",
            value,
            flags=re.UNICODE,
        )

        value = value.strip()

        # 혹시 punctuation만 남은 경우 최종 방어.
        if not re.search(r"[0-9A-Za-z가-힣]", value):
            return ""

        return value

    @classmethod
    def _sorted_unique(
        cls,
        values: Iterable[str],
    ) -> list[str]:
        rows: list[str] = []
        seen: set[str] = set()

        for value in values:
            value = str(value or "").strip()

            if not value:
                continue

            key = cls._normalize_key(value)

            if key in seen:
                continue

            seen.add(key)
            rows.append(value)

        return sorted(
            rows,
            key=len,
            reverse=True,
        )

    @classmethod
    def _dedupe(
        cls,
        values: Iterable[str],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for value in values:
            value = str(value or "").strip()

            if not value:
                continue

            key = cls._normalize_key(value)

            if key in seen:
                continue

            seen.add(key)
            result.append(value)

        return result
