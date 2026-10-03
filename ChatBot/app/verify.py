"""L3 사실 검증관 — 답변의 숫자가 도구 결과에 실제로 있는지 대조한다.

── 왜 이 층이 있나 ──────────────────────────────────────────
FEEDiT 에서 제일 위험한 실패는 "DB 가 안 붙었는데 화면에 그럴듯한 숫자가
떠 있는 것" 이다. 화면 쪽은 이미 그 원칙을 지킨다 — 값이 없으면
`unavailableHTML` 이 사유를 적지, 씨드 난수를 그리지 않는다.

챗봇에는 그 자리가 없었다. LLM 은 문장을 매끄럽게 만들려고 빈 칸을 채운다.
"온도 71°" 까지는 도구가 준 값인데 "전년 대비 +40%" 를 슬쩍 덧붙이는 식이다.
읽는 사람은 둘을 구분할 방법이 없다. **숫자 하나가 나머지 전부의 신뢰를
무너뜨린다.**

── 어떻게 막나 ──────────────────────────────────────────────
두 겹이다. 순서가 중요하다.

  ① 기계 대조 (모델 없음, 0원)
     답변에서 숫자를 뽑아 TraceLog 의 원본과 맞춰 본다.
     의심스러운 게 하나도 없으면 여기서 끝난다 — LLM 을 아예 안 부른다.
     정상 답변은 대부분 여기서 통과한다.

  ② 고쳐 쓰기 (소형 모델, effort=none)
     의심되는 숫자가 있을 때만 부른다. 도구 결과 원본을 함께 주고
     "없는 값은 지우거나 '측정 자료가 없습니다' 로 바꿔라" 라고 시킨다.

── 왜 소형 모델인가 (설계도 05) ─────────────────────────────
이건 창작이 아니라 **일치 확인**이다. 출력이 스키마로 닫혀 있고 effort 가
none 이라, 큰 모델로 올려도 얻는 게 거의 없다. 판단을 만들어야 하는 자리는
L1·L2 이고 여기는 아니다.

── 대조 원본이 없으면 이 파일은 무의미하다 ──────────────────
TraceLog 가 도구 결과를 **요약해서** 들고 있으면 대조할 것이 없어지고,
검증은 그냥 통과 도장이 된다. tools.TraceLog 가 원본을 그대로 보관하는
이유가 이것이다.
"""
from __future__ import annotations

import re
import time
from typing import Any

from . import llm
from .tools import _numstr

# ★ 이 층도 전체 시간 예산 안이다 (2026-09-10, 인수인계 18번).
#   fix() 는 모델을 한 번 부른다. 예전에는 timeout=15 가 고정이라, 오케스트레이터가
#   예산을 다 쓴 뒤에도 15초를 더 썼다. 이제 agent_path 가 준 마감시각을 보고
#   남은 만큼만 쓰고, 남은 게 없으면 **부르지 않고** 그 사실을 남긴다.
FIX_TIMEOUT = 15        # 대조 한 번의 상한
MIN_CALL = 2.0          # 이보다 적게 남았으면 부르지 않는다

# ★ 이 사유 문자열은 agent_path 가 화면 안내를 고르는 데 쓴다.
#   문자열을 양쪽에서 따로 적었다가 어긋났던 자리다(2026-09-10) —
#   verify 는 "no_tool_results" 를 남기는데 agent_path 는 "web_sourced" 를
#   보고 있어서, 웹으로 답했다는 안내 대신 "사실 확인을 끝내지 못했습니다"
#   라는 경고가 나갔다. 한 곳에서만 적는다.
NO_TOOL_RESULTS = "no_tool_results"

# 답변에서 숫자를 뽑는다. 1,240 · 3.5 · -6 · +82 를 모두 잡는다.
_NUM = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?")

# 연도는 지표가 아니다. 2026-09-08 같은 날짜도 여기서 걸러진다.
_YEARLIKE = re.compile(r"(19|20)\d{2}")

# ★ 모델명·품번 안의 숫자 (2026-09-10 실측)
#   답변에 "피지컬가먼츠 P5069" 가 들어가자 5069 를 지어낸 숫자로 잡아 지웠고,
#   화면에는 "P5069에서 도구 결과에 없는 숫자 5069를 제거했습니다" 가 떴다.
#   "Y2K" 의 2, "XT-6" 의 6, "KD7983" 도 같은 자리다. 이것들은 **주장이 아니라
#   이름**이다. 날짜·목록 번호와 같은 계열의 오탐이라 같은 방식으로 먼저 걷어낸다.
_MODELCODE = re.compile(r"[A-Za-z][A-Za-z0-9]*-?\d[A-Za-z0-9-]*")

# 목록 번호 — "1. 발레코어" 의 1 은 주장하는 숫자가 아니다.
_ORDINAL = re.compile(r"^\s*\(?\d{1,2}[.)]\s", re.M)

# ★ 마크다운 **표**의 순번 칸. 2026-09-09 실측 —
#   모델이 순위를 목록이 아니라 표로 쓰면
#       | 1 | 자켓 | 아이템 | 69° |
#   _ORDINAL 은 "1." 꼴만 보므로 1·2·3… 이 전부 "지어낸 숫자" 로 잡혔다.
#   같은 순번인데 형식만 다르다.
_TABLE_IDX = re.compile(r"^\s*\|\s*(\d{1,2})\s*\|", re.M)

# 권유로 읽히는 말. 사실 서술("내려가는 중입니다")과 구분한다.
_RECOMMEND = re.compile(
    r"사도\s*(?:되|괜찮|좋)|살\s*만|추천(?:합|드|해)"
    r"|지금이?\s*(?:적기|기회|타이밍)|나쁘지\s*않|괜찮은\s*시점"
    r"|들어가도|담아도|사세요|사시")

# ★ 날짜를 **먼저** 통째로 지운다.
#   안 그러면 "2026-09-08" 이 _NUM 에 2026 · -09 · -08 세 조각으로 잡힌다.
#   2026 은 연도라 걸러지지만 **-9 와 -8 이 "지어낸 음수" 로 남는다.**
#   기준일을 성실히 밝힌 답변일수록 더 많이 걸리는, 정확히 거꾸로 된 판정이었다.
#   (2026-09-09 실측: 정상 답변 하나가 이것 때문에 통째로 재작성 대상이 됐다)
#   ★ 2026-09-09 추가 — 반대 방향 오탐도 막는다.
#     예전 두 번째 갈래 `\d{1,2}\s*[-./월]\s*\d{1,2}\s*일` 은 구분자에 `-` 를
#     허용하고 공백까지 받아서, **"54.46 - 7일 평균"** 의 `46 - 7일` 을 날짜로
#     먹었다. 남은 `54.` 가 `54` 로 잡혀 "지어낸 숫자" 판정이 났다.
#     소수가 나오는 답변(모멘텀·이동평균)마다 걸리던 자리다.
#     그래서 ① 하이픈 갈래를 빼고 `월` 을 필수로 두고,
#          ② 앞뒤에 `(?<![\d.])` · `(?![\d.])` 를 걸어 소수 한복판을 못 자르게 한다.
_DATE = re.compile(
    r"(?<![\d.])\d{4}\s*[-./년]\s*\d{1,2}\s*[-./월]\s*\d{1,2}\s*일?(?![\d.])"  # 2026-09-08 · 2026년 9월 8일
    r"|(?<![\d.])\d{1,2}\s*월\s*\d{1,2}\s*일(?![\d.])"                            # 9월 8일
    r"|(?<![\d.])\d{1,2}:\d{2}(?![\d.])"                                          # 14:30
)


class Report:
    """무엇을 의심했고 무엇을 고쳤나. 로그와 진단에 쓴다."""

    def __init__(self) -> None:
        self.suspect_numbers: list[str] = []   # 도구 결과에 없던 숫자
        self.missing_axes: list[str] = []      # declare_missing 인데 언급된 축
        self.bad_recommend: list[str] = []     # 금지 조건인데 권유한 대상
        self.changed: bool = False
        self.removed: list[str] = []           # 모델이 지웠다고 말한 것
        self.skipped: str = ""                 # 고쳐 쓰기를 건너뛴 이유
        self.escalated: str = ""               # Luna 가 막혀 Sol 로 다시 부른 이유 (2026-09-18)

    @property
    def clean(self) -> bool:
        return (not self.suspect_numbers and not self.missing_axes
                and not self.bad_recommend)

    def as_dict(self) -> dict:
        return {"suspect_numbers": self.suspect_numbers,
                "missing_axes": self.missing_axes,
                "bad_recommend": self.bad_recommend,
                "changed": self.changed, "removed": self.removed,
                "skipped": self.skipped, "escalated": self.escalated}


def _numbers_in(text: str) -> set[str]:
    """답변이 주장하는 숫자들. 연도·목록번호는 뺀다."""
    body = _DATE.sub(" ", text or "")
    body = _MODELCODE.sub(" ", body)
    body = _ORDINAL.sub(" ", body)
    body = _TABLE_IDX.sub(" | ", body)
    out: set[str] = set()
    for m in _NUM.finditer(body):
        raw = m.group(0)
        if _YEARLIKE.fullmatch(raw.lstrip("+-")):
            continue
        try:
            v = float(raw.replace(",", "").replace("+", ""))
        except ValueError:
            continue
        out.add(_numstr(v))
    return out


_NKEY = re.compile(r"^n(\d{1,3})$")


def _windows(trace) -> set[str]:
    """관측 창 크기 — `observations: {n7: 3, n14: 4, n28: 4}` 의 **7 · 14 · 28**.

    ★ 2026-09-09 실측
      답변이 "최근 7일 관측 3건, 14일 4건, 28일 4건" 이라고 성실히 적었는데
      14 와 28 이 "지어낸 숫자" 로 잡혔다. 값(3·4·4)은 도구 결과에 있지만
      창 크기는 **키 이름**에만 있어 numbers() 가 못 본다.
      기준일을 밝힐수록 걸리던 _DATE 문제와 같은 종류다.
    """
    out: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                m = _NKEY.match(str(k))
                if m:
                    out.add(m.group(1))
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(trace.calls if trace else [])
    return out


def _known(trace, question: str) -> set[str]:
    """대조 기준이 되는 숫자들 — **반올림 표기까지 함께** 인정한다.

    ★ 왜 반올림을 허용하나 (2026-09-09 실측)
      도구가 momentum=54.46 · ma7=34.55 · ma28=33.54 를 줬는데, 모델은
      사람이 읽기 좋게 **54.5 · 34.5 · 33.5** 로 적었다. 문자열 정확 일치로
      대조하니 셋 다 "지어낸 숫자" 로 잡혔다.
      반올림은 지어낸 것이 아니라 **읽기 좋게 쓴 것**이고, 오히려 바람직하다.
      여기서 막으면 모델은 소수점 두 자리를 그대로 나열하게 된다.
    """
    base = set(trace.numbers()) | _numbers_in(question) | _windows(trace)
    out = set(base)
    for s in base:
        try:
            v = float(s)
        except ValueError:
            continue
        for k in (0, 1, 2):
            r = round(v, k)
            out.add(_numstr(r))
            # ★ 부호를 뗀 표기도 인정한다 (2026-09-09 실측).
            #   delta_1w = -31.0 을 모델은 "31° **하락**" 이라고 쓴다. 한국어에서
            #   자연스러운 표기인데, _numstr(-31.0) 은 "-31" 이라 대조에 걸렸고
            #   검증관이 멀쩡한 31 을 **실제로 지웠다**(removed: ['31.0']).
            #   방향은 숫자 대조가 아니라 말할_수_있는_것 이 지키는 몫이다.
            out.add(_numstr(abs(r)))
    return out


def check(answer: str, trace, question: str = "") -> Report:
    """① 기계 대조. 모델을 부르지 않는다."""
    rep = Report()
    if not answer or trace is None:
        return rep

    # 도구가 실제로 준 숫자 + 사용자가 질문에 쓴 숫자는 통과시킨다.
    #   ("10개 알려줘" 의 10 을 지어낸 값으로 볼 수는 없다)
    known = _known(trace, question)

    for n in _numbers_in(answer):
        if n not in known:
            rep.suspect_numbers.append(n)

    # declare_missing 으로 "없다" 고 기록한 축을 답변이 말하고 있나.
    #   축 이름이 나오면서 그 근처에 숫자가 있으면 값을 지어낸 것이다.
    for m in (trace.missing or []):
        axis = str(m.get("axis") or "").strip()
        if not axis or axis not in answer:
            continue
        near = _near(answer, axis)
        if _NUM.search(near):
            rep.missing_axes.append(axis)

    # ★ 숫자 말고 **권유 문장**을 본다 (설계도 부록 14).
    #   L3 는 원래 "숫자가 도구 결과에 있나" 만 봤다. 그런데 사용자를 움직이는
    #   문장은 인과와 권유다 — 숫자가 다 맞아도 "지금 사도 됩니다" 는 틀릴 수
    #   있고, 구매를 유도하므로 책임이 따른다. 대조로는 못 막으니
    #   **도구가 금지라고 말한 조건에서 권유가 나왔는지**를 본다.
    for c in (trace.calls if trace else []):
        if c.get("tool") != "get_metric":
            continue
        rule = (c.get("result") or {}).get("말할_수_있는_것") or {}
        if rule.get("recommend") != "금지":
            continue
        term = (c.get("args") or {}).get("term") or ""
        if _RECOMMEND.search(answer):
            rep.bad_recommend.append(term or "(대상)")

    rep.suspect_numbers.sort()
    return rep


def _near(text: str, needle: str, span: int = 40) -> str:
    i = text.find(needle)
    if i < 0:
        return ""
    return text[max(0, i - span): i + len(needle) + span]


_SCHEMA = llm.strict_schema(
    "verified_answer",
    {
        "answer": {"type": "string", "description": "고친 답변 전문"},
        "removed": {"type": "array", "items": {"type": "string"},
                    "description": "지우거나 바꾼 주장. 없으면 빈 배열"},
        "ok": {"type": "boolean",
               "description": "원문 그대로 두어도 되면 true"},
    },
    ["answer", "removed", "ok"],
)

_FIX_INSTRUCTIONS = """너는 FEEDiT 답변의 사실 검증관이다.

답변 초안과, 그 답변을 만들 때 실제로 조회한 도구 결과 원본을 받는다.
할 일은 하나다 — **답변의 숫자와 주장이 도구 결과에 실제로 있는지 대조한다.**

## 규칙
1. 도구 결과에 없는 숫자는 지운다. 그 문장이 숫자 없이 성립하면 문장은 남기고
   숫자만 뺀다. 성립하지 않으면 문장을 통째로 뺀다.
   ★ 숫자만 빼서 "상위 개는" · "총 건" 처럼 단위만 남으면 성립하지 않는 것이다.
     그 문장을 통째로 뺀다.
2. `missing` 에 적힌 축은 자료가 없는 것이다. 그 축의 **값**을 말하는 문장은
   "아직 측정 자료가 없습니다" 로 바꾼다.
2-1. `bad_recommend` 가 비어 있지 않으면, 그 대상에 대한 **권유 문장을 지운다.**
   도구가 그 조건에서 권유를 금지했다 (내려가는 중이거나 표본이 모자람).
   사실 서술은 남긴다 — "내려가는 중입니다" 는 되고 "지금 사도 됩니다" 는 안 된다.
3. **새로 쓰지 마라.** 없는 내용을 채우거나 문장을 늘리지 않는다.
   너는 고치는 사람이지 쓰는 사람이 아니다.
4. 도구 결과에 있는 숫자는 절대 건드리지 않는다. 반올림도 하지 마라.
5. 문체·어투는 그대로 둔다.

## 판단 기준
- 질문에 사용자가 쓴 숫자("10개 알려줘" 의 10)는 지어낸 값이 아니다.
- 연도·날짜·목록 번호는 지표가 아니다.
- 도구 결과에 있는 값을 다른 단위로 바꿔 쓴 것(0.88 → 상위 12%)은
  근거가 있으므로 남긴다.

원문 그대로 두어도 되면 ok=true 로 하고 answer 에 원문을 그대로 넣어라."""


def _read_fix(answer: str, res: dict | None) -> tuple[str | None, str]:
    """모델 응답 → (고친 답 | None, 실패 사유).  (None, "") 는 '원문 그대로 두어도 된다'."""
    if not res:
        return None, f"llm_{llm.LAST_ERROR or 'unknown'}"
    if res.get("ok"):
        return None, ""
    fixed = (res.get("answer") or "").strip()
    if not fixed:
        return None, "empty_fix"
    # ★ 고친 답을 그대로 믿지 않는다 (2026-09-14).
    #   실측: "감성 지표는 아직 측정 자료가 없습니다.keletal" 이 화면에 떴다.
    #   규칙 2 가 시킨 대로 문장은 바꿨는데, 소형 모델이 끝에 영문 조각을
    #   흘렸다. 검증관의 일은 **지우는 것**이지 쓰는 것이 아니므로(규칙 3),
    #   원문에 없던 영문 낱말이 새로 생겼다면 그 재작성은 깨진 것이다.
    strays = _new_latin_words(answer, fixed)
    if strays:
        return None, "fix_garbled:" + ",".join(strays[:3])
    # ★ 숫자만 뽑고 단위를 남긴 재작성도 깨진 것이다 (2026-10-01).
    #   실측: "상위 4개는 모두 과열" 의 4 를 지우고 "상위 개는 모두 과열" 을 내보냈다.
    #   규칙 1 은 그럴 때 문장을 통째로 빼라고 했다. 원문보다 '단위만 남은 자리' 가
    #   늘었으면 그 재작성은 받지 않는다.
    if _dangling_units(fixed) > _dangling_units(answer):
        return None, "fix_garbled:dangling_unit"
    return fixed, ""


# 숫자 없이 홀로 남은 단위 — "상위 개는", "총 건", "온도 점" 의 개 · 건 · 점
_DANGLING = re.compile(r"(?:^|(?<=[\s(·,]))(?:개|건|위|일|점|명|배|곳|%)"
                       r"(?=[는은이가를의도만까지와과로\s,.)]|$)", re.M)


def _dangling_units(text: str) -> int:
    return len(_DANGLING.findall(text or ""))


def fix(answer: str, trace, rep: Report, question: str = "",
        deadline: float | None = None) -> str:
    """② 의심되는 게 있을 때만 부른다. 소형 모델."""
    payload = {
        "question": question,
        "answer": answer,
        # ★ 요약하지 않는다. 대조할 원본이 그대로 필요하다.
        "tool_results": trace.as_payload() if trace else [],
        "missing": (trace.missing if trace else []),
        "suspect_numbers": rep.suspect_numbers,
        "suspect_axes": rep.missing_axes,
        "bad_recommend": rep.bad_recommend,
    }
    # ★ 남은 시간 안에서만 부른다(18번). 없으면 부르지 않는다 —
    #   예산을 넘겨 가며 대조하면, 그 초과분만큼 사용자는 빈 화면을 본다.
    left = (deadline - time.monotonic()) if deadline else float(FIX_TIMEOUT)
    if left < MIN_CALL:
        rep.skipped = "time_budget"
        return _hedge(answer, rep)
    res = llm.respond(_FIX_INSTRUCTIONS, payload, _SCHEMA,
                      timeout=min(float(FIX_TIMEOUT), left),
                      **llm.role("verify"))
    fixed, why = _read_fix(answer, res)
    # ★ Luna 가 못 닿았거나(res 없음) 고친 답이 깨졌다 — 시간이 남으면 Sol 로 한 번 (2026-09-18).
    #   의심 숫자를 그대로 두고 경고만 붙이는 것(_hedge)보다 제대로 고친 답이 낫다.
    if why:
        left = (deadline - time.monotonic()) if deadline else float(FIX_TIMEOUT)
        if left >= MIN_CALL and llm.can_escalate(bad_output=res is not None):
            rep.escalated = "verify:" + (llm.LAST_ERROR or why)
            res = llm.respond(_FIX_INSTRUCTIONS, payload, _SCHEMA,
                              timeout=min(float(FIX_TIMEOUT), left),
                              **llm.escalate("verify"))
            fixed, why = _read_fix(answer, res)
    if why:
        # ★ 검증을 못 했으면 통과시키지 않는다.
        #   모델에 못 닿았다고 지어낸 숫자를 그대로 내보내면
        #   이 층이 있으나 마나다. 의심 구간을 알리는 쪽이 낫다.
        rep.skipped = why
        return _hedge(answer, rep)
    if fixed is None:                    # ok=true — 원문 그대로 둬도 된다
        return answer
    rep.changed = fixed != answer
    rep.removed = [str(x) for x in (res.get("removed") or [])]
    return fixed


_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")


def _new_latin_words(before: str, after: str) -> list[str]:
    """고친 답에만 새로 생긴 영문 낱말.

    왜 영문만 보나 — 검증관이 하는 일은 숫자를 지우고 문장을 정해진 한국어
    문구로 바꾸는 것뿐이다. 브랜드명 같은 영문은 원문에 이미 있으므로 통과하고,
    원문에 없던 영문이 튀어나오면 생성이 깨진 것이다. 한국어로 새 문장을
    지어내는 경우까지 잡지는 못한다 — 그건 이 검사가 노리는 것이 아니다.
    """
    had = {w.lower() for w in _LATIN_WORD.findall(before)}
    out = []
    for w in _LATIN_WORD.findall(after):
        if w.lower() not in had and w.lower() not in out:
            out.append(w.lower())
    return out


def _hedge(answer: str, rep: Report) -> str:
    """검증 자체가 실패했을 때. 숨기지 말고 그대로 밝힌다."""
    bits = []
    if rep.suspect_numbers:
        bits.append("일부 수치(" + ", ".join(rep.suspect_numbers[:5]) + ")")
    if rep.missing_axes:
        bits.append("일부 항목(" + ", ".join(rep.missing_axes[:3]) + ")")
    what = " 와 ".join(bits) if bits else "일부 내용"
    return (answer.rstrip()
            + f"\n\n> ⚠ {what} 은 측정 자료에서 확인하지 못했습니다. "
              "그대로 믿지 마시고 화면의 지표를 함께 봐 주세요.")


def verify(answer: str, trace, question: str = "",
           web_sourced: bool = False,
           deadline: float | None = None) -> tuple[str, Report]:
    """검증 한 번. 깨끗하면 모델을 안 부른다(0원).

    돌려주는 것: (최종 답변, 무엇을 했나)

    ★ web_sourced — 우리 도구를 하나도 안 쓰고 웹 검색으로만 답한 경우.
      이 층은 "도구 결과에 있는 숫자인가" 만 본다. 웹 검색 결과는 우리
      TraceLog 에 없으므로, 그대로 대조하면 **맞는 숫자가 전부 지어낸 것으로
      잡힌다.** 실측(2026-09-09) — "오늘 날씨 어때?" 답변의 14·18·19·21°C 가
      의심으로 잡혔고 검증관이 **19°C 를 실제로 지웠다.**
      확인할 원본이 없는 것을 지우는 것은 검증이 아니라 훼손이다.
      대신 FEEDiT 측정값이 아니라는 사실을 답변이 밝히게 한다
      (orchestrator.INSTRUCTIONS 의 web_search 규칙).
    """
    if web_sourced:
        # 대조할 도구 결과가 없다. 확인 못 한 것을 지우지 않고, 못 했다고 남긴다.
        rep = Report()
        rep.skipped = NO_TOOL_RESULTS
        return answer, rep
    rep = check(answer, trace, question)
    if rep.clean:
        return answer, rep
    return fix(answer, trace, rep, question, deadline), rep
