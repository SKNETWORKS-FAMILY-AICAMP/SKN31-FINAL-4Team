from __future__ import annotations

from django.db import transaction

from apps.core.models import CrawlTarget, Source

from .detail_categories import (
    build_ably_detail_target_name,
    iter_ably_detail_categories,
)
from .register_detail_ranking_targets import (
    upsert_ably_detail_ranking_targets,
)


@transaction.atomic
def replace_ably_targets_with_detail_rankings() -> list[CrawlTarget]:
    """Deactivate old ABLY targets and activate only 27 detail rankings.

    Historical targets are disabled instead of physically deleted because a
    hard delete would cascade into their CrawlRun/RawDocument history.
    """

    source = Source.objects.get(code__iexact="ABLY")
    detail_target_names = [
        build_ably_detail_target_name(category)
        for category in iter_ably_detail_categories()
    ]

    (
        CrawlTarget.objects.filter(source=source, is_active=True)
        .exclude(name__in=detail_target_names)
        .update(is_active=False)
    )

    return upsert_ably_detail_ranking_targets(source=source)


def upsert_ably_targets() -> list[CrawlTarget]:
    """Default ABLY registration entry point."""

    return replace_ably_targets_with_detail_rankings()
