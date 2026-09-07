from __future__ import annotations

from .exceptions import (
    YoutubeParseError,
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