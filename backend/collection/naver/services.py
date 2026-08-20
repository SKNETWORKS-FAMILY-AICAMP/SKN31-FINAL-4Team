from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.html import strip_tags

from apps.naver.models import (
    Audience,
    NaverBlogPost,
    NaverBlogPostKeywordMatch,
    NaverSearchTrendDaily,
    NaverShoppingTrendDaily,
    TrendKeyword,
)

from .api import get_blog, get_search_trend, get_shopping_trend
from .client import NaverApiClient
from .keywords import AUDIENCE_FILTERS, SHOPPING_CATEGORIES, SHOPPING_CATEGORY_CODE
from .query_builder import chunks, keyword_group, make_blog_queries
from .request_cache import mark_collected_today, was_collected_today


def _date_range() -> tuple[str, str]:
    today = timezone.localdate()
    return str(today), str(today)


def collect_blog(client: NaverApiClient | None = None) -> dict[str, int]:
    client = client or NaverApiClient()
    today = timezone.localdate()
    stats = {"queries": 0, "api_skipped": 0, "created": 0, "duplicates": 0, "outside_today": 0}
    for keyword in TrendKeyword.objects.filter(is_active=True):
        for query in make_blog_queries(keyword.name, keyword.category):
            request_payload = {"query": query, "display": 100, "sort": "date"}
            if was_collected_today("blog", request_payload):
                stats["api_skipped"] += 1
                continue
            stats["queries"] += 1
            for item in get_blog(client, query):
                link = item.get("link", "")
                if not link:
                    continue
                post_date = parse_date(item.get("postdate", ""))
                if post_date != today:
                    stats["outside_today"] += 1
                    continue
                post, created = NaverBlogPost.objects.get_or_create(
                    link=link,
                    defaults={
                        "title": strip_tags(item.get("title", "")),
                        "description": strip_tags(item.get("description", "")),
                        "blogger_name": item.get("bloggername", ""),
                        "blogger_link": item.get("bloggerlink", ""),
                        "post_date": post_date,
                        "collected_at": timezone.now(),
                    },
                )
                stats["created" if created else "duplicates"] += 1
                NaverBlogPostKeywordMatch.objects.get_or_create(
                    post=post, keyword=keyword, query=query, defaults={"collected_at": timezone.now()}
                )
            mark_collected_today("blog", request_payload)
    return stats


def collect_search_trends(client: NaverApiClient | None = None) -> dict[str, int]:
    client = client or NaverApiClient()
    start_date, end_date = _date_range()
    keywords = list(TrendKeyword.objects.filter(is_active=True))
    stats = {"batches": 0, "api_skipped": 0, "saved": 0}
    for audience, filters in AUDIENCE_FILTERS.items():
        for batch in chunks(keywords):
            groups = [keyword_group(item.name, item.aliases) for item in batch]
            request_payload = {
                "startDate": start_date, "endDate": end_date, "timeUnit": "date",
                "keywordGroups": groups, "ages": filters["search_ages"],
            }
            if was_collected_today("search-trend", request_payload):
                stats["api_skipped"] += 1
                continue
            results = get_search_trend(client, request_payload)
            stats["batches"] += 1
            keyword_by_name = {item.name: item for item in batch}
            for result in results:
                keyword = keyword_by_name.get(result.get("title"))
                if keyword is None:
                    continue
                for point in result.get("data", []):
                    date = parse_date(point.get("period", ""))
                    if not date:
                        continue
                    NaverSearchTrendDaily.objects.update_or_create(
                        keyword=keyword, audience=audience, date=date,
                        defaults={"search_ratio": point["ratio"], "collected_at": timezone.now()},
                    )
                    stats["saved"] += 1
            mark_collected_today("search-trend", request_payload)
    return stats


def collect_shopping_trends(client: NaverApiClient | None = None) -> dict[str, int]:
    client = client or NaverApiClient()
    start_date, end_date = _date_range()
    keywords = list(TrendKeyword.objects.filter(is_active=True, category__in=SHOPPING_CATEGORIES))
    stats = {"batches": 0, "api_skipped": 0, "saved": 0}
    for audience, filters in AUDIENCE_FILTERS.items():
        for batch in chunks(keywords):
            request_payload = {
                "startDate": start_date, "endDate": end_date, "timeUnit": "date",
                "category": SHOPPING_CATEGORY_CODE,
                "keyword": [{"name": item.name, "param": [item.name]} for item in batch],
                "ages": filters["shopping_ages"],
            }
            if was_collected_today("shopping", request_payload):
                stats["api_skipped"] += 1
                continue
            results = get_shopping_trend(client, request_payload)
            stats["batches"] += 1
            keyword_by_name = {item.name: item for item in batch}
            for result in results:
                keyword = keyword_by_name.get(result.get("title"))
                if keyword is None:
                    continue
                for point in result.get("data", []):
                    date = parse_date(point.get("period", ""))
                    if not date:
                        continue
                    NaverShoppingTrendDaily.objects.update_or_create(
                        keyword=keyword, audience=audience, category_code=SHOPPING_CATEGORY_CODE, date=date,
                        defaults={"shopping_click_ratio": point["ratio"], "collected_at": timezone.now()},
                    )
                    stats["saved"] += 1
            mark_collected_today("shopping", request_payload)
    return stats
