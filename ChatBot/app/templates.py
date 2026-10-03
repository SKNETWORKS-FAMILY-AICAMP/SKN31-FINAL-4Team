"""의도 → 어떤 블록을 쓸 것인가. **레지스트리 하나가 원본이다.**

여기 없는 조합은 나올 수 없다. 그게 요점이다.
프롬프트로 구조를 만들게 하면 매번 달라지고, 없는 클래스를 지어내고, 숫자가 샌다.

화면(트렌드 탭 EDIT 6종)이 이미 정해 둔 골격을 따른다 —
    결론 → 요약 수치 → 근거(차트·표) → 어떻게 읽나
챗봇 팝업은 폭이 좁아 차트를 빼고 표와 막대만 쓴다.
"""
from __future__ import annotations

from . import blocks as B

# 의도마다 어떤 걸 채울지. 순서가 곧 화면 순서다.
#   'compare' 는 term 이 둘 이상일 때만 뜬다 (블록 함수가 None 을 돌려준다).
PLAN = {
    "metric.level":     ["rank", "sources", "evidence", "notes"],
    "metric.direction": ["direction", "rank", "sources", "notes"],
    "metric.compare":   ["compare", "rank", "sources", "notes"],
    "metric.platform":  ["rank", "platform_temp", "sources", "notes"],
    "metric.assoc":     ["assoc", "assoc_axis", "notes"],
    "metric.sentiment": ["sentiment", "sentiment_signal", "rank", "evidence", "notes"],
    "metric.lifecycle": ["rank", "sources", "notes"],       # 수명주기 표가 생기면 여기 추가
    "knowledge.origin": ["web", "rank", "notes"],
    "buy.verdict":      ["rank", "sources", "notes"],       # 살!말?지수가 생기면 verdict 가 맨 앞
    "buy.price":        ["rank", "sources", "notes"],
    "buy.longevity":    ["rank", "sources", "notes"],
    "buy.alternative":  ["assoc", "rank", "notes"],
    "buy.opinion":      ["sentiment", "evidence", "notes"],
    "buy.tryon":        ["rank", "sources", "notes"],
}
DEFAULT = ["rank", "sources", "notes"]

# LLM 이 고를 수 있는 후보. **이 목록 밖은 못 만든다.**
CHOOSABLE = ["rank", "direction", "sources", "platform_temp", "assoc", "assoc_axis",
             "sentiment", "sentiment_signal", "evidence", "compare"]


def build(intent: str, nodes: list[dict], rep: dict, as_of: str,
          extra: list[str] | None = None) -> list[dict]:
    """리포트에 넣을 블록 배열. None 을 돌려준 블록은 조용히 빠진다."""
    want = list(PLAN.get(intent, DEFAULT))
    for e in (extra or []):
        if e in CHOOSABLE and e not in want:
            want.insert(max(0, len(want) - 1), e)      # notes 앞에 끼워 넣는다

    t = nodes[0]
    out: list[dict] = []
    for name in want:
        got = None
        if name == "rank":            got = B.b_metric_rank(t, as_of)
        elif name == "direction":     got = B.b_direction(t)
        elif name == "sources":       got = B.b_sources(t, as_of)
        elif name == "platform_temp": got = B.b_platform_temp(t, as_of)
        elif name == "assoc":         got = B.b_assoc(t)
        elif name == "assoc_axis":    got = B.b_assoc_axis(t)
        elif name == "sentiment":     got = B.b_sentiment(t)
        elif name == "sentiment_signal": got = B.b_sentiment_signal(t)
        elif name == "evidence":      got = B.b_evidence(t)
        elif name == "compare":       got = B.b_compare(nodes, as_of)
        elif name == "web":
            if rep.get("web"):
                out.extend(B.b_web(rep["web"], t))
            continue
        elif name == "notes":
            out.extend(B.b_notes(rep.get("notes")))
            continue
        if got:
            out.append(got)

    if rep.get("upsell"):
        out.append(B.b_upsell(rep["upsell"]))

    # 오른쪽이 비면 왼쪽이 혼자 넓게 남는다. 근거라도 채운다.
    if not any(b["slot"] == "right" for b in out):
        ev = B.b_evidence(t)
        if ev:
            out.append(ev)
    return out
