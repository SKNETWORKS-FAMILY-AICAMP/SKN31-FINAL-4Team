# apps/dashboard/views/analytics.py

from __future__ import annotations

from collections import Counter
import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Min, Q
from django.core.paginator import Paginator
from django.db.models.functions import TruncDate
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from apps.core.models import (
    ContentSnapshot,
    DictionaryTerm,
    ProductSource,
    ProductSourceSnapshot,
    ResaleSnapshot,
    Source,
    TermAlias,
    TermMetricDaily,
)

from analysis.metrics.common import METRIC_VERSION


from .helpers import (
    ordered_sources,
    attach_latest_product_snapshot,
    _get_comment_summary,
    _get_intent_stats,
    _get_slot_stats,
    _get_polarity_stats,
    _get_tag_count_stats,
    _get_slot_combinations,
    _get_term_pairs,
)

from ._common import _qs_without_page



PRODUCT_METRIC_ORDER_CHOICES = [
    ("recent", "최근 확인순"),
    ("rank", "랭킹순"),
    ("discount", "할인율 높은순"),
    ("review", "리뷰 많은순"),
    ("price_desc", "판매가 높은순"),
    ("price_asc", "판매가 낮은순"),
]


# ============================================================
# COMMON HELPERS
# ============================================================
def _term_detail_label(term):
    """
    DictionaryTerm subtype별 상세 분류 표시.

    relation/field가 없는 경우 안전하게 '-'.
    """

    term_type = str(
        getattr(term, "term_type", "")
        or ""
    ).upper()

    relation_map = {
        "ITEM": "item",
        "STYLE": "style",
        "DETAIL": "detail",
        "MATERIAL": "material",
        "COLOR": "color",
        "TPO": "tpo",
    }

    relation_name = relation_map.get(
        term_type
    )

    if not relation_name:
        return "-"

    try:
        obj = getattr(
            term,
            relation_name,
            None,
        )
    except Exception:
        obj = None

    if obj is None:
        return "-"

    # 실제 subtype 모델마다 이름이 조금 달라도 대응
    field_candidates = (
        "detail_type",
        "item_type",
        "style_type",
        "material_type",
        "color_type",
        "tpo_type",
        "subtype",
        "sub_type",
        "category",
        "group",
        "type",
    )

    for field in field_candidates:
        value = getattr(
            obj,
            field,
            None,
        )

        if value not in (
            None,
            "",
        ):
            # choices display 지원
            display_method = getattr(
                obj,
                f"get_{field}_display",
                None,
            )

            if callable(display_method):
                try:
                    displayed = (
                        display_method()
                    )

                    if displayed:
                        return str(
                            displayed
                        )
                except Exception:
                    pass

            return str(value)

    return "-"

def _float_or_none(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value, digits=1):
    value = _float_or_none(value)

    if value is None:
        return None

    return round(value, digits)


def _rate_to_percent(value):
    """
    0~1 비율값 -> 0~100 %

    만약 이미 0~100으로 저장돼 있는 경우도 방어.
    """
    value = _float_or_none(value)

    if value is None:
        return None

    if abs(value) <= 1:
        value *= 100

    return round(value, 1)


def _dict_get(data, *keys, default=None):
    """
    nested dict 안전 접근

    _dict_get(
        metrics,
        "signals",
        "commerce",
        "score",
    )
    """
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def _signal_score(metrics, signal_name):
    value = _dict_get(
        metrics,
        "signals",
        signal_name,
        "score",
    )

    return _round_or_none(value)


def _search_value(
    metrics,
    platform,
    field,
):
    return _dict_get(
        metrics,
        "search",
        "platforms",
        platform,
        field,
    )


def _lifecycle_stage(
    *,
    level,
    momentum,
):
    """
    현재는 Admin 시각화용 단계.

    lifecycle 공식 확정 후
    이 함수만 교체하면 됨.
    """

    level = _float_or_none(level)
    momentum = _float_or_none(momentum)

    if level is None:
        level = 0.0

    if momentum is None:
        momentum = 50.0

    if momentum < 40:
        return "COOLING"

    if level >= 70 and momentum < 60:
        return "MATURE"

    if level >= 60 and momentum >= 60:
        return "GROWING"

    if momentum >= 60:
        return "EMERGING"

    return "DISCOVERY"


def _avg(values):
    values = [
        float(v)
        for v in values
        if v is not None
    ]

    if not values:
        return None

    return round(
        sum(values) / len(values),
        1,
    )


# ============================================================
# EXISTING
# 용어별 지표
# ============================================================

@login_required(
    login_url="/admin-dashboard/login/"
)
def term_metrics(request):
    """
    기존 '용어별 지표' 페이지.

    DictionaryTerm을 기준으로 보여주고,
    존재하는 TermMetricDaily를 붙여서 표시.
    """

    search_query = (
        request.GET.get("q", "")
        .strip()
    )

    selected_type = (
        request.GET.get(
            "term_type",
            "",
        )
        .strip()
    )

    selected_date = (
        request.GET.get(
            "metric_date",
            "",
        )
        .strip()
    )

    # --------------------------------------------------------
    # 날짜
    # --------------------------------------------------------

    dates = list(
        TermMetricDaily.objects
        .filter(
            metric_version=METRIC_VERSION,
        )
        .values_list(
            "metric_date",
            flat=True,
        )
        .distinct()
        .order_by(
            "-metric_date"
        )
    )

    # --------------------------------------------------------
    # DictionaryTerm
    # --------------------------------------------------------

    term_qs = (
        DictionaryTerm.objects
        .all()
        .order_by(
            "canonical_name"
        )
    )

    if selected_type:
        term_qs = term_qs.filter(
            term_type=selected_type
        )

    if search_query:
        term_qs = term_qs.filter(
            Q(
                canonical_name__icontains=search_query
            )
            |
            Q(
                normalized_name__icontains=search_query
            )
        )

    # --------------------------------------------------------
    # Metrics
    # --------------------------------------------------------

    metric_qs = (
        TermMetricDaily.objects
        .filter(
            metric_version=METRIC_VERSION,
        )
        .select_related(
            "term",
            "source",
        )
    )

    if selected_date:
        try:
            parsed_date = date.fromisoformat(
                selected_date
            )

            metric_qs = metric_qs.filter(
                metric_date=parsed_date
            )

        except ValueError:
            pass

    # 기존 페이지는 term 당 하나의 대표 row가 필요하므로
    # ALL(source=NULL)을 우선 사용.
    metrics_by_term = {}

    for metric in (
        metric_qs
        .order_by(
            "term_id",
            "-metric_date",
        )
    ):
        current = metrics_by_term.get(
            metric.term_id
        )

        if current is None:
            metrics_by_term[
                metric.term_id
            ] = metric
            continue

        # 같은 term/date면 ALL row 우선
        if (
            metric.source_id is None
            and current.source_id is not None
        ):
            metrics_by_term[
                metric.term_id
            ] = metric

    rows = []

    for term in term_qs:
        metric = metrics_by_term.get(
            term.id
        )

        rows.append(
            {
                "id": term.id,

                "term_text": (
                    term.canonical_name
                ),

                "term_type": (
                    metric.term.term_type
                ),
                
                "term_detail": (
                    _term_detail_label(
                        metric.term
                    )
                ),
                "metric_date": (
                    metric.metric_date
                    if metric
                    else None
                ),

                "mention_count": (
                    metric.mention_count
                    if metric
                    else 0
                ),

                "document_count": (
                    metric.document_count
                    if metric
                    else 0
                ),

                # 현재 구조에서는 source별 row가 분리되어 있으므로
                # 대표 row에서 1/ALL 의미보다 term의 source 개수를 계산.
                "source_count": (
                    TermMetricDaily.objects
                    .filter(
                        term_id=term.id,
                        metric_version=METRIC_VERSION,
                        metric_date=metric.metric_date,
                    )
                    .exclude(
                        source__isnull=True
                    )
                    .values(
                        "source_id"
                    )
                    .distinct()
                    .count()
                    if metric
                    else 0
                ),

                # 기존 HTML 호환
                "growth_rate": (
                    _round_or_none(
                        metric.momentum,
                        2,
                    )
                    if metric
                    else None
                ),

                "trend_score": (
                    _round_or_none(
                        metric.trend_temperature,
                        2,
                    )
                    if metric
                    else None
                ),
            }
        )

    # --------------------------------------------------------
    # term type 목록
    # --------------------------------------------------------

    term_types = list(
        DictionaryTerm.objects
        .exclude(
            term_type__isnull=True
        )
        .exclude(
            term_type=""
        )
        .values_list(
            "term_type",
            flat=True,
        )
        .distinct()
        .order_by(
            "term_type"
        )
    )

    summary = {
        "metric_rows": (
            TermMetricDaily.objects
            .filter(
                metric_version=METRIC_VERSION
            )
            .count()
        ),

        "measured_terms": (
            TermMetricDaily.objects
            .filter(
                metric_version=METRIC_VERSION
            )
            .values(
                "term_id"
            )
            .distinct()
            .count()
        ),

        "terms": (
            DictionaryTerm.objects
            .count()
        ),

        "aliases": (
            TermAlias.objects
            .count()
        ),

        "dates": len(
            dates
        ),
    }

    context = {
        "page_title": "용어별 지표",

        "page_description": (
            "DictionaryTerm 기준으로 "
            "수집·분석된 용어별 지표를 확인합니다."
        ),

        "summary": summary,

        "rows": rows,

        "filtered_count": len(
            rows
        ),

        "term_types": (
            term_types
        ),

        "dates": dates,

        "selected_type": (
            selected_type
        ),

        "selected_date": (
            selected_date
        ),

        "search_query": (
            search_query
        ),
    }

    return render(
        request,
        "dashboard/analytics/term_metrics.html",
        context,
    )


# ============================================================
# NEW
# 트렌드 시그널
# ============================================================

@login_required(login_url="/admin-dashboard/login/")
def trend_metrics(request):
    """
    FEEDIT L2 Trend Signal Dashboard

    TermMetricDaily
        +
    Commerce
    Content
    Reaction
    Search
        ↓
    Level
    MA7
    MA28
    Momentum
    Trend Temperature
    """

    # --------------------------------------------------------
    # latest date
    # --------------------------------------------------------

    latest_metric_date = (
        TermMetricDaily.objects
        .filter(
            metric_version=METRIC_VERSION,
        )
        .order_by(
            "-metric_date"
        )
        .values_list(
            "metric_date",
            flat=True,
        )
        .first()
    )

    # --------------------------------------------------------
    # filters
    # --------------------------------------------------------

    date_raw = (
        request.GET.get(
            "date",
            "",
        )
        .strip()
    )

    selected_term_type = (
        request.GET.get(
            "term_type",
            "",
        )
        .strip()
    )

    selected_source = (
        request.GET.get(
            "source",
            "",
        )
        .strip()
    )

    q = (
        request.GET.get(
            "q",
            "",
        )
        .strip()
    )

    if date_raw:
        try:
            selected_date = (
                date.fromisoformat(
                    date_raw
                )
            )
        except ValueError:
            selected_date = (
                latest_metric_date
            )
    else:
        selected_date = (
            latest_metric_date
        )

    # --------------------------------------------------------
    # queryset
    # --------------------------------------------------------

    qs = (
        TermMetricDaily.objects
        .filter(
            metric_version=METRIC_VERSION,
        )
        .select_related(
            "term",
            "source",
        )
    )

    if selected_date:
        qs = qs.filter(
            metric_date=selected_date
        )

    if selected_term_type:
        qs = qs.filter(
            term__term_type=selected_term_type
        )

    if selected_source:

        if (
            selected_source.upper()
            == "ALL"
        ):
            qs = qs.filter(
                source__isnull=True
            )

        else:
            qs = qs.filter(
                source__code__iexact=(
                    selected_source
                )
            )

    if q:
        qs = qs.filter(
            Q(
                term__canonical_name__icontains=q
            )
            |
            Q(
                term__normalized_name__icontains=q
            )
        )

    qs = qs.order_by(
        "-trend_temperature",
        "-level",
        "term__canonical_name",
        "source_id",
    )

    # --------------------------------------------------------
    # rows
    # --------------------------------------------------------

    rows = []

    for metric in qs:

        metrics = (
            metric.metrics
            if isinstance(
                metric.metrics,
                dict,
            )
            else {}
        )

        commerce_score = (
            _signal_score(
                metrics,
                "commerce",
            )
        )

        content_score = (
            _signal_score(
                metrics,
                "content",
            )
        )

        reaction_score = (
            _signal_score(
                metrics,
                "reaction",
            )
        )

        search_score = (
            _signal_score(
                metrics,
                "search",
            )
        )

        # signals.search.score가 없을 때
        # metrics.search.score fallback
        if search_score is None:
            search_score = (
                _round_or_none(
                    _dict_get(
                        metrics,
                        "search",
                        "score",
                    )
                )
            )

        google_volume = (
            _search_value(
                metrics,
                "google",
                "search_volume",
            )
        )

        naver_volume = (
            _search_value(
                metrics,
                "naver",
                "search_volume",
            )
        )

        # ----------------------------------------------------
        # reaction rate
        #
        # 모델에 rate 컬럼이 있으면 사용.
        # 없으면 count / mention_count로 계산.
        # ----------------------------------------------------

        mention_count = int(
            metric.mention_count
            or 0
        )

        purchase_rate = getattr(
            metric,
            "purchase_rate",
            None,
        )

        question_rate = getattr(
            metric,
            "question_rate",
            None,
        )

        positive_rate = getattr(
            metric,
            "positive_rate",
            None,
        )

        negative_rate = getattr(
            metric,
            "negative_rate",
            None,
        )

        if (
            purchase_rate is None
            and mention_count > 0
        ):
            purchase_count = getattr(
                metric,
                "purchase_count",
                0,
            ) or 0

            purchase_rate = (
                purchase_count
                / mention_count
            )

        if (
            question_rate is None
            and mention_count > 0
        ):
            question_count = getattr(
                metric,
                "question_count",
                0,
            ) or 0

            question_rate = (
                question_count
                / mention_count
            )

        if (
            positive_rate is None
            and mention_count > 0
        ):
            positive_rate = (
                (metric.positive_count or 0)
                / mention_count
            )

        if (
            negative_rate is None
            and mention_count > 0
        ):
            negative_rate = (
                (metric.negative_count or 0)
                / mention_count
            )

        lifecycle = (
            _lifecycle_stage(
                level=metric.level,
                momentum=metric.momentum,
            )
        )

        rows.append(
            {
                "id": metric.id,

                "term_id": (
                    metric.term_id
                ),

                "term_name": (
                    metric.term.canonical_name
                ),

                "term_type": (
                    metric.term.term_type
                ),

                "source": (
                    metric.source.code
                    if metric.source_id
                    else "ALL"
                ),

                # ------------------------------
                # base
                # ------------------------------

                "raw_count": (
                    _round_or_none(
                        metric.raw_count,
                        2,
                    )
                ),

                "percentile": (
                    _round_or_none(
                        metric.percentile,
                        1,
                    )
                ),

                # ------------------------------
                # trend
                # ------------------------------

                "level": (
                    _round_or_none(
                        metric.level,
                        1,
                    )
                ),

                "ma7": (
                    _round_or_none(
                        metric.ma7,
                        1,
                    )
                ),

                "ma28": (
                    _round_or_none(
                        metric.ma28,
                        1,
                    )
                ),

                "momentum": (
                    _round_or_none(
                        metric.momentum,
                        1,
                    )
                ),

                "trend_temperature": (
                    _round_or_none(
                        metric.trend_temperature,
                        1,
                    )
                ),

                # ------------------------------
                # domain signals
                # ------------------------------

                "commerce_score": (
                    commerce_score
                ),

                "content_score": (
                    content_score
                ),

                "reaction_score": (
                    reaction_score
                ),

                "search_score": (
                    search_score
                ),

                # ------------------------------
                # reaction
                # ------------------------------

                "mention_count": (
                    mention_count
                ),

                "document_count": int(
                    metric.document_count
                    or 0
                ),

                "purchase_rate": (
                    _rate_to_percent(
                        purchase_rate
                    )
                ),

                "question_rate": (
                    _rate_to_percent(
                        question_rate
                    )
                ),

                "positive_rate": (
                    _rate_to_percent(
                        positive_rate
                    )
                ),

                "negative_rate": (
                    _rate_to_percent(
                        negative_rate
                    )
                ),

                # ------------------------------
                # search
                # ------------------------------

                "google_volume": (
                    google_volume
                ),

                "naver_volume": (
                    naver_volume
                ),

                "lifecycle": (
                    lifecycle
                ),
            }
        )

    # ========================================================
    # ALL ROWS
    #
    # summary는 source별 row 중복을 피하기 위해
    # source=NULL aggregate row만 기준.
    # ========================================================

    all_rows = [
        row
        for row in rows
        if row["source"] == "ALL"
    ]

    # source 필터로 ALL row가 사라진 경우에도
    # 상단 카드 자체가 전부 0이 되지 않도록
    # 현재 rows fallback
    summary_rows = (
        all_rows
        if all_rows
        else rows
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    total_terms = len(
        {
            row["term_id"]
            for row in summary_rows
        }
    )

    rising_terms = len(
        {
            row["term_id"]
            for row in summary_rows
            if (
                row["momentum"]
                is not None
                and row["momentum"] >= 60
            )
        }
    )

    search_connected = sum(
        1
        for row in summary_rows
        if (
            row["google_volume"]
            is not None
            or row["naver_volume"]
            is not None
        )
    )

    search_coverage = (
        round(
            search_connected
            / len(summary_rows)
            * 100,
            1,
        )
        if summary_rows
        else 0.0
    )

    summary = {
        "total_terms": (
            total_terms
        ),

        "avg_level": _avg(
            [
                row["level"]
                for row in summary_rows
            ]
        ),

        "avg_temperature": _avg(
            [
                row[
                    "trend_temperature"
                ]
                for row in summary_rows
            ]
        ),

        "rising_terms": (
            rising_terms
        ),

        "search_coverage": (
            f"{search_coverage}%"
        ),
    }

    # ========================================================
    # SIGNAL SUMMARY
    # ========================================================

    signal_summary = {
        "commerce": (
            _avg(
                [
                    row["commerce_score"]
                    for row in summary_rows
                ]
            )
            or 0
        ),

        "content": (
            _avg(
                [
                    row["content_score"]
                    for row in summary_rows
                ]
            )
            or 0
        ),

        "reaction": (
            _avg(
                [
                    row["reaction_score"]
                    for row in summary_rows
                ]
            )
            or 0
        ),

        "search": (
            _avg(
                [
                    row["search_score"]
                    for row in summary_rows
                ]
            )
            or 0
        ),
    }

    # ========================================================
    # LIFECYCLE
    # ========================================================

    lifecycle_counter = Counter(
        row["lifecycle"]
        for row in summary_rows
    )

    lifecycle_order = [
        "DISCOVERY",
        "EMERGING",
        "GROWING",
        "MATURE",
        "COOLING",
    ]

    lifecycle_total = sum(
        lifecycle_counter.values()
    )

    lifecycle_summary = []

    for stage in lifecycle_order:

        count = (
            lifecycle_counter.get(
                stage,
                0,
            )
        )

        percent = (
            round(
                count
                / lifecycle_total
                * 100,
                1,
            )
            if lifecycle_total
            else 0
        )

        lifecycle_summary.append(
            {
                "stage": stage,
                "count": count,
                "percent": percent,
            }
        )

    # ========================================================
    # FILTER OPTIONS
    # ========================================================

    sources = (
        Source.objects
        .all()
        .order_by(
            "code"
        )
    )

    term_type_values = list(
        DictionaryTerm.objects
        .exclude(
            term_type__isnull=True
        )
        .exclude(
            term_type=""
        )
        .values_list(
            "term_type",
            flat=True,
        )
        .distinct()
        .order_by(
            "term_type"
        )
    )

    # HTML:
    # {% for value, label in term_types %}
    term_types = [
        (
            value,
            value,
        )
        for value
        in term_type_values
    ]

    # ========================================================
    # CONTEXT
    # ========================================================

    context = {
        "page_title": (
            "트렌드 시그널"
        ),

        "page_description": (
            "Commerce · Content · Reaction · Search를 통합해 "
            "용어별 트렌드 강도와 성장 모멘텀을 분석합니다."
        ),

        # filter
        "selected_date": (
            selected_date.isoformat()
            if selected_date
            else ""
        ),

        "selected_term_type": (
            selected_term_type
        ),

        "selected_source": (
            selected_source
        ),

        "q": q,

        "sources": (
            sources
        ),

        "term_types": (
            term_types
        ),

        # dashboard
        "summary": (
            summary
        ),

        "signal_summary": (
            signal_summary
        ),

        "lifecycle_summary": (
            lifecycle_summary
        ),

        "rows": (
            rows
        ),

        "filtered_count": (
            len(rows)
        ),

        "metric_version": (
            METRIC_VERSION
        ),
    }

    return render(
        request,
        "dashboard/trend/trend_signals.html",
        context,
    )


@login_required(login_url="/admin-dashboard/login/")
def product_metrics(request):
    """상품별 지표 — 플랫폼 상품에 최신 스냅샷 지표를 붙여 조회."""

    selected_source = request.GET.get("source", "").strip()
    selected_order = request.GET.get("order", "recent").strip()
    q = request.GET.get("q", "").strip()

    queryset = (
        ProductSource.objects
        .select_related("source", "source_brand")
        .all()
    )

    if selected_source:
        queryset = queryset.filter(source_id=selected_source)

    if q:
        queryset = queryset.filter(
            Q(source_name__icontains=q)
            | Q(normalized_name__icontains=q)
            | Q(source_product_id__icontains=q)
            | Q(source_brand__name__icontains=q)
        )

    if selected_order == "rank":
        queryset = queryset.annotate(
            v=Min("snapshots__rank_position")
        ).exclude(v__isnull=True).order_by("v")
    elif selected_order == "discount":
        queryset = queryset.annotate(
            v=Max("snapshots__discount_rate")
        ).exclude(v__isnull=True).order_by("-v")
    elif selected_order == "review":
        queryset = queryset.annotate(
            v=Max("snapshots__review_count")
        ).exclude(v__isnull=True).order_by("-v")
    elif selected_order == "price_desc":
        queryset = queryset.annotate(
            v=Max("snapshots__sale_price")
        ).exclude(v__isnull=True).order_by("-v")
    elif selected_order == "price_asc":
        queryset = queryset.annotate(
            v=Min("snapshots__sale_price")
        ).exclude(v__isnull=True).order_by("v")
    else:
        queryset = queryset.order_by("-last_seen_at", "-id")

    paginator = Paginator(queryset, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = list(page_obj.object_list)
    attach_latest_product_snapshot(rows)

    snapshots = ProductSourceSnapshot.objects.all()

    context = {
        "page_title": "상품별 지표",
        "page_description": (
            "플랫폼 상품의 최신 가격·할인·평점·순위를 조회합니다."
        ),
        "summary": {
            "product_source": ProductSource.objects.count(),
            "snapshot_rows": snapshots.count(),
            "resale_rows": ResaleSnapshot.objects.count(),
            "with_snapshot": (
                snapshots.values("product_source_id").distinct().count()
            ),
            "latest_observed": (
                snapshots.order_by("-observed_at")
                .values_list("observed_at", flat=True)
                .first()
            ),
        },
        "sources": ordered_sources(),
        "order_choices": PRODUCT_METRIC_ORDER_CHOICES,
        "rows": rows,
        "page_obj": page_obj,
        "filtered_count": paginator.count,
        "selected_source": selected_source,
        "selected_order": selected_order,
        "search_query": q,
        "qs": _qs_without_page(request),
    }

    return render(
        request,
        "dashboard/analytics/product_metrics.html",
        context,
    )

@login_required(login_url="/admin-dashboard/login/")
def product_snapshot(request):
    """상품 스냅샷 — 관측 시점별 원본 지표 행."""

    selected_source = request.GET.get("source", "").strip()
    q = request.GET.get("q", "").strip()

    queryset = (
        ProductSourceSnapshot.objects
        .select_related(
            "product_source",
            "product_source__source",
        )
        .order_by("-observed_at", "-id")
    )

    if selected_source:
        queryset = queryset.filter(
            product_source__source_id=selected_source
        )

    if q:
        queryset = queryset.filter(
            Q(product_source__source_name__icontains=q)
            | Q(product_source__source_product_id__icontains=q)
        )

    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    snapshots = ProductSourceSnapshot.objects.all()

    daily_counts = list(
        snapshots
        .annotate(day=TruncDate("observed_at"))
        .values("day")
        .annotate(n=Count("id"))
        .order_by("-day")[:14]
    )

    context = {
        "page_title": "상품 스냅샷",
        "page_description": (
            "관측 시점별로 쌓인 상품 지표 원본을 조회합니다."
        ),
        "summary": {
            "snapshot_rows": snapshots.count(),
            "resale_rows": ResaleSnapshot.objects.count(),
            "content_rows": ContentSnapshot.objects.count(),
            "observed_days": (
                snapshots
                .annotate(day=TruncDate("observed_at"))
                .values("day")
                .distinct()
                .count()
            ),
            "latest_observed": (
                snapshots.order_by("-observed_at")
                .values_list("observed_at", flat=True)
                .first()
            ),
        },
        "daily_counts": daily_counts,
        "sources": ordered_sources(),
        "rows": page_obj.object_list,
        "page_obj": page_obj,
        "filtered_count": paginator.count,
        "selected_source": selected_source,
        "search_query": q,
        "qs": _qs_without_page(request),
    }

    return render(
        request,
        "dashboard/analytics/product_snapshot.html",
        context,
    )

@login_required(login_url="/admin-dashboard/login/")
def text_comment_metrics(request):
    """댓글 분석 대시보드 — intent/slot/polarity/복합 태그/동시등장 분석."""

    summary = _get_comment_summary()
    intent_stats = _get_intent_stats()
    slot_stats = _get_slot_stats()
    polarity_stats = _get_polarity_stats()
    tag_count_stats = _get_tag_count_stats()
    slot_combinations = _get_slot_combinations(limit=20)
    term_pairs = _get_term_pairs(limit=50)

    # Chart.js에서 바로 사용할 수 있도록 JSON도 함께 전달한다.
    # 템플릿에서 json_script를 쓰는 경우에는 아래 *_json 값 대신
    # 원본 리스트(intent_stats 등)를 사용해도 된다.
    context = {
        "page_title": "댓글 데이터 분석",
        "page_description": (
            "댓글의 의도·패션 속성·극성·복합 태그와 "
            "동시 등장 용어를 분석합니다."
        ),
        "summary": summary,
        "intent_stats": intent_stats,
        "slot_stats": slot_stats,
        "polarity_stats": polarity_stats,
        "tag_count_stats": tag_count_stats,
        "slot_combinations": slot_combinations,
        "term_pairs": term_pairs,
        "intent_stats_json": json.dumps(
            intent_stats,
            ensure_ascii=False,
            default=str,
        ),
        "slot_stats_json": json.dumps(
            slot_stats,
            ensure_ascii=False,
            default=str,
        ),
        "polarity_stats_json": json.dumps(
            polarity_stats,
            ensure_ascii=False,
            default=str,
        ),
        "tag_count_stats_json": json.dumps(
            tag_count_stats,
            ensure_ascii=False,
            default=str,
        ),
    }

    return render(
        request,
        "dashboard/analytics/text_comments.html",
        context,
    )


@login_required(login_url="/admin-dashboard/login/")
def product_snapshot_detail(
    request,
    snapshot_id: int,
):
    snapshot = get_object_or_404(
        ProductSourceSnapshot.objects.select_related(
            "product_source",
            "product_source__source",
        ),
        pk=snapshot_id,
    )

    product_source = snapshot.product_source

    context = {
        "page_title": "상품 스냅샷 상세",
        "page_description": "선택한 상품 스냅샷의 상세 데이터를 확인합니다.",
        "snapshot": snapshot,
        "product_source": product_source,
    }

    return render(
        request,
        "dashboard/analytics/product_snapshot_detail.html",
        context,
    )