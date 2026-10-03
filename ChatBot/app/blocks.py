"""응답을 '블록'으로 만든다 — 질문 유형마다 구조가 달라지게.

왜 프롬프트만으로 안 하나
  1. 화면이 깨진다. LLM 이 없는 CSS 클래스를 지어내면 버튼이 맨 글자로 나온다.
     (AGENTS.md §4.2 가 적어 둔 실제 사고다)
  2. 매번 다르게 나온다. 같은 질문에 어제와 오늘의 구조가 다르면 그건 제품이 아니다.
  3. 숫자가 샌다. 구조를 LLM 이 만들면 그 안의 값도 LLM 이 쓰게 된다.

그래서 구조는 **서버가 정한 목록에서 고른다.**
  · 어떤 블록이 있는지는 여기(blocks.py)가 정한다 — 프론트에 실제로 있는 것만.
  · 의도마다 어떤 블록을 쓸지는 templates.py 가 정한다.
  · LLM 은 애매할 때 **후보 중에서 고르는 것**만 한다. 새로 만들지 못한다.

슬롯 세 개
  full   카드 위 전체 폭 (판정 다이얼 같은 것)
  left   카드 왼쪽 (넓다 · 1.15fr)
  right  카드 오른쪽 (1fr)
"""
from __future__ import annotations

from datetime import date as _date

from .config import THIN_SAMPLE, temp_band

FACET_KO = {"style": "스타일", "item": "아이템", "material": "소재", "brand": "브랜드",
            "fit": "핏", "color": "컬러", "detail": "디테일", "tpo": "TPO"}


# ── 개별 블록 ─────────────────────────────────────────
TONE_KO = {"positive": "긍정", "negative": "부정", "mixed": "엇갈림", "neutral": None}


def b_metric_rank(t: dict, as_of: str) -> dict | None:
    """지표를 행으로. 가장 기본이 되는 블록.

    ★ 2026-10-01 — 값은 트렌드 분석 화면과 같은 것이다(report.build_term → trend_view).
      · 온도 옆 말은 화면 제목의 판정(뜨거움·달아오르는 중 …)을 그대로 쓴다.
      · 언급량은 **최근 28일 합계**다. 예전엔 마지막 하루 행이라 '1건' 이 찍혔다.
      · 순위는 그날 언급된 전체 용어 중 백분위(0~100)다.
    """
    if not t.get("available"):
        return {"type": "rank", "slot": "left", "title": t["canonical"],
                "meta": (t.get("facet_name") or "") + " · " + as_of,
                "rows": [{"k": t.get("reason") or "아직 수집된 언급이 없습니다",
                          "small": "사전에는 있습니다", "v": "0건", "up": False}]}
    rows = []
    if t.get("temp") is not None:
        rows.append({"k": "트렌드 온도", "small": t.get("temp_verdict") or t.get("temp_band"),
                     "v": f"{t['temp']}점", "up": t["temp"] >= 65})
    if t.get("raw_count") is not None:
        window = t.get("mention_window")
        rows.append({"k": "언급량",
                     "small": f"최근 {window}일" if window else
                              (f"{len(t.get('sources') or [])}개 소스" if t.get("sources") else ""),
                     "v": f"{int(t['raw_count']):,}건", "up": int(t["raw_count"]) >= 20})
    if t.get("pct_rank") is not None:
        top = t.get("top_pct")
        if top is None:
            top = max(1, 100 - round(float(t["pct_rank"])))
        rows.append({"k": "순위", "small": "그날 전체 용어 중",
                     "v": f"상위 {top}%",
                     "up": float(t["pct_rank"]) >= 50})
    meta_day = t.get("observed_on") or as_of
    return {"type": "rank", "slot": "left", "title": t["canonical"],
            "meta": (t.get("facet_name") or "") + " · " + str(meta_day), "rows": rows}


# 비율 칸의 설명. coverage.direction() 의 구간과 같은 말을 쓴다.
_RATIO_NOTE = {
    "up": "1.1 이상이면 오르는 중",
    "flat": "0.9~1.1 은 변화 없음",
    "down": "0.9 미만이면 내리는 중",
}


def b_direction(t: dict) -> dict | None:
    """방향만 크게. '꺾였어?' 에는 온도보다 이게 답이다."""
    d = t.get("direction")
    if not d:
        cov = t.get("coverage") or {}
        return {"type": "note", "slot": "left",
                "text": f"최근 28일 중 관측이 {cov.get('obs28', 0)}일뿐이라 "
                        f"오르는지 내리는지 말할 수 없습니다."}
    return {"type": "kpis", "slot": "full", "title": t.get("canonical") or "",
            "meta": t.get("facet_name") or "", "items": [
        {"k": "온도 방향", "v": d["label"], "unit": "", "note": "최근 7일 대 4주", "up": d["tone"] == "up"},
        # ★ 문턱을 여기서 따로 정하지 않는다 (2026-09-09).
        #   note 가 늘 "1보다 크면 오르는 중" 이고 up 이 ratio>=1 이라,
        #   coverage 가 **평평함**(0.9~1.1)이라고 판정한 1.03 이 바로 옆 칸에서
        #   상승색으로 "오르는 중" 이라고 강조됐다. 같은 카드 줄 안에서
        #   '평평함' 과 '오르는 중' 이 나란히 있고, 본문은 "식은 상태" 라고 썼다.
        #   판정 근거는 coverage.direction 의 tone 하나뿐이어야 한다.
        {"k": "온도 7일/4주 비율", "v": f"{d['ratio']}", "unit": "배",
         "note": _RATIO_NOTE.get(d.get("tone"), ""),
         "up": d.get("tone") == "up"},
        {"k": "온도 7일 평균", "v": f"{d['ma7']}", "unit": "", "note": "", "up": True},
        {"k": "온도 4주 평균", "v": f"{d['ma28']}", "unit": "", "note": "", "up": True},
    ]}


def b_sources(t: dict, as_of: str) -> dict | None:
    src = t.get("sources") or []
    if not src:
        return None
    mx = max((s.get("raw_count") or 0) for s in src) or 1
    return {"type": "bars", "slot": "right", "title": _of(t, "플랫폼별 언급량"), "meta": as_of,
            "items": [{"k": s["name"], "w": round(100 * (s.get("raw_count") or 0) / mx),
                       "v": f"{int(s.get('raw_count') or 0):,}"} for s in src]}


def b_platform_temp(t: dict, as_of: str) -> dict | None:
    """플랫폼별 '온도'. 언급량 막대와 다른 질문에 답한다 —
       '어디서 많이 나오나' 가 아니라 '어디가 더 뜨거운가'."""
    src = [s for s in (t.get("sources") or []) if s.get("temp") is not None]
    if not src:
        return None
    return {"type": "table", "slot": "right", "title": _of(t, "플랫폼별 온도"), "meta": "0–100",
            "head": ["플랫폼", "", "온도"],
            "rows": [{"k": s["name"], "w": int(s["temp"]), "v": f"{int(s['temp'])}°",
                      "up": int(s["temp"]) >= 65} for s in src]}


def _of(t: dict, label: str) -> str:
    """어느 용어의 지표인지 제목에 밝힌다. 둘 이상 나란히 놓여도 구분되게."""
    name = t.get("canonical")
    return f"{name} {label}" if name else label


def b_assoc(t: dict) -> dict | None:
    a = t.get("associations") or []
    if not a:
        return None
    return {"type": "rank", "slot": "left", "title": _of(t, "연관어"),
            "meta": f"{len(a)}개",
            "rows": [{"k": x["canonical"],
                      "small": x.get("facet_name", "") + (" · NEW" if x.get("is_new") else ""),
                      "v": (f"{int(x['co_count']):,}회" if x.get("co_count") else
                            "검색 신호" if "search" in (x.get("basis") or []) else "언급 수 없음"),
                      "up": True} for x in a[:6]]}


def b_assoc_axis(t: dict) -> dict | None:
    """연관어를 축별로 묶어 비중을 보여 준다. 화면 연관어 파트의 '축별 비중'."""
    a = t.get("associations") or []
    if not a:
        return None
    agg: dict[str, int] = {}
    for x in a:
        agg[x.get("facet_name") or "기타"] = agg.get(x.get("facet_name") or "기타", 0) + 1
    mx = max(agg.values()) or 1
    return {"type": "bars", "slot": "right", "title": _of(t, "연관어 축별 비중"), "meta": "연관어 수",
            "items": [{"k": k, "w": round(100 * v / mx), "v": str(v)}
                      for k, v in sorted(agg.items(), key=lambda x: -x[1])]}


def b_sentiment(t: dict) -> dict | None:
    """긍부정 결론 — 트렌드 분석 긍부정 탭의 다이얼·비율과 같은 값(최근 28일 합계)."""
    s = t.get("sentiment")
    if not s or s.get("unavailable"):
        return None
    r = s.get("반응") or {}
    dial = s.get("dial")
    return {"type": "kpis", "slot": "full", "title": _of(t, "긍부정"),
            "meta": f"{t.get('facet_name') or ''} · 최근 {s.get('window_days', 28)}일".strip(" ·"), "items": [
        {"k": s.get("dial_label") or "긍정 우위 %", "v": "–" if dial is None else str(dial),
         "unit": "" if dial is None else ("점" if s.get("purchase_intent_index") is not None else "%"),
         "note": f"{s.get('verdict')} · 반응 {int(r.get('합계') or 0):,}건",
         "up": bool(s.get("judged")) and (dial or 0) >= 55},
        {"k": "긍정 반응 비율", "v": "–" if s.get("positive_pct") is None else str(s["positive_pct"]),
         "unit": "" if s.get("positive_pct") is None else "%",
         "note": f"최근 {s.get('window_days', 28)}일 · {int(r.get('긍정') or 0):,}건", "up": True},
        {"k": "부정 반응 비율", "v": "–" if s.get("negative_pct") is None else str(s["negative_pct"]),
         "unit": "" if s.get("negative_pct") is None else "%",
         "note": f"최근 {s.get('window_days', 28)}일 · {int(r.get('부정') or 0):,}건", "up": False},
    ]}


def b_sentiment_signal(t: dict) -> dict | None:
    """긍부정을 '몇 %' 가 아니라 '몇 건' 으로 — 화면의 '신호 유형별 건수' 표와 같은 6칸.

    순서는 DB 칸 순서(질문·구매·경험·호평·비판·잡담)로 고정한다. 건수로 줄 세우면
    날마다 자리가 바뀌어 비교가 안 된다. 0건도 지우지 않는다 — '없었다' 도 결과다.
    """
    s = t.get("sentiment")
    if not s or s.get("unavailable"):
        return None
    sig = s.get("signals") or {}
    if not sig:
        return None
    from .trend_view import SIGNALS
    mx = max([int(v or 0) for v in sig.values()] + [1])
    rows = [{"k": name, "w": round(100 * int(sig.get(name) or 0) / mx),
             "v": f"{int(sig.get(name) or 0):,}건", "up": pol > 0}
            for name, _f, pol in SIGNALS if name in sig]
    r = s.get("반응") or {}
    return {"type": "table", "slot": "right", "title": _of(t, "신호 유형별 건수"),
            "meta": f"최근 {s.get('window_days', 28)}일 · 반응 {int(r.get('합계') or 0):,}건",
            "head": ["신호 유형", "", "건수"], "rows": rows}


def b_evidence(t: dict) -> dict | None:
    """근거 인용.

    본문 전체가 아니라 '이 대목 때문에 그렇게 셌다' 하는 짧은 span 만 싣는다.
    긴 원문을 잘라 붙이면 말이 중간에서 끊기고, 그 term 과 무관한 문장이 딸려온다.
    """
    ev = t.get("evidence") or []
    if not ev:
        return None
    items = []
    for e in ev[:3]:
        body = str(e.get("body") or "").strip()
        if len(body) < 6:
            continue
        items.append({"src": e.get("source"), "kind": e.get("kind"),
                      "tone": TONE_KO.get(e.get("tone")), "body": body})
    if not items:
        return None
    return {"type": "quotes", "slot": "right", "title": "근거가 된 대목",
            "meta": f"{len(items)}건", "items": items}


def b_compare(nodes: list[dict], as_of: str) -> dict | None:
    """둘 이상을 나란히. '무신사 vs 29CM' 같은 질문의 답."""
    ok = [n for n in nodes if n.get("available")]
    if len(ok) < 2:
        return None
    mx = max(int(n.get("temp") or 0) for n in ok) or 1
    # ★ 무슨 점수인지 제목에 밝힌다 (2026-10-02) — "나란히 보기 · 86점" 만으로는 트렌드 온도인지
    #   살말 지수인지 알 수 없었다.
    return {"type": "bars", "slot": "full", "title": "트렌드 온도 나란히 보기",
            "meta": " · ".join(x for x in ("점 = 트렌드 온도(0~100)", as_of) if x),
            "items": [{"k": n["canonical"], "w": round(100 * int(n.get("temp") or 0) / mx),
                       "v": f"{int(n.get('temp') or 0)}점"} for n in ok]}


def b_web(web: dict, t: dict) -> list[dict]:
    out = [{"type": "prose", "slot": "left", "title": t["canonical"], "meta": "웹에서 찾음",
            "text": web["answer"]}]
    if web.get("sources"):
        out.append({"type": "links", "slot": "left", "items": web["sources"][:4]})
    return out


def b_upsell(up: dict) -> dict:
    return {"type": "upsell", "slot": "right", "title": "더 볼 수 있는 것", "meta": "PRO",
            "why": up.get("why"), "unlocks": (up.get("unlocks") or [])[:4]}


def b_notes(notes: list[dict], limit: int = 3) -> list[dict]:
    return [{"type": "note", "slot": "left", "text": n["message"]} for n in (notes or [])[:limit]]


# ══════════════════════════════════════════════════════════
#  리포트 템플릿용 그림 블록 (2026-10-02)
# ──────────────────────────────────────────────────────────
#  질문 유형마다 한눈에 읽히는 그림이 다르다 — 진단은 티커, 원인은 주석 그래프,
#  비교는 VS, 순위는 리더보드, 연관은 오빗, 살말은 판정 도장, 관측이 얇으면 정직한
#  빈 상태. 어떤 템플릿을 쓸지는 report_skill.choose_template 이 정한다.
#
#  ★ 여기서도 값을 만들지 않는다. 노드(report.build_term)와 도구 결과에 있는 값만
#    옮겨 담고, 그림의 축·위치는 화면(chat_api.js)이 계산한다.
#  ★ 없는 값은 None 으로 둔다. 화면은 None 인 칸을 그리지 않는다 — 0 으로 채우면
#    "변화 없음" 처럼 읽힌다.
# ══════════════════════════════════════════════════════════
def _days_between(a: str, b: str) -> int | None:
    try:
        return (_date.fromisoformat(str(b)[:10]) - _date.fromisoformat(str(a)[:10])).days
    except (TypeError, ValueError):
        return None


def _recent(rows: list[dict], days: int) -> list[dict]:
    """마지막 행 기준 최근 days 일 안의 행만."""
    rows = [r for r in (rows or []) if isinstance(r, dict) and r.get("d")]
    if not rows:
        return []
    last = rows[-1]["d"]
    return [r for r in rows if (_days_between(r["d"], last) or 0) < days]


def _temp_points(t: dict, days: int = 90) -> list[dict]:
    return [{"d": r["d"], "t": r["t"]} for r in _recent(t.get("series") or [], days)
            if r.get("t") is not None]


def b_ticker(t: dict, as_of: str) -> dict | None:
    """단일 용어 진단 — 온도를 시세처럼. '요즘 어때?' 의 답."""
    if not t.get("available") or t.get("temp") is None:
        return None
    d = t.get("direction") or {}
    plats = sorted([s for s in (t.get("sources") or []) if s.get("temp") is not None],
                   key=lambda s: -float(s["temp"]))
    return {
        "type": "ticker", "term": t["canonical"], "facet": t.get("facet_name") or "",
        "as_of": str(t.get("observed_on") or as_of or ""),
        "temp": t["temp"], "band": t.get("temp_band"), "verdict": t.get("temp_verdict"),
        "verdict_text": t.get("temp_verdict_text"),
        "delta_1w": t.get("delta_1w"), "temp_1w_ago": t.get("temp_1w_ago"),
        "top_pct": t.get("top_pct"),
        "direction": d.get("label"), "tone": d.get("tone"), "ratio": d.get("ratio"),
        "mention_7d": t.get("mention_7d"), "mention_28d": t.get("raw_count"),
        "series": _temp_points(t, 90),
        "platforms": [{"name": s["name"], "temp": s["temp"]} for s in plats[:5]],
        "assoc": [{"name": a["canonical"], "is_new": bool(a.get("is_new"))}
                  for a in (t.get("associations") or [])[:4]],
        "notes": [str(n) for n in (t.get("notes") or [])[:2]],
    }


SPIKE_MIN = 10          # 이보다 적은 날은 급상승이라 부르지 않는다 — 2건 → 6건은 우연이다
SPIKE_RATIO = 3.0       # 직전 14일 중앙값의 몇 배부터 급상승인가
SPIKE_GAP = 5           # 두 급상승은 이만큼 떨어져 있어야 따로 센다


def _spikes(points: list[dict], history: list[dict]) -> list[dict]:
    """언급량이 직전 2주 평소보다 크게 튄 날. 많아야 둘.

    행이 없는 날은 언급 0 이다(지표 행은 언급이 있는 날에만 생긴다).
    ★ 직전 2주가 기록 안에 다 있는 날만 본다. 기록이 시작된 첫날들은 '앞이 0' 이라
      무엇이든 급상승으로 보인다.
    """
    by_day = {p["d"]: int(p.get("m") or 0) for p in history}
    first = history[0]["d"] if history else None
    out = []
    for p in points:
        if first is None or (_days_between(first, p["d"]) or 0) < 14:
            continue
        prev = []
        for back in range(1, 15):
            try:
                day = _date.fromordinal(_date.fromisoformat(p["d"]).toordinal() - back).isoformat()
            except ValueError:
                continue
            prev.append(by_day.get(day, 0))
        prev.sort()
        base = max(1.0, (prev[6] + prev[7]) / 2) if len(prev) == 14 else 1.0
        m = int(p.get("m") or 0)
        if m >= SPIKE_MIN and m >= SPIKE_RATIO * base:
            out.append({"d": p["d"], "m": m, "x": round(m / base, 1)})
    out.sort(key=lambda s: -s["x"])
    picked: list[dict] = []
    for s in out:
        if all(abs(_days_between(s["d"], q["d"]) or 0) >= SPIKE_GAP for q in picked):
            picked.append(s)
        if len(picked) == 2:
            break
    return sorted(picked, key=lambda s: s["d"])


def b_timeline(t: dict, *, evidence: bool) -> dict | None:
    """원인 — 최근 60일 언급량과 급상승한 날, 그 무렵의 근거. '왜 떴어?' 의 답.

    ★ 근거는 get_evidence 를 실제로 부른 용어에만 싣는다(evidence=True).
    ★ 급상승한 날 근처(−2일 ~ +3일)에 근거가 없으면 붙이지 않는다. 가까운 날짜의 아무 글을
      '원인' 처럼 세우면 지어낸 인과가 된다.
    """
    if not t.get("available"):
        return None
    pts = [{"d": r["d"], "m": int(r.get("m") or 0)} for r in _recent(t.get("series") or [], 60)]
    if len(pts) < 7:
        return None
    ev = []
    for e in (t.get("evidence") or [])[:12] if evidence else []:
        body = str(e.get("body") or "").strip()
        if len(body) < 6:
            continue
        ev.append({"src": e.get("source"), "kind": e.get("kind"),
                   "body": body[:90] + ("…" if len(body) > 90 else ""),
                   "url": e.get("url"), "at": str(e.get("at") or "")[:10] or None,
                   "tone": TONE_KO.get(e.get("tone"))})
    spikes = _spikes(pts, [{"d": r["d"], "m": int(r.get("m") or 0)}
                           for r in (t.get("series") or []) if r.get("d")])
    for s in spikes:
        near = [e for e in ev if e["at"] and -2 <= (_days_between(s["d"], e["at"]) or 99) <= 3]
        if near:
            s["src"] = near[0]["src"]
            s["body"] = near[0]["body"][:28] + ("…" if len(near[0]["body"]) > 28 else "")
    sent = None
    s = t.get("sentiment") or {}
    if s and not s.get("unavailable") and s.get("judged") and s.get("positive_pct") is not None:
        pos, neg = int(s.get("positive_pct") or 0), int(s.get("negative_pct") or 0)
        sent = {"pos": pos, "neg": neg, "neu": max(0, 100 - pos - neg),
                "n": int((s.get("반응") or {}).get("합계") or 0),
                "days": int(s.get("window_days") or 28)}
    return {"type": "timeline", "term": t["canonical"], "window": 60,
            "points": pts, "spikes": spikes, "evidence": ev[:3], "sentiment": sent,
            "mention_28d": t.get("raw_count")}


def b_versus(nodes: list[dict]) -> dict | None:
    """정확히 둘을 맞세운다. 셋 이상은 '나란히 보기'(b_compare)가 맡는다."""
    ok = [n for n in nodes if n.get("available") and n.get("temp") is not None]
    if len(ok) != 2:
        return None
    a, b = ok

    def side(n: dict) -> dict:
        d = n.get("direction") or {}
        return {"term": n["canonical"], "facet": n.get("facet_name") or "",
                "temp": n["temp"], "delta_1w": n.get("delta_1w"),
                "verdict": n.get("temp_verdict"), "tone": d.get("tone"),
                "series": _temp_points(n, 28)}

    rows: list[dict] = []

    def row(k, av, bv, fmt, lo, hi, higher_better=True):
        if av is None or bv is None:
            return
        better = None if av == bv else ("a" if (av > bv) == higher_better else "b")
        rows.append({"k": k, "a": av, "b": bv, "av": fmt(av), "bv": fmt(bv),
                     "lo": lo, "hi": hi, "better": better})

    ta, tb = float(a["temp"]), float(b["temp"])
    row("트렌드 온도", ta, tb, lambda v: f"{v:g}°",
        max(0, int(min(ta, tb)) - 10), min(100, int(max(ta, tb)) + 10))
    da, db = a.get("delta_1w"), b.get("delta_1w")
    if da is not None and db is not None:
        span = max(abs(float(da)), abs(float(db))) + 2
        row("1주 변화", float(da), float(db), lambda v: f"{v:+g}°", -span, span)
    ma, mb = a.get("mention_7d"), b.get("mention_7d")
    if ma is not None and mb is not None:
        row("7일 언급", int(ma), int(mb), lambda v: f"{int(v):,}건", 0,
            round(max(int(ma), int(mb), 1) * 1.15))
    sa, sb = a.get("sentiment") or {}, b.get("sentiment") or {}
    if sa.get("judged") and sb.get("judged") and sa.get("positive_pct") is not None \
            and sb.get("positive_pct") is not None:
        row("긍정 반응", int(sa["positive_pct"]), int(sb["positive_pct"]), lambda v: f"{int(v)}%", 0, 100)
    pa, pb = a.get("top_pct"), b.get("top_pct")
    if pa is not None and pb is not None:
        # 상위 % 는 작을수록 앞선다. 막대는 100 − 상위% 로 놓아 오른쪽이 앞서게 둔다.
        row("전체 순위", 100 - int(pa), 100 - int(pb), lambda v: f"상위 {100 - int(v)}%", 0, 100)
    return {"type": "versus", "a": side(a), "b": side(b), "rows": rows}


def b_leaderboard(res: dict) -> dict | None:
    """rank_terms → 리더보드. 순위 변동은 우리 데이터에 없어 그리지 않는다."""
    items = []
    for it in (res.get("items") or [])[:10]:
        if not it.get("term"):
            continue
        items.append({"rank": it.get("rank") or len(items) + 1, "term": it["term"],
                      "facet": it.get("facet_name") or FACET_KO.get(it.get("facet") or "", ""),
                      "temp": it.get("temp"), "verdict": it.get("verdict"),
                      "band": it.get("band"), "date": it.get("date")})
    if not items:
        return None
    return {"type": "leaderboard", "items": items, "as_of": res.get("as_of"),
            "window_days": res.get("window_days"),
            "short": bool(res.get("short_of_asked")), "asked": res.get("asked")}


SALMAL_LABELS = {"taste": "취향", "behavior": "검색·찜", "trend": "트렌드",
                 "price": "가격", "community": "커뮤니티"}


def b_verdict(res: dict) -> dict | None:
    """살말 판정 — 도장 하나와 그 점수가 어떻게 나왔는지(가중치 × 점수)."""
    if not isinstance(res, dict) or res.get("score") is None:
        return None
    from .salmal_index import WEIGHTS
    signals = []
    for sg in (res.get("signals") or [])[:5]:
        if not isinstance(sg, dict):
            continue
        key = str(sg.get("key") or "")
        signals.append({"key": key,
                        "label": str(sg.get("label") or SALMAL_LABELS.get(key, key) or "근거"),
                        "weight": int(sg.get("weight") or WEIGHTS.get(key, 0)),
                        "score": round(float(sg.get("score") or 0)),
                        "why": str(sg.get("why") or "")})
    missing = [{"key": k, "label": SALMAL_LABELS.get(k, k), "weight": WEIGHTS.get(k, 0)}
               for k in (res.get("missing") or []) if isinstance(k, str)]
    return {"type": "verdict", "term": str(res.get("term") or ""),
            "score": int(res["score"]), "rec": str(res.get("recommendation") or "보류"),
            "allowed": bool(res.get("recommendation_allowed")),
            "confidence": str(res.get("confidence") or "낮음"),
            "coverage": int(res.get("coverage") or 0),
            "signals": signals, "missing": missing, "as_of": res.get("as_of")}


LIFECYCLE_STAGES = ("태동", "확산", "정점", "쇠퇴")


def b_lifecycle(res: dict) -> dict | None:
    """get_market(axis=lifecycle) → 수명주기 곡선 위 '지금 여기'. 판정을 보류했으면 그리지 않는다."""
    if not isinstance(res, dict) or res.get("unavailable"):
        return None
    stage = res.get("stage")
    if stage not in LIFECYCLE_STAGES:
        return None
    weekly = [{"w": int(w.get("weeks_ago") or 0), "t": w.get("temp")}
              for w in (res.get("weekly_temp_recent") or []) if isinstance(w, dict)]
    return {"type": "lifecycle", "term": str(res.get("term") or res.get("label") or ""),
            "stage": stage, "progress": res.get("progress"),
            "peak_date": res.get("peak_date"), "age_weeks": res.get("age_weeks"),
            "weekly": weekly, "as_of": res.get("as_of")}


def b_orbit(t: dict) -> dict | None:
    """같이 언급되는 말을 연관 강도(lift)만큼 가까이. 셋 미만이면 그림이 되지 않는다."""
    rows = [a for a in (t.get("associations") or []) if a.get("lift") is not None]
    if len(rows) < 3:
        return None
    rows = sorted(rows, key=lambda a: -float(a["lift"]))[:8]
    return {"type": "orbit", "term": t["canonical"],
            "items": [{"name": a["canonical"], "lift": round(float(a["lift"]), 1),
                       "co": int(a.get("co_count") or 0), "is_new": bool(a.get("is_new")),
                       "facet": a.get("facet_name") or ""} for a in rows]}


def b_lowsignal(t: dict) -> dict | None:
    """관측이 얇은 용어 — 온도 대신 '지금 아는 것' 만. 지어낸 그래프를 그리지 않는다."""
    if not t.get("available"):
        return None
    n = int(t.get("raw_count") or 0)
    if not (t.get("thin") or n < THIN_SAMPLE):
        return None
    pts = [{"d": r["d"], "m": int(r.get("m") or 0)}
           for r in _recent(t.get("series") or [], 28) if int(r.get("m") or 0) > 0]
    seen = [r["d"] for r in (t.get("series") or []) if int(r.get("m") or 0) > 0]
    return {"type": "lowsignal", "term": t["canonical"], "facet": t.get("facet_name") or "",
            "n": n, "need": THIN_SAMPLE, "window": 28, "points": pts,
            "first_seen": seen[0] if seen else None,
            "sources": [{"name": s["name"], "n": int(s.get("raw_count") or 0)}
                        for s in (t.get("sources") or []) if int(s.get("raw_count") or 0) > 0][:4],
            "near": [a["canonical"] for a in (t.get("associations") or [])[:3]]}


def b_market(results: dict) -> dict | None:
    """get_market(discount · resale) → 시세 KPI. 결과에 있는 칸만."""
    items = []
    disc = results.get("discount") or {}
    overall = disc.get("overall") or {}
    if overall.get("avg_discount") is not None:
        items.append({"k": "평균 할인", "v": f"{overall['avg_discount']:g}", "unit": "%",
                      "note": f"최근 {disc.get('days') or 30}일 · 상품 {int(overall.get('products') or 0):,}개",
                      "up": False})
    if overall.get("min_sale_price") is not None:
        items.append({"k": "최저 판매가", "v": f"{int(overall['min_sale_price']):,}", "unit": "원",
                      "note": str((disc.get("cheapest") or {}).get("name") or ""), "up": False})
    resale = results.get("resale") or {}
    if resale.get("keep_pct") is not None:
        items.append({"k": "리셀 가격 유지율", "v": f"{resale['keep_pct']:g}", "unit": "%",
                      "note": "정가 대비", "up": float(resale["keep_pct"]) >= 100})
    if resale.get("volume_4w") is not None:
        items.append({"k": "4주 거래", "v": f"{int(resale['volume_4w']):,}", "unit": "건",
                      "note": "무신사 유즈드 · 크림", "up": False})
    if not items:
        return None
    label = disc.get("label") or resale.get("label") or ""
    return {"type": "kpis", "slot": "full", "title": "시세", "meta": str(label), "items": items[:4]}
