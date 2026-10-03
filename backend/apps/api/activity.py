"""금주의 리포트 · 활동 지표 집계 (DB 없이 도는 순수 계산부).

activity_views.py 가 DB에서 행을 읽어 dict 목록으로 넘기면, 여기서 숫자를 만든다.
DB 조회와 계산을 나눠 둔 이유는 Postgres 없이도 단위 테스트를 돌리기 위해서다.

★ 주(週) 기준
  - 한국 시간 월요일 00:00 ~ 일요일 23:59 를 한 주로 본다.
  - '지난주 대비'는 바로 앞 주(월~일) 전체와 비교한다.

★ 이벤트 한 행의 모양 (activity_views._event_rows 가 만든다)
  {"type": "SEARCH"|"VOTE"|"SAVE"|"CHAT", "at": aware datetime, "meta": dict, "style": str|None}
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
TASTE_LIMIT = 4

# 켰다가 이 시간 안에 다시 끈 것은 '없던 일'로 본다 (초).
# 잘못 눌러 바로 취소한 것까지 활동량으로 세면, 화면의 막대가 실제 관심보다 부풀어 보인다.
# 값을 바꾸고 싶으면 여기 한 줄만 고치면 된다.
UNDO_WINDOW = 30


def week_bounds(now: datetime):
    """이번 주 월요일 00:00(KST), 다음 주 월요일 00:00, 지난주 월요일 00:00 을 돌려준다."""
    local = now.astimezone(KST)
    start = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7), start - timedelta(days=7)


def _in(row, lo, hi):
    return lo <= row["at"] < hi


def latest_state(events, kind, key_name, on_value):
    """토글형 기록(찜·투표)의 '지금 상태'를 계산한다.

    같은 대상에 여러 번 누르면 마지막 기록만 유효하다.
    반환: {대상 키: 마지막으로 켜진 시각} — 꺼진 대상은 빠진다.
    """
    last = {}
    for row in sorted((r for r in events if r["type"] == kind), key=lambda r: r["at"]):
        key = str(row["meta"].get(key_name) or "")
        if key:
            last[key] = row
    return {k: r["at"] for k, r in last.items() if on_value(r["meta"])}


def _voted(meta):
    return meta.get("choice") in ("BUY", "PASS")


def _liked(meta):
    return bool(meta.get("liked"))


def _search_block(events, start, end, prev):
    this = [r for r in events if r["type"] == "SEARCH" and _in(r, start, end)]
    last = [r for r in events if r["type"] == "SEARCH" and _in(r, prev, start)]
    words = Counter(str(r["meta"].get("q") or "").strip() for r in this)
    words.pop("", None)
    prev_words = {str(r["meta"].get("q") or "").strip() for r in last} - {""}
    top = None
    if words:
        # 횟수가 같으면 더 최근에 검색한 말을 앞에 둔다.
        recent = {}
        for r in this:
            recent[str(r["meta"].get("q") or "").strip()] = r["at"]
        label, n = max(words.items(), key=lambda kv: (kv[1], recent.get(kv[0])))
        # 축(스타일 · 브랜드 · 아이템 · 색상 · TPO …)은 그 말을 마지막으로 검색했을 때 남은 값을 쓴다.
        facet = next((str(r["meta"].get("facet") or "") for r in reversed(this)
                      if str(r["meta"].get("q") or "").strip() == label and r["meta"].get("facet")), "")
        top = {"label": label, "count": n, "facet": facet}
    return {
        "keywords": len(words),              # 이번 주 검색한 서로 다른 키워드 수
        "count": len(this),                  # 검색 횟수
        "prev_keywords": len(prev_words),
        "delta": len(words) - len(prev_words),
        "top": top,
    }


def _vote_block(events, start, end, prev):
    def voted_in(lo, hi):
        rows = [r for r in events if r["type"] == "VOTE" and r["at"] < hi]
        state = latest_state(rows, "VOTE", "card_key", _voted)
        return sum(1 for at in state.values() if at >= lo)

    now_state = latest_state(events, "VOTE", "card_key", _voted)
    this, last = voted_in(start, end), voted_in(prev, start)
    return {"count": this, "prev": last, "delta": this - last, "total": len(now_state)}


def _saved_block(events, start, end):
    state = latest_state(events, "SAVE", "item_id", _liked)
    return {"new": sum(1 for at in state.values() if start <= at < end), "total": len(state)}


IDLE_GAP_SEC = 5 * 60        # 이보다 오래 비면 자리를 비운 것으로 보고 끊는다
ANSWER_MAX_SEC = 3 * 60      # 응답 시간 상한 — 멈춘 요청 하나가 시간을 부풀리지 않게


def _chat_block(events, sessions, start, end):
    """챗봇 '실제 사용 시간'.

    예전에는 chat_session 의 started_at ~ updated_at 을 셌다. 그러면 월요일에 한 번 묻고
    일요일에 한 번 더 물은 대화가 6일이 된다. 이제는 질문 단위로 센다.

      · 질문 하나 = [질문 시각, 질문 시각 + 응답 시간(answer_ms)] 구간
        (CHAT 이벤트의 at 이 질문 시각, meta.answer_ms 는 답이 끝났을 때 chat_views 가 채운다)
      · 앞 구간이 끝나고 5분 안에 다음 질문을 했으면 그 사이(답을 읽고 다음 질문을 쓰는 시간)도 사용 중으로 본다
      · 5분 넘게 비면 끊는다 — 그 공백은 세지 않는다
      · 다른 대화방을 동시에 써도 겹치는 시간은 한 번만 센다

    질문을 한 번이라도 했으면 최소 1분으로 올린다.
    CHAT 이벤트가 하나도 없던 옛 기록만 예전 방식(세션 시작~끝, 대화당 30분 상한)으로 센다.
    """
    turns = sorted((r for r in events if r["type"] == "CHAT" and _in(r, start, end)), key=lambda r: r["at"])
    if turns:
        spans, convs = [], set()
        for r in turns:
            meta = r["meta"] or {}
            try:
                ans = float(meta.get("answer_ms") or 0) / 1000
            except (TypeError, ValueError):
                ans = 0.0
            ans = max(0.0, min(ans, ANSWER_MAX_SEC))
            spans.append((r["at"], r["at"] + timedelta(seconds=ans)))
            convs.add(meta.get("conversation_id") or id(r))
        total = 0.0
        g_start, g_end = spans[0]
        for a, b in spans[1:]:
            if (a - g_end).total_seconds() <= IDLE_GAP_SEC:
                g_end = max(g_end, b)
            else:
                total += (g_end - g_start).total_seconds()
                g_start, g_end = a, b
        total += (g_end - g_start).total_seconds()
        minutes = max(1, round(total / 60))
        n = len(convs)
        return {"minutes": minutes, "sessions": n, "avg_minutes": max(1, round(total / 60 / n)) if n else 0}

    mins = []
    for s in sessions:
        if not (start <= s["updated_at"] < end):
            continue
        began = max(s["started_at"], start)
        mins.append(min(30, max(1, round((s["updated_at"] - began).total_seconds() / 60))))
    total = sum(mins)
    return {"minutes": total, "sessions": len(mins), "avg_minutes": round(total / len(mins)) if mins else 0}


# 토글형 기록(찜·투표)의 켬/끔 판정. (이벤트 종류, 대상 키, 켜짐인가) 로 읽는다.
TOGGLES = (
    ("SAVE", "item_id", lambda m: bool(m.get("liked"))),
    ("VOTE", "card_key", lambda m: m.get("choice") in ("BUY", "PASS")),
)


def _undone(events):
    """켰다가 UNDO_WINDOW 안에 끈 쌍을 찾아 그 두 행을 돌려준다.

    왜 필요한가
    -----------
    찜을 잘못 눌러 곧바로 취소해도 user_event 에는 두 행(liked True → False)이 남는다.
    '찜한 것' KPI 는 마지막 상태만 보므로 0으로 맞지만, 요일별 활동 막대는 행 수를
    그대로 세기 때문에 왕복 한 번이 활동 2건이 된다. 사람은 그 막대를
    "내가 이만큼 관심을 보였다"로 읽으므로, 없던 일은 빼는 편이 정직하다.

    같은 대상을 여러 번 켜고 끄면 각 쌍을 따로 본다. 창을 넘겨 끈 것(진짜로 한동안
    찜해 두었다가 나중에 취소한 것)은 **빼지 않는다** — 그건 실제 활동이다.
    반환: 제외할 행의 id 집합(파이썬 객체 식별자).
    """
    drop = set()
    for kind, key_name, is_on in TOGGLES:
        rows = sorted((r for r in events if r["type"] == kind), key=lambda r: r["at"])
        pending = {}   # 대상 키 → 아직 짝을 못 찾은 '켬' 행
        for row in rows:
            key = str(row["meta"].get(key_name) or "")
            if not key:
                continue
            if is_on(row["meta"]):
                pending[key] = row
                continue
            opened = pending.pop(key, None)
            if opened is None:
                continue
            if (row["at"] - opened["at"]).total_seconds() <= UNDO_WINDOW:
                drop.add(id(opened))
                drop.add(id(row))
    return drop


def _activity_block(events, start, end):
    """요일별 · 시간대별 활동량. 30초 안에 취소한 찜·투표는 세지 않는다."""
    drop = _undone(events)
    days, hours = [0] * 7, [0] * 24
    for r in events:
        if _in(r, start, end) and id(r) not in drop:
            local = r["at"].astimezone(KST)
            days[local.weekday()] += 1
            hours[local.hour] += 1
    return {"days": days, "hours": hours}


def _taste_block(events, start, end, prev):
    """내 취향 지분 — 이번 주와 지난주에 **검색한 키워드 중 스타일**의 비중을 비교한다 (방식 b).

    스냅샷 테이블 없이 user_event 만으로 계산한다.
    ★ 2026-09-17 · 투표 · 찜은 빼고 검색만 센다. 리포트의 축이 '가장 많이 검색한 키워드'이고,
      취향 지분은 그 검색 기록을 스타일 축으로만 나눠 본 것이다.
    스타일이 아닌 검색(브랜드 · 아이템 · 색상 · TPO …)은 분모에서 뺀다.
    """
    kinds = ("SEARCH",)

    def shares(lo, hi):
        c = Counter(r["style"] for r in events if r["type"] in kinds and r.get("style") and _in(r, lo, hi))
        n = sum(c.values())
        return ({k: v / n * 100 for k, v in c.items()} if n else {}), n

    cur, n_cur = shares(start, end)
    old, n_old = shares(prev, start)
    rows = []
    for label, pct in sorted(cur.items(), key=lambda kv: -kv[1])[:TASTE_LIMIT]:
        rows.append({
            "label": label,
            "share": round(pct),
            # 지난주 기록이 아예 없으면 비교하지 않는다(None) — 0에서 올랐다고 부풀리지 않는다.
            "delta": None if not n_old else round(pct - old.get(label, 0.0)),
        })
    new = [r["label"] for r in rows if n_old and r["label"] not in old]
    return {"items": rows, "signals": n_cur, "prev_signals": n_old, "new_style": new[0] if new else None}


def build_weekly_report(events, sessions, now):
    start, end, prev = week_bounds(now)
    return {
        "week": {"start": start.date().isoformat(), "end": (end - timedelta(days=1)).date().isoformat()},
        "search": _search_block(events, start, end, prev),
        "vote": _vote_block(events, start, end, prev),
        "saved": _saved_block(events, start, end),
        "chat": _chat_block(events, sessions, start, end),
        "activity": _activity_block(events, start, end),
        "taste": _taste_block(events, start, end, prev),
    }
