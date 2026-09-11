from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Part:
    text: str
    role: str


@dataclass
class CompoundResult:
    is_compound: bool
    label: str
    parts: list[Part]
    reason: str | None = None


class CompoundResolver:
    """
    v4:
    - 2-way split에서 종료하지 않고 multi-part segmentation.
    - longest-match + DP 방식으로 전체 문자열을 역할 토큰들로
      완전히 설명할 수 있을 때만 COMPONENT 처리.
    - 문자열 자체 blacklist가 아니라 역할 lexicon 사용.

    예:
    팬츠장바구니쿠폰
    → 팬츠(KNOWN_TERM) + 장바구니(COMMERCE) + 쿠폰(COMMERCE)

    간절기아우터
    → 간절기(METADATA_SEASON) + 아우터(CATEGORY/KNOWN_TERM)

    무신사단독
    → 무신사(BRAND/CATEGORY) + 단독(MARKETING)
    """

    METADATA = {
        "여성": "METADATA_GENDER",
        "여자": "METADATA_GENDER",
        "남성": "METADATA_GENDER",
        "남자": "METADATA_GENDER",
        "공용": "METADATA_GENDER",
        "유니섹스": "METADATA_GENDER",
        "봄": "METADATA_SEASON",
        "여름": "METADATA_SEASON",
        "가을": "METADATA_SEASON",
        "겨울": "METADATA_SEASON",
        "간절기": "METADATA_SEASON",
        "ss": "METADATA_SEASON",
        "fw": "METADATA_SEASON",
        "spring": "METADATA_SEASON",
        "summer": "METADATA_SEASON",
        "fall": "METADATA_SEASON",
        "autumn": "METADATA_SEASON",
        "winter": "METADATA_SEASON",
    }

    MARKETING = {
        "단독": "MARKETING",
        "한정": "MARKETING",
        "특가": "MARKETING",
        "할인": "MARKETING",
        "기획": "MARKETING",
        "에디션": "MARKETING",
        "셀러": "MARKETING",
    }

    COMMERCE = {
        "쿠폰": "COMMERCE",
        "장바구니": "COMMERCE",
        "무료배송": "COMMERCE",
        "배송": "COMMERCE",
        "혜택": "COMMERCE",
        "적립": "COMMERCE",
        "가격": "COMMERCE",
        "판매": "COMMERCE",
    }

    INTENT = {
        "추천": "INTENT",
        "코디": "INTENT",
        "선물": "INTENT",
        "pick": "INTENT",
    }

    ALLOWED_COMPOUND_ROLES = {
        "KNOWN_TERM",
        "BRAND",
        "CATEGORY",
        "METADATA_GENDER",
        "METADATA_SEASON",
        "MARKETING",
        "COMMERCE",
        "INTENT",
    }

    def __init__(self, dictionary_guard):
        self.guard = dictionary_guard

    def _role(self, text: str) -> str | None:
        normalized = self.guard.normalize(text)

        if not normalized:
            return None

        known_role = self.guard.role_of(normalized)
        if known_role:
            return known_role

        if normalized in self.METADATA:
            return self.METADATA[normalized]

        if normalized in self.MARKETING:
            return self.MARKETING[normalized]

        if normalized in self.COMMERCE:
            return self.COMMERCE[normalized]

        if normalized in self.INTENT:
            return self.INTENT[normalized]

        return None

    def _candidate_parts(self, text: str, start: int):
        """
        start 위치에서 시작하는 모든 role-match 반환.
        긴 match 우선.
        """
        matches = []

        for end in range(len(text), start, -1):
            piece = text[start:end]
            role = self._role(piece)

            if role:
                matches.append(
                    (end, Part(piece, role))
                )

        return matches

    def _segment_full(self, text: str) -> list[Part] | None:
        """
        DP/backtracking.
        전체 문자열을 role token으로 100% 설명할 수 있어야 성공.
        """
        memo: dict[int, list[Part] | None] = {}

        def solve(start: int):
            if start == len(text):
                return []

            if start in memo:
                return memo[start]

            for end, part in self._candidate_parts(
                text,
                start,
            ):
                rest = solve(end)

                if rest is not None:
                    memo[start] = [part] + rest
                    return memo[start]

            memo[start] = None
            return None

        return solve(0)

    @staticmethod
    def _is_meaningful_compound(
        parts: list[Part],
    ) -> bool:
        if len(parts) < 2:
            return False

        roles = {part.role for part in parts}

        # KNOWN/CATEGORY/BRAND 조합
        if (
            "KNOWN_TERM" in roles
            or "CATEGORY" in roles
            or "BRAND" in roles
        ):
            return True

        # metadata + commerce/marketing/intention도 신규 패션 용어는 아님
        if any(
            role.startswith("METADATA_")
            for role in roles
        ) and roles.intersection(
            {"MARKETING", "COMMERCE", "INTENT"}
        ):
            return True

        return False

    def resolve(self, text: str) -> CompoundResult:
        normalized = self.guard.normalize(text)

        if not normalized or len(normalized) < 2:
            return CompoundResult(
                is_compound=False,
                label="NOT_COMPOUND",
                parts=[],
            )

        # 공백/구두점 정규화 후 붙여쓰기 기준으로 검사
        compact = normalized.replace(" ", "")

        parts = self._segment_full(compact)

        if not parts:
            return CompoundResult(
                is_compound=False,
                label="NOT_COMPOUND",
                parts=[],
            )

        if not self._is_meaningful_compound(parts):
            return CompoundResult(
                is_compound=False,
                label="NOT_COMPOUND",
                parts=parts,
            )

        reason = " + ".join(
            f"{part.text}({part.role})"
            for part in parts
        )

        return CompoundResult(
            is_compound=True,
            label="COMPONENT",
            parts=parts,
            reason=reason,
        )
