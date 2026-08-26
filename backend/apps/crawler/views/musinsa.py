from django.contrib import messages
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.crawler.models import (
    CrawlJob,
    CrawlTarget,
    MusinsaBrand,
    MusinsaProduct,
    Source,
)

from apps.crawler.tasks.musinsa import (
    run_all_musinsa_targets,
    run_musinsa_target,
)

# ============================================================
# MUSINSA META
# ============================================================

MUSINSA_META = {
    "code": "MUSINSA",
    "name": "MUSINSA",
    "description": ("무신사 상품, 랭킹, 가격 및 반응 데이터를 수집합니다."),
}


# ============================================================
# SOURCE
# ============================================================


def _get_musinsa_source():
    """
    MUSINSA Source 조회.

    Source가 존재하지 않는 경우 None을 반환한다.
    """

    return Source.objects.filter(
        code="MUSINSA",
    ).first()


# ============================================================
# TODAY JOB
# ============================================================


def _get_today_jobs(source, today):
    """
    오늘 생성된 MUSINSA CrawlJob 중
    Target별 가장 최근 Job을 가져오기 위한 QuerySet.

    Target마다 여러 번 실행될 수 있기 때문에
    created_at DESC 기준으로 정렬한다.
    """

    return (
        CrawlJob.objects.filter(
            source=source,
            created_at__date=today,
        )
        .select_related(
            "crawl_target",
        )
        .order_by(
            "-created_at",
        )
    )


# ============================================================
# TARGETS
# ============================================================


def _get_musinsa_targets(source, today):
    """
    활성 MUSINSA Target 목록.

    각 Target 객체에 다음 값을 동적으로 추가한다.

        target.today_job

    오늘 실행된 Job 중 가장 최근 Job.
    """

    if source is None:
        return CrawlTarget.objects.none()

    today_jobs = _get_today_jobs(
        source=source,
        today=today,
    )

    targets = list(
        CrawlTarget.objects.filter(
            source=source,
            is_active=True,
        )
        .prefetch_related(
            Prefetch(
                "crawl_jobs",
                queryset=today_jobs,
                to_attr="today_jobs",
            )
        )
        .order_by(
            "display_name",
        )
    )

    for target in targets:

        jobs = getattr(
            target,
            "today_jobs",
            [],
        )

        target.today_job = jobs[0] if jobs else None

    return targets


# ============================================================
# PAGE
# ============================================================


def musinsa(request):
    """
    MUSINSA Crawler Dashboard.

    이 페이지는 CrawlJob 자체를 나열하는 것이 아니라
    CrawlTarget을 기준으로 오늘의 수집 상태를 보여준다.

    Target
        ↓
    오늘 가장 최근 CrawlJob
        ↓
    Job 상세 페이지
    """

    source = _get_musinsa_source()

    today = timezone.localdate()

    # --------------------------------------------------------
    # 실제 수집 데이터
    # --------------------------------------------------------

    brand_count = MusinsaBrand.objects.count()

    product_count = MusinsaProduct.objects.count()

    # --------------------------------------------------------
    # Targets
    # --------------------------------------------------------

    crawl_targets = _get_musinsa_targets(
        source=source,
        today=today,
    )

    target_count = len(crawl_targets)

    # --------------------------------------------------------
    # 오늘 상태 집계
    # --------------------------------------------------------

    success_count = 0
    failed_count = 0
    running_count = 0
    pending_count = 0
    not_run_count = 0

    for target in crawl_targets:

        job = target.today_job

        if job is None:

            not_run_count += 1

            continue

        if job.status == CrawlJob.Status.SUCCESS:

            success_count += 1

        elif job.status == CrawlJob.Status.FAILED:

            failed_count += 1

        elif job.status == CrawlJob.Status.RUNNING:

            running_count += 1

        elif job.status == CrawlJob.Status.PENDING:

            pending_count += 1

    # --------------------------------------------------------
    # Context
    # --------------------------------------------------------

    context = {
        "source": "musinsa",
        "crawler": MUSINSA_META,
        "today": today,
        # KPI
        "brand_count": brand_count,
        "product_count": product_count,
        "target_count": target_count,
        # Target
        "crawl_targets": crawl_targets,
        # Today's status
        "success_count": success_count,
        "failed_count": failed_count,
        "running_count": running_count,
        "pending_count": pending_count,
        "not_run_count": not_run_count,
    }

    return render(
        request,
        "crawler/musinsa.html",
        context,
    )


# ============================================================
# RUN ONE TARGET
# ============================================================


@require_POST
def run_target(request, target_id):
    """
    특정 MUSINSA Target 즉시 실행.
    """

    target = get_object_or_404(
        CrawlTarget,
        id=target_id,
        source__code="MUSINSA",
        is_active=True,
    )

    run_musinsa_target.delay(
        target.id,
    )

    messages.success(
        request,
        f"'{target.display_name}' 크롤링을 시작했습니다.",
    )

    return redirect(
        "crawler:musinsa",
    )


# ============================================================
# RUN ALL TARGETS
# ============================================================


@require_POST
def run_all_targets(request):
    """
    활성화된 MUSINSA Target 전체 실행.
    """

    source = _get_musinsa_source()

    if source is None:

        messages.error(
            request,
            "MUSINSA Source가 등록되어 있지 않습니다.",
        )

        return redirect(
            "crawler:musinsa",
        )

    target_count = CrawlTarget.objects.filter(
        source=source,
        is_active=True,
    ).count()

    if target_count == 0:

        messages.warning(
            request,
            "실행할 MUSINSA Target이 없습니다.",
        )

        return redirect(
            "crawler:musinsa",
        )

    run_all_musinsa_targets.delay()

    messages.success(
        request,
        f"활성 Target {target_count}개의 크롤링을 시작했습니다.",
    )

    return redirect(
        "crawler:musinsa",
    )


from django.shortcuts import render


def overview(request):
    context = {
        "active_menu": "musinsa",
        "active_tab": "overview",
    }

    return render(
        request,
        "crawler/musinsa/overview.html",
        context,
    )


def targets(request):
    context = {
        "active_menu": "musinsa",
        "active_tab": "targets",
    }

    return render(
        request,
        "crawler/musinsa/targets.html",
        context,
    )
