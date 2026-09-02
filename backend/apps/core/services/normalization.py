from __future__ import annotations

import json

import boto3

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.core.models import (
    Brand,
    BrandSource,
    CrawlRun,
    DictionaryTerm,
    MappingCandidate,
    RawDocument,
    TermAlias,
)

from analysis.commerce.musinsa.normalizer import (
    MusinsaNormalizer,
)


# =========================================================
# Common
# =========================================================


def normalize_text(
    value: str | None,
) -> str:
    """
    문자열 비교용 기본 정규화.

    현재는:
    - 앞뒤 공백 제거
    - 소문자 변환
    - 연속 공백 제거

    추후 필요하면:
    - 특수문자 제거
    - 유니코드 정규화
    - 한글/영문 브랜드명 전처리
    등을 공통 normalizer로 확장할 수 있다.
    """

    if not value:
        return ""

    return " ".join(
        str(value)
        .strip()
        .lower()
        .split()
    )


# =========================================================
# S3 RawDocument
# =========================================================


def _load_raw_json(
    raw_document: RawDocument,
) -> dict:
    """
    RawDocument에 기록된 S3 위치에서
    원본 JSON을 읽는다.
    """

    client = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
    )

    response = client.get_object(
        Bucket=raw_document.s3_bucket,
        Key=raw_document.s3_key,
    )

    body = (
        response["Body"]
        .read()
        .decode("utf-8")
    )

    return json.loads(body)


# =========================================================
# Brand Matching
# =========================================================


def _find_brand_by_brand_table(
    *,
    name_ko: str | None,
    name_en: str | None,
) -> Brand | None:
    """
    Brand 테이블 자체에서 exact match.

    1. 한글/대표 이름
    2. 영문 이름

    한 건만 정확하게 발견됐을 때만 반환한다.
    """

    if name_ko:
        qs = Brand.objects.filter(
            status=Brand.Status.ACTIVE,
            name__iexact=name_ko.strip(),
        )

        if qs.count() == 1:
            return qs.first()

    if name_en:
        qs = Brand.objects.filter(
            status=Brand.Status.ACTIVE,
            english_name__iexact=name_en.strip(),
        )

        if qs.count() == 1:
            return qs.first()

    return None


def _find_brand_by_term_alias(
    *,
    source,
    name_ko: str | None,
    name_en: str | None,
) -> Brand | None:
    """
    DictionaryTerm + TermAlias를 이용한 브랜드 검색.

    예:
        나이키
        NIKE
        nike

        ↓

        TermAlias
        ↓
        DictionaryTerm(term_type=BRAND)
        ↓
        Brand
    """

    normalized_values = {
        normalize_text(name_ko),
        normalize_text(name_en),
    }

    normalized_values.discard("")

    if not normalized_values:
        return None

    aliases = (
        TermAlias.objects
        .select_related(
            "term",
            "term__brand",
            "source",
        )
        .filter(
            normalized_alias__in=normalized_values,
            term__term_type=(
                DictionaryTerm.TermType.BRAND
            ),
            term__status=(
                DictionaryTerm.Status.ACTIVE
            ),
            term__brand__isnull=False,
        )
        .filter(
            Q(source=source)
            | Q(source__isnull=True)
        )
        .order_by(
            # 특정 플랫폼 alias를 공통 alias보다 우선
            "-source_id",
            "id",
        )
    )

    brand_ids = list(
        aliases.values_list(
            "term__brand_id",
            flat=True,
        )
        .distinct()
    )

    # 하나의 브랜드로만 명확하게 결정되는 경우
    if len(brand_ids) == 1:
        return (
            Brand.objects
            .filter(
                id=brand_ids[0],
                status=Brand.Status.ACTIVE,
            )
            .first()
        )

    return None


def _find_brand_by_dictionary_term(
    *,
    name_ko: str | None,
    name_en: str | None,
) -> Brand | None:
    """
    Alias가 없어도 DictionaryTerm의
    canonical_name / normalized_name / english_name과
    직접 일치하면 브랜드를 찾는다.
    """

    normalized_values = {
        normalize_text(name_ko),
        normalize_text(name_en),
    }

    normalized_values.discard("")

    if not normalized_values:
        return None

    terms = (
        DictionaryTerm.objects
        .select_related("brand")
        .filter(
            term_type=(
                DictionaryTerm.TermType.BRAND
            ),
            status=(
                DictionaryTerm.Status.ACTIVE
            ),
            brand__isnull=False,
        )
        .filter(
            Q(
                normalized_name__in=(
                    normalized_values
                )
            )
            | Q(
                canonical_name__iexact=(
                    name_ko or ""
                )
            )
            | Q(
                english_name__iexact=(
                    name_en or ""
                )
            )
        )
    )

    brand_ids = list(
        terms.values_list(
            "brand_id",
            flat=True,
        )
        .distinct()
    )

    if len(brand_ids) == 1:
        return (
            Brand.objects
            .filter(
                id=brand_ids[0],
                status=Brand.Status.ACTIVE,
            )
            .first()
        )

    return None


def _find_exact_brand(
    *,
    source,
    name_ko: str | None,
    name_en: str | None,
) -> Brand | None:
    """
    브랜드 검색 최종 순서.

    1. Brand 직접 exact
    2. TermAlias
    3. DictionaryTerm 직접 exact

    애매하면 자동 매핑하지 않는다.
    """

    brand = _find_brand_by_brand_table(
        name_ko=name_ko,
        name_en=name_en,
    )

    if brand:
        return brand

    brand = _find_brand_by_term_alias(
        source=source,
        name_ko=name_ko,
        name_en=name_en,
    )

    if brand:
        return brand

    return _find_brand_by_dictionary_term(
        name_ko=name_ko,
        name_en=name_en,
    )


# =========================================================
# Mapping Candidate
# =========================================================


def _upsert_brand_candidate(
    *,
    source,
    source_brand_id: str,
    name_ko: str | None,
    name_en: str | None,
    detected_count: int,
) -> tuple[MappingCandidate, bool]:
    """
    자동 매핑에 실패한 플랫폼 브랜드를
    관리자 검토 대상 MappingCandidate에 저장한다.
    """

    now = timezone.now()

    candidate, created = (
        MappingCandidate.objects
        .get_or_create(
            source=source,
            mapping_type=(
                MappingCandidate.MappingType.BRAND
            ),
            source_key=source_brand_id,
            defaults={
                "source_name": (
                    name_ko
                    or name_en
                    or source_brand_id
                ),
                "source_detail": {
                    "source_brand_id": (
                        source_brand_id
                    ),
                    "name_ko": name_ko,
                    "name_en": name_en,
                    "normalized_name_ko": (
                        normalize_text(name_ko)
                    ),
                    "normalized_name_en": (
                        normalize_text(name_en)
                    ),
                },
                "detected_count": (
                    detected_count
                ),
                "status": (
                    MappingCandidate.Status.PENDING
                ),
                "first_seen_at": now,
                "last_seen_at": now,
            },
        )
    )

    if not created:
        candidate.source_name = (
            name_ko
            or name_en
            or source_brand_id
        )

        candidate.source_detail = {
            "source_brand_id": (
                source_brand_id
            ),
            "name_ko": name_ko,
            "name_en": name_en,
            "normalized_name_ko": (
                normalize_text(name_ko)
            ),
            "normalized_name_en": (
                normalize_text(name_en)
            ),
        }

        candidate.detected_count += (
            detected_count
        )

        candidate.last_seen_at = now

        # 이전에 REJECTED 등이었다면
        # 자동으로 PENDING으로 되돌리지는 않는다.
        candidate.save(
            update_fields=[
                "source_name",
                "source_detail",
                "detected_count",
                "last_seen_at",
                "updated_at",
            ]
        )

    return candidate, created


# =========================================================
# Main
# =========================================================


def normalize_musinsa_brands_from_crawl_run(
    *,
    crawl_run_id: int,
) -> dict:
    """
    MUSINSA CrawlRun의 RawDocument들을 읽어
    플랫폼 브랜드를 FEEDIT 표준 Brand에 매핑한다.

    처리 우선순위:

        source_brand_id
            ↓
        BrandSource 존재?
            ↓ YES
        기존 Brand 사용

            ↓ NO

        Brand / TermAlias / DictionaryTerm
        exact matching
            ↓
        성공
            ↓
        BrandSource 생성

        실패
            ↓
        MappingCandidate 생성/누적
    """

    crawl_run = (
        CrawlRun.objects
        .select_related("source")
        .get(
            id=crawl_run_id
        )
    )

    if (
        crawl_run.status
        != CrawlRun.Status.SUCCESS
    ):
        raise ValueError(
            "SUCCESS CrawlRun만 정제할 수 있습니다."
        )

    if (
        crawl_run.source.code.upper()
        != "MUSINSA"
    ):
        raise ValueError(
            "현재 브랜드 정제는 MUSINSA만 지원합니다."
        )

    source = crawl_run.source

    raw_documents = (
        RawDocument.objects
        .filter(
            crawl_run=crawl_run,
        )
        .order_by("id")
    )

    if not raw_documents.exists():
        raise ValueError(
            "연결된 RawDocument가 없습니다."
        )

    total_detected = 0
    created_count = 0
    updated_count = 0
    matched_count = 0
    unmatched_count = 0

    normalizer = MusinsaNormalizer()

    # ---------------------------------------------------------
    # 같은 CrawlRun 안에서 동일 브랜드가
    # 여러 RawDocument에 등장할 수 있으므로
    # Run 전체 기준으로 먼저 그룹화한다.
    # ---------------------------------------------------------

    grouped: dict[str, dict] = {}

    for raw_document in raw_documents:

        if raw_document.document_type not in {
            "RANKING",
            "PRODUCT",
        }:
            continue

        raw = _load_raw_json(
            raw_document
        )

        # -----------------------------------------------------
        # Commerce Normalizer
        # -----------------------------------------------------

        if (
            raw_document.document_type
            == "RANKING"
        ):
            normalized = (
                normalizer
                .normalize_ranking(raw)
            )

            products = (
                normalized.get("products")
                or []
            )

        else:
            product = (
                normalizer
                .normalize_product(raw)
            )

            products = (
                [product]
                if product
                else []
            )

        # -----------------------------------------------------
        # 플랫폼 브랜드 그룹화
        # -----------------------------------------------------

        for item in products:

            if not item:
                continue

            brand_data = (
                item.get("brand")
                or {}
            )

            source_brand_id = (
                brand_data.get(
                    "source_brand_code"
                )
                or brand_data.get(
                    "brand_code"
                )
                or brand_data.get(
                    "source_brand_id"
                )
            )

            if not source_brand_id:
                continue

            source_brand_id = str(
                source_brand_id
            ).strip()

            if not source_brand_id:
                continue

            name_ko = (
                brand_data.get("name_ko")
                or brand_data.get("name")
                or None
            )

            name_en = (
                brand_data.get("name_en")
                or brand_data.get(
                    "english_name"
                )
                or None
            )

            if (
                source_brand_id
                not in grouped
            ):
                grouped[
                    source_brand_id
                ] = {
                    "count": 0,
                    "name_ko": name_ko,
                    "name_en": name_en,
                    "brand_data": (
                        brand_data
                    ),
                }

            grouped[
                source_brand_id
            ]["count"] += 1

            # 기존 데이터에 이름이 없고
            # 뒤쪽 상품에서 이름을 발견했다면 보완
            if (
                not grouped[
                    source_brand_id
                ]["name_ko"]
                and name_ko
            ):
                grouped[
                    source_brand_id
                ]["name_ko"] = name_ko

            if (
                not grouped[
                    source_brand_id
                ]["name_en"]
                and name_en
            ):
                grouped[
                    source_brand_id
                ]["name_en"] = name_en

    # ---------------------------------------------------------
    # 그룹별 브랜드 매핑
    # ---------------------------------------------------------

    for (
        source_brand_id,
        data,
    ) in grouped.items():

        total_detected += 1

        detected_count = (
            data["count"]
        )

        name_ko = (
            data.get("name_ko")
            or source_brand_id
        )

        name_en = (
            data.get("name_en")
        )

        # =====================================================
        # 1. BrandSource 기존 매핑 확인
        # =====================================================

        brand_source = (
            BrandSource.objects
            .select_related("brand")
            .filter(
                source=source,
                source_brand_id=(
                    source_brand_id
                ),
            )
            .first()
        )

        if brand_source:

            changed_fields = []

            if (
                brand_source
                .source_brand_name
                != name_ko
            ):
                brand_source.source_brand_name = (
                    name_ko
                )
                changed_fields.append(
                    "source_brand_name"
                )

            brand_source.last_seen_at = (
                timezone.now()
            )

            changed_fields.append(
                "last_seen_at"
            )

            changed_fields.append(
                "updated_at"
            )

            brand_source.save(
                update_fields=changed_fields
            )

            updated_count += 1
            matched_count += 1

            continue

        # =====================================================
        # 2. 기존 FEEDIT Brand 자동 검색
        # =====================================================

        matched_brand = (
            _find_exact_brand(
                source=source,
                name_ko=name_ko,
                name_en=name_en,
            )
        )

        # =====================================================
        # 3. 찾았으면 BrandSource 생성
        # =====================================================

        if matched_brand:

            now = timezone.now()

            BrandSource.objects.create(
                brand=matched_brand,
                source=source,
                source_brand_id=(
                    source_brand_id
                ),
                source_brand_name=(
                    name_ko
                ),
                first_seen_at=now,
                last_seen_at=now,
            )

            # 과거 미매핑 후보가 있었다면
            # 승인 상태로 정리
            candidate = (
                MappingCandidate.objects
                .filter(
                    source=source,
                    mapping_type=(
                        MappingCandidate
                        .MappingType
                        .BRAND
                    ),
                    source_key=(
                        source_brand_id
                    ),
                )
                .first()
            )

            if candidate:
                candidate.status = (
                    MappingCandidate
                    .Status
                    .APPROVED
                )

                candidate.selected_target_type = (
                    "Brand"
                )

                candidate.selected_target_id = (
                    matched_brand.id
                )

                candidate.selected_target_name = (
                    matched_brand.name
                )

                candidate.match_method = (
                    "EXACT"
                )

                candidate.reviewed_at = now

                candidate.save(
                    update_fields=[
                        "status",
                        "selected_target_type",
                        "selected_target_id",
                        "selected_target_name",
                        "match_method",
                        "reviewed_at",
                        "updated_at",
                    ]
                )

            created_count += 1
            matched_count += 1

            continue

        # =====================================================
        # 4. 매칭 실패 → MappingCandidate
        # =====================================================

        _candidate, created = (
            _upsert_brand_candidate(
                source=source,
                source_brand_id=(
                    source_brand_id
                ),
                name_ko=name_ko,
                name_en=name_en,
                detected_count=(
                    detected_count
                ),
            )
        )

        if created:
            created_count += 1
        else:
            updated_count += 1

        unmatched_count += 1

    # ---------------------------------------------------------
    # Result
    # ---------------------------------------------------------

    return {
        "crawl_run_id": (
            crawl_run.id
        ),
        "detected": (
            total_detected
        ),
        "created": (
            created_count
        ),
        "updated": (
            updated_count
        ),
        "matched": (
            matched_count
        ),
        "unmatched": (
            unmatched_count
        ),
    }