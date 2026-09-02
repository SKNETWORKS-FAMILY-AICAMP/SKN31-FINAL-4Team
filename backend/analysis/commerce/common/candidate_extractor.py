from __future__ import annotations

from django.db import models

from apps.core.models import (
    Brand,
    BrandAlias,
    Source,
)


def normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    return " ".join(
        str(value)
        .strip()
        .lower()
        .split()
    )


class BrandMatcher:

    def process(
        self,
        *,
        source: Source,
        brand_data: dict,
        detected_count: int = 1,
    ) -> BrandAlias | None:

        source_brand_id = (
            brand_data.get("source_brand_code")
            or brand_data.get("brand_code")
        )

        if not source_brand_id:
            return None

        source_brand_id = str(
            source_brand_id
        ).strip()

        name_ko = (
            brand_data.get("name_ko")
            or brand_data.get("name")
            or source_brand_id
        )

        name_en = (
            brand_data.get("name_en")
        )

        # ==================================================
        # 1. 플랫폼 브랜드 무조건 적재
        # ==================================================

        alias, created = (
            BrandAlias.objects.get_or_create(
                source=source,
                source_brand_id=source_brand_id,
                defaults={
                    "alias": name_ko,
                    "normalized_alias": (
                        normalize_text(name_ko)
                    ),
                    "english_alias": name_en,
                    "normalized_english_alias": (
                        normalize_text(name_en)
                        if name_en
                        else None
                    ),
                    "detected_count": detected_count,
                },
            )
        )

        # ==================================================
        # 2. 이미 존재하면 count 누적 + 이름 최신화
        # ==================================================

        if not created:
            alias.alias = name_ko
            alias.normalized_alias = (
                normalize_text(name_ko)
            )

            alias.english_alias = name_en
            alias.normalized_english_alias = (
                normalize_text(name_en)
                if name_en
                else None
            )

            alias.detected_count += (
                detected_count
            )

            alias.save(
                update_fields=[
                    "alias",
                    "normalized_alias",
                    "english_alias",
                    "normalized_english_alias",
                    "detected_count",
                    "updated_at",
                ]
            )

        # ==================================================
        # 3. 이미 표준 Brand 연결됐으면 끝
        # ==================================================

        if alias.brand_id:
            return alias

        # ==================================================
        # 4. 표준 Brand exact 매칭
        # ==================================================

        matched_brand = (
            self._find_exact_brand(
                name_ko=name_ko,
                name_en=name_en,
            )
        )

        if matched_brand:
            alias.brand = matched_brand

            alias.save(
                update_fields=[
                    "brand",
                    "updated_at",
                ]
            )

        return alias

    def _find_exact_brand(
        self,
        *,
        name_ko: str | None,
        name_en: str | None,
    ) -> Brand | None:

        # 한글 exact
        if name_ko:
            qs = Brand.objects.filter(
                status=Brand.Status.ACTIVE,
                name__iexact=name_ko,
            )

            if qs.count() == 1:
                return qs.first()

        # 영문 exact
        if name_en:
            qs = Brand.objects.filter(
                status=Brand.Status.ACTIVE,
                english_name__iexact=name_en,
            )

            if qs.count() == 1:
                return qs.first()

        # 다른 플랫폼에서 이미 동일 이름으로
        # 특정 Brand에 연결된 경우
        normalized_names = []

        if name_ko:
            normalized_names.append(
                normalize_text(name_ko)
            )

        if name_en:
            normalized_names.append(
                normalize_text(name_en)
            )

        for normalized in normalized_names:

            brand_ids = list(
                BrandAlias.objects
                .filter(
                    brand__isnull=False,
                )
                .filter(
                    models.Q(
                        normalized_alias=normalized,
                    )
                    |
                    models.Q(
                        normalized_english_alias=normalized,
                    )
                )
                .values_list(
                    "brand_id",
                    flat=True,
                )
                .distinct()
            )

            if len(brand_ids) == 1:
                return Brand.objects.get(
                    id=brand_ids[0]
                )

        return None