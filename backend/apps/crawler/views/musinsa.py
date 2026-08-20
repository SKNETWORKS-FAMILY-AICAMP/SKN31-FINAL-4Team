from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.crawler.models import CrawlJob, CrawlTarget, Source


MUSINSA_META = {
    "code": "MUSINSA",
    "name": "MUSINSA",
    "description": "무신사 상품, 랭킹, 가격 및 반응 스냅샷 수집 상태를 관리합니다.",
}


def _get_source():
    return Source.objects.filter(code="MUSINSA").first()


def _trend(source):
    today = timezone.localdate()
    labels, totals, successes = [], [], []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        qs = CrawlJob.objects.filter(source=source, created_at__date=day) if source else CrawlJob.objects.none()
        labels.append(day.strftime("%m-%d"))
        totals.append(qs.count())
        successes.append(qs.filter(status=CrawlJob.Status.SUCCESS).count())
    return {"labels": labels, "totals": totals, "successes": successes}


def musinsa(request):
    source = _get_source()
    jobs = CrawlJob.objects.none()
    targets = CrawlTarget.objects.none()

    if source:
        jobs = CrawlJob.objects.filter(source=source).select_related("source", "crawl_target")
        targets = CrawlTarget.objects.filter(source=source, is_active=True).order_by("display_name")

    last_job = jobs.order_by("-created_at").first()
    last_7d = jobs.filter(created_at__gte=timezone.now() - timedelta(days=7))
    total_jobs = last_7d.count()
    success_jobs = last_7d.filter(status=CrawlJob.Status.SUCCESS).count()

    crawler = {
        **MUSINSA_META,
        "is_active": bool(source and source.status == Source.Status.ACTIVE),
        "cycle_hours": int((source.crawl_interval_minutes or 1440) / 60) if source else 24,
    }

    context = {
        "source": "musinsa",
        "crawler": crawler,
        "crawler_status": source.status if source else "NOT REGISTERED",
        "last_job": last_job,
        "crawler_stats": {
            "success_rate": round(success_jobs / total_jobs * 100, 1) if total_jobs else 0,
            "total_jobs": total_jobs,
            "total_items": sum(last_7d.values_list("items_found", flat=True)),
        },
        "crawler_trend_data": _trend(source),
        "crawl_targets": targets,
        "recent_jobs": jobs.order_by("-created_at")[:50],
        "alerts": [],
    }
    return render(request, "crawler/musinsa.html", context)


def run_target(request, target_id):
    target = get_object_or_404(CrawlTarget, pk=target_id)
    if request.method == "POST":
        CrawlJob.objects.create(
            source=target.source,
            crawl_target=target,
            status=CrawlJob.Status.PENDING,
            trigger_type=CrawlJob.TriggerType.MANUAL,
            scheduled_at=timezone.now(),
        )
        messages.success(request, f"{target.display_name or target.target_value} Job을 PENDING으로 생성했습니다.")
    return redirect("crawler:musinsa")


def run_all_targets(request):
    source = _get_source()
    if request.method == "POST" and source:
        targets = CrawlTarget.objects.filter(source=source, is_active=True)
        for target in targets:
            CrawlJob.objects.create(
                source=source,
                crawl_target=target,
                status=CrawlJob.Status.PENDING,
                trigger_type=CrawlJob.TriggerType.MANUAL,
                scheduled_at=timezone.now(),
            )
        messages.success(request, f"활성 Target {targets.count()}개의 Job을 생성했습니다.")
    return redirect("crawler:musinsa")


def toggle_active(request):
    source = _get_source()
    if request.method == "POST" and source:
        source.status = Source.Status.INACTIVE if source.status == Source.Status.ACTIVE else Source.Status.ACTIVE
        source.save(update_fields=["status", "updated_at"])
        messages.success(request, f"MUSINSA 상태를 {source.status}로 변경했습니다.")
    return redirect("crawler:musinsa")


def update_cycle(request):
    source = _get_source()
    if request.method == "POST" and source:
        try:
            hours = max(1, int(request.POST.get("cycle_hours", "24")))
        except ValueError:
            hours = 24
        source.crawl_interval_minutes = hours * 60
        source.save(update_fields=["crawl_interval_minutes", "updated_at"])
        messages.success(request, f"수집 주기를 {hours}시간으로 변경했습니다.")
    return redirect("crawler:musinsa")
