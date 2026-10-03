from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q

from apps.core.models import Brand, BrandSource, ProductSource


@dataclass
class BrandMappingResult:
    total: int = 0
    already_mapped: int = 0
    mapped_by_source_name: int = 0
    mapped_by_brand_exact: int = 0
    unmapped: int = 0


def _normalize(value) -> str:
    if value in (None, ""):
        return ""

    return (
        unicodedata
        .normalize(
            "NFKC",
            str(value),
        )
        .strip()
        .casefold()
    )


def _model_field_names(model) -> set[str]:
    return {
        field.name
        for field in model._meta.get_fields()
    }


def _mapping_status_auto():
    status = getattr(
        BrandSource,
        "MappingStatus",
        None,
    )

    if status is None:
        return None

    return getattr(
        status,
        "AUTO_MAPPED",
        None,
    )


def _mapping_method_value(
    name: str,
):
    methods = getattr(
        BrandSource,
        "MappingMethod",
        None,
    )

    if methods is None:
        return None

    return getattr(
        methods,
        name,
        None,
    )


def _save_mapping(
    brand_source: BrandSource,
    *,
    brand: Brand,
    method: str,
    confidence: float = 1.0,
) -> None:

    field_names = _model_field_names(
        BrandSource
    )

    brand_source.brand = brand

    update_fields = [
        "brand",
    ]

    if "mapping_status" in field_names:
        value = _mapping_status_auto()

        if value is not None:
            brand_source.mapping_status = value
            update_fields.append(
                "mapping_status"
            )

    if "mapping_method" in field_names:
        value = _mapping_method_value(
            method
        )

        if value is not None:
            brand_source.mapping_method = value
            update_fields.append(
                "mapping_method"
            )

    if "mapping_confidence" in field_names:
        brand_source.mapping_confidence = (
            confidence
        )
        update_fields.append(
            "mapping_confidence"
        )

    if "updated_at" in field_names:
        update_fields.append(
            "updated_at"
        )

    brand_source.save(
        update_fields=list(
            dict.fromkeys(
                update_fields
            )
        )
    )


def _find_from_existing_mapping(
    brand_source: BrandSource,
) -> Brand | None:
    """
    이미 다른 BrandSource에서 사람이 매핑해 둔 결과를 재사용한다.

    예:
    zigzag / 나이키 -> Brand #123

    이후
    musinsa / 나이키

    가 들어오면 같은 FEEDIT Brand #123을 사용할 수 있다.
    """

    names = []

    for value in (
        brand_source.name,
        brand_source.english_name,
    ):
        normalized = _normalize(value)

        if (
            normalized
            and normalized not in names
        ):
            names.append(
                normalized
            )

    if not names:
        return None

    candidates = (
        BrandSource.objects
        .filter(
            brand__isnull=False,
        )
        .exclude(
            id=brand_source.id,
        )
        .select_related(
            "brand",
        )
    )

    matched_brand_ids = set()

    for candidate in candidates.iterator(
        chunk_size=1000
    ):
        candidate_names = {
            _normalize(
                candidate.name
            ),
            _normalize(
                candidate.english_name
            ),
        }

        candidate_names.discard("")

        if any(
            name in candidate_names
            for name in names
        ):
            matched_brand_ids.add(
                candidate.brand_id
            )

    # 서로 다른 FEEDIT Brand가 같은 이름으로 잡히면
    # 자동 선택하지 않는다.
    if len(matched_brand_ids) != 1:
        return None

    brand_id = next(
        iter(matched_brand_ids)
    )

    return Brand.objects.filter(
        id=brand_id
    ).first()


def _find_brand_exact(
    brand_source: BrandSource,
) -> Brand | None:
    """
    FEEDIT Brand 자체에서 exact name을 찾는다.

    프로젝트마다 Brand 모델 필드명이 다를 수 있으므로
    실제 존재하는 이름 필드만 사용한다.
    """

    brand_fields = _model_field_names(
        Brand
    )

    candidate_fields = [
        field_name
        for field_name in (
            "name",
            "korean_name",
            "english_name",
            "display_name",
        )
        if field_name in brand_fields
    ]

    source_names = [
        value
        for value in (
            brand_source.name,
            brand_source.english_name,
        )
        if value not in (
            None,
            "",
        )
    ]

    if (
        not candidate_fields
        or not source_names
    ):
        return None

    query = Q()

    for field_name in candidate_fields:
        for value in source_names:
            query |= Q(
                **{
                    f"{field_name}__iexact":
                        str(value).strip()
                }
            )

    candidates = list(
        Brand.objects
        .filter(query)
        .distinct()[:2]
    )

    # exact 결과가 하나일 때만 자동 매핑
    if len(candidates) != 1:
        return None

    return candidates[0]


@transaction.atomic
def resolve_brand_source(
    brand_source_id: int,
) -> tuple[Brand | None, str]:

    brand_source = (
        BrandSource.objects
        .select_for_update()
        .get(
            id=brand_source_id
        )
    )

    # --------------------------------------------------------
    # 1. 이미 매핑되어 있음
    # --------------------------------------------------------

    if brand_source.brand_id:
        return (
            brand_source.brand,
            "ALREADY_MAPPED",
        )

    # --------------------------------------------------------
    # 2. 기존 BrandSource 매핑 학습값 재사용
    # --------------------------------------------------------

    brand = _find_from_existing_mapping(
        brand_source
    )

    if brand is not None:
        _save_mapping(
            brand_source,
            brand=brand,
            method="EXACT_NAME",
            confidence=1.0,
        )

        return (
            brand,
            "SOURCE_NAME",
        )

    # --------------------------------------------------------
    # 3. FEEDIT Brand exact
    # --------------------------------------------------------

    brand = _find_brand_exact(
        brand_source
    )

    if brand is not None:
        _save_mapping(
            brand_source,
            brand=brand,
            method="EXACT_NAME",
            confidence=1.0,
        )

        return (
            brand,
            "BRAND_EXACT",
        )

    # --------------------------------------------------------
    # 4. 확실하지 않으면 UNMAPPED
    # --------------------------------------------------------

    return (
        None,
        "UNMAPPED",
    )

    # --------------------------------------------------------
    # 4. 확실하지 않으면 그대로 UNMAPPED
    # --------------------------------------------------------

    return (
        None,
        "UNMAPPED",
    )


def resolve_step01_brands(
    product_source_ids: list[int],
) -> BrandMappingResult:

    result = BrandMappingResult()

    if not product_source_ids:
        return result

    brand_source_ids = list(
        ProductSource.objects
        .filter(
            id__in=product_source_ids,
            source_brand__isnull=False,
        )
        .values_list(
            "source_brand_id",
            flat=True,
        )
        .distinct()
    )

    result.total = len(
        brand_source_ids
    )

    for brand_source_id in brand_source_ids:

        brand, method = resolve_brand_source(
            brand_source_id
        )

        if method == "ALREADY_MAPPED":
            result.already_mapped += 1

        elif method == "SOURCE_NAME":
            result.mapped_by_source_name += 1

        elif method == "BRAND_EXACT":
            result.mapped_by_brand_exact += 1

        else:
            result.unmapped += 1

    return result