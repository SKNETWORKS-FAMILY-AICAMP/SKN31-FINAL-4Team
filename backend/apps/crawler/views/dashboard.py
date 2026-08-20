from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django.shortcuts import render

from apps.crawler.models import CrawlJob, Source


def _source_card(source, *, name, description, url):
    last_job = (
        CrawlJob.objects.filter(source=source)
        .order_by("-created_at")
        .first()
        if source else None
    )
    status = source.status if source else "NOT REGISTERED"
    badge_class = "success-badge" if status == "ACTIVE" else "pending-badge"
    return {
        "code": source.code if source else name.upper(),
        "name": name,
        "description": description,
        "status": status,
        "badge_class": badge_class,
        "last_run": last_job.created_at if last_job else None,
        "url": url,
    }


def dashboard(request):
    now = timezone.now()
    since = now - timedelta(hours=24)

    jobs_24h = CrawlJob.objects.filter(created_at__gte=since)
    total_24h = jobs_24h.count()
    success_24h = jobs_24h.filter(status=CrawlJob.Status.SUCCESS).count()
    success_rate = round((success_24h / total_24h) * 100, 1) if total_24h else 0

    source_map = {source.code: source for source in Source.objects.all()}

    platform_cards = [
        _source_card(
            source_map.get("MUSINSA"),
            name="MUSINSA",
            description="무신사 상품 · 랭킹 · 스냅샷 수집",
            url=reverse("crawler:musinsa"),
        ),
        _source_card(
            source_map.get("YOUTUBE"),
            name="YouTube",
            description="패션 크리에이터 영상 · 지표 · 자막 수집",
            url=reverse("crawler:youtube"),
        ),
    ]

    context = {
        "overview": {
            "source_count": Source.objects.count(),
            "active_source_count": Source.objects.filter(status=Source.Status.ACTIVE).count(),
            "jobs_24h": total_24h,
            "success_rate_24h": success_rate,
        },
        "platform_cards": platform_cards,
        "recent_jobs": CrawlJob.objects.select_related("source", "crawl_target").order_by("-created_at")[:10],
    }
    return render(request, "crawler/dashboard.html", context)
