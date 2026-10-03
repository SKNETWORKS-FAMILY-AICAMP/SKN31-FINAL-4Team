"""프론트(트렌드 분석 페이지)가 부르는 읽기 전용 API.

── 구조 ────────────────────────────────────────────────────
    브라우저 ─▶ (Vercel 함수 또는 vite 프록시) ─▶ 이 API ─▶ AWS RDS

스키마는 SKN31-FINAL-4Team/backend 의 모델(apps/core/models)이 원본이다.
이 파일은 그 표를 **읽기만** 한다.

── 원칙 ────────────────────────────────────────────────────
① 쓰지 않는다. 전부 GET.
② 지표(온도·모멘텀·구매의향 지수·연관도)는 적재된 값을 그대로 쓴다.
   여기서 하는 계산은 "읽은 값끼리의 집계"(평균·중앙값·기간 비교)뿐이다.
   수명주기 단계처럼 저장된 칸이 없는 판정은 규칙을 응답(`rule`)에 함께 적는다.
③ 값이 없으면 지어내지 않는다. `status:"empty"` 와 사유를 돌려주고,
   칸 단위로 없는 값은 null 로 둔다. 화면은 그 자리를 '측정 불가'로 그린다.

── 탭 ↔ 주소 ───────────────────────────────────────────────
    언급량·온도   /api/trend?term=
    연관어        /api/assoc?term=
    긍부정        /api/trend?term=      (같은 표의 반응·의도 칸)
    할인률 변화   /api/discount?style=&kind=&brand=&item=&term=
    리세일 시세   /api/resale?…          (같은 조건)
    수명주기      /api/lifecycle?…       (같은 조건)
"""

from __future__ import annotations

import math
import os
import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from django.db import connection
from django.db.models import Avg, Case, Count, Exists, F, FloatField, IntegerField, Max, Min, OuterRef, Q, Subquery, Sum, Value, When, Window
from django.db.models.functions import Cast, Coalesce, Greatest, Ln, RowNumber, TruncDate
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from .notifications import josa
from apps.api.images import absolute_image_url
from apps.core.models import (
    Brand,
    BrandSource,
    ContentItem,
    DictionaryTerm,
    Product,
    ProductSource,
    ProductSourceSnapshot,
    ProductTerm,
    ResaleSnapshot,
    TermAlias,
    TermAssocDaily,
    TermMetricDaily,
    TermSearchMetricMonthly,
    TermSearchRegion,
    TermSearchTrend,
    TextDocument,
    TextTermMention,
    VoteBallot,
    VoteCard,
)

MAX_LIMIT = 500

# ★ 팀이 정한 핵심 스타일 10종 (2026-09-16).
#   세부 검색 STYLE 칸에는 이 10개만, 이 순서를 기준으로 보여 준다.
#   상품 태그가 0건이어도 칸에서 빼지 않고 0 으로 둔다 — 핵심인데 안 보이면
#   "적재가 안 됐다" 는 사실이 가려진다.
#   바꿔야 하면 코드 대신 .env 의 FEEDIT_CORE_STYLES=고프코어,블록코어,… 로 덮는다.
DEFAULT_CORE_STYLES = (
    "고프코어", "블록코어", "바이크코어", "놈코어", "애슬레저",
    "클래식", "아메카지", "그런지", "페미닌", "스트릿웨어",
)


def _core_styles():
    env = [x.strip() for x in (os.getenv("FEEDIT_CORE_STYLES") or "").split(",") if x.strip()]
    return tuple(env) if env else DEFAULT_CORE_STYLES

# 우리 term_type ↔ 화면이 쓰는 축 이름
FACET_KO = {
    "BRAND": "브랜드", "STYLE": "스타일", "ITEM": "아이템", "MATERIAL": "소재",
    "DETAIL": "디테일", "COLOR": "색", "TPO": "TPO", "PERSON": "인물",
}


# ══════════════════════════════════════════════════════════════
#  공용 도우미
# ══════════════════════════════════════════════════════════════

def _ok(data, **extra):
    return JsonResponse({"status": "ok", **extra, "data": data})


def _empty(reason, **extra):
    return JsonResponse({"status": "empty", "reason": reason, **extra, "data": None})


def _safe_log_metric(expression):
    """Return ln(1 + count), treating missing or invalid negative counts as zero."""
    zero = Value(0.0, output_field=FloatField())
    safe_count = Greatest(Coalesce(expression, zero), zero)
    return Ln(safe_count + Value(1.0, output_field=FloatField()))


def _num(v, nd=None):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if nd is not None else f


def _pct(v):
    """할인율 — 0~1 로 들어온 값은 % 로 바꾼다."""
    v = _num(v)
    if v is None:
        return None
    return round(v * 100 if 0 < v <= 1 else v, 1)


def _retail_discount_pct(row):
    """일반 판매 스냅샷은 정가·판매가를 우선한다. 1%를 100%로 오해하지 않는다."""
    list_price = _num(row.get("list_price"))
    sale_price = _num(row.get("sale_price"))
    if list_price is not None and list_price > 0 and sale_price is not None:
        if sale_price < 0 or sale_price > list_price:
            return None
        return round((list_price - sale_price) / list_price * 100, 1)
    raw = _num(row.get("discount_rate"))
    return round(raw, 1) if raw is not None and 0 <= raw <= 100 else None


def _int(request, name, default, lo, hi):
    try:
        return max(lo, min(hi, int(request.GET.get(name, default))))
    except (TypeError, ValueError):
        return default


def _norm(s):
    return "".join(str(s or "").split()).lower()


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _pick_measured(qs):
    """같은 이름이 여러 축에 있을 때(예: '니트' ITEM · MATERIAL) 지표가 가장 많은 쪽.
    예전에는 순서 없는 .first() 라 지표가 적은 쪽이 잡히기도 했다(2026-09-19)."""
    return qs.annotate(_n=Count("daily_metrics")).order_by("-_n", "id").first()


def _resolve_term(name):
    """화면에서 온 말 → DictionaryTerm. 표준명 › 정규화명 › 별칭 › 브랜드명 순."""
    name = (name or "").strip()
    if not name:
        return None
    base = DictionaryTerm.objects.exclude(status="INACTIVE")
    t = _pick_measured(base.filter(canonical_name=name))
    if t:
        return t
    n = _norm(name)
    t = _pick_measured(base.filter(normalized_name=n))
    if t:
        return t
    alias = (
        TermAlias.objects.filter(Q(alias=name) | Q(normalized_alias=n))
        .values_list("term_id", flat=True).first()
    )
    if alias:
        return base.filter(id=alias).first()
    return base.filter(
        Q(brand__name=name) | Q(brand__english_name__iexact=name), term_type="BRAND"
    ).first()


def _resolve_brand(name):
    """표준명·영문명·플랫폼 표기 중 하나로 활성 브랜드를 찾는다."""
    name = (name or "").strip()
    if not name:
        return None
    brand = Brand.objects.filter(status="ACTIVE").filter(
        Q(name=name) | Q(english_name__iexact=name)
    ).first()
    if brand:
        return brand
    brand_id = (
        BrandSource.objects.filter(brand__status="ACTIVE")
        .filter(Q(name=name) | Q(english_name__iexact=name))
        .values_list("brand_id", flat=True)
        .first()
    )
    return Brand.objects.filter(id=brand_id).first() if brand_id else None


def _brand_variants(brand):
    """댓글에서 브랜드를 찾을 때 쓸 검수된 표기. 너무 짧은 표기는 오탐을 막는다."""
    raw = [brand.name, brand.english_name]
    raw.extend(
        value
        for pair in BrandSource.objects.filter(brand=brand).values_list("name", "english_name")
        for value in pair
    )
    variants, seen = [], set()
    for value in raw:
        value = str(value or "").strip()
        key = _norm(value)
        if not key or key in seen or (value.isascii() and len(key) < 3) or (not value.isascii() and len(key) < 2):
            continue
        seen.add(key)
        variants.append(value)
    return variants[:40]


def _contains_any(field, values):
    query = Q()
    for value in values:
        query |= Q(**{f"{field}__icontains": value})
    return query


# ★ 2026-09-23 — 긍부정 탭에 커머스 리뷰(REVIEW)를 넣는다.
#   댓글은 analysis_metadata.published_at 에 작성 시각이 있지만
#   리뷰는 그 키가 없고 source_published_at 에만 있다(sync_product_reviews).
#   그래서 metadata 가 비면 source_published_at 으로 떨어진다 — 안 그러면 리뷰가 조용히 전부 빠진다.
SENTIMENT_DOC_TYPES = ("COMMENT", "REVIEW")


def _published_date(metadata, fallback=None):
    raw = metadata.get("published_at") if isinstance(metadata, dict) else None
    try:
        parsed = parse_datetime(str(raw)) if raw else None
    except ValueError:
        parsed = None
    if parsed:
        return parsed.date()
    if fallback:
        return timezone.localtime(fallback).date() if timezone.is_aware(fallback) else fallback.date()
    return None


def _direct_sentiment_series(rows, days):
    """mention 행을 댓글 단위로 합친 뒤, 실제 게시일 기준 일별 반응으로 만든다."""
    documents = {}
    for row in rows:
        day = _published_date(row.get("document__analysis_metadata"),
                              row.get("document__source_published_at"))
        score = _num(row.get("sentiment_score"))
        if day is None or score is None:
            continue
        doc = documents.setdefault(
            row["document_id"], {"date": day, "scores": [], "intent": row.get("intent_code")}
        )
        doc["scores"].append(score)
        if not doc["intent"] and row.get("intent_code"):
            doc["intent"] = row["intent_code"]

    if not documents:
        return [], None, 0

    last_date = max(doc["date"] for doc in documents.values())
    since = last_date - timedelta(days=days - 1)
    daily = defaultdict(lambda: defaultdict(int))
    intent_fields = {
        "QUESTION": "question_n", "PURCHASE": "purchase_n", "EXPERIENCE": "experience_n",
        "PRAISE": "praise_n", "CRITIQUE": "critique_n", "CHITCHAT": "chitchat_n",
    }
    included = 0
    for doc in documents.values():
        if doc["date"] < since:
            continue
        included += 1
        bucket = daily[doc["date"]]
        score = sum(doc["scores"]) / len(doc["scores"])
        polarity = "pos_n" if score > 0.5 else "neg_n" if score < 0.5 else "neu_n"
        bucket[polarity] += 1
        intent_field = intent_fields.get(str(doc["intent"] or "").upper())
        if intent_field:
            bucket[intent_field] += 1

    series = []
    count_fields = (
        "pos_n", "neu_n", "neg_n", "question_n", "purchase_n", "experience_n",
        "praise_n", "critique_n", "chitchat_n",
    )
    for day in sorted(daily):
        bucket = daily[day]
        point = {"date": day.isoformat(), **{field: bucket[field] for field in count_fields}}
        total = point["pos_n"] + point["neu_n"] + point["neg_n"]
        point.update({
            "mention": total,
            "document": total,
            "pos_rate": round(point["pos_n"] / total * 100, 4) if total else None,
            "neu_rate": round(point["neu_n"] / total * 100, 4) if total else None,
            "neg_rate": round(point["neg_n"] / total * 100, 4) if total else None,
            "sentiment": round((point["pos_n"] - point["neg_n"]) / total, 5) if total else None,
            "intent": None,
        })
        series.append(point)
    return series, last_date, included


# ── 장기 이력 (2026-09-19) ─────────────────────────────────────
#  RDS 의 YouTube 댓글·설명란을 '쓰인 날'로 되돌려 다시 계산한 일별 지표.
#  (backend/apps/core/management/commands/rebuild_term_history.py)
#  플랫폼 합산 버전(feedit-l2-v2)은 하루치뿐이라 수명주기(28일 이상)를 못 낸다.
#  그래서 '수명주기 · 추이' 에서만 이 버전을 읽는다. 플랫폼별 온도·새 용어는 기존 버전 그대로.
#  ★ 기본 버전 고르기(_metric_version)에서는 빼야 한다 — 적재 시각이 더 늦어
#    '가장 최근 버전'으로 잡히면 합산 행이 없는 버전이 기본이 되어 화면 전체가 빈다.
HISTORY_VERSION = (os.getenv("FEEDIT_HISTORY_METRIC_VERSION") or "feedit-yt-history-v1").strip()
HISTORY_SOURCE = "YOUTUBE"
HISTORY_MIN_POINTS = 28
HISTORY_BASIS = {
    "source": HISTORY_SOURCE,
    "metric_version": HISTORY_VERSION,
    "note": "YouTube 댓글·영상 설명의 작성일 기준 재계산 이력입니다. 다른 플랫폼은 포함되지 않습니다.",
}


# ── 플랫폼별 온도 창 (2026-09-21) ─────────────────────
#  커머스 리뷰는 '쓰인 날'로 지표가 쌓여 최신 행이 몇 달 전일 수 있다.
#  창을 좀게 잡으면 적재가 됐는데도 화면에서 사라진다 — 그게 9월까지의 상황이었다.
PLATFORM_WINDOW_DAYS = 90
STALE_AFTER_DAYS = 14


def _platform_window():
    try:
        return max(1, int(os.getenv("FEEDIT_PLATFORM_WINDOW_DAYS") or PLATFORM_WINDOW_DAYS))
    except ValueError:
        return PLATFORM_WINDOW_DAYS


def _history_series(term, days):
    """장기 이력(YouTube) — 마지막 적재일 기준으로 days 만큼."""
    qs = TermMetricDaily.objects.filter(
        term=term, metric_version=HISTORY_VERSION, source__code__iexact=HISTORY_SOURCE)
    last = qs.aggregate(d=Max("metric_date"))["d"]
    if not last:
        return []
    return list(qs.filter(metric_date__gt=last - timedelta(days=days))
                .order_by("metric_date").values(*METRIC_VALUES))


def _data_as_of():
    """데이터베이스 최신화 일자 — 지표 화면의 '기준일' 은 전부 이 날짜로 통일한다.

    용어마다 마지막 적재일이 다르면 화면마다 다른 기준일이 떠서
    같은 데이터를 보는데도 날짜가 어긋나 보인다.
    """
    d = (TermMetricDaily.objects.exclude(metric_version=HISTORY_VERSION)
         .aggregate(d=Max("metric_date"))["d"])
    return d.isoformat() if d else None


def _metric_version(term_id=None):
    """여러 지표 버전이 섞여 있을 수 있다 — 환경변수 › 가장 최근 적재 버전.
    장기 이력 버전(HISTORY_VERSION)은 합산 행이 없으므로 기본 버전 후보에서 뺀다."""
    env = (os.getenv("FEEDIT_METRIC_VERSION") or "").strip()
    qs = TermMetricDaily.objects.exclude(metric_version=HISTORY_VERSION)
    if term_id:
        qs = qs.filter(term_id=term_id)
    if env and qs.filter(metric_version=env).exists():
        return env
    row = qs.order_by("-metric_date", "-updated_at").values("metric_version").first()
    return row["metric_version"] if row else None


def _term_missing_reason(name, days=None):
    as_brand = Brand.objects.filter(Q(name=name) | Q(english_name__iexact=name)).exists()
    if as_brand:
        return (f"‘{name}’ 은 브랜드 사전에는 있지만 지표 대상 용어(dictionary_term)로 "
                "연결돼 있지 않아 지표가 없습니다.")
    return f"‘{name}’ 을 사전에서 찾지 못했습니다."


# ══════════════════════════════════════════════════════════════
#  health · dictionary · terms
# ══════════════════════════════════════════════════════════════

def _column_mismatch():
    """모델에는 있는데 실제 DB 표에는 없는 칸 — 스키마 어긋남을 먼저 알린다."""
    out = {}
    models = (DictionaryTerm, TermMetricDaily, TermAssocDaily, Product,
              ProductSource, ProductSourceSnapshot, ResaleSnapshot)
    with connection.cursor() as c:
        for model in models:
            raw = model._meta.db_table.replace('"', "")
            schema, _, tbl = raw.rpartition(".")
            try:
                c.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s", [schema or "public", tbl])
                have = {r[0] for r in c.fetchall()}
            except Exception as exc:  # noqa: BLE001
                out[raw] = {"missing": ["(표를 못 읽음)"], "error": str(exc)[:120]}
                continue
            if not have:
                out[raw] = {"missing": ["(표 자체가 없음)"]}
                continue
            gap = sorted({f.column for f in model._meta.concrete_fields} - have)
            if gap:
                out[raw] = {"missing": gap}
    return out


@require_GET
def health(request):
    """붙었는지, 표마다 몇 행인지, 모델과 어긋나지 않는지."""
    mismatch = _column_mismatch()
    counts = {}
    for label, model in (
        ("dictionary.dictionary_term", DictionaryTerm),
        ("commerce.product_source", ProductSource),
        ("snapshot.product_source_snapshot", ProductSourceSnapshot),
        ("snapshot.resale_snapshot", ResaleSnapshot),
        ("analysis.term_metric_daily", TermMetricDaily),
        ("analysis.term_assoc_daily", TermAssocDaily),
    ):
        try:
            counts[label] = model.objects.count()
        except Exception as exc:  # noqa: BLE001
            counts[label] = f"error: {str(exc)[:80]}"
    latest = None
    try:
        latest = TermMetricDaily.objects.aggregate(d=Max("metric_date"))["d"]
    except Exception:  # noqa: BLE001
        pass
    # 지표 표가 어떤 모양으로 적재돼 있는지 — 합산 행(source 없음)·버전·용어당 날짜 수
    metric_shape = None
    try:
        tm = TermMetricDaily.objects
        per_term = (tm.values("term_id").annotate(n=Count("metric_date", distinct=True))
                    .order_by("-n"))
        metric_shape = {
            "rows_all_sources": tm.filter(source__isnull=True).count(),
            "rows_by_source": {(r["source__code"] or "ALL"): r["n"] for r in
                               tm.values("source__code").annotate(n=Count("id"))},
            "versions": {r["metric_version"]: r["n"] for r in
                         tm.values("metric_version").annotate(n=Count("id"))},
            "terms": per_term.count(),
            "max_days_per_term": per_term[0]["n"] if per_term else 0,
            "dates": list(tm.values_list("metric_date", flat=True).distinct().order_by("metric_date")[:40]),
            "filled": {
                "trend_temperature": tm.filter(trend_temperature__isnull=False).count(),
                "level": tm.filter(level__isnull=False).count(),
                "momentum": tm.filter(momentum__isnull=False).count(),
                "purchase_intent_index": tm.filter(purchase_intent_index__isnull=False).count(),
                "positive_rate": tm.filter(positive_rate__isnull=False).count(),
            },
            "sample_terms": list(per_term.values_list("term__canonical_name", "term__term_type", "n")[:10]),
        }
    except Exception as exc:  # noqa: BLE001
        metric_shape = {"error": str(exc)[:200]}

    # 핵심 스타일 10종이 사전·스타일 표·상품 태그에 실제로 있는지
    core_styles = []
    try:
        from apps.core.models import Style
        for name in _core_styles():
            term = DictionaryTerm.objects.filter(term_type="STYLE", canonical_name=name).first()
            style = Style.objects.filter(term=term).first() if term else None
            core_styles.append({
                "style": name,
                "in_dictionary": term is not None,
                "is_core_flag": (style.is_core if style else None),
                "tagged_products": (ProductTerm.objects.filter(term=term)
                                    .values("product_source_id").distinct().count() if term else 0),
            })
    except Exception as exc:  # noqa: BLE001
        core_styles = [{"error": str(exc)[:200]}]

    bits = []
    if mismatch:
        bits.append("★ 모델과 실제 DB 가 어긋납니다: " + " / ".join(
            f"{k}: {', '.join(v.get('missing') or [])}" for k, v in mismatch.items()))
    bits.append(f"트렌드 지표 {counts.get('analysis.term_metric_daily')}행 (최신 {latest}).")
    return JsonResponse({
        "ok": True,
        "checked_at": timezone.now().isoformat(),
        "tables": counts,
        "latest_metric_date": latest,
        "metric_version": _metric_version(),
        "column_mismatch": mismatch or None,
        "core_styles": core_styles,
        "metric_shape": metric_shape,
        "verdict": " ".join(bits),
    })


HOT_MIN_ACTIVE_28 = 7   # 최근 28일 중 언급된 날이 이보다 적으면 순위에서 뺀다 (하루 튄 용어 방지)
HOT_RULE = ("최근 7일 평균(ma7)이 28일 평균(ma28)보다 얼마나 높은지(%)로 줄 세웁니다. "
            f"최근 28일 중 {HOT_MIN_ACTIVE_28}일 이상 언급된 용어만 올립니다.")


# ★ 2026-10-01 — 홈 HOT TREND 는 **매일 다시 계산되는 버전**을 읽는다.
#   매일 04:10 core.refresh_text_signals_daily 가 최근 35일을 이 버전으로 다시 쓴다
#   (analysis/text_signals/metrics.py METRIC_VERSION). 운영 .env 의
#   FEEDIT_METRIC_VERSION 이 있으면 그쪽을 따른다 — 트렌드 분석 화면의 기본 버전과 같은 값이다.
HOT_DAILY_BASIS_NOTE = ("유튜브 댓글·영상 설명·커머스 리뷰를 합친 지표입니다. "
                        "매일 새벽 최근 35일을 다시 계산합니다.")


def _hot_source():
    """(행 묶음, 기준 설명) — 매일 갱신 버전의 전 플랫폼 합산 행. 없을 때만 장기 이력."""
    # 분석 패키지는 다른 곳(apps/core/tasks.py)처럼 쓰는 자리에서 불러온다.
    from analysis.text_signals.metrics import METRIC_VERSION as DAILY_METRIC_VERSION
    version = (os.getenv("FEEDIT_METRIC_VERSION") or DAILY_METRIC_VERSION).strip()
    daily = TermMetricDaily.objects.filter(metric_version=version, source__isnull=True)
    if daily.exists():
        return daily, {"source": "ALL", "metric_version": version,
                       "refresh": "daily", "note": HOT_DAILY_BASIS_NOTE}
    hist = TermMetricDaily.objects.filter(
        metric_version=HISTORY_VERSION, source__code__iexact=HISTORY_SOURCE)
    return hist, {**HISTORY_BASIS, "refresh": "manual"}


def _hot_terms(request):
    """GET /api/trend?rank=hot — 홈 HOT TREND TOP 10.

    지표는 다시 계산하지 않고 적재된 ma7·ma28 을 그대로 읽어 변화율만 낸다.

    ★ 2026-10-01 — 예전엔 장기 이력 버전(feedit-yt-history-v1)을 읽었다. 그 버전은
      2026-09-19 에 한 번 적재한 백필이라 **2026-09-08 에 멈춰** 있었고, 홈의 순위가
      3주 넘게 같은 목록(배럴레그 · 플랫슈즈 …)이었다. 이제 매일 다시 계산되는 버전의
      합산 행(source 없음)을 읽는다(_hot_source). 그 버전에 행이 없을 때만 장기 이력으로 간다.
    """
    limit = _int(request, "limit", 10, 1, 30)
    base, basis = _hot_source()
    as_of = base.aggregate(d=Max("metric_date"))["d"]
    if not as_of:
        return _empty("순위를 낼 지표가 아직 없습니다.")
    active = dict(
        base.filter(metric_date__gt=as_of - timedelta(days=28))
        .values("term_id").annotate(n=Count("id")).values_list("term_id", "n"))
    latest = (
        base.filter(metric_date__gt=as_of - timedelta(days=3),
                    term_id__in=[k for k, v in active.items() if v >= HOT_MIN_ACTIVE_28])
        .exclude(term__status="INACTIVE")
        .order_by("term_id", "-metric_date").distinct("term_id")
        .values("term_id", "term__canonical_name", "term__term_type", "metric_date",
                "ma7", "ma28", "trend_temperature")
    )
    rows = []
    for r in latest:
        ma7, ma28 = _num(r["ma7"]), _num(r["ma28"])
        if not ma28:
            continue
        rows.append({
            "term": r["term__canonical_name"], "facet": r["term__term_type"],
            "change_pct": round((ma7 / ma28 - 1) * 100),
            "temp": _num(r["trend_temperature"]),
            "active_days_28": active.get(r["term_id"], 0),
            "date": r["metric_date"].isoformat(),
        })
    rising = sorted((x for x in rows if x["change_pct"] > 0), key=lambda x: -x["change_pct"])
    falling = sorted((x for x in rows if x["change_pct"] < 0), key=lambda x: x["change_pct"])
    return _ok({
        "as_of": as_of.isoformat(),
        "basis": basis,
        "rule": HOT_RULE,
        "rising": rising[:limit],
        "falling": falling[:limit],
    })


@require_GET
def terms(request):
    """지표가 실제로 있는 용어 목록 — 화면의 검색 후보. ?rank=hot 이면 HOT 순위."""
    if (request.GET.get("rank") or "").strip() == "hot":
        return _hot_terms(request)
    ver = _metric_version()
    qs = (
        TermMetricDaily.objects.filter(source__isnull=True, metric_version=ver)
        .values("term__canonical_name", "term__term_type")
        .annotate(points=Count("id"), last_date=Max("metric_date"))
        # 적재 초기에는 용어당 하루치뿐일 수 있다 — 하루라도 있으면 목록에 올린다.
        .filter(points__gte=1)
        .order_by("-points", "term__canonical_name")[: _int(request, "limit", 300, 1, MAX_LIMIT)]
    )
    rows = list(qs)
    if not rows:
        return _empty("지표가 있는 용어가 아직 없습니다. analysis.term_metric_daily 적재를 확인하세요.")
    return _ok([
        {"term": r["term__canonical_name"], "facet": r["term__term_type"],
         "points": r["points"], "last_date": r["last_date"]}
        for r in rows
    ])


@require_GET
def dictionary(request):
    """GET /api/dictionary — 화면 검색이 쓸 사전 전체 (용어 + 브랜드)."""
    limit = _int(request, "limit", 6000, 1, 12000)
    rows, seen = [], set()
    for r in DictionaryTerm.objects.filter(status="ACTIVE").values(
            "canonical_name", "term_type", "english_name")[:limit]:
        key = (r["canonical_name"], r["term_type"])
        if not r["canonical_name"] or key in seen:
            continue
        seen.add(key)
        rows.append({"label": r["canonical_name"],
                     "facet": FACET_KO.get(r["term_type"], r["term_type"]),
                     "kind": "brand" if r["term_type"] == "BRAND" else "term",
                     "en": r["english_name"] or ""})
    # 용어로 아직 연결 안 된 브랜드도 검색은 되게 한다.
    for r in Brand.objects.filter(status="ACTIVE").values("name", "english_name")[:limit]:
        if r["name"] and (r["name"], "BRAND") not in seen:
            seen.add((r["name"], "BRAND"))
            rows.append({"label": r["name"], "facet": "브랜드", "kind": "brand",
                         "en": r["english_name"] or ""})
    if not rows:
        return _empty("사전이 비어 있습니다. dictionary_term·brand 적재를 확인하세요.")
    by_facet = defaultdict(int)
    for r in rows:
        by_facet[r["facet"]] += 1
    return _ok(rows, counts=dict(by_facet), total=len(rows))


# ══════════════════════════════════════════════════════════════
#  언급량·온도 / 긍부정  — analysis.term_metric_daily
# ══════════════════════════════════════════════════════════════

METRIC_VALUES = (
    "metric_date", "raw_count", "mention_count", "document_count", "content_count",
    "creator_count", "log_count", "percentile", "level", "ma7", "ma28", "momentum",
    "trend_temperature", "sentiment_avg",
    "positive_count", "neutral_count", "negative_count",
    "question_count", "purchase_count", "experience_count", "praise_count",
    "critique_count", "chitchat_count",
    "positive_rate", "neutral_rate", "negative_rate",
    "question_rate", "purchase_rate", "experience_rate", "praise_rate", "critique_rate",
    "purchase_intent_index", "metrics",
)


def _metric_point(r, share=None):
    """DB 한 행 → 화면이 쓰는 이름. (예전 화면이 쓰던 temp·mention 이름을 유지)"""
    return {
        "date": r["metric_date"].isoformat(),
        "mention": r["mention_count"],
        "document": r["document_count"],
        "content": r["content_count"],
        "creator": r["creator_count"],
        "raw": _num(r["raw_count"]),
        "log": _num(r["log_count"]),
        "pct_rank": _num(r["percentile"]),
        "level": _num(r["level"]),
        "ma7": _num(r["ma7"]),
        "ma28": _num(r["ma28"]),
        "momentum": _num(r["momentum"]),
        "temp": _num(r["trend_temperature"]),
        "sentiment": _num(r["sentiment_avg"]),
        "share_pct": share,
        # 긍부정
        "pos_n": r["positive_count"], "neu_n": r["neutral_count"], "neg_n": r["negative_count"],
        "pos_rate": _num(r["positive_rate"]), "neu_rate": _num(r["neutral_rate"]),
        "neg_rate": _num(r["negative_rate"]),
        # 의도
        "question_n": r["question_count"], "purchase_n": r["purchase_count"],
        "experience_n": r["experience_count"], "praise_n": r["praise_count"],
        "critique_n": r["critique_count"], "chitchat_n": r["chitchat_count"],
        "intent": _num(r["purchase_intent_index"]),
    }


def _term_series(term, days, source=None, version=None):
    """용어 하나의 일별 지표. source=None 이면 전체 합산 행."""
    since = timezone.localdate() - timedelta(days=days)
    version = version or _metric_version(term.id)
    qs = TermMetricDaily.objects.filter(term=term, metric_version=version)
    # 최신 적재일이 오늘보다 한참 전일 수 있다 → 기준을 '마지막 적재일'로 잡는다.
    last = qs.filter(source__isnull=True).aggregate(d=Max("metric_date"))["d"]
    if last:
        since = min(since, last - timedelta(days=days))
    qs = qs.filter(metric_date__gte=since)
    qs = qs.filter(source__code=source) if source else qs.filter(source__isnull=True)
    return list(qs.order_by("metric_date").values(*METRIC_VALUES)), version


@require_GET
def trend(request):
    """GET /api/trend?term=발레코어&days=120&source=musinsa

    반환: series(일별), platforms(플랫폼별 최신 온도), new_terms(최근 새로 잡힌 용어)
    """
    name = (request.GET.get("term") or "").strip()
    if not name:
        return terms(request)
    days = _int(request, "days", 120, 7, 730)
    source = (request.GET.get("source") or "").strip() or None

    term = _resolve_term(name)
    if term is None:
        return _empty(_term_missing_reason(name), term=name, known=False)

    rows, version = _term_series(term, days, source)
    if not rows:
        return _empty(
            f"‘{term.canonical_name}’ 은 사전에 있지만 측정된 지표가 아직 없습니다.",
            term=term.canonical_name, known=True)

    # 점유율 — 같은 날 전체(합산 행) 언급량 중 이 용어의 몫
    dates = [r["metric_date"] for r in rows]
    totals = dict(
        TermMetricDaily.objects.filter(
            source__isnull=True, metric_version=version,
            metric_date__gte=dates[0], metric_date__lte=dates[-1])
        .values_list("metric_date").annotate(t=Sum("mention_count"))
    )
    series = []
    for r in rows:
        tot = totals.get(r["metric_date"]) or 0
        share = round(r["mention_count"] / tot * 100, 2) if tot else None
        series.append(_metric_point(r, share))

    last_date = rows[-1]["metric_date"]

    # 추이 — 합산 이력이 28일보다 짧으면 장기 이력(YouTube)으로 그린다.
    # 플랫폼별 온도 · 새 용어는 아래에서 그대로 기존 버전(version)을 쓴다.
    series_basis = None
    if source is None and len(rows) < HISTORY_MIN_POINTS:
        hist = _history_series(term, days)
        if len(hist) > len(rows):
            series = [_metric_point(r, (r.get("metrics") or {}).get("share_pct")) for r in hist]
            series_basis = HISTORY_BASIS

    # 플랫폼별 최신 온도
    #  ★ 2026-09-21 — 커머스(무신사·지그재그·에이블리·크림)가 한 줄도 안 뜼던 이유가
    #    여기 두 줄에 있었다. 적재는 돼 있었고(rows_by_source: musinsa 3601,
    #    zigzag 1634, ABLY 202, kream 118), 읽는 쪽이 못 집었다.
    #    ① 창이 14일이었다. 리뷰 문서의 기준일은 '리뷰가 쓰인 날'이라
    #       metric_date 가 과거로 횩어진다(예: 팬츠 × 무신사 최신 행 = 2026-07-09).
    #       합산 기준일이 9/21 이면 14일 창 밖으로 전부 떨어졌다.
    #    ② 용어의 대표 버전(version)으로 못을 박고 있었다. 커머스 행이 다른
    #       버전(feedit-l2-v2 등)에 들어가 있으면 통째로 걸러졌다.
    #    → 이력 버전만 빼고 소스별 '가장 최근 행'을 집는다. 단, 값이 오래됐다는
    #      사실을 감추지 않는다 — date·days_ago·stale·metric_version 을 같이 보낸다.
    #      화면은 stale 이 true 면 날짜를 병기해야 한다. "70도"만 띄우면 거짓말이 된다.
    plat_rows = (
        TermMetricDaily.objects
        .filter(term=term, source__isnull=False,
                metric_date__gte=last_date - timedelta(days=_platform_window()))
        .exclude(metric_version=HISTORY_VERSION)
        # ★ 2026-09-22 — 같은 소스에 여러 버전이 있으면 **지금 버전을 먼저** 집는다.
        #   옛 버전(feedit-l2-v2)은 mention_count 가 0 인데 trend_temperature 만 차 있다.
        #   그 행이 이기면 화면에 "무신사 82.51도 · 언급 0건" 이 뜬다 — 거짓말이다.
        #   지금 버전에 행이 있으면 그쪽을, 없을 때만 옛 버전을 쓴다.
        .annotate(_ver_rank=Case(When(metric_version=version, then=Value(0)),
                                 default=Value(1), output_field=IntegerField()))
        .order_by("source_id", "_ver_rank", "-metric_date")
        .values("source__code", "source__name", "metric_date", "trend_temperature",
                "level", "mention_count", "metric_version")
    )
    platforms, seen = [], set()
    for p in plat_rows:
        if p["source__code"] in seen:
            continue
        seen.add(p["source__code"])
        age = (last_date - p["metric_date"]).days
        platforms.append({"code": p["source__code"], "name": p["source__name"],
                          "date": p["metric_date"].isoformat(),
                          "days_ago": age, "stale": age > STALE_AFTER_DAYS,
                          "metric_version": p["metric_version"],
                          # 지금 버전이 아니면 화면이 조심해서 다뤄야 한다.
                          "legacy": p["metric_version"] != version,
                          "temp": _num(p["trend_temperature"]), "level": _num(p["level"]),
                          "mention": p["mention_count"]})
    platforms.sort(key=lambda x: (x["temp"] is None, -(x["temp"] or 0)))

    # 최근 7일 안에 처음 잡힌 용어 (같은 축) — 온도 높은 순
    first_seen = (
        TermMetricDaily.objects.filter(source__isnull=True, metric_version=version,
                                       term__term_type=term.term_type)
        .values("term_id").annotate(first=Min("metric_date"))
        .filter(first__gte=last_date - timedelta(days=7))
    )
    new_ids = [x["term_id"] for x in first_seen[:200]]
    new_terms = list(
        TermMetricDaily.objects.filter(term_id__in=new_ids, source__isnull=True,
                                       metric_version=version, metric_date=last_date)
        .order_by("-trend_temperature")
        .values("term__canonical_name", "trend_temperature")[:5]
    )

    last = series[-1]
    missing = [f for f in ("temp", "momentum", "level", "intent") if last.get(f) is None]
    extra = {}
    if missing:
        extra["unavailable"] = {
            "fields": missing,
            "reason": f"최신 행에 비어 있는 값이 있습니다 ({'·'.join(missing)}).",
        }
    return _ok(
        {
            "term": term.canonical_name,
            "facet": term.term_type,
            "source": source,
            "days": days,
            "points": len(series),
            "as_of": last_date.isoformat(),
            "data_as_of": _data_as_of(),
            "metric_version": version,
            "series": series,
            "series_as_of": series[-1]["date"] if series else None,
            "series_basis": series_basis,
            "platforms": platforms,
            "new_terms": [{"term": x["term__canonical_name"],
                           "temp": _num(x["trend_temperature"])} for x in new_terms],
        },
        **extra,
    )


def _sentiment_evidence(term, is_brand=False, variants=None):
    """긍부정 신호 유형별 근거 문장 추출"""
    evidence = defaultdict(list)
    intents = ["QUESTION", "PURCHASE", "EXPERIENCE", "PRAISE", "CRITIQUE", "CHITCHAT"]

    if is_brand:
        docs = TextDocument.objects.filter(
            document_type=TextDocument.DocumentType.COMMENT
        ).filter(_contains_any("body", variants)).values_list("id", flat=True)[:2000]
        qs = TextTermMention.objects.filter(
            document_id__in=docs, intent_code__in=intents
        ).exclude(mention_text__isnull=True).filter(_contains_any("mention_text", variants))
    else:
        qs = TextTermMention.objects.filter(
            term=term, document__document_type__in=SENTIMENT_DOC_TYPES,
            intent_code__in=intents
        ).exclude(mention_text__isnull=True)

    rows = (
        qs.order_by("-created_at")
        .values("intent_code", "mention_text", "document__source__name", "document__document_type")[:1000]
    )

    for row in rows:
        intent = str(row["intent_code"]).upper()
        if not intent or intent == "NONE":
            continue
        bucket = evidence[intent]
        if len(bucket) < 2:
            bucket.append({
                "tag": row["document__source__name"] or row["document__document_type"],
                "text": row["mention_text"][:160],
            })
    return evidence


@require_GET
def sentiment(request):
    """GET /api/sentiment?term=셔츠&days=400&subject=term|brand.

    사전 용어는 TextTermMention의 해당 term 분석을 직접 집계한다.
    브랜드는 아직 DictionaryTerm(BRAND)이 없으므로 브랜드 표기가 실제 포함된
    mention 문맥만 모아 '브랜드 언급 문맥 반응'으로 제공한다.
    """
    name = (request.GET.get("term") or "").strip()
    if not name:
        return _empty("term 을 지정해 주세요. 예: /api/sentiment?term=셔츠")
    days = _int(request, "days", 400, 7, 730)
    requested_kind = (request.GET.get("subject") or request.GET.get("kind") or "").strip().lower()
    term = None if requested_kind == "brand" else _resolve_term(name)

    method = "TERM_MENTION"
    facet = None
    canonical = name
    if term is not None:
        canonical = term.canonical_name
        facet = term.term_type
        mention_rows = list(
            TextTermMention.objects.filter(
                term=term,
                document__document_type__in=SENTIMENT_DOC_TYPES,
                sentiment_score__isnull=False,
            ).values(
                "document_id", "document__analysis_metadata", "document__source_published_at",
                "sentiment_score", "intent_code"
            )
        )
        matched_comments = len({row["document_id"] for row in mention_rows})
    else:
        brand = _resolve_brand(name)
        if brand is None:
            return _empty(
                f"‘{name}’ 을 활성 사전이나 브랜드 표에서 찾지 못했습니다.",
                term=name, known=False,
            )
        canonical = brand.name or brand.english_name or name
        facet = "BRAND"
        method = "BRAND_CONTEXT"
        variants = _brand_variants(brand)
        if not variants:
            return _empty(
                f"‘{canonical}’ 은 브랜드이지만 댓글에서 안전하게 찾을 수 있는 표기가 없습니다.",
                term=canonical, known=True,
            )
        documents = list(
            TextDocument.objects.filter(document_type=TextDocument.DocumentType.COMMENT)
            .filter(_contains_any("body", variants))
            .values("id", "analysis_metadata")
        )
        matched_comments = len(documents)
        doc_meta = {row["id"]: row["analysis_metadata"] for row in documents}
        mention_rows = list(
            TextTermMention.objects.filter(
                document_id__in=doc_meta,
                sentiment_score__isnull=False,
            )
            .exclude(mention_text__isnull=True)
            .filter(_contains_any("mention_text", variants))
            .values("document_id", "sentiment_score", "intent_code")
        )
        for row in mention_rows:
            row["document__analysis_metadata"] = doc_meta.get(row["document_id"], {})

    series, last_date, classified_comments = _direct_sentiment_series(mention_rows, days)
    if not series:
        detail = (
            "브랜드가 언급된 댓글은 있지만 해당 문맥에 연결된 긍부정 분석행이 없습니다."
            if method == "BRAND_CONTEXT" and matched_comments
            else "댓글·리뷰에서 이 용어와 연결된 긍부정 분석행이 없습니다."
        )
        return _empty(detail, term=canonical, facet=facet, known=True)

    evidence = _sentiment_evidence(term, is_brand=(method == "BRAND_CONTEXT"), variants=variants if method == "BRAND_CONTEXT" else None)

    return _ok({
        "term": canonical,
        "facet": facet,
        "days": days,
        "points": len(series),
        "as_of": last_date.isoformat(),
        "data_as_of": _data_as_of(),
        "metric_version": "direct-text-mention-v1",
        "method": method,
        "scope_label": "브랜드 언급 문맥" if method == "BRAND_CONTEXT" else "용어 직접 언급",
        "doc_types": ["COMMENT"] if method == "BRAND_CONTEXT" else list(SENTIMENT_DOC_TYPES),
        "matched_comments": matched_comments,
        "classified_comments": classified_comments,
        "series": series,
        "evidence": dict(evidence),
    })


# ══════════════════════════════════════════════════════════════
#  연관어 — analysis.term_assoc_daily
# ══════════════════════════════════════════════════════════════

def _analysis_tag_term_map():
    """콘텐츠 JSON 태그의 표기 → 공통 DictionaryTerm ID.

    새 분석이나 외부 호출은 하지 않는다. 표준명·정규화명·검수된 별칭만 연결한다.
    같은 표기가 여러 활성 용어에 걸리면 먼저 확정된 표준 용어 하나만 사용한다.
    """
    terms = list(
        DictionaryTerm.objects.exclude(status="INACTIVE")
        .values("id", "canonical_name", "normalized_name", "term_type")
    )
    by_id = {row["id"]: row for row in terms}
    by_name = {}
    for row in terms:
        for value in (row["canonical_name"], row["normalized_name"]):
            key = _norm(value)
            if key:
                by_name.setdefault(key, row["id"])
    for alias in TermAlias.objects.filter(term_id__in=by_id).values(
        "term_id", "alias", "normalized_alias"
    ):
        for value in (alias["alias"], alias["normalized_alias"]):
            key = _norm(value)
            if key:
                by_name.setdefault(key, alias["term_id"])
    return by_name, by_id


def _tag_values(value):
    """analysis_tags의 현재/과거 JSON 모양에서 문자열 태그만 꺼낸다."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _tag_values(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not str(key).startswith("_"):
                yield from _tag_values(item)


def _assoc_evidence(source_term, target_ids):
    """실제 같은 문서 안에서 찾은 대상 용어 문맥만 근거로 돌려준다."""
    evidence = defaultdict(list)
    if not target_ids:
        return evidence
    doc_ids = TextTermMention.objects.filter(term=source_term).values("document_id")
    rows = (
        TextTermMention.objects.filter(term_id__in=target_ids, document_id__in=doc_ids)
        .exclude(mention_text__isnull=True).exclude(mention_text="")
        .order_by("-created_at")
        .values("term_id", "mention_text", "document__document_type", "document__source__name")[:1500]
    )
    for row in rows:
        bucket = evidence[row["term_id"]]
        if len(bucket) < 2:
            bucket.append({
                "tag": row["document__source__name"] or row["document__document_type"],
                "text": row["mention_text"][:160],
            })
    return evidence


def _direct_assoc(term, limit):
    """적재 지표 없이 기존 DB의 공통 키만으로 연관 용어를 찾는다.

    - 문서: 같은 TextDocument의 TextTermMention
    - 상품: 같은 ProductSource의 ProductTerm (표준 상품 style도 기준 용어로 인정)
    - 콘텐츠: 같은 ContentItem.analysis_tags JSON

    서로 단위가 다른 세 개의 수를 새 지표처럼 합성하지 않는다. 화면 호환용
    cooccurrence는 '공통 레코드 수 합계'이고, 원천별 수를 sources에 함께 공개한다.
    """
    stats = defaultdict(lambda: {"documents": 0, "products": 0, "contents": 0})

    source_docs = TextTermMention.objects.filter(term=term).values("document_id")
    for row in (
        TextTermMention.objects.filter(document_id__in=source_docs)
        .exclude(term=term)
        .values("term_id")
        .annotate(n=Count("document_id", distinct=True))
    ):
        stats[row["term_id"]]["documents"] = row["n"]

    source_products = (
        ProductSource.objects.filter(product_terms__term=term)
        .values("id")
        .distinct()
    )
    for row in (
        ProductTerm.objects.filter(product_source_id__in=source_products)
        .exclude(term=term)
        .values("term_id")
        .annotate(n=Count("product_source_id", distinct=True))
    ):
        stats[row["term_id"]]["products"] = row["n"]

    by_name, term_rows = _analysis_tag_term_map()
    source_id = term.id
    content_matches = 0
    for row in ContentItem.objects.exclude(analysis_tags={}).values("analysis_tags").iterator(chunk_size=500):
        ids = {
            by_name[key]
            for raw in _tag_values(row["analysis_tags"])
            if (key := _norm(raw)) in by_name
        }
        if source_id not in ids:
            continue
        content_matches += 1
        for target_id in ids - {source_id}:
            stats[target_id]["contents"] += 1

    ranked = []
    for target_id, sources in stats.items():
        total = sum(sources.values())
        if total:
            ranked.append((target_id, total, sum(1 for value in sources.values() if value), sources))
    ranked.sort(key=lambda row: (-row[1], -row[2], term_rows.get(row[0], {}).get("canonical_name", "")))
    ranked = ranked[:limit]
    evidence = _assoc_evidence(term, [row[0] for row in ranked])

    items = []
    for rank, (target_id, total, _, sources) in enumerate(ranked, 1):
        target = term_rows.get(target_id)
        if not target:
            continue
        items.append({
            "term": target["canonical_name"],
            "facet": target["term_type"],
            "facet_ko": FACET_KO.get(target["term_type"], target["term_type"]),
            "cooccurrence": total,
            "lift": None,
            "pmi": None,
            "percentile": None,
            "rank": rank,
            "change": None,
            "sources": sources,
            "evidence": evidence.get(target_id, []),
        })
    return {
        "term": term.canonical_name,
        "as_of": timezone.localdate().isoformat(),
        "previous": None,
        "metric_version": None,
        "method": "DIRECT_SHARED_KEYS",
        "scope_label": "기존 DB 공통 키 직접 연결",
        "items": items,
        "history": [],
        "source_records": {
            "documents": TextTermMention.objects.filter(term=term).values("document_id").distinct().count(),
            "products": source_products.count(),
            "contents": content_matches,
        },
    }

@require_GET
def assoc(request):
    """GET /api/assoc?term=발레코어&limit=60&days=90

    items   최근 28일의 연관어 (일별 동시언급 합·평균 lift/PMI·최고 백분위·순위 변화·근거 문장)
    history 기준일별 연관어 수와 동시언급 문서 합 — 추이 차트
    """
    name = (request.GET.get("term") or "").strip()
    if not name:
        return _empty("term 을 지정해 주세요. 예: /api/assoc?term=발레코어")
    term = _resolve_term(name)
    if term is None:
        return _empty(_term_missing_reason(name), term=name)
    # 화면은 축별 10개까지만 보존한 뒤 상위 5개를 펼친다.
    # API에서 먼저 잘라 버리면 TPO처럼 행이 적은 축이나 토트백 같은 후순위
    # 연관어가 화면의 '더 보기'에도 들어오지 못한다. 화면이 Top 5를 접어 둔다.
    limit = _int(request, "limit", 200, 5, 200)
    days = _int(request, "days", 120, 7, 730)

    # ★ 2026-09-21 — 연관어 출처가 두 갈래가 됐다.
    #   TEXT    같은 문서 안에서 함께 언급 (유튜브 댓글 · 커머스 리뷰)
    #   SEARCH  같은 검색에서 함께 찾음 (구글 related queries · 네이버 연관검색어)
    #
    #   섞을 때 lift·PMI 로 줄 세우면 안 된다 — 문서 통계라 검색 쪽엔 없는 값이고,
    #   있더라도 단위가 다르다. 비교 가능한 건 association_percentile 하나뿐이다
    #   — 각 소스 **안에서의** 상대순위라 단위가 없다.
    #
    #   점수 = 지지 문서 수로 보정한 높은 쪽 백분위 + (양쪽에 다 잡혔으면 +10)
    #   두 소스가 같은 말을 가리키면 그게 가장 믿을 만한 연관어라는 뜻이다.
    ASSOC_BOTH_BONUS = 10
    ASSOC_WINDOW_DAYS = 28

    sort_method = request.GET.get("sort", "pmi")

    def _window_rank(rows, basis_value):
        """28일 집계 행의 화면 순위. SEARCH와 TEXT 모두 비교 가능한 백분위를 먼저 본다."""
        for row in rows:
            percentile = _num(row.get("association_percentile")) or 0.0
            support = max(0, int(row.get("cooccurrence_count") or 0))
            # 하루 문서 1~2건에서 백분위 100을 받은 말이 28일 대표 연관어 1위로
            # 튀지 않게 TEXT만 지지 문서 수로 완만하게 보정한다. SEARCH는 횟수가
            # 아니라 related-query 순위라 cooccurrence=0이어도 보정하지 않는다.
            support_weight = (min(1.0, math.log1p(support) / math.log(11))
                              if basis_value == TermAssocDaily.Basis.TEXT else 1.0)
            row["_rank_score"] = percentile * support_weight
        if sort_method == "cooc":
            rows.sort(key=lambda r: (-(r["cooccurrence_count"] or 0),
                                     -(_num(r["pmi"]) or 0),
                                     r["target_term__canonical_name"]))
        else:
            rows.sort(key=lambda r: (-r["_rank_score"],
                                     -(_num(r["pmi"]) or 0),
                                     -(r["cooccurrence_count"] or 0),
                                     r["target_term__canonical_name"]))
        for rank, row in enumerate(rows, 1):
            row["association_rank"] = rank
        return rows

    def _basis_rows(basis_value):
        """basis 하나의 최근 28일 집계 + 같은 방식으로 계산한 직전 28일 집계."""
        qs = TermAssocDaily.objects.filter(source_term=term, basis=basis_value)
        # feedit-l2는 여러 날짜의 결과를 한 번에 담은 누적 스냅샷이라 추이용
        # 버전으로 고르면 관측일이 하루뿐이 된다. TEXT는 일별 버전을 우선하고,
        # 일별 적재가 전혀 없는 용어만 누적 스냅샷으로 대체한다.
        latest_row = None
        if basis_value == TermAssocDaily.Basis.TEXT:
            latest_row = qs.exclude(metric_version__startswith="feedit-l2-").order_by(
                "-metric_date", "-id").values("metric_date", "metric_version").first()
        if latest_row is None:
            latest_row = qs.order_by("-metric_date", "-id").values(
                "metric_date", "metric_version").first()
        if latest_row is None:
            return [], None, None, [], False
        newest = latest_row["metric_date"]
        version = latest_row["metric_version"]
        qs = qs.filter(metric_version=version)

        def aggregate(window_qs):
            rows = list(window_qs.values(
                "target_term_id", "target_term__canonical_name", "target_term__term_type",
            ).annotate(
                cooccurrence_count=Sum("cooccurrence_count"),
                lift=Avg("lift"),
                pmi=Avg("pmi"),
                association_percentile=Max("association_percentile"),
                first_seen=Min("metric_date"),
                last_seen=Max("metric_date"),
            ))
            return _window_rank(rows, basis_value)

        current_start = newest - timedelta(days=ASSOC_WINDOW_DAYS - 1)
        current_qs = qs.filter(metric_date__range=(current_start, newest))
        got = aggregate(current_qs)
        for row in got:
            row["_recent_cooccurrence"] = row.get("cooccurrence_count") or 0
            row["_recent_rank_score"] = row.get("_rank_score") or 0.0
            row["_recent_signal"] = True

        # feedit-l2-v1은 문서·상품·콘텐츠 전체를 한 번에 집계한 누적 기준선이다.
        # 일별 파이프라인으로 바뀐 뒤에도 시티보이·데님블루처럼 안정적으로 함께
        # 나타난 용어를 잃지 않도록, TEXT에서는 가장 최근 누적 스냅샷을 합친다.
        legacy_base = None
        legacy = []
        if basis_value == TermAssocDaily.Basis.TEXT:
            legacy_base = TermAssocDaily.objects.filter(
                source_term=term, basis=basis_value,
                metric_version__startswith="feedit-l2-",
            ).order_by("-metric_date", "-id").values("metric_date", "metric_version").first()
            if legacy_base and legacy_base["metric_version"] != version:
                legacy = list(TermAssocDaily.objects.filter(
                    source_term=term, basis=basis_value,
                    metric_version=legacy_base["metric_version"],
                    metric_date=legacy_base["metric_date"],
                ).values(
                    "target_term_id", "target_term__canonical_name", "target_term__term_type",
                    "cooccurrence_count", "lift", "pmi", "association_rank",
                ))
        def merge_legacy(window_rows):
            if not legacy or not legacy_base:
                return window_rows
            legacy_total = max(1, len(legacy) - 1)
            by_target = {row["target_term_id"]: row for row in window_rows}
            for old in legacy:
                old_rank = old.get("association_rank") or len(legacy)
                old_pct = 100.0 if len(legacy) == 1 else 100.0 * (len(legacy) - old_rank) / legacy_total
                current = by_target.get(old["target_term_id"])
                if current is None:
                    current = {
                        **old,
                        "association_percentile": old_pct,
                        "first_seen": legacy_base["metric_date"],
                        "last_seen": legacy_base["metric_date"],
                        "_recent_cooccurrence": 0,
                        "_recent_rank_score": 0.0,
                        "_recent_signal": False,
                        "_stable_baseline": True,
                    }
                    window_rows.append(current)
                    by_target[old["target_term_id"]] = current
                else:
                    current["cooccurrence_count"] = max(
                        current.get("cooccurrence_count") or 0,
                        old.get("cooccurrence_count") or 0,
                    )
                    current["association_percentile"] = max(
                        _num(current.get("association_percentile")) or 0.0, old_pct)
                    # 누적 기준선의 PMI가 있으면 장기 특징값으로 사용한다.
                    if old.get("pmi") is not None:
                        current["pmi"] = old["pmi"]
                        current["lift"] = old["lift"]
                    current["_stable_baseline"] = True
            return _window_rank(window_rows, basis_value)

        got = merge_legacy(got)

        # 검색 근거(metrics)는 집계할 수 없는 JSON이라, 창 안의 가장 최근 행을 대표로 쓴다.
        latest_meta = {}
        for meta_row in current_qs.order_by("-metric_date", "association_rank", "id").values(
                "target_term_id", "metrics"):
            latest_meta.setdefault(meta_row["target_term_id"], meta_row["metrics"] or {})
        for row in got:
            row["metrics"] = latest_meta.get(row["target_term_id"], {})
            row["is_new"] = False

        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=ASSOC_WINDOW_DAYS - 1)
        previous_rows = aggregate(qs.filter(metric_date__range=(previous_start, previous_end)))
        had_previous = bool(previous_rows)
        for row in previous_rows:
            row["_recent_cooccurrence"] = row.get("cooccurrence_count") or 0
            row["_recent_rank_score"] = row.get("_rank_score") or 0.0
            row["_recent_signal"] = True
        previous_rows = merge_legacy(previous_rows)
        return got[:limit * 2], newest, version, previous_rows, had_previous

    text_rows, text_date, text_ver, text_prev_rows, text_had_prev = _basis_rows(TermAssocDaily.Basis.TEXT)
    srch_rows, srch_date, srch_ver, srch_prev_rows, srch_had_prev = _basis_rows(TermAssocDaily.Basis.SEARCH)

    if not text_rows and not srch_rows:
        direct = _direct_assoc(term, limit)
        if direct["items"]:
            return _ok(direct)
        total = TermAssocDaily.objects.count()
        return _empty(
            f"‘{term.canonical_name}’ 과 공통 문서·상품·콘텐츠 태그를 가진 연관 용어가 없습니다.",
            term=term.canonical_name, total_rows=total,
            source_records=direct["source_records"])

    # 화면의 기준일·추이 차트는 여전히 언급(TEXT) 쪽을 기준으로 그린다.
    base = TermAssocDaily.objects.filter(source_term=term,
                                         basis=TermAssocDaily.Basis.TEXT)
    if text_ver:
        base = base.filter(metric_version=text_ver)
    latest = max(d for d in (text_date, srch_date) if d is not None)
    prev = latest - timedelta(days=ASSOC_WINDOW_DAYS) if (text_had_prev or srch_had_prev) else None

    def merge_sources(text_basis, search_basis):
        """TEXT와 SEARCH를 동일한 통합 연관 점수 구조로 합친다."""
        result = {}
        for bucket, rows_in in (("text", text_basis), ("search", search_basis)):
            for row in rows_in:
                tid = row["target_term_id"]
                item = result.setdefault(tid, {"row": row, "bases": [], "recent_bases": [], "pct": {},
                                               "rank_score": {}, "historical_score": {},
                                               "stable": False, "meta": {}})
                item["bases"].append(bucket)
                if row.get("_recent_signal"):
                    item["recent_bases"].append(bucket)
                item["pct"][bucket] = _num(row["association_percentile"]) or 0.0
                item["rank_score"][bucket] = _num(row.get("_recent_rank_score")) or 0.0
                item["historical_score"][bucket] = _num(row.get("_rank_score")) or 0.0
                item["stable"] = item["stable"] or bool(row.get("_stable_baseline"))
                item["meta"][bucket] = row.get("metrics") or {}
                # 언급 기반 행이 있으면 그쪽을 대표로 삼는다 (lift·PMI·근거문장이 있다).
                if bucket == "text":
                    item["row"] = row
        return result

    def score_merged(source):
        ranked = []
        for tid, item in source.items():
            both = len(item["bases"]) > 1
            score = max(item["historical_score"].values() or [0.0]) + (ASSOC_BOTH_BONUS if both else 0)
            support = item["row"].get("cooccurrence_count") or 0
            ranked.append((score, support, tid, item))
        ranked.sort(key=lambda x: (
            -x[0],
            -x[1],
            -max(x[3]["historical_score"].values() or [0.0]),
            x[3]["row"]["target_term__canonical_name"],
        ))
        return ranked

    def facet_ranks(ranked):
        """화면 숫자와 같은 축 내부 순위를 만든다."""
        counts = {}
        ranks = {}
        for _, _, tid, item in ranked:
            facet = item["row"]["target_term__term_type"]
            counts[facet] = counts.get(facet, 0) + 1
            ranks[tid] = counts[facet]
        return ranks

    def cooc_facet_ranks(source):
        """누적 TEXT 동시 언급이 있는 행을 축 내부 언급량 순위로 만든다."""
        buckets = {}
        supports = {}
        for tid, item in source.items():
            total = (item["row"].get("cooccurrence_count") or 0) if "text" in item["bases"] else 0
            supports[tid] = total
            if total <= 0:
                continue
            row = item["row"]
            facet = row["target_term__term_type"]
            buckets.setdefault(facet, []).append((
                -total,
                -(_num(row.get("pmi")) or 0),
                row["target_term__canonical_name"],
                tid,
            ))
        ranks = {}
        for rows_in in buckets.values():
            rows_in.sort()
            for rank, (_, _, _, tid) in enumerate(rows_in, 1):
                ranks[tid] = rank
        return ranks, supports

    merged = merge_sources(text_rows, srch_rows)
    previous_merged = merge_sources(text_prev_rows, srch_prev_rows)
    all_scored = score_merged(merged)
    previous_scored = score_merged(previous_merged)
    feature_ranks = facet_ranks(all_scored)
    previous_feature_ranks = facet_ranks(previous_scored)
    cooc_ranks, _ = cooc_facet_ranks(merged)
    previous_cooc_ranks, _ = cooc_facet_ranks(previous_merged)

    scored = all_scored[:limit]
    rows = [item["row"] for _, _, _, item in scored]
    merged_by_id = {tid: (score, item) for score, _, tid, item in scored}

    target_ids = [r["target_term_id"] for r in rows]
    evidence = _assoc_evidence(term, target_ids)

    # 팝오버의 3주 전~이번 주 그래프. 누적 순위와 별개로 최근 활동만 보여 준다.
    # 적재 자체가 없던 주는 None, 적재는 있었지만 해당 용어가 없던 주는 0이다.
    weekly_counts = {tid: [None, None, None, None] for tid in target_ids}
    if text_date:
        weekly_start = text_date - timedelta(days=27)
        weekly_rows = list(base.filter(
            metric_date__range=(weekly_start, text_date),
            target_term_id__in=target_ids,
        ).values("target_term_id", "metric_date").annotate(
            cooc=Sum("cooccurrence_count")))
        covered_weeks = set()
        for metric_date in base.filter(
                metric_date__range=(weekly_start, text_date)).values_list(
                    "metric_date", flat=True).distinct():
            covered_weeks.add(min(3, max(0, (metric_date - weekly_start).days // 7)))
        for values in weekly_counts.values():
            for week in covered_weeks:
                values[week] = 0
        for weekly in weekly_rows:
            week = min(3, max(0, (weekly["metric_date"] - weekly_start).days // 7))
            values = weekly_counts[weekly["target_term_id"]]
            values[week] = (values[week] or 0) + (weekly["cooc"] or 0)

    items = []
    for rank, r in enumerate(rows, 1):
        tid = r["target_term_id"]
        score, item = merged_by_id.get(tid, (None, {"bases": ["text"], "meta": {}}))
        bases = item["bases"]
        feature_rank = feature_ranks.get(tid)
        feature_before = previous_feature_ranks.get(tid)
        if text_had_prev or srch_had_prev:
            feature_change = ("new" if feature_before is None and not item.get("stable")
                              else feature_before - feature_rank
                              if feature_before is not None and feature_rank is not None else None)
        else:
            feature_change = None

        recent_cooccurrence = (item["row"].get("_recent_cooccurrence") or 0) if "text" in bases else 0
        cooc_rank = cooc_ranks.get(tid)
        cooc_before = previous_cooc_ranks.get(tid)
        if "text" not in bases or not text_had_prev or cooc_rank is None:
            cooc_change = None
        elif cooc_before is None:
            cooc_change = "new"
        else:
            cooc_change = cooc_before - cooc_rank
        # 근거 문장은 언급 기반에만 있다. 검색만으로 잡힌 말은 빈칸이 되므로
        # 그 자리에 "어떤 검색 신호였는지" 를 대신 넣는다 — 빈 칸보다 낫다.
        proof = evidence.get(tid, [])
        if not proof and "search" in bases:
            meta = item["meta"].get("search") or {}
            kind = {"rising": "급상승 연관검색어", "top": "인기 연관검색어"}.get(
                meta.get("kind"), "연관검색어")
            raw = meta.get("raw_value")
            tail = ""
            if isinstance(raw, str) and raw.strip().lower() in ("breakout", "급상승"):
                tail = " · 증가율 측정 불가(급등)"
            elif raw not in (None, ""):
                tail = f" · {raw}"
            proof = [{"text": f"{meta.get('platform', '검색')} {kind}{tail}",
                      "source": meta.get("platform"), "kind": "search"}]
        items.append({
            "term": r["target_term__canonical_name"],
            "facet": r["target_term__term_type"],
            "facet_ko": FACET_KO.get(r["target_term__term_type"], r["target_term__term_type"]),
            "cooccurrence": r["cooccurrence_count"],
            "recent_cooccurrence": recent_cooccurrence,
            "lift": _num(r["lift"], 4),
            "pmi": _num(r["pmi"], 4),
            "percentile": _num(r["association_percentile"], 2),
            "rank": rank,
            "feature_rank": feature_rank,
            "feature_change": feature_change,
            "cooc_rank": cooc_rank,
            "cooc_change": cooc_change,
            "change": feature_change,
            # ★ 어느 소스에서 나온 연관어인지 — 화면은 이걸로 배지를 단다.
            #   ["text","search"] 면 두 소스가 같은 말을 가리킨 것 — 가장 믿을 만하다.
            "basis": bases,
            "recent_bases": item.get("recent_bases", []),
            "is_historical": not bool(item.get("recent_bases")),
            "weekly_counts": weekly_counts.get(tid, []),
            "score": round(score, 2) if score is not None else None,
            "evidence": proof,
        })

    hist = (
        base.filter(metric_date__gte=latest - timedelta(days=days))
        .values("metric_date")
        .annotate(count=Count("id"), cooc=Sum("cooccurrence_count"))
        .order_by("metric_date")
    )
    history = [{"date": h["metric_date"].isoformat(), "count": h["count"], "cooc": h["cooc"]}
               for h in hist]

    return _ok({
        "term": term.canonical_name,
        "as_of": latest.isoformat(),
        "data_as_of": _data_as_of(),
        "previous": prev.isoformat() if prev else None,
        "window_days": ASSOC_WINDOW_DAYS,
        "ranking_scope": "cumulative",
        "window_start": (latest - timedelta(days=ASSOC_WINDOW_DAYS - 1)).isoformat(),
        "metric_version": text_ver or srch_ver,
        "bases": {
            "text": {"as_of": text_date.isoformat() if text_date else None,
                     "metric_version": text_ver, "count": len(text_rows)},
            "search": {"as_of": srch_date.isoformat() if srch_date else None,
                       "metric_version": srch_ver, "count": len(srch_rows)},
        },
        "blend_rule": "누적 기준선과 최근 28일을 합치고, TEXT는 지지 문서 수로 보정한 뒤 양쪽 모두 잡힐 경우 +10",
        "items": items,
        "history": history,
    })


# ══════════════════════════════════════════════════════════════
#  세부 검색 조건 → 상품(플랫폼 상품) 집합
# ══════════════════════════════════════════════════════════════
#  네 칸(스타일·종류·브랜드·아이템명)은 서로 독립된 필터이고, 겹치면 교집합이다.
#  스냅샷(가격·리셀)은 commerce.product_source 에 붙으므로 그 단위로 센다.
#  (표준 상품 product 가 아직 연결 안 된 UNMAPPED 행도 빠지지 않게)

FACET_PARAMS = ("style", "kind", "brand", "item")
MIN_PRODUCTS_FOR_FACETS = 20

BRAND_EXPR = Coalesce("product__brand__name", "source_brand__brand__name", "source_brand__name")
ITEM_EXPR = Coalesce("product__canonical_name", "source_name")
CATEGORY_EXPR = Coalesce("product__category__name", "source_category__category__name", "source_category__source_category_name")

def _list(request, name):
    out, seen = [], set()
    for v in request.GET.getlist(name):
        v = (v or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _selection(request):
    return {k: _list(request, k) for k in FACET_PARAMS}


def _apply(qs, sel, skip=None):
    """고른 조건을 ProductSource 목록에 건다. `skip` 축은 뺀다(자기 축 제외)."""
    if skip != "style" and sel["style"]:
        # ★ 2026-09-21 — 스타일은 상품마다 여러 개 달린다. 연결 표(product_term)만 본다.
        #   예전 단일 FK(product.style) 갈래는 칸 자체가 없어져 떼어냈다.
        qs = qs.filter(
            id__in=ProductTerm.objects.filter(term__term_type="STYLE",
                                              term__canonical_name__in=sel["style"])
            .values("product_source_id"))
    if skip != "kind" and sel["kind"]:
        qs = qs.filter(
            Q(id__in=ProductTerm.objects.filter(term__term_type="ITEM",
                                                term__canonical_name__in=sel["kind"])
              .values("product_source_id"))
            | Q(product__category__name__in=sel["kind"])
            | Q(source_category__category__name__in=sel["kind"]))
    if skip != "brand" and sel["brand"]:
        qs = qs.filter(Q(product__brand__name__in=sel["brand"])
                       | Q(product__brand__english_name__in=sel["brand"])
                       | Q(source_brand__brand__name__in=sel["brand"])
                       | Q(source_brand__name__in=sel["brand"]))
    if skip != "item" and sel["item"]:
        qs = qs.filter(Q(product__canonical_name__in=sel["item"]) | Q(source_name__in=sel["item"]))
    return qs


def _selected_sources(sel, market=None):
    qs = _apply(ProductSource.objects.all(), sel)
    if market:
        qs = qs.filter(market_type=market)
    return qs


def _selection_term(sel, preferred=""):
    """검색 조건에서 실제 지표가 있는 대표 용어를 고른다.

    카테고리·상품명은 commerce 쪽 값이라 같은 이름의 사전 용어가 없을 수 있다.
    그때 선택 상품에 붙은 태그 중 지표 이력이 가장 많은 용어로 내려가면,
    검색 조건은 유지하면서도 빈 수명주기를 잘못 보여 주지 않는다.
    """
    candidates = [preferred]
    for key in ("item", "kind", "style", "brand"):
        candidates.extend(sel.get(key) or [])
    seen = set()
    for name in candidates:
        key = _norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        term = _resolve_term(name)
        if term:
            return term
    if not any(sel.values()):
        return None
    source_ids = _selected_sources(sel).values("id")
    return _pick_measured(
        DictionaryTerm.objects.exclude(status="INACTIVE")
        .filter(product_terms__product_source_id__in=source_ids)
        .distinct()
    )


def _selection_label(sel):
    b, i = (sel["brand"] or [None])[0], (sel["item"] or [None])[0]
    if b and i:
        return f"{b} {i}"
    for k in ("item", "brand", "kind", "style"):
        if sel[k]:
            return sel[k][0]
    return ""


def _count_rows(qs, expr, keep, limit):
    agg = (qs.annotate(_label=expr).exclude(_label__isnull=True).exclude(_label="")
           .values("_label").annotate(n=Count("id", distinct=True)).order_by("-n", "_label"))
    out = [{"label": r["_label"], "count": r["n"]} for r in agg[:limit]]
    have = {o["label"] for o in out}
    out += [{"label": k, "count": 0, "picked_only": True} for k in keep if k not in have]
    return out


def _core_style_rows(qs, keep):
    """STYLE 칸 — 핵심 스타일만, 0건도 0 으로 남긴다. 많이 걸린 순, 같으면 핵심 목록 순."""
    core = _core_styles()
    counts = dict(
        ProductTerm.objects.filter(term__term_type="STYLE", term__canonical_name__in=core,
                                   product_source_id__in=qs.values("id"))
        .values_list("term__canonical_name")
        .annotate(n=Count("product_source_id", distinct=True))
    )
    out = [{"label": name, "count": counts.get(name, 0), "core": True} for name in core]
    out.sort(key=lambda o: (-o["count"], core.index(o["label"])))
    # 다른 경로(검색창 등)로 이미 걸린 비핵심 스타일은 칩을 뗄 수 있게 남긴다.
    out += [{"label": k, "count": 0, "picked_only": True} for k in keep if k not in core]
    return out


def _recount_kind(qs, rows):
    """카테고리 칸 숫자를 클릭 시 걸리는 상품(_apply 의 kind)과 같은 기준으로 다시 센다.

    용어 연결 · 상품 카테고리 · 소스 카테고리 중 하나라도
    그 이름이면 한 번만 센다."""
    labels = [o["label"] for o in rows]
    ids = qs.values("id")
    sets = defaultdict(set)
    for name, sid in (ProductTerm.objects
                      .filter(term__term_type="ITEM", term__canonical_name__in=labels,
                              product_source_id__in=ids)
                      .values_list("term__canonical_name", "product_source_id")):
        sets[name].add(sid)
    for field in ("product__category__name", "source_category__category__name"):
        for name, sid in (qs.filter(**{field + "__in": labels}).values_list(field, "id")):
            sets[name].add(sid)
    out = [dict(o, count=len(sets[o["label"]])) for o in rows]
    out.sort(key=lambda o: (-o["count"], o["label"]))
    return out


def _term_rows(qs, term_type, keep, limit):
    ids = qs.values("id")
    agg = (ProductTerm.objects.filter(term__term_type=term_type, product_source_id__in=ids)
           .values("term__canonical_name")
           .annotate(n=Count("product_source_id", distinct=True))
           .order_by("-n", "term__canonical_name"))
    out = [{"label": r["term__canonical_name"], "count": r["n"]} for r in agg[:limit]
           if r["term__canonical_name"]]
    if term_type == "ITEM" and out:
        out = _recount_kind(qs, out)
    have = {o["label"] for o in out}
    out += [{"label": k, "count": 0, "picked_only": True} for k in keep if k not in have]
    return out


def _item_with_thumb_rows(qs, expr, keep, limit):
    out = _count_rows(qs, expr, keep, limit)
    labels = [o["label"] for o in out if not o.get("picked_only")]

    thumb_map = {}
    if labels:
        from apps.core.models import ProductSource

        # 1. Check ProductSource by product__canonical_name (fast join)
        prod_thumbs = ProductSource.objects.filter(product__canonical_name__in=labels)\
            .exclude(thumbnail_url__isnull=True).exclude(thumbnail_url="")\
            .values_list("product__canonical_name", "thumbnail_url")
        for k, v in prod_thumbs:
            if k not in thumb_map:
                thumb_map[k] = absolute_image_url(v)

        # 2. For remaining labels, check ProductSource by source_name (fast index)
        missing_labels = [L for L in labels if L not in thumb_map]
        if missing_labels:
            ps_thumbs = ProductSource.objects.filter(source_name__in=missing_labels)\
                .exclude(thumbnail_url__isnull=True).exclude(thumbnail_url="")\
                .values_list("source_name", "thumbnail_url")
            for k, v in ps_thumbs:
                if k not in thumb_map:
                    thumb_map[k] = absolute_image_url(v)

    for o in out:
        o["thumb"] = thumb_map.get(o["label"])

    return out


def _discount_product_rows(qs, query, limit, offset=0):
    """할인률 후보는 이름 집계가 아니라 실제 일반 판매 상품 ID 단위로 돌려준다."""
    qs = qs.filter(Exists(ProductSourceSnapshot.objects.filter(product_source_id=OuterRef("pk"))))
    qs = qs.annotate(_label=ITEM_EXPR, _brand=BRAND_EXPR)
    if query:
        qs = qs.filter(Q(source_name__icontains=query)
                       | Q(product__canonical_name__icontains=query)
                       | Q(_brand__icontains=query))
    rows = (qs
            .values("id", "_label", "_brand", "thumbnail_url", "source__name")
            .distinct().order_by("-id")[offset:offset + limit])
    return [{"id": row["id"], "label": row["_label"] or "상품명 없음",
             "brand": row["_brand"] or "", "source": row["source__name"],
             "thumb": absolute_image_url(row["thumbnail_url"])} for row in rows]


@require_GET
def facets(request):
    """GET /api/facets?style=스트릿&brand=스투시&limit=200 — 세부 검색 네 칸의 후보."""
    limit = _int(request, "limit", 200, 1, 1000)
    sel = _selection(request)
    base = ProductSource.objects.filter(status="ACTIVE")
    n_products = base.count()

    if n_products < MIN_PRODUCTS_FOR_FACETS:
        def dict_terms(kind):
            return [{"label": r, "count": None} for r in
                    DictionaryTerm.objects.filter(status="ACTIVE", term_type=kind)
                    .values_list("canonical_name", flat=True)[:limit] if r]
        data = {
            "style": [{"label": name, "count": None, "core": True} for name in _core_styles()],
            "kind": dict_terms("ITEM"),
            "brand": [{"label": r, "count": None} for r in
                      Brand.objects.filter(status="ACTIVE").values_list("name", flat=True)[:limit] if r],
            "item": [],
        }
        if not any(data.values()):
            return _empty("상품도 사전도 비어 있습니다.", narrowed=False, products=n_products)
        return _ok(data, matched=0, narrowed=False, products=n_products,
                   note=(f"commerce.product_source 가 {n_products}개뿐이라 축끼리 좁히지 못했습니다 "
                         "— 사전 목록을 그대로 보냅니다."))

    matched = _apply(base, sel).count()
    data = {
        "style": _core_style_rows(_apply(base, sel, "style"), sel["style"]),
        "kind": _term_rows(_apply(base, sel, "kind"), "ITEM", sel["kind"], limit),
        "brand": _count_rows(_apply(base, sel, "brand"), BRAND_EXPR, sel["brand"], limit),
        "item": _count_rows(_apply(base, sel, "item"), ITEM_EXPR, sel["item"], limit),
    }
    if not any(len(v) for v in data.values()):
        return _empty("고른 조건에 맞는 상품이 없습니다. 조건을 하나 빼고 다시 보세요.",
                      matched=0, narrowed=True)
    return _ok(data, matched=matched, narrowed=True, selected=sel, products=n_products)


@require_GET
def discount_facets(request):
    """GET /api/discount/facets?style=스트릿&brand=스투시&limit=200"""
    limit = _int(request, "limit", 200, 1, 1000)
    item_limit = _int(request, "item_limit", min(limit, 24), 1, 50)
    item_offset = _int(request, "item_offset", 0, 0, 10000)
    sel = _selection(request)
    query = (request.GET.get("q") or "").strip()
    base = ProductSource.objects.filter(market_type="RETAIL", status="ACTIVE")
    def item_page():
        # 한 건을 더 읽어 다음 페이지 유무만 확인한다. 3천 건을 세거나 URL을 보내지 않는다.
        rows = _discount_product_rows(_apply(base, sel, "item"), query,
                                      item_limit + 1, item_offset)
        return rows[:item_limit], len(rows) > item_limit

    # 입력 중에는 상품명 후보만 바뀐다. 네 축의 집계를 매 글자마다 다시 하지 않는다.
    if request.GET.get("items_only") == "1":
        rows, has_more = item_page()
        return _ok({"item": rows}, items_only=True, item_has_more=has_more,
                   item_offset=item_offset)
    n_products = base.count()

    if n_products == 0:
        return _empty("상품 데이터가 비어 있습니다.", narrowed=False, products=n_products)

    matched = _apply(base, sel).count()
    rows, has_more = item_page()
    data = {
        "style": _core_style_rows(_apply(base, sel, "style"), sel["style"]),
        "brand": _count_rows(_apply(base, sel, "brand"), BRAND_EXPR, sel["brand"], limit),
        "kind": _term_rows(_apply(base, sel, "kind"), "ITEM", sel["kind"], limit),
        "item": rows,
    }
    if not any(len(v) for v in data.values()):
        return _empty("고른 조건에 맞는 상품이 없습니다. 조건을 하나 빼고 다시 보세요.",
                      matched=0, narrowed=True)
    return _ok(data, matched=matched, narrowed=True, selected=sel, products=n_products,
               item_has_more=has_more, item_offset=item_offset)


def _temp_block(term_name, days):
    """선택 대상의 대표 용어 온도 — 할인률·리세일·수명주기 탭이 함께 쓴다."""
    term = _resolve_term(term_name) if term_name else None
    if term is None:
        return {"term": term_name or None, "status": "empty",
                "reason": (_term_missing_reason(term_name) if term_name else "대표 용어가 없습니다."),
                "series": []}
    rows, _ = _term_series(term, days)
    if not rows:
        return {"term": term.canonical_name, "status": "empty",
                "reason": f"‘{term.canonical_name}’ 의 트렌드 지표가 아직 없습니다.", "series": []}
    series = [_metric_point(r) for r in rows]
    return {"term": term.canonical_name, "facet": term.term_type, "status": "ok",
            "as_of": series[-1]["date"], "latest": series[-1], "series": series}


def _no_selection():
    return _empty("세부 검색에서 스타일·종류·브랜드·아이템명 중 하나 이상을 골라 주세요.")


# ══════════════════════════════════════════════════════════════
#  할인률 변화 — snapshot.product_source_snapshot
# ══════════════════════════════════════════════════════════════

@require_GET
def discount(request):
    """GET /api/discount?source_id=17&days=90 — 한 일반 판매 상품의 가격 기록."""
    sel = _selection(request)
    source_id = _int(request, "source_id", 0, 0, 2_147_483_647)
    source = None
    if source_id:
        source = (ProductSource.objects.filter(id=source_id, market_type="RETAIL", status="ACTIVE")
                  .select_related("source", "product", "product__brand", "source_brand").first())
        if source is None:
            return _empty("선택한 일반 판매 상품을 찾을 수 없습니다.", source_id=source_id)
    if source is None and not any(sel.values()):
        return _no_selection()
    days = _int(request, "days", 90, 14, 365)
    label = (source.source_name or source.product.canonical_name) if source else _selection_label(sel)
    term_name = (request.GET.get("term") or "").strip() or ("" if source else label)

    sources = _selected_sources(sel).filter(market_type="RETAIL") if source is None else None
    ps_ids = [source.id] if source else list(sources.values_list("id", flat=True)[:5000])
    if not ps_ids:
        return _empty(f"‘{label}’ 조건에 맞는 판매 상품이 없습니다.", label=label)

    snaps = ProductSourceSnapshot.objects.filter(product_source_id__in=ps_ids)
    last_obs = snaps.aggregate(d=Max("observed_at"))["d"]
    if last_obs is None:
        return _empty(f"‘{label}’ 상품 {len(ps_ids)}개에 가격 스냅샷이 아직 없습니다.",
                      label=label, products=len(ps_ids))
    since = last_obs - timedelta(days=days)

    rows = list(
        snaps.filter(observed_at__gte=since)
        .order_by("product_source_id", "observed_at")
        .values("product_source_id", "product_source__source__code",
                "product_source__source__name", "observed_at", "list_price", "sale_price",
                "discount_rate", "stock_status", "rating", "review_count", "like_count",
                "sales_count")[:60000]
    )

    # 상품별 최신 스냅샷 + 재입고(품절 → 판매 전환) 횟수
    latest, restock, prev_stock = {}, 0, {}
    first_disc = None
    max_disc = None
    for r in rows:
        pid = r["product_source_id"]
        d = _retail_discount_pct(r)
        r["_d"] = d
        st = (r["stock_status"] or "").upper()
        if prev_stock.get(pid) in ("SOLD_OUT", "OUT_OF_STOCK") and st and st not in ("SOLD_OUT", "OUT_OF_STOCK"):
            restock += 1
        if st:
            prev_stock[pid] = st
        if d and d > 0:
            first_disc = r["observed_at"] if first_disc is None else min(first_disc, r["observed_at"])
            max_disc = d if max_disc is None else max(max_disc, d)
        latest[pid] = r

    def plat_summary(items):
        ds = [x["_d"] for x in items if x["_d"] is not None]
        priced = [x for x in items if x["sale_price"] is not None]
        cheapest = min(priced, key=lambda x: x["sale_price"]) if priced else None
        sold = [x for x in items if (x["stock_status"] or "").upper() in ("SOLD_OUT", "OUT_OF_STOCK")]
        return {
            "products": len(items),
            "avg_discount": round(_mean(ds), 1) if ds else None,
            "max_discount": max(ds) if ds else None,
            "full_price_pct": round(sum(1 for x in ds if x <= 0) / len(ds) * 100, 1) if ds else None,
            "min_sale_price": _num(cheapest["sale_price"]) if cheapest else None,
            "min_list_price": _num(cheapest["list_price"]) if cheapest else None,
            "min_discount": cheapest["_d"] if cheapest else None,
            "sold_out": len(sold),
            "rating": round(_mean([_num(x["rating"]) for x in items]), 2)
            if any(x["rating"] is not None for x in items) else None,
            "reviews": sum(x["review_count"] or 0 for x in items),
            "likes": sum(x["like_count"] or 0 for x in items),
            "stock": dict(sorted(
                {k: sum(1 for x in items if (x["stock_status"] or "미상") == k)
                 for k in {(x["stock_status"] or "미상") for x in items}}.items(),
                key=lambda kv: -kv[1])),
        }

    by_plat = defaultdict(list)
    for r in latest.values():
        by_plat[(r["product_source__source__code"], r["product_source__source__name"])].append(r)
    platforms = []
    for (code, pname), items in by_plat.items():
        platforms.append({"code": code, "name": pname, **plat_summary(items)})
    platforms.sort(key=lambda p: (p["min_sale_price"] is None, p["min_sale_price"] or 0))

    # 일별 할인율 — 단일 상품은 하루 중 마지막 관측값, 조건 검색은 평균.
    daily = defaultdict(list)
    daily_plat = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["_d"] is None:
            continue
        day = timezone.localtime(r["observed_at"]).date().isoformat()
        if source:
            daily[day] = [r["_d"]]
            daily_plat[r["product_source__source__code"]][day] = [r["_d"]]
        else:
            daily[day].append(r["_d"])
            daily_plat[r["product_source__source__code"]][day].append(r["_d"])
    series = [{"date": d, "discount": round(_mean(v), 2)} for d, v in sorted(daily.items())]
    plat_series = {c: [{"date": d, "discount": round(_mean(v), 2)} for d, v in sorted(m.items())]
                   for c, m in daily_plat.items()}

    # 최근 2주 변화(%p)
    change_2w = None
    if series:
        last_day = series[-1]["date"]
        cut = (timezone.datetime.fromisoformat(last_day) - timedelta(days=14)).date().isoformat()
        before = [s for s in series if s["date"] <= cut]
        if before:
            change_2w = round(series[-1]["discount"] - before[-1]["discount"], 1)

    overall = plat_summary(list(latest.values()))
    cheapest = platforms[0] if platforms and platforms[0]["min_sale_price"] is not None else None
    product = None
    price_series = []
    matched_platforms = []
    if source:
        current = latest[source.id]
        # 하루에 여러 번 수집했다면 그날의 마지막 유효 판매가만 그린다.
        # 가격이 없는 날을 0원이나 직전 가격으로 채우지 않는다.
        price_by_day = {}
        for row in rows:
            sale = _num(row["sale_price"])
            if sale is None or sale <= 0:
                continue
            regular = _num(row["list_price"])
            day = timezone.localtime(row["observed_at"]).date().isoformat()
            price_by_day[day] = {
                "date": day, "sale_price": sale,
                "list_price": regular if regular is not None and regular > 0 else None,
            }
        price_series = [price_by_day[day] for day in sorted(price_by_day)]
        minimum = min(price_series, key=lambda point: point["sale_price"]) if price_series else None
        maximum = max(price_series, key=lambda point: point["sale_price"]) if price_series else None
        brand = (source.product.brand.name if source.product_id and source.product.brand_id
                 else source.source_brand.name if source.source_brand_id else "")
        # 표준 상품(product_id)이 같다고 확인된 일반 판매 상품만 가격 비교에 넣는다.
        # 현재 DB에 매칭이 한 판매처뿐이면 다른 상품을 이름으로 추측해 끼워 넣지 않는다.
        peers = ([source] if not source.product_id or source.mapping_status != "MAPPED" else
                 list(ProductSource.objects.filter(
                     product_id=source.product_id, mapping_status="MAPPED",
                     market_type="RETAIL", status="ACTIVE",
                 ).select_related("source").order_by("id")[:50]))
        if not any(peer.id == source.id for peer in peers):
            peers = peers[:49] + [source]
        peer_snapshots = {}
        for snap in (ProductSourceSnapshot.objects.filter(product_source_id__in=[peer.id for peer in peers])
                     .order_by("product_source_id", "-observed_at", "-id")
                     .distinct("product_source_id")
                     .values("product_source_id", "list_price", "sale_price", "discount_rate", "observed_at")):
            peer_snapshots[snap["product_source_id"]] = snap
        by_platform = {}
        for peer in peers:
            snap = peer_snapshots.get(peer.id)
            if not snap:
                continue
            sale = _num(snap["sale_price"])
            if sale is None or sale <= 0:
                continue
            candidate = {
                "source_id": peer.id, "name": peer.source.name,
                "sale_price": sale, "list_price": _num(snap["list_price"]),
                "discount_rate": _retail_discount_pct(snap),
                "observed_at": snap["observed_at"],
            }
            previous = by_platform.get(peer.source_id)
            if previous is None or sale < previous["sale_price"]:
                by_platform[peer.source_id] = candidate
        matched_platforms = sorted(by_platform.values(), key=lambda item: item["sale_price"])
        product = {
            "id": source.id, "name": label, "brand": brand,
            "source": source.source.name,
            "image": absolute_image_url(source.thumbnail_url, source.source.code),
            "list_price": _num(current["list_price"]),
            "sale_price": _num(current["sale_price"]),
            "discount_rate": current["_d"],
            "observed_at": current["observed_at"],
            "history_min_price": minimum["sale_price"] if minimum else None,
            "history_min_at": minimum["date"] if minimum else None,
            "history_max_price": maximum["sale_price"] if maximum else None,
            "history_max_at": maximum["date"] if maximum else None,
            "observed_days": len(price_series),
        }
    return _ok({
        "label": label,
        "selected": sel,
        "as_of": timezone.localtime(last_obs).isoformat(),
        "days": days,
        "overall": overall,
        "cheapest": cheapest,
        "platforms": platforms,
        "change_2w": change_2w,
        "first_discount_at": timezone.localtime(first_disc).date().isoformat() if first_disc else None,
        "first_discount_days": (timezone.localtime(last_obs).date()
                                - timezone.localtime(first_disc).date()).days if first_disc else None,
        "max_discount_period": max_disc,
        "restock_count": restock,
        "series": series,
        "platform_series": plat_series,
        "temperature": _temp_block(term_name, days),
        "product": product,
        "price_series": price_series,
        "matched_platforms": matched_platforms,
    })


# ══════════════════════════════════════════════════════════════
#  리세일 시세 — snapshot.resale_snapshot
# ══════════════════════════════════════════════════════════════

RESALE_STYLE_MIN = 30        # 스타일로 고른 매물이 이보다 적으면 대표 브랜드로 넓힌다
STYLE_PROXY_BRANDS = 6       # 대표 브랜드 수


def _style_proxy_brands(styles, limit=STYLE_PROXY_BRANDS):
    """그 스타일에 **몰려 있는** 브랜드 — 스타일 태그 상품 수만 보면 나이키·무신사 스탠다드처럼
    상품이 많은 범용 브랜드가 모든 스타일의 대표가 된다(2026-09-20 실측: 고프코어 대표에 무신사 스탠다드).
    그래서 '그 브랜드 태그 상품 중 이 스타일 비율'(집중도) × √(이 스타일 상품 수)로 고른다. 최소 3개."""
    key = "product_source__source_brand__brand__name"
    base = ProductTerm.objects.filter(term__term_type="STYLE", product_source__market_type="RETAIL",
                                      product_source__source_brand__brand__isnull=False)
    in_style = dict(base.filter(term__canonical_name__in=styles).values_list(key)
                    .annotate(n=Count("product_source_id", distinct=True)))
    in_style = {b: n for b, n in in_style.items() if b and n >= 3}
    if not in_style:
        return []
    total = dict(base.filter(**{f"{key}__in": list(in_style)}).values_list(key)
                 .annotate(n=Count("product_source_id", distinct=True)))
    score = {b: (n / max(1, total.get(b, n))) * math.sqrt(n) for b, n in in_style.items()}
    return [b for b, _ in sorted(score.items(), key=lambda kv: -kv[1])[:limit]]


def _resale_price(r):
    for k in ("last_trade_price", "median_price", "avg_price", "min_price", "lowest_ask"):
        v = _num(r.get(k))
        if v:
            return v
    return None


def _resale_source_images(sources):
    """연결 상품의 이미지 후보를 브라우저 성공 가능성이 높은 순서로 돌려준다.

    예전 구현은 ``thumbnail_url`` 자체가 비어 있지 않은 첫 행을 고른 뒤
    ``absolute_image_url`` 변환이 실패해도 그대로 ``None``을 확정했다. 그래서 같은
    표준상품의 두 번째·세 번째 소스에 정상 이미지가 있어도 화면에는 빠졌다.

    KREAM의 오래된 CDN 주소는 문자열은 정상이어도 원격에서 만료된 경우가 있어,
    동일 상품의 무신사·USED 이미지를 먼저 쓰고 나머지는 브라우저 폴백 후보로 준다.
    """
    source_priority = {"MUSINSA": 0, "MUSINSA_USED": 1, "ZIGZAG": 2,
                       "ABLY": 3, "KREAM": 9}
    ordered = sorted(
        sources,
        key=lambda row: (not bool(row.thumbnail_url),
                         source_priority.get(str(row.source.code or "").upper(), 5),
                         row.market_type == ProductSource.MarketType.RESALE, row.id),
    )
    images = []
    for source in ordered:
        image = absolute_image_url(source.thumbnail_url, source.source.code)
        if image and image not in images:
            images.append(image)
    return images


def _resale_source_image(sources):
    images = _resale_source_images(sources)
    return images[0] if images else None


def _resale_product_payload(product, sources):
    """표준상품 검색·리세일 본문이 함께 쓰는 최소 상품 정보."""
    images = _resale_source_images(sources)
    image = images[0] if images else None
    canonical_name = (product.canonical_name or "").strip()
    display_name = canonical_name
    # 초기 표준화 자료에는 상품명이 '블랙'·'화이트'처럼 속성 한 단어로 축약된 행이 있다.
    # FK 매핑은 신뢰하되 화면 이름까지 그 축약값을 강요하지 않고, 연결된 원본 중 짧고
    # 설명적인 이름을 보조 표시한다. 표준명 자체는 canonical_name으로 그대로 보존한다.
    if len(canonical_name) <= 3:
        source_names = [row.source_name.strip() for row in sources
                        if row.source_name and len(row.source_name.strip()) > len(canonical_name)]
        if source_names:
            display_name = min(source_names, key=lambda value: (len(value) > 80, len(value)))
    style_counts = Counter(row.style_no.strip() for row in sources if row.style_no and row.style_no.strip())
    model_code = style_counts.most_common(1)[0][0] if style_counts else None
    return {
        "id": product.id,
        "code": product.product_code,
        "model_code": model_code,
        "name": display_name,
        "canonical_name": canonical_name,
        "brand": product.brand.name if product.brand_id else None,
        "category": product.category.name if product.category_id else None,
        "image": image,
        "images": images,
    }


def _resale_listing_count(row):
    """스냅샷 한 건에서 실제로 관측된 판매 매물 수와 완전성 여부를 읽는다.

    USED는 한 ProductSource가 매물 한 건이라 listing_count/available_count가 채워진다.
    KREAM은 그 칸이 비어 있고 ``market_metrics.sample_asks[].quantity``에 가격·사이즈별
    판매 호가 수가 들어간다. asks_complete가 거짓이면 전체가 아니라 관측 하한이므로
    partial=True를 함께 돌려 화면이 `건+`로 구분하게 한다.
    """
    for key in ("available_count", "listing_count", "available", "listings"):
        value = row.get(key)
        if value is not None:
            return max(0, int(value)), False

    metrics = row.get("market_metrics") or {}
    coverage = metrics.get("coverage") or {}
    asks = metrics.get("sample_asks") or []
    quantities = []
    for ask in asks:
        if not isinstance(ask, dict) or ask.get("quantity") is None:
            continue
        try:
            quantities.append(max(0, int(ask["quantity"])))
        except (TypeError, ValueError):
            continue
    if quantities:
        return sum(quantities), coverage.get("asks_complete") is not True

    listings = metrics.get("sample_listings") or []
    if listings:
        ids = {str(item.get("inventory_item_id")) for item in listings
               if isinstance(item, dict) and item.get("inventory_item_id") is not None}
        count = len(ids) or len(listings)
        return count, coverage.get("listings_complete") is not True

    stats = metrics.get("sample_statistics") or {}
    sample_count = stats.get("listing_sample_count")
    if sample_count is not None:
        return max(0, int(sample_count)), coverage.get("listings_complete") is not True
    return None, False


def _resale_recommendations(all_sources, latest_by_source, limit=15):
    """브랜드·카테고리 시장 분석 아래에서 5장씩 순환할 실제 중고 매물 후보.

    ProductSource와 최신 ResaleSnapshot이 모두 있는 행만 사용한다. 표준상품으로
    묶인 여러 매물은 한 장으로 줄이고, 이미지가 없는 USED 매물은 같은 표준상품의
    다른 플랫폼 이미지로 보완한다. 가격이나 이미지를 추정해서 만들지는 않는다.
    """
    by_product = defaultdict(list)
    for source in all_sources:
        if source.product_id:
            by_product[source.product_id].append(source)

    image_by_product = {
        product_id: _resale_source_image(sources)
        for product_id, sources in by_product.items()
    }
    candidates = []
    for source in all_sources:
        latest = latest_by_source.get(source.id)
        if latest is None or source.market_type != ProductSource.MarketType.RESALE:
            continue
        image = (absolute_image_url(source.thumbnail_url, source.source.code)
                 or image_by_product.get(source.product_id))
        product = source.product if source.product_id else None
        brand = None
        if product and product.brand_id:
            brand = product.brand.name
        elif source.source_brand_id:
            brand = source.source_brand.name
        listing_count, listing_count_partial = _resale_listing_count(latest)
        candidates.append({
            "source_id": source.id,
            "product_id": source.product_id,
            "name": (source.source_name or (product.canonical_name if product else None)
                     or source.source_product_id),
            "brand": brand,
            "model_code": source.style_no,
            "image": image,
            "platform": source.source.name,
            "platform_code": source.source.code,
            "price": _num(latest.get("price"), 0),
            "listing_count": listing_count,
            "listing_count_partial": listing_count_partial,
            "observed_at": latest["day"].isoformat(),
        })

    # USED는 ProductSource 한 행이 실제 매물 한 건이다. 표준상품 카드 하나로 줄이기 전에
    # 같은 표준상품·플랫폼의 여러 행을 합치지 않으면 언제나 대표 행의 1건만 보인다.
    # KREAM도 같은 플랫폼 묶음 안에서는 JSONB 호가 수량을 합산한다.
    grouped_candidates = defaultdict(list)
    for row in candidates:
        key = (("product", row["product_id"], row["platform_code"])
               if row["product_id"] else ("source", row["source_id"], row["platform_code"]))
        grouped_candidates[key].append(row)

    candidates = []
    for rows in grouped_candidates.values():
        base = min(rows, key=lambda row: (not bool(row["image"]), row["name"] or ""))
        known_counts = [row["listing_count"] for row in rows if row["listing_count"] is not None]
        prices = [row["price"] for row in rows if row["price"] is not None]
        base = {**base,
                "listing_count": sum(known_counts) if known_counts else None,
                "listing_count_partial": any(row["listing_count_partial"] for row in rows
                                             if row["listing_count"] is not None),
                "price": _num(_median(prices), 0),
                "observed_at": max(row["observed_at"] for row in rows)}
        candidates.append(base)

    # 표준상품은 플랫폼이 달라도 한 장만 보여 준다. 아직 매핑 전인 행은 source 단위다.
    candidates.sort(key=lambda row: (not bool(row["image"]), -(row["listing_count"] or 0),
                                     row["name"] or ""))
    result, seen = [], set()
    for row in candidates:
        key = ("product", row["product_id"]) if row["product_id"] else ("source", row["source_id"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= limit:
            break
    return result


def _resale_platform_cards(sources):
    """동일 표준상품으로 확인된 플랫폼에 실제 값이 있을 때만 카드를 만든다.

    일반 판매처와 리셀 플랫폼의 숫자는 의미가 다르므로 한 평균으로 섞지 않는다.
    각 ProductSource의 최신 스냅샷 한 줄만 사용한다.
    """
    source_ids = [row.id for row in sources]
    if not source_ids:
        return []

    retail_latest = {}
    for row in (ProductSourceSnapshot.objects.filter(product_source_id__in=source_ids)
                .order_by("product_source_id", "-observed_at")
                .values("product_source_id", "observed_at", "list_price", "sale_price",
                        "discount_rate", "stock_status")):
        retail_latest.setdefault(row["product_source_id"], row)

    resale_latest = {}
    for row in (ResaleSnapshot.objects.filter(product_source_id__in=source_ids)
                .order_by("product_source_id", "-observed_at")
                .values("product_source_id", "observed_at", "listing_count", "available_count",
                        "min_price", "max_price", "avg_price", "median_price", "lowest_ask",
                        "highest_bid", "last_trade_price", "trade_volume", "sold_count",
                        "market_metrics")):
        resale_latest.setdefault(row["product_source_id"], row)

    grouped = defaultdict(list)
    for source in sources:
        grouped[(source.source.code, source.source.name)].append(source)

    cards = []
    for (code, name), platform_sources in grouped.items():
        retail_rows = [retail_latest[row.id] for row in platform_sources if row.id in retail_latest]
        resale_rows = [resale_latest[row.id] for row in platform_sources if row.id in resale_latest]
        if not retail_rows and not resale_rows:
            continue

        list_prices = [_num(row["list_price"]) for row in retail_rows if row["list_price"] is not None]
        sale_prices = [_num(row["sale_price"]) for row in retail_rows if row["sale_price"] is not None]
        resale_prices = [_resale_price(row) for row in resale_rows]
        resale_prices = [value for value in resale_prices if value is not None]
        asks = [_num(row["lowest_ask"]) for row in resale_rows if row["lowest_ask"] is not None]
        bids = [_num(row["highest_bid"]) for row in resale_rows if row["highest_bid"] is not None]
        trades = [_num(row["last_trade_price"]) for row in resale_rows
                  if row["last_trade_price"] is not None]
        observed_at = max([row["observed_at"] for row in [*retail_rows, *resale_rows]])

        available_values = []
        listing_count_partial = False
        for row in resale_rows:
            metrics = row.get("market_metrics") or {}
            if metrics.get("is_sold_out") is True:
                continue
            count, partial = _resale_listing_count(row)
            if count is not None:
                available_values.append(count)
                listing_count_partial = listing_count_partial or partial
        available = sum(available_values) if available_values else None

        list_price = _median(list_prices)
        sale_price = _median(sale_prices)
        discount = None
        if list_price and sale_price is not None and 0 <= sale_price <= list_price:
            discount = round((list_price - sale_price) / list_price * 100, 1)
        elif retail_rows:
            rates = [_pct(row["discount_rate"]) for row in retail_rows
                     if row["discount_rate"] is not None]
            discount = _median(rates)

        cards.append({
            "code": code,
            "name": name,
            "market": "resale" if resale_rows else "retail",
            "product_sources": len(platform_sources),
            "list_price": _num(list_price, 0),
            "sale_price": _num(sale_price, 0),
            "discount_rate": _num(discount, 1),
            "listing_count": available if resale_rows else None,
            "listing_count_partial": listing_count_partial if available is not None else False,
            "median_price": _num(_median(resale_prices), 0),
            "min_price": _num(min(resale_prices), 0) if resale_prices else None,
            "max_price": _num(max(resale_prices), 0) if resale_prices else None,
            "lowest_ask": _num(_median(asks), 0),
            "highest_bid": _num(_median(bids), 0),
            "last_trade_price": _num(_median(trades), 0),
            "as_of": timezone.localtime(observed_at).isoformat(),
        })
    return sorted(cards, key=lambda row: (row["market"] != "retail", row["name"]))


@require_GET
def resale_products(request):
    """GET /api/resale/products?q=에어포스&kind=쇼츠 — 리세일 상품 검색.

    표준상품(Product)을 먼저 돌려주고, 아직 표준상품에 연결되지 않은 리셀 상품은
    `platform_only` 후보로 분리한다. 검색어가 없어도 브랜드·카테고리·스타일 조건에
    맞는 상품을 보여 줘 세부 검색의 마지막 칸이 비어 있지 않게 한다.

    플랫폼 단독 후보를 표준상품인 것처럼 합치지 않는다.
    """
    query = (request.GET.get("q") or "").strip()
    limit = _int(request, "limit", 16, 1, 40)
    sel = _selection(request)
    has_selection = any(sel.values())

    has_resale = Exists(
        ResaleSnapshot.objects.filter(product_source__product_id=OuterRef("pk"))
    )
    latest_resale = (ResaleSnapshot.objects
                     .filter(product_source__product_id=OuterRef("pk"))
                     .order_by("-observed_at").values("observed_at")[:1])
    products = (Product.objects.filter(status=Product.Status.ACTIVE)
                .annotate(_has_resale=has_resale, _last_resale=Subquery(latest_resale))
                .filter(_has_resale=True))
    if has_selection:
        matched_products = (_selected_sources(sel).exclude(product_id__isnull=True)
                            .values("product_id"))
        products = products.filter(id__in=matched_products)
    if query:
        products = products.filter(
                    Q(canonical_name__icontains=query)
                    | Q(normalized_name__icontains=query)
                    | Q(product_code__icontains=query)
                    | Q(sources__source_name__icontains=query)
                    | Q(sources__style_no__icontains=query)
                    | Q(brand__name__icontains=query)
                )
    products = (products.select_related("brand", "category")
                .distinct().order_by("-_last_resale", "canonical_name")[:limit])

    product_rows = list(products)
    product_ids = [row.id for row in product_rows]
    sources_by_product = defaultdict(list)
    if product_ids:
        for source in (ProductSource.objects.filter(product_id__in=product_ids, status="ACTIVE")
                       .select_related("source", "source_brand")):
            sources_by_product[source.product_id].append(source)

    items = []
    for product in product_rows:
        sources = sources_by_product[product.id]
        platforms = []
        counts = defaultdict(int)
        names = {}
        for source in sources:
            counts[source.source.code] += 1
            names[source.source.code] = source.source.name
        for code, count in sorted(counts.items(), key=lambda row: (-row[1], row[0])):
            platforms.append({"code": code, "name": names[code], "count": count})
        payload = _resale_product_payload(product, sources)
        payload.update({
            "type": "product",
            "platforms": platforms,
            "source_count": len(sources),
        })
        items.append(payload)

    # 표준상품 후보가 적을 때만 플랫폼 단독 리셀 상품을 보충한다.
    # 이 후보는 선택해도 그 플랫폼 한 건만 분석하며 다른 플랫폼과 추정 결합하지 않는다.
    remaining = max(0, limit - len(items))
    if remaining:
        solo = ProductSource.objects.filter(
                    product_id__isnull=True,
                    status="ACTIVE",
                    resale_snapshots__isnull=False,
                )
        if has_selection:
            solo = _apply(solo, sel)
        if query:
            solo = solo.filter(Q(source_name__icontains=query) | Q(style_no__icontains=query)
                               | Q(source_brand__name__icontains=query))
        solo = (solo.select_related("source", "source_brand")
                .annotate(_last_resale=Max("resale_snapshots__observed_at"))
                .order_by("-_last_resale", "source_name", "id")[:remaining])
        for source in solo:
            image = absolute_image_url(source.thumbnail_url, source.source.code)
            items.append({
                "id": source.id,
                "type": "platform_only",
                "code": source.style_no,
                "name": source.source_name or "상품명 없음",
                "brand": source.source_brand.name if source.source_brand_id else None,
                "category": None,
                "image": image,
                "images": [image] if image else [],
                "platforms": [{"code": source.source.code, "name": source.source.name, "count": 1}],
                "source_count": 1,
            })

    if not items:
        target = f"‘{query}’" if query else _selection_label(sel) or "현재 조건"
        return _empty(f"{target}으로 찾은 중고·리셀 상품이 없습니다.")
    return _ok({"query": query, "selection": sel, "items": items, "count": len(items)})


@require_GET
def resale(request):
    """GET /api/resale?product_id=123 — 표준상품 또는 기존 조건의 중고 시세.

    가치 유지율 = 중고 거래가 ÷ 정가. 적재된 resale_price_ratio 가 있으면 그것을,
    없으면 market_metrics.regular_price(없으면 같은 표준상품의 최신 정가)로 나눈다.
    """
    sel = _selection(request)
    product_id = _int(request, "product_id", 0, 0, 2_147_483_647)
    source_id = _int(request, "source_id", 0, 0, 2_147_483_647)
    if not any(sel.values()) and not product_id and not source_id:
        return _no_selection()
    days = _int(request, "days", 90, 14, 365)
    selected_product = None
    selected_source = None
    analysis_scope = "selection"
    all_sources = None

    if product_id:
        selected_product = (Product.objects.filter(id=product_id, status=Product.Status.ACTIVE)
                            .select_related("brand", "category").first())
        if selected_product is None:
            return _empty("선택한 표준상품을 찾지 못했습니다.", product_id=product_id)
        all_sources = list(ProductSource.objects.filter(
            product_id=selected_product.id, status="ACTIVE"
        ).select_related("source", "source_brand", "source_category"))
        label = selected_product.canonical_name
        analysis_scope = "product"
    elif source_id:
        selected_source = (ProductSource.objects.filter(id=source_id, status="ACTIVE")
                           .select_related("source", "source_brand", "source_category",
                                           "product", "product__brand", "product__category")
                           .first())
        if selected_source is None:
            return _empty("선택한 플랫폼 상품을 찾지 못했습니다.", source_id=source_id)
        selected_product = selected_source.product
        if selected_product is not None:
            all_sources = list(ProductSource.objects.filter(
                product_id=selected_product.id, status="ACTIVE"
            ).select_related("source", "source_brand", "source_category"))
            analysis_scope = "product"
        else:
            all_sources = [selected_source]
            analysis_scope = "platform_only"
        label = (selected_product.canonical_name if selected_product
                 else selected_source.source_name or selected_source.source_product_id)
    else:
        label = _selection_label(sel)
        active_axes = [axis for axis, values in sel.items() if values]
        if active_axes == ["brand"]:
            analysis_scope = "brand"
        elif active_axes == ["kind"]:
            analysis_scope = "category"
        elif active_axes == ["style"]:
            analysis_scope = "style"
    term_name = (request.GET.get("term") or "").strip() or label
    metric_term = _selection_term(sel, term_name) if any(sel.values()) else _resolve_term(term_name)

    # 리셀 매물에는 스타일·종류 태그가 안 붙어 있는 경우가 많다 →
    # 조건에 걸린 상품과 같은 표준 상품(product)으로 묶인 매물까지 함께 본다.
    if all_sources is not None:
        source_ids = [row.id for row in all_sources]
        sources = ProductSource.objects.filter(id__in=source_ids)
    else:
        matched = _selected_sources(sel)
        sources = ProductSource.objects.filter(
            Q(id__in=matched.values("id"))
            | Q(product_id__in=matched.exclude(product_id__isnull=True).values("product_id")))
        # 여기서 일반 판매 소스까지 1만 행을 먼저 materialize하면 큰 브랜드는
        # 리세일 스냅샷을 읽기 전부터 수 초를 쓴다. 아래에서 실제 스냅샷이 확인된
        # source id를 확정한 뒤 필요한 행만 가져온다.
        all_sources = None
    resale_src = sources.filter(Q(market_type="RESALE") | Q(resale_snapshots__isnull=False)).distinct()
    ps = list(resale_src.values("id", "product_id", "source__code", "source__name")[:5000])
    basis_note = None
    # ★ 2026-09-20 — 크림 · 무신사 유즈드 매물에는 스타일 태그가 거의 없다(크림 0 · 유즈드 5건).
    #   스타일로 고르면 매물이 몇 건뿐이라, 그 스타일로 태그된 일반 판매 상품의 **대표 브랜드**
    #   매물로 넓혀 본다. 대표 브랜드와 기준을 응답에 적어 화면·챗봇이 밝힐 수 있게 한다.
    if analysis_scope in {"selection", "style"} and sel.get("style") and len(ps) < RESALE_STYLE_MIN:
        brands = _style_proxy_brands(sel["style"])
        if brands:
            proxy_sel = {**sel, "style": [], "brand": brands}
            proxy = ProductSource.objects.filter(
                Q(id__in=_selected_sources(proxy_sel).values("id")), Q(market_type="RESALE"))
            extra = list(proxy.values("id", "product_id", "source__code", "source__name")[:5000])
            have = {p["id"] for p in ps}
            ps += [p for p in extra if p["id"] not in have]
            basis_note = (f"‘{label}’ 태그가 붙은 중고·리셀 매물이 적어, 이 스타일의 대표 브랜드 "
                          f"({', '.join(brands)}) 매물로 넓혀 계산했습니다.")
    if not ps:
        return _empty(f"‘{label}’ 조건에 맞는 리셀·중고 매물이 없습니다.", label=label)
    ps_by_id = {p["id"]: p for p in ps}
    broad_scope = analysis_scope in {"brand", "category", "style", "selection"}
    if all_sources is None:
        all_sources = []

    snaps = ResaleSnapshot.objects.filter(product_source_id__in=list(ps_by_id))
    last_obs = snaps.aggregate(d=Max("observed_at"))["d"]
    if last_obs is None:
        return _empty(f"‘{label}’ 매물 {len(ps)}개에 시세 스냅샷이 아직 없습니다.", label=label)
    since = last_obs - timedelta(days=max(days, 56))

    # 신상품 기준가 — 같은 표준상품을 판매하는 각 일반 판매처의 최신 할인가를
    # 먼저 쓰고, 할인가가 없을 때만 표기 정가를 쓴 뒤 상품별 중앙값을 낸다.
    # 한 판매처 한 행이나 MSRP를 대표값처럼 쓰지 않는다.
    product_ids = {p["product_id"] for p in ps if p["product_id"]}
    retail_price = {}
    if product_ids:
        retail_price_rows = defaultdict(list)
        for r in (ProductSourceSnapshot.objects
                  .filter(product_source__product_id__in=product_ids)
                  .exclude(product_source__market_type="RESALE")
                  .filter(Q(sale_price__isnull=False) | Q(list_price__isnull=False))
                  .order_by("product_source_id", "-observed_at")
                  .distinct("product_source_id")
                  .values("product_source__product_id", "sale_price", "list_price")):
            price = _num(r["sale_price"]) or _num(r["list_price"])
            if price is not None:
                retail_price_rows[r["product_source__product_id"]].append(price)
        retail_price = {product_id: _median(prices)
                        for product_id, prices in retail_price_rows.items()}

    row_fields = [
        "product_source_id", "observed_at", "listing_count", "available_count", "min_price",
        "max_price", "avg_price", "median_price", "sold_count", "lowest_ask", "highest_bid",
        "last_trade_price", "trade_volume", "resale_price_ratio", "resale_index",
    ]
    snapshot_rows = snaps.filter(observed_at__gte=since)
    if broad_scope:
        # 브랜드·카테고리는 동일 매물이 하루에 여러 번 수집되어도 마지막 관측 한 건만
        # 대표로 쓴다. 같은 매물을 수집 횟수만큼 과대 가중하지 않고 전송량도 줄인다.
        snapshot_rows = (snapshot_rows.annotate(
            snapshot_day=TruncDate("observed_at"),
            daily_rank=Window(
                expression=RowNumber(),
                partition_by=[F("product_source_id"), TruncDate("observed_at")],
                order_by=F("observed_at").desc(),
            ),
        ).filter(daily_rank=1).order_by("product_source_id", "observed_at"))
    else:
        snapshot_rows = snapshot_rows.order_by("observed_at")
        row_fields.append("market_metrics")
    rows = list(snapshot_rows.values(*row_fields)[:60000])

    recs = []
    for r in rows:
        mm = r.get("market_metrics") or {}
        price = _resale_price(r)
        regular = (retail_price.get(ps_by_id[r["product_source_id"]]["product_id"])
                   or _num(mm.get("regular_price")))
        ratio = _num(r["resale_price_ratio"])
        if ratio is None and price and regular:
            ratio = price / regular
        recs.append({
            "pid": r["product_source_id"],
            "day": timezone.localtime(r["observed_at"]).date(),
            "price": price, "regular": regular, "ratio": ratio,
            "index": _num(r["resale_index"]),
            "ask": _num(r["lowest_ask"]), "bid": _num(r["highest_bid"]),
            "trade": _num(r["last_trade_price"]),
            "volume": r["trade_volume"] if r["trade_volume"] is not None else r["sold_count"],
            "listings": r["listing_count"],
            "available_count": r["available_count"],
            "market_metrics": mm,
            "size": mm.get("size"), "grade": mm.get("condition_grade") or mm.get("condition_grade_raw"),
            "sold_out": mm.get("is_sold_out"),
            "platform": ps_by_id[r["product_source_id"]]["source__name"],
        })

    latest_by_source = {}
    for record in recs:
        latest_by_source[record["pid"]] = record

    recommendation_sources = all_sources
    if broad_scope:
        # 추천 5장을 위해 5천 ProductSource 전체 모델을 읽지 않는다. 최신 관측 중
        # 매물 수가 많은 후보 40개만 상세 정보와 이미지를 읽는다.
        candidate_ids = [source_id for source_id, _ in sorted(
            latest_by_source.items(),
            key=lambda item: (-(item[1].get("listings") or 1), item[1]["day"], -item[0]),
        )[:40]]
        recommendation_sources = list(ProductSource.objects.filter(id__in=candidate_ids).select_related(
            "source", "source_brand", "source_category", "product", "product__brand"
        ))
        # 추천 카드는 표준상품 하나를 대표하므로 후보 한 행만 읽으면 USED가 항상 1건으로
        # 보인다. 후보 표준상품에 연결된 리세일 ProductSource를 모두 가져와 플랫폼별
        # 현재 매물 수를 합칠 수 있게 한다. 플랫폼 단독 후보는 기존 source 단위로 유지한다.
        recommendation_product_ids = {row.product_id for row in recommendation_sources
                                      if row.product_id}
        if recommendation_product_ids:
            mapped_resale_sources = list(ProductSource.objects.filter(
                product_id__in=recommendation_product_ids,
                status=ProductSource.Status.ACTIVE,
                market_type=ProductSource.MarketType.RESALE,
            ).select_related(
                "source", "source_brand", "source_category", "product", "product__brand"
            ))
            platform_only_sources = [row for row in recommendation_sources if not row.product_id]
            recommendation_sources = mapped_resale_sources + platform_only_sources
        # 브랜드·카테고리 시계열은 전송량 때문에 JSONB를 제외하지만 추천 카드 40건은
        # KREAM의 sample_asks 수량과 USED 연결 매물 수가 필요하다. 후보 표준상품에
        # 연결된 리세일 source의 최신 스냅샷만 다시 읽는다.
        recommendation_source_ids = [row.id for row in recommendation_sources]
        candidate_latest = {}
        for row in (ResaleSnapshot.objects.filter(product_source_id__in=recommendation_source_ids)
                    .order_by("product_source_id", "-observed_at")
                    .distinct("product_source_id")
                    .values("product_source_id", "observed_at", "listing_count", "available_count",
                            "min_price", "max_price", "avg_price", "median_price", "lowest_ask",
                            "last_trade_price", "market_metrics")):
            candidate_latest.setdefault(row["product_source_id"], row)
        for source_id, row in candidate_latest.items():
            record = latest_by_source.get(source_id)
            if record is None:
                record = {
                    "pid": source_id,
                    "day": timezone.localtime(row["observed_at"]).date(),
                    "price": _resale_price(row),
                }
                latest_by_source[source_id] = record
            record["listing_count"] = row["listing_count"]
            record["available_count"] = row["available_count"]
            record["market_metrics"] = row["market_metrics"] or {}
        donors = list(ProductSource.objects.filter(
            product_id__in=recommendation_product_ids,
            thumbnail_url__isnull=False,
        ).exclude(thumbnail_url="").order_by("product_id", "id")
          .distinct("product_id").select_related(
              "source", "source_brand", "source_category", "product", "product__brand"
          ))
        have_source_ids = {row.id for row in recommendation_sources}
        recommendation_sources += [row for row in donors if row.id not in have_source_ids]

    last_day = timezone.localtime(last_obs).date()
    win = [x for x in recs if x["day"] > last_day - timedelta(days=days)]
    wk = [x for x in recs if x["day"] > last_day - timedelta(days=7)]
    prev_wk = [x for x in recs if last_day - timedelta(days=14) < x["day"] <= last_day - timedelta(days=7)]
    m4 = [x for x in recs if x["day"] > last_day - timedelta(days=28)]
    p4 = [x for x in recs if last_day - timedelta(days=56) < x["day"] <= last_day - timedelta(days=28)]

    ratio_now = _median([x["ratio"] for x in (wk or win)])
    ratio_prev = _median([x["ratio"] for x in prev_wk])

    def vol(xs):
        v = [x["volume"] for x in xs if x["volume"] is not None]
        return sum(v) if v else None

    # 거래량이 적재되지 않으면 관측된 매물 수로 대신한다 — 어느 쪽인지 밝힌다.
    vol_now, vol_prev = vol(m4), vol(p4)
    vol_basis = "trade_volume/sold_count"
    if vol_now is None:
        vol_now, vol_prev, vol_basis = len({(x["pid"], x["day"]) for x in m4}), \
            len({(x["pid"], x["day"]) for x in p4}), "observed_listings"

    # 일별 중앙 유지율 → 프리미엄(≥1.0) 연속 일수
    by_day = defaultdict(list)
    for x in win:
        if x["ratio"] is not None:
            by_day[x["day"]].append(x["ratio"])
    series = [{"date": d.isoformat(), "ratio": round(_median(v), 4),
               "keep_pct": round(_median(v) * 100, 1)} for d, v in sorted(by_day.items())]
    prem_days = 0
    for s in reversed(series):
        if s["ratio"] >= 1:
            prem_days += 1
        else:
            break

    def group(key):
        g = defaultdict(list)
        for x in win:
            if x[key]:
                g[str(x[key])].append(x)
        total = sum(len(v) for v in g.values()) or 1
        out = [{"label": k, "count": len(v), "share_pct": round(len(v) / total * 100, 1),
                "ratio": _num(_median([y["ratio"] for y in v]), 3),
                "price": _num(_median([y["price"] for y in v]), 0)} for k, v in g.items()]
        if key == "grade":
            grade_order = {
                "S+": 0, "S": 1, "A+": 2, "A": 3, "B+": 4, "B": 5,
                "C+": 6, "C": 7, "D": 8,
                "새상품": 0, "미사용": 1, "최상": 2, "상": 3, "중": 5, "하": 7,
            }
            def grade_rank(row):
                normalized = str(row["label"]).upper().replace("급", "").replace(" ", "")
                return grade_order.get(normalized, 99), -row["count"], normalized
            return sorted(out, key=grade_rank)[:12]
        return sorted(out, key=lambda o: -o["count"])[:12]

    asks = [x["ask"] for x in win if x["ask"]]
    trades = [x["trade"] or x["bid"] for x in win if (x["trade"] or x["bid"])]
    spread = None
    if asks and trades:
        a, t = _median(asks), _median(trades)
        spread = {"ask": round(a), "trade": round(t), "gap_pct": round((a - t) / t * 100, 1) if t else None}

    selected_payload = None
    if selected_product is not None:
        selected_payload = _resale_product_payload(selected_product, all_sources)
        selected_payload["mapped"] = True
    elif selected_source is not None:
        selected_payload = {
            "id": selected_source.id,
            "code": selected_source.style_no,
            "name": selected_source.source_name or selected_source.source_product_id,
            "brand": selected_source.source_brand.name if selected_source.source_brand_id else None,
            "category": (selected_source.source_category.source_category_name
                         if selected_source.source_category_id else None),
            "image": absolute_image_url(selected_source.thumbnail_url, selected_source.source.code),
            "mapped": False,
        }

    # 브랜드·카테고리 전체 분석은 서로 다른 상품을 한 플랫폼 카드로 뭉치지 않는다.
    # 플랫폼 비교는 표준상품 하나 또는 플랫폼 단독 상품 하나를 고른 경우에만 제공한다.
    platform_cards = (_resale_platform_cards(all_sources)
                      if analysis_scope in {"product", "platform_only"} else [])
    current_listing_values = [row["listing_count"] for row in platform_cards
                              if row["market"] == "resale" and row["listing_count"] is not None]
    current_listing_count = (sum(current_listing_values)
                             if current_listing_values else None)
    current_listing_count_partial = any(
        row["listing_count_partial"] for row in platform_cards
        if row["market"] == "resale" and row["listing_count"] is not None
    )
    recommendations = (_resale_recommendations(recommendation_sources, latest_by_source)
                       if analysis_scope in {"brand", "category", "style", "selection"} else [])
    observed_days = len({x["day"] for x in win})
    platform_count = len(platform_cards)
    if analysis_scope == "product" and platform_count >= 2 and len({x["pid"] for x in win}) >= 10 \
            and observed_days >= 3 and ratio_now is not None:
        confidence = {"code": "high", "label": "높음"}
    elif ratio_now is not None and len({x["pid"] for x in win}) >= 3:
        confidence = {"code": "medium", "label": "보통"}
    else:
        confidence = {"code": "low", "label": "낮음"}

    grouped_platforms = group("platform")
    keep_pct = round(ratio_now * 100, 1) if ratio_now is not None else None
    volume_change_pct = (round((vol_now - vol_prev) / vol_prev * 100, 1)
                         if vol_prev else None)
    has_trade_volume = vol_basis != "observed_listings"
    md_signals = [
        {
            "label": "가격 방어율",
            "value": f"{keep_pct:g}%" if keep_pct is not None else "측정 전",
            "tone": ("positive" if keep_pct is not None and keep_pct >= 70
                     else "neutral" if keep_pct is not None and keep_pct >= 45 else "caution"),
            "description": ("관측 중고가의 정가 대비 중앙값입니다."
                            if keep_pct is not None else "정가와 중고가가 함께 연결되면 계산됩니다."),
        },
        {
            "label": "거래량 증감률",
            "value": (f"{volume_change_pct:+g}%" if has_trade_volume and volume_change_pct is not None
                      else "측정 전"),
            "tone": ("positive" if has_trade_volume and volume_change_pct is not None
                     and volume_change_pct > 0 else "neutral"),
            "description": ("최근 4주 중고거래량을 직전 4주와 비교했습니다."
                            if has_trade_volume and volume_change_pct is not None
                            else "실제 거래량이 두 기간에 쌓이면 증감률을 계산합니다."),
        },
        {
            "label": "프리미엄 지속 기간",
            "value": f"{prem_days}일" if ratio_now is not None else "측정 전",
            "tone": "positive" if prem_days > 0 else "neutral",
            "description": ("정가보다 중고가가 높았던 최근 연속 기간입니다."
                            if ratio_now is not None else "정가 대비 중고가 시계열이 쌓이면 계산됩니다."),
        },
    ]

    return _ok({
        "label": label,
        "analysis_scope": analysis_scope,
        "product": selected_payload,
        "selected": sel,
        "as_of": timezone.localtime(last_obs).isoformat(),
        "days": days,
        "observed_days": observed_days,
        "listings": len({x["pid"] for x in win}),
        "confidence": confidence,
        "mapping": {
            "platform_count": platform_count,
            "platforms": [row["name"] for row in platform_cards],
            "source_count": len(ps) if broad_scope else len(all_sources),
        },
        "platform_cards": platform_cards,
        "current_listing_count": current_listing_count,
        "current_listing_count_partial": current_listing_count_partial,
        "recommendations": recommendations,
        "md_signals": md_signals,
        "keep_pct": keep_pct,
        "keep_change_pp": round((ratio_now - ratio_prev) * 100, 1)
        if ratio_now is not None and ratio_prev is not None else None,
        "premium": (ratio_now or 0) >= 1,
        "premium_days": prem_days,
        "used_price": _num(_median([x["price"] for x in (wk or win)]), 0),
        "regular_price": _num(_median([x["regular"] for x in (wk or win)]), 0),
        "resale_index": _num(_median([x["index"] for x in (wk or win)]), 3),
        "volume_4w": vol_now,
        "volume_change_pct": volume_change_pct,
        "volume_basis": vol_basis,
        "sizes": group("size"),
        "grades": group("grade"),
        "platforms": grouped_platforms,
        "spread": spread,
        "basis_note": basis_note,
        "series": series,
        "temperature": _temp_block(metric_term.canonical_name if metric_term else term_name, days),
    })


# ══════════════════════════════════════════════════════════════
#  수명주기 — term_metric_daily 의 level·momentum 으로 판정
# ══════════════════════════════════════════════════════════════

LIFECYCLE_RULE = (
    "28일 이동평균(ma28)의 관측 기간 최고점 대비 현재 위치와 모멘텀(50=보합)으로 판정합니다. "
    "모멘텀 ≥ 55: 최근 7일 수준(ma7) < 35 이면 태동, 아니면 확산 / "
    "45 ≤ 모멘텀 < 55 이고 ma28 이 최고점의 85% 이상이면 정점 / "
    "그 밖(모멘텀 < 45 등)은 최고점을 지났으면 쇠퇴, 최고점 자체가 낮으면(ma7 최고 < 35) 태동. "
    "관측 28일 미만이면 판단을 보류합니다."
)


# ── 발주 판별 (2026-09-27, METRIC-002) ─────────────────────────
# 요구사항: 단계를 판정하고 '발주 적기인지 비추천인지' 를 판별한다.
# 판별은 단계 하나에서만 나온다 — 리드타임 · 재고 같은 입력은 우리 데이터에 없으므로
# 숫자(몇 주 뒤 등)를 지어내지 않는다. 화면 · 챗봇이 같은 값을 쓰도록 여기서 한 번만 정한다.
ORDER_TIMING = {
    "태동": ("GOOD", "발주 적기",
             "화제성이 막 오르기 시작했습니다. 먼저 들이면 선점할 수 있지만 그대로 사라질 수도 있어 소량부터 권합니다."),
    "확산": ("GOOD", "발주 적기",
             "오름세가 이어지는 구간입니다. 지금 들여도 수요가 남아 있을 가능성이 가장 높습니다."),
    "정점": ("CAUTION", "주의",
             "오름세가 멈춘 정점 부근입니다. 들여온 물량이 팔릴 기간이 짧을 수 있어 추가 발주는 신중해야 합니다."),
    "쇠퇴": ("AVOID", "발주 비추천",
             "최고점을 지나 내려가는 중입니다. 추가 발주보다 남은 재고를 소진하는 편이 낫습니다."),
}
ORDER_TIMING_RULE = "발주 판별은 수명주기 단계로만 정합니다 — 태동 · 확산은 적기, 정점은 주의, 쇠퇴는 비추천. 판정을 보류한 용어는 판별하지 않습니다."


def _order_timing(stage):
    hit = ORDER_TIMING.get(stage)
    if hit is None:
        return None
    code, label, reason = hit
    return {"code": code, "label": label, "reason": reason}


def _smooth_level(p):
    """판정에 쓰는 수준 — 하루치 level 은 드문 용어에서 0↔100 으로 튄다(2026-09-19).
    ma7 이 있으면 ma7, 없으면 level."""
    v = p.get("ma7")
    return v if v is not None else p.get("level")


def _lifecycle_stage(series):
    pts = [p for p in series if p.get("level") is not None or p.get("ma28") is not None]
    if len(pts) < 28:
        return None, None, None
    last = pts[-1]
    lvl = _smooth_level(last) or 0
    mom = last.get("momentum")
    ma = [p.get("ma28") for p in pts if p.get("ma28") is not None]
    peak = max(ma) if ma else None
    now = ma[-1] if ma else None
    ratio = (now / peak) if (peak and now is not None) else None
    peak_i = max(range(len(pts)), key=lambda i: pts[i].get("ma28") or -1)
    after_peak = peak_i < len(pts) - 1 and ratio is not None and ratio < 0.999
    max_level = max((_smooth_level(p) or 0) for p in pts)

    if mom is None:
        stage = None
    elif mom >= 55:
        stage = "태동" if lvl < 35 else "확산"
    elif mom >= 45 and ratio is not None and ratio >= 0.85:
        stage = "정점"
    elif max_level < 35:
        stage = "태동"
    else:
        stage = "쇠퇴"

    # 유행 진행도(0~100): 최고점 전에는 0~50, 지난 뒤에는 50~100
    progress = None
    if ratio is not None:
        progress = round(ratio * 50) if (not after_peak or stage in ("태동", "확산")) \
            else round(50 + (1 - ratio) * 50)
    return stage, progress, pts[peak_i]["date"]


@require_GET
def lifecycle(request):
    """GET /api/lifecycle?style=고프코어&term=고프코어"""
    sel = _selection(request)
    label = _selection_label(sel)
    term_name = (request.GET.get("term") or "").strip() or label
    if not term_name:
        return _no_selection()
    term = _selection_term(sel, term_name)
    if term is None:
        return _empty(_term_missing_reason(term_name), label=label or term_name)
    rows, _ = _term_series(term, 365)
    basis = None
    if len(rows) < HISTORY_MIN_POINTS:
        hist = _history_series(term, 365)
        if len(hist) > len(rows):
            rows, basis = hist, HISTORY_BASIS
    if not rows:
        return _empty(f"‘{term.canonical_name}’ 의 트렌드 지표가 아직 없습니다.", label=label)
    series = [_metric_point(r) for r in rows]
    stage, progress, peak_date = _lifecycle_stage(series)

    last = series[-1]
    last_day = rows[-1]["metric_date"]

    def sum_mention(a, b):
        return sum(p["mention"] or 0 for p in series
                   if last_day - timedelta(days=a) < timezone.datetime.fromisoformat(p["date"]).date()
                   <= last_day - timedelta(days=b))

    m_now, m_prev = sum_mention(28, 0), sum_mention(56, 28)
    first_active = next((p["date"] for p in series if (p.get("level") or 0) >= 20), series[0]["date"])
    age_weeks = (last_day - timezone.datetime.fromisoformat(first_active).date()).days // 7

    # 주별 온도 (최근 12주)
    weekly = defaultdict(list)
    for p in series:
        d = timezone.datetime.fromisoformat(p["date"]).date()
        if d > last_day - timedelta(weeks=12) and p["temp"] is not None:
            weekly[(last_day - d).days // 7].append(p["temp"])
    weekly_temp = [{"weeks_ago": k, "temp": round(_mean(v), 1)} for k, v in sorted(weekly.items())]

    # 판매 신호 — 선택 조건 상품의 일별 판매수 증가분 합
    sales = []
    if any(sel.values()):
        ps_ids = list(_selected_sources(sel).values_list("id", flat=True)[:3000])
        if ps_ids:
            prev, daily = {}, defaultdict(int)
            for r in (ProductSourceSnapshot.objects
                      .filter(product_source_id__in=ps_ids, sales_count__isnull=False,
                              observed_at__date__gte=last_day - timedelta(days=365))
                      .order_by("product_source_id", "observed_at")
                      .values("product_source_id", "observed_at", "sales_count")[:80000]):
                pid, v = r["product_source_id"], r["sales_count"]
                if pid in prev and v >= prev[pid]:
                    daily[timezone.localtime(r["observed_at"]).date().isoformat()] += v - prev[pid]
                prev[pid] = v
            sales = [{"date": d, "sales": v} for d, v in sorted(daily.items())]

    return _ok({
        "label": label or term.canonical_name,
        "term": term.canonical_name,
        "facet": term.term_type,
        "as_of": last["date"],
        "data_as_of": _data_as_of(),
        "points": len(series),
        "basis": basis,
        "stage": stage,
        "progress": progress,
        "peak_date": peak_date,
        "age_weeks": age_weeks,
        "level": last["level"],
        "momentum": last["momentum"],
        "temp": last["temp"],
        "inflow_pct": round((m_now - m_prev) / m_prev * 100, 1) if m_prev else None,
        "mention_28d": m_now,
        "weekly_temp": weekly_temp,
        "series": series,
        "sales_series": sales,
        "rule": LIFECYCLE_RULE,
        "order_timing": _order_timing(stage),
        "order_rule": ORDER_TIMING_RULE,
    })


# ══════════════════════════════════════════════════════════════
#  상품 · 살!말? (챗봇이 쓰는 창구 — 새 스키마에 맞춤)
# ══════════════════════════════════════════════════════════════

@require_GET
def products(request):
    """GET /api/products?style=고프코어&gender=FEMALE&limit=16 — 태그된 상품 목록.

    스타일은 자동 태깅 결과(`commerce.product_term` · term_type='STYLE')로 고른다.
    한 상품에 스타일이 여러 개 달릴 수 있어, 그중 하나라도 맞으면 포함한다.
    화면에서 쓸 수 있게 원본 상품 이미지와 최신 가격도 같이 돌려준다.
    gender 를 주면 수집 원본에 적힌 해당 성별·공용 상품만 반환한다.
    """
    kw = (request.GET.get("q") or "").strip()
    gender = (request.GET.get("gender") or "").strip().upper()
    if gender and gender not in ("FEMALE", "MALE"):
        return JsonResponse({"status": "error", "reason": "성별은 FEMALE 또는 MALE 중에서 선택해 주세요.",
                             "data": None}, status=400)
    brand = (request.GET.get("brand") or "").strip()
    category_group = (request.GET.get("category_group") or "").strip().lower()
    limit = _int(request, "limit", 40, 1, 200)
    offset = _int(request, "offset", 0, 0, 1_000_000)
    sel = _selection(request)
    # brand 는 기존 API 의 영문 대소문자 무시 동작을 유지하려고 아래에서 따로 건다.
    product_sel = {**sel, "brand": []}
    qs = _selected_sources(product_sel).filter(status="ACTIVE").distinct()
    if gender:
        # 수집 원본의 M/W/U 및 MEN/WOMEN/UNISEX 표기만 쓴다.
        # 알 수 없는 숫자 코드나 빈 값은 다른 성별 옷으로 추측하지 않는다.
        own = "W|F|WOMEN|FEMALE" if gender == "FEMALE" else "M|MEN|MALE"
        pattern = rf"(^|[,:[:space:]])({own}|U|UNISEX)([,:[:space:]]|$)"
        qs = qs.filter(
            Q(gender_scope__iregex=pattern)
            | (Q(gender_scope__isnull=True) | Q(gender_scope=""))
            & Q(product__gender_scope__iregex=pattern)
        )
    if kw:
        qs = qs.filter(Q(source_name__icontains=kw) | Q(product__canonical_name__icontains=kw))
    if brand:
        qs = qs.filter(Q(product__brand__name=brand) | Q(product__brand__english_name__iexact=brand)
                       | Q(source_brand__name=brand) | Q(source_brand__brand__name=brand))
    # 스타일 화면의 큰 분류. 페이지를 자른 뒤 브라우저에서 분류하면 한 페이지에
    # 아우터가 1~2개만 섞여 보이므로, 반드시 여기서 먼저 거른다.
    # 순서는 프론트 itemCatKey(ST_CAT_RULES)와 같다. 앞 분류를 제외해
    # '원피스·스커트'처럼 두 규칙에 걸리는 이름도 브라우저와 동일하게 판정한다.
    category_patterns = {
        "shoes": r"신발|슈즈|스니커|운동화|부츠|워커|로퍼|모카신|샌들|슬리퍼|더비|옥스포드|힐|플랫|메리제인|첼시|shoes|sneaker|boots|loafer|sandal",
        "dress": r"원피스|드레스|점프수트|셋업|jumpsuit|dress|onepiece",
        "outer": r"아우터|아웃터|자켓|재킷|코트|점퍼|블루종|봄버|패딩|다운|플리스|무스탕|가디건|베스트|조끼|바람막이|파카|트렌치|블레이저|jacket|coat|outer|parka|blouson|fleece|vest|cardigan",
        "bottom": r"하의|바지|팬츠|슬랙스|데님|진|청바지|스커트|치마|반바지|쇼츠|조거|레깅스|pants|denim|jeans|skirt|shorts|slacks|jogger|legging",
        "top": r"상의|티셔츠|티|반팔|긴팔|맨투맨|스웨트|후디|후드|셔츠|블라우스|니트|스웨터|폴로|탑|나시|피케|tee|t-shirt|shirt|blouse|knit|sweater|hood|sweat|polo|top",
    }

    def category_match(pattern):
        return (Q(product__category__name__iregex=pattern)
                | Q(source_category__category__name__iregex=pattern)
                | Q(source_category__source_category_name__iregex=pattern)
                | Q(product__canonical_name__iregex=pattern)
                | Q(source_name__iregex=pattern))

    if category_group in category_patterns:
        order = tuple(category_patterns)
        qs = qs.filter(category_match(category_patterns[category_group]))
        for earlier in order[:order.index(category_group)]:
            qs = qs.exclude(category_match(category_patterns[earlier]))
    # 정렬 — 값은 모두 최신 스냅샷 한 줄에서 온다. 값이 없는 상품은 어느 정렬이든 맨 뒤.
    # recommend(FEEDiT 추천순): 리뷰·좋아요·판매량(로그) + 평점 + 할인율 + 이미지·가격 보유 가산점.
    # 계산식은 api/products.js(Node) 와 같게 유지한다.
    sort = (request.GET.get("sort") or "latest").strip()
    snap = ProductSourceSnapshot.objects.filter(product_source_id=OuterRef("pk")).order_by("-observed_at")

    def last(field):
        return Cast(Subquery(snap.values(field)[:1]), FloatField())

    zero = Value(0.0, output_field=FloatField())
    extra = {"_price": Cast(Subquery(snap.annotate(_p=Coalesce("sale_price", "list_price")).values("_p")[:1]),
                            FloatField())}
    tail = ("-last_seen_at", "-id")
    simple = {"reviews": "review_count", "rating": "rating", "likes": "like_count", "sales": "sales_count"}
    if sort == "price_desc":
        ordering = (F("_price").desc(nulls_last=True), "-id")
    elif sort == "price_asc":
        ordering = (F("_price").asc(nulls_last=True), "-id")
    elif sort in simple:
        extra["_key"] = last(simple[sort])
        ordering = (F("_key").desc(nulls_last=True),) + (
            (F("_rv").desc(nulls_last=True),) if sort == "rating" else ()) + tail
        if sort == "rating":
            extra["_rv"] = last("review_count")
    elif sort in ("discount", "recommend"):
        extra["_dc_raw"] = last("discount_rate")
        disc = Case(When(_dc_raw__lte=1, then=F("_dc_raw") * 100), default=F("_dc_raw"), output_field=FloatField())
        if sort == "discount":
            extra["_key"] = disc
            ordering = (F("_key").desc(nulls_last=True),) + tail
        else:
            extra.update({"_rv": last("review_count"), "_lk": last("like_count"),
                          "_sl": last("sales_count"), "_rt": last("rating")})
            extra["_key"] = (
                _safe_log_metric(F("_rv")) * 1.0
                + _safe_log_metric(F("_lk")) * 0.8
                + _safe_log_metric(F("_sl")) * 0.8
                + Coalesce(F("_rt"), zero) * 0.6
                + Coalesce(disc, zero) * 0.03
                + Case(When(thumbnail_url__isnull=False, then=Value(0.5)), default=zero, output_field=FloatField())
                + Case(When(_price__isnull=False, then=Value(0.5)), default=zero, output_field=FloatField())
            )
            ordering = (F("_key").desc(),) + tail
    else:
        ordering = tail
    sort_fields = [k for k in extra]
    rows = list(qs.annotate(
        **extra,
        _brand=BRAND_EXPR,
        _name=ITEM_EXPR,
        _category=Coalesce(
            "product__category__name",
            "source_category__category__name",
            "source_category__source_category_name",
        ),
    ).values(
        "id", "product_id", "_name", "_brand", "_category", "source__code", "source__name",
        "product_url", "thumbnail_url", "market_type", *sort_fields,
    ).order_by(*ordering)[offset:offset + limit + 1])
    if not rows:
        label = kw or brand or (sel["style"] or [None])[0]
        return _empty(f"조건에 맞는 상품이 없습니다 (검색어 ‘{label}’)."
                      if label else "commerce.product_source 가 비어 있습니다.")
    has_more = len(rows) > limit
    rows = rows[:limit]
    total = qs.count()   # '더 보기' 버튼이 "24 / 312" 를 보여 주려면 전체 개수가 필요하다
    snaps = {}
    for s in (ProductSourceSnapshot.objects.filter(product_source_id__in=[r["id"] for r in rows])
              .order_by("product_source_id", "-observed_at")
              .values("product_source_id", "list_price", "sale_price", "discount_rate",
                      "stock_status", "observed_at")):
        snaps.setdefault(s["product_source_id"], s)
    items = []
    for r in rows:
        s = snaps.get(r["id"])
        items.append({
            "id": r["product_id"] or r["id"], "product_source_id": r["id"],
            "name": r["_name"], "brand": r["_brand"], "source": r["source__code"],
            "source_label": r["source__name"],
            "url": r["product_url"],
            # 상대 경로로 저장된 사진에 베이스를 붙인다(images.absolute_image_url).
            # 전체의 38%가 그 모양이라, 그대로 내보내면 카드 사진이 안 뜬다.
            "image": absolute_image_url(r["thumbnail_url"], r["source__code"]),
            "category": r["_category"], "market": r["market_type"],
            "price": {
                "list": _num(s["list_price"]) if s else None,
                "sale": _num(s["sale_price"]) if s else None,
                "discount": _pct(s["discount_rate"]) if s else None,
                "stock": s["stock_status"] if s else None,
                "as_of": s["observed_at"] if s else None,
                "unavailable": None if s else "이 상품은 아직 가격 스냅샷이 없습니다.",
            },
        })
    return _ok({
        "count": len(items),
        "items": items,
        "offset": offset,
        "next_offset": offset + len(items),
        "has_more": has_more,
        "total": total,
        "style": sel["style"],
        "category_group": category_group if category_group in category_patterns else None,
    })


@require_GET
def price_history(request):
    """GET /api/price-history?ids=17,18,19 — 찜한 상품들의 가격 기록 요약.

    트렌드 분석 › 찜한 키워드 화면이 '최저가'를 실값으로 그리려고 부른다.
    ids 는 commerce.product_source.id (스타일 페이지 상품 카드의 product_source_id).
    가격은 판매가, 없으면 정가를 쓴다. 스냅샷이 없는 상품은 결과에서 빠진다 —
    0원이나 추정값으로 채우지 않는다.
    """
    raw = (request.GET.get("ids") or "").replace(" ", "")
    ids = []
    for x in raw.split(","):
        if x.isdigit() and int(x) not in ids:
            ids.append(int(x))
    ids = ids[:100]
    if not ids:
        return _empty("ids 가 비어 있습니다 (예: ?ids=17,18).")

    out = {}
    rows = (ProductSourceSnapshot.objects.filter(product_source_id__in=ids)
            .order_by("product_source_id", "observed_at")
            .values("product_source_id", "list_price", "sale_price", "observed_at"))
    for r in rows:
        price = _num(r["sale_price"]) if r["sale_price"] is not None else _num(r["list_price"])
        if price is None:
            continue
        d = out.setdefault(str(r["product_source_id"]), {
            "points": 0, "min": price, "max": price, "min_at": r["observed_at"],
            "first_at": r["observed_at"], "current": price, "current_at": r["observed_at"],
            "previous": None, "list": None,
        })
        d["points"] += 1
        if price < d["min"]:
            d["min"], d["min_at"] = price, r["observed_at"]
        d["max"] = max(d["max"], price)
        if d["points"] > 1:
            d["previous"] = d["current"]
        d["current"], d["current_at"] = price, r["observed_at"]
        d["list"] = _num(r["list_price"])
    if not out:
        return _empty("요청한 상품들에 가격 스냅샷이 아직 없습니다.", ids=ids)
    return _ok({"count": len(out), "items": out})


def _salmal_card_payload(card):
    product = card.product
    ballots = VoteBallot.objects.filter(card_id=card.id)
    total = ballots.count()
    buys = ballots.filter(choice=VoteBallot.Choice.BUY).count()
    tags = [str(x).strip() for x in (card.tags or []) if str(x).strip()]
    product_tags, price = [], None
    if product is not None:
        product_tags = list(ProductTerm.objects.filter(product_source__product_id=product.id)
                            .values_list("term__canonical_name", flat=True).distinct()[:20])
        latest = (ProductSourceSnapshot.objects.filter(product_source__product_id=product.id)
                  .order_by("-observed_at")
                  .values("list_price", "sale_price", "discount_rate", "stock_status", "observed_at")
                  .first())
        if latest:
            price = {"list_price": _num(latest["list_price"]), "sale_price": _num(latest["sale_price"]),
                     "discount_rate": _pct(latest["discount_rate"]),
                     "stock_status": latest["stock_status"], "observed_at": latest["observed_at"]}
    return {
        "card": {"id": card.id, "title": card.title, "description": card.description,
                 "image_url": card.image_url, "tags": tags, "status": card.status,
                 "created_at": card.created_at},
        "product": (None if product is None else {
            "id": product.id, "name": product.canonical_name,
            "brand": product.brand.name if product.brand_id else None,
            "category": product.category.name if product.category_id else None,
            "tags": list(dict.fromkeys([*tags, *product_tags])),
        }),
        "vote_summary": {"total": total, "buy": buys, "pass": total - buys,
                         "buy_pct": (round(buys / total * 100, 1) if total else None),
                         "closed": card.status == VoteCard.Status.CLOSED},
        "price_snapshot": price,
        "as_of": timezone.now().isoformat(),
    }


@require_GET
def salmal_card(request):
    card_id = _int(request, "card_id", 0, 0, 2_147_483_647)
    if not card_id:
        return _empty("card_id를 지정해 주세요.")
    card = VoteCard.objects.filter(id=card_id).select_related(
        "product", "product__brand", "product__category").first()
    if card is None:
        return _empty("해당 살!말? 카드를 찾지 못했습니다.", card_id=card_id)
    return _ok(_salmal_card_payload(card))


@require_GET
def salmal_search(request):
    term = (request.GET.get("term") or "").strip()
    if not term:
        return _empty("term을 지정해 주세요.")
    limit = _int(request, "limit", 5, 1, 10)
    cards = (VoteCard.objects.filter(Q(title__icontains=term)
                                     | Q(product__canonical_name__icontains=term)
                                     | Q(product__brand__name__icontains=term))
             .select_related("product", "product__brand", "product__category")
             .order_by("-created_at")[:limit])
    rows = [_salmal_card_payload(c) for c in cards]
    if not rows:
        return _empty(f"‘{term}’{josa(term, '과', '와')} 연결된 살!말? 카드가 없습니다.", term=term)
    return _ok({"term": term, "items": rows, "count": len(rows)})


# ══════════════════════════════════════════════════════════════
#  검색 지표 (2026-09-22)
#
#  ★ 언급(term_metric_daily) 과 **일부러 나눈다.**
#    저쪽은 '사람이 뭐라고 말했나'(유튜브 댓글 · 커머스 리뷰),
#    이쪽은 '사람이 뭘 찾아봤나'(네이버 · 구글 검색량)다.
#    다른 현상이라 같은 '온도' 라는 이름으로 한 줄에 세우면
#    "무신사 82도 / 구글 56도" 처럼 비교 불가능한 숫자가 나란히 선다.
#    그래서 표도 API 도 화면 카드도 따로 둔다.
#
#  값이 없으면 지어내지 않는다 — 칸은 null 로 두고 사유를 적는다.
# ══════════════════════════════════════════════════════════════

SEARCH_SOURCES = (("naver", "NAVER_SEARCH"), ("google", "GOOGLE_SEARCH"))


def _search_monthly(term):
    """월간 절대 검색량 — 소스별 '가장 최근 달' 한 줄씩.

    네이버 검색광고(N1·N4)와 구글 키워드플래너(K1)가 주는 절대값이다.
    상대지수(트렌드)를 절대값으로 환산할 때의 앵커이기도 하다.
    """
    out, months = {}, []
    for key, code in SEARCH_SOURCES:
        row = (TermSearchMetricMonthly.objects
               .filter(term=term, source__code=code)
               .order_by("-metric_month").values(
                   "metric_month", "search_volume", "pc_volume",
                   "mobile_volume", "competition").first())
        if not row:
            out[key] = None
            continue
        months.append(row["metric_month"])
        out[key] = {
            "month": row["metric_month"].isoformat(),
            "total": row["search_volume"],
            "pc": row["pc_volume"],
            "mobile": row["mobile_volume"],
            # ★ '광고 경쟁 강도' 다. '시장 포화도' 로 읽히지 않게 이름을 그대로 쓴다.
            "competition": row["competition"],
        }

    naver = (out.get("naver") or {}).get("total") or 0
    google = (out.get("google") or {}).get("total") or 0
    total = naver + google
    share = None
    if total:
        share = {"naver": round(naver / total * 100, 1),
                 "google": round(google / total * 100, 1)}
    return {"by_source": out, "total": total or None, "share": share,
            "as_of": max(months).isoformat() if months else None}


def _search_trend(term, days, segment="all"):
    """주간 상대지수 추이 — 창의 끝은 '마지막 적재일' 이다.

    오늘을 끝으로 잡으면 적재가 하루라도 밀린 날 화면이 빈다.
    마지막 적재일 기준이라 하루 적재될 때마다 창이 저절로 하루 민다.
    """
    qs = TermSearchTrend.objects.filter(term=term, segment=segment)
    last = qs.aggregate(d=Max("metric_date"))["d"]
    if not last:
        return [], None
    rows = (qs.filter(metric_date__gt=last - timedelta(days=days))
            .order_by("metric_date")
            .values("metric_date", "source__code", "ratio", "estimated_volume"))
    merged = {}
    for r in rows:
        day = r["metric_date"].isoformat()
        slot = merged.setdefault(day, {"date": day, "naver": None, "google": None,
                                       "naver_volume": None, "google_volume": None})
        key = "naver" if r["source__code"] == "NAVER_SEARCH" else "google"
        slot[key] = _num(r["ratio"], 2)
        slot[key + "_volume"] = r["estimated_volume"]
    return [merged[k] for k in sorted(merged)], last.isoformat()


def _search_seasonality(term):
    """12개월 시즌성 — 구글 키워드플래너의 월별 절대 검색량(K2).

    상대지수가 아니라 절대값이라 '작년 이맘때와 비교' 가 된다.
    수명주기 탭이 쓰기 좋은 모양이다.
    """
    rows = (TermSearchMetricMonthly.objects
            .filter(term=term, source__code="GOOGLE_SEARCH")
            .order_by("metric_month")
            .values("metric_month", "search_volume"))
    series = [{"month": r["metric_month"].strftime("%Y-%m"),
               "volume": r["search_volume"]} for r in rows]
    if len(series) < 3:
        return []          # 두 점으로 시즌성을 말하지 않는다
    return series


def _search_regions(term, limit=17):
    """시·도별 관심도 (G5).

    ★ 이 값은 '용어 하나짜리 요청' 으로 받은 것이어야 의미가 있다.
      여러 용어를 한 번에 물으면 구글이 '그 지역 안에서의 용어 점유율' 을 준다.
      수집 쪽에서 collect_region() 만 쓰도록 막아 뒀다.
      값은 '그 시·도 검색량 대비 비율' 이라 인구 보정이 이미 들어가 있다.
    """
    last = (TermSearchRegion.objects.filter(term=term)
            .aggregate(d=Max("metric_date"))["d"])
    if not last:
        return [], None
    rows = (TermSearchRegion.objects.filter(term=term, metric_date=last)
            .order_by("-value").values("region", "value")[:limit])
    return [{"region": r["region"], "value": r["value"]} for r in rows], last.isoformat()


def _search_segments(term, days):
    """성별·연령 분해 (D2·D3) — 세그먼트별 최근 평균.

    일간 변동값이 아니라 '이 말을 누가 찾나' 라는 캐릭터 규정이라
    수집도 주 1회고, 여기서도 구간 평균 한 숫자로 준다.
    """
    last = (TermSearchTrend.objects.filter(term=term)
            .exclude(segment="all").aggregate(d=Max("metric_date"))["d"])
    if not last:
        return None
    rows = (TermSearchTrend.objects
            .filter(term=term, metric_date__gt=last - timedelta(days=days))
            .exclude(segment="all")
            .values("segment").annotate(avg=Avg("ratio")).order_by("segment"))
    gender, age = {}, {}
    for r in rows:
        seg, value = r["segment"], _num(r["avg"], 2)
        if seg.startswith("gender:"):
            gender[seg.split(":", 1)[1]] = value
        elif seg.startswith("age:"):
            age[seg.split(":", 1)[1]] = value
    if not gender and not age:
        return None
    return {"as_of": last.isoformat(), "gender": gender or None, "age": age or None}


@require_GET
def search(request):
    """GET /api/search?term=팬츠&days=90

    검색 기반 지표만 돌려준다. 언급 기반(/api/trend)과 섞지 않는다.
    """
    name = (request.GET.get("term") or "").strip()
    if not name:
        return _empty("term 을 지정해 주세요. 예: /api/search?term=팬츠")
    term = _resolve_term(name)
    if term is None:
        return _empty(_term_missing_reason(name), term=name)

    days = _int(request, "days", 90, 7, 730)

    monthly = _search_monthly(term)
    trend, trend_as_of = _search_trend(term, days)
    seasonality = _search_seasonality(term)
    regions, regions_as_of = _search_regions(term)
    segments = _search_segments(term, days)

    if not any((monthly["total"], trend, seasonality, regions)):
        return _empty(
            f"‘{term.canonical_name}’ 의 검색 지표가 아직 없습니다. "
            "검색량 수집(collect_search_signals)이 돌면 채워집니다.",
            term=term.canonical_name)

    # 무엇이 아직 없는지 숨기지 않는다 — 화면이 '측정 불가' 로 그릴 수 있게 알린다.
    missing = []
    if not monthly["total"]:
        missing.append("절대 검색량")
    if not trend:
        missing.append("주간 추이")
    if not seasonality:
        missing.append("시즌성(12개월)")
    if not regions:
        missing.append("지역별")
    if not segments:
        missing.append("성별·연령")

    extra = {}
    if missing:
        extra["unavailable"] = {
            "fields": missing,
            "reason": "아직 수집되지 않은 항목입니다 ("
                      + " · ".join(missing) + ").",
        }

    return _ok(
        {
            "term": term.canonical_name,
            "facet": term.term_type,
            "days": days,
            "volume": monthly,
            "trend": trend,
            "trend_as_of": trend_as_of,
            "seasonality": seasonality,
            "regions": regions,
            "regions_as_of": regions_as_of,
            "segments": segments,
            "note": "검색량은 '무엇을 찾아봤나' 입니다. "
                    "언급량(트렌드 온도)과는 다른 현상이라 따로 봅니다.",
        },
        **extra,
    )
