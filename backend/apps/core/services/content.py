from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import (
    ContentItem,
    ContentProfile,
    ContentSnapshot,
    Source,
    TextDocument,
)


GENDER_MAP = {
    "남성": ContentProfile.Gender.MALE,
    "MALE": ContentProfile.Gender.MALE,
    "M": ContentProfile.Gender.MALE,

    "여성": ContentProfile.Gender.FEMALE,
    "FEMALE": ContentProfile.Gender.FEMALE,
    "F": ContentProfile.Gender.FEMALE,

    "혼성": ContentProfile.Gender.MIXED,
    "MIXED": ContentProfile.Gender.MIXED,
}


def _normalize_gender(
    value,
) -> str:
    if value is None:
        return ContentProfile.Gender.UNKNOWN

    key = str(value).strip()

    if not key:
        return ContentProfile.Gender.UNKNOWN

    return GENDER_MAP.get(
        key.upper(),
        GENDER_MAP.get(
            key,
            ContentProfile.Gender.UNKNOWN,
        ),
    )


@transaction.atomic
def upsert_youtube_content_profile(
    *,
    source: Source,
    data: dict,
) -> ContentProfile:
    
    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "YouTube profile data는 dict여야 합니다."
        )

    channel_id = data.get(
        "channel_id"
    )

    if not channel_id:
        raise ValueError(
            "YouTube profile data에 channel_id가 없습니다."
        )

    seed = (
        data.get("seed")
        if isinstance(
            data.get("seed"),
            dict,
        )
        else {}
    )

    statistics = (
        data.get("statistics")
        if isinstance(
            data.get("statistics"),
            dict,
        )
        else {}
    )

    content_details = (
        data.get("content_details")
        if isinstance(
            data.get("content_details"),
            dict,
        )
        else {}
    )

    branding_settings = (
        data.get("branding_settings")
        if isinstance(
            data.get("branding_settings"),
            dict,
        )
        else {}
    )

    now = timezone.now()

    profile, created = (
        ContentProfile.objects
        .get_or_create(
            source=source,
            external_profile_id=str(
                channel_id
            ),
            defaults={
                "profile_type": (
                    "YOUTUBE_CHANNEL"
                ),
                "name": (
                    data.get("name")
                    or seed.get("name")
                    or str(channel_id)
                ),
                "gender": (
                    _normalize_gender(
                        seed.get("gender")
                    )
                ),
                "first_seen_at": now,
                "last_seen_at": now,
                "status": "ACTIVE",
            },
        )
    )

    current_metadata = (
        profile.platform_metadata
        if isinstance(
            profile.platform_metadata,
            dict,
        )
        else {}
    )

    platform_metadata = {
        **current_metadata,

        # YouTube 채널 기본 메타
        "country": data.get(
            "country"
        ),
        "published_at": data.get(
            "published_at"
        ),

        # YouTube statistics
        "subscriber_count": statistics.get(
            "subscriber_count"
        ),
        "video_count": statistics.get(
            "video_count"
        ),
        "view_count": statistics.get(
            "view_count"
        ),
        "hidden_subscriber_count": (
            statistics.get(
                "hidden_subscriber_count"
            )
        ),

        # uploads playlist 등
        "uploads_playlist_id": (
            content_details.get(
                "uploads_playlist_id"
            )
        ),
        "likes_playlist_id": (
            content_details.get(
                "likes_playlist_id"
            )
        ),

        # YouTube 원본 branding 정보
        "branding_settings": (
            branding_settings
        ),

        # FEEDIT seed 정보
        "fashion_filter": seed.get(
            "fashion_filter"
        ),
        "seed_name": seed.get(
            "name"
        ),
        "seed_handle": seed.get(
            "handle"
        ),
    }

    profile.profile_type = (
        "YOUTUBE_CHANNEL"
    )

    profile.name = (
        data.get("name")
        or seed.get("name")
        or str(channel_id)
    )

    profile.gender = (
        _normalize_gender(
            seed.get("gender")
        )
    )

    profile.handle = data.get(
        "handle"
    )

    profile.profile_url = (
        data.get("channel_url")
    )

    profile.profile_image_url = (
        data.get(
            "profile_image_url"
        )
    )

    profile.description = data.get(
        "description"
    )

    profile.platform_metadata = (
        platform_metadata
    )

    if (
        created
        or profile.first_seen_at is None
    ):
        profile.first_seen_at = now

    profile.last_seen_at = now
    profile.status = "ACTIVE"

    profile.save(
        update_fields=[
            "profile_type",
            "name",
            "gender",
            "handle",
            "profile_url",
            "profile_image_url",
            "description",
            "platform_metadata",
            "first_seen_at",
            "last_seen_at",
            "status",
            "updated_at",
        ]
    )

    return profile


# ============================================================
# VIDEO
# ============================================================


def _to_datetime(value):
    """
    YouTube가 주는 ISO8601 문자열을 datetime으로 바꾼다.
    파싱할 수 없으면 None.
    """

    if value is None:
        return None

    if hasattr(value, "tzinfo"):
        return value

    text = str(value).strip()

    if not text:
        return None

    # '2026-09-05T09:00:00Z' 형태 대응
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    return parse_datetime(text)


def _observation_date(value):
    """
    관측 시각을 '그날 00:00(로컬 타임존)'으로 내린다.

    ContentSnapshot은 (content_item, observed_at) 유니크이므로
    초 단위 시각을 그대로 쓰면 실행할 때마다 새 행이 생긴다.
    수집 주기가 하루 1회이므로 날짜 단위로 맞춰
    같은 날 재실행은 갱신이 되게 한다.
    """

    moment = _to_datetime(value) or timezone.now()

    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)

    local = timezone.localtime(moment)

    return local.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _content_type(value) -> str:
    key = str(value or "").strip().upper()

    if key == ContentItem.ContentType.SHORTS:
        return ContentItem.ContentType.SHORTS

    return ContentItem.ContentType.VIDEO


@transaction.atomic
def upsert_youtube_content_item(
    *,
    source: Source,
    data: dict,
    profile: ContentProfile | None = None,
    observed_at=None,
) -> ContentItem:
    """
    영상 1건을 적재한다.

    ContentItem     : upsert (있으면 갱신)
    ContentSnapshot : observed_at(날짜) 기준으로 하루 1행
    """

    if not isinstance(data, dict):
        raise ValueError(
            "YouTube video data는 dict여야 합니다."
        )

    video_id = data.get("video_id")

    if not video_id:
        raise ValueError(
            "YouTube video data에 video_id가 없습니다."
        )

    now = timezone.now()

    observed_at = _observation_date(observed_at)

    statistics = (
        data.get("statistics")
        if isinstance(data.get("statistics"), dict)
        else {}
    )

    # --------------------------------------------------------
    # CONTENT ITEM
    # --------------------------------------------------------

    item, created = (
        ContentItem.objects
        .get_or_create(
            source=source,
            external_content_id=str(video_id),
            defaults={
                "content_type": _content_type(
                    data.get("content_type")
                ),
                "content_url": (
                    data.get("video_url") or ""
                ),
                "first_seen_at": now,
                "last_seen_at": now,
            },
        )
    )

    current_metadata = (
        item.platform_metadata
        if isinstance(item.platform_metadata, dict)
        else {}
    )

    item.platform_metadata = {
        **current_metadata,

        "channel_id": data.get("channel_id"),
        "channel_title": data.get("channel_title"),
        "tags": data.get("tags") or [],
        "category_id": data.get("category_id"),
        "default_audio_language": (
            data.get("default_audio_language")
        ),
        "has_caption": data.get("has_caption"),
        "definition": data.get("definition"),
        "privacy_status": data.get("privacy_status"),
        "made_for_kids": data.get("made_for_kids"),

        # 최신 지표 (추이는 ContentSnapshot에 쌓인다)
        "latest_statistics": {
            "view_count": statistics.get("view_count"),
            "like_count": statistics.get("like_count"),
            "comment_count": statistics.get(
                "comment_count"
            ),
            "observed_at": observed_at.isoformat(),
        },
    }

    if profile is not None:
        item.profile = profile

    item.content_type = _content_type(
        data.get("content_type")
    )

    item.title = data.get("title")

    item.description = data.get("description")

    item.content_url = (
        data.get("video_url")
        or item.content_url
        or ""
    )

    item.thumbnail_url = data.get("thumbnail_url")

    published_at = _to_datetime(
        data.get("published_at")
    )

    if published_at is not None:
        item.published_at = published_at

    item.duration_seconds = data.get(
        "duration_seconds"
    )

    if created or item.first_seen_at is None:
        item.first_seen_at = now

    item.last_seen_at = now

    item.save(
        update_fields=[
            "profile",
            "content_type",
            "title",
            "description",
            "content_url",
            "thumbnail_url",
            "published_at",
            "duration_seconds",
            "platform_metadata",
            "first_seen_at",
            "last_seen_at",
            "updated_at",
        ]
    )

    # --------------------------------------------------------
    # CONTENT SNAPSHOT
    #
    # 조회수처럼 매일 변하는 값은 여기에 누적한다.
    # (content_item, observed_at) 유니크라
    # 같은 날 재실행은 갱신으로 처리된다.
    # --------------------------------------------------------

    ContentSnapshot.objects.update_or_create(
        content_item=item,
        observed_at=observed_at,
        defaults={
            "view_count": statistics.get("view_count"),
            "like_count": statistics.get("like_count"),
            "comment_count": statistics.get(
                "comment_count"
            ),
            "platform_metrics": {
                "favorite_count": statistics.get(
                    "favorite_count"
                ),
            },
        },
    )

    return item


def upsert_youtube_content_items(
    *,
    source: Source,
    videos: list[dict],
    profile: ContentProfile | None = None,
    observed_at=None,
) -> dict:
    """
    영상 여러 건을 적재한다.

    한 건이 실패해도 나머지는 계속 적재하고,
    실패 내역만 모아서 돌려준다.
    """

    observed_at = _observation_date(observed_at)

    created_ids: list[int] = []
    errors: list[dict] = []

    for data in videos or []:

        try:
            item = upsert_youtube_content_item(
                source=source,
                data=data,
                profile=profile,
                observed_at=observed_at,
            )

            created_ids.append(item.id)

        except Exception as exc:
            errors.append(
                {
                    "video_id": (
                        data.get("video_id")
                        if isinstance(data, dict)
                        else None
                    ),
                    "error_type": (
                        exc.__class__.__name__
                    ),
                    "error_message": str(exc),
                }
            )

    return {
        "observed_at": observed_at,
        "content_item_ids": created_ids,
        "success_count": len(created_ids),
        "failure_count": len(errors),
        "errors": errors,
    }


# ============================================================
# COMMENT
# ============================================================


@transaction.atomic
def upsert_youtube_comments(
    *,
    source: Source,
    content_item: ContentItem,
    comments: list[dict],
) -> dict:
    """
    한 영상의 댓글을 TextDocument에 적재한다.

    댓글 1건 = 1행.
    원댓글과 대댓글 모두 document_type=COMMENT 이며
    analysis_metadata.is_reply / parent_id 로 구분한다.

    (source, external_id) 조합으로 중복을 막는다.
    유니크 제약이 없으므로 조회 후 분기한다.
    """

    rows = [
        c
        for c in (comments or [])
        if isinstance(c, dict) and c.get("comment_id")
    ]

    if not rows:
        return {
            "created": 0,
            "updated": 0,
            "failed": 0,
            "errors": [],
        }

    comment_ids = [
        str(c["comment_id"])
        for c in rows
    ]

    existing = {
        doc.external_id: doc
        for doc in TextDocument.objects.filter(
            source=source,
            document_type=(
                TextDocument.DocumentType.COMMENT
            ),
            external_id__in=comment_ids,
        )
    }

    to_create: list[TextDocument] = []
    updated = 0
    failed = 0
    errors: list[dict] = []

    for data in rows:

        try:
            comment_id = str(data["comment_id"])

            body = str(data.get("text") or "").strip()

            if not body:
                continue

            metadata = {
                "author": data.get("author"),
                "author_channel_id": data.get(
                    "author_channel_id"
                ),
                "like_count": data.get("like_count"),
                "published_at": data.get(
                    "published_at"
                ),
                "updated_at": data.get("updated_at"),
                "is_reply": bool(
                    data.get("is_reply")
                ),
                "parent_id": data.get("parent_id"),
                "reply_count": data.get(
                    "reply_count"
                ),
                "video_id": data.get("video_id"),
            }

            document = existing.get(comment_id)

            if document is None:
                to_create.append(
                    TextDocument(
                        source=source,
                        content_item=content_item,
                        document_type=(
                            TextDocument
                            .DocumentType
                            .COMMENT
                        ),
                        external_id=comment_id,
                        body=body,
                        language="ko",
                        analysis_metadata=metadata,
                        analysis_status=(
                            TextDocument
                            .AnalysisStatus
                            .PENDING
                        ),
                    )
                )

            else:
                # 이미 있는 댓글은 본문과 좋아요 수만 갱신.
                # 분석 결과(sentiment_score 등)는 건드리지 않는다.
                document.body = body
                document.content_item = content_item

                current = (
                    document.analysis_metadata
                    if isinstance(
                        document.analysis_metadata,
                        dict,
                    )
                    else {}
                )

                document.analysis_metadata = {
                    **current,
                    **metadata,
                }

                document.save(
                    update_fields=[
                        "body",
                        "content_item",
                        "analysis_metadata",
                        "updated_at",
                    ]
                )

                updated += 1

        except Exception as exc:
            failed += 1
            errors.append(
                {
                    "comment_id": data.get(
                        "comment_id"
                    ),
                    "error_type": (
                        exc.__class__.__name__
                    ),
                    "error_message": str(exc),
                }
            )

    created = 0

    if to_create:
        TextDocument.objects.bulk_create(
            to_create,
            batch_size=500,
        )
        created = len(to_create)

    return {
        "created": created,
        "updated": updated,
        "failed": failed,
        "errors": errors,
    }
