from django.contrib import admin, messages
from django.contrib.admin.views.decorators import (
    staff_member_required,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from apps.core.models import (
    BrandSource,
    CrawlRun,
    MappingCandidate,
)

from apps.core.services.normalization import (
    normalize_musinsa_brands_from_crawl_run,
)


@staff_member_required
def normalization_dashboard(request):
    recent_runs = (
        CrawlRun.objects
        .select_related(
            "source",
            "crawl_target",
        )
        .filter(
            source__code__iexact="MUSINSA",
            status=CrawlRun.Status.SUCCESS,
        )
        .order_by("-id")[:30]
    )

    # ---------------------------------------------------------
    # 미매핑 브랜드
    #
    # BrandAlias는 제거했기 때문에,
    # 아직 표준 Brand로 확정되지 않은 브랜드는
    # MappingCandidate에서 관리한다.
    # ---------------------------------------------------------
    unmapped_brands = (
        MappingCandidate.objects
        .select_related("source")
        .filter(
            source__code__iexact="MUSINSA",
            mapping_type=MappingCandidate.MappingType.BRAND,
            status=MappingCandidate.Status.PENDING,
        )
        .order_by(
            "-detected_count",
            "source_name",
        )[:100]
    )

    # ---------------------------------------------------------
    # 매핑 완료 브랜드
    #
    # 플랫폼 브랜드 ID → FEEDIT Brand 매핑은
    # BrandSource에서 관리한다.
    # ---------------------------------------------------------
    mapped_count = (
        BrandSource.objects
        .filter(
            source__code__iexact="MUSINSA",
        )
        .count()
    )

    unmapped_count = (
        MappingCandidate.objects
        .filter(
            source__code__iexact="MUSINSA",
            mapping_type=MappingCandidate.MappingType.BRAND,
            status=MappingCandidate.Status.PENDING,
        )
        .count()
    )

    context = {
        **admin.site.each_context(request),
        "title": "브랜드 정제",
        "recent_runs": recent_runs,
        "unmapped_brands": unmapped_brands,
        "unmapped_count": unmapped_count,
        "mapped_count": mapped_count,
    }

    return render(
        request,
        "admin/normalization/dashboard.html",
        context,
    )


@staff_member_required
def normalize_brands(
    request,
    run_id,
):
    if request.method != "POST":
        return redirect(
            "normalization_dashboard"
        )

    crawl_run = get_object_or_404(
        CrawlRun,
        id=run_id,
        source__code__iexact="MUSINSA",
        status=CrawlRun.Status.SUCCESS,
    )

    try:
        result = (
            normalize_musinsa_brands_from_crawl_run(
                crawl_run_id=crawl_run.id,
            )
        )

        messages.success(
            request,
            (
                f"CrawlRun #{run_id} 브랜드 정제 완료 "
                f"/ 발견 {result.get('detected', 0)} "
                f"/ 신규 {result.get('created', 0)} "
                f"/ 누적 {result.get('updated', 0)} "
                f"/ 매칭 {result.get('matched', 0)} "
                f"/ 미매핑 {result.get('unmatched', 0)}"
            ),
        )

    except Exception as exc:
        messages.error(
            request,
            (
                f"CrawlRun #{run_id} "
                f"브랜드 정제 실패: {exc}"
            ),
        )

    return redirect(
        "normalization_dashboard"
    )