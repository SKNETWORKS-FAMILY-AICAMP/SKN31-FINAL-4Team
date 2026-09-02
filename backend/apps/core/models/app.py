from django.db import models


class AppUser(models.Model):
    """
    FEEDIT 서비스 사용자.
    Django auth.User와 1:1로 연결해서 쓰는 구조.
    """

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="feedit_profile",
        verbose_name="사용자",
    )

    nickname = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="닉네임",
    )

    gender = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="성별",
    )

    birth_year = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="출생연도",
    )

    body_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="체형",
    )

    profile_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 프로필 정보",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="가입일시",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정일시",
    )

    class Meta:
        db_table = '"app"."app_user"'
        verbose_name = "사용자"
        verbose_name_plural = "사용자"

    def __str__(self):
        return self.nickname or self.user.username


class UserTaste(models.Model):
    """
    사용자의 관심 스타일 / 아이템 / 브랜드 / 용어.
    """

    class TasteType(models.TextChoices):
        TERM = "TERM", "용어"
        BRAND = "BRAND", "브랜드"
        CATEGORY = "CATEGORY", "카테고리"

    user = models.ForeignKey(
        AppUser,
        on_delete=models.CASCADE,
        related_name="tastes",
        verbose_name="사용자",
    )

    taste_type = models.CharField(
        max_length=20,
        choices=TasteType.choices,
        verbose_name="취향 유형",
    )

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_tastes",
        verbose_name="용어",
    )

    brand = models.ForeignKey(
        "core.Brand",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_tastes",
        verbose_name="브랜드",
    )

    category = models.ForeignKey(
        "core.Category",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_tastes",
        verbose_name="카테고리",
    )

    weight = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        default=1,
        verbose_name="관심 가중치",
    )

    source = models.CharField(
        max_length=30,
        default="USER",
        verbose_name="취향 출처",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"app"."user_taste"'
        verbose_name = "사용자 취향"
        verbose_name_plural = "사용자 취향"

        indexes = [
            models.Index(
                fields=["user", "taste_type"],
                name="idx_taste_user_type",
            ),
        ]

    def __str__(self):
        if self.term:
            return f"{self.user} / {self.term}"
        if self.brand:
            return f"{self.user} / {self.brand}"
        if self.category:
            return f"{self.user} / {self.category}"

        return str(self.user)


class UserEvent(models.Model):
    """
    사용자의 행동 로그.
    클릭, 조회, 저장, 검색, 투표 등.
    """

    class EventType(models.TextChoices):
        VIEW = "VIEW", "조회"
        CLICK = "CLICK", "클릭"
        SAVE = "SAVE", "저장"
        SEARCH = "SEARCH", "검색"
        VOTE = "VOTE", "투표"
        CHAT = "CHAT", "챗봇"

    user = models.ForeignKey(
        AppUser,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="사용자",
    )

    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
        verbose_name="행동 유형",
    )

    content_item = models.ForeignKey(
        "core.ContentItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_events",
        verbose_name="콘텐츠",
    )

    product = models.ForeignKey(
        "core.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_events",
        verbose_name="상품",
    )

    term = models.ForeignKey(
        "core.DictionaryTerm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_events",
        verbose_name="용어",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="행동 추가 정보",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="발생일시",
    )

    class Meta:
        db_table = '"app"."user_event"'
        verbose_name = "사용자 행동"
        verbose_name_plural = "사용자 행동"

        indexes = [
            models.Index(
                fields=["user", "-created_at"],
                name="idx_event_user_time",
            ),
            models.Index(
                fields=["event_type", "-created_at"],
                name="idx_event_type_time",
            ),
        ]

    def __str__(self):
        return f"{self.user} / {self.get_event_type_display()}"


class UserSavedItem(models.Model):
    """
    사용자가 저장한 상품 또는 콘텐츠.
    """

    user = models.ForeignKey(
        AppUser,
        on_delete=models.CASCADE,
        related_name="saved_items",
        verbose_name="사용자",
    )

    product = models.ForeignKey(
        "core.Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="saved_by_users",
        verbose_name="상품",
    )

    content_item = models.ForeignKey(
        "core.ContentItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="saved_by_users",
        verbose_name="콘텐츠",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="저장일시",
    )

    class Meta:
        db_table = '"app"."user_saved_item"'
        verbose_name = "저장 항목"
        verbose_name_plural = "저장 항목"

        indexes = [
            models.Index(
                fields=["user", "-created_at"],
                name="idx_saved_user_time",
            ),
        ]

    def __str__(self):
        return f"{self.user} / 저장"


class VoteCard(models.Model):
    """
    '살!말?' 카드.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "진행 중"
        CLOSED = "CLOSED", "종료"

    user = models.ForeignKey(
        AppUser,
        on_delete=models.CASCADE,
        related_name="vote_cards",
        verbose_name="작성자",
    )

    product = models.ForeignKey(
        "core.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vote_cards",
        verbose_name="상품",
    )

    title = models.CharField(
        max_length=300,
        verbose_name="제목",
    )

    description = models.TextField(
        null=True,
        blank=True,
        verbose_name="내용",
    )

    image_url = models.TextField(
        null=True,
        blank=True,
        verbose_name="이미지 URL",
    )

    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name="태그",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
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
        db_table = '"app"."vote_card"'
        verbose_name = "살말 카드"
        verbose_name_plural = "살말 카드"

        indexes = [
            models.Index(
                fields=["status", "-created_at"],
                name="idx_vote_card_status",
            ),
        ]

    def __str__(self):
        return self.title


class VoteBallot(models.Model):
    """
    살 / 말 투표.
    """

    class Choice(models.TextChoices):
        BUY = "BUY", "살"
        PASS = "PASS", "말"

    card = models.ForeignKey(
        VoteCard,
        on_delete=models.CASCADE,
        related_name="ballots",
        verbose_name="살말 카드",
    )

    user = models.ForeignKey(
        AppUser,
        on_delete=models.CASCADE,
        related_name="vote_ballots",
        verbose_name="사용자",
    )

    choice = models.CharField(
        max_length=10,
        choices=Choice.choices,
        verbose_name="선택",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="투표일시",
    )

    class Meta:
        db_table = '"app"."vote_ballot"'
        verbose_name = "살말 투표"
        verbose_name_plural = "살말 투표"

        constraints = [
            models.UniqueConstraint(
                fields=["card", "user"],
                name="uq_vote_ballot",
            ),
        ]

    def __str__(self):
        return f"{self.card} / {self.get_choice_display()}"


class ChatSession(models.Model):
    """
    사용자와 AI 챗봇의 대화 세션.
    """

    user = models.ForeignKey(
        AppUser,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
        verbose_name="사용자",
    )

    title = models.CharField(
        max_length=300,
        null=True,
        blank=True,
        verbose_name="대화 제목",
    )

    context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="세션 컨텍스트",
    )

    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="시작일시",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="최근 대화일시",
    )

    class Meta:
        db_table = '"app"."chat_session"'
        verbose_name = "챗봇 세션"
        verbose_name_plural = "챗봇 세션"

        indexes = [
            models.Index(
                fields=["user", "-updated_at"],
                name="idx_chat_session_user",
            ),
        ]

    def __str__(self):
        return self.title or f"대화 {self.id}"


class ChatMessage(models.Model):
    """
    챗봇 세션 안의 개별 메시지.
    """

    class Role(models.TextChoices):
        USER = "USER", "사용자"
        ASSISTANT = "ASSISTANT", "AI"
        SYSTEM = "SYSTEM", "시스템"

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="대화",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        verbose_name="메시지 역할",
    )

    content = models.TextField(
        verbose_name="내용",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 정보",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    class Meta:
        db_table = '"app"."chat_message"'
        verbose_name = "챗봇 메시지"
        verbose_name_plural = "챗봇 메시지"

        indexes = [
            models.Index(
                fields=["session", "created_at"],
                name="idx_chat_msg_session",
            ),
        ]

    def __str__(self):
        return f"{self.get_role_display()} / {self.created_at}"