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

    product_source = models.ForeignKey(
        "core.ProductSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="text_documents",
        verbose_name="소스 상품",
        help_text="커머스 리뷰가 귀속되는 실제 플랫폼 상품",
    )

    analysis_run = models.ForeignKey(
        "core.AnalysisPipelineRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name="분석 실행",
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

    # 0062 migration added this column for actual comment/review dates.
    # Keep the ORM model in sync: /api/sentiment reads this field for reviews.
    source_published_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="원문 작성일시",
        help_text="수집일이 아니라 댓글·리뷰가 실제 작성된 시각",
    )

    source_payload_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="원문 해시",
        help_text="원문이 바뀐 경우에만 재분석하기 위한 SHA-256",
    )

    analysis_version = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="분석 버전",
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
            models.Index(
                fields=["product_source", "document_type"],
                name="idx_text_doc_product",
            ),
            models.Index(
                fields=["source", "analysis_version", "analysis_status"],
                name="idx_text_doc_anl_ver",
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["source", "document_type", "external_id"],
                condition=(
                    models.Q(external_id__isnull=False)
                    & ~models.Q(external_id="")
                ),
                name="uq_text_doc_source_type_external",
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
        # 텍스트 신호 파이프라인(analysis/text_signals)이 댓글·리뷰 언급에 쓴다.
        COMMENT = "COMMENT", "유튜브 댓글"
        REVIEW = "REVIEW", "커머스 리뷰"

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
    class Basis(models.TextChoices):
        TEXT = "TEXT", "언급 동시출현"
        SEARCH = "SEARCH", "검색 동시질의"

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
    
    # 0065_term_assoc_basis 와 같은 정의다. 길이·인덱스를 바꾸면 운영 DB 변경이 따라온다.
    basis = models.CharField(
        max_length=10,
        choices=Basis.choices,
        default=Basis.TEXT,
        verbose_name="연관 근거",
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
                    "basis",
                ],
                name="uq_term_assoc_day_ver_basis",
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
            models.Index(
                fields=["source_term", "basis", "-metric_date"],
                name="idx_assoc_src_basis",
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

    # ★ 2026-09-21 — 네이버 검색광고(N1·N4)가 같은 응답으로 주는 값들.
    #   PC/모바일 분리는 데이터랩 device 컷을 따로 받지 않아도 되게 해 준다.
    pc_volume = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="PC 검색량",
    )

    mobile_volume = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="모바일 검색량",
    )

    competition = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="광고 경쟁도",
        help_text="네이버 검색광고 기준 높음/중간/낮음. '시장 포화도'가 아니라 광고 경쟁 강도다.",
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


# ============================================================
# Legacy service models preserved during backend merge
# ============================================================

class AnalysisPipelineRun(models.Model):
    """수집 이후 텍스트 분석·적재·지표 계산 실행 이력."""

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "실행 중"
        SUCCESS = "SUCCESS", "성공"
        PARTIAL = "PARTIAL", "일부 성공"
        FAILED = "FAILED", "실패"

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analysis_pipeline_runs",
        verbose_name="플랫폼",
    )
    run_date = models.DateField(db_index=True, verbose_name="기준일")
    pipeline_version = models.CharField(max_length=64, db_index=True)
    prompt_version = models.CharField(max_length=64, blank=True, default="")
    model_name = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    input_count = models.BigIntegerField(default=0)
    analyzed_count = models.BigIntegerField(default=0)
    skipped_count = models.BigIntegerField(default=0)
    failure_count = models.BigIntegerField(default=0)
    prompt_tokens = models.BigIntegerField(default=0)
    cached_tokens = models.BigIntegerField(default=0)
    output_tokens = models.BigIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=0,
    )
    metrics = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = '"analysis"."pipeline_run"'
        indexes = [
            models.Index(
                fields=["-run_date", "status"],
                name="idx_pipeline_run_day_status",
            ),
        ]


class PlatformMetricDaily(models.Model):
    """플랫폼별 분석 커버리지와 신호 품질을 감시하는 일별 운영 지표."""

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.CASCADE,
        related_name="platform_daily_metrics",
    )
    metric_date = models.DateField()
    document_count = models.BigIntegerField(default=0)
    analyzed_document_count = models.BigIntegerField(default=0)
    kept_document_count = models.BigIntegerField(default=0)
    mention_count = models.BigIntegerField(default=0)
    candidate_count = models.BigIntegerField(default=0)
    analysis_coverage_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
    )
    evidence_valid_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
    )
    positive_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
    )
    negative_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
    )
    purchase_intent_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
    )
    metric_version = models.CharField(max_length=64, default="feedit-platform-v1")
    metrics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"analysis"."platform_metric_daily"'
        constraints = [
            models.UniqueConstraint(
                fields=["source", "metric_date", "metric_version"],
                name="uq_platform_metric_day_ver",
            ),
        ]
        indexes = [
            models.Index(
                fields=["metric_date", "source"],
                name="idx_platform_metric_day_src",
            ),
        ]


class TermSearchTrend(models.Model):
    """검색 관심도 시계열 — 네이버 데이터랩(D1·D2·D3) · 구글 트렌즈(G1).

    ★ 2026-09-21 신설.
      term_metric_daily 는 '사람이 뭐라고 말했나'(댓글·리뷰 언급)를 센다.
      이 표는 '사람이 뭘 찾아봤나'(검색)를 센다.
      둘은 다른 현상이다 — 한 표에 섞으면 같은 이름의 '온도'가 두 가지 뜻을
      갖게 되고, 화면에서 "무신사 70도 / 구글 56도"처럼 비교 불가능한 숫자가
      나란히 서게 된다. 그래서 표를 나눈다.

      ratio             플랫폼이 주는 상대 지수(0~100). 절대값이 아니다.
      estimated_volume  월간 절대 검색량(TermSearchMetricMonthly)을 앵커로
                        환산한 추정치. 환산식은 processors/normalizer.py.
      segment           all | gender:m | gender:f | age:10s … (데이터랩 컷)
                        세그먼트는 일간 변동값이 아니라 '캐릭터 규정'이라
                        주 1회만 받는다. 자세한 셈은 collectors/naver_datalab.py.
    """

    class TimeUnit(models.TextChoices):
        DAY = "DAY", "일간"
        WEEK = "WEEK", "주간"
        MONTH = "MONTH", "월간"

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="search_trend",
        verbose_name="용어",
    )

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.CASCADE,
        related_name="term_search_trend",
        verbose_name="검색 플랫폼",
    )

    metric_date = models.DateField(
        verbose_name="구간 시작일",
        help_text="주간이면 그 주의 시작일, 월간이면 1일.",
    )

    time_unit = models.CharField(
        max_length=10,
        choices=TimeUnit.choices,
        default=TimeUnit.WEEK,
    )

    segment = models.CharField(
        max_length=20,
        default="all",
        verbose_name="세그먼트",
    )

    ratio = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="상대 지수 (0~100)",
    )

    estimated_volume = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="추정 절대 검색량",
    )

    metric_version = models.CharField(
        max_length=50,
        default="feedit-search-v1",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"analysis"."term_search_trend"'

        constraints = [
            models.UniqueConstraint(
                fields=["term", "source", "metric_date", "time_unit",
                        "segment", "metric_version"],
                name="uq_term_search_trend",
            ),
        ]

        indexes = [
            models.Index(fields=["term", "-metric_date"], name="idx_strend_term_date"),
            models.Index(fields=["source", "-metric_date"], name="idx_strend_src_date"),
            models.Index(fields=["segment"], name="idx_strend_segment"),
        ]

    def __str__(self):
        return f"{self.term_id} {self.metric_date} {self.segment}"


class TermSearchRegion(models.Model):
    """시·도별 검색 관심도 (G5 · 구글 트렌즈).

    ★ 2026-09-21 신설. 적재 전에 반드시 알아야 할 것이 하나 있다 —
      **값은 용어 하나짜리 요청으로 받은 것이어야 한다.**
      여러 용어를 한 페이로드에 넣고 지역을 받으면 구글은 '그 지역 안에서
      비교 용어들끼리의 점유율'을 준다(지역마다 합 100). 실제로 2026-09-21
      테스트에서 고프코어가 강원도 100, 경상남도 100 으로 동시에 나왔다 —
      용어별 정규화라면 불가능한 값이다.
      그 값을 term × region 으로 넣으면 같은 배치에 누가 묶였느냐에 따라
      숫자가 통째로 바뀌는 가짜 지표가 된다.
      수집은 collectors/google_trends.py 의 collect_region() 만 쓸 것.

      value 는 '그 시·도 전체 검색량 대비 비율'로 정규화된 0~100 이다.
      인구 보정이 이미 들어가 있어 서울이 자동으로 1등이 되지 않는다.
      KR 은 16개 시·도가 온다(세종 없음). 검색량이 적은 용어는 대부분 0 이다.
    """

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        related_name="search_region",
        verbose_name="용어",
    )

    source = models.ForeignKey(
        "core.Source",
        on_delete=models.CASCADE,
        related_name="term_search_region",
        verbose_name="검색 플랫폼",
    )

    metric_date = models.DateField(
        verbose_name="수집 기준일",
    )

    region = models.CharField(
        max_length=40,
        verbose_name="시·도",
    )

    value = models.IntegerField(
        default=0,
        verbose_name="지역 관심도 (0~100)",
    )

    metric_version = models.CharField(
        max_length=50,
        default="feedit-search-v1",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"analysis"."term_search_region"'

        constraints = [
            models.UniqueConstraint(
                fields=["term", "source", "metric_date", "region", "metric_version"],
                name="uq_term_search_region",
            ),
        ]

        indexes = [
            models.Index(fields=["term", "-metric_date"], name="idx_sregion_term_date"),
            models.Index(fields=["region", "-value"], name="idx_sregion_value"),
        ]

    def __str__(self):
        return f"{self.term_id} {self.region} {self.value}"
