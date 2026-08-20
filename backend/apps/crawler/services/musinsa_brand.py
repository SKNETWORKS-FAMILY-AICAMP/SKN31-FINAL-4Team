# apps/crawler/services/musinsa_brand.py

from django.db import transaction

from apps.crawler.models import (
    MusinsaBrand,
)


class MusinsaBrandService:
    """
    MusinsaBrand 저장 서비스.

    핵심:
    - 새 브랜드는 create
    - 기존 브랜드는 값이 들어온 필드만 update
    - None/빈 문자열 때문에 기존 상세정보를 지우지 않음
    """

    UPDATE_FIELDS = (
        "name_ko",
        "name_en",
        "nation",
        "since_year",
        "logo_url",
        "description",
    )

    @classmethod
    @transaction.atomic
    def save_brand(
        cls,
        brand_data: dict,
    ):
        if not isinstance(
            brand_data,
            dict,
        ):
            raise ValueError("brand_data는 dict여야 합니다.")

        brand_id = brand_data.get("brand_id")

        if not brand_id:
            raise ValueError("brand_id가 없습니다.")

        brand = MusinsaBrand.objects.filter(brand_id=brand_id).first()

        if brand is None:
            brand = MusinsaBrand.objects.create(
                brand_id=brand_id,
                name_ko=(
                    brand_data.get("name_ko") or brand_data.get("name_en") or brand_id
                ),
                name_en=brand_data.get("name_en"),
                nation=brand_data.get("nation"),
                since_year=brand_data.get("since_year"),
                logo_url=brand_data.get("logo_url"),
                description=brand_data.get("description"),
            )

            return brand, True

        changed_fields = []

        for field in cls.UPDATE_FIELDS:
            value = brand_data.get(field)

            if value in (
                None,
                "",
            ):
                continue

            if (
                getattr(
                    brand,
                    field,
                )
                != value
            ):
                setattr(
                    brand,
                    field,
                    value,
                )

                changed_fields.append(field)

        if changed_fields:
            brand.save(
                update_fields=[
                    *changed_fields,
                    "updated_at",
                ]
            )

        return brand, False

    @classmethod
    def save_brands(
        cls,
        brands: list[dict],
    ) -> dict:
        created = 0
        updated = 0
        failed = 0
        errors = []

        for brand_data in brands:
            try:
                _, is_created = cls.save_brand(brand_data)

                if is_created:
                    created += 1

                else:
                    updated += 1

            except Exception as exc:
                failed += 1

                errors.append(
                    {
                        "brand_id": (brand_data.get("brand_id")),
                        "error": str(exc),
                    }
                )

        return {
            "created": created,
            "updated": updated,
            "failed": failed,
            "errors": errors,
        }
