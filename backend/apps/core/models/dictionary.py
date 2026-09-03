from django.db import models
from django.db.models import Q


class DictionaryTerm(models.Model):

    class TermType(models.TextChoices):
        BRAND = "BRAND", "브랜드"
        STYLE = "STYLE", "스타일"
        ITEM = "ITEM", "아이템"
        DETAIL = "DETAIL", "디테일"
        MATERIAL = "MATERIAL", "소재"
        COLOR = "COLOR", "색상"
        TPO = "TPO", "TPO"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"
        MERGED = "MERGED", "병합됨"

    term_code = models.CharField(
        max_length=150,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        verbose_name="용어 코드",
    )

    term_type = models.CharField(
        max_length=30,
        choices=TermType.choices,
        verbose_name="용어 유형",
    )

    canonical_name = models.CharField(
        max_length=255,
        verbose_name="표준 용어명",
    )

    normalized_name = models.CharField(
        max_length=255,
        verbose_name="정규화 용어명",
    )

    english_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="영문명",
    )

    description = models.TextField(
        null=True,
        blank=True,
        verbose_name="설명",
    )

    # BRAND 타입 용어일 때 실제 FEEDIT 표준 브랜드와 연결
    brand = models.OneToOneField(
        "Brand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dictionary_term",
        verbose_name="표준 브랜드",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="상태",
    )

    first_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="최초 관측일",
    )

    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="최근 관측일",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정일시",
    )

    class Meta:
        db_table = '"dictionary"."dictionary_term"'

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "term_type",
                    "normalized_name",
                ],
                name="uq_dict_term_name",
            ),

            models.CheckConstraint(
                condition=Q(
                    term_type__in=[
                        "BRAND",
                        "STYLE",
                        "ITEM",
                        "DETAIL",
                        "MATERIAL",
                        "COLOR",
                        "TPO",
                    ]
                ),
                name="ck_dict_term_type",
            ),

            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "ACTIVE",
                        "INACTIVE",
                        "MERGED",
                    ]
                ),
                name="ck_dict_term_status",
            ),
        ]

    def __str__(self):
        return (
            f"[{self.term_type}] "
            f"{self.canonical_name}"
        )

class TermAlias(models.Model):

    class AliasType(models.TextChoices):
        SYNONYM = "SYNONYM", "동의어/유사어"
        PLATFORM = "PLATFORM", "플랫폼 표기"
        OCR = "OCR", "OCR 표기"
        TYPO = "TYPO", "오탈자"
        OTHER = "OTHER", "기타"

    term = models.ForeignKey(
        DictionaryTerm,
        on_delete=models.CASCADE,
        related_name="aliases",
        verbose_name="표준 용어",
    )

    # NULL이면 모든 소스에서 공통 사용
    source = models.ForeignKey(
        "core.Source",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="term_aliases",
        verbose_name="출처",
    )

    alias = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="별칭",
    )

    normalized_alias = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="정규화 별칭",
    )

    alias_type = models.CharField(
        max_length=30,
        choices=AliasType.choices,
        default=AliasType.SYNONYM,
        db_index=True,
        verbose_name="별칭 유형",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"dictionary"."term_alias"'

        constraints = [
            # 공통 alias
            models.UniqueConstraint(
                fields=[
                    "term",
                    "normalized_alias",
                ],
                condition=Q(
                    source__isnull=True,
                ),
                name="uq_term_alias_global",
            ),

            # source별 alias
            models.UniqueConstraint(
                fields=[
                    "term",
                    "normalized_alias",
                    "source",
                ],
                condition=Q(
                    source__isnull=False,
                ),
                name="uq_term_alias_source",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "normalized_alias",
                ],
                name="idx_term_alias_norm",
            ),

            models.Index(
                fields=[
                    "source",
                    "normalized_alias",
                ],
                name="idx_term_alias_src_norm",
            ),
        ]

    def __str__(self):
        return (
            f"{self.alias} "
            f"-> {self.term.canonical_name}"
        )
    
class Category(models.Model):

    class CategoryType(models.TextChoices):
        PRODUCT = "PRODUCT", "상품 카테고리"
        BRAND = "BRAND", "브랜드 카테고리"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"

    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="상위 카테고리",
    )

    category_type = models.CharField(
        max_length=20,
        choices=CategoryType.choices,
        default=CategoryType.PRODUCT,
        db_index=True,
        verbose_name="카테고리 유형",
    )

    code = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name="카테고리 코드",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="카테고리명",
    )

    level = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="계층 레벨",
    )

    sort_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="정렬 순서",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="상태",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."category"'

        ordering = [
            "category_type",
            "level",
            "sort_order",
            "code",
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    category_type__in=["PRODUCT", "BRAND"]
                ),
                name="ck_category_type",
            ),
            models.CheckConstraint(
                condition=models.Q(level__gte=1),
                name="ck_category_level",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(sort_order__isnull=True)
                    | models.Q(sort_order__gte=0)
                ),
                name="ck_category_sort",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["ACTIVE", "INACTIVE"]
                ),
                name="ck_category_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(parent__isnull=True)
                    | ~models.Q(parent=models.F("id"))
                ),
                name="ck_category_self",
            ),
        ]

    def __str__(self):
        return f"[{self.category_type}] {self.name}"

class Style(models.Model):
    term = models.OneToOneField(
        DictionaryTerm,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="style",
        verbose_name="용어",
    )

    style_group = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="스타일 그룹",
    )

    is_core = models.BooleanField(
        default=False,
        verbose_name="핵심 스타일",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."style"'
        verbose_name = "스타일"
        verbose_name_plural = "스타일"

    def __str__(self):
        return self.term.canonical_name


class Item(models.Model):
    term = models.OneToOneField(
        DictionaryTerm,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="item",
        verbose_name="용어",
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
        limit_choices_to={"category_type": "PRODUCT"},
        verbose_name="카테고리",
    )

    gender_scope = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        verbose_name="성별 범위",
    )

    note = models.TextField(
        null=True,
        blank=True,
        verbose_name="메모",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."item"'
        verbose_name = "아이템"
        verbose_name_plural = "아이템"

    def __str__(self):
        return self.term.canonical_name


class Detail(models.Model):
    term = models.OneToOneField(
        DictionaryTerm,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="detail",
        verbose_name="용어",
    )

    attribute_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="속성 유형",
    )

    target_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="적용 대상",
    )

    note = models.TextField(
        null=True,
        blank=True,
        verbose_name="메모",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."detail"'
        verbose_name = "디테일"
        verbose_name_plural = "디테일"

    def __str__(self):
        return self.term.canonical_name

class Material(models.Model):
    term = models.OneToOneField(
        DictionaryTerm,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="material",
        verbose_name="용어",
    )

    material_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="소재 유형",
    )

    process_type = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="조직/가공 유형",
    )

    note = models.TextField(
        null=True,
        blank=True,
        verbose_name="메모",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."material"'
        verbose_name = "소재"
        verbose_name_plural = "소재"

    def __str__(self):
        return self.term.canonical_name


class Color(models.Model):
    term = models.OneToOneField(
        DictionaryTerm,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="color",
        verbose_name="용어",
    )

    color_family = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="색상 계열",
    )

    base_color = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_colors",
        verbose_name="기준 색상",
    )

    note = models.TextField(
        null=True,
        blank=True,
        verbose_name="설명",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정일시",
    )

    class Meta:
        db_table = '"dictionary"."color"'
        verbose_name = "색상"
        verbose_name_plural = "색상"

        ordering = [
            "color_family",
            "term__canonical_name",
        ]

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(base_color__isnull=True)
                    | ~models.Q(base_color=models.F("term"))
                ),
                name="ck_color_self_base",
            ),
        ]

    def __str__(self):
        return self.term.canonical_name

class TPO(models.Model):

    term = models.OneToOneField(
        "DictionaryTerm",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="tpo",
        verbose_name="용어",
    )

    tpo_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="TPO 유형",
    )

    note = models.TextField(
        null=True,
        blank=True,
        verbose_name="설명",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정일시",
    )

    class Meta:
        db_table = '"dictionary"."tpo"'
        verbose_name = "TPO"
        verbose_name_plural = "TPO"

        ordering = [
            "tpo_type",
            "term__canonical_name",
        ]

    def __str__(self):
        return self.term.canonical_name

class TermRelation(models.Model):
    source_term = models.ForeignKey(
        DictionaryTerm,
        on_delete=models.CASCADE,
        related_name="outgoing_relations",
        verbose_name="기준 용어",
    )

    target_term = models.ForeignKey(
        DictionaryTerm,
        on_delete=models.CASCADE,
        related_name="incoming_relations",
        verbose_name="연관 용어",
    )

    relation_type = models.CharField(
        max_length=50,
        verbose_name="관계 유형",
    )

    weight = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="가중치",
    )

    confidence = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="신뢰도",
    )

    relation_source = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="관계 출처",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."term_relation"'
        verbose_name = "용어 관계"
        verbose_name_plural = "용어 관계"

        constraints = [
            models.UniqueConstraint(
                fields=["source_term", "target_term", "relation_type"],
                name="uq_term_relation",
            ),
            models.CheckConstraint(
                condition=~models.Q(source_term=models.F("target_term")),
                name="ck_term_rel_self",
            ),
        ]

        indexes = [
            models.Index(
                fields=["source_term", "relation_type"],
                name="idx_term_rel_src",
            ),
            models.Index(
                fields=["target_term", "relation_type"],
                name="idx_term_rel_tgt",
            ),
        ]

    def __str__(self):
        return (
            f"{self.source_term.canonical_name} "
            f"→ {self.target_term.canonical_name}"
        )


class TermCandidate(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "검토 대기"
        APPROVED = "APPROVED", "승인"
        REJECTED = "REJECTED", "제외"

    raw_term = models.CharField(
        max_length=255,
        verbose_name="원본 용어",
    )

    normalized_term = models.CharField(
        max_length=255,
        verbose_name="정규화 용어",
    )

    suggested_type = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        verbose_name="추천 유형",
    )

    detected_count = models.BigIntegerField(
        default=1,
        verbose_name="발견 횟수",
    )

    confidence = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="신뢰도",
    )

    detected_source = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="발견 출처",
    )

    example_context = models.TextField(
        null=True,
        blank=True,
        verbose_name="예시 문맥",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="상태",
    )

    first_seen_at = models.DateTimeField(
        verbose_name="최초 발견일시",
    )

    last_seen_at = models.DateTimeField(
        verbose_name="최근 발견일시",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="검토일시",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."term_candidate"'
        verbose_name = "용어 후보"
        verbose_name_plural = "용어 후보"

        indexes = [
            models.Index(
                fields=["normalized_term", "suggested_type"],
                name="idx_term_cand_norm",
            ),
            models.Index(
                fields=["status", "-detected_count"],
                name="idx_term_cand_status",
            ),
        ]

    def __str__(self):
        return self.raw_term

class Brand(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"

    brand_code = models.CharField(
        max_length=150,
        unique=True,
        null=True,
        blank=True,
        verbose_name="FEEDIT 브랜드 코드",
    )

    name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="표준 브랜드명",
    )

    english_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="영문 브랜드명",
    )

    country_code = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        verbose_name="국가 코드",
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="brands",
        limit_choices_to={"category_type": "BRAND"},
        verbose_name="브랜드 카테고리",
    )

    description = models.TextField(
        null=True,
        blank=True,
        verbose_name="설명",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="상태",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."brand"'
        ordering = ["name"]

    def __str__(self):
        return self.name
    
class CategoryAlias(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="aliases",
        verbose_name="표준 카테고리",
    )

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.CASCADE,
        related_name="category_aliases",
        verbose_name="출처",
    )

    source_category_id = models.CharField(
        max_length=255,
        verbose_name="원본 카테고리 ID",
    )

    source_category_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="원본 카테고리명",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"dictionary"."category_alias"'
        verbose_name = "카테고리 매핑"
        verbose_name_plural = "카테고리 매핑"

        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_category_id"],
                name="uq_cat_alias_src",
            ),
        ]

    def __str__(self):
        return self.source_category_name or self.source_category_id

    
class BrandSource(models.Model):

    class MappingStatus(models.TextChoices):
        UNMAPPED = "UNMAPPED", "미매핑"
        AUTO_MAPPED = "AUTO_MAPPED", "자동 매핑"
        MANUAL_MAPPED = "MANUAL_MAPPED", "수동 매핑"
        REJECTED = "REJECTED", "제외"

    class MappingMethod(models.TextChoices):
        SOURCE_ID = "SOURCE_ID", "기존 Source ID"
        EXACT_NAME = "EXACT_NAME", "이름 정확 일치"
        NORMALIZED_NAME = (
            "NORMALIZED_NAME",
            "정규화 이름 일치",
        )
        ALIAS = "ALIAS", "별칭 일치"
        MANUAL = "MANUAL", "수동 매핑"

    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_mappings",
        verbose_name="표준 브랜드",
    )       

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.CASCADE,
        related_name="brand_sources",
        verbose_name="출처",
    )

    source_brand_id = models.CharField(
        max_length=255,
        verbose_name="플랫폼 브랜드 ID",
    )

    source_brand_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="플랫폼 브랜드명",
    )

    normalized_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="정규화 플랫폼 브랜드명",
    )

    source_brand_name_en = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="플랫폼 영문 브랜드명",
    )

    normalized_name_en = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="정규화 플랫폼 영문 브랜드명",
    )

    source_brand_url = models.URLField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name="플랫폼 브랜드 URL",
    )

    # -----------------------------------------------------
    # Mapping metadata
    # -----------------------------------------------------

    mapping_status = models.CharField(
        max_length=30,
        choices=MappingStatus.choices,
        default=MappingStatus.UNMAPPED,
        db_index=True,
        verbose_name="매핑 상태",
    )

    mapping_method = models.CharField(
        max_length=30,
        choices=MappingMethod.choices,
        null=True,
        blank=True,
        verbose_name="매핑 방식",
    )

    mapping_confidence = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="매핑 신뢰도",
    )

    # -----------------------------------------------------
    # Observation metadata
    # -----------------------------------------------------

    detected_count = models.BigIntegerField(
        default=1,
        verbose_name="발견 횟수",
    )

    first_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="최초 발견일시",
    )

    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="최근 발견일시",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"dictionary"."brand_source"'
        verbose_name = "플랫폼 브랜드"
        verbose_name_plural = "플랫폼 브랜드"

        constraints = [
            # 한 플랫폼 안에서 source_brand_id는 유일
            models.UniqueConstraint(
                fields=[
                    "source",
                    "source_brand_id",
                ],
                name="uq_brand_source_src_id",
            ),

            models.CheckConstraint(
                condition=Q(
                    mapping_status__in=[
                        "UNMAPPED",
                        "AUTO_MAPPED",
                        "MANUAL_MAPPED",
                        "REJECTED",
                    ]
                ),
                name="ck_brand_source_mapping_status",
            ),

            models.CheckConstraint(
                condition=(
                    Q(last_seen_at__isnull=True)
                    | Q(first_seen_at__isnull=True)
                    | Q(
                        last_seen_at__gte=models.F(
                            "first_seen_at"
                        )
                    )
                ),
                name="ck_brand_source_seen",
            ),

            # 매핑 상태와 Brand FK의 일관성 보장
            models.CheckConstraint(
                condition=(
                    (
                        Q(
                            mapping_status__in=[
                                "AUTO_MAPPED",
                                "MANUAL_MAPPED",
                            ]
                        )
                        & Q(
                            brand__isnull=False,
                        )
                    )
                    |
                    (
                        Q(
                            mapping_status__in=[
                                "UNMAPPED",
                                "REJECTED",
                            ]
                        )
                        & Q(
                            brand__isnull=True,
                        )
                    )
                ),
                name="ck_brand_source_mapping_consistency",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "brand",
                ],
                name="idx_brand_source_brand",
            ),

            models.Index(
                fields=[
                    "source",
                    "mapping_status",
                ],
                name="idx_brand_source_status",
            ),

            models.Index(
                fields=[
                    "source",
                    "normalized_name",
                ],
                name="idx_brand_source_name",
            ),
        ]

    def __str__(self):
        brand_name = (
            self.brand.name
            if self.brand_id
            else "UNMAPPED"
        )

        return (
            f"[{self.source.code}] "
            f"{self.source_brand_name or self.source_brand_id} "
            f"-> {brand_name}"
        )


class MappingCandidate(models.Model):

    class MappingType(models.TextChoices):
        BRAND = "BRAND", "브랜드"
        CATEGORY = "CATEGORY", "카테고리"
        DETAIL = "DETAIL", "디테일"
        MATERIAL = "MATERIAL", "소재"
        COLOR = "COLOR", "색상"
        ITEM = "ITEM", "아이템"
        STYLE = "STYLE", "스타일"
        TAG = "TAG", "태그"

    class Status(models.TextChoices):
        PENDING = "PENDING", "검토 대기"
        APPROVED = "APPROVED", "승인"
        CREATE = "CREATE", "신규 생성"
        REJECTED = "REJECTED", "제외"

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.PROTECT,
        related_name="mapping_candidates",
        verbose_name="출처",
    )

    mapping_type = models.CharField(
        max_length=30,
        choices=MappingType.choices,
        db_index=True,
        verbose_name="매핑 유형",
    )

    source_key = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name="원본 키",
    )

    source_name = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="원본명",
    )

    source_detail = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="원본 상세 정보",
    )

    suggested_target_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="추천 대상 유형",
    )

    suggested_target_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="추천 대상 ID",
    )

    suggested_target_name = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="추천 대상명",
    )

    selected_target_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="선택 대상 유형",
    )

    selected_target_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="선택 대상 ID",
    )

    selected_target_name = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="선택 대상명",
    )

    match_method = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="매칭 방식",
    )

    confidence = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="신뢰도",
    )

    detected_count = models.BigIntegerField(
        default=1,
        verbose_name="발견 횟수",
    )

    sample_entity_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="예시 엔터티 ID",
    )

    sample_entity_name = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="예시 엔터티명",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="상태",
    )

    note = models.TextField(
        null=True,
        blank=True,
        verbose_name="검토 메모",
    )

    first_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="최초 발견일시",
    )

    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="최근 발견일시",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="검토일시",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"dictionary"."mapping_candidate"'
        verbose_name = "매핑 후보"
        verbose_name_plural = "매핑 후보"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source",
                    "mapping_type",
                    "source_key",
                ],
                name="uq_mapping_candidate",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "mapping_type",
                    "status",
                ],
                name="idx_mapping_type_status",
            ),
            models.Index(
                fields=[
                    "source",
                    "status",
                ],
                name="idx_mapping_source_status",
            ),
        ]

    def __str__(self):
        return (
            f"[{self.mapping_type}] "
            f"{self.source_name or self.source_key}"
        )