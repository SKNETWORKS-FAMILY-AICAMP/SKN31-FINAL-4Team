# backend/apps/core/admin.py

from django.contrib import admin, messages
from django.apps import apps
from django.db import models
from django.urls import path, reverse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils.html import format_html

from apps.core.models import (
    Brand,
    BrandSource,
)

from django.contrib import admin

from apps.core.models import Category
from apps.core.models import CrawlTarget
from apps.core.tasks import run_live_target


# ============================================================
# COMMON ADMIN
# ============================================================


class FeeditModelAdmin(admin.ModelAdmin):
    """
    core 앱의 모델을 기본 Django Admin에서
    최대한 편하게 확인하기 위한 공통 Admin.
    """

    list_per_page = 50
    save_on_top = True

    def get_list_display(self, request):
        field_names = []

        for field in self.model._meta.fields:
            if isinstance(
                field,
                (
                    models.JSONField,
                    models.TextField,
                    models.BinaryField,
                ),
            ):
                continue

            field_names.append(field.name)

        if "id" in field_names:
            field_names.remove("id")
            field_names.insert(0, "id")

        return field_names[:8]

    def get_search_fields(self, request):
        search_fields = []

        preferred = [
            "name",
            "code",
            "title",
            "external_id",
            "source_category_id",
            "source_category_name",
            "source_brand_id",
            "source_key",
            "source_name",
        ]

        model_fields = {
            field.name: field
            for field in self.model._meta.fields
        }

        for field_name in preferred:
            field = model_fields.get(field_name)

            if isinstance(
                field,
                (
                    models.CharField,
                    models.TextField,
                ),
            ):
                search_fields.append(field_name)

        return search_fields

    def get_list_filter(self, request):
        candidates = [
            "source",
            "status",
            "mapping_status",
            "mapping_type",
            "category_type",
            "document_type",
            "source_type",
            "run_type",
        ]

        model_fields = {
            field.name
            for field in self.model._meta.fields
        }

        return [
            field
            for field in candidates
            if field in model_fields
        ]

    def get_readonly_fields(
        self,
        request,
        obj=None,
    ):
        candidates = [
            "created_at",
            "updated_at",
            "collected_at",
        ]

        model_fields = {
            field.name
            for field in self.model._meta.fields
        }

        return [
            field
            for field in candidates
            if field in model_fields
        ]


# ============================================================
# BRAND SOURCE ADMIN
# ============================================================


@admin.register(BrandSource)
class BrandSourceAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "source",
        "source_brand_id",
        "name",
        "english_name",
        "detected_count",
        "mapping_status",
        "mapped_brand",
        "promote_button",
    )

    list_filter = (
        "source",
        "mapping_status",
        "country_code",
    )

    search_fields = (
        "source_brand_id",
        "name",
        "english_name",
        "brand__name",
        "brand__english_name",
        "brand__brand_code",
    )

    ordering = (
        "-detected_count",
        "-last_seen_at",
    )

    list_per_page = 50
    filter_horizontal = ("styles",)

    readonly_fields = (
        "source",
        "source_brand_id",
        "name",
        "english_name",
        "image_url",
        "country_code",
        "description",
        "target_gender",
        "target_age",
        "website_url",
        "source_profile_url",
        "attributes",
        "detected_count",
        "first_seen_at",
        "last_seen_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="FEEDIT 브랜드")
    def mapped_brand(self, obj):
        return obj.brand.name if obj.brand_id else "-"

    @admin.display(description="작업")
    def promote_button(self, obj):
        if obj.brand_id:
            return "매핑 완료"

        url = reverse(
            "admin:brand_source_promote",
            args=[obj.pk],
        )
        return format_html(
            '<a class="button" href="{}">브랜드 등록</a>',
            url,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:source_id>/promote/",
                self.admin_site.admin_view(self.promote_brand),
                name="brand_source_promote",
            ),
        ]
        return custom_urls + urls

    def promote_brand(self, request, source_id):
        brand_source = get_object_or_404(
            BrandSource,
            pk=source_id,
        )

        if brand_source.brand_id:
            messages.warning(
                request,
                "이미 FEEDIT 브랜드에 매핑되어 있습니다.",
            )
            return redirect(
                "admin:core_brandsource_changelist"
            )

        if request.method == "POST":
            action = request.POST.get("action")

            if action == "map_existing":
                brand = get_object_or_404(
                    Brand,
                    pk=request.POST.get("brand_id"),
                )

                brand_source.brand = brand
                brand_source.mapping_status = (
                    BrandSource.MappingStatus.MANUAL_MAPPED
                )
                brand_source.mapping_method = (
                    BrandSource.MappingMethod.MANUAL
                )
                brand_source.mapping_confidence = 1
                brand_source.save(
                    update_fields=[
                        "brand",
                        "mapping_status",
                        "mapping_method",
                        "mapping_confidence",
                        "updated_at",
                    ]
                )

                brand.source_count = (
                    BrandSource.objects
                    .filter(brand=brand)
                    .values("source_id")
                    .distinct()
                    .count()
                )
                brand.save(
                    update_fields=[
                        "source_count",
                        "updated_at",
                    ]
                )

                messages.success(
                    request,
                    f"{brand_source.name} → {brand.name} 매핑 완료",
                )
                return redirect(
                    "admin:core_brandsource_changelist"
                )

            if action == "create_new":
                brand_code = (
                    request.POST.get("brand_code") or ""
                ).strip().upper().replace(" ", "_").replace("-", "_")

                while "__" in brand_code:
                    brand_code = brand_code.replace("__", "_")

                if brand_code and not brand_code.startswith("BRAND_"):
                    brand_code = f"BRAND_{brand_code}"

                name = (
                    request.POST.get("name")
                    or brand_source.name
                    or ""
                ).strip()

                english_name = (
                    request.POST.get("english_name")
                    or brand_source.english_name
                    or ""
                ).strip()

                category_id = (
                    request.POST.get("category_id") or ""
                ).strip()

                if not brand_code or not name:
                    messages.error(
                        request,
                        "브랜드 코드와 브랜드명은 필수입니다.",
                    )
                elif Brand.objects.filter(
                    brand_code__iexact=brand_code
                ).exists():
                    messages.error(
                        request,
                        f"{brand_code} 코드가 이미 존재합니다.",
                    )
                else:
                    category = None
                    if category_id:
                        category = get_object_or_404(
                            Category,
                            pk=category_id,
                            category_type=Category.CategoryType.BRAND,
                        )

                    brand = Brand.objects.create(
                        brand_code=brand_code,
                        name=name,
                        english_name=english_name or None,
                        image_url=brand_source.image_url,
                        category=category,
                        country_code=brand_source.country_code,
                        description=brand_source.description,
                        target_gender=brand_source.target_gender,
                        target_age=brand_source.target_age,
                        website_url=brand_source.website_url,
                        is_verified=True,
                        source_count=1,
                        status=Brand.Status.ACTIVE,
                    )
                    brand.styles.set(brand_source.styles.all())

                    brand_source.brand = brand
                    brand_source.mapping_status = (
                        BrandSource.MappingStatus.MANUAL_MAPPED
                    )
                    brand_source.mapping_method = (
                        BrandSource.MappingMethod.MANUAL
                    )
                    brand_source.mapping_confidence = 1
                    brand_source.save(
                        update_fields=[
                            "brand",
                            "mapping_status",
                            "mapping_method",
                            "mapping_confidence",
                            "updated_at",
                        ]
                    )

                    messages.success(
                        request,
                        f"{brand.name} 신규 등록 및 매핑 완료",
                    )
                    return redirect(
                        "admin:core_brandsource_changelist"
                    )

        brands = (
            Brand.objects
            .filter(status=Brand.Status.ACTIVE)
            .order_by("name")
        )
        brand_categories = (
            Category.objects
            .filter(
                category_type=Category.CategoryType.BRAND,
                status=Category.Status.ACTIVE,
            )
            .order_by("sort_order", "name")
        )

        context = {
            **self.admin_site.each_context(request),
            "title": "플랫폼 브랜드 등록 / 매핑",
            "brand_source": brand_source,
            "brands": brands,
            "brand_categories": brand_categories,
        }

        return render(
            request,
            "admin/core/brandsource/promote.html",
            context,
        )


# ============================================================
# REGISTER ALL CORE MODELS
# BrandSource는 위에서 커스텀 등록했으므로 제외
# ============================================================


core_app = apps.get_app_config(
    "core"
)

custom_registered_models = {
    BrandSource,
}


for model in core_app.get_models():

    if model in custom_registered_models:
        continue

    try:
        admin.site.register(
            model,
            FeeditModelAdmin,
        )

    except admin.sites.AlreadyRegistered:
        pass


# ============================================================
# ADMIN SITE TITLE
# ============================================================

admin.site.site_header = "FEEDIT Admin"
admin.site.site_title = "FEEDIT"
admin.site.index_title = "FEEDIT 데이터 관리"