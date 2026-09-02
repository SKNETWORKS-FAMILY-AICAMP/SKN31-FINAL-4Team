from django.contrib import admin, messages
from apps.core.models import CrawlTarget
from apps.core.tasks import run_live_target

from .models import (
    # collection
    CrawlRun,
    CrawlTarget,
    RawDocument,
    Source,
    # dictionary
    DictionaryTerm,
    TermAlias,
    Category,
    Style,
    Item,
    Detail,
    Material,
    Color,
    TPO,
    TermRelation,
    TermCandidate,
    Brand,
    BrandAlias,
    CategoryAlias,
    # commerce
    Product,
    ProductSource,
    ProductSourceSnapshot,
    ResaleSnapshot,
    ProductTerm,
    # content
    ContentProfile,
    ContentItem,
    ContentSnapshot,
    # analysis
    TextDocument,
    TermMetricDaily,
    TermAssocDaily,
    # app
    AppUser,
    UserTaste,
    UserEvent,
    UserSavedItem,
    VoteCard,
    VoteBallot,
    ChatSession,
    ChatMessage,
)


# =====================================================================
# collection: 크롤링 소스 / 실행 / 원본 데이터
# =====================================================================

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = (
        "code", "name", "source_type", "collection_method",
        "status", "crawl_interval_minutes", "requests_per_minute", "updated_at",
    )
    list_filter = ("source_type", "collection_method", "status")
    search_fields = ("code", "name", "base_url")
    ordering = ("code",)


@admin.register(CrawlRun)
class CrawlRunAdmin(admin.ModelAdmin):
    list_display = (
        "id", "source", "run_type", "status",
        "started_at", "finished_at", "success_count", "failure_count", "error_code",
    )
    list_filter = ("status", "run_type", "source")
    search_fields = ("target", "error_code", "error_message")
    autocomplete_fields = ("source",)
    date_hierarchy = "started_at"
    list_select_related = ("source",)
    readonly_fields = ("created_at",)


@admin.register(RawDocument)
class RawDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "source", "document_type", "external_id",
        "http_status", "content_type", "collected_at",
    )
    list_filter = ("source", "document_type", "http_status")
    search_fields = ("external_id", "source_url", "s3_key", "content_hash")
    autocomplete_fields = ("source", "crawl_run")
    date_hierarchy = "collected_at"
    list_select_related = ("source", "crawl_run")
    readonly_fields = ("created_at",)


# =====================================================================
# dictionary: 표준 용어 사전 / 카테고리 / 브랜드
# =====================================================================

class TermAliasInline(admin.TabularInline):
    model = TermAlias
    extra = 0
    fields = ("alias", "normalized_alias", "alias_type", "source")
    autocomplete_fields = ("source",)


@admin.register(DictionaryTerm)
class DictionaryTermAdmin(admin.ModelAdmin):
    list_display = (
        "canonical_name", "term_type", "term_code",
        "status", "first_seen_at", "last_seen_at",
    )
    list_filter = ("term_type", "status")
    search_fields = ("term_code", "canonical_name", "normalized_name", "english_name")
    inlines = [TermAliasInline]
    ordering = ("term_type", "term_code")


@admin.register(TermAlias)
class TermAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "term", "alias_type", "source", "created_at")
    list_filter = ("alias_type", "source")
    search_fields = ("alias", "normalized_alias")
    autocomplete_fields = ("term", "source")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name", "code", "category_type", "parent",
        "level", "sort_order", "status",
    )
    list_filter = ("category_type", "status", "level")
    search_fields = ("code", "name")
    autocomplete_fields = ("parent",)
    ordering = ("category_type", "level", "sort_order", "code")


@admin.register(Style)
class StyleAdmin(admin.ModelAdmin):
    list_display = ("term", "style_group", "is_core")
    list_filter = ("style_group", "is_core")
    search_fields = ("term__canonical_name",)
    autocomplete_fields = ("term",)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("term", "category", "gender_scope")
    list_filter = ("gender_scope", "category")
    search_fields = ("term__canonical_name",)
    autocomplete_fields = ("term", "category")


@admin.register(Detail)
class DetailAdmin(admin.ModelAdmin):
    list_display = ("term", "attribute_type", "target_type")
    list_filter = ("attribute_type",)
    search_fields = ("term__canonical_name",)
    autocomplete_fields = ("term",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("term", "material_type", "process_type")
    list_filter = ("material_type", "process_type")
    search_fields = ("term__canonical_name",)
    autocomplete_fields = ("term",)


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("term", "color_family", "base_color")
    list_filter = ("color_family",)
    search_fields = ("term__canonical_name",)
    autocomplete_fields = ("term", "base_color")
    ordering = ("color_family", "term__canonical_name")


@admin.register(TPO)
class TPOAdmin(admin.ModelAdmin):
    list_display = ("term", "tpo_type")
    list_filter = ("tpo_type",)
    search_fields = ("term__canonical_name",)
    autocomplete_fields = ("term",)


@admin.register(TermRelation)
class TermRelationAdmin(admin.ModelAdmin):
    list_display = (
        "source_term", "target_term", "relation_type",
        "weight", "confidence", "relation_source",
    )
    list_filter = ("relation_type", "relation_source")
    search_fields = ("source_term__canonical_name", "target_term__canonical_name")
    autocomplete_fields = ("source_term", "target_term")


@admin.register(TermCandidate)
class TermCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "raw_term", "normalized_term", "suggested_type",
        "detected_count", "status", "last_seen_at",
    )
    list_filter = ("status", "suggested_type", "detected_source")
    search_fields = ("raw_term", "normalized_term", "example_context")
    date_hierarchy = "last_seen_at"
    actions = ["approve_candidates", "reject_candidates"]

    @admin.action(description="선택한 용어 후보 승인 처리")
    def approve_candidates(self, request, queryset):
        updated = queryset.update(status=TermCandidate.Status.APPROVED)
        self.message_user(request, f"{updated}건을 승인 처리했습니다.")

    @admin.action(description="선택한 용어 후보 제외 처리")
    def reject_candidates(self, request, queryset):
        updated = queryset.update(status=TermCandidate.Status.REJECTED)
        self.message_user(request, f"{updated}건을 제외 처리했습니다.")


class BrandAliasInline(admin.TabularInline):
    model = BrandAlias
    extra = 0
    fields = ("alias", "normalized_alias", "language", "source")
    autocomplete_fields = ("source",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = (
        "name", "brand_code", "english_name",
        "country_code", "category", "status",
    )
    list_filter = ("status", "country_code", "category")
    search_fields = ("brand_code", "name", "english_name")
    autocomplete_fields = ("category",)
    inlines = [BrandAliasInline]
    ordering = ("name",)


@admin.register(BrandAlias)
class BrandAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "brand", "language", "source", "created_at")
    list_filter = ("language", "source")
    search_fields = ("alias", "normalized_alias")
    autocomplete_fields = ("brand", "source")


@admin.register(CategoryAlias)
class CategoryAliasAdmin(admin.ModelAdmin):
    list_display = ("source_category_name", "category", "source", "source_category_id", "created_at")
    list_filter = ("source",)
    search_fields = ("source_category_id", "source_category_name")
    autocomplete_fields = ("category", "source")


# =====================================================================
# commerce: 상품 / 플랫폼 상품 / 스냅샷
# =====================================================================

class ProductSourceInline(admin.TabularInline):
    model = ProductSource
    extra = 0
    fields = ("source", "source_product_id", "market_type", "status", "last_seen_at")
    autocomplete_fields = ("source",)
    show_change_link = True


class ProductTermInline(admin.TabularInline):
    model = ProductTerm
    extra = 0
    autocomplete_fields = ("term",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "canonical_name", "brand", "category", "item_term",
        "gender_scope", "status", "updated_at",
    )
    list_filter = ("status", "gender_scope", "brand", "category")
    search_fields = ("canonical_name", "normalized_name")
    autocomplete_fields = ("brand", "category", "item_term")
    inlines = [ProductSourceInline, ProductTermInline]
    list_select_related = ("brand", "category", "item_term")


@admin.register(ProductSource)
class ProductSourceAdmin(admin.ModelAdmin):
    list_display = (
        "product", "source", "source_product_id",
        "market_type", "status", "last_seen_at",
    )
    list_filter = ("market_type", "status", "source")
    search_fields = ("source_product_id", "product__canonical_name")
    autocomplete_fields = ("product", "source")
    list_select_related = ("product", "source")


@admin.register(ProductSourceSnapshot)
class ProductSourceSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "product_source", "observed_at", "sale_price", "list_price",
        "discount_rate", "rank_position", "rating", "stock_status",
    )
    list_filter = ("stock_status", "ranking_scope")
    search_fields = ("product_source__source_product_id", "product_source__product__canonical_name")
    autocomplete_fields = ("product_source",)
    date_hierarchy = "observed_at"
    list_select_related = ("product_source", "product_source__product")


@admin.register(ResaleSnapshot)
class ResaleSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "product_source", "observed_at", "avg_price",
        "median_price", "sold_count", "resale_index",
    )
    search_fields = ("product_source__source_product_id",)
    autocomplete_fields = ("product_source",)
    date_hierarchy = "observed_at"
    list_select_related = ("product_source",)


@admin.register(ProductTerm)
class ProductTermAdmin(admin.ModelAdmin):
    list_display = ("product", "term", "created_at")
    search_fields = ("product__canonical_name", "term__canonical_name")
    autocomplete_fields = ("product", "term")


# =====================================================================
# content: 콘텐츠 프로필 / 콘텐츠 / 스냅샷
# =====================================================================

@admin.register(ContentProfile)
class ContentProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "handle", "source", "profile_type", "status", "last_seen_at")
    list_filter = ("source", "profile_type", "status")
    search_fields = ("name", "handle", "external_profile_id")
    autocomplete_fields = ("source",)
    list_select_related = ("source",)


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = (
        "title", "source", "profile", "content_type",
        "analysis_status", "published_at",
    )
    list_filter = ("content_type", "analysis_status", "source")
    search_fields = ("title", "external_content_id", "description")
    autocomplete_fields = ("source", "profile")
    date_hierarchy = "published_at"
    list_select_related = ("source", "profile")


@admin.register(ContentSnapshot)
class ContentSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "content_item", "observed_at", "view_count",
        "like_count", "comment_count", "share_count",
    )
    search_fields = ("content_item__title",)
    autocomplete_fields = ("content_item",)
    date_hierarchy = "observed_at"
    list_select_related = ("content_item",)


# =====================================================================
# analysis: 텍스트 분석 / 용어 트렌드 지표
# =====================================================================

@admin.register(TextDocument)
class TextDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "document_type", "content_item", "source",
        "language", "sentiment_score", "analysis_status", "analyzed_at",
    )
    list_filter = ("document_type", "analysis_status", "language", "source")
    search_fields = ("external_id", "body")
    autocomplete_fields = ("source", "content_item")
    date_hierarchy = "created_at"
    list_select_related = ("source", "content_item")


@admin.register(TermMetricDaily)
class TermMetricDailyAdmin(admin.ModelAdmin):
    list_display = (
        "term", "metric_date", "mention_count", "document_count",
        "source_count", "sentiment_avg", "growth_rate", "trend_score",
    )
    list_filter = ("metric_date",)
    search_fields = ("term__canonical_name",)
    autocomplete_fields = ("term",)
    date_hierarchy = "metric_date"
    list_select_related = ("term",)


@admin.register(TermAssocDaily)
class TermAssocDailyAdmin(admin.ModelAdmin):
    list_display = (
        "source_term", "target_term", "metric_date",
        "cooccurrence_count", "association_score", "confidence",
    )
    list_filter = ("metric_date",)
    search_fields = ("source_term__canonical_name", "target_term__canonical_name")
    autocomplete_fields = ("source_term", "target_term")
    date_hierarchy = "metric_date"
    list_select_related = ("source_term", "target_term")


# =====================================================================
# app: 서비스 사용자 / 취향 / 행동 로그 / 살말 / 챗봇
# =====================================================================

class UserTasteInline(admin.TabularInline):
    model = UserTaste
    extra = 0
    autocomplete_fields = ("term", "brand", "category")


@admin.register(AppUser)
class AppUserAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "gender", "birth_year", "body_type", "created_at")
    list_filter = ("gender", "body_type")
    search_fields = ("nickname", "user__username", "user__email")
    autocomplete_fields = ("user",)
    inlines = [UserTasteInline]


@admin.register(UserTaste)
class UserTasteAdmin(admin.ModelAdmin):
    list_display = ("user", "taste_type", "term", "brand", "category", "weight", "source")
    list_filter = ("taste_type", "source")
    search_fields = ("user__nickname", "term__canonical_name", "brand__name", "category__name")
    autocomplete_fields = ("user", "term", "brand", "category")


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "content_item", "product", "term", "created_at")
    list_filter = ("event_type",)
    search_fields = ("user__nickname",)
    autocomplete_fields = ("user", "content_item", "product", "term")
    date_hierarchy = "created_at"
    list_select_related = ("user",)


@admin.register(UserSavedItem)
class UserSavedItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "content_item", "created_at")
    search_fields = ("user__nickname", "product__canonical_name", "content_item__title")
    autocomplete_fields = ("user", "product", "content_item")
    date_hierarchy = "created_at"


class VoteBallotInline(admin.TabularInline):
    model = VoteBallot
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(VoteCard)
class VoteCardAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "product", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "description")
    autocomplete_fields = ("user", "product")
    inlines = [VoteBallotInline]
    date_hierarchy = "created_at"


@admin.register(VoteBallot)
class VoteBallotAdmin(admin.ModelAdmin):
    list_display = ("card", "user", "choice", "created_at")
    list_filter = ("choice",)
    search_fields = ("card__title", "user__nickname")
    autocomplete_fields = ("card", "user")


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    fields = ("role", "content", "created_at")
    readonly_fields = ("created_at",)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "started_at", "updated_at")
    search_fields = ("title", "user__nickname")
    autocomplete_fields = ("user",)
    inlines = [ChatMessageInline]
    date_hierarchy = "started_at"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("session", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("content", "session__title")
    autocomplete_fields = ("session",)
    date_hierarchy = "created_at"
@admin.register(CrawlTarget)
class CrawlTargetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "target_type",
        "collection_mode",
        "is_active",
        "priority",
        "last_crawled_at",
        "next_crawl_at",
    )

    list_filter = (
        "source",
        "target_type",
        "collection_mode",
        "is_active",
    )

    search_fields = (
        "source__code",
        "source__name",
        "target_url",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_crawled_at",
    )

    actions = [
        "run_selected_targets",
    ]

    @admin.action(
        description="선택한 수집 대상 실행"
    )
    def run_selected_targets(
        self,
        request,
        queryset,
    ):
        count = 0

        for target in queryset:
            if not target.is_active:
                continue

            run_live_target.delay(
                target.id
            )

            count += 1

        self.message_user(
            request,
            f"{count}개 수집 작업을 큐에 등록했습니다.",
            level=messages.SUCCESS,
        )