from django.db import models
from django.db.models import Q
from pgvector.django import VectorField


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

    brand = models.OneToOneField(
        "Brand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dictionary_term",
        verbose_name="표준 브랜드",
    )

    embedding = VectorField(
        dimensions=1536,
        null=True,
        blank=True,
        verbose_name="용어 임베딩",
    )

    embedding_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="임베딩 갱신일시",
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
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="상태",
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

        verbose_name = "표준 용어"
        verbose_name_plural = "표준 용어"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "term_type",
                    "canonical_name",
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
            models.UniqueConstraint(
                fields=[
                    "term",
                    "alias",
                ],
                condition=Q(
                    source__isnull=True,
                ),
                name="uq_term_alias_global",
            ),

            models.UniqueConstraint(
                fields=[
                    "term",
                    "alias",
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
                    "alias",
                ],
                name="idx_term_alias",
            ),

            models.Index(
                fields=[
                    "source",
                    "alias",
                ],
                name="idx_term_alias_source",
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
        REVIEWING = "REVIEWING", "검토 중"
        RESOLVED = "RESOLVED", "처리 완료"

    class Decision(models.TextChoices):
        PENDING = "PENDING", "미판정"
        NEW_TERM = "NEW_TERM", "신규 표준 용어"
        ALIAS = "ALIAS", "기존 용어 별칭"
        REJECT = "REJECT", "제외"

    raw_term = models.CharField(
        max_length=255,
        verbose_name="원본 용어",
    )
    suggested_attribute_type = models.CharField(
    max_length=50,
    null=True,
    blank=True,
    db_index=True,
    verbose_name="추천 세부 속성 유형",
    )
    suggested_type = models.CharField(
        max_length=30,
        choices=DictionaryTerm.TermType.choices,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="추천 용어 유형",
    )
    decision_reason = models.TextField(
    null=True,
    blank=True,
    verbose_name="자동 판정 사유",
    )

    detected_count = models.BigIntegerField(
        default=1,
        verbose_name="총 발견 횟수",
    )

    source_count = models.PositiveIntegerField(
        default=1,
        verbose_name="발견 출처 수",
    )

    confidence = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="후보 신뢰도",
    )
    embedding = VectorField(
        dimensions=1536,
        null=True,
        blank=True,
        verbose_name="후보 임베딩",
    )
    embedding_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="임베딩 갱신일시",
    )
    nearest_term = models.ForeignKey(
        DictionaryTerm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nearest_candidates",
        verbose_name="가장 유사한 기존 용어",
    )
    similarity_score = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="기존 용어 유사도",
    )
    decision = models.CharField(
        max_length=20,
        choices=Decision.choices,
        default=Decision.PENDING,
        db_index=True,
        verbose_name="판정",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="처리 상태",
    )

    note = models.TextField(
        null=True,
        blank=True,
        verbose_name="검토 메모",
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

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"dictionary"."term_candidate"'
        verbose_name = "신규 용어 후보"
        verbose_name_plural = "신규 용어 후보"

        indexes = [
            models.Index(
                fields=["raw_term", "suggested_type"],
                name="idx_term_cand_raw_type",
            ),
            models.Index(
                fields=["status", "decision"],
                name="idx_term_cand_decision",
            ),
            models.Index(
                fields=["suggested_type", "-detected_count",],
                name="idx_term_cand_type_count",
            ),
            models.Index(
                fields=["-last_seen_at",],
                name="idx_term_cand_last_seen",
            ),]

    def __str__(self):
        return (
            f"{self.raw_term} "
            f"[{self.get_decision_display()}]"
        )
    
class TermCandidateObservation(models.Model):

    class SourceType(models.TextChoices):
        PRODUCT_NAME = (
            "PRODUCT_NAME",
            "상품명",
        )
        PRODUCT_ATTRIBUTE = (
            "PRODUCT_ATTRIBUTE",
            "상품 속성",
        )
        PRODUCT_DESCRIPTION = (
            "PRODUCT_DESCRIPTION",
            "상품 설명",
        )
        OCR = (
            "OCR",
            "OCR",
        )
        VIDEO_TITLE = (
            "VIDEO_TITLE",
            "영상 제목",
        )
        TRANSCRIPT = (
            "TRANSCRIPT",
            "영상 자막",
        )
        REVIEW = (
            "REVIEW",
            "리뷰",
        )
        COMMENT = (
            "COMMENT",
            "댓글",
        )
        OTHER = (
            "OTHER",
            "기타",
        )

    candidate = models.ForeignKey(
        TermCandidate,
        on_delete=models.CASCADE,
        related_name="observations",
        verbose_name="용어 후보",
    )

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="term_candidate_observations",
        verbose_name="출처",
    )

    source_type = models.CharField(
        max_length=30,
        choices=SourceType.choices,
        db_index=True,
        verbose_name="발견 데이터 유형",
    )

    source_entity_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="원본 엔터티 ID",
    )

    detected_phrase = models.CharField(
        max_length=255,
        verbose_name="발견 표현",
    )

    raw_text = models.TextField(
        verbose_name="원본 문맥",
    )

    detected_at = models.DateTimeField(
        db_index=True,
        verbose_name="발견일시",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = (
            '"dictionary".'
            '"term_candidate_observation"'
        )

        verbose_name = "용어 후보 관측"
        verbose_name_plural = "용어 후보 관측"

        indexes = [
            models.Index(
                fields=[
                    "candidate",
                    "-detected_at",
                ],
                name="idx_term_obs_candidate",
            ),

            models.Index(
                fields=[
                    "source",
                    "source_type",
                ],
                name="idx_term_obs_source",
            ),
        ]

    def __str__(self):
        return (
            f"{self.candidate.raw_term} "
            f"/ {self.source_type}"
        )

class Brand(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"

    brand_code = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="FEEDIT 표준 브랜드 코드. ex) BRAND_NIKE",
    )

    name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="표준 브랜드명",
    )

    english_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="영문 브랜드명",
    )

    image_url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        help_text="브랜드 대표 이미지 또는 로고",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="brands",
        limit_choices_to={"category_type": "BRAND"},
        help_text="FEEDIT 브랜드 카테고리",
    )
    country_code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        db_index=True,
        help_text="KR / US / JP / FR 등",
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="브랜드 소개 / 컨셉 / 슬로건",
    )
    target_gender = models.JSONField(
        blank=True,
        null=True,
        help_text='ex) ["WOMEN", "MEN", "UNISEX"]',
    )
    target_age = models.JSONField(
        blank=True,
        null=True,
        help_text='ex) ["20", "25", "30"]',
    )
    styles = models.ManyToManyField(
        "Style",
        blank=True,
        related_name="brands",
        help_text="FEEDIT 표준 스타일",
    )
    website_url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
    )
    is_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="관리자가 표준 브랜드 정보를 검수했는지 여부",
    )
    source_count = models.PositiveIntegerField(
        default=0,
        help_text="현재 연결된 플랫폼 BrandSource 수",
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
        return f"[{self.brand_code}] {self.name}"

    
class CategorySource(models.Model):

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_mappings",
        verbose_name="FEEDIT 표준 카테고리",
    )

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.CASCADE,
        related_name="category_sources",
        verbose_name="출처",
    )

    source_category_id = models.CharField(
        max_length=255,
        verbose_name="플랫폼 카테고리 ID",
    )

    source_category_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="플랫폼 카테고리명",
    )

    source_category_path = models.TextField(
        null=True,
        blank=True,
        verbose_name="플랫폼 카테고리 경로",
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
        db_table = '"dictionary"."category_source"'

        verbose_name = "플랫폼 카테고리"
        verbose_name_plural = "플랫폼 카테고리"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source",
                    "source_category_id",
                ],
                name="uq_category_source_src_id",
            ),
            models.CheckConstraint(
                condition=(
                    Q(last_seen_at__isnull=True)
                    | Q(first_seen_at__isnull=True)
                    | Q(last_seen_at__gte=models.F("first_seen_at"))
                ),
                name="ck_category_source_seen",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "source",
                    "source_category_id",
                ],
                name="idx_cat_source_src_id",
            ),
            models.Index(
                fields=[
                    "source",
                    "source_category_name",
                ],
                name="idx_cat_source_name",
            ),
            models.Index(
                fields=["category"],
                name="idx_cat_source_category",
            ),
        ]

    def __str__(self):
        target = (
            self.category.name
            if self.category_id
            else "UNMAPPED"
        )

        return (
            f"[{self.source.code}] "
            f"{self.source_category_name or self.source_category_id} "
            f"-> {target}"
        )

    
class BrandSource(models.Model):

    class MappingStatus(models.TextChoices):
        UNMAPPED = "UNMAPPED", "미매핑"
        AUTO_MAPPED = "AUTO_MAPPED", "자동 매핑"
        MANUAL_MAPPED = "MANUAL_MAPPED", "수동 매핑"
        EXCLUDED = "EXCLUDED", "제외"

    class MappingMethod(models.TextChoices):
        SOURCE_ID = "SOURCE_ID", "Source ID"
        EXACT_NAME = "EXACT_NAME", "정확 이름"
        ALIAS = "ALIAS", "Alias"
        SIMILARITY = "SIMILARITY", "유사도"
        MANUAL = "MANUAL", "수동"

    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="brand_sources",
    )       

    source = models.ForeignKey(
        "Source",
        on_delete=models.CASCADE,
        related_name="brand_sources",
    )

    source_brand_id = models.CharField(
        max_length=255,
        help_text="플랫폼 브랜드/스토어 고유 ID",
    )

    name = models.CharField(
        max_length=200,
        db_index=True,
        null=True,
        blank=True,
        help_text="플랫폼에서 수집한 브랜드명",
    )

    english_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
    )
    image_url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        help_text="플랫폼에서 제공한 대표 이미지/로고",
    )

    country_code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        db_index=True,
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="플랫폼에서 제공한 브랜드 소개/문구",
    )
    target_gender = models.JSONField(
        blank=True,
        null=True,
    )

    target_age = models.JSONField(
        blank=True,
        null=True,
    )
    styles = models.ManyToManyField(
        "Style",
        blank=True,
        related_name="brand_sources",
    )

    website_url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
    )
    source_profile_url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        help_text="플랫폼 브랜드/스토어 페이지",
    )
    attributes = models.JSONField(
        blank=True,
        null=True,
        help_text="플랫폼별 추가 원본 정보",
    )

    mapping_status = models.CharField(
        max_length=30,
        choices=MappingStatus.choices,
        default=MappingStatus.UNMAPPED,
        db_index=True,
    )

    mapping_method = models.CharField(
        max_length=30,
        choices=MappingMethod.choices,
        blank=True,
        null=True,
    )

    mapping_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        blank=True,
        null=True,
    )

    # ========================================================
    # OBSERVATION
    # ========================================================

    detected_count = models.PositiveIntegerField(
        default=0,
    )

    first_seen_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    last_seen_at = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"dictionary"."brand_source"'

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source",
                    "source_brand_id",
                ],
                name="uq_brand_source_source_brand_id",
            ),
        ]

    def __str__(self):
        return (
            f"[{self.source.code}] "
            f"{self.name}"
        )