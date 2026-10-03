from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from django.db import transaction

from apps.core.models import (
    Brand,
    DictionaryTerm,
    TermAlias,
)

from apps.core.models.dictionary import normalize_dictionary_text

from .tokenizer import reload_tokenizer_dictionary


SPACE_RE = re.compile(r"\s+")


def _clean(value) -> str:
    if not value:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    return SPACE_RE.sub(
        " ",
        value,
    ).strip()


def _normalize_term_name(value: str) -> str:
    """
    DictionaryTerm.save()와 정확히 동일한 규칙으로
    normalized_name을 생성한다.
    """
    value = _clean(value)

    if not value:
        return ""

    return normalize_dictionary_text(value)
    

def _brand_term_field_name() -> str | None:
    """
    Brand -> DictionaryTerm FK/OneToOne 필드를
    프로젝트 모델에서 자동 탐색한다.
    """

    for field in Brand._meta.fields:

        remote = getattr(
            field,
            "remote_field",
            None,
        )

        model = getattr(
            remote,
            "model",
            None,
        )

        if model is DictionaryTerm:
            return field.name

    return None


def _brand_source_rows(brand):
    """
    Brand와 연결된 BrandSource를 반환한다.
    """

    for rel in Brand._meta.related_objects:

        model = getattr(
            rel,
            "related_model",
            None,
        )

        if (
            model is None
            or model.__name__ != "BrandSource"
        ):
            continue

        manager = getattr(
            brand,
            rel.get_accessor_name(),
            None,
        )

        if manager is None:
            continue

        try:
            yield from manager.all()

        except Exception:
            continue


@dataclass
class BrandSyncStats:
    brands: int = 0

    terms_created: int = 0
    terms_reused: int = 0
    terms_linked: int = 0

    aliases_created: int = 0
    aliases_existing: int = 0
    aliases_skipped_collision: int = 0

    skipped_no_name: int = 0

    errors: int = 0

    def to_dict(self):
        return self.__dict__.copy()


def _find_existing_brand_term(
    *,
    canonical: str,
) -> DictionaryTerm | None:
    """
    기존 BRAND DictionaryTerm 탐색.

    UNIQUE constraint 기준인
    (term_type, normalized_name)을 최우선으로 사용한다.

    canonical_name exact/iexact는
    기존 데이터 호환용 fallback이다.
    """

    normalized = _normalize_term_name(
        canonical
    )

    if normalized:

        term = (
            DictionaryTerm.objects
            .filter(
                term_type=DictionaryTerm.TermType.BRAND,
                normalized_name=normalized,
            )
            .order_by("id")
            .first()
        )

        if term is not None:
            return term

    # --------------------------------------------------------
    # fallback 1
    # canonical exact
    # --------------------------------------------------------

    term = (
        DictionaryTerm.objects
        .filter(
            term_type=DictionaryTerm.TermType.BRAND,
            canonical_name=canonical,
        )
        .order_by("id")
        .first()
    )

    if term is not None:
        return term

    # --------------------------------------------------------
    # fallback 2
    # canonical case-insensitive
    # --------------------------------------------------------

    return (
        DictionaryTerm.objects
        .filter(
            term_type=DictionaryTerm.TermType.BRAND,
            canonical_name__iexact=canonical,
        )
        .order_by("id")
        .first()
    )


def _get_or_create_brand_term(
    *,
    canonical: str,
    english: str,
) -> tuple[DictionaryTerm, bool]:
    """
    BRAND DictionaryTerm을 안전하게 가져오거나 생성한다.

    get_or_create(
        normalized_name=canonical.casefold()
    )

    방식을 사용하지 않는다.

    이유:
    DictionaryTerm.save()에서 실제 normalized_name이
    다른 규칙으로 만들어질 수 있기 때문이다.
    """

    existing = _find_existing_brand_term(
        canonical=canonical,
    )

    if existing is not None:
        return existing, False

    try:

        with transaction.atomic():

            term = DictionaryTerm.objects.create(
                term_type=DictionaryTerm.TermType.BRAND,
                canonical_name=canonical,
                english_name=english or None,
                description=(
                    f"FEEDIT 브랜드 엔티티: "
                    f"{canonical}"
                ),
                status=DictionaryTerm.Status.ACTIVE,
            )

        return term, True

    except Exception:

        # ----------------------------------------------------
        # 중요
        #
        # save() 과정에서 normalized_name이 생성되면서
        # concurrent/기존 데이터 UNIQUE 충돌이 발생할 수 있다.
        #
        # transaction rollback 후 실제 DB 값을 다시 조회한다.
        # ----------------------------------------------------

        existing = _find_existing_brand_term(
            canonical=canonical,
        )

        if existing is not None:
            return existing, False

        raise


def _link_brand_term(
    *,
    brand,
    term,
    term_field_name: str | None,
) -> bool:

    if not term_field_name:
        return False

    try:
        current = getattr(
            brand,
            term_field_name,
            None,
        )

    except Exception:
        current = None

    if current is not None:

        if current.pk == term.pk:
            return False

        # 기존 연결은 자동으로 덮어쓰지 않는다.
        return False

    setattr(
        brand,
        term_field_name,
        term,
    )

    brand.save(
        update_fields=[
            term_field_name,
        ]
    )

    return True


def _sync_alias(
    *,
    term,
    alias_value: str,
    stats: BrandSyncStats,
) -> None:

    alias_value = _clean(
        alias_value
    )

    if not alias_value:
        return

    # 한 글자 브랜드 alias는 일반 텍스트에서
    # 오탐 가능성이 너무 높으므로 자동 등록하지 않는다.
    if len(alias_value) <= 1:
        return

    # canonical과 동일하면 alias 불필요
    canonical = _clean(
        getattr(
            term,
            "canonical_name",
            None,
        )
    )

    if (
        canonical
        and alias_value.casefold()
        == canonical.casefold()
    ):
        return

    # --------------------------------------------------------
    # 이미 동일 term에 존재
    # --------------------------------------------------------

    existing_same = (
        TermAlias.objects
        .filter(
            term=term,
            alias__iexact=alias_value,
        )
        .first()
    )

    if existing_same is not None:
        stats.aliases_existing += 1
        return

    # --------------------------------------------------------
    # 다른 term이 동일 alias 사용
    # --------------------------------------------------------

    collision = (
        TermAlias.objects
        .filter(
            alias__iexact=alias_value,
        )
        .exclude(
            term=term,
        )
        .exists()
    )

    if collision:

        stats.aliases_skipped_collision += 1

        return

    # --------------------------------------------------------
    # CREATE
    # --------------------------------------------------------

    try:

        with transaction.atomic():

            TermAlias.objects.create(
                term=term,
                alias=alias_value,
                source=None,
                alias_type=(
                    TermAlias.AliasType.SYNONYM
                ),
            )

        stats.aliases_created += 1

    except Exception:

        # save()에서 alias normalization UNIQUE가
        # 별도로 걸려 있을 수 있으므로 재확인한다.

        same = (
            TermAlias.objects
            .filter(
                term=term,
                alias__iexact=alias_value,
            )
            .exists()
        )

        if same:
            stats.aliases_existing += 1
            return

        collision = (
            TermAlias.objects
            .filter(
                alias__iexact=alias_value,
            )
            .exclude(
                term=term,
            )
            .exists()
        )

        if collision:
            stats.aliases_skipped_collision += 1
            return

        raise


def sync_brand_dictionary(
    *,
    reload_dictionary: bool = True,
    progress_every: int = 100,
) -> BrandSyncStats:
    """
    FEEDIT Brand -> DictionaryTerm(BRAND) 동기화.

    특징
    ----
    1. 기존 BRAND DictionaryTerm 재사용
    2. normalized_name UNIQUE 충돌 안전 처리
    3. Brand -> DictionaryTerm 기존 연결 유지
    4. Brand/BrandSource 자연어 이름 alias 등록
    5. source_brand_id는 등록하지 않음
    6. alias collision 자동 이동 금지
    7. 여러 번 실행해도 같은 결과를 유지하도록 설계
    8. 진행률 출력
    """

    stats = BrandSyncStats()

    term_field_name = (
        _brand_term_field_name()
    )

    qs = (
        Brand.objects
        .all()
        .order_by("id")
    )

    field_names = {
        field.name
        for field in Brand._meta.fields
    }

    if "status" in field_names:

        active = getattr(
            getattr(
                Brand,
                "Status",
                object,
            ),
            "ACTIVE",
            "ACTIVE",
        )

        qs = qs.filter(
            status=active,
        )

    total = qs.count()

    print()
    print(
        "BRAND TOTAL:",
        total,
    )

    print(
        "BRAND TERM FIELD:",
        term_field_name or "NONE",
    )

    print()

    for index, brand in enumerate(
        qs.iterator(
            chunk_size=500,
        ),
        start=1,
    ):

        stats.brands += 1

        name = _clean(
            getattr(
                brand,
                "name",
                None,
            )
        )

        english = _clean(
            getattr(
                brand,
                "english_name",
                None,
            )
        )

        canonical = (
            name
            or english
        )

        if not canonical:

            stats.skipped_no_name += 1

            continue

        try:

            # =================================================
            # EXISTING LINK
            # =================================================

            linked = None

            if term_field_name:

                try:

                    linked = getattr(
                        brand,
                        term_field_name,
                        None,
                    )

                except Exception:
                    linked = None

            # =================================================
            # TERM
            # =================================================

            if (
                linked is not None
                and getattr(
                    linked,
                    "term_type",
                    None,
                )
                == DictionaryTerm.TermType.BRAND
            ):

                term = linked

                stats.terms_reused += 1

            else:

                term, created = (
                    _get_or_create_brand_term(
                        canonical=canonical,
                        english=english,
                    )
                )

                if created:
                    stats.terms_created += 1
                else:
                    stats.terms_reused += 1

                linked_now = _link_brand_term(
                    brand=brand,
                    term=term,
                    term_field_name=term_field_name,
                )

                if linked_now:
                    stats.terms_linked += 1

            # =================================================
            # ALIASES
            # =================================================

            alias_values = {
                name,
                english,
            }

            for source_brand in (
                _brand_source_rows(
                    brand
                )
            ):

                if (
                    getattr(
                        source_brand,
                        "mapping_status",
                        None,
                    )
                    == "EXCLUDED"
                ):
                    continue

                alias_values.add(
                    _clean(
                        getattr(
                            source_brand,
                            "name",
                            None,
                        )
                    )
                )

                alias_values.add(
                    _clean(
                        getattr(
                            source_brand,
                            "english_name",
                            None,
                        )
                    )
                )

            alias_values.discard("")

            for alias_value in sorted(
                alias_values,
                key=str.casefold,
            ):

                _sync_alias(
                    term=term,
                    alias_value=alias_value,
                    stats=stats,
                )

        except Exception as exc:

            stats.errors += 1

            print()
            print(
                f"[ERROR {index}/{total}]"
            )

            print(
                "BRAND ID :",
                getattr(
                    brand,
                    "id",
                    None,
                ),
            )

            print(
                "NAME     :",
                canonical,
            )

            print(
                "ERROR    :",
                type(exc).__name__,
                str(exc),
            )

            # 한 브랜드 오류 때문에
            # 전체 7천여 개 sync를 중단하지 않는다.
            continue

        # =====================================================
        # PROGRESS
        # =====================================================

        if (
            index == 1
            or index % progress_every == 0
            or index == total
        ):

            percent = (
                index
                / total
                * 100
                if total
                else 100
            )

            print(
                f"[{index:,}/{total:,}] "
                f"{percent:6.2f}% | "
                f"CREATED={stats.terms_created:,} | "
                f"REUSED={stats.terms_reused:,} | "
                f"LINKED={stats.terms_linked:,} | "
                f"ALIAS+={stats.aliases_created:,} | "
                f"COLLISION={stats.aliases_skipped_collision:,} | "
                f"ERROR={stats.errors:,}"
            )

    # =========================================================
    # TOKENIZER RELOAD
    # =========================================================

    if reload_dictionary:

        print()
        print(
            "Reloading tokenizer dictionary..."
        )

        reload_tokenizer_dictionary()

        print(
            "Tokenizer dictionary reloaded."
        )

    # =========================================================
    # FINAL
    # =========================================================

    print()
    print("=" * 100)
    print("BRAND DICTIONARY SYNC COMPLETE")
    print("=" * 100)

    for key, value in (
        stats.to_dict().items()
    ):

        print(
            f"{key:<28}:",
            value,
        )

    return stats