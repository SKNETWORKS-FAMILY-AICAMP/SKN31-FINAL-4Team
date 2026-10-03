from __future__ import annotations

import re


REMOVE_PATTERNS = [
    r"copyright",
    r"all rights reserved",
    r"https?://",
    r"www\.",
]


def clean_ocr_text(
    text: str,
) -> str:

    if not text:
        return ""

    lines = text.splitlines()

    cleaned_lines = []

    seen = set()

    for line in lines:

        line = line.strip()

        if not line:
            continue

        line = re.sub(
            r"[•●■◆※]+",
            " ",
            line,
        )

        line = re.sub(
            r"\s+",
            " ",
            line,
        )

        lowered = line.lower()

        if any(
            re.search(
                pattern,
                lowered,
                flags=re.IGNORECASE,
            )
            for pattern in REMOVE_PATTERNS
        ):
            continue

        if len(line) <= 1:
            continue

        # 중복 OCR 제거
        dedupe_key = lowered

        if dedupe_key in seen:
            continue

        seen.add(
            dedupe_key
        )

        cleaned_lines.append(
            line
        )

    return "\n".join(
        cleaned_lines
    )