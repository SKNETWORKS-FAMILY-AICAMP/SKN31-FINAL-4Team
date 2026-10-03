"""리포트 조립 — 숫자는 전부 DB 에서 온다.

★ 여기서 LLM 이 숫자를 쓰지 못하게 하는 것이 핵심이다.
  문장은 자리표시자가 있는 틀이고, 값은 서버가 도구 반환값에서 직접 꽂는다.
  LLM 은 어투만 다듬는다. 그래야 "지어낸 숫자"가 구조적으로 불가능하다.

★ 모든 답에 기준 시각이 붙는다.
  가격·재고는 볼 때마다 달라진다. 언제 기준인지 반드시 적는다 (AGENTS.md §6.2).
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from . import plans, templates, trend_view
from .config import SEARCH_FACETS
from .coverage import assess, direction

KST = timezone(timedelta(hours=9))
SOURCE_KO = {"musinsa": "무신사", "naver": "네이버", "youtube": "유튜브",
             "zigzag": "지그재그", "ably": "에이블리", "kream": "크림",
             "fruitsfamily": "후르츠패밀리", "musinsa_used": "무신사 유즈드"}
FACET_KO = {"style": "스타일", "item": "아이템", "material": "소재", "brand": "브랜드",
            "fit": "핏", "color": "컬러", "detail": "디테일", "tpo": "TPO"}
# ★ 빠진 doc_kind 는 영어 코드 그대로 화면에 나간다.
#   'product_review' 가 인용 밑에 그대로 찍히던 것을 2026-09-09 에 발견했다.
#   새 doc_kind 가 생기면 여기에 한 줄 추가한다.
DOC_KO = {"naver_blog": "블로그", "naver_cafearticle": "카페 글", "yt_comment": "댓글",
          "yt_comment_reply": "답글", "yt_video_context": "영상 설명", "yt_transcript": "자막",
          "product_review": "리뷰"}


def _has_batchim(word: str) -> bool:
    if not word:
        return False
    ch = ord(word[-1])
    return 0xAC00 <= ch <= 0xD7A3 and (ch - 0xAC00) % 28 != 0


def _josa(word: str, with_b: str, without_b: str) -> str:
    """받침에 맞는 조사. 은/는 · 과/와 · 이/가 전부 이걸 쓴다.

    돌려 보고 잡았다 — "데님와 가장 자주" 라고 나왔다. 데님은 받침이 있으니 "데님과" 다.
    """
    return with_b if _has_batchim(word) else without_b


def build_term(store, gate, hit: dict, as_of: str, *, with_sentiment: bool = True,
               with_assoc: bool = False, with_evidence: bool = False,
               api=None) -> dict:
    """term 하나에 대해 우리가 아는 전부를 모은다. 플랜 자르기는 하지 않는다.

    ★ 2026-10-01 — 온도·언급량·순위·플랫폼·긍부정은 **트렌드 분석 화면과 같은 값**이다
      (trend_view.term_view). 예전엔 지표 표를 직접 읽어서, 같은 답 안에서 문장은
      "상위 1%" 카드는 "상위 82%" 처럼 서로 다른 말을 했다. get_metric 과 같은
      어댑터·같은 캐시를 쓰므로 한 턴의 문장과 카드가 같은 응답에서 나온다.
      연관어도 분석 화면의 API 를 읽는다. 근거는 필요할 때만 저장소에서 읽는다.
    """
    key = hit["term_key"]
    view = trend_view.term_view(hit["canonical"], hit.get("facet"),
                                with_sentiment=with_sentiment, with_assoc=with_assoc, api=api)
    T = view.get("trend") if view.get("status") == "ok" else None
    sentiment = view.get("sentiment") if T else None
    sentiment_issue = sentiment.get("unavailable") if isinstance(sentiment, dict) else None
    if sentiment_issue:
        sentiment = None
    assoc = view.get("associations") or []
    cov = assess(T, sentiment, len(assoc), view.get("reason"))
    issues = {"NO_ASSOC": view.get("assoc_unavailable"), "NO_SENTIMENT": sentiment_issue}
    cov.reasons = [(code, issues.get(code) or message) for code, message in cov.reasons]

    node = {
        "canonical": hit["canonical"],
        "facet": hit["facet"],
        "facet_name": FACET_KO.get(hit["facet"], hit["facet"]),
        "via": hit.get("via"),
        "coverage": cov.as_dict(),
    }
    if not T:
        node["available"] = False
        node["reason"] = view.get("reason")
        return node

    node["available"] = True
    node["observed_on"] = T["as_of"]
    node["data_as_of"] = T["data_as_of"]
    node["metric_version"] = T["metric_version"]
    # ★ 언급량은 하루치가 아니라 최근 28일 합계다. 카드 행 이름도 그렇게 적는다.
    node["raw_count"] = T["mention_28d"]
    node["mention_7d"] = T["mention_7d"]
    node["mention_window"] = 28
    node["temp"] = T["temp"]
    node["temp_band"] = T["band"]
    node["temp_verdict"] = T["verdict"]
    node["temp_verdict_text"] = T.get("verdict_text")
    # 지난주 대비 · 일별 기록 — 리포트 템플릿(티커 · 주석 그래프 · VS)이 그림을 그린다 (2026-10-02)
    #   ★ get_metric 과 같은 문턱 — 14일 관측이 모자라면 지난주 대비를 말하지 않는다(trend_view.may_say).
    two_weeks = trend_view.may_say(T.get("obs") or {}).get("2주변화")
    node["temp_1w_ago"] = T.get("temp_1w_ago") if two_weeks else None
    node["delta_1w"] = T.get("delta_1w") if two_weeks else None
    node["obs"] = dict(T.get("obs") or {})
    node["thin"] = bool(T.get("thin"))
    node["series"] = list(T.get("series") or [])
    node["pct_rank"] = T["percentile"]
    node["top_pct"] = T["top_pct"]
    node["level"] = T["level"]
    node["momentum"] = T["momentum"]
    node["share_pct"] = None
    node["notes"] = T["notes"]

    if cov.can_direction:
        node["direction"] = direction({"ma7": T["ma7"], "ma28": T["ma28"]})

    node["sources"] = [{"code": p["code"],
                        "name": SOURCE_KO.get(str(p["code"] or "").lower(), p["name"]),
                        "raw_count": int(p.get("mention") or 0),
                        "temp": p["temp"],
                        "observed_on": p.get("date"),
                        "stale": p.get("stale")} for p in view.get("platforms") or []]

    if cov.can_assoc:
        node["associations"] = [{"canonical": a["assoc_canonical"],
                                 "facet": a["assoc_facet"],
                                 "facet_name": a.get("facet_name") or FACET_KO.get(a["assoc_facet"], a["assoc_facet"]),
                                 "co_count": a["co_count"],
                                 "lift": a["lift"], "score": a["score_v"],
                                 "is_new": bool(a["is_new"]),
                                 "basis": a.get("basis") or []} for a in assoc]
    if cov.can_sentiment:
        # 화면 긍부정 탭과 같은 값 — 최근 28일 합계와 판정(trend_view.sentiment_summary).
        node["sentiment"] = sentiment

    # 근거는 '원문 통짜'가 아니라 판정에 실제로 쓰인 짧은 대목이다 (store.term_evidence 주석)
    # url 은 원문으로 돌아갈 수 있을 때만 채워진다(store.evidence_link).
    # 없는 것을 None 인 채로 들고 온다 — 여기서 지어 채우면 화면의 링크가 거짓이 된다.
    try:
        evidence = store.term_evidence(key) if with_evidence else []
    except Exception:  # noqa: BLE001 - optional proof must not erase verified temperature
        evidence = []
    node["evidence"] = [{"source": SOURCE_KO.get(e["source_code"], e["source_code"]),
                         "kind": DOC_KO.get(e["doc_kind"], e["doc_kind"]),
                         "body": e["body"], "at": e["at"],
                         "tone": e.get("sentiment"), "origin": e.get("origin"),
                         "url": e.get("url")}
                        for e in evidence]
    return node


# ── 한 줄 결론 — 틀에 값을 꽂는다. 문장을 생성하지 않는다 ──────────
def headline(node: dict, intent: str) -> str:
    if not node.get("available"):
        if node.get("reason"):
            return str(node["reason"])
        return (f"<b>{node['canonical']}</b>{_josa(node['canonical'],'은','는')} "
                f"사전에는 있지만 아직 수집된 언급이 없습니다.")
    c, t, band = node["canonical"], node["temp"], node["temp_band"]
    n = node["raw_count"]
    j = _josa(c, "은", "는")

    if intent == "metric.direction":
        d = node.get("direction")
        if d:
            return (f"<b>{c}</b>{j} <b>{d['label']}</b>입니다. "
                    f"최근 7일 평균이 4주 평균의 {d['ratio']}배입니다.")
        return (f"<b>{c}</b>의 방향은 아직 말할 수 없습니다. "
                f"최근 28일 중 관측이 {node['coverage']['obs28']}일뿐입니다.")

    if intent == "metric.assoc" and node.get("associations"):
        top = " · ".join(a["canonical"] for a in node["associations"][:3])
        gwa = _josa(c, "과", "와")
        return f"<b>{c}</b>{gwa} 가장 자주 같이 나오는 말은 <b>{top}</b>입니다."

    if intent == "metric.sentiment":
        s = node.get("sentiment")
        if s:
            # 화면 긍부정 탭의 결론 카드와 같은 말 (최근 28일 합계)
            r = s.get("반응") or {}
            return (f"<b>{c}</b>{j} 지금 <b>{s['verdict']}</b>입니다. "
                    f"최근 {s['window_days']}일 반응 {r.get('합계', 0):,}건 기준입니다.")
        return f"<b>{c}</b>{j} 긍부정을 판단할 반응이 아직 없습니다."

    if t is None:
        return f"<b>{c}</b>의 트렌드 온도가 아직 계산되지 않았습니다."
    verdict = node.get("temp_verdict") or band
    return (f"<b>{c}</b>{j} 지금 <b>{verdict}</b> 구간 — 트렌드 온도 <b>{t}점</b>입니다. "
            f"최근 28일 언급 {n:,}건 기준입니다.")


def compose(store, gate, question: str, intent: str, parsed: dict,
            plan: str = plans.FREE, mode: str = "general") -> dict:
    """최종 응답. 프론트가 그대로 그릴 수 있는 모양."""
    as_of = store.latest_day()
    now = datetime.now(KST).isoformat(timespec="seconds")
    hits = parsed["search"]

    if not hits:
        return {"ok": False, "reason": "NOT_IN_LEXICON", "intent": intent,
                "question": question, "generated_at": now}

    nodes = [build_term(store, gate, h, as_of) for h in hits]
    locked_all: set = set()
    gated = []
    for n in nodes:
        g, locked = plans.apply(plan, n)
        locked_all.update(locked)
        gated.append(g)

    notes = []
    for n in nodes:
        for code, msg in (n["coverage"].get("reasons") or []):
            notes.append({"code": code, "term": n["canonical"], "message": msg})

    if intent == "metric.lifecycle":
        # ★ 수명주기는 아직 계산하지 못한다 (FEEDiT_지표계산_설계서.md 6장) —
        #   로지스틱 곡선을 맞추려면 최소 8~12주치 시계열이 필요하다.
        #   조용히 다른 지표로 대신 답하면 사용자는 그게 수명주기 답인 줄 안다.
        #   못 한다고 먼저 말하고, 지금 보이는 지표만 아래에 덧붙인다.
        notes.insert(0, {
            "code": "LIFECYCLE_PENDING", "term": nodes[0]["canonical"],
            "message": "수명주기(계절 · 착용 예측)는 아직 계산하지 못합니다.\n"
                       "최소 8~12주치 시계열이 쌓여야 예측 곡선을 맞출 수 있습니다.\n"
                       "지금 볼 수 있는 지표만 아래에 보여드립니다.",
        })

    head = headline(nodes[0], intent)
    pending = None
    if mode == "salmal":
        # ★ 살!말?지수는 아직 계산하지 못한다 (설계서 7장).
        #   수명주기 표와 가격 이력이 먼저 필요하다.
        #   조용히 일반 모드 답을 주면 사용자는 그게 '살말 판정'인 줄 안다.
        #   못 한다고 먼저 말하고, 아는 것만 덧붙인다.
        pending = {
            "code": "SALMAL_INDEX_PENDING",
            "message": "살!말?지수는 아직 계산하지 못합니다.\n"
                       "가격 이력과 수명주기 데이터가 더 쌓여야 합니다.",
        }
        head = "아직 <b>살지 말지</b>는 판단하지 못합니다. 지금 아는 것만 알려드립니다 — " + head

    rep = {
        "ok": True,
        "kind": mode,
        "intent": intent,
        "question": question,
        "as_of": {"metric": as_of, "generated_at": now},
        "metric_version": store.version,
        "headline": head,
        "terms": gated,
        "modifiers": parsed.get("modifier", []),
        "notes": notes,
        "locked": sorted(locked_all),
        "plan": plans.normalize(plan),
        "source_note": f"무신사·유튜브 등 수집 소스 통합 · {as_of} 기준",
    }
    if pending:
        rep["pending"] = pending
        rep["notes"] = [{"code": pending["code"], "term": "", "message": pending["message"]}] + rep["notes"]
    up = plans.upsell(sorted(locked_all), plan)
    if up:
        rep["upsell"] = up

    # ── 질문 유형에 맞는 구조를 고른다 ──
    #   블록 목록은 templates.py 의 레지스트리가 정한다. LLM 이 만들지 않는다.
    #   plan 으로 잘린 노드(gated)를 쓴다 — 잠긴 지표는 블록에도 안 들어간다.
    rep["blocks"] = templates.build(intent, gated, rep, as_of)
    return rep


# 등록 요청에 쓸 말을 고를 때 버리는 어절 — 질문의 껍데기다
_ASK_STOP = {"어때", "어떤가", "요즘", "지금", "알려줘", "뭐야", "무엇", "어떻게",
             "트렌드", "온도", "살까", "말까", "사도", "될까", "추천", "좀", "이거",
             "그거", "저거", "지수", "분석", "해줘", "보여줘", "궁금해", "인가요"}


def guess_surface(question: str) -> str:
    """사전에 없는 말 중 무엇을 등록 요청할 것인가.

    질문 전체를 그대로 보내면 관리자가 "코르셋코어 어때?" 를 사전에 넣게 된다.
    껍데기 어절을 걷어내고 가장 긴 것을 고른다. 틀려도 관리자가 고친다 — 비워 두는 것보다 낫다.
    """
    import re as _re
    toks = [t for t in _re.findall(r"[가-힣A-Za-z0-9]+", _nfc_q(question))
            if len(t) >= 2 and t not in _ASK_STOP]
    return max(toks, key=len) if toks else question[:40]


def _nfc_q(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFC", str(s or ""))


def strip_urls(question: str) -> str:
    """주소를 걷어낸 질문. 주소 안의 조각(musinsa · products · 숫자)이
    '혹시 이건가요' 후보나 등록 요청 단어로 새어 나가지 않게 한다."""
    import re as _re
    q = _re.sub(r"https?://\S+|\bwww\.[^\s]+", " ", str(question or ""), flags=_re.I)
    return _re.sub(r"\s+", " ", q).strip()


def link_not_identified(question: str, seen: dict | None = None) -> dict:
    """링크는 받았는데 그 상품을 우리 사전의 말로 잇지 못했다.

    ★ 여기서 **앞 대화의 다른 상품으로 대신 답하지 않는다** (2026-09-13).
      링크를 붙였다는 것은 그 링크의 물건을 묻는다는 뜻이라, 다른 상품의
      지표를 보여 주면 맞는 숫자로 틀린 답을 하게 된다.
    """
    label = " ".join(x for x in ((seen or {}).get("brand"),
                                 (seen or {}).get("item_name")) if x)
    if label:
        head = (f"링크의 상품은 '{label}' 로 확인했습니다.\n\n"
                "다만 이 상품을 FEEDiT 사전의 스타일 · 소재 · 아이템 · 브랜드로 "
                "잇지 못해 트렌드 지표를 낼 수 없습니다.")
    else:
        head = ("링크에서 어떤 상품인지 확인하지 못했습니다.\n\n"
                "FEEDiT 는 스타일 · 소재 · 아이템 · 브랜드 네 가지로만 트렌드를 셉니다.")
    return {
        "ok": False,
        "reason": "LINK_NOT_IDENTIFIED",
        "message": head + "\n\n어떤 아이템인지 한 단어로 알려 주시면 바로 찾아보겠습니다.",
        "near_label": "",
        "near": [],
        "surface_guess": "",
        "link": {"url": (seen or {}).get("url"),
                 "item_name": (seen or {}).get("item_name"),
                 "brand": (seen or {}).get("brand"),
                 "price_krw": (seen or {}).get("price_krw")} if seen else None,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
    }


def not_in_lexicon(gate, store, question: str) -> dict:
    """사전에 없는 말. 실패로 끝내지 않는다 — 가까운 말과 등록 요청을 준다."""
    question = strip_urls(question) or question
    near = gate.near_candidates(question)
    fallback = not near
    if fallback:
        near = gate.popular(store)
    return {
        "ok": False,
        "reason": "NOT_IN_LEXICON",
        "message": ("사전에 없는 말입니다.\n\n"
                    "FEEDiT 는 스타일 · 소재 · 아이템 · 브랜드 네 가지로만 트렌드를 셉니다.\n"
                    "사전에 없으면 언급량을 셀 수가 없어 답을 만들 수 없습니다."),
        "near_label": "많이 찾는 키워드" if fallback else "혹시 이건가요",
        "near": near,
        "surface_guess": guess_surface(question),
        "action": {"type": "lexicon_request", "label": "등록 요청"},
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
    }
