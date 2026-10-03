"""도구 결과를 매 요청마다 새로운 리포트 캔버스로 조립한다.

이 모듈은 ``ranking``/``pulse`` 같은 완성 양식을 고르지 않는다. 오케스트레이터가
데이터를 조회한 뒤 ``compose_report`` 도구로 남긴 UI 스펙을 읽고, 실제 데이터
블록을 그 스펙에 결합한다.

모델이 정하는 것
  · 어떤 결과를 보여 줄지
  · 각 결과의 표현 역할(hero/card/chart/list/editorial/compact)
  · 12열 캔버스에서 차지할 폭과 강조도
  · 전체 색·표면·밀도

모델이 정하지 못하는 것
  · 수치·상품·출처 자체
  · HTML·CSS·스크립트

모든 내용은 ``catalog`` 에 이미 있는 블록 id 로만 결합된다. 존재하지 않는
kind/term 을 요청하면 조용히 제외한다. 모델 호출이 끊겨 스펙이 없을 때는 콘텐츠를
순서대로 흘리는 안전한 폴백을 쓰지만, 이 역시 이름 붙은 완성 양식은 아니다.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


KINDS = {
    "ranking", "comparison", "metric", "direction", "sources", "salmal",
    "associations", "sentiment", "recommendations", "taste", "context",
    "evidence", "links", "missing", "lifecycle", "market",
}
# ── 리포트 템플릿 (2026-10-02) ─────────────────────────────
#   질문 유형마다 한눈에 읽히는 그림이 있다. 모델은 템플릿 이름만 고르고, 그 템플릿에
#   필요한 그림(VISUAL_KINDS)이 실제 결과에 없으면 서버가 결과에 맞는 템플릿으로 바꾼다.
#     ticker      진단   "요즘 어때?" "뜨고 있어?"        get_metric(온도)
#     verdict     판정   "살까 말까?" "사도 될까?"         get_salmal_index (+ get_market)
#     why         원인   "왜 떴어?" "어디서 뜬 거야?"      get_metric + get_evidence
#     versus      비교   "A vs B" "뭐가 더 떠?"           get_metric 두 용어
#     leaderboard 순위   "TOP 10" "요즘 뭐가 떠?"          rank_terms
#     orbit       연관   "같이 뜨는 거?" "뭐랑 입어?"      get_metric(연관어)
#     lowsignal   관측 부족 — 모델이 고르지 않는다. 주인공 용어의 언급이 얇으면 서버가 바꾼다.
#     canvas      섞인 결과 — 예전 생성형 캔버스(모델이 모듈을 직접 배치)
#   ★ 템플릿은 '그림의 문법' 이다. 값은 여전히 도구 결과에서만 나온다.
TEMPLATES = ("ticker", "verdict", "why", "versus", "leaderboard", "orbit", "lowsignal", "canvas")
VISUAL_KINDS = {"ticker", "timeline", "versus", "leaderboard", "orbit", "lowsignal"}
# 템플릿의 주인공 그림 · 그 그림이 이미 보여 주므로 따로 세우지 않는 종류
TEMPLATE_LEAD = {"ticker": "ticker", "why": "timeline", "versus": "versus",
                 "leaderboard": "leaderboard", "orbit": "orbit", "lowsignal": "lowsignal"}
TEMPLATE_COVERS = {
    "ticker": {"metric", "direction", "sources", "associations"},
    "why": {"evidence", "links", "sentiment", "metric", "direction"},
    "versus": {"comparison", "metric", "direction", "sentiment"},
    "leaderboard": {"ranking"},
    "orbit": {"associations"},
    "lowsignal": {"metric", "direction", "sources", "associations"},
    "verdict": set(),
}
TEMPLATE_TITLES = {
    "ticker": "{term} 지금 온도", "why": "{term}, 왜 지금일까", "versus": "{term} 비교",
    "leaderboard": "지금 뜨는 흐름", "orbit": "{term}{wa} 같이 뜨는 것",
    "lowsignal": "{term}, 아직 관측 중", "verdict": "{term} 살까 말까",
}
PRESENTATIONS = {"hero", "card", "chart", "list", "editorial", "compact"}
EMPHASIS = {"strong", "normal", "quiet"}
ACCENTS = {"coral", "ink", "violet", "blue", "lime"}
SURFACES = {"paper", "soft", "contrast", "glass"}
DENSITIES = {"airy", "balanced", "compact"}
MAX_MODULES = 9

# 모델은 정보의 위계와 폭을 고르되, 데이터 모양과 맞지 않는 표면까지 만들지는 못한다.
# rank 를 editorial 로 그리면 같은 표 안에서도 어떤 것은 베이지 지면, 어떤 것은
# 테두리 카드가 되어 새 지표가 생길 때마다 디자인이 달라진다.
BLOCK_PRESENTATIONS = {
    "rank": {"hero", "card", "list"},
    "kpis": {"hero", "card"},
    "bars": {"hero", "card", "chart"},
    "table": {"hero", "card", "list"},
    "quotes": {"editorial", "card"},
    "links": {"editorial", "compact"},
    "note": {"editorial", "compact", "card"},
}
BLOCK_DEFAULT_PRESENTATION = {
    "rank": "card", "kpis": "card", "bars": "chart", "table": "card",
    "quotes": "editorial", "links": "compact", "note": "compact",
}


def _pick(value: Any, allowed: set[str], fallback: str) -> str:
    value = str(value or "")
    return value if value in allowed else fallback


def _span(value: Any, fallback: int = 6) -> int:
    try:
        return max(4, min(12, int(value)))
    except (TypeError, ValueError):
        return fallback


def _presentation(content: dict, requested: Any) -> str:
    """블록의 정보 구조를 보존하는 범위에서만 모델의 표현 선택을 허용한다."""
    block = content.get("block") if isinstance(content, dict) else None
    block_type = str((block or {}).get("type") or "")
    picked = _pick(requested, PRESENTATIONS, "card")
    allowed = BLOCK_PRESENTATIONS.get(block_type, PRESENTATIONS)
    return picked if picked in allowed else BLOCK_DEFAULT_PRESENTATION.get(block_type, "card")


def design_from(trace) -> dict | None:
    """가장 마지막 ``compose_report`` 결과만 읽는다."""
    for call in reversed(trace.calls if trace else []):
        if call.get("tool") != "compose_report":
            continue
        result = call.get("result")
        if isinstance(result, dict) and result.get("ok") and isinstance(result.get("spec"), dict):
            return result["spec"]
    return None


def _match(catalog: list[dict], used: set[str], kind: str,
           term: str | None) -> dict | None:
    candidates = [c for c in catalog if c.get("id") not in used and c.get("kind") == kind]
    if term:
        exact = [c for c in candidates if str(c.get("term") or "") == term]
        if exact:
            return exact[0]
        return None
    return candidates[0] if candidates else None


def _fallback_modules(catalog: list[dict]) -> list[dict]:
    """디자인 호출 실패 시 데이터 순서를 보존하는 유동형 캔버스."""
    out = []
    for i, content in enumerate(catalog[:MAX_MODULES]):
        kind = content.get("kind")
        strong = i == 0 and kind not in ("links", "missing")
        out.append({
            "content": content,
            "presentation": "hero" if strong else ("editorial" if kind in ("evidence", "links") else "card"),
            "span": 12 if strong or kind in ("ranking", "comparison", "missing") else 6,
            "emphasis": "strong" if strong else ("quiet" if kind in ("links", "missing") else "normal"),
        })
    return out


def _fallback_title(catalog: list[dict]) -> str:
    """내용 종류와 실제 용어만으로 짧은 편집 제목을 만든다."""
    kinds = {str(content.get("kind") or "") for content in catalog}
    terms = list(dict.fromkeys(
        str(content.get("term") or "").strip()
        for content in catalog if str(content.get("term") or "").strip()
    ))
    if "context" in kinds:
        return "오늘의 옷차림"
    if "salmal" in kinds:
        return "나를 위한 살말 리포트"
    if "comparison" in kinds and len(terms) >= 2:
        return f"{terms[0]} · {terms[1]} 비교"
    if "ranking" in kinds:
        return "지금 뜨는 흐름"
    if len(terms) == 1:
        suffix = "다음 탐색" if "recommendations" in kinds else "흐름"
        return f"{terms[0]} {suffix}"
    if "taste" in kinds:
        return "나의 취향 지도"
    if "recommendations" in kinds:
        return "추천 탐색"
    if "evidence" in kinds or "links" in kinds:
        return "근거 한눈에"
    return "FEEDiT 트렌드 브리프"


def _normalize_notes(modules: list[dict]) -> None:
    """안내문(note)은 누가 고르든 **한 가지 모양**으로 그린다.

    ★ 왜 (2026-09-11 실측)
      같은 화면 안에서 "상품 단위 지표: 측정 자료 없음" 은 베이지 지면
      (editorial), "이번 판단에 빠진 신호" 는 흰 카드, "판매가·재고·세일"
      은 점선 상자로 나왔다. 셋 다 **같은 말**(없는 자료)인데 모양이 셋이라
      사용자는 서로 다른 종류의 정보로 읽는다. 모델이 고른 표현이든 서버가
      덧붙인 것이든, 안내문은 안내문이다.
    """
    for module in modules:
        block = (module.get("content") or {}).get("block") or {}
        if block.get("type") != "note":
            continue
        module["presentation"] = "compact"
        module["emphasis"] = "normal"
        module["span"] = 12


def _pack_rows(modules: list[dict]) -> None:
    """한 줄에 남는 칸이 있으면 그 줄의 마지막 모듈이 끝까지 채운다.

    ★ 왜 (2026-09-11 실측)
      '트랙 자켓 구매 판단' 에서 방향 지표가 6열짜리 모듈 하나로 놓여
      오른쪽 절반이 통째로 비었다. 12열 캔버스는 모델이 폭을 고르지만,
      **비어 있는 칸은 디자인이 아니라 사고**다. 순서와 위계는 그대로 두고
      줄 끝의 여백만 메운다.
    """
    row: list[dict] = []
    used = 0
    for module in modules:
        span = module["span"]
        if row and used + span > 12:
            row[-1]["span"] += 12 - used
            row, used = [], 0
        row.append(module)
        used += span
        if used >= 12:
            row, used = [], 0
    if row and used < 12:
        row[-1]["span"] += 12 - used


def _module_payload(module: dict) -> dict:
    """콘텐츠 개수까지 보고 브라우저가 안전하게 그릴 레이아웃 힌트를 붙인다.

    모델은 정보 관계와 모듈 폭을 고르지만, KPI 안쪽 열 수까지 추측하게 두지 않는다.
    3개 지표는 한 줄 3칸, 4개 지표는 좁은 모듈에서 2×2가 기본이다. 실제 픽셀 폭이
    넓으면 CSS 컨테이너 규칙이 4칸으로 확장한다.
    """
    content = module["content"]
    block = content["block"]
    payload = {
        "id": content["id"], "kind": content["kind"],
        "presentation": module["presentation"], "span": module["span"],
        "emphasis": module["emphasis"], "block": block,
    }
    if block.get("type") == "kpis":
        count = len(block.get("items") or [])
        if count:
            # 폭을 다 쓰는 모듈이면 4개도 한 줄에 선다. 좁은 모듈에서만 2×2.
            wide = module["span"] >= 10
            payload["columns"] = (count if count <= 4 and wide else
                                  3 if count == 3 else min(count, 2))
    return payload


def _wa(word: str) -> str:
    ch = (word or "").strip()[-1:]
    if not ch or not ("가" <= ch <= "힣"):
        return "와"
    return "과" if (ord(ch) - 0xAC00) % 28 else "와"


def _lead(catalog: list[dict], kind: str, term: str | None) -> dict | None:
    rows = [c for c in catalog if c.get("kind") == kind]
    if term:
        exact = [c for c in rows if str(c.get("term") or "") == term]
        if exact:
            return exact[0]
    return rows[0] if rows else None


def _verdict(catalog: list[dict]) -> dict | None:
    return next((c for c in catalog if c.get("kind") == "salmal"
                 and (c.get("block") or {}).get("type") == "verdict"), None)


def choose_template(spec: dict | None, catalog: list[dict]) -> tuple[str, dict | None]:
    """(템플릿 이름, 주인공 콘텐츠). 모델이 고른 것을 먼저 보되 결과가 정한다.

    ★ 질문 문장을 보지 않는다. 무엇을 조회했고 무엇이 돌아왔는지(카탈로그)만 본다 —
      같은 질문이라도 데이터가 얇으면 다른 그림이 맞다(AGENTS.md §6).
    """
    spec = spec or {}
    want = str(spec.get("template") or "")
    focus = str(spec.get("term") or "").strip() or None

    def lead_of(name: str) -> dict | None:
        if name == "verdict":
            return _verdict(catalog)
        kind = TEMPLATE_LEAD.get(name)
        return _lead(catalog, kind, focus) if kind else None

    def thin(content: dict | None) -> dict | None:
        """주인공 용어의 관측이 얇으면 그 용어의 관측 부족 카드."""
        if not content or not content.get("term"):
            return None
        return next((c for c in catalog if c.get("kind") == "lowsignal"
                     and c.get("term") == content.get("term")), None)

    # 예전 스펙(템플릿 없이 모듈만) — 모델이 직접 배치한 캔버스를 존중한다.
    if want == "canvas" or (not want and spec.get("modules")):
        return "canvas", None
    if want in TEMPLATES and want != "canvas":
        hit = lead_of(want)
        if hit:
            if want in ("ticker", "why", "orbit"):
                low = thin(hit)
                if low:
                    return "lowsignal", low
            return want, hit
    # 결과로 고른다 — 판정 → 순위 → 비교 → 원인(근거를 조회했을 때만) → 진단 → 연관
    if _verdict(catalog):
        return "verdict", _verdict(catalog)
    for name in ("leaderboard", "versus"):
        hit = lead_of(name)
        if hit:
            return name, hit
    timeline = lead_of("why")
    if timeline and (timeline.get("block") or {}).get("evidence"):
        return ("lowsignal", thin(timeline)) if thin(timeline) else ("why", timeline)
    for name in ("ticker", "orbit"):
        hit = lead_of(name)
        if hit:
            return ("lowsignal", thin(hit)) if thin(hit) else (name, hit)
    return "canvas", None


def _template_canvas(name: str, lead: dict, catalog: list[dict], spec: dict | None) -> dict:
    """템플릿 하나 = 주인공 그림(12열) + 그 그림이 보여 주지 않는 결과(보조 모듈)."""
    spec = spec or {}
    covers = TEMPLATE_COVERS.get(name, set())
    term = str(lead.get("term") or "")
    modules: list[dict] = []
    used: set[str] = set()

    def add(content: dict, span: int, presentation: str = "hero", emphasis: str = "strong"):
        used.add(content["id"])
        modules.append({"content": content, "presentation": presentation,
                        "span": span, "emphasis": emphasis})

    add(lead, 12)
    if name == "verdict":
        # 살말 판정 옆에는 수명주기와 시세가 선다 — 같은 판단의 근거라서.
        side = [c for c in catalog if c.get("kind") in ("lifecycle", "market")]
        for c in side:
            add(c, 7 if (len(side) == 2 and c.get("kind") == "lifecycle") else
                (5 if len(side) == 2 else 12), "card", "normal")
    elif name in ("ticker", "why", "lowsignal"):
        life = _lead(catalog, "lifecycle", term or None)
        if life:
            add(life, 12, "card", "normal")
    for c in catalog:
        kind = c.get("kind")
        # 주인공 그림이 보여 주는 것은 그 용어의 것만 가린다. 비교·순위는 대상 전체가 주인공이다.
        covered = kind in covers and (name in ("versus", "leaderboard") or not c.get("term")
                                      or str(c.get("term")) == term)
        if c["id"] in used or kind in VISUAL_KINDS or covered:
            continue
        # 다른 용어의 같은 종류는 둔다 — 비교 템플릿이 아닌데 둘째 용어를 조회했다면 보여 준다.
        block_type = str((c.get("block") or {}).get("type") or "")
        span = 12 if block_type in ("rank", "note", "table") or kind in ("missing", "salmal") else 6
        add(c, span, BLOCK_DEFAULT_PRESENTATION.get(block_type, "card"),
            "quiet" if kind in ("missing", "links") else "normal")
    _normalize_notes(modules)
    _pack_rows(modules)

    title = str(spec.get("title") or "").strip()[:48]
    if not title or title.casefold().replace(" ", "") == "feeditsignal":
        if name == "versus":
            block = lead.get("block") or {}
            pair = [str((block.get(k) or {}).get("term") or "") for k in ("a", "b")]
            title = f"{pair[0]} vs {pair[1]}" if all(pair) else "나란히 보기"
        else:
            title = TEMPLATE_TITLES.get(name, "{term}").format(term=term or "", wa=_wa(term))
            title = title.strip(" ,") or _fallback_title(catalog)
    accent = _pick(spec.get("accent"), ACCENTS, "coral")
    surface = _pick(spec.get("surface"), SURFACES, "paper")
    density = _pick(spec.get("density"), DENSITIES, "balanced")
    serial = json.dumps({"template": name, "modules": [
        (m["content"]["id"], m["span"]) for m in modules]}, ensure_ascii=False, sort_keys=True)
    return {
        "type": "generative_report", "slot": "full", "title": title[:48],
        "template": name, "accent": accent, "surface": surface, "density": density,
        # model = 모델이 고른 템플릿 그대로 · auto = 결과에 맞춰 서버가 바꿈 · fallback = 디자인 호출 없음
        "source": ("model" if spec.get("template") == name else "auto" if spec else "fallback"),
        "fingerprint": hashlib.sha1(serial.encode("utf-8")).hexdigest()[:10],
        "modules": [_module_payload(m) for m in modules],
    }


def build(catalog: list[dict], trace) -> dict | None:
    """검증된 콘텐츠 카탈로그와 모델의 UI 스펙을 하나의 캔버스로 결합한다."""
    catalog = [c for c in catalog if isinstance(c, dict) and c.get("id") and c.get("block")]
    if not catalog:
        return None

    spec = design_from(trace)
    name, lead = choose_template(spec, catalog)
    if name != "canvas" and lead:
        return _template_canvas(name, lead, catalog, spec)
    # 캔버스 — 그림 전용 종류는 빼고 예전처럼 조립한다(같은 값을 두 모양으로 세우지 않게).
    catalog = [c for c in catalog if c.get("kind") not in VISUAL_KINDS]
    if not catalog:
        return None
    fallback_title = _fallback_title(catalog)[:48]
    modules: list[dict] = []
    used: set[str] = set()
    if spec:
        for request in (spec.get("modules") or [])[:MAX_MODULES]:
            if not isinstance(request, dict):
                continue
            kind = _pick(request.get("kind"), KINDS, "")
            term = request.get("term")
            term = str(term).strip() if term is not None else None
            content = _match(catalog, used, kind, term)
            if not content:
                continue
            used.add(content["id"])
            modules.append({
                "content": content,
                "presentation": _presentation(content, request.get("presentation")),
                "span": _span(request.get("span")),
                "emphasis": _pick(request.get("emphasis"), EMPHASIS, "normal"),
            })

    # 살말 근거와 없는 자료를 숨기는 디자인은 허용하지 않는다.
    for content in catalog:
        if content.get("kind") in ("salmal", "missing") and content["id"] not in used:
            used.add(content["id"])
            is_missing = content.get("kind") == "missing"
            modules.append({"content": content,
                            "presentation": "compact" if is_missing else _presentation(content, "card"),
                            "span": 12, "emphasis": "quiet" if is_missing else "normal"})

    if not modules:
        modules = _fallback_modules(catalog)
        source = "fallback"
        title, accent, surface, density = fallback_title, "coral", "paper", "balanced"
    else:
        # ★ spec 이 없어도 여기로 온다 (2026-09-11 실측 버그).
        #   바로 위의 "살말·없는 자료는 숨기지 않는다" 루프가 spec 과 무관하게
        #   모듈을 넣기 때문에, compose_report 를 부르기 전에 예산이 끊기면
        #   modules 는 차 있고 spec 은 None 인 상태가 된다. 그 조합에서
        #   spec.get() 이 AttributeError 로 터졌고, agent_path 가 예외를
        #   조용히 삼켜 **리포트 카드가 통째로 사라졌다.** 화면에는 문장만
        #   남아서 원인이 보이지 않았다.
        design = spec or {}
        source = "model" if spec else "fallback"
        title = str(design.get("title") or "").strip()[:48]
        if not title or title.casefold().replace(" ", "") == "feedit signal".replace(" ", ""):
            title = fallback_title
        accent = _pick(design.get("accent"), ACCENTS, "coral")
        surface = _pick(design.get("surface"), SURFACES, "paper")
        density = _pick(design.get("density"), DENSITIES, "balanced")

    # 모듈이 다 정해진 뒤에 시각 문법을 맞춘다 — 모델이 고른 것과 서버가
    # 덧붙인 것이 같은 화면에서 서로 다른 모양이 되지 않게.
    _normalize_notes(modules)
    _pack_rows(modules)

    serial = json.dumps({
        "source": source, "accent": accent, "surface": surface, "density": density,
        "modules": [(m["content"]["id"], m["presentation"], m["span"], m["emphasis"])
                    for m in modules],
    }, ensure_ascii=False, sort_keys=True)
    fingerprint = hashlib.sha1(serial.encode("utf-8")).hexdigest()[:10]

    return {
        "type": "generative_report", "slot": "full", "title": title, "template": "canvas",
        "accent": accent, "surface": surface, "density": density,
        "source": source, "fingerprint": fingerprint,
        "modules": [_module_payload(m) for m in modules],
    }
