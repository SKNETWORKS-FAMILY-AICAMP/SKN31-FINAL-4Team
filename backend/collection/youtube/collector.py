from __future__ import annotations

from .client import (
    YoutubeClient,
)
from .constants import (
    CHANNELS_API_URL,
)
from .exceptions import (
    YoutubeCollectError,
)
from .parser import (
    YoutubeParser,
)


class YoutubeCollector:

    def __init__(
        self,
        *,
        api_key: str,
    ):
        self.client = YoutubeClient(
            api_key=api_key,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        self.close()

    # ============================================================
    # PROFILE
    # ============================================================

    def collect_profile(
        self,
        channel_id: str,
        *,
        seed: dict | None = None,
    ) -> dict:

        body = self.client.get_json(
            CHANNELS_API_URL,

            params={
                "part": (
                    "snippet,"
                    "statistics,"
                    "contentDetails,"
                    "brandingSettings"
                ),

                "id": (
                    channel_id
                ),
            },
        )

        items = (
            body.get("items")
            or []
        )

        if not items:
            raise YoutubeCollectError(
                "YouTube 채널을 찾을 수 없습니다: "
                f"{channel_id}"
            )

        return YoutubeParser.parse_channel(
            items[0],
            seed=seed,
        )

    # ============================================================
    # MULTIPLE PROFILES
    # ============================================================

    def collect_profiles(
        self,
        seeds: list[dict],
    ) -> dict:

        profiles = []
        errors = []

        for seed in seeds:

            channel_id = (
                seed.get(
                    "channel_id"
                )
            )

            if not channel_id:
                errors.append(
                    {
                        "seed": seed,
                        "error": (
                            "channel_id 없음"
                        ),
                    }
                )
                continue

            try:
                profile = (
                    self.collect_profile(
                        channel_id,
                        seed=seed,
                    )
                )

                profiles.append(
                    profile
                )

            except Exception as exc:
                errors.append(
                    {
                        "channel_id": (
                            channel_id
                        ),

                        "seed_name": (
                            seed.get(
                                "name"
                            )
                        ),

                        "error_type": (
                            exc
                            .__class__
                            .__name__
                        ),

                        "error_message": (
                            str(exc)
                        ),
                    }
                )

        return {
            "profiles": profiles,

            "summary": {
                "requested_count": (
                    len(seeds)
                ),

                "success_count": (
                    len(profiles)
                ),

                "failure_count": (
                    len(errors)
                ),
            },

            "errors": errors,
        }