from django.db import models


class MusinsaBrand(models.Model):
    """
    무신사 브랜드 정보
    """

    brand_id = models.CharField(
        max_length=50,
        primary_key=True,
        help_text="무신사 고유 브랜드 ID (ex. trillion)",
    )
    name_ko = models.CharField(max_length=100, help_text="브랜드 한글명")
    name_en = models.CharField(
        max_length=100, blank=True, null=True, help_text="브랜드 영문명"
    )
    nation = models.CharField(
        max_length=50, blank=True, null=True, help_text="브랜드 국가"
    )
    since_year = models.IntegerField(blank=True, null=True, help_text="론칭 연도")

    logo_url = models.URLField(
        max_length=500, blank=True, null=True, help_text="브랜드 로고 이미지 URL"
    )
    description = models.TextField(
        blank=True, null=True, help_text="브랜드 메모/설명 (ex. 브랜드 철학 및 컨셉)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "musinsa_brand"

    def __str__(self):
        return self.name_ko


class MusinsaProduct(models.Model):
    """
    무신사 상품 기본 정보
    시간에 따라 자주 변하지 않는 데이터 중심
    """

    goods_no = models.IntegerField(
        primary_key=True, help_text="상품 고유 번호 (ex. 6307599)"
    )
    style_no = models.CharField(
        max_length=100, blank=True, null=True, help_text="브랜드 품번"
    )
    name = models.CharField(max_length=255, help_text="상품명")

    brand = models.ForeignKey(
        MusinsaBrand,
        on_delete=models.CASCADE,
        related_name="products",
        null=True,  # 데이터베이스에 빈 값(Null) 저장을 허용
        blank=True,  # 관리자 페이지나 폼(Form)에서 입력을 비워두는 것을 허용
    )

    # 카테고리
    category_depth1 = models.CharField(
        max_length=50, null=True, blank=True, help_text="대분류 (ex. 상의)"
    )
    category_depth2 = models.CharField(
        max_length=50, null=True, blank=True, help_text="중분류 (ex. 셔츠/블라우스)"
    )

    # 타겟 및 시즌
    sex = models.CharField(
        max_length=20, null=True, blank=True, help_text="대상 성별 (남성, 여성, 공용)"
    )
    season_year = models.IntegerField(blank=True, null=True, help_text="시즌 연도")
    season = models.CharField(
        max_length=20, blank=True, null=True, help_text="시즌 (ex. 1, SS, FW 등)"
    )

    # 이미지
    thumbnail_url = models.URLField(max_length=500, blank=True, null=True)

    # 메타 데이터 (핏, 촉감, 신축성, 두께 등 형태가 다양한 데이터는 JSON으로 유연하게 저장)
    material_info = models.JSONField(
        blank=True, null=True, help_text="핏, 촉감, 신축성 등 소재 특성 JSON"
    )

    tags = models.JSONField(
        blank=True,
        null=True,
        help_text="상품 관련 태그 목록",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "musinsa_product"

    def __str__(self):
        return f"[{self.goods_no}] {self.name}"


class MusinsaProductSnapshot(models.Model):
    """
    무신사 상품의 시간에 따른 변화 기록
    (가격, 랭킹, 반응 등 변동성이 높은 시계열 데이터)
    """

    product = models.ForeignKey(
        MusinsaProduct,  # 문자열 참조로 순환 참조 방지
        on_delete=models.CASCADE,
        related_name="snapshots",
    )

    crawl_job = models.ForeignKey(
        "crawler.CrawlJob",  # 문자열 참조 (앱 내에 존재한다고 가정)
        on_delete=models.SET_NULL,
        related_name="musinsa_snapshots",
        blank=True,
        null=True,
    )

    crawl_target = models.ForeignKey(
        "crawler.CrawlTarget",  # 문자열 참조 (앱 내에 존재한다고 가정)
        on_delete=models.SET_NULL,
        related_name="musinsa_snapshots",
        blank=True,
        null=True,
    )

    # --- 가격 정보 ---
    regular_price = models.BigIntegerField(
        blank=True, null=True, help_text="정상가 (ex. 48000)"
    )

    sale_price = models.BigIntegerField(
        blank=True, null=True, help_text="판매가 (ex. 34800)"
    )

    discount_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="할인율 (ex. 28.00)",
    )

    # --- 랭킹 정보 ---
    rank = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="해당 시점의 상품 랭킹",
    )
    ranking_period = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="랭킹 기간 유형 (ex. MONTHLY, DAILY)",
    )

    ranking_year = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="랭킹 기준 연도",
    )

    ranking_month = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="랭킹 기준 월",
    )
    ranking_gender = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="랭킹 성별 기준 (ex. A, M, F)",
    )

    ranking_category_depth1_code = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    ranking_category_depth1_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    ranking_category_depth2_code = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    ranking_category_depth2_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    # --- 고객 반응 지표 ---
    review_count = models.BigIntegerField(
        blank=True, null=True, help_text="누적 후기 수 (ex. 323)"
    )

    # 🌟 추가된 필드: 평점
    satisfaction_score = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        blank=True,
        null=True,
        help_text="평점 (ex. 4.0)",
    )

    like_count = models.BigIntegerField(
        blank=True,
        null=True,
        help_text="좋아요/찜 수",  # (주: 주어진 JSON에는 없지만 추후 확장을 위해 유지 권장)
    )

    view_count = models.BigIntegerField(
        blank=True,
        null=True,
        help_text="상품 조회수",
    )

    sales_count = models.BigIntegerField(
        blank=True,
        null=True,
        help_text="누적 판매 수량",
    )

    # --- 상태 정보 ---
    availability = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="판매 상태 (ex. 주문가능, 품절 등)",
    )

    # 🌟 추가된 필드: 품절 여부 (분석 시 조건절에 유용함)
    is_out_of_stock = models.BooleanField(
        default=False, help_text="품절 여부 (True면 품절)"
    )

    # --- 메타 정보 ---
    observed_at = models.DateTimeField(help_text="실제 데이터가 관측(수집)된 시간")

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "musinsa_product_snapshot"

        # 무결성 유지: 동일 상품을 동일 타겟(ex. 카테고리 URL)에서 동일 시간에 중복 수집 방지
        constraints = [
            models.UniqueConstraint(
                fields=["product", "crawl_target", "observed_at"],
                name="unique_musinsa_product_target_observation",
            )
        ]

        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["observed_at"]),
            models.Index(fields=["rank"]),
            models.Index(fields=["product", "observed_at"]),
            models.Index(fields=["crawl_target", "observed_at"]),
        ]

    def __str__(self):
        return f"{self.product_id} Snapshot - {self.observed_at}"
