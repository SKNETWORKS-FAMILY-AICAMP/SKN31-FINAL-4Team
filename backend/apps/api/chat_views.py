"""챗봇 대화 기록 API — /api/auth/chats

대화의 원본은 RDS 의 app.chat_session · app.chat_message 다.
브라우저(localStorage)는 화면을 빨리 그리기 위한 사본일 뿐이다.

  GET    /api/auth/chats                 내 대화 목록 (최근순, 고정 먼저)
  GET    /api/auth/chats?id=<session>    대화 하나의 메시지 전부
  POST   /api/auth/chats  {op:"turn"}     질문 + 답변 한 턴 저장 (세션이 없으면 만든다)
  POST   /api/auth/chats  {op:"import"}   브라우저에만 있던 대화를 한 번에 옮긴다
  POST   /api/auth/chats  {op:"update"}   제목 · 고정 변경
  POST   /api/auth/chats  {op:"truncate"} 질문을 고쳐 다시 물을 때 그 뒤 메시지를 지운다
  DELETE /api/auth/chats  {key}           대화 삭제 — 메시지는 지우고 세션 행은 남긴다(아래)

세션 식별
  context.conversation_id = "cp-<mode>-<key>". 팀의 /api/auth/event(CHAT) 도
  같은 값으로 세션을 찾으므로 두 기록이 한 행으로 모인다(금주의 리포트 사용 시간).

★ 삭제해도 '챗봇 사용 시간'은 남는다
  금주의 리포트(activity.py _chat_block)는 chat_session 의 started_at ~ updated_at 으로
  사용 시간을 센다. 그래서 삭제는 메시지(본문)만 지우고 세션 행은 context.deleted=true,
  제목 없음으로 남긴다. 목록 · 조회에서는 보이지 않는다.
  같은 이유로 이름 변경 · 고정 · 삭제는 updated_at 을 건드리지 않는다(queryset.update) —
  일주일 전 대화 이름을 바꿨다고 사용 시간이 일주일로 늘면 안 된다.

★ 첨부 사진(data URL)은 저장하지 않는다 — 한 장이 수백 KB 다. 장 수만 남기고,
  사진에서 읽어 낸 관찰값은 turn.visual 에 남아 다음 질문의 맥락으로 쓰인다.
"""

from __future__ import annotations

import re

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from datetime import timedelta

from django.utils import timezone

from apps.core.models import ChatMessage, ChatSession, UserEvent

from .activity_views import _body, _error, _login_profile, _text

MODES = ("general", "salmal")
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
HTML_MAX = 120_000        # 답변 카드 한 조각 상한 (보고서 카드가 커도 이 안에 든다)
TEXT_MAX = 8_000
LIST_MAX = 60
IMPORT_MAX_TURNS = 40
HTML_FIELDS = ("html", "card_html", "follow_html", "cue_html", "actions_html")


def _conv_id(mode, key):
    return f"cp-{mode}-{key}"


def _clip(value, limit):
    return str(value or "")[:limit]


def _clean_turn(turn):
    """챗봇 기억에 필요한 것만 — 무엇을 물었나 · 어떤 용어 · 사진 관찰값 · 챗봇이 되물은 것.

    ★ next (2026-10-01) — 답변 끝의 이어 갈 질문. "응 두개 다 알려줘" 가 무엇에 대한
      대답인지 다음 턴이 알아야 한다. 여기서 버리면 대화를 다시 열었을 때 사라진다.
    """
    if not isinstance(turn, dict):
        return None
    terms = []
    for t in (turn.get("terms") or [])[:12]:
        if isinstance(t, dict) and t.get("canonical"):
            terms.append({k: _text(t.get(k), 80) for k in ("canonical", "facet", "term_key")})
    out = {"q": _text(turn.get("q"), 500), "intent": _text(turn.get("intent"), 60), "terms": terms}
    if isinstance(turn.get("visual"), (dict, list)):
        out["visual"] = turn["visual"]
    nxt = _text(turn.get("next"), 200)
    if nxt:
        out["next"] = nxt
    return out


def _session_row(s):
    ctx = s.context if isinstance(s.context, dict) else {}
    return {
        "id": s.id,
        "key": ctx.get("key") or "",
        "mode": ctx.get("mode") or "general",
        "conversation_id": ctx.get("conversation_id") or "",
        "title": s.title or "",
        "pinned": bool(ctx.get("pinned")),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _message_row(m):
    meta = m.metadata if isinstance(m.metadata, dict) else {}
    return {"id": m.id, "role": m.role, "content": m.content, "metadata": meta,
            "created_at": m.created_at.isoformat() if m.created_at else None}


def _mode_key(data):
    mode = _text(data.get("mode"), 10)
    key = _text(data.get("key"), 40)
    if mode not in MODES:
        return None, None, "mode 는 general 또는 salmal 이어야 합니다."
    if not KEY_RE.match(key or ""):
        return None, None, "key 형식이 올바르지 않습니다."
    return mode, key, None


def _live(qs):
    """삭제 표시된 세션은 빼고 — 사용 시간 집계용으로만 남아 있는 행이다."""
    # exclude(context__deleted=True) 는 키가 없는 행(NULL)까지 빼 버린다 — 둘로 나눠 적는다
    return qs.filter(Q(context__deleted__isnull=True) | Q(context__deleted=False))


def _set_ctx(s, **changes):
    """context 만 고친다. save() 를 부르면 auto_now 인 updated_at 이 움직인다."""
    ctx = dict(s.context or {}); ctx.update(changes); s.context = ctx
    ChatSession.objects.filter(id=s.id).update(context=ctx)


def _find(profile, mode, key, lock=False):
    qs = _live(ChatSession.objects.filter(user=profile, context__conversation_id=_conv_id(mode, key)))
    if lock:
        qs = qs.select_for_update()
    return qs.first()


def _get_or_create(profile, mode, key, title):
    s = _find(profile, mode, key, lock=True)
    if s is None:
        # 팀의 event(CHAT) 가 먼저 만든 행이면 위에서 찾힌다. 없을 때만 만든다.
        s = ChatSession.objects.create(
            user=profile, title=_text(title, 300) or None,
            context={"conversation_id": _conv_id(mode, key), "key": key, "mode": mode, "pinned": False},
        )
        return s
    ctx = dict(s.context or {})
    changed = False
    for k, v in (("key", key), ("mode", mode)):
        if ctx.get(k) != v:
            ctx[k] = v; changed = True
    if changed:
        s.context = ctx
    if not s.title and title:
        s.title = _text(title, 300)
    s.save()   # updated_at 을 앞으로 민다
    return s


def _write_turn(session, turn_in):
    """{question, images, answer:{text, html…, key, turn}} → USER · ASSISTANT 두 행."""
    q = _clip(turn_in.get("question"), TEXT_MAX)
    images = turn_in.get("images")
    images = max(0, min(9, int(images))) if isinstance(images, int) else 0
    user_msg = ChatMessage.objects.create(
        session=session, role=ChatMessage.Role.USER, content=q,
        metadata={"images": images} if images else {},
    )
    ans = turn_in.get("answer") if isinstance(turn_in.get("answer"), dict) else {}
    meta = {k: _clip(ans.get(k), HTML_MAX) for k in HTML_FIELDS if ans.get(k)}
    if ans.get("key"):
        meta["key"] = _text(ans.get("key"), 40)
    t = _clean_turn(ans.get("turn"))
    if t:
        meta["turn"] = t
    ai_msg = ChatMessage.objects.create(
        session=session, role=ChatMessage.Role.ASSISTANT,
        content=_clip(ans.get("text"), TEXT_MAX), metadata=meta,
    )
    return user_msg.id, ai_msg.id


def _record_answer_time(profile, session, answer_ms):
    """금주의 리포트 '챗봇 사용 시간'용 — 이 질문의 CHAT 이벤트에 응답 시간을 붙인다.

    질문할 때 프론트가 /api/auth/event(CHAT) 로 남긴 행(at = 질문 시각)을 찾아 answer_ms 를 채운다.
    그 행이 없으면(기록 요청이 실패했으면) 질문 시각으로 되짚어 새로 만든다.
    user_event 는 대화방을 지워도 남으므로 사용 시간 누적이 유지된다 (activity._chat_block).
    """
    try:
        ms = int(answer_ms)
    except (TypeError, ValueError):
        return
    ms = max(0, min(ms, 3 * 60 * 1000))
    conv = (session.context or {}).get("conversation_id")
    ev = (UserEvent.objects.filter(user=profile, event_type=UserEvent.EventType.CHAT,
                                   metadata__conversation_id=conv,
                                   created_at__gte=timezone.now() - timedelta(minutes=10))
          .order_by("-created_at").first())
    # 이 대화의 가장 최근 질문 기록이 아직 응답 시간이 없을 때만 그 행이 '이번 질문'이다
    if ev is not None and "answer_ms" not in (ev.metadata or {}):
        meta = dict(ev.metadata or {}); meta["answer_ms"] = ms; meta["chat_session_id"] = session.id
        UserEvent.objects.filter(id=ev.id).update(metadata=meta)
        return
    ev = UserEvent.objects.create(user=profile, event_type=UserEvent.EventType.CHAT,
                                  metadata={"conversation_id": conv, "chat_session_id": session.id,
                                            "answer_ms": ms})
    UserEvent.objects.filter(id=ev.id).update(created_at=timezone.now() - timedelta(milliseconds=ms))


@require_http_methods(["GET", "POST", "DELETE"])
def chats(request):
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)

    if request.method == "GET":
        sid = request.GET.get("id")
        if sid:
            if not str(sid).isdigit():
                return _error("id 가 올바르지 않습니다.")
            s = _live(ChatSession.objects.filter(user=profile, id=int(sid))).first()
            if s is None:
                return _error("대화를 찾을 수 없습니다.", status=404)
            msgs = [_message_row(m) for m in s.messages.order_by("created_at", "id")]
            return JsonResponse({"status": "ok", "data": {"session": _session_row(s), "messages": msgs}})
        qs = _live(ChatSession.objects.filter(user=profile, context__has_key="key"))
        mode = request.GET.get("mode")
        if mode in MODES:
            qs = qs.filter(context__mode=mode)
        rows = [_session_row(s) for s in qs.order_by("-updated_at")[:LIST_MAX]]
        rows.sort(key=lambda r: not r["pinned"])   # 안정 정렬 — 고정 먼저, 그 안에서 최근순
        return JsonResponse({"status": "ok", "data": {"sessions": rows}})

    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    mode, key, err = _mode_key(data)
    if err:
        return _error(err)

    if request.method == "DELETE":
        with transaction.atomic():
            s = _find(profile, mode, key, lock=True)
            if s is not None:
                s.messages.all().delete()                       # 본문은 지운다
                _set_ctx(s, deleted=True, pinned=False)         # 행은 사용 시간 집계용으로 남긴다
                ChatSession.objects.filter(id=s.id).update(title=None)
        return JsonResponse({"status": "ok", "data": {"deleted": True}})

    op = _text(data.get("op"), 20)
    with transaction.atomic():
        if op == "turn":
            s = _get_or_create(profile, mode, key, data.get("title"))
            uid, aid = _write_turn(s, data)
            _record_answer_time(profile, s, data.get("answer_ms"))
            return JsonResponse({"status": "ok", "data": {"session": _session_row(s),
                                                          "user_message_id": uid, "ai_message_id": aid}})
        if op == "import":
            turns = data.get("turns") if isinstance(data.get("turns"), list) else []
            s = _find(profile, mode, key, lock=True)
            if s is not None and s.messages.exists():
                return JsonResponse({"status": "ok", "data": {"session": _session_row(s), "ids": [], "skipped": True}})
            s = _get_or_create(profile, mode, key, data.get("title"))
            _set_ctx(s, pinned=bool(data.get("pinned")))
            ids = [_write_turn(s, t) for t in turns[:IMPORT_MAX_TURNS] if isinstance(t, dict)]
            return JsonResponse({"status": "ok", "data": {"session": _session_row(s), "ids": ids}})
        s = _find(profile, mode, key, lock=True)
        if s is None:
            return _error("대화를 찾을 수 없습니다.", status=404)
        if op == "update":
            if "title" in data:
                s.title = _text(data.get("title"), 300) or None
                ChatSession.objects.filter(id=s.id).update(title=s.title)
            if "pinned" in data:
                _set_ctx(s, pinned=bool(data.get("pinned")))
            return JsonResponse({"status": "ok", "data": {"session": _session_row(s)}})
        if op == "truncate":
            from_id = data.get("from_message_id")
            if not isinstance(from_id, int):
                return _error("from_message_id 가 필요합니다.")
            n, _ = s.messages.filter(id__gte=from_id).delete()
            return JsonResponse({"status": "ok", "data": {"deleted": n}})
    return _error("op 는 turn · import · update · truncate 중 하나여야 합니다.")
