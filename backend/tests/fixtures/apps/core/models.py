from __future__ import annotations
import re
from django.db import models
from django.db.models import F, Q
from pgvector.django import VectorField

class Source(models.Model):

    class SourceType(models.TextChoices):
        COMMERCE = ('COMMERCE', 'Commerce')
        CONTENT = ('CONTENT', 'Content')
        SEARCH = ('SEARCH', 'Search')

    class CollectionMethod(models.TextChoices):
        API = ('API', 'API')
        JSON = ('JSON', 'JSON')
        HTML = ('HTML', 'HTML')
        BROWSER = ('BROWSER', 'Browser')

    class Status(models.TextChoices):
        ACTIVE = ('ACTIVE', 'Active')
        INACTIVE = ('INACTIVE', 'Inactive')
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    base_url = models.TextField(null=True, blank=True)
    collection_method = models.CharField(max_length=30, choices=CollectionMethod.choices, null=True, blank=True)
    crawl_interval_minutes = models.IntegerField(null=True, blank=True)
    requests_per_minute = models.IntegerField(null=True, blank=True)
    policy_version = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"collection"."source"'

    def __str__(self):
        return f'{self.code} - {self.name}'

def normalize_dictionary_text(value: str | None) -> str | None:
    """
    FEEDIT Dictionary 공통 문자열 정규화.

    - lowercase
    - "_" / "-" -> space
    - 특수문자 제거
    - 연속 공백 축약

    주의:
    "와이드핏"과 "와이드 핏"을 강제로 붙이지는 않는다.
    형태적으로 다른 표현은 TermAlias에서 같은 canonical term으로 묶는다.
    """
    if value is None:
        return None
    text = str(value).lower().strip()
    if not text:
        return ''
    text = text.replace('_', ' ')
    text = text.replace('-', ' ')
    text = re.sub('[^\\w가-힣\\s]', ' ', text)
    text = re.sub('\\s+', ' ', text)
    return text.strip()

class DictionaryTerm(models.Model):

    class TermType(models.TextChoices):
        BRAND = ('BRAND', '브랜드')
        STYLE = ('STYLE', '스타일')
        ITEM = ('ITEM', '아이템')
        DETAIL = ('DETAIL', '디테일')
        MATERIAL = ('MATERIAL', '소재')
        COLOR = ('COLOR', '색상')
        TPO = ('TPO', 'TPO')
        PERSON = ('PERSON', '인물')
        TARGET = ('TARGET', '타깃')

    class Status(models.TextChoices):
        ACTIVE = ('ACTIVE', '활성')
        INACTIVE = ('INACTIVE', '비활성')
        MERGED = ('MERGED', '병합됨')
    term_code = models.CharField(max_length=150, unique=True, db_index=True, null=True, blank=True, verbose_name='용어 코드')
    term_type = models.CharField(max_length=30, choices=TermType.choices, db_index=True, verbose_name='용어 유형')
    canonical_name = models.CharField(max_length=255, verbose_name='표준 용어명')
    normalized_name = models.CharField(max_length=255, blank=True, db_index=True, verbose_name='정규화 용어명')
    english_name = models.CharField(max_length=255, null=True, blank=True, verbose_name='영문명')
    description = models.TextField(null=True, blank=True, verbose_name='설명')
    brand = models.OneToOneField('Brand', on_delete=models.SET_NULL, null=True, blank=True, related_name='dictionary_term', verbose_name='표준 브랜드')
    embedding = VectorField(dimensions=1536, null=True, blank=True, verbose_name='용어 임베딩')
    embedding_updated_at = models.DateTimeField(null=True, blank=True, verbose_name='임베딩 갱신일시')
    first_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='최초 관측일')
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='최근 관측일')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True, verbose_name='상태')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')

    class Meta:
        db_table = '"dictionary"."dictionary_term"'
        verbose_name = '표준 용어'
        verbose_name_plural = '표준 용어'
        constraints = [models.UniqueConstraint(fields=['term_type', 'normalized_name'], name='uq_dict_term_name'), models.CheckConstraint(condition=Q(term_type__in=['BRAND', 'STYLE', 'ITEM', 'DETAIL', 'MATERIAL', 'COLOR', 'TPO', 'PERSON', 'TARGET']), name='ck_dict_term_type'), models.CheckConstraint(condition=Q(status__in=['ACTIVE', 'INACTIVE', 'MERGED']), name='ck_dict_term_status')]
        indexes = [models.Index(fields=['term_type', 'normalized_name'], name='idx_dict_term_type_norm')]

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_dictionary_text(self.canonical_name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'[{self.term_type}] {self.canonical_name}'

class TermAlias(models.Model):

    class AliasType(models.TextChoices):
        SYNONYM = ('SYNONYM', '동의어/유사어')
        PLATFORM = ('PLATFORM', '플랫폼 표기')
        OCR = ('OCR', 'OCR 표기')
        TYPO = ('TYPO', '오탈자')
        OTHER = ('OTHER', '기타')
    term = models.ForeignKey(DictionaryTerm, on_delete=models.CASCADE, related_name='aliases', verbose_name='표준 용어')
    source = models.ForeignKey('core.Source', on_delete=models.SET_NULL, null=True, blank=True, related_name='term_aliases', verbose_name='출처')
    alias = models.CharField(max_length=255, db_index=True, verbose_name='별칭')
    normalized_alias = models.CharField(max_length=255, blank=True, db_index=True, verbose_name='정규화 별칭')
    alias_type = models.CharField(max_length=30, choices=AliasType.choices, default=AliasType.SYNONYM, db_index=True, verbose_name='별칭 유형')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."term_alias"'
        constraints = [models.UniqueConstraint(fields=['term', 'alias'], condition=Q(source__isnull=True), name='uq_term_alias_global'), models.UniqueConstraint(fields=['term', 'alias', 'source'], condition=Q(source__isnull=False), name='uq_term_alias_source')]
        indexes = [models.Index(fields=['alias'], name='idx_term_alias'), models.Index(fields=['normalized_alias'], name='idx_term_alias_norm'), models.Index(fields=['source', 'alias'], name='idx_term_alias_source')]

    def save(self, *args, **kwargs):
        self.normalized_alias = normalize_dictionary_text(self.alias)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.alias} -> {self.term.canonical_name}'

class Category(models.Model):

    class CategoryType(models.TextChoices):
        PRODUCT = ('PRODUCT', '상품 카테고리')
        BRAND = ('BRAND', '브랜드 카테고리')

    class Status(models.TextChoices):
        ACTIVE = ('ACTIVE', '활성')
        INACTIVE = ('INACTIVE', '비활성')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children', verbose_name='상위 카테고리')
    category_type = models.CharField(max_length=20, choices=CategoryType.choices, default=CategoryType.PRODUCT, db_index=True, verbose_name='카테고리 유형')
    code = models.CharField(max_length=100, unique=True, db_index=True, verbose_name='카테고리 코드')
    name = models.CharField(max_length=150, verbose_name='카테고리명')
    level = models.PositiveSmallIntegerField(default=1, verbose_name='계층 레벨')
    sort_order = models.PositiveIntegerField(null=True, blank=True, verbose_name='정렬 순서')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True, verbose_name='상태')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."category"'
        ordering = ['category_type', 'level', 'sort_order', 'code']
        constraints = [models.CheckConstraint(condition=Q(category_type__in=['PRODUCT', 'BRAND']), name='ck_category_type'), models.CheckConstraint(condition=Q(level__gte=1), name='ck_category_level'), models.CheckConstraint(condition=Q(sort_order__isnull=True) | Q(sort_order__gte=0), name='ck_category_sort'), models.CheckConstraint(condition=Q(status__in=['ACTIVE', 'INACTIVE']), name='ck_category_status'), models.CheckConstraint(condition=Q(parent__isnull=True) | ~Q(parent=models.F('id')), name='ck_category_self')]

    def __str__(self):
        return f'[{self.category_type}] {self.name}'

class Style(models.Model):
    term = models.OneToOneField(DictionaryTerm, on_delete=models.CASCADE, primary_key=True, related_name='style', verbose_name='용어')
    style_group = models.CharField(max_length=100, null=True, blank=True, verbose_name='스타일 그룹')
    is_core = models.BooleanField(default=False, verbose_name='핵심 스타일')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."style"'
        verbose_name = '스타일'
        verbose_name_plural = '스타일'

    def __str__(self):
        return self.term.canonical_name

class Detail(models.Model):

    class AttributeType(models.TextChoices):
        PATTERN = ('PATTERN', '패턴')
        FIT = ('FIT', '핏')
        SILHOUETTE = ('SILHOUETTE', '실루엣')
        LENGTH = ('LENGTH', '기장')
        SHAPE = ('SHAPE', '형태/쉐입')
        NECKLINE = ('NECKLINE', '넥라인/카라')
        SLEEVE = ('SLEEVE', '소매')
        POCKET = ('POCKET', '포켓')
        CLOSURE = ('CLOSURE', '여밈')
        DECORATION = ('DECORATION', '장식')
        ETC = ('ETC', '기타')
    term = models.OneToOneField(DictionaryTerm, on_delete=models.CASCADE, primary_key=True, related_name='detail', verbose_name='용어', limit_choices_to={'term_type': DictionaryTerm.TermType.DETAIL})
    attribute_type = models.CharField(max_length=30, choices=AttributeType.choices, default=AttributeType.ETC, db_index=True, verbose_name='속성 유형')
    target_type = models.CharField(max_length=100, null=True, blank=True, verbose_name='적용 대상')
    note = models.TextField(null=True, blank=True, verbose_name='메모')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."detail"'
        verbose_name = '디테일'
        verbose_name_plural = '디테일'

    def __str__(self):
        return self.term.canonical_name

class Brand(models.Model):

    class PriceTier(models.TextChoices):
        LOW = ('LOW', '저가')
        MID = ('MID', '중가')
        HIGH = ('HIGH', '고가')
        LUXURY = ('LUXURY', '럭셔리')

    class Status(models.TextChoices):
        ACTIVE = ('ACTIVE', '활성')
        INACTIVE = ('INACTIVE', '비활성')
    brand_code = models.CharField(max_length=100, unique=True, db_index=True, help_text='FEEDIT 표준 브랜드 코드. ex) BRAND_NIKE')
    name = models.CharField(max_length=255, null=True, blank=True, db_index=True, verbose_name='표준 브랜드명')
    english_name = models.CharField(max_length=255, null=True, blank=True, verbose_name='영문 브랜드명')
    image_url = models.URLField(max_length=1000, blank=True, null=True, help_text='브랜드 대표 이미지 또는 로고')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='brands', limit_choices_to={'category_type': 'BRAND'}, help_text='FEEDIT 브랜드 카테고리')
    price_tier = models.CharField(max_length=20, choices=PriceTier.choices, null=True, blank=True, db_index=True, verbose_name='가격 포지션', help_text='브랜드의 전반적인 가격 포지션')
    product_categories = models.ManyToManyField(Category, blank=True, related_name='brands_by_product_focus', limit_choices_to={'category_type': 'PRODUCT'}, verbose_name='주요 상품군', help_text='브랜드가 주력으로 전개하는 FEEDIT 상품 카테고리')
    country_code = models.CharField(max_length=10, blank=True, null=True, db_index=True, help_text='KR / US / JP / FR 등')
    description = models.TextField(blank=True, null=True, help_text='브랜드 소개 / 컨셉 / 슬로건')
    target_gender = models.JSONField(blank=True, null=True, help_text='ex) ["WOMEN", "MEN", "UNISEX"]')
    target_age = models.JSONField(blank=True, null=True, help_text='ex) ["20", "25", "30"]')
    website_url = models.URLField(max_length=1000, blank=True, null=True)
    terms = models.ManyToManyField(DictionaryTerm, blank=True, related_name='brands', verbose_name='연관 키워드', help_text='브랜드를 설명하는 FEEDIT Dictionary Term')
    is_verified = models.BooleanField(default=False, db_index=True, help_text='관리자가 표준 브랜드 정보를 검수했는지 여부')
    source_count = models.PositiveIntegerField(default=0, help_text='현재 연결된 플랫폼 BrandSource 수')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True, verbose_name='상태')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."brand"'
        ordering = ['name']

    def __str__(self):
        return f'[{self.brand_code}] {self.name}'

class CategorySource(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='source_mappings', verbose_name='FEEDIT 표준 카테고리')
    source = models.ForeignKey('core.Source', on_delete=models.CASCADE, related_name='category_sources', verbose_name='출처')
    source_category_id = models.CharField(max_length=255, verbose_name='플랫폼 카테고리 ID')
    source_category_name = models.CharField(max_length=255, null=True, blank=True, db_index=True, verbose_name='플랫폼 카테고리명')
    source_category_path = models.TextField(null=True, blank=True, verbose_name='플랫폼 카테고리 경로')
    first_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='최초 관측일')
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='최근 관측일')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')

    class Meta:
        db_table = '"dictionary"."category_source"'
        verbose_name = '플랫폼 카테고리'
        verbose_name_plural = '플랫폼 카테고리'
        constraints = [models.UniqueConstraint(fields=['source', 'source_category_id'], name='uq_category_source_src_id'), models.CheckConstraint(condition=Q(last_seen_at__isnull=True) | Q(first_seen_at__isnull=True) | Q(last_seen_at__gte=models.F('first_seen_at')), name='ck_category_source_seen')]
        indexes = [models.Index(fields=['source', 'source_category_id'], name='idx_cat_source_src_id'), models.Index(fields=['source', 'source_category_name'], name='idx_cat_source_name'), models.Index(fields=['category'], name='idx_cat_source_category')]

    def __str__(self):
        target = self.category.name if self.category_id else 'UNMAPPED'
        return f'[{self.source.code}] {self.source_category_name or self.source_category_id} -> {target}'

class BrandSource(models.Model):

    class MappingStatus(models.TextChoices):
        UNMAPPED = ('UNMAPPED', '미매핑')
        AUTO_MAPPED = ('AUTO_MAPPED', '자동 매핑')
        MANUAL_MAPPED = ('MANUAL_MAPPED', '수동 매핑')
        EXCLUDED = ('EXCLUDED', '제외')

    class MappingMethod(models.TextChoices):
        SOURCE_ID = ('SOURCE_ID', 'Source ID')
        EXACT_NAME = ('EXACT_NAME', '정확 이름')
        ALIAS = ('ALIAS', 'Alias')
        SIMILARITY = ('SIMILARITY', '유사도')
        MANUAL = ('MANUAL', '수동')
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='brand_sources')
    source = models.ForeignKey('core.Source', on_delete=models.CASCADE, related_name='brand_sources')
    source_brand_id = models.CharField(max_length=255, help_text='플랫폼 브랜드/스토어 고유 ID')
    name = models.CharField(max_length=200, db_index=True, null=True, blank=True, help_text='플랫폼에서 수집한 브랜드명')
    english_name = models.CharField(max_length=200, blank=True, null=True)
    image_url = models.URLField(max_length=1000, blank=True, null=True, help_text='플랫폼에서 제공한 대표 이미지/로고')
    country_code = models.CharField(max_length=10, blank=True, null=True, db_index=True)
    description = models.TextField(blank=True, null=True, help_text='플랫폼에서 제공한 브랜드 소개/문구')
    target_gender = models.JSONField(blank=True, null=True)
    target_age = models.JSONField(blank=True, null=True)
    styles = models.ManyToManyField(Style, blank=True, related_name='brand_sources')
    website_url = models.URLField(max_length=1000, blank=True, null=True)
    source_profile_url = models.URLField(max_length=1000, blank=True, null=True, help_text='플랫폼 브랜드/스토어 페이지')
    attributes = models.JSONField(blank=True, null=True, help_text='플랫폼별 추가 원본 정보')
    mapping_status = models.CharField(max_length=30, choices=MappingStatus.choices, default=MappingStatus.UNMAPPED, db_index=True)
    mapping_method = models.CharField(max_length=30, choices=MappingMethod.choices, blank=True, null=True)
    mapping_confidence = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    detected_count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(blank=True, null=True)
    last_seen_at = models.DateTimeField(blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"dictionary"."brand_source"'
        constraints = [models.UniqueConstraint(fields=['source', 'source_brand_id'], name='uq_brand_source_source_brand_id')]

    def __str__(self):
        return f'[{self.source.code}] {self.name}'

class Product(models.Model):

    class Status(models.TextChoices):
        ACTIVE = ('ACTIVE', '활성')
        INACTIVE = ('INACTIVE', '비활성')
    product_code = models.CharField(max_length=255, unique=True, db_index=True, null=True, blank=True, verbose_name='상품 코드')
    group_key = models.CharField(max_length=150, null=True, blank=True, db_index=True, verbose_name='상품 그룹 키')
    brand = models.ForeignKey('core.Brand', on_delete=models.SET_NULL, null=True, blank=True, related_name='products', verbose_name='브랜드')
    category = models.ForeignKey('core.Category', on_delete=models.SET_NULL, null=True, blank=True, related_name='products', verbose_name='표준 카테고리')
    styles = models.ManyToManyField('core.Style', related_name='products', blank=True, verbose_name='스타일')
    canonical_name = models.CharField(max_length=500, verbose_name='상품명')
    normalized_name = models.CharField(max_length=500, verbose_name='검색용 상품명')
    english_name = models.CharField(max_length=500, null=True, blank=True, verbose_name='영문 상품명')
    gender_scope = models.CharField(max_length=30, null=True, blank=True, verbose_name='성별 범위')
    attributes = models.JSONField(default=dict, blank=True, verbose_name='표준 상품 속성')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True, verbose_name='상태')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')

    class Meta:
        db_table = '"commerce"."product"'
        indexes = [models.Index(fields=['brand', 'normalized_name'], name='idx_product_brand'), models.Index(fields=['category'], name='idx_product_cat'), models.Index(fields=['brand', 'group_key'], name='idx_product_group')]

class ProductSource(models.Model):

    class MarketType(models.TextChoices):
        RETAIL = ('RETAIL', '일반 판매')
        RESALE = ('RESALE', '리셀')

    class Status(models.TextChoices):
        ACTIVE = ('ACTIVE', '활성')
        INACTIVE = ('INACTIVE', '비활성')

    class MappingStatus(models.TextChoices):
        UNMAPPED = ('UNMAPPED', '표준 상품 미매핑')
        MAPPED = ('MAPPED', '표준 상품 연결 완료')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='sources', verbose_name='표준 상품')
    source = models.ForeignKey('core.Source', on_delete=models.PROTECT, related_name='product_sources', verbose_name='플랫폼')
    source_product_id = models.CharField(max_length=255, verbose_name='플랫폼 상품 ID')
    style_no = models.CharField(max_length=255, null=True, blank=True, db_index=True, verbose_name='스타일/모델 번호')
    source_name = models.CharField(max_length=500, null=True, blank=True, verbose_name='플랫폼 상품명')
    normalized_name = models.CharField(max_length=500, null=True, blank=True, db_index=True, verbose_name='정규화 상품명')
    source_brand = models.ForeignKey('core.BrandSource', on_delete=models.SET_NULL, null=True, blank=True, related_name='product_sources', verbose_name='플랫폼 브랜드')
    source_category = models.ForeignKey('core.CategorySource', on_delete=models.SET_NULL, null=True, blank=True, related_name='product_sources', verbose_name='플랫폼 카테고리')
    source_name_en = models.CharField(max_length=500, null=True, blank=True, verbose_name='플랫폼 영문 상품명')
    thumbnail_url = models.TextField(null=True, blank=True, verbose_name='대표 이미지 URL')
    product_url = models.TextField(null=True, blank=True, verbose_name='상품 URL')
    gender_scope = models.CharField(max_length=50, null=True, blank=True, verbose_name='성별 범위')
    attributes = models.JSONField(default=dict, blank=True, verbose_name='플랫폼 상품 속성')
    season_year = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True, verbose_name='시즌 연도')
    season = models.CharField(max_length=50, null=True, blank=True, db_index=True, verbose_name='시즌')
    source_genders = models.JSONField(default=list, blank=True, verbose_name='플랫폼 성별 정보')
    sell_start_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name='판매 시작일시')
    sell_end_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name='판매 종료일시')
    market_type = models.CharField(max_length=20, choices=MarketType.choices, default=MarketType.RETAIL, verbose_name='판매 유형')
    mapping_status = models.CharField(max_length=20, choices=MappingStatus.choices, default=MappingStatus.UNMAPPED, db_index=True, verbose_name='상품 매핑 상태')
    first_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='최초 발견일시')
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='최근 확인일시')
    detected_count = models.BigIntegerField(default=1, verbose_name='발견 횟수')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True, verbose_name='상태')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')

    class Meta:
        db_table = '"commerce"."product_source"'
        verbose_name = '플랫폼 상품'
        verbose_name_plural = '플랫폼 상품'
        constraints = [models.UniqueConstraint(fields=['source', 'source_product_id'], name='uq_product_src')]
        indexes = [models.Index(fields=['source', 'source_product_id'], name='idx_prod_src_lookup'), models.Index(fields=['product'], name='idx_prod_src_prod'), models.Index(fields=['source_brand'], name='idx_prod_src_brand'), models.Index(fields=['source_category'], name='idx_prod_src_cat'), models.Index(fields=['source', 'mapping_status'], name='idx_prod_src_map_status'), models.Index(fields=['style_no'], name='idx_prod_src_style'), models.Index(fields=['market_type'], name='idx_prod_src_market')]

    def __str__(self):
        name = self.source_name or self.source_product_id
        return f'[{self.source.code}] {name}'

class ProductTerm(models.Model):

    class RelationType(models.TextChoices):
        """
        ProductSource와 DictionaryTerm 사이의 관계 유형.

        DictionaryTerm.term_type:
            해당 용어 자체의 사전 분류

        ProductTerm.relation_type:
            해당 용어가 이 상품에서 어떤 역할로 사용됐는지
        """
        HAS_ITEM = ('HAS_ITEM', '아이템')
        HAS_MATERIAL = ('HAS_MATERIAL', '소재')
        HAS_COLOR = ('HAS_COLOR', '색상')
        HAS_FIT = ('HAS_FIT', '핏')
        HAS_SILHOUETTE = ('HAS_SILHOUETTE', '실루엣')
        HAS_NECKLINE = ('HAS_NECKLINE', '넥라인')
        HAS_SLEEVE = ('HAS_SLEEVE', '소매')
        HAS_LENGTH = ('HAS_LENGTH', '기장')
        HAS_SHAPE = ('HAS_SHAPE', '형태')
        HAS_DETAIL = ('HAS_DETAIL', '디테일')
        HAS_STYLE = ('HAS_STYLE', '스타일')
        HAS_TPO = ('HAS_TPO', 'TPO')
    product_source = models.ForeignKey('core.ProductSource', on_delete=models.CASCADE, related_name='product_terms', verbose_name='소스 상품', null=True, blank=True)
    term = models.ForeignKey('core.DictionaryTerm', on_delete=models.CASCADE, related_name='product_terms', verbose_name='상품 특성')
    relation_type = models.CharField(max_length=32, choices=RelationType.choices, db_index=True, null=True, blank=True, verbose_name='관계 유형')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')

    class Meta:
        db_table = '"commerce"."product_term"'
        constraints = [models.UniqueConstraint(fields=['product_source', 'term', 'relation_type'], name='uq_prodsrc_term_relation')]
        indexes = [models.Index(fields=['product_source'], name='idx_prod_term_source'), models.Index(fields=['relation_type', 'term'], name='idx_prod_term_relation')]
        verbose_name = '상품 특성 관계'
        verbose_name_plural = '상품 특성 관계'

    def __str__(self):
        return f'{self.product_source_id} / {self.relation_type} / {self.term.term_code}'
