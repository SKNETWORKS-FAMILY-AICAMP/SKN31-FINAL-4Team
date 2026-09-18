from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    ContentItem,
    DictionaryTerm,
    TextDocument,
    TextTermMention,
)


# analysis_tags key -> DictionaryTerm 타입
FACET_MAP = {
    "item": "ITEM",
    "style": "STYLE",
    "material": "MATERIAL",
    "detail": "DETAIL",
    "color": "COLOR",
    "tpo": "TPO",
    "brand": "BRAND",
}


def _normalize(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _resolve_term(
    *,
    value: str,
    term_type: str,
) -> DictionaryTerm | None:
    """
    analysis_tags의 문자열을 DictionaryTerm으로 매칭.

    현재 DictionaryTerm 필드명이 프로젝트마다 조금 다를 수 있어서
    실제 존재하는 필드를 보고 자동 선택한다.
    """

    value = str(value or "").strip()

    if not value:
        return None

    fields = {
        field.name
        for field in DictionaryTerm._meta.get_fields()
    }

    qs = DictionaryTerm.objects.all()

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    if "term_type" in fields:
        qs = qs.filter(term_type=term_type)

    elif "facet" in fields:
        qs = qs.filter(facet=term_type)

    elif "type" in fields:
        qs = qs.filter(type=term_type)

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    if "normalized_name" in fields:
        term = qs.filter(
            normalized_name__iexact=_normalize(value),
        ).first()

        if term:
            return term

    if "normalized_term" in fields:
        term = qs.filter(
            normalized_term__iexact=_normalize(value),
        ).first()

        if term:
            return term

    if "name" in fields:
        term = qs.filter(
            name__iexact=value,
        ).first()

        if term:
            return term

    if "term" in fields:
        term = qs.filter(
            term__iexact=value,
        ).first()

        if term:
            return term

    return None


@transaction.atomic
def get_or_create_description_document(
    content_item: ContentItem,
) -> TextDocument | None:
    """
    ContentItem.description을 DESCRIPTION TextDocument로 만든다.

    description이 없으면 None.
    """

    body = str(
        getattr(content_item, "description", "") or ""
    ).strip()

    if not body:
        return None

    external_content_id = (
        getattr(content_item, "external_content_id", None)
        or str(content_item.pk)
    )

    document, created = TextDocument.objects.get_or_create(
        content_item=content_item,
        document_type=TextDocument.DocumentType.DESCRIPTION,
        defaults={
            "source": content_item.source,
            "external_id": (
                f"{external_content_id}:description"
            ),
            "body": body,
            "language": "ko",
            "analysis_status": (
                TextDocument.AnalysisStatus.DONE
            ),
            "analysis_metadata": {
                "origin": "content_item",
                "analysis_source": "analysis_tags",
            },
            "analyzed_at": timezone.now(),
        },
    )

    # 기존 document가 있는데 description이 바뀐 경우
    if not created and document.body != body:
        document.body = body
        document.source = content_item.source
        document.analysis_status = (
            TextDocument.AnalysisStatus.DONE
        )
        document.analyzed_at = timezone.now()

        document.save(
            update_fields=[
                "body",
                "source",
                "analysis_status",
                "analyzed_at",
                "updated_at",
            ]
        )

    return document


@transaction.atomic
def analysis_tags_to_mentions(
    content_item: ContentItem,
) -> dict:
    """
    ContentItem.analysis_tags를 이용해

    ContentItem
        -> DESCRIPTION TextDocument
        -> TextTermMention

    구조로 저장한다.

    같은 document + term은 한 번만 저장한다.
    """

    tags = (
        getattr(content_item, "analysis_tags", None)
        or {}
    )

    document = get_or_create_description_document(
        content_item
    )

    if document is None:
        return {
            "content_item_id": content_item.pk,
            "document_id": None,
            "created": 0,
            "existing": 0,
            "unmatched": [],
            "reason": "description_empty",
        }

    created_count = 0
    existing_count = 0
    unmatched = []

    # 동일 document에서 같은 term이 여러 facet/tag로 들어와도
    # TextTermMention은 한 번만 생성
    seen_term_ids = set()

    for facet_key, term_type in FACET_MAP.items():

        values = tags.get(facet_key) or []

        if not isinstance(values, list):
            continue

        for value in values:

            if not isinstance(value, str):
                continue

            value = value.strip()

            if not value:
                continue

            term = _resolve_term(
                value=value,
                term_type=term_type,
            )

            if term is None:
                unmatched.append(
                    {
                        "value": value,
                        "facet": facet_key,
                        "term_type": term_type,
                    }
                )
                continue

            # 같은 term 중복 방지
            if term.pk in seen_term_ids:
                continue

            seen_term_ids.add(term.pk)

            mention, created = (
                TextTermMention.objects.get_or_create(
                    document=document,
                    term=term,
                    defaults={
                        "mention_text": None,
                        "mention_role": (
                            TextTermMention
                            .MentionRole
                            .CONTEXT
                        ),
                        "analysis_metadata": {
                            "source": (
                                "content_item.analysis_tags"
                            ),
                            "facet": facet_key,
                            "original_value": value,
                        },
                    },
                )
            )

            if created:
                created_count += 1
            else:
                existing_count += 1

    return {
        "content_item_id": content_item.pk,
        "document_id": document.pk,
        "created": created_count,
        "existing": existing_count,
        "unmatched": unmatched,
    }


def backfill_content_analysis_tags(
    *,
    limit: int | None = None,
) -> dict:
    """
    기존 ContentItem 전체 백필.

    analysis_tags가 있고 description이 있는 콘텐츠만 처리.
    """

    qs = (
        ContentItem.objects
        .exclude(description__isnull=True)
        .exclude(description="")
        .order_by("id")
    )

    if limit:
        qs = qs[:limit]

    processed = 0
    created = 0
    existing = 0
    unmatched = []

    for content_item in qs.iterator():

        tags = (
            getattr(
                content_item,
                "analysis_tags",
                None,
            )
            or {}
        )

        if not tags:
            continue

        result = analysis_tags_to_mentions(
            content_item
        )

        processed += 1
        created += result["created"]
        existing += result["existing"]

        if result["unmatched"]:
            unmatched.append(
                {
                    "content_item_id": content_item.pk,
                    "terms": result["unmatched"],
                }
            )

    return {
        "processed_contents": processed,
        "created_mentions": created,
        "existing_mentions": existing,
        "unmatched_contents": len(unmatched),
        "unmatched": unmatched,
    }