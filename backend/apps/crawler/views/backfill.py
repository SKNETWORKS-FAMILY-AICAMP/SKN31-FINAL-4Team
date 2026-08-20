from datetime import datetime

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.crawler.models import BackfillBatch, BackfillItem, Source


CATEGORY_OPTIONS = {
    "001": "상의",
    "002": "아우터",
    "003": "바지",
    "004": "원피스/스커트",
    "005": "가방",
    "006": "신발",
}


def backfill(request):
    batches = BackfillBatch.objects.select_related("source").order_by("-created_at")[:100]
    for batch in batches:
        batch.completed_items = batch.success_items + batch.failed_items
    return render(
        request,
        "crawler/backfill.html",
        {"batches": batches, "category_options": CATEGORY_OPTIONS},
    )


def _month_to_date(value):
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def backfill_create(request):
    if request.method != "POST":
        return redirect("crawler:backfill")

    source = Source.objects.filter(code="MUSINSA").first()
    if not source:
        messages.error(request, "MUSINSA Source가 등록되어 있지 않습니다.")
        return redirect("crawler:backfill")

    try:
        start_month = _month_to_date(request.POST["start_month"])
        end_month = _month_to_date(request.POST["end_month"])
    except (KeyError, ValueError):
        messages.error(request, "시작 월과 종료 월을 확인해주세요.")
        return redirect("crawler:backfill")

    genders = request.POST.getlist("gender_codes")
    categories = request.POST.getlist("category_codes")
    if not genders or not categories:
        messages.error(request, "성별과 카테고리를 하나 이상 선택해주세요.")
        return redirect("crawler:backfill")

    batch = BackfillBatch.objects.create(
        source=source,
        status=BackfillBatch.Status.DRAFT,
        start_month=start_month,
        end_month=end_month,
        gender_codes=genders,
        category_codes=categories,
    )
    messages.success(request, f"Backfill Batch #{batch.id}를 생성했습니다.")
    return redirect("crawler:backfill")


def backfill_run(request, batch_id):
    batch = get_object_or_404(BackfillBatch, pk=batch_id)
    if request.method == "POST":
        # 여기서 실제 Celery backfill task를 delay()로 연결하면 됩니다.
        batch.status = BackfillBatch.Status.PENDING
        batch.save(update_fields=["status"])
        messages.info(request, f"Batch #{batch.id}를 PENDING으로 변경했습니다. Celery task 연결 후 실제 실행됩니다.")
    return redirect("crawler:backfill")
