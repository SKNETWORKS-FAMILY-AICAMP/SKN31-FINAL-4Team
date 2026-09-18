from __future__ import annotations

from typing import Iterable

from django.db import transaction

from apps.core.models import (
    ContentItem,
    DictionaryTerm,
    TextDocument,
    TextTermMention,
)


@transaction.atomic
def get_or_create_text_document(
    *,
    content_item: ContentItem,
    document_type: str,
    body: str,
    external_id: str | None = None,
    language: str = "ko",
) -> TextDocument:
    """
    ContentItem에 연결된 TextDocument를 생성/조회한다.

    DESCRIPTION / TRANSCRIPT 등은
    ContentItem 하나당 document_type별 하나를 기본으로 사용한다.
    """

    body = (body or "").strip()

    if not body:
        raise ValueError("TextDocument body가 비어 있습니다.")

    document, created = TextDocument.objects.get_or_create(
        content_item=content_item,
        document_type=document_type,
        defaults={
            "source": content_item.source,
            "external_id": external_id,
            "body": body,
            "language": language,
            "analysis_status": TextDocument.AnalysisStatus.PENDING,
        },
    )

    # 기존 Document인데 원문이 갱신된 경우
    if not created and document.body != body:
        document.body = body
        document.analysis_status = TextDocument.AnalysisStatus.PENDING
        document.analyzed_at = None

        document.save(
            update_fields=[
                "body",
                "analysis_status",
                "analyzed_at",
                "updated_at",
            ]
        )

    return document


@transaction.atomic
def save_term_mention(
    *,
    document: TextDocument,
    term: DictionaryTerm,
    mention_text: str | None = None,
    mention_role: str = TextTermMention.MentionRole.CONTEXT,
    sentiment_score=None,
    intent_code: str | None = None,
    confidence=None,
    analysis_metadata: dict | None = None,
) -> tuple[TextTermMention, bool]:
    """
    같은 document + term은 한 번만 저장한다.

    예:
    같은 자막에서 '데님'이 7번 나와도
    TextTermMention은 1 row만 생성.
    """

    mention, created = TextTermMention.objects.get_or_create(
        document=document,
        term=term,
        defaults={
            "mention_text": mention_text,
            "mention_role": mention_role,
            "sentiment_score": sentiment_score,
            "intent_code": intent_code,
            "confidence": confidence,
            "analysis_metadata": analysis_metadata or {},
        },
    )

    return mention, created


@transaction.atomic
def save_term_mentions(
    *,
    document: TextDocument,
    terms: Iterable[DictionaryTerm],
) -> int:
    """
    이미 DictionaryTerm으로 resolve된 term들을 저장한다.

    같은 term이 입력 리스트에 여러 번 있어도
    document당 하나만 저장한다.
    """

    unique_terms = {
        term.pk: term
        for term in terms
        if term is not None and term.pk is not None
    }

    created_count = 0

    for term in unique_terms.values():
        _, created = save_term_mention(
            document=document,
            term=term,
        )

        if created:
            created_count += 1

    return created_count