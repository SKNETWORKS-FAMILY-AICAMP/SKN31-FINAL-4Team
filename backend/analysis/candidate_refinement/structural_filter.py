from __future__ import annotations

import re


class StructuralFilter:
    PURE_NUMBER_RE = re.compile(r"^\d+(?:[.,]\d+)?$")
    SYMBOL_ONLY_RE = re.compile(r"^[\W_]+$", flags=re.UNICODE)
    CODE_LIKE_RE = re.compile(
        r"^(?=.*[a-zA-Z])(?=.*\d)[a-zA-Z0-9._/-]{2,20}$"
    )

    def __init__(
        self,
        *,
        min_length: int = 2,
        max_length: int = 40,
    ):
        self.min_length = min_length
        self.max_length = max_length

    def check(
        self,
        value: str | None,
    ) -> tuple[bool, str]:
        text = str(value or "").strip()

        if not text:
            return False, "EMPTY"

        if len(text) < self.min_length:
            return False, "TOO_SHORT"

        if len(text) > self.max_length:
            return False, "TOO_LONG"

        if self.PURE_NUMBER_RE.fullmatch(text):
            return False, "PURE_NUMBER"

        if self.SYMBOL_ONLY_RE.fullmatch(text):
            return False, "SYMBOL_ONLY"

        if self.CODE_LIKE_RE.fullmatch(text):
            return False, "CODE_LIKE"

        return True, "PASS"
