from django.db import models
from django.utils import timezone


# ============================================================
# SOURCE
# ============================================================


class Source(models.Model):
    """
    외부 데이터 소스 마스터.

    예:
    - MUSINSA
    - ZIGZAG
    - ABLY
    - KREAM
    - YOUTUBE
    """

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
        default=dict,
        blank=True,
    )

    interval_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
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
    """
    실제 수집 실행 이력.

    CrawlTarget = 무엇을 수집할지
    CrawlRun    = 실제 한 번의 실행

    예:
        MUSINSA 여성 아우터 DAILY target

        09/01 → SUCCESS
        09/02 → SUCCESS
        09/03 → FAILED

    각각 별도의 CrawlRun으로 남는다.
    """

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
        CrawlTarget,
        on_delete=models.SET_NULL,
        related_name="crawl_runs",
        null=True,
        blank=True,
    )

    run_type = models.CharField(
        max_length=50,
        choices=RunType.choices,
    )

    # 실제 실행 대상 문자열
    #
    # URL 또는:
    # "2025-01/F/002"
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
    """
    S3 RAW 객체에 대한 DB pointer.

    JSON 원문 자체는 RDS에 저장하지 않는다.

    실제 데이터:
        S3

    RDS:
        S3 bucket/key
        source
        external_id
        hash
        collected_at
        crawl_run
    """

    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="raw_documents",
    )

    crawl_run = models.ForeignKey(
        CrawlRun,
        on_delete=models.SET_NULL,
        related_name="raw_documents",
        null=True,
        blank=True,
    )

    # PRODUCT / RANKING / REVIEW / STORE / VIDEO ...
    document_type = models.CharField(
        max_length=50,
    )

    # 플랫폼 원본 식별자
    #
    # KREAM:
    # 842180
    #
    # MUSINSA:
    # goodsNo
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
        ]

    @property
    def s3_uri(self):
        return (
            f"s3://{self.s3_bucket}/"
            f"{self.s3_key}"
        )

    def __str__(self):
        return self.s3_uri