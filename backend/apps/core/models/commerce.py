from django.db import models
from django.db.models import F, Q


class Product(models.Model):

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"

    product_code = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        verbose_name="상품 코드",
    )
    
    group_key = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="상품 그룹 키",
    )

    brand = models.ForeignKey(
        "core.Brand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="브랜드",
    )

    category = models.ForeignKey(
        "core.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="표준 카테고리",
    )

    styles = models.ManyToManyField(
        "core.Style",
        related_name="products",
        blank=True,
        verbose_name="스타일",
    )

    canonical_name = models.CharField(
        max_length=500,
        verbose_name="상품명",
    )

    normalized_name = models.CharField(
        max_length=500,
        verbose_name="검색용 상품명",
    )

    english_name = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="영문 상품명",
    )

    gender_scope = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        verbose_name="성별 범위",
    )

    attributes = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="표준 상품 속성",
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
        db_table = '"commerce"."product"'

        indexes = [
            models.Index(
                fields=["brand", "normalized_name"],
                name="idx_product_brand",
            ),
            models.Index(
                fields=["category"],
                name="idx_product_cat",
            ),
            models.Index(
                fields=["brand", "group_key"],
                name="idx_product_group",
            ),
        ]

    
class ProductSource(models.Model):
    class MarketType(models.TextChoices):
        RETAIL = "RETAIL", "일반 판매"
        RESALE = "RESALE", "리셀"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"

    class MappingStatus(models.TextChoices):
        UNMAPPED = "UNMAPPED", "표준 상품 미매핑"
        MAPPED = "MAPPED", "표준 상품 연결 완료"

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sources",
        verbose_name="표준 상품",
    )

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.PROTECT,
        related_name="product_sources",
        verbose_name="플랫폼",
    )

    source_product_id = models.CharField(
        max_length=255,
        verbose_name="플랫폼 상품 ID",
    )
    style_no = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="스타일/모델 번호",
    )
    source_name = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="플랫폼 상품명",
    )

    normalized_name = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="정규화 상품명",
    )

    source_brand = models.ForeignKey(
        "core.BrandSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_sources",
        verbose_name="플랫폼 브랜드",
    )

    source_category = models.ForeignKey(
        "core.CategorySource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_sources",
        verbose_name="플랫폼 카테고리",
    )
    source_name_en = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="플랫폼 영문 상품명",
    )

    thumbnail_url = models.TextField(
        null=True,
        blank=True,
        verbose_name="대표 이미지 URL",
    )

    product_url = models.TextField(
        null=True,
        blank=True,
        verbose_name="상품 URL",
    )

    gender_scope = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="성별 범위",
    )

    attributes = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="플랫폼 상품 속성",
    )
    season_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="시즌 연도",
    )
    season = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="시즌",
    )

    source_genders = models.JSONField(
        default=list,
        blank=True,
        verbose_name="플랫폼 성별 정보",
    )

    sell_start_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="판매 시작일시",
    )

    sell_end_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="판매 종료일시",
    )
    
    market_type = models.CharField(
        max_length=20,
        choices=MarketType.choices,
        default=MarketType.RETAIL,
        verbose_name="판매 유형",
    )
    mapping_status = models.CharField(
        max_length=20,
        choices=MappingStatus.choices,
        default=MappingStatus.UNMAPPED,
        db_index=True,
        verbose_name="상품 매핑 상태",
    )

    first_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="최초 발견일시",
    )

    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="최근 확인일시",
    )

    detected_count = models.BigIntegerField(
        default=1,
        verbose_name="발견 횟수",
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
        db_table = '"commerce"."product_source"'
        verbose_name = "플랫폼 상품"
        verbose_name_plural = "플랫폼 상품"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source",
                    "source_product_id",
                ],
                name="uq_product_src",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "source",
                    "source_product_id",
                ],
                name="idx_prod_src_lookup",
            ),
            models.Index(
                fields=["product"],
                name="idx_prod_src_prod",
            ),
            models.Index(
                fields=["source_brand"],
                name="idx_prod_src_brand",
            ),
            models.Index(
                fields=["source_category"],
                name="idx_prod_src_cat",
            ),
            models.Index(
                fields=[
                    "source",
                    "mapping_status",
                ],
                name="idx_prod_src_map_status",
            ),
            models.Index(
                fields=["style_no"],
                name="idx_prod_src_style",
            ),
            models.Index(
                fields=["market_type"],
                name="idx_prod_src_market",
            ),
        ]

    def __str__(self):
        name = (
            self.source_name
            or self.source_product_id
        )

        return (
            f"[{self.source.code}] "
            f"{name}"
        )


class ProductSourceRelation(models.Model):
    class RelationType(models.TextChoices):
        RESALE_OF = "RESALE_OF", "중고 매물의 원상품"

    from_product_source = models.ForeignKey(
        ProductSource,
        on_delete=models.CASCADE,
        related_name="outgoing_relations",
    )
    to_product_source = models.ForeignKey(
        ProductSource,
        on_delete=models.CASCADE,
        related_name="incoming_relations",
    )
    relation_type = models.CharField(
        max_length=50,
        choices=RelationType.choices,
    )
    evidence_source = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"commerce"."product_source_relation"'
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "from_product_source",
                    "to_product_source",
                    "relation_type",
                ],
                name="uq_product_source_relation",
            ),
        ]
        indexes = [
            models.Index(
                fields=["from_product_source", "relation_type"],
                name="idx_prod_src_rel_from",
            ),
            models.Index(
                fields=["to_product_source", "relation_type"],
                name="idx_prod_src_rel_to",
            ),
        ]


class ProductSourceSnapshot(models.Model):
    product_source = models.ForeignKey(
        ProductSource,
        on_delete=models.CASCADE,
        related_name="snapshots",
        verbose_name="플랫폼 상품",
    )

    snapshot_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="스냅샷 기준일",
        help_text="한국 시간 기준 수집 날짜",
    )

    observed_at = models.DateTimeField(
        db_index=True,
        verbose_name="최종 관측일시",
        help_text="해당 날짜에 마지막으로 수집된 데이터의 관측 시각",
    )

    list_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="정가")
    sale_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="판매가")
    discount_rate = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True, verbose_name="할인율")

    rank_position = models.IntegerField(null=True, blank=True, verbose_name="순위")
    ranking_scope = models.CharField(max_length=50, null=True, blank=True, verbose_name="랭킹 범위")
    ranking_context = models.JSONField(default=dict, blank=True, verbose_name="랭킹 조건")

    rating = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, verbose_name="평점")
    review_count = models.BigIntegerField(null=True, blank=True, verbose_name="리뷰 수")
    like_count = models.BigIntegerField(null=True, blank=True, verbose_name="좋아요 수")
    view_count = models.BigIntegerField(null=True, blank=True, verbose_name="조회 수")
    sales_count = models.BigIntegerField(null=True, blank=True, verbose_name="판매 수")

    stock_status = models.CharField(max_length=30, null=True, blank=True, verbose_name="재고 상태")
    platform_metrics = models.JSONField(default=dict, blank=True, verbose_name="플랫폼 추가 지표")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일시")

    class Meta:
        db_table = '"snapshot"."product_source_snapshot"'
        verbose_name = "상품 스냅샷"
        verbose_name_plural = "상품 스냅샷"

        constraints = [
            models.UniqueConstraint(
                fields=["product_source", "snapshot_date", "ranking_scope"],
                name="uq_prod_snapshot_daily_scope",
            ),
        ]

        indexes = [
            models.Index(
                fields=["-snapshot_date", "-observed_at"],
                name="idx_prod_snap_date",
            ),
            models.Index(
                fields=["product_source", "-snapshot_date"],
                name="idx_prod_snap_prod_date",
            ),
            models.Index(
                fields=["product_source", "rank_position"],
                name="idx_prod_snap_rank",
            ),
        ]

        ordering = ["-snapshot_date", "-observed_at"]

    def __str__(self):
        return (
            f"{self.product_source} / "
            f"{self.snapshot_date} / "
            f"{self.ranking_scope} / "
            f"{self.observed_at}"
        )


class ResaleSnapshot(models.Model):
    product_source = models.ForeignKey(
        ProductSource,
        on_delete=models.CASCADE,
        related_name="resale_snapshots",
        verbose_name="리셀 상품",
    )

    snapshot_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="스냅샷 기준일",
        help_text="한국 시간 기준 수집 날짜",
    )

    observed_at = models.DateTimeField(
        db_index=True,
        verbose_name="최종 관측일시",
        help_text="해당 날짜에 마지막으로 수집된 데이터의 관측 시각",
    )

    listing_count = models.IntegerField(null=True, blank=True, verbose_name="등록 수")
    available_count = models.IntegerField(null=True, blank=True, verbose_name="판매 가능 수")
    sold_count = models.BigIntegerField(null=True, blank=True, verbose_name="판매 수")

    min_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="최저가")
    max_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="최고가")
    avg_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="평균가")
    median_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="중앙값")

    lowest_ask = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="최저 판매 호가")
    highest_bid = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="최고 구매 호가")
    last_trade_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="최근 거래가")
    trade_volume = models.BigIntegerField(null=True, blank=True, verbose_name="거래량")

    resale_price_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="리셀 가격 비율",
        help_text="최근 거래가 / 검증된 발매가",
    )

    resale_index = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="리셀 지수",
        help_text="FEEDIT 분석 파이프라인에서 산출하는 지표",
    )

    market_metrics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 시장 지표",
        help_text="사이즈별 가격 요약, 표본 통계, 수집 범위 및 플랫폼별 추가 시장 지표",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일시")

    class Meta:
        db_table = '"snapshot"."resale_snapshot"'
        verbose_name = "리셀 스냅샷"
        verbose_name_plural = "리셀 스냅샷"

        constraints = [
            models.UniqueConstraint(
                fields=["product_source", "snapshot_date"],
                name="uq_resale_daily",
            ),
        ]

        indexes = [
            models.Index(
                fields=["-snapshot_date", "-resale_index"],
                name="idx_resale_date_index",
            ),
            models.Index(
                fields=["product_source", "-snapshot_date"],
                name="idx_resale_prod_date",
            ),
        ]

        ordering = ["-snapshot_date", "-observed_at"]

    def __str__(self):
        return (
            f"{self.product_source} / "
            f"{self.snapshot_date} / "
            f"{self.observed_at}"
        )


class ProductTerm(models.Model):

    class RelationType(models.TextChoices):
        """
        ProductSource와 DictionaryTerm 사이의 관계 유형.

        DictionaryTerm.term_type:
            해당 용어 자체의 사전 분류

        ProductTerm.relation_type:
            해당 용어가 이 상품에서 어떤 역할로 사용됐는지
        """

        # 상품
        HAS_ITEM = "HAS_ITEM", "아이템"

        # 기본 속성
        HAS_MATERIAL = "HAS_MATERIAL", "소재"
        HAS_COLOR = "HAS_COLOR", "색상"

        # 형태 / 디자인
        HAS_FIT = "HAS_FIT", "핏"
        HAS_SILHOUETTE = "HAS_SILHOUETTE", "실루엣"
        HAS_NECKLINE = "HAS_NECKLINE", "넥라인"
        HAS_SLEEVE = "HAS_SLEEVE", "소매"
        HAS_LENGTH = "HAS_LENGTH", "기장"
        HAS_SHAPE = "HAS_SHAPE", "형태"
        HAS_DETAIL = "HAS_DETAIL", "디테일"

        # 스타일 / 착용 맥락
        HAS_STYLE = "HAS_STYLE", "스타일"
        HAS_TPO = "HAS_TPO", "TPO"

    product_source = models.ForeignKey(
        "core.ProductSource",
        on_delete=models.CASCADE,
        related_name="product_terms",
        verbose_name="소스 상품",
        null=True,
        blank=True,
    )

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="product_terms",
        verbose_name="상품 특성",
    )

    relation_type = models.CharField(
        max_length=32,
        choices=RelationType.choices,
        db_index=True,
        null=True,
        blank=True,
        verbose_name="관계 유형",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    class Meta:
        db_table = '"commerce"."product_term"'

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "product_source",
                    "term",
                    "relation_type",
                ],
                name="uq_prodsrc_term_relation",
            ),
        ]

        indexes = [
            # 특정 상품에 연결된 모든 term 조회
            models.Index(
                fields=[
                    "product_source",
                ],
                name="idx_prod_term_source",
            ),

            # 관계별 term 집계 / 검색
            # 예: HAS_STYLE + 발레코어
            models.Index(
                fields=[
                    "relation_type",
                    "term",
                ],
                name="idx_prod_term_relation",
            ),
        ]

        verbose_name = "상품 특성 관계"
        verbose_name_plural = "상품 특성 관계"

    def __str__(self):
        return (
            f"{self.product_source_id} / "
            f"{self.relation_type} / "
            f"{self.term.term_code}"
        )

class ProductReview(models.Model):

    product_source = models.ForeignKey(
        "core.ProductSource",
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    source_review_id = models.CharField(
        max_length=100,
    )

    review_type = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )

    content = models.TextField()

    grade = models.IntegerField(
        null=True,
        blank=True,
    )

    goods_option = models.CharField(
        max_length=200,
        blank=True,
        default="",
    )

    like_count = models.IntegerField(
        default=0,
    )

    reviewer_sex = models.CharField(
        max_length=20,
        blank=True,
        default="",
    )

    reviewer_height = models.IntegerField(
        null=True,
        blank=True,
    )

    reviewer_weight = models.IntegerField(
        null=True,
        blank=True,
    )

    survey = models.JSONField(
        default=dict,
        blank=True,
    )

    source_created_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = '"commerce"."product_review"'

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "product_source",
                    "source_review_id",
                ],
                name="uq_product_review_source_review",
            ),
        ]


class ProductTermRelation(models.Model):

    class RelationType(models.TextChoices):
        HAS_ATTRIBUTE = (
            "HAS_ATTRIBUTE",
            "속성 보유",
        )
        HAS_MATERIAL = (
            "HAS_MATERIAL",
            "소재 보유",
        )
        HAS_COLOR = (
            "HAS_COLOR",
            "색상 보유",
        )
        HAS_STYLE = (
            "HAS_STYLE",
            "스타일 연관",
        )
        HAS_TPO = (
            "HAS_TPO",
            "TPO 연관",
        )
        PART_OF_SET = (
            "PART_OF_SET",
            "세트 구성",
        )
        RELATED = (
            "RELATED",
            "기타 연관",
        )

    product_source = models.ForeignKey(
        "core.ProductSource",
        on_delete=models.CASCADE,
        related_name="term_relations",
        verbose_name="소스 상품",
    )

    subject_term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="product_relation_subjects",
        verbose_name="주체 용어",
    )

    relation_type = models.CharField(
        max_length=30,
        choices=RelationType.choices,
        db_index=True,
        verbose_name="관계 유형",
    )

    object_term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="product_relation_objects",
        verbose_name="대상 용어",
    )

    evidence_text = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="근거 텍스트",
    )

    confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name="신뢰도",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    class Meta:
        db_table = '"commerce"."product_term_relation"'

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "product_source",
                    "subject_term",
                    "relation_type",
                    "object_term",
                ],
                name="uq_prod_term_relation",
            ),

            models.CheckConstraint(
                condition=~Q(
                    subject_term=F("object_term")
                ),
                name="ck_prod_term_rel_not_self",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "product_source",
                ],
                name="idx_ptr_product",
            ),
            models.Index(
                fields=[
                    "subject_term",
                    "relation_type",
                ],
                name="idx_ptr_subject_rel",
            ),
            models.Index(
                fields=[
                    "object_term",
                    "relation_type",
                ],
                name="idx_ptr_object_rel",
            ),
            models.Index(
                fields=[
                    "product_source",
                    "subject_term",
                ],
                name="idx_ptr_prod_subject",
            ),
        ]

    def __str__(self):
        return (
            f"{self.product_source_id} | "
            f"{self.subject_term.canonical_name} "
            f"-[{self.relation_type}]-> "
            f"{self.object_term.canonical_name}"
        )
