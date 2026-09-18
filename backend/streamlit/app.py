from __future__ import annotations

import re
import pandas as pd
import streamlit as st

# =========================================================
# Django bootstrap
# =========================================================
from normalization.django_bootstrap import setup_django

BACKEND_DIR = setup_django()

from django.apps import apps
from django.db import transaction

from normalization.queries import (
    load_unmapped_brand_sources,
    load_feedit_brands,
)

from normalization.brand_matcher import (
    find_brand_candidates,
    search_feedit_brands,
)


# =========================================================
# Django Models
# =========================================================
Brand = apps.get_model("core", "Brand")
BrandSource = apps.get_model("core", "BrandSource")

try:
    Category = apps.get_model("core", "Category")
except LookupError:
    Category = None

Style = None
for model_name in [
    "Style",
    "BrandStyle",
    "DictionaryStyle",
]:
    try:
        Style = apps.get_model("core", model_name)
        break
    except LookupError:
        pass


# =========================================================
# Page
# =========================================================
st.set_page_config(
    page_title="FEEDIT Normalization Lab",
    page_icon="🧪",
    layout="wide",
)

st.title("FEEDIT Normalization Lab")
st.caption("브랜드 정규화 작업실")


# =========================================================
# Generic helpers
# =========================================================
def model_field_names(model):
    if model is None:
        return set()

    return {
        f.name
        for f in model._meta.get_fields()
    }


def safe_model_values(model, preferred_fields):
    if model is None:
        return []

    existing = model_field_names(model)

    fields = [
        field
        for field in preferred_fields
        if field in existing
    ]

    if not fields:
        return []

    return list(
        model.objects
        .all()
        .values(*fields)
    )


def make_brand_code(english_name: str | None) -> str:
    """
    고정 규칙:
    BRAND_<영문명 대문자>
    공백/하이픈/특수문자는 "_"
    """
    if not english_name:
        return ""

    value = str(english_name).strip().upper()
    value = re.sub(r"[^A-Z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("_")

    if not value:
        return ""

    return f"BRAND_{value}"


def get_field_choices(model, field_name):
    """
    Django TextChoices/choices가 있으면 [(value, label), ...] 반환.
    """
    if model is None:
        return []

    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return []

    return list(field.choices or [])


def normalize_nullable(value, default=""):
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    return value


# =========================================================
# Cached reads
# =========================================================
@st.cache_data(ttl=60)
def cached_unmapped(
    platform: str,
    limit: int,
    search: str,
):
    return load_unmapped_brand_sources(
        platform=platform,
        limit=limit,
        search=search or None,
    )


@st.cache_data(ttl=300)
def cached_feedit_brands():
    return load_feedit_brands()


@st.cache_data(ttl=300)
def cached_categories():
    if Category is None:
        return pd.DataFrame()

    rows = safe_model_values(
        Category,
        [
            "id",
            "name",
            "category_code",
            "parent_id",
        ],
    )

    df = pd.DataFrame(rows)

    if not df.empty and "name" in df.columns:
        df = df.sort_values(
            ["name", "id"],
            na_position="last",
        ).reset_index(drop=True)

    return df


@st.cache_data(ttl=300)
def cached_styles():
    if Style is None:
        return pd.DataFrame()

    rows = safe_model_values(
        Style,
        [
            "id",
            "name",
            "style_code",
        ],
    )

    return pd.DataFrame(rows)


# =========================================================
# DB write: 기존 Brand에 즉시 매핑
# =========================================================
def map_brand_source_to_existing(
    brand_source_id: int,
    brand_id: int,
):
    """
    기존 FEEDIT Brand가 존재하는 경우 즉시 DB 매핑.
    Pending 사용하지 않음.
    """
    with transaction.atomic():
        brand_source = (
            BrandSource.objects
            .select_for_update()
            .get(id=brand_source_id)
        )

        if brand_source.brand_id is not None:
            raise ValueError(
                f"BrandSource #{brand_source_id}는 이미 "
                f"Brand #{brand_source.brand_id}에 매핑되어 있습니다."
            )

        brand = Brand.objects.get(id=brand_id)

        brand_source.brand = brand

        update_fields = ["brand"]
        bs_fields = model_field_names(BrandSource)

        if "mapping_status" in bs_fields:
            brand_source.mapping_status = "MANUAL_MAPPED"
            update_fields.append("mapping_status")

        if "mapping_method" in bs_fields:
            brand_source.mapping_method = "MANUAL"
            update_fields.append("mapping_method")

        brand_source.save(
            update_fields=update_fields
        )

        return brand


# =========================================================
# DB write: 신규 Brand 승격
# =========================================================
def promote_brand_to_db(record: dict):
    """
    승격 Pending 1건 실제 반영.
    Brand 생성 + BrandSource 매핑.
    """
    brand_source_id = int(
        record["brand_source_id"]
    )

    brand_source = (
        BrandSource.objects
        .select_for_update()
        .get(id=brand_source_id)
    )

    if brand_source.brand_id is not None:
        raise ValueError(
            f"BrandSource #{brand_source_id}는 이미 "
            f"Brand #{brand_source.brand_id}에 매핑되어 있습니다."
        )

    brand_code = str(
        record.get("brand_code") or ""
    ).strip()

    name = str(
        record.get("name") or ""
    ).strip()

    english_name = str(
        record.get("english_name") or ""
    ).strip()

    if not brand_code:
        raise ValueError(
            f"BrandSource #{brand_source_id}: brand_code가 없습니다."
        )

    if not name:
        raise ValueError(
            f"BrandSource #{brand_source_id}: 브랜드명이 없습니다."
        )

    if Brand.objects.filter(
        brand_code=brand_code
    ).exists():
        raise ValueError(
            f"이미 존재하는 brand_code입니다: {brand_code}"
        )

    brand_fields = model_field_names(Brand)

    create_kwargs = {
        "brand_code": brand_code,
        "name": name,
    }

    optional_values = {
        "english_name": english_name,
        "country_code": record.get("country_code"),
        "description": record.get("description"),
        "image_url": record.get("image_url"),
        "website_url": record.get("website_url"),
        "status": record.get("status"),
        "target_gender": record.get("target_gender"),
        "target_age": record.get("target_age"),
        "is_verified": record.get("is_verified"),
    }

    for field_name, value in optional_values.items():
        if field_name not in brand_fields:
            continue

        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        create_kwargs[field_name] = value

    category_id = record.get(
        "category_id"
    )

    if (
        category_id
        and "category" in brand_fields
    ):
        create_kwargs["category_id"] = int(
            category_id
        )

    brand = Brand.objects.create(
        **create_kwargs
    )

    style_ids = record.get(
        "style_ids"
    ) or []

    if (
        style_ids
        and hasattr(brand, "styles")
    ):
        brand.styles.set(style_ids)

    brand_source.brand = brand

    update_fields = ["brand"]
    bs_fields = model_field_names(BrandSource)

    if "mapping_status" in bs_fields:
        brand_source.mapping_status = "MANUAL_MAPPED"
        update_fields.append("mapping_status")

    if "mapping_method" in bs_fields:
        brand_source.mapping_method = "MANUAL"
        update_fields.append("mapping_method")

    brand_source.save(
        update_fields=update_fields
    )

    return brand


def promote_all_pending_to_db(
    records: list[dict],
):
    """
    승격 Pending 전체 일괄 반영.
    하나라도 실패하면 전체 rollback.
    """
    if not records:
        return []

    created_brands = []

    with transaction.atomic():
        for record in records:
            brand = promote_brand_to_db(record)
            created_brands.append(brand)

    return created_brands



def get_wholesale_category_id():
    """
    Brand Category 중 '보세'를 찾는다.
    1순위 exact '보세'
    2순위 name에 '보세' 포함
    """
    if Category is None:
        raise ValueError("Category 모델을 찾을 수 없습니다.")

    fields = model_field_names(Category)

    if "name" not in fields:
        raise ValueError("Category 모델에 name 필드가 없습니다.")

    exact = (
        Category.objects
        .filter(name__iexact="보세")
        .order_by("id")
        .first()
    )

    if exact is not None:
        return exact.id

    contains = (
        Category.objects
        .filter(name__icontains="보세")
        .order_by("id")
        .first()
    )

    if contains is not None:
        return contains.id

    raise ValueError("'보세' 카테고리를 DB에서 찾지 못했습니다.")


def fast_promote_brand_source(
    brand_source_id: int,
    wholesale_category_id: int,
):
    """
    BrandSource 1건을 즉시 Brand로 승격.

    고정 규칙:
    - name: BrandSource.name
    - english_name: BrandSource.english_name
    - brand_code: BRAND_<ENGLISH_NAME>
    - category: 보세
    - country_code: BrandSource 값이 있으면 사용, 없으면 KR
    - image_url: BrandSource 값 승계
    - BrandSource mapping_status = MANUAL_MAPPED
    - BrandSource mapping_method = MANUAL

    1건 단위 transaction.
    """
    with transaction.atomic():

        brand_source = (
            BrandSource.objects
            .select_for_update()
            .select_related("source")
            .get(id=brand_source_id)
        )

        if brand_source.brand_id is not None:
            raise ValueError(
                f"이미 Brand #{brand_source.brand_id}에 매핑됨"
            )

        name = str(
            getattr(brand_source, "name", "") or ""
        ).strip()

        english_name = str(
            getattr(brand_source, "english_name", "") or ""
        ).strip()

        if not name:
            raise ValueError("name 없음")

        if not english_name:
            raise ValueError("english_name 없음")

        brand_code = make_brand_code(
            english_name
        )

        if not brand_code:
            raise ValueError(
                "english_name으로 brand_code 생성 실패"
            )

        if Brand.objects.filter(
            brand_code=brand_code
        ).exists():
            raise ValueError(
                f"brand_code 중복: {brand_code}"
            )

        brand_fields = model_field_names(Brand)

        kwargs = {
            "brand_code": brand_code,
            "name": name,
        }

        if "english_name" in brand_fields:
            kwargs["english_name"] = english_name

        if "category" in brand_fields:
            kwargs["category_id"] = int(
                wholesale_category_id
            )

        if "country_code" in brand_fields:
            source_country = getattr(
                brand_source,
                "country_code",
                None,
            )

            kwargs["country_code"] = (
                str(source_country).strip()
                if source_country
                else "KR"
            )

        if "image_url" in brand_fields:
            source_image = getattr(
                brand_source,
                "image_url",
                None,
            )

            if source_image:
                kwargs["image_url"] = source_image

        brand = Brand.objects.create(
            **kwargs
        )

        brand_source.brand = brand

        update_fields = ["brand"]

        bs_fields = model_field_names(
            BrandSource
        )

        if "mapping_status" in bs_fields:
            brand_source.mapping_status = (
                "MANUAL_MAPPED"
            )
            update_fields.append(
                "mapping_status"
            )

        if "mapping_method" in bs_fields:
            brand_source.mapping_method = (
                "MANUAL"
            )
            update_fields.append(
                "mapping_method"
            )

        brand_source.save(
            update_fields=update_fields
        )

        return brand


def fast_promote_selected(
    brand_source_ids: list[int],
):
    """
    선택된 BrandSource를 순서대로 즉시 승격.

    한 건 실패해도 나머지는 계속 처리.
    """
    wholesale_category_id = (
        get_wholesale_category_id()
    )

    success = []
    failed = []

    for brand_source_id in brand_source_ids:
        try:
            brand = fast_promote_brand_source(
                brand_source_id=brand_source_id,
                wholesale_category_id=(
                    wholesale_category_id
                ),
            )

        except Exception as exc:
            failed.append(
                {
                    "brand_source_id":
                        int(brand_source_id),
                    "error":
                        str(exc),
                }
            )

        else:
            success.append(
                {
                    "brand_source_id":
                        int(brand_source_id),
                    "brand_id":
                        int(brand.id),
                    "brand_code":
                        brand.brand_code,
                    "name":
                        brand.name,
                    "english_name":
                        getattr(
                            brand,
                            "english_name",
                            None,
                        ),
                }
            )

    return (
        pd.DataFrame(success),
        pd.DataFrame(failed),
    )


# =========================================================
# Session State
# =========================================================
if "pending_brand_promotions" not in st.session_state:
    st.session_state.pending_brand_promotions = []

if "skipped_brand_source_ids" not in st.session_state:
    st.session_state.skipped_brand_source_ids = set()

if "promotion_brand_source_id" not in st.session_state:
    st.session_state.promotion_brand_source_id = None

if "fast_promote_success" not in st.session_state:
    st.session_state.fast_promote_success = []

if "fast_promote_failed" not in st.session_state:
    st.session_state.fast_promote_failed = []


def pending_promotion_ids() -> set[int]:
    return {
        int(row["brand_source_id"])
        for row
        in st.session_state.pending_brand_promotions
    }


def add_or_replace_pending_promotion(
    record: dict,
):
    brand_source_id = int(
        record["brand_source_id"]
    )

    st.session_state.pending_brand_promotions = [
        row
        for row
        in st.session_state.pending_brand_promotions
        if int(row["brand_source_id"])
        != brand_source_id
    ]

    st.session_state.pending_brand_promotions.append(
        record
    )


# =========================================================
# Sidebar
# =========================================================
with st.sidebar:
    st.header("필터")

    platform = st.selectbox(
        "플랫폼",
        [
            "zigzag",
            "musinsa",
            "musinsa_used",
            "ably",
            "kream",
        ],
        index=0,
    )

    search = st.text_input(
        "미매핑 브랜드 검색",
        placeholder="name / english_name",
    )

    limit = st.number_input(
        "최대 조회 개수",
        min_value=10,
        max_value=5000,
        value=500,
        step=50,
    )

    min_score = st.slider(
        "자동 후보 최소 유사도",
        min_value=0.0,
        max_value=1.0,
        value=0.30,
        step=0.05,
    )

    st.caption(
        "자동 후보는 3개 고정"
    )

    if st.button(
        "데이터 새로고침",
        use_container_width=True,
    ):
        cached_unmapped.clear()
        cached_feedit_brands.clear()
        cached_categories.clear()
        cached_styles.clear()

        st.session_state.promotion_brand_source_id = None

        st.rerun()


# =========================================================
# Load
# =========================================================
unmapped_df = cached_unmapped(
    platform,
    int(limit),
    search,
)

feedit_brands_df = cached_feedit_brands()
categories_df = cached_categories()
styles_df = cached_styles()

reviewed = pending_promotion_ids()
skipped = (
    st.session_state.skipped_brand_source_ids
)

if not unmapped_df.empty:
    working_df = unmapped_df[
        ~unmapped_df["id"].isin(
            reviewed | skipped
        )
    ].reset_index(drop=True)
else:
    working_df = unmapped_df


# =========================================================
# Summary
# =========================================================
c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "UNMAPPED",
    len(unmapped_df),
)

c2.metric(
    "승격 Pending",
    len(
        st.session_state.pending_brand_promotions
    ),
)

c3.metric(
    "스킵",
    len(
        st.session_state.skipped_brand_source_ids
    ),
)

c4.metric(
    "남은 작업",
    len(working_df),
)

st.divider()


# =========================================================
# Tabs
# =========================================================
tab_review, tab_fast, tab_pending, tab_all = st.tabs(
    [
        "브랜드 정규화",
        "⚡ 빠른 승격 50",
        "승격 Pending",
        "미매핑 전체",
    ]
)


# =========================================================
# TAB 1: 브랜드 정규화
# =========================================================
with tab_review:

    if working_df.empty:
        st.success(
            "현재 필터 기준으로 검토할 미매핑 브랜드가 없습니다."
        )

    else:
        current = working_df.iloc[0]

        brand_source_id = int(
            current["id"]
        )

        source_name = normalize_nullable(
            current.get("name"),
            "",
        )

        source_en = normalize_nullable(
            current.get("english_name"),
            "",
        )

        st.subheader(
            source_name or "-"
        )

        meta1, meta2, meta3, meta4 = (
            st.columns(4)
        )

        meta1.write(
            f"**BrandSource ID**  \n"
            f"{brand_source_id}"
        )

        meta2.write(
            f"**플랫폼**  \n"
            f"{current.get('platform')}"
        )

        meta3.write(
            f"**source_brand_id**  \n"
            f"{current.get('source_brand_id')}"
        )

        meta4.write(
            f"**english_name**  \n"
            f"{source_en or '-'}"
        )

        image_url = normalize_nullable(
            current.get("image_url"),
            "",
        )

        if (
            isinstance(image_url, str)
            and image_url.strip()
        ):
            st.image(
                image_url,
                width=150,
            )

        # -------------------------------------------------
        # 자동 후보
        # -------------------------------------------------
        st.markdown(
            "### 기존 FEEDIT Brand 자동 후보"
        )

        candidates = find_brand_candidates(
            source_name=source_name,
            source_english_name=source_en,
            feedit_brands=feedit_brands_df,
            top_n=3,
            min_score=min_score,
        )

        auto_selected_idx = None

        if candidates.empty:
            st.info("자동 후보 없음")

        else:
            display_cols = [
                col
                for col in [
                    "brand_id",
                    "brand_code",
                    "feedit_name",
                    "feedit_english_name",
                ]
                if col in candidates.columns
            ]

            st.dataframe(
                candidates[display_cols],
                use_container_width=True,
                hide_index=True,
            )

            auto_options = list(
                candidates.index
            )

            def auto_label(idx):
                row = candidates.loc[idx]

                return (
                    f"{row['feedit_name']} / "
                    f"{row['feedit_english_name'] or '-'}"
                )

            auto_selected_idx = st.radio(
                "자동 후보",
                options=auto_options,
                format_func=auto_label,
                index=0,
                key=(
                    f"auto_candidate_"
                    f"{brand_source_id}"
                ),
                label_visibility="collapsed",
            )

        # -------------------------------------------------
        # 직접 검색
        # -------------------------------------------------
        st.markdown(
            "### FEEDIT Brand 직접 검색"
        )

        manual_keyword = st.text_input(
            "브랜드명 / 영문명 / Brand Code",
            placeholder=(
                "예: 겐조, KENZO, BRAND_KENZO"
            ),
            key=(
                f"manual_keyword_"
                f"{brand_source_id}"
            ),
        )

        manual_results = (
            search_feedit_brands(
                feedit_brands=feedit_brands_df,
                keyword=manual_keyword,
                limit=30,
            )
        )

        manual_selected_idx = None

        if manual_keyword.strip():

            if manual_results.empty:
                st.warning(
                    "검색 결과 없음"
                )

            else:
                manual_display_cols = [
                    col
                    for col in [
                        "id",
                        "brand_code",
                        "name",
                        "english_name",
                    ]
                    if col
                    in manual_results.columns
                ]

                st.dataframe(
                    manual_results[
                        manual_display_cols
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

                manual_options = list(
                    manual_results.index
                )

                def manual_label(idx):
                    row = manual_results.loc[
                        idx
                    ]

                    name = normalize_nullable(
                        row.get("name"),
                        "-",
                    )

                    english_name = (
                        normalize_nullable(
                            row.get(
                                "english_name"
                            ),
                            "-",
                        )
                    )

                    return (
                        f"{name} / "
                        f"{english_name}"
                    )

                manual_selected_idx = (
                    st.radio(
                        "직접 검색 결과",
                        options=manual_options,
                        format_func=manual_label,
                        key=(
                            f"manual_result_"
                            f"{brand_source_id}"
                        ),
                        label_visibility=(
                            "collapsed"
                        ),
                    )
                )

        # -------------------------------------------------
        # 매핑 대상 선택
        # -------------------------------------------------
        st.markdown("### 작업")

        mapping_mode = st.radio(
            "매핑 방식",
            [
                "자동 후보",
                "직접 검색",
            ],
            horizontal=True,
            key=(
                f"mapping_mode_"
                f"{brand_source_id}"
            ),
        )

        b1, b2, b3 = st.columns(3)

        # -------------------------------------------------
        # 기존 Brand 즉시 매핑
        # -------------------------------------------------
        with b1:
            if st.button(
                "매핑",
                type="primary",
                use_container_width=True,
            ):
                selected_brand_id = None

                if mapping_mode == "자동 후보":
                    if auto_selected_idx is None:
                        st.error(
                            "자동 후보를 선택하세요."
                        )
                    else:
                        selected_brand_id = int(
                            candidates.loc[
                                auto_selected_idx,
                                "brand_id",
                            ]
                        )

                else:
                    if manual_selected_idx is None:
                        st.error(
                            "직접 검색 결과를 "
                            "선택하세요."
                        )
                    else:
                        selected_brand_id = int(
                            manual_results.loc[
                                manual_selected_idx,
                                "id",
                            ]
                        )

                if selected_brand_id is not None:
                    try:
                        brand = (
                            map_brand_source_to_existing(
                                brand_source_id=(
                                    brand_source_id
                                ),
                                brand_id=(
                                    selected_brand_id
                                ),
                            )
                        )

                    except Exception as exc:
                        st.exception(exc)

                    else:
                        cached_unmapped.clear()
                        cached_feedit_brands.clear()

                        st.success(
                            f"매핑 완료 → "
                            f"{brand.name} "
                            f"({brand.brand_code})"
                        )

                        st.rerun()

        # -------------------------------------------------
        # 신규 Brand 승격 Pending
        # -------------------------------------------------
        with b2:
            if st.button(
                "승격",
                use_container_width=True,
            ):
                st.session_state.promotion_brand_source_id = (
                    brand_source_id
                )

                st.rerun()

        # -------------------------------------------------
        # Skip
        # -------------------------------------------------
        with b3:
            if st.button(
                "스킵",
                use_container_width=True,
            ):
                st.session_state.skipped_brand_source_ids.add(
                    brand_source_id
                )

                st.rerun()

        # =================================================
        # 신규 Brand 승격 입력 Form
        # =================================================
        if (
            st.session_state.promotion_brand_source_id
            == brand_source_id
        ):
            st.divider()
            st.subheader(
                "신규 FEEDIT Brand 승격"
            )

            default_name = str(
                source_name or ""
            )

            default_en = str(
                source_en or ""
            )

            default_country = (
                normalize_nullable(
                    current.get(
                        "country_code"
                    ),
                    "KR",
                )
            )

            default_image = (
                normalize_nullable(
                    current.get(
                        "image_url"
                    ),
                    "",
                )
            )

            brand_fields = model_field_names(
                Brand
            )

            # ---------------------------------------------
            # Category
            # ---------------------------------------------
            category_options = [None]
            category_labels = {
                None: "선택 안 함"
            }

            if not categories_df.empty:
                for row in (
                    categories_df.itertuples(
                        index=False
                    )
                ):
                    cid = int(row.id)

                    category_options.append(
                        cid
                    )

                    category_labels[cid] = (
                        getattr(
                            row,
                            "name",
                            None,
                        )
                        or str(cid)
                    )

            # ★ 플랫폼 상관 없이 무조건 '보세'를 기본값으로
            default_category_id = None

            if (
                not categories_df.empty
                and "name"
                in categories_df.columns
            ):
                category_name_series = (
                    categories_df["name"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                )

                # 1순위: 이름이 정확히 "보세"
                bose_rows = categories_df[
                    category_name_series.eq(
                        "보세"
                    )
                ]

                # 2순위: 혹시 "국내 보세" 등으로 되어 있으면 포함 검색
                if bose_rows.empty:
                    bose_rows = categories_df[
                        category_name_series.str.contains(
                            "보세",
                            regex=False,
                        )
                    ]

                if not bose_rows.empty:
                    default_category_id = int(
                        bose_rows.iloc[0]["id"]
                    )

            default_category_index = 0

            if (
                default_category_id
                in category_options
            ):
                default_category_index = (
                    category_options.index(
                        default_category_id
                    )
                )

            # ---------------------------------------------
            # Style
            # ---------------------------------------------
            style_options = []
            style_labels = {}

            if not styles_df.empty:
                for row in (
                    styles_df.itertuples(
                        index=False
                    )
                ):
                    sid = int(row.id)

                    style_options.append(sid)

                    style_labels[sid] = (
                        getattr(
                            row,
                            "name",
                            None,
                        )
                        or str(sid)
                    )

            with st.form(
                key=(
                    f"promote_form_"
                    f"{brand_source_id}"
                ),
                clear_on_submit=False,
            ):
                col1, col2 = st.columns(2)

                with col1:
                    new_name = st.text_input(
                        "브랜드명 *",
                        value=default_name,
                    )

                    new_english_name = (
                        st.text_input(
                            "영문명 *",
                            value=default_en,
                        )
                    )

                    displayed_brand_code = (
                        make_brand_code(
                            new_english_name
                        )
                    )

                    st.text_input(
                        "Brand Code",
                        value=(
                            displayed_brand_code
                        ),
                        disabled=True,
                    )

                    new_country_code = (
                        st.text_input(
                            "국가 코드",
                            value=str(
                                default_country
                            ),
                        )
                    )

                    new_image_url = (
                        st.text_input(
                            "이미지 URL",
                            value=str(
                                default_image
                            ),
                        )
                    )

                    new_website_url = ""

                    if (
                        "website_url"
                        in brand_fields
                    ):
                        new_website_url = (
                            st.text_input(
                                "웹사이트 URL",
                                value="",
                            )
                        )

                with col2:
                    # ★ 항상 보이고, 기본값은 "보세"
                    selected_category_id = (
                        st.selectbox(
                            "카테고리",
                            options=(
                                category_options
                            ),
                            index=(
                                default_category_index
                            ),
                            format_func=lambda x:
                                category_labels.get(
                                    x,
                                    str(x),
                                ),
                        )
                    )

                    # status
                    new_status = ""

                    if "status" in brand_fields:
                        status_choices = (
                            get_field_choices(
                                Brand,
                                "status",
                            )
                        )

                        if status_choices:
                            status_values = [
                                value
                                for value, _
                                in status_choices
                            ]

                            status_labels = {
                                value: label
                                for value, label
                                in status_choices
                            }

                            new_status = (
                                st.selectbox(
                                    "상태",
                                    options=(
                                        [""]
                                        + status_values
                                    ),
                                    format_func=lambda x:
                                        "선택 안 함"
                                        if x == ""
                                        else (
                                            status_labels.get(
                                                x,
                                                x,
                                            )
                                        ),
                                )
                            )
                        else:
                            new_status = (
                                st.text_input(
                                    "상태",
                                    value="",
                                )
                            )

                    # target_gender
                    new_target_gender = ""

                    if (
                        "target_gender"
                        in brand_fields
                    ):
                        gender_choices = (
                            get_field_choices(
                                Brand,
                                "target_gender",
                            )
                        )

                        if gender_choices:
                            gender_values = [
                                value
                                for value, _
                                in gender_choices
                            ]

                            gender_labels = {
                                value: label
                                for value, label
                                in gender_choices
                            }

                            new_target_gender = (
                                st.selectbox(
                                    "타깃 성별",
                                    options=(
                                        [""]
                                        + gender_values
                                    ),
                                    format_func=lambda x:
                                        "선택 안 함"
                                        if x == ""
                                        else (
                                            gender_labels.get(
                                                x,
                                                x,
                                            )
                                        ),
                                )
                            )
                        else:
                            new_target_gender = (
                                st.text_input(
                                    "타깃 성별",
                                    value="",
                                )
                            )

                    # target_age
                    new_target_age = ""

                    if "target_age" in brand_fields:
                        age_choices = (
                            get_field_choices(
                                Brand,
                                "target_age",
                            )
                        )

                        if age_choices:
                            age_values = [
                                value
                                for value, _
                                in age_choices
                            ]

                            age_labels = {
                                value: label
                                for value, label
                                in age_choices
                            }

                            new_target_age = (
                                st.selectbox(
                                    "타깃 연령",
                                    options=(
                                        [""]
                                        + age_values
                                    ),
                                    format_func=lambda x:
                                        "선택 안 함"
                                        if x == ""
                                        else (
                                            age_labels.get(
                                                x,
                                                x,
                                            )
                                        ),
                                )
                            )
                        else:
                            new_target_age = (
                                st.text_input(
                                    "타깃 연령",
                                    value="",
                                )
                            )

                    selected_style_ids = []

                    if (
                        "styles"
                        in brand_fields
                        and style_options
                    ):
                        selected_style_ids = (
                            st.multiselect(
                                "스타일",
                                options=(
                                    style_options
                                ),
                                format_func=lambda x:
                                    style_labels.get(
                                        x,
                                        str(x),
                                    ),
                            )
                        )

                    new_is_verified = False

                    if (
                        "is_verified"
                        in brand_fields
                    ):
                        new_is_verified = (
                            st.checkbox(
                                "검증 완료",
                                value=False,
                            )
                        )

                new_description = ""

                if (
                    "description"
                    in brand_fields
                ):
                    new_description = (
                        st.text_area(
                            "상세 설명",
                            value="",
                            height=120,
                        )
                    )

                submit_col, cancel_col = (
                    st.columns(2)
                )

                with submit_col:
                    submitted = (
                        st.form_submit_button(
                            "승격 Pending 저장",
                            type="primary",
                            use_container_width=True,
                        )
                    )

                with cancel_col:
                    cancelled = (
                        st.form_submit_button(
                            "취소",
                            use_container_width=True,
                        )
                    )

                if cancelled:
                    st.session_state.promotion_brand_source_id = None
                    st.rerun()

                if submitted:
                    final_brand_code = (
                        make_brand_code(
                            new_english_name
                        )
                    )

                    if not new_name.strip():
                        st.error(
                            "브랜드명은 필수입니다."
                        )

                    elif not (
                        new_english_name.strip()
                    ):
                        st.error(
                            "영문명은 필수입니다."
                        )

                    elif not final_brand_code:
                        st.error(
                            "Brand Code를 "
                            "생성할 수 없습니다."
                        )

                    else:
                        add_or_replace_pending_promotion(
                            {
                                "brand_source_id":
                                    brand_source_id,

                                "platform":
                                    current.get(
                                        "platform"
                                    ),

                                "source_brand_id":
                                    current.get(
                                        "source_brand_id"
                                    ),

                                "decision":
                                    "PROMOTE",

                                "brand_code":
                                    final_brand_code,

                                "name":
                                    new_name.strip(),

                                "english_name":
                                    new_english_name.strip(),

                                "category_id":
                                    selected_category_id,

                                "country_code":
                                    new_country_code.strip(),

                                "description":
                                    new_description.strip(),

                                "image_url":
                                    new_image_url.strip(),

                                "website_url":
                                    new_website_url.strip(),

                                "status":
                                    str(
                                        new_status
                                    ).strip(),

                                "target_gender":
                                    str(
                                        new_target_gender
                                    ).strip(),

                                "target_age":
                                    str(
                                        new_target_age
                                    ).strip(),

                                "style_ids":
                                    selected_style_ids,

                                "is_verified":
                                    bool(
                                        new_is_verified
                                    ),
                            }
                        )

                        st.session_state.promotion_brand_source_id = None

                        st.rerun()



# =========================================================
# TAB 2: 빠른 승격 50
# =========================================================
with tab_fast:

    st.subheader("⚡ 미매핑 브랜드 빠른 승격")

    st.caption(
        "현재 필터의 미매핑 BrandSource 중 최대 50개를 보여줍니다. "
        "체크한 행은 즉시 Brand로 생성됩니다."
    )

    st.info(
        "고정 규칙: category=보세 · "
        "brand_code=BRAND_<ENGLISH_NAME> · "
        "BrandSource 즉시 매핑"
    )

    fast_df = (
        unmapped_df
        .head(50)
        .copy()
        if not unmapped_df.empty
        else pd.DataFrame()
    )

    if fast_df.empty:
        st.success("처리할 미매핑 브랜드가 없습니다.")

    else:
        # 보기용 / 선택용 테이블
        editor_df = pd.DataFrame(
            {
                "승격": False,
                "brand_source_id":
                    fast_df["id"].astype(int),
                "name":
                    fast_df["name"]
                    if "name" in fast_df.columns
                    else "",
                "english_name":
                    fast_df["english_name"]
                    if "english_name"
                    in fast_df.columns
                    else "",
                "source_brand_id":
                    fast_df["source_brand_id"]
                    if "source_brand_id"
                    in fast_df.columns
                    else None,
                "platform":
                    fast_df["platform"]
                    if "platform"
                    in fast_df.columns
                    else platform,
            }
        )

        # 예상 brand_code 확인
        editor_df["brand_code"] = (
            editor_df["english_name"]
            .fillna("")
            .astype(str)
            .apply(make_brand_code)
        )

        edited_df = st.data_editor(
            editor_df,
            use_container_width=True,
            hide_index=True,
            height=min(
                900,
                80 + len(editor_df) * 36,
            ),
            disabled=[
                "brand_source_id",
                "name",
                "english_name",
                "source_brand_id",
                "platform",
                "brand_code",
            ],
            column_config={
                "승격":
                    st.column_config.CheckboxColumn(
                        "승격",
                        help=(
                            "체크한 브랜드를 바로 "
                            "FEEDIT Brand로 승격"
                        ),
                        default=False,
                    ),
                "brand_source_id":
                    st.column_config.NumberColumn(
                        "BrandSource ID",
                    ),
                "brand_code":
                    st.column_config.TextColumn(
                        "생성 Brand Code",
                    ),
            },
            key=(
                f"fast_promote_editor_"
                f"{platform}_{search}"
            ),
        )

        selected_df = edited_df[
            edited_df["승격"] == True
        ]

        c1, c2 = st.columns(2)

        c1.metric(
            "현재 50개",
            len(editor_df),
        )

        c2.metric(
            "선택",
            len(selected_df),
        )

        if st.button(
            f"🚀 선택 {len(selected_df)}건 바로 승격",
            type="primary",
            use_container_width=True,
            disabled=selected_df.empty,
        ):
            selected_ids = (
                selected_df[
                    "brand_source_id"
                ]
                .astype(int)
                .tolist()
            )

            success_df, failed_df = (
                fast_promote_selected(
                    selected_ids
                )
            )

            st.session_state.fast_promote_success = (
                success_df.to_dict(
                    orient="records"
                )
                if not success_df.empty
                else []
            )

            st.session_state.fast_promote_failed = (
                failed_df.to_dict(
                    orient="records"
                )
                if not failed_df.empty
                else []
            )

            cached_unmapped.clear()
            cached_feedit_brands.clear()
            cached_categories.clear()

            st.rerun()

        # ---------------------------------------------
        # 직전 처리 결과
        # ---------------------------------------------
        success_result = pd.DataFrame(
            st.session_state.fast_promote_success
        )

        failed_result = pd.DataFrame(
            st.session_state.fast_promote_failed
        )

        if not success_result.empty:
            st.success(
                f"직전 승격 성공 "
                f"{len(success_result)}건"
            )

            st.dataframe(
                success_result,
                use_container_width=True,
                hide_index=True,
            )

        if not failed_result.empty:
            st.error(
                f"직전 승격 실패 "
                f"{len(failed_result)}건"
            )

            st.dataframe(
                failed_result,
                use_container_width=True,
                hide_index=True,
            )


# =========================================================
# TAB 3: 승격 Pending
# =========================================================
with tab_pending:

    promotion_df = pd.DataFrame(
        st.session_state.pending_brand_promotions
    )

    if promotion_df.empty:
        st.info("승격 Pending 없음")

    else:
        st.subheader(
            f"승격 Pending "
            f"{len(promotion_df)}건"
        )

        preferred_cols = [
            "brand_source_id",
            "platform",
            "source_brand_id",
            "brand_code",
            "name",
            "english_name",
            "category_id",
            "country_code",
            "status",
            "target_gender",
            "target_age",
            "is_verified",
        ]

        display_cols = [
            col
            for col in preferred_cols
            if col in promotion_df.columns
        ]

        extra_cols = [
            col
            for col in promotion_df.columns
            if col not in display_cols
        ]

        st.dataframe(
            promotion_df[
                display_cols + extra_cols
            ],
            use_container_width=True,
            hide_index=True,
            height=min(
                700,
                80 + len(promotion_df) * 36,
            ),
        )

        csv_bytes = (
            promotion_df
            .to_csv(index=False)
            .encode("utf-8-sig")
        )

        st.download_button(
            "승격 Pending CSV",
            data=csv_bytes,
            file_name=(
                f"brand_promotion_pending_"
                f"{platform}.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

        st.divider()

        st.warning(
            f"위 {len(promotion_df)}건을 "
            "한 번에 실제 Brand로 생성하고 "
            "BrandSource를 매핑합니다. "
            "하나라도 실패하면 전체 롤백됩니다."
        )

        if st.button(
            (
                f"🚀 승격 Pending "
                f"{len(promotion_df)}건 전체 실제 반영"
            ),
            type="primary",
            use_container_width=True,
        ):
            records = list(
                st.session_state.pending_brand_promotions
            )

            try:
                created_brands = (
                    promote_all_pending_to_db(
                        records
                    )
                )

            except Exception as exc:
                st.error(
                    "전체 승격 실패 — "
                    "DB 변경은 전부 롤백되었습니다."
                )
                st.exception(exc)

            else:
                created_count = len(
                    created_brands
                )

                st.session_state.pending_brand_promotions = []

                cached_unmapped.clear()
                cached_feedit_brands.clear()
                cached_categories.clear()
                cached_styles.clear()

                st.success(
                    f"승격 완료: "
                    f"{created_count}건"
                )

                st.rerun()

        st.divider()

        with st.expander(
            "Pending 항목 개별 제거"
        ):
            remove_id = st.selectbox(
                "제거할 BrandSource ID",
                options=(
                    promotion_df[
                        "brand_source_id"
                    ]
                    .astype(int)
                    .tolist()
                ),
                key="remove_promotion",
            )

            if st.button(
                "선택 승격 Pending 제거",
                use_container_width=True,
            ):
                st.session_state.pending_brand_promotions = [
                    row
                    for row
                    in st.session_state.pending_brand_promotions
                    if int(
                        row["brand_source_id"]
                    )
                    != int(remove_id)
                ]

                st.rerun()


# =========================================================
# TAB 4: 미매핑 전체
# =========================================================
with tab_all:

    st.subheader(
        f"{platform} · UNMAPPED BrandSource"
    )

    if unmapped_df.empty:
        st.info("데이터 없음")

    else:
        preferred = [
            "id",
            "platform",
            "source_brand_id",
            "name",
            "english_name",
            "mapping_status",
            "image_url",
        ]

        cols = [
            col
            for col in preferred
            if col in unmapped_df.columns
        ]

        st.dataframe(
            unmapped_df[cols],
            use_container_width=True,
            hide_index=True,
        )
