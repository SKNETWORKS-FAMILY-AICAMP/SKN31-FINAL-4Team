from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from django.db import connection, transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from langchain.tools import tool

from apps.core.models import (
    DictionaryTerm,
    DiscoveryExclusion,
    ProductSource,
    TermAlias,
    TermCandidate,
)


MAX_SQL_ROWS = 200


def _json(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        default=str,
        indent=2,
    )


def _choice_values(choices) -> set[str]:
    return {str(value) for value, _ in choices}


def _serialize_instance(obj, *, max_fields: int = 18) -> dict:
    """
    Admin Agent용 가벼운 serializer.
    JSON/텍스트가 지나치게 큰 필드는 잘라서 반환한다.
    """
    result = {"id": obj.pk}
    count = 0

    for field in obj._meta.concrete_fields:
        if field.primary_key:
            continue

        name = field.name

        try:
            value = getattr(obj, name)
        except Exception:
            continue

        if hasattr(value, "pk"):
            value = value.pk

        if isinstance(value, Decimal):
            value = str(value)

        if isinstance(value, (dict, list)):
            rendered = json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )
            if len(rendered) > 1500:
                value = rendered[:1500] + "...(truncated)"

        elif isinstance(value, str) and len(value) > 1500:
            value = value[:1500] + "...(truncated)"

        result[name] = value
        count += 1

        if count >= max_fields:
            break

    return result


@tool
def search_dictionary(
    query: str,
    term_type: str | None = None,
    limit: int = 20,
) -> str:
    """
    DictionaryTerm과 TermAlias에서 패션 용어를 검색한다.
    query는 표준명/영문명/정규화명/alias에 사용한다.
    term_type은 BRAND, STYLE, ITEM, DETAIL, MATERIAL, COLOR, TPO 중 하나다.
    """
    query = (query or "").strip()
    limit = max(1, min(int(limit), 50))

    qs = DictionaryTerm.objects.all().prefetch_related("aliases")

    if term_type:
        term_type = term_type.upper().strip()
        valid = _choice_values(DictionaryTerm.TermType.choices)

        if term_type not in valid:
            return _json({
                "error": "INVALID_TERM_TYPE",
                "valid": sorted(valid),
            })

        qs = qs.filter(term_type=term_type)

    if query:
        qs = qs.filter(
            Q(canonical_name__icontains=query)
            | Q(normalized_name__icontains=query)
            | Q(english_name__icontains=query)
            | Q(aliases__alias__icontains=query)
            | Q(aliases__normalized_alias__icontains=query)
        ).distinct()

    rows = []

    for term in qs.order_by("term_type", "canonical_name")[:limit]:
        rows.append({
            "id": term.id,
            "term_code": term.term_code,
            "term_type": term.term_type,
            "canonical_name": term.canonical_name,
            "normalized_name": term.normalized_name,
            "english_name": term.english_name,
            "status": term.status,
            "aliases": [
                {
                    "id": alias.id,
                    "alias": alias.alias,
                    "alias_type": alias.alias_type,
                    "source_id": alias.source_id,
                }
                for alias in term.aliases.all()[:20]
            ],
        })

    return _json({
        "count": len(rows),
        "results": rows,
    })


@tool
def search_candidates(
    query: str = "",
    status: str | None = None,
    min_detected_count: int = 0,
    limit: int = 30,
) -> str:
    """
    TermCandidate를 검색한다.
    query가 있으면 raw_term/normalized_term에서 검색한다.
    status는 PENDING, REVIEWING, RESOLVED, REJECTED 중 하나다.
    """
    query = (query or "").strip()
    limit = max(1, min(int(limit), 100))
    min_detected_count = max(0, int(min_detected_count))

    qs = TermCandidate.objects.select_related("nearest_term").filter(
        detected_count__gte=min_detected_count
    )

    if status:
        status = status.upper().strip()
        valid = _choice_values(TermCandidate.Status.choices)

        if status not in valid:
            return _json({
                "error": "INVALID_STATUS",
                "valid": sorted(valid),
            })

        qs = qs.filter(status=status)

    if query:
        qs = qs.filter(
            Q(raw_term__icontains=query)
            | Q(normalized_term__icontains=query)
        )

    rows = []

    for candidate in qs.order_by(
        "-detected_count",
        "-last_seen_at",
    )[:limit]:
        rows.append({
            "id": candidate.id,
            "term": candidate.normalized_term,
            "raw_term": candidate.raw_term,
            "status": candidate.status,
            "decision": candidate.decision,
            "suggested_type": candidate.suggested_type,
            "detected_count": candidate.detected_count,
            "document_count": candidate.document_count,
            "source_count": candidate.source_count,
            "source_breakdown": candidate.source_breakdown,
            "nearest_term": (
                candidate.nearest_term.canonical_name
                if candidate.nearest_term
                else None
            ),
            "similarity_score": candidate.similarity_score,
            "evidence_s3_uri": candidate.evidence_s3_uri,
        })

    return _json({
        "count": len(rows),
        "results": rows,
    })


@tool
def inspect_candidate(candidate_id: int) -> str:
    """
    TermCandidate 한 건의 상세 상태를 조회한다.
    대표 문맥, 통계, vector match 결과, S3 evidence 경로까지 반환한다.
    """
    try:
        candidate = (
            TermCandidate.objects
            .select_related("nearest_term")
            .get(pk=int(candidate_id))
        )
    except TermCandidate.DoesNotExist:
        return _json({
            "error": "CANDIDATE_NOT_FOUND",
            "candidate_id": candidate_id,
        })

    return _json({
        "id": candidate.id,
        "raw_term": candidate.raw_term,
        "normalized_term": candidate.normalized_term,
        "suggested_type": candidate.suggested_type,
        "suggested_attribute_type": candidate.suggested_attribute_type,
        "detected_count": candidate.detected_count,
        "document_count": candidate.document_count,
        "source_count": candidate.source_count,
        "source_breakdown": candidate.source_breakdown,
        "field_breakdown": candidate.field_breakdown,
        "sample_contexts": candidate.sample_contexts,
        "confidence": candidate.confidence,
        "decision_reason": candidate.decision_reason,
        "nearest_term": (
            {
                "id": candidate.nearest_term_id,
                "canonical_name": candidate.nearest_term.canonical_name,
                "term_type": candidate.nearest_term.term_type,
            }
            if candidate.nearest_term
            else None
        ),
        "similarity_score": candidate.similarity_score,
        "status": candidate.status,
        "decision": candidate.decision,
        "note": candidate.note,
        "first_seen_at": candidate.first_seen_at,
        "last_seen_at": candidate.last_seen_at,
        "evidence_s3_uri": candidate.evidence_s3_uri,
        "evidence_updated_at": candidate.evidence_updated_at,
    })


@tool
def search_products(
    query: str,
    limit: int = 20,
) -> str:
    """
    ProductSource에서 문자열 필드를 대상으로 상품을 검색한다.
    모델 필드가 바뀌어도 CharField/TextField를 동적으로 찾아 검색한다.
    """
    query = (query or "").strip()

    if not query:
        return _json({
            "error": "QUERY_REQUIRED",
        })

    limit = max(1, min(int(limit), 50))

    text_fields = []

    for field in ProductSource._meta.concrete_fields:
        internal_type = field.get_internal_type()

        if internal_type in {
            "CharField",
            "TextField",
        }:
            text_fields.append(field.name)

    # 너무 많은 필드를 OR 검색하지 않도록 우선순위 적용.
    preferred = [
        "source_name",
        "normalized_name",
        "platform_product_name",
        "source_product_id",
        "name",
    ]

    ordered_fields = [
        name
        for name in preferred
        if name in text_fields
    ]

    ordered_fields += [
        name
        for name in text_fields
        if name not in ordered_fields
    ]

    ordered_fields = ordered_fields[:10]

    if not ordered_fields:
        return _json({
            "error": "NO_SEARCHABLE_TEXT_FIELDS",
        })

    condition = Q()

    for field_name in ordered_fields:
        condition |= Q(
            **{
                f"{field_name}__icontains": query,
            }
        )

    qs = ProductSource.objects.filter(condition)[:limit]

    rows = [
        _serialize_instance(obj)
        for obj in qs
    ]

    return _json({
        "searched_fields": ordered_fields,
        "count": len(rows),
        "results": rows,
    })


_WRITE_SQL_RE = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|"
    r"GRANT|REVOKE|COMMENT|COPY|VACUUM|ANALYZE|REFRESH|"
    r"REINDEX|CLUSTER|CALL|DO|LOCK|SET|RESET|"
    r"NEXTVAL|SETVAL|PG_SLEEP|PG_TERMINATE_BACKEND"
    r")\b",
    flags=re.IGNORECASE,
)


@tool
def run_readonly_query(sql: str) -> str:
    """
    PostgreSQL 조회 쿼리를 실행한다.
    SELECT / WITH / EXPLAIN만 허용하며 DB 변경 쿼리는 거부한다.
    최대 200행까지만 반환한다.
    """
    sql = (sql or "").strip()

    if not sql:
        return _json({
            "error": "EMPTY_SQL",
        })

    # trailing semicolon 1개만 허용.
    body = sql[:-1].strip() if sql.endswith(";") else sql

    if ";" in body:
        return _json({
            "error": "MULTIPLE_STATEMENTS_NOT_ALLOWED",
        })

    upper = body.lstrip().upper()

    if not upper.startswith(
        ("SELECT ", "WITH ", "EXPLAIN ")
    ):
        return _json({
            "error": "READ_ONLY_QUERY_REQUIRED",
        })

    if _WRITE_SQL_RE.search(body):
        return _json({
            "error": "WRITE_OR_UNSAFE_SQL_BLOCKED",
        })

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET LOCAL TRANSACTION READ ONLY"
                )
                cursor.execute(
                    "SET LOCAL statement_timeout = '8000ms'"
                )
                cursor.execute(body)

                if cursor.description is None:
                    return _json({
                        "columns": [],
                        "rows": [],
                    })

                columns = [
                    col.name
                    for col in cursor.description
                ]

                fetched = cursor.fetchmany(
                    MAX_SQL_ROWS + 1
                )

    except Exception as exc:
        return _json({
            "error": type(exc).__name__,
            "message": str(exc),
        })

    truncated = len(fetched) > MAX_SQL_ROWS
    fetched = fetched[:MAX_SQL_ROWS]

    return _json({
        "columns": columns,
        "row_count": len(fetched),
        "truncated": truncated,
        "rows": [
            dict(zip(columns, row))
            for row in fetched
        ],
    })


# ============================================================
# WRITE TOOLS
# 아래 3개는 agent.py의 HumanInTheLoopMiddleware에서 승인 필수.
# ============================================================


@tool
@transaction.atomic
def create_alias(
    term_id: int,
    alias: str,
    alias_type: str = "SYNONYM",
    source_id: int | None = None,
) -> str:
    """
    기존 DictionaryTerm에 alias를 추가한다.
    실제 DB 변경 Tool이므로 관리자 승인이 필요하다.
    """
    alias = (alias or "").strip()

    if not alias:
        return _json({
            "error": "ALIAS_REQUIRED",
        })

    try:
        term = DictionaryTerm.objects.get(
            pk=int(term_id)
        )
    except DictionaryTerm.DoesNotExist:
        return _json({
            "error": "TERM_NOT_FOUND",
            "term_id": term_id,
        })

    alias_type = (
        alias_type
        or TermAlias.AliasType.SYNONYM
    ).upper().strip()

    valid = _choice_values(
        TermAlias.AliasType.choices
    )

    if alias_type not in valid:
        return _json({
            "error": "INVALID_ALIAS_TYPE",
            "valid": sorted(valid),
        })

    # 동일 표기가 다른 term에 이미 연결되어 있으면 자동 생성 금지.
    conflict = (
        TermAlias.objects
        .filter(alias__iexact=alias)
        .exclude(term_id=term.id)
        .select_related("term")
        .first()
    )

    if conflict:
        return _json({
            "error": "ALIAS_CONFLICT",
            "alias": alias,
            "existing_term_id": conflict.term_id,
            "existing_term": conflict.term.canonical_name,
        })

    lookup = {
        "term": term,
        "alias": alias,
        "source_id": source_id,
    }

    obj, created = TermAlias.objects.get_or_create(
        **lookup,
        defaults={
            "alias_type": alias_type,
        },
    )

    if not created and obj.alias_type != alias_type:
        obj.alias_type = alias_type
        obj.save(
            update_fields=[
                "alias_type",
                "updated_at",
            ]
        )

    return _json({
        "created": created,
        "alias_id": obj.id,
        "term_id": term.id,
        "term": term.canonical_name,
        "alias": obj.alias,
        "normalized_alias": obj.normalized_alias,
        "alias_type": obj.alias_type,
        "source_id": obj.source_id,
    })


@tool
@transaction.atomic
def create_term(
    canonical_name: str,
    term_type: str,
    english_name: str | None = None,
    description: str | None = None,
) -> str:
    """
    새 DictionaryTerm을 생성한다.
    실제 DB 변경 Tool이므로 관리자 승인이 필요하다.
    """
    canonical_name = (
        canonical_name
        or ""
    ).strip()

    term_type = (
        term_type
        or ""
    ).upper().strip()

    if not canonical_name:
        return _json({
            "error": "CANONICAL_NAME_REQUIRED",
        })

    valid = _choice_values(
        DictionaryTerm.TermType.choices
    )

    if term_type not in valid:
        return _json({
            "error": "INVALID_TERM_TYPE",
            "valid": sorted(valid),
        })

    existing = (
        DictionaryTerm.objects
        .filter(
            term_type=term_type,
            canonical_name__iexact=canonical_name,
        )
        .first()
    )

    if existing:
        return _json({
            "created": False,
            "reason": "ALREADY_EXISTS",
            "term_id": existing.id,
            "canonical_name": existing.canonical_name,
            "term_type": existing.term_type,
        })

    term = DictionaryTerm.objects.create(
        canonical_name=canonical_name,
        term_type=term_type,
        english_name=(
            (english_name or "").strip()
            or None
        ),
        description=(
            (description or "").strip()
            or None
        ),
        status=DictionaryTerm.Status.ACTIVE,
    )

    return _json({
        "created": True,
        "term_id": term.id,
        "canonical_name": term.canonical_name,
        "normalized_name": term.normalized_name,
        "term_type": term.term_type,
    })


@tool
@transaction.atomic
def add_discovery_exclusion(
    term: str,
    reason: str,
    source_id: int | None = None,
    note: str | None = None,
) -> str:
    """
    DiscoveryExclusion에 운영 제외 표현을 추가/갱신한다.
    실제 패션 의미 후보를 함부로 제외하면 안 된다.
    실제 DB 변경 Tool이므로 관리자 승인이 필요하다.
    """
    term = (term or "").strip()
    reason = (reason or "").upper().strip()

    if not term:
        return _json({
            "error": "TERM_REQUIRED",
        })

    valid = _choice_values(
        DiscoveryExclusion.Reason.choices
    )

    if reason not in valid:
        return _json({
            "error": "INVALID_REASON",
            "valid": sorted(valid),
        })

    obj, created = (
        DiscoveryExclusion.objects
        .update_or_create(
            term=term,
            source_id=source_id,
            defaults={
                "reason": reason,
                "note": (
                    (note or "").strip()
                    or None
                ),
                "is_active": True,
            },
        )
    )

    return _json({
        "created": created,
        "id": obj.id,
        "term": obj.term,
        "normalized_term": obj.normalized_term,
        "reason": obj.reason,
        "source_id": obj.source_id,
        "is_active": obj.is_active,
    })


READ_TOOLS = [
    search_dictionary,
    search_candidates,
    inspect_candidate,
    search_products,
    run_readonly_query,
]

WRITE_TOOLS = [
    create_alias,
    create_term,
    add_discovery_exclusion,
]

ALL_TOOLS = [
    *READ_TOOLS,
    *WRITE_TOOLS,
]
