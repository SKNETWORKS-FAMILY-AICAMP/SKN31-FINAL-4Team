from __future__ import annotations

import re
from dataclasses import dataclass


BOUNDARY = re.compile(
    r"[.!?！？…⋯~。\n]+|"
    r"[\U0001F300-\U0001FAFF\U0001F900-\U0001F9FF☀-➿⬀-⯿]+"
)
EVALUATION_CUE = re.compile(
    r"좋|예쁘|이쁘|만족|추천|편하|최고|괜찮|맘에|마음에|강추|가성비|"
    r"어울|따뜻|시원|부드럽|고급|찰떡|대박|사고\s*싶|사야|살까|샀|"
    r"구매|주문|별로|아쉽|실망|불편|후회|비추|애매|비싸|싫|최악|"
    r"보풀|늘어나|까칠|얇|두껍|작아|크다|불량|환불|반품|품절|재입고|"
    r"[?？]|까요|나요|어떤|어디|얼마|궁금|사이즈|핏|재질|소재|색"
)


@dataclass(frozen=True)
class EvidenceSpan:
    quote: str
    start: int | None
    end: int | None
    status: str
    reason: str = ""

    @property
    def valid(self) -> bool:
        return self.status in {"EXACT", "EXPANDED"}


def _segments(text: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    for match in BOUNDARY.finditer(text):
        if match.start() > cursor:
            result.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        result.append((cursor, len(text)))
    return result or [(0, len(text))]


def _containing_segment(
    segments: list[tuple[int, int]],
    start: int,
    end: int,
) -> tuple[int, int]:
    for left, right in segments:
        if left <= start < right and left < end <= right:
            return left, right
    return max(0, start - 60), min(end + 60, segments[-1][1])


def _occurrences(text: str, value: str) -> list[int]:
    if not value:
        return []
    out: list[int] = []
    cursor = 0
    while cursor <= len(text):
        index = text.find(value, cursor)
        if index < 0:
            break
        out.append(index)
        cursor = index + max(1, len(value))
    return out


def _choose_occurrence(
    text: str,
    value: str,
    positions: list[int],
    hint: int | None,
) -> int | None:
    if not positions:
        return None
    if hint is not None:
        return min(positions, key=lambda pos: abs(pos - hint))
    segments = _segments(text)
    with_cue = []
    for pos in positions:
        left, right = _containing_segment(segments, pos, pos + len(value))
        if EVALUATION_CUE.search(text[left:right]):
            with_cue.append(pos)
    return with_cue[0] if with_cue else positions[0]


def _expand_same_sentence(
    text: str,
    start: int,
    end: int,
    *,
    max_length: int,
) -> tuple[str, int, int]:
    segments = _segments(text)
    left, right = _containing_segment(segments, start, end)
    quote = text[left:right].strip()
    real_left = left + len(text[left:right]) - len(text[left:right].lstrip())
    real_right = real_left + len(quote)

    # 용어만 한 조각으로 끊긴 경우에만 바로 다음 문장을 붙인다. LLM이 준
    # 위치를 유지하므로 같은 단어가 여러 번 나와도 다른 자리로 이동하지 않는다.
    if len(quote) <= (end - start) + 4 or not EVALUATION_CUE.search(quote):
        following = next(((a, b) for a, b in segments if a >= right), None)
        if following and following[1] - left <= max_length:
            candidate = text[left:following[1]].strip()
            if EVALUATION_CUE.search(candidate) or len(quote) <= (end - start) + 4:
                quote = candidate
                real_left = left + len(text[left:following[1]]) - len(text[left:following[1]].lstrip())
                real_right = real_left + len(quote)

    if len(quote) > max_length:
        window_left = max(left, start - max_length // 3)
        window_right = min(len(text), window_left + max_length)
        if end > window_right:
            window_right = end
            window_left = max(0, window_right - max_length)
        quote = text[window_left:window_right].strip()
        real_left = window_left + len(text[window_left:window_right]) - len(text[window_left:window_right].lstrip())
        real_right = real_left + len(quote)
    return quote, real_left, real_right


def resolve_evidence(
    text: str,
    *,
    quote: str,
    surface: str,
    start: int | None = None,
    end: int | None = None,
    max_length: int = 220,
) -> EvidenceSpan:
    """LLM 근거를 원문에 고정하고, 키워드만 온 경우 같은 문장 안에서 복원한다.

    우선순위는 정확한 문자 위치 → 정확한 quote → 정확한 surface다. 세 경로가
    모두 실패하면 추측하지 않고 INVALID로 돌려보낸다.
    """

    text = str(text or "")
    quote = str(quote or "").strip()
    surface = str(surface or "").strip()
    if not text or not surface:
        return EvidenceSpan("", None, None, "INVALID", "본문 또는 표면형 없음")

    resolved_start: int | None = None
    resolved_end: int | None = None

    if isinstance(start, int) and isinstance(end, int):
        if 0 <= start < end <= len(text) and text[start:end] == quote:
            resolved_start, resolved_end = start, end

    if resolved_start is None and quote:
        positions = _occurrences(text, quote)
        resolved_start = _choose_occurrence(text, quote, positions, start)
        if resolved_start is not None:
            resolved_end = resolved_start + len(quote)

    if resolved_start is None:
        positions = _occurrences(text, surface)
        resolved_start = _choose_occurrence(text, surface, positions, start)
        if resolved_start is None:
            return EvidenceSpan("", None, None, "INVALID", "원문에 표면형 없음")
        resolved_end = resolved_start + len(surface)
        quote = surface

    assert resolved_end is not None
    if surface not in text[resolved_start:resolved_end]:
        surface_positions = _occurrences(text, surface)
        surface_start = _choose_occurrence(text, surface, surface_positions, resolved_start)
        if surface_start is None:
            return EvidenceSpan("", None, None, "INVALID", "근거에 표면형 없음")
        resolved_start = surface_start
        resolved_end = surface_start + len(surface)
        quote = surface

    too_short = len(quote) <= len(surface) + 4 or len(quote) < 12
    has_context = bool(EVALUATION_CUE.search(quote))
    if too_short or not has_context:
        expanded, left, right = _expand_same_sentence(
            text,
            resolved_start,
            resolved_end,
            max_length=max_length,
        )
        if surface not in expanded:
            return EvidenceSpan("", None, None, "INVALID", "확장 중 표면형 이탈")
        if len(expanded) <= len(surface) + 2:
            return EvidenceSpan("", None, None, "INVALID", "근거가 단어 수준")
        return EvidenceSpan(expanded, left, right, "EXPANDED", "같은 문장 안에서 확장")

    return EvidenceSpan(
        text[resolved_start:resolved_end],
        resolved_start,
        resolved_end,
        "EXACT",
    )
