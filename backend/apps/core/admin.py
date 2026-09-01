from django.contrib import admin

from .models_dictionary import (
    Category,
    DictionaryTerm,
    Style,
    Brand,
)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "name",
        "parent",
        "level",
        "sort_order",
        "status",
        "updated_at",
    )

    list_filter = (
        "level",
        "status",
    )

    search_fields = (
        "code",
        "name",
    )

    ordering = (
        "level",
        "sort_order",
        "code",
    )

    list_select_related = (
        "parent",
    )


@admin.register(DictionaryTerm)
class DictionaryTermAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "term_code",
        "term_type",
        "canonical_name",
        "normalized_name",
        "english_name",
        "status",
        "updated_at",
    )

    list_filter = (
        "term_type",
        "status",
    )

    search_fields = (
        "term_code",
        "canonical_name",
        "normalized_name",
        "english_name",
    )

    ordering = (
        "term_type",
        "canonical_name",
    )

@admin.register(Style)
class StyleAdmin(admin.ModelAdmin):
    list_display = (
        "term_code",
        "canonical_name",
        "style_group",
        "is_core",
        "updated_at",
    )

    list_filter = (
        "style_group",
        "is_core",
    )

    search_fields = (
        "term__term_code",
        "term__canonical_name",
        "term__english_name",
    )

    ordering = (
        "term__term_code",
    )

    list_select_related = (
        "term",
    )

    @admin.display(description="용어 코드", ordering="term__term_code")
    def term_code(self, obj):
        return obj.term.term_code

    @admin.display(description="스타일명", ordering="term__canonical_name")
    def canonical_name(self, obj):
        return obj.term.canonical_name

    @admin.display(description="수정일시", ordering="term__updated_at")
    def updated_at(self, obj):
        return obj.term.updated_at


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "brand_code",
        "name",
        "english_name",
        "category",
        "country_code",
        "status",
        "updated_at",
    )

    list_filter = (
        "category",
        "country_code",
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

    list_select_related = (
        "category",
    )