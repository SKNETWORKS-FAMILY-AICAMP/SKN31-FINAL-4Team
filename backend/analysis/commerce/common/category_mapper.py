from __future__ import annotations

from dataclasses import dataclass

from apps.core.models import (
    Category,
    CategoryAlias,
    Source,
)


@dataclass
class CategoryMappingResult:
    category: Category | None
    matched: bool
    method: str | None

    source_category_code: str | None
    source_category_name: str | None


class CategoryMapper:

    def map(
        self,
        *,
        source: Source,
        source_category: dict,
    ) -> CategoryMappingResult:

        code, name = (
            self._deepest_category(
                source_category
            )
        )

        if not code and not name:
            return CategoryMappingResult(
                category=None,
                matched=False,
                method=None,
                source_category_code=None,
                source_category_name=None,
            )

        # ======================================================
        # 1. source category code
        # ======================================================

        if code:

            alias = (
                CategoryAlias.objects
                .select_related("category")
                .filter(
                    source=source,
                    source_category_code=code,
                )
                .first()
            )

            if alias:
                return CategoryMappingResult(
                    category=alias.category,
                    matched=True,
                    method="SOURCE_CODE",
                    source_category_code=code,
                    source_category_name=name,
                )

        # ======================================================
        # 2. source category name
        # ======================================================

        if name:

            alias = (
                CategoryAlias.objects
                .select_related("category")
                .filter(
                    source=source,
                    source_category_name__iexact=name,
                )
                .first()
            )

            if alias:
                return CategoryMappingResult(
                    category=alias.category,
                    matched=True,
                    method="SOURCE_NAME",
                    source_category_code=code,
                    source_category_name=name,
                )

        # ======================================================
        # 3. FEEDIT category exact match
        # ======================================================

        if name:

            category = (
                Category.objects
                .filter(
                    name__iexact=name
                )
                .order_by(
                    "-level"
                )
                .first()
            )

            if category:
                return CategoryMappingResult(
                    category=category,
                    matched=True,
                    method="CATEGORY_NAME",
                    source_category_code=code,
                    source_category_name=name,
                )

        # ======================================================
        # 4. 실패
        # ======================================================

        return CategoryMappingResult(
            category=None,
            matched=False,
            method=None,
            source_category_code=code,
            source_category_name=name,
        )

    @staticmethod
    def _deepest_category(
        source_category: dict,
    ) -> tuple[
        str | None,
        str | None,
    ]:

        for depth in (
            4,
            3,
            2,
            1,
        ):

            code = source_category.get(
                f"depth{depth}_code"
            )

            name = source_category.get(
                f"depth{depth}_name"
            )

            if code or name:
                return (
                    str(code)
                    if code
                    else None,
                    name,
                )

        return None, None