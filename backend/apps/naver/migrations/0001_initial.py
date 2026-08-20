import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="NaverBlogPost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.TextField()), ("link", models.URLField(max_length=1000, unique=True)),
                ("description", models.TextField(blank=True)), ("blogger_name", models.CharField(blank=True, max_length=255)),
                ("blogger_link", models.URLField(blank=True, max_length=1000)),
                ("post_date", models.DateField(blank=True, null=True)), ("collected_at", models.DateTimeField()),
            ], options={"ordering": ["-post_date", "-collected_at"]},
        ),
        migrations.CreateModel(
            name="TrendKeyword",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("category", models.CharField(choices=[("STYLE", "스타일"), ("COLOR", "컬러"), ("FIT", "핏 / 실루엣"), ("TPO", "상황 / TPO"), ("SEASON", "계절 / 시즌"), ("OUTER", "아우터"), ("DRESS_SET", "원피스 / 셋업"), ("BOTTOM", "하의"), ("TOP", "상의")], max_length=20)),
                ("aliases", models.JSONField(blank=True, default=list)), ("is_active", models.BooleanField(default=True)),
                ("priority", models.IntegerField(default=0)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ], options={"ordering": ["category", "priority", "name"]},
        ),
        migrations.CreateModel(
            name="NaverShoppingTrendDaily",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("audience", models.CharField(choices=[("TEENS", "10대"), ("TWENTIES", "20대"), ("THIRTIES", "30대")], max_length=20)),
                ("category_code", models.CharField(max_length=30)), ("date", models.DateField()),
                ("shopping_click_ratio", models.FloatField()), ("collected_at", models.DateTimeField()),
                ("keyword", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_trends", to="naver.trendkeyword")),
            ],
        ),
        migrations.CreateModel(
            name="NaverSearchTrendDaily",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("audience", models.CharField(choices=[("TEENS", "10대"), ("TWENTIES", "20대"), ("THIRTIES", "30대")], max_length=20)),
                ("date", models.DateField()), ("search_ratio", models.FloatField()), ("collected_at", models.DateTimeField()),
                ("keyword", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="search_trends", to="naver.trendkeyword")),
            ],
        ),
        migrations.CreateModel(
            name="NaverBlogPostKeywordMatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query", models.CharField(max_length=255)), ("collected_at", models.DateTimeField()),
                ("keyword", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blog_matches", to="naver.trendkeyword")),
                ("post", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="keyword_matches", to="naver.naverblogpost")),
            ],
        ),
        migrations.AddConstraint(model_name="trendkeyword", constraint=models.UniqueConstraint(fields=("category", "name"), name="naver_unique_keyword")),
        migrations.AddIndex(model_name="naversearchtrenddaily", index=models.Index(fields=["audience", "date"], name="naver_naver_audienc_667e50_idx")),
        migrations.AddConstraint(model_name="naversearchtrenddaily", constraint=models.UniqueConstraint(fields=("keyword", "audience", "date"), name="naver_unique_search_trend")),
        migrations.AddIndex(model_name="navershoppingtrenddaily", index=models.Index(fields=["audience", "date"], name="naver_naver_audienc_f50e40_idx")),
        migrations.AddConstraint(model_name="navershoppingtrenddaily", constraint=models.UniqueConstraint(fields=("keyword", "audience", "category_code", "date"), name="naver_unique_shopping_trend")),
        migrations.AddConstraint(model_name="naverblogpostkeywordmatch", constraint=models.UniqueConstraint(fields=("post", "keyword", "query"), name="naver_unique_blog_match")),
    ]
