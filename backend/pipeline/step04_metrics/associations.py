from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import log

from django.db import transaction

from apps.core.models import TermAssocDaily

from .common import (
    METRIC_VERSION,
    clamp,
    execute_query,
    percentile_rank,
)


@transaction.atomic
def build_term_associations(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
    min_cooccurrence: int = 2,
    top_n: int = 30,
) -> dict:
    """
    TextTermMention 기반 TEXT 연관 지표 생성.

    날짜 기준:
    - COMMENT: TextDocument.analysis_metadata.published_at
    - REVIEW: ProductReview.source_created_at

    TermAssocDaily의 TEXT basis만 재계산한다.
    SEARCH association은 건드리지 않는다.
    """

    basis = TermAssocDaily.Basis.TEXT

    # ---------------------------------------------------------
    # 1. 같은 날짜 / 버전 / TEXT 결과만 재생성
    # ---------------------------------------------------------
    TermAssocDaily.objects.filter(
        metric_date=metric_date,
        metric_version=metric_version,
        basis=basis,
    ).delete()

    # ---------------------------------------------------------
    # 2. 해당 날짜의 확정 TextTermMention 조회
    # ---------------------------------------------------------
    sql = """
    WITH dated_mentions AS (
        SELECT DISTINCT
            ttm.document_id,
            ttm.term_id,
            CASE
                WHEN td.document_type = 'COMMENT' THEN
                    (
                        NULLIF(
                            td.analysis_metadata->>'published_at',
                            ''
                        )::timestamptz
                        AT TIME ZONE 'Asia/Seoul'
                    )::date

                WHEN td.document_type = 'REVIEW' THEN
                    (
                        pr.source_created_at
                        AT TIME ZONE 'Asia/Seoul'
                    )::date

                ELSE NULL
            END AS metric_date

        FROM analysis.text_term_mention ttm

        JOIN analysis.text_document td
          ON td.id = ttm.document_id

        LEFT JOIN commerce.product_review pr
          ON td.document_type = 'REVIEW'
         AND COALESCE(
                td.analysis_metadata->>'review_id',
                ''
             ) ~ '^[0-9]+$'
         AND pr.id = (
                td.analysis_metadata->>'review_id'
             )::bigint

        WHERE td.analysis_status = 'DONE'
          AND td.document_type IN (
              'COMMENT',
              'REVIEW'
          )
    )

    SELECT
        document_id,
        term_id

    FROM dated_mentions

    WHERE metric_date = %s
    """

    mention_rows = execute_query(
        sql,
        [metric_date],
    )

    # ---------------------------------------------------------
    # 3. 문서별 term 집합
    # ---------------------------------------------------------
    docs: dict[int, set[int]] = defaultdict(set)

    for row in mention_rows:
        docs[int(row["document_id"])].add(
            int(row["term_id"])
        )

    term_doc_count: dict[int, int] = defaultdict(int)

    pair_count: dict[
        tuple[int, int],
        int,
    ] = defaultdict(int)

    for term_ids in docs.values():
        ordered = sorted(term_ids)

        for term_id in ordered:
            term_doc_count[term_id] += 1

        for i, source_id in enumerate(ordered):
            for target_id in ordered[i + 1:]:
                pair_count[
                    (source_id, target_id)
                ] += 1

    total_docs = len(docs)

    # ---------------------------------------------------------
    # 4. Lift / PMI 계산
    # ---------------------------------------------------------
    directional = []

    for (
        source_id,
        target_id,
    ), cooccurrence_count in pair_count.items():

        if cooccurrence_count < min_cooccurrence:
            continue

        if total_docs <= 0:
            continue

        source_probability = (
            term_doc_count[source_id]
            / total_docs
        )

        target_probability = (
            term_doc_count[target_id]
            / total_docs
        )

        pair_probability = (
            cooccurrence_count
            / total_docs
        )

        if (
            source_probability > 0
            and target_probability > 0
        ):
            lift = (
                pair_probability
                / (
                    source_probability
                    * target_probability
                )
            )
        else:
            lift = None

        if (
            source_probability > 0
            and target_probability > 0
            and pair_probability > 0
        ):
            pmi = log(
                pair_probability
                / (
                    source_probability
                    * target_probability
                ),
                2,
            )
        else:
            pmi = None

        directional.extend(
            (
                (
                    source_id,
                    target_id,
                    cooccurrence_count,
                    lift,
                    pmi,
                ),
                (
                    target_id,
                    source_id,
                    cooccurrence_count,
                    lift,
                    pmi,
                ),
            )
        )

    # ---------------------------------------------------------
    # 5. source term 기준 그룹화
    # ---------------------------------------------------------
    by_source: dict[
        int,
        list[tuple],
    ] = defaultdict(list)

    for row in directional:
        by_source[row[0]].append(row)

    objects = []

    # ---------------------------------------------------------
    # 6. source별 Top N + percentile/rank
    # ---------------------------------------------------------
    for (
        source_id,
        source_rows,
    ) in by_source.items():

        source_rows.sort(
            key=lambda row: (
                (
                    row[4]
                    if row[4] is not None
                    else -999
                ),
                row[2],
            ),
            reverse=True,
        )

        source_rows = source_rows[:top_n]

        percentile_map = percentile_rank(
            {
                index: (
                    row[4]
                    if row[4] is not None
                    else 0
                )
                for index, row
                in enumerate(source_rows)
            }
        )

        # 이전 TEXT association만 비교한다.
        # SEARCH association은 is_new 판정에도 섞지 않는다.
        previous_targets = set(
            TermAssocDaily.objects.filter(
                source_term_id=source_id,
                metric_date__lt=metric_date,
                metric_version=metric_version,
                basis=basis,
            ).values_list(
                "target_term_id",
                flat=True,
            )
        )

        for index, row in enumerate(
            source_rows
        ):
            (
                _,
                target_id,
                cooccurrence_count,
                lift,
                pmi,
            ) = row

            objects.append(
                TermAssocDaily(
                    source_term_id=source_id,
                    target_term_id=target_id,
                    metric_date=metric_date,
                    cooccurrence_count=(
                        cooccurrence_count
                    ),
                    lift=lift,
                    pmi=pmi,
                    association_percentile=clamp(
                        percentile_map.get(
                            index,
                            0,
                        )
                    ),
                    association_rank=index + 1,
                    is_new=(
                        target_id
                        not in previous_targets
                    ),

                    # 실제 DB 컬럼
                    basis=basis,

                    metric_version=metric_version,

                    metrics={
                        "document_count": total_docs,
                        "basis": "TEXT",
                        "mention_basis": (
                            "analysis."
                            "text_term_mention"
                        ),
                    },
                )
            )

    # ---------------------------------------------------------
    # 7. 저장
    # ---------------------------------------------------------
    TermAssocDaily.objects.bulk_create(
        objects,
        batch_size=1000,
    )

    return {
        "metric_date": str(metric_date),
        "metric_version": metric_version,
        "basis": "TEXT",
        "document_count": total_docs,
        "pair_count": len(pair_count),
        "saved": len(objects),
    }