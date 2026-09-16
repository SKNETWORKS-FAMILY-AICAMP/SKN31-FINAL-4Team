from django.db import models

class TextDocument(models.Model):
    """
    분석 가능한 원본 텍스트 단위.

    예:
    - YouTube 자막
    - YouTube 댓글
    - 상품 리뷰
    - 콘텐츠 설명
    - 기사 본문

    분석 결과(term/sentiment/intent)는 이 테이블에 직접 저장하지 않고
    TextTermMention에 저장한다.
    """

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

    analysis_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="분석 메타데이터",
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
                fields=["source", "document_type"],
                name="idx_text_doc_source_type",
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
            return (
                f"{self.get_document_type_display()} / "
                f"{self.content_item}"
            )

        return f"{self.get_document_type_display()} / {self.id}"


# ============================================================
# TEXT TERM MENTION
# ============================================================

class TextTermMention(models.Model):
    """
    TextDocument 안에서 DictionaryTerm이 실제 언급된 사실.

    지표의 가장 중요한 Evidence Layer.

    예:
    document = 유튜브 자막
    term = 스웨이드
    mention_text = "올가을 스웨이드 자켓이..."
    """

    class MentionRole(models.TextChoices):
        TARGET = "TARGET", "주요 대상"
        CONTEXT = "CONTEXT", "문맥 언급"
        COMPARISON = "COMPARISON", "비교 대상"

    document = models.ForeignKey(
        "TextDocument",
        on_delete=models.CASCADE,
        related_name="term_mentions",
        verbose_name="분석 문서",
    )

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="text_mentions",
        verbose_name="용어",
    )

    mention_text = models.TextField(
        null=True,
        blank=True,
        verbose_name="언급 문맥",
    )

    mention_role = models.CharField(
        max_length=20,
        choices=MentionRole.choices,
        default=MentionRole.CONTEXT,
        verbose_name="언급 역할",
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
        verbose_name="구매 의도",
    )

    confidence = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="추출 신뢰도",
    )

    start_seconds = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="시작 시점",
    )

    end_seconds = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="종료 시점",
    )

    analysis_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 분석 정보",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    class Meta:
        db_table = '"analysis"."text_term_mention"'
        verbose_name = "텍스트 용어 언급"
        verbose_name_plural = "텍스트 용어 언급"

        indexes = [
            models.Index(
                fields=["document", "term"],
                name="idx_mention_doc_term",
            ),
            models.Index(
                fields=["term"],
                name="idx_mention_term",
            ),
            models.Index(
                fields=["term", "mention_role"],
                name="idx_mention_term_role",
            ),
        ]

    def __str__(self):
        return f"{self.term} / {self.document_id}"

class TermMetricDaily(models.Model):
    """
    용어별 일 단위 지표.

    source가 존재하면 플랫폼별 metric.
    source=NULL이면 전체 플랫폼을 합친 종합 metric.

    예:
    스웨이드 / 2026-09-14 / YouTube
    스웨이드 / 2026-09-14 / NULL(ALL)
    """

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="daily_metrics",
        verbose_name="용어",
    )

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="term_daily_metrics",
        verbose_name="플랫폼",
    )

    metric_date = models.DateField(
        verbose_name="기준일",
    )

    # --------------------------------------------------------
    # RAW
    # --------------------------------------------------------

    raw_count = models.DecimalField(
        max_digits=16,
        decimal_places=4,
        default=0,
        verbose_name="원시 신호",
    )

    mention_count = models.BigIntegerField(
        default=0,
        verbose_name="언급 수",
    )

    document_count = models.BigIntegerField(
        default=0,
        verbose_name="문서 수",
    )

    content_count = models.BigIntegerField(
        default=0,
        verbose_name="콘텐츠 수",
    )

    creator_count = models.BigIntegerField(
        default=0,
        verbose_name="크리에이터 수",
    )

    # --------------------------------------------------------
    # NORMALIZED
    # --------------------------------------------------------

    log_count = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="로그 보정값",
    )

    percentile = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="플랫폼 내 백분위",
    )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    level = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="화제성 레벨",
    )

    ma7 = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="7일 이동평균",
    )

    ma28 = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="28일 이동평균",
    )

    momentum = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="성장 모멘텀",
    )

    trend_temperature = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="트렌드 온도",
    )

    sentiment_avg = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name="평균 감성",
    )

    # ========================================================
    # POLARITY RAW
    # ========================================================

    positive_count = models.BigIntegerField(
        default=0,
        verbose_name="긍정 반응 수",
    )

    neutral_count = models.BigIntegerField(
        default=0,
        verbose_name="중립 반응 수",
    )

    negative_count = models.BigIntegerField(
        default=0,
        verbose_name="부정 반응 수",
    )

    # ========================================================
    # INTENT RAW
    # ========================================================

    question_count = models.BigIntegerField(
        default=0,
        verbose_name="질문 반응 수",
    )

    purchase_count = models.BigIntegerField(
        default=0,
        verbose_name="구매 반응 수",
    )

    experience_count = models.BigIntegerField(
        default=0,
        verbose_name="경험 반응 수",
    )

    praise_count = models.BigIntegerField(
        default=0,
        verbose_name="호평 반응 수",
    )

    critique_count = models.BigIntegerField(
        default=0,
        verbose_name="비판 반응 수",
    )

    chitchat_count = models.BigIntegerField(
        default=0,
        verbose_name="잡담 반응 수",
    )

    # ========================================================
    # POLARITY RATE
    # 0 ~ 100 (%)
    # ========================================================

    positive_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="긍정 반응 비율",
    )

    neutral_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="중립 반응 비율",
    )

    negative_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="부정 반응 비율",
    )

    # ========================================================
    # INTENT RATE
    # 0 ~ 100 (%)
    # ========================================================

    question_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="질문 반응 비율",
    )

    purchase_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="구매 반응 비율",
    )

    experience_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="경험 반응 비율",
    )

    praise_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="호평 반응 비율",
    )

    critique_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="비판 반응 비율",
    )

    # ========================================================
    # DERIVED
    # ========================================================

    purchase_intent_index = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="구매의도 지수",
    )
    # --------------------------------------------------------
    # VERSION / META
    # --------------------------------------------------------

    metric_version = models.CharField(
        max_length=50,
        default="feedit-l2-v1",
        verbose_name="지표 버전",
    )

    metrics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 지표",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"analysis"."term_metric_daily"'
        verbose_name = "용어 일별 지표"
        verbose_name_plural = "용어 일별 지표"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "term",
                    "source",
                    "metric_date",
                    "metric_version",
                ],
                name="uq_term_metric_source_day_ver",
                nulls_distinct=False,
            ),
        ]

        indexes = [
            models.Index(
                fields=["metric_date", "-trend_temperature"],
                name="idx_metric_temp_day",
            ),
            models.Index(
                fields=["term", "-metric_date"],
                name="idx_metric_term_day",
            ),
            models.Index(
                fields=["source", "metric_date"],
                name="idx_metric_source_day",
            ),
        ]

    def __str__(self):
        source = self.source.code if self.source else "ALL"

        return (
            f"{self.term} / "
            f"{source} / "
            f"{self.metric_date}"
        )


# ============================================================
# TERM ASSOCIATION DAILY
# ============================================================

class TermAssocDaily(models.Model):
    """
    용어 ↔ 용어 연관 지표.

    최근 문서 단위 co-occurrence를 기반으로
    Lift / PMI를 계산한다.
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
        verbose_name="동시 언급 문서 수",
    )

    lift = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Lift",
    )

    pmi = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="PMI",
    )

    association_percentile = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="연관도 백분위",
    )

    association_rank = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="연관 순위",
    )

    is_new = models.BooleanField(
        default=False,
        verbose_name="신규 연관",
    )

    metric_version = models.CharField(
        max_length=50,
        default="feedit-l2-v1",
        verbose_name="지표 버전",
    )

    metrics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 지표",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

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
                    "metric_version",
                ],
                name="uq_term_assoc_day_ver",
            ),

            models.CheckConstraint(
                condition=~models.Q(
                    source_term=models.F("target_term"),
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
                fields=["metric_date", "-pmi"],
                name="idx_assoc_pmi",
            ),
            models.Index(
                fields=["source_term", "association_rank"],
                name="idx_assoc_src_rank",
            ),
        ]

    def __str__(self):
        return (
            f"{self.source_term} ↔ "
            f"{self.target_term} / "
            f"{self.metric_date}"
        )

class TermSearchMetricMonthly(models.Model):
    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="search_metric_monthly",
        verbose_name="용어",
    )

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.CASCADE,
        related_name="term_search_metric_monthly",
        verbose_name="검색 플랫폼",
    )

    metric_month = models.DateField(
        verbose_name="기준 월",
    )

    search_volume = models.BigIntegerField(
        default=0,
        verbose_name="월간 검색량",
    )

    log_volume = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )

    percentile = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
    )

    data_type = models.CharField(
        max_length=50,
        default="monthly_absolute",
    )

    metric_version = models.CharField(
        max_length=50,
        default="feedit-search-v1",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = '"analysis"."term_search_metric_monthly"'

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "term",
                    "source",
                    "metric_month",
                    "metric_version",
                ],
                name="uq_term_search_month_ver",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "metric_month",
                    "-search_volume",
                ],
                name="idx_search_month_volume",
            ),
            models.Index(
                fields=[
                    "term",
                    "-metric_month",
                ],
                name="idx_search_term_month",
            ),
        ]