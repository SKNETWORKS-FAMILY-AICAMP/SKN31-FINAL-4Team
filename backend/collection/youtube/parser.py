from __future__ import annotations

import re

from .constants import (
    SHORTS_MAX_SECONDS,
    WATCH_URL,
)
from .exceptions import (
    YoutubeParseError,
)


# PT1H2M10S / PT45S / P1DT2H 형태를 초로 바꾼다.
_DURATION_PATTERN = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?$"
)


class YoutubeParser:

    @classmethod
    def parse_channel(
        cls,
        item: dict,
        *,
        seed: dict | None = None,
    ) -> dict:

        if not isinstance(
            item,
            dict,
        ):
            raise YoutubeParseError(
                "채널 응답이 dict가 아닙니다."
            )

        channel_id = item.get("id")

        if not channel_id:
            raise YoutubeParseError(
                "channel_id가 없습니다."
            )

        seed = seed or {}

        snippet = cls._dict(
            item.get("snippet")
        )

        statistics = cls._dict(
            item.get("statistics")
        )

        content_details = cls._dict(
            item.get("contentDetails")
        )

        branding_settings = cls._dict(
            item.get("brandingSettings")
        )

        related_playlists = cls._dict(
            content_details.get(
                "relatedPlaylists"
            )
        )

        thumbnails = cls._dict(
            snippet.get("thumbnails")
        )

        return {
            "channel_id": channel_id,

            "name": (
                snippet.get("title")
            ),

            "handle": (
                snippet.get("customUrl")
            ),

            "channel_url": (
                f"https://www.youtube.com/channel/"
                f"{channel_id}"
            ),

            "profile_image_url": (
                cls._best_thumbnail(
                    thumbnails
                )
            ),

            "description": (
                snippet.get(
                    "description"
                )
            ),

            "published_at": (
                snippet.get(
                    "publishedAt"
                )
            ),

            "country": (
                snippet.get(
                    "country"
                )
            ),

            "statistics": {
                "subscriber_count": (
                    cls._to_int(
                        statistics.get(
                            "subscriberCount"
                        )
                    )
                ),

                "video_count": (
                    cls._to_int(
                        statistics.get(
                            "videoCount"
                        )
                    )
                ),

                "view_count": (
                    cls._to_int(
                        statistics.get(
                            "viewCount"
                        )
                    )
                ),

                "hidden_subscriber_count": (
                    statistics.get(
                        "hiddenSubscriberCount"
                    )
                ),
            },

            "content_details": {
                "uploads_playlist_id": (
                    related_playlists.get(
                        "uploads"
                    )
                ),

                "likes_playlist_id": (
                    related_playlists.get(
                        "likes"
                    )
                ),
            },

            "branding_settings": (
                branding_settings
            ),

            # 우리가 직접 선정한 seed 정보.
            # YouTube API 정보와 구분해서 보존.
            "seed": {
                "name": (
                    seed.get("name")
                ),

                "gender": (
                    seed.get("gender")
                ),

                "fashion_filter": (
                    seed.get(
                        "fashion_filter"
                    )
                ),

                "handle": (
                    seed.get("handle")
                ),
            },
        }

    # ============================================================
    # PLAYLIST ITEMS
    # ============================================================

    @classmethod
    def parse_playlist_items(
        cls,
        body: dict,
    ) -> list[dict]:
        """
        playlistItems 응답에서 video_id 목록만 뽑는다.

        업로드 재생목록은 최신순이므로
        앞에서부터 N개를 자르면 최근 영상 N개가 된다.
        """

        items = (
            cls._dict(body).get("items")
            or []
        )

        results: list[dict] = []

        for item in items:

            if not isinstance(item, dict):
                continue

            content_details = cls._dict(
                item.get("contentDetails")
            )

            video_id = content_details.get(
                "videoId"
            )

            if not video_id:
                continue

            results.append(
                {
                    "video_id": video_id,
                    "published_at": (
                        content_details.get(
                            "videoPublishedAt"
                        )
                    ),
                }
            )

        return results

    # ============================================================
    # VIDEO
    # ============================================================

    @classmethod
    def parse_video(
        cls,
        item: dict,
        *,
        channel_id: str | None = None,
    ) -> dict:

        if not isinstance(item, dict):
            raise YoutubeParseError(
                "영상 응답이 dict가 아닙니다."
            )

        video_id = item.get("id")

        if not video_id:
            raise YoutubeParseError(
                "video_id가 없습니다."
            )

        snippet = cls._dict(
            item.get("snippet")
        )

        statistics = cls._dict(
            item.get("statistics")
        )

        content_details = cls._dict(
            item.get("contentDetails")
        )

        status = cls._dict(
            item.get("status")
        )

        thumbnails = cls._dict(
            snippet.get("thumbnails")
        )

        duration_seconds = (
            cls.parse_duration(
                content_details.get("duration")
            )
        )

        return {
            "video_id": video_id,

            "channel_id": (
                snippet.get("channelId")
                or channel_id
            ),

            "channel_title": (
                snippet.get("channelTitle")
            ),

            "title": snippet.get("title"),

            "description": (
                snippet.get("description")
            ),

            "video_url": (
                WATCH_URL.format(
                    video_id=video_id
                )
            ),

            "thumbnail_url": (
                cls._best_thumbnail(
                    thumbnails
                )
            ),

            "published_at": (
                snippet.get("publishedAt")
            ),

            "duration_seconds": (
                duration_seconds
            ),

            "content_type": (
                cls.classify_content_type(
                    duration_seconds
                )
            ),

            "statistics": {
                "view_count": cls._to_int(
                    statistics.get("viewCount")
                ),
                "like_count": cls._to_int(
                    statistics.get("likeCount")
                ),
                "comment_count": cls._to_int(
                    statistics.get("commentCount")
                ),
                "favorite_count": cls._to_int(
                    statistics.get("favoriteCount")
                ),
            },

            "tags": snippet.get("tags") or [],

            "category_id": (
                snippet.get("categoryId")
            ),

            "default_audio_language": (
                snippet.get("defaultAudioLanguage")
                or snippet.get("defaultLanguage")
            ),

            # 공식 자막 존재 여부.
            # 이후 자막 수집 우선순위 판단에 쓴다.
            "has_caption": (
                str(
                    content_details.get("caption")
                ).lower()
                == "true"
            ),

            "definition": (
                content_details.get("definition")
            ),

            "privacy_status": (
                status.get("privacyStatus")
            ),

            "made_for_kids": (
                status.get("madeForKids")
            ),
        }

    # ============================================================
    # COMMENT
    # ============================================================

    @classmethod
    def parse_comment_threads(
        cls,
        body: dict,
        *,
        video_id: str,
    ) -> list[dict]:
        """
        commentThreads 응답을 평평한 댓글 리스트로 만든다.

        원댓글과 대댓글을 같은 형태로 담고
        is_reply / parent_id로만 구분한다.
        (TextDocument.DocumentType에 REPLY가 없으므로
         모델 변경 없이 메타데이터로 구분한다.)
        """

        items = (
            cls._dict(body).get("items")
            or []
        )

        results: list[dict] = []

        for item in items:

            if not isinstance(item, dict):
                continue

            snippet = cls._dict(
                item.get("snippet")
            )

            top_level = cls._dict(
                snippet.get("topLevelComment")
            )

            parsed = cls.parse_comment(
                top_level,
                video_id=video_id,
                is_reply=False,
                parent_id=None,
            )

            if parsed is None:
                continue

            parsed["reply_count"] = (
                cls._to_int(
                    snippet.get("totalReplyCount")
                )
                or 0
            )

            results.append(parsed)

            # 대댓글은 같은 응답에 최대 5건까지
            # 추가 쿼터 없이 딸려온다.
            replies = cls._dict(
                item.get("replies")
            )

            for reply in (
                replies.get("comments") or []
            ):
                parsed_reply = cls.parse_comment(
                    reply,
                    video_id=video_id,
                    is_reply=True,
                    parent_id=parsed["comment_id"],
                )

                if parsed_reply is not None:
                    results.append(parsed_reply)

        return results

    @classmethod
    def parse_comment(
        cls,
        item: dict,
        *,
        video_id: str,
        is_reply: bool = False,
        parent_id: str | None = None,
    ) -> dict | None:

        if not isinstance(item, dict):
            return None

        comment_id = item.get("id")

        if not comment_id:
            return None

        snippet = cls._dict(
            item.get("snippet")
        )

        text = (
            snippet.get("textOriginal")
            or snippet.get("textDisplay")
            or ""
        )

        text = str(text).strip()

        if not text:
            return None

        return {
            "comment_id": comment_id,
            "video_id": video_id,
            "text": text,

            "author": snippet.get(
                "authorDisplayName"
            ),

            "author_channel_id": (
                cls._dict(
                    snippet.get("authorChannelId")
                ).get("value")
            ),

            "like_count": cls._to_int(
                snippet.get("likeCount")
            ),

            "published_at": snippet.get(
                "publishedAt"
            ),

            "updated_at": snippet.get(
                "updatedAt"
            ),

            "is_reply": is_reply,
            "parent_id": parent_id,
            "reply_count": 0,
        }

    # ============================================================
    # DURATION
    # ============================================================

    @staticmethod
    def parse_duration(
        value,
    ) -> int | None:
        """
        ISO8601 duration을 초로 변환한다.

            PT8M32S   -> 512
            PT45S     -> 45
            PT1H2M10S -> 3730
        """

        if not value:
            return None

        match = _DURATION_PATTERN.match(
            str(value).strip()
        )

        if not match:
            return None

        parts = match.groupdict()

        try:
            days = int(parts.get("days") or 0)
            hours = int(parts.get("hours") or 0)
            minutes = int(parts.get("minutes") or 0)
            seconds = float(parts.get("seconds") or 0)

        except (TypeError, ValueError):
            return None

        total = (
            days * 86400
            + hours * 3600
            + minutes * 60
            + seconds
        )

        return int(total)

    # ============================================================
    # CONTENT TYPE
    # ============================================================

    @staticmethod
    def classify_content_type(
        duration_seconds,
    ) -> str:
        """
        YouTube API는 쇼츠 여부를 제공하지 않는다.
        길이로 추정하며, 길이를 모르면 VIDEO로 둔다.
        """

        if duration_seconds is None:
            return "VIDEO"

        if duration_seconds <= SHORTS_MAX_SECONDS:
            return "SHORTS"

        return "VIDEO"

    @staticmethod
    def _dict(
        value,
    ) -> dict:
        return (
            value
            if isinstance(
                value,
                dict,
            )
            else {}
        )

    @staticmethod
    def _best_thumbnail(
        thumbnails: dict,
    ) -> str | None:

        for key in (
            "maxres",
            "standard",
            "high",
            "medium",
            "default",
        ):
            item = thumbnails.get(
                key
            )

            if not isinstance(
                item,
                dict,
            ):
                continue

            url = item.get("url")

            if url:
                return url

        return None

    @staticmethod
    def _to_int(
        value,
    ) -> int | None:

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None