from django.db import models


class TextDocument(models.Model):
    class DocumentType(models.TextChoices):
        TRANSCRIPT = "TRANSCRIPT", "자막"
        COMMENT = "COMMENT", "댓글"
        REVIEW = "REVIEW", "리뷰"
        DESCRIPTION = "DESCRIPTION", "설명"
        ARTICLE = "ARTICLE", "본문"

    class AnalysisStatus(models.TextChoices):
        PENDING = "PENDING", "대기"
        PROCESSING = "PROCESSING", "분석 중"
        DONE = "DONE", "완료"
        FAILED = "FAILED", "실패"

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.PROTECT,
        related_name="text_documents",
        verbose_name="플랫폼",
    )

    content_item = models.ForeignKey(
        "core.ContentItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="text_documents",
        verbose_name="콘텐츠",
    )

    document_type = models.CharField(
        max_length=30,
        choices=DocumentType.choices,
        verbose_name="문서 유형",
    )

    external_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="플랫폼 문서 ID",
    )

    body = models.TextField(
        verbose_name="분석 텍스트",
    )

    language = models.CharField(
        max_length=10,
        default="ko",
        verbose_name="언어",
    )

    sentiment_score = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="감성 점수",
    )

    intent_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="의도 코드",
    )

    # 상세 분석 결과
    extracted_terms = models.JSONField(
        default=list,
        blank=True,
        verbose_name="추출 용어",
    )

    analysis_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="분석 추가 정보",
    )

    analysis_status = models.CharField(
        max_length=20,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
        verbose_name="분석 상태",
    )

    analyzed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="분석일시",
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
        db_table = '"analysis"."text_document"'
        verbose_name = "분석 문서"
        verbose_name_plural = "분석 문서"

        indexes = [
            models.Index(
                fields=["content_item", "document_type"],
                name="idx_text_doc_content",
            ),
            models.Index(
                fields=["analysis_status"],
                name="idx_text_doc_status",
            ),
            models.Index(
                fields=["-created_at"],
                name="idx_text_doc_created",
            ),
        ]

    def __str__(self):
        if self.content_item:
            return f"{self.get_document_type_display()} / {self.content_item}"

        return f"{self.get_document_type_display()} / {self.id}"


class TermMetricDaily(models.Model):
    """
    용어별 하루 단위 트렌드 지표.
    """

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="daily_metrics",
        verbose_name="용어",
    )

    metric_date = models.DateField(
        verbose_name="기준일",
    )

    mention_count = models.BigIntegerField(
        default=0,
        verbose_name="언급 수",
    )

    document_count = models.BigIntegerField(
        default=0,
        verbose_name="문서 수",
    )

    source_count = models.IntegerField(
        default=0,
        verbose_name="플랫폼 수",
    )

    sentiment_avg = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="평균 감성",
    )

    growth_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="증가율",
    )

    trend_score = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="트렌드 점수",
    )

    metrics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 지표",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"analysis"."term_metric_daily"'
        verbose_name = "용어 일별 지표"
        verbose_name_plural = "용어 일별 지표"

        constraints = [
            models.UniqueConstraint(
                fields=["term", "metric_date"],
                name="uq_term_metric_day",
            ),
        ]

        indexes = [
            models.Index(
                fields=["metric_date", "-trend_score"],
                name="idx_term_metric_trend",
            ),
            models.Index(
                fields=["term", "-metric_date"],
                name="idx_term_metric_term",
            ),
        ]

    def __str__(self):
        return f"{self.term} / {self.metric_date}"


class TermAssocDaily(models.Model):
    """
    용어 ↔ 용어 일별 연관도.
    """

    source_term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="daily_assoc_sources",
        verbose_name="기준 용어",
    )

    target_term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="daily_assoc_targets",
        verbose_name="연관 용어",
    )

    metric_date = models.DateField(
        verbose_name="기준일",
    )

    cooccurrence_count = models.BigIntegerField(
        default=0,
        verbose_name="동시 언급 수",
    )

    association_score = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="연관도",
    )

    confidence = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="신뢰도",
    )

    metrics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 지표",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"analysis"."term_assoc_daily"'
        verbose_name = "용어 일별 연관"
        verbose_name_plural = "용어 일별 연관"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source_term",
                    "target_term",
                    "metric_date",
                ],
                name="uq_term_assoc_day",
            ),
            models.CheckConstraint(
                condition=~models.Q(
                    source_term=models.F("target_term")
                ),
                name="ck_term_assoc_self",
            ),
        ]

        indexes = [
            models.Index(
                fields=["source_term", "-metric_date"],
                name="idx_assoc_src_day",
            ),
            models.Index(
                fields=["metric_date", "-association_score"],
                name="idx_assoc_score",
            ),
        ]

    def __str__(self):
        return (
            f"{self.source_term} ↔ "
            f"{self.target_term} / "
            f"{self.metric_date}"
        )