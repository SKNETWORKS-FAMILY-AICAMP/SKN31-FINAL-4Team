"""경험치(XP) — 기록에서 매번 다시 계산하는 순수 계산부 (2026-09-25).

xp_service.py 가 DB 에서 행을 읽어 아래 모양으로 넘기면, 여기서 숫자를 만든다.
activity.py · notifications.py 처럼 DB 와 계산을 나눠 둔 이유는
Postgres 없이도 단위 테스트를 돌리기 위해서다.


★ 한 주
  한국 시간 월요일 00:00 ~ 일요일 23:59.
  한 주 최대 210 = 일일 15 × 7일(105) + 주간 105.


★ 일일 — 하루 최대 15
  접속              +3   그날 로그인한 채로 한 번이라도 들어오면
  챗봇 질문         +1   그날 1번째 질문
                    +3   그날 3번째 질문 (그래서 하루 최대 4)
  살!말? 투표       +1 / +3   (같은 규칙)
  찜하기            +1 / +3   (같은 규칙)

  투표 · 찜은 **처음 켠 대상만** 센다.
  같은 카드 · 상품을 껐다 켰다 반복해서 채울 수 없게 하려는 것이다.
  30초 안에 켰다 끈 것(잘못 누른 것)은 activity.py 와 같은 기준으로 없던 일로 본다.


★ 주간 — 한 주 최대 105
  주간 올출석        +5   그 주 7일 모두 접속 (시작 주는 시작일부터 센다)
  적중               +5   내 살/말 투표가 글쓴이의 실제 결과와 맞을 때마다 (최대 25)
                          판정 기준은 badges.correct_choice 와 같다.
                          결과가 나온 날(피드백 작성일)이 속한 주에 들어간다.
  투표 피드백        +25  마감된 내 카드에 결과(샀는지 안 샀는지)를 한 건이라도 남기면
  트렌드 분석 체류   +1   화면이 실제로 보이던 2분마다 (최대 25 = 50분)
  홈페이지 피드백    +25  불편사항·추가요청 / 수정사항·버그리포트를 한 건이라도 남기면
                          운영자가 '반려'한 글은 빠진다.


★ 0 에서 시작
  start(한국 시간 날짜) 이전의 기록은 세지 않는다.
  운영 계정은 계산하지 않고 최고 레벨로 고정한다 (xp_service.xp_state).


★ 레벨 구간은 프론트 account/static/js/rank.js 의 RK_XP 가 가진다.
  서버는 누적 XP 와 이번 주 · 오늘 내역만 준다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .activity import KST, _undone

# ── 일일 ──
DAILY_CAP = 15
VISIT_XP = 3
STEP_FIRST_XP = 1        # 그날 1번째
STEP_THIRD_XP = 3        # 그날 3번째 — 1번째 +1 에 더해진다
STEP_THIRD_AT = 3

# ── 주간 ──
WEEKLY_CAP = 105
DAILY_WEEK_CAP = DAILY_CAP * 7          # 105
WEEK_CAP = DAILY_WEEK_CAP + WEEKLY_CAP  # 210
ATTEND_XP = 5
HIT_XP, HIT_CAP = 5, 25
VOTE_FEEDBACK_XP = 25
DWELL_MINUTES_PER_XP, DWELL_CAP = 2, 25
SITE_FEEDBACK_XP = 25

DAILY_ITEMS = (
    # key,    이름,           한도,                          설명
    ("visit", "접속",          VISIT_XP,                      "로그인한 채로 들어오면 +3"),
    ("chat",  "챗봇 질문",     STEP_FIRST_XP + STEP_THIRD_XP, "첫 질문 +1 · 3번째 질문 +3"),
    ("vote",  "살!말? 투표",   STEP_FIRST_XP + STEP_THIRD_XP, "첫 투표 +1 · 3번째 투표 +3"),
    ("save",  "찜하기",        STEP_FIRST_XP + STEP_THIRD_XP, "첫 찜 +1 · 3번째 찜 +3"),
)
WEEKLY_ITEMS = (
    ("attend",        "주간 올출석",     ATTEND_XP,        "월~일 7일 모두 접속하면 +5"),
    ("hit",           "적중",            HIT_CAP,          "내 살/말 투표가 실제 결과와 맞을 때마다 +5"),
    ("vote_feedback", "투표 피드백",     VOTE_FEEDBACK_XP, "마감된 내 카드에 샀는지 남기면 +25"),
    ("dwell",         "트렌드 분석 체류", DWELL_CAP,       "화면을 보는 2분마다 +1 (50분까지)"),
    ("site_feedback", "홈페이지 피드백", SITE_FEEDBACK_XP, "불편사항 · 버그를 남기면 +25"),
)


def kst_day(dt) -> date:
    return dt.astimezone(KST).date()


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def step_xp(n: int) -> int:
    """그날 n번 했을 때의 경험치 — 1번째 +1, 3번째 +3."""
    return (STEP_FIRST_XP if n >= 1 else 0) + (STEP_THIRD_XP if n >= STEP_THIRD_AT else 0)


def first_on_times(rows, kind, key_name, is_on):
    """토글형 기록(찜 · 투표)에서 대상마다 **처음 켠 시각**만 돌려준다.

    30초 안에 켰다 끈 쌍(activity._undone)은 없던 일로 보고 건너뛴다 —
    잘못 누른 것은 '처음'을 차지하지 않는다.
    rows 는 activity.py 와 같은 모양 {"type", "at", "meta"} 이다.
    """
    drop = _undone(rows)
    seen, out = set(), []
    for row in sorted((r for r in rows if r["type"] == kind), key=lambda r: r["at"]):
        if id(row) in drop or not is_on(row["meta"]):
            continue
        key = str(row["meta"].get(key_name) or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row["at"])
    return out


def _day_counts(start, visits, chats, votes, saves):
    days = defaultdict(lambda: {"visit": 0, "chat": 0, "vote": 0, "save": 0})
    for d in visits:
        if d >= start:
            days[d]["visit"] = 1
    for key, times in (("chat", chats), ("vote", votes), ("save", saves)):
        for at in times:
            d = kst_day(at)
            if d >= start:
                days[d][key] += 1
    return days


def _day_items(c):
    return {
        "visit": VISIT_XP if c["visit"] else 0,
        "chat": step_xp(c["chat"]),
        "vote": step_xp(c["vote"]),
        "save": step_xp(c["save"]),
    }


def _day_xp(c) -> int:
    return min(DAILY_CAP, sum(_day_items(c).values()))


def _week_items(w, start, visit_set, hits, vote_fbs, dwell, site_fbs):
    """한 주(w = 월요일)의 주간 항목 — {key: (xp, 진행 정보)}."""
    week_days = [w + timedelta(days=i) for i in range(7)]
    need = [d for d in week_days if d >= start]
    came = [d for d in need if d in visit_set]
    # 아직 오지 않은 날이 남았으면 채울 수 없으니 0 이다 — 일요일에 들어오는 순간 붙는다.
    attend = ATTEND_XP if need and len(came) == len(need) else 0

    def in_week(at):
        d = kst_day(at)
        return w <= d < w + timedelta(days=7) and d >= start

    n_hit = sum(1 for at in hits if in_week(at))
    n_vf = sum(1 for at in vote_fbs if in_week(at))
    n_sf = sum(1 for at in site_fbs if in_week(at))
    seconds = sum(int(dwell.get(d, 0) or 0) for d in need)
    minutes = seconds // 60
    return {
        "attend": (attend, {"count": len(came), "goal": len(need) or 7}),
        "hit": (min(HIT_CAP, HIT_XP * n_hit), {"count": n_hit}),
        "vote_feedback": (VOTE_FEEDBACK_XP if n_vf else 0, {"count": n_vf}),
        "dwell": (min(DWELL_CAP, minutes // DWELL_MINUTES_PER_XP),
                  {"minutes": minutes, "goal": DWELL_CAP * DWELL_MINUTES_PER_XP}),
        "site_feedback": (SITE_FEEDBACK_XP if n_sf else 0, {"count": n_sf}),
    }


def _week_xp(items) -> int:
    return min(WEEKLY_CAP, sum(xp for xp, _ in items.values()))


def compute_xp(*, now, start: date, visits=(), chats=(), votes=(), saves=(),
               hits=(), vote_feedbacks=(), dwell=None, site_feedbacks=()):
    """누적 XP 와 오늘 · 이번 주 내역.

    visits          접속한 날짜들 (date)
    chats           챗봇 질문 시각들 (aware datetime)
    votes · saves   처음 켠 시각들 — first_on_times() 결과
    hits            적중이 확정된 시각들 (피드백 작성 시각)
    vote_feedbacks  내가 남긴 살!말? 사후 피드백 시각들
    dwell           {date: 트렌드 분석 체류 초}
    site_feedbacks  반려되지 않은 홈페이지 피드백 시각들
    """
    dwell = dict(dwell or {})
    visit_set = {d for d in visits if d >= start}
    today = kst_day(now)
    this_week = week_start(today)

    days = _day_counts(start, visit_set, chats, votes, saves)
    daily_total = sum(_day_xp(c) for c in days.values())

    weeks = {week_start(d) for d in days}
    weeks |= {week_start(d) for d in dwell if d >= start}
    for times in (hits, vote_feedbacks, site_feedbacks):
        weeks |= {week_start(kst_day(at)) for at in times if kst_day(at) >= start}
    week_items = {w: _week_items(w, start, visit_set, hits, vote_feedbacks, dwell, site_feedbacks)
                  for w in weeks}
    weekly_total = sum(_week_xp(items) for items in week_items.values())

    # ── 오늘 ──
    today_counts = days.get(today, {"visit": 0, "chat": 0, "vote": 0, "save": 0})
    today_xp = _day_items(today_counts)
    today_rows = [
        {"key": key, "label": label, "xp": today_xp[key], "max": cap, "hint": hint,
         "count": today_counts[key]}
        for key, label, cap, hint in DAILY_ITEMS
    ]

    # ── 이번 주 ──
    cur = week_items.get(this_week) or _week_items(
        this_week, start, visit_set, hits, vote_feedbacks, dwell, site_feedbacks)
    week_daily = sum(_day_xp(c) for d, c in days.items() if week_start(d) == this_week)
    week_weekly = _week_xp(cur)
    weekly_rows = []
    for key, label, cap, hint in WEEKLY_ITEMS:
        xp, info = cur[key]
        weekly_rows.append({"key": key, "label": label, "xp": xp, "max": cap, "hint": hint, **info})

    return {
        "fixed": False,
        "total": daily_total + weekly_total,
        "start": start.isoformat(),
        "today": {
            "date": today.isoformat(),
            "earned": min(DAILY_CAP, sum(today_xp.values())),
            "cap": DAILY_CAP,
            "items": today_rows,
        },
        "week": {
            "start": this_week.isoformat(),
            "end": (this_week + timedelta(days=6)).isoformat(),
            "earned": week_daily + week_weekly,
            "cap": WEEK_CAP,
            "daily": {"earned": week_daily, "cap": DAILY_WEEK_CAP},
            "weekly": {"earned": week_weekly, "cap": WEEKLY_CAP, "items": weekly_rows},
        },
    }


def fixed_xp_state():
    """운영 계정 — 계산하지 않고 최고 레벨로 고정한다."""
    return {"fixed": True, "total": None}
