"""사전 운영 워크벤치.

목록을 단순 조회하는 화면에서 발견 → 검수 → 표준화 → 품질 확인으로 이어지는
작업 흐름을 제공한다. 큰 벡터 필드는 항상 제외하고, 목록은 페이지 단위로 읽는다.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import BooleanField, Case, Count, Exists, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import (
    Brand,
    BrandSource,
    DictionaryTerm,
    Source,
    TermAlias,
    TermCandidate,
    TermCandidateObservation,
    TermRelation,
    TextTermMention,
    ProductTerm,
)
from apps.core.models.dictionary import normalize_dictionary_text


LOGIN_URL = "/admin-dashboard/login/"
PAGE_SIZE = 32
SNAPSHOT_CACHE_KEY = "dashboard:dictionary:snapshot:v3"
SNAPSHOT_CACHE_SECONDS = 60


def _query_without_page(request):
    query = request.GET.copy()
    query.pop("page", None)
    return query.urlencode()


def _elided_page_range(page_obj):
    return page_obj.paginator.get_elided_page_range(
        page_obj.number, on_each_side=2, on_ends=1
    )


def _dictionary_snapshot():
    """페이지마다 반복되던 15개 안팎의 count를 짧은 단일 스냅샷으로 묶는다."""
    payload = cache.get(SNAPSHOT_CACHE_KEY)
    if payload is not None:
        return payload

    term_rows = DictionaryTerm.objects.all()
    term_stats = term_rows.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=DictionaryTerm.Status.ACTIVE)),
        embedded=Count("id", filter=Q(embedding__isnull=False)),
        no_embedding=Count("id", filter=Q(embedding__isnull=True)),
    )
    term_stats["alias"] = TermAlias.objects.count()
    by_type = list(
        term_rows.values("term_type").annotate(n=Count("id")).order_by("-n", "term_type")
    )

    candidate_stats = TermCandidate.objects.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=TermCandidate.Status.PENDING)),
        reviewing=Count("id", filter=Q(status=TermCandidate.Status.REVIEWING)),
        resolved=Count("id", filter=Q(status=TermCandidate.Status.RESOLVED)),
        reject=Count("id", filter=Q(decision=TermCandidate.Decision.REJECT)),
        open=Count(
            "id",
            filter=Q(status__in=[TermCandidate.Status.PENDING, TermCandidate.Status.REVIEWING]),
        ),
    )
    brand_stats = BrandSource.objects.aggregate(
        total=Count("id"),
        unmapped=Count("id", filter=Q(brand__isnull=True, mapping_status="UNMAPPED")),
        priority=Count("id", filter=Q(brand__isnull=True, mapping_status="UNMAPPED", detected_count__gte=20)),
        mapped=Count("id", filter=Q(brand__isnull=False)),
        excluded=Count("id", filter=Q(mapping_status="EXCLUDED")),
    )

    alias_exists = TermAlias.objects.filter(term_id=OuterRef("pk"))
    mention_exists = TextTermMention.objects.filter(term_id=OuterRef("pk"))
    coverage = (
        term_rows.annotate(has_alias=Exists(alias_exists), has_mention=Exists(mention_exists))
        .aggregate(
            no_alias=Count("id", filter=Q(has_alias=False)),
            no_mentions=Count("id", filter=Q(has_mention=False)),
        )
    )
    payload = {
        "terms": term_stats,
        "by_type": by_type,
        "candidates": candidate_stats,
        "brands": brand_stats,
        "coverage": coverage,
    }
    cache.set(SNAPSHOT_CACHE_KEY, payload, SNAPSHOT_CACHE_SECONDS)
    return payload


def _clear_dictionary_snapshot():
    cache.delete(SNAPSHOT_CACHE_KEY)


@login_required(login_url=LOGIN_URL)
def dictionary_overview(request):
    snapshot = _dictionary_snapshot()
    type_counts = [dict(row) for row in snapshot["by_type"]]
    max_type_count = max((row["n"] for row in type_counts), default=1)
    for row in type_counts:
        row["percent"] = round(row["n"] / max_type_count * 100)

    context = {
        "summary": {
            "active_terms": snapshot["terms"]["active"],
            "aliases": snapshot["terms"]["alias"],
            "pending_candidates": snapshot["candidates"]["open"],
            "unmapped_brands": snapshot["brands"]["unmapped"],
            "without_embedding": snapshot["terms"]["no_embedding"],
        },
        "type_counts": type_counts,
        "candidate_queue": (
            TermCandidate.objects.filter(status__in=["PENDING", "REVIEWING"])
            .select_related("nearest_term")
            .order_by("-detected_count", "-last_seen_at")[:6]
        ),
        "brand_queue": (
            BrandSource.objects.filter(brand__isnull=True, mapping_status="UNMAPPED")
            .select_related("source")
            .order_by("-detected_count", "-last_seen_at")[:6]
        ),
    }
    return render(request, "dashboard/dictionary/overview.html", context)


@login_required(login_url=LOGIN_URL)
def dictionary_terms(request):
    selected_type = request.GET.get("term_type", "").strip()
    selected_status = request.GET.get("status", "").strip()
    q = request.GET.get("q", "").strip()

    alias_counts = (
        TermAlias.objects.filter(term_id=OuterRef("pk"))
        .values("term_id").annotate(n=Count("id")).values("n")[:1]
    )
    queryset = (
        DictionaryTerm.objects.defer("embedding", "embedding_updated_at")
        .annotate(
            has_embedding=Case(
                When(embedding__isnull=False, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
            alias_count=Coalesce(Subquery(alias_counts, output_field=IntegerField()), Value(0)),
        )
        .select_related("brand")
        .order_by("term_type", "canonical_name")
    )
    if selected_type:
        queryset = queryset.filter(term_type=selected_type)
    if selected_status:
        queryset = queryset.filter(status=selected_status)
    if q:
        queryset = queryset.filter(
            Q(canonical_name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(term_code__icontains=q)
            | Q(aliases__alias__icontains=q)
        ).distinct()

    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    snapshot = _dictionary_snapshot()

    return render(
        request,
        "dashboard/dictionary/terms.html",
        {
            "summary": snapshot["terms"],
            "by_type": snapshot["by_type"],
            "type_choices": DictionaryTerm.TermType.choices,
            "status_choices": DictionaryTerm.Status.choices,
            "page_obj": page_obj,
            "rows": page_obj.object_list,
            "filtered_count": paginator.count,
            "selected_type": selected_type,
            "selected_status": selected_status,
            "search_query": q,
            "query_without_page": _query_without_page(request),
            "elided_page_range": _elided_page_range(page_obj),
        },
    )


@login_required(login_url=LOGIN_URL)
def dictionary_term_detail(request, pk):
    alias_counts = (
        TermAlias.objects.filter(term_id=OuterRef("pk"))
        .values("term_id")
        .annotate(n=Count("id"))
        .values("n")[:1]
    )
    mention_counts = (
        TextTermMention.objects.filter(term_id=OuterRef("pk"))
        .values("term_id")
        .annotate(n=Count("id"))
        .values("n")[:1]
    )
    product_counts = (
        ProductTerm.objects.filter(term_id=OuterRef("pk"))
        .values("term_id")
        .annotate(n=Count("id"))
        .values("n")[:1]
    )
    outgoing_counts = (
        TermRelation.objects.filter(source_term_id=OuterRef("pk"))
        .values("source_term_id")
        .annotate(n=Count("id"))
        .values("n")[:1]
    )
    incoming_counts = (
        TermRelation.objects.filter(target_term_id=OuterRef("pk"))
        .values("target_term_id")
        .annotate(n=Count("id"))
        .values("n")[:1]
    )
    term = get_object_or_404(
        DictionaryTerm.objects.defer("embedding")
        .select_related("brand")
        .annotate(
            detail_alias_count=Coalesce(Subquery(alias_counts, output_field=IntegerField()), Value(0)),
            detail_mention_count=Coalesce(Subquery(mention_counts, output_field=IntegerField()), Value(0)),
            detail_product_count=Coalesce(Subquery(product_counts, output_field=IntegerField()), Value(0)),
            outgoing_relation_count=Coalesce(Subquery(outgoing_counts, output_field=IntegerField()), Value(0)),
            incoming_relation_count=Coalesce(Subquery(incoming_counts, output_field=IntegerField()), Value(0)),
        ),
        pk=pk,
    )
    aliases = term.aliases.select_related("source").order_by("alias")
    outgoing = term.outgoing_relations.select_related("target_term").order_by(
        "-weight", "target_term__canonical_name"
    )[:20]
    incoming = term.incoming_relations.select_related("source_term").order_by(
        "-weight", "source_term__canonical_name"
    )[:20]
    mentions = term.text_mentions.select_related("document").order_by("-created_at")[:12]
    return render(
        request,
        "dashboard/dictionary/term_detail.html",
        {
            "term": term,
            "aliases": aliases,
            "outgoing": outgoing,
            "incoming": incoming,
            "mentions": mentions,
            "stats": {
                "aliases": term.detail_alias_count,
                "mentions": term.detail_mention_count,
                "products": term.detail_product_count,
                "relations": term.outgoing_relation_count + term.incoming_relation_count,
            },
        },
    )


@login_required(login_url=LOGIN_URL)
def dictionary_candidates(request):
    selected_type = request.GET.get("suggested_type", "").strip()
    selected_decision = request.GET.get("decision", "").strip()
    selected_status = request.GET.get("status", "").strip()
    q = request.GET.get("q", "").strip()
    queryset = TermCandidate.objects.select_related("nearest_term").order_by(
        "-detected_count", "-last_seen_at"
    )
    if selected_type:
        queryset = queryset.filter(suggested_type=selected_type)
    if selected_decision:
        queryset = queryset.filter(decision=selected_decision)
    if selected_status:
        queryset = queryset.filter(status=selected_status)
    if q:
        queryset = queryset.filter(
            Q(raw_term__icontains=q)
            | Q(note__icontains=q)
            | Q(decision_reason__icontains=q)
        )
    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    snapshot = _dictionary_snapshot()
    return render(
        request,
        "dashboard/dictionary/candidates.html",
        {
            "summary": snapshot["candidates"],
            "type_choices": DictionaryTerm.TermType.choices,
            "decision_choices": TermCandidate.Decision.choices,
            "status_choices": TermCandidate.Status.choices,
            "page_obj": page_obj,
            "rows": page_obj.object_list,
            "filtered_count": paginator.count,
            "selected_type": selected_type,
            "selected_decision": selected_decision,
            "selected_status": selected_status,
            "search_query": q,
            "query_without_page": _query_without_page(request),
            "elided_page_range": _elided_page_range(page_obj),
        },
    )


@login_required(login_url=LOGIN_URL)
def dictionary_candidate_detail(request, pk):
    observation_counts = (
        TermCandidateObservation.objects.filter(candidate_id=OuterRef("pk"))
        .values("candidate_id")
        .annotate(n=Count("id"))
        .values("n")[:1]
    )
    candidate = get_object_or_404(
        TermCandidate.objects.select_related("nearest_term").annotate(
            observation_count=Coalesce(
                Subquery(observation_counts, output_field=IntegerField()), Value(0)
            )
        ),
        pk=pk,
    )
    observations = candidate.observations.select_related("source").order_by(
        "-detected_at"
    )[:50]
    suggestions = DictionaryTerm.objects.filter(status="ACTIVE").defer("embedding")
    if candidate.suggested_type:
        suggestions = suggestions.filter(term_type=candidate.suggested_type)
    suggestions = suggestions.order_by("canonical_name")[:300]
    return render(
        request,
        "dashboard/dictionary/candidate_detail.html",
        {
            "candidate": candidate,
            "observations": observations,
            "observation_count": candidate.observation_count,
            "suggestions": suggestions,
            "type_choices": DictionaryTerm.TermType.choices,
        },
    )


@login_required(login_url=LOGIN_URL)
@require_POST
@transaction.atomic
def dictionary_candidate_review(request, pk):
    candidate = get_object_or_404(TermCandidate.objects.select_for_update(), pk=pk)
    action = request.POST.get("action", "").strip()
    note = request.POST.get("note", "").strip()

    if action == "new_term":
        term_type = request.POST.get("term_type", "").strip()
        valid_types = {value for value, _ in DictionaryTerm.TermType.choices}
        if term_type not in valid_types:
            messages.error(request, "신규 용어 유형을 선택해주세요.")
            return redirect("dashboard:dictionary_candidate_detail", pk=pk)
        normalized = normalize_dictionary_text(candidate.raw_term)
        term, created = DictionaryTerm.objects.get_or_create(
            term_type=term_type,
            normalized_name=normalized,
            defaults={"canonical_name": candidate.raw_term, "status": "ACTIVE"},
        )
        candidate.nearest_term = term
        candidate.decision = TermCandidate.Decision.NEW_TERM
        candidate.status = TermCandidate.Status.RESOLVED
        messages.success(request, "신규 표준 용어로 등록했습니다." if created else "이미 있는 표준 용어에 연결했습니다.")
    elif action == "alias":
        term = get_object_or_404(DictionaryTerm, pk=request.POST.get("target_term_id"))
        TermAlias.objects.get_or_create(
            term=term,
            alias=candidate.raw_term,
            source=None,
            defaults={"alias_type": TermAlias.AliasType.SYNONYM},
        )
        candidate.nearest_term = term
        candidate.decision = TermCandidate.Decision.ALIAS
        candidate.status = TermCandidate.Status.RESOLVED
        messages.success(request, f"{term.canonical_name}의 별칭으로 병합했습니다.")
    elif action == "reject":
        candidate.decision = TermCandidate.Decision.REJECT
        candidate.status = TermCandidate.Status.REJECTED
        messages.success(request, "사전 반영 대상에서 제외했습니다.")
    elif action == "reopen":
        candidate.decision = TermCandidate.Decision.PENDING
        candidate.status = TermCandidate.Status.PENDING
        candidate.reviewed_at = None
        candidate.note = note or candidate.note
        candidate.save()
        _clear_dictionary_snapshot()
        messages.success(request, "후보를 검토 대기로 되돌렸습니다.")
        return redirect("dashboard:dictionary_candidate_detail", pk=pk)
    else:
        messages.error(request, "지원하지 않는 판정입니다.")
        return redirect("dashboard:dictionary_candidate_detail", pk=pk)

    candidate.note = note
    candidate.reviewed_at = timezone.now()
    candidate.save()
    _clear_dictionary_snapshot()
    return redirect("dashboard:dictionary_candidate_detail", pk=pk)


@login_required(login_url=LOGIN_URL)
def brand_sources(request):
    status = request.GET.get("status", "unmapped")
    source_id = request.GET.get("source", "")
    q = request.GET.get("q", "").strip()
    queryset = BrandSource.objects.select_related("source", "brand").all()
    if status == "unmapped":
        queryset = queryset.filter(brand__isnull=True, mapping_status="UNMAPPED")
    elif status == "mapped":
        queryset = queryset.filter(brand__isnull=False)
    elif status == "excluded":
        queryset = queryset.filter(mapping_status="EXCLUDED")
    if source_id:
        queryset = queryset.filter(source_id=source_id)
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(source_brand_id__icontains=q)
            | Q(brand__name__icontains=q)
        )
    queryset = queryset.order_by("-detected_count", "-last_seen_at")
    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    snapshot = _dictionary_snapshot()
    return render(
        request,
        "dashboard/dictionary/brand_sources.html",
        {
            "brand_sources": page_obj.object_list,
            "page_obj": page_obj,
            "filtered_count": paginator.count,
            "sources": Source.objects.order_by("name"),
            "summary": snapshot["brands"],
            "selected_status": status,
            "selected_source": str(source_id) if source_id else "",
            "search_query": q,
            "query_without_page": _query_without_page(request),
            "elided_page_range": _elided_page_range(page_obj),
        },
    )


@login_required(login_url=LOGIN_URL)
def brand_search(request):
    q = request.GET.get("q", "").strip()
    brands = Brand.objects.filter(status=Brand.Status.ACTIVE)
    if q:
        brands = brands.filter(
            Q(name__icontains=q)
            | Q(english_name__icontains=q)
            | Q(brand_code__icontains=q)
        )
    else:
        brands = brands.none()
    rows = brands.only("id", "name", "english_name", "brand_code").order_by("name")[:30]
    return JsonResponse(
        {"results": [{"id": row.id, "name": row.name, "english_name": row.english_name or "", "code": row.brand_code} for row in rows]}
    )


@login_required(login_url=LOGIN_URL)
def dictionary_quality(request):
    terms = DictionaryTerm.objects.all()
    candidates = TermCandidate.objects.all()
    snapshot = _dictionary_snapshot()
    context = {
        "summary": {
            "no_embedding": snapshot["terms"]["no_embedding"],
            "no_alias": snapshot["coverage"]["no_alias"],
            "no_mentions": snapshot["coverage"]["no_mentions"],
            "stale_candidates": snapshot["candidates"]["open"],
            "unmapped_brands": snapshot["brands"]["unmapped"],
        },
        "terms_without_alias": terms.annotate(n=Count("aliases")).filter(n=0).defer("embedding").order_by("-last_seen_at")[:12],
        "terms_without_mentions": terms.annotate(n=Count("text_mentions")).filter(n=0).defer("embedding").order_by("-updated_at")[:12],
        "stale_candidates": candidates.filter(status__in=["PENDING", "REVIEWING"]).select_related("nearest_term").order_by("first_seen_at")[:12],
    }
    return render(request, "dashboard/dictionary/quality.html", context)
