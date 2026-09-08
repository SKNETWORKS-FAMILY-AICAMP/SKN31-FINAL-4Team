# backend/apps/core/management/commands/setup_youtube_video_targets.py

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import CrawlTarget


DEFAULT_SOURCE_CODE = "YOUTUBE"
DEFAULT_VIDEO_LIMIT = 50


class Command(BaseCommand):
    help = (
        "YOUTUBE CREATOR CrawlTarget의 params에 "
        "collect_videos / video_limit을 설정합니다. "
        "타깃을 새로 만들지 않고 기존 타깃을 그대로 사용합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=DEFAULT_SOURCE_CODE,
            help=(
                "Source.code "
                f"(기본: {DEFAULT_SOURCE_CODE})"
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_VIDEO_LIMIT,
            help=(
                "채널당 수집할 영상 수 "
                f"(기본: {DEFAULT_VIDEO_LIMIT})"
            ),
        )
        parser.add_argument(
            "--target-id",
            type=int,
            default=None,
            help="특정 CrawlTarget 1건만 처리",
        )
        parser.add_argument(
            "--disable",
            action="store_true",
            help="collect_videos를 False로 되돌립니다.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="변경 없이 대상만 출력합니다.",
        )

    def handle(self, *args, **options):
        source_code = options["source"]
        video_limit = max(1, int(options["limit"]))
        target_id = options["target_id"]
        enable = not options["disable"]
        dry_run = options["dry_run"]

        queryset = (
            CrawlTarget.objects
            .select_related("source")
            .filter(
                source__code=source_code,
                target_type=CrawlTarget.TargetType.CREATOR,
            )
            .order_by("id")
        )

        if target_id is not None:
            queryset = queryset.filter(id=target_id)

        targets = list(queryset)

        self.stdout.write(
            f"source={source_code} "
            f"CREATOR 타깃 {len(targets)}건 조회"
        )

        if not targets:
            self.stdout.write(
                self.style.WARNING(
                    "대상 타깃이 없습니다. "
                    "Source.code 대소문자를 확인하세요."
                )
            )
            return

        updated = 0
        skipped = 0

        with transaction.atomic():
            for target in targets:
                params = dict(target.params or {})

                before = (
                    params.get("collect_videos"),
                    params.get("video_limit"),
                )
                after = (enable, video_limit)

                if before == after:
                    skipped += 1
                    continue

                params["collect_videos"] = enable
                params["video_limit"] = video_limit

                if dry_run:
                    self.stdout.write(
                        f"  [dry-run] #{target.id} "
                        f"{target.name} "
                        f"{before} -> {after}"
                    )
                    updated += 1
                    continue

                target.params = params
                target.save(
                    update_fields=[
                        "params",
                        "updated_at",
                    ]
                )
                updated += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f"updated={updated} / "
                f"skipped={skipped} / "
                f"total={len(targets)}"
                + (" (dry-run, 저장하지 않음)" if dry_run else "")
            )
        )
