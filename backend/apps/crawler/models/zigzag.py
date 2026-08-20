from django.db import models


class ZigzagStore(models.Model):
    """
    지그재그 스토어(=사실상 브랜드) 정보.

    지그재그 API에는 별도 '브랜드' 개체가 없고, 상품 카드가 내려주는
    shop_id/shop_name/is_brand가 그 역할을 겸함. 상품마다 이름을 중복
    저장하지 않도록 여기서 한 번만 저장하고 ZigzagProduct는 FK로 참조.
    """

    source_store_id = models.CharField(
        max_length=200,
        unique=True,
    )

    store_name = models.CharField(
        max_length=300,
        db_index=True,
    )

    # 지그재그 API의 is_brand 플래그 — 셀러형 스토어와 브랜드관을 구분
    is_brand = models.BooleanField(
        default=False,
    )

    first_seen_at = models.DateTimeField()

    last_seen_at = models.DateTimeField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["store_name"]),
            models.Index(fields=["is_brand"]),
        ]

    def __str__(self):
        return self.store_name


class ZigzagProduct(models.Model):

    source_product_id = models.CharField(
        max_length=200,
        unique=True,
    )

    product_name = models.TextField()

    store = models.ForeignKey(
        ZigzagStore,
        on_delete=models.SET_NULL,
        related_name="products",
        blank=True,
        null=True,
    )

    category_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
    )

    category_name = models.TextField(
        blank=True,
        null=True,
    )

    product_url = models.TextField()

    thumbnail_url = models.TextField(
        blank=True,
        null=True,
    )

    first_seen_at = models.DateTimeField()

    last_seen_at = models.DateTimeField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["store"]),
            models.Index(fields=["category_id"]),
            models.Index(fields=["last_seen_at"]),
        ]

    def __str__(self):
        return self.product_name


class ZigzagProductSnapshot(models.Model):

    product = models.ForeignKey(
        ZigzagProduct,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )

    crawl_job = models.ForeignKey(
        "crawler.CrawlJob",
        on_delete=models.SET_NULL,
        related_name="zigzag_snapshots",
        blank=True,
        null=True,
    )

    crawl_target = models.ForeignKey(
        "crawler.CrawlTarget",
        on_delete=models.SET_NULL,
        related_name="zigzag_snapshots",
        blank=True,
        null=True,
    )

    regular_price = models.BigIntegerField(
        blank=True,
        null=True,
    )

    sale_price = models.BigIntegerField(
        blank=True,
        null=True,
    )

    discount_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
    )

    rank = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    review_count = models.BigIntegerField(
        blank=True,
        null=True,
    )

    like_count = models.BigIntegerField(
        blank=True,
        null=True,
    )

    availability = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    observed_at = models.DateTimeField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "crawl_target", "observed_at"],
                name="unique_zigzag_product_target_observation",
            )
        ]

        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["observed_at"]),
            models.Index(fields=["rank"]),
            models.Index(fields=["product", "observed_at"]),
            models.Index(fields=["crawl_target", "observed_at"]),
        ]

    def __str__(self):
        return f"{self.product_id} @ {self.observed_at:%Y-%m-%d %H:%M}"
