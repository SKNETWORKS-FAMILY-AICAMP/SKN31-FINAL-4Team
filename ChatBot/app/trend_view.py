"""트렌드 분석 화면이 보는 값을 챗봇도 그대로 본다 (2026-10-01).

── 왜 이 파일이 생겼나 ─────────────────────────────────────
챗봇이 지표 표(analysis.term_metric_daily)를 직접 읽는 동안 화면과 판단이 갈렸다.
같은 대화에서 실제로 나온 어긋남이다.

    질문                 트렌드 분석 화면                       챗봇(고치기 전)
    아디다스 어때?        온도 83° · 뜨거움                      "트렌드 수치가 아직 없다"
    아디다스 긍부정       28일 29건 · 긍정 우위 91 · 강한 신호     (보지 못함)
    트랙탑 순위          그날 전체 용어 중 상위 82%               "같은 축 상위 1%"
    팬츠 긍부정          28일 536건 · 긍정 우위 86 · 강한 신호    "9월 29일 감성 표본 2건 — 판단 불가"

원인은 셋이었다.
  ① 출처 — 화면은 /api/trend · /api/sentiment 를 부르고, 챗봇은 표를 따로 읽었다.
     /api/trend 는 용어마다 가장 최근 적재 버전을 고르는데 챗봇은 한 버전에 못 박혀 있었다.
  ② 기간 — 화면의 긍부정은 최근 28일 합계, 챗봇은 마지막 **하루** 행이었다.
  ③ 척도 — 백분위(0~100)를 0~1 로 읽었고, 온도 구간 경계도 화면과 달랐다.

그래서 챗봇은 화면이 부르는 주소를 같은 인자로 부르고(adapters.TrendHTTPAdapter),
화면과 **같은 규칙**으로 요약한다(이 파일). 숫자를 새로 정의하지 않는다.

── 규칙의 원본 (여기를 바꾸기 전에 저쪽부터) ─────────────────
  · 온도 구간 · 판정 문구   frontend/trend/static/js/dispatch.js   id==='temp'
  · 지난주 대비 온도        frontend/trend/static/js/live_data.js  summaryOf()
  · 긍부정 판정 · 28일 창   frontend/trend/static/js/dispatch.js   id==='sentiment'
  · 주별 · 월별 원형        frontend/trend/static/js/dispatch.js   sentPie()
화면 쪽 숫자가 바뀌면 이 파일과 tests/test_trend_view.py 의 화면 실측값을 같이 맞춘다.

── 하루치가 아니다 ─────────────────────────────────────────
  · 온도는 마지막 집계일 행의 값이다. 그 행이 이미 최근 7일·28일 이동평균(모멘텀)을
    품고 있다 — 화면 다이얼도 같은 행을 읽는다.
  · 언급량 · 반응 · 표본 판단은 **최근 7일 / 28일 합계**로 말한다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .config import (MIN_OBS_14, MIN_OBS_28, MIN_OBS_7, TEMP_VERDICTS, THIN_SAMPLE,
                     js_round, temp_band)

# ── 긍부정 탭 (dispatch.js id==='sentiment') ─────────────────
SENT_WINDOW = 28          # recent = rows.filter(r => trDayDiff(r.date, last.date) < 28)
SENT_MIN_N = 20           # SENT_MIN_N
SENT_BANDS = (            # band = dialV>=75 ? 0 : >=55 ? 1 : >=35 ? 2 : 3
    (75, "강한 구매 신호", "긍정 신호가 압도적입니다. 지금 재고·물량을 걱정할 시점입니다."),
    (55, "구매 신호 우세", "긍정 쪽이 앞서 있습니다. 부정 신호가 늘지 않는지만 함께 지켜보세요."),
    (35, "팽팽한 신호", "긍정과 부정이 비슷하게 맞섭니다. 부정 신호의 종류를 먼저 확인해야 합니다."),
    (-1, "구매 저해 신호 우세", "부정 신호가 앞섭니다. 가격·실물 관련 이슈부터 해소돼야 반등합니다."),
)
# 신호 유형 6칸 — DB 칸 순서 그대로, 극성(1 긍정 계열 · 0 중립 · -1 부정 계열)
SIGNALS = (("질문", "question_n", 0), ("구매", "purchase_n", 1), ("경험", "experience_n", 1),
           ("호평", "praise_n", 1), ("비판", "critique_n", -1), ("잡담", "chitchat_n", 0))
PIE_WINDOWS = (("주별", 7), ("월별", 30))   # SENT_PIE_G — 기준일 포함 최근 7일 · 30일
SERIES_DAYS = 90          # 리포트 그래프가 받는 일별 기록의 길이 (7 · 28 · 90일 전환)
STALE_NOTE_DAYS = 2       # 마지막 집계일이 기준일보다 이만큼 넘게 이르면 '주의' 에 적는다


def day_diff(a: str, b: str) -> int:
    """trDayDiff(a, b) — b 가 a 보다 며칠 뒤인가."""
    return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days


def _num(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _rows(data: dict) -> list[dict]:
    rows = [r for r in (data.get("series") or []) if isinstance(r, dict) and r.get("date")]
    return sorted(rows, key=lambda r: str(r["date"])[:10])


def _sum(rows: list[dict], field: str) -> int:
    return int(sum(_num(r.get(field)) or 0 for r in rows))


# ══════════════════════════════════════════════════════════
#  언급량 · 온도
# ══════════════════════════════════════════════════════════
def trend_summary(data: dict) -> dict | None:
    """/api/trend 의 data → 화면 '언급량·온도' 탭과 같은 요약. 행이 없으면 None."""
    rows = _rows(data)
    if not rows:
        return None
    last = rows[-1]
    as_of = str(last["date"])[:10]

    def within(n: int) -> list[dict]:
        return [r for r in rows if 0 <= day_diff(r["date"], as_of) < n]

    # summaryOf().back(7) — 정확히 그날이 없으면 그 앞의 가장 가까운 행
    want = (date.fromisoformat(as_of) - timedelta(days=7)).isoformat()
    back = None
    for r in rows:
        if str(r["date"])[:10] <= want:
            back = r

    temp = _num(last.get("temp"))
    pct = _num(last.get("pct_rank"))
    level = _num(last.get("level"))
    momentum = _num(last.get("momentum"))
    back_temp = _num(back.get("temp")) if back else None
    m7, m28 = _sum(within(7), "mention"), _sum(within(28), "mention")
    data_as_of = str(data.get("data_as_of") or as_of)[:10]

    notes: list[str] = []
    stale = day_diff(as_of, data_as_of) if data_as_of >= as_of else 0
    # 하루 이틀 비는 것은 언급이 드문 용어에서 흔하다. 그보다 묵으면 밝힌다.
    if stale > STALE_NOTE_DAYS:
        notes.append(f"이 용어의 마지막 집계일은 {as_of} 입니다 "
                     f"(전체 데이터 기준일 {data_as_of}, {stale}일 전).")
    basis = data.get("series_basis") or None
    if isinstance(basis, dict) and basis.get("note"):
        notes.append(str(basis["note"]))
    if temp is not None and m28 == 0:
        notes.append(f"최근 28일 언급 건수가 0으로 기록된 행에서 나온 온도입니다 "
                     f"(지표 버전 {data.get('metric_version') or '미상'}). "
                     "건수로 뒷받침되는 값이 아닙니다.")

    band = temp_band(temp) if temp is not None else None
    verdict = TEMP_VERDICTS.get(band) if band else None
    return {
        "term": data.get("term"),
        "facet": data.get("facet"),
        "as_of": as_of,
        "data_as_of": data_as_of,
        "stale_days": stale,
        "metric_version": data.get("metric_version"),
        "series_basis": (basis or {}).get("metric_version") if isinstance(basis, dict) else None,
        "temp": None if temp is None else js_round(temp),
        "band": band,
        "verdict": verdict[0] if verdict else None,
        "verdict_text": verdict[1] if verdict else None,
        "level": None if level is None else js_round(level),
        "momentum": None if momentum is None else js_round(momentum),
        "ma7": _num(last.get("ma7")),
        "ma28": _num(last.get("ma28")),
        # 백분위는 0~100 이다(analysis/text_signals/metrics.py _percentiles).
        # 그날 언급된 **전체 용어** 사이의 순위라 '같은 축' 이 아니다.
        "percentile": pct,
        "top_pct": None if pct is None else max(1, js_round(100 - pct)),
        "temp_1w_ago": None if back_temp is None else js_round(back_temp),
        "temp_1w_ago_date": str(back["date"])[:10] if back else None,
        "delta_1w": (None if back_temp is None or temp is None
                     else js_round(temp - back_temp)),
        "mention_last_day": int(_num(last.get("mention")) or 0),
        "mention_7d": m7,
        "mention_28d": m28,
        "obs": {"n7": len(within(7)), "n14": len(within(14)), "n28": len(within(28))},
        "thin": m28 < THIN_SAMPLE,
        "notes": notes,
        # ★ 리포트 그래프용 일별 기록 (2026-10-02). 화면의 언급량·온도 그래프와 같은 행이다.
        #   행이 없는 날은 넣지 않는다 — '0건' 이 아니라 '관측 없음' 이라, 채우면 그림이 거짓말을 한다.
        #   모델(get_metric)에는 싣지 않는다. 카드(report.build_term)만 읽는다.
        "series": [{"d": str(r["date"])[:10],
                    "t": None if _num(r.get("temp")) is None else round(_num(r.get("temp")), 1),
                    "m": int(_num(r.get("mention")) or 0)}
                   for r in within(SERIES_DAYS)],
    }


def platforms(data: dict) -> list[dict]:
    """플랫폼별 온도 — 화면 표와 같은 거르기.

    옛 버전 행(legacy)인데 언급이 0이면 뺀다. 언급 0 에서 나온 82° 를 댓글 24건에서
    나온 86° 옆에 세우면 틀린 비교를 부른다(dispatch.js 2026-09-22 주석).
    """
    out = []
    for p in data.get("platforms") or []:
        if not isinstance(p, dict) or p.get("temp") is None:
            continue
        if p.get("legacy") and not p.get("mention"):
            continue
        out.append({"code": p.get("code"), "name": p.get("name") or p.get("code"),
                    "temp": js_round(p["temp"]), "mention": p.get("mention"),
                    "date": p.get("date"), "stale": bool(p.get("stale"))})
    return out


def association_items(data: dict, limit: int = 8) -> list[dict]:
    """Map the analytics page's /api/assoc items to the chatbot's existing contract."""
    out = []
    for item in (data.get("items") or [])[:limit]:
        if not isinstance(item, dict) or not item.get("term"):
            continue
        facet = str(item.get("facet") or "").lower()
        score = item.get("score")
        out.append({
            "assoc_canonical": item["term"],
            "assoc_facet": facet,
            "facet_name": item.get("facet_ko"),
            "co_count": int(_num(item.get("cooccurrence")) or 0),
            "lift": _num(item.get("lift")),
            "score_v": _num(score if score is not None else item.get("percentile")),
            "is_new": item.get("change") == "new",
            "basis": item.get("basis") or [],
        })
    return out


# ══════════════════════════════════════════════════════════
#  긍부정
# ══════════════════════════════════════════════════════════
def sentiment_summary(data: dict) -> dict | None:
    """/api/sentiment 의 data → 화면 '긍부정' 탭의 결론 카드와 같은 값."""
    rows = _rows(data)
    if not rows:
        return None
    last = rows[-1]
    as_of = str(last["date"])[:10]
    recent = [r for r in rows if day_diff(r["date"], as_of) < SENT_WINDOW]

    count_fields = ["pos_n", "neu_n", "neg_n"] + [f for _, f, _ in SIGNALS]
    any_count = any((_num(r.get(f)) or 0) > 0 for r in rows for f in count_fields)
    if last.get("intent") is None and last.get("pos_rate") is None and not any_count:
        counted = any(r.get(f) is not None for r in rows for f in count_fields)
        return {"as_of": as_of, "judged": False, "verdict": None,
                "unavailable": ("분류된 반응이 아직 0건입니다." if counted
                                else "긍부정·구매의향 지표가 아직 계산되지 않았습니다.")}

    pos, neu, neg = _sum(recent, "pos_n"), _sum(recent, "neu_n"), _sum(recent, "neg_n")
    total = pos + neu + neg

    def pct(v: int, rate_field: str):
        if total > 0:
            return js_round(v / total * 100)
        rate = _num(last.get(rate_field))
        return None if rate is None else js_round(rate)

    score = None if last.get("intent") is None else js_round(_num(last["intent"]) or 0)
    lead = js_round(pos / (pos + neg) * 100) if (pos + neg) > 0 else None
    thin = score is None and (total < SENT_MIN_N or lead is None)
    dial = score if score is not None else (lead if lead is not None else 0)

    has_intent = any(r.get(f) is not None for r in recent for _, f, _ in SIGNALS)
    signals = [(name, _sum(recent, f), pol) for name, f, pol in SIGNALS]
    if not (has_intent and any(n > 0 for _, n, _ in signals)):
        signals = []
    by_count = sorted([s for s in signals if s[1] > 0], key=lambda s: -s[1])
    top_pos = next((s for s in by_count if s[2] > 0), None)
    top_neg = next((s for s in by_count if s[2] < 0), None)

    if thin:
        verdict, text = "판단 보류", (f"최근 {SENT_WINDOW}일 반응이 {total}건뿐이라 판정하기엔 자료가 적습니다. "
                                    f"{SENT_MIN_N}건 이상 모이면 판정합니다.")
    else:
        verdict, text = next((label, say) for edge, label, say in SENT_BANDS if dial >= edge)

    def window(n: int) -> dict:
        rs = [r for r in rows if 0 <= day_diff(r["date"], as_of) < n]
        p, u, g = _sum(rs, "pos_n"), _sum(rs, "neu_n"), _sum(rs, "neg_n")
        return {"days": n, "긍정": p, "중립": u, "부정": g, "합계": p + u + g}

    return {
        "basis": "트렌드 분석 › 긍부정 탭과 같은 값",
        "scope": data.get("scope_label") or "용어 직접 언급",
        "method": data.get("method"),
        "as_of": as_of,
        "data_as_of": str(data.get("data_as_of") or as_of)[:10],
        "window_days": SENT_WINDOW,
        "반응": {"긍정": pos, "중립": neu, "부정": neg, "합계": total},
        "positive_pct": pct(pos, "pos_rate"),
        "negative_pct": pct(neg, "neg_rate"),
        # 화면 다이얼: 구매의향 지수가 있으면 그 값, 없으면 긍정 ÷ (긍정+부정) × 100
        "dial": dial if (score is not None or lead is not None) else None,
        "dial_label": "구매의향 지수" if score is not None else "긍정 우위 %",
        "lead_pct": lead,
        "purchase_intent_index": score,
        "judged": not thin,
        "min_n": SENT_MIN_N,
        "verdict": verdict,
        "verdict_text": text,
        "signals": {name: n for name, n, _ in signals},
        "top_positive_signal": ({"name": top_pos[0], "count": top_pos[1]} if top_pos else None),
        "top_negative_signal": ({"name": top_neg[0], "count": top_neg[1]} if top_neg else None),
        "windows": {label: window(n) for label, n in PIE_WINDOWS},
    }


# ══════════════════════════════════════════════════════════
#  용어 하나 — 문장(get_metric)과 카드(report.build_term)가 같이 쓴다
# ══════════════════════════════════════════════════════════
_SOURCE = None


def source():
    """공유 어댑터. 짧은 캐시가 있어 한 턴의 문장과 카드가 같은 응답을 쓴다."""
    global _SOURCE
    if _SOURCE is None:
        from .adapters import TrendHTTPAdapter
        _SOURCE = TrendHTTPAdapter()
    return _SOURCE


def set_source(src) -> None:
    """시험·진단용. None 이면 다음 호출에서 기본 어댑터를 다시 만든다."""
    global _SOURCE
    _SOURCE = src


def is_brand(facet: Any) -> bool:
    return str(facet or "").strip().lower() in ("brand", "브랜드")


def term_view(term: str, facet_hint: str | None = None, *, with_sentiment: bool = True,
              with_assoc: bool = False,
              api=None) -> dict:
    """용어 하나의 온도·플랫폼·(선택)긍부정. 화면과 같은 주소·같은 규칙.

    돌려주는 status
      ok     — trend 가 있다
      empty  — 화면도 '측정된 지표 없음' 을 띄우는 경우. reason 은 API 문장 그대로
      error  — API 에 닿지 못했다. 표를 직접 읽어 대신 채우지 않는다 —
               그러면 화면과 다른 숫자가 다시 나간다.
    """
    api = api or source()
    # ★ 축을 이미 알면 두 주소를 **함께** 부른다. 화면 API 는 한 번에 1~3초가 걸린다
    #   (2026-10-01 실측: 아디다스 브랜드 긍부정 3.5초). 도구는 한 바퀴 안에서 차례로
    #   돌기 때문에, 줄 세워 부르면 용어 둘만 비교해도 그대로 시간 예산을 먹는다.
    pending = None
    if with_sentiment and facet_hint:
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(max_workers=1)
        pending = pool.submit(api.sentiment, term, is_brand(facet_hint))
        pool.shutdown(wait=False)
    raw = api.trend(term) or {}
    status = raw.get("status")
    if status == "error" or status not in ("ok", "empty"):
        return {"status": "error",
                "reason": raw.get("reason") or "트렌드 분석 데이터를 읽지 못했습니다."}
    if status == "empty":
        return {"status": "empty",
                "reason": raw.get("reason") or "이 용어는 아직 측정된 지표가 없습니다."}

    data = raw.get("data") or {}
    summary = trend_summary(data)
    if summary is None:
        return {"status": "empty", "reason": "이 용어는 아직 측정된 지표가 없습니다."}
    view: dict[str, Any] = {"status": "ok", "trend": summary, "platforms": platforms(data)}

    if with_assoc:
        try:
            araw = api.assoc(term) or {}
        except Exception as exc:  # noqa: BLE001 - an optional axis must not erase the trend
            araw = {"status": "error", "reason": f"연관어 데이터를 읽지 못했습니다 ({type(exc).__name__})."}
        view["associations"] = (association_items(araw.get("data") or {})
                                if araw.get("status") == "ok" else [])
        if araw.get("status") not in ("ok", "empty"):
            view["assoc_unavailable"] = araw.get("reason") or "연관어 데이터를 읽지 못했습니다."

    if with_sentiment:
        brand = is_brand(data.get("facet")) or is_brand(facet_hint)
        if pending is not None and brand == is_brand(facet_hint):
            try:
                sraw = pending.result() or {}
            except Exception as exc:                    # noqa: BLE001
                sraw = {"status": "error", "reason": f"긍부정 데이터를 읽지 못했습니다 ({type(exc).__name__})."}
        else:
            # 사전(화면 검색)의 축과 지표의 축 중 하나라도 브랜드면 브랜드 문맥으로 본다.
            sraw = api.sentiment(term, brand=brand) or {}
        if sraw.get("status") == "ok":
            s = sentiment_summary(sraw.get("data") or {})
            view["sentiment"] = s or {"unavailable": "긍부정 지표가 아직 없습니다."}
        else:
            view["sentiment"] = {"unavailable": sraw.get("reason") or "긍부정 지표가 아직 없습니다."}
    return view


def may_say(obs: dict) -> dict:
    """관측 일수로 말해도 되는 것. config 의 실측 기준(MIN_OBS_*)을 그대로 쓴다."""
    return {"수준": obs.get("n7", 0) >= MIN_OBS_7,
            "2주변화": obs.get("n14", 0) >= MIN_OBS_14,
            "방향": obs.get("n28", 0) >= MIN_OBS_28}
