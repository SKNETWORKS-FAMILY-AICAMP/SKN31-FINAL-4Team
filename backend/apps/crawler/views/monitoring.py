from django.shortcuts import render

from apps.crawler.models import CrawlJob, Source


def monitoring(request):
    recent_jobs = (
        CrawlJob.objects.select_related("source", "crawl_target")
        .order_by("-created_at")[:100]
    )
    failed_jobs = (
        CrawlJob.objects.select_related("source", "crawl_target")
        .filter(status=CrawlJob.Status.FAILED)
        .order_by("-created_at")[:30]
    )

    alerts = [
        {
            "severity": "danger",
            "message": f"{job.source.code} Job #{job.id} 실패",
            "detail": job.error_message or job.error_type or "상세 오류 메시지가 없습니다.",
            "created_at": job.created_at,
            "tags": [job.source.code, job.status],
        }
        for job in failed_jobs
    ]

    crawlers = {
        source.code.lower(): {
            "code": source.code,
            "name": source.code,
        }
        for source in Source.objects.order_by("code")
    }

    return render(
        request,
        "crawler/monitoring.html",
        {
            "recent_jobs": recent_jobs,
            "alerts": alerts,
            "crawlers": crawlers,
        },
    )
