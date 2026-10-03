"""LLM 이 뱉은 마크다운을 화면이 쓰는 형태로 바꾼다.

문제
  화면은 받은 글자를 전부 이스케이프해서 그린다 (chat_api.js esc()).
  안전하지만, 모델이 `**발레코어**` 나 `[출처](https://…)` 를 쓰면
  사용자 눈에는 별표와 대괄호가 그대로 보인다. 실제로 그렇게 보였다.

두 가지 길이 있었다.
  (가) 화면에서 마크다운을 렌더한다 → HTML 을 다시 허용해야 한다. 주입 경로가 열린다.
  (나) 서버에서 마크다운을 없앤다 → 화면은 계속 글자만 그린다.
  (나)를 택했다. 링크는 지우지 않고 **links 블록으로 옮긴다** —
  본문에 붙어 있던 주소가 사라지는 게 아니라 제자리를 찾는 것이다.

돌려주는 것
  {"text": 문단 사이 빈 줄 하나로 정리된 순수 텍스트,
   "links": [{"title","url"}]}
"""
from __future__ import annotations

import re

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_MD_LINK = re.compile(r"\[([^\]\n]{0,120})\]\((https?://[^\s)]+)\)")
_AUTOLINK = re.compile(r"<(https?://[^\s>]+)>")
_BARE_URL = re.compile(r"(?<![\w(])(https?://[^\s<>()\[\]]+)")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.S)
_ITALIC = re.compile(r"(?<![\w*_])([*_])([^\s*_][^*_]*?)\1(?![\w*_])")
_STRIKE = re.compile(r"~~(.+?)~~", re.S)
_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}[^\n]*$", re.M)   # 제목은 통째로 뺀다 — 블록에 title 이 따로 있다
_QUOTE = re.compile(r"^\s{0,3}>\s?", re.M)
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+", re.M)
_ORDERED = re.compile(r"^\s{0,3}(\d{1,2})[.)]\s+", re.M)
_RULE = re.compile(r"^\s{0,3}([-*_])\s*(?:\1\s*){2,}$", re.M)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)          # 표는 3~5문장 답변에 들어올 자리가 아니다
_FOOTNOTE = re.compile(r"\[\^?\d{1,2}\]")
# Responses API의 웹 검색 인용은 본문에 전용 표식으로 섞일 수 있다.
# 출처 URL·제목은 llm._sources()가 별도로 보존하므로 화면 문장에서는 표식만 뺀다.
_CITATION = re.compile(
    r"\ue200cite\ue202.*?\ue201"
    r"|(?:[▮▤▥▦▧▨▩█]+)?cite(?:[▮▤▥▦▧▨▩█]+)?"
    r"turn\d+(?:search|fetch|open)\d+"
    r"(?:(?:[▮▤▥▦▧▨▩█,;|·\s]+)turn\d+(?:search|fetch|open)\d+)*"
    r"(?:[▮▤▥▦▧▨▩█]+)?",
    re.I,
)
_BLANKS = re.compile(r"\n{3,}")
_TRAIL = re.compile(r"[ \t]+$", re.M)


def convert(md: str | None) -> dict:
    if not md:
        return {"text": "", "links": []}
    s = _CITATION.sub("", str(md))
    links: list[dict] = []
    seen: set[str] = set()

    def _take(title: str, url: str) -> None:
        u = url.rstrip(".,)”\"'")
        if u in seen:
            return
        seen.add(u)
        links.append({"title": (title or "").strip() or u, "url": u})

    s = _FENCE.sub(" ", s)
    s = _INLINE_CODE.sub(r"\1", s)

    def _link(m):
        _take(m.group(1), m.group(2))
        return m.group(1).strip()                 # 글에는 말만 남기고 주소는 옮긴다
    s = _MD_LINK.sub(_link, s)

    def _auto(m):
        _take("", m.group(1))
        return ""
    s = _AUTOLINK.sub(_auto, s)
    s = _BARE_URL.sub(_auto, s)

    s = _BOLD.sub(r"\2", s)
    s = _STRIKE.sub(r"\1", s)
    s = _ITALIC.sub(r"\2", s)
    s = _RULE.sub("", s)
    s = _TABLE_ROW.sub("", s)
    s = _HEADING_LINE.sub("", s)
    s = _QUOTE.sub("", s)
    s = _BULLET.sub("· ", s)
    s = _ORDERED.sub(r"\1. ", s)
    s = _FOOTNOTE.sub("", s)
    s = _TRAIL.sub("", s)
    # 주소를 걷어내고 나면 "· 참고:" 처럼 껍데기만 남는 줄이 생긴다
    s = "\n".join(ln for ln in s.split("\n")
                  if len(ln.strip().lstrip("·").strip(" :·-")) >= 4 or not ln.strip())
    s = _BLANKS.sub("\n\n", s)
    # 문장 사이에 끼어든 홑줄바꿈은 붙인다 — 모델이 넣은 줄바꿈은 문단이 아니라 습관이다
    s = re.sub(r"(?<![.\n!?…:·])\n(?!\n)(?![·\d])", " ", s)
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    return {"text": s, "links": links}


def first_sentence(text: str, limit: int = 140) -> str:
    """한 줄 결론으로 쓸 첫 문장. 문단 나눔·글머리표는 빼고 본다."""
    for line in (text or "").split("\n"):
        line = line.strip().lstrip("· ").strip()
        if len(line) < 8:
            continue
        m = re.search(r"^(.{8,}?[.!?…]|.{8,}?(?:입니다|습니다|이다|한다)\.)", line)
        out = (m.group(1) if m else line).strip()
        return out if len(out) <= limit else out[:limit].rstrip() + "…"
    return (text or "").strip()[:limit]


# ══════════════════════════════════════════════════════════
#  마크다운을 **그린다** — 새 경로(오케스트레이터) 답변용
# ══════════════════════════════════════════════════════════
#  ★ 이 파일 머리말은 (나) "서버에서 마크다운을 없앤다" 를 택했다고 적어 뒀다.
#    그 선택의 이유는 "화면에서 렌더하면 HTML 을 다시 허용해야 하니 주입 경로가
#    열린다" 였고, 예전 경로의 답이 **한 줄 결론**이라 지워도 잃을 게 없었다.
#
#    새 경로는 다르다. 답변이 목록과 강조가 있는 여러 문단이라, 별표만 지우면
#    문단이 통째로 한 덩어리가 되어 읽을 수 없다.
#    (2026-09-10 팝업 실측: "**온도:** 56° - **1주 변화:** 87°→56°" 가 별표째로,
#     줄바꿈도 없이 한 줄로 흘렀다.)
#
#    그래서 여기서는 **렌더하되 주입 경로는 먼저 막는다** — 이스케이프를 제일
#    앞에서 하고, 그 뒤에 우리가 아는 표시만 태그로 바꾼다. 모델이 <script> 를
#    써도 그때는 이미 글자다. 결과에 있는 태그는 전부 이 함수가 만든 것이다.
#    화면 계약("서버는 안전한 HTML 만 보낸다")은 그대로다 — 바뀐 것은
#    그 HTML 을 누가 만드느냐가 아니라, 무엇까지 살려 보내느냐다.
_H_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.S)
_H_ITALIC = re.compile(r"(?<![\w*_])([*_])([^\s*_][^*_]*?)\1(?![\w*_])")
_H_LINK = re.compile(r"\[([^\]\n]{0,120})\]\((https?://[^\s)]+)\)")
_H_BARE = re.compile(r"(?<![\w(=\"])(https?://[^\s<>()\[\]]+)")
_H_BULLET = re.compile(r"^\s{0,3}[-*+]\s+(.*)$")
_H_ORDERED = re.compile(r"^\s{0,3}(\d{1,2})[.)]\s+(.*)$")
_H_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.*)$")
_H_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _inline(s: str) -> str:
    """한 줄 안의 표시. **이스케이프가 끝난 글자**에만 쓴다."""
    s = _INLINE_CODE.sub(r"\1", s)
    s = _H_LINK.sub(
        lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">'
                  f'{m.group(1).strip() or m.group(2)}</a>', s)
    s = _H_BARE.sub(lambda m: f'<a href="{m.group(1)}" target="_blank" '
                              f'rel="noopener">{m.group(1)}</a>', s)
    s = _H_BOLD.sub(r"<b>\2</b>", s)
    s = _H_ITALIC.sub(r"<i>\2</i>", s)
    s = _STRIKE.sub(r"\1", s)
    return s


def to_html(md: str | None) -> str:
    """마크다운 → 화면이 그릴 수 있는 안전한 HTML.

    살리는 것: 문단 · 글머리표 · 번호 목록 · 굵게 · 기울임 · 링크.
    나머지(제목·인용·표·코드블록)는 문단으로 낮춘다 — 말풍선에는 그 자리가 없다.
    """
    if not md:
        return ""
    src = _CITATION.sub("", str(md))
    src = _FENCE.sub(" ", src)
    src = _RULE.sub("", src)
    src = _TABLE_ROW.sub("", src)

    out: list[str] = []
    buf: list[str] = []          # 쌓이는 문단
    kind = ""                    # 열려 있는 목록 ("ul" · "ol" · "")

    def close_list() -> None:
        nonlocal kind
        if kind:
            out.append(f"</{kind}>")
            kind = ""

    def flush() -> None:
        if buf:
            out.append("<p>" + " ".join(buf) + "</p>")
            buf.clear()

    # ★ 줄 종류는 **원문에서** 가려낸다. 이스케이프를 먼저 하면 인용의 ">" 가
    #   "&gt;" 가 되어 못 알아본다. 이스케이프는 알맹이에만 건다(_line).
    def _line(t: str) -> str:
        return _inline(_esc(t))

    for raw in src.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flush(); close_list()
            continue
        m = _H_BULLET.match(line)
        o = _H_ORDERED.match(line) if not m else None
        if m or o:
            flush()
            want = "ul" if m else "ol"
            if kind != want:
                close_list()
                out.append(f"<{want}>")
                kind = want
            out.append("<li>" + _line(m.group(1) if m else o.group(2)) + "</li>")
            continue
        close_list()
        h = _H_HEADING.match(line)
        if h:
            flush()
            out.append("<p><b>" + _line(h.group(1)) + "</b></p>")
            continue
        q = _H_QUOTE.match(line)
        buf.append(_line(q.group(1) if q else line.strip()))
    flush(); close_list()
    return "".join(out)
