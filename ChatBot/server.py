"""feedit-chat 개발 서버 — 표준 라이브러리만 쓴다.

왜 FastAPI 를 안 쓰나
  이 기기의 python3 에 fastapi 가 없다. 크롤러 venv 에는 있지만,
  그걸 쓰게 하면 "venv 를 켜야 챗봇이 돈다" 는 조건이 하나 더 붙는다.
  전송 계층은 나중에 Django/FastAPI 로 갈아 끼울 것이라 지금 얇게 둔다.
  ChatEngine 은 HTTP 를 모른다 — 갈아 끼울 때 손댈 곳은 이 파일뿐이다.

  ⚠ 로그인은 아직 없다. 밖에 열 때의 방어는 두 가지다 —
     ① IP 당 분당 횟수 제한 (항상 켜짐, 설정 필요 없음)
     ② 공유 토큰 FEEDIT_CHAT_TOKEN (설정했을 때만 검사 — 공개 베타 중에도 검사한다)
     둘 다 로그인의 대체물이 아니다. 스캐너가 우리 OpenAI 키를 태우는 것을
     막는 최소한이다. 사용자별 한도·과금은 여전히 없다.

엔드포인트
  GET  /v1/health                    떠 있나 · 기준일 · 적재 term 수
  GET  /v1/llm                       LLM 배선 진단 (모델 · 키 유무 · 마지막 오류)
  GET  /v1/magazines?term=발레코어    추천 웹매거진 기사 (웹 검색)
  GET  /v1/me?plan=FREE              플랜과 하루 한도 (아직 계정이 없어 질의로 받는다)
  POST /v1/chat                      SSE 스트림
       {question, mode, plan, conversation_id, history?, images?, plan_ticket?}
       plan 은 베타 동안 무시된다(전부 BUSINESS). 베타가 끝나면(FEEDIT_PUBLIC_BETA=0)
       plan 도 무시하고 Django 가 서명한 plan_ticket 만 믿는다 — 없거나 틀리면 FREE (2026-10-03).
       history 는 [{q, intent, terms:[{canonical,facet,term_key}]}] — 최근 8턴까지.
       보내면 그쪽을 쓰고, 안 보내면 서버가 conversation_id 로 기억한 것을 쓴다.
       images 는 data URL 문자열 배열(최대 MAX_IMAGES장, data:image/... 로 시작)이다.
       사진이 오면 지표 게이트·도구 루프를 타지 않고 곧장 비전 모델로 간다
       (ChatEngine._vision_ask, 2026-09-10 — 아래 이미지 첨부 절 참고).
  POST /v1/chat/cancel               실행 중인 답변 중단
       {request_id}
  POST /v1/lexicon/requests          어휘 등록 요청
       {surface, facet_guess, question}

SSE 순서는 프론트가 이미 그리는 순서에 맞춘다 (chat_popup.js:105~121).
  status → text(여러 번) → report → actions → done
  글자를 먼저 흘리고 카드를 나중에 보내야 .ansCard.reveal.in 이 뒤따라 떠오른다.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from app import llm, plans
from app.adapters import SalmalHTTPAdapter
from app.engine import ChatEngine
from app import vton

# ── 어디에 여나 ────────────────────────────────────────────
#   기본은 127.0.0.1 이다. 그대로 둔다 — 인증이 없기 때문이다.
#   프록시가 필요한 운영 환경의 바인딩 주소는 서버 설정에서 따로 관리한다.
HOST = os.getenv("FEEDIT_CHAT_HOST", "127.0.0.1")
PORT = int(os.getenv("FEEDIT_CHAT_PORT", "8770"))

# vite dev 서버만 허용한다. 와일드카드를 쓰지 않는다.
#   팀원이 다른 포트를 쓰면 FEEDIT_CHAT_ORIGINS 에 쉼표로 이어 붙인다.
_DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173",
                    "http://localhost:4173", "http://127.0.0.1:4173")
ALLOW_ORIGINS = {o.strip() for o in
                 (os.getenv("FEEDIT_CHAT_ORIGINS") or ",".join(_DEFAULT_ORIGINS)).split(",")
                 if o.strip()}
# ★ 이미지 첨부(2026-09-10) 전에는 64KB였다. 사진은 base64로 실려 오면
#   원본보다 33% 정도 불어나므로, 프론트가 축소·압축해 보내는 걸 전제로 하고도
#   여유를 넉넉히 둔다. MAX_IMAGES · MAX_IMAGE_DATAURL 이 실제 상한을 잡는다.
MAX_BODY = 32 * 1024 * 1024
MAX_IMAGES = 6
MAX_IMAGE_DATAURL = 6 * 1024 * 1024   # data URL 문자열 길이 기준 — 대략 디코딩 4.5MB

# ── 밖에 열 때의 최소 방어 ──────────────────────────────────
#   ★ 이건 로그인이 아니다. "주소를 아무도 모른다" 는 방어가 아니라서 둔다 —
#     공개된 주소는 봇이 몇 시간 안에 찾아낸다. 그때 막아 주는 건 이 둘뿐이다.
#
#   ★ 2026-09-23 보안 — 공개 베타(FEEDIT_PUBLIC_BETA)는 **플랜만** 연다.
#     예전에는 베타 동안 토큰까지 무시해서, 챗봇 주소만 알면 누구나
#     /v1/chat · /v1/virtual-fitting 을 불러 OpenAI 비용을 쓸 수 있었다.
#     토큰은 버셀 함수만 붙이므로 사용자 경험은 그대로다.
#     "팀원별 로컬 설정 때문에 누구는 목업으로 떨어지던" 문제는 vite 개발
#     프록시가 루트 .env 의 FEEDIT_CHAT_TOKEN 을 붙여 보내는 것으로 해결했다.
#   FEEDIT_CHAT_TOKEN  비워 두면 검사하지 않는다(로컬 개발 그대로).
#                      넣으면 X-FEEDiT-Token 머리글이 같아야 통과한다.
#                      버셀 함수가 붙여 주므로 브라우저는 토큰을 모른다.
def _chat_token() -> str:
    return (os.getenv("FEEDIT_CHAT_TOKEN") or "").strip()


def _token_ok(got: str | None) -> bool:
    """상수 시간 비교. 글자 수가 다를 때 빨리 끝나면 길이가 새어 나간다."""
    return hmac.compare_digest((got or "").encode("utf-8", "replace"),
                               CHAT_TOKEN.encode("utf-8"))


CHAT_TOKEN = _chat_token()

#   IP 당 분당 질문 수. 사람은 분당 몇 번 못 묻는다.
RATE_PER_MIN = int(os.getenv("FEEDIT_CHAT_RATE_PER_MIN", "20"))
_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()
_chat_cancels: dict[str, threading.Event] = {}
_chat_cancels_lock = threading.Lock()


def _request_id(value) -> str:
    value = str(value or "").strip()
    return value[:80] if re.fullmatch(r"[A-Za-z0-9._:-]{8,80}", value) else ""


def rate_ok(ip: str) -> bool:
    """최근 60초 안에 RATE_PER_MIN 을 넘었나. 넘으면 False."""
    now = time.time()
    with _hits_lock:
        q = [t for t in _hits.get(ip, ()) if now - t < 60]
        if len(q) >= RATE_PER_MIN:
            _hits[ip] = q
            return False
        q.append(now)
        _hits[ip] = q
        if len(_hits) > 5000:                 # 메모리가 무한정 늘지 않게
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > 300]:
                _hits.pop(k, None)
    return True


# ── 하루 사용 한도 (FREE 만) ─────────────────────────────────
#   기획대로 FREE 는 하루 plans.QUOTA[FREE]["turns"]회 — 숫자를 여기 새로 적지 않고
#   plans.py 값을 그대로 쓴다. 한 곳에서만 정해야 화면 문구와 여기가 어긋나지 않는다.
#   PRO·BUSINESS 는 막지 않는다 (plans.py 주석 — "300 은 사실상 무제한").
#
#   ★ 아직 로그인이 없어(이 파일 머리말) IP 로 센다. plan 값도 요청이 스스로 말한 값이라
#     클라이언트가 "PRO" 라고 우기면 지금은 못 막는다 — 로그인이 붙기 전까지의 한계다.
_daily: dict[str, tuple[str, int]] = {}
_daily_lock = threading.Lock()


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def daily_ok(ip: str, plan: str) -> bool:
    """오늘 이 IP 가 FREE 하루 한도를 넘었나. FREE 가 아니면 항상 True."""
    if plan != plans.FREE:
        return True
    limit = plans.QUOTA[plans.FREE]["turns"]
    today = _today()
    with _daily_lock:
        day, count = _daily.get(ip, (today, 0))
        if day != today:
            day, count = today, 0
        if count >= limit:
            _daily[ip] = (day, count)
            return False
        _daily[ip] = (day, count + 1)
        if len(_daily) > 5000:                # 메모리가 무한정 늘지 않게
            for k, (d, _c) in list(_daily.items()):
                if d != today:
                    _daily.pop(k, None)
    return True

# 어휘 등록 요청을 어디에 쌓나.
#   배포되면 RDS 의 dictionary.term_candidate 로 간다 (설계서 3.5).
#   지금은 RDS 에 붙을 수 없어 파일에 줄 단위로 쌓는다.
#   ★ 버튼만 만들어 두고 아무 데도 안 보내면 "누르면 되는 척" 이 된다. 실제로 남긴다.
REQ_LOG = Path(__file__).resolve().parent / "data" / "lexicon_requests.jsonl"
# 답변 피드백 — 사용자가 "이 답 아쉬웠다" 고 알려 준 것만 쌓인다.
# 무엇이 자주 틀리는지는 이 파일이 유일한 근거다(2026-09-13).
FEEDBACK_LOG = Path(__file__).resolve().parent / "data" / "answer_feedback.jsonl"
KST = timezone(timedelta(hours=9))
_req_lock = threading.Lock()

_engine: ChatEngine | None = None
_engine_lock = threading.Lock()


def engine() -> ChatEngine:
    """엔진은 하나만 만든다. 사전 로딩이 무거워 매 요청 만들면 안 된다."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = ChatEngine(use_llm=not llm.DISABLED, salmal=SalmalHTTPAdapter())
    return _engine


def _json_default(value):
    """json 이 모르는 값(Decimal · 날짜)은 숫자나 문자열로 — 모양 때문에 답이 죽지 않게."""
    from decimal import Decimal
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return str(value)


def sse(event: str, data) -> bytes:
    return (f"event: {event}\n"
            f"data: {json.dumps(data, ensure_ascii=False, default=_json_default)}\n\n").encode("utf-8")


def _log_turn(question: str, rep: dict) -> None:
    """답 하나가 어떻게 끝났는지 한 줄. (2026-09-10)

    ★ 왜 필요한가 — 화면에 안내문이 뜨면 원인이 **시간(NET_ReadTimeout)** 인지
      **한도(HTTP_429)** 인지 구분할 방법이 없었다. 둘 다 같은 문구로 나온다.
      trace 는 report 이벤트에 실려 나가지만 그걸 보려면 개발자도구를 열어야 하고,
      서버 콘솔에는 아무것도 남지 않았다. 추측하지 않으려고 한 줄 남긴다.
    ★ 질문은 앞 40자만. 로그는 원본이 아니다.
    """
    tr = rep.get("trace") or {}
    if not tr:
        return
    mark = "!" if (tr.get("stopped") not in ("done", None) or tr.get("over_budget")) else " "
    try:
        rounds = "+".join(str(x) for x in (tr.get("round_ms") or [])) or "-"
        hosted = tr.get("hosted") or 0
        blocks = tr.get("blocks")
        block_note = f"블록={blocks}" if blocks is not None else ""
        if tr.get("block_error"):
            block_note += f"(조립실패 {tr['block_error']})"
        budget = tr.get("budget_ms")
        print(f"{mark} [{time.strftime('%H:%M:%S')}] {tr.get('ms')}ms"
              f"{f'/{budget}ms' if budget else ''} "
              f"stopped={tr.get('stopped')} 바퀴={tr.get('rounds')}({rounds}ms) "
              f"웹검색={hosted} 호출={tr.get('calls')} {block_note} "
              f"도구={','.join(tr.get('tools') or []) or '-'} "
              f"| {question[:40]}", flush=True)
    except Exception:                              # noqa: BLE001
        pass                                       # 로그가 대화를 막지 않는다


def split_deltas(html: str) -> list[str]:
    """한 줄 결론을 조각으로 나눈다.

    태그(<b>…</b>)는 통째로 한 조각으로 보낸다.
    프론트가 어느 순간에 잘라도 항상 닫힌 HTML 만 그리게 하기 위해서다
    (chat_popup.js 의 cpTypeHTML 이 쓰는 규칙과 같다).
    """
    out, buf = [], ""
    for tok in re.split(r"(<[^>]+>)", html):
        if not tok:
            continue
        if tok.startswith("<"):
            if buf:
                out.append(buf)
                buf = ""
            out.append(tok)
            continue
        for ch in tok:
            buf += ch
            if len(buf) >= 3:
                out.append(buf)
                buf = ""
    if buf:
        out.append(buf)
    return out


def clean_taste_context(raw: dict) -> dict:
    """브라우저가 보낸 취향 컨텍스트를 길이·모양만 잘라서 통과시킨다.

    값을 새로 만들지 않는다 — 자르기만 한다. favorite_style_profiles 는
    가입할 때 고른 스타일과 그 대표 어휘라서 중첩이 한 겹 있다.
    """
    out: dict = {}
    for key in ("favorite_styles", "searched_terms", "saved_terms"):
        value = raw.get(key)
        if isinstance(value, list):
            out[key] = [str(x)[:80] for x in value[:30] if str(x).strip()]
    profiles = raw.get("favorite_style_profiles")
    if isinstance(profiles, list):
        cleaned = []
        for item in profiles[:10]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()[:40]
            if not name:
                continue
            words = item.get("keywords")
            words = [str(w)[:40] for w in words[:8] if str(w).strip()] \
                if isinstance(words, list) else []
            cleaned.append({"name": name, "keywords": words})
        if cleaned:
            out["favorite_style_profiles"] = cleaned
    return out


_TREND_ACTION_INTENTS = {"metric.level", "metric.direction", "metric.platform",
                         "metric.assoc", "metric.sentiment", "metric.lifecycle"}
_STYLE_DETAIL_ASK = re.compile(r"뜻|유래|기원|정의|어떤\s*스타일|무슨\s*스타일|설명해", re.I)
_TREND_DETAIL_ASK = re.compile(
    r"지표|온도|트렌드|유행|인기|요즘|핫|유효|추이|상승|하락|꺾", re.I)
_COMMUNITY_ASK = re.compile(r"투표|사람들|다들|의견|후기|커뮤니티|물어", re.I)
_PURCHASE_ASK = re.compile(r"살까|사도|말까|살지|구매|지를까|추천|고민|어때", re.I)


def actions_for(rep: dict, mode: str = "general") -> list[dict]:
    """답에서 바로 이어 할 가치가 있는 행동만 보낸다.

    버튼은 기능 목록이 아니다. 매 답변마다 같은 네 개를 붙이면 사용자는 본문보다
    버튼을 먼저 무시하게 된다. 현재 질문·의도·확인된 상품/사진이 실제로 다음 행동과
    이어질 때만 노출한다.
    """
    acts = []
    terms = rep.get("terms") or []
    first = terms[0] if terms else None
    question = str(rep.get("question") or "")
    intent = str(rep.get("intent") or "")

    if mode == "general" and len(terms) == 1:
        # 뜻·유래를 설명한 뒤에는 Style 페이지가 자연스러운 다음 단계다.
        if (first and first.get("facet") == "style"
                and (intent == "knowledge.origin" or _STYLE_DETAIL_ASK.search(question))):
            acts.append({"label": "Style 탭에서 자세히", "type": "view",
                         "view": "style", "style": first.get("canonical")})
        # 수치·방향·플랫폼을 물은 경우에만 상세 지표 페이지를 제안한다.
        if (first and first.get("available")
                and (intent in _TREND_ACTION_INTENTS
                     or _TREND_DETAIL_ASK.search(question))):
            acts.append({"label": "지표로 보기", "type": "view", "view": "trend",
                         "part": "temp", "keyword": first.get("canonical")})
    if rep.get("hint", {}).get("code") == "MODE_MISMATCH":
        acts.append(rep["hint"]["action"] | {"label": "살!말? 모드로"})
    if mode == "salmal":
        # 물어보기 카드는 **확인한 것만** 들고 간다. 확인하지 못한 칸은 비워 두고
        # 사용자가 직접 적는다 — 짐작으로 채우면 사용자가 확인한 값으로 읽는다.
        draft = rep.get("item_draft")
        keep = {}
        if isinstance(draft, dict):
            keep = {k: draft.get(k) for k in ("title", "brand", "price", "image", "source")
                    if draft.get(k) not in (None, "")}
        # 실제 상품을 확인했거나 사용자가 다른 사람의 의견을 요청했을 때만 커뮤니티로.
        if keep or intent == "buy.opinion" or _COMMUNITY_ASK.search(question):
            community = {"label": "물어보기", "type": "community"}
            if keep:
                community["draft"] = keep
            acts.append(community)

    # ── 입혀보기 (2026-09-18: 조건을 넓혔다) ─────────────────────
    #   예전에는 살말 모드에서 "입혀/착용" 을 말하거나 사진을 올려 구매를 물을 때만 떴다.
    #   그래서 링크로 옷을 보내 "살까 말까" 를 물어도 한 번도 안 나왔다.
    #   이제는 **입어 볼 대상이 분명할 때** 모드와 관계없이 제안한다.
    #     ① 입혀/착용/어울려 같은 말을 했거나 의도가 buy.tryon
    #     ② 이번 답이 사진 속 옷을 봤고, 구매·코디 얘기다
    #     ③ 살말 모드에서 링크로 실제 상품을 확인했다(상품명이 확인됨)
    has_visual = isinstance(rep.get("visual_context"), dict) and bool(rep["visual_context"])
    # ★ 질문에 정규식을 걸지 않는다 (2026-09-22). 같은 문장을 nlu.classify 가 이미
    #   분류하고 있어(buy.tryon), 답변 경로에 **두 번째 분류표**가 숨어 있던 자리다.
    #   남은 신호는 전부 일어난 사실이다: 의도 · 사진 첨부 · 링크로 확인된 상품 ·
    #   모델이 코디 도구를 불렀다.
    wants_tryon = intent == "buy.tryon"
    photo_item = has_visual and (intent == "vision.salmal" or mode == "salmal"
                                 or bool(_PURCHASE_ASK.search(question)))
    draft = rep.get("item_draft") if isinstance(rep.get("item_draft"), dict) else {}
    # ★ 출처 문구로 판단하지 않는다 — 지수 도구가 같은 상품을 "챗봇이 확인한 값" 으로 다시
    #   적으면서 '링크' 가 사라져 버튼이 한 번도 안 떴다(2026-09-18). 질문에 링크가 있고
    #   상품명이 확인됐으면 충분하다.
    linked_item = (mode == "salmal" and bool(draft.get("title"))
                   and bool(re.search(r"https?://|www\.", question, re.I)))
    # ── 코디 (2026-09-22) ───────────────────────────────────────
    #   ① 확정된 코디(build_fit)가 있으면 그것을 들고 간다 — 착장 칸이 채워져 열린다.
    #   ② 제안(propose_fit)만 있으면 **승인 카드**다. 여기서 살!말? 로 넘어간다.
    #      VTON 은 살!말? 의 고유 기능이라, 일반 모드의 답은 제안에서 멈춘다.
    built = rep.get("fit") if isinstance(rep.get("fit"), dict) else None
    proposal = rep.get("fit_proposal") if isinstance(rep.get("fit_proposal"), dict) else None
    if built and built.get("items"):
        # ★ 확정된 코디는 report 의 fit 하나가 원본이다 — 버튼에 한 벌 더 실으면
        #   두 곳이 어긋난다. 화면은 답변과 함께 착장 칸을 펼치고, 이 버튼은
        #   접고 펴는 자리로 쓴다(chat_popup 의 m.fit / m.fitSaved).
        acts.append({"label": "입혀보기", "type": "virtual_fit"})
    elif proposal and proposal.get("items"):
        acts.append({"label": "이 코디로 입혀보기", "type": "fit_confirm", "fit": proposal})
    elif wants_tryon or photo_item or linked_item:
        if mode == "salmal":
            acts.append({"label": "입혀보기", "type": "virtual_fit"})
        else:
            # ★ 일반 모드에서는 빈 위젯을 열지 않는다 (2026-09-22). VTON 은 살!말? 의
            #   고유 기능이라, 여기서 열면 경계가 흐려진다. 넘어가는 문만 준다 —
            #   코디를 짜 온 경우(위 fit_confirm)와 달리 아직 입힐 것이 없다.
            acts.append({"label": "살!말? 에서 입혀보기", "type": "switch_mode",
                         "to": "salmal"})
    return acts


class _Server(ThreadingHTTPServer):
    """요청마다 스레드 하나. 대기열(listen backlog)만 넉넉히 (2026-10-02).

    기본값 5 는 기수 30명이 한꺼번에 질문 · 입혀보기를 누르면 접속 자체가 밀려
    거절될 수 있다. 실제 처리는 스레드라 줄 길이만 늘리면 된다."""
    request_queue_size = 128
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "feedit-chat/dev"

    # 접속 로그를 조용히 — 개발 중 콘솔이 SSE 로 도배된다
    def log_message(self, fmt, *args):
        if "--verbose" in sys.argv:
            super().log_message(fmt, *args)

    # ── 공통 ──────────────────────────────────────────
    def _origin_ok(self) -> str | None:
        o = self.headers.get("Origin")
        return o if o in ALLOW_ORIGINS else None

    def _cors(self):
        o = self._origin_ok()
        if o:
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── GET ───────────────────────────────────────────
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/v1/health":
            try:
                e = engine()
                # ★ 어떤 코드가 돌고 있나 (2026-09-22). 화면만 보고 "배포가 된 건가"
                #   를 알 길이 없어, 컨테이너를 받아 놓고도 옛 동작을 한참 들여다봤다.
                #   도구 목록은 코드가 바뀌면 같이 바뀐다 — 한 번의 조회로 갈린다.
                #   계측이 없으면 처방도 없다(AGENTS.md §4).
                from app.tools import NAMES
                return self._json(200, {"ok": True, "as_of": e.store.latest_day(),
                                        "metric_version": e.store.version,
                                        "terms": len(e.gate.prefer),
                                        "tools": len(NAMES),
                                        "fit": sorted(n for n in NAMES
                                                      if n.endswith("_fit"))})
            except Exception as ex:                       # noqa: BLE001
                # 비밀값이 섞일 수 있어 메시지는 싣지 않는다 — 자세한 건 서버 로그
                return self._json(503, {"ok": False, "error": type(ex).__name__,
                                        "hint": "챗봇 서버 로그에서 원인을 확인하세요"})
        if u.path == "/v1/llm":
            # 배선 진단. **키 값은 절대 안 나간다** — 있나 없나와 길이뿐이다.
            from app import llm
            from app.env import where
            return self._json(200, {"ok": True, "model": llm.MODEL, "api": llm.API,
                                    "effort": llm.DEFAULT_EFFORT,
                                    "disabled": llm.DISABLED,
                                    "key": llm.key_hint(), "key_from": llm.source_hint(),
                                    "env_file": where(), "last_error": llm.LAST_ERROR})
        if u.path == "/v1/magazines":
            # 금주의 리포트 · 추천 웹매거진 — 관심 키워드를 다룬 기사 (app/magazine.py)
            from app import magazine
            term = ((parse_qs(u.query).get("term") or [""])[0]).strip()
            if not term:
                return self._json(400, {"ok": False, "error": "TERM_REQUIRED"})
            return self._json(200, {"ok": True, **magazine.find(term)})
        if u.path == "/v1/me":
            q = parse_qs(u.query)
            plan = plans.effective((q.get("plan") or ["FREE"])[0])
            return self._json(200, {"ok": True, "plan": plan,
                                    "quota": plans.QUOTA[plan],
                                    "public_beta": plans.PUBLIC_BETA,
                                    "note": ("공개 베타 기간에는 모든 챗봇 기능을 사용할 수 있습니다."
                                             if plans.PUBLIC_BETA else
                                             "인증이 아직 없습니다. 개발용으로 질의 문자열의 plan 을 그대로 씁니다.")})
        return self._json(404, {"ok": False, "error": "NOT_FOUND"})

    # ── POST ──────────────────────────────────────────
    def _read_json(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0 or n > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _client_ip(self) -> str:
        """앞단(Caddy)이 붙여 주는 X-Forwarded-For 의 **맨 앞**이 진짜 손님이다.
        뒤쪽은 중간 프록시라 그걸 쓰면 전원이 한 IP 로 묶여 다 같이 막힌다.

        ★ 버셀 중계를 거치면 (2026-10-02) 운영 nginx 가 X-Forwarded-For 를 '버셀 함수 IP' 로
          덮어써, 30명이 IP 몇 개를 같이 쓰며 분당 횟수 제한을 나눠 먹었다. 중계가 손님 IP 를
          X-FEEDiT-Client-IP 로 따로 보낸다. **공유 토큰이 맞는 요청에서만** 믿는다 —
          토큰 없이 밖에서 지어 보낸 값으로 제한을 피할 수 없게."""
        relayed = (self.headers.get("X-FEEDiT-Client-IP") or "").strip()
        if relayed and CHAT_TOKEN and _token_ok(self.headers.get("X-FEEDiT-Token")) \
                and re.fullmatch(r"[0-9A-Fa-f:.]{3,45}", relayed):
            return relayed
        fwd = self.headers.get("X-Forwarded-For") or ""
        return (fwd.split(",")[0].strip() or self.client_address[0])

    def _guard(self) -> bool:
        """토큰·횟수 검사. 막으면 응답까지 보내고 False 를 돌려준다."""
        if CHAT_TOKEN and not _token_ok(self.headers.get("X-FEEDiT-Token")):
            # 왜 막혔는지 자세히 알려 주지 않는다 — 맞히는 데 도움이 된다.
            self._json(401, {"ok": False, "reason": "UNAUTHORIZED",
                             "message": "허용되지 않은 요청입니다."})
            return False
        if not rate_ok(self._client_ip()):
            self._json(429, {"ok": False, "reason": "RATE_LIMITED",
                             "message": f"질문이 너무 잦습니다. 잠시 후 다시 시도해 주세요 "
                                        f"(분당 {RATE_PER_MIN}회)."})
            return False
        return True

    def _lexicon_request(self):
        req = self._read_json()
        if not req:
            return self._json(400, {"ok": False, "error": "BAD_BODY"})
        surface = " ".join(str(req.get("surface") or "").split())[:60]
        if not surface:
            return self._json(400, {"ok": False, "error": "EMPTY_SURFACE"})
        row = {
            "surface": surface,
            "facet_guess": (str(req.get("facet_guess") or "") or None),
            "question": " ".join(str(req.get("question") or "").split())[:300],
            "source": "chatbot",
            "at": datetime.now(KST).isoformat(timespec="seconds"),
        }
        with _req_lock:
            REQ_LOG.parent.mkdir(parents=True, exist_ok=True)
            with REQ_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            # 같은 말이 몇 번 요청됐나 — 사전 보강 우선순위가 된다
            count = sum(1 for ln in REQ_LOG.open(encoding="utf-8")
                        if json.loads(ln).get("surface") == surface)
        return self._json(200, {"ok": True, "surface": surface, "count": count,
                                "message": f"'{surface}' 등록 요청을 받았습니다. 검토 후 사전에 추가됩니다."})

    def _feedback(self):
        """답변 하나에 대한 도움됨/아쉬움. 화면에서 누른 그대로만 적는다.

        ★ 답변 본문을 통째로 저장하지 않는다. 무엇에 대한 피드백인지 알 정도만
          남긴다 — 질문 앞부분, 의도, 사유, 사용자가 정정해 준 대상.
        """
        req = self._read_json()
        if not req:
            return self._json(400, {"ok": False, "error": "BAD_BODY"})
        verdict = str(req.get("verdict") or "").strip()
        if verdict not in ("up", "down"):
            return self._json(400, {"ok": False, "error": "BAD_VERDICT"})
        row = {
            "verdict": verdict,
            "reason": " ".join(str(req.get("reason") or "").split())[:40] or None,
            "correction": " ".join(str(req.get("correction") or "").split())[:60] or None,
            "question": " ".join(str(req.get("question") or "").split())[:300],
            "intent": " ".join(str(req.get("intent") or "").split())[:40] or None,
            "mode": "salmal" if str(req.get("mode")) == "salmal" else "general",
            "at": datetime.now(KST).isoformat(timespec="seconds"),
        }
        with _req_lock:
            FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
            with FEEDBACK_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return self._json(200, {"ok": True,
                                "message": "의견 고맙습니다. 답변 품질을 고치는 데 씁니다."})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/v1/chat", "/v1/chat/cancel", "/v1/lexicon/requests",
                        "/v1/virtual-fitting", "/v1/fit-classify", "/v1/feedback"):
            return self._json(404, {"ok": False, "error": "NOT_FOUND"})
        # ★ 쓰는 길은 전부 여기를 지난다. 검사를 분기 뒤에 두면
        #   새 엔드포인트를 더할 때 조용히 빠뜨리게 된다.
        if not self._guard():
            return
        if path == "/v1/lexicon/requests":
            return self._lexicon_request()
        if path == "/v1/feedback":
            return self._feedback()
        if path == "/v1/chat/cancel":
            req = self._read_json()
            request_id = _request_id((req or {}).get("request_id"))
            if not request_id:
                return self._json(400, {"ok": False, "error": "BAD_REQUEST_ID"})
            with _chat_cancels_lock:
                event = _chat_cancels.get(request_id)
                if event:
                    event.set()
            return self._json(200, {"ok": True, "cancelled": bool(event)})
        if path == "/v1/fit-classify":
            # 사진이 상의인지 하의인지 아우터인지만 돌려준다. 화면은 이 값으로
            # 첨부 사진을 알맞은 칸에 넣는다 — 사용자가 지웠다 다시 넣지 않게.
            req = self._read_json()
            if not req:
                return self._json(400, {"ok": False, "error": "BAD_BODY"})
            images = req.get("images")
            if not isinstance(images, list) or not images:
                return self._json(400, {"ok": False, "error": "NO_IMAGES"})
            try:
                cats = vton.classify([str(u or "") for u in images])
            except Exception:  # noqa: BLE001
                # 분류는 편의 기능이다. 실패해도 화면이 멈추면 안 된다 —
                # 전부 '자동 분류' 로 돌려주면 예전과 같은 순서 배치가 된다.
                cats = [vton.AUTO] * len(images[:vton.MAX_ITEMS])
            return self._json(200, {"ok": True, "categories": cats})
        if path == "/v1/virtual-fitting":
            req = self._read_json()
            if not req:
                return self._json(400, {"ok": False, "error": "BAD_BODY"})
            try:
                result = vton.generate(
                    items=req.get("items") if isinstance(req.get("items"), list) else None,
                    image_data_url=str(req.get("image") or ""),
                    model_id=str(req.get("model_id") or "woman"),
                    category=str(req.get("category") or "상의"),
                    # 착장 옵션(아우터 레이어드·열림/닫힘). 없으면 예전과 같다.
                    options=req.get("options") if isinstance(req.get("options"), dict) else None,
                    # 포즈 (2026-09-14). 비우면 준비된 포즈 중에서 무작위로
                    # 뽑는다 — 같은 옷을 다시 입혀 봐도 다른 컷이 나온다.
                    # 앞선 결과의 pose 를 그대로 보내면 같은 자세로 다시 낸다.
                    pose=str(req.get("pose") or "") or None,
                    # 생성 엔진 (2026-10-01) — sunburst(기본, 화질) · flare(빠르게).
                    # 모르는 이름이나 빈 값은 기본 엔진으로 간다(vton.engine_of).
                    engine=str(req.get("engine") or "") or None,
                    # 결과 사진 위 쇼핑 태그 (2026-10-02) — 판매처가 있는 상품이 있을 때만
                    # 화면이 켠다. vision 한 번이 더 들어 사진 직접 올린 경우는 끈다.
                    tags=req.get("tags") is True,
                )
            except (ValueError, RuntimeError) as exc:
                return self._json(400, {"ok": False, "error": type(exc).__name__,
                                        "message": str(exc)})
            except Exception as exc:  # noqa: BLE001
                return self._json(502, {"ok": False, "error": type(exc).__name__,
                                        "message": "착용 이미지를 만들지 못했습니다."})
            return self._json(200, {"ok": True, **result})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self._json(400, {"ok": False, "error": "BAD_BODY"})
        try:
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"ok": False, "error": "BAD_JSON"})

        question = str(req.get("question") or "")
        request_id = _request_id(req.get("request_id"))
        cancel_event = threading.Event()
        mode = "salmal" if req.get("mode") == "salmal" else "general"
        # ★ 요금제 (2026-10-03). 베타 동안은 예전과 같다 — effective() 가 무엇을 받든 BUSINESS.
        #   베타가 끝나면 요청이 적은 plan 을 믿지 않는다. Django 가 서명한 plan_ticket 만 믿고,
        #   없거나 틀리면 FREE 로 본다(plans.verify_ticket). 하루 횟수도 확인증이 있으면
        #   IP 가 아니라 계정으로 센다 — 한 IP 를 같이 쓰는 사람들이 서로의 횟수를 먹지 않게.
        ticket = None if plans.PUBLIC_BETA else plans.verify_ticket(req.get("plan_ticket"))
        plan = plans.effective(ticket["plan"] if ticket else None)
        quota_key = f"user:{ticket['user']}" if ticket else self._client_ip()
        conv = str(req.get("conversation_id") or "")[:64] or None
        # 클라이언트가 최근 턴을 같이 보낼 수 있다 (세션 목록의 원본은 클라이언트다).
        # 안 보내면 서버 메모리의 같은 conversation_id 를 쓴다.
        hist = req.get("history") if isinstance(req.get("history"), list) else None

        # ── 이미지 첨부 (2026-09-10) ─────────────────────────
        #   data URL 문자열만 받는다 — 형식이 아니면(잘못된 값·주소만 온 것 등)
        #   조용히 버린다. 개수·장당 용량은 여기서 미리 자른다 —
        #   ChatEngine 안까지 큰 문자열을 들고 가지 않게.
        images_in = req.get("images") if isinstance(req.get("images"), list) else []
        images: list[str] = []
        for u in images_in[:MAX_IMAGES]:
            if not isinstance(u, str):
                continue
            u = u.strip()
            if not u.startswith("data:image/"):
                continue
            if len(u) > MAX_IMAGE_DATAURL:
                return self._json(400, {"ok": False, "error": "IMAGE_TOO_LARGE",
                                        "message": "이미지 용량이 너무 큽니다. 더 작은 이미지로 다시 시도해 주세요."})
            images.append(u)

        if not daily_ok(quota_key, plan):
            limit = plans.QUOTA[plans.FREE]["turns"]
            return self._json(429, {
                "ok": False, "reason": "DAILY_LIMIT",
                "message": f"오늘 무료 이용 횟수({limit}회)를 다 쓰셨습니다.\n"
                           "내일 다시 이용하시거나, 더 넉넉한 플랜으로 올려 보세요.",
            })

        if request_id:
            with _chat_cancels_lock:
                _chat_cancels[request_id] = cancel_event

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()

        def push(ev, data):
            self.wfile.write(sse(ev, data))
            self.wfile.flush()

        try:
            push("status", {"stage": "lexicon"})
            e = engine()
            push("status", {"stage": "metric"})
            # 화면 컨텍스트 — 새 경로가 "이거 어때?" 를 푸는 재료.
            #   없으면 없는 대로 돈다(도구 목록만 줄어든다).
            extra = {k: req.get(k) for k in
                     ("screen_term", "salmal_card_id", "user_id", "region", "taste_context", "gender",
                      # 승인된 코디 — 이것이 있는 턴에만 build_fit 이 도구 목록에 있다
                      # (tools.specs_for). 승인을 거치지 않으면 확정할 코디가 없다.
                      "fit_proposal",
                      # 이 대화에서 보여 준 코디 기억 — '다른 룩' 이 같은 상품을 다시 내밀지
                      # 않게(fit.clean_memory 가 걸러 engine 이 ctx 에 넣는다).
                      "fit_memory")
                     if req.get(k)}
            if isinstance(extra.get("taste_context"), dict):
                extra["taste_context"] = clean_taste_context(extra["taste_context"])
            if extra.get("gender") not in ("FEMALE", "MALE"):
                extra.pop("gender", None)
            # ★ 도구를 부를 때마다 사용자의 말로 흘려보낸다 (설계도 부록 10).
            #   답이 완성될 때까지 화면이 비어 있으면 3초만 지나도 고장난 것처럼
            #   보인다. 같은 시간이라도 무엇을 보고 있는지 알면 기다림이 된다.
            def say(msg):
                push("status", {"stage": "tool", "message": msg})

            rep = e.ask(question, mode=mode, plan=plan,
                        conversation_id=conv, history_in=hist, extra=extra,
                        on_progress=say, images=images or None,
                        cancel_check=cancel_event.is_set)

            if cancel_event.is_set():
                return

            if not rep.get("ok"):
                # 실패도 대화다. 에러 코드로 끝내지 않고 할 말을 준다.
                push("error", rep)
                push("done", {"ok": False, "reason": rep.get("reason")})
                return

            if rep.get("kind") == "meta":
                for d in split_deltas(rep["message"]):
                    push("text", {"delta": d})
                    time.sleep(0.012)
                push("done", {"ok": True})
                return

            for d in split_deltas(rep["headline"]):
                push("text", {"delta": d})
                time.sleep(0.012)
            push("report", rep)
            _log_turn(question, rep)
            acts = actions_for(rep, mode=mode)
            if acts:
                push("actions", acts)
            push("done", {"ok": True, "intent": rep.get("intent"),
                          "as_of": rep.get("as_of"),
                          "partial": bool(rep.get("partial"))})
        except BrokenPipeError:
            pass                                   # 사용자가 창을 닫았다. 정상이다.
        except Exception as ex:                    # noqa: BLE001
            # ★ 삼키지 않는다 (2026-09-18). 예전에는 종류만 화면에 보내고 로그엔 아무것도
            #   안 남겨, "서버에서 답을 만들지 못했습니다" 의 원인을 찾을 길이 없었다.
            import traceback
            traceback.print_exc()
            tb = traceback.extract_tb(ex.__traceback__)
            where_ = next((f"{Path(f.filename).name}:{f.lineno}" for f in reversed(tb)
                           if "/app/" in f.filename or f.filename.endswith("server.py")), "")
            try:
                push("error", {"ok": False, "reason": "SERVER_ERROR",
                               "message": "서버에서 답을 만들지 못했습니다.",
                               # 종류와 위치만 — 예외 문구에는 값이 섞일 수 있어 싣지 않는다
                               "detail": type(ex).__name__ + (f" @ {where_}" if where_ else "")})
                push("done", {"ok": False})
            except OSError:
                pass
        finally:
            if request_id:
                with _chat_cancels_lock:
                    _chat_cancels.pop(request_id, None)


def main():
    port = PORT
    for a in sys.argv[1:]:
        if a.startswith("--port="):
            port = int(a.split("=", 1)[1])

    # ★ 준비물이 없으면 여기서 멈춘다.
    #   없는 채로 engine() 을 부르면 ImportError 스택트레이스가 뜨는데,
    #   처음 켜 보는 팀원에게 그건 "고장났다" 로 읽힌다. 무엇이 없는지 말해 준다.
    from app import config, llm
    gaps = config.missing_inputs()
    if gaps:
        print("먼저 채워야 할 것이 있습니다 — 챗봇 엔진을 켤 수 없습니다.\n")
        for g in gaps:
            print("  · " + g)
        print("\n어휘 추출기·Lexicon 은 ChatBot/vendor/ 에 들어 있습니다.")
        print("RDS 모드면 DB_* 환경변수를, SQLite 모드면 FEEDIT_CHAT_DB 를 확인해 주세요.")
        print("\n자세한 진단:  python3 tools_env_check.py")
        return 2

    # 사전을 미리 읽어 첫 요청을 빠르게 한다.
    # ★ 여기서 실패해도(RDS 가 잠깐 안 닿는 등) 죽지 않는다. 죽으면 컨테이너가
    #   재시작을 반복하고 앞단 nginx 는 502 만 돌려줘 원인이 안 보인다(2026-09-18).
    #   떠 있으면 /v1/health 가 실패 종류를 말하고, 다음 요청 때 엔진을 다시 만든다.
    srv = _Server((HOST, port), Handler)
    print(f"feedit-chat  http://{HOST}:{port}")
    try:
        e = engine()
        print(f"  기준일 {e.store.latest_day()} · 지표 term {len(e.gate.prefer):,}개")
    except Exception as ex:                           # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"  ⚠ 엔진을 만들지 못했습니다 ({type(ex).__name__}) — 서버는 띄우고 요청 때 다시 시도합니다.")
    print(f"  모델 {llm.MODEL} · 키 {llm.key_hint()}")
    print(f"  허용 오리진 {sorted(ALLOW_ORIGINS)}")
    access = ("토큰 검사함" if CHAT_TOKEN else "토큰 없음(로컬 개발)") + (
        " · 공개 베타(전 기능 개방)" if plans.PUBLIC_BETA else "")
    print(f"  접근 {access} · 분당 {RATE_PER_MIN}회 제한")
    if not plans.PUBLIC_BETA and not plans.ticket_secret():
        print("  ⚠ 베타가 꺼져 있는데 요금제 서명 키(FEEDIT_PLAN_SECRET 또는 FEEDIT_CHAT_TOKEN)가 없습니다.\n"
              "    모든 사용자를 FREE 로 봅니다.")
    if HOST not in ("127.0.0.1", "localhost") and not CHAT_TOKEN:
        print("  ⚠ 밖에 열면서 FEEDIT_CHAT_TOKEN 이 없습니다. 주소가 알려지면 누구나 질문할 수 있습니다.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
        srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
