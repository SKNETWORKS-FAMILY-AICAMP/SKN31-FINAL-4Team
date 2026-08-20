from django.contrib import admin

from .models import (
    NaverBlogPost,
    NaverBlogPostKeywordMatch,
    NaverSearchTrendDaily,
    NaverShoppingTrendDaily,
    TrendKeyword,
)

admin.site.register(TrendKeyword)
admin.site.register(NaverBlogPost)
admin.site.register(NaverBlogPostKeywordMatch)
admin.site.register(NaverSearchTrendDaily)
admin.site.register(NaverShoppingTrendDaily)
