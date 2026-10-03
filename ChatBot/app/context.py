"""④ 대화 맥락 해석 — 사전 게이트와 규칙이 놓친 질문을 LLM이 유연하게 읽는다.

여기로 오는 질문은 이미 두 관문을 통과하지 못한 것들이다.
    · lexicon_gate   이번 질문에 사전 단어가 없다
    · followup       정규식(앞머리 접속어 · 지시대명사 · 비교 표현)으로도 못 이었다

intents.py 의 원래 계획이 이것이다 — "애매한 것만 나중에 LLM 파서로 넘긴다
(아직 안 붙였다)". 여기서 그 자리를 채운다. 단, followup.py 가 규칙만 쓴 이유
(속도 · "왜 이어받았는지 설명 못 함")는 그대로 지킨다 — 이 모듈은 **정규식이
확실히 놓쳤을 때만, 마지막 수단으로만** 불리고, 이어받은 이유를 항상 note 로
남긴다 (engine.py 참고).

여기서도 하지 않는 것 — LLM 이 자유로워지는 자리가 아니다.
    · 새 단어를 만들지 않는다. "이거 얘기인가?" 판단은 **이미 대화에 등장해서
      사전 게이트를 통과했던** canonical 목록(candidate_terms) 중에서만 고른다.
      스키마의 enum 으로 강제한다 — 목록 밖의 값은 아예 응답으로 나올 수 없다.
    · 새 의도 코드를 만들지 않는다. candidate_intents(기존 intents.py 목록)
      중에서만 고른다.
    · 숫자를 쓰지 않는다. 잡담 답변(reply)에 숫자가 섞여 있으면 그 자리에서
      버리고 규칙 기본값으로 떨어진다 — 트렌드 수치는 report.py 가 DB 에서
      직접 꽂을 때만 나온다.
    · 화면 구조를 만들지 않는다. 잡담이면 문장 하나만, 이어받기면 기존 카드
      템플릿(report.py · templates.py)을 그대로 탄다.

실패하면 None. 그러면 부르는 쪽(engine.py)이 기존 "사전에 없는 말입니다" 로
떨어진다. LLM 이 죽어도, 애매해도, 챗봇은 늘 뭔가는 답한다.
"""
from __future__ import annotations

import re

from . import llm
from .followup import NEVER_INHERIT as _NOT_ANSWERABLE

INSTRUCTIONS = """당신은 한국 패션 트렌드 서비스 FEEDiT 의 대화 맥락 해석기다.
사용자의 이번 메시지에 사전에 걸리는 패션 단어가 없고, 정형화된 되묻기 규칙에도
안 걸렸을 때만 너를 부른다. 최근 대화(recent_turns)를 보고 다음 중 하나로 분류한다.

  smalltalk   트렌드 데이터와 무관한 잡담 · 인사 · 감사 · 리액션 · 잡담성 되물음.
              reply 에 짧고 자연스러운 한국어 답을 쓴다.
              ★ 숫자 · 온도 · 순위를 지어내지 않는다. "핫해요" · "인기 많아요" ·
                "요즘 잘 나가요" 처럼 숫자 없이도 트렌드 판단처럼 들리는 말도
                쓰지 않는다 — 그건 이 서비스의 지표만이 답할 수 있다. 서비스를
                소개하거나 "무엇이 궁금하신가요?" 처럼 되묻는 수준까지만 답한다.
  followup    사용자가 앞선 대화에서 이미 다뤘던 것 중 무엇을 가리키는지,
              그리고 그게 어떤 종류의 물음인지 이번 메시지로 알 수 있을 때.
              refer_terms 는 **candidate_terms 목록에 있는 것만** 고른다 — 목록에
              없는 것을 가리키는 것 같으면 unclear 로 넘긴다. intent 도
              **candidate_intents 목록에 있는 것만** 고른다.
  unclear     위 둘 다 아니면 이걸 고른다. 억지로 끼워 맞추지 않는다.
              확신이 없을 때도 이걸 고르고 confidence 를 낮게 준다.

candidate_terms · candidate_intents 는 이미 사전 게이트를 통과했던 값들이다.
목록 밖의 말을 지어내면 안 된다. mode 가 "salmal" 이면 사용자는 "살!말?" 모드에
있다 — 살지 말지를 묻는 맥락임을 참고만 하고, 판단 자체는 여전히 만들지 않는다."""


def _schema(term_choices: list[str], intent_choices: list[str]) -> dict:
    # strict 스키마는 enum 이 비면 안 되므로, 후보가 없을 때는 더미 값 하나를 채운다 —
    # 실제로 그 값이 골라져도 candidate_terms 에 없으니 resolve() 가 걸러낸다.
    term_enum = term_choices or ["__none__"]
    intent_enum = intent_choices or ["__none__"]
    props = {
        "kind": {"type": "string", "enum": ["smalltalk", "followup", "unclear"]},
        "reply": {"type": "string", "maxLength": 200},
        "refer_terms": {"type": "array", "maxItems": 2,
                        "items": {"type": "string", "enum": term_enum}},
        "intent": {"type": "string", "enum": intent_enum},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }
    return llm.strict_schema("feedit_context", props,
                             ["kind", "reply", "refer_terms", "intent", "confidence"])


_HAS_DIGIT = re.compile(r"\d")
# 숫자가 없어도 트렌드 판단처럼 들리는 말 — 잡담 답변엔 나오면 안 된다.
_TREND_CLAIM = re.compile(
    r"핫해|hot|인기가?\s*많|잘\s*나가|유행(이|입니다|이에요)|뜨고\s*있|"
    r"트렌드(예요|이에요|입니다)|과열|미지근|차가움|따뜻함")


def resolve(question: str, history: list[dict], intent_choices: list[str],
           *, mode: str = "general", timeout: int = 8) -> dict | None:
    """{kind:'smalltalk', reply} 또는 {kind:'followup', refer_terms, intent} 또는 None.

    None 이면 실패했거나 확신이 없다는 뜻 — 부르는 쪽이 규칙 기본값을 쓴다.
    """
    if not llm.available() or not history:
        return None

    intent_choices = [c for c in intent_choices if c not in _NOT_ANSWERABLE]
    if not intent_choices:
        return None

    seen: dict[str, bool] = {}
    turns = []
    for t in history[-4:]:
        terms = [x.get("canonical") for x in (t.get("terms") or []) if x.get("canonical")]
        for c in terms:
            seen[c] = True
        turns.append({"q": t.get("q"), "intent": t.get("intent"), "terms": terms})
    if not turns:
        return None

    term_choices = list(seen.keys())
    got = llm.respond(
        INSTRUCTIONS,
        {"question": question, "mode": mode, "recent_turns": turns,
         "candidate_terms": term_choices, "candidate_intents": intent_choices},
        _schema(term_choices, intent_choices),
        timeout=timeout, max_output_tokens=300, **llm.role("context"))
    if not got:
        return None

    conf = float(got.get("confidence") or 0)
    if conf < 0.5:
        return None

    kind = got.get("kind")
    if kind == "smalltalk":
        reply = str(got.get("reply") or "").strip()
        # ★ 숫자나 트렌드 판단 표현이 섞였으면 신뢰하지 않는다 — 값을 지어냈을 가능성이다.
        if not reply or _HAS_DIGIT.search(reply) or _TREND_CLAIM.search(reply):
            return None
        return {"kind": "smalltalk", "reply": reply}

    if kind == "followup":
        refer = [c for c in (got.get("refer_terms") or []) if c in term_choices]
        got_intent = got.get("intent")
        if not refer or got_intent not in intent_choices:
            return None
        return {"kind": "followup", "refer_terms": refer, "intent": got_intent}

    return None
