"""알림을 실제로 만드는 자리 — DB 를 읽고 app.notification 에 남긴다.

문구와 판정 기준은 notifications.py 에 있다. 여기서는 그것을 DB 에 붙인다.

다루는 알림 (2026-09-19):
  PRICE_DROP     찜한 상품 변동 — 급락 · 6개월 최저가 · 급등 · 품절, 하루 한 번 묶어서 (배치)
  VOTE_RESULT    살!말? 투표가 기준 표 수를 넘었을 때 (투표가 들어온 순간)
  WEEKLY_REPORT  주간 트렌드 리포트 — 주 1회 (배치)
  BADGE          뱃지 달성 (활동이 기록된 순간)
  TERM_ADDED     요청한 용어가 사전에 올라갔을 때 (배치)

★ 스타일 단계 변화 · FEEDiT Pick 갱신은 여기 없다.
  단계 판정 규칙과 Pick 의 정의가 아직 확정되지 않았다 — 정해지면 더한다.

★ 알림은 사용자의 동작을 막지 않는다.
  화면 요청 도중에 부르는 함수(check_vote_result · check_badges)는
  예외를 밖으로 내보내지 않는다. 대신 로그에 남긴다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from apps.core.models import (
    Announcement,
    AppUser,
    ChatSession,
    DictionaryTerm,
    Notification,
    NotificationSetting,
    ProductSourceSnapshot,
    TermAlias,
    TermRequest,
    UserEvent,
    UserSavedItem,
    VoteBallot,
)

from . import notifications as rules
from .badges import BADGE_LABELS, badge_states

logger = logging.getLogger(__name__)


def norm_term(value):
    """'스투시 후디' → '스투시후디'. views.py 의 _norm 과 같은 규칙."""
    return "".join(str(value or "").split()).lower()


# ── 설정 ────────────────────────────────────────────────────

def setting_of(profile):
    """설정 행이 없으면 만들지 않는다 — 없으면 전부 켜진 것으로 본다."""
    return NotificationSetting.objects.filter(user=profile).first()


def allowed(profile, kind, setting=None):
    row = setting if setting is not None else setting_of(profile)
    if row is None:
        return True
    if not row.enabled:
        return False
    field = rules.SETTING_FIELD.get(kind)
    return True if field is None else bool(getattr(row, field))


# ── 한 건 만들기 ────────────────────────────────────────────

def notify(profile, kind, dedup_key, title, body="", link="", payload=None, setting=None):
    """알림 한 건. 이미 같은 키가 있거나 꺼 둔 종류면 None 을 돌려준다."""
    if profile is None or not title:
        return None
    if not allowed(profile, kind, setting=setting):
        return None
    row, created = Notification.objects.get_or_create(
        user=profile,
        dedup_key=dedup_key,
        defaults={
            "kind": kind,
            "title": title[:200],
            "body": (body or "")[:500],
            "link": (link or "")[:200],
            "payload": payload or {},
        },
    )
    return row if created else None


# ── ① 찜한 상품 가격 하락 ───────────────────────────────────

def _latest_price(source_ids):
    """판매처 id → (가격, 관측일시). 판매가가 없으면 정가를 쓴다 (price-history 와 같은 규칙)."""
    out = {}
    ids = [i for i in source_ids if i]
    if not ids:
        return out
    rows = (ProductSourceSnapshot.objects.filter(product_source_id__in=ids)
            .order_by("product_source_id", "-observed_at", "-id")
            .distinct("product_source_id")
            .values("product_source_id", "list_price", "sale_price", "observed_at"))
    for r in rows:
        price = r["sale_price"] if r["sale_price"] is not None else r["list_price"]
        if price is not None:
            out[r["product_source_id"]] = (price, r["observed_at"])
    return out


def sync_saved_price(saved_item, product_source_id):
    """찜한 순간의 가격을 기준값으로 박아 둔다.

    이미 기준값이 있으면 건드리지 않는다 — 찜을 유지한 채로 기준이 바뀌면
    '찜한 뒤 얼마나 내렸나' 를 셀 수 없다.
    """
    if saved_item is None or saved_item.saved_price is not None:
        return False
    latest = _latest_price([product_source_id])
    got = latest.get(product_source_id)
    if not got:
        return False
    price, observed_at = got
    saved_item.saved_price = price
    saved_item.saved_price_source_id = product_source_id
    saved_item.saved_price_at = observed_at
    saved_item.save(update_fields=["saved_price", "saved_price_source", "saved_price_at"])
    return True


def _stock_and_low(source_ids, now):
    """판매처 id → {"sold_out_now": bool, "was_sold_out": bool, "low_before": 가격|None}.

    - 품절: 가장 최근 스냅숏이 품절이고 바로 앞 스냅숏은 아니었을 때만 '새로 품절' 로 본다
      (매일 같은 품절을 다시 알리지 않는다).
    - 최저가: 최근 6개월 스냅숏 중 **가장 최근 것을 뺀** 최저 가격. 지금 가격이 이보다 낮으면 새 최저가다.
    """
    out = {}
    ids = [i for i in source_ids if i]
    if not ids:
        return out
    since = now - timedelta(days=rules.LOW_WINDOW_DAYS)
    rows = (ProductSourceSnapshot.objects
            .filter(product_source_id__in=ids, observed_at__gte=since)
            .order_by("product_source_id", "-observed_at", "-id")
            .values("product_source_id", "stock_status", "sale_price", "list_price"))
    seen = {}
    for r in rows:
        sid = r["product_source_id"]
        k = seen.get(sid, 0)
        seen[sid] = k + 1
        row = out.setdefault(sid, {"sold_out_now": False, "was_sold_out": None, "low_before": None})
        price = r["sale_price"] if r["sale_price"] is not None else r["list_price"]
        if k == 0:
            row["sold_out_now"] = rules.is_sold_out(r["stock_status"])
            continue
        if k == 1:
            row["was_sold_out"] = rules.is_sold_out(r["stock_status"])
        if price is not None and (row["low_before"] is None or price < row["low_before"]):
            row["low_before"] = price
    return out


def price_drop_digest(profile, now=None, setting=None):
    """한 사용자의 오늘치 찜 상품 변동 알림 — 급락 · 6개월 최저가 · 급등 · 품절 (FAVORITE-002).

    만들었으면 Notification, 아니면 None. 종류는 예전과 같은 PRICE_DROP 이다
    (알림 설정의 '찜한 상품' 칸 하나로 켜고 끈다).
    """
    now = now or timezone.now()
    items = list(UserSavedItem.objects.filter(
        user=profile, saved_price__isnull=False, saved_price_source__isnull=False,
    ).select_related("saved_price_source", "product"))
    if not items:
        return None
    source_ids = [i.saved_price_source_id for i in items]
    latest = _latest_price(source_ids)
    extra = _stock_and_low(source_ids, now)

    rows, by_key, sold_out, lows = [], {}, [], set()
    for item in items:
        name = (item.saved_price_source.source_name
                or (item.product.canonical_name if item.product_id else ""))
        key = f"src-{item.saved_price_source_id}"
        info = extra.get(item.saved_price_source_id) or {}
        if info.get("sold_out_now") and info.get("was_sold_out") is False:
            sold_out.append({"item_id": key, "name": name})
        got = latest.get(item.saved_price_source_id)
        if not got:
            continue
        current, _observed = got
        # 이미 알린 가격이 있으면 그것과 견준다 — 같은 변동을 며칠 내리 알리지 않는다.
        base = item.notified_price if item.notified_price is not None else item.saved_price
        rows.append({"item_id": key, "name": name, "base": base, "current": current})
        by_key[key] = (item, current)
        low = info.get("low_before")
        if low is not None and current < low:
            lows.add(key)

    drops = rules.price_drops(rows)
    rises = rules.price_rises(rows)
    title, body = rules.saved_change_digest(drops, rises, sold_out, lows)
    if not title:
        return None
    day = rules.kst_day(now).isoformat()
    payload_items = [{"name": d["name"], "percent": d["percent"], "change": "drop",
                      "low": d["item_id"] in lows,
                      "source_id": int(d["item_id"].split("-")[1]),
                      "base": float(d["base"]), "current": float(d["current"])} for d in drops]
    payload_items += [{"name": r["name"], "percent": r["percent"], "change": "rise",
                       "source_id": int(r["item_id"].split("-")[1]),
                       "base": float(r["base"]), "current": float(r["current"])} for r in rises]
    payload_items += [{"name": s["name"], "change": "sold_out",
                       "source_id": int(s["item_id"].split("-")[1])} for s in sold_out]
    row = notify(
        profile, rules.PRICE_DROP, f"PRICE_DROP:{day}", title, body,
        link="mypage",
        payload={"items": payload_items},
        setting=setting,
    )
    if row is None:
        # 꺼 두었거나 오늘 이미 보냈다 — 기준값은 손대지 않는다.
        return None
    for d in list(drops) + list(rises):
        item, current = by_key[d["item_id"]]
        item.notified_price = current
        item.notified_at = now
        item.save(update_fields=["notified_price", "notified_at"])
    return row


def run_price_drops(now=None):
    """배치 — 찜 기준가가 있는 사용자 전부. 만든 알림 수를 돌려준다."""
    now = now or timezone.now()
    user_ids = (UserSavedItem.objects.filter(saved_price__isnull=False)
                .values_list("user_id", flat=True).distinct())
    made = 0
    for profile in AppUser.objects.filter(id__in=list(user_ids)):
        try:
            if price_drop_digest(profile, now=now) is not None:
                made += 1
        except Exception:
            logger.exception("가격 하락 알림 실패 user=%s", profile.id)
    return made


# ── ② 살!말? 투표 결과 ──────────────────────────────────────

def check_vote_result(card):
    """표가 기준선을 넘었으면 카드 작성자에게 한 번 알린다."""
    if card is None or card.user_id is None:
        return None
    try:
        total = VoteBallot.objects.filter(card_id=card.id).count()
        milestone = rules.vote_milestone(total)
        if milestone is None:
            return None
        buys = VoteBallot.objects.filter(card_id=card.id, choice=VoteBallot.Choice.BUY).count()
        title, body = rules.vote_result_text(total, buys, card.title or "")
        return notify(
            card.user, rules.VOTE_RESULT, f"VOTE_RESULT:{card.id}:{milestone}",
            title, body, link="salmal",
            payload={"card_id": card.id, "total": total, "buy": buys, "milestone": milestone},
        )
    except Exception:
        logger.exception("투표 결과 알림 실패 card=%s", getattr(card, "id", None))
        return None


def notify_vote_closed(cards):
    """투표가 마감된 내 카드 — 작성자에게 '결과를 알려 주세요'(사후 피드백)를 한 번 알린다.

    종류는 VOTE_RESULT 설정을 따른다(투표 결과 알림을 끈 사람에게는 보내지 않는다).
    링크 'salmal' 로 들어가면 살말 화면이 피드백 팝업을 띄운다 (salmal/static/js/feedback.js).
    """
    made = 0
    for card in cards:
        if card is None or card.user_id is None or not str(card.seed_key or "").startswith("user:"):
            continue
        try:
            total = VoteBallot.objects.filter(card_id=card.id).count()
            buys = VoteBallot.objects.filter(card_id=card.id, choice=VoteBallot.Choice.BUY).count()
            body = (f"{total}명 중 {buys}명이 '살!'을 골랐어요.\n구매하셨다면 후기를 들려주세요."
                    if total else "구매하셨다면 후기를 들려주세요.")
            if notify(card.user, rules.VOTE_RESULT, f"VOTE_CLOSED:{card.id}",
                      f"'{(card.title or '내 카드')[:40]}' 투표가 마감됐어요.", body, link="salmal",
                      payload={"card_id": card.id, "total": total, "buy": buys, "closed": True}):
                made += 1
        except Exception:
            logger.exception("마감 알림 실패 card=%s", getattr(card, "id", None))
    return made


def notify_vote_comment(card, comment, author):
    """내 살말 카드에 남이 댓글을 달면 카드 작성자에게 알린다. 댓글 하나당 한 번."""
    try:
        if card is None or comment is None or card.user_id is None:
            return None
        if author is not None and card.user_id == author.id:
            return None
        nickname = getattr(author, "nickname", "") or ""
        title, body = rules.vote_comment_text(nickname, card.title, comment.content, comment.choice)
        return notify(card.user, rules.VOTE_COMMENT, f"VOTE_COMMENT:{comment.id}",
                      title, body, link="salmal",
                      payload={"card_id": card.id, "comment_id": comment.id})
    except Exception:
        logger.exception("댓글 알림 실패 comment=%s", getattr(comment, "id", None))
        return None


def notify_job_review(profile, job, approved, reason="", requested_at=""):
    """직업 인증 승인·반려를 신청자에게 알린다. 같은 신청(신청 시각)에는 한 번만."""
    try:
        title, body = rules.job_review_text(job, approved, reason)
        return notify(profile, rules.JOB_REVIEW,
                      f"JOB_REVIEW:{profile.id}:{requested_at or job}",
                      title, body, link="mypage",
                      payload={"job": job, "approved": bool(approved), "reason": reason or ""})
    except Exception:
        logger.exception("직업 인증 알림 실패 user=%s", getattr(profile, "id", None))
        return None


def notify_plan_review(profile, plan, status, reason="", key_at=""):
    """요금제 신청 승인 · 반려, 운영자의 해지(REVOKED)를 신청자에게 알린다. 같은 건에는 한 번만."""
    try:
        title, body = rules.plan_review_text(plan, status, reason)
        return notify(profile, rules.PLAN_REVIEW,
                      f"PLAN_REVIEW:{profile.id}:{status}:{key_at or plan}",
                      title, body, link="price",
                      payload={"plan": plan, "status": status, "reason": reason or ""})
    except Exception:
        logger.exception("요금제 결과 알림 실패 user=%s", getattr(profile, "id", None))
        return None


def pending_plan_requests():
    """심사 대기 중인 요금제 신청 — [(AppUser, 신청 dict)] 신청 시각 오래된 순."""
    rows = []
    for p in AppUser.objects.filter(profile_metadata__has_key="plan_request").select_related("user"):
        req = (p.profile_metadata or {}).get("plan_request")
        if isinstance(req, dict) and req.get("status") == "PENDING":
            rows.append((p, req))
    rows.sort(key=lambda r: str(r[1].get("requested_at") or ""))
    return rows


def notify_admin_plan_pending(admin_profile):
    """운영(ADMIN) 계정 — 요금제 신청 대기가 있으면 'N건 대기' 알림을 한 번 띄운다.

    직업 인증 대기(notify_admin_job_pending)와 같은 방식 — 새 신청이 들어올 때마다 한 건씩만 생긴다.
    """
    try:
        rows = pending_plan_requests()
        if not rows:
            return None
        who, req = rows[-1]
        n = len(rows)
        name = who.nickname or who.user.username
        label = rules.PLAN_LABEL.get(str(req.get("plan") or "").upper(), req.get("plan") or "-")
        body = f"새 신청: {name} · {label}" + (f"\n그 밖에 {n - 1}건이 더 기다리고 있어요." if n > 1 else "")
        return notify(admin_profile, rules.PLAN_REVIEW,
                      f"PLAN_PENDING:{req.get('requested_at') or who.id}",
                      f"요금제 신청 대기 {n}건", body, link="price",
                      payload={"admin_pending": n})
    except Exception:
        logger.exception("요금제 신청 대기 알림 실패 admin=%s", getattr(admin_profile, "id", None))
        return None


def pending_job_requests():
    """심사 대기 중인 직업 인증 신청 — [(AppUser, 신청 dict)] 신청 시각 오래된 순."""
    rows = []
    for p in AppUser.objects.filter(profile_metadata__has_key="job_request").select_related("user"):
        req = (p.profile_metadata or {}).get("job_request")
        if isinstance(req, dict) and req.get("status") == "PENDING":
            rows.append((p, req))
    rows.sort(key=lambda r: str(r[1].get("requested_at") or ""))
    return rows


def notify_admin_job_pending(admin_profile):
    """운영(ADMIN) 계정 — 직업 인증 심사 대기가 있으면 'N건 대기' 알림을 한 번 띄운다.

    ★ 2026-09-19. 알림 목록을 받을 때(30초 폴링) 부른다.
      키를 '가장 최근 신청 시각'으로 잡아서, 새 신청이 들어올 때마다 한 건씩만 새로 생긴다
      (같은 대기 목록으로는 다시 만들지 않는다).
    """
    try:
        rows = pending_job_requests()
        if not rows:
            return None
        who, req = rows[-1]
        n = len(rows)
        name = who.nickname or who.user.username
        body = f"새 신청: {name} · {req.get('job') or '-'}" + (f"\n그 밖에 {n - 1}건이 더 기다리고 있어요." if n > 1 else "")
        return notify(admin_profile, rules.JOB_REVIEW,
                      f"JOB_PENDING:{req.get('requested_at') or who.id}",
                      f"직업 인증 심사 대기 {n}건", body, link="mypage",
                      payload={"admin_pending": n})
    except Exception:
        logger.exception("심사 대기 알림 실패 admin=%s", getattr(admin_profile, "id", None))
        return None


# ── ③ 뱃지 달성 ────────────────────────────────────────────

def check_badges(profile, now=None):
    """오늘 달성한 뱃지만 알린다.

    ★ '오늘' 로 자르는 이유 — 예전에 딴 뱃지까지 한꺼번에 알리면
      알림을 처음 켠 사람의 알림창이 옛날 뱃지로 가득 찬다.
    """
    if profile is None:
        return []
    now = now or timezone.now()
    today = rules.kst_day(now).strftime("%Y.%m.%d")
    made = []
    try:
        for badge_id, state in badge_states(profile).items():
            if not state.get("earned") or state.get("date") != today:
                continue
            label = BADGE_LABELS.get(badge_id, badge_id)
            title, body = rules.badge_text(label)
            row = notify(profile, rules.BADGE, f"BADGE:{badge_id}", title, body,
                         link="mypage", payload={"badge_id": badge_id, "label": label})
            if row is not None:
                made.append(row)
    except Exception:
        logger.exception("뱃지 알림 실패 user=%s", getattr(profile, "id", None))
    return made


# ── ④ 주간 트렌드 리포트 ───────────────────────────────────

def run_weekly_reports(now=None):
    """배치 — 지난 한 주에 활동이 있었던 사용자에게 주 1회.

    활동이 없으면 보내지 않는다. 빈 리포트를 알리는 것은 소음이다.
    리포트 내용은 화면이 /api/auth/weekly-report 로 그때 받아 그린다.
    """
    now = now or timezone.now()
    day = rules.kst_day(now)
    week_start = day - timedelta(days=day.weekday())
    since = now - timedelta(days=7)
    active = set(UserEvent.objects.filter(created_at__gte=since)
                 .values_list("user_id", flat=True).distinct())
    active |= set(ChatSession.objects.filter(updated_at__gte=since)
                  .values_list("user_id", flat=True).distinct())
    if not active:
        return 0
    title, body = rules.weekly_report_text(week_start)
    made = 0
    for profile in AppUser.objects.filter(id__in=list(active)):
        try:
            row = notify(profile, rules.WEEKLY_REPORT,
                         f"WEEKLY_REPORT:{week_start.isoformat()}", title, body,
                         link="trend",
                         payload={"week_start": week_start.isoformat()})
            if row is not None:
                made += 1
        except Exception:
            logger.exception("주간 리포트 알림 실패 user=%s", profile.id)
    return made


# ── ⑤ 용어 사전 등재 ───────────────────────────────────────

def find_active_term(raw_term, normalized):
    """표준명 › 정규화명 › 별칭 순으로 ACTIVE 용어를 찾는다 (views._resolve_term 과 같은 순서)."""
    base = DictionaryTerm.objects.filter(status=DictionaryTerm.Status.ACTIVE)
    term = base.filter(canonical_name=raw_term).first()
    if term:
        return term
    term = base.filter(normalized_name=normalized).first()
    if term:
        return term
    alias_id = (TermAlias.objects.filter(Q(alias=raw_term) | Q(normalized_alias=normalized))
                .values_list("term_id", flat=True).first())
    return base.filter(id=alias_id).first() if alias_id else None


def run_term_added(now=None):
    """배치 — 검토 대기 중인 요청 중 사전에 오른 것을 찾아 알린다."""
    now = now or timezone.now()
    made = 0
    pending = (TermRequest.objects.filter(status=TermRequest.Status.PENDING)
               .select_related("user"))
    for req in pending:
        try:
            term = find_active_term(req.raw_term, req.normalized_term)
            if term is None:
                continue
            with transaction.atomic():
                req.status = TermRequest.Status.ADDED
                req.term = term
                req.resolved_at = now
                req.save(update_fields=["status", "term", "resolved_at", "updated_at"])
                title, body = rules.term_added_text(req.raw_term, term.canonical_name)
                row = notify(req.user, rules.TERM_ADDED, f"TERM_ADDED:{req.id}", title, body,
                             link="trend",
                             payload={"term_request_id": req.id, "term_id": term.id,
                                      "canonical_name": term.canonical_name})
            if row is not None:
                made += 1
        except Exception:
            logger.exception("용어 등재 알림 실패 request=%s", req.id)
    return made


# ── 배치 묶음 ──────────────────────────────────────────────

def run_daily(now=None):
    now = now or timezone.now()
    return {"price_drop": run_price_drops(now), "term_added": run_term_added(now)}


def run_weekly(now=None):
    now = now or timezone.now()
    return {"weekly_report": run_weekly_reports(now)}


# ── ⑥ 성별 요청 (2026-10-02) ───────────────────────────────
#   가입에서 성별을 받기 시작한 것(2026-10-01) 이전의 회원 · 알파 계정은 성별이 비어 있다.
#   가상 피팅 기본 모델 · 코디 추천이 성별을 쓰므로 한 번 묻는다. 알림 목록을 열 때(30초
#   폴링) 확인한다 — 배치를 따로 돌리지 않아도 새로 들어온 빈 계정까지 빠짐없이 받는다.
#   ★ 같은 키로 한 번만 만든다. 사용자가 지웠으면 다시 만들지 않는다(행이 남는다).

GENDER_CHECK_TTL = 60 * 60     # 한 사람당 한 시간에 한 번만 DB 를 본다 (폴링 30초마다라)


def ensure_gender_prompt(profile):
    if profile is None or getattr(profile, "gender", None):
        return None
    key = f"noti:gender-prompt:{profile.pk}"
    if not cache.add(key, 1, GENDER_CHECK_TTL):
        return None
    title, body = rules.gender_prompt_text()
    try:
        return notify(profile, rules.PROFILE_GENDER, rules.PROFILE_GENDER_KEY, title, body,
                      link="", payload={"action": "gender"})
    except Exception:
        logger.exception("성별 요청 알림 실패 user=%s", profile.pk)
        return None


def clear_gender_prompt(profile):
    """성별을 정하면 그 알림은 할 일이 끝났다 — 읽음 처리하고 목록에서 내린다."""
    if profile is None:
        return 0
    now = timezone.now()
    return (Notification.objects
            .filter(user=profile, dedup_key=rules.PROFILE_GENDER_KEY, deleted_at__isnull=True)
            .update(read_at=now, deleted_at=now))


# ── ⑦ 운영 공지 (관리자 화면에서 보냄, 2026-10-02) ──────────────

def notice_targets(target, ids=None, names=None):
    """보낼 대상 → (AppUser QuerySet, 찾지 못한 이름 목록).

    target: all(전체) · no_gender(성별 미입력) · pick(번호 · 닉네임으로 고름)
    탈퇴 · 비활성 계정에는 보내지 않는다.
    """
    qs = AppUser.objects.filter(user__is_active=True)
    missing = []
    if target == "all":
        return qs, missing
    if target == "no_gender":
        return qs.filter(Q(gender__isnull=True) | Q(gender="")), missing
    if target == "pick":
        ids, names = list(ids or []), list(names or [])
        by_name = {p.nickname: p.pk for p in qs.filter(nickname__in=names)} if names else {}
        missing = [n for n in names if n not in by_name]
        found_ids = set(qs.filter(pk__in=ids).values_list("pk", flat=True)) if ids else set()
        missing += [str(i) for i in ids if i not in found_ids]
        return qs.filter(pk__in=found_ids | set(by_name.values())), missing
    raise ValueError("보낼 대상을 골라 주세요.")


def send_admin_notice(profiles, title, body="", link="", by=""):
    """운영 공지를 한 번에 만든다. → {"batch", "sent", "skipped"}

    · 같은 발송은 같은 키(ADMIN_NOTICE:<batch>)라 두 번 눌러도 한 사람에게 한 건이다
    · '알림 전체 끄기' 를 한 사람은 건너뛴다 (allowed() 와 같은 규칙)
    · 500 명씩 끊어 넣는다 — 한 번에 수만 행을 메모리에 들지 않는다
    """
    title, body, link = rules.clean_notice(title, body, link)
    batch = uuid.uuid4().hex[:12]
    key = f"{rules.ADMIN_NOTICE}:{batch}"
    muted = set(NotificationSetting.objects.filter(enabled=False).values_list("user_id", flat=True))
    sent = skipped = 0
    chunk = []
    payload = {"batch": batch, "by": str(by or "")[:60]}

    def flush():
        nonlocal sent
        if chunk:
            Notification.objects.bulk_create(chunk, ignore_conflicts=True)
            sent += len(chunk)
            chunk.clear()

    for pk in profiles.values_list("pk", flat=True).iterator(chunk_size=500):
        if pk in muted:
            skipped += 1
            continue
        chunk.append(Notification(user_id=pk, kind=rules.ADMIN_NOTICE, dedup_key=key,
                                  title=title, body=body, link=link, payload=payload))
        if len(chunk) >= 500:
            flush()
    flush()
    logger.info("운영 공지 발송 batch=%s sent=%s skipped=%s by=%s", batch, sent, skipped, by)
    return {"batch": batch, "sent": sent, "skipped": skipped}


def admin_notice_history(limit=20):
    """보낸 공지 묶음 — 최근 순. 읽은 사람 수를 같이 센다."""
    rows = (Notification.objects.filter(kind=rules.ADMIN_NOTICE)
            .values("dedup_key")
            .annotate(sent=Count("id"), read=Count("read_at"), at=Min("created_at"),
                      title=Max("title"), body=Max("body"), link=Max("link"))
            .order_by("-at")[:limit])
    return [{**r, "batch": r["dedup_key"].split(":", 1)[-1]} for r in rows]


# ── ⑧ 상단 띠 공지 (2026-10-02) ──────────────────────────────

TICKER_CACHE_KEY = "noti:ticker:live"
TICKER_CACHE_TTL = 15          # 초. 방문자 모두가 30초마다 묻는다 — DB 는 15초에 한 번만


def live_announcements(now=None, use_cache=True):
    """지금 걸려 있는 공지 — 최근 것 먼저, 최대 3개."""
    if use_cache:
        hit = cache.get(TICKER_CACHE_KEY)
        if hit is not None:
            return hit
    now = now or timezone.now()
    rows = (Announcement.objects.filter(active=True, starts_at__lte=now)
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
            .order_by("-starts_at", "-id")[:3])
    out = [{"id": a.id, "message": a.message, "link": a.link,
            "starts_at": a.starts_at.isoformat(),
            "ends_at": a.ends_at.isoformat() if a.ends_at else None} for a in rows]
    cache.set(TICKER_CACHE_KEY, out, TICKER_CACHE_TTL)
    return out


def forget_live_announcements():
    """관리자가 올리거나 내리면 바로 반영되게 (같은 프로세스의 캐시를 비운다)."""
    cache.delete(TICKER_CACHE_KEY)
