from django.shortcuts import get_object_or_404, render

from apps.crawler.models import CrawlJob, MusinsaProductSnapshot, RawObject


def job(request, job_id):
    crawl_job = get_object_or_404(
        CrawlJob.objects.select_related("source", "crawl_target"),
        pk=job_id,
    )
    is_musinsa = crawl_job.source.code == "MUSINSA"

    ranking_results = MusinsaProductSnapshot.objects.none()
    if is_musinsa:
        ranking_results = (
            MusinsaProductSnapshot.objects.filter(crawl_job=crawl_job)
            .select_related("product", "product__brand")
            .order_by("rank", "-observed_at")
        )

    raw_objects = RawObject.objects.filter(crawl_job=crawl_job).order_by("-collected_at")

    return render(
        request,
        "crawler/job.html",
        {
            "job": crawl_job,
            "is_musinsa": is_musinsa,
            "ranking_results": ranking_results,
            "raw_objects": raw_objects,
        },
    )
