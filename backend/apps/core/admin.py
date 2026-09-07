from django.contrib import admin, messages
from apps.core.tasks import run_live_target
from .models import *

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = (
        "code", "name", "source_type", "collection_method",
        "status", "crawl_interval_minutes", "requests_per_minute", "updated_at",
    )
    list_filter = ("source_type", "collection_method", "status")
    search_fields = ("code", "name", "base_url")
    ordering = ("code",)


@admin.register(CrawlTarget)
class CrawlTargetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "target_type",
        "name",
        "is_active",
        "last_crawled_at",
        "created_at",
    )

    list_filter = (
        "source",
        "target_type",
        "is_active",
    )

    search_fields = (
        "name",
        "target_key",
        "target_url",
        "source__code",
    )

    list_select_related = (
        "source",
    )

    ordering = (
        "source",
        "id",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_crawled_at",
    )

    list_per_page = 50
    
@admin.register(CrawlRun)
class CrawlRunAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "target_name",
        "source",
        "run_type",
        "status",
        "discovered_count",
        "success_count",
        "failure_count",
        "started_at",
        "finished_at",
    )

    list_filter = (
        "source",
        "run_type",
        "status",
    )

    search_fields = (
        "id",
        "crawl_target__name",
        "target",
        "source__code",
        "celery_task_id",
        "error_message",
    )

    @admin.display(
        description="Target name",
        ordering="crawl_target__name",
    )
    def target_name(self, obj):
        if obj.crawl_target:
            return (
                obj.crawl_target.name
                or str(obj.crawl_target)
            )

        return "-"
    

@admin.register(RawDocument)
class RawDocumentAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "crawl_run",
        "source_name",
        "document_type",
        "normalization_status",
        "normalized_at",
        "short_s3_key",
        "error_summary",
    )

    list_filter = (
        "normalization_status",
        "document_type",
        "crawl_run__source",
    )

    search_fields = (
        "s3_bucket",
        "s3_key",
        "crawl_run__source__code",
    )

    list_select_related = (
        "crawl_run",
        "crawl_run__source",
    )

    ordering = (
        "-id",
    )

    list_per_page = 50

    readonly_fields = (
        "crawl_run",
        "s3_bucket",
        "s3_key",
        "document_type",
        "normalization_status",
        "normalized_at",
        "normalization_error",
    )

    @admin.display(
        description="출처",
        ordering="crawl_run__source__code",
    )
    def source_name(self, obj):
        return (
            obj.crawl_run.source.code
            if obj.crawl_run_id
            and obj.crawl_run.source_id
            else "-"
        )

    @admin.display(
        description="S3 Key",
    )
    def short_s3_key(self, obj):
        if not obj.s3_key:
            return "-"

        if len(obj.s3_key) <= 80:
            return obj.s3_key

        return (
            "..."
            + obj.s3_key[-77:]
        )

    @admin.display(
        description="정규화 오류",
    )
    def error_summary(self, obj):
        if not obj.normalization_error:
            return "-"

        error = str(
            obj.normalization_error
        )

        if len(error) <= 80:
            return error

        return error[:77] + "..."

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "brand_code",
        "name",
        "english_name",
        "status",
    )

    list_filter = (
        "status",
    )

    search_fields = (
        "brand_code",
        "name",
        "english_name",
    )

    ordering = (
        "name",
    )

    list_per_page = 50


# =========================================================
# 플랫폼 브랜드
# =========================================================


class BrandMappingFilter(
    admin.SimpleListFilter
):
    title = "매핑 여부"
    parameter_name = "brand_mapping"

    def lookups(
        self,
        request,
        model_admin,
    ):
        return (
            ("mapped", "매핑 완료"),
            ("unmapped", "미매핑"),
        )

    def queryset(
        self,
        request,
        queryset,
    ):
        if self.value() == "mapped":
            return queryset.filter(
                brand__isnull=False,
            )

        if self.value() == "unmapped":
            return queryset.filter(
                brand__isnull=True,
            )

        return queryset


@admin.register(BrandSource)
class BrandSourceAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "source",
        "source_brand_id",
        "source_brand_name",
        "source_brand_name_en",
        "brand_name",
        "mapping_status",
        "mapping_method",
        "detected_count",
        "last_seen_at",
    )

    list_filter = (
        "source",
        BrandMappingFilter,
        "mapping_status",
        "mapping_method",
    )

    search_fields = (
        "source_brand_id",
        "source_brand_name",
        "source_brand_name_en",
        "normalized_name",
        "normalized_name_en",
        "brand__brand_code",
        "brand__name",
        "brand__english_name",
    )

    raw_id_fields = (
        "brand",
        "source",
    )

    list_select_related = (
        "brand",
        "source",
    )

    ordering = (
        "source",
        "source_brand_name",
    )

    list_per_page = 50

    readonly_fields = (
        "detected_count",
        "first_seen_at",
        "last_seen_at",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "플랫폼 브랜드 정보",
            {
                "fields": (
                    "source",
                    "source_brand_id",
                    "source_brand_name",
                    "normalized_name",
                    "source_brand_name_en",
                    "normalized_name_en",
                    "source_brand_url",
                ),
            },
        ),
        (
            "FEEDIT 브랜드 매핑",
            {
                "fields": (
                    "brand",
                    "mapping_status",
                    "mapping_method",
                    "mapping_confidence",
                ),
            },
        ),
        (
            "수집 이력",
            {
                "fields": (
                    "detected_count",
                    "first_seen_at",
                    "last_seen_at",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(
        description="표준 브랜드",
        ordering="brand__name",
    )
    def brand_name(self, obj):
        if not obj.brand_id:
            return "❌ 미매핑"

        return (
            f"{obj.brand.name} "
            f"({obj.brand.brand_code})"
        )


# ====================================================