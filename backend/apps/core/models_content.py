from django.db import models


class ContentProfile(models.Model):
    """
    유튜브 채널, 인스타 계정 등
    콘텐츠를 발행하는 플랫폼 프로필.
    """

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.PROTECT,
        related_name="content_profiles",
        verbose_name="플랫폼",
    )

    external_profile_id = models.CharField(
        max_length=255,
        verbose_name="플랫폼 프로필 ID",
    )

    profile_type = models.CharField(
        max_length=30,
        verbose_name="프로필 유형",
    )

    name = models.CharField(
        max_length=300,
        verbose_name="프로필명",
    )

    handle = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name="핸들",
    )

    profile_url = models.TextField(
        null=True,
        blank=True,
        verbose_name="프로필 URL",
    )

    profile_image_url = models.TextField(
        null=True,
        blank=True,
        verbose_name="프로필 이미지",
    )

    description = models.TextField(
        null=True,
        blank=True,
        verbose_name="설명",
    )

    platform_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="플랫폼 추가 정보",
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

    status = models.CharField(
        max_length=20,
        default="ACTIVE",
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
        db_table = '"content"."content_profile"'
        verbose_name = "콘텐츠 프로필"
        verbose_name_plural = "콘텐츠 프로필"

        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_profile_id"],
                name="uq_content_profile",
            ),
        ]

        indexes = [
            models.Index(
                fields=["source", "name"],
                name="idx_content_prof_src",
            ),
            models.Index(
                fields=["profile_type"],
                name="idx_content_prof_type",
            ),
        ]

    def __str__(self):
        return self.name


class ContentItem(models.Model):
    class ContentType(models.TextChoices):
        VIDEO = "VIDEO", "영상"
        SHORTS = "SHORTS", "쇼츠"
        POST = "POST", "게시글"
        ARTICLE = "ARTICLE", "기사"

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.PROTECT,
        related_name="content_items",
        verbose_name="플랫폼",
    )

    profile = models.ForeignKey(
        "core.ContentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contents",
        verbose_name="프로필",
    )

    external_content_id = models.CharField(
        max_length=255,
        verbose_name="플랫폼 콘텐츠 ID",
    )

    content_type = models.CharField(
        max_length=30,
        choices=ContentType.choices,
        verbose_name="콘텐츠 유형",
    )

    title = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="제목",
    )

    description = models.TextField(
        null=True,
        blank=True,
        verbose_name="설명",
    )

    content_url = models.TextField(
        verbose_name="콘텐츠 URL",
    )

    thumbnail_url = models.TextField(
        null=True,
        blank=True,
        verbose_name="썸네일",
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="게시일시",
    )

    duration_seconds = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="재생시간(초)",
    )

    # 분석 결과 요약
    analysis_tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name="분석 태그",
    )

    analysis_status = models.CharField(
        max_length=20,
        default="PENDING",
        verbose_name="분석 상태",
    )

    platform_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="플랫폼 추가 정보",
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"content"."content_item"'
        verbose_name = "콘텐츠"
        verbose_name_plural = "콘텐츠"

        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_content_id"],
                name="uq_content_item",
            ),
        ]

    def __str__(self):
        return self.title or self.external_content_id

class ContentSnapshot(models.Model):
    """
    조회수, 좋아요, 댓글 등
    시간에 따라 변하는 콘텐츠 지표.
    """

    content_item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="snapshots",
        verbose_name="콘텐츠",
    )

    observed_at = models.DateTimeField(
        verbose_name="관측일시",
    )

    view_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="조회수",
    )

    like_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="좋아요 수",
    )

    comment_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="댓글 수",
    )

    share_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="공유 수",
    )

    save_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="저장 수",
    )

    engagement_count = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="반응 수",
    )

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
        db_table = '"snapshot"."content_snapshot"'
        verbose_name = "콘텐츠 스냅샷"
        verbose_name_plural = "콘텐츠 스냅샷"

        constraints = [
            models.UniqueConstraint(
                fields=["content_item", "observed_at"],
                name="uq_content_snapshot",
            ),
        ]

        indexes = [
            models.Index(
                fields=["-observed_at"],
                name="idx_content_snap_time",
            ),
            models.Index(
                fields=["content_item"],
                name="idx_content_snap_item",
            ),
        ]

    def __str__(self):
        return f"{self.content_item} / {self.observed_at}"