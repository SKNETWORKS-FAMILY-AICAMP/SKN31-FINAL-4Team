from django.db import models
from django.utils import timezone


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

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"collection"."source"'

    def __str__(self):
        return f"{self.code} - {self.name}"

class CrawlRun(models.Model):

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        PARTIAL_SUCCESS = "PARTIAL_SUCCESS", "Partial Success"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="crawl_runs",
    )

    run_type = models.CharField(max_length=50)

    target = models.CharField(
        max_length=500,
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )

    started_at = models.DateTimeField()

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    success_count = models.BigIntegerField(default=0)
    failure_count = models.BigIntegerField(default=0)

    error_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    error_message = models.TextField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"collection"."crawl_run"'

        indexes = [
            models.Index(
                fields=["source", "-started_at"],
                name="idx_crawl_run_source_started",
            ),
            models.Index(
                fields=["status", "-started_at"],
                name="idx_crawl_run_status_started",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
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
                    models.Q(success_count__gte=0)
                    & models.Q(failure_count__gte=0)
                ),
                name="ck_crawl_run_counts",
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(finished_at__isnull=True)
                    | models.Q(
                        finished_at__gte=models.F("started_at")
                    )
                ),
                name="ck_crawl_run_time",
            ),
        ]

    def __str__(self):
        return f"{self.source.code} | {self.run_type} | {self.status}"


class RawDocument(models.Model):

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

    document_type = models.CharField(max_length=50)

    external_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    source_url = models.TextField(
        null=True,
        blank=True,
    )

    s3_bucket = models.CharField(max_length=255)
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

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"collection"."raw_document"'

        constraints = [
            models.UniqueConstraint(
                fields=["s3_bucket", "s3_key"],
                name="uq_raw_document_s3_object",
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(http_status__isnull=True)
                    | models.Q(http_status__gte=100, http_status__lte=599)
                ),
                name="ck_raw_document_http_status",
            ),
        ]

        indexes = [
            models.Index(
                fields=["source", "external_id", "document_type"],
                name="idx_raw_external",
            ),
            models.Index(
                fields=["crawl_run"],
                name="idx_raw_run",
            ),
            models.Index(
                fields=["content_hash"],
                name="idx_raw_hash",
            ),
            models.Index(
                fields=["source", "-collected_at"],
                name="idx_raw_src_collected",
            ),
        ]

    def __str__(self):
        return f"s3://{self.s3_bucket}/{self.s3_key}"


from .models_dictionary import *
from .models_commerce import *
from .models_content import *
from .models_analysis import *
from .models_app import *