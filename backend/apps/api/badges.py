"""컬렉션 배지 — 실제 활동 기록으로만 계산한다 (2026-09-19).

예전 화면(badges.js)은 획득일·진행도가 전부 하드코딩된 목업이었다.
여기서는 이미 쌓이는 기록으로 셀 수 있는 것만 계산하고,
기록이 없는 배지(사후 만족도 피드백 · 만족도 적중 · 공유 등)는 잠금 + '기록 없음' 으로 둔다.

  b01      스타일 입문자     즐겨입는 스타일을 1개 이상 고름 (user_taste STYLE)
  b02      첫 살말           첫 투표 (vote_ballot)
  b06~b08  살말 백전 N       투표 수 (vote_ballot)
  b12~b14  개근상 N          연속 활동일 — 투표·댓글·카드·찜·검색·챗봇 중 하나라도 한 날 (KST)
  b09~b11  성실 피드백러 N   내 카드에 남긴 사후 피드백 수 (vote_feedback)
  b15~b17  연속 적중 N       내 살/말 투표가 글쓴이의 실제 결과와 연속으로 맞은 횟수
  b03~b05  여론 조력자 N     글쓴이가 '투표가 도움이 됐다'고 했고, 최종 결정이 내 투표와 같은 카드 수
  (적중 판정: 샀고 만족 4~5 · 안 샀고 후회 1~2 → '살'이 정답 / 샀고 불만 1~2 · 안 샀고 만족 4~5 → '말'이 정답.
   만족 3 · 아직 고민 중은 판정하지 않는다.
   ★ 2026-09-19 만족도 입력을 뺐다 — 만족도가 없으면 샀으면 '살', 안 샀으면 '말'이 정답.)
그 외(카테고리 안목러 · 결산 공유러)는 계산 근거가 없어 잠금.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.core.models import UserEvent, UserTaste, VoteBallot, VoteCard, VoteComment, VoteFeedback

NO_RECORD = "기록 없음"

# 뱃지 이름 — 알림 문구("뱃지 '살말 백전 100'을 달성했어요")에 쓴다.
# 화면 목록(frontend/account/static/js/badges.js 의 BADGES)의 n·tier 와 같은 글자다.
# 한쪽만 고치면 화면과 알림이 다른 이름을 부른다.
BADGE_LABELS = {
    "b01": "스타일 입문자", "b02": "첫 살말",
    "b03": "여론 조력자 1", "b04": "여론 조력자 10", "b05": "여론 조력자 50",
    "b06": "살말 백전 100", "b07": "살말 백전 500", "b08": "살말 백전 1000",
    "b09": "성실 피드백러 10", "b10": "성실 피드백러 50", "b11": "성실 피드백러 100",
    "b12": "개근상 7", "b13": "개근상 30", "b14": "개근상 100",
    "b15": "연속 적중 5", "b16": "연속 적중 10", "b17": "연속 적중 20",
    "b18": "카테고리 안목러", "b19": "결산 공유러",
}


def _day(dt):
    return timezone.localtime(dt).date()


def _fmt(d):
    return d.strftime("%Y.%m.%d") if d else None


def _streak_reach(days, n):
    """정렬된 날짜들에서 연속 n일을 처음 채운 날 · 지금까지 최장 연속 · 오늘 기준 현재 연속."""
    best, run, reached, prev = 0, 0, None, None
    for d in days:
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        prev = d
        best = max(best, run)
        if reached is None and run >= n:
            reached = d
    return reached, best


def correct_choice(fb):
    """글쓴이의 실제 결과로 본 '정답' 투표 — BUY · PASS · None(판정 안 함)."""
    s = fb.satisfaction
    if fb.purchase == VoteFeedback.Purchase.UNDECIDED:
        return None
    # ★ 2026-09-19 — 피드백 창에서 만족도(1~5)를 뺐다. 만족도가 없으면 실제로 한 선택이 정답이다
    #   (샀으면 '살', 안 샀으면 '말'). 예전에 만족도까지 남긴 기록은 아래 규칙 그대로 판정한다.
    if s is None:
        return {"BOUGHT": "BUY", "SKIPPED": "PASS"}.get(fb.purchase)
    if s == 3:
        return None
    if fb.purchase == VoteFeedback.Purchase.BOUGHT:
        return "BUY" if s >= 4 else "PASS"
    if fb.purchase == VoteFeedback.Purchase.SKIPPED:
        return "PASS" if s >= 4 else "BUY"
    return None


def badge_states(profile):
    """{badge_id: {"earned": bool, "date": "YYYY.MM.DD"|None, "progress": str|None}}"""
    if profile is None:
        return {}
    out = {}

    taste = (UserTaste.objects.filter(user=profile, taste_type=UserTaste.TasteType.TERM,
                                      term__term_type="STYLE")
             .order_by("created_at").values_list("created_at", flat=True).first())
    out["b01"] = {"earned": bool(taste), "date": _fmt(_day(taste)) if taste else None,
                  "progress": None if taste else "스타일 선택 전"}

    ballots = list(VoteBallot.objects.filter(user=profile).order_by("created_at")
                   .values_list("created_at", flat=True))
    out["b02"] = {"earned": bool(ballots), "date": _fmt(_day(ballots[0])) if ballots else None,
                  "progress": None if ballots else "0/1"}
    for bid, n in (("b06", 100), ("b07", 500), ("b08", 1000)):
        got = len(ballots) >= n
        out[bid] = {"earned": got, "date": _fmt(_day(ballots[n - 1])) if got else None,
                    "progress": None if got else f"{len(ballots):,}/{n:,}"}

    days = {_day(t) for t in ballots}
    days |= {_day(t) for t in UserEvent.objects.filter(user=profile).values_list("created_at", flat=True)}
    days |= {_day(t) for t in VoteComment.objects.filter(user=profile).values_list("created_at", flat=True)}
    days |= {_day(t) for t in VoteCard.objects.filter(user=profile).values_list("created_at", flat=True)}
    days = sorted(days)
    for bid, n in (("b12", 7), ("b13", 30), ("b14", 100)):
        reached, best = _streak_reach(days, n)
        out[bid] = {"earned": reached is not None, "date": _fmt(reached),
                    "progress": None if reached else f"{best}/{n}"}

    # ── 사후 피드백 기반 ─────────────────────────────────
    fbs = list(VoteFeedback.objects.filter(user=profile).order_by("created_at")
               .values_list("created_at", flat=True))
    for bid, n in (("b09", 10), ("b10", 50), ("b11", 100)):
        got = len(fbs) >= n
        out[bid] = {"earned": got, "date": _fmt(_day(fbs[n - 1])) if got else None,
                    "progress": None if got else f"{len(fbs)}/{n}"}

    judged = (VoteBallot.objects.filter(user=profile, card__feedback__isnull=False)
              .exclude(card__user=profile)
              .select_related("card__feedback").order_by("card__feedback__created_at"))
    streak, best, reach, helped = 0, 0, {}, []
    for b in judged:
        fb = b.card.feedback
        answer = correct_choice(fb)
        if answer is None:
            continue
        if b.choice == answer:
            streak += 1
            for n in (5, 10, 20):
                if streak >= n and n not in reach:
                    reach[n] = fb.created_at
        else:
            streak = 0
        best = max(best, streak)
        decided = {"BOUGHT": "BUY", "SKIPPED": "PASS"}.get(fb.purchase)
        if fb.helpful and decided and b.choice == decided:
            helped.append(fb.created_at)
    for bid, n in (("b15", 5), ("b16", 10), ("b17", 20)):
        got = n in reach
        out[bid] = {"earned": got, "date": _fmt(_day(reach[n])) if got else None,
                    "progress": None if got else f"{best}/{n}"}
    for bid, n in (("b03", 1), ("b04", 10), ("b05", 50)):
        got = len(helped) >= n
        out[bid] = {"earned": got, "date": _fmt(_day(helped[n - 1])) if got else None,
                    "progress": None if got else f"{len(helped)}/{n}"}

    for bid in ("b18", "b19"):
        out[bid] = {"earned": False, "date": None, "progress": NO_RECORD}
    return out
