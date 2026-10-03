"""L1 오케스트레이터 — 도구를 고르고, 결과를 보고 다시 고른다.

── 이 파일이 대체하는 것 ────────────────────────────────────
`intents.py` 의 정규식 14개와 `templates.py` 의 의도→블록 고정 매핑.

예전에는 질문이 들어오면 정규식으로 의도를 **확정**하고, 그 의도에 붙은
블록 목록을 그렸다. 근거를 보기 전에 되돌릴 수 없는 결정을 하는 셈이라
세 곳에서 깨졌다:

  ① 축이 여러 개인 질문
     "살로몬 XT-6 지금 사도 돼?" 는 할인률·수명주기·리세일 셋 다인데
     하나를 고르는 순간 나머지 근거가 사라진다.
  ② 지시대명사
     "이거 어때?" 를 분류하려면 "이거" 가 뭔지 알아야 하고, 그건 분류
     이후에나 확정된다. 순서가 뒤집혀 있다.
  ③ 용어가 없는 질문
     "요즘 뭐가 핫해?" 는 사전에 걸리는 말이 없다고 범용으로 흘러갔다.
     답이 용어인 질문인데 우리 데이터를 안 보고 지어냈다.

여기서는 의도 코드를 만들지 않는다. **다음에 부를 도구**만 정하고,
결과를 받아 다시 정한다. 위 셋이 전부 이 한 가지로 풀린다.

── 일반 / 살!말? 를 가르지 않는다 ───────────────────────────
`is_salmal_question()` 정규식이 하던 일은 이제 **도구 목록의 유무**가 한다.
살말 카드에서 넘어왔으면 tools 에 get_salmal 이 있고, 아니면 없다.
모드는 라우팅 대상이 아니라 컨텍스트다(설계도 03).

── 안전장치 (설계도 08) ─────────────────────────────────────
도구를 자유롭게 부르게 두면 비용과 지연이 열려 있게 된다. 네 개를 건다:
  · 최대 바퀴 수          빈 결과를 주면 같은 것을 계속 다시 부른다
  · 같은 인자 재호출 금지  같은 인자로 두 번 부르는 건 언제나 버그다
  · 전체 시간 예산        SSE 가 시작을 못 하면 멈춘 줄 안다
                          ★ 이 예산은 **이 루프만의 것이 아니다**(18번).
                            agent_path 가 마감시각을 정해 넘기고, 루프와
                            _finish · verify 가 그 하나를 나눠 쓴다.
  · 도구 결과 원본 보관   verify.py 가 대조할 것이 없으면 검증이 도장이 된다
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from . import llm
from .tools import Toolbox, progress_say, specs_for

# ── 안전장치 값 ────────────────────────────────────────────
MAX_ROUNDS = 6          # 한 질문에 도구를 부를 수 있는 바퀴 수
# ★ 2026-09-18 — 4 → 5. 살말 질문은 검색 → 지표 → 지수 → 결측 기록 → 리포트로
#   바퀴를 딱 맞게 쓰는 일이 흔해서, 도구 하나만 더 부르면 **시간은 남았는데**
#   답을 못 쓰고 끝났다(실측: 예산 33초 중 21초 사용, 링크 질문 5바퀴 전부 사용).
#   진짜 상한은 시간 예산(TIME_BUDGET)이고, 바퀴는 무한 반복을 막는 안전장치다.
#   그리고 마지막 바퀴는 **답 쓰기 전용**으로 돌린다(run() 참고) — 바퀴가 바닥나도
#   답 없이 끝나지 않는다.
# ★ 링크 질문은 바퀴가 하나 더 든다 (2026-09-11 실측, 예산과 같은 이유).
#   `33058ms/33000ms stopped=max_rounds 바퀴=4(5328+12387+4624+3006ms)`
#   ① 링크 확인 ② 지표·지수 ③ 결측 기록 ④ compose_report — 네 바퀴를 다 쓰고
#   **답을 쓰는 다섯 번째 바퀴가 없었다.** 예산은 남았는데 바퀴가 모자란 것이다.
LINK_EXTRA_ROUNDS = 1
# ★ 2026-09-22 — 5 → 6. 코디 인계가 바퀴를 둘 쓴다(propose_fit → 승인 → build_fit).
#   propose_fit 이 도는 턴은 취향·트렌드 조회 → 코디 → compose_report → 답 쓰기다.
#   바퀴를 먼저 늘리지 않으면 "시간은 남았는데 답을 못 쓴다" 로 끝난다.
MAX_CALLS = 18          # 바퀴를 합쳐 도구 호출 총량 (2026-09-22: 바퀴 6·7 에 맞춰 14 → 18)
# ★ 2026-09-09 추가 — 같은 도구를 인자만 바꿔 계속 부르는 것을 막는다.
#   _sig() 는 **동일 인자**만 걸러서, search_terms("살로몬 XT-6") →
#   ("XT-6") → ("살로몬") 처럼 조금씩 바꾸면 그대로 통과했다.
#   실측(2026-09-09 "살로몬 XT-6 지금 사도 돼?"): search_terms 4연속, 8.9초.
#   결론은 옳았지만 네 바퀴를 다 쓰고 도달했다.
MAX_PER_TOOL = 3        # 한 질문에 같은 도구를 부를 수 있는 횟수
# ★ ask_user 만 예외다. 부르는 순간 루프가 끝나므로 셀 이유가 없다.
#   declare_missing 은 예외가 아니다 — 처음엔 "종결 도구" 로 보고 뺐는데,
#   스펙이 axis 를 **하나씩** 받는 기록 도구라 없는 축마다 한 번씩 불렸다.
#   실측(2026-09-09 "살로몬 XT-6 …"): search_terms 1 + get_metric 1 +
#   declare_missing 3 = 5호출 · 4바퀴 · 25초. 상한이 없어 막을 것이 없었다.
#   ★ 2026-09-10 — 스펙을 axes(배열)로 바꿔 **원인 쪽**을 고쳤다(17번).
#     이제 없는 축이 몇 개든 한 번이면 된다. 상한은 그대로 둔다 —
#     고친 것은 스펙이고, 상한은 모델이 그래도 반복할 때의 뒷문이다.
NO_CAP = ("ask_user",)
# ── 되묻기 예산 (2026-09-10, 인수인계 15번) ────────────────
# ★ 되묻기는 실패가 아니다. 다만 **대화마다** 되물으면 답을 못 하는 챗봇이 된다.
#   지금까지 상한은 프롬프트 규칙 3(직전 턴에 되물었으면 또 묻지 마라)뿐이었다 —
#   지키는지는 모델에 달려 있었고, 코드에는 막을 것이 없었다.
#   이제 예산을 다 쓰면 **도구 목록에서 ask_user 를 뺀다.** 부를 수 없으면 못 부른다.
#   설계도 03 의 "모드는 라우팅 대상이 아니라 도구 목록" 과 같은 방식이다.
#   대신 빈손으로 두지 않는다 — 기본값으로 답하고 무엇을 가정했는지 밝히게 한다
#   (_ctx_block 의 [되묻기 예산 소진] 줄).
ASK_BUDGET = 1          # 한 대화에서 되물을 수 있는 횟수
# ★ 예산은 환경변수로 뺀다 (FEEDIT_CHAT_TIME_BUDGET).
#   실측(2026-09-09, 전 역할 luna): 8초로는 "살로몬 XT-6 …" 과 "오버핏 니트 …"
#   가 마지막 답변 작성 중에 끊겼다(llm_NET_ReadTimeout). 모델을 바꾸거나
#   예산을 올리는 판단이 필요한데, 그때마다 코드를 고치게 하지 않는다.
# ★ 2026-09-10 (인수인계 18번) — 예산의 **뜻**이 바뀌었다.
#   예전에는 이 루프만 덮었다. 루프가 예산을 다 쓰고 나면 _finish 가 도구 없이
#   한 번 더 부르고(CALL_TIMEOUT 20초), 그 뒤 verify.fix 가 또 부른다(15초).
#   둘 다 예산 밖이라 "예산 14초인데 25초" 가 나왔다. 예산이 예산이 아니었다.
#   이제 TIME_BUDGET 은 **답변 하나의 전체 벽시계**다.
#   기본값을 8 → 17 로 올린 것은 뜻이 바뀌었기 때문이지 느슨해진 것이 아니다:
#   루프 8 + _finish 5 + verify 4 = 예전에 **실제로 쓰던** 시간에 상한을 씌운 것.
# ★ 2026-09-18 — 17 → 45초. Terra 로 올린 뒤 한 바퀴가 2~7초라, 살말 질문(검색 → 지표 →
#   지수 → 리포트)이 17~25초 안에서 자꾸 "조회를 끝까지 하지 못했다" 로 끝났다.
#   답이 빨리 끝나면 그만큼만 쓴다 — 상한은 모델이 멈췄을 때 무한 대기를 막는 용도다.
#   버셀 중계 함수 한도(api/v1/[name].js maxDuration)보다 넉넉히 작아야 한다.
TIME_BUDGET = float(os.getenv("FEEDIT_CHAT_TIME_BUDGET") or 45.0)
# 뒷단계 몫. 루프가 예산을 다 써 버리면 답을 쓸 시간이 남지 않는다.
# ★ 2026-09-10 실측으로 값을 낮췄다. 처음엔 _finish 5 + verify 4 = 9초를 뗐는데,
#   예산 14초에서 루프가 7초밖에 못 써서 "살로몬 XT-6 …"(10.1초)와
#   "오버핏 니트 …"(10.6초)가 루프 안에서 답을 못 만들고 안내문으로 끝났다.
#   예산은 지켰지만 답이 나빠졌다 — 뒷정리 자리를 비워 두느라 본 작업을 굶긴 것이다.
#   · verify.fix 는 **의심이 잡혔을 때만** 모델을 부른다. 실측 4문항 모두 의심 0 이라
#     매번 4초를 떼 두는 것은 거의 항상 버리는 시간이었다.
#   · _finish 는 루프가 실패했을 때만 부른다. 그 자리를 넉넉히 비워 둘수록
#     루프가 실패할 확률이 올라간다 — 비워 둔 만큼 실패를 부르는 셈이다.
#   그래서 뒷몫은 바닥값 하나로 줄이고, 두 단계는 남은 시간 안에서 쓸 수 있는
#   만큼만 쓴다. 못 쓰면 STOP_SAY · _hedge 가 받는다(모델을 안 부른다).
#   ★ 2026-09-10 오후 — 3.5 로는 이번엔 **반대편**이 굶었다.
#     예산 17초에서 루프가 13.5초를 쓰고 나면 뒷정리에 3.5초가 남는데, 거기서
#     verify 몫을 떼면 _finish 에 1.75초뿐이라 MIN_CALL(2.5)에 못 미쳐 **아예
#     안 불린다.** 실측: "아디다스 트랙탑" 링크 질문에서 도구 조회는 전부
#     성공해 카드가 다 그려졌는데 본문만 안내문이었다. 문장 쓸 시간이 구조적으로
#     없었던 것이다.
#     그래서 6.0 으로 올린다 — 예산 17이면 루프 11 · 마무리 4 · 검증 2 다.
#     루프 11초는 9월 9일 실측에서 루프가 실제로 쓴 최대(11.0초)와 같다.
#   ★ 이 값을 만질 때는 **양쪽 실패를 같이 본다.** 너무 크면 루프가 답을 못
#     만들고(9→7초 사건), 너무 작으면 답을 못 쓴다(3.5초 사건). 둘 다 겪었다.
#   ★ 2026-09-10 저녁 — 실측으로 **답 쓰는 데 드는 시간**을 처음 쟀다.
#     `바퀴=3(4751+3657+5563ms) 웹검색=1 호출=3`
#     1바퀴 4.8초(웹검색 포함) + 2바퀴 3.7초로 조회를 끝냈고, 3바퀴째가 답을
#     쓰는 호출이었는데 5.6초에 잘렸다. 그 뒤 _finish 도 4.0초를 받아 또 잘렸다.
#     **한 번도 충분히 못 받고 두 번 실패한 것이다.**
#     그래서 뒷몫을 8초로 올린다 — 예산 20이면 루프 12 · 마무리 6 · 검증 2.
TAIL_RESERVE = 8.0      # 루프는 마감시각보다 이만큼 먼저 멈춘다
VERIFY_RESERVE = 2.0    # 그 8초 안에서 verify.fix 몫 (나머지 6초가 _finish)
# ★ 새 바퀴를 시작할 최소 시간. 이보다 적게 남았으면 **시작하지 않는다.**
#   예전 문턱은 1초였다. 그러면 5.6초 남았을 때 새 바퀴를 시작하고, 그 바퀴가
#   답을 쓰는 호출이면 5.6초 안에 못 끝내 통째로 버려진다. 버린 뒤 _finish 로
#   내려가는데 거기도 시간이 줄어 있다. 못 끝낼 호출을 시작하는 대신,
#   그 시간을 마무리에 몰아 준다.
#   ★ 2026-09-10 밤 실측으로 4.0 → 6.5. 답 쓰는 호출이 5.8초에 잘리고 그 뒤
#     _finish 도 6초에 잘렸다(바퀴=3(4173+2085+5756ms) · 총 18.1초).
#     **답 쓰기는 6초로도 모자란다.** 5.7초 남았을 때 시작하면 잘리는 쪽에 가깝고,
#     잘리면 그 시간이 통째로 버려진 뒤 마무리 몫까지 줄어든다. 차라리 시작하지
#     않고 그 시간을 마무리에 얹는다 — 같은 예산에서 한 번을 제대로 쓴다.
WRITE_MIN = 6.5
# ★ 링크 질문은 **바퀴가 하나 더 든다** (2026-09-11 실측).
#   `18574ms stopped=time_budget 바퀴=3(5563+6871ms) 웹검색=2 호출=5`
#   ① 링크가 무엇인지 확인(호스티드 web_search) 5.6초
#   ② 확인한 용어로 지표·지수 조회 6.9초
#   ③ 답을 쓰고 compose_report — **여기까지 오지 못했다.**
#   ①은 링크 질문에만 있는 비용이고, 그 탓에 ③이 예산 밖으로 밀린다.
#   질문마다 다른 일을 시키면서 같은 시계를 주면, 링크 질문은 구조적으로
#   답을 못 쓴다. 그 한 바퀴만큼을 더 준다.
LINK_EXTRA = float(os.getenv("FEEDIT_CHAT_LINK_EXTRA") or 15.0)
# ── 코디 예산 (2026-09-22) ─────────────────────────────────
#   ★ 링크와 같은 이유로 시간을 더 주지만, **판단하는 자리가 다르다.**
#     링크는 질문에 주소가 있으니 시작 전에 안다(budget_for). 코디는 모델이
#     propose_fit 을 부르기로 정하는 순간에 비로소 정해진다 — 그래서 질문이 아니라
#     **도구가 불린 사실**로 한 번만 늘린다("조회가 끝났으면 뒷몫에서 빌린다" 와
#     같은 자리). 먼저 재고 늘린다(AGENTS.md §4): 조회를 병렬로 부르면
#     (fit.propose) 한 바퀴가 4~5초이므로, 한 바퀴 값만 더한다.
FIT_EXTRA = float(os.getenv("FEEDIT_CHAT_FIT_EXTRA") or 10.0)
FIT_TOOLS = ("propose_fit", "build_fit")
# ── 요즘 코디 찾기 예산 (2026-10-02) ─────────────────────────
#   find_looks 는 웹 검색이라 한 번에 10~20초가 든다(캐시면 즉시). 코디와 같은 방식으로,
#   **불린 사실**이 확인됐을 때 한 번만 늘린다. 안 늘리면 룩을 찾아 놓고 코디를 못 짠다.
LOOK_EXTRA = float(os.getenv("FEEDIT_CHAT_LOOK_EXTRA") or 20.0)
_URL = re.compile(r"https?://|\bwww\.[^\s]+", re.I)
CALL_TIMEOUT = 30       # 한 번의 모델 호출 상한 (2026-09-18: 20 → 30, Terra·웹검색 여유)
MIN_CALL = 2.5          # 이보다 적게 남으면 부르지 않는다 — 못 끝낼 호출은 기다림만 늘린다
FINISH_MAX_TOKENS = 700 # 마무리 답변 길이 상한. 안 묶으면 쓰다가 끊긴다


def _is_link_question(question: str) -> bool:
    return bool(_URL.search(str(question or "")))


def budget_for(question: str) -> float:
    """이 질문 하나에 줄 전체 벽시계. 링크가 있으면 확인 바퀴만큼 더 준다."""
    return TIME_BUDGET + (LINK_EXTRA if _is_link_question(question) else 0.0)


def rounds_for(question: str) -> int:
    """이 질문에 허용할 바퀴 수. 링크 확인에 한 바퀴를 먼저 쓰기 때문이다."""
    return MAX_ROUNDS + (LINK_EXTRA_ROUNDS if _is_link_question(question) else 0)


def reserve(left: float, want: float) -> float:
    """남은 시간에서 뒷단계 몫을 뗀다.

    ★ 예산이 작으면 몫도 줄인다. 8초 예산에서 9초를 떼면 루프가 시작도 못 하고
      끝난다. 절반까지만 뗀다 — 앞뒤 중 한쪽이 굶는 일이 없어야 한다.
    """
    return max(0.0, min(want, left * 0.5))


INSTRUCTIONS = """너는 FEEDiT 의 패션 트렌드 분석 상담원이다.
FEEDiT 는 SNS·커머스를 수집해 용어별 트렌드 지표를 계산하는 서비스다.

## 어떻게 답을 만드나
질문을 분류하지 마라. 무엇을 더 알아야 답할 수 있는지만 판단하고 도구를 불러라.
결과를 보고 방향을 바꿔도 된다. 도구는 한 번에 여러 개를 불러도 되고,
한 바퀴로 끝나지 않아도 된다.

## 반드시 지킬 것
1. **도구가 준 값만 말한다.** 지표·숫자·용어를 기억이나 추측으로 만들지 마라.
   FEEDiT 는 측정한 것만 말하는 서비스다. 지어낸 숫자 하나가 나머지 전부의
   신뢰를 무너뜨린다.
2. **없으면 없다고 한다.** 그 축의 자료가 없으면 declare_missing 을 부르고,
   답변에서 "아직 측정 자료가 없습니다" 라고 밝혀라. 대충 메우지 마라.
   ★ 없는 축이 여럿이면 axes 에 **한 번에 모두** 넣어 한 번만 불러라.
     축마다 따로 부르면 도구 상한에 걸려 뒤쪽 축이 기록되지 않는다.
3. **모르면 되묻는다.** "이거 어때?" 처럼 무엇을 묻는지 알 수 없으면
   추측하지 말고 ask_user 를 불러라. 그건 실패가 아니다.
   ★ 단, **우리가 할 수 없는 일에는 되묻지 마라.** 주문·결제·장바구니 담기·
     개인정보 입력은 FEEDiT 챗봇이 하지 않는다("이거 대신 주문해 줘",
     "결제해 줘", "장바구니에 넣어 줘"). 어떤 상품인지 되물으면 사용자는
     고르기만 하면 해 준다는 뜻으로 읽는다 — 실제로 그렇게 읽혔다.
     되묻지 말고 **첫 문장에서 못 한다고 말한 뒤**, 대신 살지 말지 판단은
     도울 수 있다고 한 줄로 덧붙여라. 도구를 부르지 마라.
   다만 **되묻기는 한 대화에 한 번뿐이다.** 두 번 되묻는 챗봇은 답을 못 하는
   챗봇이다. 예산을 다 쓰면 ask_user 가 도구 목록에서 아예 빠진다 —
   그때는 가장 그럴듯한 것으로 잡아 답하고, 무엇을 가정했는지 한 줄로 밝힌 뒤
   "아니면 말씀해 주세요" 를 붙여라. [최근 본 용어] 가 주어지면 거기서 골라라.
4. **요청보다 적게 나오면 그대로 말한다.** rank_terms 가 short_of_asked=true 를
   주면 나머지를 채우지 말고 몇 개뿐인지 밝혀라.
   ★ 순위의 구간·개수는 rank_terms 가 준 값으로만 말한다. 항목마다 `band`(화면 막대
     구간)가 있고, "상위 몇 개가 같은 구간인지" 는 `top_streak`, 구간별 개수는
     `band_counts` 에 있다. 항목을 세어 개수를 새로 만들지 마라 — 도구에 없는 숫자는
     검증에서 지워지고, 지워진 자리가 "상위 개는" 처럼 깨진 문장으로 남는다
     (2026-10-01 실측). 계절·용도처럼 도구가 주지 않은 성격도 붙이지 마라.
5. **may_say 를 지킨다.** get_metric 의 may_say 에서 false 인 축은 관측이
   모자라 말할 수 없는 것이다. 그 값을 근거로 삼지 마라.
6. **링크를 지어내지 않는다.** 근거를 인용할 때 주소는 get_evidence 가 준 url
   그대로만 쓴다. url 이 비어 있으면 플랫폼과 시점만 밝히고 끝에 "(원문 링크 없음)"
   이라고 적어라. 검색 결과 주소나 그럴듯한 주소를 만들어 붙이면, 누른 사람은
   우리가 인용하지 않은 글에 도착한다. 지어낸 숫자와 같은 종류의 거짓말이다.
7. **말할_수_있는_것을 지킨다.** get_metric 이 그 조건에서 허용되는 표현을
   함께 준다. `recommend` 가 "금지" 면 **사도 된다/괜찮다 같은 권유를 하지 마라.**
   사실만 적는다. "조건부" 면 note 에 적힌 단서를 반드시 함께 쓴다.
   숫자가 전부 맞아도 결론이 틀릴 수 있고, 구매를 권하는 문장에는 책임이 따른다.
8. **숫자에는 기준선을 붙인다.** "온도 71°" 만 쓰면 높은 건지 낮은 건지 모른다.
   rank_text · delta_1w · sample_n 이 있으면 함께 적어라 —
   "온도 71°(그날 언급된 전체 용어 중 상위 12%, 9월 22일 78°에서 내려오는 중)".
   ★ get_metric 의 값은 **트렌드 분석 화면과 같다.** 판정도 화면의 말로 한다 —
     온도는 `온도.verdict`("뜨거움 구간"), 긍부정은 `긍부정.verdict`("강한 구매 신호",
     "판단 보류")를 그대로 쓰고, 다른 판정을 새로 만들지 마라.
     언급량·반응 수는 하루치가 아니라 **최근 7일·28일 합계**다. 그렇게 적어라.
     `주의` 가 있으면(마지막 집계일이 기준일보다 이르거나, 옛 집계 방식의 온도) 한 줄로 밝혀라.
9. **가격·할인·리셀 시세는 get_market 으로만 말한다.** (2026-09-20 무신사·지그재그·에이블리
   할인, 무신사 유즈드·크림 리셀 연결) 결과에 있는 숫자와 기준일·판매처만 쓰고,
   unavailable 이면 "그 조건의 가격 기록은 아직 없다" 고 말한다. 개별 상품의 지금 재고·
   쿠폰가는 우리가 모른다 — 필요하면 판매처에서 확인하라고 덧붙인다.
   "살까 말까" 를 묻는 질문에서 가격 축을 못 봤으면 **유행 관점의 판단**이라는 것을 한 번은 밝혀라.
10. **한국 서비스다.** 사용자는 한국에 있고, 값도 한국 기준으로 읽는다.
   지역이 필요한 질문에 [사용자 지역] 이 주어지면 그대로 쓰고, 없으면
   **서울**을 기본으로 잡아 답한 뒤 "다른 지역이면 말씀해 주세요" 를 덧붙여라.
   되묻더라도 선택지는 **한국 도시**로 낸다.
   ★ 직전 대화에서 사용자가 지역을 말했으면(`[직전 질문]`·`[직전 답변 요약]`)
     **그 지역을 이어서 쓴다.** 매번 다시 묻지 마라. 한 번 말한 것을 또 묻는
     챗봇은 기억이 없는 것처럼 보인다.
   ★ 미국 도시를 기본 선택지로 내지 마라.
     (2026-09-09 실측: "오늘 날씨 어때?" 에 뉴욕·로스앤젤레스·시카고가 나왔다.
      한국 패션 서비스에서 이 선택지는 사용자를 당황하게 한다.)

11. **이어 갈 질문은 맨 마지막 줄에 `[다음]` 으로 쓴다.** 본문 안에서 다음 질문을
   던지지 마라. 화면이 그 줄을 리포트 **아래**로 옮겨 붙인다. 본문에 섞여 있으면
   사용자는 근거를 보기 전에 질문부터 받는다.
   형식: `[다음] (이번에 조회한 용어 한두 개)을 더 자세히 볼까요?` — 한 줄, 한 질문.
   ★ `[다음]` 에는 **이번 질문에서 도구로 조회한 것만** 건다. `[최근 본 용어]` ·
     `[직전 질문]` 에 있던 지난 주제를 끌어오지 마라. 사용자가 새 질문으로 넘어왔는데
     지난 주제를 내밀면 질문을 잘못 알아들은 것처럼 보인다.
     (2026-10-01 실측: "핫한 아이템 순위는?" 답 끝에 "플리스재킷과 트랙탑 중 …" —
      트랙탑은 순위에 없었고 세 턴 전 주제였다. 이런 줄은 화면에서 빠진다.)
   ★ 사용자가 짧게 대답하면(응 · 좋아 · 둘 다 · 첫 번째 거) `[직전 답변이 물은 것]` 에
     대한 대답이다. 그 질문이 내민 것을 그대로 실행하라 — "둘 다" 면 거기 적힌 두 가지를
     모두, 같은 대상으로. [직전 질문] 목록에서 '두 개' 를 새로 짐작하지 마라.
     (2026-10-01 실측: "더비슈즈의 출처별 반응이나 실제 언급 근거를 볼까요?" → "응 두개 다"
      에 아이템 순위 · 소재 순위를 다시 보여 줬다.)
   물을 것이 없으면 안 써도 된다.

12. **답만 읽는 편이 나은지, 리포트로 보는 편이 나은지 먼저 판단한다.**
   compose_report 는 데이터를 조회했다는 표시가 아니라, 그림이 읽기를 실제로 돕는
   답에서만 쓰는 UI 스킬이다.
   - **문장만 답한다:** 인사·잡담·거절·되묻기, 용어 뜻, 사진의 소재·색·길이 같은
     후속 설명, 한 용어의 한 가지 사실("온도 몇 도야?"), 간단한 코디·상담처럼
     1~3문장으로 충분한 답.
   - **리포트로 답한다 — 질문 유형마다 template 이 정해져 있다 (2026-10-02):**
     · ticker — 한 용어의 흐름을 묻는 진단. "OO 요즘 어때?" "뜨고 있어?" "식었어?"
       "아직 유행이야?". get_metric(온도·모멘텀, 가능하면 출처별·연관어).
     · verdict — 살말 판정. "OO 살까 말까?" "지금 사도 될까?" "이 가격 괜찮아?".
       get_salmal_index. "아직 유행이야/끝물이야" 가 섞이면 get_market(lifecycle),
       가격·할인·리셀을 물으면 get_market(discount·resale) 도 함께.
     · why — 원인. "OO 왜 떴어?" "어디서 뜬 거야?" "갑자기 왜 많이 보여?".
       get_metric(온도·긍부정) + get_evidence.
     · versus — 정확히 두 대상. "A vs B" "A랑 B 중 뭐가 더 떠?". 두 용어 get_metric.
       셋 이상이면 canvas(comparison).
     · leaderboard — 순위. "TOP 10" "요즘 뭐가 떠?" "아이템 순위". rank_terms.
     · orbit — 연관. "OO랑 같이 뜨는 거?" "OO엔 뭐랑 입어?". get_metric(연관어).
     · canvas — 위에 맞지 않는 섞인 결과(취향·상황 적합도·추천 탐색·셋 이상 비교).
       이때만 modules 를 직접 배치한다.
     템플릿을 골랐으면 modules 는 빈 배열, term 에는 주인공 용어를 적는다.
     관측이 얇은 용어는 서버가 '관측 부족' 카드로 바꾼다 — 얇다고 리포트를 피하지 마라.
   - 애매하면 먼저 자연스러운 대화 문장으로 답한다. 카드는 장식이 아니다.
   리포트가 필요한 경우 조회를 모두 마친 뒤 최종 문장을 쓰기 직전에
   compose_report 를 정확히 한 번 부른다.
   - 이미 받은 도구 결과에 있는 것만 그린다. 그 템플릿에 필요한 결과가 없으면 서버가
     결과에 맞는 그림으로 바꾼다 — 없는 지표를 화면에 만들지 마라.
   - canvas 를 쓸 때는 가장 중요한 결과를 hero/strong/넓은 span, 보조 근거는
     editorial 또는 compact 로 두고 **결론 → 핵심 신호 → 근거** 순으로 읽히게 한다.
     rank·table 은 hero/card/list, KPI 는 hero/card 를 쓴다.
   - 제목은 `FEEDiT SIGNAL` 같은 범용 문구 대신 질문의 대상과 결과가 드러나는 짧은
     한국어로 쓴다. 수치는 제목에 넣지 않는다. why 템플릿의 제목은 잡지 헤드라인처럼
     크게 실린다 — 근거에서 확인된 계기만 쓴다.
   - HTML·CSS·수치·상품명은 만들지 않는다. 데이터는 서버가 실제 결과와 결합한다.
   - compose_report 를 부른 뒤에는 다른 도구를 부르지 말고 바로 답을 쓴다.
   - 구조화 지표 결과가 전혀 없거나 ask_user 로 되묻는 경우에는 부르지 않는다.
   - **declare_missing 이 필요하면 compose_report 와 같은 바퀴에서 함께 불러라.**
     둘 다 조회가 끝난 뒤의 기록·구성이다. 따로 나누면 바퀴를 하나 더 쓰고,
     그만큼 답을 쓰는 바퀴가 밀린다(2026-09-11 실측: 네 바퀴를 다 쓰고도
     답을 못 썼다).

13. **살말 모드에서는 get_salmal_index를 반드시 부른다.** 지수·살/말/보류 결론은
    이 도구 결과만 사용한다. recommendation_allowed=false이면 억지로 살/말을 고르지
    말고 보류 또는 판단 자료 부족이라고 말한다. 커뮤니티 투표는 참고 신호일 뿐이다.
    ★ 링크나 사진으로 무슨 브랜드의 무슨 옷인지 확인했다면 그 상품명·브랜드·가격을
    **같은 호출의 item_name·brand·price 에 함께 적는다.** 화면의 '물어보기' 버튼이
    그 값으로 커뮤니티 카드를 채운다 — 적지 않으면 사용자가 친 원문(링크 주소)이
    상품명 칸에 그대로 들어간다. 확인하지 못한 칸은 null 로 둔다.
    이 때문에 도구를 한 번 더 부르지 마라. 바퀴가 모자라면 리포트가 통째로 사라진다.
    ★ 예외 — `[승인된 코디]` 가 있는 턴은 입혀보기다. build_fit 만 부르고 짧게 답한다
    (이 턴에는 살말 지수 도구가 목록에 없다).

14. **직전 사진을 기억한다.** `[최근 이미지 분석]`이 있으면 "소재는?", "길이는?",
    "위 아이템은?" 같은 질문의 대상은 그 사진 속 아이템이다. 무엇을 말하는지 다시
    묻지 말고, 기록된 관찰값 안에서 바로 답한다. 기록에 없는 특징은 사진에서 확인하지
    못했다고 말하고 지어내지 마라. 이미지 관찰값은 색·소재·실루엣·디테일 설명에만
    쓰며 브랜드·가격·트렌드의 근거로 쓰지 않는다. 이처럼 **구매 판정이 아닌 사진 설명
    후속 질문**에는 살말 모드여도 get_salmal_index를 다시 부를 필요가 없다.

## 도구 고르는 법
- 질문이 용어를 지목했으면 → search_terms 로 정확한 표기를 얻고 get_metric
- 용어를 지목하지 않았는데 "요즘 뭐가 핫해" 류면 → rank_terms
- 판단을 묻는 질문("사도 돼?", "괜찮아?")이면 → 축을 **여러 개** 넣어라.
  온도 하나로는 답이 안 된다.
- **용어가 여럿이면 get_metric 을 같은 바퀴에 나란히 불러라.** 한 바퀴에 여러 도구를
  부를 수 있다. 용어마다 바퀴를 새로 쓰면 조회만 하다 답 쓸 시간이 없어진다.
  (2026-09-10 실측: get_metric 세 번이 세 바퀴에 흩어져 17.6초를 썼다.)
- **가격·할인·최저가 / 리셀가·중고 시세·프리미엄 / 아직 유행인지·끝물인지** 는
  get_market 으로 조회한다(axis = discount · resale · lifecycle). 온도(get_metric)와
  함께 부르면 "사도 돼?" 판단이 된다. 상품 단위가 아니라 브랜드·종류·스타일 단위다.
  unavailable 이 오면 그 축은 없다고 말하고 지어내지 않는다.
- 우리 지표로 답할 수 없는 질문이면 → web_search. 다만 그 내용이 FEEDiT
  측정값이 아니라는 것을 답변에 밝혀라.
- **"A랑 B 중에 뭐?" 같은 비교 질문이면 두 용어의 get_metric 을 다 불러라.**
  하나만 보고 답하면 비교가 아니다. 축은 같은 것으로 맞춰야 나란히 읽힌다.
  둘 다 조회되면 화면에 '나란히 보기' 가 붙는다.
- **상품 링크나 정확한 상품명이 오면 그대로 찾지 말고 나눠서 찾아라.**
  우리 지표에는 **상품 단위가 없다.** 브랜드 · 아이템 · 소재 단위로만 있다.
  ① 링크뿐이라 무엇인지 모르면 inspect_product_link 로 브랜드·상품명·현재 원화 판매가를
     한 번에 확인한다. 확인된 필드만 사용하고 null은 추측해서 채우지 않는다.
     상품 링크 확인에 일반 web_search를 중복 호출하지 않는다.
       두 번 나눠 찾으면 그 한 번이 5초 넘게 들어(2026-09-11 실측: 웹검색 2회),
       정작 답을 쓰는 바퀴가 예산 밖으로 밀린다. 한 번 찾아 모르면 모르는 대로
       두고, 지표 조회로 넘어가라.
  ② search_terms 는 **한 번만** 부른다. 구성 요소는 alts 에 함께 넣어라 —
     `q="아디다스 트랙탑", alts=["아디다스","트랙탑"]`. 나눠서 두 번 세 번 부르면
     부를 때마다 바퀴를 하나씩 쓰고, 조회만 하다 답 쓸 시간이 없어진다.
     (2026-09-10 실측: 링크 질문에서 search_terms 3연속으로 15초를 다 썼다.)
  ③ **대신 본 것은 반드시 밝힌다** — "아디다스 트랙탑 자체 지표는 없어
     '트랙탑' 기준으로 봤습니다". 밝히지 않으면 사용자는 그 상품의 지표로 읽는다.
     지어낸 숫자와 같은 종류의 오해다.
  ④ 그러고도 없는 축만 declare_missing 으로 기록한다.
  ⑤ 마지막 줄 `[다음]` 으로 나눠서 찾은 용어를 걸어 대화를 잇는다 —
     "아디다스 트랙탑은 찾지 못했지만, 아디다스나 트랙탑을 더 볼까요?"
- **"지금 입을 만해?" 처럼 계절·기온을 묻는 질문이면 → season_fit.**
  ① 먼저 web_search 로 오늘 기온을 확인해 temp_c 에 넣는다(지역 기본값은 서울).
  ② 볼 이름은 terms 에 **한 번에** 넣는다 — 아이템과 소재를 같이 (예: ["트랙탑","폴리에스터"]).
  ③ 이 결과는 **우리 측정값이 아니라 일반적인 착용 기준**이다. 답변에 그렇게 밝혀라.
     트렌드 지표(온도·모멘텀)와 섞어 한 문장에 담지 마라 — 둘은 출처가 다르다.
  ④ 표에 없어 unknown 으로 온 말은 판단하지 마라.
- **"비슷한 거 추천해줘" 면 → similar_terms.**
  ★ 아는 후보를 `terms` 에 **모두** 넣어라. 도구가 그중 기준을 고른다(아이템 축 우선).
    **상품 추천이면 아이템 축 용어를 반드시 함께 넣어라** — "레이어드 와이드팬츠"
    라면 `["팬츠","와이드팬츠","레이어드"]` 처럼. 스타일 용어만 주면
    "레이어드와 비슷한 것: 스트릿웨어 · 캐주얼" 이 나온다. 팬츠를 물었는데
    스타일 목록을 주는 셈이다(2026-09-10 실측).
  ★ 응답의 `base_note` 대로 **무엇을 기준으로 봤는지 답변에 밝혀라.**
    `caution` 이 있으면 그것도 그대로 전해라.
  ★ 응답의 `items` 만 "비슷한 것" 이다. `paired_with` 는 **함께 언급된 말**이라
    같이 입는 것에 가깝다 — 이것을 비슷한 것으로 말하지 마라.
    (실측: 반팔 티셔츠에 "비슷한 것" 으로 팬츠·자켓을 늘어놨다. 말이 안 된다.)
    코디를 곁들이고 싶으면 "같이 많이 언급되는 건 …" 이라고 **따로** 말해라.
  ★ `method` 를 답변에 옮겨라 — 무엇을 근거로 골랐는지가 답의 신뢰를 정한다.
    "연관어 프로필 겹침"(함께 쓰이는 말이 겹친다)과 "이름 계열"(…팬츠 처럼 이름이
    같은 갈래)은 다른 근거다. 이름 계열은 표기가 갈리면 놓친다는 것도 알고 있어라.
  ★ `items` 가 비어 있으면 **비슷한 것을 못 찾은 것이다.** 먼저 그렇게 말해라.
    그때 오는 `alternatives` 는 다른 질문의 답이다 — "대신 지금 이 축에서 높은
    것은 …" 처럼 **따로** 소개해라. 비슷한 것으로 소개하면 팬츠 옆에 자켓·백팩이
    서게 된다(2026-09-10 실측). 우리 연관어 자료가 아직 얇아서 생기는 일이다.
  ★ 우리 데이터는 **용어** 단위라 상품 목록도 사진도 없다. "사진을 보여 드릴게요"
    라고 말하지 마라. 용어를 짚어 주고 `[다음]` 으로 무엇을 더 볼지 물어라.
- **상황으로 코디를 물으면(데이트룩 · 하객룩 · 출근룩 · "○○ 갈 때 뭐 입지") → find_looks 먼저.**
  요즘 연예인·인플루언서·매거진에서 실제로 입은 조합을 찾고, 그중 하나를 골라 그 룩의
  items 를 slots·kinds 로, source.url 을 ref_url 로, 상황을 occasion 으로 propose_fit 에
  넘긴다. 답에는 "요즘 ○○(출처)에서 이런 조합이 보여서 이렇게 짰다" 를 한 줄로 쓴다 —
  이건 FEEDiT 측정값이 아니라 웹에서 찾은 코디라는 점이 드러나게. looks 가 비면 그 사실을
  말하고 스타일 기준으로 propose_fit 을 부른다(출처를 지어내지 않는다).
- **"다른 룩" · "다른 거" · 직전에 "다른 룩도 볼까요?" 에 "응" 이면 → 새 코디를 짠다.**
  [직전 답변이 물은 것]과 [이 대화에서 쓴 코디]를 보고, 앞서 근거로 쓴 룩(used_before)이 아닌
  다른 룩이나 다른 스타일로 find_looks → propose_fit 을 다시 부른다. 이미 보여 준 상품은
  서버가 빼 준다. 같은 상황(occasion)은 그대로 이어 간다.
- **"입혀봐 줘" · "코디 보여 줘" 면 → propose_fit.** 승인 카드가 뜨고, 사용자가 누르면
  살!말? 에서 입혀본다. styles 에는 **스타일**만 적는다 — 하객·출근 같은 상황은 어울리는
  스타일로 바꿔 적고, 블라우스·슬랙스 같은 아이템은 kinds 에 적는다.
  unavailable 과 함께 available_styles 가 오면 거기서 골라 **한 번 더** 부른다.
  "입혀볼 수 있는 스타일이 뭐야?" 는 → fit_styles. rank_terms 가 아니다 — 순위는
  최근 언급된 용어의 트렌드 표라 상품에 붙은 태그와 다르다(2026-10-01 실측: 순위가 비어
  "태깅된 스타일이 없다" 고 답했다).
- **날씨처럼 우리 지표 밖이지만 옷차림과 이어지는 질문은 되묻지 마라.**
  지역 기본값(서울)으로 web_search 해서 답하고, 옷차림 제안으로 자연스럽게 잇는다.
  이 서비스에서 날씨는 목적이 아니라 **패션 조언의 재료**다.

## 답변 문체
한국어. **사람과 대화하듯 쓴다.**

- **"결론적으로" · "결론:" · "요약하면" 같은 머리말을 붙이지 마라.** 보고서가 아니다.
  숫자와 근거는 화면 카드가 이미 보여 주고 있고, 본문은 그 옆에서 말을 건네는 자리다.
  첫 문장에서 바로 답한다.
- **판단·분석 답은 이 틀로 쓴다** (살말 판단, 트렌드 분석, 비교 등 근거가 둘 이상인 답):
  ```
  **결론 한 문장**

  - 근거 한 줄
  - 근거 한 줄
  - 근거 한 줄

  아쉬운 점이나 주의할 점 한 줄 (있을 때만)
  ```
  · 결론은 첫 줄 한 문장, `**` 로 감싼다. 그 뒤 반드시 빈 줄.
  · 근거는 `- ` 글머리표로 2~4개. **한 줄에 한 가지 사실, 한 문장.** 쉼표로 이어 붙이지 마라.
  · "아직 측정 자료가 없습니다" 류는 항목마다 쓰지 말고 마지막 한 줄로 묶는다
    (예: "가격·커뮤니티 신호는 아직 측정 자료가 없어 판단에서 뺐어요.").
  · 문단 사이·목록 앞뒤에는 **빈 줄**을 둔다. 3문장 넘는 문단을 만들지 마라.
  (2026-09-18 실측: 3문장짜리 문단 세 개를 이어 써서 화면이 빽빽하고 읽기 어려웠다.)
- 인사·잡담·용어 뜻처럼 근거가 하나뿐인 답은 틀 없이 1~3문장으로 답한다.
- **길어도 6문장.** 지표 숫자는 카드에 이미 그려지므로 본문에서 전부 되풀이하지
  마라 — 결론과 그 근거가 되는 값만 고른다.
- **카드에 목록으로 실은 것을 본문에서 다시 나열하지 마라.** compose_report 를
  불렀다면 그 모듈이 화면에 그대로 그려진다. 본문에 같은 목록을 또 쓰면 사용자는
  같은 것을 두 번 읽는다 — 화면이 두 배로 길어질 뿐 새로 아는 것이 없다.
  (2026-09-14 실측: "트렌드 TOP 10 알려줘" 에 본문이 1~10위를 전부 읊고 그 아래
   카드가 같은 10줄을 또 그렸다.)
  · ranking·comparison·recommendations·associations·sources·links·evidence 처럼
    **여러 줄이 늘어서는 모듈**을 카드에 넣었으면, 본문은 그 목록을 옮기지 않는다.
  · 본문이 할 일은 목록을 대신 **읽어 주는 것**이다 — 맨 위 한둘만 이름으로
    짚고, 무엇을 센 순위인지·무엇이 눈에 띄는지·그래서 어떻게 읽어야 하는지를
    말한다. "1위는 자켓, 2위는 셔츠…" 가 아니라 "아우터가 상위권을 차지했고,
    소재 축에서는 레더가 유일하게 올라왔습니다" 처럼.
  · 반대로 compose_report 를 **부르지 않았다면** 화면에 카드가 없다. 그때는
    본문이 목록을 그대로 적어야 한다 — 안 그러면 사용자가 아무것도 못 받는다.
- 숫자에는 기준일을 붙이고, 확실하지 않은 것은 확실하지 않다고 쓴다. 과장하지 않는다."""


class Result:
    """오케스트레이터가 내놓는 것.

    answer 를 그대로 사용자에게 보내지 않는다 — verify.py 를 거친다.
    trace 가 그 검증의 원본이다.
    """

    def __init__(self) -> None:
        self.answer: str = ""
        self.trace = None            # tools.TraceLog
        self.rounds: int = 0
        self.calls: int = 0
        self.stopped: str = ""       # 왜 멈췄나 (진단용)
        self.ask: dict | None = None  # ask_user 가 걸렸으면 여기
        self.sources: list[dict] = []
        self.deadline: float = 0.0   # 이 답변 전체의 마감시각 (time.monotonic 기준)
        # ★ 바퀴마다 몇 초가 걸렸나. 이게 없으면 "18초가 어디로 갔나" 를 추측하게 된다.
        self.round_ms: list[int] = []
        # ★ 호스티드 도구(web_search · mcp)가 몇 번 돌았나.
        #   우리 TraceLog 에는 **안 남는다** — 모델 쪽에서 도는 것이라 도구 목록에도
        #   안 보인다. 그래서 링크 질문이 왜 느린지가 로그에서 통째로 빠져 있었다.
        self.hosted: int = 0
        # ★ 상한(바퀴·시간)에 걸렸지만 모델이 **이미 다 써 둔 답**을 되살렸나.
        #   그렇다면 답은 온전하다 — 화면에 "조회를 끝까지 못 했다" 고 적으면
        #   멀쩡한 답에 경고가 붙는다.
        self.recovered: bool = False
        # ★ Sol 로 다시 부른 자리 (2026-09-18) — "어디서 막혔나" 가 여기 남는다.
        #   예: ["orchestrator:NET_ReadTimeout", "finish:empty"]
        self.escalated: list[str] = []


def _recent_terms(history: list[dict] | None, limit: int = 5) -> list[str]:
    """이 대화에서 최근에 본 용어들 — 최신 순 (15번, 세션 기억).

    ★ 새로 저장하지 않는다. history 의 각 턴이 이미 terms 를 들고 있다.
      "이거 어때?" 를 풀 때 화면에 보던 용어(screen_term) 하나만으로는
      모자란 자리가 있다 — 방금 두세 개를 물어본 대화에서는 '이거' 가
      직전 용어일 확률이 높다.
    """
    out: list[str] = []
    for t in reversed(history or []):
        for x in (t.get("terms") or []):
            c = (x or {}).get("canonical")
            if c and c not in out:
                out.append(str(c))
                if len(out) >= limit:
                    return out
    return out


def _ctx_block(question: str, ctx: dict, history: list[dict] | None) -> str:
    """모델에게 주는 상황. 질문만으로는 '이거' 를 못 푼다(설계도 L0)."""
    lines = [f"[질문] {question}"]
    # ★ 챗봇이 바로 앞 답 끝에 되물은 것 (2026-10-01). "응 두개 다 알려줘" 는 이 질문에
    #   대한 대답이다. 예전엔 기억에 사용자 질문만 있어서 모델이 '두 개' 를 짐작했다.
    last = (history or [])[-1] if history else None
    if isinstance(last, dict) and last.get("next"):
        lines.append(f"[직전 답변이 물은 것] {last['next']}  ← 짧은 대답(응 · 좋아 · 둘 다 · "
                     "그거)은 이 질문에 대한 대답이다")
    if ctx.get("screen_term"):
        lines.append(f"[사용자가 보던 용어] {ctx['screen_term']}")
    if ctx.get("salmal_card_id"):
        lines.append(f"[살!말? 카드에서 넘어옴] card_id={ctx['salmal_card_id']}")
    # ★ 승인된 코디 (2026-10-01). 이 턴의 질문은 버튼이 보낸 "이 코디로 입혀보기" 뿐이라,
    #   무엇을 입힐지는 여기에만 있다. 없으면 모델은 "어떤 코디를요?" 를 되묻는다.
    proposal = ctx.get("fit_proposal")
    if isinstance(proposal, dict) and proposal.get("items"):
        worn = " / ".join(f"{r.get('slot')} {str(r.get('name') or '')[:30]}"
                          for r in proposal["items"] if isinstance(r, dict))
        styles = "·".join(proposal.get("styles") or [])
        lines.append(f"[승인된 코디] {styles + ' — ' if styles else ''}{worn}  ← 사용자가 "
                     "'이 코디로 입혀보기' 를 눌러 승인했다. 되묻지 말고 build_fit 을 불러 "
                     "착장 칸을 채워라. 이 턴은 구매 판단이 아니다.")
    # ★ 이 대화에서 이미 보여 준 코디 (2026-10-02) — '다른 룩' 이 같은 룩이 되지 않게.
    if ctx.get("fit_occasion"):
        lines.append(f"[이 대화의 코디 상황] {ctx['fit_occasion']}  ← '다른 룩' 이면 이 상황을 이어 간다")
    if ctx.get("fit_seen"):
        lines.append(f"[이 대화에서 이미 보여 준 상품] {len(ctx['fit_seen'])}점 — propose_fit 이 빼고 고른다")
    if ctx.get("fit_refs"):
        lines.append("[이 대화에서 근거로 쓴 코디 기사] " + " · ".join(ctx["fit_refs"][:4]) +
                     "  ← '다른 룩' 이면 이 기사 말고 다른 룩을 골라라")
    # ★ 지역 — 없으면 한국을 기본으로 잡게 한다. 모델은 놔두면 미국을 가정한다.
    if ctx.get("region"):
        lines.append(f"[사용자 지역] {ctx['region']}")
    else:
        lines.append("[지역 미상] 한국 사용자다. 지역이 필요하면 서울을 기본으로 잡아라")
    if ctx.get("user_id"):
        lines.append("[로그인함] 취향을 근거로 쓸 수 있다")
    else:
        lines.append("[비로그인] 취향 얘기를 하지 마라")
    # ★ 되묻기 예산이 없으면 그 사실과 **대신 할 일**을 같이 준다.
    #   막기만 하면 모델은 되물을 자리에서 멈추거나 엉뚱하게 지어낸다.
    if ctx.get("no_ask"):
        lines.append("[되묻기 예산 소진] 이 대화에서 이미 되물었다. 또 되묻지 마라. "
                     "가장 그럴듯한 것으로 잡아 답하고, 무엇을 가정했는지 한 줄로 "
                     "밝힌 뒤 '아니면 말씀해 주세요' 를 붙여라.")
    seen = _recent_terms(history)
    if seen:
        # ★ 쓰임을 좁힌다 (2026-10-01). 예전 문구는 쓰임을 말하지 않아서, 새 질문
        #   ("핫한 아이템 순위는?")의 답에 지난 주제(플리스·트랙탑)가 끼어들었다.
        lines.append("[최근 본 용어] " + " · ".join(seen)
                     + "  ← '이거 · 아까 그거' 같은 지시어를 풀 때만 쓴다. "
                       "질문이 새 대상을 물으면 답변과 [다음] 에 끌어오지 마라")
    visual = next((t.get("visual") for t in reversed(history or [])
                   if isinstance(t, dict) and isinstance(t.get("visual"), dict)), None)
    if visual:
        bits = []
        if visual.get("item"):
            bits.append("아이템=" + str(visual["item"]))
        labels = {"colors": "색", "materials": "소재", "silhouette": "실루엣",
                  "details": "디테일", "styles": "스타일", "tags": "태그",
                  "uncertainties": "불확실"}
        for key, label in labels.items():
            values = visual.get(key)
            if isinstance(values, list) and values:
                bits.append(label + "=" + "·".join(str(x) for x in values[:6]))
        if bits:
            lines.append("[최근 이미지 분석] " + "; ".join(bits))
        # 브라우저가 돌려주는 history는 밖에서 온 값이다. 자유문장 summary를 시스템
        # 문맥에 다시 넣지 않고, 길이·개수가 제한된 구조화 필드만 사용한다.
        lines.append("[이미지 기억 범위] 위 값은 사진에서 본 특징에만 사용한다. "
                     "브랜드·가격·트렌드는 별도 근거 없이는 추측하지 마라")
    for t in (history or [])[-3:]:
        q, a = t.get("q"), t.get("a")
        if q:
            lines.append(f"[직전 질문] {q}")
        if a:
            lines.append(f"[직전 답변 요약] {str(a)[:160]}")
    return "\n".join(lines)


def _hosted_calls(raw: dict) -> int:
    """모델이 서버 쪽에서 직접 돌린 도구 수 (web_search_call · mcp_call 등).

    ★ 이것들은 Toolbox 를 거치지 않으므로 TraceLog 에 안 남는다. 그런데 링크
      질문에서는 이게 제일 느린 항목일 수 있다 — 무슨 상품인지 알려면 모델이
      웹을 뒤져야 하기 때문이다. 안 세면 그 시간이 어디로 갔는지 알 수 없다.
    """
    n = 0
    for item in (raw.get("output") or []):
        t = str((item or {}).get("type") or "")
        if t.endswith("_call") and t != "function_call":
            n += 1
    return n


def _history_asks(history: list[dict] | None) -> int:
    """history 안의 되묻기 턴 수. 세는 규칙은 history.py 한 곳에 있다."""
    from .history import count_asks
    return count_asks(history)


def _sig(name: str, args: dict) -> str:
    """같은 도구를 같은 인자로 부르는지 보는 지문."""
    try:
        return name + "|" + json.dumps(args, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return name + "|?"


_REPORT_MATERIAL = {
    "rank_terms", "get_metric", "get_evidence", "get_user_taste",
    "get_salmal", "search_salmal", "get_salmal_index",
    "season_fit", "similar_terms", "declare_missing", "get_market",
}

_REPORT_EXPLICIT = re.compile(
    r"(?:리포트|보고서|표(?:로|로\s*보)|차트|그래프|상세|자세히|근거|"
    r"분석|비교|\bvs\b|순위|랭킹|\btop\s*\d*\b|플랫폼별|출처별|"
    r"연관어|긍부정|감성|수명주기|아직\s*유효|유효해|추이)",
    re.I,
)
_REPORT_ALWAYS_TOOLS = {"rank_terms", "get_salmal", "search_salmal",
                        "get_salmal_index"}


def _has_report_material(trace) -> bool:
    """문장뿐 아니라 구조화 화면으로 보여 줄 도구 결과가 있는가."""
    return any(c.get("tool") in _REPORT_MATERIAL for c in (trace.calls if trace else []))


def report_required(question: str, trace) -> bool:
    """모델이 카드를 빠뜨려도 반드시 복구해야 하는 복잡한 질의인가.

    이것은 리포트를 *고르는* 1차 판단이 아니다. 1차 판단은 Terra 오케스트레이터가
    대화 맥락까지 보고 compose_report 호출 여부로 남긴다. 이 함수는 TOP·비교·살말
    처럼 문장만 나오면 정보 구조가 훼손되는 경우에만 안전망으로 작동한다.
    """
    calls = list(trace.calls if trace else [])
    if not any(c.get("tool") in _REPORT_MATERIAL for c in calls):
        return False
    if _REPORT_EXPLICIT.search(str(question or "")):
        return True

    names = {c.get("tool") for c in calls}
    if names & _REPORT_ALWAYS_TOOLS:
        return True

    metrics = [c for c in calls if c.get("tool") == "get_metric"
               and isinstance(c.get("result"), dict)
               and c["result"].get("has_metric") is not False]
    metric_terms = {
        str((c.get("result") or {}).get("term") or (c.get("args") or {}).get("term") or "")
        for c in metrics
    }
    metric_terms.discard("")
    if len(metric_terms) >= 2:
        return True

    axes = set()
    for c in metrics:
        raw = (c.get("args") or {}).get("axes")
        if isinstance(raw, list):
            axes.update(str(x) for x in raw if x)
    if len(axes) >= 3:
        return True

    # 숫자와 원문 근거, 또는 여러 개의 연관 항목은 나란히 보는 편이 낫다.
    if metrics and "get_evidence" in names:
        return True
    for c in calls:
        if c.get("tool") == "similar_terms":
            res = c.get("result") or {}
            items = res.get("items") or res.get("terms") or res.get("similar") or []
            if isinstance(items, list) and len(items) >= 3:
                return True
    return False


def _has_report_design(trace) -> bool:
    return any(c.get("tool") == "compose_report" and
               isinstance(c.get("result"), dict) and c["result"].get("ok")
               for c in (trace.calls if trace else []))


def _recent_styles(history, ctx: dict) -> list[str]:
    """이 대화에서 **이미 다룬 스타일**을 새 것부터 모은다 (2026-09-22).

    왜 필요한가 —
      "위 스타일대로 입혀 줘" 에 챗봇이 "어떤 스타일로요?" 를 되물었다. 방금
      자기가 추천한 것을 되묻는 꼴이다. 원인은 코드에 있었다: 코디 도구가 스타일을
      **인자로만** 받아서, 모델이 앞 턴을 옮겨 적지 않으면 아무 데도 없었다.
      기억하는 자리를 도구가 닿는 곳(ctx)에 만든다 — 프롬프트로 "기억해라" 하고
      부탁하는 것과 다르다.
    ★ 답변 문장에서 뽑지 않는다. history 의 terms 는 도구가 조회한 것만 남고
      (history.make_turn), 모델이 지어낸 이름은 거기 없다.
    ★ 조회한 스타일이 없으면 취향(즐겨입는 스타일)으로 떨어진다. 그것도 없으면
      빈 목록이고, 도구는 되묻지 않고 "고를 수 없다" 고 말한다.
    """
    out: list[str] = []
    for turn in reversed(list(history or [])):
        for t in (turn.get("terms") or []):
            name = str((t or {}).get("canonical") or "").strip()
            facet = str((t or {}).get("facet") or "").lower()
            if name and facet == "style" and name not in out:
                out.append(name)
    taste = ctx.get("taste_context") if isinstance(ctx.get("taste_context"), dict) else {}
    for name in (taste.get("favorite_styles") or []):
        text = str(name).strip()
        if text and text not in out:
            out.append(text)
    return out[:6]


def run(question: str, *, store, gate, ctx: dict | None = None,
        history: list[dict] | None = None, salmal=None, taste=None,
        websearch=None, on_progress=None, deadline: float | None = None,
        cancel_check=None) -> Result:
    ctx = ctx or {}
    out = Result()
    box = Toolbox(store, gate, ctx=ctx, salmal=salmal, taste=taste, websearch=websearch)
    out.trace = box.trace

    # ★ 되묻기 예산 (15번). 다 썼으면 ask_user 를 목록에서 뺀다.
    #   engine 이 세어 준 값(서버 기억 기준)과 여기서 본 history 중 큰 쪽을 쓴다 —
    #   orchestrator 를 직접 부르는 자리(스모크·테스트)에서도 상한이 걸리게.
    # ★ 방금 다룬 스타일을 도구가 볼 수 있게 둔다. propose_fit 이 인자 없이도
    #   코디를 짤 수 있으면 모델은 되물을 이유가 없다.
    recent = _recent_styles(history, ctx)
    if recent:
        ctx = {**ctx, "recent_styles": recent}

    asked = max(int(ctx.get("asked_before") or 0), _history_asks(history))
    if asked >= ASK_BUDGET:
        ctx = dict(ctx)
        ctx["no_ask"] = True
    tools = specs_for(ctx)
    items: list[Any] = [{"role": "user", "content": _ctx_block(question, ctx, history)}]
    seen: set[str] = set()
    per_tool: dict[str, int] = {}      # 도구 이름 → 부른 횟수 (MAX_PER_TOOL)
    pending_answer = ""               # 디자인 호출을 빼먹은 답은 잠시 보류한다.
    borrowed = False                  # 뒷몫을 빌려 마지막 한 바퀴를 도는 중인가
    started = time.monotonic()
    # ★ 마감시각은 밖에서 온다(agent_path). 혼자 돌 때만 여기서 만든다 —
    #   그래야 _finish · verify 까지 같은 하나를 나눠 쓴다(18번).
    if deadline is None:
        deadline = started + budget_for(question)
    out.deadline = deadline
    # 루프는 예산을 다 쓰지 않는다. 뒷단계 몫을 먼저 떼고 시작한다.
    loop_end = deadline - reserve(deadline - started, TAIL_RESERVE)

    # 코디 도구가 불려 마감시각을 늘렸는가. 한 답변에 한 번만 늘린다.
    fit_extended = False
    look_extended = False

    max_rounds = rounds_for(question)
    for rnd in range(max_rounds):
        if cancel_check and cancel_check():
            out.stopped = "cancelled"
            break
        out.rounds = rnd + 1
        left = loop_end - time.monotonic()
        # ★ 남은 시간이 한 호출을 끝낼 만큼이 아니면 시작하지 않는다(WRITE_MIN).
        #   시작해서 잘리면 그 시간은 통째로 버려지고, 마무리에 쓸 몫까지 줄어든다.
        if left < WRITE_MIN and _has_report_material(box.trace):
            # ★ 다만 조회가 이미 끝났다면 남은 일은 **답 쓰기 하나**다 (2026-09-11).
            #   뒷몫(TAIL_RESERVE)은 루프가 답을 못 썼을 때 _finish 가 대신 쓰라고
            #   비워 둔 시간이다. 그런데 그 시간을 비워 두느라 루프가 답을 못 쓰면,
            #   같은 일을 **한 번 더** 하려고 예산을 두 번 쓰는 셈이 된다.
            #   이 바퀴가 성공하면 _finish 는 아예 필요 없고, 실패해도 _recap 이
            #   도구 결과로 받는다(모델을 부르지 않는다). 그러니 여기서 빌린다.
            left = deadline - VERIFY_RESERVE - time.monotonic()
            if left >= WRITE_MIN:
                # 빌렸으면 이번이 마지막이다. 그 사실을 모델에게 말해 준다 —
                # 말하지 않으면 도구를 더 부르다 끝나고, 빌린 시간도 버려진다.
                borrowed = True
        if left < WRITE_MIN:
            out.stopped = "time_budget"
            break
        if borrowed:
            items.append({
                "role": "user",
                "content": ("시간이 거의 없습니다. 데이터 도구를 더 부르지 말고, "
                            "지금까지 받은 결과만으로 바로 답하세요. 여러 지표를 나란히 "
                            "보여야 할 때만 compose_report 를 한 번 부르세요."),
            })
            borrowed = False

        # ★ 마지막 바퀴는 답 쓰기 전용 (2026-09-18).
        #   예전에는 마지막 바퀴에도 도구를 다 줬다. 모델이 하나 더 부르면 바퀴가
        #   바닥나 답 없이 끝났고, 화면엔 조회 목록과 "요약 문장을 쓸 시간이 모자라"
        #   만 남았다. 마지막 바퀴에는 데이터 도구를 빼고(리포트 구성만 남김) 그 사실을 말한다.
        round_tools = tools
        if rnd == max_rounds - 1:
            round_tools = ([t for t in tools if t.get("name") == "compose_report"]
                           if not _has_report_design(box.trace) else [])
            if not borrowed:
                items.append({
                    "role": "user",
                    "content": ("이번이 마지막 차례입니다. 데이터 도구는 더 부를 수 없습니다. "
                                "지금까지 받은 결과만으로 답을 쓰세요."
                                + (" 시각 리포트가 필요하면 답과 함께 compose_report 를 한 번만 부르세요."
                                   if round_tools else "")),
                })

        t_round = time.monotonic()
        res = llm.respond(
            INSTRUCTIONS, items, tools=round_tools or None, raw_flag=True,
            # ★ 남은 시간을 **실수 그대로** 상한으로 쓴다.
            #   int(left) 는 내림이라 2.9 초 남았을 때 2 초만 주고 끊었다.
            #   하한 2 초는 연결 자체가 안 되는 시간을 피하기 위한 것이다.
            timeout=max(2.0, min(float(CALL_TIMEOUT), left)),
            **llm.role("orchestrator"),
        )
        if res is None and "orchestrator" not in " ".join(out.escalated) and llm.can_escalate():
            # ★ Terra 가 막혔다 — 남은 시간이 한 바퀴를 쓸 만하면 Sol 로 같은 바퀴를 다시 돈다.
            left = deadline - VERIFY_RESERVE - time.monotonic()
            if left >= WRITE_MIN:
                out.escalated.append(f"orchestrator:{llm.LAST_ERROR}")
                res = llm.respond(
                    INSTRUCTIONS, items, tools=round_tools or None, raw_flag=True,
                    timeout=max(2.0, min(float(CALL_TIMEOUT), left)),
                    **llm.escalate("orchestrator"),
                )
        if res is None:
            # 모델에 못 닿았다. 지금까지 모은 것이 있으면 그걸로라도 답한다.
            out.round_ms.append(int((time.monotonic() - t_round) * 1000))
            out.stopped = f"llm_{llm.LAST_ERROR or 'unknown'}"
            break

        raw = res.get("_raw") or {}
        out.sources = res.get("_raw_sources") or out.sources
        out.round_ms.append(int((time.monotonic() - t_round) * 1000))
        out.hosted += _hosted_calls(raw)
        calls = llm.tool_calls(res)

        if not calls:
            # 도구를 더 안 부른다 = 답할 준비가 됐다.
            candidate = (res.get("text") or "").strip()
            # Terra가 문장만으로 충분하다고 판단했다면 그대로 끝낸다. 다만 TOP·비교·
            # 살말처럼 카드가 없으면 정보 관계가 사라지는 질의만 안전망으로 복구한다.
            if (candidate and report_required(question, box.trace)
                    and not _has_report_design(box.trace) and rnd < max_rounds - 1):
                pending_answer = candidate
                items.extend(raw.get("output") or [])
                items.append({
                    "role": "user",
                    "content": ("답변 본문은 준비됐습니다. 이번 질문은 순위·비교·다축 "
                                "결과라 시각 리포트가 필요합니다. 새 데이터 도구는 부르지 말고, 실제 "
                                "결과만 사용해 compose_report를 정확히 한 번 부르세요."),
                })
                continue
            out.answer = candidate
            out.stopped = "done"
            break

        # ★ compose_report 를 부르면서 **같이 쓴 답변 문장**은 버리지 않는다
        #   (2026-09-11). 모델은 마지막 바퀴에서 도구 호출과 문장을 함께 내는
        #   일이 잦은데, 이 루프는 호출이 있으면 문장을 통째로 버리고 다음
        #   바퀴에서 다시 쓰게 했다. 그 바퀴가 없으면(max_rounds) 답이 사라진다.
        #   compose_report 는 조회가 끝났다는 신호라서, 그 바퀴의 문장만 받는다 —
        #   중간 바퀴의 "이제 지표를 볼게요" 같은 말은 답이 아니다.
        if not pending_answer and any(c["name"] == "compose_report" for c in calls):
            said = (res.get("text") or "").strip()
            if said:
                pending_answer = said

        # ★ 모델이 낸 출력 항목을 그대로 되돌려 넣는다.
        #   이게 없으면 모델은 자기가 뭘 불렀는지 모른 채 다음 바퀴를 돌고,
        #   같은 도구를 영원히 다시 부른다.
        items.extend(raw.get("output") or [])

        for c in calls:
            if cancel_check and cancel_check():
                out.stopped = "cancelled"
                break
            if out.calls >= MAX_CALLS:
                out.stopped = "max_calls"
                break
            sig = _sig(c["name"], c["args"])
            if sig in seen:
                # 같은 인자로 두 번은 언제나 버그다. 사실대로 알려 주면
                # 다음 바퀴에서 다른 것을 부르거나 답을 쓴다.
                items.append(llm.tool_result_item(
                    c["call_id"],
                    {"skipped": "같은 인자로 이미 불렀습니다. 결과가 위에 있습니다."}))
                continue
            used = per_tool.get(c["name"], 0)
            if c["name"] == "compose_report" and used >= 1:
                items.append(llm.tool_result_item(
                    c["call_id"],
                    {"skipped": "compose_report 는 이미 구성했습니다. 다시 부르지 말고 답을 쓰십시오."}))
                continue
            if c["name"] not in NO_CAP and used >= MAX_PER_TOOL:
                # 인자를 바꿔 가며 같은 도구를 계속 부르는 자리.
                # 막기만 하면 또 부르므로, **무엇을 하라고** 같이 적어 준다.
                items.append(llm.tool_result_item(
                    c["call_id"],
                    {"skipped": f"{c['name']} 는 이미 {used}번 불렀습니다. "
                                "인자를 바꿔 다시 부르지 마십시오. "
                                "없는 축이 더 있으면 도구를 또 부르지 말고, "
                                "답변에서 한 문장으로 묶어 밝히십시오 "
                                "(\"…와 …는 아직 측정 자료가 없습니다\"). "
                                "그 밖에는 다른 도구를 쓰거나 답을 쓰십시오."}))
                continue
            seen.add(sig)
            per_tool[c["name"]] = used + 1
            out.calls += 1
            # ★ 부르기 **전에** 알린다. 조회가 끝난 뒤 알리면 이미 늦다.
            #   콜백이 터져도 대화는 계속돼야 한다 — 화면 장식이지 본체가 아니다.
            if on_progress:
                say = progress_say(c["name"], c["args"])
                if say:
                    try:
                        on_progress(say)
                    except Exception:                    # noqa: BLE001
                        pass
            result = box.run(c["name"], c["args"])
            items.append(llm.tool_result_item(c["call_id"], result))
            # ★ 코디 도구는 상품 조회(또는 사진 검수)를 한 바퀴 더 쓴다. 그 사실이
            #   확인된 지금 마감시각을 한 번만 늘린다 — 늘리지 않으면 코디를 짜 놓고
            #   답을 못 쓴다. 두 번 늘리지 않는다(fit_extended).
            if c["name"] in FIT_TOOLS and not fit_extended:
                fit_extended = True
                deadline += FIT_EXTRA
                loop_end += FIT_EXTRA
                out.deadline = deadline
            if c["name"] == "find_looks" and not look_extended:
                look_extended = True
                deadline += LOOK_EXTRA
                loop_end += LOOK_EXTRA
                out.deadline = deadline

        # 도구 사이에서 들어온 중단은 아래의 보류 답 복구보다 우선한다.
        # 그렇지 않으면 compose_report 와 함께 써 둔 문장이 cancelled 를 done 으로
        # 다시 덮어, 사용자가 중단했는데 완료 응답이 전송될 수 있다.
        if out.stopped == "cancelled":
            break

        # 보류된 답이 있고 디자인 스킬 호출이 끝났으면 같은 문장을 다시 쓰게
        # 하지 않는다. 여기서 바로 닫아 지연과 비용을 한 바퀴 줄인다.
        if pending_answer and _has_report_design(box.trace):
            out.answer = pending_answer
            out.stopped = "done"
            break

        if box.trace.asked:
            # 되묻기가 걸렸다. 더 부를 이유가 없다.
            out.ask = box.trace.asked
            out.stopped = "ask_user"
            break
        if out.stopped == "max_calls":
            break
    else:
        out.stopped = "max_rounds"

    # ★ 디자인 호출을 기다리며 보류해 둔 답이 있는데 루프가 끝났다면,
    #   그 답을 버리지 않는다 (2026-09-11). 예전에는 compose_report 가 돌았을
    #   때만 꺼내 썼다 — 시간이 모자라 못 돌면 **이미 다 써 둔 답을 버리고**
    #   같은 답을 쓰려고 모델을 한 번 더 불렀다. 화면은 폴백 레이아웃으로
    #   그려지지만(report_skill), 답변 문장은 멀쩡한 것이 남는다.
    if not out.answer and not out.ask and pending_answer:
        out.answer = pending_answer
        out.recovered = True

    # 바퀴를 다 썼거나 시간이 다 됐는데 답이 없다 —
    # 모은 것으로 한 번만 더, 도구 없이 쓰게 한다.
    if out.stopped == "cancelled":
        out.answer = "답변 생성을 중단했습니다."
    elif not out.answer and not out.ask:
        out.answer = _finish(items, out, deadline)

    return out


# 안전장치가 걸렸을 때 사용자에게 보이는 말 (설계도 부록 16).
#   "안 걸리면 생기는 일" 만 정해 두고 걸렸을 때 할 말이 없으면,
#   그 순간 화면은 그냥 멈춘 것처럼 보인다.
STOP_SAY = {
    "time_budget": "여기까지 확인했습니다. 어느 쪽을 더 볼까요?",
    "max_rounds": "여기까지 확인했습니다. 어느 쪽을 더 볼까요?",
    "max_calls": "여기까지 확인했습니다. 어느 쪽을 더 볼까요?",
}


# ★ 마무리 전용 지시문 (2026-09-10).
#   예전에는 _finish 도 INSTRUCTIONS(규칙 11개 + 도구 고르는 법 전체)를 통째로
#   보냈다. 그런데 이 자리에서는 **도구를 고르지 않는다** — 이미 모은 것을 문장으로
#   옮길 뿐이다. 안 쓰는 규칙을 매번 같이 보내면 그만큼 읽고 생각하는 시간이 든다.
#   남은 시간이 4~6초뿐인 자리에서 그 차이는 답이 나오느냐 마느냐를 가른다.
_FINISH_INSTRUCTIONS = """너는 FEEDiT 의 패션 트렌드 분석 상담원이다.
앞에서 조회한 도구 결과가 함께 온다. 그것만으로 답을 쓴다.

1. **도구 결과에 있는 값만 쓴다.** 없는 숫자를 채우지 마라.
2. 없는 축은 "아직 측정 자료가 없습니다" 라고 밝힌다.
3. 요청한 대상이 없어 다른 용어로 대신 봤다면 **그 사실을 반드시 밝힌다.**
4. 주소는 도구가 준 것만 쓴다. 없으면 "(원문 링크 없음)".
5. 한국어. **사람과 대화하듯** 쓴다. "결론적으로" · "결론:" 같은 머리말을 붙이지 마라.
   첫 문장에서 바로 답한다. 숫자에는 기준일을 붙인다.
6. **길어도 6문장.** 판단·분석 답은 `**결론 한 문장**` → 빈 줄 → `- ` 근거 2~4줄
   (한 줄에 한 사실) → 빈 줄 → 없는 자료를 묶은 한 줄. 3문장 넘는 문단을 만들지 마라.
   숫자는 카드에 이미 그려지니 전부 되풀이하지 마라.
7. 이어 갈 질문이 있으면 맨 마지막 줄에 `[다음] …` 한 줄로."""


_AXIS_LABEL = {"taste": "취향", "behavior": "검색·찜", "trend": "트렌드",
               "price": "가격", "community": "커뮤니티"}


def _recap(out: Result) -> str:
    """조회한 것으로 마무리 문장을 **직접** 쓴다. 모델을 부르지 않는다.

    ★ 왜 (2026-09-11 실측)
      링크 질문은 웹 검색 한 바퀴를 먼저 쓰기 때문에, 마무리 문장을 쓸 시간이
      남지 않는 일이 있다. 그때 화면에는 지표 카드가 다 그려져 있는데 본문은
      "여기까지 확인했습니다. 어느 쪽을 더 볼까요?" 한 줄뿐이었다. 무엇을 봤고
      무엇이 나왔는지가 통째로 사라진 셈이다.

      값은 전부 도구 결과에서 가져온다. 지어내는 문장이 아니라 **옮겨 적는**
      문장이라 모델 없이 쓸 수 있고, 그래서 시간이 없을 때도 쓸 수 있다.
    """
    calls = list(out.trace.calls if out.trace else [])
    if not calls:
        return ""
    metrics: list[str] = []
    empty: list[str] = []
    salmal: dict | None = None
    for c in calls:
        res = c.get("result")
        if not isinstance(res, dict):
            continue
        if c.get("tool") == "get_metric":
            term = str(res.get("term") or (c.get("args") or {}).get("term") or "").strip()
            if not term:
                continue
            temp = res.get("온도") if isinstance(res.get("온도"), dict) else None
            if res.get("has_metric") and temp and temp.get("temp") is not None:
                band = str(temp.get("band") or "").strip()
                metrics.append(f"{term} {temp['temp']}점{f' ({band})' if band else ''}")
            elif res.get("has_metric") is False:
                empty.append(term)
        elif c.get("tool") == "get_salmal_index" and res.get("score") is not None:
            salmal = res

    lines: list[str] = []
    if salmal:
        conf = str(salmal.get("confidence") or "")
        lines.append(f"살말 지수 {salmal['score']}점 · {salmal.get('recommendation') or '보류'}"
                     + (f" (신뢰도 {conf})" if conf else "") + ".")
    if metrics:
        lines.append("확인한 지표: " + " · ".join(metrics[:4]) + ".")
    if empty:
        lines.append("측정 자료가 없던 것: " + " · ".join(dict.fromkeys(empty))[:120] + ".")
    if salmal and salmal.get("missing"):
        missing = [_AXIS_LABEL.get(x, x) for x in salmal["missing"]]
        lines.append("빠진 신호: " + " · ".join(missing) + ".")
    if not lines:
        return ""
    # ★ 사유를 사실대로 (2026-09-18). 바퀴가 바닥난 것을 "시간이 모자라" 라고 적으니
    #   빨리 끝난 답에 시간 핑계가 붙어 어색했다.
    why = ("요약 문장을 쓸 시간이 모자라" if out.stopped == "time_budget"
           else "조회 단계가 길어져 요약 문장 대신")
    lines.append(f"{why} 조회한 것만 정리했습니다. 어느 쪽을 더 볼까요?")
    return "\n\n".join(lines)


def _stop_say(out: Result) -> str:
    """지어내지 않는다. 왜 못 했는지만 말한다."""
    # ★ 도구 결과가 있으면 화면에는 **카드가 다 그려진다.** 그 옆에 "아무것도
    #   못 했다" 는 문구가 붙으면 둘이 서로 어긋난다 — 사용자는 데이터가
    #   가득한 화면을 보면서 실패했다는 말을 읽는다. (2026-09-10 실측)
    #   조회는 됐고 **요약 문장만** 못 쓴 것이니, 그렇게 적는다.
    got = bool(out.trace and out.trace.calls)
    if out.stopped in STOP_SAY:
        # 조회한 것이 있으면 그것을 적는다. 한 줄로 닫는 것은 마지막 수단이다.
        return _recap(out) or STOP_SAY[out.stopped]
    if str(out.stopped).startswith("llm_"):
        # ★ 이건 데이터 문제가 아니라 **모델 응답이 끊긴 것**이다 (2026-09-10).
        #   "지표를 불러오지 못했습니다" 라고 적으면 사용자는 그 용어의 자료가
        #   없다고 읽는다. 실제로 그렇게 읽혔다.
        if got:
            return ("지표는 아래에 담았지만, 요약 문장을 만들다 응답이 끊겼습니다. "
                    "다시 시도할까요?")
        return "답을 만드는 중에 응답이 끊겼습니다. 다시 시도할까요?"
    return ("지금은 답을 만들지 못했습니다 "
            f"({out.stopped or 'unknown'}). 잠시 뒤 다시 물어봐 주세요.")


def _finish(items: list[Any], out: Result, deadline: float | None = None) -> str:
    """도구 없이 마무리 한 번. 여기서도 실패하면 사유를 그대로 돌려준다."""
    # ★ 예산이 다 됐을 때는 **빈손으로 끝내지 않는다**(설계도 부록 10).
    #   세 갈래 중 ②를 고른다 — 확인한 항목을 나열하고 되묻는다.
    #   부분 답변만 주면 사용자가 다음에 뭘 할지 모르고, 재시도 버튼만 주면
    #   지금까지 조회한 것이 버려진다. ②는 둘 다 피하고 다음 바퀴의 입력도 얻는다.
    partial = out.stopped in STOP_SAY
    ask = ("\n\n마지막에 **확인한 항목을 한 줄로 나열하고**, "
           "어느 쪽을 더 볼지 한 가지만 되물어라. 빈손으로 끝내지 마라."
           if partial else "")
    items = list(items) + [{
        "role": "user",
        "content": "더 조회하지 말고, 지금까지 받은 도구 결과만으로 답하라. "
                   "부족한 축은 '아직 측정 자료가 없습니다' 라고 밝혀라." + ask,
    }]
    # ★ 이 호출도 예산 안이다(18번). 남은 시간에서 verify 몫을 뗀 만큼만 쓴다.
    #   예전에는 CALL_TIMEOUT(20초)을 통째로 썼다 — 예산이 끝난 자리에서
    #   20초를 더 쓰니, 예산은 루프의 것일 뿐 답변의 것이 아니었다.
    left = (deadline - time.monotonic()) if deadline else float(CALL_TIMEOUT)
    budget = left - reserve(left, VERIFY_RESERVE)
    if budget < MIN_CALL:
        # 부를 시간이 없다. 빈손으로 끝내지 않고 지금까지 확인한 것으로 닫는다.
        out.stopped = out.stopped or "time_budget"
        return _stop_say(out)
    # budget 은 이미 MIN_CALL 이상이다. 여기서 하한을 또 걸면 마감시각을 넘는다.
    # ★ 역할은 orchestrator 가 아니라 finish 다 (2026-09-10). 여기는 판단이 아니라
    #   정리다 — 생각을 오래 하라고 시키면 정리도 못 하고 끝난다(llm.ROLES 주석).
    # ★ 출력 길이도 묶는다. 안 묶으면 예산은 지켜도 **쓰다가** 끊긴다.
    res = llm.respond(_FINISH_INSTRUCTIONS, items,
                      timeout=min(float(CALL_TIMEOUT), budget),
                      max_output_tokens=FINISH_MAX_TOKENS,
                      **llm.role("finish"))
    if res and res.get("text"):
        return res["text"].strip()
    # ★ Luna 가 막혔거나 빈 답을 냈다 — 시간이 남으면 Sol 로 한 번 (2026-09-18).
    left = (deadline - time.monotonic()) if deadline else float(CALL_TIMEOUT)
    budget = left - reserve(left, VERIFY_RESERVE)
    if budget >= MIN_CALL and llm.can_escalate(bad_output=res is not None):
        out.escalated.append("finish:" + (llm.LAST_ERROR or "empty"))
        res = llm.respond(_FINISH_INSTRUCTIONS, items,
                          timeout=min(float(CALL_TIMEOUT), budget),
                          max_output_tokens=FINISH_MAX_TOKENS,
                          **llm.escalate("finish"))
        if res and res.get("text"):
            return res["text"].strip()
    return _stop_say(out)
