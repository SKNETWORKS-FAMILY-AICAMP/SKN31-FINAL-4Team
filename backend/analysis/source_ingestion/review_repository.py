from __future__ import annotations

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.core.models import (
    ProductSource,
    ProductReview,
)


class MusinsaReviewRepository:

    @transaction.atomic
    def save_many(
        self,
        reviews,
    ) -> dict:

        created = 0
        updated = 0
        skipped = 0

        for row in reviews:

            product_source = (
                ProductSource.objects
                .filter(
                    source__code__iexact="musinsa",
                    source_product_id=str(
                        row.goods_no
                    ),
                )
                .first()
            )

            if not product_source:
                skipped += 1
                continue

            obj, was_created = (
                ProductReview.objects.update_or_create(
                    product_source=product_source,
                    source_review_id=str(
                        row.review_id
                    ),
                    defaults={
                        "review_type": (
                            row.review_type or ""
                        ),
                        "content": row.content,
                        "grade": row.grade,
                        "goods_option": (
                            row.goods_option or ""
                        ),
                        "like_count": (
                            row.like_count or 0
                        ),
                        "reviewer_sex": (
                            row.reviewer_sex or ""
                        ),
                        "reviewer_height": (
                            row.reviewer_height
                        ),
                        "reviewer_weight": (
                            row.reviewer_weight
                        ),
                        "survey": {
                            "size": (
                                row.survey_size
                            ),
                            "color": (
                                row.survey_color
                            ),
                            "quality": (
                                row.survey_quality
                            ),
                            "thickness": (
                                row.survey_thickness
                            ),
                            "warmth": (
                                row.survey_warmth
                            ),
                        },
                        "source_created_at": (
                            row.created_at
                        ),
                    },
                )
            )

            if was_created:
                created += 1
            else:
                updated += 1

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }