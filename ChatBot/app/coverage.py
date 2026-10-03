"""이 term 에 대해 무엇을 말해도 되는가.

챗봇의 정직함이 여기서 나온다.
데이터가 없는데 답하면 지어내는 것이고, 있는데 안 답하면 쓸모가 없다.
그 경계를 한 곳에서 정한다.

2026-09-02 실측 (최신 2026-09-01, term 509개, source `__all__`)

    축         term   n7>=3  n14>=5  n28>=10   최신일에 있음
    style        34      17      12        8            32
    item        111      56      43       37            96
    material     64      30      24       14            56
    brand       223       2       1        0           200   ← 방향을 말할 수 없다
    detail       41      18      13       13            31
    fit/color/tpo 36       0       0        0            36   ← 시계열이 아예 없다

브랜드가 223개 중 ma7 가능 2개다. **브랜드에 "오르는 중"이라고 말하면 안 된다.**
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from .config import MIN_OBS_7, MIN_OBS_14, MIN_OBS_28, THIN_SAMPLE


@dataclass
class Coverage:
    """무엇을 말해도 되는지 켜고 끄는 스위치 묶음."""
    has_latest: bool = False        # 최신 스냅샷이 있나
    can_level: bool = False         # 지금 온도·언급량을 말해도 되나
    can_direction: bool = False     # 오르는지 내리는지 말해도 되나
    can_delta14: bool = False       # 2주 변화를 말해도 되나
    can_assoc: bool = False
    can_sentiment: bool = False
    thin_sample: bool = False       # 표본이 적어 경고를 붙여야 하나
    stale_days: int = 0             # 이 term 의 최신 관측이 며칠 묵었나
    obs7: int = 0
    obs14: int = 0
    obs28: int = 0
    reasons: list = None            # 못 하는 것마다 왜 못 하는지

    def as_dict(self):
        d = asdict(self)
        d["reasons"] = self.reasons or []
        return d


def assess(trend: dict | None, sentiment: dict | None, assoc_count: int,
           reason: str | None = None) -> Coverage:
    """무엇을 말해도 되는지. trend 는 trend_view.trend_summary() 의 결과다.

    ★ 2026-10-01 — 관측 일수와 표본을 **트렌드 분석 화면과 같은 시계열**에서 센다.
      예전엔 지표 표를 따로 읽어 표본을 **하루치** 언급 수로 쟀다(raw < 20 이면 표본 부족).
      그러면 거의 모든 용어가 '표본 부족' 이 되어 화면과 다른 판단을 했다.
      지금은 최근 28일 언급 합계로 잰다.
    """
    c = Coverage(reasons=[])
    if not trend:
        c.reasons.append(("NO_METRIC", reason or "이 말은 사전에는 있지만 아직 수집된 언급이 없습니다."))
        return c

    c.has_latest = True
    c.can_level = True
    m28 = int(trend.get("mention_28d") or 0)
    c.thin_sample = bool(trend.get("thin"))
    if c.thin_sample:
        c.reasons.append(("THIN_SAMPLE",
                          f"최근 28일 언급이 {m28}건뿐이라 값이 크게 흔들립니다."))

    obs = trend.get("obs") or {}
    c.obs7, c.obs14, c.obs28 = int(obs.get("n7") or 0), int(obs.get("n14") or 0), int(obs.get("n28") or 0)

    c.can_direction = c.obs28 >= MIN_OBS_28 and c.obs7 >= MIN_OBS_7
    if not c.can_direction:
        c.reasons.append(("SHORT_HISTORY",
                          f"최근 28일 중 관측이 {c.obs28}일뿐이라 "
                          f"오르는지 내리는지 말할 수 없습니다."))

    c.can_delta14 = c.obs14 >= MIN_OBS_14
    if not c.can_delta14:
        c.reasons.append(("SHORT_HISTORY_14",
                          f"최근 14일 중 관측이 {c.obs14}일뿐이라 2주 변화를 낼 수 없습니다."))

    c.can_assoc = assoc_count > 0
    if not c.can_assoc:
        c.reasons.append(("NO_ASSOC", "아직 계산된 연관어가 없습니다."))

    n_sent = int(((sentiment or {}).get("반응") or {}).get("합계") or 0)
    c.can_sentiment = bool(sentiment) and n_sent > 0
    if not c.can_sentiment:
        c.reasons.append(("NO_SENTIMENT", "긍부정을 판단할 반응이 아직 없습니다."))
    elif not sentiment.get("judged"):
        c.reasons.append(("THIN_SENTIMENT",
                          f"최근 28일 반응이 {n_sent}건이라 판단을 보류합니다 "
                          f"({THIN_SAMPLE}건 이상이면 판정)."))

    c.stale_days = int(trend.get("stale_days") or 0)
    return c


def direction(latest: dict) -> dict | None:
    """방향은 온도로 말하지 않는다. ma7/ma28 배수로 말한다.

    이유 — momentum 이 포화돼 있다. 2026-09-01 기준 451개 중 410개(90.9%)가 99 이상이다.
    `momentum = 100/(1+exp(-6*(ma7/ma28-1)))` 에서 수집량이 계속 늘어
    ma7/ma28 이 항상 1을 넘고 시그모이드가 천장에 붙었다.
    그래서 `temp = 0.6*level + 0.4*momentum` 이 사실상 `0.6*level + 40` 이다.
    온도로는 오르는지 식는지 구분할 수 없다.
    """
    ma7 = float(latest.get("ma7") or 0)
    ma28 = float(latest.get("ma28") or 0)
    if ma28 <= 0:
        return None
    ratio = ma7 / ma28
    if ratio >= 1.5:
        label, tone = "가파른 상승", "up"
    elif ratio >= 1.1:
        label, tone = "완만한 상승", "up"
    elif ratio >= 0.9:
        label, tone = "평평함", "flat"
    else:
        label, tone = "내려오는 중", "down"
    return {"ratio": round(ratio, 2), "label": label, "tone": tone,
            "ma7": round(ma7, 2), "ma28": round(ma28, 2)}
