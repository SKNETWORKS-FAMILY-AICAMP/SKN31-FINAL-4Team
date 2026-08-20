from django.db import models


class YoutubeCreator(models.Model):
    """
    패션 크리에이터 / 채널
    """

    channel_id = models.CharField(
        max_length=200,
        unique=True,
    )

    channel_name = models.CharField(
        max_length=300,
        db_index=True,
    )

    channel_url = models.TextField(
        blank=True,
        null=True,
    )

    profile_image_url = models.TextField(
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    uploads_playlist_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        db_index=True,
    )

    first_seen_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    last_seen_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    last_video_id = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )

    last_checked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.channel_name


class YoutubeContent(models.Model):
    """
    YouTube 영상 자체

    조회수, 좋아요 수처럼 계속 변하는 값은
    YoutubeContentMetric에 저장
    """

    class ContentType(models.TextChoices):
        VIDEO = "VIDEO", "일반 영상"
        SHORTS = "SHORTS", "Shorts"

    creator = models.ForeignKey(
        YoutubeCreator,
        on_delete=models.CASCADE,
        related_name="contents",
    )

    video_id = models.CharField(
        max_length=200,
        unique=True,
    )

    content_type = models.CharField(
        max_length=30,
        choices=ContentType.choices,
        default=ContentType.VIDEO,
    )

    title = models.TextField()

    description = models.TextField(
        blank=True,
        null=True,
    )

    content_url = models.TextField()

    thumbnail_url = models.TextField(
        blank=True,
        null=True,
    )

    duration_seconds = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    published_at = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
    )

    first_seen_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    last_seen_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["creator"]),
            models.Index(fields=["published_at"]),
            models.Index(fields=["content_type"]),
        ]

    def __str__(self):
        return self.title


# ============================================================


class YoutubeContentMetric(models.Model):
    """
    YouTube 콘텐츠의 시간별 지표

    예:
    12:00 조회수 10만
    18:00 조회수 15만
    """

    content = models.ForeignKey(
        YoutubeContent,
        on_delete=models.CASCADE,
        related_name="metrics",
    )

    crawl_job = models.ForeignKey(
        "crawler.CrawlJob",
        on_delete=models.SET_NULL,
        related_name="youtube_metrics",
        blank=True,
        null=True,
    )

    view_count = models.BigIntegerField(
        blank=True,
        null=True,
    )

    like_count = models.BigIntegerField(
        blank=True,
        null=True,
    )

    comment_count = models.BigIntegerField(
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
                fields=["content", "observed_at"],
                name="unique_youtube_content_observation",
            )
        ]

        indexes = [
            models.Index(fields=["content"]),
            models.Index(fields=["observed_at"]),
            models.Index(fields=["content", "observed_at"]),
        ]


# ============================================================


class YoutubeTranscript(models.Model):
    """
    YouTube 자막 / STT 결과

    이후 LLM이 여기 있는 텍스트를 분석해서
    트렌드, 아이템, 컬러, 브랜드 등의 Mention을 추출
    """

    class TranscriptType(models.TextChoices):
        AUTO = "AUTO", "자동 자막"
        MANUAL = "MANUAL", "수동 자막"
        STT = "STT", "음성 인식"

    content = models.ForeignKey(
        YoutubeContent,
        on_delete=models.CASCADE,
        related_name="transcripts",
    )

    language = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    transcript_type = models.CharField(
        max_length=30,
        choices=TranscriptType.choices,
        blank=True,
        null=True,
    )

    full_text = models.TextField()

    source = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    collected_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["content"]),
            models.Index(fields=["language"]),
        ]

    def __str__(self):
        return f"{self.content.title} - {self.language or 'unknown'}"
