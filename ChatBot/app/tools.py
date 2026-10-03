"""오케스트레이터가 부를 수 있는 도구들 — 스키마와 디스패치.

── 이 파일이 하는 일 ────────────────────────────────────────
`store.py` 의 조회 함수에 **JSON 스키마를 씌우는 얇은 층**이다.
조회 로직을 여기 새로 쓰지 않는다. store.py 는 그대로 두고, 모델이
고를 수 있는 형태로 이름과 인자만 정리한다.

── 왜 도구인가 (설계도 원칙 1·2·3) ──────────────────────────
예전 구조는 정규식으로 의도를 **확정**하고 그 의도에 맞는 블록을 그렸다.
근거를 보기 전에 되돌릴 수 없는 결정을 하는 셈이라, 축이 여러 개인 질문
("살로몬 XT-6 지금 사도 돼?" — 할인률·수명주기·리세일 셋 다)에서 깨졌다.

도구는 다르다. 0번도 3번도 부를 수 있고, 결과를 보고 방향을 바꿀 수 있다.
그래서 여기 있는 것들은 전부 **갈림길이 아니라 함수**다:

  · 사전 조회(search_terms)도 게이트가 아니라 도구다.
    못 찾았다고 대화가 끝나지 않는다 — 모델이 rank_terms 로 갈아탈 수 있다.
  · 되묻기(ask_user)도 도구다. 실패 경로가 아니라 선택 가능한 행동이다.
  · "없음"(declare_missing)도 도구다. 지어내는 대신 없다고 기록한다.

── 지어내기를 구조로 막는다 ─────────────────────────────────
체형·사이즈·후기는 우리 데이터에 없다. 그러면 **도구를 만들지 않는다.**
도구가 없으면 오케스트레이터는 그 축을 부를 수 없고, 부를 수 없으면
아래 층이 지어낼 기회도 없다. 대신 declare_missing 이 남긴 기록을
verify.py 가 "그 축 얘기는 지운다"의 근거로 쓴다.

호출 기록(TraceLog)은 반드시 원본 그대로 남긴다. 검증관이 대조할
원본이 없으면 검증이 통과 도장으로 전락한다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from . import season as season_ref     # 인자 이름(season)과 겹치지 않게
from . import product_link, salmal_index, trend_view
from . import vton
from .config import MIN_OBS_28, MIN_OBS_7, RANK_WINDOW_DAYS, TEMP_VERDICTS, js_round, temp_band
from .coverage import direction as _direction

# ══════════════════════════════════════════════════════════
#  스키마
# ══════════════════════════════════════════════════════════
#  Responses API 의 function tool 형식이다.
#  strict 를 켜면 목록 밖 값을 모델이 아예 못 뱉는다 — 이게 모델 크기보다
#  정확도에 더 크게 작용한다(설계도 05).

AXES = ["온도", "모멘텀", "순위", "연관어", "긍부정", "출처별", "근거"]

# ══════════════════════════════════════════════════════════
#  말해도 되는 문장 — 표현 자체를 조건에 묶는다
# ══════════════════════════════════════════════════════════
#  ★ 왜 이게 도구 응답에 들어가나 (설계도 부록 14)
#    verify.py 는 **숫자가 도구 결과에 있는지**만 본다. 그런데 사용자를
#    움직이는 문장은 "2주째 내려오는 중이고 구매 의향이 82%니 지금이
#    나쁘지 않다" 같은 **인과와 권유**다. 숫자가 전부 맞아도 이 결론은
#    틀릴 수 있고, 구매를 유도하므로 책임이 따른다.
#
#    대조로는 못 막는다. 그래서 **어떤 문장을 써도 되는지를 데이터가
#    직접 말하게** 한다. 모델이 판단 문장을 지어내기 전에, 이 조건에서
#    허용되는 표현이 무엇인지 응답에 함께 온다.
#
#  백분위 상위 = pct_rank >= 50   (백분위는 0~100 — metrics._percentiles)
#  방향      = coverage.direction() 의 tone (ma7 ÷ ma28). 모멘텀 값으로 정하지 않는다.
#
#  ★ 2026-10-01 — 예전엔 pct_rank >= 0.5 · momentum > 0 으로 갈랐다.
#    둘 다 척도를 잘못 읽은 것이다. 백분위는 0~100 이라 거의 모든 용어가 '상위' 였고,
#    모멘텀은 50 이 보합인 0~100 값이라 늘 '오르는 중' 이었다.
#    그 결과 표본이 충분한 용어는 전부 "지금 올라오는 중 · 권유 가능" 이 됐다.

def _say_rule(pct_rank, tone, thin: bool, mention_28d: int | None = None) -> dict:
    """이 지표 조합에서 허용되는 표현과 권유 가능 여부."""
    if thin:
        # 표본이 임계 아래면 판단 문장 자체를 막는다.
        n = f"최근 28일 언급 {mention_28d}건 — " if mention_28d is not None else ""
        return {"allowed": "관측만 적는다",
                "recommend": "금지",
                "note": f"{n}표본이 적어 판단 문장을 쓰지 마세요. 관측된 수치와 화면의 온도 구간만 적으세요."}
    if pct_rank is None or tone is None:
        return {"allowed": "관측만 적는다", "recommend": "금지",
                "note": "백분위나 28일 방향을 낼 관측이 없어 오르는지 내리는지 말할 수 없습니다."}
    high = float(pct_rank) >= 50
    if high and tone == "up":
        return {"allowed": "지금 올라오는 중입니다", "recommend": "가능", "note": ""}
    if high:
        return {"allowed": "정점을 지나는 중입니다" if tone == "down" else "높은 수준에 머물러 있습니다",
                "recommend": "조건부",
                "note": "권유하려면 얼마나 남았는지 기간을 함께 적으세요."}
    if tone == "up":
        return {"allowed": "이제 올라오기 시작했습니다", "recommend": "조건부",
                "note": "아직 절대량이 적다는 점을 함께 적으세요."}
    return {"allowed": "내려가는 중입니다" if tone == "down" else "아직 낮은 수준에 머물러 있습니다",
            "recommend": "금지",
            "note": "올라오는 근거가 없으니 권하지 마세요. 사실만 적으세요."}
FACETS = ["style", "material", "item", "brand"]
# similar_terms 가 훑어볼 후보 수. 후보마다 연관어를 한 번씩 읽으므로
# 이 값이 곧 SQLite 조회 횟수다. 로컬이라 40이면 수십 ms 다.
CAND_MAX = 40
# similar_terms 가 기준(base)을 고르는 순서. 낮을수록 먼저다.
#   ★ 왜 아이템이 먼저인가 (2026-09-10 실측)
#     "…레이어드 와이드팬츠" 링크에 모델이 **레이어드**(스타일)를 기준으로 넘겼고,
#     "레이어드와 비슷한 것: 스트릿웨어 · 캐주얼 · Y2K" 가 나왔다. 팬츠를 물었는데
#     스타일 목록이 나온 것이다. 어느 축을 기준으로 삼느냐가 답의 종류를 바꾼다.
BASE_ORDER = {"item": 0, "material": 1, "style": 2, "tpo": 3, "fit": 4, "color": 5, "brand": 6}
# 이름 계열을 볼 때 훑는 같은 축 용어 수. item 축이 111개라 200이면 전부 덮는다.
FAMILY_POOL = 200
MIN_SUFFIX = 2          # 공통 꼬리가 이만큼이면 같은 계열로 본다


def _family(base: str, other: str) -> int:
    """이름이 같은 계열인가. 0 이면 아니고, 클수록 강하다.

    ★ 왜 이름을 보나 (2026-09-10)
      "비슷한 것" 의 근거는 연관어 프로필 겹침(2차 연관)이 제일 좋은데,
      실측에서 연관어 표가 얇았다 — 1054행, 'item:팬츠' 는 0개.
      지표에도 사전에도 상의/하의 같은 하위 분류가 **없다**
      (사전이 들고 있는 것: version · surfaces · facet_of · trendable · 차단어).
      그래서 남은 근거가 이름이다. 한국어 패션 용어는 복합어의 **뒤쪽이 범주**인
      경우가 많다 — 와이드팬츠 · 조거팬츠 · 카고팬츠 는 전부 '팬츠' 로 끝난다.
    ★ 완벽하지 않다. '자켓/재킷' 처럼 표기가 갈리면 못 잡고, '블레이저' 는 놓친다.
      **놓치는 것은 괜찮고 틀리게 묶는 것이 문제**라, 기준을 느슨하게 잡지 않는다.
    """
    a = "".join(str(base or "").split())
    b = "".join(str(other or "").split())
    if not a or not b or a == b:
        return 0
    if a in b or b in a:                      # 팬츠 ⊂ 와이드팬츠
        return max(len(a), len(b))
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n if n >= MIN_SUFFIX else 0

# ★ 축을 지목하지 않은 순위("요즘 뭐가 핫해")에서 볼 축.
#   브랜드를 뺀다 — lexicon.yaml 이 브랜드·제품명을 사전에서 뺀 것과 같은 이유다
#   ("사전에 넣으면 트렌드 지표가 특정 브랜드 홍보판이 됩니다").
#   색·핏·TPO 도 뺀다. '블랙' 이 늘 상위에 있는 것은 트렌드가 아니라 상수다.
#   브랜드 순위가 필요하면 facet="brand" 로 명시해서 부르면 그대로 나온다.
TREND_FACETS = ["style", "material", "item"]


def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": desc,
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": props,
            "required": required,
        },
    }


SPECS: list[dict] = [
    _fn(
        "search_terms",
        "질문에 나온 말을 사전에서 찾아 정확한 표기와 축을 돌려준다. "
        "지표를 조회하려면 이 표기가 있어야 한다. 별칭·오타도 잡는다. "
        "결과가 비어도 실패가 아니다 — 용어를 지목하지 않는 질문일 수 있다. "
        "★ 후보가 여럿이면 alts 에 **한 번에 모두** 넣어라. 한 번에 다 찾아 준다. "
        "나눠서 여러 번 부르면 그만큼 바퀴를 쓰고 답 쓸 시간이 없어진다.",
        {"q": {"type": "string", "description": "사용자 질문 원문 또는 그 일부"},
         "alts": {"type": "array", "items": {"type": "string"},
                  "description": "함께 찾아 볼 후보들. 상품명이면 브랜드·아이템·소재로 "
                                 "나눈 말 (예: [\"아디다스\", \"트랙탑\"]). 없으면 빈 배열"}},
        ["q", "alts"],
    ),
    _fn(
        "rank_terms",
        "지금 온도가 높은 용어를 순서대로 돌려준다. "
        "'요즘 뭐가 핫해' '뜨는 브랜드' 처럼 답이 용어인 질문에 쓴다. "
        "질문이 용어를 지목하지 않았을 때 search_terms 대신 이것을 쓴다. "
        "최근 window_days(7)일 안에 언급된 용어마다 마지막 날의 온도로 줄을 세운다 — "
        "항목마다 그 값의 날짜(date)가 있다. 기준을 말할 때는 '최근 7일' 이라고 적어라.",
        {
            "facet": {"type": ["string", "null"], "enum": FACETS + [None],
                      "description": "축을 좁힐 때만. 전체면 null"},
            "limit": {"type": "integer", "description": "몇 개까지. 기본 10"},
        },
        ["facet", "limit"],
    ),
    _fn(
        "get_metric",
        "한 용어의 지표를 가져온다. axes 를 여러 개 넣으면 한 번에 가져온다. "
        "판단이 필요한 질문일수록 여러 축을 함께 넣어야 한다 — "
        "'지금 사도 돼?' 는 온도만으로는 답이 안 된다. "
        "★ 값은 트렌드 분석 화면과 같다(온도 구간·판정 문구·최근 7/28일 합계·긍부정 28일 판정). "
        "온도는 화면의 verdict 로, 긍부정은 화면의 verdict 로 말하고 따로 판정을 만들지 마라. "
        "'주의' 가 있으면 그 기준일·집계 방식을 답변에 밝혀라.",
        {
            "term": {"type": "string", "description": "search_terms 가 준 정확한 표기"},
            "axes": {"type": "array", "items": {"type": "string", "enum": AXES},
                     "description": "필요한 축들. 여러 개 가능"},
        },
        ["term", "axes"],
    ),
    _fn(
        "get_evidence",
        "그 용어가 실제로 어떻게 언급됐는지 원문 조각을 가져온다. "
        "판단의 근거를 사람이 직접 확인할 수 있게 할 때 쓴다. "
        "각 항목은 플랫폼·시점·원문·url 을 준다. url 은 되돌아갈 수 있을 때만 채워지며, "
        "빈 항목은 링크 없이 인용하고 주소를 지어내지 않는다.",
        {"term": {"type": "string"},
         "limit": {"type": "integer", "description": "기본 3"}},
        ["term", "limit"],
    ),
    _fn(
        "get_salmal",
        "살!말? 카드 하나의 투표 현황과 상품 정보를 가져온다. "
        "사용자가 살!말? 화면에서 넘어왔을 때(컨텍스트에 salmal_card_id 가 있을 때) 쓴다.",
        {"card_id": {"type": "integer"}},
        ["card_id"],
    ),
    _fn(
        "search_salmal",
        "같은 아이템·브랜드로 올라온 다른 살!말? 고민들을 찾는다. "
        "'사람들은 뭐래?' 같은 질문에 쓴다.",
        {"term": {"type": "string"}, "limit": {"type": "integer"}},
        ["term", "limit"],
    ),
    _fn(
        "get_salmal_index",
        "구매 고민 대상의 검증된 신호를 가중 결합해 0~100 살말 지수와 근거를 돌려준다. "
        "살말 모드에서는 결론을 쓰기 전에 반드시 호출한다. 없는 축은 임의로 채우지 않는다. "
        "★ 링크·사진·질문에서 **확인한** 구체적 상품이 있으면 item_name·brand·price 에 "
        "함께 적는다. 그 값이 화면의 '물어보기' 버튼을 눌렀을 때 커뮤니티 카드 작성칸에 "
        "그대로 들어간다 — 적지 않으면 사용자가 친 원문(링크 주소)이 상품명 칸에 남는다. "
        "확인하지 못한 칸은 반드시 null 로 둔다. 짐작해서 채우면 사용자가 확인된 값으로 "
        "읽고 그대로 올린다. 가격은 상품 페이지나 검색 결과에서 실제로 본 판매가만 적는다.",
        {"term": {"type": "string", "description": "판단할 정확한 용어 또는 상품명"},
         "item_name": {"type": ["string", "null"],
                       "description": "확인한 상품명(브랜드 제외). 모르면 null"},
         "brand": {"type": ["string", "null"], "description": "확인한 브랜드명. 모르면 null"},
         "price": {"type": ["integer", "null"],
                   "description": "확인한 원화 판매가(숫자만). 확인 못 했으면 null"},
         # ★ 2026-09-18 — 취향 축은 '상품의 스타일' 과 '가입 때 고른 스타일' 을 비교한다.
         #   예전에는 살말 카드의 태그만 봐서, 링크·질문으로 온 상품은 늘 '취향: 빠진 신호' 였다.
         "style_tags": {"type": ["array", "null"], "items": {"type": "string"},
                        "description": ("이 상품이 속하는 패션 스타일 1~3개 (예: 고프코어, 아메카지, "
                                        "스트릿웨어, 미니멀). 상품 페이지·검색 결과·상품 종류로 판단한다. "
                                        "판단할 근거가 없으면 null")}},
        ["term", "item_name", "brand", "price", "style_tags"],
    ),
    _fn(
        "get_user_taste",
        "로그인한 사용자의 취향 가중치를 가져온다. "
        "'나한테 어울려?' '내 취향이야?' 의 유일한 근거다. "
        "비로그인이면 비어서 돌아온다 — 그때는 취향 얘기를 하지 않는다.",
        {},
        [],
    ),
    _fn(
        "inspect_product_link",
        "사용자가 보낸 상품 URL에서 현재 표시된 상품명·브랜드·원화 판매가를 한 번에 "
        "확인한다. 링크 질문에서는 일반 web_search보다 먼저 정확히 한 번 호출한다. "
        "확인하지 못한 필드는 null이며 추측해서 채우지 않는다.",
        {"url": {"type": "string", "description": "사용자가 보낸 원본 http(s) URL"}},
        ["url"],
    ),
    _fn(
        "web_search",
        "사전 밖 지식이나 최신 소식을 웹에서 찾는다. "
        "우리 지표로 답할 수 없는 질문에 쓴다. 출처를 함께 돌려주며, "
        "이 결과는 FEEDiT 측정값이 아니므로 답변에서 그렇게 밝혀야 한다.",
        {"q": {"type": "string"}},
        ["q"],
    ),
    _fn(
        "season_fit",
        "이 옷을 지금 기온·계절에 입을 만한지 본다. "
        "'지금 가을인데 입을 만해?' '이거 지금 입어도 돼?' 같은 질문에 쓴다. "
        "★ 우리 측정값이 아니라 **일반적인 착용 기준**이다 — 답변에서 그렇게 밝혀야 한다. "
        "temp_c 는 web_search 로 알아낸 현재 기온을 넣는다. 모르면 null 로 두면 "
        "계절 평균으로 대신 잡고, 무엇으로 잡았는지 함께 돌려준다.",
        {"terms": {"type": "array", "items": {"type": "string"},
                   "description": "볼 아이템·소재 이름들. 한 번에 여러 개 (예: [\"트랙탑\", \"폴리에스터\"])"},
         "temp_c": {"type": ["number", "null"], "description": "지금 기온(°C). 모르면 null"},
         "season": {"type": ["string", "null"], "description": "봄·여름·가을·겨울. 모르면 null"}},
        ["terms", "temp_c", "season"],
    ),
    _fn(
        "similar_terms",
        "비슷한 것을 우리 지표에서 찾는다. '비슷한 거 추천해줘' 에 쓴다. "
        "★ 후보를 아는 대로 terms 에 **모두** 넣어라 — 도구가 그중 기준을 고른다. "
        "상품 추천이면 **아이템 축 용어(팬츠·티셔츠 …)를 반드시 함께** 넣어라. "
        "스타일 용어(레이어드·스트릿웨어)만 주면 '성격이 비슷한 스타일' 을 찾게 되어 "
        "상품 추천과 다른 답이 나온다. "
        "★ 상품이 아니라 **용어** 단위다. 우리 데이터에 상품 사진은 없다.",
        {"terms": {"type": "array", "items": {"type": "string"},
                   "description": "기준 후보들 (예: [\"팬츠\", \"조거팬츠\", \"레이어드\"]). "
                                  "아이템 축을 우선 고른다"},
         "limit": {"type": "integer", "description": "몇 개까지. 기본 6"}},
        ["terms", "limit"],
    ),
    _fn(
        "compose_report",
        "진단·판정·원인·비교·순위·연관처럼 그림이 읽기를 실제로 돕는 답에서만, 조회가 "
        "끝난 뒤 화면을 구성하는 선택형 UI 스킬이다. 짧은 사실 확인, 인사, 용어 뜻, "
        "간단한 설명처럼 문장만으로 충분하면 호출하지 않는다. 호출한다면 최종 문장을 "
        "쓰기 직전에 한 번만 부른다. "
        "template 으로 질문 유형에 맞는 그림을 고른다: "
        "ticker=한 용어 진단('요즘 어때'·'뜨고 있어'·'식었어', get_metric 온도) · "
        "verdict=살말 판정('살까 말까'·'사도 될까', get_salmal_index, 수명주기·시세는 get_market) · "
        "why=원인('왜 떴어'·'어디서 뜬 거야', get_metric + get_evidence) · "
        "versus=정확히 두 대상 비교('A vs B', 두 용어 get_metric) · "
        "leaderboard=순위('TOP'·'요즘 뭐 떠', rank_terms) · "
        "orbit=연관('같이 뜨는 거'·'뭐랑 입어', get_metric 연관어) · "
        "canvas=위에 맞지 않는 섞인 결과(취향·상황·추천 탐색 등)를 modules 로 직접 배치. "
        "템플릿을 고르면 modules 는 빈 배열로 둔다. 템플릿에 필요한 결과가 없거나 관측이 "
        "얇으면 서버가 결과에 맞는 그림(관측 부족 카드 포함)으로 바꾼다. "
        "★ 이 도구를 부르는 순간 그 모듈의 목록·수치는 **화면이 맡는다.** "
        "카드에 실은 목록을 최종 답변 본문에 다시 나열하지 마라 — 사용자가 같은 "
        "것을 두 번 읽게 된다. 본문은 맨 위 한둘만 짚고 무엇을 센 순위인지와 "
        "어떻게 읽어야 하는지를 말하는 자리다. "
        "kind 는 이미 호출한 도구 결과에 있는 "
        "것만 쓴다: rank_terms=ranking, 둘 이상 get_metric=comparison, get_metric=metric, "
        "모멘텀=direction, 출처별=sources, 연관어=associations, 긍부정=sentiment, "
        "similar_terms=recommendations, get_user_taste=taste, season_fit=context, "
        "get_salmal_index=salmal, "
        "get_evidence=evidence/links, declare_missing=missing. term 은 특정 용어 모듈이면 "
        "그 정확한 표기를 쓰고 공통 모듈이면 null. 화면은 결론→핵심 신호→근거 순으로 "
        "읽히게 하고, 중요한 모듈과 보조 모듈의 폭·강조를 다르게 해 편집형 리듬을 만든다. "
        "모든 모듈을 같은 카드처럼 반복하거나 의미 없이 airy 를 쓰지 말고, 제목은 "
        "'FEEDiT SIGNAL' 대신 질문의 대상과 결과를 드러내는 짧은 한국어로 쓴다. "
        "rank·table은 hero/card/list, KPI는 hero/card로 표현하고 editorial·compact는 "
        "근거와 설명에만 써서 데이터 카드의 시각 문법을 통일한다. "
        "HTML·CSS나 수치·상품을 인자에 쓰지 마라.",
        {
            "template": {"type": "string", "enum": [
                "ticker", "verdict", "why", "versus", "leaderboard", "orbit", "canvas"],
                "description": "질문 유형에 맞는 그림. 섞인 결과면 canvas"},
            "term": {"type": ["string", "null"],
                     "description": "그림의 주인공 용어(정확한 표기). 순위·비교·판정이면 null 가능"},
            "title": {"type": "string", "description": "짧은 리포트 제목. 수치를 넣지 않는다"},
            "accent": {"type": "string", "enum": ["coral", "ink", "violet", "blue", "lime"]},
            "surface": {"type": "string", "enum": ["paper", "soft", "contrast", "glass"]},
            "density": {"type": "string", "enum": ["airy", "balanced", "compact"]},
            "modules": {
                "type": "array", "maxItems": 9,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "kind": {"type": "string", "enum": [
                            "ranking", "comparison", "metric", "direction", "sources",
                            "associations", "sentiment", "recommendations", "taste", "salmal",
                            "context", "evidence", "links", "missing", "lifecycle", "market"]},
                        "term": {"type": ["string", "null"],
                                 "description": "특정 용어 모듈이면 정확한 용어, 공통이면 null"},
                        "presentation": {"type": "string", "enum": [
                            "hero", "card", "chart", "list", "editorial", "compact"]},
                        "span": {"type": "integer", "minimum": 4, "maximum": 12,
                                 "description": "12열 캔버스에서 차지할 열 수"},
                        "emphasis": {"type": "string", "enum": ["strong", "normal", "quiet"]},
                    },
                    "required": ["kind", "term", "presentation", "span", "emphasis"],
                },
            },
        },
        ["template", "term", "title", "accent", "surface", "density", "modules"],
    ),
    _fn(
        "ask_user",
        "무엇을 볼지 되묻는다. 실패가 아니라 정상 행동이다. "
        "'이거 어때?' 처럼 정보가 질문에 없어 어떤 모델도 풀 수 없을 때 쓴다. "
        "★ 우리가 할 수 없는 일(주문·결제·장바구니·개인정보 입력)에는 부르지 마라. "
        "★ 코디·입혀보기 요청에도 부르지 마라 — propose_fit 이 이미 다룬 스타일로 "
        "짠다. 방금 추천한 스타일을 되물으면 기억하지 못하는 챗봇이 된다. "
        "어떤 상품을 주문할지 되물으면 사용자는 고르기만 하면 해 준다는 뜻으로 읽는다. "
        "그때는 도구 없이 못 한다고 답한다. "
        "추측해서 엉뚱한 용어로 답하지 말고 이것을 부른다.",
        {
            "question": {"type": "string", "description": "되물을 한 문장"},
            "options": {"type": "array", "items": {"type": "string"},
                        "description": "고를 수 있는 보기 2~4개. 없으면 빈 배열"},
        },
        ["question", "options"],
    ),
    _fn(
        "declare_missing",
        "그 축들은 우리 데이터에 없다고 기록한다. 지어내는 대신 이것을 부른다. "
        "기록해 두면 답변에서 '아직 측정 자료가 없습니다' 로 정직하게 말할 수 있다. "
        "★ 없는 축이 여럿이면 axes 에 한 번에 모두 넣어라. 축마다 따로 부르지 않는다.",
        {"term": {"type": "string"},
         "axes": {"type": "array", "items": {"type": "string"},
                  "description": "없는 축 이름들 (예: [\"리세일\", \"체형\", \"사이즈\"]). "
                                 "하나뿐이어도 배열로 넣는다"},
         "reason": {"type": "string",
                    "description": "왜 없는지 한 줄. 축들에 공통으로 붙는다"}},
        ["term", "axes", "reason"],
    ),
    # ★ 2026-09-20 — 가격 · 할인 · 리세일 · 수명주기. 트렌드 분석 화면과 같은 API 를 읽는다.
    _fn(
        "get_market",
        "브랜드·아이템 종류·스타일 조건으로 실제 판매·거래 기록을 조회한다. "
        "axis=discount: 무신사·지그재그·에이블리 판매처별 평균/최대 할인율·최저 판매가·품절 수. "
        "axis=resale: 무신사 유즈드·크림 중고/리셀 거래가, 정가 대비 유지율(keep_pct), 거래량, 사이즈별 시세. "
        "axis=lifecycle: 태동·확산·정점·쇠퇴 수명주기 단계와 최근 온도 추이. "
        "'얼마야/할인해?/최저가', '리셀가/중고 시세/프리미엄', '아직 유행해?/끝물이야?' 같은 질문에 쓴다. "
        "조건은 아는 것만 넣고 모르는 칸은 null. 결과에 unavailable 이 있으면 그 축은 없다고 말한다. "
        "숫자는 결과에 있는 값만 쓰고, 판매처·기간(as_of, days)을 함께 적는다.",
        {"axis": {"type": "string", "enum": ["discount", "resale", "lifecycle"]},
         "brand": {"type": ["string", "null"], "description": "브랜드 (예: 나이키, 아크테릭스)"},
         "kind": {"type": ["string", "null"], "description": "아이템 종류 (예: 스니커즈, 바람막이)"},
         "style": {"type": ["string", "null"], "description": "스타일 (예: 고프코어)"},
         "item": {"type": ["string", "null"], "description": "정확한 상품명을 알 때만"},
         "days": {"type": ["integer", "null"], "description": "기간(일). 기본 30"}},
        ["axis", "brand", "kind", "style", "item", "days"],
    ),
    _fn(
        "propose_fit",
        "추천한 스타일로 코디를 짜서 **제안한다**. 입히지는 않는다 — 사용자가 승인하면 "
        "살!말? 로 넘어가 거기서 입혀본다. 사용자가 '이 스타일대로 입혀 줄 수 있어?' "
        "'코디 보여 줘' 처럼 물을 때 부른다. "
        "★ 어떤 스타일인지 되묻지 마라. styles 를 비우면 이 대화에서 이미 다룬 "
        "스타일(앞 턴에서 조회한 것 · 즐겨입는 스타일)로 서버가 짠다. 앞서 네가 "
        "추천한 스타일이 있으면 그것을 styles 에 그대로 적어라. "
        "★ styles 에는 **스타일**만 적는다. 하객·출근·데이트 같은 착용 상황(TPO)이나 "
        "아이템 이름은 스타일 태그가 아니라 상품이 걸리지 않는다 — 그런 요청이면 "
        "어울리는 스타일을 골라 적고(무엇이 있는지 모르면 fit_styles), 아이템은 kinds 에 적어라. "
        "결과가 unavailable 이고 available_styles 가 함께 오면, 그 목록에서 요청에 맞는 "
        "스타일을 골라 **한 번 더** 불러라. 목록을 보고도 고를 수 없을 때만 목록을 "
        "보여 주며 사용자에게 고르게 한다. "
        "kinds 에는 그때 함께 말한 아이템을 칸 순서대로 적는다(예: 트랙 재킷, 카고 팬츠) "
        "— 적으면 그 말로 찾고, 비우면 칸의 기본 아이템으로 찾는다. "
        "slots 은 채울 칸이다. 비우면 상의·하의·신발 한 벌로 고른다. 같은 칸을 두 번 "
        "적으면 두 점을 고른다 — 아우터를 겹쳐 입히려면 '아우터' 를 두 번 적어라. "
        "options 는 켤 연출만 적는다(적지 않은 것은 모델이 알아서 그린다). "
        "outer_layered 는 아우터가 둘일 때만, top_open·top_closed 는 여밈이 있는 상의에만 "
        "성립한다 — 어긋나면 서버가 떼어내고 사유를 돌려준다. "
        "결과의 items 에 있는 상품만 말해라. 사진 없는 상품은 담기지 않는다. "
        "wearer 는 누가 입을 옷인가다. 사용자 본인이 입을 옷이면 self — 서버가 회원정보의 "
        "성별로 상품과 모델을 고른다. '여자친구 선물로', '남자 코디로' 처럼 **다른 성별의 사람이 "
        "입을 옷**이라고 분명히 말했을 때만 FEMALE 또는 MALE 을 적는다. '여자친구랑 데이트할 때 "
        "입을 옷' 은 본인이 입을 옷이다(self).",
        {"styles": {"type": "array", "items": {"type": "string"},
                    "description": "고를 기준이 되는 스타일 이름 (예: 블록코어)"},
         "slots": {"type": "array",
                   "items": {"type": "string",
                             "enum": ["상의", "하의", "아우터", "원피스(셋업)", "신발"]},
                   "description": "채울 칸. 비우면 상의·하의·신발"},
         "kinds": {"type": "array", "items": {"type": "string"},
                   "description": "칸 순서대로 찾을 아이템 말. 없으면 빈 배열"},
         "options": {"type": "array",
                     "items": {"type": "string",
                               "enum": ["outer_layered", "outer_open", "outer_closed",
                                        "top_open", "top_closed"]},
                     "description": "켤 연출만. 없으면 빈 배열"},
         "why": {"type": "string", "description": "이 조합을 고른 이유 한 문장"},
         "wearer": {"type": "string", "enum": ["self", "FEMALE", "MALE"],
                    "description": "입을 사람. 본인이면 self, 다른 성별의 옷을 분명히 말했을 때만 FEMALE/MALE"},
         "occasion": {"type": "string",
                      "description": "입을 상황(TPO) 한 줄. 예: '친구 결혼식 하객', '주말 데이트'. 없으면 빈 문자열"},
         "ref_url": {"type": "string",
                     "description": "이 코디를 짠 근거로 쓴 find_looks 룩의 source.url. 안 썼으면 빈 문자열"}},
        ["styles", "slots", "kinds", "options", "why", "wearer", "occasion", "ref_url"],
    ),
    # ★ 2026-10-02 — "데이트룩 추천해줘" 를 몇 번 물어도 같은 룩이었다. 코디의 재료가
    #   모델의 일반 상식과 상품 추천순 1위뿐이었다. 요즘 실제로 입는 조합을 먼저 찾는다.
    _fn(
        "find_looks",
        "상황(TPO)·분위기에 맞는 **요즘 연예인·인플루언서·매거진 코디**를 웹에서 찾는다. "
        "출처(기사 주소)가 확인된 룩만 돌아오고, 룩마다 칸별 아이템(상품 검색어)이 있다. "
        "'데이트룩 추천해줘' · '하객룩 뭐 입지' · '출근룩 짜줘' 처럼 **상황으로 코디를 물으면 "
        "propose_fit 전에 먼저 부른다.** 고른 룩의 items 를 slots·kinds 로, source.url 을 "
        "ref_url 로 propose_fit 에 넘겨라. 이 결과는 FEEDiT 측정값이 아니다 — 답변에서 "
        "'요즘 ○○에서 이런 조합이 보인다' 처럼 출처와 함께 소개하라. "
        "'다른 룩' 을 원하면 앞서 쓴 룩이 아닌 다른 룩을 골라라(캐시라 다시 불러도 빠르다).",
        {"occasion": {"type": "string", "description": "입을 상황. 예: '친구 결혼식 하객', '주말 데이트'"},
         "styles": {"type": "array", "items": {"type": "string"},
                    "description": "원하는 분위기·스타일(있으면). 예: ['미니멀']"},
         "wearer": {"type": "string", "enum": ["self", "FEMALE", "MALE"],
                    "description": "입을 사람. propose_fit 의 wearer 와 같은 뜻"}},
        ["occasion", "styles", "wearer"],
    ),
    # ★ 2026-10-01 — "입혀볼 수 있는 스타일이 뭐가 있어?" 의 답. 예전엔 이 질문에
    #   맞는 도구가 없어 모델이 트렌드 순위(rank_terms)를 뒤졌고, 그날 언급된 스타일이
    #   없어 "목록이 확인되지 않았다" 고 답했다. 순위와 상품 태그는 다른 표다.
    _fn(
        "fit_styles",
        "코디를 짜서 입혀볼 수 있는 스타일 목록 — 상품에 스타일 태그가 달린 핵심 스타일과 "
        "그 상품 수(스타일 화면 세부 검색과 같은 숫자). '입혀볼 수 있는 스타일이 뭐야?' "
        "'어떤 스타일로 코디돼?' 에, 또는 propose_fit 에 적을 스타일을 고를 때 부른다. "
        "★ 트렌드 순위(rank_terms)는 최근 언급된 용어의 순위라 이 질문의 답이 아니다. "
        "상품 수는 태그가 달린 수다 — 사진이 없는 상품은 코디에 담기지 않는다.",
        {},
        [],
    ),
    _fn(
        "build_fit",
        "승인된 코디를 입혀볼 수 있게 확정한다. 상품 사진을 실제로 보고(칸·여밈·두께) "
        "연출을 검수한 뒤 화면의 착장 칸을 채운다. 생성은 사용자가 위젯에서 누를 때 "
        "일어난다 — 이 도구는 이미지를 만들지 않는다. "
        "결과의 dropped 에 사유가 있으면 답변에 그대로 밝혀라(없는 연출을 말하면 안 된다). "
        "options 를 비우면 승인된 연출을 그대로 쓴다.",
        {"options": {"type": "array",
                     "items": {"type": "string",
                               "enum": ["outer_layered", "outer_open", "outer_closed",
                                        "top_open", "top_closed"]},
                     "description": "바꿀 연출. 비우면 승인된 그대로"}},
        ["options"],
    ),
]

NAMES = [s["name"] for s in SPECS]


# ══════════════════════════════════════════════════════════
#  지금 무엇을 하고 있는지 — 사용자의 말로
# ══════════════════════════════════════════════════════════
#  ★ 왜 필요한가 (설계도 부록 10)
#    도구 루프는 답이 완성될 때까지 화면에 아무것도 안 보낸다. 3초 무반응은
#    이미 고장난 화면이다. 같은 3.4초라도 무엇을 하고 있는지 보이면 기다림이 된다.
#
#    부수 효과가 더 크다 — 어떤 데이터를 봤는지가 답변 **전에** 드러나므로
#    대기 시간이 신뢰의 재료로 바뀐다. L3 가 뒤에서 하는 대조는 사용자가 못
#    보지만, L1 이 무엇을 불렀는지는 보여 줄 수 있다.
#
#  ⚠ 도구 이름을 그대로 쓰지 않는다. `get_metric` 이 아니라 "온도 보는 중".
FACET_SAY = {"style": "스타일", "material": "소재", "item": "아이템", "brand": "브랜드"}
AXIS_SAY = {"온도": "온도", "모멘텀": "추세", "순위": "순위", "연관어": "연관어",
            "긍부정": "반응", "출처별": "플랫폼별", "근거": "실제 언급"}


def _axis_list(axes: Any, axis: Any = None) -> list[str]:
    """declare_missing 의 축 인자를 목록으로 고른다.

    ★ 표준은 axes(배열)다 (2026-09-10, 인수인계 17번).
      예전 스펙은 axis 를 **하나씩** 받아서, 없는 축마다 한 번씩 불렸다.
      그 반복이 orchestrator.MAX_PER_TOOL 에 걸리면 뒤쪽 축은 기록되지
      않은 채 조용히 사라진다 — 상한은 그 증상을 막은 것이지 원인을
      고친 것이 아니었다.
    ★ 그래도 axis(문자열)를 받는다. strict 스키마를 켜도 모델이 옛 모양으로
      부르는 일이 있고, 그때 죽는 것보다 받아 주는 편이 낫다.
    """
    raw: list[Any] = []
    if isinstance(axes, str):
        raw.append(axes)
    elif isinstance(axes, (list, tuple)):
        raw.extend(axes)
    if axis:
        raw.append(axis)
    out: list[str] = []
    for a in raw:
        s = str(a or "").strip()
        if s and s not in out:          # 같은 축을 두 번 적어도 한 줄로 남는다
            out.append(s)
    return out


def progress_say(name: str, args: dict) -> str | None:
    """도구 호출 하나를 사람이 읽는 한 줄로. 보여 줄 게 없으면 None."""
    args = args or {}
    term = str(args.get("term") or "").strip()
    head = f"{term} " if term else ""
    if name == "search_terms":
        # ★ 같은 문구가 반복되면 화면이 멈춘 것처럼 보인다. 찾는 말을 넣는다.
        q = " ".join(str(args.get("q") or "").split())
        if q.startswith("http"):
            # 주소를 그대로 보여 주면 화면이 한 줄을 다 먹는다. 후보 쪽을 보여 준다.
            alt = [str(a).strip() for a in (args.get("alts") or []) if str(a).strip()]
            return f"'{alt[0]}' 찾아보는 중" if alt else "보내신 링크를 살펴보는 중"
        if not q:
            return "말을 사전에서 찾는 중"
        return f"'{q[:12]}…' 찾아보는 중" if len(q) > 12 else f"'{q}' 찾아보는 중"
    if name == "rank_terms":
        f = FACET_SAY.get(args.get("facet") or "")
        return f"지금 뜨는 {f} 세는 중" if f else "지금 뜨는 것 세는 중"
    if name == "get_metric":
        axes = [AXIS_SAY.get(a, a) for a in (args.get("axes") or [])]
        return f"{head}{' · '.join(axes[:3]) or '지표'} 보는 중"
    if name == "get_evidence":
        return f"{head}실제 언급 찾는 중"
    if name == "declare_missing":
        ax = _axis_list(args.get("axes"), args.get("axis"))
        if not ax:
            return "없는 항목을 기록하는 중"
        head = " · ".join(ax[:3]) + ("…" if len(ax) > 3 else "")
        return f"{head} 은(는) 측정 자료가 없다고 기록하는 중"
    if name == "season_fit":
        ts = [str(t).strip() for t in (args.get("terms") or []) if str(t).strip()]
        return f"{ts[0]} 지금 입기 좋은지 보는 중" if ts else "지금 입기 좋은지 보는 중"
    if name == "similar_terms":
        cand = [str(t).strip() for t in (args.get("terms") or []) if str(t).strip()]
        first = cand[0] if cand else term
        return f"{first} 비슷한 것 찾는 중" if first else "비슷한 것 찾는 중"
    if name == "get_market":
        what = " ".join(str(args.get(k)).strip() for k in ("brand", "kind", "style", "item")
                        if args.get(k)) or "조건"
        axis = {"discount": "할인·최저가", "resale": "리셀·중고 시세",
                "lifecycle": "수명주기"}.get(args.get("axis"), "시장 기록")
        return f"{what} {axis} 보는 중"
    if name == "propose_fit":
        st = [str(t).strip() for t in (args.get("styles") or []) if str(t).strip()]
        return f"{st[0]} 코디 짜는 중" if st else "코디 짜는 중"
    if name == "find_looks":
        occ = str(args.get("occasion") or "").strip()
        return f"요즘 {occ} 코디 찾아보는 중" if occ else "요즘 코디 찾아보는 중"
    if name == "fit_styles":
        return "입혀볼 수 있는 스타일 보는 중"
    if name == "build_fit":
        return "고른 옷을 살펴보는 중"
    if name == "get_salmal":
        return "살!말? 투표 보는 중"
    if name == "search_salmal":
        return f"{head}비슷한 고민 찾는 중"
    if name == "get_salmal_index":
        return f"{head}살말 지수 계산하는 중"
    if name == "get_user_taste":
        return "취향에 맞춰 보는 중"
    if name == "inspect_product_link":
        return "보내신 링크에서 브랜드와 가격을 확인하는 중"
    if name == "compose_report":
        return "결과에 맞는 화면을 구성하는 중"
    if name == "web_search":
        return "밖에서 찾아보는 중"
    # ask_user · declare_missing 은 조회가 아니다. 진행 표시를 낼 것이 없다.
    return None


# ══════════════════════════════════════════════════════════
#  실행
# ══════════════════════════════════════════════════════════

def _rank_items(rows: list[dict]) -> dict:
    """rank_terms 의 항목 — 숫자와 구간을 트렌드 분석 화면과 같게 (2026-10-01).

    ★ 온도는 화면처럼 반올림한다(Math.round). 예전엔 원값(87.6)을 주고 카드는
      int() 로 잘라 87점이 떴다 — 화면은 같은 용어를 88° 로 보여 준다.
      구간은 반올림한 값으로 정하므로(84.6 → 85 → 과열), 잘라 쓰면 "84점 · 과열" 처럼
      숫자와 구간이 어긋난다.
    ★ 순위 · 구간별 개수 · 맨 위부터 같은 구간이 몇 개인지를 **도구가 센다.**
      모델이 항목을 세어 "상위 4개는 모두 과열" 이라고 쓰면 4 는 도구 결과에 없는
      숫자라 검증이 지웠고, 화면에 "상위 개는 모두 과열" 이 남았다(2026-10-01 실측).
    """
    items = []
    for i, r in enumerate(rows, 1):
        raw = r.get("temp")
        temp = None if raw is None else js_round(raw)
        band = None if raw is None else temp_band(raw)
        facet = r.get("facet")
        item = {"rank": i, "term": r["canonical"], "facet": facet,
                "facet_name": FACET_SAY.get(facet, facet),
                "temp": temp, "band": band,
                "verdict": TEMP_VERDICTS[band][0] if band else None,
                "raw_count": r.get("raw_count")}
        if r.get("metric_date"):
            # 이 온도가 며칠 자 값인가 — 순위는 최근 7일 안의 마지막 값이다 (2026-10-01)
            item["date"] = str(r["metric_date"])[:10]
        items.append(item)
    counts: dict[str, int] = {}
    for it in items:
        if it["band"]:
            counts[it["band"]] = counts.get(it["band"], 0) + 1
    streak = 0
    for it in items:
        if items and it["band"] and it["band"] == items[0]["band"]:
            streak += 1
        else:
            break
    return {
        "items": items,
        # 화면 '언급량·온도' 탭과 같은 구간 경계 (config.TEMP_BANDS)
        "band_edges": {"과열": 85, "따뜻함": 65, "미지근": 40},
        "band_counts": {b: counts[b] for b in ("과열", "따뜻함", "미지근", "차가움") if b in counts},
        "top_streak": ({"band": items[0]["band"], "count": streak} if items and items[0]["band"] else None),
    }


class TraceLog:
    """이번 요청에서 무엇을 불렀고 무엇이 돌아왔나.

    ★ 원본을 그대로 들고 있어야 한다.
      verify.py 가 답변의 숫자를 여기와 대조한다. 요약해서 넣으면
      대조할 것이 없어지고, 검증은 그냥 통과 도장이 된다.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.missing: list[dict] = []       # declare_missing 이 남긴 것
        self.asked: dict | None = None      # ask_user 가 남긴 것

    def add(self, name: str, args: dict, result: Any) -> None:
        self.calls.append({"tool": name, "args": args, "result": result})

    def numbers(self) -> set[str]:
        """도구 결과에 실제로 등장한 숫자들. 검증관이 쓴다."""
        seen: set[str] = set()

        def walk(v: Any) -> None:
            if isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    walk(x)
            elif isinstance(v, bool):
                return
            elif isinstance(v, (int, float)):
                seen.add(_numstr(v))
            elif isinstance(v, str) and v.replace(".", "", 1).lstrip("-").isdigit():
                seen.add(_numstr(float(v) if "." in v else int(v)))

        # compose_report 의 span·제목은 화면 배치값이지 조회 사실이 아니다.
        # 검증 숫자에 섞이면 모델이 만든 숫자가 도구 근거인 것처럼 통과한다.
        walk([c for c in self.calls if c.get("tool") != "compose_report"])
        return seen

    def terms(self) -> set[str]:
        """도구 결과에 등장한 용어·라벨. 없는 말을 지어냈는지 볼 때 쓴다."""
        out: set[str] = set()
        for c in self.calls:
            if c.get("tool") == "compose_report":
                continue
            for k in ("term", "q"):
                if isinstance(c["args"].get(k), str):
                    out.add(c["args"][k])
            _collect_labels(c["result"], out)
        return out

    def as_payload(self) -> list[dict]:
        return self.calls


def _numstr(v: float | int) -> str:
    """1.0 과 1 을 같은 것으로 본다. 검증에서 헛걸림을 줄인다."""
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0").rstrip(".")


def _collect_labels(v: Any, out: set[str]) -> None:
    KEYS = ("canonical", "assoc_canonical", "label", "title", "brand", "source_code")
    if isinstance(v, dict):
        for k, x in v.items():
            if k in KEYS and isinstance(x, str) and x:
                out.add(x)
            else:
                _collect_labels(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _collect_labels(x, out)


class Toolbox:
    """도구 이름 → 실제 함수.

    store·gate 는 밖에서 넣는다. 이 파일이 SQLite 를 직접 열지 않는다 —
    나중에 RDS(Django ORM)로 옮길 때 store.py 만 갈아 끼우면 되도록.

    salmal·taste 는 아직 원본이 없다(RDS 쪽 표는 있으나 챗봇이 안 본다).
    없는 채로 부르면 **비어 있음**을 돌려준다. 죽지 않고, 지어내지도 않는다.
    """

    def __init__(self, store, gate, ctx: dict | None = None,
                 salmal=None, taste=None, websearch=None, market=None,
                 trend=None) -> None:
        self.store = store
        self.market = market   # 없으면 처음 부를 때 MarketHTTPAdapter 를 만든다
        self.trend = trend     # 없으면 trend_view.source() — 리포트 카드와 같은 캐시를 쓴다
        self.gate = gate
        self.ctx = ctx or {}
        self.salmal = salmal
        self.taste = taste
        self.websearch = websearch
        self.product = None
        self.trace = TraceLog()

    # ── 디스패치 ────────────────────────────────────────
    def run(self, name: str, args: dict) -> Any:
        fn: Callable | None = getattr(self, f"t_{name}", None)
        if fn is None:
            # 모델이 없는 도구를 부르는 일은 실제로 일어난다.
            # 죽이지 말고 사실대로 알려 주면 다음 바퀴에서 고쳐 부른다.
            result = {"error": "없는 도구입니다", "available": NAMES}
        else:
            try:
                result = fn(**args)
            except TypeError as e:
                result = {"error": f"인자가 맞지 않습니다: {e}"}
            except Exception as e:                      # noqa: BLE001
                # 도구 하나가 죽어도 대화는 계속돼야 한다.
                result = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
        self.trace.add(name, args, result)
        return result

    # ── 사전 ────────────────────────────────────────────
    def _key(self, term: str) -> str:
        """term_key 를 만든다. 사전에 없으면 지표 표의 축을 쓴다.

        gate.term_key() 는 lex.facet_of 만 보므로 브랜드는 "None:살로몬" 이 된다.
        """
        f = self.gate.facet_of(term)
        if not f:
            f = self.store.metric_facet(term)
        return f"{f}:{term}"

    def _look_up(self, text: str) -> tuple[list[dict], str]:
        """말 하나를 사전 → 지표 순으로 찾는다. (hits, 어디서 찾았나)"""
        parsed = self.gate.parse(text)
        hits = [{"term": h["canonical"], "facet": h["facet"], "term_key": h["term_key"]}
                for h in parsed.get("search", [])]
        if hits:
            return hits, "lexicon"
        # ★ 사전에 없어도 **지표에는 있을 수 있다.** (2026-09-09)
        #   실측: "살로몬" 은 지표 표에 8행 있는데 사전에 없어 못 찾았고,
        #   챗봇은 "측정 자료가 없습니다" 라고 답했다. 틀린 답이다.
        direct = self.store.metric_terms_in(text, limit=3)
        if direct:
            return ([{"term": r["canonical"], "facet": r["facet"],
                      "term_key": f'{r["facet"]}:{r["canonical"]}'} for r in direct],
                    "metric")
        return [], ""

    def t_search_terms(self, q: str, alts: Any = None) -> dict:
        """q 와 alts 를 **한 번에** 찾는다 (2026-09-10).

        ★ 왜 alts 인가 — 실측(무신사 상품 링크): 모델이 링크 → "아디다스 트랙탑"
          → "트랙탑" 순으로 search_terms 를 **세 번** 불렀다. 한 번 부를 때마다
          모델 왕복이 한 바퀴라, 세 바퀴(15초)를 조회에만 쓰고 답을 못 썼다.
          17번의 declare_missing 과 같은 낭비다 — **스펙이 하나씩만 받으면
          모델은 하나씩 부른다.** 그래서 여기도 한 번에 받는다.
        ★ 후보를 순회하되 **첫 성공에서 멈추지 않는다.** 브랜드와 아이템이 둘 다
          잡혀야 '나란히 보기' 가 붙는다.
        """
        tried = [str(q or "").strip()]
        for a in (alts if isinstance(alts, (list, tuple)) else []):
            t = str(a or "").strip()
            if t and t not in tried:
                tried.append(t)

        hits: list[dict] = []
        seen: set[str] = set()
        sources: set[str] = set()
        for cand in tried:
            if not cand:
                continue
            got, where = self._look_up(cand)
            if where:
                sources.add(where)
            for h in got:
                if h["term"] in seen:
                    continue
                seen.add(h["term"])
                hits.append(dict(h, **({"from": cand} if cand != tried[0] else {})))

        parsed = self.gate.parse(tried[0] if tried else "")
        out: dict[str, Any] = {"found": hits, "count": len(hits), "tried": tried}
        if hits and "metric" in sources:
            out["source"] = "metric"          # 사전이 아니라 지표에서 직접 찾았다
            out["note"] = ("사전에는 없지만 지표에 이름이 있는 용어가 있습니다"
                           "(브랜드 등). 그대로 get_metric 에 넘기면 됩니다.")
        # ★ '대신 봤다' 는 **원문으로는 못 찾았을 때만**이다 (2026-10-01).
        #   예전엔 alts 를 넘기기만 하면 붙었다. "더비슈즈는 왜 93점이야?" 는 원문에서
        #   더비슈즈를 찾았는데도 "'더비슈즈는 왜 93점이야?' 대신 더비슈즈 기준으로 봤다"
        #   는 어색한 문장이 나갔다. 원문에서 찾은 것(from 이 없는 것)이 있으면 대체가 아니다.
        if hits and len(tried) > 1 and all(h.get("from") for h in hits):
            out["substituted"] = True
            첫말 = tried[0] if len(tried[0]) <= 40 else tried[0][:39] + "…"
            out["substituted_note"] = (
                f"'{첫말}' 로는 못 찾아 다른 후보로 찾았습니다. "
                "답변에 **무엇 대신 무엇을 봤는지 반드시 밝히십시오.**")
        if not hits:
            # 못 찾았다고 끝이 아니다. 가까운 말과 인기어를 같이 준다 —
            # 모델이 되묻거나 rank_terms 로 갈아탈 재료가 된다.
            out["near"] = self.gate.near_candidates(q, limit=3)
            out["popular"] = self.gate.popular(self.store, limit=3)
            out["hint"] = ("용어를 지목하지 않은 질문일 수 있습니다. "
                           "'요즘 뭐가 핫해' 류면 rank_terms 를 쓰세요.")
            # ★ 표기만 바꿔 다시 부르는 것을 막는다 (2026-09-09 실측:
            #   "살로몬 XT-6" → "XT-6" → "살로몬" 으로 3~4연속 호출).
            out["retry"] = "금지"
            out["retry_note"] = (
                "같은 대상을 표기만 바꿔(띄어쓰기·모델명 분리·영문) 다시 부르지 마십시오. "
                "사전에도 지표에도 없는 말은 표기를 바꿔도 없습니다. "
                "구성 요소로 나눠 볼 생각이면 **이 도구를 다시 부르지 말고 alts 에 "
                "한 번에 넣으십시오** (예: alts=[\"아디다스\", \"트랙탑\"]). "
                "한 번 더 부를 때마다 바퀴를 하나 쓰고, 그만큼 답 쓸 시간이 줄어듭니다. "
                "그래도 없으면 declare_missing 으로 기록하고 답을 쓰십시오.")
        # 수식어(핏·색·TPO)는 검색어가 아니지만 답변 톤에 쓰인다
        out["modifiers"] = [h["canonical"] for h in parsed.get("modifier", [])]
        return out

    def t_rank_terms(self, facet: str | None = None, limit: int = 10) -> dict:
        n = max(1, min(int(limit or 10), 20))
        rows = self.store.top_terms(facet=facet or None, limit=n,
                                    facets=None if facet else TREND_FACETS)
        day = self.store.latest_day()
        return {
            "as_of": day,
            # ★ 하루가 아니라 최근 며칠 안에서 용어마다 마지막 값이다 (2026-10-01, config.RANK_WINDOW_DAYS).
            "window_days": RANK_WINDOW_DAYS,
            "window_note": (f"최근 {RANK_WINDOW_DAYS}일 안에 언급된 용어마다 마지막 날의 온도로 "
                            "줄을 세웠습니다. 날짜는 항목마다 다릅니다."),
            "asked": n,
            "returned": len(rows),
            # 어떤 축을 보고 센 순위인지 밝힌다. 모델이 답에 적을 수 있어야 한다.
            "facets_seen": [facet] if facet else TREND_FACETS,
            "facets_note": (None if facet else
                            "브랜드·색·핏 축은 전체 순위에서 제외했습니다. "
                            "브랜드 순위를 원하면 facet=\"brand\" 로 다시 부르십시오."),
            # ★ 요청한 수보다 적을 수 있다. 그 사실을 명시한다 —
            #   안 그러면 모델이 나머지를 채워 넣는다.
            "short_of_asked": len(rows) < n,
            **_rank_items(rows),
        }

    # ── 지표 ────────────────────────────────────────────
    def _trend_api(self):
        if self.trend is None:
            self.trend = trend_view.source()
        return self.trend

    def t_get_metric(self, term: str, axes: list[str]) -> dict:
        """한 용어의 지표 — **트렌드 분석 화면과 같은 값**을 읽는다 (2026-10-01).

        온도·모멘텀·순위·출처별·긍부정은 화면이 부르는 /api/trend · /api/sentiment 를
        같은 인자로 불러 화면과 같은 규칙으로 요약한다(trend_view.py).
        연관어는 화면의 /api/assoc 를 읽는다. 원문 근거만 RDS 에서 읽는다.

        ★ 예전엔 표를 직접 읽어 화면과 판단이 갈렸다(trend_view.py 머리말의 표).
          · 브랜드는 '측정 자료 없음'(화면은 온도 83°)
          · 긍부정은 마지막 하루 행(팬츠 2건, 화면은 28일 536건)
          · 백분위를 0~1 로 읽어 '상위 1%'(화면 기준 상위 82%)
        """
        want = set(axes or [])
        view = trend_view.term_view(term, self.gate.facet_of(term),
                                    with_sentiment="긍부정" in want,
                                    with_assoc="연관어" in want, api=self._trend_api())
        if view["status"] == "error":
            # ★ 표를 직접 읽어 대신 채우지 않는다. 화면과 다른 숫자가 다시 나간다.
            #   has_metric 을 False 로 두지 않는다 — '없다' 가 아니라 '못 읽었다' 다.
            return {"term": term, "has_metric": None,
                    "unavailable": view["reason"] + " 잠시 뒤 다시 물어 주세요."}
        if view["status"] == "empty":
            # ★ 키 이름을 found 로 쓰지 않는다.
            #   search_terms 는 found 를 **목록**으로 준다. 같은 이름으로 여기서
            #   불리언을 주면 결과를 훑는 코드가 bool 을 순회하려다 터지고,
            #   모델도 두 도구의 found 를 같은 뜻으로 읽는다.
            #   (2026-09-09 실측: agent_path._terms_from 이 이걸로 죽었다)
            return {"term": term, "has_metric": False, "reason": view["reason"]}

        T = view["trend"]
        obs = T["obs"]
        say = trend_view.may_say(obs)
        can_dir = obs["n28"] >= MIN_OBS_28 and obs["n7"] >= MIN_OBS_7
        d = _direction({"ma7": T["ma7"], "ma28": T["ma28"]}) if can_dir else None
        out: dict[str, Any] = {
            "term": term, "has_metric": True,
            "basis": "트렌드 분석 화면과 같은 값",
            "as_of": T["as_of"],                 # 이 용어의 마지막 집계일
            "data_as_of": T["data_as_of"],       # 화면이 '기준일' 로 띄우는 DB 최신화 일자
            "metric_version": T["metric_version"],
            # ★ 언급량은 하루치가 아니라 기간 합계로 준다.
            "mentions": {"최근7일": T["mention_7d"], "최근28일": T["mention_28d"]},
            "observations": T["obs"],
            # ★ 관측이 모자라면 그 축은 **말하면 안 된다.** config 의 실측 기준이다.
            "may_say": say,
            "thin_sample": T["thin"],
        }
        if T["notes"]:
            # 기준일이 묵었거나, 장기 이력으로 그렸거나, 언급 0 행의 온도인 경우.
            # 숫자만 말하면 오늘 값처럼 읽힌다 — 답변에 그대로 밝힌다.
            out["주의"] = T["notes"]
            # '며칠 전' 을 적으면 verify 가 대조할 수 있게 숫자로도 둔다.
            out["stale_days"] = T["stale_days"]
        if "온도" in want:
            out["온도"] = {
                "temp": T["temp"],
                "band": T["band"],                 # 화면 막대: 차가움·미지근·따뜻함·과열
                "verdict": T["verdict"],           # 화면 제목: "OO는 지금 {verdict} 구간"
                "verdict_text": T["verdict_text"],
                # ★ 기준선 (설계도 부록 11) — "온도 71°" 만으로는 높은지 낮은지 모른다.
                #   백분위는 그날 언급된 **전체 용어** 사이의 순위다(0~100). '같은 축' 이 아니다.
                "percentile": T["percentile"],
                "rank_text": (None if T["top_pct"] is None else
                              f"그날 언급된 전체 용어 중 상위 {T['top_pct']}%"),
                # 화면의 '이번 주 온도 변화' 와 같은 계산(7일 전 또는 그 앞의 가장 가까운 행).
                #   ★ 2주 관측이 모자라면 말하지 않게 한다 — 표본 몇 건짜리가 "31° 하락" 으로 나간다.
                "delta_1w": T["delta_1w"] if say["2주변화"] else None,
                "temp_1w_ago": T["temp_1w_ago"] if say["2주변화"] else None,
                "temp_1w_ago_date": T["temp_1w_ago_date"] if say["2주변화"] else None,
                "delta_1w_note": (None if say["2주변화"] else
                                  f"14일 관측 {obs['n14']}일 — 지난주 대비 변화를 말하기엔 모자랍니다."),
                # 표본 — 12건으로 낸 71° 와 1,240건으로 낸 71° 는 다르다
                "sample_n": T["mention_28d"],
                "sample_basis": "최근 28일 언급 합계",
                "as_of": T["as_of"],
            }
        if "모멘텀" in want:
            out["모멘텀"] = ({"momentum": T["momentum"], "flat_at": 50,   # 화면: 성장 모멘텀 (50=보합)
                            "ma7": T["ma7"], "ma28": T["ma28"],
                            "direction": d["label"] if d else None,
                            "ratio_7d_28d": d["ratio"] if d else None}
                           if can_dir else
                           {"unavailable": f"28일 관측 {obs['n28']}일 — 방향을 말하기엔 모자랍니다."})
        if "순위" in want:
            out["순위"] = {"percentile": T["percentile"], "top_pct": T["top_pct"],
                         "level": T["level"],
                         "basis": "그날 언급된 전체 용어 사이의 백분위(0~100)"}
        if "출처별" in want:
            out["출처별"] = view["platforms"] or {"unavailable": "플랫폼별 온도가 아직 없습니다."}
        if "연관어" in want:
            out["연관어"] = ({"unavailable": view["assoc_unavailable"]}
                          if view.get("assoc_unavailable") else view.get("associations") or [])
        if "긍부정" in want:
            # ★ 화면 긍부정 탭과 같은 값 — 최근 28일 합계, 20건 미만이면 '판단 보류'.
            #   (2026-09-09 의 '표본 문턱' 은 그대로다. 문턱의 자리만 화면과 맞췄다.)
            out["긍부정"] = view.get("sentiment") or {"unavailable": "긍부정 지표가 아직 없습니다."}
        if "근거" in want:
            try:
                out["근거"] = self.store.term_evidence(self._key(term), limit=3)
            except Exception as exc:  # noqa: BLE001 - preserve the verified metric axes
                out["근거"] = {"unavailable": f"원문 근거를 읽지 못했습니다 ({type(exc).__name__})."}

        # ★ 이 조건에서 써도 되는 문장. 모델이 판단을 지어내기 전에 준다.
        out["말할_수_있는_것"] = _say_rule(T["percentile"], d["tone"] if d else None,
                                       T["thin"], T["mention_28d"])
        return out

    def t_get_evidence(self, term: str, limit: int = 3) -> dict:
        """근거 원문 조각. 링크는 **있는 것만** 붙인다.

        ★ 왜 url 이 None 인 채로 그냥 나가나
          store.evidence_link() 는 되돌아갈 수 있는 주소만 만든다. 네이버는
          product_uid 가 'kw:<검색어>' 라 글 자체를 가리키지 못한다(전체의 약 40%).
          여기서 "네이버 블로그 검색 결과" 같은 그럴듯한 주소를 지어 붙이면,
          누른 사람은 우리가 인용한 글이 아닌 곳에 떨어진다. 틀린 숫자와 같은 종류의
          거짓말이다. 그래서 없으면 없는 채로 내보내고, 몇 개가 확인 가능한지
          linkable 로 함께 알려 준다 — 모델이 "3건 중 2건은 원문 확인 가능" 이라고
          정직하게 쓸 수 있도록.
        """
        key = self._key(term)
        rows = self.store.term_evidence(key, limit=max(1, min(int(limit or 3), 8)))
        items = []
        for r in rows:
            it = {"platform": r.get("platform") or r.get("source_code"),
                  "at": r.get("at"),
                  "body": r.get("body"),
                  "sentiment": r.get("sentiment"),
                  "url": r.get("url")}
            if not it["url"]:
                it["url_note"] = "원문 링크 없음"
            items.append(it)
        linkable = sum(1 for it in items if it.get("url"))
        return {"term": term, "count": len(items), "linkable": linkable,
                "items": items,
                "link_rule": "url 이 있는 항목만 링크로 쓸 수 있다. "
                             "url 이 없으면 '(원문 링크 없음)' 이라고 적고, "
                             "주소를 짐작해서 만들지 마라."}

    # ── 살!말? ──────────────────────────────────────────
    def t_get_market(self, axis: str, brand=None, kind=None, style=None,
                     item=None, days=None) -> dict:
        if self.market is None:
            from .adapters import MarketHTTPAdapter
            self.market = MarketHTTPAdapter()
        sel = {"brand": brand, "kind": kind, "style": style, "item": item}
        if not any(v for v in sel.values()):
            return {"unavailable": "브랜드·아이템 종류·스타일 중 하나는 있어야 조회할 수 있습니다.",
                    "axis": axis}
        try:
            d = max(7, min(int(days or 30), 365))
        except (TypeError, ValueError):
            d = 30
        if axis == "discount":
            out = self.market.discount(sel, days=d)
        elif axis == "resale":
            out = self.market.resale(sel, days=max(14, d))
        elif axis == "lifecycle":
            out = self.market.lifecycle(sel, term=style or kind or brand or item)
        else:
            return {"error": "axis 는 discount · resale · lifecycle 중 하나입니다."}
        if isinstance(out, dict):
            out.setdefault("axis", axis)
            out.setdefault("query", {k: v for k, v in sel.items() if v})
        return out

    # ── 코디 인계 (2026-09-22) ─────────────────────────────
    #   propose_fit 은 고르기만 하고, build_fit 은 사진을 보고 확정한다.
    #   둘을 한 도구에 합치면 제안과 확정이 같은 호출 안에서 갈려 궤적에 구분이
    #   남지 않는다 — 승인 전후를 대조할 원본이 없어진다(원칙 2).
    def _market_api(self):
        if self.market is None:
            from .adapters import MarketHTTPAdapter
            self.market = MarketHTTPAdapter()
        return self.market

    def _gender_for(self, wearer: str | None) -> str | None:
        # ★ 성별 (2026-10-02) — 기본은 회원정보의 성별(ctx.gender · 화면이 ME.gender 를 보낸다).
        #   질문 글자로 정하지 않는다: "여자친구랑 데이트할 때 뭐 입지?" 는 남자가 입을 옷이다.
        #   다른 사람의 옷이라고 분명히 말했을 때만 모델이 wearer 로 바꾼다.
        return wearer if wearer in ("FEMALE", "MALE") else self.ctx.get("gender")

    def t_find_looks(self, occasion: str = "", styles: Any = None, wearer: str = "self") -> dict:
        from . import lookbook
        names = [str(s).strip() for s in (styles or []) if str(s or "").strip()]
        got = lookbook.find(occasion, names, self._gender_for(wearer))
        # 이 대화에서 이미 근거로 쓴 룩을 알려 준다 — '다른 룩' 이면 그걸 피해서 고르게.
        used = [str(u) for u in (self.ctx.get("fit_refs") or [])]
        if used and got.get("looks"):
            got = {**got, "used_before": [lk["source"]["url"] for lk in got["looks"]
                                          if lk["source"]["url"] in used]}
        return got

    def _look_for(self, url: str) -> dict | None:
        """이번 턴에 find_looks 가 실제로 돌려준 룩 중 이 주소의 것. 없으면 None —
        모델이 적은 주소를 그대로 출처로 올리지 않는다."""
        url = str(url or "").strip()
        if not url:
            return None
        for call in self.trace.calls:
            if call.get("tool") != "find_looks":
                continue
            for look in (call.get("result") or {}).get("looks") or []:
                if look.get("source", {}).get("url") == url:
                    return look
        return None

    def t_propose_fit(self, styles: Any = None, slots: Any = None, kinds: Any = None,
                      options: Any = None, why: str = "", wearer: str = "self",
                      occasion: str = "", ref_url: str = "") -> dict:
        from . import fit

        asked = [str(s).strip() for s in (styles or []) if str(s or "").strip()]
        # ★ 사전으로 스타일 표준 이름을 고른다 (2026-10-01, fit.resolve_styles).
        #   "긱시크룩" → 긱시크. "결혼식 하객" 은 TPO 라 스타일로 찾지 않는다.
        picked, skipped = fit.resolve_styles(asked, self.gate)
        if asked and not picked:
            # 적은 말이 하나도 스타일이 아니었다. 즐겨입는 스타일로 몰래 바꾸지 않는다 —
            # 하객룩을 물었는데 고프코어 코디가 나오면 엉뚱하다. 고를 수 있는 목록을 준다.
            names = " · ".join(f"‘{s['name']}’" for s in skipped)
            return {"unavailable": f"{names} 은(는) 상품 스타일 태그가 아니라 그 이름으로는 "
                                   "상품을 고를 수 없습니다.",
                    "skipped": skipped, **self._fit_choices()}
        # ★ 되묻지 않는다 (2026-09-22). 모델이 앞 턴의 스타일을 옮겨 적지 않아도,
        #   이 대화에서 이미 다룬 스타일이 ctx 에 있다(orchestrator._recent_styles).
        #   "위 스타일대로 입혀 줘" 에 "어떤 스타일로요?" 를 되묻던 자리다.
        if not picked:
            picked = [str(s) for s in (self.ctx.get("recent_styles") or [])]
        gender = self._gender_for(wearer)
        # ★ 이 대화에서 이미 보여 준 상품은 뺀다(화면이 fit_seen 으로 보낸다) — "다른 룩" 에
        #   같은 셔츠가 또 나오지 않게. 후보 안에서 무작위로 고른다(fit.POOL · PICK_TOP).
        found = fit.propose(self._market_api(), picked, slots, kinds, gender=gender,
                            seen=self.ctx.get("fit_seen"))
        if "unavailable" in found:
            out = {**found, **self._fit_choices()}
            if skipped:
                out["skipped"] = skipped
            return out
        on = {str(k): True for k in (options or []) if str(k) in vton.OPTION_LINES}
        # ★ 아직 사진을 보지 않았다. 구조로 걸러지는 것만 먼저 뗀다(seen=[]) —
        #   여밈 판단은 사진을 볼 수 있는 build_fit 이 한다.
        on, dropped = fit.prune_options(on, found["items"], [])
        out = {"proposed": True, **found,
               # 인자가 비어 대화 기억으로 골랐으면 그 사실을 남긴다. 답변이
               # "앞서 말한 고프코어로 짰습니다" 라고 말할 근거다.
               "styles_from": "대화" if not (styles or []) else "요청",
               "options": sorted(k for k, v in on.items() if v),
               "why": str(why or "").strip()[:200],
               "note": "아직 입히지 않았다. 사용자가 승인하면 살!말? 에서 입혀본다."}
        if str(occasion or "").strip():
            out["occasion"] = str(occasion).strip()[:40]
        look = self._look_for(ref_url)
        if look:
            # 근거로 쓴 코디 기사 — find_looks 가 확인한 주소만 싣는다.
            out["ref"] = {"title": look["title"], "who": look.get("who") or "",
                          "url": look["source"]["url"], "domain": look["source"].get("domain") or ""}
        elif str(ref_url or "").strip():
            out["ref_dropped"] = "ref_url 이 이번 find_looks 결과에 없어 출처로 싣지 않았다."
        if dropped:
            out["dropped"] = dropped
        if skipped:
            # 적은 말 중 스타일이 아니어서 뺀 것 — 답변이 "하객은 스타일이 아니라 …" 라고
            # 말할 근거다. 조용히 빼지 않는다.
            out["skipped"] = skipped
        return out

    def _fit_choices(self) -> dict:
        """코디를 못 짰을 때 함께 주는 것 — 고를 수 있는 스타일 목록과 다음 행동."""
        rows = self._fit_style_rows()
        if not rows:
            return {}
        return {"available_styles": rows,
                "next": "available_styles 에서 요청(상황·아이템)에 어울리는 스타일을 골라 "
                        "propose_fit 을 한 번 더 불러라. kinds 는 그대로 둔다. 고를 수 없으면 "
                        "이 목록을 보여 주고 사용자에게 고르게 하라."}

    def _fit_style_rows(self) -> list[dict]:
        # 목록을 못 읽어도 코디 답 자체는 죽지 않는다 — 목록 없이 사유만 간다.
        getter = getattr(self._market_api(), "styles", None)
        try:
            rows = getter() if callable(getter) else []
        except Exception:                       # noqa: BLE001
            rows = []
        return [r for r in (rows or []) if isinstance(r, dict) and r.get("style")]

    def t_fit_styles(self) -> dict:
        rows = self._fit_style_rows()
        if not rows:
            return {"unavailable": "스타일 태그 목록을 읽지 못했습니다."}
        return {"styles": rows,
                "basis": "스타일 화면 세부 검색과 같은 목록 — 핵심 스타일마다 태그가 달린 "
                         "판매 중 상품 수",
                "note": "이 이름으로 propose_fit 을 부르면 코디를 짤 수 있다. 사진이 없는 "
                        "상품은 코디에 담기지 않으므로 상품 수가 곧 입혀볼 수 있는 수는 아니다."}

    def t_build_fit(self, options: Any = None) -> dict:
        from . import fit

        proposal = self.ctx.get("fit_proposal")
        proposal = proposal if isinstance(proposal, dict) else {}
        # ★ 코디는 화면을 거쳐 돌아온다 — 우리가 고른 그것이라는 보장이 없다.
        #   허용한 상품 CDN 의 사진만 본다(vton.ALLOWED_IMAGE_HOSTS). 생성 단계에서
        #   어차피 막히는 주소를, 사진 검수에 먼저 보내지 않는다.
        items = [r for r in (proposal.get("items") or [])
                 if isinstance(r, dict) and r.get("slot")
                 and vton.image_host_allowed(r.get("image"))][:vton.MAX_ITEMS]
        if not items:
            return {"unavailable": "확정할 코디가 없습니다 — 먼저 propose_fit 으로 제안하세요."}
        # 사진을 실제로 본다. 실패하면 전부 '모르겠음' 이 돌아온다(vton.UNKNOWN).
        seen = vton.inspect([str(r["image"]) for r in items])
        picked = [str(k) for k in (options or []) if str(k) in vton.OPTION_LINES]
        on = ({k: True for k in picked} if picked
              else {str(k): True for k in (proposal.get("options") or [])
                    if str(k) in vton.OPTION_LINES})
        on, dropped = fit.prune_options(on, items, seen)
        # ★ 사진이 다른 칸이라고 하면 칸을 조용히 바꾸지 않는다 — 어느 칸으로 넣을지는
        #   무엇을 찾아서 고른 것인가(DB 태그)가 정한다. 다만 말은 해 준다.
        for row, look in zip(items, seen):
            if look.get("slot") not in (vton.AUTO, row.get("slot")):
                dropped.append(f"{str(row.get('name') or '')[:20]} 는 "
                               f"사진상 {look['slot']} 로 보입니다.")
        return {"ready": True,
                "items": fit.layer_order(items, seen),
                "gender": proposal.get("gender"),
                "occasion": proposal.get("occasion") or "", "ref": proposal.get("ref"),
                "options": sorted(k for k, v in on.items() if v),
                "dropped": dropped,
                "note": "화면의 착장 칸을 채웠다. 생성은 사용자가 누를 때 일어난다."}

    def t_get_salmal(self, card_id: int) -> dict:
        if self.salmal is None:
            return {"unavailable": "살!말? 데이터 연결이 아직 없습니다.",
                    "card_id": card_id}
        return self.salmal.card(int(card_id))

    def t_search_salmal(self, term: str, limit: int = 5) -> dict:
        if self.salmal is None:
            return {"unavailable": "살!말? 데이터 연결이 아직 없습니다.", "term": term}
        return self.salmal.search(term, limit=max(1, min(int(limit or 5), 10)))

    def t_get_salmal_index(self, term: str, item_name=None, brand=None,
                           price=None, style_tags=None) -> dict:
        if self.product:
            item_name = item_name or self.product.get("item_name")
            brand = brand or self.product.get("brand")
            price = price if price is not None else self.product.get("price_krw")
            image = self.product.get("image_url")
        else:
            image = None
        metric = self.t_get_metric(term, ["온도", "모멘텀"])
        temp = metric.get("온도") if isinstance(metric, dict) else None
        trend = {"temp": temp.get("temp")} if isinstance(temp, dict) else None
        card = None
        card_id = self.ctx.get("salmal_card_id")
        if card_id and self.salmal is not None:
            card = self.salmal.card(int(card_id))
        product = (card or {}).get("product") or {}
        card_tags = product.get("tags") or (card or {}).get("card", {}).get("tags") or []
        guessed = [str(t).strip() for t in (style_tags or []) if str(t).strip()][:3]
        result = salmal_index.calculate(
            term=term,
            product_tags=list(dict.fromkeys([*card_tags, *guessed])),
            taste_context=self.ctx.get("taste_context"),
            trend=trend,
            price=(card or {}).get("price_snapshot"),
            community=(card or {}).get("vote_summary"),
        )
        result.update({"term": term, "style_tags": guessed,
                       "as_of": (card or {}).get("as_of") or metric.get("as_of"),
                       "card": (card or {}).get("card"), "product": product or None,
                       "price_snapshot": (card or {}).get("price_snapshot"),
                       "vote_summary": (card or {}).get("vote_summary"),
                       "item_draft": _item_draft(item_name, brand, price, image)})
        return result

    def t_get_user_taste(self) -> dict:
        uid = self.ctx.get("user_id")
        if not uid:
            return {"logged_in": False,
                    "note": "비로그인 상태입니다. 취향을 근거로 말하지 마세요."}
        if self.taste is None:
            # ★ 화면이 보낸 취향(가입 때 고른 즐겨입는 스타일 · 최근 검색 · 찜)을 쓴다
            #   (2026-09-18). 원본은 RDS 계정 프로필이고, 브라우저가 로그인 때 받아 둔 값이다.
            #   예전에는 여기서 '연결 없음'으로 끝나 로그인한 사용자도 취향을 못 썼다.
            tc = self.ctx.get("taste_context") if isinstance(self.ctx.get("taste_context"), dict) else {}
            styles = [str(s) for s in (tc.get("favorite_styles") or []) if str(s).strip()]
            searched = [str(s) for s in (tc.get("searched_terms") or []) if str(s).strip()]
            saved = [str(s) for s in (tc.get("saved_terms") or []) if str(s).strip()]
            if not (styles or searched or saved):
                return {"logged_in": True,
                        "unavailable": "가입할 때 고른 스타일이나 검색·찜 기록이 아직 없습니다."}
            items = ([{"name": s, "why": "즐겨입는 스타일"} for s in styles[:6]]
                     + [{"name": s, "why": "찜"} for s in saved[:3]]
                     + [{"name": s, "why": "최근 검색"} for s in searched[-3:]])
            return {"logged_in": True, "source": "profile",
                    "favorite_styles": styles[:10],
                    "style_keywords": {p.get("name"): p.get("keywords") or []
                                       for p in (tc.get("favorite_style_profiles") or [])
                                       if isinstance(p, dict) and p.get("name")},
                    "saved_terms": saved[:30], "searched_terms": searched[-20:],
                    "items": items[:6]}
        return self.taste.of(uid)

    # ── 출력 디자인 스킬 ─────────────────────────────────
    # 여러 줄이 늘어서는 모듈 — 본문이 되풀이하면 같은 것을 두 번 읽게 되는 것들.
    #   (2026-09-14: "트렌드 TOP 10 알려줘" 에서 본문과 카드가 같은 10줄을 그렸다.)
    LIST_KINDS = {"ranking", "comparison", "recommendations", "associations",
                  "sources", "links", "evidence"}

    # 템플릿이 화면에 늘어놓는 목록 — 본문이 되풀이하지 않게 알려 준다.
    TEMPLATE_LISTS = {"leaderboard": "순위", "versus": "비교 지표", "orbit": "연관어",
                      "why": "근거", "ticker": "플랫폼별 온도", "verdict": "판정 근거"}

    def t_compose_report(self, title: str, accent: str, surface: str,
                         density: str, modules: Any, template: str | None = None,
                         term: str | None = None) -> dict:
        """모델의 UI 결정을 기록한다. 데이터는 여기서 만들지 않는다.

        실제 모듈 존재 여부는 agent_blocks → report_skill 이 궤적과 다시 맞춘다.
        이 도구는 안전한 디자인 어휘만 남기므로 HTML/CSS 주입 경로가 없다.
        """
        allowed = {
            "kinds": {"ranking", "comparison", "metric", "direction", "sources", "salmal",
                      "associations", "sentiment", "recommendations", "taste", "context",
                      "evidence", "links", "missing", "lifecycle", "market"},
            "presentations": {"hero", "card", "chart", "list", "editorial", "compact"},
            "emphasis": {"strong", "normal", "quiet"},
            "accents": {"coral", "ink", "violet", "blue", "lime"},
            "surfaces": {"paper", "soft", "contrast", "glass"},
            "densities": {"airy", "balanced", "compact"},
        }
        clean = []
        for raw in (modules if isinstance(modules, list) else [])[:9]:
            if not isinstance(raw, dict) or raw.get("kind") not in allowed["kinds"]:
                continue
            try:
                span = max(4, min(12, int(raw.get("span") or 6)))
            except (TypeError, ValueError):
                span = 6
            clean.append({
                "kind": raw["kind"],
                "term": (str(raw["term"]).strip() if raw.get("term") is not None else None),
                "presentation": (raw.get("presentation") if raw.get("presentation") in
                                 allowed["presentations"] else "card"),
                "span": span,
                "emphasis": (raw.get("emphasis") if raw.get("emphasis") in
                             allowed["emphasis"] else "normal"),
            })
        template = template if template in ("ticker", "verdict", "why", "versus", "leaderboard",
                                            "orbit", "canvas") else None
        spec = {
            "template": template,
            "term": (str(term).strip() or None) if term is not None else None,
            "title": str(title or "FEEDiT SIGNAL").strip()[:48],
            "accent": accent if accent in allowed["accents"] else "coral",
            "surface": surface if surface in allowed["surfaces"] else "paper",
            "density": density if density in allowed["densities"] else "balanced",
            "modules": clean,
        }
        # ★ 답을 쓰기 직전에 모델이 마지막으로 읽는 줄이다 (2026-09-14).
        #   "본문에 다시 쓰지 마라" 는 지침을 프롬프트 맨 위에만 두면, 조회를
        #   여러 바퀴 돈 뒤에는 멀어져 잊힌다. 무엇이 이미 화면에 올라갔는지를
        #   **도구가 직접 알려 준다** — 되풀이를 막는 재료를 손에 쥐여 주는 쪽이
        #   프롬프트로 부탁하는 것보다 확실하다(AGENTS.md §1-②).
        listed = sorted({m["kind"] for m in clean if m["kind"] in self.LIST_KINDS})
        if template and template != "canvas":
            listed = [self.TEMPLATE_LISTS[template]]
        note = "실제 조회 결과와 일치하는 모듈만 화면에 결합됩니다."
        if listed:
            note += (" 화면이 " + " · ".join(listed) + " 목록을 이미 보여 줍니다 — "
                     "최종 답변 본문에 같은 목록을 다시 나열하지 마세요. 맨 위 한둘만 "
                     "이름으로 짚고, 무엇을 센 것인지와 어떻게 읽어야 하는지를 쓰세요.")
        return {"ok": True, "skill": "generative-report-v2", "spec": spec, "note": note}

    # ── 밖 ──────────────────────────────────────────────
    def t_inspect_product_link(self, url: str) -> dict:
        result = product_link.inspect(url)
        if result.get("found"):
            self.product = result
        return result

    def t_web_search(self, q: str) -> dict:
        if self.websearch is None:
            return {"unavailable": "웹 검색이 꺼져 있습니다."}
        hits = self.websearch(q)
        return {"q": q, "from": "web", "not_feedit_data": True, "items": hits}

    # ── 계절·비슷한 것 ──────────────────────────────────
    def t_season_fit(self, terms: Any = None, temp_c: Any = None,
                     season: Any = None) -> dict:
        """지금 기온에 입을 만한가. **일반 기준**이지 우리 측정값이 아니다.

        ★ 판단을 모델에게 맡기지 않고 표에서 읽는다(app/season.py 머리말).
          모델이 그때그때 판단하면 대조할 원본이 없어 지어낸 숫자와 같은 자리에 선다.
        ★ 표에 없는 말은 unknown 으로 돌려준다. 비슷해 보인다고 끼워 맞추지 않는다.
        """
        names = _axis_list(terms)
        if not names:
            return {"error": "terms 가 비어 있습니다. 볼 아이템·소재 이름을 배열로 넣으십시오."}
        try:
            t = float(temp_c) if temp_c is not None else None
        except (TypeError, ValueError):
            t = None
        basis = f"{t:g}°C 기준" if t is not None else ""
        if t is None:
            t, basis = season_ref.temp_for_season(season)
        if t is None:
            return {"unavailable": "기온도 계절도 받지 못했습니다.",
                    "hint": "web_search 로 현재 기온을 확인해 temp_c 에 넣거나, "
                            "season 에 '가을' 처럼 계절을 넣어 다시 부르십시오."}
        fits, unknown = [], []
        for n in names:
            r = season_ref.fit(n, t)
            (fits.append(r) if r else unknown.append(n))
        return {
            "temp_c": t, "basis": basis, "items": fits, "unknown": unknown,
            # ★ 이 두 줄이 이 도구의 핵심이다. 빼지 마라.
            "not_feedit_data": True,
            "note": ("일반적인 착용 기준이며 FEEDiT 측정값이 아닙니다. "
                     "답변에서 그렇게 밝히십시오. "
                     + ("표에 없는 말(" + ", ".join(unknown) + ")은 판단하지 마십시오."
                        if unknown else "")),
        }

    def _pick_base(self, names: list[str]) -> tuple[str, str | None, list[dict]]:
        """후보 중 기준을 고른다. 아이템 축이 먼저다(BASE_ORDER).

        고른 이유와 함께 돌려준다 — 모델이 답변에 "무엇을 기준으로 봤는지" 를
        적을 수 있어야 한다.
        """
        seen: list[dict] = []
        for nm in names:
            key = self._key(nm)
            f = key.split(":", 1)[0] if ":" in key else None
            if f in ("", "None"):
                f = None
            seen.append({"term": nm, "facet": f})
        ranked = sorted(seen, key=lambda x: BASE_ORDER.get(x["facet"] or "", 9))
        best = ranked[0] if ranked else {"term": "", "facet": None}
        return best["term"], best["facet"], seen

    def t_similar_terms(self, terms: Any = None, term: str = "",
                        limit: int = 6) -> dict:
        """비슷한 것 = **연관어 프로필이 겹치는 것** (2026-09-10 다시 씀).

        ★ 처음에는 연관어를 그대로 "비슷한 것" 으로 내보냈다. 틀렸다.
          연관어는 **함께 언급된** 말이라 대부분 코디(보완재)다.
          실측: 반팔 티셔츠 링크에 "비슷한 것" 으로 팬츠·자켓이 나왔다.
          같이 입는 것이지 대신 입는 것이 아니다.

        ★ 대체재는 지표로 구할 수 있다. **같은 자리에 놓이는 말은 같은 것들과
          함께 언급된다.** 티셔츠와 맨투맨은 둘 다 팬츠·데님과 함께 나오고,
          팬츠는 그 둘과 함께 나오지만 팬츠의 연관어는 상의들이다.
          그래서 base 의 연관어 집합과 후보의 연관어 집합이 얼마나 겹치는지
          (자카드)로 고른다 — 1차 연관이 아니라 **2차 연관**이다.
          분류표를 새로 만들지 않고 우리 지표만으로 푸는 방법이다.

        ★ 두 목록을 **나눠서** 돌려준다.
            items — 비슷한 것 (대신 입을 만한 것)
            pairs — 함께 언급된 것 (같이 입는 것). 섞으면 이번 같은 답이 나온다.

        ★ 연관어 자료가 얇으면 같은 축 상위로 대신하되 **그렇게 밝힌다**(method).
        """
        names = _axis_list(terms, term)
        if not names:
            return {"error": "terms 가 비어 있습니다. 기준 후보를 배열로 넣으십시오."}
        n = max(1, min(int(limit or 6), 10))
        term, facet, considered = self._pick_base(names)
        key = self._key(term)

        base_rows = self.store.term_assoc(key, limit=30)
        base_set = {r.get("assoc_canonical") for r in base_rows if r.get("assoc_canonical")}
        pairs = [{"term": r.get("assoc_canonical"), "facet": r.get("assoc_facet"),
                  "co_count": r.get("co_count")}
                 for r in base_rows[:6] if r.get("assoc_canonical")]

        cands = self.store.top_terms(facet=facet, limit=CAND_MAX) if facet else []
        scored: list[dict] = []
        for r in cands:
            name = r.get("canonical")
            if not name or name == term:
                continue
            if not base_set:
                break                       # 겹칠 원본이 없다. 아래 폴백으로 간다.
            other = self.store.term_assoc(f'{r.get("facet")}:{name}', limit=30)
            other_set = {x.get("assoc_canonical") for x in other if x.get("assoc_canonical")}
            if not other_set:
                continue
            shared = base_set & other_set
            if not shared:
                continue
            score = len(shared) / len(base_set | other_set)
            scored.append({
                "term": name, "facet": r.get("facet"), "temp": r.get("temp"),
                "band": temp_band(r.get("temp")), "score": round(score, 3),
                "shared": sorted(shared)[:3],
                "why": "같은 말들과 함께 언급됨",
            })

        scored.sort(key=lambda x: (x["score"], x.get("temp") or 0), reverse=True)
        items = scored[:n]
        method = "연관어 프로필이 겹치는 정도(2차 연관)로 골랐습니다"

        # ★ 연관어가 얇으면 **이름 계열**로 채운다. 지표에도 사전에도 하위 분류가
        #   없으니 남은 근거가 이름이다(_family 머리말). 근거가 다르므로 why 도 다르다.
        if len(items) < n and facet:
            있음 = {i["term"] for i in items}
            가족 = []
            for r in self.store.top_terms(facet=facet, limit=FAMILY_POOL):
                nm = r.get("canonical")
                if not nm or nm == term or nm in 있음:
                    continue
                w = _family(term, nm)
                if w:
                    가족.append({"term": nm, "facet": r.get("facet"), "temp": r.get("temp"),
                                 "band": temp_band(r.get("temp")), "kin": w,
                                 "why": "이름이 같은 계열"})
            가족.sort(key=lambda x: (x["kin"], x.get("temp") or 0), reverse=True)
            items = items + 가족[: n - len(items)]
            if 가족:
                method = ("연관어 프로필 겹침과 **이름 계열**로 골랐습니다"
                          if scored else "**이름 계열**로 골랐습니다 (연관어 자료가 없습니다)")

        axis = FACET_SAY.get(facet or "", facet or "같은")
        alts: list[dict] = []
        if not items:
            # ★ 연관어가 없으면 **비슷한 것을 못 찾은 것이다.** (2026-09-10 실측:
            #   연관어 표 1054행 중 'item:팬츠' 는 0개, 'item:티셔츠' 는 3개다.)
            #   예전에는 축 상위를 items 에 담아 돌려줬는데, 이름이 같으니 모델이
            #   그대로 "비슷한 것" 으로 소개했다 — 팬츠 옆에 자켓·백팩이 섰다.
            #   말로 "이건 비슷한 게 아니다" 라고 덧붙이는 대신 **자리를 나눈다.**
            #   items 는 비우고 alternatives 에 담는다. 섞일 수 없는 모양으로 준다.
            for r in cands:
                name = r.get("canonical")
                if not name or name == term:
                    continue
                alts.append({"term": name, "facet": r.get("facet"), "temp": r.get("temp"),
                             "band": temp_band(r.get("temp")),
                             "why": f"{axis} 축에서 지금 높은 것"})
                if len(alts) >= n:
                    break
            # ★ 축 이름을 분명히 적는다. "같은 축" 이라고만 주면 모델이 "팬츠 축에서"
            #   로 옮겨 적는다 — 실제로 그렇게 나갔다. 우리 지표의 축은
            #   style · material · item · brand 넷뿐이고, item 안에 상의·하의·가방이
            #   전부 들어 있다. 그래서 팬츠의 '같은 축' 에 자켓·백팩이 함께 나온다.
            method = (f"'{term}' 의 연관어 자료가 없어 **비슷한 것을 찾지 못했습니다.** "
                      f"먼저 그렇게 말하십시오. alternatives 는 다른 질문의 답입니다 — "
                      f"{axis} 축에서 지금 온도가 높은 용어이고 이 축에는 다른 종류도 "
                      "섞여 있습니다. '비슷한 것' 으로 소개하지 마십시오.")

        out: dict[str, Any] = {
            "term": term, "facet": facet, "as_of": self.store.latest_day(),
            "base_note": f"'{term}' 기준. 무엇을 기준으로 봤는지 답변에 밝히십시오.",
            "method": method, "count": len(items), "items": items,
            # 비슷한 것을 못 찾았을 때만 채워진다. items 와 **다른 것**이다.
            "alternatives": alts,
            # ★ 이건 비슷한 것이 아니다. 이름과 설명을 분명히 해서 넘긴다.
            # 함께 언급된 말 = 같이 입는 것. 비슷한 것이 아니다.
            "paired_with": pairs[:4],
            "note": ("용어 단위입니다. 상품 목록·사진 없음. paired_with 를 '비슷한 것' 으로 "
                     "말하지 마십시오." if items else
                     "비슷한 것을 찾지 못했습니다. 그 사실을 먼저 말하십시오."),
        }
        if facet not in ("item", "material"):
            # ★ 스타일·브랜드 축을 기준으로 삼으면 '비슷한 상품' 이 아니라
            #   '성격이 비슷한 스타일' 이 나온다. 다른 질문의 답이다.
            out["caution"] = (
                f"'{term}' 은 아이템·소재 축이 아닙니다. 비슷한 상품이 아니라 "
                "성격이 비슷한 스타일입니다. 그렇게 밝히십시오.")
        return out

    # ── 대화 행동 ───────────────────────────────────────
    def t_ask_user(self, question: str, options: list[str]) -> dict:
        self.trace.asked = {"question": question, "options": options or []}
        return {"ok": True, "note": "되묻기를 준비했습니다. 여기서 도구 호출을 멈추세요."}

    def t_declare_missing(self, term: str = "", reason: str = "",
                          axes: Any = None, axis: Any = None) -> dict:
        """없는 축들을 **한 번에** 기록한다 (인수인계 17번).

        ★ 기록 모양은 예전 그대로 축 하나당 한 줄이다.
          trace.missing 을 읽는 곳이 셋(verify.check · agent_path._notes ·
          agent_blocks)이라, 저장 모양까지 바꾸면 파급이 셋으로 퍼진다.
          바뀐 것은 **부르는 모양**뿐이다.
        """
        names = _axis_list(axes, axis)
        if not names:
            return {"error": "axes 가 비어 있습니다. 없는 축 이름을 배열로 넣으십시오."}
        already = {(m.get("term"), m.get("axis")) for m in self.trace.missing}
        added = []
        for a in names:
            if (term, a) in already:
                continue
            self.trace.missing.append({"term": term, "axis": a, "reason": reason})
            added.append(a)
        joined = " · ".join(names)
        return {"ok": True, "axes": names, "recorded": added, "count": len(names),
                "note": f"'{joined}' 는 없는 것으로 기록했습니다. "
                        "답변에서 그 축의 값을 말하지 마세요. "
                        "없는 축이 더 있어도 이 도구를 다시 부르지 말고, "
                        "지금 한 번에 넣었어야 합니다."}


# ══════════════════════════════════════════════════════════
#  OpenAI 가 서버 쪽에서 직접 돌려 주는 도구들
# ══════════════════════════════════════════════════════════
#  우리가 실행하지 않는다. tools 목록에 넣어 두면 모델이 알아서 부르고,
#  결과는 output 안에 web_search_call · mcp_call 같은 항목으로 되돌아온다.
#  그래서 Toolbox.run() 을 거치지 않는다 — 디스패치할 것이 없다.
#
#  ★ 왜 이걸 쓰나
#    web_search 는 우리가 만든 websearch.py 보다 최신 소식에 강하고, 무엇보다
#    출처를 붙여 준다. "오늘 날씨" 같은 사전 밖 질문에서 이게 답이 된다.
#    MCP 는 우리가 코드를 짜지 않고도 바깥 도구를 붙일 수 있는 길이다.
#
#  ⚠ MCP 는 **환경변수에 적은 서버만** 붙는다.
#    require_approval 을 "never" 로 두면 사람 확인 없이 실행된다. 챗봇에는
#    승인 UI 가 없어서 "always" 로 두면 아무것도 못 부르기 때문인데,
#    그만큼 **읽기 전용 서버만** 적어야 한다. 쓰기가 되는 서버를 여기 넣으면
#    사용자 문장 하나가 그대로 실행 명령이 된다.
#    allowed_tools 로 부를 수 있는 것을 좁혀 두는 편이 안전하다.

def _mcp_servers() -> list[dict]:
    """FEEDIT_MCP_SERVERS — JSON 배열. 없으면 MCP 를 아예 안 붙인다.

        FEEDIT_MCP_SERVERS='[{"label":"musinsa","url":"https://.../mcp",
                              "description":"무신사 상품 조회",
                              "allowed_tools":["search_product"]}]'
    """
    raw = (os.getenv("FEEDIT_MCP_SERVERS") or "").strip()
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        # 오타 하나로 챗봇이 통째로 죽지 않게 한다. MCP 만 빠진다.
        return []
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict) or not it.get("url"):
            continue
        spec: dict[str, Any] = {
            "type": "mcp",
            "server_label": str(it.get("label") or "mcp"),
            "server_url": str(it["url"]),
            "server_description": str(it.get("description") or ""),
            # 승인 UI 가 없다. 대신 환경변수에 적은 것만 붙는다는 게 승인이다.
            "require_approval": str(it.get("require_approval") or "never"),
        }
        if it.get("allowed_tools"):
            spec["allowed_tools"] = list(it["allowed_tools"])
        if it.get("authorization"):
            spec["authorization"] = str(it["authorization"])
        out.append(spec)
    return out


def hosted_specs() -> list[dict]:
    """모델이 서버 쪽에서 직접 쓰는 도구들."""
    out: list[dict] = []
    if (os.getenv("FEEDIT_TOOL_WEB_SEARCH") or "1").strip() not in ("0", "false", "no"):
        out.append({"type": "web_search"})
    out.extend(_mcp_servers())
    return out


def _item_draft(name, brand, price, image=None) -> dict | None:
    """모델이 확인한 상품의 정체를 그대로 적어 둔다. 값을 만들지 않는다.

    ★ 왜 지수 도구에 붙였나 (2026-09-11)
      링크를 주면 챗봇은 이미 "아디다스 럭비 폴로 셔츠" 라고 부르며 답한다.
      그런데 그 이름은 **답변 문장 안에만** 있어서, '물어보기' 로 넘어갈 때
      화면은 사용자가 친 원문(링크)을 그대로 상품명 칸에 넣었다.
      답변에서 정규식으로 뽑는 고침은 다음 질문에서 또 틀린다.
      그렇다고 전용 도구를 따로 만들면 **바퀴를 하나 더 쓴다** — 실제로
      그렇게 했다가 14초 예산이 모자라 compose_report 까지 못 가고 리포트
      카드가 통째로 사라졌다(AGENTS.md §3: 스펙이 한 번에 받게 고친다).
      살말 모드에서 어차피 반드시 부르는 이 도구가 같이 받는다.
    """
    def _text(v, limit):
        t = str(v or "").replace("\n", " ").strip()
        return t[:limit] or None

    won = None
    if price is not None:
        digits = re.sub(r"[^0-9]", "", str(price))
        if digits:
            won = int(digits[:9])
    img = _text(image, 2000)
    if img and not img.startswith("https://"):
        img = None
    draft = {"name": _text(name, 120), "brand": _text(brand, 60), "price": won, "image": img}
    filled = [k for k, v in draft.items() if v is not None]
    if not filled:
        return None
    draft["recorded"] = filled
    return draft


def specs_for(ctx: dict | None = None) -> list[dict]:
    """컨텍스트에 맞는 도구만 준다.

    ★ 모드로 라우팅하지 않는다(설계도 03·L1).
      살!말? 카드에서 넘어왔으면 살말 도구가 목록에 있고, 아니면 없다.
      일반/살말을 정규식으로 가르던 is_salmal_question() 이 하던 일을
      **도구 목록의 유무**가 대신한다.
    """
    ctx = ctx or {}
    drop = set()
    if not ctx.get("salmal_card_id"):
        drop.add("get_salmal")
    if ctx.get("mode") != "salmal":
        drop.add("get_salmal_index")
        # ★ VTON 은 살!말? 의 고유 기능이다 (2026-09-22). 일반 모드가 할 수 있는
        #   일은 propose_fit — 제안까지다. 프롬프트로 "입히지 마라" 라고 적는 것과
        #   다르다: 목록에 없으면 모델이 어떻게 우겨도 부를 수 없다.
        drop.add("build_fit")
    if not ctx.get("fit_proposal"):
        # 승인을 거치지 않은 턴에는 확정할 코디가 없다. get_salmal 이 카드에서
        # 넘어왔을 때만 목록에 있는 것과 같은 방식이다.
        drop.add("build_fit")
    else:
        # ★ 승인 버튼이 보낸 턴이다 (2026-10-01). 할 일은 입혀보기 하나 — 살말 지수
        #   (규칙 13 "반드시")와 되묻기는 이 턴의 답이 아니다. 실측: 승인한 아메카지
        #   코디를 받고도 "어떤 코디를 입혀볼까요?" 를 되물었다. 목록이 지킨다.
        drop.add("get_salmal_index")
        drop.add("ask_user")
    if not ctx.get("user_id"):
        drop.add("get_user_taste")
    if ctx.get("no_ask"):
        # 되묻기 예산 소진 (orchestrator.ASK_BUDGET). 목록에 없으면 못 부른다 —
        # 프롬프트로 부탁하는 것과 달리 이건 지켜진다.
        drop.add("ask_user")
    hosted = hosted_specs()
    # ★ 이름이 겹치면 안 된다.
    #   우리 함수 web_search 와 내장 도구 {"type":"web_search"} 가 같은 이름이라,
    #   둘 다 넣으면 모델이 어느 쪽을 부를지 모르고 API 도 거부한다.
    #   내장 쪽이 낫다 — 출처를 붙여 주고 최신 소식에 강하다. 우리 것은
    #   내장을 껐을 때(FEEDIT_TOOL_WEB_SEARCH=0)만 남긴다.
    if any(h.get("type") == "web_search" for h in hosted):
        drop.add("web_search")
    ours = [s for s in SPECS if s["name"] not in drop]
    # 우리 함수 + OpenAI 가 직접 돌리는 것. 모델에게는 구분 없이 한 목록이다.
    return ours + hosted
