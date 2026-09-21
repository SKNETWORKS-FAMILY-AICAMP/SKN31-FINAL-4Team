from __future__ import annotations

from collections import Counter
from decimal import Decimal

from django.db import transaction

from analysis.source_ingestion.common import normalize_brand_name
from apps.core.models import Brand, BrandSource, Source


def _unique_brand_lookup() -> dict[str, Brand]:
    lookup: dict[str, Brand | None] = {}
    for brand in Brand.objects.filter(status=Brand.Status.ACTIVE).only(
        "id", "name", "english_name"
    ):
        for value in (brand.name, brand.english_name):
            key = normalize_brand_name(value) if value else ""
            if not key:
                continue
            if key in lookup and lookup[key] != brand:
                lookup[key] = None
            else:
                lookup[key] = brand
    return {key: brand for key, brand in lookup.items() if brand is not None}


@transaction.atomic
def auto_map_ably_brand_sources(
    *,
    brand_source_ids: list[int] | None = None,
) -> dict:
    """Map only unique exact ABLY names; leave every other row UNMAPPED."""

    source = Source.objects.get(code__iexact="ABLY")
    queryset = BrandSource.objects.select_for_update().filter(
        source=source,
        brand__isnull=True,
        mapping_status=BrandSource.MappingStatus.UNMAPPED,
    )
    if brand_source_ids is not None:
        queryset = queryset.filter(id__in=brand_source_ids)

    lookup = _unique_brand_lookup()
    mapped = []
    kinds = Counter()
    for brand_source in queryset:
        key = normalize_brand_name(brand_source.name) if brand_source.name else ""
        canonical_brand = lookup.get(key)
        if canonical_brand is None:
            continue

        brand_source.brand = canonical_brand
        brand_source.mapping_status = BrandSource.MappingStatus.AUTO_MAPPED
        brand_source.mapping_method = BrandSource.MappingMethod.EXACT_NAME
        brand_source.mapping_confidence = Decimal("1.0000")
        brand_source.save(
            update_fields=[
                "brand",
                "mapping_status",
                "mapping_method",
                "mapping_confidence",
                "updated_at",
            ]
        )
        mapped.append(brand_source)
        kinds[(brand_source.attributes or {}).get("candidate_kind", "UNKNOWN")] += 1

    for brand_id in {item.brand_id for item in mapped}:
        Brand.objects.filter(pk=brand_id).update(
            source_count=BrandSource.objects.filter(brand_id=brand_id).count()
        )

    return {
        "mapped": len(mapped),
        "mapped_by_candidate_kind": dict(kinds),
        "brand_source_ids": [item.id for item in mapped],
    }

