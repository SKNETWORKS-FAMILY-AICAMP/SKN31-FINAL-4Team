"""검증된 신호만으로 0~100 살말 지수를 계산한다.

점수는 추천 그 자체가 아니라 판단 보조 지표다. 없는 축은 50으로 메우지 않고
분모에서 제외한다. 그래서 ``coverage``가 낮으면 같은 점수라도 낮은 신뢰도로
표시된다. 커뮤니티 투표는 다른 사람의 의견이므로 전체 가중치의 5%만 차지한다.
"""
from __future__ import annotations

import re
from typing import Any


WEIGHTS = {"taste": 35, "behavior": 25, "trend": 20, "price": 15, "community": 5}


def _number(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, n))


def _names(values: Any) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(v).strip().casefold() for v in values if str(v).strip()}


def _squash(text: str) -> str:
    """띄어쓰기·구두점을 지운 비교용 표기.

    "미디 스커트" 와 "미디스커트" 는 사람에게 같은 말인데 문자열로는 다르다.
    비교 전에 한 번 눌러 둔다.
    """
    return re.sub(r"[\s·\-_/,]+", "", str(text or "").strip().casefold())


def _overlap(targets: set[str], vocab: dict[str, str]) -> list[str]:
    """상품 쪽 말(targets)과 취향 쪽 말(vocab)이 겹치는 지점을 돌려준다.

    ★ 왜 완전 일치가 아닌가 (2026-09-11)
      취향은 스타일 이름("블록코어")으로, 상품은 아이템 이름("벌룬 카고 미디
      스커트")으로 들어온다. 완전 일치로 비교하면 두 어휘가 만나는 일이
      사실상 없어서, 취향 축은 늘 "겹치는 태그가 없음"으로 떨어졌다.
      그래서 스타일의 대표 어휘(vocab)를 함께 받아 **포함 관계**로 본다.
      두 글자 미만은 보지 않는다 — 우연히 겹친다.

    vocab 은 {비교용 표기: 사람에게 보여 줄 이름} 이다.
    """
    hits: list[str] = []
    squashed = [(_squash(t), t) for t in targets]
    for key, label in vocab.items():
        if len(key) < 2:
            continue
        for tgt, _raw in squashed:
            if len(tgt) < 2:
                continue
            if key in tgt or tgt in key:
                if label not in hits:
                    hits.append(label)
                break
    return hits


def _style_vocab(ctx: dict) -> tuple[dict[str, str], list[str]]:
    """즐겨입는 스타일에서 비교용 어휘를 만든다.

    profiles 는 프런트가 보내는 [{name, keywords:[…]}] 로, 가입할 때 고른
    스타일과 그 스타일의 대표 키워드다(STYLES.kw). 키워드가 없으면 이름만으로
    비교한다 — 그때는 예전과 같은 정확도다.
    """
    vocab: dict[str, str] = {}
    picked: list[str] = []
    profiles = ctx.get("favorite_style_profiles")
    if isinstance(profiles, (list, tuple)):
        for item in profiles:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            picked.append(name)
            vocab.setdefault(_squash(name), name)
            keywords = item.get("keywords")
            if isinstance(keywords, (list, tuple)):
                for kw in keywords:
                    key = _squash(kw)
                    if key:
                        vocab.setdefault(key, f"{name}({str(kw).strip()})")
    for name in _names(ctx.get("favorite_styles")):
        vocab.setdefault(_squash(name), name)
        if name not in [p.casefold() for p in picked]:
            picked.append(name)
    return vocab, picked


def calculate(*, term: str = "", product_tags: list[str] | None = None,
              taste_context: dict | None = None, trend: dict | None = None,
              price: dict | None = None, community: dict | None = None) -> dict:
    """사용 가능한 축만 가중 평균하고 근거·결측을 함께 돌려준다."""
    ctx = taste_context if isinstance(taste_context, dict) else {}
    targets = _names([term, *(product_tags or [])])
    signals: dict[str, dict] = {}

    style_vocab, style_names = _style_vocab(ctx)
    if targets and style_vocab:
        matched = _overlap(targets, style_vocab)
        if matched:
            signals["taste"] = {"score": 100, "label": "취향 일치",
                                "why": "가입할 때 고른 즐겨입는 스타일과 겹칩니다: "
                                       + " · ".join(matched[:3])}
        elif product_tags:
            picked = " · ".join(style_names[:3]) if style_names else "선택한 스타일"
            signals["taste"] = {"score": 25, "label": "취향 거리",
                                "why": f"즐겨입는 스타일({picked})과 겹치는 "
                                       "요소를 찾지 못했습니다."}

    searched = {_squash(v): v for v in _names(ctx.get("searched_terms")) if _squash(v)}
    saved = {_squash(v): v for v in _names(ctx.get("saved_terms")) if _squash(v)}
    if targets and (searched or saved):
        saved_hit = _overlap(targets, saved)
        search_hit = _overlap(targets, searched)
        if saved_hit:
            signals["behavior"] = {"score": 100, "label": "찜 신호",
                                   "why": "찜한 아이템/키워드와 연결됩니다: "
                                          + " · ".join(saved_hit[:3])}
        elif search_hit:
            signals["behavior"] = {"score": 82, "label": "검색 신호",
                                   "why": "최근 찾아본 키워드와 연결됩니다: "
                                          + " · ".join(search_hit[:3])}
        elif product_tags:
            signals["behavior"] = {"score": 30, "label": "행동 거리",
                                   "why": "최근 검색·찜 기록과 직접 겹치지 않습니다."}

    trend_score = _number((trend or {}).get("temp"))
    if trend_score is not None:
        signals["trend"] = {"score": trend_score, "label": "트렌드",
                            "why": f"트렌드 온도 {round(trend_score)}점 기준"}

    discount = _number((price or {}).get("discount_rate"))
    if discount is not None:
        # 할인 0%는 중립보다 낮게, 50% 이상은 상한으로 본다.
        price_score = min(100.0, 35.0 + discount * 1.3)
        signals["price"] = {"score": price_score, "label": "가격",
                            "why": f"확인된 할인율 {round(discount, 1)}% 기준"}

    buy_pct = _number((community or {}).get("buy_pct"))
    votes = int((community or {}).get("total") or 0)
    if buy_pct is not None and votes > 0:
        signals["community"] = {"score": buy_pct, "label": "커뮤니티 참고",
                                "why": f"살 의견 {round(buy_pct)}% · {votes:,}표 (참고 신호)"}

    # ★ 왜 빠졌는지를 같이 준다 (2026-09-18). 로그인해서 스타일을 골랐는데도 '취향: 빠진
    #   신호' 만 보이면, 사용자는 로그인이 안 잡힌 줄 안다. 실제로는 상품의 스타일을 몰라
    #   비교할 대상이 없었던 것이다.
    why_missing: dict[str, str] = {}
    if "taste" not in signals:
        why_missing["taste"] = ("상품의 스타일을 확인하지 못해 즐겨입는 스타일과 비교하지 못했습니다"
                                if style_vocab else
                                "로그인하지 않았거나 가입할 때 고른 스타일이 없습니다")

    available_weight = sum(WEIGHTS[k] for k in signals)
    if not available_weight:
        return {"score": None, "recommendation": "판단 자료 부족", "confidence": "낮음",
                "coverage": 0, "signals": [], "missing": list(WEIGHTS),
                "missing_why": why_missing, "recommendation_allowed": False}

    score = round(sum(v["score"] * WEIGHTS[k] for k, v in signals.items()) / available_weight)
    coverage = round(available_weight / sum(WEIGHTS.values()) * 100)
    if coverage < 40:
        recommendation, allowed = "보류", False
    elif score >= 67:
        recommendation, allowed = "살", True
    elif score <= 43:
        recommendation, allowed = "말", True
    else:
        recommendation, allowed = "보류", True
    confidence = "높음" if coverage >= 75 else "보통" if coverage >= 50 else "낮음"
    return {
        "score": score, "recommendation": recommendation, "confidence": confidence,
        "coverage": coverage, "signals": [dict(key=k, weight=WEIGHTS[k], **v)
                                           for k, v in signals.items()],
        "missing": [k for k in WEIGHTS if k not in signals],
        "missing_why": why_missing,
        "recommendation_allowed": allowed,
        "formula": "취향 35 · 검색/찜 25 · 트렌드 20 · 가격 15 · 커뮤니티 5",
    }
