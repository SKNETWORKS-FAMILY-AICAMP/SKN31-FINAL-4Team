"""운영 알림 — 수집 실패 · 장기 미갱신을 담당자에게 알린다 (2026-09-27).

요구사항 COLLECT-001(실패 시 담당자 알림) · OPERATIONS-002(이상 시 메일 알림).

받는 사람
  - 서비스 알림(종 모양): 운영 계정(auth.User.is_staff 또는 is_superuser) 전원 — 앱 오른쪽 위 알림에 뜬다.
  - 메일: 서버 .env 의 OPS_ALERT_EMAILS(쉼표로 여러 개). 비어 있으면 운영 계정에 적힌 메일 주소.
    메일은 settings.MAILERS(EMAIL_HOST) 가 있을 때만 나간다. 없으면 서비스 알림만 남는다.

얼마나 자주
  - 수집 실패: 소스마다 **하루(KST) 한 번**. 같은 날 같은 소스가 또 실패해도 다시 알리지 않는다.
    (1분마다 도는 크롤 배치가 같은 오류로 계속 실패하면 알림이 수백 건 쌓인다)
  - 장기 미갱신: 하루 한 번 배치(core.check_data_freshness)가 확인하고, 그날 한 번만 알린다.

★ 알림은 수집을 막지 않는다. 여기서 나는 예외는 로그로만 남기고 밖으로 내보내지 않는다.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

KST = dt_timezone(timedelta(hours=9))
OPS_ALERT = "OPS_ALERT"


def kst_day(at=None):
    return (at or timezone.now()).astimezone(KST).date()


def _staff_profiles():
    from django.db.models import Q
    from apps.core.models import AppUser
    # 앱의 ADMIN 판정(auth_views: is_staff 또는 is_superuser)과 같게 본다
    return list(AppUser.objects.filter(Q(user__is_staff=True) | Q(user__is_superuser=True), user__is_active=True)
                .select_related("user"))


def alert_emails():
    raw = os.getenv("OPS_ALERT_EMAILS", "")
    listed = [e.strip() for e in raw.split(",") if e.strip()]
    if listed:
        return listed
    User = get_user_model()
    from django.db.models import Q
    return sorted({e for e in User.objects.filter(Q(is_staff=True) | Q(is_superuser=True), is_active=True)
                   .exclude(email="").values_list("email", flat=True) if e})


def mail_configured():
    """콘솔 백엔드(EMAIL_HOST 없음)는 보낸 것으로 치지 않는다 — 운영에서 조용히 사라지면 안 된다."""
    backend = (getattr(settings, "MAILERS", {}) or {}).get("default", {}).get("BACKEND", "")
    return bool(backend) and "console" not in backend


def send_ops_alert(dedup_key, title, body="", payload=None):
    """운영 알림 한 건. 이미 같은 키로 보냈으면 아무것도 하지 않는다.

    돌려주는 값: {"notified": 새로 만든 서비스 알림 수, "mailed": 메일 받은 주소 수}
    """
    from apps.core.models import Notification

    made = 0
    profiles = _staff_profiles()
    for profile in profiles:
        # notification_service.notify 와 같지만 사용자 알림 설정은 보지 않는다 —
        # 운영 알림은 끌 수 없다(알림을 전부 꺼 둔 운영 계정도 수집 실패는 받아야 한다).
        try:
            _row, created = Notification.objects.get_or_create(
                user=profile, dedup_key=dedup_key,
                defaults={"kind": OPS_ALERT, "title": title[:200], "body": (body or "")[:500],
                          "link": "", "payload": payload or {}},
            )
            made += int(created)
        except Exception:
            logger.exception("운영 알림 저장 실패 user=%s key=%s", profile.id, dedup_key)

    # 메일은 '처음 알린 때' 한 번만 — 같은 키의 서비스 알림이 이미 있으면 보낸 것으로 본다.
    # 운영 계정이 하나도 없으면 중복을 기억할 곳이 없으므로, 부르는 쪽이 하루 한 번만 부른다.
    mailed = 0
    if (made or not profiles) and mail_configured():
        to = alert_emails()
        if to:
            try:
                send_mail(f"[FEEDiT 운영] {title}", body or title, None, to, fail_silently=False)
                mailed = len(to)
            except Exception:
                logger.exception("운영 알림 메일 실패 key=%s", dedup_key)
    return {"notified": made, "mailed": mailed}


# ── 수집 실패 ─────────────────────────────────────────────────


def _source_label(source):
    try:
        from apps.dashboard.services.dashboard_service import _label
        return _label(source)
    except Exception:
        return getattr(source, "name", "") or getattr(source, "code", "")


def alert_crawl_failed(crawl_run):
    """수집 실행이 FAILED 로 끝났을 때 부른다. 소스마다 하루 한 번만 알린다."""
    try:
        from apps.core.models import CrawlRun

        source = crawl_run.source
        day = kst_day(crawl_run.finished_at or crawl_run.started_at)
        start = datetime(day.year, day.month, day.day, tzinfo=KST)
        failed_today = CrawlRun.objects.filter(
            source=source, status=CrawlRun.Status.FAILED, finished_at__gte=start,
        ).count()
        target = (crawl_run.crawl_target.name if crawl_run.crawl_target_id and crawl_run.crawl_target
                  else (crawl_run.target or "-"))
        name = _source_label(source)
        body = "\n".join([
            f"대상: {target}",
            f"오류: {crawl_run.error_code or '-'} — {(crawl_run.error_message or '메시지 없음')[:300]}",
            f"오늘 이 소스의 실패 {failed_today}건 · 실행 #{crawl_run.id}",
            "운영 대시보드 › Collection Runs 에서 실패 실행을 확인하세요.",
        ])
        return send_ops_alert(
            f"CRAWL_FAILED:{source.code}:{day.isoformat()}",
            f"수집 실패 · {name}",
            body,
            payload={"source": source.code, "crawl_run_id": crawl_run.id, "failed_today": failed_today},
        )
    except Exception:
        logger.exception("수집 실패 알림 실패 run=%s", getattr(crawl_run, "id", None))
        return None


# ── 장기 미갱신 ───────────────────────────────────────────────


def check_freshness_and_alert(now=None):
    """지연 · 기록 없음인 소스가 있으면 그날 한 번 알린다. 없으면 아무것도 하지 않는다."""
    from apps.dashboard.services.dashboard_service import source_freshness, stale_alerts

    now = now or timezone.now()
    fresh = source_freshness(now)
    alerts = stale_alerts(fresh, now)
    if not alerts:
        return {"stale": 0, "notified": 0, "mailed": 0}
    stale = sum(1 for f in fresh.values() if f["state"] in ("late", "never"))
    title = " · ".join(a["title"] for a in alerts)
    body = "\n".join(a["detail"] for a in alerts) + "\n운영 대시보드 › Collection › Platform Status 에서 확인하세요."
    sent = send_ops_alert(f"STALE:{kst_day(now).isoformat()}", title, body, payload={"stale": stale})
    return {"stale": stale, **sent}
