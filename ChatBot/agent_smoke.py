"""새 경로(오케스트레이터) 스모크 — 같은 질문을 두 설정으로 돌려 비교한다.

★ 왜 파일로 두나
  zsh 에서 heredoc 으로 붙여넣으면 `#` 주석과 `─` 같은 문자가 깨진다.
  A/B 를 여러 번 돌릴 것이므로 파일로 둔다.

쓰는 법
    cd ChatBot
    python3 agent_smoke.py                                  # 지금 .env 설정 그대로
    FEEDIT_LLM_MODEL_MID=gpt-5.6-terra python3 agent_smoke.py   # L1 만 terra 로
    FEEDIT_CHAT_TIME_BUDGET=14 python3 agent_smoke.py           # 예산만 올려서
                                                                # (예산 = 답변 하나의 전체 시간)
    python3 agent_smoke.py "니트 요즘 어때?"                     # 질문을 직접 주기

보는 곳
    도구      같은 도구를 인자만 바꿔 반복하지 않는가 (MAX_PER_TOOL=3)
    stopped   done 이 아니면 무엇에 걸렸나. llm_* 는 모델 호출 실패다
    부분      끊긴 답변에 표시가 붙는가
    의심      verify 가 잡은 숫자. 비어 있어야 정상이다
    ms        예산(전체)을 넘지 않아야 한다. 넘으면 예산 밖에서 부르는 층이 있다
"""
from __future__ import annotations

import sys
import time

from app import llm
from app.engine import ChatEngine

# 인수인계 문서가 "기존 경로가 깨진다" 고 지목한 셋 + 도메인 밖 하나
기본질문 = [
    "살로몬 XT-6 지금 사도 돼?",   # 사전에 없는 브랜드·제품명
    "요즘 뭐가 핫해?",             # 답이 용어인 질문
    "오버핏 니트 어때?",           # 사전이 잡는 질문 — 대조군
    "오늘 날씨 어때?",             # 도메인 밖
]


def main() -> int:
    질문들 = sys.argv[1:] or 기본질문

    e = ChatEngine()
    print("=" * 70)
    print(" 설정")
    for r in ("orchestrator", "verify", "polish"):
        d = llm.role(r)
        print(f"   {r:14s} {d.get('model'):18s} effort={d.get('effort')}")
    try:
        from app import orchestrator as O
        loop = O.TIME_BUDGET - O.reserve(O.TIME_BUDGET, O.TAIL_RESERVE)
        print(f"   {'시간 예산(전체)':14s} {O.TIME_BUDGET}초 "
              f"(루프 {loop:.1f} + 뒷정리 {O.TIME_BUDGET - loop:.1f}) "
              f"· 최대 {O.MAX_ROUNDS}바퀴 · 도구당 {O.MAX_PER_TOOL}회")
    except Exception:                                    # noqa: BLE001
        pass
    print("=" * 70)

    요약 = []
    for q in 질문들:
        t0 = time.monotonic()
        out = e.ask(q, mode="general")
        벽시계 = int((time.monotonic() - t0) * 1000)

        tr = out.get("trace") or {}
        v = tr.get("verify") or {}
        의심 = v.get("suspect_numbers") or []
        본문 = (out.get("headline") or out.get("message") or "(빈 답변)")

        print("-" * 70)
        print("Q :", q)
        print(f"경로: {out.get('kind')} | 바퀴: {tr.get('rounds')} "
              f"| 호출: {tr.get('calls')} | {tr.get('stopped')} "
              f"| 부분: {out.get('partial')} | {벽시계}ms")
        print("도구:", tr.get("tools"))
        print("A :", 본문[:320].replace("\n", " "))
        if 의심 or v.get("removed") or v.get("skipped"):
            print("검증:", {"의심숫자": 의심, "지운것": v.get("removed"),
                          "건너뜀": v.get("skipped")})
        print("블록:", [b.get("type") for b in (out.get("blocks") or [])])

        요약.append({
            "질문": q[:16],
            "경로": out.get("kind"),
            "바퀴": tr.get("rounds"),
            "호출": tr.get("calls"),
            "stopped": tr.get("stopped"),
            "ms": 벽시계,
            "의심": len(의심),
            "빈답변": not (out.get("headline") or out.get("message")),
        })

    print("=" * 70)
    print(f"{'질문':18s} {'경로':6s} {'바퀴':>3s} {'호출':>3s} {'ms':>7s} "
          f"{'의심':>3s}  stopped")
    for s in 요약:
        print(f"{s['질문']:18s} {str(s['경로']):6s} {str(s['바퀴']):>3s} "
              f"{str(s['호출']):>3s} {s['ms']:>7d} {s['의심']:>3d}  {s['stopped']}")

    나쁨 = [s for s in 요약
            if s["의심"] or s["빈답변"] or str(s["stopped"] or "").startswith("llm_")]
    print()
    print("문제 있는 질문:", len(나쁨), "/", len(요약))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
