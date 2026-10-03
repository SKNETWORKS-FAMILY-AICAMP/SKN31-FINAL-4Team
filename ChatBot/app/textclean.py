"""수집 원문에서 화면에 낼 수 있는 짧은 문장을 만든다.

왜 따로 두나 — 지저분함의 종류가 서로 다르고, 지우는 순서가 결과를 바꾼다.
  1) `&lt;아디다스&gt;` : 크롤러가 HTML 엔티티를 그대로 저장한 것.  ← 되돌린다
  2) `<아디다스>`     : 되돌리고 나면 남는 꺾쇠.  ← 진짜 태그가 아니면 껍데기만 벗긴다
  3) `<b>`, `<br/>`   : 진짜 태그.  ← 통째로 지운다
  4) `http://…`       : 본문에 붙어 온 링크.  ← 근거 문장에서는 소음이다
2를 1보다 먼저 하면 `&lt;아디다스&gt;` 는 살아남는다. 순서를 바꾸지 말 것.
"""
from __future__ import annotations

import html
import re

# 진짜 HTML 태그로 볼 것 — 여는/닫는/자기완결, 이름이 ASCII 로 시작
_REAL_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>")
# 태그가 아닌 꺾쇠 묶음 — 안쪽만 남긴다
_FAKE_TAG = re.compile(r"<([^<>]{1,40})>")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
_MD = re.compile(r"(\*\*|__|~~|`+|^\s{0,3}#{1,6}\s+|^\s{0,3}>\s?)", re.M)
_INVISIBLE = re.compile(r"[​-‏  ﻿\xa0]")
_WS = re.compile(r"\s+")
_REPEAT = re.compile(r"([!?~.,ㅋㅎㅠㅜ])\1{2,}")
# 문장 끝으로 볼 자리
_SENT_END = re.compile(r"[.!?…]|다\.|요\.|죠\.")


def unescape_entities(s: str) -> str:
    """두 번까지만 되돌린다. `&amp;lt;` 같은 이중 인코딩이 실제로 있다."""
    for _ in range(2):
        t = html.unescape(s)
        if t == s:
            break
        s = t
    return s


_CLOSERS = "]})>"
_OPENERS = "[({<"


def _drop_orphan_close(s: str) -> str:
    """`엄브로] 클래식 나일론…` 처럼 여는 짝 없이 남은 닫는 괄호를 앞부분에서 걷어낸다.

    span 을 자를 때 `[브랜드명] 상품명` 의 뒤쪽 절반만 잡히면 이런 꼴이 된다.
    앞 12자 안에서만 본다 — 뒤쪽의 닫는 괄호는 대개 짝이 있는 진짜 괄호다.
    """
    head = s[:12]
    for i, ch in enumerate(head):
        if ch in _CLOSERS and not any(o in s[:i] for o in _OPENERS):
            return s[i + 1:].lstrip(" ,.")
    return s


def clean_text(s: str | None) -> str:
    """근거·인용에 쓸 문자열을 씻는다. 길이는 건드리지 않는다."""
    if not s:
        return ""
    s = unescape_entities(str(s))
    s = _REAL_TAG.sub(" ", s)      # ① 진짜 태그는 통째로
    s = _FAKE_TAG.sub(r"\1", s)    # ② 꺾쇠만 벗기고 안쪽 말은 살린다
    s = _URL.sub(" ", s)
    s = _MD.sub("", s)
    s = _INVISIBLE.sub(" ", s)
    s = _REPEAT.sub(r"\1\1", s)
    s = _WS.sub(" ", s).strip()
    s = re.sub(r'\.{2,}\s*$', '…', s)
    s = _drop_orphan_close(s)
    # 앞뒤에 남은 구두점 껍데기
    s = s.strip(" -–—·|/\\\"'“”‘’[](){}")
    return s


def trim(s: str, limit: int = 90) -> str:
    """자를 때 말 중간에서 끊지 않는다.

    근거는 짧아야 읽힌다. 문장 끝이 limit 안에 있으면 거기서 끊고,
    없으면 어절 경계에서 끊고 말줄임을 붙인다.
    """
    s = s.strip()
    if len(s) <= limit:
        return s
    head = s[: limit + 1]
    ends = [m.end() for m in _SENT_END.finditer(head)]
    if ends and ends[-1] >= limit * 0.5:
        return head[: ends[-1]].strip()
    cut = head.rfind(" ")
    if cut < limit * 0.5:
        cut = limit
    return head[:cut].rstrip(" ,.·") + "…"


def snippet(s: str | None, limit: int = 90) -> str:
    return trim(clean_text(s), limit)


def sentence_with(body: str | None, needle: str, limit: int = 90) -> str:
    """본문에서 그 말이 들어 있는 문장 하나만 뽑는다 (opinion 근거가 없을 때의 대비책)."""
    txt = clean_text(body)
    if not txt:
        return ""
    if not needle or needle not in txt:
        return trim(txt, limit)
    parts = re.split(r"(?<=[.!?…])\s+|(?<=다)\s+(?=[가-힣])|\n+", txt)
    hit = [p for p in parts if needle in p]
    if not hit:
        return trim(txt, limit)
    best = min(hit, key=lambda p: abs(len(p) - limit))
    return trim(best.strip(), limit)
