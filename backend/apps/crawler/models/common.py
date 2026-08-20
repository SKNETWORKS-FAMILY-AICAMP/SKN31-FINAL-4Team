from django.db import models


# 수집 출처
class Source(models.Model):

    class SourceType(models.TextChoices):
        MARKETPLACE = "MARKETPLACE", "쇼핑플랫폼"
        CONTENT = "CONTENT", "콘텐츠"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "활성"
        INACTIVE = "INACTIVE", "비활성"
        REVIEW = "REVIEW", "검토중"
        BLOCKED = "BLOCKED", "차단"

    class CollectionMethod(models.TextChoices):
        API = "API", "API"
        HTML = "HTML", "HTML"
        JSON = "JSON", "JSON"
        BROWSER = "BROWSER", "Browser"

    class RobotsStatus(models.TextChoices):
        UNKNOWN = "UNKNOWN", "미확인"
        ALLOWED = "ALLOWED", "허용"
        DISALLOWED = "DISALLOWED", "비허용"
        ERROR = "ERROR", "확인실패"

    # --------------------------------------------------------
    # 기본 정보
    code = models.CharField(
        max_length=30,
        unique=True,
    )

    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REVIEW,
    )

    base_url = models.TextField(
        blank=True,
        null=True,
    )

    collection_method = models.CharField(
        max_length=20,
        choices=CollectionMethod.choices,
    )

    # --------------------------------------------------------
    # 수집 설정
    crawl_interval_minutes = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    requests_per_minute = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # robots.txt
    robots_url = models.TextField(
        blank=True,
        null=True,
    )

    robots_status = models.CharField(
        max_length=20,
        choices=RobotsStatus.choices,
        default=RobotsStatus.UNKNOWN,
    )

    robots_txt = models.TextField(
        blank=True,
        null=True,
    )

    robots_checked_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # 정책
    policy_version = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # 생성/수정
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.code


# 실제 크롤링 대상 -----
class CrawlTarget(models.Model):
    """
    실제 크롤링 대상

    예:
    MUSINSA
        - 여성 상의 랭킹
        - 신발 랭킹

    YOUTUBE
        - 특정 패션 크리에이터 채널
    """

    class TargetType(models.TextChoices):
        CATEGORY = "CATEGORY", "카테고리"
        RANKING = "RANKING", "랭킹"
        CHANNEL = "CHANNEL", "채널"
        KEYWORD = "KEYWORD", "키워드"
        OTHER = "OTHER", "기타"

    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="crawl_targets",
    )

    target_type = models.CharField(
        max_length=30,
        choices=TargetType.choices,
    )

    target_value = models.CharField(
        max_length=500,
    )

    display_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["source", "is_active"]),
        ]

    def __str__(self):
        return self.display_name or f"{self.source.code}:{self.target_value}"


class CrawlJob(models.Model):
    """
    실제 크롤러 실행 1회를 기록

    예:
    2026-08-17 12:00
    MUSINSA 여성 상의 랭킹 크롤링
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "대기"
        RUNNING = "RUNNING", "진행중"
        SUCCESS = "SUCCESS", "성공"
        FAILED = "FAILED", "실패"

    class TriggerType(models.TextChoices):
        SCHEDULED = "SCHEDULED", "스케줄"
        MANUAL = "MANUAL", "수동"
        RETRY = "RETRY", "재시도"
        BACKFILL = "BACKFILL", "과거 데이터 수집"

    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="crawl_jobs",
    )

    crawl_target = models.ForeignKey(
        CrawlTarget,
        on_delete=models.SET_NULL,
        related_name="crawl_jobs",
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    trigger_type = models.CharField(
        max_length=20,
        choices=TriggerType.choices,
        blank=True,
        null=True,
    )

    # Celery가 생성하는 Task ID
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
    )

    scheduled_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    started_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    finished_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    items_found = models.PositiveIntegerField(
        default=0,
    )

    items_created = models.PositiveIntegerField(
        default=0,
    )

    items_updated = models.PositiveIntegerField(
        default=0,
    )

    attempt = models.PositiveIntegerField(
        default=1,
    )

    error_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    error_message = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["crawl_target"]),
            models.Index(fields=["status"]),
            models.Index(fields=["started_at"]),
            models.Index(fields=["source", "started_at"]),
        ]

    def __str__(self):
        return f"{self.source.code} #{self.pk} - {self.status}"


# ============================================================
class RawObject(models.Model):
    """
    크롤링한 원본 데이터 위치 기록

    실제 HTML / JSON 전체를 DB에 넣기보다는
    S3 등에 저장하고 storage_key만 관리
    """

    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="raw_objects",
    )

    crawl_target = models.ForeignKey(
        CrawlTarget,
        on_delete=models.SET_NULL,
        related_name="raw_objects",
        blank=True,
        null=True,
    )

    crawl_job = models.ForeignKey(
        CrawlJob,
        on_delete=models.CASCADE,
        related_name="raw_objects",
    )

    request_url = models.TextField(
        blank=True,
        null=True,
    )

    storage_key = models.TextField()

    content_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    http_status = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    checksum = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
    )

    parser_version = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    collected_at = models.DateTimeField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["crawl_job"]),
            models.Index(fields=["collected_at"]),
        ]

    def __str__(self):
        return f"RawObject #{self.pk} - {self.source.code}"

    # ============================================================


class BackfillBatch(models.Model):
    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="backfill_batches",
    )

    status = models.CharField(...)

    start_date = models.DateField()
    end_date = models.DateField()

    params = models.JSONField(
        default=dict,
        blank=True,
    )

    total_items = models.PositiveIntegerField(default=0)
    success_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class BackfillItem(models.Model):
    batch = models.ForeignKey(
        BackfillBatch,
        on_delete=models.CASCADE,
        related_name="items",
    )

    crawl_job = models.OneToOneField(
        CrawlJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backfill_item",
    )

    target_key = models.CharField(
        max_length=255,
    )

    params = models.JSONField(
        default=dict,
        blank=True,
    )

    request_url = models.TextField(
        blank=True,
        null=True,
    )

    status = models.CharField(...)

    items_found = models.PositiveIntegerField(default=0)
    items_created = models.PositiveIntegerField(default=0)
    items_updated = models.PositiveIntegerField(default=0)

    celery_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    error_type = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    error_message = models.TextField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
