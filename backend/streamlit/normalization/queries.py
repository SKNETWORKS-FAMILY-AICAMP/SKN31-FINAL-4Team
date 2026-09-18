from __future__ import annotations
import pandas as pd
from django.apps import apps


Brand = apps.get_model("core", "Brand")
BrandSource = apps.get_model("core", "BrandSource")
Category = apps.get_model("core", "Category")


def load_unmapped_brand_sources(
    platform: str = "zigzag",
    limit: int = 100,
    search: str | None = None,
) -> pd.DataFrame:
    """
    진짜 미매핑 BrandSource만 조회.

    조건:
    - brand IS NULL
    - mapping_status = UNMAPPED
    - source.code = platform
    """
    qs = BrandSource.objects.filter(
        brand__isnull=True,
        mapping_status="UNMAPPED",
        source__code__iexact=platform,
    )

    if search:
        from django.db.models import Q

        qs = qs.filter(
            Q(name__icontains=search)
            | Q(english_name__icontains=search)
        )

    rows = list(
        qs.order_by("name", "id")
        .values(
            "id",
            "source_id",
            "source__code",
            "source_brand_id",
            "name",
            "english_name",
            "mapping_status",
            "mapping_method",
            "country_code",
            "image_url",
        )[:limit]
    )

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.rename(
            columns={
                "source__code": "platform",
            }
        )

    return df

def load_brand_categories() -> pd.DataFrame:
    rows = list(
        Category.objects
        .all()
        .order_by("name", "id")
        .values(
            "id",
            "name",
        )
    )
    return pd.DataFrame(rows)


def load_feedit_brands() -> pd.DataFrame:
    rows = list(
        Brand.objects
        .all()
        .order_by("name", "id")
        .values(
            "id",
            "brand_code",
            "name",
            "english_name",
        )
    )

    return pd.DataFrame(rows)

def get_brand_source(brand_source_id: int):
    return (
        BrandSource.objects
        .select_related("source")
        .get(id=brand_source_id)
    )
