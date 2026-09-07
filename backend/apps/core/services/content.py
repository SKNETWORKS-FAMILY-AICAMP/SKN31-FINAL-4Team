from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    ContentProfile,
    Source,
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
