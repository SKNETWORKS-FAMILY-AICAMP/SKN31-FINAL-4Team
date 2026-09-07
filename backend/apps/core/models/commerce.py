from django.db import models


class Product(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"

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
        verbose_name="카테고리",
    )

    item_term = models.ForeignKey(
        "core.Item",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="아이템",
    )

    canonical_name = models.CharField(
        max_length=500,
        verbose_name="상품명",
    )

    normalized_name = models.CharField(
        max_length=500,
        verbose_name="검색용 상품명",
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
        verbose_name="상품 속성",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
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
        verbose_name = "상품"
        verbose_name_plural = "상품"

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
                fields=["item_term"],
                name="idx_product_item",
            ),
        ]

    def __str__(self):
        return self.canonical_name

class ProductSource(models.Model):
    class MarketType(models.TextChoices):
        RETAIL = "RETAIL", "일반 판매"
        RESALE = "RESALE", "리셀"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"

    class MappingStatus(models.TextChoices):
        UNMAPPED = "UNMAPPED", "표준 상품 미매핑"
        REVIEW = "REVIEW", "검토 중"
        MAPPED = "MAPPED", "표준 상품 연결 완료"
        REJECTED = "REJECTED", "제외"

    # ============================================================
    # FEEDIT 표준 상품
    # - 초기 적재 시 NULL
    # - 나중에 동일 상품 판별 후 연결
    # ============================================================

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sources",
        verbose_name="표준 상품",
    )

    # ============================================================
    # 플랫폼
    # ============================================================

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

    # ============================================================
    # 플랫폼 원본 브랜드 / 카테고리
    # ============================================================

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

    # ============================================================
    # 상품 원본 정보
    # ============================================================

    style_no = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="스타일/모델 번호",
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

    # ============================================================
    # 판매 유형 / 매핑 상태
    # ============================================================

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

    # ============================================================
    # 관측 정보
    # ============================================================

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


class ProductSourceSnapshot(models.Model):
    product_source = models.ForeignKey(
        ProductSource,
        on_delete=models.CASCADE,
        related_name="snapshots",
        verbose_name="플랫폼 상품",
    )

    observed_at = models.DateTimeField(
        verbose_name="관측일시",
    )

    # 가격
    list_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="정가",
    )

    sale_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="판매가",
    )

    discount_rate = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="할인율",
    )

    # 랭킹
    rank_position = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="순위",
    )

    ranking_scope = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="랭킹 범위",
    )

    ranking_context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="랭킹 조건",
    )

    # 반응
    rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="평점",
    )

    review_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="리뷰 수",
    )

    like_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="좋아요 수",
    )

    # 상태
    stock_status = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        verbose_name="재고 상태",
    )

    # 플랫폼별 추가 값
    platform_metrics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="플랫폼 추가 지표",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    class Meta:
        db_table = '"snapshot"."product_source_snapshot"'
        verbose_name = "상품 스냅샷"
        verbose_name_plural = "상품 스냅샷"

        constraints = [
            models.UniqueConstraint(
                fields=["product_source", "observed_at"],
                name="uq_prod_snapshot",
            ),
        ]

        indexes = [
            models.Index(
                fields=["-observed_at"],
                name="idx_prod_snap_time",
            ),
            models.Index(
                fields=["product_source", "rank_position"],
                name="idx_prod_snap_rank",
            ),
        ]

    def __str__(self):
        return f"{self.product_source} / {self.observed_at}"


class ResaleSnapshot(models.Model):
    product_source = models.ForeignKey(
        ProductSource,
        on_delete=models.CASCADE,
        related_name="resale_snapshots",
        verbose_name="리셀 상품",
    )

    observed_at = models.DateTimeField(
        verbose_name="관측일시",
    )

    listing_count = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="등록 수",
    )

    available_count = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="판매 가능 수",
    )

    min_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="최저가",
    )

    max_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="최고가",
    )

    avg_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="평균가",
    )

    median_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="중앙값",
    )

    sold_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="판매 수",
    )

    lowest_ask = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="최저 판매가",
    )

    highest_bid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="최고 구매가",
    )

    last_trade_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="최근 거래가",
    )

    trade_volume = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="거래량",
    )

    resale_price_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="리셀 가격 비율",
    )

    resale_index = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="리셀 지수",
    )

    market_metrics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 시장 지표",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    class Meta:
        db_table = '"snapshot"."resale_snapshot"'
        verbose_name = "리셀 스냅샷"
        verbose_name_plural = "리셀 스냅샷"

        constraints = [
            models.UniqueConstraint(
                fields=["product_source", "observed_at"],
                name="uq_resale_snap",
            ),
        ]

        indexes = [
            models.Index(
                fields=["-observed_at", "-resale_index"],
                name="idx_resale_index",
            ),
            models.Index(
                fields=["product_source"],
                name="idx_resale_prod",
            ),
        ]

    def __str__(self):
        return f"{self.product_source} / {self.observed_at}"



class ProductTerm(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_terms",
        verbose_name="상품",
    )

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="product_terms",
        verbose_name="상품 특성",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    class Meta:
        db_table = '"commerce"."product_term"'
        verbose_name = "상품 특성"
        verbose_name_plural = "상품 특성"

        constraints = [
            models.UniqueConstraint(
                fields=["product", "term"],
                name="uq_product_term",
            ),
        ]

    def __str__(self):
        return f"{self.product_id} / {self.term.term_code}"