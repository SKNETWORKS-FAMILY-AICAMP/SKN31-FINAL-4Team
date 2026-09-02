from __future__ import annotations

from dataclasses import dataclass

from apps.core.models import (
    Brand,
    BrandAlias,
    Source,
)


@dataclass
class BrandMappingResult:
    brand: Brand | None
    matched: bool
    method: str | None
    source_brand_code: str | None
    source_brand_name: str | None


class BrandMapper:

    def map(
        self,
        *,
        source: Source,
        source_brand_code: str | None,
        name_ko: str | None,
        name_en: str | None,
    ) -> BrandMappingResult:

        # ======================================================
        # 1. 플랫폼 브랜드 코드 기준
        # ======================================================

        if source_brand_code:
            alias = (
                BrandAlias.objects
                .select_related("brand")
                .filter(
                    source=source,
                    source_brand_code=(
                        source_brand_code
                    ),
                )
                .first()
            )

            if alias:
                return BrandMappingResult(
                    brand=alias.brand,
                    matched=True,
                    method="SOURCE_CODE",
                    source_brand_code=(
                        source_brand_code
                    ),
                    source_brand_name=(
                        name_ko
                        or name_en
                    ),
                )

        # ======================================================
        # 2. 플랫폼 alias 이름
        # ======================================================

        names = [
            value.strip()
            for value in (
                name_ko,
                name_en,
            )
            if value
            and value.strip()
        ]

        for name in names:

            alias = (
                BrandAlias.objects
                .select_related("brand")
                .filter(
                    source=source,
                    alias__iexact=name,
                )
                .first()
            )

            if alias:
                return BrandMappingResult(
                    brand=alias.brand,
                    matched=True,
                    method="SOURCE_ALIAS",
                    source_brand_code=(
                        source_brand_code
                    ),
                    source_brand_name=name,
                )

        # ======================================================
        # 3. FEEDIT Brand exact name
        # ======================================================

        if name_ko:

            brand = (
                Brand.objects
                .filter(
                    name__iexact=(
                        name_ko.strip()
                    )
                )
                .first()
            )

            if brand:
                return BrandMappingResult(
                    brand=brand,
                    matched=True,
                    method="BRAND_NAME",
                    source_brand_code=(
                        source_brand_code
                    ),
                    source_brand_name=(
                        name_ko
                    ),
                )

        if name_en:

            brand = (
                Brand.objects
                .filter(
                    name_en__iexact=(
                        name_en.strip()
                    )
                )
                .first()
            )

            if brand:
                return BrandMappingResult(
                    brand=brand,
                    matched=True,
                    method="BRAND_NAME_EN",
                    source_brand_code=(
                        source_brand_code
                    ),
                    source_brand_name=(
                        name_en
                    ),
                )

        # ======================================================
        # 4. 실패
        # ======================================================

        return BrandMappingResult(
            brand=None,
            matched=False,
            method=None,
            source_brand_code=(
                source_brand_code
            ),
            source_brand_name=(
                name_ko
                or name_en
            ),
        )