"""① 의도 분류에 Luna 를 붙인다 — 규칙이 못 잡을 때만.

왜 규칙을 먼저 두나
  규칙은 공짜고 즉시다. "발레코어 꺾였어?" 는 정규식으로 확실히 잡힌다.
  그런 걸 매번 LLM 에 보내면 느려지고 돈이 나간다.
  **규칙이 아무것도 못 잡았을 때만** 부른다.

★ LLM 이 정하지 않는 것 — 엔티티

  무엇에 대한 질문인지는 **사전 게이트가 정한다.** LLM 은 '무엇을 묻는가' 만 고른다.
  LLM 에게 키워드까지 맡기면 사전에 없는 말을 지어내 게이트를 뒷문으로 통과시킨다.
  4종 축 게이트가 이 서비스의 뼈대라 거기는 열어 주지 않는다.

★ 실패하면 규칙 결과를 쓴다. LLM 이 죽어도 챗봇은 답한다.
"""
from __future__ import annotations

from . import llm
from .intents import GENERAL, SALMAL, GENERAL_CODES, SALMAL_CODES, classify_rule

INSTRUCTIONS = """당신은 한국 패션 트렌드 서비스 FEEDiT 의 질문 분류기다.
사용자 질문이 **무엇을 묻는지** 코드 하나로 고른다.

주의
- 키워드나 상품명을 뽑지 않는다. 그건 다른 곳에서 한다. 당신은 의도만 고른다.
- 주어진 목록 밖의 코드를 만들지 않는다.
- 패션과 무관한 질문이면 out_of_scope 를 고른다.
- 확신이 없으면 confidence 를 낮게 준다. 억지로 고르지 않는다.

코드의 뜻
  metric.level      지금 얼마나 뜨거운가 (온도·언급량)
  metric.direction  오르는 중인가 내리는 중인가
  metric.compare    둘을 견준다
  metric.platform   어느 플랫폼에서 많이 나오나
  metric.assoc      무엇과 같이 언급되나
  metric.sentiment  사람들 반응·구매 의향
  metric.lifecycle  얼마나 오래 갈까 · 수명주기
  knowledge.origin  그게 뭔가 · 어떻게 시작됐나 (지식 질문)
  meta.capability   챗봇이 뭘 할 수 있나
  out_of_scope      패션 밖

  buy.verdict       사도 되나
  buy.price         가격·최저가·할인
  buy.longevity     내년에도 입을까
  buy.alternative   더 싼 대안
  buy.opinion       남들은 뭐라 하나
  buy.tryon         나한테 어울릴까 · 입은 모습"""


def _schema(codes: list[str]) -> dict:
    return llm.strict_schema(
        "feedit_intent",
        {"intent": {"type": "string", "enum": codes},
         "confidence": {"type": "number", "minimum": 0, "maximum": 1},
         "why": {"type": "string", "maxLength": 80}},
        ["intent", "confidence", "why"])


def classify(question: str, mode: str = GENERAL, *, use_llm: bool = True) -> dict:
    """{intent, source, confidence, rule_intent}

    source  'rule'      규칙이 잡았다
            'llm'       규칙이 못 잡아 Luna 가 골랐다
            'rule_fallback'  Luna 를 부르려다 실패해 규칙 기본값을 썼다
    """
    rule_code, sure = classify_rule(question, mode)
    out = {"intent": rule_code, "source": "rule", "confidence": 1.0 if sure else 0.3,
           "rule_intent": rule_code}
    if sure or not use_llm or not llm.available():
        if not sure and use_llm:
            out["source"] = "rule_fallback"
        return out

    codes = SALMAL_CODES if mode == SALMAL else GENERAL_CODES
    got = llm.respond(INSTRUCTIONS, {"question": question, "mode": mode},
                      _schema(codes), timeout=8, max_output_tokens=200, **llm.role("classify"))
    if not got or got.get("intent") not in codes:
        out["source"] = "rule_fallback"
        return out

    conf = float(got.get("confidence") or 0)
    if conf < 0.45:
        # 모델도 확신 못 했다. 규칙 기본값이 낫다.
        out["source"] = "rule_fallback"
        out["llm_intent"] = got["intent"]
        out["confidence"] = conf
        return out

    out.update({"intent": got["intent"], "source": "llm", "confidence": conf,
                "why": got.get("why")})
    return out
