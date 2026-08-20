from datetime import timedelta

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.crawler.models import (
    CrawlJob,
    CrawlTarget,
    Source,
    ZigzagProduct,
    ZigzagProductSnapshot,
    ZigzagStore,
)
from apps.crawler.tasks.zigzag import (
    run_all_zigzag_targets,
    run_zigzag_target,
)

ZIGZAG_META = {
    "code": "ZIGZAG",
    "name": "ZIGZAG",
    "description": (
        "지그재그 카테고리 상품과 랭킹 변화를 " "지속적으로 수집하고 추적합니다."
    ),
}


# ============================================================
# INTERNAL
# ============================================================


def _get_zigzag_source():
    return Source.objects.filter(
        code="ZIGZAG",
    ).first()


def _zigzag_trend(source):
    """
    최초 CrawlJob 실행일 ~ 오늘까지의 실행 추이.
    """

    if source is None:
        return {
            "labels": [],
            "totals": [],
            "successes": [],
        }

    first_job = CrawlJob.objects.filter(source=source).order_by("created_at").first()

    if first_job is None:
        return {
            "labels": [],
            "totals": [],
            "successes": [],
        }

    start_date = timezone.localtime(first_job.created_at).date()

    end_date = timezone.localdate()

    labels = []
    totals = []
    successes = []

    current_date = start_date

    while current_date <= end_date:
        qs = CrawlJob.objects.filter(
            source=source,
            created_at__date=current_date,
        )

        labels.append(current_date.strftime("%m-%d"))

        totals.append(qs.count())

        successes.append(
            qs.filter(
                status=CrawlJob.Status.SUCCESS,
            ).count()
        )

        current_date += timedelta(days=1)

    return {
        "labels": labels,
        "totals": totals,
        "successes": successes,
    }


# ============================================================
# PAGE
# ============================================================


def zigzag(request):
    source = _get_zigzag_source()

    jobs = CrawlJob.objects.none()
    targets = CrawlTarget.objects.none()

    if source:
        jobs = CrawlJob.objects.filter(source=source).select_related(
            "source",
            "crawl_target",
        )

        targets = CrawlTarget.objects.filter(
            source=source,
            is_active=True,
        ).order_by(
            "display_name",
            "id",
        )

    last_job = jobs.order_by("-created_at").first()

    # ========================================================
    # DATA STATS
    # ========================================================

    total_products = ZigzagProduct.objects.count()

    total_snapshots = ZigzagProductSnapshot.objects.count()

    total_stores = ZigzagStore.objects.count()

    brand_stores = ZigzagStore.objects.filter(is_brand=True).count()

    avg_snapshots_per_product = (
        round(
            total_snapshots / total_products,
            1,
        )
        if total_products
        else 0
    )

    # 가장 많은 Snapshot이 쌓인 상품
    most_tracked_product = (
        ZigzagProduct.objects.annotate(snapshot_count=Count("snapshots"))
        .order_by("-snapshot_count")
        .first()
    )

    crawler = {
        **ZIGZAG_META,
        "is_active": bool(source and source.status == Source.Status.ACTIVE),
        "cycle_hours": (
            max(
                1,
                int((source.crawl_interval_minutes or 1440) / 60),
            )
            if source
            else 24
        ),
    }

    context = {
        "source": "zigzag",
        "crawler": crawler,
        "crawler_status": (source.status if source else "NOT REGISTERED"),
        "last_job": last_job,
        # 핵심 데이터 지표
        "zigzag_stats": {
            "total_products": total_products,
            "total_snapshots": total_snapshots,
            "avg_snapshots_per_product": (avg_snapshots_per_product),
            "total_stores": total_stores,
            "brand_stores": brand_stores,
        },
        "most_tracked_product": (most_tracked_product),
        "crawler_trend_data": (_zigzag_trend(source)),
        "crawl_targets": targets,
        "recent_jobs": (jobs.order_by("-created_at")[:50]),
        "alerts": [],
    }

    return render(
        request,
        "crawler/zigzag.html",
        context,
    )


@require_POST
def zigzag_run_target(
    request,
    target_id,
):
    target = get_object_or_404(
        CrawlTarget,
        id=target_id,
        source__code="ZIGZAG",
    )

    task = run_zigzag_target.delay(
        target.id,
        CrawlJob.TriggerType.MANUAL,
    )

    messages.success(
        request,
        (f"{target.display_name} 크롤링을 시작했습니다. " f"Task ID: {task.id}"),
    )

    return redirect(
        "crawler:zigzag",
    )


# ============================================================
# RUN ALL TARGETS
# ============================================================


@require_POST
def zigzag_run_all_targets(
    request,
):
    source = _get_zigzag_source()

    if source is None:
        messages.error(
            request,
            "ZIGZAG Source가 등록되어 있지 않습니다.",
        )
        return redirect(
            "crawler:zigzag",
        )

    target_count = CrawlTarget.objects.filter(
        source=source,
        target_type=CrawlTarget.TargetType.CATEGORY,
        is_active=True,
    ).count()

    if target_count == 0:
        messages.warning(
            request,
            "실행할 활성 ZIGZAG Target이 없습니다.",
        )
        return redirect(
            "crawler:zigzag",
        )

    task = run_all_zigzag_targets.delay(
        CrawlJob.TriggerType.MANUAL,
    )

    messages.success(
        request,
        (
            f"활성 Target {target_count}개의 "
            f"지그재그 수집을 시작했습니다. "
            f"Task ID: {task.id}"
        ),
    )

    return redirect(
        "crawler:zigzag",
    )


# ============================================================
# ACTIVE / INACTIVE
# ============================================================


@require_POST
def zigzag_toggle_active(
    request,
):
    source = _get_zigzag_source()

    if source is None:
        messages.error(
            request,
            "ZIGZAG Source가 등록되어 있지 않습니다.",
        )
        return redirect(
            "crawler:zigzag",
        )

    source.status = (
        Source.Status.INACTIVE
        if source.status == Source.Status.ACTIVE
        else Source.Status.ACTIVE
    )

    source.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    messages.success(
        request,
        f"ZIGZAG 상태를 {source.status}로 변경했습니다.",
    )

    return redirect(
        "crawler:zigzag",
    )


# ============================================================
# UPDATE CYCLE
# ============================================================


@require_POST
def zigzag_update_cycle(
    request,
):
    source = _get_zigzag_source()

    if source is None:
        messages.error(
            request,
            "ZIGZAG Source가 등록되어 있지 않습니다.",
        )
        return redirect(
            "crawler:zigzag",
        )

    try:
        hours = max(
            1,
            int(
                request.POST.get(
                    "cycle_hours",
                    "24",
                )
            ),
        )

    except (TypeError, ValueError):
        messages.error(
            request,
            "올바른 수집 주기를 입력해주세요.",
        )
        return redirect(
            "crawler:zigzag",
        )

    source.crawl_interval_minutes = hours * 60

    source.save(
        update_fields=[
            "crawl_interval_minutes",
            "updated_at",
        ]
    )

    messages.success(
        request,
        f"수집 주기를 {hours}시간으로 변경했습니다.",
    )

    return redirect(
        "crawler:zigzag",
    )
