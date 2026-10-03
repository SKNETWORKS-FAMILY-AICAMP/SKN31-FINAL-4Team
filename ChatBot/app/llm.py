"""역할별 OpenAI 모델 클라이언트 — Responses API.

전송 방식은 크롤러의 `llm_analysis.py` 와 같되, 챗봇 안에서는 역할별 모델을 쓴다.
도구 선택·해석은 Terra, 값 대조·형식 정리는 Luna가 기본이다.

★ 이 모듈이 지키는 것

1. **키를 절대 출력하지 않는다.** 예외 문구에도 안 넣는다.
   실패하면 예외 종류와 HTTP 상태만 남긴다 (AGENTS.md §8).

2. **실패하면 None 을 돌려준다.** 던지지 않는다.
   LLM 이 죽어도 챗봇은 규칙으로 답해야 한다. LLM 은 거들 뿐이다.

3. **숫자를 만들게 하지 않는다.** 이 모듈은 전송만 한다.
   무엇을 시킬지는 부르는 쪽이 정하고, 숫자 보호는 polish.py 가 자리표시자로 막는다.

★ 키를 어디서 읽나
   ① 환경변수 OPENAI_API_KEY
      — 셸 지정, 도커 `env_file`, 그리고 저장소 루트 `feedit/.env`.
        .env 는 `app/__init__.py` 가 import 시점에 한 번 읽어 둔다(app/env.py).
   ② 크롤러의 data/keys.json (관리자 화면이 저장하는 곳)
   둘 다 없으면 available() 이 False 다 — 챗봇은 그냥 규칙으로 돈다.

   어디서 읽혔는지는 `source_hint()` 로 본다. 값은 안 나온다.
   설정이 맞는지 한 번에 보려면: `python3 tools_env_check.py`
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from .config import CRAWLER

# ── 어디로 · 어떤 모델로 보내나 ────────────────────────────────
#   전부 환경변수로 뺐다. 팀원마다 다른 값을 쓸 수 있어야 하고,
#   모델을 바꿀 때 코드를 고치면 누가 언제 바꿨는지가 기록에 안 남는다.
#
#   OPENAI_BASE_URL   기본 https://api.openai.com/v1
#                     사내 게이트웨이·프록시를 쓸 때만 바꾼다.
#   FEEDIT_LLM_MODEL  기본 gpt-5.6-luna
#   FEEDIT_LLM_EFFORT 기본 low — 부르는 쪽이 따로 정하면 그쪽이 이긴다.
#                     none · low · medium · high · xhigh · max
API = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
MODEL = os.getenv("FEEDIT_LLM_MODEL", "gpt-5.6-luna")
DEFAULT_EFFORT = (os.getenv("FEEDIT_LLM_EFFORT") or "low").strip().lower()
EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")

# ── 역할별 크기 (2026-09-09) ───────────────────────────────
#   설계도 05 — "작은 모델 = 성능 저하" 가 아니다. 출력이 닫혀 있고 온도가
#   0에 가까운 작업(대조·발췌·형식변환)은 작은 쪽이 오히려 덜 흔들린다.
#   판단을 **만들어야** 하는 자리(도구 선택·해석·조언)에만 큰 것을 둔다.
#
#   ── 2026-09-09 실측 단가 (developers.openai.com/api/docs/models) ──
#     gpt-6-astra    $10 / $50   컨텍스트 —      가장 센 것. 우리 일엔 과하다
#     gpt-5.6-sol    $4  / $20   1.05M          복잡한 전문 작업
#     gpt-5.6-terra  $2  / $12   1.05M · 출력 128K   지능과 비용의 균형
#     gpt-5.6-luna   $0.20/$1.20 1.05M · 출력 128K   캐시 입력 $0.02
#
#   ★ Luna 가 기능을 안 깎는다.
#     function calling · structured outputs · web search · MCP · file search ·
#     code interpreter · skills · tool search 를 **전부** 지원한다.
#     Terra 와 다른 것은 값과 추론 깊이지 할 수 있는 일이 아니다.
#     그래서 "작은 모델을 쓰면 기능이 줄어든다"는 걱정은 여기 해당 없다.
#
#   왜 이렇게 갈랐나 — 대조·발췌·형식변환은 출력이 닫혀 있고 effort 가 none 이라
#   Terra 로 올려도 얻는 게 거의 없다. 반대로 도구를 고르고 다시 고르는 판단은
#   한 번 틀리면 아래가 전부 틀리므로 Terra 를 쓴다. 10배 차이는 거기에만 낸다.
MODEL_LARGE = os.getenv("FEEDIT_LLM_MODEL_LARGE") or "gpt-5.6-sol"
MODEL_MID = os.getenv("FEEDIT_LLM_MODEL_MID") or "gpt-5.6-terra"
MODEL_SMALL = os.getenv("FEEDIT_LLM_MODEL_SMALL") or "gpt-5.6-luna"

ROLES: dict[str, tuple[str, str]] = {
    # 역할              (모델,        추론 강도)
    "orchestrator":   (MODEL_MID,   "medium"),   # 도구를 고르고 다시 고른다
    "interpreter":    (MODEL_MID,   "medium"),   # 숫자 → 판단 (창작에 가깝다)
    "advisor":        (MODEL_MID,   "medium"),   # 살!말? 결론
    "general":        (MODEL_MID,   "low"),      # 사전 밖 상담 (웹검색 동반)
    "quote":          (MODEL_SMALL, "none"),     # 원문 발췌 — 새로 쓰지 않는다
    "verify":         (MODEL_SMALL, "none"),     # 숫자 대조 — 일치 확인
    "polish":         (MODEL_SMALL, "none"),     # 형식 변환
    "ask":            (MODEL_SMALL, "none"),     # 되묻는 한 문장
    # ★ 2026-09-18 — 역할 없이 기본 모델(FEEDIT_LLM_MODEL)로 떨어지던 자리들을 설계대로 묶었다.
    #   닫힌 출력(분류·추출·형식)은 Luna, 열린 답(사전 밖 지식 설명)은 Terra.
    "classify":       (MODEL_SMALL, "low"),      # 의도 분류 (nlu.py) — 목록 중 하나 고르기
    "context":        (MODEL_SMALL, "low"),      # 앞 턴 이어받기 (context.py) — 후보 중 고르기
    "extract":        (MODEL_SMALL, "low"),      # 상품 링크 · 매거진 기사 찾기 (웹검색 + 값 뽑기)
    # ★ 2026-09-10 — 마무리(_finish)는 **판단이 아니라 정리**다.
    #   무엇을 볼지는 루프에서 이미 정했고, 값도 이미 손에 있다. 남은 일은
    #   그것을 문장으로 옮기는 것뿐인데 orchestrator 역할(medium)로 부르니
    #   생각하는 데 시간을 쓰다 끝났다. 실측(무신사 링크, 예산 20초):
    #   루프가 14초를 쓰고 마무리에 4초가 갔는데 그 4초 안에 못 끝냈다.
    #   effort 를 낮추면 같은 4초 안에 쓴다. 여기서 판단이 나빠질 일은 없다.
    "finish":         (MODEL_SMALL, "low"),      # 모은 결과를 문장으로만 옮긴다
    # ★ 2026-09-10 — 이미지 첨부. 사진 속 옷을 보고 설명·판단하는 자리라
    #   판단이 필요하지만(advisor 급), 도구 루프처럼 여러 바퀴를 돌지는 않는
    #   한 번짜리 호출이라 medium 대신 low로 둔다.
    "vision":         (MODEL_MID,   "low"),      # 사진을 보고 답한다
}


# ── Sol: 막혔을 때만 (2026-09-18) ─────────────────────────────
#   평소 답은 Terra·Luna 가 낸다. Terra/Luna 호출이 **실패했거나(모델 오류·응답 없음)
#   결과가 깨졌을 때** 남은 예산이 있으면 Sol 로 한 번만 더 부른다.
#   · 같은 역할의 추론 강도를 그대로 쓰고 모델만 올린다 — 할 일은 같다
#   · 키가 없거나(NO_KEY) 일부러 끈 것(DISABLED) · 인증 실패(401/403)는 올려도 소용없다
#   · 한 답변 안에서 자리마다 한 번뿐이다 (부르는 쪽이 센다)
#   FEEDIT_LLM_ESCALATE=0 이면 끈다. 비용은 실패한 호출에만 붙는다.
ESCALATE = os.getenv("FEEDIT_LLM_ESCALATE", "1").strip() not in ("0", "false", "no", "")
_NO_ESCALATE = ("DISABLED", "NO_KEY", "NO_REQUESTS")


def can_escalate(*, bad_output: bool = False) -> bool:
    """Sol 로 다시 불러 볼 만한가.

    bad_output=True 는 모델은 답했지만 결과를 못 쓰는 경우(빈 답·깨진 수정)다.
    그때는 LAST_ERROR 가 비어 있어도 올린다.
    """
    if not ESCALATE or not MODEL_LARGE or DISABLED:
        return False
    err = LAST_ERROR or ""
    if err in _NO_ESCALATE or err.startswith(("HTTP_401", "HTTP_403")):
        return False
    return bad_output or bool(err)


def escalate(name: str) -> dict:
    """역할은 그대로, 모델만 Sol 로.  llm.respond(..., **llm.escalate("orchestrator"))"""
    _, effort = ROLES.get(name, (MODEL, DEFAULT_EFFORT))
    return {"model": MODEL_LARGE, "effort": effort}


def role(name: str) -> dict:
    """역할 이름 → respond() 에 그대로 펼쳐 넣을 인자.

        llm.respond(instr, payload, schema, **llm.role("verify"))

    모르는 이름이면 지금까지의 기본값으로 떨어진다 — 오타 하나로
    챗봇이 통째로 멈추지 않게 한다.
    """
    model, effort = ROLES.get(name, (MODEL, DEFAULT_EFFORT))
    return {"model": model, "effort": effort}
PROMPT_VERSION = "feedit-chat-v1"

# 챗봇 전체를 규칙만으로 돌리고 싶을 때 (FEEDIT_LLM_DISABLED=1)
DISABLED = (os.getenv("FEEDIT_LLM_DISABLED") or "").strip().lower() in ("1", "true", "yes")

# 마지막 실패 이유. 진단용이고 키는 절대 안 들어간다.
LAST_ERROR: str | None = None

_key_cache: str | None = None
_key_lock = threading.Lock()


def _read_key() -> str:
    global _key_cache
    if _key_cache is not None:
        return _key_cache
    with _key_lock:
        if _key_cache is not None:
            return _key_cache
        # ① 환경변수 (셸 · 도커 env_file · 저장소 .env — app/__init__.py 가 읽어 둔다)
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            # ② 크롤러 관리자 화면이 저장하는 곳. 크롤러를 같이 쓰는 사람만 해당된다.
            path = CRAWLER / "data" / "keys.json"
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                key = str((d.get("OPENAI_API_KEY") or {}).get("value") or "").strip()
            except (OSError, ValueError, AttributeError):
                key = ""
        _key_cache = key
    return _key_cache


def source_hint() -> str:
    """키를 어디서 읽었나. 값은 안 보여 준다 — 팀원이 설정을 못 찾을 때 이것만 보면 된다."""
    if not _read_key():
        return "없음"
    if (os.getenv("OPENAI_API_KEY") or "").strip():
        from .env import where
        return f"환경변수 OPENAI_API_KEY (.env: {where()})"
    return f"{CRAWLER / 'data' / 'keys.json'}"


def available() -> bool:
    return (not DISABLED) and bool(_read_key())


def key_hint() -> str:
    """키가 있나 없나만. 값은 안 보여 준다."""
    k = _read_key()
    return f"있음 ({len(k)}자)" if k else "없음"


def respond(instructions: str, payload: Any, schema: dict | None = None,
            *, effort: str | None = None, timeout: int = 20,
            tools: list | None = None, max_output_tokens: int | None = None,
            model: str | None = None, raw_flag: bool = False) -> dict | None:
    """Responses API 를 한 번 부른다. 실패하면 None.

    schema 를 주면 JSON 을 강제하고 파싱해서 돌려준다.
    schema 가 없으면 {"text": 출력문자열} 을 돌려준다.
    """
    global LAST_ERROR
    if DISABLED:
        LAST_ERROR = "DISABLED"           # 일부러 끈 것이다. 오류가 아니다.
        return None
    key = _read_key()
    if not key:
        LAST_ERROR = "NO_KEY"
        return None
    try:
        import requests
    except ImportError:
        LAST_ERROR = "NO_REQUESTS"
        return None

    body: dict[str, Any] = {
        "model": model or MODEL,
        "store": False,                       # 대화를 OpenAI 쪽에 남기지 않는다
        # 목록 밖의 값을 보내면 400 이 난다. 오타 하나로 챗봇이 통째로 규칙으로
        # 떨어지는 걸 막으려고 여기서 한 번 거른다.
        "reasoning": {"effort": (effort or DEFAULT_EFFORT) if (effort or DEFAULT_EFFORT) in EFFORTS else "low"},
        "instructions": instructions,
        # ★ 리스트는 그대로 보낸다.
        #   도구 루프는 이전 턴의 function_call 과 그 결과를 **항목 목록**으로
        #   되돌려줘야 모델이 무엇을 이미 불렀는지 안다. json.dumps 로 감싸면
        #   그게 그냥 문자열이 되어, 같은 도구를 무한히 다시 부른다.
        "input": payload if isinstance(payload, (str, list))
                 else json.dumps(payload, ensure_ascii=False),
    }
    if schema:
        body["text"] = {"format": schema}
    if tools:
        body["tools"] = tools
    if max_output_tokens:
        body["max_output_tokens"] = max_output_tokens

    try:
        r = requests.post(f"{API}/responses", timeout=timeout,
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          json=body)
    except Exception as e:                     # noqa: BLE001
        LAST_ERROR = f"NET_{type(e).__name__}"  # 문구에 키가 섞일 수 있어 종류만
        return None

    if r.status_code >= 400:
        # ★ 키는 절대 안 넣는다. OpenAI 의 오류 코드만 덧붙인다 —
        #   401(키 틀림) · 404(모델명 틀림) · 429(한도)를 구분 못 하면
        #   팀원은 "그냥 안 돼요" 밖에 말할 수 없다.
        code = ""
        try:
            code = str(((r.json() or {}).get("error") or {}).get("code") or "")[:40]
        except ValueError:
            code = ""
        LAST_ERROR = f"HTTP_{r.status_code}" + (f"_{code}" if code else "")
        return None

    try:
        raw = r.json()
    except ValueError:
        LAST_ERROR = "BAD_JSON_ENVELOPE"
        return None

    # ★ 도구 루프는 output_text 가 **비어 있는 것이 정상**이다.
    #   모델이 글 대신 function_call 을 냈기 때문이다. 그걸 EMPTY_OUTPUT 으로
    #   처리하면 루프가 첫 바퀴에서 죽는다. raw=True 면 봉투를 그대로 준다.
    if raw_flag:
        LAST_ERROR = None
        return {"_raw": raw, "text": raw.get("output_text") or _output_text(raw),
                "_raw_sources": _sources(raw)}

    out = raw.get("output_text") or _output_text(raw)
    if not out:
        LAST_ERROR = "EMPTY_OUTPUT"
        return None

    if not schema:
        LAST_ERROR = None
        return {"text": out, "_raw_sources": _sources(raw)}

    try:
        parsed = json.loads(out)
    except (TypeError, ValueError):
        LAST_ERROR = "BAD_JSON_OUTPUT"
        return None
    parsed["_raw_sources"] = _sources(raw)
    LAST_ERROR = None
    return parsed


def _output_text(raw: dict) -> str:
    """output_text 가 없을 때 조각을 이어 붙인다 (llm_analysis.py 와 같은 처리)."""
    parts = []
    for item in raw.get("output") or []:
        for c in item.get("content") or []:
            if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                parts.append(c.get("text") or "")
    return "".join(parts).strip()


_TRACK = ("utm_", "fbclid", "gclid", "igshid", "ref_")


def _clean_url(u: str) -> tuple[str, str]:
    """(보여 줄 주소, 중복 판정용 열쇠).

    ★ 2026-09-09 실측 — 같은 보그 기사가 출처에 두 번 떴다.
      하나는 퍼센트 인코딩이 중간에 끊겨 있었고(%EA%B3%A0프코어에-…),
      다른 하나는 ?utm_source=openai 가 붙어 제목이 도메인 그대로였다.
      사용자에게는 같은 글이 두 줄로 보인다. 신뢰가 깎이는 자리다.
    """
    from urllib.parse import (parse_qsl, unquote, urlencode, urlsplit,
                              urlunsplit)
    try:
        s = urlsplit(u)
        q = [(k, v) for k, v in parse_qsl(s.query)
             if not any(k.lower().startswith(p) for p in _TRACK)]
        shown = urlunsplit((s.scheme, s.netloc, s.path, urlencode(q), s.fragment))
        # 열쇠는 인코딩 차이를 없앤 뒤 비교한다
        key = urlunsplit(("", s.netloc.lower(), unquote(s.path).rstrip("/"),
                          urlencode(sorted(q)), ""))
        return shown, key
    except Exception:                                    # noqa: BLE001
        return u, u


def _sources(raw: dict) -> list[dict]:
    """web_search 도구가 쓴 출처를 긁어낸다. 출처 없는 문장은 화면에 못 올린다."""
    out: list[dict] = []
    seen: dict[str, int] = {}
    for item in raw.get("output") or []:
        for c in item.get("content") or []:
            for a in (c.get("annotations") or []) if isinstance(c, dict) else []:
                url = a.get("url")
                if not url:
                    continue
                shown, key = _clean_url(url)
                title = (a.get("title") or "").strip()
                if key in seen:
                    # 같은 글이다. 제목이 도메인뿐인 쪽을 제대로 된 제목으로 올린다.
                    i = seen[key]
                    cur = out[i]["title"]
                    if title and (cur == out[i]["url"] or cur.count(".") >= 1
                                  and " " not in cur):
                        out[i]["title"] = title
                    continue
                seen[key] = len(out)
                out.append({"url": shown, "title": title or shown})
    return out


def tool_calls(result: dict | None) -> list[dict]:
    """raw_flag=True 로 받은 응답에서 모델이 부르려는 도구를 꺼낸다.

    Responses API 는 도구 호출을 output 배열 안에 `function_call` 항목으로 준다:
        {"type":"function_call", "call_id":"...", "name":"get_metric",
         "arguments":"{\"term\":\"발레코어\"}"}

    arguments 는 **문자열**이다. 여기서 한 번만 파싱해 둔다 —
    부르는 쪽마다 json.loads 를 하면 깨진 JSON 처리가 곳곳에 흩어진다.
    """
    if not result:
        return []
    out = []
    for item in ((result.get("_raw") or {}).get("output") or []):
        if item.get("type") != "function_call":
            continue
        try:
            args = json.loads(item.get("arguments") or "{}")
        except (TypeError, ValueError):
            args = {}                       # 인자가 깨져도 루프는 계속 돈다
        if not isinstance(args, dict):
            args = {}
        out.append({"call_id": item.get("call_id") or item.get("id") or "",
                    "name": item.get("name") or "", "args": args})
    return out


def tool_result_item(call_id: str, payload: Any) -> dict:
    """도구 결과를 모델에게 되돌려줄 항목. 다음 바퀴의 input 에 넣는다."""
    return {"type": "function_call_output", "call_id": call_id,
            "output": json.dumps(payload, ensure_ascii=False, default=str)}


# ── 이미지 첨부 (2026-09-10) ────────────────────────────────
#   사진 한두 장을 보고 짧게 답한다. 지표 게이트·도구 루프를 거치지 않는다 —
#   사진 속 옷이 어떤 스타일인지는 우리 DB에 없는 값이라, 애초에 도구가
#   값을 내줄 수 있는 질문이 아니다(engine.py._vision_ask 주석 참고).
_VISION_GENERAL = (
    "당신은 FEEDiT 패션 트렌드 챗봇입니다. 사용자가 올린 사진을 보고 한국어로 "
    "답하세요. 사진에 보이는 의류·아이템·색상·소재·실루엣을 구체적으로 짚고, "
    "어울리는 스타일(코어)이 있으면 함께 언급하세요. 확실하지 않은 것은 "
    "확실하지 않다고 말하고, 사진에 없는 브랜드명·가격·수치를 지어내지 "
    "마세요. 2~4문장으로 간결하게 답하세요."
)
_VISION_SALMAL = (
    "당신은 FEEDiT 살!말? 챗봇입니다. 사용자가 구매를 고민 중인 옷·아이템 "
    "사진을 보고 한국어로 답하세요. 사진에서 보이는 것만 근거로 설명하고, "
    "가격·재고·트렌드 수명주기처럼 사진만으로 알 수 없는 값은 모른다고 "
    "분명히 밝히세요(지어내지 마세요). 사도 되는지 묻는 말투에는 판단을 "
    "돕되, 최종 결정은 사용자 몫이라는 것을 은근히 남기세요. 2~4문장으로 "
    "간결하게 답하세요."
)


def vision(question: str, images: list[str], *, mode: str = "general") -> dict | None:
    """사진 설명과 다음 턴에 이어 쓸 관찰값을 한 번에 구조화한다.

    예전에는 답변 문자열만 받아 아이템·소재가 다음 턴의 history에서 사라졌다.
    숫자나 브랜드 추측은 받지 않고, 사진에서 직접 볼 수 있는 항목만 저장한다.
    """
    r = role("vision")
    instr = _VISION_SALMAL if mode == "salmal" else _VISION_GENERAL
    content: list[dict] = [{"type": "input_text", "text": question or "이 사진을 봐 주세요."}]
    for u in images[:6]:
        content.append({"type": "input_image", "image_url": u})
    payload = [{"role": "user", "content": content}]
    schema = strict_schema("general_visual", {
        "item": {"type": "string"},
        "colors": {"type": "array", "items": {"type": "string"}},
        "materials": {"type": "array", "items": {"type": "string"}},
        "silhouette": {"type": "array", "items": {"type": "string"}},
        "details": {"type": "array", "items": {"type": "string"}},
        "styles": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    }, ["item", "colors", "materials", "silhouette", "details", "styles",
        "uncertainties", "summary"])
    return respond(instr + " 사진에서 직접 확인한 내용을 스키마에 나눠 담고, "
                   "summary는 사용자에게 보여 줄 2~4문장 답변으로 작성하세요.",
                   payload, schema, effort=r["effort"], model=r["model"], timeout=30)


def vision_salmal(question: str, images: list[str]) -> dict | None:
    """살말 판단과 후속 질문에 함께 쓸 시각 관찰값을 구조화한다.

    지수는 이 모델 출력 숫자가 아니라 salmal_index의 고정 계산식이 만든다.
    색·소재·실루엣도 함께 받아야 다음 턴의 "소재는?" 같은 질문에서 사진을
    다시 올리라고 하지 않는다.
    """
    content: list[dict] = [{"type": "input_text", "text": question or "이 아이템 살까 말까?"}]
    for u in images[:6]:
        content.append({"type": "input_image", "image_url": u})
    schema = strict_schema("salmal_visual", {
        "item": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "colors": {"type": "array", "items": {"type": "string"}},
        "materials": {"type": "array", "items": {"type": "string"}},
        "silhouette": {"type": "array", "items": {"type": "string"}},
        "details": {"type": "array", "items": {"type": "string"}},
        "styles": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    }, ["item", "tags", "colors", "materials", "silhouette", "details",
        "styles", "uncertainties", "summary"])
    instructions = (
        "FEEDiT 살말 분석용 시각 판독기입니다. 사진에서 직접 확인되는 의류 종류, "
        "색, 소재로 보이는 표면 특성, 실루엣·길이, 디테일과 스타일 태그를 각각 "
        "반환하세요. 사진만으로 정확한 혼용률이나 소재를 확정할 수 없으면 materials에 "
        "'광택 있는 직물로 보임'처럼 관찰 수준으로 쓰고 uncertainties에 한계를 적으세요. "
        "브랜드, 가격, 재고, 트렌드 수치나 점수는 추측하지 마세요. tags는 한국어 명사 "
        "1~6개, summary는 보이는 특징과 구매 전 확인할 점을 2~3문장으로 작성하세요."
    )
    return respond(instructions, [{"role": "user", "content": content}], schema,
                   timeout=30, **role("vision"))


def strict_schema(name: str, properties: dict, required: list[str]) -> dict:
    """Structured Outputs 스키마 껍데기.

    strict 모드는 additionalProperties:false 와 required 전부 나열을 요구한다.
    (llm_analysis.py 가 겪은 것과 같은 제약 — uniqueItems 도 못 쓴다)
    """
    return {"type": "json_schema", "name": name, "strict": True,
            "schema": {"type": "object", "additionalProperties": False,
                       "properties": properties, "required": required}}
