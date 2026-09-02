from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from apps.core.models import (
    CrawlTarget,
    Source,
)


class Command(BaseCommand):
    help = (
        "youtube_channels.json 기준으로 "
        "YOUTUBE CREATOR CrawlTarget 생성"
    )

    def add_arguments(
        self,
        parser,
    ):
        parser.add_argument(
            "json_path",
        )

    def handle(
        self,
        *args,
        **options,
    ):
        path = Path(
            options["json_path"]
        ).resolve()

        if not path.exists():
            raise CommandError(
                f"파일 없음: {path}"
            )

        with path.open(
            "r",
            encoding="utf-8",
        ) as f:
            seeds = json.load(f)

        if not isinstance(
            seeds,
            list,
        ):
            raise CommandError(
                "JSON 최상위는 list여야 합니다."
            )

        source, _ = (
            Source.objects
            .get_or_create(
                code="YOUTUBE",
                defaults={
                    "name": "YouTube",
                    "source_type": "CONTENT",
                    "base_url": (
                        "https://www.youtube.com"
                    ),
                    "collection_method": "API",
                    "status": "ACTIVE",
                },
            )
        )

        created_count = 0
        updated_count = 0

        for seed in seeds:

            channel_id = seed.get(
                "channel_id"
            )

            if not channel_id:
                continue

            gender = (
                seed.get("gender")
                or "미상"
            )

            name = (
                seed.get("name")
                or channel_id
            )

            target_name = (
                f"[{gender}] {name}"
            )

            target_url = (
                "https://www.youtube.com/"
                f"channel/{channel_id}"
            )

            target, created = (
                CrawlTarget.objects
                .update_or_create(
                    source=source,
                    target_type=(
                        CrawlTarget
                        .TargetType
                        .CREATOR
                    ),
                    target_url=target_url,
                    defaults={
                        "name": (
                            target_name
                        ),

                        "collection_mode": (
                            CrawlTarget
                            .CollectionMode
                            .LIVE
                        ),

                        "params": {
                            "channel_id": (
                                channel_id
                            ),

                            "seed": {
                                "name": (
                                    seed.get(
                                        "name"
                                    )
                                ),

                                "gender": (
                                    seed.get(
                                        "gender"
                                    )
                                ),

                                "handle": (
                                    seed.get(
                                        "handle"
                                    )
                                ),

                                "fashion_filter": (
                                    seed.get(
                                        "fashion_filter"
                                    )
                                ),
                            },
                        },

                        "interval_minutes": (
                            1440
                        ),

                        "priority": 5,

                        "is_active": True,
                    },
                )
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "YOUTUBE Target 생성 완료 "
                f"/ created={created_count} "
                f"/ updated={updated_count}"
            )
        )