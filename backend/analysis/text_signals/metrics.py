from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import connection, transaction

from apps.core.models import PlatformMetricDaily, TermAssocDaily, TermMetricDaily


METRIC_VERSION = "feedit-unified-text-v1"
PLATFORM_METRIC_VERSION = "feedit-platform-v1"


def _percentiles(values: dict[int, float]) -> dict[int, float]:
    ordered = sorted((value, key) for key, value in values.items())
    if not ordered:
        return {}
    if len(ordered) == 1:
        return {ordered[0][1]: 100.0}
    result: dict[int, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        rank = 100.0 * ((index + end - 1) / 2) / (len(ordered) - 1)
        for _, key in ordered[index:end]:
            result[key] = rank
        index = end
    return result


def _momentum(ma7: float, ma28: float) -> float:
    if ma28 <= 0:
        return 50.0 if ma7 <= 0 else 100.0
    return 100.0 / (1.0 + math.exp(-6.0 * (ma7 / ma28 - 1.0)))


def _rate(value: int, total: int) -> Decimal | None:
    if not total:
        return None
    return Decimal(str(round(value / total * 100, 4)))


def rebuild_text_metrics(
    *,
    since: date,
    until: date,
    metric_version: str = METRIC_VERSION,
) -> dict:
    """검증된 텍스트 언급을 같은 식으로 일별 지표화한다.

    ★ 2026-09-20 — 댓글 · 리뷰만 세던 것을 콘텐츠 본문(영상 제목+설명 · 자막 · 기사)까지 넓혔다.
      댓글만으로는 스타일 용어(고프코어 등)가 거의 잡히지 않아 트렌드가 얇아졌다."""

    history_since = since - timedelta(days=27)
    sql = """
        SELECT m.term_id, d.source_id,
               (d.source_published_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
               m.document_id, d.content_item_id, d.product_source_id,
               m.sentiment_score, m.intent_code, m.evidence_status,
               d.analysis_metadata, d.document_type, ci.profile_id
          FROM analysis.text_term_mention m
          JOIN analysis.text_document d ON d.id = m.document_id
          LEFT JOIN content.content_item ci ON ci.id = d.content_item_id
         WHERE d.source_published_at IS NOT NULL
           AND (d.source_published_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
           AND d.analysis_status = 'DONE'
           AND d.document_type IN ('COMMENT','REVIEW','DESCRIPTION','TRANSCRIPT','ARTICLE')
           AND m.evidence_status IN ('EXACT', 'EXPANDED', 'LEGACY')
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [history_since, until])
        rows = cursor.fetchall()

    grouped: dict[tuple[date, int | None, int], dict] = {}
    for (term_id, source_id, day, document_id, content_id, product_id, sentiment, intent, _status,
         meta, doc_type, profile_id) in rows:
        if day is None:
            continue
        for source_key in (source_id, None):
            key = (day, source_key, term_id)
            item = grouped.setdefault(key, {
                "mentions": 0, "documents": set(), "entities": set(), "creators": set(),
                "sentiments": [], "intents": defaultdict(int), "polarity": defaultdict(int),
            })
            item["mentions"] += 1
            item["documents"].add(document_id)
            if content_id:
                item["entities"].add(f"content:{content_id}")
            if product_id:
                item["entities"].add(f"product:{product_id}")
            metadata = meta if isinstance(meta, dict) else {}
            # 댓글은 쓴 사람, 영상 제목·설명·자막 같은 콘텐츠 본문은 그 크리에이터(채널)를 센다
            creator = metadata.get("author_channel_id") or metadata.get("author")
            if not creator and doc_type in ("DESCRIPTION", "TRANSCRIPT", "ARTICLE") and profile_id:
                creator = f"profile:{profile_id}"
            if creator:
                item["creators"].add(str(creator))
            if sentiment is not None:
                value = float(sentiment)
                item["sentiments"].append(value)
                item["polarity"]["positive" if value > 0.5 else "negative" if value < 0.5 else "neutral"] += 1
            if intent:
                item["intents"][str(intent).lower()] += 1

    by_day_source: dict[tuple[date, int | None], dict[int, float]] = defaultdict(dict)
    for (day, source_id, term_id), value in grouped.items():
        by_day_source[(day, source_id)][term_id] = math.log1p(len(value["documents"]))
    levels = {
        (day, source_id, term_id): rank
        for (day, source_id), values in by_day_source.items()
        for term_id, rank in _percentiles(values).items()
    }

    objects: list[TermMetricDaily] = []
    # ★ 2026-09-20 — source_id 는 출처별 행(정수)과 전체 합산 행(None)이 섞여 있다.
    #   그대로 sorted() 하면 None 과 정수를 비교하다 TypeError 가 나서 지표가 하나도 안 만들어졌다.
    #   합산 행(None)을 앞에 두는 키로 정렬한다.
    ordered_keys = sorted(grouped, key=lambda k: (k[0], -1 if k[1] is None else k[1], k[2]))
    for (day, source_id, term_id) in ordered_keys:
        value = grouped[(day, source_id, term_id)]
        if day < since:
            continue
        history = [levels.get((day - timedelta(days=offset), source_id, term_id), 0.0) for offset in range(27, -1, -1)]
        ma7 = sum(history[-7:]) / 7
        ma28 = sum(history) / 28
        momentum = _momentum(ma7, ma28)
        level = levels[(day, source_id, term_id)]
        mention_total = value["mentions"]
        intents = value["intents"]
        polarity = value["polarity"]
        purchase_index = (
            intents["purchase"] + 0.6 * intents["question"] + 0.4 * intents["experience"]
            + 0.2 * intents["praise"] - 0.4 * intents["critique"]
        ) / max(1, mention_total) * 100
        objects.append(TermMetricDaily(
            term_id=term_id,
            source_id=source_id,
            metric_date=day,
            raw_count=len(value["documents"]),
            mention_count=mention_total,
            document_count=len(value["documents"]),
            content_count=len(value["entities"]),
            creator_count=len(value["creators"]),
            log_count=Decimal(str(round(math.log1p(len(value["documents"])), 6))),
            percentile=Decimal(str(round(level, 4))),
            level=Decimal(str(round(level, 2))),
            ma7=Decimal(str(round(ma7, 4))),
            ma28=Decimal(str(round(ma28, 4))),
            momentum=Decimal(str(round(momentum, 4))),
            trend_temperature=Decimal(str(max(0, min(100, round(0.6 * level + 0.4 * momentum, 2))))),
            sentiment_avg=(Decimal(str(round(sum(value["sentiments"]) / len(value["sentiments"]), 5))) if value["sentiments"] else None),
            positive_count=polarity["positive"], neutral_count=polarity["neutral"], negative_count=polarity["negative"],
            question_count=intents["question"], purchase_count=intents["purchase"], experience_count=intents["experience"],
            praise_count=intents["praise"], critique_count=intents["critique"], chitchat_count=intents["chitchat"],
            positive_rate=_rate(polarity["positive"], mention_total), neutral_rate=_rate(polarity["neutral"], mention_total),
            negative_rate=_rate(polarity["negative"], mention_total), question_rate=_rate(intents["question"], mention_total),
            purchase_rate=_rate(intents["purchase"], mention_total), experience_rate=_rate(intents["experience"], mention_total),
            praise_rate=_rate(intents["praise"], mention_total), critique_rate=_rate(intents["critique"], mention_total),
            purchase_intent_index=Decimal(str(round(max(0, min(100, purchase_index)), 4))),
            metric_version=metric_version,
            metrics={"basis": "validated text evidence", "timezone": "Asia/Seoul"},
        ))

    with transaction.atomic():
        TermMetricDaily.objects.filter(
            metric_version=metric_version,
            metric_date__range=(since, until),
        ).delete()
        TermMetricDaily.objects.bulk_create(objects, batch_size=2000)

    platform_count = rebuild_platform_metrics(since=since, until=until)
    association_count = rebuild_term_associations(
        since=since,
        until=until,
        metric_version=metric_version,
    )
    return {
        "term_metrics": len(objects),
        "term_associations": association_count,
        "platform_metrics": platform_count,
    }


def rebuild_term_associations(
    *,
    since: date,
    until: date,
    metric_version: str = METRIC_VERSION,
    limit_per_term: int = 50,
) -> int:
    """같은 원문 안에서 함께 검증된 용어를 챗봇 연관어 지표로 만든다."""

    mention_sql = """
        SELECT (d.source_published_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
               m.document_id, m.term_id
          FROM analysis.text_term_mention m
          JOIN analysis.text_document d ON d.id=m.document_id
         WHERE d.source_published_at IS NOT NULL
           AND (d.source_published_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
           AND d.analysis_status='DONE'
           AND d.document_type IN ('COMMENT','REVIEW','DESCRIPTION','TRANSCRIPT','ARTICLE')
           AND m.evidence_status IN ('EXACT','EXPANDED','LEGACY')
    """
    universe_sql = """
        SELECT (source_published_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
               count(*)
          FROM analysis.text_document
         WHERE source_published_at IS NOT NULL
           AND (source_published_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
           AND analysis_status='DONE'
           AND document_type IN ('COMMENT','REVIEW','DESCRIPTION','TRANSCRIPT','ARTICLE')
         GROUP BY 1
    """
    with connection.cursor() as cursor:
        cursor.execute(mention_sql, [since, until])
        mention_rows = cursor.fetchall()
        cursor.execute(universe_sql, [since, until])
        universes = {row[0]: int(row[1]) for row in cursor.fetchall()}

    document_terms: dict[tuple[date, int], set[int]] = defaultdict(set)
    for day, document_id, term_id in mention_rows:
        document_terms[(day, document_id)].add(term_id)

    term_counts: dict[date, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    cooccurrences: dict[date, dict[int, dict[int, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for (day, _document_id), terms in document_terms.items():
        ordered = sorted(terms)
        for term_id in ordered:
            term_counts[day][term_id] += 1
        for index, source_term_id in enumerate(ordered):
            for target_term_id in ordered[index + 1:]:
                cooccurrences[day][source_term_id][target_term_id] += 1
                cooccurrences[day][target_term_id][source_term_id] += 1

    objects: list[TermAssocDaily] = []
    for day, sources in cooccurrences.items():
        universe = max(1, universes.get(day, len({doc for d, doc in document_terms if d == day})))
        for source_term_id, targets in sources.items():
            source_count = term_counts[day][source_term_id]
            scored = []
            for target_term_id, cooccurrence_count in targets.items():
                target_count = term_counts[day][target_term_id]
                if not source_count or not target_count:
                    continue
                lift = universe * cooccurrence_count / (source_count * target_count)
                pmi = math.log2(lift) if lift > 0 else 0.0
                scored.append((target_term_id, cooccurrence_count, lift, pmi))
            scored.sort(key=lambda row: (row[3], row[1]), reverse=True)
            denominator = max(1, len(scored) - 1)
            for rank, (target_term_id, count, lift, pmi) in enumerate(
                scored[:limit_per_term],
                start=1,
            ):
                percentile = (
                    100.0
                    if len(scored) == 1
                    else 100.0 * (len(scored) - rank) / denominator
                )
                objects.append(TermAssocDaily(
                    basis=TermAssocDaily.Basis.TEXT,
                    source_term_id=source_term_id,
                    target_term_id=target_term_id,
                    metric_date=day,
                    cooccurrence_count=count,
                    lift=Decimal(str(round(lift, 6))),
                    pmi=Decimal(str(round(pmi, 6))),
                    association_percentile=Decimal(str(round(percentile, 4))),
                    association_rank=rank,
                    is_new=False,
                    metric_version=metric_version,
                    metrics={"basis": "validated document cooccurrence"},
                ))

    with transaction.atomic():
        # ★ 2026-09-21 — basis="TEXT" 로 한정한다.
        #   이 조건이 없으면 검색 기반(SEARCH) 연관어까지 같이 지워진다.
        #   텍스트 재계산은 매일 돌고 검색 수집은 주기가 달라서,
        #   조건 없이 지우면 "어제는 있었는데 오늘 없어졌다" 가 된다.
        TermAssocDaily.objects.filter(
            metric_version=metric_version,
            metric_date__range=(since, until),
            basis=TermAssocDaily.Basis.TEXT,
        ).delete()
        TermAssocDaily.objects.bulk_create(objects, batch_size=2000)
    return len(objects)


def rebuild_platform_metrics(*, since: date, until: date) -> int:
    sql = """
        WITH docs AS (
            SELECT d.id, d.source_id,
                   (d.source_published_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
                   d.analysis_status,
                   CASE WHEN d.analysis_metadata->>'keep' IN ('true','false')
                        THEN (d.analysis_metadata->>'keep')::boolean ELSE false END AS kept,
                   d.analysis_metadata->>'intent' AS intent,
                   CASE WHEN jsonb_typeof(d.analysis_metadata->'candidates')='array'
                        THEN jsonb_array_length(d.analysis_metadata->'candidates')
                        ELSE 0 END AS candidates
             FROM analysis.text_document d
             WHERE d.source_published_at IS NOT NULL
               AND (d.source_published_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
               AND d.document_type IN ('COMMENT','REVIEW','DESCRIPTION','TRANSCRIPT','ARTICLE')
        ), mention_stats AS (
            SELECT m.document_id,
                   count(*) AS mentions,
                   count(*) FILTER (WHERE m.evidence_status IN ('EXACT','EXPANDED')) AS valid_evidence,
                   count(*) FILTER (WHERE m.sentiment_score > 0.5) AS positive,
                   count(*) FILTER (WHERE m.sentiment_score < 0.5) AS negative
              FROM analysis.text_term_mention m
              JOIN docs d ON d.id=m.document_id
             GROUP BY m.document_id
        )
        SELECT d.source_id, d.metric_date,
               count(*) AS documents,
               count(*) FILTER (WHERE d.analysis_status='DONE') AS analyzed,
               count(*) FILTER (WHERE d.kept) AS kept,
               coalesce(sum(m.mentions),0) AS mentions,
               coalesce(sum(m.valid_evidence),0) AS valid_evidence,
               coalesce(sum(m.positive),0) AS positive,
               coalesce(sum(m.negative),0) AS negative,
               count(*) FILTER (WHERE d.intent IN ('PURCHASE','QUESTION')) AS purchase_docs,
               coalesce(sum(d.candidates),0) AS candidates
          FROM docs d
          LEFT JOIN mention_stats m ON m.document_id=d.id
         GROUP BY d.source_id, d.metric_date
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [since, until])
        rows = cursor.fetchall()
    objects = []
    for source_id, day, docs, analyzed, kept, mentions, valid, positive, negative, purchase_docs, candidates in rows:
        objects.append(PlatformMetricDaily(
            source_id=source_id,
            metric_date=day,
            document_count=docs,
            analyzed_document_count=analyzed,
            kept_document_count=kept,
            mention_count=mentions,
            candidate_count=candidates,
            analysis_coverage_rate=_rate(analyzed, docs),
            evidence_valid_rate=_rate(valid, mentions),
            positive_rate=_rate(positive, mentions),
            negative_rate=_rate(negative, mentions),
            purchase_intent_rate=_rate(purchase_docs, docs),
            metric_version=PLATFORM_METRIC_VERSION,
            metrics={"timezone": "Asia/Seoul"},
        ))
    with transaction.atomic():
        PlatformMetricDaily.objects.filter(
            metric_version=PLATFORM_METRIC_VERSION,
            metric_date__range=(since, until),
        ).delete()
        PlatformMetricDaily.objects.bulk_create(objects, batch_size=1000)
    return len(objects)
