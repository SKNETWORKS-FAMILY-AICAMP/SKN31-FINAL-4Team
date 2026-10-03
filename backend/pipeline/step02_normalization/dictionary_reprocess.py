from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.core.models import DictionaryTerm, ProductSource
from pipeline.step02_normalization.pipeline import ProductNormalizationPipeline
from pipeline.step02_normalization.writer import save_step02_result


SUPPORTED_SOURCES = {
    "musinsa",
    "musinsa_used",
    "zigzag",
    "kream",
    "ably",
}


def _normalize_source_code(value: Any) -> str:
    return str(value or "").strip().lower()


def _get_dictionary_term(
    term: str,
) -> DictionaryTerm:
    """
    canonical_name / normalized_name / english_name 기준으로
    DictionaryTerm을 찾는다.

    canonical_name 정확 일치를 가장 우선한다.
    """

    value = str(term or "").strip()

    if not value:
        raise ValueError("term은 비어 있을 수 없습니다.")

    obj = (
        DictionaryTerm.objects
        .filter(
            Q(canonical_name__iexact=value)
            | Q(normalized_name__iexact=value)
            | Q(english_name__iexact=value)
        )
        .order_by(
            "-status",
            "id",
        )
        .first()
    )

    if obj is None:
        raise DictionaryTerm.DoesNotExist(
            f"DictionaryTerm을 찾을 수 없습니다: {value}"
        )

    return obj


def _build_search_terms(
    dictionary_term: DictionaryTerm,
) -> list[str]:
    candidates = [
        dictionary_term.canonical_name,
        dictionary_term.normalized_name,
        dictionary_term.english_name,
    ]

    candidates.extend(
        dictionary_term.aliases.values_list(
            "alias",
            flat=True,
        )
    )

    result: list[str] = []
    seen: set[str] = set()

    for value in candidates:
        value = str(value or "").strip()

        if not value:
            continue

        key = value.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


def get_reprocess_targets(
    term: str,
):
    """
    해당 사전 용어의 영향을 받을 가능성이 있는
    ProductSource queryset을 반환한다.

    source_name 원문을 기준으로 검색한다.
    """

    dictionary_term = _get_dictionary_term(term)

    search_terms = _build_search_terms(
        dictionary_term
    )

    query = Q()

    for search_term in search_terms:
        query |= Q(
            source_name__icontains=search_term
        )

    if not query.children:
        return ProductSource.objects.none()

    return (
        ProductSource.objects
        .filter(query)
        .select_related(
            "source",
            "source_brand",
            "source_category",
        )
        .order_by(
            "source__code",
            "id",
        )
        .distinct()
    )


def preview_reprocess_term(
    term: str,
    *,
    limit: int = 30,
) -> dict[str, Any]:
    """
    실제 DB 변경 없이 영향 범위만 확인한다.
    """

    dictionary_term = _get_dictionary_term(term)

    search_terms = _build_search_terms(
        dictionary_term
    )

    targets = get_reprocess_targets(term)

    total = targets.count()

    by_source: dict[str, int] = {}

    for source_code in (
        targets
        .values_list(
            "source__code",
            flat=True,
        )
        .distinct()
    ):
        normalized_source = _normalize_source_code(
            source_code
        )

        by_source[normalized_source] = (
            targets
            .filter(
                source__code=source_code
            )
            .count()
        )

    samples = []

    for ps in targets[:limit]:
        samples.append(
            {
                "id": ps.id,
                "source": _normalize_source_code(
                    ps.source.code
                ),
                "source_name": ps.source_name,
                "normalized_name": ps.normalized_name,
                "normalized_attributes": (
                    (ps.attributes or {})
                    .get(
                        "normalized",
                        {},
                    )
                ),
            }
        )

    return {
        "dictionary_term_id": dictionary_term.id,
        "term_code": dictionary_term.term_code,
        "term_type": dictionary_term.term_type,
        "canonical_name": (
            dictionary_term.canonical_name
        ),
        "search_terms": search_terms,
        "total": total,
        "by_source": by_source,
        "samples": samples,
    }


def reprocess_term(
    term: str,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    특정 DictionaryTerm의 영향을 받는 ProductSource만
    Step02로 재분석한다.

    dry_run=True:
        분석만 수행하고 DB에는 저장하지 않는다.

    dry_run=False:
        save_step02_result()까지 실행하여
        ProductSource.attributes["normalized"] 및
        ProductTerm을 현재 사전 기준으로 재구축한다.
    """

    dictionary_term = _get_dictionary_term(term)

    search_terms = _build_search_terms(
        dictionary_term
    )

    targets = get_reprocess_targets(term)

    if limit is not None:
        target_ids = list(
            targets.values_list(
                "id",
                flat=True,
            )[:limit]
        )
    else:
        target_ids = list(
            targets.values_list(
                "id",
                flat=True,
            )
        )

    total = len(target_ids)

    if verbose:
        print("=" * 100)
        print("DICTIONARY REPROCESS")
        print("=" * 100)

        print(
            "TERM ID      :",
            dictionary_term.id,
        )

        print(
            "TERM CODE    :",
            dictionary_term.term_code,
        )

        print(
            "TERM TYPE    :",
            dictionary_term.term_type,
        )

        print(
            "CANONICAL    :",
            dictionary_term.canonical_name,
        )

        print(
            "SEARCH TERMS :",
            search_terms,
        )

        print(
            "TARGET COUNT :",
            total,
        )

        print(
            "MODE         :",
            "DRY RUN"
            if dry_run
            else "SAVE",
        )

        print("=" * 100)

    pipelines: dict[
        str,
        ProductNormalizationPipeline,
    ] = {}

    success = 0
    failed = 0

    failed_rows: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for index, ps_id in enumerate(
        target_ids,
        start=1,
    ):
        ps = None
        source_code = "unknown"

        try:
            ps = (
                ProductSource.objects
                .select_related(
                    "source",
                    "source_brand",
                    "source_category",
                )
                .get(id=ps_id)
            )

            source_code = (
                _normalize_source_code(
                    ps.source.code
                )
            )

            if (
                source_code
                not in SUPPORTED_SOURCES
            ):
                raise ValueError(
                    "지원하지 않는 source입니다: "
                    f"{source_code}"
                )

            if source_code not in pipelines:
                pipelines[source_code] = (
                    ProductNormalizationPipeline(
                        source_code=source_code
                    )
                )

            pipeline = pipelines[source_code]

            old_name = ps.normalized_name

            old_attributes = dict(
                (ps.attributes or {}).get(
                    "normalized",
                    {}
                )
            )

            result = pipeline.run(ps)

            new_name = result.get(
                "normalized_name"
            )

            new_attributes = result.get(
                "product_attributes"
            ) or {}

            save_result = None

            if not dry_run:
                save_result = (
                    save_step02_result(
                        product_source_id=ps.id,
                        result=result,
                    )
                )

            success += 1

            row = {
                "product_source_id": ps.id,
                "source": source_code,
                "source_name": ps.source_name,
                "old_normalized_name": old_name,
                "new_normalized_name": new_name,
                "old_attributes": old_attributes,
                "new_attributes": new_attributes,
                "saved": not dry_run,
            }

            if save_result is not None:
                row["product_terms"] = (
                    save_result.get(
                        "product_terms"
                    )
                )

            results.append(row)

            if verbose:
                print()

                print(
                    f"[{index}/{total}] "
                    f"SUCCESS | "
                    f"PS {ps.id} | "
                    f"{source_code}"
                )

                print(
                    "SOURCE :",
                    ps.source_name,
                )

                if (
                    old_name
                    != new_name
                ):
                    print(
                        "NAME   :",
                        old_name,
                        "->",
                        new_name,
                    )

                if (
                    old_attributes
                    != new_attributes
                ):
                    print(
                        "OLD    :",
                        old_attributes,
                    )

                    print(
                        "NEW    :",
                        new_attributes,
                    )

        except Exception as exc:
            failed += 1

            failed_row = {
                "product_source_id": ps_id,
                "source": source_code,
                "error_type": (
                    type(exc).__name__
                ),
                "error": str(exc),
            }

            failed_rows.append(
                failed_row
            )

            if verbose:
                print()

                print(
                    f"[{index}/{total}] "
                    f"FAILED | "
                    f"PS {ps_id} | "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

    summary = {
        "dictionary_term_id": (
            dictionary_term.id
        ),
        "term_code": (
            dictionary_term.term_code
        ),
        "term_type": (
            dictionary_term.term_type
        ),
        "canonical_name": (
            dictionary_term.canonical_name
        ),
        "search_terms": search_terms,
        "dry_run": dry_run,
        "total": total,
        "success": success,
        "failed": failed,
        "results": results,
        "failed_rows": failed_rows,
    }

    if verbose:
        print()
        print("=" * 100)
        print("REPROCESS COMPLETE")
        print("=" * 100)

        print(
            "MODE    :",
            "DRY RUN"
            if dry_run
            else "SAVE",
        )

        print("TOTAL   :", total)
        print("SUCCESS :", success)
        print("FAILED  :", failed)

        print("=" * 100)

    return summary