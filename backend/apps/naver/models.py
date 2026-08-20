from django.db import models


class TrendKeyword(models.Model):
    class Category(models.TextChoices):
        STYLE = "STYLE", "스타일"
        COLOR = "COLOR", "컬러"
        FIT = "FIT", "핏 / 실루엣"
        TPO = "TPO", "상황 / TPO"
        SEASON = "SEASON", "계절 / 시즌"
        OUTER = "OUTER", "아우터"
        DRESS_SET = "DRESS_SET", "원피스 / 셋업"
        BOTTOM = "BOTTOM", "하의"
        TOP = "TOP", "상의"

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category.choices)
    aliases = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["category", "name"], name="naver_unique_keyword"),
        ]
        ordering = ["category", "priority", "name"]

    def __str__(self):
        return f"{self.category}: {self.name}"


class Audience(models.TextChoices):
    TEENS = "TEENS", "10대"
    TWENTIES = "TWENTIES", "20대"
    THIRTIES = "THIRTIES", "30대"


class NaverBlogPost(models.Model):
    title = models.TextField()
    link = models.URLField(max_length=1000, unique=True)
    description = models.TextField(blank=True)
    blogger_name = models.CharField(max_length=255, blank=True)
    blogger_link = models.URLField(max_length=1000, blank=True)
    post_date = models.DateField(null=True, blank=True)
    collected_at = models.DateTimeField()

    class Meta:
        ordering = ["-post_date", "-collected_at"]


class NaverBlogPostKeywordMatch(models.Model):
    post = models.ForeignKey(NaverBlogPost, on_delete=models.CASCADE, related_name="keyword_matches")
    keyword = models.ForeignKey(TrendKeyword, on_delete=models.CASCADE, related_name="blog_matches")
    query = models.CharField(max_length=255)
    collected_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "keyword", "query"], name="naver_unique_blog_match"),
        ]


class NaverApiRequest(models.Model):
    """A successfully processed NAVER API request for a single collection day."""

    source = models.CharField(max_length=30)
    request_hash = models.CharField(max_length=64)
    collection_date = models.DateField()
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "request_hash", "collection_date"],
                name="naver_unique_api_request",
            ),
        ]
        indexes = [
            models.Index(fields=["source", "collection_date"], name="naver_api_request_day_idx"),
        ]


class NaverSearchTrendDaily(models.Model):
    keyword = models.ForeignKey(TrendKeyword, on_delete=models.CASCADE, related_name="search_trends")
    audience = models.CharField(max_length=20, choices=Audience.choices)
    date = models.DateField()
    search_ratio = models.FloatField()
    collected_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["keyword", "audience", "date"], name="naver_unique_search_trend"),
        ]
        indexes = [
            models.Index(fields=["audience", "date"], name="naver_naver_audienc_667e50_idx"),
        ]


class NaverShoppingTrendDaily(models.Model):
    keyword = models.ForeignKey(TrendKeyword, on_delete=models.CASCADE, related_name="shopping_trends")
    audience = models.CharField(max_length=20, choices=Audience.choices)
    category_code = models.CharField(max_length=30)
    date = models.DateField()
    shopping_click_ratio = models.FloatField()
    collected_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["keyword", "audience", "category_code", "date"],
                name="naver_unique_shopping_trend",
            ),
        ]
        indexes = [
            models.Index(fields=["audience", "date"], name="naver_naver_audienc_f50e40_idx"),
        ]
