"""어투 다듬기 — 숫자를 LLM 이 건드릴 수 없게 구조로 막는다.

왜 이렇게까지 하나
  "값을 이미 꽂은 문장을 다듬어라" 라고 시켜도 모델은 숫자를 바꾼다.
  86점을 87점으로, 333건을 300여 건으로 고쳐 놓는다. 악의가 아니라 문장을 다듬다 그렇게 된다.
  그리고 그건 **지어낸 숫자**다. 이 프로젝트가 가장 먼저 금지한 것이다.

그래서 부탁하지 않고 봉인한다
  보내기 전에 숫자를 자리표시자로 바꾼다.

      발레코어의 트렌드 온도는 86점 · 과열입니다.
   →  발레코어의 트렌드 온도는 ⟦0⟧점 · 과열입니다.

  모델은 ⟦0⟧ 이 무슨 값인지 모른다. 바꿀 수가 없다.
  돌아온 문장에 자리표시자가 그대로 있는지, 새 숫자가 끼지 않았는지 확인하고 되돌린다.
  하나라도 어긋나면 **원문을 그대로 쓴다.** 다듬기는 있으면 좋은 것이지 없으면 안 되는 게 아니다.
"""
from __future__ import annotations

import re

from . import llm

# 숫자 + 바로 붙는 단위/기호까지 한 덩어리로 잡는다.
#   '1,284' · '86' · '3.88' · '−12' 를 통째로 봉인한다.
_NUM = re.compile(r"[-−+]?\d[\d,]*(?:\.\d+)?")
_PH = "⟦{}⟧"
_PH_RE = re.compile(r"⟦(\d+)⟧")

INSTRUCTIONS = """당신은 한국 패션 트렌드 서비스 FEEDiT 의 문장을 다듬는다.

지켜야 할 것
- ⟦0⟧ ⟦1⟧ 같은 자리표시자는 **글자 그대로 그 자리에** 남긴다. 지우거나 옮기거나 바꾸지 않는다.
- 숫자를 새로 쓰지 않는다. 어떤 수치도 추가하지 않는다.
- 사실을 더하지 않는다. 주어진 문장에 없는 내용을 만들지 않는다.
- 판단을 뒤집지 않는다. "말할 수 없습니다" 를 "아마 오를 겁니다" 로 바꾸지 않는다.
- 재촉하지 않는다. '지금 아니면', '서두르', '놓치면' 같은 말을 쓰지 않는다.
- 존댓말, 담백하게. 감탄사와 이모지를 쓰지 않는다.
- 원문과 길이가 비슷해야 한다. 늘리지 않는다.
- <b> 태그가 있으면 감싼 대상을 그대로 유지한다. 태그를 새로 만들지 않는다.

출력은 다듬은 문장 하나뿐이다."""

_SCHEMA = llm.strict_schema("feedit_polish",
                            {"sentence": {"type": "string"}}, ["sentence"])

# 재촉·과장 금지어. 모델이 넣으면 통째로 되돌린다.
_MD_RE = __import__("re").compile(r"\*\*|__|^#{1,6}\s|\[[^\]]*\]\(|```|~~")

_BANNED = ("지금 아니면", "서두르", "놓치면", "마지막 기회", "품절 임박입니다",
           "강력 추천", "무조건", "반드시 사", "후회", "역대급")


def seal(text: str) -> tuple[str, list[str]]:
    """숫자를 자리표시자로 바꾼다."""
    vals: list[str] = []

    def sub(m):
        vals.append(m.group(0))
        return _PH.format(len(vals) - 1)

    return _NUM.sub(sub, text), vals


def unseal(text: str, vals: list[str]) -> str:
    return _PH_RE.sub(lambda m: vals[int(m.group(1))], text)


def verify(sealed_in: str, sealed_out: str, vals: list[str]) -> str | None:
    """다듬은 문장을 받아도 되나. 안 되면 이유를 돌려준다 (None 이면 통과)."""
    if not sealed_out or not sealed_out.strip():
        return "EMPTY"
    want = sorted(int(m) for m in _PH_RE.findall(sealed_in))
    got = sorted(int(m) for m in _PH_RE.findall(sealed_out))
    if want != got:
        return f"PLACEHOLDER_MISMATCH {want} != {got}"
    if any(int(i) >= len(vals) for i in got):
        return "PLACEHOLDER_OUT_OF_RANGE"
    # 자리표시자를 뺀 자리에 숫자가 새로 생겼나
    stripped = _PH_RE.sub("", sealed_out)
    if re.search(r"\d", stripped):
        return "NEW_DIGIT"
    if sealed_out.count("<b>") != sealed_out.count("</b>"):
        return "UNBALANCED_TAG"
    if sealed_out.count("<b>") > sealed_in.count("<b>"):
        return "EXTRA_TAG"
    # 마크다운은 화면에서 글자로 보인다 (chat_api.js 가 전부 이스케이프한다).
    # 다듬는 김에 별표를 붙이는 일이 실제로 있어 여기서 막는다.
    if _MD_RE.search(sealed_out):
        return "MARKDOWN"
    low = sealed_out.replace(" ", "")
    for w in _BANNED:
        if w.replace(" ", "") in low:
            return f"BANNED:{w}"
    if len(sealed_out) > len(sealed_in) * 1.6 + 20:
        return "TOO_LONG"
    return None


def polish(text: str, *, context: dict | None = None, timeout: int = 12) -> tuple[str, str]:
    """다듬은 문장과 그 출처를 돌려준다.

    돌아오는 두 번째 값
        'llm'   다듬어졌다
        'rule'  원문 그대로 (키 없음 · 호출 실패 · 검증 탈락)
    """
    if not text or not text.strip():
        return text, "rule"
    if not llm.available():
        return text, "rule"

    sealed_in, vals = seal(text)
    got = llm.respond(
        INSTRUCTIONS,
        {"sentence": sealed_in, "context": context or {}},
        _SCHEMA, timeout=timeout, max_output_tokens=400, **llm.role("polish"))
    if not got:
        return text, "rule"

    sealed_out = str(got.get("sentence") or "").strip()
    why = verify(sealed_in, sealed_out, vals)
    if why:
        # 조용히 넘어가지 않는다. 왜 버렸는지 남긴다.
        llm.LAST_ERROR = f"POLISH_REJECT {why}"
        return text, "rule"
    return unseal(sealed_out, vals), "llm"
