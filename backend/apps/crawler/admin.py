from django.contrib import admin

from apps.crawler.models import (
    Source,
    CrawlTarget,
    CrawlJob,
    RawObject,
    BackfillBatch,
    BackfillItem,
    MusinsaBrand,
    MusinsaProduct,
    MusinsaProductSnapshot,
    AblyProduct,
    AblyProductSnapshot,
    ZigzagProduct,
    ZigzagProductSnapshot,
    YoutubeCreator,
    YoutubeContent,
    YoutubeContentMetric,
    YoutubeTranscript,
)

# ============================================================
# COMMON
# ============================================================


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "source_type",
        "status",
        "collection_method",
        "crawl_interval_minutes",
        "updated_at",
    )

    list_filter = (
        "source_type",
        "status",
        "collection_method",
    )

    search_fields = (
        "code",
        "base_url",
    )

    ordering = ("code",)


@admin.register(CrawlTarget)
class CrawlTargetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "display_name",
        "target_type",
        "target_value",
        "is_active",
        "updated_at",
    )

    list_filter = (
        "source",
        "target_type",
        "is_active",
    )

    search_fields = (
        "display_name",
        "target_value",
    )

    list_editable = ("is_active",)


@admin.register(CrawlJob)
class CrawlJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "crawl_target",
        "status",
        "trigger_type",
        "items_found",
        "items_created",
        "items_updated",
        "attempt",
        "started_at",
        "finished_at",
    )

    list_filter = (
        "source",
        "status",
        "trigger_type",
    )

    search_fields = (
        "celery_task_id",
        "error_type",
        "error_message",
    )

    readonly_fields = (
        "created_at",
        "started_at",
        "finished_at",
    )

    ordering = ("-id",)


@admin.register(RawObject)
class RawObjectAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "crawl_job",
        "http_status",
        "content_type",
        "collected_at",
    )

    list_filter = (
        "source",
        "http_status",
        "content_type",
    )

    search_fields = (
        "request_url",
        "storage_key",
        "checksum",
    )

    ordering = ("-collected_at",)


@admin.register(BackfillBatch)
class BackfillBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "status",
        "start_date",
        "end_date",
        "total_items",
        "success_items",
        "failed_items",
        "created_at",
    )

    list_filter = (
        "source",
        "status",
    )

    search_fields = ("id",)

    readonly_fields = (
        "created_at",
        "started_at",
        "finished_at",
    )

    ordering = ("-created_at",)


admin.register(BackfillItem)


class BackfillItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "batch",
        "target_key",
        "status",
        "items_found",
        "items_created",
        "items_updated",
        "created_at",
    )

    list_filter = ("status",)

    search_fields = (
        "target_key",
        "request_url",
        "celery_task_id",
        "error_type",
        "error_message",
    )

    readonly_fields = (
        "created_at",
        "started_at",
        "finished_at",
    )

    ordering = ("-created_at",)


# ============================================================
# MUSINSA
# ============================================================


@admin.register(MusinsaBrand)
class MusinsaBrandAdmin(admin.ModelAdmin):
    list_display = (
        "brand_id",
        "name_ko",
        "name_en",
        "nation",
        "since_year",
        "updated_at",
    )

    search_fields = (
        "brand_id",
        "name_ko",
        "name_en",
    )

    list_filter = ("nation",)

    ordering = ("name_ko",)


@admin.register(MusinsaProduct)
class MusinsaProductAdmin(admin.ModelAdmin):
    list_display = (
        "goods_no",
        "name",
        "brand",
        "category_depth1",
        "category_depth2",
        "sex",
        "season_year",
        "season",
        "updated_at",
    )

    list_filter = (
        "category_depth1",
        "category_depth2",
        "sex",
        "season",
    )

    search_fields = (
        "goods_no",
        "name",
        "style_no",
        "brand__name_ko",
        "brand__name_en",
    )

    ordering = ("-updated_at",)


@admin.register(MusinsaProductSnapshot)
class MusinsaProductSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "rank",
        "sale_price",
        "discount_rate",
        "review_count",
        "satisfaction_score",
        "is_out_of_stock",
        "observed_at",
    )

    list_filter = (
        "ranking_gender",
        "ranking_period",
        "is_out_of_stock",
        "ranking_category_depth1_name",
    )

    search_fields = (
        "product__name",
        "product__goods_no",
        "product__brand__name_ko",
    )

    ordering = ("-observed_at",)


# ============================================================
# ABLY
# ============================================================


@admin.register(AblyProduct)
class AblyProductAdmin(admin.ModelAdmin):
    list_display = (
        "source_product_id",
        "product_name",
        "market_name",
        "category_name",
        "first_seen_at",
        "last_seen_at",
    )

    list_filter = (
        "market_name",
        "category_name",
    )

    search_fields = (
        "source_product_id",
        "product_name",
        "market_name",
    )

    ordering = ("-last_seen_at",)


@admin.register(AblyProductSnapshot)
class AblyProductSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "rank",
        "sale_price",
        "discount_rate",
        "review_count",
        "like_count",
        "availability",
        "observed_at",
    )

    list_filter = ("availability",)

    search_fields = (
        "product__product_name",
        "product__source_product_id",
    )

    ordering = ("-observed_at",)


# ============================================================
# ZIGZAG
# ============================================================


@admin.register(ZigzagProduct)
class ZigzagProductAdmin(admin.ModelAdmin):
    list_display = (
        "source_product_id",
        "product_name",
        "store_name",
        "brand_name",
        "category_name",
        "first_seen_at",
        "last_seen_at",
    )

    list_filter = (
        "store_name",
        "brand_name",
        "category_name",
    )

    search_fields = (
        "source_product_id",
        "product_name",
        "store_name",
        "brand_name",
    )

    ordering = ("-last_seen_at",)


@admin.register(ZigzagProductSnapshot)
class ZigzagProductSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "rank",
        "sale_price",
        "discount_rate",
        "review_count",
        "like_count",
        "availability",
        "observed_at",
    )

    list_filter = ("availability",)

    search_fields = (
        "product__product_name",
        "product__source_product_id",
    )

    ordering = ("-observed_at",)


# ============================================================
# YOUTUBE
# ============================================================


@admin.register(YoutubeCreator)
class YoutubeCreatorAdmin(admin.ModelAdmin):
    list_display = (
        "channel_name",
        "channel_id",
        "uploads_playlist_id",
        "last_video_id",
        "last_checked_at",
        "last_seen_at",
        "updated_at",
    )

    search_fields = (
        "channel_name",
        "channel_id",
        "uploads_playlist_id",
    )

    ordering = ("channel_name",)


@admin.register(YoutubeContent)
class YoutubeContentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "creator",
        "video_id",
        "content_type",
        "published_at",
        "last_seen_at",
    )

    list_filter = (
        "content_type",
        "creator",
    )

    search_fields = (
        "title",
        "video_id",
        "creator__channel_name",
    )

    ordering = ("-published_at",)


@admin.register(YoutubeContentMetric)
class YoutubeContentMetricAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "content",
        "view_count",
        "like_count",
        "comment_count",
        "observed_at",
    )

    search_fields = (
        "content__title",
        "content__video_id",
    )

    ordering = ("-observed_at",)


@admin.register(YoutubeTranscript)
class YoutubeTranscriptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "content",
        "language",
        "transcript_type",
        "source",
        "collected_at",
        "updated_at",
    )

    list_filter = (
        "language",
        "transcript_type",
        "source",
    )

    search_fields = (
        "content__title",
        "content__video_id",
        "full_text",
    )

    ordering = ("-created_at",)


# ============================================================
# ADMIN SITE
# ============================================================

admin.site.site_header = "FEEDIT Admin"
admin.site.site_title = "FEEDIT Admin"
admin.site.index_title = "Crawler & Data Management"
