"""관리자 대시보드 메인 화면 데이터.

이전에는 하드코딩된 예시 값이었으나, 실제 테이블을 조회하도록 바꿨다.
"""

from datetime import timedelta

from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from apps.core.models import (
    ContentItem,
    CrawlRun,
    CrawlTarget,
    DictionaryTerm,
    ProductSource,
    RawDocument,
    Source,
    TermCandidate,
    TermMetricDaily,
    TextDocument,
)


SOURCE_LABELS = {
    "musinsa": "무신사",
    "musinsa_used": "무신사 USED",
    "zigzag": "지그재그",
    "ably": "에이블리",
    "kream": "크림",
    "YOUTUBE": "유튜브",
    "youtube": "유튜브",
    "naver": "네이버",
}

SOURCE_ORDER = [
    "musinsa", "zigzag", "ably", "musinsa_used", "kream", "YOUTUBE", "naver",
]


def _label(source):
    return SOURCE_LABELS.get(source.code, source.name or source.code)


# ── 장기 미갱신 경고 (2026-09-27, DATA_STATUS-003) ──────────────
#
# 소스마다 '마지막으로 정상 수집한 때' 를 보고, 기대 주기의 2배가 지나도록 새로
# 받지 못했으면 지연으로 본다. 기대 주기는 그 소스의 **활성 LIVE 타깃 중 가장 짧은 주기**,
# 타깃이 없으면 Source.crawl_interval_minutes, 그것도 없으면 하루다.
# 활성 타깃이 하나도 없는 소스는 일부러 멈춘 것이므로 경고하지 않는다('수집 안 함').
STALE_FACTOR = 2
DEFAULT_INTERVAL_MINUTES = 1440
OK_RUN_STATUSES = ("SUCCESS", "PARTIAL_SUCCESS")


def source_freshness(now=None):
    """소스 id → 신선도 한 줄.

    state: ok(기준 안) · late(기준 초과) · never(활성 타깃이 있는데 성공 기록이 없음) · idle(활성 타깃 없음)
    """
    now = now or timezone.now()
    # finished_at 이 비어 있는 옛 기록은 시작 시각으로 대신한다
    last_ok = {
        r["source_id"]: r["fin"] or r["st"]
        for r in CrawlRun.objects.filter(status__in=OK_RUN_STATUSES)
        .values("source_id").annotate(fin=Max("finished_at"), st=Max("started_at"))
    }
    last_doc = dict(
        RawDocument.objects.values("source_id").annotate(at=Max("collected_at"))
        .values_list("source_id", "at")
    )
    live = dict(
        CrawlTarget.objects.filter(is_active=True, collection_mode="LIVE")
        .values("source_id").annotate(m=Min("interval_minutes"))
        .values_list("source_id", "m")
    )
    active = set(
        CrawlTarget.objects.filter(is_active=True).values_list("source_id", flat=True)
    )

    out = {}
    for source in Source.objects.all():
        interval = (live.get(source.id) or source.crawl_interval_minutes
                    or DEFAULT_INTERVAL_MINUTES)
        limit = timedelta(minutes=interval * STALE_FACTOR)
        at = last_ok.get(source.id)
        age = (now - at) if at else None
        if source.id not in active:
            state = "idle"
        elif at is None:
            state = "never"
        elif age > limit:
            state = "late"
        else:
            state = "ok"
        out[source.id] = {
            "state": state,
            "last_success_at": at,
            "last_doc_at": last_doc.get(source.id),
            "age_hours": round(age.total_seconds() / 3600, 1) if age is not None else None,
            "interval_minutes": interval,
            "limit_hours": round(limit.total_seconds() / 3600, 1),
        }
    return out


def stale_alerts(freshness=None, now=None):
    """대시보드 '점검이 필요한 항목' 에 붙일 경고 — 지연 · 기록 없음만."""
    freshness = freshness if freshness is not None else source_freshness(now)
    names = {s.id: _label(s) for s in Source.objects.filter(id__in=freshness)}
    late = [(sid, f) for sid, f in freshness.items() if f["state"] == "late"]
    never = [sid for sid, f in freshness.items() if f["state"] == "never"]
    alerts = []
    if late:
        late.sort(key=lambda x: -(x[1]["age_hours"] or 0))
        parts = [f"{names.get(sid, sid)} {f['age_hours']:g}시간 전(기준 {f['limit_hours']:g}시간)"
                 for sid, f in late]
        alerts.append({
            "level": "danger",
            "title": f"장기 미갱신 {len(late)}곳",
            "detail": "마지막 정상 수집: " + " · ".join(parts),
        })
    if never:
        alerts.append({
            "level": "warning",
            "title": f"정상 수집 기록 없음 {len(never)}곳",
            "detail": "활성 타깃이 있는데 성공한 실행이 없습니다: "
                      + " · ".join(str(names.get(sid, sid)) for sid in never),
        })
    return alerts


def _percent(part, whole):
    if not whole:
        return None
    return round(part / whole * 100, 1)


def get_dashboard_context():
    now = timezone.now()
    today = timezone.localtime(now).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_ago = now - timedelta(days=7)

    runs = CrawlRun.objects.all()
    docs = RawDocument.objects.all()

    # 실행 지표를 한 번의 쿼리로 집계한다.
    run_agg = runs.aggregate(
        total=Count("id"),
        success=Count("id", filter=Q(status="SUCCESS")),
        failed=Count("id", filter=Q(status="FAILED")),
        running=Count("id", filter=Q(status="RUNNING")),
        today=Count("id", filter=Q(started_at__gte=today)),
        recent_total=Count("id", filter=Q(started_at__gte=week_ago)),
        recent_success=Count(
            "id",
            filter=Q(started_at__gte=week_ago, status="SUCCESS"),
        ),
        stale=Count(
            "id",
            filter=Q(
                status="RUNNING",
                started_at__lt=now - timedelta(hours=1),
            ),
        ),
    )

    # 원본 문서 지표도 한 번에.
    doc_agg = docs.aggregate(
        total=Count("id"),
        today=Count("id", filter=Q(collected_at__gte=today)),
        pending=Count("id", filter=Q(normalization_status="PENDING")),
        failed=Count("id", filter=Q(normalization_status="FAILED")),
    )

    total_runs = run_agg["total"]
    success_runs = run_agg["success"]
    failed_runs = run_agg["failed"]

    # ---------------- 상단 지표 ----------------
    stats = {
        "collected_today": doc_agg["today"],
        "success_rate": _percent(
            run_agg["recent_success"], run_agg["recent_total"]
        ),
        "success_rate_all": _percent(success_runs, total_runs),
        "normalize_pending": doc_agg["pending"],
        "normalize_failed": doc_agg["failed"],
        "term_candidates": TermCandidate.objects.count(),
        "dictionary_terms": DictionaryTerm.objects.count(),
        "raw_total": doc_agg["total"],
        "runs_today": run_agg["today"],
        "failed_runs": failed_runs,
        "running": run_agg["running"],
    }

    # ---------------- 파이프라인 ----------------
    product_sources = ProductSource.objects.count()
    content_items = ContentItem.objects.count()
    text_documents = TextDocument.objects.count()
    metrics = TermMetricDaily.objects.count()

    pipeline = [
        {
            "name": "수집",
            "table": "CrawlRun",
            "count": total_runs,
            "status": "success" if total_runs else "idle",
            "note": f"성공 {success_runs:,} · 실패 {failed_runs:,}",
        },
        {
            "name": "원본 적재",
            "table": "RawDocument / S3",
            "count": doc_agg["total"],
            "status": "success" if docs.exists() else "idle",
            "note": "S3 원본 + 포인터",
        },
        {
            "name": "정규화",
            "table": "ProductSource / ContentItem",
            "count": product_sources + content_items,
            "status": "success" if (product_sources or content_items) else "idle",
            "note": f"상품 {product_sources:,} · 콘텐츠 {content_items:,}",
        },
        {
            "name": "텍스트 분석",
            "table": "TextDocument",
            "count": text_documents,
            "status": "success" if text_documents else "idle",
            "note": "댓글·리뷰 적재",
        },
        {
            "name": "트렌드 집계",
            "table": "TermMetricDaily",
            "count": metrics,
            "status": "success" if metrics else "idle",
            "note": "일자별 용어 지표",
        },
    ]

    # 파이프라인 막대 비율
    pipeline_max = max([step["count"] for step in pipeline] or [0])
    for step in pipeline:
        step["pct"] = (
            round(step["count"] / pipeline_max * 100, 1)
            if pipeline_max else 0
        )

    # ---------------- 플랫폼별 ----------------
    by_code = {s.code: s for s in Source.objects.all()}
    ordered = [by_code.pop(c) for c in SOURCE_ORDER if c in by_code]
    ordered += [by_code[c] for c in sorted(by_code)]

    run_by_source = {
        row["source_id"]: row
        for row in runs.values("source_id").annotate(
            n=Count("id"),
            failed=Count("id", filter=Q(status="FAILED")),
        )
    }
    doc_by_source = {
        row["source_id"]: row["n"]
        for row in docs.values("source_id").annotate(n=Count("id"))
    }
    last_by_source = {}
    for run in (
        CrawlRun.objects
        .order_by("source_id", "-started_at")
        .only("id", "source_id", "started_at")
    ):
        last_by_source.setdefault(run.source_id, run)

    sources = []
    for source in ordered:
        stat = run_by_source.get(source.id, {})
        total = stat.get("n", 0)
        failed = stat.get("failed", 0)
        doc_count = doc_by_source.get(source.id, 0)
        last = last_by_source.get(source.id)

        if total == 0:
            status = "idle"
        elif failed / total >= 0.4:
            status = "danger"
        elif failed:
            status = "warning"
        else:
            status = "healthy"

        sources.append({
            "name": _label(source),
            "code": source.code,
            "status": status,
            "count": doc_count,
            "runs": total,
            "failed": failed,
            "success_rate": _percent(total - failed, total),
            "last_run": last.started_at if last else None,
        })

    # ---------------- 최근 오류 ----------------
    recent_errors = []
    for run in (
        runs.select_related("source", "crawl_target")
        .filter(status="FAILED")
        .order_by("-started_at")[:8]
    ):
        recent_errors.append({
            "run_id": run.id,
            "time": timezone.localtime(run.started_at).strftime("%m-%d %H:%M")
            if run.started_at else "-",
            "source": _label(run.source) if run.source else "-",
            "target": (
                run.crawl_target.name if run.crawl_target
                else (run.target or "-")
            ),
            "code": run.error_code or "UNKNOWN",
            "message": (run.error_message or "오류 메시지 없음")[:160],
        })

    # ---------------- 점검이 필요한 항목 ----------------
    stale_running = run_agg["stale"]

    alerts = stale_alerts(now=now)
    if stats["failed_runs"] and total_runs:
        rate = round(stats["failed_runs"] / total_runs * 100, 1)
        if rate >= 20:
            alerts.append({
                "level": "danger",
                "title": f"수집 실패율 {rate}%",
                "detail": f"전체 {total_runs:,}건 중 {stats['failed_runs']:,}건이 실패했습니다.",
            })
    if stale_running:
        alerts.append({
            "level": "warning",
            "title": f"멈춘 실행 {stale_running}건",
            "detail": "1시간 넘게 RUNNING 상태입니다. 워커가 중단됐을 수 있습니다.",
        })
    if not metrics:
        alerts.append({
            "level": "warning",
            "title": "트렌드 지표 미집계",
            "detail": "term_metric_daily가 비어 있어 분석 화면이 채워지지 않습니다.",
        })
    if not text_documents:
        alerts.append({
            "level": "info",
            "title": "텍스트 분석 대기",
            "detail": "수집한 댓글이 아직 TextDocument로 적재되지 않았습니다.",
        })

    return {
        "stats": stats,
        "pipeline": pipeline,
        "sources": sources,
        "recent_errors": recent_errors,
        "alerts": alerts,
        "targets": {
            "total": CrawlTarget.objects.count(),
            "active": CrawlTarget.objects.filter(is_active=True).count(),
        },
        "generated_at": now,
    }
