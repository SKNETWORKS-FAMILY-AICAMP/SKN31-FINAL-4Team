"""경험치 — DB 에서 기록을 읽어 xp.py 계산부에 넘기고, 접속 · 체류를 적는다 (2026-09-25).

계산 규칙은 xp.py 맨 위 설명이 기준이다. 여기에는 '어느 표의 어느 행을 세는가'만 있다.

  접속          app.user_daily_activity (하루 한 행)
  챗봇 질문     app.user_event CHAT
  투표 · 찜     app.user_event VOTE · SAVE — 대상마다 처음 켠 시각
  적중          app.vote_ballot × app.vote_feedback (남의 카드 · badges.correct_choice)
  투표 피드백   app.vote_feedback (내가 글쓴이)
  체류          app.user_daily_activity.analysis_seconds
  홈페이지 피드백  app.site_feedback (반려 제외)
"""

from __future__ import annotations

import os
from datetime import date, datetime, time

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    SiteFeedback,
    UserDailyActivity,
    UserEvent,
    UserXp,
    VoteBallot,
    VoteFeedback,
)

from .activity import KST, TOGGLES
from .badges import correct_choice
from .xp import compute_xp, first_on_times, fixed_xp_state, kst_day

# 모든 일반 계정이 0 XP 에서 시작하는 날(한국 시간). 이 날 전의 기록은 세지 않는다.
# 배포가 늦어지면 .env 의 FEEDIT_XP_START=YYYY-MM-DD 로 배포일을 적는다.
DEFAULT_XP_START = date(2026, 9, 25)

# 체류 기록 한 번에 받을 수 있는 최대 초. 프론트는 60초마다 보낸다.
DWELL_PING_MAX = 90


def xp_start() -> date:
    raw = (os.getenv("FEEDIT_XP_START") or "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return DEFAULT_XP_START


def _start_dt(start: date) -> datetime:
    return datetime.combine(start, time.min, tzinfo=KST)


def is_operator(user) -> bool:
    """운영 계정 — 서버 곳곳의 기준(permissions.py)과 같다."""
    return bool(user and (user.is_superuser or user.is_staff))


def xp_inputs(profile, start: date) -> dict:
    since = _start_dt(start)
    visits, dwell = set(), {}
    for day, seconds in (UserDailyActivity.objects.filter(user=profile, day__gte=start)
                         .values_list("day", "analysis_seconds")):
        visits.add(day)
        if seconds:
            dwell[day] = seconds

    chats = list(UserEvent.objects.filter(
        user=profile, event_type=UserEvent.EventType.CHAT, created_at__gte=since,
    ).values_list("created_at", flat=True))

    # 투표 · 찜은 '처음 켠 때'를 가려야 하므로 시작일 전 기록까지 전부 읽는다.
    # 시작 전에 이미 찜한 상품을 껐다 다시 켜도 새 찜으로 치지 않는다.
    rows = [
        {"type": kind, "at": at, "meta": meta if isinstance(meta, dict) else {}}
        for kind, at, meta in UserEvent.objects.filter(
            user=profile, event_type__in=(UserEvent.EventType.VOTE, UserEvent.EventType.SAVE),
        ).order_by("created_at").values_list("event_type", "created_at", "metadata")
    ]
    toggles = {kind: (key, on) for kind, key, on in TOGGLES}
    votes = first_on_times(rows, "VOTE", *toggles["VOTE"])
    saves = first_on_times(rows, "SAVE", *toggles["SAVE"])

    hits = []
    judged = (VoteBallot.objects.filter(user=profile, card__feedback__created_at__gte=since)
              .exclude(card__user=profile)
              .select_related("card__feedback"))
    for ballot in judged:
        fb = ballot.card.feedback
        if correct_choice(fb) == ballot.choice:
            hits.append(fb.created_at)

    vote_feedbacks = list(VoteFeedback.objects.filter(user=profile, created_at__gte=since)
                          .values_list("created_at", flat=True))
    site_feedbacks = list(SiteFeedback.objects.filter(user=profile, created_at__gte=since)
                          .exclude(status=SiteFeedback.Status.REJECTED)
                          .values_list("created_at", flat=True))
    return {
        "visits": visits, "chats": chats, "votes": votes, "saves": saves, "hits": hits,
        "vote_feedbacks": vote_feedbacks, "dwell": dwell, "site_feedbacks": site_feedbacks,
    }


def xp_state(profile, now=None, save=True) -> dict | None:
    """내 경험치 — 누적 · 오늘 · 이번 주. 운영 계정은 고정."""
    if profile is None:
        return None
    if is_operator(profile.user):
        return fixed_xp_state()
    now = now or timezone.now()
    start = xp_start()
    state = compute_xp(now=now, start=start, **xp_inputs(profile, start))
    if save:
        _save_snapshot(profile, state["total"])
    return state


def _save_snapshot(profile, total):
    """다른 사람 화면(살!말? 댓글)에 쓸 사본 — 값이 바뀌었을 때만 쓴다."""
    row = UserXp.objects.filter(user=profile).only("id", "total").first()
    if row is None:
        UserXp.objects.get_or_create(user=profile, defaults={"total": total})
    elif row.total != total:
        UserXp.objects.filter(pk=row.pk).update(total=total, updated_at=timezone.now())


def mark_visit(profile, now=None):
    """오늘(한국 시간) 접속을 적는다. 하루 한 행이라 몇 번을 불러도 같다."""
    if profile is None:
        return None
    now = now or timezone.now()
    row, _ = UserDailyActivity.objects.get_or_create(user=profile, day=kst_day(now))
    return row


def add_dwell(profile, seconds, now=None) -> int:
    """트렌드 분석 체류 시간을 더한다. 실제로 더한 초를 돌려준다.

    화면이 보낸 초를 그대로 믿지 않는다.
      · 한 번에 DWELL_PING_MAX 초까지만 받는다.
      · 오늘 마지막으로 받은 때부터 실제로 흐른 시간보다 많이 받지 않는다.
        탭을 여러 개 띄워도, 요청을 빨리 보내도 시간이 부풀지 않는다.
    """
    now = now or timezone.now()
    try:
        want = int(seconds)
    except (TypeError, ValueError):
        return 0
    want = max(0, min(want, DWELL_PING_MAX))
    if not want:
        return 0
    day = kst_day(now)
    with transaction.atomic():
        UserDailyActivity.objects.get_or_create(user=profile, day=day)
        row = UserDailyActivity.objects.select_for_update().get(user=profile, day=day)
        if row.analysis_ping_at is not None:
            elapsed = int((now - row.analysis_ping_at).total_seconds())
            want = max(0, min(want, elapsed))
        row.analysis_seconds += want
        row.analysis_ping_at = now
        row.save(update_fields=["analysis_seconds", "analysis_ping_at", "updated_at"])
    return want


def snapshot_totals(profile_ids) -> dict:
    """{app_user.id: 누적 XP 사본} — 살!말? 댓글 작성자 레벨용."""
    ids = [i for i in set(profile_ids) if i]
    if not ids:
        return {}
    return dict(UserXp.objects.filter(user_id__in=ids).values_list("user_id", "total"))
