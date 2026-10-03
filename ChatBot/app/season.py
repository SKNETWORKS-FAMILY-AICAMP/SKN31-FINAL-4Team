"""계절·기온 적합도 — 우리 지표가 아니라 **일반 착용 기준**이다.

★ 왜 이 파일이 따로 있나 (2026-09-10)
  "지금 가을인데 이 옷 입을 만해?" 에 챗봇이 "계절·기온 적합도 자료는 아직
  측정 자료가 없습니다" 라고만 답했다. 틀린 말은 아니다 — 수명주기(계절·착용
  예측)는 아직 계산하지 못한다(설계서 6장, report 의 LIFECYCLE_PENDING).
  그런데 사용자가 물은 것은 지표가 아니라 **상식**이다. 반팔이 11월에 맞느냐는
  측정하지 않아도 답할 수 있고, 못 한다고만 말하는 챗봇은 쓸모가 없다.

★ 그렇다고 모델에게 맡기지 않는다. "값은 도구에서만 나온다"(tools.py 머리말).
  모델이 그때그때 판단하면 그 판단은 지어낸 숫자와 같은 자리에 선다 — 검증할
  원본이 없기 때문이다. 그래서 기준을 여기 **눈에 보이게** 적어 두고 도구는 이
  표만 읽는다. 기준이 마음에 안 들면 이 표를 고치면 되고, 고친 것이 그대로 답에 나온다.

★ 이 결과에는 항상 not_feedit_data 가 붙는다. 답변에서 "일반적인 착용 기준"
  이라고 밝혀야 한다. 이걸 측정값처럼 말하는 순간, 진짜 측정한 나머지 지표의
  신뢰까지 같이 깎인다.

★ 표에 없는 말은 **모른다고 한다.** 비슷해 보인다고 끼워 맞추지 않는다.
"""
from __future__ import annotations

# 이름 → (이 기온보다 낮으면 춥다, 이 기온보다 높으면 덥다). None 은 제한 없음.
#   한국 낮 기온 기준이고, 경계에서 ±3°C 는 '애매' 로 본다(_MARGIN).
WEAR_C: dict[str, tuple[int | None, int | None]] = {
    # ── 아우터 ──────────────────────────────────────────
    "패딩": (None, 5), "다운": (None, 5), "무스탕": (None, 8), "퍼": (None, 8),
    "코트": (None, 12), "플리스": (None, 12), "트렌치코트": (5, 18),
    "가죽자켓": (None, 18), "아노락": (8, 20),
    "자켓": (8, 22), "재킷": (8, 22), "블레이저": (8, 22),
    "가디건": (10, 22), "트랙탑": (10, 24), "바람막이": (10, 24), "후드집업": (10, 22),
    # ── 상의 ────────────────────────────────────────────
    "니트": (None, 18), "스웨터": (None, 18), "맨투맨": (8, 22), "후드": (8, 22),
    "스웨트셔츠": (8, 22), "셔츠": (13, 26), "긴팔": (13, 26), "블라우스": (14, 27),
    "티셔츠": (19, None), "반팔": (19, None), "슬리브리스": (24, None), "나시": (24, None),
    # ── 하의 ────────────────────────────────────────────
    "반바지": (22, None), "숏팬츠": (22, None), "치마": (14, None), "스커트": (14, None),
    "청바지": (None, 28), "데님": (None, 28), "슬랙스": (None, None), "팬츠": (None, None),
    # ── 신발 ────────────────────────────────────────────
    "샌들": (22, None), "슬리퍼": (22, None), "부츠": (None, 16),
    # ── 소재 ────────────────────────────────────────────
    "린넨": (22, None), "시어서커": (22, None), "메시": (23, None),
    "울": (None, 15), "캐시미어": (None, 12), "트위드": (None, 16),
    "코듀로이": (None, 18), "플란넬": (None, 18), "스웨이드": (None, 20), "가죽": (None, 18),
    "코튼": (None, None), "면": (None, None), "폴리에스터": (None, None), "나일론": (None, None),
}

# 기온을 못 받았을 때 계절로 대신한다. 서울 낮 기온의 대략값이고, 그렇게 밝힌다.
SEASON_C: dict[str, int] = {"봄": 16, "여름": 28, "가을": 17, "겨울": 2}

_MARGIN = 3          # 경계에서 이만큼은 '애매'


def fit(term: str, temp_c: float) -> dict | None:
    """이 말이 이 기온에 맞나. 표에 없으면 None — 모른다고 말하기 위해서다."""
    rng = WEAR_C.get(str(term or "").strip())
    if rng is None:
        return None
    lo, hi = rng
    t = float(temp_c)
    if lo is None and hi is None:
        return {"term": term, "verdict": "무관",
                "say": "기온을 크게 타지 않는 편입니다."}
    if lo is not None and t < lo - _MARGIN:
        return {"term": term, "verdict": "부적합",
                "say": f"{lo}°C 이상에서 입는 편이라 {t:g}°C 에는 춥습니다."}
    if hi is not None and t > hi + _MARGIN:
        return {"term": term, "verdict": "부적합",
                "say": f"{hi}°C 이하에서 입는 편이라 {t:g}°C 에는 덥습니다."}
    if (lo is not None and t < lo) or (hi is not None and t > hi):
        return {"term": term, "verdict": "애매",
                "say": f"{t:g}°C 는 경계입니다. 겹쳐 입기나 시간대에 따라 갈립니다."}
    band = (f"{lo}~{hi}°C" if lo is not None and hi is not None
            else (f"{lo}°C 이상" if lo is not None else f"{hi}°C 이하"))
    return {"term": term, "verdict": "적합",
            "say": f"{band}에 어울리는 편이라 {t:g}°C 에 맞습니다."}


def temp_for_season(season: str | None) -> tuple[float | None, str]:
    """기온을 못 받았을 때 계절로 대신한다. (기온, 무엇으로 잡았는지)"""
    s = str(season or "").strip()
    for name, c in SEASON_C.items():
        if name in s:
            return float(c), f"{name} 평균 낮 기온({c}°C)으로 잡았습니다"
    return None, ""
