"""L2 출력 → 화면 블록. 도구가 조회한 것만 그린다.

── 왜 필요한가 (13번 피드백) ────────────────────────────────
새 경로(orchestrator)는 지금 **문장만** 내놓는다. 화면은 그 문장을 말풍선에
흘려보내고, 그 아래 report 이벤트로 받은 blocks 를 카드로 그린다. blocks 가
비어 있으니 카드는 제목줄만 있는 빈 상자로 뜬다. 예전 경로(templates.py)는
같은 질문에 온도 막대·플랫폼 표·인용을 그렸다. 즉 **새 경로로 갈아타면 화면이
가난해진다.** 답변 품질을 올리려고 만든 경로가 화면을 후퇴시키면 갈아탈 수 없다.

── 원칙: 블록은 궤적에서 만든다, 답변 문장에서 만들지 않는다 ─
`agent_path._terms_from()` 과 같은 이유다. 답변 문장을 파싱해 블록을 만들면
모델이 지어낸 말이 그대로 막대그래프가 된다. 숫자를 검증하는 층(verify.py)을
두고서 그 옆으로 지어낸 값이 그림이 되어 새어 나가는 셈이다.

그래서 여기서는 **도구를 실제로 부른 기록(TraceLog)** 만 읽고, 값은 store 에서
다시 가져온다(report.build_term). 문장과 그림의 출처가 같아진다.

── 구조도 도구 결과가 된다 (2026-09-10) ───────────────────
오케스트레이터는 조회를 마친 뒤 compose_report 를 부른다. 이 도구는 완성 양식의
이름을 고르지 않고, 실제 결과 모듈의 표현 역할·폭·강조도·색을 매번 조합한다.
여기서는 그 스펙을 실제 블록 카탈로그와 결합한다. 모델이 없는 모듈을 요청해도
카탈로그에 없으면 붙지 않으므로, 디자인 경로로 값이 새어 나오지 않는다.
"""
from __future__ import annotations

from typing import Any

from . import blocks as B
from . import report, report_skill
from .tools import FACET_SAY          # 축 한글 이름 — 화면 문구를 도구와 맞춘다

MAX_TERMS = 4       # 생성형 12열 캔버스라 비교 대상을 둘에 고정하지 않는다.


def _facet_of(term_key: str, fallback: str | None = None) -> str | None:
    if fallback:
        return fallback
    if term_key and ":" in term_key:
        return term_key.split(":", 1)[0]
    return None


def _key_for(term: str, gate, store, hint: str | None) -> str:
    """term_key. 사전 밖 용어(브랜드)까지 만든다 — tools.Toolbox._key 와 같은 규칙.

    ★ gate.term_key() 만 쓰면 브랜드가 "None:살로몬" 이 된다(lex.facet_of 에
      없으므로). 그러면 report.build_term 이 못 찾아 available=False 가 되고,
      블록이 통째로 안 그려진다. 지표 조회는 되는데 카드만 비는 상태가 된다.
      2026-09-09 실측: "살로몬 XT-6 …" 답변에 블록이 note 하나뿐이었다.
    """
    f = hint or gate.facet_of(term)
    if not f:
        try:
            f = store.metric_facet(term)
        except Exception:                       # noqa: BLE001
            f = None
    return f"{f}:{term}"


def _scan(trace) -> dict[str, Any]:
    """궤적에서 '무엇을 조회했나' 만 뽑는다. 값은 여기서 쓰지 않는다."""
    got: dict[str, Any] = {"metric": {}, "metric_results": {}, "facets": {},
                           "evidence": set(), "evidence_results": {},
                           "rank": None, "web": None, "as_of": None, "similar": None,
                           "taste": None, "season": None, "salmal": None,
                           "no_metric": {}, "market": {}}
    for c in (trace.calls if trace else []):
        name, args = c.get("tool"), (c.get("args") or {})
        res = c.get("result")
        if not isinstance(res, dict):
            continue
        if res.get("as_of") and not got["as_of"]:
            got["as_of"] = str(res["as_of"])

        if name == "search_terms":
            for h in (res.get("found") or []):
                if h.get("term") and h.get("facet"):
                    got["facets"][h["term"]] = h["facet"]
        elif name == "get_metric" and res.get("has_metric"):
            term = res.get("term") or args.get("term")
            if term:
                axes = set(args.get("axes") or [])
                got["metric"].setdefault(term, set()).update(axes)
                got["metric_results"][term] = res
        elif name == "get_metric" and res.get("has_metric") is False:
            # ★ 찾아봤는데 없었다는 것도 결과다 (2026-09-11).
            #   예전에는 여기서 통째로 버려서, 조회한 용어가 전부 무측정이면
            #   카탈로그가 비고 **리포트 카드가 아예 뜨지 않았다.** 화면에는
            #   문장만 남아 무엇을 보고 그렇게 말했는지 확인할 자리가 없었다.
            term = res.get("term") or args.get("term")
            if term:
                got["no_metric"].setdefault(
                    term, str(res.get("reason") or "아직 측정된 지표가 없습니다."))
        elif name == "get_evidence" and (res.get("count") or 0) > 0:
            term = res.get("term") or args.get("term")
            if term:
                got["evidence"].add(term)
                got["evidence_results"][term] = res
        elif name == "rank_terms" and (res.get("items") or []):
            got["rank"] = res
        elif name == "similar_terms" and (res.get("items") or res.get("alternatives")):
            # ★ alternatives 만 있어도 그린다. 제목이 "아이템 축에서 지금 높은 것"
            #   으로 바뀌므로 화면이 잘못 말하지 않는다(_similar_block).
            got["similar"] = res
        elif name == "web_search" and (res.get("items") or []):
            got["web"] = res
        elif name == "get_user_taste":
            # unavailable 도 질문의 의미를 드러내는 결과다. 사용자가 취향을
            # 요청했는데 데이터가 없었다면 그 사실을 해당 섹션에서 말한다.
            got["taste"] = res
        elif name == "season_fit" and (res.get("items") or res.get("unknown")):
            got["season"] = res
        elif name == "get_salmal_index":
            got["salmal"] = res
        elif name == "get_market" and not res.get("unavailable") and not res.get("error"):
            # 수명주기 · 할인 · 리셀 — 축마다 마지막 결과 하나 (2026-10-02, 살말 판정 템플릿)
            axis = str(res.get("axis") or args.get("axis") or "")
            if axis in ("lifecycle", "discount", "resale"):
                got["market"][axis] = res
    return got


def _trace_metric_entries(term: str, axes: set, res: dict, facet: str | None,
                          as_of: str) -> list[dict]:
    """저장소 재조회가 실패해도 이미 검증된 get_metric 결과로 핵심 카드를 살린다.

    평소에는 report.build_term 이 더 풍부한 블록을 만든다. 이 함수는 그 재조회가
    순간적으로 실패한 경우에만 쓰는 안전망이며, 도구 응답에 없는 값은 만들지 않는다.
    """
    out: list[dict] = []
    temp = res.get("온도")
    if isinstance(temp, dict) and temp.get("temp") is not None:
        rows = [{"k": "트렌드 온도", "small": str(temp.get("verdict") or temp.get("band") or ""),
                 "v": f"{temp['temp']}점", "up": float(temp["temp"]) >= 65}]
        sample = temp.get("sample_n")
        if sample is not None:
            rows.append({"k": "언급량", "small": "최근 28일",
                         "v": f"{int(sample):,}건", "up": int(sample) >= 20})
        block = {"type": "rank", "slot": "left", "title": term,
                 "meta": " · ".join(x for x in (FACET_SAY.get(facet or "", facet or ""),
                                                   str(res.get("as_of") or as_of)) if x),
                 "rows": rows}
        entry = _content("metric", block, term=term)
        if entry:
            out.append(entry)

    raw_sources = res.get("출처별")
    if "출처별" in axes and isinstance(raw_sources, list) and raw_sources:
        # get_metric 의 출처별 = 트렌드 분석 '플랫폼별 온도' 표(trend_view.platforms).
        #   예전 모양(source_code · raw_count)도 읽는다 — 시험 기록과 옛 궤적.
        sources = []
        for s in raw_sources:
            if not isinstance(s, dict):
                continue
            code = str(s.get("code") or s.get("source_code") or "")
            sources.append({"name": report.SOURCE_KO.get(code.lower(), s.get("name") or code or "출처"),
                            "raw_count": s.get("mention", s.get("raw_count"))})
        entry = _content("sources", B.b_sources({"sources": sources},
                                                 str(res.get("as_of") or as_of)), term=term)
        if entry:
            out.append(entry)
    return out


def _trace_evidence_entry(term: str, res: dict) -> dict | None:
    items = []
    for row in (res.get("items") or [])[:4]:
        if not isinstance(row, dict) or not row.get("body"):
            continue
        items.append({"src": str(row.get("platform") or "출처 미상"), "kind": "",
                      "tone": B.TONE_KO.get(row.get("sentiment"), row.get("sentiment")),
                      "body": str(row["body"])})
    if not items:
        return None
    return _content("evidence", {"type": "quotes", "slot": "right",
                                  "title": "근거가 된 대목", "meta": f"{len(items)}건",
                                  "items": items}, term=term)


def _rank_block(res: dict, as_of: str) -> dict | None:
    """rank_terms 결과 → 순위 블록.

    ★ short_of_asked 를 meta 에 적는다. 10개를 물었는데 4개뿐이면 그 사실이
      화면에도 있어야 한다 — 문장에만 있으면 카드만 본 사람은 4개가 전부인 줄
      모르고 '나머지는 어디 갔나' 로 읽는다.
    """
    items = res.get("items") or []
    if not items:
        return None
    meta = as_of or ""
    if res.get("window_days"):
        # ★ 하루 순위가 아니다 (2026-10-01) — 최근 며칠 안에서 용어마다 마지막 값이다.
        meta = f"최근 {res['window_days']}일" + (f" · {meta} 기준" if meta else "")
    if res.get("short_of_asked"):
        meta = (meta + " · " if meta else "") + f"찾은 것 {len(items)}개가 전부입니다"
    rows = []
    for it in items[:8]:
        temp = it.get("temp")
        # ★ 축 이름은 한글(facet_name)로 — 예전엔 rank_terms 가 주지 않아 'item' 이 그대로 떴다.
        #   온도는 rank_terms 가 화면처럼 반올림해 준다. 여기서 int() 로 다시 자르지 않는다.
        small = it.get("facet_name") or FACET_SAY.get(it.get("facet") or "", it.get("facet") or "")
        day = str(it.get("date") or "")
        if day and day != as_of:
            # 기준일과 다른 날의 값이면 그 날짜를 옆에 적는다 (9/30 → "9/30")
            small = f"{small} · {int(day[5:7])}/{int(day[8:10])}" if len(day) >= 10 else small
        rows.append({"k": it.get("term") or "",
                     "small": small,
                     "v": (f"{temp}점" if temp is not None else "—"),
                     "up": (temp is not None and float(temp) >= 65)})
    # 오른쪽 숫자가 무엇인지 — 순위의 기준이 곧 그 값이다 (2026-10-02)
    meta = "트렌드 온도순" + (f" · {meta}" if meta else "")
    return {"type": "rank", "slot": "full", "title": "지금 뜨는 것",
            "meta": meta, "rows": rows}


def _similar_block(res: dict, as_of: str) -> dict | None:
    """비슷한 것 — 순위표와 같은 모양으로 그린다 (2026-09-10).

    ★ 새 블록 타입을 만들지 않는다. 프론트가 모르는 type 은 **에러 없이 안
      그려진다**(인수인계 4장). rank 는 이미 아는 모양이라 그대로 쓴다.
    ★ 온도가 있는 것(축 상위)과 없는 것(연관어)이 섞인다. 없는 자리에
      숫자를 채우지 않고 왜 뽑혔는지를 적는다.
    ★ items 가 비면 '비슷한 것' 을 못 찾은 것이다. 그때는 alternatives 를
      **다른 제목으로** 그린다. 같은 제목 아래 두면 화면이 거짓말을 한다.
    """
    items = res.get("items") or []
    fallback = not items
    if fallback:
        items = res.get("alternatives") or []
    if not items:
        return None
    rows = []
    for it in items[:8]:
        temp = it.get("temp")
        # ★ 왜 뽑혔는지를 적는다. 겹친 말이 있으면 그것이 제일 설득력 있는 이유다.
        shared = it.get("shared") or []
        why = ("함께 쓰이는 말: " + " · ".join(shared[:3])) if shared else (it.get("why") or "")
        rows.append({"k": it.get("term") or "", "small": why,
                     "v": (f"{int(temp)}점" if temp is not None else "—"),
                     "up": (temp is not None and int(temp) >= 50)})
    base = str(res.get("term") or "").strip()
    # ★ 제목과 내용이 어긋나지 않게 한다 (2026-09-10).
    #   연관어가 얇아 축 상위로 대신한 목록에 "팬츠와 비슷한 것" 을 달면,
    #   자켓·백팩이 팬츠와 비슷하다고 화면이 말하는 셈이 된다.
    if fallback:
        axis = FACET_SAY.get(res.get("facet") or "", "같은")
        title = f"{axis} 축에서 지금 높은 것"
    else:
        title = f"{base}{_wa(base)} 비슷한 것" if base else "비슷한 것"
    # 오른쪽 '점' 이 무엇인지 — 연관 정도가 아니라 그 용어의 트렌드 온도다 (2026-10-02)
    meta = " · ".join(x for x in ("점 = 트렌드 온도", as_of or "") if x)
    return {"type": "rank", "slot": "full", "title": title,
            "meta": meta, "rows": rows}


def _wa(word: str) -> str:
    """받침을 보고 '와/과' 를 고른다. '트랙탑 와(과)' 처럼 쓰지 않는다."""
    ch = (word or "").strip()[-1:]
    if not ch or not ("가" <= ch <= "힣"):
        return "와"
    return "과" if (ord(ch) - 0xAC00) % 28 else "와"


def _evidence_links(node: dict) -> dict | None:
    """근거 중 **원문으로 돌아갈 수 있는 것만** 링크로.

    없는 것은 아예 넣지 않는다. 인용 블록(b_evidence)에는 그대로 남아 있으므로
    '인용은 3건인데 링크는 2건' 이 화면에서도 그대로 보인다. 링크가 없는 근거에
    검색 결과 주소 같은 것을 붙이면 누른 사람이 우리가 인용하지 않은 글에
    도착한다 — store.evidence_link() 가 네이버에 대해 None 을 주는 이유다.
    """
    items = []
    for e in (node.get("evidence") or [])[:4]:
        url = e.get("url")
        if not url:
            continue
        title = str(e.get("body") or "").strip()
        items.append({"url": url,
                      "title": (title[:40] + "…") if len(title) > 41 else title})
    if not items:
        return None
    return {"type": "links", "slot": "right", "items": items}


def _taste_section(res: dict | None) -> dict | None:
    """취향 도구가 실제로 불렸을 때만 섹션을 만든다.

    현재 어댑터는 대부분 unavailable 이다. 미래 어댑터가 ``items`` 또는
    ``tags`` 로 이름·점수를 주면 기존 rank 블록으로 바로 그릴 수 있게 하되,
    알 수 없는 모양을 짐작해 채우지는 않는다.
    """
    if not isinstance(res, dict):
        return None
    if res.get("unavailable"):
        return {"key": "taste", "label": "취향분석", "state": "unavailable",
                "message": str(res["unavailable"])}
    if res.get("logged_in") is False:
        return {"key": "taste", "label": "취향분석", "state": "unavailable",
                "message": str(res.get("note") or "로그인하면 취향분석을 볼 수 있습니다.")}

    raw = res.get("items") or res.get("tags") or []
    rows = []
    for item in raw[:6] if isinstance(raw, list) else []:
        if isinstance(item, str):
            rows.append({"k": item, "small": "", "v": "", "up": True})
            continue
        if not isinstance(item, dict):
            continue
        name = item.get("canonical") or item.get("name") or item.get("tag")
        if not name:
            continue
        value = item.get("score", item.get("match", item.get("value")))
        rows.append({"k": str(name), "small": str(item.get("why") or ""),
                     "v": (str(value) if value is not None else ""), "up": True})
    if rows:
        return {"key": "taste", "label": "취향분석", "state": "ready",
                "blocks": [{"type": "rank", "slot": "full", "title": "나의 취향",
                            "meta": "", "rows": rows}]}
    return {"key": "taste", "label": "취향분석", "state": "unavailable",
            "message": "취향 데이터 형식을 확인하지 못해 화면에 표시하지 않았습니다."}


def _season_blocks(res: dict | None) -> list[dict]:
    """season_fit 결과를 일반 착용 기준 섹션으로 만든다."""
    if not isinstance(res, dict):
        return []
    rows = []
    for item in (res.get("items") or [])[:6]:
        if not isinstance(item, dict) or not item.get("term"):
            continue
        verdict = str(item.get("verdict") or "—")
        rows.append({"k": str(item["term"]), "small": str(item.get("say") or ""),
                     "v": verdict, "up": verdict in ("적합", "무관")})
    unknown = [str(term) for term in (res.get("unknown") or [])[:3] if term]
    if unknown:
        rows.append({"k": "판단하지 않은 항목", "small": " · ".join(unknown),
                     "v": "기준표 없음", "up": False})
    if not rows:
        return []
    basis = str(res.get("basis") or "")
    return [
        {"type": "rank", "slot": "full", "title": "상황에 맞는지",
         "meta": basis, "rows": rows},
        {"type": "note", "slot": "full",
         "text": "일반적인 착용 기준이며 FEEDiT 트렌드 측정값이 아닙니다."},
    ]


def salmal_blocks(res: dict | None) -> list[dict]:
    """검증된 살말 지수 → 판정 블록(도장 · 가중치 × 점수 막대) (2026-10-02).

    ★ 예전엔 KPI 세 칸 + 근거 순위 + 빠진 신호 안내 셋으로 그렸다. 셋이 같은 판단의
      다른 면이라 한 블록에 모았다 — 빠진 신호는 막대 자리에 '없음' 으로 남는다.
    """
    if not isinstance(res, dict):
        return []
    verdict = B.b_verdict(res)
    if verdict is None:
        return [{"type": "note", "slot": "full",
                 "text": "살말 지수를 계산할 근거가 아직 부족합니다."}]
    why = (res.get("missing_why") or {}).get("taste")
    if "taste" in (res.get("missing") or []) and why:
        verdict["missing_note"] = f"취향: {why}"
    return [verdict]


def _content(kind: str, block: dict | None, *, term: str | None = None,
             suffix: str = "") -> dict | None:
    """실제 블록에 안정적인 참조 id 를 붙여 디자인 스킬용 카탈로그로 만든다."""
    if not block:
        return None
    ident = f"{kind}:{term or 'all'}" + (f":{suffix}" if suffix else "")
    return {"id": ident, "kind": kind, "term": term, "block": block}


def build(trace, store, gate, question: str = "") -> list[dict]:
    """궤적 → 블록 목록. 조회한 것이 없으면 빈 목록을 돌려준다.

    빈 목록이면 agent_path 가 report 이벤트를 보내지 않는다 — 빈 카드를
    그리느니 카드를 안 그리는 쪽이 맞다.
    """
    if trace is None or store is None:
        return []
    got = _scan(trace)
    as_of = got["as_of"] or ""
    catalog: list[dict] = []

    # ★ 먼저 node 를 다 만든다. 둘 이상이면 나란히 보기를 앞에 세우기 위해서다.
    built: list[tuple[str, set, dict]] = []
    trace_fallbacks: list[dict] = []
    fallback_terms: set[str] = set()
    for term, axes in list(got["metric"].items())[:MAX_TERMS]:
        node = None
        try:
            key = _key_for(term, gate, store, got["facets"].get(term))
            # ★ get_metric 과 같은 어댑터·같은 캐시로 읽는다(trend_view.source).
            #   문장과 카드가 같은 응답에서 나와야 "상위 1%" 옆에 "상위 82%" 가 서지 않는다.
            node = report.build_term(
                store, gate,
                {"term_key": key, "canonical": term,
                 "facet": _facet_of(key, got["facets"].get(term))},
                as_of or "", with_sentiment="긍부정" in axes,
                with_assoc="연관어" in axes, with_evidence=term in got["evidence"])
        except Exception:                       # noqa: BLE001
            # 저장소 재조회가 실패해도 도구가 이미 돌려준 값은 버리지 않는다.
            node = None
        if not isinstance(node, dict) or not node.get("available"):
            recovered = _trace_metric_entries(
                term, axes, got["metric_results"].get(term) or {},
                got["facets"].get(term), as_of)
            if recovered:
                trace_fallbacks.extend(recovered)
                fallback_terms.add(term)
            continue
        built.append((term, axes, node))

    if got["rank"]:
        entry = _content("ranking", _rank_block(got["rank"], as_of))
        if entry:
            catalog.append(entry)
        entry = _content("leaderboard", B.b_leaderboard(got["rank"]))
        if entry:
            catalog.append(entry)
    # ── 템플릿 그림 (2026-10-02) ───────────────────────────
    #   같은 노드에서 그림만 다르게 만든다. 어떤 것을 화면에 세울지는
    #   report_skill.choose_template 이 정하고, 나머지는 버린다.
    if len(built) == 2:
        entry = _content("versus", B.b_versus([n for _, _, n in built]))
        if entry:
            catalog.append(entry)
    for term, axes, node in built:
        visual = [
            (_content("ticker", B.b_ticker(node, as_of or ""), term=term)
             if not axes or axes & {"온도", "순위", "모멘텀"} else None),
            _content("timeline", B.b_timeline(node, evidence=term in got["evidence"]), term=term),
            _content("orbit", B.b_orbit(node), term=term) if "연관어" in axes else None,
            _content("lowsignal", B.b_lowsignal(node), term=term),
        ]
        catalog.extend(e for e in visual if e)
    lifecycle = got["market"].get("lifecycle")
    if lifecycle:
        entry = _content("lifecycle", B.b_lifecycle(lifecycle),
                         term=str(lifecycle.get("term") or "") or None)
        if entry:
            catalog.append(entry)
    if got["market"].get("discount") or got["market"].get("resale"):
        entry = _content("market", B.b_market(got["market"]))
        if entry:
            catalog.append(entry)
    # 비교 블록은 온도/순위를 실제로 요청했을 때만 만든다. 감성만 물었는데
    # 온도 비교가 따라 나오면 디자인 모델이 지표를 고른다는 계약이 깨진다.
    if len(built) >= 2 and any(axes & {"온도", "순위"} for _, axes, _ in built):
        entry = _content("comparison", B.b_compare([n for _, _, n in built], as_of or ""))
        if entry:
            catalog.append(entry)
    # 재조회 안전망도 일반 모듈과 같은 생성형 캔버스에 들어간다. compose_report 가
    # 없거나 해당 모듈을 고르지 못해도 report_skill 의 폴백이 화면을 보존한다.
    catalog.extend(trace_fallbacks)
    for term in fallback_terms:
        evidence = _trace_evidence_entry(term, got["evidence_results"].get(term) or {})
        if evidence:
            catalog.append(evidence)
    for term, axes, node in built:
        entries = [
            (_content("metric", B.b_metric_rank(node, as_of or node.get("observed_on") or ""), term=term)
             if not axes or axes & {"온도", "순위"} else None),
            _content("direction", B.b_direction(node), term=term) if "모멘텀" in axes else None,
            _content("sources", B.b_sources(node, as_of or ""), term=term) if "출처별" in axes else None,
            _content("associations", B.b_assoc(node), term=term) if "연관어" in axes else None,
            _content("sentiment", B.b_sentiment(node), term=term, suffix="summary") if "긍부정" in axes else None,
            _content("sentiment", B.b_sentiment_signal(node), term=term, suffix="signals") if "긍부정" in axes else None,
        ]
        catalog.extend(e for e in entries if e)
        if term in got["evidence"]:
            for entry in (
                _content("evidence", B.b_evidence(node), term=term),
                _content("links", _evidence_links(node), term=term),
            ):
                if entry:
                    catalog.append(entry)

    if got["similar"]:
        entry = _content("recommendations", _similar_block(got["similar"], as_of),
                         term=str(got["similar"].get("term") or "") or None)
        if entry:
            catalog.append(entry)

    taste = _taste_section(got["taste"])
    if taste:
        if taste.get("state") == "ready":
            for i, block in enumerate(taste.get("blocks") or []):
                entry = _content("taste", block, suffix=str(i))
                if entry:
                    catalog.append(entry)
        else:
            catalog.append(_content("taste", {"type": "note", "slot": "full",
                                               "text": taste.get("message")}))

    context_blocks = _season_blocks(got["season"])
    for i, block in enumerate(context_blocks):
        entry = _content("context", block, suffix=str(i))
        if entry:
            catalog.append(entry)

    for i, block in enumerate(salmal_blocks(got["salmal"])):
        entry = _content("salmal", block, term=str((got["salmal"] or {}).get("term") or "") or None,
                         suffix=str(i))
        if entry:
            catalog.append(entry)

    if got["web"]:
        src = [{"url": h.get("url"), "title": h.get("title")}
               for h in (got["web"].get("items") or [])[:4] if h.get("url")]
        if src:
            catalog.extend(filter(None, [
                _content("evidence", {"type": "note", "slot": "full",
                                      "text": "아래 출처는 웹에서 찾은 것으로, FEEDiT 측정값이 아닙니다."},
                         suffix="web-note"),
                _content("links", {"type": "links", "slot": "full", "items": src},
                         suffix="web-links"),
            ]))

    # 찾아봤지만 지표가 없던 용어. 이미 값이 있거나 declare_missing 으로
    # 기록된 용어는 빼서 같은 말을 두 번 하지 않는다.
    declared = {str(m.get("term") or "") for m in (trace.missing or [])}
    for i, (term, reason) in enumerate(
            [(t, r) for t, r in got["no_metric"].items()
             if t not in got["metric"] and t not in declared][:3]):
        catalog.append(_content(
            "missing",
            {"type": "note", "slot": "full", "text": f"{term} — {reason}"},
            term=term, suffix=f"nometric{i}"))

    for i, m in enumerate((trace.missing or [])[:3]):
        catalog.append(_content(
            "missing",
            {"type": "note", "slot": "full",
             "text": f"{m.get('term')} — {m.get('axis')}: 아직 측정 자료가 없습니다."},
            term=str(m.get("term") or "") or None, suffix=str(i)))

    catalog = [c for c in catalog if c]
    if not catalog:
        return []
    canvas = report_skill.build(catalog, trace)
    return [canvas] if canvas else []
