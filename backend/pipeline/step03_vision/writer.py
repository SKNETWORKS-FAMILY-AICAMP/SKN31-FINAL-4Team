from __future__ import annotations

from django.db import transaction

from apps.core.models import (
    DictionaryTerm,
    ProductSource,
    ProductTerm,
)

from .config import RELATION_TYPE


@transaction.atomic
def save_vision_style(
    *,
    product_source_id: int,
    style_label: str,
) -> dict:
    """
    Vision은 STEP02 결과를 재작성하지 않는다.

    기존 ProductTerm delete 없음.
    normalized attributes 수정 없음.
    STYLE이 이미 생겼다면 저장하지 않음.
    """

    product_source = (
        ProductSource.objects
        .select_for_update()
        .get(id=product_source_id)
    )

    has_style = (
        ProductTerm.objects
        .filter(
            product_source=product_source,
            term__term_type="STYLE",
        )
        .exists()
    )

    if has_style:
        return {
            "status": "SKIPPED",
            "reason": "STYLE_ALREADY_EXISTS",
            "product_source_id": product_source.id,
        }

    style_term = (
        DictionaryTerm.objects
        .filter(
            term_type="STYLE",
            canonical_name=style_label,
            status="ACTIVE",
        )
        .first()
    )

    if style_term is None:
        raise ValueError(
            "ACTIVE STYLE DictionaryTerm not found: "
            f"{style_label}"
        )

    product_term, created = (
        ProductTerm.objects.get_or_create(
            product_source=product_source,
            term=style_term,
            defaults={
                "relation_type": RELATION_TYPE,
            },
        )
    )

    return {
        "status": (
            "CREATED"
            if created
            else "EXISTS"
        ),
        "product_source_id": product_source.id,
        "term_id": style_term.id,
        "style": style_term.canonical_name,
        "relation_type": getattr(
            product_term,
            "relation_type",
            RELATION_TYPE,
        ),
    }
