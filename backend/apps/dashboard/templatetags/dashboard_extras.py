"""대시보드 전용 템플릿 필터."""

import json
import re

from django import template

from apps.dashboard.security import (
    dashboard_operator_allowed,
    dashboard_session_age,
    otp_required,
    otp_verified,
)

register = template.Library()


@register.simple_tag(takes_context=True)
def dashboard_session_seconds(context):
    """상단바 카운트다운의 시작값을 반환한다."""

    request = context.get("request")
    if request is None or not dashboard_operator_allowed(getattr(request, "user", None)):
        return 0
    if otp_required() and not otp_verified(request):
        return 0
    return dashboard_session_age()


# 유튜브 썸네일 파일명 → mqdefault(320x180, 약 10KB)로 낮춘다.
_YT_HOSTS = ("i.ytimg.com", "img.youtube.com", "i9.ytimg.com")
_YT_PATTERN = re.compile(
    r"/(maxresdefault|sddefault|hq720|hqdefault|mqdefault|default)\.(jpg|webp)"
)


@register.filter
def small_thumb(url):
    """목록용 경량 썸네일 URL로 바꾼다.

    원본 해상도를 그대로 40장씩 받으면 목록이 느려진다.
    플랫폼이 저해상도 변형을 제공하면 그쪽을 쓴다.
    """

    if not url:
        return url

    text = str(url)

    # 유튜브: 파일명만 바꾸면 저해상도 변형이 나온다.
    if any(host in text for host in _YT_HOSTS):
        return _YT_PATTERN.sub("/mqdefault.jpg", text)

    # 무신사: 쿼리 파라미터로 리사이즈를 지원한다.
    if "image.msscdn.net" in text and "?" not in text:
        return text + "?w=120"

    return text


# ContentItem.analysis_tags(JSONB)를 관리자 화면에서 항상 같은 순서로
# 읽을 수 있게 만든다. PostgreSQL JSONB는 키 순서를 보존하지 않는다.
TAG_SLOTS = (
    ("item", "아이템"),
    ("style", "스타일"),
    ("material", "소재"),
    ("detail", "디테일"),
    ("color", "색상"),
    ("tpo", "TPO"),
    ("brand", "브랜드"),
)


@register.filter
def tag_slots(tags):
    """태그 JSONB를 고정된 슬롯 순서의 (라벨, 값 목록)으로 반환한다."""

    if not isinstance(tags, dict):
        tags = {}
    return [(label, tags.get(key) or []) for key, label in TAG_SLOTS]


@register.filter
def tag_summary(tags, limit=6):
    """목록에서 빠르게 확인할 대표 태그를 중복 없이 반환한다."""

    if not isinstance(tags, dict):
        return []

    picked = []
    for key in ("item", "style", "brand", "color", "material", "tpo"):
        for value in tags.get(key) or []:
            if value not in picked:
                picked.append(value)
            if len(picked) >= int(limit):
                return picked
    return picked


@register.filter
def tag_count(tags):
    """사전 슬롯에 저장된 태그의 총개수를 반환한다."""

    if not isinstance(tags, dict):
        return 0
    return sum(len(tags.get(key) or []) for key, _ in TAG_SLOTS)


@register.filter
def get_key(value, key):
    """템플릿에서 JSONB/dict 키를 안전하게 조회한다."""

    if isinstance(value, dict):
        return value.get(key)
    return None


@register.filter
def pretty_json(value):
    """JSONField 값을 관리자 화면에서 읽기 좋은 문자열로 표시한다."""

    if value in (None, "", {}, []):
        return ""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
            default=str,
        )
    except (TypeError, ValueError):
        return str(value)
