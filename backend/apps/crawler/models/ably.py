from django.db import models


class AblyProduct(models.Model):

    source_product_id = models.CharField(
        max_length=200,
        unique=True,
    )

    product_name = models.TextField()

    market_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
    )

    market_name = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        db_index=True,
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
            models.Index(fields=["market_id"]),
            models.Index(fields=["market_name"]),
            models.Index(fields=["category_id"]),
            models.Index(fields=["last_seen_at"]),
        ]

    def __str__(self):
        return self.product_name


# ============================================================


class AblyProductSnapshot(models.Model):

    product = models.ForeignKey(
        AblyProduct,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )

    crawl_job = models.ForeignKey(
        "crawler.CrawlJob",
        on_delete=models.SET_NULL,
        related_name="ably_snapshots",
        blank=True,
        null=True,
    )

    crawl_target = models.ForeignKey(
        "crawler.CrawlTarget",
        on_delete=models.SET_NULL,
        related_name="ably_snapshots",
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
                name="unique_ably_product_target_observation",
            )
        ]

        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["observed_at"]),
            models.Index(fields=["rank"]),
            models.Index(fields=["product", "observed_at"]),
            models.Index(fields=["crawl_target", "observed_at"]),
        ]
