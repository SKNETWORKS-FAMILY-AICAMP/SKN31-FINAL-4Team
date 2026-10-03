# -*- coding: utf-8 -*-
"""검색 기반 연관어 (2026-09-21)

구글 related queries(G2 rising · G3 top)와 네이버 연관검색어(N6)를
`analysis.term_assoc_daily` 에 **basis="SEARCH"** 로 넣는다.

── 왜 같은 표에 넣나 ──────────────────────────────────────────
화면의 연관어 탭은 하나다. 표를 따로 만들면 API 가 두 번 읽고 두 번 정렬해야
하고, 결국 "이쪽 연관어와 저쪽 연관어가 왜 다르냐"는 질문이 남는다.
같은 표에 basis 로 구분해 담고, 화면에서 배지로 출처를 밝히는 편이 낫다.

── 섞을 때 조심할 것 ──────────────────────────────────────────
① lift · PMI 는 **문서 동시출현 통계**다. 검색 연관어에는 그런 게 없다.
   억지로 채우지 않고 null 로 둔다. 없는 값을 지어내지 않는다.
② cooccurrence_count 는 '동시 언급 문서 수'다. 검색에는 해당 개념이 없어
   0 으로 두고, 구글이 준 원래 숫자는 metrics JSON 에 그대로 보관한다.
③ 소스끼리 비교 가능한 건 association_percentile 하나뿐이다
   — 각 소스 **안에서의** 상대순위라 단위가 없다.
   섞는 규칙은 apps/api/views.py 의 assoc() 에 적혀 있다.

── 사전에 없는 말은 ───────────────────────────────────────────
target_term 은 DictionaryTerm FK 라 사전에 없는 검색어는 넣을 수 없다.
버리지 않고 TermCandidate(후보 용어)로 넘긴다 — 발굴은 그쪽 파이프라인의 일이다.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date

logger = logging.getLogger(__name__)

SEARCH_METRIC_VERSION = "feedit-search-assoc-v1"

# 구글 rising 은 급등이 심하면 숫자 대신 "Breakout" 을 준다 (보통 +5000% 이상).
BREAKOUT_SCORE = 5000.0

_SPACE = re.compile(r"\s+")


def normalize(value) -> str:
    """사전 매칭용 정규화 — 공백 제거 + 소문자."""
    return _SPACE.sub("", str(value or "")).strip().lower()


def _score(kind: str, raw) -> float:
    """랭킹용 점수.

    top    구글이 주는 0~100 인기도
    rising 증가율(%) — 'Breakout' 은 상한값으로 친다

    두 종류를 한 줄로 못 세우므로 kind 별로 따로 순위를 매긴 뒤 합친다.
    여기서는 '같은 kind 안에서의 크기'만 의미가 있다.
    """
    if isinstance(raw, str) and raw.strip().lower() in ("breakout", "급상승"):
        return BREAKOUT_SCORE
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def build_rows(related_queries: dict, term_map: dict, *, platform: str = "GOOGLE",
               limit_per_term: int = 50):
    """수집 결과 → (연관어 행, 사전에 없던 후보) 로 나눈다.

    Django 를 안 쓴다 — 순수 함수라 DB 없이 테스트할 수 있다.

    related_queries : {검색키워드: {"top": [{"query","value"}], "rising": [...]}}
    term_map        : {정규화된 문자열: term_id}

    반환 rows : [{source_term_id, target_term_id, rank, percentile, metrics}]
         misses: {정규화문자열: {"raw":…, "count":…, "sources":{…}}}
    """
    rows, misses = [], {}

    for keyword, buckets in (related_queries or {}).items():
        source_id = term_map.get(normalize(keyword))
        if not source_id:
            continue

        # (target_term_id) → 가장 센 신호 하나만 남긴다.
        # 같은 말이 top 에도 rising 에도 나오면 rising 을 우선한다 — 그쪽이 새 소식이다.
        best = {}
        for kind in ("rising", "top"):
            entries = (buckets or {}).get(kind) or []
            ranked = sorted(entries, key=lambda e: -_score(kind, e.get("value")))
            for order, entry in enumerate(ranked, start=1):
                query = entry.get("query") or entry.get("keyword") or ""
                key = normalize(query)
                if not key:
                    continue
                target_id = term_map.get(key)
                if not target_id:
                    miss = misses.setdefault(key, {"raw": str(query).strip(),
                                                   "count": 0, "sources": {}})
                    miss["count"] += 1
                    miss["sources"][platform] = miss["sources"].get(platform, 0) + 1
                    continue
                if target_id == source_id:
                    continue                      # 자기 자신은 제약(ck_term_assoc_self)에 걸린다
                if target_id in best and best[target_id]["kind"] == "rising":
                    continue                      # 이미 rising 으로 잡혔으면 둔다
                best[target_id] = {
                    "kind": kind,
                    "value": entry.get("value"),
                    "score": _score(kind, entry.get("value")),
                    "order": order,
                }

        if not best:
            continue

        # rising 을 앞에 세우고, 같은 kind 안에서는 점수 순
        ordered = sorted(
            best.items(),
            key=lambda kv: (0 if kv[1]["kind"] == "rising" else 1, -kv[1]["score"]),
        )[:limit_per_term]

        total = len(ordered)
        denominator = max(1, total - 1)
        for rank, (target_id, info) in enumerate(ordered, start=1):
            percentile = 100.0 if total == 1 else 100.0 * (total - rank) / denominator
            rows.append({
                "source_term_id": source_id,
                "target_term_id": target_id,
                "rank": rank,
                "percentile": round(percentile, 4),
                "metrics": {
                    "basis": "search co-query",
                    "platform": platform,
                    "kind": info["kind"],           # rising | top
                    "raw_value": info["value"],     # 구글이 준 원래 값 (숫자 또는 'Breakout')
                    "seed": keyword,
                },
            })

    return rows, misses


# ══════════════════════════════════════════════════════════════
#  Django 쪽 — 위 순수 함수의 결과를 표에 넣는다
# ══════════════════════════════════════════════════════════════

def load_term_map():
    """사전 + 별칭 → {정규화문자열: term_id}"""
    from apps.core.models import DictionaryTerm, TermAlias

    mapping = {}
    for tid, canonical, normalized, english in DictionaryTerm.objects.values_list(
        "id", "canonical_name", "normalized_name", "english_name"
    ):
        for name in (canonical, normalized, english):
            key = normalize(name)
            if key:
                mapping.setdefault(key, tid)
    for tid, alias in TermAlias.objects.values_list("term_id", "alias"):
        key = normalize(alias)
        if key:
            mapping.setdefault(key, tid)
    return mapping


def rebuild_search_associations(*, related_queries, metric_date=None, platform="GOOGLE",
                                metric_version=SEARCH_METRIC_VERSION,
                                limit_per_term=50, record_candidates=True) -> dict:
    """검색 연관어를 term_assoc_daily 에 basis=SEARCH 로 다시 쓴다."""
    from django.db import transaction
    from apps.core.models import TermAssocDaily

    metric_date = metric_date or date.today()
    term_map = load_term_map()
    rows, misses = build_rows(related_queries, term_map,
                              platform=platform, limit_per_term=limit_per_term)

    objects = [
        TermAssocDaily(
            basis=TermAssocDaily.Basis.SEARCH,
            source_term_id=r["source_term_id"],
            target_term_id=r["target_term_id"],
            metric_date=metric_date,
            cooccurrence_count=0,     # 검색에는 '동시 언급 문서 수' 개념이 없다
            lift=None,                # 문서 통계라 검색에는 없다 — 지어내지 않는다
            pmi=None,
            association_percentile=r["percentile"],
            association_rank=r["rank"],
            is_new=(r["metrics"].get("kind") == "rising"),
            metric_version=metric_version,
            metrics=r["metrics"],
        )
        for r in rows
    ]

    with transaction.atomic():
        # ★ basis=SEARCH 로 한정 — 텍스트 연관어를 건드리면 안 된다.
        TermAssocDaily.objects.filter(
            metric_version=metric_version,
            metric_date=metric_date,
            basis=TermAssocDaily.Basis.SEARCH,
        ).delete()
        TermAssocDaily.objects.bulk_create(objects, batch_size=2000)

    candidates = 0
    if record_candidates:
        try:
            candidates = _record_candidates(misses, platform)
        except Exception as exc:               # noqa: BLE001
            # 후보 적재는 부수 작업이다. 여기서 터져도 위에서 저장한
            # 연관어·지표는 이미 커밋돼 있으니 수집 자체를 실패로 만들지 않는다.
            logger.error("후보 용어 단계 실패 — 연관어는 저장됨: %s", exc)

    return {
        "metric_date": str(metric_date),
        "platform": platform,
        "rows": len(objects),
        "missed_terms": len(misses),
        "candidates_touched": candidates,
    }


def _record_candidates(misses: dict, platform: str) -> int:
    """사전에 없던 검색어를 후보 용어로 넘긴다.

    여기서 거르지 않는다 — 패션 관련성 판정은 candidate_refinement 의 일이다.
    (구글 연관검색어는 "니트 옷걸이 거는 법" 같은 방법 질의도 섞여 온다.)

    ★ 2026-09-22 — first_seen_at · last_seen_at 은 **필수 칸**이다.
      auto_now_add 도 기본값도 없어서 안 채우면 NOT NULL 위반으로 터진다.
      (실측: "null value in column first_seen_at ... violates not-null constraint")
      그리고 이 단계는 부수 작업이다 — 한 줄이 실패해도 이미 저장한
      지표·연관어까지 날리면 안 되므로 줄 단위로 감싼다.
    """
    from django.utils import timezone

    from apps.core.models import TermCandidate

    now = timezone.now()
    touched = 0
    for key, info in misses.items():
        raw = (info.get("raw") or "")[:200]
        if not raw:
            continue
        try:
            row = TermCandidate.objects.filter(normalized_term=key).first()
            if row is None:
                row = TermCandidate(
                    normalized_term=key, raw_term=raw,
                    first_seen_at=now, last_seen_at=now,
                    detected_count=0, source_breakdown={},
                )
            row.last_seen_at = now
            if row.first_seen_at is None:      # 예전에 빈 채로 들어간 행 보정
                row.first_seen_at = now
            row.detected_count = (row.detected_count or 0) + info["count"]
            breakdown = dict(row.source_breakdown or {})
            tag = f"search:{platform}"
            breakdown[tag] = breakdown.get(tag, 0) + info["count"]
            row.source_breakdown = breakdown
            row.save()
            touched += 1
        except Exception as exc:               # noqa: BLE001
            logger.warning("후보 용어 저장 실패(건너뜀): %s — %s", key, exc)
    return touched
