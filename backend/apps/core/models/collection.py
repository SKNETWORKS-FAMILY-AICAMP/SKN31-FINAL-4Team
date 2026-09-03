from django.db import models
from django.utils import timezone

def default_crawl_target_params():
    return {
        "limit": 100,
    }

class Source(models.Model):

    class SourceType(models.TextChoices):
        COMMERCE = "COMMERCE", "Commerce"
        CONTENT = "CONTENT", "Content"

    class CollectionMethod(models.TextChoices):
        API = "API", "API"
        JSON = "JSON", "JSON"
        HTML = "HTML", "HTML"
        BROWSER = "BROWSER", "Browser"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    code = models.CharField(
        max_length=50,
        unique=True,
    )

    name = models.CharField(
        max_length=100,
    )

    source_type = models.CharField(
        max_length=30,
        choices=SourceType.choices,
    )

    base_url = models.TextField(
        null=True,
        blank=True,
    )

    collection_method = models.CharField(
        max_length=30,
        choices=CollectionMethod.choices,
        null=True,
        blank=True,
    )

    crawl_interval_minutes = models.IntegerField(
        null=True,
        blank=True,
    )

    requests_per_minute = models.IntegerField(
        null=True,
        blank=True,
    )

    policy_version = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"collection"."source"'

    def __str__(self):
        return f"{self.code} - {self.name}"

class CrawlTarget(models.Model):

    class TargetType(models.TextChoices):
        PRODUCT = "PRODUCT", "Product"
        RANKING = "RANKING", "Ranking"
        STORE = "STORE", "Store"
        REVIEW = "REVIEW", "Review"
        CREATOR = "CREATOR", "Creator"
        VIDEO = "VIDEO", "Video"

    class CollectionMode(models.TextChoices):
        LIVE = "LIVE", "Live"
        BACKFILL = "BACKFILL", "Backfill"

    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="crawl_targets",
    )

    name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "사람이 알아보기 쉬운 타깃 이름. "
            "예: 남성 상의 전체연령 DAILY"
        ),
    )

    target_type = models.CharField(
        max_length=30,
        choices=TargetType.choices,
    )

    target_url = models.TextField(
        null=True,
        blank=True,
    )

    collection_mode = models.CharField(
        max_length=20,
        choices=CollectionMode.choices,
        default=CollectionMode.LIVE,
    )

    params = models.JSONField(
        default=default_crawl_target_params,
        blank=True,
    )

    interval_minutes = models.PositiveIntegerField(
        default=1440,
        help_text="수집 주기(분). 기본값 1440분 = 24시간",
    )

    priority = models.PositiveSmallIntegerField(
        default=5,
    )

    is_active = models.BooleanField(
        default=True,
    )

    last_crawled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    next_crawl_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"collection"."crawl_target"'

        indexes = [
            models.Index(
                fields=[
                    "source",
                    "is_active",
                ],
                name="idx_target_src_active",
            ),
            models.Index(
                fields=[
                    "collection_mode",
                    "is_active",
                ],
                name="idx_target_mode_active",
            ),
            models.Index(
                fields=[
                    "next_crawl_at",
                ],
                name="idx_target_next_crawl",
            ),
        ]

    def __str__(self):
        if self.name:
            return (
                f"{self.name} "
                f"[{self.source.code}]"
            )

        return (
            f"{self.source.code} | "
            f"{self.target_type} | "
            f"{self.collection_mode}"
        )

# ============================================================
# CRAWL RUN
# ============================================================


class CrawlRun(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"

        PARTIAL_SUCCESS = (
            "PARTIAL_SUCCESS",
            "Partial Success",
        )

        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    class RunType(models.TextChoices):
        LIVE = "LIVE", "Live"
        BACKFILL = "BACKFILL", "Backfill"
        MANUAL = "MANUAL", "Manual"

    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="crawl_runs",
    )

    crawl_target = models.ForeignKey(
        "CrawlTarget",
        on_delete=models.CASCADE,
        related_name="crawl_runs",
        null=True,
        blank=True,
        verbose_name="수집 대상",
    )


    run_type = models.CharField(
        max_length=50,
        choices=RunType.choices,
    )

    target = models.CharField(
        max_length=500,
        null=True,
        blank=True,
    )

    # BACKFILL 등의 실제 실행 파라미터 보존
    params = models.JSONField(
        default=dict,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Celery와 연결
    celery_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # 랭킹에서 상품 100개 발견 등의 용도
    discovered_count = models.BigIntegerField(
        default=0,
    )

    success_count = models.BigIntegerField(
        default=0,
    )

    failure_count = models.BigIntegerField(
        default=0,
    )

    error_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    error_message = models.TextField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = '"collection"."crawl_run"'

        indexes = [
            models.Index(
                fields=[
                    "source",
                    "-started_at",
                ],
                name="idx_crawl_run_source_started",
            ),
            models.Index(
                fields=[
                    "status",
                    "-started_at",
                ],
                name="idx_crawl_run_status_started",
            ),
            models.Index(
                fields=[
                    "crawl_target",
                    "-started_at",
                ],
                name="idx_run_target_started",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "PENDING",
                        "RUNNING",
                        "SUCCESS",
                        "PARTIAL_SUCCESS",
                        "FAILED",
                        "CANCELLED",
                    ]
                ),
                name="ck_crawl_run_status",
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(
                        discovered_count__gte=0
                    )
                    & models.Q(
                        success_count__gte=0
                    )
                    & models.Q(
                        failure_count__gte=0
                    )
                ),
                name="ck_crawl_run_counts",
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(
                        finished_at__isnull=True
                    )
                    | models.Q(
                        finished_at__gte=models.F(
                            "started_at"
                        )
                    )
                ),
                name="ck_crawl_run_time",
            ),
        ]

    def __str__(self):
        return (
            f"{self.source.code} | "
            f"{self.run_type} | "
            f"{self.status}"
        )


# ============================================================
# RAW DOCUMENT
# ============================================================


class RawDocument(models.Model):

    class NormalizationStatus(models.TextChoices):
        PENDING = "PENDING", "정규화 대기"
        PROCESSING = "PROCESSING", "정규화 중"
        SUCCESS = "SUCCESS", "성공"
        FAILED = "FAILED", "실패"

    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="raw_documents",
    )

    crawl_run = models.ForeignKey(
        "CrawlRun",
        on_delete=models.CASCADE,
        related_name="raw_documents",
        verbose_name="수집 실행",
    )

    document_type = models.CharField(
        max_length=50,
    )

    external_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    source_url = models.TextField(
        null=True,
        blank=True,
    )

    s3_bucket = models.CharField(
        max_length=255,
    )

    s3_key = models.TextField()

    content_hash = models.CharField(
        max_length=128,
        null=True,
        blank=True,
    )

    http_status = models.IntegerField(
        null=True,
        blank=True,
    )

    content_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    collected_at = models.DateTimeField(
        default=timezone.now,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    normalization_status = models.CharField(
        max_length=20,
        choices=NormalizationStatus.choices,
        default=NormalizationStatus.PENDING,
        db_index=True,
        verbose_name="정규화 상태",
    )
    normalized_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="정규화 완료일시",
    )

    normalization_error = models.TextField(
        null=True,
        blank=True,
        verbose_name="정규화 오류",
    )

    class Meta:
        db_table = '"collection"."raw_document"'

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "s3_bucket",
                    "s3_key",
                ],
                name="uq_raw_document_s3_object",
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(
                        http_status__isnull=True
                    )
                    | models.Q(
                        http_status__gte=100,
                        http_status__lte=599,
                    )
                ),
                name="ck_raw_document_http_status",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "source",
                    "external_id",
                    "document_type",
                ],
                name="idx_raw_external",
            ),
            models.Index(
                fields=[
                    "crawl_run",
                ],
                name="idx_raw_run",
            ),
            models.Index(
                fields=[
                    "content_hash",
                ],
                name="idx_raw_hash",
            ),
            models.Index(
                fields=[
                    "source",
                    "-collected_at",
                ],
                name="idx_raw_src_collected",
            ),
            models.Index(
                fields=[
                    "normalization_status",
                    "id",
                ],
                name="idx_rawdoc_norm_status",
            ),
        ]

    @property
    def s3_uri(self):
        return (
            f"s3://{self.s3_bucket}/"
            f"{self.s3_key}"
        )

    def __str__(self):
        return self.s3_uri