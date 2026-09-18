from __future__ import annotations

import re
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import (
    ContentItem,
    DictionaryTerm,
    TermAlias,
    TextDocument,
    TextTermMention,
)


# ============================================================
# analysis_tags facet -> DictionaryTerm.term_type
# ============================================================

FACET_MAP = {
    "item": "ITEM",
    "style": "STYLE",
    "material": "MATERIAL",
    "detail": "DETAIL",
    "color": "COLOR",
    "tpo": "TPO",
    "brand": "BRAND",
}


# ============================================================
# NORMALIZE
# ============================================================

def normalize_term(value: str) -> str:
    """
    사전 lookup용 최소 정규화.

    과도한 변형은 하지 않는다.
    DictionaryTerm / TermAlias의 normalized_* 와 비교하는 용도.
    """
    value = str(value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)

    return value


# ============================================================
# TERM RESOLVER
# ============================================================

def resolve_dictionary_term(
    value: str,
    term_type: str,
) -> tuple[DictionaryTerm | None, str | None]:
    """
    analysis_tags 문자열 하나를 canonical DictionaryTerm으로 resolve.

    우선순위:
        1. DictionaryTerm.normalized_name
        2. DictionaryTerm.canonical_name
        3. TermAlias.normalized_alias
        4. TermAlias.alias

    return:
        (DictionaryTerm, match_type)

    match_type:
        canonical
        alias
        None
    """

    value = str(value or "").strip()

    if not value:
        return None, None

    normalized = normalize_term(value)

    # --------------------------------------------------------
    # 1. CANONICAL MATCH
    # --------------------------------------------------------

    term = (
        DictionaryTerm.objects
        .filter(term_type=term_type)
        .filter(
            Q(normalized_name=normalized)
            | Q(canonical_name__iexact=value)
        )
        .first()
    )

    if term:
        return term, "canonical"

    # --------------------------------------------------------
    # 2. ALIAS MATCH
    # --------------------------------------------------------

    alias = (
        TermAlias.objects
        .select_related("term")
        .filter(term__term_type=term_type)
        .filter(
            Q(normalized_alias=normalized)
            | Q(alias__iexact=value)
        )
        .first()
    )

    if alias:
        return alias.term, "alias"

    # --------------------------------------------------------
    # MATCH FAILED
    # --------------------------------------------------------

    return None, None


# ============================================================
# TEXT DOCUMENT
# ============================================================

@transaction.atomic
def get_or_create_text_document(
    *,
    content_item: ContentItem,
    document_type: str,
    body: str,
    external_id: str | None = None,
) -> TextDocument:
    """
    ContentItem에 속한 분석용 TextDocument 생성.

    ContentItem
      ├─ DESCRIPTION
      ├─ TRANSCRIPT
      └─ COMMENT ...
    """

    body = str(body or "").strip()

    if not body:
        raise ValueError("TextDocument body가 비어 있습니다.")

    document, created = TextDocument.objects.get_or_create(
        content_item=content_item,
        document_type=document_type,
        external_id=external_id,
        defaults={
            "source": content_item.source,
            "body": body,
            "language": "ko",
            "analysis_status": TextDocument.AnalysisStatus.DONE,
            "analysis_metadata": {},
            "analyzed_at": timezone.now(),
        },
    )

    if not created and document.body != body:
        document.body = body
        document.analyzed_at = timezone.now()

        document.save(
            update_fields=[
                "body",
                "analyzed_at",
                "updated_at",
            ]
        )

    return document


# ============================================================
# TEXT TERM MENTION
# ============================================================

def save_term_mention(
    *,
    document: TextDocument,
    term: DictionaryTerm,
    original_value: str,
    facet: str,
    match_type: str,
) -> tuple[TextTermMention, bool]:
    """
    같은 document에서 같은 canonical term은 1번만 저장.

    예:
        청바지 -> 데님 팬츠
        데님진 -> 데님 팬츠

    같은 document 안에서 둘 다 나와도
    TextTermMention(term=데님 팬츠)는 하나.
    """

    mention = (
        TextTermMention.objects
        .filter(
            document=document,
            term=term,
        )
        .first()
    )

    if mention:
        return mention, False

    mention = TextTermMention.objects.create(
        document=document,

        # ★ 진짜 중요한 부분
        # 문자열이 아니라 canonical DictionaryTerm FK
        term=term,

        mention_text=None,

        mention_role=(
            TextTermMention.MentionRole.CONTEXT
        ),

        analysis_metadata={
            "source": "content_item.analysis_tags",
            "facet": facet,
            "original_value": original_value,
            "match_type": match_type,
        },
    )

    return mention, True


# ============================================================
# ANALYSIS TAGS -> MENTIONS
# ============================================================

@transaction.atomic
def analysis_tags_to_mentions(
    *,
    content_item: ContentItem,
    document: TextDocument,
) -> dict[str, Any]:
    """
    ContentItem.analysis_tags
        ↓
    canonical / alias lookup
        ↓
    DictionaryTerm
        ↓
    TextTermMention.term FK
    """

    tags = content_item.analysis_tags or {}

    created = []
    existing = []
    unmatched = []

    # 같은 canonical term이 여러 태그를 통해 잡히는 경우 방지
    seen_term_ids: set[int] = set()

    for facet, term_type in FACET_MAP.items():

        values = tags.get(facet) or []

        if not isinstance(values, list):
            continue

        for raw_value in values:

            if not isinstance(raw_value, str):
                continue

            raw_value = raw_value.strip()

            if not raw_value:
                continue

            # ---------------------------------------------
            # 실제 사전 매핑
            # ---------------------------------------------

            term, match_type = resolve_dictionary_term(
                value=raw_value,
                term_type=term_type,
            )

            # ---------------------------------------------
            # 사전 미등록
            # ---------------------------------------------

            if term is None:
                unmatched.append({
                    "original": raw_value,
                    "facet": facet,
                    "term_type": term_type,
                })
                continue

            # ---------------------------------------------
            # 하나의 document에서 canonical term 중복 방지
            # ---------------------------------------------

            if term.pk in seen_term_ids:
                continue

            seen_term_ids.add(term.pk)

            mention, was_created = save_term_mention(
                document=document,
                term=term,
                original_value=raw_value,
                facet=facet,
                match_type=match_type,
            )

            row = {
                "original": raw_value,

                # 실제 canonical 매핑 결과
                "term_id": term.pk,
                "canonical": term.canonical_name,
                "term_type": term.term_type,

                "match_type": match_type,
            }

            if was_created:
                created.append(row)
            else:
                existing.append(row)

    return {
        "content_item_id": content_item.pk,
        "document_id": document.pk,

        "created": created,
        "existing": existing,
        "unmatched": unmatched,

        "created_count": len(created),
        "existing_count": len(existing),
        "unmatched_count": len(unmatched),
    }


# ============================================================
# CONTENT ITEM PIPELINE
# ============================================================

@transaction.atomic
def process_content_item(
    content_item: ContentItem,
) -> dict[str, Any]:
    """
    현재 ContentItem.analysis_tags는 description 분석 결과라고 가정.

    ContentItem
        ↓
    DESCRIPTION TextDocument
        ↓
    analysis_tags
        ↓
    DictionaryTerm / TermAlias
        ↓
    TextTermMention
    """

    description = str(
        content_item.description or ""
    ).strip()

    if not description:
        return {
            "content_item_id": content_item.pk,
            "status": "SKIPPED",
            "reason": "description_empty",
        }

    if not content_item.analysis_tags:
        return {
            "content_item_id": content_item.pk,
            "status": "SKIPPED",
            "reason": "analysis_tags_empty",
        }

    external_content_id = (
        content_item.external_content_id
        or str(content_item.pk)
    )

    # --------------------------------------------------------
    # 1. TextDocument
    # --------------------------------------------------------

    document = get_or_create_text_document(
        content_item=content_item,
        document_type=TextDocument.DocumentType.DESCRIPTION,
        body=description,
        external_id=f"{external_content_id}:description",
    )

    # --------------------------------------------------------
    # 2. 실제 DictionaryTerm mapping
    # --------------------------------------------------------

    result = analysis_tags_to_mentions(
        content_item=content_item,
        document=document,
    )

    result["status"] = "DONE"

    return result


# ============================================================
# BACKFILL
# ============================================================

def backfill_content_items(
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    기존 ContentItem 전체를 TextDocument/TextTermMention으로 백필.
    """

    qs = (
        ContentItem.objects
        .exclude(description__isnull=True)
        .exclude(description="")
        .order_by("id")
    )

    if limit is not None:
        qs = qs[:limit]

    summary = {
        "processed": 0,
        "created_mentions": 0,
        "existing_mentions": 0,
        "unmatched_terms": 0,
        "unmatched": [],
    }

    for content_item in qs:

        if not content_item.analysis_tags:
            continue

        result = process_content_item(
            content_item
        )

        if result.get("status") != "DONE":
            continue

        summary["processed"] += 1

        summary["created_mentions"] += (
            result["created_count"]
        )

        summary["existing_mentions"] += (
            result["existing_count"]
        )

        summary["unmatched_terms"] += (
            result["unmatched_count"]
        )

        if result["unmatched"]:
            summary["unmatched"].append({
                "content_item_id": content_item.pk,
                "terms": result["unmatched"],
            })

    return summary