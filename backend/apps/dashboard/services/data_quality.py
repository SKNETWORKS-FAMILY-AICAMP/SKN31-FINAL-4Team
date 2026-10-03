"""데이터 품질 — 누락 · 중복 · 정규화 상태를 한 화면에 (2026-09-27).

요구사항 DATA_QUALITY-001(이상 현황) · 002(누락) · 003(중복).
숫자는 전부 RDS 테이블을 그대로 센 값이다. 표본을 뽑거나 추정하지 않는다.

- 누락: 플랫폼 상품(commerce.product_source)에서 화면 · 지표가 쓰는 칸이 빈 비율.
  가격은 상품 행이 아니라 스냅숏에 있으므로 '가격 관측이 한 번도 없는 상품' 으로 센다.
- 중복: 같은 브랜드 · 같은 정규화 이름의 통합 상품(commerce.product),
  이름만 같은 브랜드(core.brand), 같은 원본(content_hash)을 두 번 받은 수집 문서.
- 정규화: 수집 문서(raw_document)의 정규화 상태를 플랫폼별로.
"""

from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.functions import Lower, Trim

from apps.core.models import (
    Brand,
    Product,
    ProductSource,
    ProductSourceSnapshot,
    RawDocument,
    Source,
)

from .dashboard_service import SOURCE_ORDER, _label

# (키, 화면 이름, 빈 칸 조건) — 화면 · 지표가 실제로 쓰는 칸만 센다
MISSING_FIELDS = [
    ("product", "통합 상품 연결", Q(product__isnull=True)),
    ("brand", "브랜드", Q(source_brand__isnull=True)),
    ("category", "카테고리", Q(source_category__isnull=True)),
    ("thumbnail", "대표 이미지", Q(thumbnail_url__isnull=True) | Q(thumbnail_url="")),
    ("url", "상품 주소", Q(product_url__isnull=True) | Q(product_url="")),
    ("price", "가격 관측", Q(has_snapshot=False)),
]

# 이 비율을 넘으면 칸을 붉게 칠한다 — 화면에서 눈에 띄게만 한다(판정 기준 아님)
WARN_PCT = 20.0

DUPLICATE_LIST_LIMIT = 30


def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else None


def _ordered(sources):
    order = {code: i for i, code in enumerate(SOURCE_ORDER)}
    return sorted(sources, key=lambda s: (order.get(s.code, len(order)), s.code))


def missing_by_source():
    """플랫폼별 빈 칸 비율. 상품이 없는 플랫폼은 빼고 돌려준다."""
    has_snapshot = Exists(ProductSourceSnapshot.objects.filter(product_source=OuterRef("pk")))
    agg = {"n": Count("id")}
    for key, _label_, cond in MISSING_FIELDS:
        agg[key] = Count("id", filter=cond)
    rows = {
        r["source_id"]: r
        for r in ProductSource.objects.annotate(has_snapshot=has_snapshot)
        .values("source_id").annotate(**agg)
    }
    out = []
    for source in _ordered(Source.objects.filter(id__in=rows)):
        r = rows[source.id]
        cells = []
        for key, name, _cond in MISSING_FIELDS:
            pct = _pct(r[key], r["n"])
            cells.append({"key": key, "name": name, "count": r[key], "pct": pct,
                          "warn": pct is not None and pct >= WARN_PCT})
        out.append({"source": source, "label": _label(source), "total": r["n"], "cells": cells})
    return out


def duplicate_products(limit=DUPLICATE_LIST_LIMIT):
    """같은 브랜드 · 같은 정규화 이름으로 두 번 이상 들어간 통합 상품."""
    groups = (
        Product.objects.exclude(normalized_name__isnull=True).exclude(normalized_name="")
        .values("brand_id", "normalized_name")
        .annotate(n=Count("id")).filter(n__gt=1)
    )
    total_groups = groups.count()
    extra_rows = sum(g["n"] - 1 for g in groups)
    top = list(groups.order_by("-n", "normalized_name")[:limit])
    brand_names = dict(Brand.objects.filter(id__in={g["brand_id"] for g in top if g["brand_id"]})
                       .values_list("id", "name"))
    for g in top:
        g["brand"] = brand_names.get(g["brand_id"]) or "(브랜드 없음)"
        g["ids"] = list(Product.objects.filter(brand_id=g["brand_id"], normalized_name=g["normalized_name"])
                        .order_by("id").values_list("id", flat=True)[:8])
    return {"groups": total_groups, "extra_rows": extra_rows, "top": top}


def duplicate_brands(limit=DUPLICATE_LIST_LIMIT):
    """대소문자 · 앞뒤 공백만 다른 이름의 브랜드."""
    groups = (
        Brand.objects.annotate(key=Lower(Trim("name")))
        .values("key").annotate(n=Count("id")).filter(n__gt=1)
    )
    total = groups.count()
    top = list(groups.order_by("-n", "key")[:limit])
    for g in top:
        g["rows"] = list(Brand.objects.annotate(key=Lower(Trim("name"))).filter(key=g["key"])
                         .order_by("id").values("id", "name", "brand_code")[:8])
    return {"groups": total, "top": top}


def duplicate_raw_documents():
    """같은 원본(content_hash)을 같은 플랫폼에서 두 번 이상 받은 수집 문서 — 플랫폼별."""
    dup_hashes = (
        RawDocument.objects.exclude(content_hash__isnull=True).exclude(content_hash="")
        .values("source_id", "content_hash").annotate(n=Count("id")).filter(n__gt=1)
    )
    by_source = {}
    for g in dup_hashes:
        row = by_source.setdefault(g["source_id"], {"hashes": 0, "extra": 0})
        row["hashes"] += 1
        row["extra"] += g["n"] - 1
    out = []
    for source in _ordered(Source.objects.filter(id__in=by_source)):
        out.append({"source": source, "label": _label(source), **by_source[source.id]})
    return out


def normalization_by_source():
    """플랫폼별 정규화 상태 — 실패 비율이 높은 곳을 먼저 보이게 한다."""
    rows = {
        r["source_id"]: r
        for r in RawDocument.objects.values("source_id").annotate(
            n=Count("id"),
            success=Count("id", filter=Q(normalization_status="SUCCESS")),
            failed=Count("id", filter=Q(normalization_status="FAILED")),
            pending=Count("id", filter=Q(normalization_status__in=("PENDING", "PROCESSING"))),
        )
    }
    out = []
    for source in _ordered(Source.objects.filter(id__in=rows)):
        r = rows[source.id]
        fail_pct = _pct(r["failed"], r["n"])
        out.append({"source": source, "label": _label(source), "total": r["n"],
                    "success": r["success"], "failed": r["failed"], "pending": r["pending"],
                    "fail_pct": fail_pct, "warn": fail_pct is not None and fail_pct >= WARN_PCT})
    return out


def data_quality_context():
    missing = missing_by_source()
    products = duplicate_products()
    brands = duplicate_brands()
    raw = duplicate_raw_documents()
    norm = normalization_by_source()
    return {
        "fields": [name for _k, name, _c in MISSING_FIELDS],
        "missing": missing,
        "dup_products": products,
        "dup_brands": brands,
        "dup_raw": raw,
        "normalization": norm,
        "warn_pct": WARN_PCT,
        "summary": {
            "product_sources": sum(r["total"] for r in missing),
            "missing_hot": sum(1 for r in missing for c in r["cells"] if c["warn"]),
            "dup_product_groups": products["groups"],
            "dup_brand_groups": brands["groups"],
            "dup_raw_extra": sum(r["extra"] for r in raw),
            "norm_failed": sum(r["failed"] for r in norm),
        },
    }
