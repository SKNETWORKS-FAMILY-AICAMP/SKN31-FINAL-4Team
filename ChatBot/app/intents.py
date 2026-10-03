"""무엇을 묻는 질문인가.

규칙으로 먼저 본다. 라벨이 몇 개 안 되고 표현이 정형적이라 규칙으로 대부분 잡힌다.
애매한 것만 나중에 LLM 파서로 넘긴다 (아직 안 붙였다).

intent.py 가 구매의향 분류에서 쓴 방식과 같은 태도다 — 모델을 먼저 붙이지 않는다.
"""
from __future__ import annotations

import re

GENERAL = "general"
SALMAL = "salmal"

# 인사말 — 그 자체로 완결된 문장일 때만 잡는다.
#   "안녕하세요, 카고팬츠 온도 알려줘" 처럼 뒤에 진짜 질문이 붙으면 이 규칙을 건너뛰고
#   평소대로 사전 게이트로 넘어간다 (문장 전체가 인사말일 때만 매치되도록 앵커를 건다).
GREETING = re.compile(
    r"^(안녕(하세요|하십니까|하신가요)?|하이|hi|hello|헬로우?|"
    r"반가워요?|반갑습니다|처음\s*뵙겠습니다|좋은\s*아침|굿모닝)"
    r"[\s!~.,?]*$", re.I)


def is_greeting(question: str) -> bool:
    q = re.sub(r"\s+", " ", str(question or "")).strip()
    return bool(GREETING.match(q))


RULES_GENERAL = [
    ("metric.platform",  r"플랫폼|무신사|29ㅅ|29CM|지그재그|에이블리|크림|유튜브|인스타|어디서\s*더|온도\s*차"),
    ("metric.assoc",     r"연관|같이|함께|뭐랑|무엇과|조합|매치"),
    ("metric.sentiment", r"반응|평가|후기|사람들|다들|만족|불만|살\s*마음|긍부정|긍정|부정"),
    ("metric.lifecycle", r"수명|내년|오래|얼마나\s*갈|끝났|한물|계속\s*갈"),
    ("metric.direction", r"꺾|하락|상승|오르|내리|식|뜨고|지고|추세|방향|성장"),
    ("metric.compare",   r"vs|대\s*비|비교|어느\s*쪽|둘\s*중"),
    ("knowledge.origin", r"어떻게\s*시작|유래|기원|뭐야|무엇|뜻이|정의|어디서\s*나왔|출처"),
    ("metric.level",     r"어때|어떤가|온도|지금|요즘|인기|얼마나|핫"),
]

RULES_SALMAL = [
    ("buy.price",       r"최저가|가격|싸|비싸|할인|세일|얼마"),
    ("buy.longevity",   r"내년|오래|계속|수명|몇\s*시즌"),
    ("buy.alternative", r"대신|비슷|대안|다른\s*거|더\s*싼"),
    ("buy.opinion",     r"투표|다들|사람들|반응"),
    ("buy.tryon",       r"어울|입어|착용|입은\s*모습|코디해"),
    ("buy.verdict",     r"살까|사도|말까|살지|고민|추천"),
]

META = r"너\s*뭐|무엇을\s*할|기능|어떤\s*걸\s*물어|사용법|도움말"

# 일반 모드에서 이런 말이 나오면 살!말? 모드로 물어야 할 질문이다.
#   결정을 묻는 말이지 시장을 묻는 말이 아니다.
SALMAL_SIGNAL = r"살까|살지|사도\s*(될|되|괜찮)|말까|지를까|사야\s*(할|하)|" \
                r"살\s*만한|구매할까|고민(이|중|돼|되)"


def is_salmal_question(question: str) -> bool:
    return bool(re.search(SALMAL_SIGNAL, str(question or ""), re.I))


GENERAL_CODES = [c for c, _ in RULES_GENERAL] + ["meta.capability", "meta.greeting", "out_of_scope"]
SALMAL_CODES = [c for c, _ in RULES_SALMAL] + ["meta.capability", "meta.greeting", "out_of_scope"]


def classify_rule(question: str, mode: str = GENERAL) -> tuple[str, bool]:
    """규칙 분류. (코드, 확신했나)

    확신했다 = 어떤 규칙이 실제로 걸렸다.
    확신 못 했다 = 아무것도 안 걸려 기본값으로 떨어졌다 — 여기가 LLM 이 필요한 자리다.
    """
    q = re.sub(r"\s+", " ", str(question or "")).strip()
    if is_greeting(q):
        return "meta.greeting", True
    if re.search(META, q):
        return "meta.capability", True
    rules = RULES_SALMAL if mode == SALMAL else RULES_GENERAL
    for code, pat in rules:
        if re.search(pat, q, re.I):
            return code, True
    return ("buy.verdict" if mode == SALMAL else "metric.level"), False


def classify(question: str, mode: str = GENERAL) -> str:
    """규칙만. LLM 을 쓰려면 nlu.classify() 를 부른다."""
    return classify_rule(question, mode)[0]
