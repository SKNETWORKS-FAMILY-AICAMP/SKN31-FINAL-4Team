"""대시보드 전용 템플릿 필터."""

import re

from django import template

register = template.Library()


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
