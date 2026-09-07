import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

import django

django.setup()


from django.utils import timezone

from apps.core.models import DictionaryTerm

from analysis.term_discovery.embedding_service import (
    TermEmbeddingService,
)


def build_term_text(term):

    parts = [
        f"패션 용어: {term.canonical_name}",
        f"유형: {term.term_type}",
    ]

    if term.english_name:
        parts.append(
            f"영문명: {term.english_name}"
        )

    if term.description:
        parts.append(
            f"설명: {term.description}"
        )

    return "\n".join(parts)


def main():

    service = TermEmbeddingService()

    terms = (
        DictionaryTerm.objects
        .filter(embedding__isnull=True)
        .order_by("id")
    )

    total = terms.count()

    print(
        f"Embedding 대상: {total}개"
    )

    for index, term in enumerate(
        terms.iterator(),
        start=1,
    ):

        text = build_term_text(term)

        vector = service.embed(text)

        term.embedding = vector
        term.embedding_updated_at = (
            timezone.now()
        )

        term.save(
            update_fields=[
                "embedding",
                "embedding_updated_at",
            ]
        )

        print(
            f"[{index}/{total}] "
            f"{term.canonical_name}"
        )


if __name__ == "__main__":
    main()